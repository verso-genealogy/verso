"""A synthetic Familio МК workbook for the library's tests.

The official template (`Shablon_MK.xlsx`) is Familio's file and lives with the corpus's data
(`<corpus>/familio/Shablon_MK.xlsx`); what the tests assert of it — its helper sheets, VLOOKUPs,
x14 dropdowns, formatting — is a corpus's own test. The
library's tests ask only what our writer does, on a workbook of the shape it reads: one sheet a
record type with two header rows over `TEMPLATE_DATA_START_ROW`, a `location` sheet and an
`about` sheet labelled in column A.
"""
from __future__ import annotations

from pathlib import Path

from verso.ru.exporters.familio_spravochnik import LOCATION_HELPER_HEADERS
from verso.ru.exporters.familio_template import TEMPLATE_MAPS, TEMPLATE_SHEET_TITLES

# The about sheet's labels the writer fills (FamilioTemplateWriter._write_about_sheet).
ABOUT_LABELS = (
    "Название справочника",
    "Годы, охватываемые индексацией",
    "Наименьший год, охватываемый индексацией",
    "Описание, которое будет под названием справочника на сайте",
    "Кем проведена индексация (авторство)",
    "Ссылка на профиль автора на Familio",
    "Никнейм (имя пользователя) в мессенджере Telegram для ссылки на автора",
    "Тип написания окончания отчества у людей (рождённых, умерших детей)",
    "Это новый справочник или дополнительные данные к ранее начатому?",
    "Ссылка на загруженный ранее справочник на сайте familio.org",
)
# Where the record sheets keep a location helper (a VLOOKUP against `location`): the column right
# of each Н.П. the source maps — template column H (event) and, for births, U (parent).
_HELPERS = {"births": {8: "full_location", 21: "person_location"}, "marriages": {8: "full_location"},
            "deaths": {8: "full_location"}}
assert {h for cols in _HELPERS.values() for h in cols.values()} <= LOCATION_HELPER_HEADERS


def build_template(path: Path) -> Path:
    """Write the synthetic workbook to `path` and return it."""
    import openpyxl

    wb = openpyxl.Workbook()
    for sheet in list(wb.worksheets):
        wb.remove(sheet)
    for record_type, title in TEMPLATE_SHEET_TITLES.items():
        ws = wb.create_sheet(title)
        ws.cell(1, 1, title)
        for c in range(1, len(TEMPLATE_MAPS[record_type]) + 1):
            ws.cell(2, c, "№ п/п" if c == 1 else f"поле {c}")
        for c, header in _HELPERS[record_type].items():
            ws.cell(2, c, header)
    location = wb.create_sheet("location")
    for c, header in enumerate(("Н.П.", "тип", "губерния", "уезд", "волость", "сборка", "full_location",
                                "ссылка", "uuid"), start=1):
        location.cell(2, c, header)
    location.cell(3, 1, "образец")
    about = wb.create_sheet("about")
    for r, label in enumerate(ABOUT_LABELS, start=1):
        about.cell(r, 1, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
