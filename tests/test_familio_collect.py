"""`collect`: a справочник's rows from record sets — no CSV on a disk, the unreviewed left out."""
from __future__ import annotations

import csv
from calendar import Month
from pathlib import Path

import pytest

from tests import records_fixture
from verso.ru.domain import Gender, page, person
from verso.ru.dsl.records.births import birth, birth_month, birth_records
from verso.ru.exporters.csv_familio import exporter_of
from verso.ru.exporters.familio_spravochnik import (
    RECORD_SET_TYPES, RECORD_TYPES, Collected, build_sheet, collect, years_label_for)


@pytest.fixture(scope="module")
def sets() -> dict[str, object]:
    return records_fixture.namespace()


def _rows_through_a_file(record_set, tmp_path: Path) -> list[list[str]]:
    """The set's rows as the CLI once read them: `export()` into a directory, the file read back."""
    exporter = exporter_of(record_set)
    assert exporter is not None
    with open(exporter.export(record_set, target_dir=tmp_path), encoding="utf-8", newline="") as f:
        return list(csv.reader(f))[1:]


def _small_births(case: str, numbers: tuple[int, ...], *, parish: str = "Маниловка", year: int = 1900):
    return birth_records(
        "ЦГА", "47", "9", case, parish, "Церковь", year,
        *page("1", *birth_month(Month.JANUARY, *(
            birth(n, Gender.MALE, 3, 4, child=person("Иванъ"), father=person("Петръ")) for n in numbers))))


def test_record_set_types_are_the_three_tabs():
    assert sorted(RECORD_SET_TYPES.values()) == sorted(RECORD_TYPES)


def test_rows_equal_the_csv_path(sets, tmp_path):
    collected = collect(sets.values(), reviewed_only=False)
    assert isinstance(collected, Collected)
    for variable, record_type in (("births", "births"), ("marriages", "marriages"),
                                  ("hlestakovka_deaths_1913", "deaths")):
        (year_records,) = collected.records_by_type[record_type]
        assert year_records.year == sets[variable].year
        assert year_records.rows == _rows_through_a_file(sets[variable], tmp_path)
    assert collected.left_out == 0
    assert collected.taken == sum(len(sets[v].records) for v in ("births", "marriages", "hlestakovka_deaths_1913"))


def test_unreviewed_left_out_and_counted(sets, tmp_path):
    births = sets["births"]
    unreviewed = [r for r in births.records if getattr(r, "reviewed", None) is False]
    assert len(unreviewed) == 2, "the fixture: two unreviewed births, one of them on Geni"
    collected = collect([births])
    (year_records,) = collected.records_by_type["births"]
    every = _rows_through_a_file(births, tmp_path)
    kept = [row for row, r in zip(every, births.records, strict=True) if r not in unreviewed]
    assert year_records.rows == kept
    assert collected.left_out == 2
    assert collected.taken == len(births.records) - 2
    # …and with the switch off they are in, as the CLI once wrote them.
    all_in = collect([births], reviewed_only=False)
    assert all_in.records_by_type["births"][0].rows == every
    assert all_in.left_out == 0


def test_a_record_on_geni_and_unreviewed_is_left_out(sets):
    births = sets["births"]
    on_geni = births.records[2]
    assert vars(on_geni).get("on_geni") is True
    numbers = [row[10] for row in collect([births]).records_by_type["births"][0].rows]
    assert str(on_geni.record_num) not in numbers


def test_parish_and_years_filter(sets):
    only = collect(sets.values(), parish="Хлестаковка", reviewed_only=False)
    assert [len(only.records_by_type[rt]) for rt in RECORD_TYPES] == [0, 0, 1]
    assert only.parishes == ("Хлестаковка",)
    assert collect(sets.values(), years={1900}, reviewed_only=False).parishes == ("Маниловка",)
    assert collect(sets.values(), years={1850}).taken == 0


def test_other_kinds_and_an_alias(sets):
    collected = collect(sets.values(), reviewed_only=False)
    # The divorces, the roll, the name list and the cards give no row; the deaths, bound twice, give theirs once.
    assert {rt: len(v) for rt, v in collected.records_by_type.items()} == {"births": 1, "marriages": 1, "deaths": 1}
    assert collected.parishes == ("Маниловка", "Хлестаковка")


def test_a_set_with_nothing_left_gives_no_year():
    held = birth_records(
        "ЦГА", "47", "9", "1", "Маниловка", "Церковь", 1900,
        *page("1", *birth_month(Month.JANUARY, birth(1, Gender.MALE, 3, 4, child=person("Иванъ"),
                                                     father=person("Петръ"))), reviewed=False))
    collected = collect([held])
    assert collected.records_by_type["births"] == []
    assert (collected.taken, collected.left_out, collected.parishes) == (0, 1, ())


def test_two_cases_of_one_year_both_in():
    first, second = _small_births("755", (1, 2)), _small_births("12", (1,))
    collected = collect([first, second])
    assert len(collected.records_by_type["births"]) == 2
    sheet = build_sheet("births", collected.records_by_type["births"])
    assert sheet is not None
    assert [row[0] for row in sheet.rows] == ["1", "2", "3"]              # сквозная, no gap
    assert [row[4] for row in sheet.rows] == ["12", "755", "755"]         # each дело together


def test_years_label_for():
    assert years_label_for([1805]) == "1805"
    assert years_label_for([1832, 1833, 1834]) == "1832-1834"
    assert years_label_for([1799, 1805]) == "1799, 1805"
