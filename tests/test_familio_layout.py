"""The МК workbook the library builds itself: the template's layout as data (`familio_mk.json`), a workbook of
five sheets made of it, and the writer filling that workbook where it is given no template file."""
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import openpyxl
import pytest

from verso.ru.exporters.familio_layout import LOCATION_HELPER_HEADERS, build_workbook, load_layout
from verso.ru.exporters.familio_spravochnik import (
    AboutInfo, FamilioTemplateWriter, LocationRow, YearRecords, build_spravochnik)
from verso.ru.exporters.familio_template import TEMPLATE_DATA_START_ROW, TEMPLATE_MAPS, TEMPLATE_SHEET_TITLES

WIDTHS = {"births": 81, "marriages": 111, "deaths": 65}     # a source row of each familio CSV
ABOUT = AboutInfo(spravochnik_name="Метрические книги с. Маниловка", description="Описание", author_name="Автор",
                  author_familio_url="https://example.org/a", author_telegram="@avtor", otchestvo_type="старый",
                  is_update=True, prior_catalog_url="https://example.org/catalog")
LOCATIONS = [LocationRow("Маниловка", "с.", "Энская", "Маниловский", "Заманиловская", "https://example.org/s/1")]


def _row(record_type: str, number: str, **cells: str) -> list[str]:
    row = [""] * WIDTHS[record_type]
    row[1], row[2], row[3], row[4], row[6], row[10] = "ЦГА", "47", "9", "755", "Маниловка", number
    for column, value in cells.items():
        row[int(column.removeprefix("c"))] = value
    return row


def _spravochnik(**births_cells: str):
    return build_spravochnik("Маниловка", 1900, 1901, {
        "births": [YearRecords(1900, [_row("births", "1", c19="Иван", c20="Маниловка", **births_cells),
                                      _row("births", "2", c19="Анна")])],
        "marriages": [YearRecords(1901, [_row("marriages", "1")])],
        "deaths": [YearRecords(1900, [_row("deaths", "1")])],
    })


def _cells(path: Path) -> dict[str, dict[str, object]]:
    """Every written cell of the five sheets the library fills, by sheet and coordinate."""
    wb = openpyxl.load_workbook(path)
    return {name: {c.coordinate: c.value for row in wb[name].iter_rows() for c in row if c.value is not None}
            for name in ("about", "location", *TEMPLATE_SHEET_TITLES.values())}


def test_layout_matches_the_maps():
    layout = load_layout()
    assert {k: len(s.columns) for k, s in layout.sheets.items()} == {k: len(m) for k, m in TEMPLATE_MAPS.items()}
    assert {k: len(s.columns) for k, s in layout.sheets.items()} == {"births": 69, "marriages": 97, "deaths": 53}
    for record_type, sheet in layout.sheets.items():
        assert sheet.title == TEMPLATE_SHEET_TITLES[record_type]
        assert sheet.helpers == frozenset(
            c for c, name in enumerate(sheet.columns, start=1) if name in LOCATION_HELPER_HEADERS)
        assert sheet.helpers, record_type
        # A helper column is filled by a formula, never from a source column — and reads the Н.П. on its left.
        assert all(TEMPLATE_MAPS[record_type][c - 1] is None for c in sheet.helpers)
        assert all(TEMPLATE_MAPS[record_type][c - 2] is not None for c in sheet.helpers)


def test_layout_holds_no_sample():
    text = files("verso.ru.exporters").joinpath("familio_mk.json").read_text(encoding="utf-8")
    assert "familio.org/users" not in text and "@" not in text and "http" not in text
    strings: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            strings.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)

    walk(json.loads(text))
    assert max(len(s) for s in strings) <= 120


def test_built_workbook_has_five_sheets():
    layout = load_layout()
    wb = build_workbook()
    assert wb.sheetnames == ["about", "location", "РОЖДЕНИЕ", "БРАК", "СМЕРТЬ"]
    for record_type, sheet in layout.sheets.items():
        ws = wb[sheet.title]
        assert [ws.cell(2, c).value for c in range(1, len(sheet.columns) + 1)] == list(sheet.columns)
        for first, last, label in sheet.groups:
            assert ws.cell(1, first).value == label
            if last > first:
                assert f"{ws.cell(1, first).coordinate}:{ws.cell(1, last).coordinate}" in {
                    str(m) for m in ws.merged_cells.ranges}, (record_type, label)
        assert ws.max_row == 2                                    # no data row, no sample
        assert ws.freeze_panes == "A4"
        assert not ws.data_validations.dataValidation and not ws.tables
    about, location = wb["about"], wb["location"]
    assert [about["A1"].value, about["B1"].value] == ["Название", "Содержимое"]
    assert [(r, about.cell(r, 1).value) for r, _ in layout.about_labels] == list(layout.about_labels)
    assert [about.cell(r, 2).value for r, _ in layout.about_labels] == [None] * len(layout.about_labels)
    assert [location.cell(1, c).value for c in range(1, 10)] == list(layout.location_titles)
    assert [location.cell(2, c).value for c in range(1, 10)] == list(layout.location_names)
    assert location.max_row == 2 and location.freeze_panes == "A3"


def test_writer_without_template(tmp_path):
    out = FamilioTemplateWriter().write(_spravochnik(), tmp_path / "mk.xlsx", location_rows=LOCATIONS, about=ABOUT)
    wb = openpyxl.load_workbook(out)
    births = wb["РОЖДЕНИЕ"]
    start = TEMPLATE_DATA_START_ROW
    assert [births.cell(start, 1).value, births.cell(start + 1, 1).value] == [1, 2]       # сквозная
    assert births.cell(start, 19).value == "Иван" and births.cell(start, 20).value == "Маниловка"
    assert births.cell(3, 1).value is None
    for c in load_layout().sheets["births"].helpers:
        formula = births.cell(start, c).value
        assert isinstance(formula, str) and formula.startswith("=IF(") and "VLOOKUP(" in formula, c
    assert wb["БРАК"].cell(start, 1).value == 1 and wb["СМЕРТЬ"].cell(start, 1).value == 1
    location = wb["location"]
    assert [location.cell(3, c).value for c in (1, 2, 3, 4, 5, 8)] == [
        "Маниловка", "с.", "Энская", "Маниловский", "Заманиловская", "https://example.org/s/1"]
    assert all(str(location.cell(3, c).value).startswith("=") for c in (6, 7, 9))
    about = {wb["about"].cell(r, 1).value: wb["about"].cell(r, 2).value for r, _ in load_layout().about_labels}
    assert all(value not in (None, "") for value in about.values()), about
    assert about["Название справочника"] == "Метрические книги с. Маниловка"
    assert about["Годы, охватываемые индексацией"] == "1900-1901"
    assert about["Это новый справочник или дополнительные данные к ранее начатому?"] == "обновление начатого ранее"


def test_same_cells_with_and_without_template(tmp_path):
    """A template file of the same layout — with the sample rows and the helper sheets Familio's carries — is
    filled to the very cells the built workbook is: the samples go, the extra sheets stay."""
    template = build_workbook()
    for title in TEMPLATE_SHEET_TITLES.values():
        template[title].cell(TEMPLATE_DATA_START_ROW, 2, "образец")
        template[title].cell(TEMPLATE_DATA_START_ROW + 5, 3, "образец")
    template["location"].cell(3, 1, "Образцовка")
    template.create_sheet("spiski").cell(1, 1, "список")
    path = tmp_path / "template.xlsx"
    template.save(path)
    with_template = FamilioTemplateWriter(path).write(
        _spravochnik(), tmp_path / "a.xlsx", location_rows=LOCATIONS, about=ABOUT)
    built = FamilioTemplateWriter().write(_spravochnik(), tmp_path / "b.xlsx", location_rows=LOCATIONS, about=ABOUT)
    assert _cells(with_template) == _cells(built)
    assert "spiski" in openpyxl.load_workbook(with_template).sheetnames
    assert "spiski" not in openpyxl.load_workbook(built).sheetnames


@pytest.mark.parametrize("value", ["=1+1", "=HYPERLINK(\"http://example.org\")", "+7 900", "-см. № 5", "@имя"])
def test_record_value_is_never_a_formula(tmp_path, value):
    out = FamilioTemplateWriter().write(_spravochnik(c79=value), tmp_path / "mk.xlsx")      # births «Комментарий»
    ws = openpyxl.load_workbook(out)["РОЖДЕНИЕ"]
    column = TEMPLATE_MAPS["births"].index(79) + 1
    cell = ws.cell(TEMPLATE_DATA_START_ROW, column)
    assert cell.value == value and cell.data_type == "s"
    formulas = {c.column for row in ws.iter_rows(min_row=TEMPLATE_DATA_START_ROW) for c in row if c.data_type == "f"}
    assert formulas == set(load_layout().sheets["births"].helpers)


def test_about_and_location_values_are_never_formulas(tmp_path):
    about = AboutInfo("=A1", "=B2", "=cmd", "", "", "современный", False, "")
    places = [LocationRow("=Маниловка", "=с.", "", "", "", "=link")]
    out = FamilioTemplateWriter().write(_spravochnik(), tmp_path / "mk.xlsx", location_rows=places, about=about)
    wb = openpyxl.load_workbook(out)
    assert {c.coordinate for row in wb["about"].iter_rows() for c in row if c.data_type == "f"} == set()
    assert {c.column for c in wb["location"][3] if c.data_type == "f"} == {6, 7, 9}
    assert wb["location"]["A3"].value == "=Маниловка"


def test_built_workbook_says_its_years_without_an_about(tmp_path):
    out = FamilioTemplateWriter().write(_spravochnik(), tmp_path / "mk.xlsx")
    ws = openpyxl.load_workbook(out)["about"]
    said = {ws.cell(r, 1).value: ws.cell(r, 2).value for r, _ in load_layout().about_labels}
    assert said.pop("Годы, охватываемые индексацией") == "1900-1901"
    assert said.pop("Наименьший год, охватываемый индексацией") == 1900
    assert set(said.values()) == {None}


def test_a_template_about_is_left_alone_without_an_about(tmp_path):
    template = build_workbook()
    template["about"]["B5"] = "образец годов"
    template.save(tmp_path / "template.xlsx")
    out = FamilioTemplateWriter(tmp_path / "template.xlsx").write(_spravochnik(), tmp_path / "mk.xlsx")
    assert openpyxl.load_workbook(out)["about"]["B5"].value == "образец годов"
