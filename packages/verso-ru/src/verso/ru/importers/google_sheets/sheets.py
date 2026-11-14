"""Google Sheets / CSV row access and authentication."""
from verso.ru.importers.google_sheets.cells import _get
from verso.ru.importers.google_sheets.columns import HEADER_ROWS




def _get_worksheet(spreadsheet_id, sheet_name):
    import gspread
    gc = gspread.oauth()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    target = sheet_name.lower()
    for ws in spreadsheet.worksheets():
        if ws.title.lower() == target:
            return ws
    raise ValueError(f"Sheet '{sheet_name}' not found in spreadsheet")



def _fetch_rows(worksheet, year, year_col_idx, village_filter=None, header_rows=HEADER_ROWS):
    """Fetch all matching data rows for the given year (and optional village)."""
    all_values = worksheet.get_all_values()
    return _filter_rows(all_values, year, year_col_idx, village_filter, header_rows)



def _fetch_rows_from_csv(csv_path, year, year_col_idx, village_filter=None, header_rows=1):
    """Fetch matching rows from a local CSV file."""
    import csv as csv_mod
    with open(csv_path, encoding='utf-8') as f:
        all_values = list(csv_mod.reader(f))
    return _filter_rows(all_values, year, year_col_idx, village_filter, header_rows)



def _filter_rows(all_values, year, year_col_idx, village_filter=None, header_rows=HEADER_ROWS):
    """Filter rows by year and optional village."""
    year_str = str(year)
    rows = []
    for row in all_values[header_rows:]:
        if len(row) > year_col_idx and str(row[year_col_idx]).strip() == year_str:
            if village_filter:
                row_village = _get(row, 6)
                if row_village.lower() != village_filter.lower():
                    continue
            rows.append(row)
    return rows
