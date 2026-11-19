"""TDD tests for the Familio справочник submission exporter.

A *справочник* is one Familio submission file covering many years of records,
projected onto the official Familio МК template (``Shablon_MK.xlsx``). These tests
pin the domain rules (continuous сквозная numbering, year ordering, column
remapping, empty-tab skipping) and the template-filling writer — on a synthetic
workbook of the template's shape; the template itself is the corpus's data.
"""
import functools
import tempfile
import unittest
from pathlib import Path

from verso.ru.exporters.familio_spravochnik import (
    AboutInfo, FamilioTemplateWriter, YearRecords, build_sheet, build_spravochnik, read_about)
from verso.ru.exporters.familio_template import SRC_BIRTHS

from tests.familio_template import build_template

# A synthetic workbook of the template's shape (tests/familio_template.py): Familio's own file is the
# corpus's data, and what is asserted of it is a corpus's own test.
@functools.cache
def template() -> Path:
    return build_template(Path(tempfile.mkdtemp(prefix="familio-template-")) / "Shablon_MK.xlsx")

# Width of a source births CSV row (verso.ru.exporters.csv_familio births header).
BIRTHS_SRC_WIDTH = 81


def births_src_row(record_num="1", archive="ГАРО", child_name="Иван", father_residence=""):
    """A minimal source births row: only the columns the tests assert on."""
    row = [""] * BIRTHS_SRC_WIDTH
    row[1] = archive            # Архив
    row[10] = record_num        # № записи
    row[14] = "1832"            # Рожд. Год
    row[19] = child_name        # Имя реб. (совр.)
    row[20] = father_residence  # Отец: Н.П.
    return row


class TestBuildSheet(unittest.TestCase):
    def test_assigns_continuous_skvoznaya(self):
        yr = YearRecords(year=1832, rows=[births_src_row(), births_src_row(), births_src_row()])
        sheet = build_sheet("births", [yr])
        assert sheet is not None
        self.assertEqual([r[0] for r in sheet.rows], ["1", "2", "3"])  # template col "А"

    def test_orders_rows_by_year(self):
        later = YearRecords(year=1840, rows=[births_src_row(archive="A40")])
        earlier = YearRecords(year=1832, rows=[births_src_row(archive="A32")])
        sheet = build_sheet("births", [later, earlier])  # given out of order
        assert sheet is not None
        self.assertEqual([r[1] for r in sheet.rows], ["A32", "A40"])  # Архив column
        self.assertEqual([r[0] for r in sheet.rows], ["1", "2"])

    def test_remaps_to_template_columns(self):
        sheet = build_sheet("births", [YearRecords(1832, [births_src_row(record_num="7", child_name="Пётр")])])
        assert sheet is not None
        self.assertEqual(sheet.title, "РОЖДЕНИЕ")
        self.assertEqual(len(sheet.rows[0]), len(SRC_BIRTHS))  # 69 template cols
        row = sheet.rows[0]
        self.assertEqual(row[10], "7")       # № записи preserved at template idx 10
        self.assertEqual(row[18], "Пётр")    # child Имя lands at template idx 18
        self.assertEqual(row[7], "")         # full_location left blank

    def test_maps_father_residence_to_pripiski(self):
        sheet = build_sheet("births", [YearRecords(1832, [births_src_row(father_residence="Собакевичево")])])
        assert sheet is not None
        # Родитель / Н.П. приписки (template col T, idx 19) = father residence.
        self.assertEqual(sheet.rows[0][19], "Собакевичево")

    def test_returns_none_when_no_rows(self):
        self.assertIsNone(build_sheet("deaths", [YearRecords(1832, [])]))
        self.assertIsNone(build_sheet("deaths", []))


class TestBuildSpravochnik(unittest.TestCase):
    def test_skips_record_type_with_no_rows(self):
        records_by_type = {
            "births": [YearRecords(1832, [births_src_row()])],
            "marriages": [YearRecords(1832, [[""] * 111])],
            "deaths": [YearRecords(1832, [])],
        }
        sp = build_spravochnik("Горюхино", 1832, 1840, records_by_type)
        self.assertEqual([s.title for s in sp.sheets], ["РОЖДЕНИЕ", "БРАК"])  # СМЕРТЬ skipped

    def test_carries_year_range_and_village(self):
        sp = build_spravochnik(
            "Горюхино", 1832, 1840, {"births": [YearRecords(1832, [births_src_row()])]}
        )
        self.assertEqual((sp.village, sp.from_year, sp.to_year), ("Горюхино", 1832, 1840))


class TestFamilioTemplateWriter(unittest.TestCase):
    def test_injects_curated_location_sheet(self):
        import openpyxl

        from verso.ru.exporters.familio_spravochnik import LocationRow

        sp = build_spravochnik(
            "Горюхино", 1832, 1832, {"births": [YearRecords(1832, [births_src_row()])]}
        )
        rows = [
            LocationRow("Горюхино", "с.", "Глуповская", "Ротозейский", "Майданская", "url-1"),
            LocationRow("Собакевичево", "с.", "Глуповская", "Ротозейский", "Майданская", "url-2"),
        ]
        with tempfile.TemporaryDirectory() as d:
            out = FamilioTemplateWriter(template()).write(
                sp, Path(d) / "mk.xlsx", location_rows=rows
            )
            ws = openpyxl.load_workbook(out)["location"]
            # Curated places written from row 3; full_location (col G) is a formula.
            self.assertEqual(ws.cell(3, 1).value, "Горюхино")
            self.assertEqual(ws.cell(4, 1).value, "Собакевичево")
            self.assertTrue(str(ws.cell(3, 7).value).startswith("=CONCATENATE("))
            self.assertEqual(ws.cell(3, 8).value, "url-1")
            # Template's sample rows beyond the curated data are cleared.
            self.assertIsNone(ws.cell(5, 1).value)

    def test_fills_about_sheet_by_label(self):
        import openpyxl

        from verso.ru.exporters.familio_spravochnik import AboutInfo

        sp = build_spravochnik(
            "Горюхино", 1832, 1840, {"births": [YearRecords(1832, [births_src_row()])]}
        )
        about = AboutInfo(
            spravochnik_name="МК с. Горюхино за 1832-1840 годы",
            description="МК 1832–1840, Ротозейского уезда",
            author_name="Дмитрий Чичиков",
            author_familio_url="https://familio.org/users/abc",
            author_telegram="@author_handle",
            otchestvo_type="современный",
            is_update=True,
            prior_catalog_url="https://familio.org/knowledge-base/catalogs/mkgorjuhinotambov",
        )
        with tempfile.TemporaryDirectory() as d:
            out = FamilioTemplateWriter(template()).write(sp, Path(d) / "mk.xlsx", about=about)
            ws = openpyxl.load_workbook(out)["about"]
            labelled = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, ws.max_row + 1)}
            self.assertEqual(labelled["Название справочника"], "МК с. Горюхино за 1832-1840 годы")
            self.assertEqual(labelled["Годы, охватываемые индексацией"], "1832-1840")
            self.assertEqual(labelled["Наименьший год, охватываемый индексацией"], 1832)
            self.assertEqual(labelled["Кем проведена индексация (авторство)"], "Дмитрий Чичиков")
            self.assertEqual(
                labelled["Это новый справочник или дополнительные данные к ранее начатому?"],
                "обновление начатого ранее",
            )

def delo_row(case, record_num="1", archive="ГАТО"):
    """A births source row stamped with a specific дело (Архив/Фонд/Опись/Дело)."""
    row = births_src_row(record_num=record_num, archive=archive)
    row[2] = "1049"   # Фонд
    row[3] = "10"     # Опись
    row[4] = case     # Дело
    return row


class TestDeloGrouping(unittest.TestCase):
    """Records of the same дело are grouped together (CLI gap-fill files)."""

    def test_same_delo_rows_become_contiguous(self):
        # 1799: case 90 (×2) then case 85 (×2); 1800: case 90 (×1).
        yr1799 = YearRecords(1799, [delo_row("90", "a"), delo_row("90", "b"),
                                    delo_row("85", "c"), delo_row("85", "d")])
        yr1800 = YearRecords(1800, [delo_row("90", "e")])
        sheet = build_sheet("births", [yr1800, yr1799])  # input order shouldn't matter
        assert sheet is not None
        delos = [r[4] for r in sheet.rows]  # template col E (idx 4) = Дело
        # дело 85 (earliest 1799) first; дело 90 groups its 1799 + 1800 rows together.
        self.assertEqual(delos, ["85", "85", "90", "90", "90"])
        self.assertEqual([r[0] for r in sheet.rows], ["1", "2", "3", "4", "5"])  # renumbered

    def test_thick_border_at_each_delo_boundary(self):
        import openpyxl

        yr = YearRecords(1799, [delo_row("85", "a"), delo_row("85", "b"), delo_row("90", "c")])
        sp = build_spravochnik("Горюхино", 1799, 1799, {"births": [yr]})
        with tempfile.TemporaryDirectory() as d:
            out = FamilioTemplateWriter(template()).write(sp, Path(d) / "mk.xlsx")
            ws = openpyxl.load_workbook(out)["РОЖДЕНИЕ"]
            # Order 85,85,90 -> rows 4,5,6; boundaries after row 5 (last 85) and row 6 (end).
            self.assertEqual(ws.cell(5, 5).border.bottom.style, "thick")
            self.assertEqual(ws.cell(6, 5).border.bottom.style, "thick")
            self.assertNotEqual(ws.cell(4, 5).border.bottom.style, "thick")  # mid-group

    def test_cases_filter_keeps_only_listed_дела(self):
        def fid_row(fund, opis, delo, rec):
            r = births_src_row(record_num=rec)
            r[2], r[3], r[4] = fund, opis, delo
            return r

        yr = YearRecords(1810, [
            fid_row("64", "9", "956", "a"),
            fid_row("40", "1", "13", "b"),   # stray дело to drop
            fid_row("64", "9", "956", "c"),
        ])
        sheet = build_sheet("births", [yr], cases=frozenset({"64-9-956"}))
        assert sheet is not None
        self.assertEqual([r[4] for r in sheet.rows], ["956", "956"])  # 13 filtered out
        # Without a filter every record is kept.
        unfiltered = build_sheet("births", [yr])
        assert unfiltered is not None
        self.assertEqual(len(unfiltered.rows), 3)


class TestYearsLabel(unittest.TestCase):
    """Non-contiguous year-set support (CLI --years)."""

    def test_single_year(self):
        from verso.ru.cli.familio_spravochnik import years_label_for

        self.assertEqual(years_label_for([1805]), "1805")

    def test_contiguous_range(self):
        from verso.ru.cli.familio_spravochnik import years_label_for

        self.assertEqual(years_label_for([1832, 1833, 1834, 1835]), "1832-1835")

    def test_non_contiguous_set(self):
        from verso.ru.cli.familio_spravochnik import years_label_for

        self.assertEqual(years_label_for([1799, 1805]), "1799, 1805")

    def test_build_spravochnik_years_label_default_is_range(self):
        sp = build_spravochnik("Горюхино", 1799, 1805, {"births": [YearRecords(1799, [births_src_row()])]})
        self.assertEqual(sp.years_label, "1799-1805")

    def test_build_spravochnik_years_label_explicit(self):
        sp = build_spravochnik(
            "Горюхино", 1799, 1805,
            {"births": [YearRecords(1799, [births_src_row()])]}, years_label="1799, 1805",
        )
        self.assertEqual(sp.years_label, "1799, 1805")


class TestReadAbout(unittest.TestCase):
    def _about_json(self, d):
        import json

        data = {
            "spravochnik_name": "Метрические книги с. {village} за {years} годы",
            "description": "МК {village}, {years}",
            "author_name": "Дмитрий Чичиков",
            "author_familio_url": "https://familio.org/users/abc",
            "author_telegram": "@author_handle",
            "otchestvo_type": "современный",
            "is_update": True,
            "prior_catalog_url": "https://familio.org/knowledge-base/catalogs/mkgorjuhinotambov",
        }
        p = Path(d) / "about.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def test_substitutes_village_and_years(self):
        with tempfile.TemporaryDirectory() as d:
            about = read_about(self._about_json(d), "Горюхино", 1799, 1805, "1799, 1805")
            assert about is not None
            self.assertEqual(about.spravochnik_name, "Метрические книги с. Горюхино за 1799, 1805 годы")
            self.assertEqual(about.description, "МК Горюхино, 1799, 1805")
            self.assertTrue(about.is_update)

    def test_years_label_defaults_to_range_when_omitted(self):
        with tempfile.TemporaryDirectory() as d:
            about = read_about(self._about_json(d), "Горюхино", 1832, 1840)
            assert about is not None
            self.assertEqual(about.spravochnik_name, "Метрические книги с. Горюхино за 1832-1840 годы")

    def test_missing_file_returns_none(self):
        self.assertIsNone(read_about(Path("/no/such/about.json"), "X", 1, 2))

    def test_about_sheet_годы_cell_uses_years_label(self):
        import openpyxl

        sp = build_spravochnik(
            "Горюхино", 1799, 1805,
            {"births": [YearRecords(1799, [births_src_row()])]}, years_label="1799, 1805",
        )
        about = AboutInfo(
            spravochnik_name="n", description="d", author_name="A",
            author_familio_url="u", author_telegram="@a", otchestvo_type="современный",
            is_update=True, prior_catalog_url="c",
        )
        with tempfile.TemporaryDirectory() as d:
            out = FamilioTemplateWriter(template()).write(sp, Path(d) / "mk.xlsx", about=about)
            ws = openpyxl.load_workbook(out)["about"]
            labelled = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, ws.max_row + 1)}
            self.assertEqual(labelled["Годы, охватываемые индексацией"], "1799, 1805")
            self.assertEqual(labelled["Наименьший год, охватываемый индексацией"], 1799)


if __name__ == "__main__":
    unittest.main()
