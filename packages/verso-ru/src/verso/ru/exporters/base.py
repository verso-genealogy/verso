from abc import ABC, abstractmethod


import csv
import os
from dataclasses import dataclass
from pathlib import Path


def csv_writer(f):
    """A `csv.writer` that terminates lines the way this repository stores them.

    `csv.writer` defaults to `lineterminator="\r\n"` — RFC 4180 is right about
    the wire format and wrong about a git working tree. Every CSV here is
    committed and the repo is LF, so the default rewrote 225 files on every
    regeneration with nothing but carriage returns: churn that looks exactly
    like real work in `git status` and hides the diffs that are.
    """
    return csv.writer(f, lineterminator="\n")


def csv_dict_writer(f, fieldnames):
    """A `csv.DictWriter` that terminates lines the way `csv_writer` does.

    Same reasoning, same repository: the stdlib default is CRLF, and every CSV
    here is a committed file. Anything writing one goes through this or
    `csv_writer`, so the terminator is stated in exactly one place.
    """
    return csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")


@dataclass(frozen=True)
class CsvTable:
    """A CSV before it is a file: its name (`<parish>_<year>_births_familio.csv`), its header and its rows as
    the exporter built them. `write_table` writes it; `text_rows` is what reading that file back gives."""
    name: str
    headers: list[str]
    rows: list[list[object]]

    def text_rows(self) -> list[list[str]]:
        """The rows as the csv module writes a value and reads it back: None is empty, a float its repr,
        anything else its str."""
        return [[_text(value) for value in row] for row in self.rows]


def _text(value: object) -> str:
    if value is None:
        return ""
    return repr(value) if isinstance(value, float) else str(value)


def write_table(table: CsvTable, target_dir: str | Path) -> str:
    """`table` as a file of `target_dir`, UTF-8, LF; its path."""
    filename = os.path.join(str(target_dir), table.name)
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv_writer(f)
        writer.writerow(table.headers)
        writer.writerows(table.rows)
    return filename


class RecordsExporter(ABC):
    @abstractmethod
    def export(self, records_container, /, target_dir: str | Path | None = None) -> str:
        # positional-only so subclasses may name the param birth_records /
        # marriage_records / ... without an incompatible-override error.
        # The CSV goes into `target_dir`, the current directory without one (a DSL
        # file's own `__main__`, until 0.1.0's `verso export-csv`); its path is returned.
        ...
