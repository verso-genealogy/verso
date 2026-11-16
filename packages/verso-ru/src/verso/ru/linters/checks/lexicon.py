"""The names layers' own check, not a DSL one — a layer's three TSV files read in the sum of the layers under it.

The layer is a directory of `verso.ru.naming.layer_files`.

Codes:

* **LEX001** (hard) — a key the lexicon cannot be asked by: not one Cyrillic word (in the base: not one word of the
  Russian alphabet — the Ukrainian «і», the Serbian «ј» are another language's), a stress mark, a stray space,
  a sex other than M, F or empty, no sex on a forms row or on a patronymic tied to a father or a form.
* **LEX002** (hard) — a key written twice in one table of the layer: the layer would answer by the order of
  its rows, which is what the layers exist to end.
* **LEX003** (hard) — a base no layer of the sum holds: `matching_base` would fold onto a name the lexicon does
  not know — a row's own base, or the base of a lower entry a removal row (`-`) takes away; and a pin's father no
  layer holds as a man's name: `father_name_for_patronymic` would answer a name the lexicon does not know.
* **LEX004** — a base that is itself a variant: in the base layer an error (its bases are a fixed point — one
  step of `matching_base` reaches the canonical name), above it advice — a corpus may fold onto its own
  spelling, and a chain there is the corpus's to collapse.
* **LEX005** (advice) — a row that answers as the sum without it does: a name entry the layers under it hold
  alike, a forms cell the rule gives (an upper forms entry replaces the lower one whole, so a cell left empty
  there is the rule's, never the lower layer's), a pin the derivation gives. Redundant, and a later
  change under it would be shadowed.
* **LEX007** (hard) — two names the sum (the layers below, then this layer) derives one short or modern
  patronymic from, which no pin settles: what `Lexicon.complete()` refuses, a lookup at runtime answering it by a
  fixed order. Each is named with its candidates; a pin in `patronymics.tsv` settles it.
* **LEX006** (hard, the base only) — a row of the base whose source is none of `SOURCES`, or that removes a key
  (`-` in bases): the base has no layer under it.

A row with LEX001 or LEX002 is left out of the reading the other codes make.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from verso.ru.gender import Gender
from verso.ru.linters.issue import Issue, Param, issue
from verso.ru.naming.derived import Unpinned, fill
from verso.ru.naming.layer_files import FILES, KEY_COLUMN, SEX, FilesLayer, Table, entry_of, is_base_source, read_rows
from verso.ru.naming.lexicon import (
    IGNORE_LIST, FormsEntry, Layer, Lexicon, LexiconConflict, NameEntry, PatronymicEntry)

_WORD = re.compile("[\u0400-\u04ff]+(?:-[\u0400-\u04ff]+)?")  # one word of the Cyrillic block
#: One word of the Russian alphabet — what a key of the base is (а-я, ё, their capitals).
_RUSSIAN = re.compile("[\u0410-\u044f\u0401\u0451]+(?:-[\u0410-\u044f\u0401\u0451]+)?")
_STRESS = frozenset("̀́")
_ERROR, _WARN = "error", "warn"

#: Each table's line of each key, as the layer was read.
Lines = dict[Table, dict[tuple[Gender | None, str], int]]

#: The forms cells a rule fills in.
_FORM_COLUMNS = ("genitive", "patronymic_m", "patronymic_f", "old_patronymic_m", "old_patronymic_f")


@dataclass(frozen=True)
class Finding:
    """A finding of a layer: the file of its table, and the finding itself (its line, the file's)."""
    file: str
    issue: Issue


def _key_problem(key: str, base: bool) -> str | None:
    if any(c in _STRESS for c in key):
        return "stress"
    if key != key.strip() or any(c.isspace() for c in key):
        return "space"
    if not _WORD.fullmatch(key):
        return "not_cyrillic"
    if base and not _RUSSIAN.fullmatch(key):
        return "not_russian"
    return None


def lint_layer(source: FilesLayer, *, below: Sequence[Layer] = (), base: bool = False) -> list[Finding]:
    """Every finding of the layer `source` read on top of `below` (bottom to top); `base` — the layer is the
    library's base: its bases are a fixed point and its sources are `SOURCES`."""
    found: list[Finding] = []
    entries: list[NameEntry | FormsEntry | PatronymicEntry] = []
    lines: Lines = {}
    for table, rows in read_rows(source.directory).items():
        file, kept = FILES[table], lines.setdefault(table, {})
        first: dict[tuple[str, str], int] = {}
        for line, row in rows:
            key = row[KEY_COLUMN[table]]
            said: tuple[str, str, dict[str, Param]] | None = None
            problem = _key_problem(key, base)
            if problem:
                said = ("LEX001", problem, {})
            elif row["sex"] not in SEX:
                said = ("LEX001", "bad_sex", {"sex": row["sex"]})
            elif row["sex"] == "" and (table == "forms" or (table == "patronymics" and (
                    row["father"] or row["modern"] or row["old"]))):
                said = ("LEX001", "no_sex", {})
            elif (row["sex"], key) in first:
                said = ("LEX002", "duplicate", {"first": first[(row["sex"], key)]})
            else:
                first[(row["sex"], key)] = line
                entry = entry_of(table, row, file=file, line=line)
                if base and isinstance(entry, NameEntry) and entry.removes:
                    said = ("LEX006", "removal", {})  # left out of the reading, as a key it cannot be asked by
                else:
                    kept[entry.key] = line
                    entries.append(entry)
                    if base and not is_base_source(row["source"]):
                        said = ("LEX006", "source", {"source": row["source"]})
            if said is not None:
                code, variant, params = said
                found.append(Finding(file, Issue(code, variant, _ERROR, line, {"key": key, **params}, key)))
    layer = Layer(source.name, {e.key: e for e in entries if isinstance(e, NameEntry)},
                  {e.key: e for e in entries if isinstance(e, FormsEntry)},
                  {e.key: e for e in entries if isinstance(e, PatronymicEntry)}, writable=source.writable,
                  derives=True)
    found += _bases(layer, lines["names"], below, base)
    found += _fathers(layer, lines.get("patronymics", {}), below)
    found += _conflicts(layer, below)
    found += _redundant(layer, lines, below)
    return found


#: How many conflicts `_conflicts` reports before it stops (each one is pinned in its reading to find the next).
_MAX_CONFLICTS = 100


def _conflicts(layer: Layer, below: Sequence[Layer]) -> list[Finding]:
    """LEX007: two derivations of one key the sum (the layers below, then this one) leaves unpinned — what
    `Lexicon.complete()` refuses. Each is pinned in the reading, on its first candidate, to find the next."""
    found: list[Finding] = []
    pins = dict(layer.patronymics)
    while len(found) < _MAX_CONFLICTS:
        reading = Layer(layer.name, layer.names, layer.forms, pins, derives=layer.derives)
        try:
            Lexicon.of([*below, reading]).complete()
            return found
        except LexiconConflict as conflict:
            index, key = conflict.key
            shown = ", ".join(" / ".join(str(p or "—") for p in c) if isinstance(c, tuple) else str(c)
                              for c in conflict.candidates)
            found.append(Finding("patronymics.tsv", issue("LEX007", "conflict", None, level=_ERROR, token=key,
                                                          key=key, index=index, candidates=shown)))
            sex = Gender.MALE if index.endswith("_m") else Gender.FEMALE
            first = conflict.candidates[0]
            if index.startswith("old"):
                modern, father = first  # type: ignore[misc]
                pins[(sex, key)] = PatronymicEntry(sex, key, father or None, modern or None, "lint")
            else:
                pins[(sex, key)] = PatronymicEntry(sex, key, source="lint", old=str(first))
    return found


def _summed_names(layers: Sequence[Layer]) -> dict[tuple[Gender | None, str], NameEntry]:
    out: dict[tuple[Gender | None, str], NameEntry] = {}
    for layer in layers:
        out.update(layer.names)
        for key, entry in layer.names.items():
            if entry.removes:
                del out[key]
    return out


def _bases(layer: Layer, lines: dict[tuple[Gender | None, str], int], below: Sequence[Layer],
           base: bool) -> list[Finding]:
    """LEX003 and LEX004: what each base of the layer is in the sum."""
    names = _summed_names([*below, layer])
    by_name: dict[str, list[NameEntry]] = {}
    for entry in names.values():
        by_name.setdefault(entry.name, []).append(entry)
    found = []
    for key, entry in layer.names.items():
        line = lines[key]
        if entry.removes:
            found += _left_dangling(entry, line, names)
            continue
        for b in entry.bases:
            held = names.get((entry.sex, b)) or names.get((None, b))
            if held is None and entry.sex is None and by_name.get(b):
                held = by_name[b][0]
            if held is None:
                found.append(Finding("names.tsv", issue("LEX003", "unknown_base", line, level=_ERROR, token=entry.name,
                                                        key=entry.name, base=b)))
            elif held.base is not None:
                found.append(Finding("names.tsv", issue("LEX004", "chain", line, level=_ERROR if base else _WARN,
                                                        token=entry.name, key=entry.name, base=b, next=held.base)))
    return found


def _fathers(layer: Layer, lines: dict[tuple[Gender | None, str], int], below: Sequence[Layer]) -> list[Finding]:
    """LEX003 at a pin: a father the sum holds as no man's name (nor as a name of no sex)."""
    names = _summed_names([*below, layer])
    found = []
    for key, pin in layer.patronymics.items():
        if pin.father is not None and (Gender.MALE, pin.father) not in names and (None, pin.father) not in names:
            found.append(Finding("patronymics.tsv", issue("LEX003", "unknown_father", lines.get(key), level=_ERROR,
                                                          token=pin.form, key=pin.form, father=pin.father)))
    return found


def _left_dangling(removal: NameEntry, line: int, names: dict[tuple[Gender | None, str], NameEntry]) -> list[Finding]:
    """LEX003 at a removal row: the entries of the sum (`names`) whose base it removes, a base no layer then holds."""
    found = []
    for entry in names.values():
        if removal.name in entry.bases and entry.sex == removal.sex and (removal.sex, removal.name) not in names \
                and (None, removal.name) not in names:
            found.append(Finding("names.tsv", issue("LEX003", "removed_base", line, level=_ERROR, token=removal.name,
                                                    key=entry.name, base=removal.name)))
    return found


def _answers(entry: NameEntry) -> tuple[object, ...]:
    """What a name entry answers by: its bases, its canonical form, and whether it is of the ignore list — the one
    source with a meaning (`IGNORE_LIST`, which `is_ignored_name` reads)."""
    return (entry.bases, entry.canonical, entry.source == IGNORE_LIST)


def _redundant(layer: Layer, lines: Lines, below: Sequence[Layer]) -> list[Finding]:
    """LEX005: the rows that answer as the sum without them does."""
    found = []
    lower_names = _summed_names(below)
    for key, entry in layer.names.items():
        line = lines["names"][key]
        held = lower_names.get(key)
        if entry.removes:
            if held is None:
                found.append(Finding("names.tsv", issue("LEX005", "removal", line, token=entry.name, key=entry.name)))
        elif held is not None and _answers(held) == _answers(entry):
            found.append(Finding("names.tsv", issue("LEX005", "names", line, token=entry.name, key=entry.name)))
    for key, fe in layer.forms.items():
        line = lines["forms"][key]
        # Without the cell the entry still replaces the lower layer's whole: the cell left empty is what the rules
        # fill in for that sex (a woman's name gives no patronymic), not the lower layer's — redundant only there.
        ruled = fill(None, fe.sex, fe.name)
        for column in _FORM_COLUMNS:
            value = getattr(fe, column)
            if value is None:
                continue
            if value == getattr(ruled, column):
                found.append(Finding("forms.tsv", issue("LEX005", "forms", line, token=fe.name, key=fe.name,
                                                        column=column, value=value)))
    if layer.patronymics:
        # A pin changes no derivation, only which one answers its key: the sum's derivations are built once, and
        # each pin is asked of the sum's pins without it — the lower layers' entry of its key, where one is.
        unpinned = Lexicon.of([*below, layer]).unpinned()
        lower: dict[tuple[Gender | None, str], PatronymicEntry] = {}
        for under in below:
            lower.update(under.patronymics)
        summed = {**lower, **layer.patronymics}
        for key, pin in layer.patronymics.items():
            rest = dict(summed)
            if key in lower:
                rest[key] = lower[key]
            else:
                del rest[key]
            if _pin_redundant(pin, unpinned, rest):
                found.append(Finding("patronymics.tsv", issue("LEX005", "patronymics", lines["patronymics"][key],
                                                              token=pin.form, key=pin.form)))
    return found


def _pin_redundant(pin: PatronymicEntry, unpinned: Unpinned,
                   rest: Mapping[tuple[Gender | None, str], PatronymicEntry]) -> bool:
    """Whether the sum under the pins `rest` — the sum's without this one — answers its key as the pin does."""
    if unpinned.conflicted(rest):
        return False  # the pin settles a conflict
    if pin.is_unattached:
        return any(p.is_unattached and p.form == pin.form for p in rest.values())
    sex = Gender.MALE if pin.sex is Gender.MALE else Gender.FEMALE
    if pin.old is not None:
        return unpinned.modern(sex, pin.form, rest) == pin.old
    derived = unpinned.old(sex, pin.form, rest)
    return derived is not None and (derived.father, derived.modern) == (pin.father, pin.modern)
