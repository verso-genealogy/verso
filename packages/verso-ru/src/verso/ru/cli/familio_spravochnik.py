"""Assemble a Familio submission ``.xlsx`` справочник from per-year records.

Aggregates a village's per-year ``*_familio.csv`` files across a year range into a
single workbook with one tab per record type (рождение / брак / смерть) and a
continuous сквозная нумерация — the form Familio's indexing program expects.

Usage::

    python -m verso.ru.cli.familio_spravochnik <village> <from_year> <to_year> \
        [--village-dir DIR] [--out FILE] [--no-regenerate]

Example::

    python -m verso.ru.cli.familio_spravochnik Горюхино 1832 1840
"""
import argparse
import subprocess
import sys
from pathlib import Path

from verso.ru.exporters.familio_spravochnik import (
    RECORD_TYPES, FamilioTemplateWriter, YearRecords, build_spravochnik, read_about, read_location_rows, read_year_records)
from verso.ru.naming.transliteration import generate_res_name
from verso.core import workspace
from verso.core.workspace import child_env
from verso.ru.messages import t

# The official Familio МК template is Familio's file, and the corpus's data: `--template`,
# else this path under the workspace's corpus.
TEMPLATE_IN_CORPUS = Path("familio") / "Shablon_MK.xlsx"


def default_template() -> Path:
    """The workspace corpus's Familio МК template; a refusal saying where to put one when there is none."""
    corpus = workspace.current().corpus_dir
    if corpus is None or not (corpus / TEMPLATE_IN_CORPUS).is_file():
        raise SystemExit(t("cli.familio_spravochnik.no_template"))
    return corpus / TEMPLATE_IN_CORPUS


def regenerate_year_csvs(village_dir: Path, year: int) -> None:
    """Re-run every DSL ``.py`` in ``village_dir/year`` so its CSVs are current.

    Mirrors the root ``make generate_csv`` target: each year file, run as
    ``__main__``, writes its own ``*_familio.csv`` into the year directory.
    """
    year_dir = village_dir / str(year)
    if not year_dir.is_dir():
        return
    for py_file in sorted(year_dir.glob("*.py")):
        subprocess.run([sys.executable, py_file.name], cwd=year_dir, check=True, env=child_env())


def collect_records(
    village_dir: Path, village: str, years: list[int], regenerate: bool
) -> dict[str, list[YearRecords]]:
    """Read per-year records for every record type across the given years."""
    records_by_type: dict[str, list[YearRecords]] = {rt: [] for rt in RECORD_TYPES}
    for year in years:
        if regenerate:
            regenerate_year_csvs(village_dir, year)
        for record_type in RECORD_TYPES:
            year_records = read_year_records(village_dir, village, year, record_type)
            if year_records is not None and year_records.rows:
                records_by_type[record_type].append(year_records)
    return records_by_type


def years_label_for(years: list[int]) -> str:
    """Human label: a single year as ``1805``, a contiguous run as ``1832-1840``,
    else an explicit list ``1799, 1805``."""
    if len(years) == 1:
        return str(years[0])
    if years == list(range(years[0], years[-1] + 1)):
        return f"{years[0]}-{years[-1]}"
    return ", ".join(str(y) for y in years)


def default_out_path(village_dir: Path, village: str, years_label: str) -> Path:
    slug = generate_res_name(village)
    suffix = years_label.replace(", ", "_").replace(" ", "")
    return village_dir / "familio_submissions" / f"mk_{slug}_{suffix}.xlsx"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("village", help="Village name (its directory)")
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
        help="Curated location.csv to populate the workbook's location sheet "
             "(default: <village-dir>/familio_submissions/location.csv if present)",
    )
    parser.add_argument(
        "--about-json", type=Path, default=None,
        help="Per-village about.json to fill the workbook's about sheet "
             "(default: <village-dir>/familio_submissions/about.json if present)",
    )
    parser.add_argument(
        "--no-regenerate", action="store_true",
        help="Skip re-running the DSL files; use the CSVs already on disk",
    )
    args = parser.parse_args(argv)

    template: Path = args.template or default_template()
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

    records_by_type = collect_records(
        village_dir, args.village, years, regenerate=not args.no_regenerate
    )
    spravochnik = build_spravochnik(
        args.village, from_year, to_year, records_by_type, years_label=years_label, cases=cases
    )

    if not spravochnik.sheets:
        parser.error(f"no records found for {args.village} {years_label}")

    out_path = args.out or default_out_path(village_dir, args.village, years_label)
    location_csv: Path = args.location_csv or (village_dir / "familio_submissions" / "location.csv")
    location_rows = read_location_rows(location_csv)
    about_json: Path = args.about_json or (village_dir / "familio_submissions" / "about.json")
    about = read_about(about_json, args.village, from_year, to_year, years_label)
    FamilioTemplateWriter(template).write(spravochnik, out_path, location_rows=location_rows, about=about)

    print(f"Wrote {out_path}")
    for sheet in spravochnik.sheets:
        print(f"  {sheet.title}: {len(sheet.rows)} records")
    if location_rows is not None:
        print(f"  location: {len(location_rows)} places from {location_csv}")
    if about is not None:
        print(f"  about: filled from {about_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
