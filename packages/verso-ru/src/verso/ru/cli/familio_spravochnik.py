"""Assemble a Familio submission ``.xlsx`` справочник from a parish's records.

Reads the record sets of a village's DSL files (the records export with ``VERSO_RECORDS``) across a year range
and writes one workbook with a tab per record type (рождение / брак / смерть) and a continuous сквозная
нумерация — the form Familio's indexing program expects. Only proofread records go in: a record held back as
``reviewed=False`` is left out and counted (``--with-unreviewed`` puts them in).

The workbook is the one the library builds of the МК template's layout (its record sheets, ``about`` and
``location``); ``--template FILE`` fills Familio's own file instead.

Usage::

    python -m verso.ru.cli.familio_spravochnik <parish> <from_year> <to_year> \
        [--village-dir DIR] [--out FILE] [--template FILE] [--with-unreviewed]

``<parish>`` is the parish the books are of — a record set's village — and, unless ``--village-dir`` says
otherwise, the directory holding them.

Example::

    python -m verso.ru.cli.familio_spravochnik Горюхино 1832 1840
"""
import argparse
from pathlib import Path

from verso.core import places
from verso.core.pipeline.load import record_namespace, village_modules
from verso.ru import corpus_data
from verso.ru.exporters.familio_spravochnik import (
    FamilioTemplateWriter, blank_places, build_spravochnik, collect, known_from, location_rows, read_about,
    read_location_rows, referenced_places, years_label_for)
from verso.ru.messages import t
from verso.ru.naming.transliteration import generate_res_name

__all__ = ["default_out_path", "main", "record_sets", "years_label_for"]


class NotImported(Exception):
    """DSL files of the years asked for that do not import: a справочник without them would be short."""

    def __init__(self, files: list[Path]) -> None:
        super().__init__(", ".join(str(f) for f in files))
        self.files = files


def record_sets(village_dir: Path, years: list[int]) -> list[object]:
    """The record sets of the village's DSL files of `years`, in the order of the files — each once, the files
    `village.toml` names in `[csv] skip` passed over (they wrote no CSV, and go into no справочник). A file
    that does not import is refused (`NotImported`), never skipped."""
    skip = set(corpus_data.village(village_dir).csv_skip)
    skipped: list[tuple[Path, Exception]] = []
    found: dict[int, object] = {}
    for path, module in village_modules(village_dir, year=years, skipped=skipped):
        if path.relative_to(village_dir).as_posix() in skip:
            continue
        for value in record_namespace(module).values():
            found.setdefault(id(value), value)
    broken = [path for path, _ in skipped if path.relative_to(village_dir).as_posix() not in skip]
    if broken:
        raise NotImported(broken)
    return list(found.values())


def default_out_path(village_dir: Path, village: str, years_label: str) -> Path:
    slug = generate_res_name(village)
    suffix = years_label.replace(", ", "_").replace(" ", "")
    return village_dir / "familio_submissions" / f"mk_{slug}_{suffix}.xlsx"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("village", help="The parish of the books (and their directory, without --village-dir)")
    parser.add_argument("from_year", type=int, nargs="?", help="First year (inclusive)")
    parser.add_argument("to_year", type=int, nargs="?", help="Last year (inclusive)")
    parser.add_argument(
        "--years", default=None,
        help="Explicit comma-separated years instead of a from/to range, e.g. 1799,1805",
    )
    parser.add_argument(
        "--cases", default=None,
        help=str(t("cli.familio_spravochnik.help_cases")),
    )
    parser.add_argument(
        "--years-label", default=None,
        help="Override the year label shown in the about sheet (e.g. 1760-1817) "
             "instead of the auto comma-list — useful for many non-contiguous years",
    )
    parser.add_argument(
        "--village-dir", type=Path, default=None,
        help="Directory holding the village's per-year folders (default: ./<village>)",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output .xlsx path")
    parser.add_argument(
        "--template", type=Path, default=None,
        help=str(t("cli.familio_spravochnik.help_template")),
    )
    parser.add_argument(
        "--location-csv", type=Path, default=None,
        help="Curated location.csv whose rows open the workbook's location sheet "
             "(default: <village-dir>/familio_submissions/location.csv if present)",
    )
    parser.add_argument(
        "--about-json", type=Path, default=None,
        help="Per-village about.json to fill the workbook's about sheet "
             "(default: <village-dir>/familio_submissions/about.json if present)",
    )
    parser.add_argument(
        "--with-unreviewed", action="store_true",
        help=str(t("cli.familio_spravochnik.help_with_unreviewed")),
    )
    parser.add_argument(
        "--no-regenerate", action="store_true",
        help=str(t("cli.familio_spravochnik.help_no_regenerate")),
    )
    args = parser.parse_args(argv)

    if args.template is not None and not args.template.is_file():
        parser.error(f"template not found: {args.template}")
    village_dir: Path = args.village_dir or Path(args.village)
    if not village_dir.is_dir():
        parser.error(f"village directory not found: {village_dir}")

    if args.years:
        years = sorted({int(y) for y in args.years.replace(" ", "").split(",") if y})
        if not years:
            parser.error("--years did not contain any years")
    elif args.from_year is not None and args.to_year is not None:
        years = list(range(args.from_year, args.to_year + 1))
    else:
        parser.error("provide from_year and to_year, or --years")
    from_year, to_year = years[0], years[-1]
    years_label = args.years_label or years_label_for(years)

    cases = (
        frozenset(c.strip() for c in args.cases.replace(" ", "").split(",") if c)
        if args.cases else None
    )

    try:
        sets = record_sets(village_dir, years)
    except NotImported as refused:
        parser.error(str(t("cli.familio_spravochnik.not_imported", count=len(refused.files), files=str(refused))))
    collected = collect(sets, parish=args.village, years=years, reviewed_only=not args.with_unreviewed)
    spravochnik = build_spravochnik(
        args.village, from_year, to_year, collected.records_by_type, years_label=years_label, cases=cases
    )

    if not spravochnik.sheets:
        left_out = (" — " + str(t("cli.familio_spravochnik.only_unreviewed", count=collected.left_out))
                    if collected.left_out else "")
        parser.error(f"no records found for {args.village} {years_label}{left_out}")

    out_path = args.out or default_out_path(village_dir, args.village, years_label)
    location_csv: Path = args.location_csv or (village_dir / "familio_submissions" / "location.csv")
    curated = read_location_rows(location_csv)
    locations = location_rows(referenced_places(spravochnik), curated=curated or (),
                              known=known_from(places.current()))
    about_json: Path = args.about_json or (village_dir / "familio_submissions" / "about.json")
    about = read_about(about_json, args.village, from_year, to_year, years_label)
    FamilioTemplateWriter(args.template).write(spravochnik, out_path, location_rows=locations, about=about)

    print(f"Wrote {out_path}")
    for sheet in spravochnik.sheets:
        print(f"  {sheet.title}: {len(sheet.rows)} records")
    if collected.left_out:
        print(t("cli.familio_spravochnik.left_out", count=collected.left_out))
    source = f" ({len(curated)} from {location_csv})" if curated is not None else ""
    print(f"  location: {len(locations)} places{source}")
    if blank_places(locations):
        print(t("cli.familio_spravochnik.blank_places", count=blank_places(locations)))
    if about is not None:
        print(f"  about: filled from {about_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
