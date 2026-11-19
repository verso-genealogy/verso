"""The `location` sheet from the records and the places: every place a row names gets a line, what the places
dictionary says of it unambiguously is filled in, the rest is left for the indexer."""
from __future__ import annotations

import openpyxl

from verso.core import places as core_places
from verso.ru.exporters.familio_layout import load_layout
from verso.ru.exporters.familio_spravochnik import (
    FamilioTemplateWriter, LocationRow, YearRecords, blank_places, build_spravochnik, derive_location, known_from,
    location_rows, referenced_places)
from verso.ru.exporters.familio_template import TEMPLATE_DATA_START_ROW

PLACES = core_places.parse('''
["Маниловка"]
city = "село Маниловка"
county = "Маниловский уезд, Заманиловская волость"
state = "Энская губерния"
country = "Россия"
familio = "00000000-0000-4000-8000-0000000000aa"

["с. Маниловка"]
same_as = "Маниловка"

["Энск"]
city = "город Энск"
county = "Маниловский уезд"
state = "Энская область"
country = "Россия"

["Выселки"]
city = "Выселки при речке"
county = "Маниловский уезд"
state = "Энская губерния"
country = "Россия"
''')


def _births(*rows: dict[int, str]) -> list[YearRecords]:
    made = []
    for number, cells in enumerate(rows, start=1):
        row = [""] * 81
        row[1], row[2], row[3], row[4], row[10] = "ЦГА", "47", "9", "755", str(number)
        for column, value in cells.items():
            row[column] = value
        made.append(row)
    return [YearRecords(1900, made)]


def _spravochnik(*rows: dict[int, str]):
    return build_spravochnik("Маниловка", 1900, 1900, {"births": _births(*rows)})


def test_referenced_places_from_every_helper():
    # The event's place (6), the father's (20), the first godparent's (36), a relative's (62).
    sp = _spravochnik({6: "Маниловка", 20: "Энск", 36: "Выселки"}, {6: "Маниловка", 62: "Чужая", 20: ""})
    assert referenced_places(sp) == ["Маниловка", "Энск", "Выселки", "Чужая"]


def test_referenced_places_keep_the_spelling_as_written():
    assert referenced_places(_spravochnik({6: "с. Маниловка"}, {6: "Маниловка "})) == ["с. Маниловка", "Маниловка "]


def test_derive_village():
    row = known_from(PLACES)("Маниловка")
    assert row == LocationRow("Маниловка", "с.", "Энская", "Маниловский", "Заманиловская",
                              "https://familio.org/settlements/00000000-0000-4000-8000-0000000000aa")


def test_derive_town_without_volost():
    row = known_from(PLACES)("Энск")
    assert (row.type, row.district, row.volost, row.link) == ("г.", "Маниловский", "", "")


def test_state_that_is_no_guberniya_is_kept_whole():
    assert known_from(PLACES)("Энск").region == "Энская область"


def test_derive_unknown_word_leaves_type_blank():
    row = known_from(PLACES)("Выселки")
    assert (row.place, row.type, row.region) == ("Выселки", "", "Энская")


def test_derive_location_reads_the_fields_alone():
    row = derive_location("Как написано", {"city": "деревня Иная", "county": "Иной уезд, Иная волость, прочее",
                                           "state": "Иная губерния", "country": "Россия"}, {})
    assert row == LocationRow("Как написано", "д.", "Иная", "Иной", "Иная", "")
    assert derive_location("Пусто", {}, {}) == LocationRow("Пусто", "", "", "", "", "")


def test_spelling_takes_its_canon():
    row = known_from(PLACES)("с. Маниловка")
    assert row.place == "с. Маниловка"
    assert (row.type, row.district, row.link[-2:]) == ("с.", "Маниловский", "aa")


def test_a_place_written_with_a_space_is_found_and_kept_as_written():
    row = known_from(PLACES)("Маниловка ")
    assert row is not None and row.place == "Маниловка " and row.type == "с."


def test_place_unknown_to_the_dictionary_is_none():
    assert known_from(PLACES)("Чужая") is None


def test_curated_wins_and_keeps_order():
    curated = [LocationRow("Лишняя", "д.", "А", "Б", "", ""), LocationRow("Маниловка", "сельцо", "Своя", "", "", "u")]
    rows = location_rows(["Энск", "Маниловка"], curated=curated, known=known_from(PLACES))
    assert rows[:2] == curated
    assert [r.place for r in rows] == ["Лишняя", "Маниловка", "Энск"]
    assert rows[2].type == "г."


def test_place_unknown_to_everyone_gets_a_blank_row():
    rows = location_rows(["Чужая", "Маниловка"], known=known_from(PLACES))
    assert rows[0] == LocationRow("Чужая", "", "", "", "", "")
    assert blank_places(rows) == 1


def test_location_rows_without_a_dictionary():
    assert location_rows(["Маниловка"]) == [LocationRow("Маниловка", "", "", "", "", "")]


def test_no_vlookup_misses(tmp_path):
    sp = _spravochnik({6: "Маниловка", 20: "с. Маниловка", 36: "Чужая"}, {6: "Маниловка ", 44: "Энск"})
    rows = location_rows(referenced_places(sp), known=known_from(PLACES))
    out = FamilioTemplateWriter().write(sp, tmp_path / "mk.xlsx", location_rows=rows)
    wb = openpyxl.load_workbook(out)
    listed = {str(wb["location"].cell(r, 1).value) for r in range(3, wb["location"].max_row + 1)}
    ws = wb["РОЖДЕНИЕ"]
    looked_up = 0
    for row in ws.iter_rows(min_row=TEMPLATE_DATA_START_ROW):
        for column in load_layout().sheets["births"].helpers:
            source = row[column - 2].value
            if source not in (None, ""):
                looked_up += 1
                assert str(source) in listed, source
    assert looked_up == 5
