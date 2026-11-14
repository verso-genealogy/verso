"""The names lexicon: layers of entries with unique keys, summed into one `Lexicon`.

A layer is three tables, each with a key no two of its entries share:

  * `names` — (sex, name) → the name's bases and the form a res_name is built from;
  * `forms` — (sex, name) → the forms the name takes: its genitive, the patronymics it gives;
  * `patronymics` — (sex, form) → a patronymic the forms do not tie to a father, or a modern
    spelling's short form, or a patronymic known with no father at all.

The layers are read bottom to top, and an entry of an upper layer replaces the lower layer's
entry of ITS key, whole — not every entry of the name: a layer that knows «Лука» only as a man
leaves the woman's «Лука» of the layer below standing. Nothing depends on the order of the
entries inside a layer: every index is built once, here, from the sum, and two answers to one
key that no entry settles are a `LexiconConflict` rather than «the first one read».

The entries are named tuples: immutable, and cheap enough to build that an old table
— some 15 000 of them, with the indexes' readings — compiles in the time it once took to read.

The indexes answer the naming functions (`verso.ru.naming.names_registry` and the modules over
it) and nothing else: a lookup asks `current_lexicon()` there, where the lexicon trace sees it.
`explain()` says which layer and which entry gave an answer.
"""
from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Protocol, runtime_checkable

from verso.ru.gender import Gender
from verso.ru.messages import t

if TYPE_CHECKING:
    from verso.ru.naming.derived import Unpinned

#: The source of a name entry the lexicon knows and leaves out of the table on purpose (the old
#: names_ignore.csv, compiled; a layer writes it as it is). It is the one source with a meaning —
#: `is_ignored_name` and `ignored_name_gender` answer by it — so it is named here, once.
IGNORE_LIST = "ignore"
#: The one base of a name entry that removes its key: «this (sex, name) does not exist in this stack» — the lower
#: layers' entry of that key goes, its forms with it (`-` in a layer's names.tsv, as `NO_FORM` in its forms.tsv).
ABSENT = "-"


class NameEntry(NamedTuple):
    """One (sex, name) of a layer.

    `bases` is empty for a canonical form; several bases are an open conflict, and a name
    compared by them is compared as written. `canonical` is what `canonicalize_name` gives,
    written only where that is not the default — the sole base, else the name (Егор stays
    Егор though its base is Георгий). `sex=None` asserts no sex: a name known with its sex
    unknown, or — beside sexed entries — what the name answers when no sex is given. `bases`
    `(ABSENT,)` (`removes`) holds no name: it takes its key out of the layers below.
    """
    sex: Gender | None
    name: str
    bases: tuple[str, ...] = ()
    canonical: str | None = None
    source: str = ""

    @property
    def key(self) -> tuple[Gender | None, str]:
        return (self.sex, self.name)

    @property
    def removes(self) -> bool:
        """Whether the entry removes its key from the layers below (`ABSENT`) rather than holding a name."""
        return self.bases == (ABSENT,)

    @property
    def base(self) -> str | None:
        """The name's one base, or None: canonical, or bases in conflict."""
        return self.bases[0] if len(self.bases) == 1 else None

    @property
    def canonical_form(self) -> str:
        """What `canonicalize_name` gives for this entry's sex."""
        return self.canonical or (self.bases[0] if len(self.bases) == 1 else self.name)


class FormsEntry(NamedTuple):
    """The forms of one (sex, name); None in a cell means «the rule derives it»."""
    sex: Gender
    name: str
    genitive: str | None = None
    patronymic_m: str | None = None
    patronymic_f: str | None = None
    old_patronymic_m: str | None = None
    old_patronymic_f: str | None = None
    source: str = ""

    @property
    def key(self) -> tuple[Gender, str]:
        return (self.sex, self.name)


class PatronymicEntry(NamedTuple):
    """One (sex, form) of a layer, of three kinds:

      * a short (old) form the forms do not tie to its father — «Абакумов» → father, modern;
      * a modern spelling with `old` set — the short form `find_old_patronymic_by_modern` gives;
      * an unattached form (`is_unattached`): known, with no father, modern or short form.
    """
    sex: Gender | None
    form: str
    father: str | None = None
    modern: str | None = None
    source: str = ""
    old: str | None = None

    @property
    def key(self) -> tuple[Gender | None, str]:
        return (self.sex, self.form)

    @property
    def is_unattached(self) -> bool:
        """A patronymic the lexicon knows and ties to nothing (the old patronymics_ignore.csv)."""
        return self.father is None and self.old is None and self.modern is None


@dataclass(frozen=True, slots=True)
class Layer:
    """Three tables of unique keys, from one source.

    `derived` may hold what `derive_old` / `derive_modern` give of this layer's own names and
    forms — a compiler that had to derive them anyway leaves them there, and a lexicon of this
    layer alone does not derive them again. The tables are not changed once a layer is made.

    `derives`: a name of this layer whose forms leave a cell empty takes that form from the rules
    (`verso.ru.naming.forms`), in the lookups and in the reverse indexes alike — a layer of three
    files writes only the forms the rules do not give. The old names table does not: it was read
    as complete, an empty cell meaning «none», and its answers are kept as they were."""
    name: str
    names: Mapping[tuple[Gender | None, str], NameEntry]
    forms: Mapping[tuple[Gender, str], FormsEntry]
    patronymics: Mapping[tuple[Gender | None, str], PatronymicEntry]
    writable: bool = False
    derived: dict[tuple[str, Gender], dict[str, Any]] = field(default_factory=dict, compare=False, repr=False, kw_only=True)
    derives: bool = field(default=False, kw_only=True)


class LayerSource(Protocol):
    """Where a layer comes from: a directory of tables, the old names.csv, a server's rows.
    `stamp()` changes whenever `load()` would read something else; `put` (an entry's type names
    its table) and `remove` (a table's key) are for a writable source."""
    name: str
    writable: bool

    def load(self) -> Layer: ...

    def stamp(self) -> str: ...

    def put(self, entry: NameEntry | FormsEntry | PatronymicEntry) -> None: ...

    def remove(self, table: Literal["names", "forms", "patronymics"], key: tuple[Gender | None, str]) -> None: ...


@runtime_checkable
class IdentifiedSource(LayerSource, Protocol):
    """A `LayerSource` that says what it is, apart from what it holds: a host's layer (`verso.ru.naming.layers.provided`) names
    its `identity` — hashable, the same for the same layer of the same store — and the registry keeps the lexicon built from it
    between workspaces (`names_registry`), by that identity and its `stamp()`. A source without one is read again each time its
    workspace is entered. The stamp must change with every write, by any process: nothing else tells the registry a kept
    lexicon is stale."""
    identity: Hashable


class LexiconConflict(Exception):
    """Two derivations of one key, and no entry of `patronymics` saying which holds."""

    def __init__(self, key: tuple[str, str], candidates: Iterable[object]) -> None:
        self.key = key
        self.candidates = tuple(sorted(candidates, key=repr))
        super().__init__(str(t("lexicon.conflict", index=key[0], key=key[1],
                               candidates=", ".join(map(_shown, self.candidates)))))


def _shown(candidate: object) -> str:
    if isinstance(candidate, tuple):
        return " / ".join(str(part or "—") for part in candidate)
    return str(candidate)


# --- the derivations, shared by `Lexicon.of` and the compilers of a layer --------------------

#: What a form entry says of a short patronymic: (modern form, father, the entry's source).
OldReading = tuple[str | None, str, str]


def derive_old(names: Mapping[tuple[Gender | None, str], NameEntry],
               forms: Mapping[tuple[Gender, str], FormsEntry],
               sex: Gender) -> dict[str, list[OldReading]]:
    """Each short patronymic of `sex` the forms give, with what each form entry says of it:
    its modern form, and the father — the name's canonical form."""
    out: dict[str, list[OldReading]] = {}
    male = sex is Gender.MALE
    for key, fe in forms.items():
        form = fe.old_patronymic_m if male else fe.old_patronymic_f
        if not form:
            continue
        entry = names.get(key)
        reading = (fe.patronymic_m if male else fe.patronymic_f,
                   entry.canonical_form if entry is not None else fe.name, fe.source)
        held = out.get(form)
        if held is None:
            out[form] = [reading]
        else:
            held.append(reading)
    return out


def pick_old(candidates: Sequence[OldReading]) -> OldReading | None:
    """The one reading the candidates agree on (their sources aside — the first source by
    spelling), or None when they disagree."""
    if len(candidates) == 1:
        return candidates[0]
    if len({(modern, father) for modern, father, _ in candidates}) > 1:
        return None
    return min(candidates, key=lambda c: c[2])


def regular_short_form(modern: str, sex: Gender) -> str | None:
    """The short form a regular modern patronymic is built on: «-ович/-евич» less «ич»,
    «-овна/-евна» with «вна» → «ва». None for an irregular one (Кузьмич, Ильинична)."""
    if sex is Gender.MALE:
        return modern[:-2] if modern.endswith(("ович", "евич")) else None
    return modern[:-3] + "ва" if modern.endswith(("овна", "евна")) else None


def derive_modern(forms: Mapping[tuple[Gender, str], FormsEntry], sex: Gender) -> dict[str, set[str]]:
    """Each modern patronymic of `sex` the forms give, with the short forms given beside it."""
    out: dict[str, set[str]] = {}
    male = sex is Gender.MALE
    for fe in forms.values():
        modern = fe.patronymic_m if male else fe.patronymic_f
        old = fe.old_patronymic_m if male else fe.old_patronymic_f
        if modern and old:
            out.setdefault(modern, set()).add(old)
    return out


def pick_modern(modern: str, sex: Gender, candidates: set[str]) -> str | None:
    """The short form of `modern`: the only one given, else the regular one among them, else
    None (they disagree)."""
    if len(candidates) == 1:
        return next(iter(candidates))
    regular = regular_short_form(modern, sex)
    return regular if regular in candidates else None


def derive_genitive(names: Mapping[tuple[Gender | None, str], NameEntry],
                    forms: Mapping[tuple[Gender, str], FormsEntry]) -> dict[str, str]:
    """Each genitive the forms give → the name it is the genitive of. Several names giving one
    genitive is no conflict: the canonical name answers (no bases), then the first by spelling."""
    out: dict[str, str] = {}
    shared: dict[str, set[FormsEntry]] = {}
    first: dict[str, FormsEntry] = {}
    for fe in forms.values():
        g = fe.genitive
        if not g:
            continue
        held = first.get(g)
        if held is None:
            first[g] = fe
            out[g] = fe.name
        elif held.name != fe.name:
            shared.setdefault(g, {held}).add(fe)
    for g, entries in shared.items():
        out[g] = min((bool((e := names.get(fe.key)) and e.bases), fe.name) for fe in entries)[1]
    return out


def _key_order(key: tuple[Gender | None, str]) -> tuple[str, str]:
    """A key's place in a fixed order: the sex (men first), then the name."""
    return ("" if key[0] is None else "0" if key[0] is Gender.MALE else "1", key[1])


# --- the sum ---------------------------------------------------------------------------------

class NameFacts(NamedTuple):
    """What the lexicon holds of one written name: its entries by sex, and its own forms. `derives`: the
    sexes of the name a deriving layer (`Layer.derives`) holds — for those, a form its forms leave empty is
    the rules' (`Lexicon.forms_of`)."""
    male: NameEntry | None
    female: NameEntry | None
    unsexed: NameEntry | None
    forms: FormsEntry | None
    derives: frozenset[Gender] = frozenset()

    @property
    def sexed(self) -> tuple[NameEntry, ...]:
        return tuple(e for e in (self.male, self.female) if e is not None)


_REMOVAL = (ABSENT,)

#: The reverse indexes, each built on its first use (`Lexicon.__getattr__`), or all at once, checked, by `complete()`.
_REVERSE = ("old_m", "old_f", "modern_m", "modern_f", "genitive")
_NO_SEX: frozenset[Gender] = frozenset()

_KINDS = ("name", "forms", "old_m", "old_f", "modern_m", "modern_f", "genitive", "ignore_name",
          "ignore_patronymic")


class Lexicon:
    """The sum of the layers, indexed once. Immutable: a changed layer is a new `Lexicon`."""

    __slots__ = (
        "_answered",
        "_cached",
        "_checked",
        "_deriving",
        "_forms",
        "_layers",
        "_names",
        "_patronymics",
        "_sources",
        "by_name",
        "genitive",
        "ignored",
        "layers",
        "modern_f",
        "modern_m",
        "old_f",
        "old_m",
        "unattached",
    )

    def __init__(self, layers: Sequence[Layer] = ()) -> None:
        """The layers summed, bottom to top (`Lexicon.of`). The indexes — `by_name`, `old_m`,
        `old_f`, `modern_m`, `modern_f`, `genitive`, `ignored`, `unattached` — are read by the
        lookups below and, on its hot path, by `names_registry`; nothing writes them."""
        self._layers = tuple(layers)
        self.layers: tuple[str, ...] = tuple(layer.name for layer in self._layers)
        self._names: dict[tuple[Gender | None, str], NameEntry] = {}
        self._forms: dict[tuple[Gender, str], FormsEntry] = {}
        self._patronymics: dict[tuple[Gender | None, str], PatronymicEntry] = {}
        for layer in self._layers:
            if len(self._layers) > 1:
                self._drop_unsexed_below(layer)
            self._names.update(layer.names)
            self._forms.update(layer.forms)
            for key, entry in layer.names.items():
                if entry.bases == _REMOVAL:  # the key goes, its forms with it — nothing else of the name
                    del self._names[key]
                    if key[0] is not None:
                        self._forms.pop(key, None)  # type: ignore[arg-type]
            for entry in layer.patronymics.values():
                if entry.sex is None and not entry.is_unattached:
                    # Only a form tied to nothing has no sex: a father, a modern or a short form
                    # is a man's or a woman's patronymic, and the index it would go to is the sex's.
                    raise ValueError(str(t("lexicon.unsexed_patronymic", form=entry.form, layer=layer.name)))
            self._patronymics.update(layer.patronymics)
        self._sources: dict[str, list[FormsEntry]] | None = None  # `feminine`'s: a man's short form → its forms
        self.by_name: dict[str, NameFacts] = {}
        self.ignored: dict[str, Gender | None] = {}
        from verso.ru.naming.derived import deriving_keys
        self._deriving = deriving_keys(self._layers, self._names)
        self._index_names()
        self._answered: dict[tuple[Gender, str], FormsEntry] | None = None if self._deriving else self._forms
        self._cached: Mapping[tuple[str, Gender], dict[str, Any]] | None = (
            self._layers[0].derived if len(self._layers) == 1 else None)
        self._checked = False
        self.unattached = frozenset(p.form for p in self._patronymics.values() if p.is_unattached)

    def _answered_forms(self) -> dict[tuple[Gender, str], FormsEntry]:
        """The forms summed, every empty cell of a deriving layer's name the rule's — what the reverse indexes
        read; filled once, on the first reverse lookup."""
        if self._answered is None:
            from verso.ru.naming.derived import fill_by_rule
            self._answered = fill_by_rule(self._forms, self._deriving)
        return self._answered

    def _reverse(self, index: str, *, strict: bool) -> Any:
        from verso.ru.naming.derived import reverse_index
        return reverse_index(index, self._names, self._answered_forms(), self._patronymics, self._cached,
                             strict=strict)

    def __getattr__(self, name: str) -> Any:
        """A reverse index on its first use: built then, that index alone (`verso.ru.naming.derived`). Two names
        the rules give one key are answered by a fixed order here, never refused — refusing them is
        `complete()`'s, the check the build and the linter run."""
        if name in _REVERSE:
            value = self._reverse(name, strict=False)
            object.__setattr__(self, name, value)
            return value
        raise AttributeError(name)

    def complete(self) -> Lexicon:
        """This lexicon checked: every reverse index built, raising `LexiconConflict` where two derivations of one
        key are left unpinned — the check the base's build, the layers' linter (LEX007) and `verso names layer-diff`
        run. A runtime loader does not call it: an index it asks is built on first use."""
        if not self._checked:
            for index in _REVERSE:
                object.__setattr__(self, index, self._reverse(index, strict=True))
            self._checked = True
        return self

    def unpinned(self) -> Unpinned:
        """What the reverse indexes derive of this sum's names and forms before any pin, to be asked under other pins
        than the sum's (`verso.ru.naming.derived.Unpinned`) — the sum without one pin, asked once a pin, needs no
        lexicon of its own."""
        from verso.ru.naming.derived import Unpinned
        return Unpinned(self._names, self._answered_forms(), self._cached)

    def forms_of(self, sex: Gender, name: str) -> FormsEntry | None:
        """The forms (sex, name) answers by: the layers' own, every empty cell the rule's where a deriving
        layer holds the key — what the reverse indexes read."""
        fe = self._forms.get((sex, name))
        if (sex, name) not in self._deriving:
            return fe
        from verso.ru.naming.derived import fill
        return fill(fe, sex, name)

    def _drop_unsexed_below(self, layer: Layer) -> None:
        """A layer that holds a name and no (None, name) entry of its own drops the lower layers'
        one: what the name answers without a sex is then derived over the entries summed, not
        pinned against sexed entries the layer has just replaced."""
        if not self._names:
            return
        for (sex, name), entry in layer.names.items():
            if sex is not None and (None, name) not in layer.names and entry.bases != _REMOVAL:
                self._names.pop((None, name), None)

    @classmethod
    def of(cls, layers: Sequence[Layer]) -> Lexicon:
        """The layers summed, bottom to top: an upper entry replaces the lower one of its key."""
        return cls(layers)

    def with_layer(self, layer: Layer) -> Lexicon:
        """This lexicon with `layer` on top."""
        return Lexicon.of([*self._layers, layer])

    def _index_names(self) -> None:
        names, forms = self._names, self._forms
        male, female = Gender.MALE, Gender.FEMALE
        # A name's own forms — the man's entry, else the woman's — read off the forms (a few) rather than asked of
        # them name by name (some ten thousand).
        own: dict[str, FormsEntry] = {}
        for (sex, name), fe in forms.items():
            if sex is male or name not in own:
                own[name] = fe
        every = all(layer.derives for layer in self._layers)
        deriving: dict[str, frozenset[Gender]] = {}
        if not every:
            for sex, name in self._deriving:
                deriving[name] = deriving.get(name, frozenset()) | {sex}
        both, men, women = frozenset((male, female)), frozenset((male,)), frozenset((female,))
        grouped: dict[str, list[NameEntry | None]] = {}
        ignored: dict[str, set[Gender | None]] = {}
        for (sex, name), entry in names.items():
            slots = grouped.get(name)
            if slots is None:
                slots = grouped[name] = [None, None, None]
            slots[0 if sex is male else 1 if sex is female else 2] = entry
            if entry.source == IGNORE_LIST:
                ignored.setdefault(name, set()).add(sex)
        for _, name in forms:
            if name not in grouped:
                grouped[name] = [None, None, None]
        new = tuple.__new__
        get = own.get
        if every:  # a stack of layers: a base no layer holds is no base — the name is compared as written
            self._drop_dangling_bases(grouped)
        for name, (m, f, u) in grouped.items():
            if every:  # every layer derives: a name derives in each sex it holds — but an ignored one (`IGNORE_LIST`)
                m_derives = m is not None and m.source != IGNORE_LIST
                f_derives = f is not None and f.source != IGNORE_LIST
                sexes = (both if f_derives else men) if m_derives else women if f_derives else _NO_SEX
            else:
                sexes = deriving.get(name, _NO_SEX)
            self.by_name[name] = new(NameFacts, (m, f, u, get(name), sexes))
        self.ignored = {name: next(iter(s)) if len(s) == 1 else None for name, s in ignored.items()}

    @staticmethod
    def _drop_dangling_bases(grouped: dict[str, list[NameEntry | None]]) -> None:
        """The entries of `grouped` (a name's male, female and unsexed entry) whose one base no entry holds — in the
        entry's sex or with none — made canonical: a layer written over a base that a later release dropped still loads
        (the linter says LEX003), and its variant answers as a name without a base, as written. The entries of
        `names` are not changed: `explain` still shows the base the layer wrote."""
        for slots in grouped.values():
            for slot, entry in enumerate(slots):
                if entry is None or len(entry.bases) != 1 or entry.bases == _REMOVAL:
                    continue
                held = grouped.get(entry.bases[0])
                if held is None:
                    known = False
                elif slot == 2:
                    known = any(e is not None for e in held)
                else:
                    known = held[slot] is not None or held[2] is not None
                if not known:
                    slots[slot] = entry._replace(bases=())

    # --- the lookups the naming functions ask ---

    def name(self, name: str) -> NameFacts | None:
        return self.by_name.get(name)

    def old_patronymic(self, form: str) -> PatronymicEntry | None:
        """The short form's reading: the men's first, as the two columns were always read."""
        return self.old_m.get(form) or self.old_f.get(form)

    def feminine(self, reading: PatronymicEntry) -> str | None:
        """The woman's modern patronymic beside a man's reading of a short form, by the reading's own entry: the
        father's forms that give the short form and the reading's own modern patronymic — their woman's
        patronymic —, else the woman's reading of the woman's short form beside it («-ов» → «-ова», «-ин» →
        «-ина») for the same father, else the father's forms giving the short form with another modern one; None
        when the lexicon holds none of them. Of several forms entries, the first by key. Nothing here reads an entry's source: a layer whose every entry names one source
        answers as one that names a row each."""
        if self._sources is None:
            answered = self._answered_forms()
            by_form: dict[str, list[FormsEntry]] = {}
            for key in sorted(answered, key=_key_order):
                fe = answered[key]
                if fe.sex is Gender.MALE and fe.old_patronymic_m:
                    by_form.setdefault(fe.old_patronymic_m, []).append(fe)
            self._sources = by_form
        father = reading.father

        def fathers(fe: FormsEntry) -> bool:
            entry = self._names.get(fe.key)
            return (entry.canonical_form if entry is not None else fe.name) == father

        candidates = [fe for fe in self._sources.get(reading.form, ()) if fathers(fe)]
        own = [fe for fe in candidates if fe.patronymic_m == reading.modern]
        for fe in own:
            if fe.patronymic_f:
                return fe.patronymic_f
        hers = self.old_f.get(reading.form + "а")
        if hers is not None and hers.father == father:
            return hers.modern
        return next((fe.patronymic_f for fe in candidates if fe.patronymic_f), None)

    def short_form(self, modern: str) -> str | None:
        """The short form of a modern patronymic: the men's first."""
        return self.modern_m.get(modern) or self.modern_f.get(modern)

    # --- what gave an answer ---

    def explain(self, kind: str, key: str) -> list[tuple[str, NameEntry | FormsEntry | PatronymicEntry]]:
        """Which layer and which entry gave the answer of index `kind` to `key` (`kind` is a
        lexicon trace kind: name, forms, old_m, old_f, modern_m, modern_f, genitive,
        ignore_name, ignore_patronymic). A derived answer lists every entry it was derived
        from; an empty list — the lexicon does not know the key."""
        if kind not in _KINDS:
            raise ValueError(str(t("lexicon.unknown_kind", kind=kind, kinds=", ".join(_KINDS))))
        answered = self._answered_forms()
        out: list[tuple[str, NameEntry | FormsEntry | PatronymicEntry]] = []

        def add(table: str, entry: NameEntry | FormsEntry | PatronymicEntry) -> None:
            layer = next((layer for layer in reversed(self._layers)
                          if getattr(layer, table).get(entry.key) is entry), None)
            if layer is None:  # forms the rules filled in: the layer of the name's entry, which derives
                layer = next(layer for layer in reversed(self._layers) if entry.key in layer.names)
            out.append((layer.name, entry))

        if kind in ("name", "ignore_name"):
            for entry in self._names.values():
                if entry.name == key and (kind == "name" or entry.source == IGNORE_LIST):
                    add("names", entry)
        elif kind == "forms":
            for entry in self._forms.values():
                if entry.name == key:
                    add("forms", entry)
        elif kind == "ignore_patronymic":
            for entry in self._patronymics.values():
                if entry.form == key and entry.is_unattached:
                    add("patronymics", entry)
        elif kind == "genitive":
            for entry in answered.values():
                if entry.genitive == key:
                    add("forms", entry)
        else:
            sex = Gender.MALE if kind.endswith("_m") else Gender.FEMALE
            modern = kind.startswith("modern")
            pin = self._patronymics.get((sex, key))
            if pin is not None and (pin.old is not None) == modern and not pin.is_unattached:
                add("patronymics", pin)
                return out
            male = sex is Gender.MALE
            for entry in answered.values():
                cell = ((entry.patronymic_m if male else entry.patronymic_f) if modern
                        else (entry.old_patronymic_m if male else entry.old_patronymic_f))
                if cell == key and (not modern or (entry.old_patronymic_m if male else entry.old_patronymic_f)):
                    add("forms", entry)
        return out
