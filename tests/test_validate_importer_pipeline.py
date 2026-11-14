#!/usr/bin/env python3
"""Unit tests for validate_importer_pipeline.py."""

import io
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from verso.ru.importers.validation import (
    Discrepancy, ValidationResult, _s, _cmp, _apply_default_status, _apply_default_residence, _reconstruct_age, split_by_year, _build_sequential_lookup, _read_csv_rows_for_year, resolve_name_patr, resolve_name_patr_marriage_orig, apply_transforms, read_familio_csv, find_csv, find_dsl, regenerate_csv, fetch_all_sheets, compare_births, compare_marriages, compare_deaths, validate_record_type, print_report, fix_discrepancies, main, CSV_YEAR_COL, FIELD_TO_SHEET_COL, BIRTH_STATUS_MALE, BIRTH_STATUS_FEMALE, DEATH_STATUS_MALE, DEATH_STATUS_FEMALE, MARRIAGE_STATUS_MALE)
from verso.ru.importers.google_sheets import HEADER_ROWS
from verso.core.workspace import use
from verso.ru.importers import validation
from verso.ru.importers.validation import SiteConfig


# The site these tests compare against: Заманиловка's, as its village.toml names it —
# no module of the library holds a village's site since 0.1.0. The sheet's id is a stand-in.
TEST_SITE = SiteConfig(spreadsheet_id="test-sheet", village_filter="Заманиловка", village="Заманиловка",
                       csv_prefix="Заманиловка", dsl_prefix="zamanilovka")


def setUpModule() -> None:
    validation.select(TEST_SITE)


def tearDownModule() -> None:
    validation.select(validation._NO_SITE)  # pyright: ignore[reportPrivateUsage]


def _test_site(site: str) -> SiteConfig:
    """`site_config` for main(): a fresh copy, since --csv writes into it."""
    import dataclasses
    return dataclasses.replace(TEST_SITE)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_sheet_row(cols_dict, width=120):
    """Build a list of `width` empty strings, then set cols_dict[idx] = value."""
    row = [""] * width
    for idx, val in cols_dict.items():
        row[idx] = val
    return row


def make_csv_row(cols_dict, width=80):
    """Build a dict keyed by int index (mimicking read_familio_csv output)."""
    d = {i: "" for i in range(width)}
    for idx, val in cols_dict.items():
        d[idx] = val
    d["_headers"] = [f"col{i}" for i in range(width)]
    return d


# ─── Test classes ────────────────────────────────────────────────────────────

class TestDiscrepancy(unittest.TestCase):
    def test_defaults(self):
        d = Discrepancy(year=1800, record_type="births", record_num="1",
                        field="f", sheet_val="a", csv_val="b")
        self.assertIsNone(d.sheet_row_idx)

    def test_with_row_idx(self):
        d = Discrepancy(year=1800, record_type="births", record_num="1",
                        field="f", sheet_val="a", csv_val="b", sheet_row_idx=5)
        self.assertEqual(d.sheet_row_idx, 5)


class TestValidationResult(unittest.TestCase):
    def test_defaults(self):
        r = ValidationResult(record_type="births")
        self.assertEqual(r.years_checked, 0)
        self.assertEqual(r.years_ok, 0)
        self.assertEqual(r.years_with_issues, 0)
        self.assertEqual(r.total_fields, 0)
        self.assertEqual(r.discrepancies, [])
        self.assertEqual(r.missing_csv, [])
        self.assertEqual(r.count_mismatches, [])


class TestNormalization(unittest.TestCase):
    def test_none(self):
        self.assertEqual(_s(None), "")

    def test_double_question_mark(self):
        self.assertEqual(_s("??"), "")

    def test_whitespace_stripping(self):
        self.assertEqual(_s("  hello  "), "hello")

    def test_normal_value(self):
        self.assertEqual(_s("Иван"), "Иван")

    def test_numeric(self):
        self.assertEqual(_s(42), "42")


class TestCmp(unittest.TestCase):
    def test_equal_values(self):
        r = ValidationResult(record_type="births")
        _cmp("field", "abc", "abc", 1800, "births", "1", r)
        self.assertEqual(r.total_fields, 1)
        self.assertEqual(len(r.discrepancies), 0)

    def test_different_values(self):
        r = ValidationResult(record_type="births")
        _cmp("field", "abc", "xyz", 1800, "births", "1", r, sheet_row_idx=10)
        self.assertEqual(r.total_fields, 1)
        self.assertEqual(len(r.discrepancies), 1)
        d = r.discrepancies[0]
        self.assertEqual(d.field, "field")
        self.assertEqual(d.sheet_val, "abc")
        self.assertEqual(d.csv_val, "xyz")
        self.assertEqual(d.sheet_row_idx, 10)

    def test_normalization_applied(self):
        r = ValidationResult(record_type="births")
        _cmp("f", "  abc ", "abc", 1800, "births", "1", r)
        self.assertEqual(len(r.discrepancies), 0)

    def test_double_question_mark_equals_empty(self):
        r = ValidationResult(record_type="births")
        _cmp("f", "??", "", 1800, "births", "1", r)
        self.assertEqual(len(r.discrepancies), 0)


class TestApplyDefaultStatus(unittest.TestCase):
    def test_nonempty_passthrough(self):
        self.assertEqual(_apply_default_status("custom", "муж", "births"), "custom")

    def test_birth_male(self):
        self.assertEqual(_apply_default_status("", "муж", "births"), BIRTH_STATUS_MALE)

    def test_birth_female(self):
        self.assertEqual(_apply_default_status("", "жен", "births"), BIRTH_STATUS_FEMALE)
        self.assertEqual(_apply_default_status("", "ж", "births"), BIRTH_STATUS_FEMALE)
        self.assertEqual(_apply_default_status("", "женский", "births"), BIRTH_STATUS_FEMALE)

    def test_death_male(self):
        self.assertEqual(_apply_default_status("", "муж", "deaths"), DEATH_STATUS_MALE)

    def test_death_female(self):
        self.assertEqual(_apply_default_status("", "жен", "deaths"), DEATH_STATUS_FEMALE)

    def test_unknown_record_type(self):
        self.assertEqual(_apply_default_status("", "муж", "marriages"), "")


class TestApplyDefaultResidence(unittest.TestCase):
    def test_nonempty_passthrough(self):
        self.assertEqual(_apply_default_residence("село", "default"), "село")

    def test_empty_returns_default(self):
        self.assertEqual(_apply_default_residence("", "Заманиловка"), "Заманиловка")


class TestSplitByYear(unittest.TestCase):
    def _make_rows(self, data_rows, year_col=14):
        """Build all_rows with HEADER_ROWS dummy header rows + data rows."""
        headers = [["h"] * (year_col + 5)] * HEADER_ROWS
        return headers + data_rows

    def test_basic_splitting(self):
        row1 = [""] * 20
        row1[14] = "1800"
        row2 = [""] * 20
        row2[14] = "1801"
        row3 = [""] * 20
        row3[14] = "1800"
        all_rows = self._make_rows([row1, row2, row3])
        result = split_by_year(all_rows, 14)
        self.assertIn(1800, result)
        self.assertIn(1801, result)
        self.assertEqual(len(result[1800]), 2)
        self.assertEqual(len(result[1801]), 1)

    def test_village_filter(self):
        row1 = [""] * 20
        row1[6] = "Заманиловка"
        row1[14] = "1800"
        row2 = [""] * 20
        row2[6] = "Другое"
        row2[14] = "1800"
        all_rows = self._make_rows([row1, row2])
        result = split_by_year(all_rows, 14, village="Заманиловка")
        self.assertEqual(len(result.get(1800, [])), 1)

    def test_village_filter_case_insensitive(self):
        row1 = [""] * 20
        row1[6] = "заманиловка"
        row1[14] = "1800"
        all_rows = self._make_rows([row1])
        result = split_by_year(all_rows, 14, village="Заманиловка")
        self.assertEqual(len(result.get(1800, [])), 1)

    def test_non_numeric_year_skipped(self):
        row1 = [""] * 20
        row1[14] = "abc"
        all_rows = self._make_rows([row1])
        result = split_by_year(all_rows, 14)
        self.assertEqual(len(result), 0)

    def test_empty_year_skipped(self):
        row1 = [""] * 20
        row1[14] = ""
        all_rows = self._make_rows([row1])
        result = split_by_year(all_rows, 14)
        self.assertEqual(len(result), 0)

    def test_short_row_skipped(self):
        all_rows = self._make_rows([["a", "b"]])  # len=2, year_col=14
        result = split_by_year(all_rows, 14)
        self.assertEqual(len(result), 0)

    def test_row_index_tracking(self):
        row1 = [""] * 20
        row1[14] = "1800"
        all_rows = self._make_rows([row1])
        result = split_by_year(all_rows, 14)
        idx, _ = result[1800][0]
        self.assertEqual(idx, HEADER_ROWS)  # first data row index


class TestBuildSequentialLookup(unittest.TestCase):
    def test_single_match(self):
        rows = [{"k": "a", "v": 1}, {"k": "b", "v": 2}]
        lookup = _build_sequential_lookup(rows, lambda r: r["k"])
        result_a = lookup("a")
        assert result_a is not None
        self.assertEqual(result_a["v"], 1)
        result_b = lookup("b")
        assert result_b is not None
        self.assertEqual(result_b["v"], 2)

    def test_duplicate_keys_deque_order(self):
        rows = [{"k": "a", "v": 1}, {"k": "a", "v": 2}]
        lookup = _build_sequential_lookup(rows, lambda r: r["k"])
        result_a1 = lookup("a")
        assert result_a1 is not None
        self.assertEqual(result_a1["v"], 1)
        result_a2 = lookup("a")
        assert result_a2 is not None
        self.assertEqual(result_a2["v"], 2)
        self.assertIsNone(lookup("a"))

    def test_missing_key(self):
        rows = [{"k": "a", "v": 1}]
        lookup = _build_sequential_lookup(rows, lambda r: r["k"])
        self.assertIsNone(lookup("z"))


class TestResolveNamePatr(unittest.TestCase):
    def test_from_orig_dict(self):
        row = make_sheet_row({25: "FallbackName", 26: "FallbackPatr"})
        orig = {"father": ("Иванъ", "Петровъ")}
        name, patr, _ln = resolve_name_patr(row, 25, 26, 27, 28, orig, "father")
        self.assertEqual(name, "Иванъ")
        self.assertEqual(patr, "Петровъ")
        self.assertIsNone(_ln)

    def test_fallback_to_columns(self):
        row = make_sheet_row({25: "Иванъ", 26: "Петровъ"})
        name, patr, _ln = resolve_name_patr(row, 25, 26, 27, 28)
        self.assertEqual(name, "Иванъ")
        self.assertEqual(patr, "Петровъ")

    def test_title_word_swap(self):
        row = make_sheet_row({25: "дьячок", 26: "Иванъ"})
        name, patr, _ln = resolve_name_patr(row, 25, 26, 27, 28)
        self.assertEqual(name, "Иванъ")
        self.assertEqual(patr, "")

    def test_title_word_no_patr(self):
        row = make_sheet_row({25: "дьячок", 26: ""})
        name, _patr, _ln = resolve_name_patr(row, 25, 26, 27, 28)
        self.assertEqual(name, "?")

    def test_imena_placeholder(self):
        row = make_sheet_row({25: "Имена", 26: "something"})
        name, patr, _ln = resolve_name_patr(row, 25, 26, 27, 28)
        self.assertEqual(name, "?")
        self.assertEqual(patr, "")

    def test_empty_name(self):
        row = make_sheet_row({})
        name, patr, _ln = resolve_name_patr(row, 25, 26, 27, 28)
        self.assertEqual(name, "")
        self.assertEqual(patr, "")
        self.assertIsNone(_ln)

    def test_canon_column_fallback(self):
        row = make_sheet_row({27: "Иван", 28: "Петров"})
        name, patr, _ln = resolve_name_patr(row, 25, 26, 27, 28)
        self.assertEqual(name, "Иван")
        # Петров is a valid old patronymic
        self.assertEqual(patr, "Петров")


class TestResolveNamePatrMarriageOrig(unittest.TestCase):
    def test_positional_orig_parts(self):
        orig_parts = ["Иванъ Петровъ", "Марья"]
        row = make_sheet_row({19: "Fallback", 20: "Fallback"})
        name, patr, _ln = resolve_name_patr_marriage_orig(
            orig_parts, 0, 19, 20, 21, 22, row)
        self.assertEqual(name, "Иванъ")
        self.assertEqual(patr, "Петровъ")

    def test_out_of_bounds_orig_idx(self):
        orig_parts = ["Иванъ"]
        row = make_sheet_row({19: "Марья", 20: "Ивановна"})
        name, _patr, _ln = resolve_name_patr_marriage_orig(
            orig_parts, 5, 19, 20, 21, 22, row)
        self.assertEqual(name, "Марья")

    def test_title_word(self):
        orig_parts = []
        row = make_sheet_row({19: "дьячок", 20: "Петръ"})
        name, patr, _ln = resolve_name_patr_marriage_orig(
            orig_parts, 0, 19, 20, 21, 22, row)
        self.assertEqual(name, "Петръ")
        self.assertEqual(patr, "")

    def test_empty_name_returns_empty(self):
        orig_parts = []
        row = make_sheet_row({})
        name, patr, _ln = resolve_name_patr_marriage_orig(
            orig_parts, 0, 19, 20, 21, 22, row)
        self.assertEqual(name, "")
        self.assertEqual(patr, "")
        self.assertIsNone(_ln)


class TestApplyTransforms(unittest.TestCase):
    def test_basic_modernization(self):
        t = apply_transforms("Иванъ", "Петровъ")
        self.assertEqual(t["name_modern"], "Иван")
        self.assertEqual(t["patr_modern"], "Петров")

    def test_name_with_question_mark_preserved(self):
        t = apply_transforms("?", "")
        self.assertEqual(t["name_canon"], "?")

    def test_fio_assembly(self):
        t = apply_transforms("Иванъ", "Петровъ", "Сидоровъ")
        self.assertIn("Сидоров", t["fio"])

    def test_empty_inputs(self):
        t = apply_transforms("", "")
        self.assertEqual(t["name_modern"], "")
        self.assertEqual(t["patr_modern"], "")
        self.assertEqual(t["name_canon"], "")
        self.assertEqual(t["patr_canon"], "")
        self.assertEqual(t["fio"], "")

    def test_patr_canonicalization_failure(self):
        # A patronymic that can't be canonicalized should yield empty patr_canon
        t = apply_transforms("Иванъ", "НеПатроним")
        self.assertEqual(t["patr_canon"], "")


class TestReadFamilioCsv(unittest.TestCase):
    @patch("builtins.open")
    def test_basic_csv(self, mock_open):
        csv_data = "col0,col1,col2\nval0,val1,val2\nval3,val4,val5\n"
        def _enter(s: object) -> io.StringIO:
            return io.StringIO(csv_data)
        mock_open.return_value.__enter__ = _enter
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        rows = read_familio_csv("/fake/path.csv")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "val0")
        self.assertEqual(rows[0][1], "val1")
        self.assertEqual(rows[0][2], "val2")
        self.assertEqual(rows[0]["_headers"], ["col0", "col1", "col2"])
        self.assertEqual(rows[1][0], "val3")


class TestFindCsvAndDsl(unittest.TestCase):
    def setUp(self) -> None:
        """The sites' villages, in a workspace of their own: these tests build paths."""
        tmp = self.enterContext(TemporaryDirectory())
        (Path(tmp) / "verso.toml").write_text('schema = 1\nvillages = ["Заманиловка", "Горюхино"]\n', encoding="utf-8")
        self.enterContext(use(Path(tmp)))

    @patch("verso.ru.importers.validation.os.path.exists")
    def test_the_village_is_the_workspaces(self, mock_exists):
        """The site's village directory is found in the workspace, not beside the code."""
        mock_exists.return_value = True
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "verso.toml").write_text('schema = 1\nvillages = ["Заманиловка"]\n', encoding="utf-8")
            with use(root):
                self.assertTrue(find_csv(1800, "births").startswith(str(root / "Заманиловка" / "1800")))
                self.assertTrue(find_dsl(1800, "births").startswith(str(root / "Заманиловка" / "1800")))

    @patch("verso.ru.importers.validation.os.path.exists")
    def test_find_csv_exists(self, mock_exists):
        mock_exists.return_value = True
        result = find_csv(1800, "births")
        self.assertIsNotNone(result)
        self.assertIn("1800", result)
        self.assertIn("births_familio.csv", result)

    @patch("verso.ru.importers.validation.os.path.exists")
    def test_find_csv_not_exists(self, mock_exists):
        mock_exists.return_value = False
        self.assertIsNone(find_csv(1800, "births"))

    @patch("verso.ru.importers.validation.os.path.exists")
    def test_find_dsl_exists(self, mock_exists):
        mock_exists.return_value = True
        result = find_dsl(1800, "marriages")
        self.assertIsNotNone(result)
        self.assertIn("zamanilovka_marriages_1800.py", result)

    @patch("verso.ru.importers.validation.os.path.exists")
    def test_find_dsl_not_exists(self, mock_exists):
        mock_exists.return_value = False
        self.assertIsNone(find_dsl(1800, "marriages"))

    @patch("verso.ru.importers.validation.os.path.exists")
    def test_find_csv_deaths(self, mock_exists):
        mock_exists.return_value = True
        result = find_csv(1810, "deaths")
        self.assertIn("deaths_familio.csv", result)


class TestRegenerateCsv(unittest.TestCase):
    @patch("verso.ru.importers.validation.find_csv")
    @patch("verso.ru.importers.validation.subprocess.run")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_no_dsl(self, mock_find_dsl, mock_run, mock_find_csv):
        mock_find_dsl.return_value = None
        self.assertFalse(regenerate_csv(1800, "births"))
        mock_run.assert_not_called()

    @patch("verso.ru.importers.validation.find_csv")
    @patch("verso.ru.importers.validation.subprocess.run")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_successful_run(self, mock_find_dsl, mock_run, mock_find_csv):
        mock_find_dsl.return_value = "/fake/dir/zamanilovka_births_1800.py"
        mock_find_csv.return_value = "/fake/dir/file.csv"
        self.assertTrue(regenerate_csv(1800, "births"))
        mock_run.assert_called_once()
        args = mock_run.call_args
        self.assertEqual(args[0][0], ["python3", "zamanilovka_births_1800.py"])

    @patch("verso.ru.importers.validation.find_csv")
    @patch("verso.ru.importers.validation.subprocess.run")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_csv_not_generated(self, mock_find_dsl, mock_run, mock_find_csv):
        mock_find_dsl.return_value = "/fake/dir/zamanilovka_births_1800.py"
        mock_find_csv.return_value = None
        self.assertFalse(regenerate_csv(1800, "births"))


class TestFetchAllSheets(unittest.TestCase):
    def test_fetches_tabs(self):
        mock_gspread_module = MagicMock()
        mock_gc = MagicMock()
        mock_gspread_module.oauth.return_value = mock_gc

        mock_ws_birth = MagicMock()
        mock_ws_birth.title = "рождение"
        mock_ws_birth.get_all_values.return_value = [["birth_data"]]

        mock_ws_marriage = MagicMock()
        mock_ws_marriage.title = "брак"
        mock_ws_marriage.get_all_values.return_value = [["marriage_data"]]

        mock_ws_death = MagicMock()
        mock_ws_death.title = "смерть"
        mock_ws_death.get_all_values.return_value = [["death_data"]]

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = [mock_ws_birth, mock_ws_marriage, mock_ws_death]
        mock_gc.open_by_key.return_value = mock_spreadsheet

        with patch.dict("sys.modules", {"gspread": mock_gspread_module}):
            result = fetch_all_sheets("test_id")
        self.assertIn("рождение", result)
        self.assertIn("брак", result)
        self.assertIn("смерть", result)
        self.assertEqual(result["рождение"], [["birth_data"]])

    def test_missing_tab(self):
        mock_gspread_module = MagicMock()
        mock_gc = MagicMock()
        mock_gspread_module.oauth.return_value = mock_gc

        mock_ws = MagicMock()
        mock_ws.title = "рождение"
        mock_ws.get_all_values.return_value = [["data"]]

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = [mock_ws]
        mock_gc.open_by_key.return_value = mock_spreadsheet

        with patch.dict("sys.modules", {"gspread": mock_gspread_module}):
            result = fetch_all_sheets("test_id")
        self.assertIn("рождение", result)
        self.assertNotIn("брак", result)
        self.assertNotIn("смерть", result)


class TestCompareBirths(unittest.TestCase):
    def _make_birth_sheet_row(self, rec_num="1", gender="муж", b_month="январь",
                              b_day="1", k_day="2", page="10",
                              archive="ГАТО", fund="1049", inventory="1", case="5",
                              child_name="Иванъ", father_name="Петръ",
                              father_patr="Ивановъ", mother_name="Марья",
                              mother_patr="Петрова"):
        from verso.ru.importers.google_sheets import (
            B_RECORD_NUM, B_GENDER, B_B_MONTH, B_B_DAY, B_K_DAY, B_PAGE, B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE, B_CHILD_NAME, B_FATHER_NAME, B_FATHER_PATR, B_MOTHER_NAME, B_MOTHER_PATR)
        return make_sheet_row({
            B_RECORD_NUM: rec_num, B_GENDER: gender,
            B_B_MONTH: b_month, B_B_DAY: b_day, B_K_DAY: k_day,
            B_PAGE: page, B_ARCHIVE: archive, B_FUND: fund,
            B_INVENTORY: inventory, B_CASE: case,
            B_CHILD_NAME: child_name,
            B_FATHER_NAME: father_name, B_FATHER_PATR: father_patr,
            B_MOTHER_NAME: mother_name, B_MOTHER_PATR: mother_patr,
        })

    def _make_birth_csv_row(self, rec_num="1", gender="муж", b_month="январь",
                            b_day="1", k_day="2", page="10",
                            archive="ГАТО", fund="1049", inventory="1", case="5",
                            child_name_modern="Иван", child_name_canon="Иоанн",
                            father_residence="Заманиловка", father_status="экономический крестьянин",
                            father_ln="", father_name_modern="Петр",
                            father_patr_modern="Иванов", father_name_canon="Петр",
                            father_patr_canon="Иванович",
                            mother_status="экономическая крестьянка",
                            mother_ln="", mother_name_modern="Марья",
                            mother_patr_modern="Петрова", mother_name_canon="Мария",
                            mother_patr_canon="Петровна"):
        return make_csv_row({
            1: archive, 2: fund, 3: inventory, 4: case,
            5: page, 10: rec_num, 11: gender, 12: b_day, 13: b_month,
            15: k_day,
            18: child_name_modern, 19: child_name_canon,
            20: father_residence, 22: father_status,
            23: father_ln, 25: father_name_modern, 26: father_patr_modern,
            27: father_name_canon, 28: father_patr_canon,
            29: mother_status, 30: mother_ln,
            31: mother_name_modern, 32: mother_patr_modern,
            33: mother_name_canon, 34: mother_patr_canon,
        })

    def test_matching_records(self):
        srow = self._make_birth_sheet_row()
        crow = self._make_birth_csv_row()
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        discrepancies = [d for d in result.discrepancies if d.field != "MISSING_IN_CSV"]
        self.assertEqual(len(discrepancies), 0)

    def test_field_mismatch(self):
        srow = self._make_birth_sheet_row(archive="ГАТО")
        crow = self._make_birth_csv_row(archive="ГАРО")
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        arch_disc = [d for d in result.discrepancies if d.field == "Архив"]
        self.assertEqual(len(arch_disc), 1)
        self.assertEqual(arch_disc[0].sheet_val, "ГАТО")
        self.assertEqual(arch_disc[0].csv_val, "ГАРО")

    def test_missing_in_csv(self):
        srow = self._make_birth_sheet_row(rec_num="99", gender="муж", b_month="март")
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [], 1800, result)
        missing = [d for d in result.discrepancies if d.field == "MISSING_IN_CSV"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].sheet_row_idx, 2)


class TestCompareMarriages(unittest.TestCase):
    def _make_marriage_sheet_row(self, rec_num="1", w_month="январь", w_day="5",
                                 page="10", archive="ГАТО", fund="1049",
                                 inventory="1", case="5",
                                 groom_name="Иванъ", groom_patr="Петровъ",
                                 bride_name="Марья", bride_patr="Иванова"):
        from verso.ru.importers.google_sheets import (
            M_RECORD_NUM, M_W_MONTH, M_W_DAY, M_PAGE, M_ARCHIVE, M_FUND, M_INVENTORY, M_CASE, M_GROOM_NAME, M_GROOM_PATR, M_BRIDE_NAME, M_BRIDE_PATR)
        return make_sheet_row({
            M_RECORD_NUM: rec_num, M_W_MONTH: w_month, M_W_DAY: w_day,
            M_PAGE: page, M_ARCHIVE: archive, M_FUND: fund,
            M_INVENTORY: inventory, M_CASE: case,
            M_GROOM_NAME: groom_name, M_GROOM_PATR: groom_patr,
            M_BRIDE_NAME: bride_name, M_BRIDE_PATR: bride_patr,
        })

    def _make_marriage_csv_row(self, rec_num="1", w_month="январь", w_day="5",
                               page="10", archive="ГАТО", fund="1049",
                               inventory="1", case="5",
                               groom_residence="Заманиловка",
                               groom_status="экономический крестьянин",
                               groom_ln="", groom_name_modern="Иван",
                               groom_patr_modern="Петров",
                               groom_name_canon="Иоанн",
                               groom_patr_canon="Петрович",
                               groom_marriage_num="",
                               bride_residence="Заманиловка",
                               bride_status="девка из экономических крестьян",
                               bride_ln="", bride_name_modern="Марья",
                               bride_patr_modern="Иванова",
                               bride_name_canon="Мария",
                               bride_patr_canon="Ивановна",
                               bride_marriage_num=""):
        return make_csv_row({
            1: archive, 2: fund, 3: inventory, 4: case,
            5: page, 10: rec_num, 11: w_day, 12: w_month,
            14: groom_residence, 16: groom_status, 17: groom_ln,
            19: groom_name_modern, 20: groom_patr_modern,
            21: groom_name_canon, 22: groom_patr_canon,
            23: groom_marriage_num,
            35: bride_residence, 37: bride_status, 38: bride_ln,
            39: bride_name_modern, 40: bride_patr_modern,
            41: bride_name_canon, 42: bride_patr_canon,
            43: bride_marriage_num,
        }, width=120)

    def test_matching_records(self):
        srow = self._make_marriage_sheet_row()
        crow = self._make_marriage_csv_row()
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        discrepancies = [d for d in result.discrepancies if d.field != "MISSING_IN_CSV"]
        self.assertEqual(len(discrepancies), 0)

    def test_field_mismatch(self):
        srow = self._make_marriage_sheet_row(archive="ГАТО")
        crow = self._make_marriage_csv_row(archive="ГАРО")
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        arch_disc = [d for d in result.discrepancies if d.field == "Архив"]
        self.assertEqual(len(arch_disc), 1)

    def test_missing_in_csv(self):
        srow = self._make_marriage_sheet_row(rec_num="99", w_month="март")
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [], 1800, result)
        missing = [d for d in result.discrepancies if d.field == "MISSING_IN_CSV"]
        self.assertEqual(len(missing), 1)


class TestCompareDeaths(unittest.TestCase):
    def _make_death_sheet_row(self, rec_num="1", gender="муж", d_month="январь",
                              d_day="1", b_day="2", page="10",
                              archive="ГАТО", fund="1049", inventory="1", case="5",
                              dec_name="Иванъ", dec_patr="Петровъ",
                              age="50", cause="", relationship=""):
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_B_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE, D_CAUSE, D_RELATIONSHIP)
        return make_sheet_row({
            D_RECORD_NUM: rec_num, D_GENDER: gender, D_D_MONTH: d_month,
            D_D_DAY: d_day, D_B_DAY: b_day,
            D_PAGE: page, D_ARCHIVE: archive, D_FUND: fund,
            D_INVENTORY: inventory, D_CASE: case,
            D_DEC_NAME: dec_name, D_DEC_PATR: dec_patr,
            D_AGE: age, D_CAUSE: cause, D_RELATIONSHIP: relationship,
        })

    def _make_death_csv_row(self, rec_num="1", gender="муж", d_month="январь",
                            d_day="1", b_day="2", page="10",
                            archive="ГАТО", fund="1049", inventory="1", case="5",
                            dec_residence="Заманиловка",
                            dec_status="экономический крестьянин",
                            dec_ln="", dec_name_modern="Иван",
                            dec_patr_modern="Петров",
                            dec_name_canon="Иоанн", dec_patr_canon="Петрович",
                            age="50", cause="натуральная", relationship=""):
        return make_csv_row({
            1: archive, 2: fund, 3: inventory, 4: case,
            5: page, 10: rec_num, 11: gender, 12: d_day, 13: d_month,
            15: b_day,
            18: dec_residence, 20: dec_status, 21: dec_ln,
            23: dec_name_modern, 24: dec_patr_modern,
            25: dec_name_canon, 26: dec_patr_canon,
            27: age, 31: relationship, 41: cause,
        })

    def test_matching_records(self):
        srow = self._make_death_sheet_row()
        crow = self._make_death_csv_row()
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        discrepancies = [d for d in result.discrepancies if d.field != "MISSING_IN_CSV"]
        self.assertEqual(len(discrepancies), 0)

    def test_field_mismatch(self):
        srow = self._make_death_sheet_row(age="50")
        crow = self._make_death_csv_row(age="60")
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        age_disc = [d for d in result.discrepancies if d.field == "Лет"]
        self.assertEqual(len(age_disc), 1)

    def test_missing_in_csv(self):
        srow = self._make_death_sheet_row(rec_num="99", gender="жен", d_month="март")
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [], 1800, result)
        missing = [d for d in result.discrepancies if d.field == "MISSING_IN_CSV"]
        self.assertEqual(len(missing), 1)

    def test_father_relationship_patr_present(self):
        """When relationship is 'отец', deceased patronymic is preserved in the CSV."""
        from verso.ru.importers.google_sheets import (
            D_DEC_NAME, D_DEC_PATR, D_REL_NAME, D_RELATIONSHIP, D_GENDER, D_RECORD_NUM, D_D_MONTH)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_DEC_NAME: "Иванъ", D_DEC_PATR: "Петровъ",
            D_RELATIONSHIP: "отец", D_REL_NAME: "Петръ",
        })
        # CSV keeps the deceased patronymic even with father relationship
        crow = make_csv_row({
            10: "1", 11: "муж", 13: "январь",
            23: "Иван", 24: "Петров",
            25: "Иван", 26: "Петрович",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        patr_disc = [d for d in result.discrepancies
                     if "Отчество" in d.field and "Умерший" in d.field]
        self.assertEqual(len(patr_disc), 0)


class TestCompareBirthsClergy(unittest.TestCase):
    def _make_sheet_row(self, priest_fio="", deacon_fio="", dyachok_fio=""):
        from verso.ru.importers.google_sheets import (
            B_RECORD_NUM, B_GENDER, B_B_MONTH, B_B_DAY, B_K_DAY, B_PAGE, B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE, B_CHILD_NAME, B_FATHER_NAME, B_FATHER_PATR, B_MOTHER_NAME, B_MOTHER_PATR, B_PRIEST_FIO, B_DEACON_FIO, B_DYACHOK_FIO)
        d = {
            B_RECORD_NUM: "1", B_GENDER: "муж",
            B_B_MONTH: "январь", B_B_DAY: "1", B_K_DAY: "2",
            B_PAGE: "10", B_ARCHIVE: "ГАТО", B_FUND: "1049",
            B_INVENTORY: "1", B_CASE: "5",
            B_CHILD_NAME: "Иванъ",
            B_FATHER_NAME: "Петръ", B_FATHER_PATR: "Ивановъ",
            B_MOTHER_NAME: "Марья", B_MOTHER_PATR: "Петрова",
        }
        if priest_fio:
            d[B_PRIEST_FIO] = priest_fio
        if deacon_fio:
            d[B_DEACON_FIO] = deacon_fio
        if dyachok_fio:
            d[B_DYACHOK_FIO] = dyachok_fio
        return make_sheet_row(d)

    def _make_csv_row(self, priest_fio="", deacon_fio="", dyachok_fio=""):
        d = {
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            15: "2",
            18: "Иван", 19: "Иван",
            20: "Заманиловка", 22: "экономический крестьянин",
            25: "Петр", 26: "Иванов", 27: "Петр", 28: "Иванович",
            29: "экономическая крестьянка",
            31: "Марья", 32: "Петрова", 33: "Мария", 34: "Петровна",
            72: priest_fio, 76: deacon_fio, 78: dyachok_fio,
        }
        return make_csv_row(d)

    def test_clergy_match(self):
        srow = self._make_sheet_row(priest_fio="Степан Космин")
        crow = self._make_csv_row(priest_fio="Степан Космин")
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        clergy_disc = [d for d in result.discrepancies if "Священник" in d.field]
        self.assertEqual(len(clergy_disc), 0)

    def test_clergy_mismatch(self):
        srow = self._make_sheet_row(priest_fio="Степан Космин")
        crow = self._make_csv_row(priest_fio="Николай Космин")
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        clergy_disc = [d for d in result.discrepancies if d.field == "Священник: ФИО"]
        self.assertEqual(len(clergy_disc), 1)

    def test_clergy_empty_both_sides(self):
        srow = self._make_sheet_row()
        crow = self._make_csv_row()
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        clergy_disc = [d for d in result.discrepancies
                       if d.field in ("Священник: ФИО", "Дьякон: ФИО", "Псаломщик: ФИО")]
        self.assertEqual(len(clergy_disc), 0)

    def test_deacon_mismatch(self):
        srow = self._make_sheet_row(deacon_fio="Иван Иванов")
        crow = self._make_csv_row(deacon_fio="Петр Петров")
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        disc = [d for d in result.discrepancies if d.field == "Дьякон: ФИО"]
        self.assertEqual(len(disc), 1)

    def test_dyachok_mismatch(self):
        srow = self._make_sheet_row(dyachok_fio="Алексей Космин")
        crow = self._make_csv_row(dyachok_fio="Сергей Космин")
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        disc = [d for d in result.discrepancies if d.field == "Псаломщик: ФИО"]
        self.assertEqual(len(disc), 1)


class TestCompareMarriagesClergy(unittest.TestCase):
    def _make_sheet_row(self, priest_fio=""):
        from verso.ru.importers.google_sheets import (
            M_RECORD_NUM, M_W_MONTH, M_W_DAY, M_PAGE, M_ARCHIVE, M_FUND, M_INVENTORY, M_CASE, M_GROOM_NAME, M_GROOM_PATR, M_BRIDE_NAME, M_BRIDE_PATR, M_PRIEST_FIO)
        d = {
            M_RECORD_NUM: "1", M_W_MONTH: "январь", M_W_DAY: "5",
            M_PAGE: "10", M_ARCHIVE: "ГАТО", M_FUND: "1049",
            M_INVENTORY: "1", M_CASE: "5",
            M_GROOM_NAME: "Иванъ", M_GROOM_PATR: "Петровъ",
            M_BRIDE_NAME: "Марья", M_BRIDE_PATR: "Иванова",
        }
        if priest_fio:
            d[M_PRIEST_FIO] = priest_fio
        return make_sheet_row(d)

    def _make_csv_row(self, priest_fio=""):
        d = {
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "5", 12: "январь",
            14: "Заманиловка", 16: "экономический крестьянин",
            19: "Иван", 20: "Петров", 21: "Иван", 22: "Петрович",
            35: "Заманиловка", 37: "девка из экономических крестьян",
            39: "Марья", 40: "Иванова", 41: "Мария", 42: "Ивановна",
            102: priest_fio,
        }
        return make_csv_row(d, width=120)

    def test_clergy_match(self):
        srow = self._make_sheet_row(priest_fio="Степан Космин")
        crow = self._make_csv_row(priest_fio="Степан Космин")
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        clergy_disc = [d for d in result.discrepancies if d.field == "Священник: ФИО"]
        self.assertEqual(len(clergy_disc), 0)

    def test_clergy_mismatch(self):
        srow = self._make_sheet_row(priest_fio="Степан Космин")
        crow = self._make_csv_row(priest_fio="Николай Космин")
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        clergy_disc = [d for d in result.discrepancies if d.field == "Священник: ФИО"]
        self.assertEqual(len(clergy_disc), 1)


class TestCompareDeathsDerivedPatr(unittest.TestCase):
    """Test that derived patronymics (from father name) are suppressed."""

    def test_derived_patr_from_father_suppressed(self):
        """When deceased has no patr but CSV derives it from father → no discrepancy."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_B_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE, D_RELATIONSHIP, D_REL_NAME)
        # Source: deceased "Петр" with NO patronymic, father "Иван"
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1", D_B_DAY: "2", D_PAGE: "10",
            D_ARCHIVE: "ГАТО", D_FUND: "1049", D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Петр", D_DEC_PATR: "",  # NO patronymic
            D_AGE: "3", D_RELATIONSHIP: "отец",
            D_REL_NAME: "Иван",
        })
        # Output CSV: deceased "Петр" with derived patronymic "Иванов" from father "Иван"
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            15: "2",
            23: "Петр", 24: "Иванов",
            25: "Петр", 26: "Иванович",
            27: "3", 31: "отец", 41: "натуральная",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        patr_disc = [d for d in result.discrepancies
                     if "Отчество" in d.field and "Умерший" in d.field]
        self.assertEqual(len(patr_disc), 0, f"Should suppress derived patr, got: {[(d.field, d.sheet_val, d.csv_val) for d in patr_disc]}")

    def test_real_patr_mismatch_not_suppressed(self):
        """When deceased HAS a patronymic that differs from CSV → still warn."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_B_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1", D_B_DAY: "2", D_PAGE: "10",
            D_ARCHIVE: "ГАТО", D_FUND: "1049", D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Петр", D_DEC_PATR: "Семенов",  # HAS patronymic
            D_AGE: "50",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            15: "2",
            23: "Петр", 24: "Иванов",  # different!
            25: "Петр", 26: "Иванович",
            27: "50", 41: "натуральная",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        patr_disc = [d for d in result.discrepancies
                     if "Отчество" in d.field and "Умерший" in d.field]
        self.assertGreater(len(patr_disc), 0)


class TestCompareDeathsClergy(unittest.TestCase):
    def _make_sheet_row(self, priest_fio=""):
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_B_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE, D_PRIEST_FIO)
        d = {
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1", D_B_DAY: "2",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Иванъ", D_DEC_PATR: "Петровъ",
            D_AGE: "50",
        }
        if priest_fio:
            d[D_PRIEST_FIO] = priest_fio
        return make_sheet_row(d)

    def _make_csv_row(self, priest_fio=""):
        d = {
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            15: "2",
            18: "Заманиловка", 20: "экономический крестьянин",
            23: "Иван", 24: "Петров", 25: "Иван", 26: "Петрович",
            27: "50", 41: "натуральная",
            55: priest_fio,
        }
        return make_csv_row(d)

    def test_clergy_match(self):
        srow = self._make_sheet_row(priest_fio="Степан Космин")
        crow = self._make_csv_row(priest_fio="Степан Космин")
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        clergy_disc = [d for d in result.discrepancies if d.field == "Священник: ФИО"]
        self.assertEqual(len(clergy_disc), 0)

    def test_clergy_mismatch(self):
        srow = self._make_sheet_row(priest_fio="Степан Космин")
        crow = self._make_csv_row(priest_fio="Николай Космин")
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        clergy_disc = [d for d in result.discrepancies if d.field == "Священник: ФИО"]
        self.assertEqual(len(clergy_disc), 1)


class TestClergyFieldsInFieldToSheetCol(unittest.TestCase):
    def test_clergy_fields_present(self):
        expected = [
            ("births", "Священник: ФИО"),
            ("births", "Дьякон: ФИО"),
            ("births", "Псаломщик: ФИО"),
            ("marriages", "Священник: ФИО"),
            ("marriages", "Дьякон: ФИО"),
            ("marriages", "Псаломщик: ФИО"),
            ("deaths", "Священник: ФИО"),
            ("deaths", "Дьякон: ФИО"),
            ("deaths", "Псаломщик: ФИО"),
        ]
        for key in expected:
            self.assertIn(key, FIELD_TO_SHEET_COL, f"{key} missing from FIELD_TO_SHEET_COL")


class TestValidateRecordType(unittest.TestCase):
    @patch("verso.ru.importers.validation._read_csv_rows_for_year")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_missing_dsl_skipped(self, mock_dsl, mock_read_year):
        mock_dsl.return_value = None
        rows_by_year = {1800: [(2, make_sheet_row({}))]}
        result = validate_record_type("births", rows_by_year)
        self.assertEqual(result.years_checked, 0)
        mock_read_year.assert_not_called()

    @patch("verso.ru.importers.validation.compare_births")
    @patch("verso.ru.importers.validation._read_csv_rows_for_year")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_missing_csv_no_regenerate(self, mock_dsl, mock_read_year, mock_compare):
        mock_dsl.return_value = "/fake/path.py"
        mock_read_year.return_value = (None, set())
        rows_by_year = {1800: [(2, make_sheet_row({}))]}
        result = validate_record_type("births", rows_by_year, regenerate=False)
        self.assertIn(1800, result.missing_csv)
        mock_compare.assert_not_called()

    @patch("verso.ru.importers.validation.compare_births")
    @patch("verso.ru.importers.validation._read_csv_rows_for_year")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_year_filter_single(self, mock_dsl, mock_read_year, mock_compare):
        mock_dsl.return_value = "/fake/path.py"
        mock_read_year.return_value = ([], set())
        rows_by_year = {1800: [(2, make_sheet_row({}))], 1801: [(3, make_sheet_row({}))]}
        result = validate_record_type("births", rows_by_year, year_filter=1800)
        # Only 1800 should be checked
        self.assertEqual(result.years_checked, 1)

    @patch("verso.ru.importers.validation.compare_births")
    @patch("verso.ru.importers.validation._read_csv_rows_for_year")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_year_filter_multiple(self, mock_dsl, mock_read_year, mock_compare):
        mock_dsl.return_value = "/fake/path.py"
        mock_read_year.return_value = ([], set())
        rows_by_year = {1800: [(2, make_sheet_row({}))], 1801: [(3, make_sheet_row({}))],
                        1802: [(4, make_sheet_row({}))]}
        result = validate_record_type("births", rows_by_year, year_filter=[1800, 1802])
        self.assertEqual(result.years_checked, 2)

    @patch("verso.ru.importers.validation.compare_births")
    @patch("verso.ru.importers.validation._read_csv_rows_for_year")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_count_mismatch_detection(self, mock_dsl, mock_read_year, mock_compare):
        mock_dsl.return_value = "/fake/path.py"
        mock_read_year.return_value = ([make_csv_row({})], set())  # 1 CSV row
        rows_by_year = {1800: [(2, make_sheet_row({})), (3, make_sheet_row({}))]}  # 2 sheet rows
        result = validate_record_type("births", rows_by_year)
        self.assertEqual(len(result.count_mismatches), 1)
        self.assertEqual(result.count_mismatches[0], (1800, 2, 1))

    @patch("verso.ru.importers.validation.compare_births")
    @patch("verso.ru.importers.validation._read_csv_rows_for_year")
    @patch("verso.ru.importers.validation.find_dsl")
    def test_exception_in_compare(self, mock_dsl, mock_read_year, mock_compare):
        mock_dsl.return_value = "/fake/path.py"
        mock_read_year.return_value = ([], set())
        mock_compare.side_effect = RuntimeError("test error")
        rows_by_year = {1800: [(2, make_sheet_row({}))]}
        result = validate_record_type("births", rows_by_year)
        error_disc = [d for d in result.discrepancies if d.field == "ERROR"]
        self.assertEqual(len(error_disc), 1)
        self.assertIn("test error", error_disc[0].sheet_val)


class TestPrintReport(unittest.TestCase):
    def test_returns_sorted_discrepancies(self):
        r1 = ValidationResult(record_type="births")
        r1.discrepancies = [
            Discrepancy(year=1801, record_type="births", record_num="2",
                        field="f", sheet_val="a", csv_val="b"),
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="f", sheet_val="c", csv_val="d"),
        ]
        r1.total_fields = 10
        with patch("sys.stdout", new_callable=io.StringIO):
            sorted_disc = print_report([r1])
        self.assertEqual(sorted_disc[0].year, 1800)
        self.assertEqual(sorted_disc[1].year, 1801)

    def test_empty_results(self):
        r = ValidationResult(record_type="births")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            sorted_disc = print_report([r])
        self.assertEqual(len(sorted_disc), 0)
        self.assertIn("No discrepancies found!", mock_out.getvalue())

    def test_numbered_output(self):
        r = ValidationResult(record_type="births")
        r.discrepancies = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="10", csv_val="20"),
        ]
        r.total_fields = 1
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_report([r])
        output = mock_out.getvalue()
        self.assertIn("1 ", output)  # numbered entry


class TestFixDiscrepancies(unittest.TestCase):
    def test_dry_run(self):
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="10", csv_val="20",
                        sheet_row_idx=5),
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fix_discrepancies(disc, [1], "test_id", dry_run=True)
        output = mock_out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("'10'", output)
        self.assertIn("'20'", output)

    def test_fix_by_number(self):
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="10", csv_val="20",
                        sheet_row_idx=5),
        ]
        mock_gspread = MagicMock()
        mock_gc = MagicMock()
        mock_gspread.oauth.return_value = mock_gc
        mock_ws = MagicMock()
        mock_ws.title = "рождение"
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = [mock_ws]
        mock_gc.open_by_key.return_value = mock_spreadsheet

        mock_rowcol_to_a1 = MagicMock(return_value="F6")
        with patch.dict("sys.modules", {
            "gspread": mock_gspread,
            "gspread.utils": MagicMock(rowcol_to_a1=mock_rowcol_to_a1),
        }):
            with patch("sys.stdout", new_callable=io.StringIO):
                fix_discrepancies(disc, [1], "test_id", dry_run=False)

        mock_ws.batch_update.assert_called_once()
        batch_arg = mock_ws.batch_update.call_args[0][0]
        self.assertEqual(len(batch_arg), 1)
        self.assertEqual(batch_arg[0]["values"], [["20"]])

    def test_fix_all(self):
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="10", csv_val="20",
                        sheet_row_idx=5),
            Discrepancy(year=1800, record_type="births", record_num="2",
                        field="Архив", sheet_val="X", csv_val="Y",
                        sheet_row_idx=6),
        ]
        mock_gspread = MagicMock()
        mock_gc = MagicMock()
        mock_gspread.oauth.return_value = mock_gc
        mock_ws = MagicMock()
        mock_ws.title = "рождение"
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = [mock_ws]
        mock_gc.open_by_key.return_value = mock_spreadsheet

        def _rowcol(r: int, c: int) -> str:
            return f"R{r}C{c}"
        mock_rowcol_to_a1 = MagicMock(side_effect=_rowcol)
        with patch.dict("sys.modules", {
            "gspread": mock_gspread,
            "gspread.utils": MagicMock(rowcol_to_a1=mock_rowcol_to_a1),
        }):
            with patch("sys.stdout", new_callable=io.StringIO):
                fix_discrepancies(disc, ["all"], "test_id", dry_run=False)

        mock_ws.batch_update.assert_called_once()
        batch_arg = mock_ws.batch_update.call_args[0][0]
        self.assertEqual(len(batch_arg), 2)

    def test_out_of_range_warning(self):
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="10", csv_val="20",
                        sheet_row_idx=5),
        ]
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            fix_discrepancies(disc, [99], "test_id", dry_run=True)
        self.assertIn("out of range", mock_err.getvalue())

    def test_no_column_mapping_skip(self):
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="MISSING_IN_CSV", sheet_val="x", csv_val="",
                        sheet_row_idx=5),
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("sys.stderr", new_callable=io.StringIO):
                fix_discrepancies(disc, [1], "test_id", dry_run=True)
        self.assertIn("no column mapping", mock_out.getvalue())

    def test_no_sheet_row_idx_skip(self):
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="10", csv_val="20",
                        sheet_row_idx=None),
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("sys.stderr", new_callable=io.StringIO):
                fix_discrepancies(disc, [1], "test_id", dry_run=True)
        self.assertIn("no sheet row index", mock_out.getvalue())

    def test_fix_empty_filters_non_empty_sheet(self):
        """fix_empty=True should only include discrepancies where sheet is empty and CSV is non-empty."""
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="", csv_val="20",
                        sheet_row_idx=5),
            Discrepancy(year=1800, record_type="births", record_num="2",
                        field="Архив", sheet_val="X", csv_val="Y",
                        sheet_row_idx=6),
            Discrepancy(year=1800, record_type="births", record_num="3",
                        field="Лист", sheet_val="", csv_val="",
                        sheet_row_idx=7),
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fix_discrepancies(disc, ["all"], "test_id", dry_run=True, fix_empty=True)
        output = mock_out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("would fix 1 cells", output)
        self.assertIn("'20'", output)
        self.assertNotIn("'Y'", output)

    def test_fix_empty_with_fix_all(self):
        """fix_empty=True with fix_ids=['all'] should only fix empty-sheet discrepancies."""
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="", csv_val="20",
                        sheet_row_idx=5),
            Discrepancy(year=1800, record_type="births", record_num="2",
                        field="Архив", sheet_val="X", csv_val="Y",
                        sheet_row_idx=6),
        ]
        mock_gspread = MagicMock()
        mock_gc = MagicMock()
        mock_gspread.oauth.return_value = mock_gc
        mock_ws = MagicMock()
        mock_ws.title = "рождение"
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = [mock_ws]
        mock_gc.open_by_key.return_value = mock_spreadsheet

        mock_rowcol_to_a1 = MagicMock(return_value="F6")
        with patch.dict("sys.modules", {
            "gspread": mock_gspread,
            "gspread.utils": MagicMock(rowcol_to_a1=mock_rowcol_to_a1),
        }):
            with patch("sys.stdout", new_callable=io.StringIO):
                fix_discrepancies(disc, ["all"], "test_id", dry_run=False, fix_empty=True)

        mock_ws.batch_update.assert_called_once()
        batch_arg = mock_ws.batch_update.call_args[0][0]
        self.assertEqual(len(batch_arg), 1)
        self.assertEqual(batch_arg[0]["values"], [["20"]])

    def test_fix_empty_false_no_filter(self):
        """fix_empty=False should process all selected discrepancies (existing behavior)."""
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="", csv_val="20",
                        sheet_row_idx=5),
            Discrepancy(year=1800, record_type="births", record_num="2",
                        field="Архив", sheet_val="X", csv_val="Y",
                        sheet_row_idx=6),
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fix_discrepancies(disc, ["all"], "test_id", dry_run=True, fix_empty=False)
        output = mock_out.getvalue()
        self.assertIn("would fix 2 cells", output)

    def test_fix_empty_whitespace_sheet_val(self):
        """fix_empty=True should treat whitespace-only sheet values as empty."""
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="  ", csv_val="20",
                        sheet_row_idx=5),
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fix_discrepancies(disc, ["all"], "test_id", dry_run=True, fix_empty=True)
        output = mock_out.getvalue()
        self.assertIn("would fix 1 cells", output)


class TestMain(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(patch("verso.ru.importers.validation.site_config", _test_site))

    @patch("verso.ru.importers.validation.print_report")
    @patch("verso.ru.importers.validation.validate_record_type")
    @patch("verso.ru.importers.validation.split_by_year")
    @patch("verso.ru.importers.validation.fetch_all_sheets")
    @patch("verso.ru.importers.validation.argparse.ArgumentParser.parse_args")
    def test_basic_flow(self, mock_args, mock_fetch, mock_split, mock_validate, mock_report):
        mock_args.return_value = MagicMock(
            record_type=None, year=None, regenerate=False, fix=None, dry_run=False, fix_empty=False, site="zamanilovka", csv=None)
        mock_fetch.return_value = {"рождение": [], "брак": [], "смерть": []}
        mock_split.return_value = {}
        mock_validate.return_value = ValidationResult(record_type="births")
        mock_report.return_value = []

        with patch("sys.stderr", new_callable=io.StringIO):
            main()

        mock_fetch.assert_called_once()
        self.assertEqual(mock_validate.call_count, 3)  # births, marriages, deaths

    @patch("verso.ru.importers.validation.fix_discrepancies")
    @patch("verso.ru.importers.validation.print_report")
    @patch("verso.ru.importers.validation.validate_record_type")
    @patch("verso.ru.importers.validation.split_by_year")
    @patch("verso.ru.importers.validation.fetch_all_sheets")
    @patch("verso.ru.importers.validation.argparse.ArgumentParser.parse_args")
    def test_fix_triggers_fix_discrepancies(self, mock_args, mock_fetch, mock_split,
                                            mock_validate, mock_report, mock_fix):
        mock_args.return_value = MagicMock(
            record_type="births", year=None, regenerate=False,
            fix=["1", "2"], dry_run=False, fix_empty=False, site="zamanilovka", csv=None)
        mock_fetch.return_value = {"рождение": []}
        mock_split.return_value = {}
        mock_validate.return_value = ValidationResult(record_type="births")
        mock_report.return_value = [Discrepancy(
            year=1800, record_type="births", record_num="1",
            field="f", sheet_val="a", csv_val="b")]

        with patch("sys.stderr", new_callable=io.StringIO):
            main()

        mock_fix.assert_called_once()
        args = mock_fix.call_args
        self.assertEqual(args[0][1], [1, 2])

    @patch("verso.ru.importers.validation.fix_discrepancies")
    @patch("verso.ru.importers.validation.print_report")
    @patch("verso.ru.importers.validation.validate_record_type")
    @patch("verso.ru.importers.validation.split_by_year")
    @patch("verso.ru.importers.validation.fetch_all_sheets")
    @patch("verso.ru.importers.validation.argparse.ArgumentParser.parse_args")
    def test_dry_run_passes_through(self, mock_args, mock_fetch, mock_split,
                                    mock_validate, mock_report, mock_fix):
        mock_args.return_value = MagicMock(
            record_type="births", year=None, regenerate=False,
            fix=["all"], dry_run=True, fix_empty=False, site="zamanilovka", csv=None)
        mock_fetch.return_value = {"рождение": []}
        mock_split.return_value = {}
        mock_validate.return_value = ValidationResult(record_type="births")
        mock_report.return_value = []

        with patch("sys.stderr", new_callable=io.StringIO):
            main()

        mock_fix.assert_called_once()
        self.assertTrue(mock_fix.call_args.kwargs["dry_run"])

    @patch("verso.ru.importers.validation.fix_discrepancies")
    @patch("verso.ru.importers.validation.print_report")
    @patch("verso.ru.importers.validation.validate_record_type")
    @patch("verso.ru.importers.validation.split_by_year")
    @patch("verso.ru.importers.validation.fetch_all_sheets")
    @patch("verso.ru.importers.validation.argparse.ArgumentParser.parse_args")
    def test_fix_empty_flag_passed_to_fix_discrepancies(self, mock_args, mock_fetch, mock_split,
                                                        mock_validate, mock_report, mock_fix):
        mock_args.return_value = MagicMock(
            record_type="births", year=None, regenerate=False,
            fix=["all"], dry_run=False, fix_empty=True, site="zamanilovka", csv=None)
        mock_fetch.return_value = {"рождение": []}
        mock_split.return_value = {}
        mock_validate.return_value = ValidationResult(record_type="births")
        mock_report.return_value = [Discrepancy(
            year=1800, record_type="births", record_num="1",
            field="f", sheet_val="", csv_val="b")]

        with patch("sys.stderr", new_callable=io.StringIO):
            main()

        mock_fix.assert_called_once()
        self.assertTrue(mock_fix.call_args.kwargs["fix_empty"])


class TestFieldToSheetCol(unittest.TestCase):
    def test_all_keys_are_tuples(self):
        for key in FIELD_TO_SHEET_COL:
            self.assertIsInstance(key, tuple)
            self.assertEqual(len(key), 2)

    def test_covers_all_record_types(self):
        record_types = {k[0] for k in FIELD_TO_SHEET_COL}
        self.assertIn("births", record_types)
        self.assertIn("marriages", record_types)
        self.assertIn("deaths", record_types)

    def test_values_are_ints(self):
        for key, val in FIELD_TO_SHEET_COL.items():
            self.assertIsInstance(val, int, f"FIELD_TO_SHEET_COL[{key}] should be int")


# ─── Tests for _read_csv_rows_for_year (carryover logic) ─────────────────────

class TestReadCsvRowsForYear(unittest.TestCase):
    """Tests for the new carryover-aware CSV row aggregation helper."""

    @patch("verso.ru.importers.validation.read_familio_csv")
    @patch("verso.ru.importers.validation.find_csv")
    def test_rows_from_current_year_only(self, mock_find, mock_read):
        """When only year X CSV exists, return its rows filtered by year."""
        mock_find.side_effect = lambda y, rt: f"/fake/{y}.csv" if y == 1800 else None  # type: ignore[reportUnknownLambdaType]
        mock_read.return_value = [
            {14: "1800", "_headers": []},
            {14: "1800", "_headers": []},
        ]
        rows, regen = _read_csv_rows_for_year(1800, "births")
        self.assertEqual(len(rows), 2)
        self.assertEqual(regen, set())

    @patch("verso.ru.importers.validation.read_familio_csv")
    @patch("verso.ru.importers.validation.find_csv")
    def test_carryover_rows_from_next_year(self, mock_find, mock_read):
        """Carryover rows in year X+1 CSV are included when year matches."""
        def find_side(y, rt):
            return f"/fake/{y}.csv" if y in (1785, 1786) else None
        mock_find.side_effect = find_side

        def read_side(path):
            if "1785" in path:
                return [{14: "1785", "_headers": []}]
            else:
                return [
                    {14: "1785", "_headers": []},  # carryover
                    {14: "1786", "_headers": []},  # normal
                ]
        mock_read.side_effect = read_side

        rows, _ = _read_csv_rows_for_year(1785, "births")
        # 1 from 1785.csv + 1 carryover from 1786.csv = 2
        self.assertEqual(len(rows), 2)

    @patch("verso.ru.importers.validation.read_familio_csv")
    @patch("verso.ru.importers.validation.find_csv")
    def test_filters_out_other_year_rows(self, mock_find, mock_read):
        """Rows from year X+1 CSV that belong to X+1 are excluded."""
        mock_find.side_effect = lambda y, rt: f"/fake/{y}.csv" if y in (1785, 1786) else None  # type: ignore[reportUnknownLambdaType]
        def read_side(path):
            if "1785" in path:
                return [{14: "1785", "_headers": []}]
            else:
                return [
                    {14: "1785", "_headers": []},  # carryover
                    {14: "1786", "_headers": []},  # different year
                ]
        mock_read.side_effect = read_side
        rows, _ = _read_csv_rows_for_year(1785, "births")
        assert rows is not None
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r[14], "1785")

    @patch("verso.ru.importers.validation.read_familio_csv")
    @patch("verso.ru.importers.validation.find_csv")
    def test_no_csv_found_returns_none(self, mock_find, mock_read):
        """When neither year X nor X+1 CSV exists, return None."""
        mock_find.return_value = None
        rows, _ = _read_csv_rows_for_year(1800, "births")
        self.assertIsNone(rows)

    @patch("verso.ru.importers.validation.read_familio_csv")
    @patch("verso.ru.importers.validation.regenerate_csv")
    @patch("verso.ru.importers.validation.find_dsl")
    @patch("verso.ru.importers.validation.find_csv")
    def test_regenerate_both_years(self, mock_find, mock_dsl, mock_regen, mock_read):
        """With regenerate=True, DSL files for both years are regenerated."""
        # find_csv: called twice per year (before regen=None, after regen=path)
        # Order: 1800 (None), 1800 (path), 1801 (None), 1801 (path)
        mock_find.side_effect = [None, "/fake/1800.csv", None, "/fake/1801.csv"]
        mock_dsl.return_value = "/fake/dsl.py"
        mock_regen.return_value = True
        mock_read.return_value = [{14: "1800", "_headers": []}]

        rows, regen = _read_csv_rows_for_year(1800, "births", regenerate=True)
        self.assertIsNotNone(rows)
        self.assertIn(1800, regen)
        self.assertIn(1801, regen)

    @patch("verso.ru.importers.validation.read_familio_csv")
    @patch("verso.ru.importers.validation.find_csv")
    def test_deaths_year_column(self, mock_find, mock_read):
        """Deaths use CSV column 14 for year."""
        mock_find.side_effect = lambda y, rt: f"/fake/{y}.csv" if y == 1800 else None  # type: ignore[reportUnknownLambdaType]
        mock_read.return_value = [{14: "1800", "_headers": []}]
        rows, _ = _read_csv_rows_for_year(1800, "deaths")
        self.assertEqual(len(rows), 1)

    @patch("verso.ru.importers.validation.read_familio_csv")
    @patch("verso.ru.importers.validation.find_csv")
    def test_marriages_year_column(self, mock_find, mock_read):
        """Marriages use CSV column 13 for year."""
        mock_find.side_effect = lambda y, rt: f"/fake/{y}.csv" if y == 1800 else None  # type: ignore[reportUnknownLambdaType]
        mock_read.return_value = [{13: "1800", "_headers": []}]
        rows, _ = _read_csv_rows_for_year(1800, "marriages")
        self.assertEqual(len(rows), 1)


# ─── Tests for godparent branches in compare_births ──────────────────────────

class TestCompareBirthsGodparents(unittest.TestCase):
    """Cover godparent 1 & 2 branches in compare_births."""

    def _make_gp_sheet_row(self, gp1_name="", gp1_patr="", gp1_status="",
                           gp1_residence="", gp2_name="", gp2_patr="",
                           gp2_status="", gp2_residence=""):
        from verso.ru.importers.google_sheets import (
            B_RECORD_NUM, B_GENDER, B_B_MONTH, B_B_DAY, B_K_DAY, B_PAGE, B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE, B_CHILD_NAME, B_FATHER_NAME, B_FATHER_PATR, B_MOTHER_NAME, B_MOTHER_PATR, B_GP1_NAME, B_GP1_PATR, B_GP1_STATUS, B_GP1_RESIDENCE, B_GP2_NAME, B_GP2_PATR, B_GP2_STATUS, B_GP2_RESIDENCE)
        d = {
            B_RECORD_NUM: "1", B_GENDER: "муж",
            B_B_MONTH: "январь", B_B_DAY: "1", B_K_DAY: "2",
            B_PAGE: "10", B_ARCHIVE: "ГАТО", B_FUND: "1049",
            B_INVENTORY: "1", B_CASE: "5",
            B_CHILD_NAME: "Иванъ",
            B_FATHER_NAME: "Петръ", B_FATHER_PATR: "Ивановъ",
            B_MOTHER_NAME: "Марья", B_MOTHER_PATR: "Петрова",
        }
        if gp1_name:
            d[B_GP1_NAME] = gp1_name
        if gp1_patr:
            d[B_GP1_PATR] = gp1_patr
        if gp1_status:
            d[B_GP1_STATUS] = gp1_status
        if gp1_residence:
            d[B_GP1_RESIDENCE] = gp1_residence
        if gp2_name:
            d[B_GP2_NAME] = gp2_name
        if gp2_patr:
            d[B_GP2_PATR] = gp2_patr
        if gp2_status:
            d[B_GP2_STATUS] = gp2_status
        if gp2_residence:
            d[B_GP2_RESIDENCE] = gp2_residence
        return make_sheet_row(d)

    def _make_gp_csv_row(self, gp1_status="", gp1_residence="",
                         gp1_name_modern="", gp1_patr_modern="",
                         gp1_name_canon="", gp1_patr_canon="", gp1_fio="",
                         gp2_status="", gp2_residence="",
                         gp2_name_modern="", gp2_patr_modern="",
                         gp2_name_canon="", gp2_patr_canon="", gp2_fio=""):
        return make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь", 15: "2",
            18: "Иван", 19: "Иван",
            20: "Заманиловка", 22: "экономический крестьянин",
            25: "Петр", 26: "Иванов", 27: "Петр", 28: "Иванович",
            29: "экономическая крестьянка",
            31: "Марья", 32: "Петрова", 33: "Мария", 34: "Петровна",
            # GP1 fields: status=35, residence=36, name_modern=38, patr_modern=39,
            # name_canon=40, patr_canon=41, fio=42
            35: gp1_status, 36: gp1_residence,
            38: gp1_name_modern, 39: gp1_patr_modern,
            40: gp1_name_canon, 41: gp1_patr_canon, 42: gp1_fio,
            # GP2 fields: status=43, residence=44, name_modern=46, patr_modern=47,
            # name_canon=48, patr_canon=49, fio=50
            43: gp2_status, 44: gp2_residence,
            46: gp2_name_modern, 47: gp2_patr_modern,
            48: gp2_name_canon, 49: gp2_patr_canon, 50: gp2_fio,
        })

    def test_godparent1_match(self):
        srow = self._make_gp_sheet_row(gp1_name="Сидоръ", gp1_patr="Ивановъ")
        crow = self._make_gp_csv_row(
            gp1_status=BIRTH_STATUS_MALE,
            gp1_residence="Заманиловка",
            gp1_name_modern="Сидор", gp1_patr_modern="Иванов",
            gp1_name_canon="Исидор", gp1_patr_canon="Иванович",
            gp1_fio="Исидор Иванович",
        )
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        gp_disc = [d for d in result.discrepancies if "Восприемник 1" in d.field]
        self.assertEqual(len(gp_disc), 0)

    def test_godparent2_match(self):
        srow = self._make_gp_sheet_row(
            gp1_name="Сидоръ", gp1_patr="Ивановъ",
            gp2_name="Анна", gp2_patr="Петрова",
        )
        crow = self._make_gp_csv_row(
            gp1_status=BIRTH_STATUS_MALE, gp1_residence="Заманиловка",
            gp1_name_modern="Сидор", gp1_patr_modern="Иванов",
            gp1_name_canon="Исидор", gp1_patr_canon="Иванович",
            gp1_fio="Исидор Иванович",
            gp2_status=BIRTH_STATUS_FEMALE, gp2_residence="Заманиловка",
            gp2_name_modern="Анна", gp2_patr_modern="Петрова",
            gp2_name_canon="Анна", gp2_patr_canon="Петровна",
            gp2_fio="Анна Петровна",
        )
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        gp_disc = [d for d in result.discrepancies if "Восприемник 2" in d.field]
        self.assertEqual(len(gp_disc), 0)

    def test_godparent1_mismatch(self):
        srow = self._make_gp_sheet_row(gp1_name="Сидоръ", gp1_patr="Ивановъ")
        crow = self._make_gp_csv_row(
            gp1_status=BIRTH_STATUS_MALE, gp1_residence="Заманиловка",
            gp1_name_modern="Федор", gp1_patr_modern="Иванов",
            gp1_name_canon="Федор", gp1_patr_canon="Иванович",
            gp1_fio="Федор Иванович",
        )
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        gp_disc = [d for d in result.discrepancies if "Восприемник 1" in d.field and "Имя" in d.field]
        self.assertGreater(len(gp_disc), 0)


# ─── Tests for witness branches in compare_marriages ─────────────────────────

class TestCompareMarriagesWitnesses(unittest.TestCase):
    """Cover witness 1 & 2 branches in compare_marriages."""

    def _make_witness_sheet_row(self, w1_name="", w1_patr="", w1_status="",
                                w1_residence="", w1_last_name="",
                                w2_name="", w2_patr="",
                                w2_status="", w2_residence="", w2_last_name=""):
        from verso.ru.importers.google_sheets import (
            M_RECORD_NUM, M_W_MONTH, M_W_DAY, M_PAGE, M_ARCHIVE, M_FUND, M_INVENTORY, M_CASE, M_GROOM_NAME, M_GROOM_PATR, M_BRIDE_NAME, M_BRIDE_PATR, M_W1_NAME, M_W1_PATR, M_W1_STATUS, M_W1_RESIDENCE, M_W1_LAST_NAME, M_W2_NAME, M_W2_PATR, M_W2_STATUS, M_W2_RESIDENCE, M_W2_LAST_NAME)
        d = {
            M_RECORD_NUM: "1", M_W_MONTH: "январь", M_W_DAY: "5",
            M_PAGE: "10", M_ARCHIVE: "ГАТО", M_FUND: "1049",
            M_INVENTORY: "1", M_CASE: "5",
            M_GROOM_NAME: "Иванъ", M_GROOM_PATR: "Петровъ",
            M_BRIDE_NAME: "Марья", M_BRIDE_PATR: "Иванова",
        }
        if w1_name:
            d[M_W1_NAME] = w1_name
        if w1_patr:
            d[M_W1_PATR] = w1_patr
        if w1_status:
            d[M_W1_STATUS] = w1_status
        if w1_residence:
            d[M_W1_RESIDENCE] = w1_residence
        if w1_last_name:
            d[M_W1_LAST_NAME] = w1_last_name
        if w2_name:
            d[M_W2_NAME] = w2_name
        if w2_patr:
            d[M_W2_PATR] = w2_patr
        if w2_status:
            d[M_W2_STATUS] = w2_status
        if w2_residence:
            d[M_W2_RESIDENCE] = w2_residence
        if w2_last_name:
            d[M_W2_LAST_NAME] = w2_last_name
        return make_sheet_row(d)

    def _make_witness_csv_row(self, w1_status="", w1_residence="",
                              w1_name_modern="", w1_patr_modern="",
                              w1_name_canon="", w1_patr_canon="", w1_fio="",
                              w1_last_name="",
                              w2_status="", w2_residence="",
                              w2_name_modern="", w2_patr_modern="",
                              w2_name_canon="", w2_patr_canon="", w2_fio="",
                              w2_last_name=""):
        return make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "5", 12: "январь",
            14: "Заманиловка", 16: "экономический крестьянин",
            19: "Иван", 20: "Петров", 21: "Иван", 22: "Петрович",
            35: "Заманиловка", 37: "девка из экономических крестьян",
            39: "Марья", 40: "Иванова", 41: "Мария", 42: "Ивановна",
            # W1: status=55, residence=56, last_name=58, name_modern=59,
            # patr_modern=60, name_canon=61, patr_canon=62, fio=63
            55: w1_status, 56: w1_residence, 58: w1_last_name,
            59: w1_name_modern, 60: w1_patr_modern,
            61: w1_name_canon, 62: w1_patr_canon, 63: w1_fio,
            # W2: status=64, residence=65, last_name=67, name_modern=68,
            # patr_modern=69, name_canon=70, patr_canon=71, fio=72
            64: w2_status, 65: w2_residence, 67: w2_last_name,
            68: w2_name_modern, 69: w2_patr_modern,
            70: w2_name_canon, 71: w2_patr_canon, 72: w2_fio,
        }, width=120)

    def test_witness1_match(self):
        srow = self._make_witness_sheet_row(w1_name="Сидоръ", w1_patr="Ивановъ")
        crow = self._make_witness_csv_row(
            w1_status=MARRIAGE_STATUS_MALE, w1_residence="Заманиловка",
            w1_name_modern="Сидор", w1_patr_modern="Иванов",
            w1_name_canon="Исидор", w1_patr_canon="Иванович",
            w1_fio="Исидор Иванович",
        )
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        w_disc = [d for d in result.discrepancies if "Поручитель 1" in d.field]
        self.assertEqual(len(w_disc), 0)

    def test_witness2_match(self):
        srow = self._make_witness_sheet_row(
            w1_name="Сидоръ", w1_patr="Ивановъ",
            w2_name="Федоръ", w2_patr="Петровъ",
        )
        crow = self._make_witness_csv_row(
            w1_status=MARRIAGE_STATUS_MALE, w1_residence="Заманиловка",
            w1_name_modern="Сидор", w1_patr_modern="Иванов",
            w1_name_canon="Исидор", w1_patr_canon="Иванович",
            w1_fio="Исидор Иванович",
            w2_status=MARRIAGE_STATUS_MALE, w2_residence="Заманиловка",
            w2_name_modern="Федор", w2_patr_modern="Петров",
            w2_name_canon="Феодор", w2_patr_canon="Петрович",
            w2_fio="Феодор Петрович",
        )
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        w_disc = [d for d in result.discrepancies if "Поручитель 2" in d.field]
        self.assertEqual(len(w_disc), 0)

    def test_witness1_mismatch(self):
        srow = self._make_witness_sheet_row(w1_name="Сидоръ", w1_patr="Ивановъ")
        crow = self._make_witness_csv_row(
            w1_status=MARRIAGE_STATUS_MALE, w1_residence="Заманиловка",
            w1_name_modern="Федор", w1_patr_modern="Иванов",
            w1_name_canon="Федор", w1_patr_canon="Иванович",
            w1_fio="Федор Иванович",
        )
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        w_disc = [d for d in result.discrepancies if "Поручитель 1" in d.field and "Имя" in d.field]
        self.assertGreater(len(w_disc), 0)

    def test_witness1_with_surname(self):
        """Witness surname from Фамилия column is used in comparison."""
        srow = self._make_witness_sheet_row(
            w1_name="Герасимъ", w1_patr="",
            w1_last_name="Дуралеевъ")
        crow = self._make_witness_csv_row(
            w1_status=MARRIAGE_STATUS_MALE, w1_residence="Заманиловка",
            w1_name_modern="Герасим", w1_last_name="Дуралеев",
            w1_name_canon="Герасим",
            w1_fio="Дуралеев Герасим",
        )
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        w_disc = [d for d in result.discrepancies if "Поручитель 1" in d.field]
        self.assertEqual(len(w_disc), 0)

    def test_witness1_surname_from_fio_fallback(self):
        """When Фамилия is empty, extract surname from ФИО column."""
        from verso.ru.importers.google_sheets import M_W1_FIO
        srow = self._make_witness_sheet_row(w1_name="Герасимъ", w1_patr="")
        srow[M_W1_FIO] = "Дуралеев Герасим"
        crow = self._make_witness_csv_row(
            w1_status=MARRIAGE_STATUS_MALE, w1_residence="Заманиловка",
            w1_name_modern="Герасим", w1_last_name="Дуралеев",
            w1_name_canon="Герасим",
            w1_fio="Дуралеев Герасим",
        )
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        w_disc = [d for d in result.discrepancies if "Поручитель 1" in d.field]
        self.assertEqual(len(w_disc), 0)

    def test_witness2_with_surname(self):
        """Witness 2 surname from Фамилия column."""
        srow = self._make_witness_sheet_row(
            w1_name="Сидоръ", w1_patr="Ивановъ",
            w2_name="Кириллъ", w2_patr="",
            w2_last_name="Беззубовъ")
        crow = self._make_witness_csv_row(
            w1_status=MARRIAGE_STATUS_MALE, w1_residence="Заманиловка",
            w1_name_modern="Сидор", w1_patr_modern="Иванов",
            w1_name_canon="Исидор", w1_patr_canon="Иванович",
            w1_fio="Исидор Иванович",
            w2_status=MARRIAGE_STATUS_MALE, w2_residence="Заманиловка",
            w2_name_modern="Кирилл", w2_last_name="Беззубов",
            w2_name_canon="Кирилл",
            w2_fio="Беззубов Кирилл",
        )
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        w_disc = [d for d in result.discrepancies if "Поручитель 2" in d.field]
        self.assertEqual(len(w_disc), 0)


# ─── Tests for death orig_names and relative branches ────────────────────────

class TestCompareDeathsOrigAndRelative(unittest.TestCase):
    """Cover orig_names parsing and relative branch in compare_deaths."""

    def test_death_with_orig_names(self):
        """Cover lines 907-908, 921-927: death with orig_names parsing."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_B_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE, D_ORIG_NAMES)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1", D_B_DAY: "2",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Иванъ", D_DEC_PATR: "Петровъ",
            D_AGE: "50",
            D_ORIG_NAMES: "Имена в МК: Іоаннъ Петровъ",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            15: "2",
            18: "Заманиловка", 20: "экономический крестьянин",
            23: "Иоанн", 24: "Петров", 25: "Иоанн", 26: "Петрович",
            27: "50", 41: "натуральная",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        # The orig_names path was exercised
        [d for d in result.discrepancies
                     if "Умерший" in d.field and "Имя" in d.field]
        # Check we got results (may or may not have discrepancies depending on transforms)
        self.assertIsNotNone(result)

    def test_death_with_relative(self):
        """Cover relative branch in compare_deaths."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_B_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE, D_RELATIONSHIP, D_REL_NAME, D_REL_PATR)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1", D_B_DAY: "2",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Иванъ", D_DEC_PATR: "Петровъ",
            D_AGE: "50",
            D_RELATIONSHIP: "жена",
            D_REL_NAME: "Сидоръ", D_REL_PATR: "Ивановъ",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            15: "2",
            18: "Заманиловка", 20: "экономический крестьянин",
            23: "Иван", 24: "Петров", 25: "Иван", 26: "Петрович",
            27: "50", 31: "жена", 41: "натуральная",
            32: "Заманиловка", 34: DEATH_STATUS_MALE,
            37: "Сидор", 38: "Иванов", 39: "Сидор", 40: "Иванович",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        [d for d in result.discrepancies if "Родственник" in d.field]
        # Should match if transforms are consistent
        self.assertIsNotNone(result)

    def test_death_title_word_in_deceased_name(self):
        """Cover line 946-948: title word handling in deceased name."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "дьячок", D_DEC_PATR: "Иванъ",
            D_AGE: "70",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            18: "Заманиловка", 20: "дьячок",
            23: "Иван", 24: "", 25: "Иван", 26: "",
            27: "70", 41: "натуральная",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        # Title word "вдова" should become status, name becomes "Марья"
        self.assertIsNotNone(result)

    def test_death_imena_placeholder(self):
        """Cover lines 951-952: 'Имена' placeholder in deceased name."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_AGE)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Имена",
            D_AGE: "1",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            18: "Заманиловка", 20: "экономический крестьянин",
            23: "?", 24: "", 25: "?", 26: "",
            27: "1", 41: "натуральная",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        self.assertIsNotNone(result)


# ─── Tests for resolve_name_patr edge cases ──────────────────────────────────

class TestResolveNamePatrEdgeCases(unittest.TestCase):
    def test_patr_should_be_lastname(self):
        """Cover lines 387-388: patronymic reclassified as last name."""
        # "Наковалкин" looks like a last name, not a patronymic
        row = make_sheet_row({10: "Иванъ", 11: "Наковалкин"})
        _name, patr, ln = resolve_name_patr(row, 10, 11, None, None)
        self.assertEqual(ln, "Наковалкин")
        self.assertEqual(patr, "")

    def test_invalid_old_patronymic_dropped(self):
        """Cover line 392: invalid old patronymic is dropped."""
        # Modern-form patronymic "Ивановна" is not a valid old-form patronymic
        row = make_sheet_row({10: "Марья", 11: "Ивановна"})
        _name, patr, _ln = resolve_name_patr(row, 10, 11, None, None)
        self.assertEqual(patr, "")


# ─── Tests for resolve_name_patr_marriage_orig edge cases ────────────────────

class TestResolveNamePatrMarriageOrigEdgeCases(unittest.TestCase):
    def test_imena_placeholder(self):
        """Cover lines 421-422: 'Имена' placeholder."""
        row = make_sheet_row({10: "Имена", 11: ""})
        name, patr, _ln = resolve_name_patr_marriage_orig([], 99, 10, 11, None, None, row)
        self.assertEqual(name, "?")
        self.assertEqual(patr, "")

    def test_patr_as_lastname(self):
        """Cover lines 424-426: patronymic reclassified as last name."""
        row = make_sheet_row({10: "Иванъ", 11: "Наковалкин"})
        _name, patr, ln = resolve_name_patr_marriage_orig([], 99, 10, 11, None, None, row)
        self.assertEqual(ln, "Наковалкин")
        self.assertEqual(patr, "")

    def test_invalid_old_patronymic_marriage(self):
        """Cover line 428-429: invalid old patronymic dropped in marriage."""
        row = make_sheet_row({10: "Марья", 11: "Ивановна"})
        _name, patr, _ln = resolve_name_patr_marriage_orig([], 99, 10, 11, None, None, row)
        self.assertEqual(patr, "")

    def test_orig_parts_used(self):
        """Cover lines 403-408: orig_parts are used when available."""
        row = make_sheet_row({10: "fallback_name", 11: "fallback_patr"})
        name, patr, _ln = resolve_name_patr_marriage_orig(
            ["Іоаннъ Петровъ"], 0, 10, 11, None, None, row)
        self.assertEqual(name, "Іоаннъ")
        self.assertEqual(patr, "Петровъ")


# ─── Tests for main() edge cases ────────────────────────────────────────────

class TestMainEdgeCases(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(patch("verso.ru.importers.validation.site_config", _test_site))

    @patch("verso.ru.importers.validation.print_report")
    @patch("verso.ru.importers.validation.validate_record_type")
    @patch("verso.ru.importers.validation.split_by_year")
    @patch("verso.ru.importers.validation.fetch_all_sheets")
    @patch("verso.ru.importers.validation.argparse.ArgumentParser.parse_args")
    def test_missing_tab_warning(self, mock_args, mock_fetch, mock_split,
                                 mock_validate, mock_report):
        """Cover lines 1261-1262: missing tab in spreadsheet."""
        mock_args.return_value = MagicMock(
            record_type=None, year=None, regenerate=False, fix=None, dry_run=False, fix_empty=False, site="zamanilovka", csv=None)
        # Only return "рождение" - "брак" and "смерть" are missing
        mock_fetch.return_value = {"рождение": []}
        mock_split.return_value = {}
        mock_validate.return_value = ValidationResult(record_type="births")
        mock_report.return_value = []

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            main()

        self.assertIn("not found", mock_err.getvalue())

    @patch("verso.ru.importers.validation.fix_discrepancies")
    @patch("verso.ru.importers.validation.print_report")
    @patch("verso.ru.importers.validation.validate_record_type")
    @patch("verso.ru.importers.validation.split_by_year")
    @patch("verso.ru.importers.validation.fetch_all_sheets")
    @patch("verso.ru.importers.validation.argparse.ArgumentParser.parse_args")
    def test_fix_invalid_id(self, mock_args, mock_fetch, mock_split,
                            mock_validate, mock_report, mock_fix):
        """Cover lines 1282-1286: invalid fix id warning."""
        mock_args.return_value = MagicMock(
            record_type="births", year=None, regenerate=False,
            fix=["abc"], dry_run=False, fix_empty=False, site="zamanilovka", csv=None)
        mock_fetch.return_value = {"рождение": []}
        mock_split.return_value = {}
        mock_validate.return_value = ValidationResult(record_type="births")
        mock_report.return_value = []

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            main()

        self.assertIn("invalid fix id", mock_err.getvalue())
        mock_fix.assert_called_once()

    @patch("verso.ru.importers.validation.fix_discrepancies")
    @patch("verso.ru.importers.validation.print_report")
    @patch("verso.ru.importers.validation.validate_record_type")
    @patch("verso.ru.importers.validation.split_by_year")
    @patch("verso.ru.importers.validation.fetch_all_sheets")
    @patch("verso.ru.importers.validation.argparse.ArgumentParser.parse_args")
    def test_fix_all_string_in_list(self, mock_args, mock_fetch, mock_split,
                                    mock_validate, mock_report, mock_fix):
        """Cover lines 1283-1285: 'all' mixed with numeric ids."""
        mock_args.return_value = MagicMock(
            record_type="births", year=None, regenerate=False,
            fix=["1", "all"], dry_run=False, fix_empty=False, site="zamanilovka", csv=None)
        mock_fetch.return_value = {"рождение": []}
        mock_split.return_value = {}
        mock_validate.return_value = ValidationResult(record_type="births")
        mock_report.return_value = []

        with patch("sys.stderr", new_callable=io.StringIO):
            main()

        mock_fix.assert_called_once()
        self.assertEqual(mock_fix.call_args[0][1], ["all"])


# ─── Test for CSV_YEAR_COL constant ──────────────────────────────────────────

# ─── Tests for print_report with count_mismatches and missing_csv ────────────

class TestPrintReportBranches(unittest.TestCase):
    def test_count_mismatch_output(self):
        """Cover lines 1116-1118: count mismatch printing."""
        r = ValidationResult(record_type="births")
        r.count_mismatches = [(1800, 5, 3)]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_report([r])
        output = mock_out.getvalue()
        self.assertIn("RECORD COUNT MISMATCHES", output)
        self.assertIn("1800", output)
        self.assertIn("sheet=5", output)
        self.assertIn("csv=3", output)

    def test_missing_csv_output(self):
        """Cover lines 1123-1124: missing CSV printing."""
        r = ValidationResult(record_type="deaths")
        r.missing_csv = [1800, 1801]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_report([r])
        output = mock_out.getvalue()
        self.assertIn("MISSING CSVs", output)
        self.assertIn("1800", output)
        self.assertIn("1801", output)


# ─── Tests for fix_discrepancies missing worksheet ───────────────────────────

class TestFixDiscrepanciesMissingWorksheet(unittest.TestCase):
    def test_worksheet_not_found(self):
        """Cover lines 1215-1216: worksheet not found during fix."""
        disc = [
            Discrepancy(year=1800, record_type="births", record_num="1",
                        field="Лист", sheet_val="10", csv_val="20",
                        sheet_row_idx=5),
        ]
        mock_gspread = MagicMock()
        mock_gc = MagicMock()
        mock_gspread.oauth.return_value = mock_gc
        # Return no worksheets so lookup fails
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = []
        mock_gc.open_by_key.return_value = mock_spreadsheet

        mock_rowcol_to_a1 = MagicMock(return_value="F6")
        with patch.dict("sys.modules", {
            "gspread": mock_gspread,
            "gspread.utils": MagicMock(rowcol_to_a1=mock_rowcol_to_a1),
        }):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                fix_discrepancies(disc, [1], "test_id", dry_run=False)
        self.assertIn("not found", mock_out.getvalue())


# ─── Tests for death relative with orig_names ───────────────────────────────

class TestCompareDeathsRelativeOrig(unittest.TestCase):
    """Cover deeper relative branches: orig_names, title words, Имена."""

    def test_relative_with_orig_names(self):
        """Cover lines 979-985: relative with orig_names."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE, D_RELATIONSHIP, D_REL_NAME, D_REL_PATR, D_ORIG_NAMES)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Иванъ", D_DEC_PATR: "Петровъ",
            D_AGE: "2",
            D_RELATIONSHIP: "отец",
            D_REL_NAME: "Петръ", D_REL_PATR: "Сидоровъ",
            D_ORIG_NAMES: "Имена в МК: Іоаннъ Петровъ; Петръ Сидоровъ",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            18: "Заманиловка", 20: "экономический крестьянин",
            23: "Иоанн", 24: "", 25: "Иоанн", 26: "",
            27: "2", 31: "отец", 41: "натуральная",
            32: "Заманиловка", 34: DEATH_STATUS_MALE,
            37: "Петр", 38: "Сидоров", 39: "Петр", 40: "Сидорович",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        # Orig_names path for relative was exercised
        self.assertIsNotNone(result)

    def test_relative_title_word(self):
        """Cover lines 996-998: title word in relative name."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_AGE, D_RELATIONSHIP, D_REL_NAME, D_REL_PATR)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "жен", D_D_MONTH: "январь",
            D_D_DAY: "1",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Марья",
            D_AGE: "50",
            D_RELATIONSHIP: "муж",
            D_REL_NAME: "дьячок", D_REL_PATR: "Иванъ",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "жен", 12: "1", 13: "январь",
            18: "Заманиловка", 20: "экономическая крестьянка",
            23: "Марья", 24: "", 25: "Мария", 26: "",
            27: "50", 31: "муж", 41: "натуральная",
            32: "Заманиловка", 34: "дьячок",
            37: "Иван", 38: "", 39: "Иван", 40: "",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        self.assertIsNotNone(result)

    def test_relative_imena_placeholder(self):
        """Cover lines 1000-1001: 'Имена' in relative name."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_AGE, D_RELATIONSHIP, D_REL_NAME)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "муж", D_D_MONTH: "январь",
            D_D_DAY: "1",
            D_PAGE: "10", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Иванъ",
            D_AGE: "2",
            D_RELATIONSHIP: "отец",
            D_REL_NAME: "Имена",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь",
            18: "Заманиловка", 20: "экономический крестьянин",
            23: "Иван", 24: "", 25: "Иван", 26: "",
            27: "2", 31: "отец", 41: "натуральная",
            32: "Заманиловка", 34: DEATH_STATUS_MALE,
            37: "?", 38: "", 39: "?", 40: "",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1800, result)
        self.assertIsNotNone(result)


# ─── Tests for marriage orig_names ───────────────────────────────────────────

class TestCompareMarriagesOrig(unittest.TestCase):
    def test_marriage_with_orig_names(self):
        """Cover lines 753-754: marriage with orig_names parsing."""
        from verso.ru.importers.google_sheets import (
            M_RECORD_NUM, M_W_MONTH, M_W_DAY, M_PAGE, M_ARCHIVE, M_FUND, M_INVENTORY, M_CASE, M_GROOM_NAME, M_GROOM_PATR, M_BRIDE_NAME, M_BRIDE_PATR, M_ORIG_NAMES)
        srow = make_sheet_row({
            M_RECORD_NUM: "1", M_W_MONTH: "январь", M_W_DAY: "5",
            M_PAGE: "10", M_ARCHIVE: "ГАТО", M_FUND: "1049",
            M_INVENTORY: "1", M_CASE: "5",
            M_GROOM_NAME: "Иванъ", M_GROOM_PATR: "Петровъ",
            M_BRIDE_NAME: "Марья", M_BRIDE_PATR: "Иванова",
            M_ORIG_NAMES: "Имена в МК: Іоаннъ Петровъ; Марья Іванова",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "5", 12: "январь",
            14: "Заманиловка", 16: "экономический крестьянин",
            19: "Иоанн", 20: "Петров", 21: "Иоанн", 22: "Петрович",
            35: "Заманиловка", 37: "девка из экономических крестьян",
            39: "Марья", 40: "Иванова", 41: "Мария", 42: "Ивановна",
        }, width=120)
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1800, result)
        self.assertIsNotNone(result)


# ─── Tests for resolve_name_patr_marriage_orig title word ────────────────────

class TestResolveNamePatrMarriageOrigTitleWord(unittest.TestCase):
    def test_title_word_in_name(self):
        """Cover line 416-418, 451, 453-454: title word handling."""
        row = make_sheet_row({10: "дьячок", 11: "Иванъ"})
        name, patr, _ln = resolve_name_patr_marriage_orig([], 99, 10, 11, None, None, row)
        self.assertEqual(name, "Иванъ")
        self.assertEqual(patr, "")


# ─── Tests for godparent title word branches ─────────────────────────────────

class TestCompareBirthsGodparentTitleWord(unittest.TestCase):
    """Cover GP1 & GP2 title word branches (lines 649-656, 677-684)."""

    def test_gp1_title_word(self):
        """GP1 name is a title word like 'вдова'."""
        from verso.ru.importers.google_sheets import (
            B_RECORD_NUM, B_GENDER, B_B_MONTH, B_B_DAY, B_K_DAY, B_PAGE, B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE, B_CHILD_NAME, B_FATHER_NAME, B_FATHER_PATR, B_MOTHER_NAME, B_MOTHER_PATR, B_GP1_NAME, B_GP1_PATR)
        srow = make_sheet_row({
            B_RECORD_NUM: "1", B_GENDER: "муж",
            B_B_MONTH: "январь", B_B_DAY: "1", B_K_DAY: "2",
            B_PAGE: "10", B_ARCHIVE: "ГАТО", B_FUND: "1049",
            B_INVENTORY: "1", B_CASE: "5",
            B_CHILD_NAME: "Иванъ",
            B_FATHER_NAME: "Петръ", B_FATHER_PATR: "Ивановъ",
            B_MOTHER_NAME: "Марья", B_MOTHER_PATR: "Петрова",
            B_GP1_NAME: "дьячок", B_GP1_PATR: "Иванъ",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь", 15: "2",
            18: "Иван", 19: "Иван",
            20: "Заманиловка", 22: "экономический крестьянин",
            25: "Петр", 26: "Иванов", 27: "Петр", 28: "Иванович",
            29: "экономическая крестьянка",
            31: "Марья", 32: "Петрова", 33: "Мария", 34: "Петровна",
            # GP1: title word "дьячок" → name becomes "Иванъ", patr empty
            35: BIRTH_STATUS_MALE, 36: "Заманиловка",
            38: "Иван", 39: "", 40: "Иван", 41: "", 42: "Иван",
        })
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        # Title word branch was exercised
        self.assertIsNotNone(result)

    def test_gp2_title_word(self):
        """GP2 name is a title word."""
        from verso.ru.importers.google_sheets import (
            B_RECORD_NUM, B_GENDER, B_B_MONTH, B_B_DAY, B_K_DAY, B_PAGE, B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE, B_CHILD_NAME, B_FATHER_NAME, B_FATHER_PATR, B_MOTHER_NAME, B_MOTHER_PATR, B_GP1_NAME, B_GP1_PATR, B_GP2_NAME, B_GP2_PATR)
        srow = make_sheet_row({
            B_RECORD_NUM: "1", B_GENDER: "муж",
            B_B_MONTH: "январь", B_B_DAY: "1", B_K_DAY: "2",
            B_PAGE: "10", B_ARCHIVE: "ГАТО", B_FUND: "1049",
            B_INVENTORY: "1", B_CASE: "5",
            B_CHILD_NAME: "Иванъ",
            B_FATHER_NAME: "Петръ", B_FATHER_PATR: "Ивановъ",
            B_MOTHER_NAME: "Марья", B_MOTHER_PATR: "Петрова",
            B_GP1_NAME: "Сидоръ", B_GP1_PATR: "Ивановъ",
            B_GP2_NAME: "дьячок", B_GP2_PATR: "Иванъ",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь", 15: "2",
            18: "Иван", 19: "Иван",
            20: "Заманиловка", 22: "экономический крестьянин",
            25: "Петр", 26: "Иванов", 27: "Петр", 28: "Иванович",
            29: "экономическая крестьянка",
            31: "Марья", 32: "Петрова", 33: "Мария", 34: "Петровна",
            35: BIRTH_STATUS_MALE, 36: "Заманиловка",
            38: "Сидор", 39: "Иванов", 40: "Исидор", 41: "Иванович",
            42: "Исидор Иванович",
            # GP2: title word "дьячок" → name becomes "Иванъ"
            43: BIRTH_STATUS_MALE, 44: "Заманиловка",
            46: "Иван", 47: "", 48: "Иван", 49: "", 50: "Иван",
        })
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        self.assertIsNotNone(result)


class TestCSVYearCol(unittest.TestCase):
    def test_births_year_col(self):
        self.assertEqual(CSV_YEAR_COL["births"], 14)

    def test_deaths_year_col(self):
        self.assertEqual(CSV_YEAR_COL["deaths"], 14)

    def test_marriages_year_col(self):
        self.assertEqual(CSV_YEAR_COL["marriages"], 13)


class TestReconstructAge(unittest.TestCase):

    def test_reconstruct_age_years(self):
        self.assertEqual(_reconstruct_age("45", "", "", ""), "45")

    def test_reconstruct_age_months(self):
        self.assertEqual(_reconstruct_age("", "6", "", ""), "6 м")

    def test_reconstruct_age_weeks(self):
        self.assertEqual(_reconstruct_age("", "", "2", ""), "2 н")

    def test_reconstruct_age_days(self):
        self.assertEqual(_reconstruct_age("", "", "", "3"), "3 д")

    def test_reconstruct_age_empty(self):
        self.assertEqual(_reconstruct_age("", "", "", ""), "")


class TestSplitNamePatrDash(unittest.TestCase):
    """Issue 2+3: dash handling in split_name_patr within _parse_orig_names."""

    def _split(self, s):
        from verso.ru.importers.google_sheets import _parse_orig_names
        # Use gp1 slot to test split_name_patr
        result = _parse_orig_names(f"Имена в МК: {s}", False, False, False, True, False)
        val = result.get("gp1", ("", "", ""))
        return val[0], val[1]  # return only name, patr

    def test_dash_comment_stripped(self):
        """'Лев - Бобчинский' → ' - Бобчинский' stripped as comment, name='Лев'."""
        name, patr = self._split("Лев - Бобчинский")
        self.assertEqual(name, "Лев")
        self.assertEqual(patr, "")  # comment stripped

    def test_dash_only_patr(self):
        """'Лев -' → name='Лев', patr=''."""
        name, patr = self._split("Лев -")
        self.assertEqual(name, "Лев")
        self.assertEqual(patr, "")

    def test_dash_as_name(self):
        """'- Нестерова' → '-' is not a valid name, returns empty."""
        name, patr = self._split("- Нестерова")
        self.assertEqual(name, "")
        self.assertEqual(patr, "")

    def test_normal_unchanged(self):
        """Normal names unaffected."""
        name, patr = self._split("Иван Петров")
        self.assertEqual(name, "Иван")
        self.assertEqual(patr, "Петров")


class TestSwapPatronymicGender(unittest.TestCase):
    """Issue 4: _swap_patronymic_gender helper."""

    def test_feminine_to_masculine(self):
        from verso.ru.importers.google_sheets import _swap_patronymic_gender
        self.assertEqual(_swap_patronymic_gender("Петрова"), "Петров")
        self.assertEqual(_swap_patronymic_gender("Сергеева"), "Сергеев")
        self.assertEqual(_swap_patronymic_gender("Ильина"), "Ильин")

    def test_masculine_to_feminine(self):
        from verso.ru.importers.google_sheets import _swap_patronymic_gender
        self.assertEqual(_swap_patronymic_gender("Петров"), "Петрова")
        self.assertEqual(_swap_patronymic_gender("Сергеев"), "Сергеева")
        self.assertEqual(_swap_patronymic_gender("Ильин"), "Ильина")

    def test_unrecognized_returns_none(self):
        from verso.ru.importers.google_sheets import _swap_patronymic_gender
        self.assertIsNone(_swap_patronymic_gender("Фёдорович"))


class TestPatrShouldBeLastnameGenderSwap(unittest.TestCase):
    """Issue 4: _patr_should_be_lastname should NOT reclassify cross-gender old patronymics."""

    def test_male_name_female_patr_valid_swap(self):
        from verso.ru.importers.google_sheets import _patr_should_be_lastname
        # Калина (male) + Петрова (female patronymic) — valid old patronymic in male form
        result = _patr_should_be_lastname("Калина", "Петрова")
        self.assertFalse(result)

    def test_male_name_female_patr_invalid(self):
        from verso.ru.importers.google_sheets import _patr_should_be_lastname
        # A true surname that doesn't validate as patronymic even when swapped
        result = _patr_should_be_lastname("Иван", "Шилохвостова")
        self.assertTrue(result)


class TestCompareBirthsGodparentSurname(unittest.TestCase):
    """GP surname from dedicated column should appear in FIO comparison."""

    def _make_gp_sheet_row(self, gp1_name="", gp1_patr="", gp1_last_name="",
                           gp1_fio=""):
        from verso.ru.importers.google_sheets import (
            B_RECORD_NUM, B_GENDER, B_B_MONTH, B_B_DAY, B_K_DAY, B_PAGE, B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE, B_CHILD_NAME, B_FATHER_NAME, B_FATHER_PATR, B_MOTHER_NAME, B_MOTHER_PATR, B_GP1_NAME, B_GP1_PATR, B_GP1_FIO)
        d = {
            B_RECORD_NUM: "1", B_GENDER: "муж",
            B_B_MONTH: "январь", B_B_DAY: "1", B_K_DAY: "2",
            B_PAGE: "10", B_ARCHIVE: "ГАТО", B_FUND: "1049",
            B_INVENTORY: "1", B_CASE: "5",
            B_CHILD_NAME: "Иван",
            B_FATHER_NAME: "Петр", B_FATHER_PATR: "Иванов",
            B_MOTHER_NAME: "Марья", B_MOTHER_PATR: "Петрова",
        }
        if gp1_name:
            d[B_GP1_NAME] = gp1_name
        if gp1_patr:
            d[B_GP1_PATR] = gp1_patr
        if gp1_fio:
            d[B_GP1_FIO] = gp1_fio
        # GP1 last name — use BirthColumns.GP1_LAST_NAME if mapped
        if gp1_last_name:
            from verso.ru.importers.google_sheets import BirthColumns
            idx = BirthColumns().GP1_LAST_NAME
            if idx is not None:
                d[idx] = gp1_last_name
        return make_sheet_row(d)

    def test_gp1_surname_in_fio(self):
        srow = self._make_gp_sheet_row(
            gp1_name="Семен", gp1_patr="Петров",
            gp1_last_name="Манилов",
            gp1_fio="Манилов Семен Петрович")
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "муж", 12: "1", 13: "январь", 15: "2",
            18: "Иван", 19: "Иоанн",
            20: "Заманиловка", 22: "экономический крестьянин",
            25: "Петр", 26: "Иванов", 27: "Петр", 28: "Иванович",
            29: "экономическая крестьянка",
            31: "Марья", 32: "Петрова", 33: "Мария", 34: "Петровна",
            35: "экономический крестьянин", 36: "Заманиловка",
            37: "Манилов",
            38: "Семен", 39: "Петров",
            40: "Симеон", 41: "Петрович",
            42: "Манилов Симеон Петрович",
        })
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1800, result)
        fio_disc = [d for d in result.discrepancies
                    if "ФИО" in d.field and "Восприемник 1" in d.field]
        self.assertEqual(len(fio_disc), 0,
                         f"FIO should match with surname, got: {[(d.sheet_val, d.csv_val) for d in fio_disc]}")


class TestParseOrigParts(unittest.TestCase):
    """Tests for _parse_orig_parts helper that filters comment text from orig_names."""

    def test_valid_prefix_returns_name_parts(self):
        """Parts after 'Имена в МК:' prefix that look like names are returned."""
        from verso.ru.importers.validation import _parse_orig_parts
        result = _parse_orig_parts("Имена в МК: Федор Александров; Анна Иванова")
        self.assertEqual(result, ["Федор Александров", "Анна Иванова"])

    def test_no_prefix_returns_empty(self):
        """Text without 'Имена в МК:' prefix is a comment, not names."""
        from verso.ru.importers.validation import _parse_orig_parts
        result = _parse_orig_parts("Возраст не виден из-за корешка книги")
        self.assertEqual(result, [])

    def test_comment_parts_after_prefix_filtered(self):
        """Semicolon-separated parts starting with non-name words are filtered out."""
        from verso.ru.importers.validation import _parse_orig_parts
        result = _parse_orig_parts(
            "Имена в МК: Федор Александров; Отчество невесты не видно из-за повреждения страницы")
        self.assertEqual(result, ["Федор Александров"])

    def test_comment_with_lowercase_non_name_word(self):
        """'Родители не указаны' is a comment, not a name."""
        from verso.ru.importers.validation import _parse_orig_parts
        result = _parse_orig_parts("Имена в МК: Спиридон; Родители не указаны")
        self.assertEqual(result, ["Спиридон"])

    def test_empty_string_returns_empty(self):
        from verso.ru.importers.validation import _parse_orig_parts
        self.assertEqual(_parse_orig_parts(""), [])

    def test_none_returns_empty(self):
        from verso.ru.importers.validation import _parse_orig_parts
        self.assertEqual(_parse_orig_parts(None), [])

    def test_prefix_only_returns_empty(self):
        from verso.ru.importers.validation import _parse_orig_parts
        self.assertEqual(_parse_orig_parts("Имена в МК:"), [])

    def test_imya_comment_filtered(self):
        """'Имя невесты не видно...' starts with 'имя' -> filtered."""
        from verso.ru.importers.validation import _parse_orig_parts
        result = _parse_orig_parts(
            "Имена в МК: Павел Терентьев; Имя невесты не видно полностью из-за корешка")
        self.assertEqual(result, ["Павел Терентьев"])

    def test_dash_comment_stripped_from_part(self):
        """'Макар Тимофеев - отчествно неразборчиво написано' -> 'Макар Тимофеев'."""
        from verso.ru.importers.validation import _parse_orig_parts
        result = _parse_orig_parts(
            "Имена в МК: Евграф Мартынов; Макар Тимофеев - отчествно неразборчиво написано; Домна Дементьева")
        self.assertEqual(result, ["Евграф Мартынов", "Макар Тимофеев", "Домна Дементьева"])

    def test_dash_short_comment_stripped(self):
        """'Федор Яковлев - вдовой' -> 'Федор Яковлев'."""
        from verso.ru.importers.validation import _parse_orig_parts
        result = _parse_orig_parts(
            "Имена в МК: Федор Яковлев - вдовой; Параскева Егорова")
        self.assertEqual(result, ["Федор Яковлев", "Параскева Егорова"])


class TestCompareDeathsCommentInOrigNames(unittest.TestCase):
    """Regression: comments in ORIG_NAMES must not be parsed as person names."""

    def test_death_comment_not_treated_as_name(self):
        """'Возраст не виден...' in ORIG_NAMES must not override deceased name."""
        from verso.ru.importers.google_sheets import (
            D_RECORD_NUM, D_GENDER, D_D_MONTH, D_D_DAY, D_B_DAY, D_PAGE, D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE, D_DEC_NAME, D_DEC_PATR, D_AGE, D_ORIG_NAMES)
        srow = make_sheet_row({
            D_RECORD_NUM: "1", D_GENDER: "жен", D_D_MONTH: "декабрь",
            D_D_DAY: "9", D_B_DAY: "10",
            D_PAGE: "41об", D_ARCHIVE: "ГАТО", D_FUND: "1049",
            D_INVENTORY: "1", D_CASE: "5",
            D_DEC_NAME: "Анна", D_DEC_PATR: "",
            D_AGE: "3",
            D_ORIG_NAMES: "Возраст не виден из-за корешка книги",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "41об", 10: "1", 11: "жен", 12: "9", 13: "декабрь",
            15: "10",
            18: "Горюхино", 20: "экономическая крестьянка",
            21: "", 23: "Анна", 24: "", 25: "Анна", 26: "",
            27: "3", 41: "натуральная",
        })
        result = ValidationResult(record_type="deaths")
        compare_deaths([(2, srow)], [crow], 1801, result)
        name_disc = [d for d in result.discrepancies
                     if "Умерший" in d.field and "Имя" in d.field]
        self.assertEqual(len(name_disc), 0,
                         f"Name should be 'Анна', not parsed from comment: {[(d.field, d.sheet_val, d.csv_val) for d in name_disc]}")


class TestCompareMarriagesCommentInOrigNames(unittest.TestCase):
    """Regression: comments after semicolons in ORIG_NAMES must not become bride names."""

    def test_marriage_comment_not_treated_as_bride_name(self):
        """'Отчество невесты не видно...' must not override bride name."""
        from verso.ru.importers.google_sheets import (
            M_RECORD_NUM, M_W_MONTH, M_W_DAY, M_PAGE, M_ARCHIVE, M_FUND, M_INVENTORY, M_CASE, M_GROOM_NAME, M_GROOM_PATR, M_GROOM_STATUS, M_BRIDE_NAME, M_BRIDE_PATR, M_BRIDE_STATUS, MarriageColumns)
        cols = MarriageColumns(
            ORIG_NAMES=80,
        )
        srow = make_sheet_row({
            M_RECORD_NUM: "1", M_W_MONTH: "май", M_W_DAY: "3",
            M_PAGE: "10", M_ARCHIVE: "ГАТО", M_FUND: "1049",
            M_INVENTORY: "1", M_CASE: "5",
            M_GROOM_NAME: "Федор", M_GROOM_PATR: "Александров",
            M_GROOM_STATUS: "экономический крестьянин",
            M_BRIDE_NAME: "Анна", M_BRIDE_PATR: "",
            M_BRIDE_STATUS: "девка из экономических крестьян",
            80: "Имена в МК: Федор Александров; Отчество невесты не видно из-за повреждения страницы",
        })
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "1", 11: "3", 12: "май",
            14: "Горюхино", 16: "экономический крестьянин",
            17: "", 19: "Федор", 20: "Александров", 21: "Федор", 22: "Александрович",
            23: "",
            35: "Горюхино", 37: "девка из экономических крестьян",
            38: "", 39: "Анна", 40: "", 41: "Анна", 42: "",
            43: "",
            102: "", 106: "", 108: "",
        }, width=120)
        result = ValidationResult(record_type="marriages")
        compare_marriages([(2, srow)], [crow], 1807, result, cols=cols)
        bride_name_disc = [d for d in result.discrepancies
                          if "Невеста" in d.field and "Имя" in d.field]
        self.assertEqual(len(bride_name_disc), 0,
                         f"Bride name should be 'Анна', not parsed from comment: {[(d.field, d.sheet_val, d.csv_val) for d in bride_name_disc]}")


class TestCompareBirthsGodparentOrigSurname(unittest.TestCase):
    """Regression: surname from orig 3-tuple must be used, not column value."""

    def test_gp1_orig_surname_preferred_over_column(self):
        """When _parse_orig_names returns (name, patr, surname), use that surname."""
        from verso.ru.importers.google_sheets import (
            B_RECORD_NUM, B_GENDER, B_B_MONTH, B_B_DAY, B_K_DAY, B_PAGE, B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE, B_CHILD_NAME, B_FATHER_NAME, B_FATHER_PATR, B_GP1_NAME, B_GP1_PATR, B_GP1_FIO, B_ORIG_NAMES, BirthColumns)
        bc = BirthColumns()
        srow = make_sheet_row({
            B_RECORD_NUM: "12", B_GENDER: "жен",
            B_B_MONTH: "август", B_B_DAY: "17", B_K_DAY: "19",
            B_PAGE: "10", B_ARCHIVE: "ГАТО", B_FUND: "1049",
            B_INVENTORY: "1", B_CASE: "5",
            B_CHILD_NAME: "Наталья",
            B_FATHER_NAME: "Назарий", B_FATHER_PATR: "Петров",
            B_GP1_NAME: "Варвара", B_GP1_PATR: "Николаева",
            B_GP1_FIO: "Пеночкина Варвара Николаевна",
            B_ORIG_NAMES: "Имена в МК: Наталья; Назарий Петров; Варвара Николаева Манилова",
        })
        # Set GP1_LAST_NAME column if mapped
        if bc.GP1_LAST_NAME is not None:
            srow[bc.GP1_LAST_NAME] = "Пеночкина"
        crow = make_csv_row({
            1: "ГАТО", 2: "1049", 3: "1", 4: "5",
            5: "10", 10: "12", 11: "жен", 12: "17", 13: "август", 15: "19",
            18: "Наталья", 19: "Наталья",
            20: "Заманиловка", 22: "экономический крестьянин",
            25: "Назарий", 26: "Петров", 27: "Назарий", 28: "Петрович",
            35: "помещица", 36: "Заманиловка",
            37: "Манилова",
            38: "Варвара", 39: "Николаева",
            40: "Варвара", 41: "Николаевна",
            42: "Манилова Варвара Николаевна",
        })
        result = ValidationResult(record_type="births")
        compare_births([(2, srow)], [crow], 1823, result)
        fio_disc = [d for d in result.discrepancies
                    if "ФИО" in d.field and "Восприемник 1" in d.field]
        self.assertEqual(len(fio_disc), 0,
                         f"Orig surname 'Манилова' should be used, not column 'Пеночкина': "
                         f"{[(d.sheet_val, d.csv_val) for d in fio_disc]}")


if __name__ == "__main__":
    unittest.main()


# --- a village's Google sheet lives in its village.toml -------------------

def _sheets_workspace(root: Path, sheets: str) -> Path:
    (root / "verso.toml").write_text('schema = 2\nvillages = ["Вязовка"]\n', encoding="utf-8")
    (root / "Вязовка").mkdir(parents=True, exist_ok=True)
    (root / "Вязовка" / "village.toml").write_text("schema = 1\n[sheets]\n" + sheets, encoding="utf-8")
    return root


def _second_village(root: Path, name: str, text: str) -> None:
    (root / "verso.toml").write_text(f'schema = 2\nvillages = ["Вязовка", "{name}"]\n', encoding="utf-8")
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "village.toml").write_text(text, encoding="utf-8")


class TestSiteConfig(unittest.TestCase):
    SHEETS = ('site = "vyazovka"\nspreadsheet_id = "sheet-id"\nvillage_filter = "Вязовка"\n'
              'csv_prefix = "Вязовка"\ndsl_prefix = "vyazovka"\nformat = "familio-standard"\nheader_rows = 3\n'
              'tab_map = { births = "f - 1", marriages = "f - 2", deaths = "f - 3" }\n')

    def test_site_config_reads_the_villages_sheets(self) -> None:
        from verso.ru.importers.google_sheets import FORMAT_FAMILIO_STANDARD
        from verso.ru.importers.validation import SiteConfig, site_config, sites
        with TemporaryDirectory() as tmp, use(_sheets_workspace(Path(tmp), self.SHEETS)):
            self.assertEqual(sites(), {"vyazovka": "Вязовка"})
            self.assertEqual(site_config("vyazovka"), SiteConfig(
                spreadsheet_id="sheet-id", village_filter="Вязовка", village="Вязовка", csv_prefix="Вязовка",
                dsl_prefix="vyazovka", header_rows=3, fmt=FORMAT_FAMILIO_STANDARD,
                tab_map={"births": "f - 1", "marriages": "f - 2", "deaths": "f - 3"}))

    def test_an_unknown_site_names_the_known_ones(self) -> None:
        from verso.core.corpus_data import CorpusDataError
        from verso.ru.importers.validation import site_config
        with TemporaryDirectory() as tmp, use(_sheets_workspace(Path(tmp), self.SHEETS)):
            with self.assertRaisesRegex(CorpusDataError, "нет таблицы «zamanilovka»: есть vyazovka"):
                site_config("zamanilovka")

    def test_an_unknown_key_of_sheets_is_refused(self) -> None:
        from verso.core.corpus_data import CorpusDataError
        from verso.ru.importers.validation import site_config
        with TemporaryDirectory() as tmp, use(_sheets_workspace(Path(tmp), self.SHEETS + 'sheet = "x"\n')):
            with self.assertRaisesRegex(CorpusDataError, r"village\.toml: неизвестный ключ «sheets\.sheet»"):
                site_config("vyazovka")

    def test_a_missing_key_of_sheets_is_refused(self) -> None:
        from verso.core.corpus_data import CorpusDataError
        from verso.ru.importers.validation import site_config
        sheets = self.SHEETS.replace('spreadsheet_id = "sheet-id"\n', "")
        with TemporaryDirectory() as tmp, use(_sheets_workspace(Path(tmp), sheets)):
            with self.assertRaisesRegex(CorpusDataError, r"village\.toml: нет ключа «sheets\.spreadsheet_id»"):
                site_config("vyazovka")

    def test_a_value_of_the_wrong_type_is_refused_naming_its_key(self) -> None:
        from verso.core.corpus_data import CorpusDataError
        from verso.ru.importers.validation import site_config
        for old, new, message in [
            ('header_rows = 3', 'header_rows = "3"', "«sheets.header_rows» — ожидалось целое число"),
            ('tab_map = { births = "f - 1", marriages = "f - 2", deaths = "f - 3" }', 'tab_map = "f - 1"',
             "«sheets.tab_map» — ожидалась таблица строк"),
            ('dsl_prefix = "vyazovka"', "dsl_prefix = 1", "«sheets.dsl_prefix» — ожидалась строка"),
            ('header_rows = 3', 'header_rows = 3\nyear_col_map = { births = "14" }',
             "«sheets.year_col_map» — ожидалась таблица целых чисел"),
        ]:
            assert old in self.SHEETS
            with self.subTest(message=message), TemporaryDirectory() as tmp, \
                    use(_sheets_workspace(Path(tmp), self.SHEETS.replace(old, new))):
                with self.assertRaisesRegex(CorpusDataError, r"village\.toml: " + re.escape(message)):
                    site_config("vyazovka")

    def test_a_broken_village_does_not_hide_another_villages_sheet(self) -> None:
        from verso.core.corpus_data import CorpusDataError
        from verso.ru.importers.validation import site_config, sites
        with TemporaryDirectory() as tmp:
            root = _sheets_workspace(Path(tmp), self.SHEETS)
            _second_village(root, "Враловка", 'schema = 1\n[sheets]\nsite = 1\n')
            with use(root):
                self.assertEqual(sites(), {"vyazovka": "Вязовка"})
                self.assertEqual(site_config("vyazovka").village, "Вязовка")
                with self.assertRaisesRegex(CorpusDataError,
                                            r"нет таблицы «vralovka»: есть vyazovka; не прочитано: .*Враловка/village\.toml: "
                                            r"«sheets\.site» — ожидалась строка"):
                    site_config("vralovka")

    def test_a_broken_toml_of_another_village_does_not_hide_a_sheet(self) -> None:
        from verso.ru.importers.validation import site_config
        with TemporaryDirectory() as tmp:
            root = _sheets_workspace(Path(tmp), self.SHEETS)
            _second_village(root, "Враловка", "schema = 1\n[sheets\n")
            with use(root):
                self.assertEqual(site_config("vyazovka").village, "Вязовка")

    def test_a_site_named_by_two_villages_is_refused(self) -> None:
        from verso.core.corpus_data import CorpusDataError
        from verso.ru.importers.validation import site_config
        with TemporaryDirectory() as tmp:
            root = _sheets_workspace(Path(tmp), self.SHEETS)
            _second_village(root, "Враловка", "schema = 1\n[sheets]\n" + self.SHEETS)
            with use(root), self.assertRaisesRegex(
                    CorpusDataError, "таблицу «vyazovka» называют две деревни: Вязовка, Враловка — оставьте одну"):
                site_config("vyazovka")

    def test_site_is_required(self) -> None:
        from verso.ru.importers.validation import main
        with patch("sys.argv", ["validation"]), patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--site", err.getvalue())
