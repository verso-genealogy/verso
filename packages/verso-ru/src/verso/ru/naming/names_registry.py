"""Data-access layer for the names lexicon — the one place the naming functions ask it.

The lexicon (`verso.ru.naming.lexicon`) is the sum of the workspace's layers (`verso.ru.naming.layers`): for
a workspace of schema ≤ 5 one layer, its three old tables (names.csv + names_ignore.csv +
patronymics_ignore.csv, `[names] dir` in verso.toml) compiled by `verso.ru.naming.legacy`; for one of
schema 6 the shipped base and the layers of `[names] layers` above it. It is
built once per workspace and kept (`current_lexicon`): a change of workspace forgets it, and so
does a changed file — its sources' stamps are looked at again at most every `RECHECK_SECONDS`,
or at once after `reload()`. A workspace with no names.csv is an error at every lookup, never a
silently empty lexicon. `answering(lexicon)` makes every lookup answer from a lexicon the caller
holds, and `asked()` collects the keys the lookups ask — a tool comparing two lexicons question by
question (`verso.ru.naming.oracle`).

The functions here, and the concept modules over them, ask through the lookups below (`_name_facts`,
`_find_old_patronymic_in_table`, …) — so a lookup goes through one place, where `asked()`
sees it, and a test that substitutes `current_lexicon` reaches every reader. They read the
lexicon's indexes themselves rather than through its methods: the corpus asks them some 10⁶
times a translation.
"""

import gc
import threading
from collections.abc import Generator
from contextlib import contextmanager
from time import monotonic

from verso.core import workspace
from verso.ru.gender import Gender
from verso.ru.naming import layers
from verso.ru.naming.lexicon import IdentifiedSource, Lexicon, LayerSource, NameEntry, NameFacts, PatronymicEntry


#: Whether a lookup reports its key: `asked()` collects them — read on the hot paths, where a lookup is asked ~10⁵
#: times a village and no call is made at all while nothing collects.
_tracing = False
_asked: set[tuple[str, str]] | None = None


def _trace(kind: str, key: str) -> None:
    if _asked is not None:
        _asked.add((kind, key))


def _sources() -> list[LayerSource]:
    """The workspace's layers, bottom to top (`LexiconNotConfigured` when it keeps none): a
    workspace of schema ≤ 5 has one, its three old tables; one of schema 6 the base and its layers."""
    return layers.sources(workspace.current())


#: How long a built lexicon is answered from before its sources' stamps are looked at again —
#: a lookup is asked ~10⁵ times a village, a stamp costs a `stat` a file.
RECHECK_SECONDS = 1.0

_held: Lexicon | None = None
_held_sources: list[LayerSource] = []
_held_stamps: tuple[str, ...] = ()
_next_check = 0.0
#: Whether a lexicon is held — the review page's tests ask it after leaving a workspace.
_names_table_loaded = False


def current_lexicon() -> Lexicon:
    """The workspace's lexicon: built on first use, again when the workspace or a source changes."""
    if _held is not None and monotonic() < _next_check:
        return _held
    return _refresh()


def _refresh() -> Lexicon:
    global _held, _held_sources, _held_stamps, _next_check, _names_table_loaded
    held = _held  # a local: another thread's `reload()` may forget the global meanwhile
    sources = _held_sources if held is not None else _sources()
    try:
        stamps = tuple(s.stamp() for s in sources)
    except Exception:
        # A source that cannot say what it holds (its names.csv gone) answers nothing: the
        # lexicon is forgotten, and every lookup until the source is back asks again and fails.
        _forget()
        _next_check = monotonic() + RECHECK_SECONDS
        raise
    if held is None or stamps != _held_stamps:
        # Some 20 000 small tuples at once: a collection every few hundred of them is a tenth
        # of the build, and none of them is garbage.
        held = _built(sources, stamps)
        _held, _held_sources, _held_stamps, _names_table_loaded = held, sources, stamps, True
    _next_check = monotonic() + RECHECK_SECONDS
    return held


#: The lexicons built lately, by what they were built from — each source's identity, and its stamp. Another workspace
#: is another lexicon, but a workspace entered again, or one more over the same base, is the same sum — the base is some
#: ten thousand names, and building the sum is most of what a switch of workspace cost. One lexicon is kept for a set
#: of sources: a lexicon built from the same sources under another stamp can never be asked again and goes when its
#: successor comes. `reload()` keeps none.
_BUILT_KEPT = 8
_built_lexicons: dict[tuple[tuple[object, ...], tuple[str, ...]], Lexicon] = {}
_built_lock = threading.Lock()


def _identity(source: LayerSource) -> object | None:
    """What a source is, apart from what it holds (its stamp): the directory of a layer, the files of the old tables, the
    `identity` a host's source names (`layers.provided`). None for a source that says nothing of the kind — its lexicon is
    never kept."""
    if isinstance(source, IdentifiedSource):
        return ("host", source.name, source.identity)
    directory = getattr(source, "directory", None)
    if directory is not None:
        return ("files", source.name, str(directory))
    files = getattr(source, "files", None)
    if files is not None:
        return ("legacy", source.name, tuple(str(f) for f in files))
    return None


def _built(sources: list[LayerSource], stamps: tuple[str, ...]) -> Lexicon:
    """The lexicon of `sources` (whose stamps are `stamps`), from the lately built ones when they were built from the same."""
    identities = tuple(_identity(s) for s in sources)
    key = (identities, stamps) if None not in identities else None
    if key is not None:
        with _built_lock:
            kept = _built_lexicons.pop(key, None)
            if kept is not None:
                _built_lexicons[key] = kept                     # the most recently asked last
                return kept
    # Some 20 000 small tuples at once: a collection every few hundred of them is a tenth
    # of the build, and none of them is garbage.
    collecting = gc.isenabled()
    gc.disable()
    try:
        # The reverse indexes are built on their first use, each alone: a process that reads names only pays
        # for none of them (`Lexicon.complete()` is the check the build and the linter run).
        built = Lexicon.of([s.load() for s in sources])
    finally:
        if collecting:
            gc.enable()
    if key is not None:
        with _built_lock:
            for stale in [k for k in _built_lexicons if k[0] == identities and k[1] != stamps]:
                _built_lexicons.pop(stale, None)
            _built_lexicons[key] = built
            while len(_built_lexicons) > _BUILT_KEPT:
                _built_lexicons.pop(next(iter(_built_lexicons)), None)
    return built


def _forget() -> None:
    """Forget the lexicon held, so the next lookup asks the sources again — the kept lexicons stay, and are asked
    for the same sources under the same stamps (a switch of workspace)."""
    global _held, _held_sources, _held_stamps, _names_table_loaded
    _held, _held_sources, _held_stamps, _names_table_loaded = None, [], (), False


def reload() -> None:
    """Forget the lexicon, so the next lookup builds it again from its sources — whatever their stamps say.

    For a long-running process that adds a row itself — the review page
    (`verso.app_dsl.service`) adding a name the reader just met — and cannot wait for the
    stamps to be looked at (a rewrite may leave a stamp as it was). A fresh process never needs it.
    """
    with _built_lock:
        _built_lexicons.clear()
    _forget()


def invalidate(identity: object) -> None:
    """The layer of a host that names this `identity` (`IdentifiedSource`) has been written by its host: the lexicon held is
    forgotten, so the next lookup asks the sources' stamps again, and the kept lexicons built from that layer go — the others
    (another project's, the files' of another workspace) stay, which `reload()` does not leave. For a host whose stamp moves
    with every write: a file layer, whose stamp can stand still, is `reload()`'s."""
    with _built_lock:
        for key in [k for k in _built_lexicons
                    if any(isinstance(i, tuple) and i[:1] == ("host",) and i[2:] == (identity,) for i in k[0])]:
            _built_lexicons.pop(key, None)
    _forget()


# Another workspace is another lexicon.
workspace.on_change(_forget)


class _Held:
    """The source of a lexicon `answering()` holds: it never changes."""
    name = "held"
    writable = False

    def stamp(self) -> str:
        return "held"


@contextmanager
def answering(lexicon: Lexicon) -> Generator[Lexicon]:
    """Every lookup answers from `lexicon` until the block ends, whatever the workspace holds — for a
    tool that asks two lexicons the same questions. The workspace's lexicon is back after the block."""
    global _held, _held_sources, _held_stamps, _next_check, _names_table_loaded
    saved = (_held, _held_sources, _held_stamps, _next_check, _names_table_loaded)
    _held, _held_sources, _held_stamps = lexicon, [_Held()], ("held",)  # type: ignore[list-item]
    _next_check, _names_table_loaded = float("inf"), True
    try:
        yield lexicon
    finally:
        _held, _held_sources, _held_stamps, _next_check, _names_table_loaded = saved


@contextmanager
def asked() -> Generator[set[tuple[str, str]]]:
    """The keys the lookups ask until the block ends, as (kind, key): a kind of `name`, `old_m`, `old_f`, `genitive`,
    `modern_m`, `modern_f`, `ignore_name`, `ignore_patronymic`."""
    global _asked, _tracing
    saved = (_asked, _tracing)
    _asked, _tracing = set(), True
    try:
        yield _asked
    finally:
        _asked, _tracing = saved


def is_ignored_name(name: str) -> bool:
    """Whether the old ignore list lists `name` (a name the table leaves out on purpose)."""
    _trace("ignore_name", name)
    return name in current_lexicon().ignored


def ignored_name_gender(name: str) -> Gender | None:
    """The sex the ignore list gives an ignored name (None: not stated)."""
    _trace("ignore_name", name)
    return current_lexicon().ignored.get(name)


def is_ignored_patronymic(patronymic: str) -> bool:
    """Whether the lexicon knows `patronymic` tied to nothing (the old patronymics_ignore.csv)."""
    _trace("ignore_patronymic", patronymic)
    return patronymic in current_lexicon().unattached


def _name_facts(name: str) -> NameFacts | None:
    """What the lexicon holds of a given name — its entries by sex and its forms — or None."""
    if not name:
        return None
    if _tracing:  # the most asked lookup: no call at all while the trace is off
        _trace("name", name)
    return current_lexicon().by_name.get(name)


def _find_name_in_table(name: str) -> list[NameEntry]:
    """The name's entries of a known sex (empty when the lexicon has none). A shim of the
    rows' lookup before 0.1.27, for the callers outside the library; to retire in 0.2."""
    facts = _name_facts(name)
    return list(facts.sexed) if facts is not None else []


def _find_old_patronymic_in_table(old_patronymic: str) -> tuple[PatronymicEntry | None, Gender | None]:
    """The reading of a short (old-form) patronymic — its modern form and father — and the sex
    it is a patronymic of (the men's first), or (None, None) if the lexicon does not know it."""
    if not old_patronymic:
        return None, None
    return _old_reading(current_lexicon(), old_patronymic)


def _old_reading(lexicon: Lexicon, old_patronymic: str) -> tuple[PatronymicEntry | None, Gender | None]:
    """`_find_old_patronymic_in_table` of a lexicon the caller holds (`old_patronymic` not empty)."""
    if _tracing:
        _trace("old_m", old_patronymic)
        _trace("old_f", old_patronymic)
    found = lexicon.old_m.get(old_patronymic)
    if found is not None:
        return found, Gender.MALE
    found = lexicon.old_f.get(old_patronymic)
    if found is not None:
        return found, Gender.FEMALE
    return None, None


def _find_full_patronymic_in_table(patronymic: str) -> tuple[PatronymicEntry | None, Gender | None]:
    """Resolve a *full* patronymic («-ович/-евич/-ич», fem. «-овна/-евна») to the reading of
    the father's short (полуотчество) form — the stamm.

    A full form is one peasant metric books don't use but the gwar.mil.ru WWI
    cards (and noble records) do. We map it back to the registered short form so
    the canonical modern patronymic and gender come out the same as for the short
    input: e.g. «Абрамович» → short «Абрамов» → canonical «Авраамович» (the stamm
    given name Абрам normalises to its church form Авраам).

    Returns `(reading, gender)` like `_find_old_patronymic_in_table`, or `(None, None)`
    when the stamm is unknown (the caller treats that as a hard error).
    """
    if not patronymic:
        return None, None
    return _full_reading(current_lexicon(), patronymic)


def _full_reading(lexicon: Lexicon, patronymic: str) -> tuple[PatronymicEntry | None, Gender | None]:
    """`_find_full_patronymic_in_table` of a lexicon the caller holds (`patronymic` not empty)."""
    p = patronymic
    # Path A: `p` is itself a registered modern patronymic — covers the irregular «-ич»
    # (Кузьмич, Ильич) and any feminine canonical form. Map it to its old form, then look
    # that up.
    old = _short_form(lexicon, p)
    if old:
        return _old_reading(lexicon, old)
    # Path B: regular masculine «-ович/-евич» == <old short М> + "ич".
    if p.endswith(('ович', 'евич')):
        return _old_reading(lexicon, p[:-2])
    # Path C: regular feminine «-овна/-евна» == <old short Ж> with "вна" → "ва".
    if p.endswith(('овна', 'евна')):
        return _old_reading(lexicon, p[:-3] + 'ва')
    return None, None


def feminine_patronymic(patronymic: str) -> str | None:
    """The modern patronymic a patronymic folds onto — the woman's, so a man's and a woman's patronymic of one father
    fold alike: the reading `canonicalize_patronymic` finds (the short form, then a full one through its stamm), and
    for a man's the woman's modern form beside it (`Lexicon.feminine`), else its own modern form. None when the
    lexicon does not know the patronymic, or knows it with no modern form."""
    if not patronymic:
        return None
    found, sex = _find_full_patronymic_in_table(patronymic)
    if found is None:
        return None
    if sex is not Gender.FEMALE:
        if _tracing:  # what `Lexicon.feminine` reads: the forms giving the short form, the woman's short form beside it
            _trace("old_m", found.form)
            _trace("old_f", found.form + "а")
        hers = current_lexicon().feminine(found)
        if hers:
            return hers
    return found.modern


def name_from_genitive(genitive: str) -> str | None:
    """The nominative of a given name from its genitive case, or None if not known.

    The name whose own forms give that genitive; two names giving one genitive answer by
    the canonical one (no bases), then by spelling — never by an order of rows.
    """
    if not genitive:
        return None
    _trace("genitive", genitive)
    return current_lexicon().genitive.get(genitive)


def genitive_from_name(name: str) -> str | None:
    """The genitive-case form of a first name, from the lexicon.

    The inverse of `name_from_genitive`, reading the name's forms. Returns None when
    the name is not in the lexicon (the Mordva / pre-Christian given names of the early
    revisions), leaving the caller to fall back on declension rules.

    A name usually had SEVERAL rows in the old table (orthographic variants, and church
    forms sharing a folk spelling), and their order did not favour the one spelled like
    the input: «Кузьма» carries both «Кузмы» and «Кузьмы», «Семён» carries «Семена»,
    «Семёна» and «Симеона», and «Андриан» leads with its church form's «Адриана». The
    compiled layer keeps the one the stem picks (`verso.ru.naming.legacy`): a candidate that
    starts with the nominative's stem; else one that matches with ё folded to е, its ending
    grafted onto the input's own stem («Парфён» + «Парфена» → «Парфёна»); else the first,
    which is what a fleeting-vowel name needs («Лев» → «Льва», «Павел» → «Павла»).
    """
    facts = _name_facts(name)
    if facts is None:
        return None
    if facts.forms is not None and facts.forms.genitive:
        return facts.forms.genitive
    if facts.derives:
        # A name a layer that writes only the forms the rules do not give holds: its forms as the reverse
        # index reads them (`Lexicon.forms_of`), the man's first, in the sexes that layer holds.
        lexicon = current_lexicon()
        for sex in (Gender.MALE, Gender.FEMALE):
            if sex in facts.derives:
                answered = lexicon.forms_of(sex, name)
                if answered is not None and answered.genitive:
                    return answered.genitive
    return (facts.forms.genitive or None) if facts.forms is not None else None  # "": no such form


def find_old_patronymic_by_modern(modern_patronymic: str) -> str | None:
    """Given a modern patronymic like 'Кузьмич', return the old form like 'Кузьмин'.

    The men's modern forms are asked first, then the women's.
    """
    if not modern_patronymic:
        return None
    return _short_form(current_lexicon(), modern_patronymic)


def _short_form(lexicon: Lexicon, modern_patronymic: str) -> str | None:
    """`find_old_patronymic_by_modern` of a lexicon the caller holds (the key not empty)."""
    if _tracing:
        _trace("modern_m", modern_patronymic)
        _trace("modern_f", modern_patronymic)
    return lexicon.modern_m.get(modern_patronymic) or lexicon.modern_f.get(modern_patronymic)


def father_name_for_patronymic(patronymic: str | None) -> str | None:
    """The father's given name a patronymic points at, by the lexicon.

    The reading is found the way `canonicalize_patronymic` finds it — the short
    (old) form first, then a full «-ович/-овна» form through its stamm — and
    the answer is its father. None when the lexicon does not know the patronymic,
    or it is partly illegible.

    A comparison aid, like `matching_base`, and never written anywhere: it lets
    «Игнатиевна» and «Игнатьевна», «Михайлович» and «Михаилович» — one father
    written two ways — agree, while «Алексеевна» and «Александровна» stay apart.
    """
    if not patronymic or '?' in patronymic:
        return None
    found, _ = _find_old_patronymic_in_table(patronymic)
    if found is None:
        found, _ = _find_full_patronymic_in_table(patronymic)
    if found is None:
        return None
    return found.father or None


def matching_base(name: str | None, gender: Gender | None = None) -> str:
    """The form to compare a name BY — never the form to write it as.

    Deliberately more aggressive than `canonicalize_name`, and the difference is
    the point. `canonicalize_name` must pick one output and keeps a variant that
    is documentary in its own right: «Егоръ» is what the books write and what a
    res_name is built from. Right for generation, wrong for identity — the sweep
    needs «Егоръ Петровъ» of one book and «Георгій Петровъ» of another to be one
    man. So this always prefers the base when the lexicon gives one.

    `gender` picks the entry when known. Without it, a name the lexicon holds in
    both sexes — «Лука» is М on its own and Ж mapping to Гликерия — is left alone
    rather than folded onto one of them at random.
    """
    if not name or '?' in name:
        return name or ""
    facts = _name_facts(name)
    if facts is None:
        return name
    if gender is not None:
        entry = facts.male if gender == Gender.MALE else facts.female
    elif facts.male is not None and facts.female is not None:
        # The name is borne by both sexes and the lexicon sends them different
        # ways. Without a gender there is nothing to choose on, so choose nothing.
        return name
    else:
        entry = facts.male or facts.female
    # No base at all (the name is already canonical), or bases that disagree:
    # either way the safe answer is the name as written.
    return entry.bases[0] if entry is not None and len(entry.bases) == 1 else name
