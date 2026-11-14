"""The old names table compiled into one layer: names.csv + names_ignore.csv + patronymics_ignore.csv.

The old table answered by row order — every index was built «first row wins» — and that is
resolved HERE, once, index by index exactly as `names_registry` built it before 0.1.27 (the
second pass over the modern patronymics included). What comes out is a `Layer` whose answers
need no order: every one of them is written down where the lexicon's own derivation would give
another —

  * `canonical` on a name entry where `canonicalize_name` is not the sole base or the name
    (with a sex: the first row's base; without one: an entry keyed (None, name));
  * an entry of `patronymics` for each short form whose first row is not what the forms
    derive, and for each modern form whose short form the forms and the regular rule do not
    give (`old` set);
  * the forms of a name are those of its first row, and its genitive the one the old lookup
    picked by stem; they sit on the man's key when the name has one, as the father's.

The genitive → name index is the one the lexicon derives (`derive_genitive`): no question of
the corpus asks it, and a genitive two names share was settled by row order alone.
"""
from __future__ import annotations

import csv
import os
from collections.abc import Callable, Iterable
from operator import attrgetter, itemgetter
from pathlib import Path
from typing import Any, Literal, NamedTuple

from verso.core import workspace
from verso.ru.gender import Gender
from verso.ru.messages import t
from verso.ru.naming.lexicon import (
    IGNORE_LIST, FormsEntry, Layer, NameEntry, OldReading, PatronymicEntry, derive_modern, derive_old, pick_modern,
    pick_old)

#: The source of an entry compiled from the old patronymics_ignore.csv (an unattached patronymic is one by its
#: shape, whatever its source says).
PATRONYMICS_IGNORE_LIST = "ignore"

# The columns the old lookups read (the others — «От», «Склонения, связи», «Источник» — no code
# ever did).
_COLUMNS = ("Пол", "Имя", "Имя-основа", "Родительный падеж", "Отчество старое М", "Отчество старое Ж",
            "Отчество М", "Отчество Ж")
_SEX = {"М": Gender.MALE, "Ж": Gender.FEMALE}


class _Row(NamedTuple):
    line: int
    sex: str  # «М» or «Ж», as written (`_SEX` reads it)
    name: str
    base: str
    genitive: str
    old_m: str
    old_f: str
    modern_m: str
    modern_f: str

    @property
    def father(self) -> str:
        return self.base or self.name


_Cell = Callable[["_Row"], str]


class _Table(NamedTuple):
    """The old table as its lookups read it: the rows by name, in file order, and the row each
    patronymic index answered a key by — the men's and the women's:

      * a short form → its first row;
      * a modern form → the first row giving it with a short form, overridden — the old second
        pass — by the first such CANONICAL row (no «Имя-основа»)."""
    by_name: dict[str, list[_Row]]
    old_m: dict[str, _Row]
    old_f: dict[str, _Row]
    modern_m: dict[str, _Row]
    modern_f: dict[str, _Row]


def _read(path: Path) -> _Table:
    """The table, in one pass of `csv.reader`. «Пол» and «Имя» are read without the spaces
    around them, as the table's linter reads them; a row with no name or a sex other than М/Ж
    is then refused: the old lookups read such a row in some indexes and not in others."""
    by_name: dict[str, list[_Row]] = {}
    old_m: dict[str, _Row] = {}
    old_f: dict[str, _Row] = {}
    modern_m: dict[str, _Row] = {}
    modern_f: dict[str, _Row] = {}
    canonical_m: dict[str, _Row] = {}
    canonical_f: dict[str, _Row] = {}
    new = tuple.__new__
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        try:
            at = [header.index(column) for column in _COLUMNS]
        except ValueError:
            raise workspace.WorkspaceError(t("legacy.no_column", path=path)) from None
        cells_of = itemgetter(*at)
        width = max(at) + 1
        for cells in reader:
            if len(cells) < width:
                if not any(cells):
                    continue
                cells = cells + [""] * (width - len(cells))
            values = cells_of(cells)
            sex, name, base, _, o_m, o_f, m_m, m_f = values
            if sex not in _SEX or name.strip() != name:
                # «М » is «М» and « Иван» is «Иван», as the table's linter reads them (NCSV005/006).
                sex, name = sex.strip(), name.strip()
                values = (sex, name, *values[2:])
            if not name or sex not in _SEX:
                raise workspace.WorkspaceError(t("legacy.bad_row", path=path, line=reader.line_num))
            r: _Row = new(_Row, (reader.line_num, *values))
            held = by_name.get(name)
            if held is None:
                by_name[name] = [r]
            else:
                held.append(r)
            if o_m:
                old_m.setdefault(o_m, r)
                if m_m:
                    modern_m.setdefault(m_m, r)
                    if not base:
                        canonical_m.setdefault(m_m, r)
            if o_f:
                old_f.setdefault(o_f, r)
                if m_f:
                    modern_f.setdefault(m_f, r)
                    if not base:
                        canonical_f.setdefault(m_f, r)
    modern_m.update(canonical_m)
    modern_f.update(canonical_f)
    return _Table(by_name, old_m, old_f, modern_m, modern_f)


def _genitive(name: str, rows: Iterable[_Row]) -> str | None:
    """The genitive the old lookup gave a name, of these rows: the first that starts with the
    name's stem, else one that does with ё read as е (its ending on the name's own stem), else
    the first — the order the rows stand in."""
    candidates = [r.genitive for r in rows if r.genitive]
    if not candidates:
        return None
    stem = name[:-1]
    for g in candidates:
        if g.startswith(stem):
            return g
    folded = stem.replace("ё", "е")
    for g in candidates:
        if g.replace("ё", "е").startswith(folded):
            return stem + g[len(stem):]
    return candidates[0]


def _read_ignored_names(path: Path | None) -> dict[str, Gender | None]:
    if path is None or not path.is_file():
        return {}
    out: dict[str, Gender | None] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("Name"):
                out[row["Name"]] = _SEX.get(row.get("Gender") or "")
    return out


def _read_ignored_patronymics(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [p for row in csv.DictReader(f) if (p := row.get("Patronymic"))]


def compile_legacy(names_csv: Path, names_ignore: Path | None = None, patronymics_ignore: Path | None = None,
                   *, name: str = "legacy") -> Layer:
    """The three old tables as one layer, every answer as the old lookups gave it."""
    table = _read(names_csv)
    source = f"{names_csv.name}:"
    male, female = Gender.MALE, Gender.FEMALE
    new = tuple.__new__

    names: dict[tuple[Gender | None, str], NameEntry] = {}
    forms: dict[tuple[Gender, str], FormsEntry] = {}
    for n, rs in table.by_name.items():
        r0 = rs[0]
        if len(rs) == 1:  # most names: one row, nothing to resolve — built as bare tuples, the
            # fastest way to make a named tuple, for the ~2200 of them a table holds
            line, written, _, base, g, o_m, o_f, m_m, m_f = r0
            at = f"{source}{line}"
            sex = _SEX[written]
            names[(sex, n)] = new(NameEntry, (sex, n, (base,) if base else (), None, at))
            forms[(sex, n)] = new(FormsEntry, (sex, n, g if g and g.startswith(n[:-1]) else _genitive(n, rs),
                                               m_m or None, m_f or None, o_m or None, o_f or None, at))
            continue
        groups: dict[Gender, list[_Row]] = {}
        for r in rs:
            groups.setdefault(_SEX[r.sex], []).append(r)
        for sex, group in groups.items():
            first = group[0]
            entry = NameEntry(sex, n, tuple(sorted({r.base for r in group if r.base})), None, f"{source}{first.line}")
            if (first.base or n) != entry.canonical_form:
                entry = entry._replace(canonical=first.base or n)
            names[(sex, n)] = entry
        # Without a sex the old lookup took the name itself when any row of it is canonical,
        # and the first row's base when none is; the lexicon takes the one sex's answer, or the
        # name for a name of both.
        unsexed = n if any(not r.base for r in rs) else r0.base
        rule = names[(_SEX[r0.sex], n)].canonical_form if len(groups) == 1 else n
        if unsexed != rule:
            names[(None, n)] = NameEntry(None, n, (), unsexed, f"{source}{r0.line}")
        # The forms of the name are its first row's, whatever that row's sex, as the father's
        # (on the man's key when the name has one); the other sex keeps its own genitive.
        own = male if male in groups else female
        forms[(own, n)] = FormsEntry(own, n, _genitive(n, rs), r0.modern_m or None, r0.modern_f or None,
                                     r0.old_m or None, r0.old_f or None, f"{source}{r0.line}")
        for sex, group in groups.items():
            if sex is not own and (genitive := _genitive(n, group)):
                forms[(sex, n)] = FormsEntry(sex, n, genitive, source=f"{source}{group[0].line}")

    for n, sex in _read_ignored_names(names_ignore).items():
        sexes = {s for s in (male, female) if (s, n) in names}
        if sex is not None and sexes and sexes != {sex}:
            # The ignore list was read first: a sex it gives that the table's rows contradict
            # was its answer alone, and no layer can say «this sex, whatever the entries say».
            raise workspace.WorkspaceError(t("legacy.ignored_sex_contradicts", name=n, path=names_ignore))
        held = names.get((sex, n))
        names[(sex, n)] = held._replace(source=IGNORE_LIST) if held else NameEntry(sex, n, source=IGNORE_LIST)

    patronymics: dict[tuple[Gender | None, str], PatronymicEntry] = {}
    derived: dict[tuple[str, Gender], dict[str, Any]] = {}
    for sex, first, modern_of in ((male, table.old_m, attrgetter("modern_m")),
                                  (female, table.old_f, attrgetter("modern_f"))):
        derived[("old", sex)] = found = derive_old(names, forms, sex)
        _pin_old(patronymics, first, found, sex, modern_of, source)
    for sex, first, old_of in ((male, table.modern_m, attrgetter("old_m")),
                               (female, table.modern_f, attrgetter("old_f"))):
        derived[("modern", sex)] = found = derive_modern(forms, sex)
        _pin_modern(patronymics, first, found, sex, old_of, source)
    for p in _read_ignored_patronymics(patronymics_ignore):
        patronymics[(None, p)] = PatronymicEntry(None, p, source=PATRONYMICS_IGNORE_LIST)
    return Layer(name, names, forms, patronymics, writable=False, derived=derived)


def _pin_old(patronymics: dict[tuple[Gender | None, str], PatronymicEntry], first: dict[str, _Row],
             derived: dict[str, list[OldReading]], sex: Gender, modern_of: _Cell, source: str) -> None:
    """A short form's reading is its first row's; pinned wherever the forms derive another."""
    for form, r in first.items():
        want = (modern_of(r) or None, r.father)
        got = pick_old(derived[form]) if form in derived else None
        if got is None or got[:2] != want:
            patronymics[(sex, form)] = PatronymicEntry(sex, form, want[1], want[0], f"{source}{r.line}")


def _pin_modern(patronymics: dict[tuple[Gender | None, str], PatronymicEntry], first: dict[str, _Row],
                derived: dict[str, set[str]], sex: Gender, old_of: _Cell, source: str) -> None:
    """A modern form's short form is its row's; pinned wherever the forms and the regular rule
    give another."""
    for modern, r in first.items():
        want = old_of(r)
        got = pick_modern(modern, sex, derived[modern]) if modern in derived else None
        if got != want:
            if (sex, modern) in patronymics:
                raise workspace.WorkspaceError(t("legacy.form_both_ways", form=modern))
            patronymics[(sex, modern)] = PatronymicEntry(sex, modern, source=f"{source}{r.line}", old=want)


class LegacyTables:
    """The old three tables of a workspace (schema ≤ 5, `[names] dir`) as a `LayerSource`."""

    writable = False

    def __init__(self, names_csv: Path, names_ignore: Path | None = None, patronymics_ignore: Path | None = None,
                 *, name: str = "legacy") -> None:
        self.name = name
        self.files = (names_csv, names_ignore, patronymics_ignore)

    def stamp(self) -> str:
        """The three files' (mtime, size); a missing names.csv is an error at every lookup."""
        names_csv = self.files[0]
        parts = []
        for path in self.files:
            try:
                st = os.stat(path) if path is not None else None
            except FileNotFoundError:
                st = None
            if st is None and path is names_csv:
                raise workspace.WorkspaceError(t("names_registry.no_file", path=names_csv))
            parts.append(f"{st.st_mtime_ns}:{st.st_size}" if st is not None else "-")
        return " ".join(parts)

    def load(self) -> Layer:
        return compile_legacy(*self.files, name=self.name)

    def put(self, entry: NameEntry | FormsEntry | PatronymicEntry) -> None:  # noqa: ARG002 — the port's signature
        raise TypeError(str(t("lexicon.read_only", layer=self.name)))

    def remove(self, table: Literal["names", "forms", "patronymics"],  # noqa: ARG002 — the port's signature
               key: tuple[Gender | None, str]) -> None:  # noqa: ARG002 — the port's signature
        raise TypeError(str(t("lexicon.read_only", layer=self.name)))
