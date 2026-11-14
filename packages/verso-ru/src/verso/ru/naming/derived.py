"""What the lexicon derives from the layers summed: the rules' forms of a deriving layer's names, and the
reverse indexes — a short or modern patronymic, a genitive, back to the name that gives it.

A layer that derives (`Layer.derives`) writes only the forms the rules (`verso.ru.naming.forms`) do not
give; every cell it leaves empty is the rule's, for each (sex, name) the layer holds: a genitive to every
name, the patronymics to a man's name (a father). `fill` gives one key's forms so, `fill_by_rule` every
key's; the forward lookups ask `Lexicon.forms_of`, the reverse indexes read `fill_by_rule`'s forms — so
the two never disagree on which (sex, name) a rule answers for.

`reverse_index` builds one of the five, a pin of the layers' `patronymics` winning over the derivation of
its key. A lexicon builds each on its first use (`Lexicon.__getattr__`), answering two derivations of one
key left unpinned by a fixed order; `Lexicon.complete()` builds them all with `strict`, raising
`LexiconConflict` there instead — the check the base's build, the layers' linter (LEX007) and `verso names
layer-diff` run. A lexicon that only reads names pays nothing for them.

The module imports `verso.ru.naming.lexicon` (the entries, the derivations), and the lexicon imports it
inside its methods.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from verso.ru.gender import Gender
from verso.ru.naming import forms as rules
from verso.ru.naming.lexicon import (
    IGNORE_LIST, FormsEntry, Layer, LexiconConflict, NameEntry, PatronymicEntry, derive_genitive, derive_modern, derive_old,
    pick_modern, pick_old)

_MALE, _FEMALE = Gender.MALE, Gender.FEMALE


def fill(fe: FormsEntry | None, sex: Gender, name: str) -> FormsEntry:
    """The forms of (sex, name) with every cell not set (None) the rule's; a cell set to "" — no such form, `-` in
    a layer's file — stays empty. The entry is named after its name (`source#name`, `rule#name`), so two of them
    are never one source."""
    cells = fe[2:7] if fe is not None else (None,) * 5
    genitive = rules.genitive(name, sex) if cells[0] is None else cells[0]
    if sex is _MALE:
        filled = (genitive,
                  rules.modern_patronymic(name, _MALE) if cells[1] is None else cells[1],
                  rules.modern_patronymic(name, _FEMALE) if cells[2] is None else cells[2],
                  rules.old_patronymic(name, _MALE) if cells[3] is None else cells[3],
                  rules.old_patronymic(name, _FEMALE) if cells[4] is None else cells[4])
    else:
        filled = (genitive, *cells[1:])
    source = f"{fe.source if fe is not None else 'rule'}#{name}"
    return tuple.__new__(FormsEntry, (sex, name, *filled, source))  # type: ignore[arg-type]


def deriving_keys(layers: Sequence[Layer],
                  names: Mapping[tuple[Gender | None, str], NameEntry]) -> frozenset[tuple[Gender, str]]:
    """Every (sex, name) of the sum a deriving layer holds — but a name of the ignore list (`IGNORE_LIST`): known, and
    not validated, so no rule gives it a form."""
    return frozenset(key for layer in layers if layer.derives for key in layer.names  # type: ignore[misc]
                     if key[0] is not None and key in names and names[key].source != IGNORE_LIST)


def fill_by_rule(forms: Mapping[tuple[Gender, str], FormsEntry],
                 keys: frozenset[tuple[Gender, str]]) -> dict[tuple[Gender, str], FormsEntry]:
    """The forms summed, each of `keys` filled by the rules — a key's filling kept for the next lexicon of this process
    (`_FILLED`: the same entry, sex and name fill alike; a tool that sums one base with many layers fills it once)."""
    answered = dict(forms)
    cache = _FILLED
    if len(cache) > _FILLED_MAX:
        cache.clear()
    get = forms.get
    for key in keys:
        fe = get(key)
        held = cache.get((fe, key))
        if held is None:
            held = cache[(fe, key)] = fill(fe, key[0], key[1])
        answered[key] = held
    return answered


#: `fill_by_rule`'s fillings, by (the forms entry or None, its key); cleared past `_FILLED_MAX`.
_FILLED: dict[tuple[FormsEntry | None, tuple[Gender, str]], FormsEntry] = {}
_FILLED_MAX = 200_000


def reverse_index(index: str, names: Mapping[tuple[Gender | None, str], NameEntry],
                  forms: Mapping[tuple[Gender, str], FormsEntry],
                  patronymics: Mapping[tuple[Gender | None, str], PatronymicEntry],
                  cached: Mapping[tuple[str, Gender], dict[str, Any]] | None = None, *, strict: bool) -> Any:
    """One reverse index over `forms` — `old_m`, `old_f` (a short patronymic → its reading), `modern_m`, `modern_f`
    (a modern one → its short form) or `genitive` (→ the name); `cached` — a compiler's own `derive_old` /
    `derive_modern` of the same forms (`Layer.derived`), read in their place. `strict`: two derivations of one key
    left unpinned are a `LexiconConflict`; else the first of them by spelling answers."""
    if index == "genitive":
        return derive_genitive(names, forms)
    kind, sex = index.split("_")[0], _MALE if index.endswith("_m") else _FEMALE
    if cached is not None and (kind, sex) in cached:
        derived = cached[(kind, sex)]
    else:
        derived = derive_old(names, forms, sex) if kind == "old" else derive_modern(forms, sex)
    if kind == "old":
        return _old_index(derived, patronymics, sex, strict)
    return _modern_index(derived, patronymics, sex, strict)


def _suffix(sex: Gender) -> str:
    return "m" if sex is _MALE else "f"


def _old_index(derived: dict[str, Any], patronymics: Mapping[tuple[Gender | None, str], PatronymicEntry],
               sex: Gender, strict: bool) -> dict[str, PatronymicEntry]:
    pinned = {p.form: p for p in patronymics.values() if p.sex is sex and p.old is None and not p.is_unattached}
    index: dict[str, PatronymicEntry] = {}
    for form, candidates in derived.items():
        if form in pinned:
            continue
        picked = pick_old(candidates)
        if picked is None:
            if strict:
                raise LexiconConflict((f"old_{_suffix(sex)}", form), [c[:2] for c in candidates])
            picked = min(candidates, key=lambda c: (c[1], c[0] or "", c[2]))
        index[form] = tuple.__new__(PatronymicEntry, (sex, form, picked[1], picked[0], picked[2], None))
    index.update(pinned)
    return index


def _modern_index(derived: dict[str, Any], patronymics: Mapping[tuple[Gender | None, str], PatronymicEntry],
                  sex: Gender, strict: bool) -> dict[str, str]:
    pinned = {p.form: p.old for p in patronymics.values() if p.sex is sex and p.old is not None}
    index: dict[str, str] = {}
    for modern, candidates in derived.items():
        if modern in pinned:
            continue
        short = pick_modern(modern, sex, candidates)
        if short is None:
            if strict:
                raise LexiconConflict((f"modern_{_suffix(sex)}", modern), candidates)
            short = min(candidates)
        index[modern] = short
    index.update(pinned)  # type: ignore[arg-type] — `old` is set on each
    return index


class Unpinned:
    """The derivations `reverse_index` reads of one sum's names and forms, before any pin — the same under every
    set of pins over them, since a pin only says which derivation answers its key. Built once, they answer what the
    reverse indexes would under any `patronymics` without building one: the layers' linter asks once a pin whether
    the sum without it answers alike (LEX005).

    `patronymics` is keyed as a layer's table is, by each entry's (sex, form): the one entry an index reads at a
    form is the one of that key."""

    def __init__(self, names: Mapping[tuple[Gender | None, str], NameEntry],
                 forms: Mapping[tuple[Gender, str], FormsEntry],
                 cached: Mapping[tuple[str, Gender], dict[str, Any]] | None = None) -> None:
        self._derived: dict[tuple[str, Gender], dict[str, Any]] = {}
        self._open: list[tuple[str, Gender, str]] = []  # (kind, sex, form): derivations no pin aside agrees on
        for kind in ("old", "modern"):
            for sex in (_MALE, _FEMALE):
                derived: dict[str, Any]
                if cached is not None and (kind, sex) in cached:
                    derived = cached[(kind, sex)]
                else:
                    derived = derive_old(names, forms, sex) if kind == "old" else derive_modern(forms, sex)
                self._derived[(kind, sex)] = derived
                for form, candidates in derived.items():
                    if (pick_old(candidates) if kind == "old" else pick_modern(form, sex, candidates)) is None:
                        self._open.append((kind, sex, form))

    def conflicted(self, patronymics: Mapping[tuple[Gender | None, str], PatronymicEntry]) -> bool:
        """Whether `reverse_index(strict=True)` refuses any of the four patronymic indexes under `patronymics`."""
        get = patronymics.get
        return any(_pin_of(kind, get((sex, form))) is None for kind, sex, form in self._open)

    def old(self, sex: Gender, form: str,
            patronymics: Mapping[tuple[Gender | None, str], PatronymicEntry]) -> PatronymicEntry | None:
        """What `old_m` / `old_f` answer for `form` under `patronymics`; under a conflict, the strict index's — none
        is built (ask `conflicted` first)."""
        pinned = _pin_of("old", patronymics.get((sex, form)))
        if pinned is not None:
            return pinned  # type: ignore[return-value]
        candidates = self._derived[("old", sex)].get(form)
        picked = pick_old(candidates) if candidates is not None else None
        if picked is None:
            return None
        return tuple.__new__(PatronymicEntry, (sex, form, picked[1], picked[0], picked[2], None))

    def modern(self, sex: Gender, form: str,
               patronymics: Mapping[tuple[Gender | None, str], PatronymicEntry]) -> str | None:
        """What `modern_m` / `modern_f` answer for `form` under `patronymics` (ask `conflicted` first)."""
        pinned = _pin_of("modern", patronymics.get((sex, form)))
        if pinned is not None:
            return pinned  # type: ignore[return-value]
        candidates = self._derived[("modern", sex)].get(form)
        return pick_modern(form, sex, candidates) if candidates is not None else None


def _pin_of(kind: str, entry: PatronymicEntry | None) -> PatronymicEntry | str | None:
    """What a pin says in an index of `kind`, as `_old_index` and `_modern_index` read it: a short form's reading, a
    modern form's short one; None when the entry is no pin of that index."""
    if entry is None:
        return None
    if kind == "old":
        return entry if entry.old is None and not entry.is_unattached else None
    return entry.old
