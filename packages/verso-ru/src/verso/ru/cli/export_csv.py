"""`verso export-csv` — a village's CSVs, written from its DSL files.

    verso export-csv --village Заманиловка [--year 1814 …] [--out DIR]

Each record set a DSL file binds goes to the exporter its type takes
(`verso.ru.exporters.table`): what the file's own `__main__` block named until 0.1.0. A CSV is
written beside its DSL file, or under `DIR/<year>/` with `--out`. A file the village's
`village.toml` names in `[csv] skip` writes none (Горюхино's thirteen that had no `__main__`).
With `VERSO_RECORDS` set the records come from the export, as for every reader of the corpus.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import shutil
import sys
import tempfile
from collections.abc import Collection
from pathlib import Path

from verso.ru import corpus_data
from verso.core.pipeline.load import load_module, record_namespace
from verso.ru.exporters.table import exporter_for
from verso.ru.messages import t

_YEAR = re.compile(r"^\d{4}$")


class ExportError(ValueError):
    """A file whose CSVs cannot be written as asked."""


def export_file(path: Path, out_dir: Path) -> list[Path]:
    """The CSVs of the DSL file at `path`, written into `out_dir`: each record set it binds
    once (an alias is the same set), in the order of its namespace. Two sets writing one CSV
    are refused, and then nothing is written. Each CSV is said as the exporters say it
    («Generated <path>»), once it is where it belongs."""
    sets: dict[int, object] = {}
    for value in record_namespace(load_module(path)).values():
        sets.setdefault(id(value), value)
    with tempfile.TemporaryDirectory() as scratch:
        made: dict[str, Path] = {}
        for record_set in sets.values():
            exporter = exporter_for(record_set)
            if exporter is None:
                continue
            with contextlib.redirect_stdout(io.StringIO()):     # it would name the scratch directory
                written = Path(exporter.export(record_set, target_dir=scratch))
            if written.name in made:
                raise ExportError(t("cli.export_csv.two_sets_one_file", path=path, name=written.name))
            made[written.name] = written
        if not made:
            return []
        out_dir.mkdir(parents=True, exist_ok=True)
        placed = []
        for name, written in made.items():
            placed.append(Path(shutil.move(str(written), str(out_dir / name))))
            print(f"Generated {placed[-1]}")
        return placed


def _files(village_dir: Path, years: Collection[int] | None) -> list[Path]:
    """The village's DSL files, year by year, each year's by name — the order `__main__` ran in."""
    year_dirs = sorted(d for d in village_dir.iterdir() if d.is_dir() and _YEAR.match(d.name)
                       and (years is None or int(d.name) in years))
    return [p for d in year_dirs for p in sorted(d.glob("*.py"))]


def export_village(village_dir: Path, out_root: Path | None = None,
                   years: Collection[int] | None = None) -> list[Path]:
    """Every CSV of the village (of `years`, all without them): beside its file, or under
    `out_root/<year>/`. The files of `[csv] skip` are passed over."""
    skip = set(corpus_data.village(village_dir).csv_skip)
    written: list[Path] = []
    for path in _files(village_dir, years):
        if path.relative_to(village_dir).as_posix() in skip:
            continue
        out_dir = path.parent if out_root is None else out_root / path.parent.name
        written += export_file(path, out_dir)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--village", required=True, help=str(t("cli.export_csv.help_village")))
    ap.add_argument("--year", type=int, action="append", help=str(t("cli.export_csv.help_year")))
    ap.add_argument("--out", help=str(t("cli.export_csv.help_out")))
    args = ap.parse_args(argv)
    village_dir = Path(args.village)
    years = set(args.year) if args.year else None
    skip = set(corpus_data.village(village_dir).csv_skip)
    files = _files(village_dir, years)
    skipped = sum(1 for p in files if p.relative_to(village_dir).as_posix() in skip)
    try:
        written = export_village(village_dir, Path(args.out) if args.out else None, years)
    except ExportError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(t("cli.export_csv.done", village=args.village, written=len(written), files=len(files) - skipped, skipped=skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
