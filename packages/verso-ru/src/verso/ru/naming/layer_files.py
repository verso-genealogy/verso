"""A names layer kept as three TSV files — `names.tsv`, `forms.tsv`, `patronymics.tsv` — in one directory.

    names.tsv        sex  name  bases  canonical  source  note
    forms.tsv        sex  name  genitive  patronymic_m  patronymic_f  old_patronymic_m  old_patronymic_f  source
    patronymics.tsv  sex  form  father  modern  old  source

A file opens with that header and holds one row a key, sorted by the key — the sex (`M`, `F`, or empty
for «not stated»), then the name. An empty cell is «not set» (None): in `forms.tsv`, the rule's form. A forms
cell `-` (`NO_FORM`) is «no such form»: the name has none, and the rules do not fill it in — a lookup reads it
as the old table's empty cell (its caller's own way: `derive_patronymic` still falls back on the rule's modern
form) and no reverse index holds a form for it; the entry carries it as "". A names row whose `bases` is `-`
(`lexicon.ABSENT`) says «this (sex, name) does not exist in this stack»: it removes the lower layers' entry of
that key, and only that key — its forms go with it — and the name answers as if no layer held it in that sex.
A layer above the base may write it; the base, with nothing below it, may not (LEX006). Several bases are written with
`|` between them; a `note` is the maintainer's word about a row, kept with it and read by no lookup. A name
entry whose source is `ignore` is a name the lexicon knows and leaves out on purpose (`IGNORE_LIST`). A table
the directory lacks is empty. The order of the rows means nothing to the lexicon (`Lexicon.of` builds
every index from the sum) — it is kept so that a change of the layer reads as a change of its rows.

`FilesLayer` is the `LayerSource` over such a directory; the library's base (`base()`) is one, shipped as
package data. `SOURCES` is the closed list of sources a row of the base may name.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Literal

from verso.ru.gender import Gender
from verso.ru.messages import t
from verso.ru.naming.lexicon import FormsEntry, Layer, NameEntry, PatronymicEntry

Table = Literal["names", "forms", "patronymics"]

#: Each table's file and columns, in their order.
FILES: dict[Table, str] = {"names": "names.tsv", "forms": "forms.tsv", "patronymics": "patronymics.tsv"}
COLUMNS: dict[Table, tuple[str, ...]] = {
    "names": ("sex", "name", "bases", "canonical", "source", "note"),
    "forms": ("sex", "name", "genitive", "patronymic_m", "patronymic_f", "old_patronymic_m", "old_patronymic_f",
              "source"),
    "patronymics": ("sex", "form", "father", "modern", "old", "source"),
}
#: The column of each table its key is read from, beside the sex.
KEY_COLUMN: dict[Table, str] = {"names": "name", "forms": "name", "patronymics": "form"}

SEX: dict[str, Gender | None] = {"M": Gender.MALE, "F": Gender.FEMALE, "": None}
_BAD = object()  # a sex cell `SEX` does not hold
#: A forms cell that says «no such form»: the rules do not fill it in (the entry holds "").
NO_FORM = "-"
_SEX_CELL = {Gender.MALE: "M", Gender.FEMALE: "F", None: ""}

#: The sources a row of the base may name: a line of the 1906 Требник's alphabet as the library ships it
#: (`trebnik1906:<line of svyatcy_1906.tsv>`), a Wikidata item (`wikidata:Q…`), the spellings the metric
#: books write (`mk`), a form the rules give (`rule`), and the maintainer's own (`editor`).
SOURCES = ("trebnik1906:<line>", "wikidata:Q<n>", "mk", "rule", "editor")
_SOURCE = re.compile(r"trebnik1906:[1-9]\d*|wikidata:Q[1-9]\d*|mk|rule|editor")

#: The base layer's directory, in the package.
BASE: Traversable = files("verso.ru.naming") / "data" / "base"

Row = dict[str, str]


class LayerFileError(ValueError):
    """A layer's file the lexicon cannot read: a header it does not know, a row of the wrong width, a key
    written twice, a sex other than M, F or empty."""


def is_base_source(source: str) -> bool:
    """Whether `source` is one of `SOURCES`."""
    return _SOURCE.fullmatch(source) is not None


def sort_key(sex: str, name: str) -> tuple[str, str]:
    """A row's place in its file: the sex cell, then the name."""
    return (sex, name)


def read_rows(directory: Path | Traversable) -> dict[Table, list[tuple[int, Row]]]:
    """Every row of the three files as written — (line, {column: cell}) — for a reader that wants the rows
    themselves, duplicates and bad cells included (the lexicon linter). A table the directory lacks has no
    rows; a header other than the table's, or a row of another width, is a `LayerFileError`."""
    out: dict[Table, list[tuple[int, Row]]] = {}
    for table, file in FILES.items():
        path = directory / file
        rows: list[tuple[int, Row]] = []
        if path.is_file():
            lines = path.read_text(encoding="utf-8").split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            columns = COLUMNS[table]
            if not lines or tuple(lines[0].split("\t")) != columns:
                raise LayerFileError(str(t("layer_files.header", file=file, columns="\t".join(columns))))
            for number, line in enumerate(lines[1:], start=2):
                cells = line.split("\t")
                if len(cells) != len(columns):
                    raise LayerFileError(str(t("layer_files.width", file=file, line=number)))
                rows.append((number, dict(zip(columns, cells, strict=True))))
        out[table] = rows
    return out


def _cell(value: str) -> str | None:
    return value or None


def _form(value: str) -> str | None:
    """A forms cell: empty — not set (the rule's); `-` — no such form ("")."""
    return "" if value == NO_FORM else value or None


def _sex(file: str, line: int, cell: str) -> Gender | None:
    if cell not in SEX:
        raise LayerFileError(str(t("layer_files.sex", file=file, line=line, sex=cell)))
    return SEX[cell]


def entry_of(table: Table, row: Row, *, file: str = "", line: int = 0) -> NameEntry | FormsEntry | PatronymicEntry:
    """The entry one row writes."""
    sex = _sex(file or FILES[table], line, row["sex"])
    if table == "names":
        bases = tuple(row["bases"].split("|")) if row["bases"] else ()
        return NameEntry(sex, row["name"], bases, _cell(row["canonical"]), row["source"])
    if table == "forms":
        if sex is None:
            raise LayerFileError(str(t("layer_files.forms_sex", file=file or FILES[table], line=line, name=row["name"])))
        return FormsEntry(sex, row["name"], _form(row["genitive"]), _form(row["patronymic_m"]),
                          _form(row["patronymic_f"]), _form(row["old_patronymic_m"]), _form(row["old_patronymic_f"]),
                          row["source"])
    return PatronymicEntry(sex, row["form"], _cell(row["father"]), _cell(row["modern"]), row["source"],
                           _cell(row["old"]))


def row_of(entry: NameEntry | FormsEntry | PatronymicEntry, note: str = "") -> tuple[Table, Row]:
    """The table and the row an entry is written as; a value no cell can hold (a tab, a line break, a `|`
    inside a base) is a ValueError."""
    if isinstance(entry, NameEntry):
        table: Table = "names"
        cells = [_SEX_CELL[entry.sex], entry.name, "|".join(entry.bases), entry.canonical or "", entry.source, note]
        bad = [b for b in entry.bases if not b or "|" in b]
    elif isinstance(entry, FormsEntry):
        table = "forms"
        cells = [_SEX_CELL[entry.sex], entry.name, *(NO_FORM if c == "" else c or "" for c in entry[2:7]),
                 entry.source]
        bad = []
    else:
        table = "patronymics"
        cells = [_SEX_CELL[entry.sex], entry.form, entry.father or "", entry.modern or "", entry.old or "",
                 entry.source]
        bad = []
    bad += [c for c in cells if "\t" in c or "\n" in c or "\r" in c]
    if bad:
        raise ValueError(str(t("layer_files.bad_value", value=repr(bad[0]))))
    return table, dict(zip(COLUMNS[table], cells, strict=True))


class FilesLayer:
    """A `LayerSource` over a directory of the three TSV files. `put` and `remove` write the file of their
    table at once, keeping it sorted by key; a read-only layer (`writable=False`) refuses them."""

    def __init__(self, directory: Path | Traversable, *, name: str, writable: bool) -> None:
        self.directory = directory
        self.name = name
        self.writable = writable

    def stamp(self) -> str:
        """Each file's (mtime, size) — `-` for a file the directory lacks; a layer read from a package that is
        no directory of the file system (a zip) never changes."""
        if not isinstance(self.directory, Path):
            return "package"
        parts = []
        for file in FILES.values():
            try:
                st = os.stat(self.directory / file)
            except FileNotFoundError:
                parts.append("-")
                continue
            parts.append(f"{st.st_mtime_ns}:{st.st_size}")
        return " ".join(parts)

    def load(self) -> Layer:
        """The layer, read in one pass a file — the cells straight into the entries (the linter reads the rows
        themselves, `read_rows`)."""
        names: dict[tuple[Gender | None, str], NameEntry] = {}
        forms: dict[tuple[Gender, str], FormsEntry] = {}
        patronymics: dict[tuple[Gender | None, str], PatronymicEntry] = {}
        new, sexes = tuple.__new__, SEX
        for table, file in FILES.items():
            path = self.directory / file
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8").split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            columns = COLUMNS[table]
            if not lines or tuple(lines[0].split("\t")) != columns:
                raise LayerFileError(str(t("layer_files.header", file=file, columns="\t".join(columns))))
            width = len(columns)
            for number, line in enumerate(lines[1:], start=2):
                cells = line.split("\t")
                if len(cells) != width:
                    raise LayerFileError(str(t("layer_files.width", file=file, line=number)))
                sex = sexes.get(cells[0], _BAD)
                if sex is _BAD:
                    raise LayerFileError(str(t("layer_files.sex", file=file, line=number, sex=cells[0])))
                key = (sex, cells[1])
                if table == "names":
                    held: dict[Any, Any] = names
                    entry: Any = new(NameEntry, (sex, cells[1], tuple(cells[2].split("|")) if cells[2] else (),
                                                 cells[3] or None, cells[4]))
                elif table == "forms":
                    if sex is None:
                        raise LayerFileError(str(t("layer_files.forms_sex", file=file, line=number, name=cells[1])))
                    held = forms
                    entry = new(FormsEntry, (sex, cells[1], *map(_form, cells[2:7]), cells[7]))
                else:
                    held = patronymics
                    entry = new(PatronymicEntry, (sex, cells[1], cells[2] or None, cells[3] or None, cells[5],
                                                  cells[4] or None))
                if key in held:
                    raise LayerFileError(str(t("layer_files.duplicate", file=file, line=number, key=cells[1])))
                held[key] = entry
        return Layer(self.name, names, forms, patronymics, writable=self.writable, derives=True)

    def put(self, entry: NameEntry | FormsEntry | PatronymicEntry) -> None:
        """Write `entry` in its key's place, replacing the row of that key (its note kept)."""
        self._writable()
        table, row = row_of(entry)
        rows = {self._key(table, r): r for _, r in read_rows(self.directory)[table]}
        key = self._key(table, row)
        if "note" in row and key in rows:
            row["note"] = rows[key]["note"]
        rows[key] = row
        self._write(table, rows)

    def put_all(self, entries: Sequence[NameEntry | FormsEntry | PatronymicEntry]) -> None:
        """`put` of every entry, the files of all their tables written under temporary names first and renamed after, so
        that a write that fails leaves no table changed (a rename that fails after another has gone is the file
        system's: each file itself is replaced whole)."""
        self._writable()
        if not isinstance(self.directory, Path):
            raise TypeError(str(t("lexicon.read_only", layer=self.name)))
        rows: dict[Table, dict[tuple[str, str], Row]] = {}
        for entry in entries:
            table, row = row_of(entry)
            held = rows.get(table)
            if held is None:
                held = rows[table] = {self._key(table, r): r for _, r in read_rows(self.directory)[table]}
            key = self._key(table, row)
            if "note" in row and key in held:
                row["note"] = held[key]["note"]
            held[key] = row
        staged: list[tuple[Path, Path]] = []
        try:
            for table, held in rows.items():
                staged.append((stage_table(self.directory, table, [held[k] for k in sorted(held)]),
                               self.directory / FILES[table]))
            for tmp, path in staged:
                tmp.replace(path)
        finally:
            for tmp, _ in staged:
                tmp.unlink(missing_ok=True)

    def remove(self, table: Table, key: tuple[Gender | None, str]) -> None:
        """Drop the row of `key` from `table`; a KeyError when the table has none."""
        self._writable()
        rows = {self._key(table, r): r for _, r in read_rows(self.directory)[table]}
        del rows[sort_key(_SEX_CELL[key[0]], key[1])]
        self._write(table, rows)

    def _writable(self) -> None:
        if not self.writable:
            raise TypeError(str(t("lexicon.read_only", layer=self.name)))

    @staticmethod
    def _key(table: Table, row: Mapping[str, str]) -> tuple[str, str]:
        return sort_key(row["sex"], row[KEY_COLUMN[table]])

    def _write(self, table: Table, rows: Mapping[tuple[str, str], Row]) -> None:
        if not isinstance(self.directory, Path):
            raise TypeError(str(t("lexicon.read_only", layer=self.name)))
        write_table(self.directory, table, [rows[k] for k in sorted(rows)])


def stage_table(directory: Path, table: Table, rows: list[Row]) -> Path:
    """Write `rows` (already in their order) as the table's file under a temporary name beside it; the path of that file."""
    directory.mkdir(parents=True, exist_ok=True)
    columns = COLUMNS[table]
    text = "".join("\t".join(r[c] for c in columns) + "\n" for r in rows)
    path = directory / FILES[table]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\t".join(columns) + "\n" + text, encoding="utf-8", newline="\n")
    return tmp


def write_table(directory: Path, table: Table, rows: list[Row]) -> None:
    """Write `rows` (already in their order) as the table's file, atomically."""
    stage_table(directory, table, rows).replace(directory / FILES[table])


def base() -> FilesLayer:
    """The library's base layer: read-only, shipped with the package (`data/base/`)."""
    return FilesLayer(BASE, name="base", writable=False)
