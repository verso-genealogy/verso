#!/usr/bin/env python3
"""
Fetches a specific record from both the Google Sheet and CSV by key,
displaying all fields side-by-side for easy comparison.

Usage (`--site` — the village's sheet, `[sheets] site` of its village.toml):
  python3 fetch_record.py --site zamanilovka births 1760 13 -g жен -m 5
  python3 fetch_record.py --site zamanilovka marriages 1760 8 -m 5
  python3 fetch_record.py --site zamanilovka deaths 1760 1 -g муж -m 3
  python3 fetch_record.py --site zamanilovka births 1760 13 -g жен -m 5 --source csv
"""

import argparse
import sys

from verso.ru.importers.google_sheets import (
    _get, B_RECORD_NUM, B_GENDER, B_B_MONTH, B_K_MONTH, M_RECORD_NUM, M_W_MONTH, D_RECORD_NUM, D_GENDER, D_D_MONTH, FORMAT_FAMILIO_EXTENDED, FORMATS)
from verso.core.corpus_data import CorpusDataError
from verso.ru.importers.validation import (
    _s, select, site_config, fetch_all_sheets, split_by_year, find_csv, read_familio_csv, FIELD_TO_SHEET_COL)
from verso.ru.messages import t

SHEET_TABS = {"births": "рождение", "marriages": "брак", "deaths": "смерть"}  # i18n: content — the sheets' tab names

# Year column indices per record type
YEAR_COL = {"births": 14, "marriages": 14, "deaths": 14}


def build_sheet_key(record_type, srow):
    """Build lookup key from a sheet row, matching compare_* logic."""
    if record_type == "births":
        rec_num = _get(srow, B_RECORD_NUM)
        gender = _get(srow, B_GENDER)
        month = _get(srow, B_B_MONTH) or _get(srow, B_K_MONTH)
        return (rec_num, gender, month)
    elif record_type == "marriages":
        rec_num = _get(srow, M_RECORD_NUM)
        month = _get(srow, M_W_MONTH)
        return (rec_num, month)
    else:  # deaths
        rec_num = _get(srow, D_RECORD_NUM)
        gender = _get(srow, D_GENDER)
        month = _get(srow, D_D_MONTH)
        return (rec_num, gender, month)


def build_csv_key(record_type, crow):
    """Build lookup key from a CSV row, matching compare_* logic."""
    if record_type == "births":
        return (_s(crow[10]), _s(crow[11]), _s(crow[13]))
    elif record_type == "marriages":
        return (_s(crow[10]), _s(crow[12]))
    else:  # deaths
        return (_s(crow[10]), _s(crow[11]), _s(crow[13]))


def build_target_key(record_type, rec_num, gender, month_name):
    """Build target key from CLI args."""
    if record_type in ("births", "deaths"):
        return (rec_num, gender, month_name)
    else:  # marriages
        return (rec_num, month_name)


def get_fields_for_type(record_type):
    """Get ordered list of (field_name, sheet_col_idx) for a record type."""
    fields = []
    for (rt, field_name), col_idx in FIELD_TO_SHEET_COL.items():
        if rt == record_type:
            fields.append((field_name, col_idx))
    return fields


def find_sheet_row(sheet_rows_with_idx, record_type, target_key):
    """Find the first sheet row matching the target key."""
    for _idx, srow in sheet_rows_with_idx:
        if build_sheet_key(record_type, srow) == target_key:
            return srow
    return None


def find_csv_row(csv_rows, record_type, target_key):
    """Find the first CSV row matching the target key."""
    for crow in csv_rows:
        if build_csv_key(record_type, crow) == target_key:
            return crow
    return None


def build_csv_col_lookup(headers):
    """Build {header_name: col_idx} from CSV headers."""
    return {h: i for i, h in enumerate(headers)}


def format_table(record_type, target_key, year, srow, crow, fields, source):
    """Format side-by-side comparison table."""
    # Build key description
    if record_type in ("births", "deaths"):
        rec_num, gender, month = target_key
        key_desc = f"rec_num={rec_num}, gender={gender}, month={month}"
    else:
        rec_num, month = target_key
        key_desc = f"rec_num={rec_num}, month={month}"

    lines = [f"\n=== {record_type}: {key_desc}, year={year} ===\n"]

    # Column widths
    fw = 40  # field name width
    vw = 30  # value width

    if source == "both":
        header = f"  {'Field':<{fw}}  {'Sheet':<{vw}}  {'CSV':<{vw}}"
        sep = f"  {'─' * fw}  {'─' * vw}  {'─' * vw}"
    elif source == "sheet":
        header = f"  {'Field':<{fw}}  {'Sheet':<{vw}}"
        sep = f"  {'─' * fw}  {'─' * vw}"
    else:
        header = f"  {'Field':<{fw}}  {'CSV':<{vw}}"
        sep = f"  {'─' * fw}  {'─' * vw}"

    lines.append(header)
    lines.append(sep)

    # Build CSV header lookup
    csv_headers = {}
    if crow:
        csv_headers = build_csv_col_lookup(crow["_headers"])

    for field_name, sheet_col in fields:
        sheet_val = _s(_get(srow, sheet_col)) if srow else ""
        csv_val = ""
        if crow and field_name in csv_headers:
            csv_val = _s(crow.get(csv_headers[field_name], ""))

        # Skip fields empty in all shown sources
        if source == "both" and not sheet_val and not csv_val:
            continue
        if source == "sheet" and not sheet_val:
            continue
        if source == "csv" and not csv_val:
            continue

        trunc_s = (sheet_val[:vw - 1] + "…") if len(sheet_val) > vw else sheet_val
        trunc_c = (csv_val[:vw - 1] + "…") if len(csv_val) > vw else csv_val

        if source == "both":
            diff = "  ← DIFF" if sheet_val != csv_val and sheet_val and csv_val else ""
            lines.append(f"  {field_name:<{fw}}  {trunc_s:<{vw}}  {trunc_c:<{vw}}{diff}")
        elif source == "sheet":
            lines.append(f"  {field_name:<{fw}}  {trunc_s:<{vw}}")
        else:
            lines.append(f"  {field_name:<{fw}}  {trunc_c:<{vw}}")

    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch a specific record from Google Sheet and/or CSV by key.")
    parser.add_argument("record_type", choices=["births", "marriages", "deaths"])
    parser.add_argument("year", type=int)
    parser.add_argument("rec_num")
    parser.add_argument("-g", "--gender", help="Gender (муж/жен) — required for births/deaths")  # i18n: content — the values the option takes
    parser.add_argument("-m", "--month", type=int, required=True, help="Month number (1-12)")
    parser.add_argument("--source", choices=["both", "sheet", "csv"], default="both")
    parser.add_argument("--site", required=True,
                        help="the village's sheet: `[sheets] site` of its village.toml")
    args = parser.parse_args(argv)

    if args.record_type in ("births", "deaths") and not args.gender:
        parser.error(f"--gender is required for {args.record_type}")

    return args


def main(argv=None):
    args = parse_args(argv)
    cfg = site_config(args.site)
    if cfg.fmt is not FORMAT_FAMILIO_EXTENDED:
        # The tabs, the year column and FIELD_TO_SHEET_COL below are familio-extended's.
        layout = next((name for name, fmt in FORMATS.items() if fmt is cfg.fmt), str(t("cli.fetch_record.other_layout")))
        raise CorpusDataError(t("cli.fetch_record.layout", site=args.site, layout=layout))
    select(cfg)

    month_str = str(args.month)
    target_key = build_target_key(args.record_type, args.rec_num, args.gender, month_str)
    fields = get_fields_for_type(args.record_type)

    srow = None
    crow = None

    # Fetch sheet data
    if args.source in ("both", "sheet"):
        print("Fetching sheet data...", file=sys.stderr)
        tab = SHEET_TABS[args.record_type]
        sheets = fetch_all_sheets(cfg.spreadsheet_id)
        if tab not in sheets:
            print(f"WARNING: Sheet tab '{tab}' not found", file=sys.stderr)
        else:
            year_col = YEAR_COL[args.record_type]
            by_year = split_by_year(sheets[tab], year_col, village=cfg.village_filter)
            year_rows = by_year.get(args.year, [])
            if not year_rows:
                print(f"WARNING: No sheet rows for year {args.year}", file=sys.stderr)
            else:
                srow = find_sheet_row(year_rows, args.record_type, target_key)
                if srow is None:
                    print(f"WARNING: Record not found in sheet for key {target_key}",
                          file=sys.stderr)

    # Fetch CSV data
    if args.source in ("both", "csv"):
        csv_path = find_csv(args.year, args.record_type)
        if csv_path is None:
            print(f"ERROR: CSV file not found for {args.record_type} {args.year}",
                  file=sys.stderr)
        else:
            csv_rows = read_familio_csv(csv_path)
            crow = find_csv_row(csv_rows, args.record_type, target_key)
            if crow is None:
                print(f"WARNING: Record not found in CSV for key {target_key}",
                      file=sys.stderr)

    if srow is None and crow is None:
        print("No data found in either source.", file=sys.stderr)
        return 1

    output = format_table(args.record_type, target_key, args.year, srow, crow, fields,
                          args.source)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
