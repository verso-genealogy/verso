#!/usr/bin/env python3
"""Unit tests for fetch_record.py."""

import io
import unittest
from unittest.mock import MagicMock, patch

from verso.ru.cli.fetch_record import (
    build_sheet_key, build_csv_key, build_target_key, get_fields_for_type, find_sheet_row, find_csv_row, format_table, parse_args, main)
from verso.ru.importers import validation
from verso.ru.importers.validation import SiteConfig
from verso.ru.importers.google_sheets import (
    B_RECORD_NUM, B_GENDER, B_B_MONTH, M_RECORD_NUM, M_W_MONTH, D_RECORD_NUM, D_GENDER, D_D_MONTH, B_PAGE, B_ARCHIVE)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_sheet_row(cols_dict, width=120):
    """Build a list of `width` empty strings, then set cols_dict[idx] = value."""
    row = [""] * width
    for idx, val in cols_dict.items():
        row[idx] = val
    return row


def make_csv_row(headers, cols_dict):
    """Build a CSV row dict keyed by int index with given headers."""
    d = {i: "" for i in range(len(headers))}
    for idx, val in cols_dict.items():
        d[idx] = val
    d["_headers"] = headers
    return d


# ─── Argument parsing ───────────────────────────────────────────────────────

class TestParseArgs(unittest.TestCase):
    def test_site_is_required(self):
        with patch("sys.stderr", new_callable=io.StringIO) as err, self.assertRaises(SystemExit):
            parse_args(["births", "1760", "13", "-g", "жен", "-m", "5"])
        self.assertIn("--site", err.getvalue())

    def test_births_requires_gender(self):
        with self.assertRaises(SystemExit):
            parse_args(["--site", "zamanilovka", "births", "1760", "13", "-m", "5"])

    def test_deaths_requires_gender(self):
        with self.assertRaises(SystemExit):
            parse_args(["--site", "zamanilovka", "deaths", "1760", "1", "-m", "3"])

    def test_marriages_no_gender_needed(self):
        args = parse_args(["--site", "zamanilovka", "marriages", "1760", "8", "-m", "5"])
        self.assertEqual(args.record_type, "marriages")
        self.assertIsNone(args.gender)

    def test_month_required(self):
        with self.assertRaises(SystemExit):
            parse_args(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен"])

    def test_source_defaults_to_both(self):
        args = parse_args(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5"])
        self.assertEqual(args.source, "both")

    def test_source_accepts_sheet(self):
        args = parse_args(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5", "--source", "sheet"])
        self.assertEqual(args.source, "sheet")

    def test_source_accepts_csv(self):
        args = parse_args(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5", "--source", "csv"])
        self.assertEqual(args.source, "csv")

    def test_births_all_args(self):
        args = parse_args(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5"])
        self.assertEqual(args.record_type, "births")
        self.assertEqual(args.year, 1760)
        self.assertEqual(args.rec_num, "13")
        self.assertEqual(args.gender, "жен")
        self.assertEqual(args.month, 5)


# ─── Key building ───────────────────────────────────────────────────────────

class TestBuildSheetKey(unittest.TestCase):
    def test_births_key(self):
        srow = make_sheet_row({B_RECORD_NUM: "13", B_GENDER: "жен", B_B_MONTH: "5"})
        key = build_sheet_key("births", srow)
        self.assertEqual(key, ("13", "жен", "5"))

    def test_marriages_key(self):
        srow = make_sheet_row({M_RECORD_NUM: "8", M_W_MONTH: "5"})
        key = build_sheet_key("marriages", srow)
        self.assertEqual(key, ("8", "5"))

    def test_deaths_key(self):
        srow = make_sheet_row({D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "3"})
        key = build_sheet_key("deaths", srow)
        self.assertEqual(key, ("1", "муж", "3"))


class TestBuildCsvKey(unittest.TestCase):
    def test_births_key(self):
        crow = {10: "13", 11: "жен", 13: "5"}
        key = build_csv_key("births", crow)
        self.assertEqual(key, ("13", "жен", "5"))

    def test_marriages_key(self):
        crow = {10: "8", 12: "5"}
        key = build_csv_key("marriages", crow)
        self.assertEqual(key, ("8", "5"))

    def test_deaths_key(self):
        crow = {10: "1", 11: "муж", 13: "3"}
        key = build_csv_key("deaths", crow)
        self.assertEqual(key, ("1", "муж", "3"))


class TestBuildTargetKey(unittest.TestCase):
    def test_births_key(self):
        key = build_target_key("births", "13", "жен", "5")
        self.assertEqual(key, ("13", "жен", "5"))

    def test_marriages_key(self):
        key = build_target_key("marriages", "8", None, "5")
        self.assertEqual(key, ("8", "5"))

    def test_deaths_key(self):
        key = build_target_key("deaths", "1", "муж", "3")
        self.assertEqual(key, ("1", "муж", "3"))


# ─── Row lookup ──────────────────────────────────────────────────────────────

class TestFindSheetRow(unittest.TestCase):
    def test_finds_matching_row(self):
        srow = make_sheet_row({B_RECORD_NUM: "13", B_GENDER: "жен", B_B_MONTH: "5"})
        rows = [(2, srow)]
        result = find_sheet_row(rows, "births", ("13", "жен", "5"))
        self.assertIs(result, srow)

    def test_returns_none_when_not_found(self):
        srow = make_sheet_row({B_RECORD_NUM: "13", B_GENDER: "жен", B_B_MONTH: "5"})
        rows = [(2, srow)]
        result = find_sheet_row(rows, "births", ("99", "жен", "5"))
        self.assertIsNone(result)

    def test_returns_first_match(self):
        srow1 = make_sheet_row({B_RECORD_NUM: "13", B_GENDER: "жен", B_B_MONTH: "5",
                                B_PAGE: "100"})
        srow2 = make_sheet_row({B_RECORD_NUM: "13", B_GENDER: "жен", B_B_MONTH: "5",
                                B_PAGE: "200"})
        rows = [(2, srow1), (3, srow2)]
        result = find_sheet_row(rows, "births", ("13", "жен", "5"))
        self.assertIs(result, srow1)


class TestFindCsvRow(unittest.TestCase):
    def test_finds_matching_row(self):
        crow = {10: "13", 11: "жен", 13: "5", "_headers": []}
        result = find_csv_row([crow], "births", ("13", "жен", "5"))
        self.assertIs(result, crow)

    def test_returns_none_when_not_found(self):
        crow = {10: "13", 11: "жен", 13: "5", "_headers": []}
        result = find_csv_row([crow], "births", ("99", "жен", "5"))
        self.assertIsNone(result)


# ─── Display / formatting ───────────────────────────────────────────────────

class TestFormatTable(unittest.TestCase):
    def _make_fields(self):
        return [("Лист", B_PAGE), ("Архив", B_ARCHIVE)]

    def _make_csv_headers(self):
        headers = [""] * 120
        headers[B_PAGE] = "Лист"
        headers[B_ARCHIVE] = "Архив"
        return headers

    def test_side_by_side_both(self):
        srow = make_sheet_row({B_PAGE: "100об", B_ARCHIVE: "ГАТО"})
        headers = self._make_csv_headers()
        crow = make_csv_row(headers, {B_PAGE: "100об", B_ARCHIVE: "ГАТО"})
        fields = self._make_fields()

        output = format_table("births", ("13", "жен", "5"), 1760, srow, crow, fields, "both")
        self.assertIn("births", output)
        self.assertIn("100об", output)
        self.assertIn("ГАТО", output)
        self.assertNotIn("DIFF", output)

    def test_diff_marker(self):
        srow = make_sheet_row({B_PAGE: "100об", B_ARCHIVE: "ГАТО"})
        headers = self._make_csv_headers()
        crow = make_csv_row(headers, {B_PAGE: "100", B_ARCHIVE: "ГАТО"})
        fields = self._make_fields()

        output = format_table("births", ("13", "жен", "5"), 1760, srow, crow, fields, "both")
        self.assertIn("← DIFF", output)

    def test_empty_fields_omitted(self):
        srow = make_sheet_row({B_PAGE: "100об"})  # B_ARCHIVE empty
        headers = self._make_csv_headers()
        crow = make_csv_row(headers, {B_PAGE: "100об"})  # B_ARCHIVE empty
        fields = self._make_fields()

        output = format_table("births", ("13", "жен", "5"), 1760, srow, crow, fields, "both")
        self.assertIn("Лист", output)
        self.assertNotIn("Архив", output)

    def test_source_sheet_only(self):
        srow = make_sheet_row({B_PAGE: "100об"})
        fields = self._make_fields()

        output = format_table("births", ("13", "жен", "5"), 1760, srow, None, fields, "sheet")
        self.assertIn("Sheet", output)
        self.assertNotIn("CSV", output)

    def test_source_csv_only(self):
        headers = self._make_csv_headers()
        crow = make_csv_row(headers, {B_PAGE: "100об"})
        fields = self._make_fields()

        output = format_table("births", ("13", "жен", "5"), 1760, None, crow, fields, "csv")
        self.assertIn("CSV", output)
        self.assertNotIn("Sheet", output)

    def test_marriages_key_desc(self):
        fields = [("Лист", 5)]
        output = format_table("marriages", ("8", "5"), 1760, None, None, fields, "both")
        self.assertIn("rec_num=8", output)
        self.assertNotIn("gender", output)


# ─── Get fields ──────────────────────────────────────────────────────────────

class TestGetFieldsForType(unittest.TestCase):
    def test_births_returns_fields(self):
        fields = get_fields_for_type("births")
        names = [f for f, _ in fields]
        self.assertIn("Лист", names)
        self.assertIn("Архив", names)

    def test_marriages_returns_fields(self):
        fields = get_fields_for_type("marriages")
        names = [f for f, _ in fields]
        self.assertIn("Лист", names)
        self.assertIn("Жених: Имя (совр. орф.)", names)

    def test_deaths_returns_fields(self):
        fields = get_fields_for_type("deaths")
        names = [f for f, _ in fields]
        self.assertIn("Лист", names)
        self.assertIn("Лет", names)

    def test_no_cross_type_fields(self):
        fields = get_fields_for_type("births")
        names = [f for f, _ in fields]
        self.assertNotIn("Жених: Имя (совр. орф.)", names)
        self.assertNotIn("Лет", names)


# ─── Integration (mocked gspread) ───────────────────────────────────────────

class TestSheetFormat(unittest.TestCase):
    def test_a_sheet_of_another_layout_is_refused(self) -> None:
        """fetch_record knows the familio-extended columns only; a familio-standard
        sheet would be read by the wrong columns, without a word."""
        from verso.core.corpus_data import CorpusDataError
        from verso.ru.importers.google_sheets import FORMAT_FAMILIO_STANDARD
        site = SiteConfig(spreadsheet_id="s", village_filter="Вязовка", village="Вязовка",
                          csv_prefix="Вязовка", dsl_prefix="vyazovka", fmt=FORMAT_FAMILIO_STANDARD)
        def site_config(_site: str) -> SiteConfig:
            return site
        self.addCleanup(validation.select, validation._NO_SITE)  # pyright: ignore[reportPrivateUsage]
        with patch("verso.ru.cli.fetch_record.site_config", site_config), \
                patch("verso.ru.cli.fetch_record.fetch_all_sheets") as fetch, \
                self.assertRaisesRegex(CorpusDataError, "fetch_record читает только таблицы familio-extended, "
                                                        "а у «vyazovka» — familio-standard"):
            main(["--site", "vyazovka", "births", "1900", "1", "-g", "муж", "-m", "1"])
        fetch.assert_not_called()


class TestMainIntegration(unittest.TestCase):
    def setUp(self) -> None:
        # The site is Заманиловка's; its village.toml is no part of the tests' workspace.
        site = SiteConfig(spreadsheet_id="test-sheet", village_filter="Заманиловка", village="Заманиловка",
                          csv_prefix="Заманиловка", dsl_prefix="zamanilovka")
        def site_config(_site: str) -> SiteConfig:
            return site
        self.enterContext(patch("verso.ru.cli.fetch_record.site_config", site_config))
        self.addCleanup(validation.select, validation._NO_SITE)  # pyright: ignore[reportPrivateUsage]

    def _mock_sheets(self, sheet_rows):
        """Return mock gspread that yields given sheet_rows for рождение tab."""
        mock_gspread = MagicMock()
        mock_gc = MagicMock()
        mock_gspread.oauth.return_value = mock_gc

        mock_ws = MagicMock()
        mock_ws.title = "рождение"
        mock_ws.get_all_values.return_value = sheet_rows

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = [mock_ws]
        mock_gc.open_by_key.return_value = mock_spreadsheet
        return mock_gspread

    def _make_header_rows(self, width=120):
        """Create HEADER_ROWS dummy header rows."""
        from verso.ru.importers.google_sheets import HEADER_ROWS
        return [["h"] * width] * HEADER_ROWS

    # fetch_record imports find_csv by name: the patch goes where it is looked up.
    # Patched on verso.ru.importers.validation it reached nobody, and the test read
    # the real Заманиловка 1760 CSV until the tests got a workspace of their own.
    @patch("verso.ru.cli.fetch_record.find_csv")
    @patch("verso.ru.cli.fetch_record.read_familio_csv")
    def test_source_csv_skips_sheet(self, mock_read_csv, mock_find_csv):
        """--source csv should not fetch sheet data."""
        headers = [""] * 20
        headers[10] = "rec_num"
        headers[11] = "gender"
        headers[13] = "month"
        crow = make_csv_row(headers, {10: "13", 11: "жен", 13: "5"})
        mock_find_csv.return_value = "/fake/path.csv"
        mock_read_csv.return_value = [crow]

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO):
                ret = main(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5", "--source", "csv"])
        self.assertEqual(ret, 0)

    @patch("verso.ru.cli.fetch_record.find_csv")
    def test_csv_not_found(self, mock_find_csv):
        """Missing CSV prints error."""
        mock_find_csv.return_value = None

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                ret = main(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5", "--source", "csv"])
        self.assertIn("CSV file not found", mock_err.getvalue())
        self.assertEqual(ret, 1)

    @patch("verso.ru.cli.fetch_record.find_csv")
    @patch("verso.ru.cli.fetch_record.read_familio_csv")
    def test_record_not_found_in_csv(self, mock_read_csv, mock_find_csv):
        """Record not in CSV prints warning."""
        mock_find_csv.return_value = "/fake/path.csv"
        headers = [""] * 20
        crow = make_csv_row(headers, {10: "99", 11: "муж", 13: "1"})
        mock_read_csv.return_value = [crow]

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                ret = main(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5", "--source", "csv"])
        self.assertIn("Record not found in CSV", mock_err.getvalue())
        self.assertEqual(ret, 1)

    @patch("verso.ru.cli.fetch_record.fetch_all_sheets")
    def test_record_not_found_in_sheet(self, mock_fetch):
        """Record not in sheet prints warning."""
        headers = self._make_header_rows()
        srow = make_sheet_row({B_RECORD_NUM: "99", B_GENDER: "муж", B_B_MONTH: "1"})
        srow[14] = "1760"
        srow[6] = "Заманиловка"
        mock_fetch.return_value = {"рождение": headers + [srow]}

        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                ret = main(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5", "--source", "sheet"])
        self.assertIn("Record not found in sheet", mock_err.getvalue())
        self.assertEqual(ret, 1)

    @patch("verso.ru.cli.fetch_record.find_csv")
    @patch("verso.ru.cli.fetch_record.read_familio_csv")
    @patch("verso.ru.cli.fetch_record.fetch_all_sheets")
    def test_full_flow_both(self, mock_fetch, mock_read_csv, mock_find_csv):
        """Full flow with both sources prints table."""
        headers_rows = self._make_header_rows()
        srow = make_sheet_row({B_RECORD_NUM: "13", B_GENDER: "жен", B_B_MONTH: "5",
                               B_PAGE: "100об"})
        srow[14] = "1760"
        srow[6] = "Заманиловка"
        mock_fetch.return_value = {"рождение": headers_rows + [srow]}

        csv_headers = [""] * 120
        csv_headers[B_PAGE] = "Лист"
        crow = make_csv_row(csv_headers, {10: "13", 11: "жен", 13: "5",
                                          B_PAGE: "100об"})
        mock_find_csv.return_value = "/fake/path.csv"
        mock_read_csv.return_value = [crow]

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("sys.stderr", new_callable=io.StringIO):
                ret = main(["--site", "zamanilovka", "births", "1760", "13", "-g", "жен", "-m", "5"])
        self.assertEqual(ret, 0)
        output = mock_out.getvalue()
        self.assertIn("births", output)
        self.assertIn("100об", output)


if __name__ == "__main__":
    unittest.main()
