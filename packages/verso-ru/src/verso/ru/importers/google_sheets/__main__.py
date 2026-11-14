"""Command-line entry point for the Google Sheets importer."""
import argparse
import sys
from verso.ru.importers.google_sheets.births import generate_births
from verso.ru.importers.google_sheets.deaths import generate_deaths
from verso.ru.importers.google_sheets.formats import FORMATS
from verso.ru.importers.google_sheets.marriages import generate_marriages
from verso.ru.importers.google_sheets.sheets import _fetch_rows, _fetch_rows_from_csv, _get_worksheet




# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import records from Google Sheets and generate Python genealogy DSL code."
    )
    parser.add_argument("spreadsheet_id", nargs="?", default=None,
                        help="Google Sheets spreadsheet ID (not needed with --csv)")
    parser.add_argument("year", type=int, help="Year to import")
    parser.add_argument("record_type", choices=["births", "marriages", "deaths"],
                        help="Type of records to import")
    parser.add_argument("--csv", default=None, metavar="PATH",
                        help="Read from local CSV file instead of Google Sheets")
    parser.add_argument("--format", default="familio-extended",
                        choices=list(FORMATS.keys()),
                        help="Spreadsheet format (default: familio-extended)")
    parser.add_argument("--sheet-name", default=None,
                        help="Sheet tab name (default depends on --format)")
    parser.add_argument("--village", default=None, help="Filter by village name")
    parser.add_argument("--output", default=None, help="Output file path (default: stdout)")
    # Optional metadata overrides (used when sheet lacks these columns)
    parser.add_argument("--archive", default="")
    parser.add_argument("--fund", default="")
    parser.add_argument("--inventory", default="")
    parser.add_argument("--case", default="")
    parser.add_argument("--church", default="")
    parser.add_argument("--status-male", default=None,
                        help="Default male status (default: экономический крестьянин)")
    parser.add_argument("--status-female", default=None,
                        help="Default female status (default: экономическая крестьянка)")
    parser.add_argument("--status-groom", default=None,
                        help="Default groom status for marriages (omitted by default, falls back to --status-male)")
    parser.add_argument("--status-bride", default=None,
                        help="Default bride status for marriages (default: девка из экономических крестьян)")
    parser.add_argument("--cause-of-death", default=None,
                        help="Default cause of death (default: натуральная)")
    args = parser.parse_args()

    fmt = FORMATS[args.format]
    year_col = fmt.year_cols[args.record_type]

    if args.csv:
        print(f"Reading from {args.csv}...", file=sys.stderr)
        rows = _fetch_rows_from_csv(args.csv, args.year, year_col, args.village,
                                    header_rows=fmt.header_rows)
    else:
        if not args.spreadsheet_id:
            parser.error("spreadsheet_id is required unless --csv is provided")
        sheet_name = args.sheet_name or fmt.sheet_names[args.record_type]
        print("Connecting to Google Sheets...", file=sys.stderr)
        worksheet = _get_worksheet(args.spreadsheet_id, sheet_name)
        print(f"Fetching rows for year {args.year}...", file=sys.stderr)
        rows = _fetch_rows(worksheet, args.year, year_col, args.village, header_rows=fmt.header_rows)
    print(f"Found {len(rows)} rows.", file=sys.stderr)

    if not rows:
        print("No matching rows found.", file=sys.stderr)
        sys.exit(1)

    kwargs = dict(
        archive=args.archive,
        fund=args.fund,
        inventory=args.inventory,
        case_=args.case,
        village=args.village or "",
        church=args.church,
        year=args.year,
    )

    # Build status overrides (only pass non-None so function defaults apply)
    status_kw = {}
    if args.status_male is not None:
        status_kw["status_male"] = args.status_male
    if args.status_female is not None:
        status_kw["status_female"] = args.status_female

    if args.record_type == "births":
        output = generate_births(rows, **kwargs, cols=fmt.birth_cols, **status_kw)
    elif args.record_type == "marriages":
        m_kw = dict(status_kw)
        if args.status_groom is not None:
            m_kw["status_groom"] = args.status_groom
        if args.status_bride is not None:
            m_kw["status_bride"] = args.status_bride
        output = generate_marriages(rows, **kwargs, cols=fmt.marriage_cols, **m_kw)
    else:
        d_kw = dict(status_kw)
        if args.cause_of_death is not None:
            d_kw["cause_of_death"] = args.cause_of_death
        output = generate_deaths(rows, **kwargs, cols=fmt.death_cols, **d_kw)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)



if __name__ == "__main__":
    main()
