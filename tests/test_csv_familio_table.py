"""A familio CSV as a table in memory (`table()`), and the file `export()` writes from it.

The golden files are what `export()` wrote of `tests/records_fixture.py` before the table existed
(verso 0.1.44): the refactor moves no byte of a corpus's CSVs.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tests import records_fixture
from verso.ru.exporters.base import CsvTable, write_table
from verso.ru.exporters.csv_familio import FamilioCsvExporter, exporter_of, merge_tables, tables

GOLDEN = Path(__file__).parent / "golden" / "csv_familio"
# The fixture's variable of each kind → the golden file, and the name `export()` gives the CSV.
KINDS = {
    "births": ("births.csv", "Маниловка_1900_births_familio.csv"),
    "marriages": ("marriages.csv", "Маниловка_1900_marriages_familio.csv"),
    "hlestakovka_deaths_1913": ("deaths.csv", "Хлестаковка_1913_deaths_familio.csv"),
    "divorces": ("divorces.csv", "Заманиловка_1923_divorces_familio.csv"),
}


@pytest.fixture(scope="module")
def sets() -> dict[str, object]:
    return records_fixture.namespace()


def exporter_for(record_set: object) -> FamilioCsvExporter:
    exporter = exporter_of(record_set)
    assert exporter is not None
    return exporter


def _golden_rows(golden: str) -> list[list[str]]:
    with (GOLDEN / golden).open(encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


@pytest.mark.parametrize("variable", list(KINDS))
def test_export_writes_the_same_bytes(variable, sets, tmp_path, capsys):
    golden, name = KINDS[variable]
    written = Path(exporter_for(sets[variable]).export(sets[variable], target_dir=tmp_path))
    assert written.name == name
    assert written.read_bytes() == (GOLDEN / golden).read_bytes()
    assert capsys.readouterr().out == f"Generated {written}\n"


@pytest.mark.parametrize("variable", list(KINDS))
def test_text_rows_are_the_csv_read_back(variable, sets):
    golden, name = KINDS[variable]
    table = exporter_for(sets[variable]).table(sets[variable])
    read = _golden_rows(golden)
    assert table.name == name
    assert table.headers == read[0]
    assert table.text_rows() == read[1:]


@pytest.mark.parametrize("variable", list(KINDS))
def test_table_writes_no_file(variable, sets, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exporter_for(sets[variable]).table(sets[variable])
    assert list(tmp_path.iterdir()) == []


def test_records_subset_keeps_order(sets):
    births = sets["births"]
    exporter = exporter_for(births)
    every = exporter.table(births).text_rows()
    assert len(every) >= 3
    chosen = exporter.table(births, records=[births.records[2], births.records[0]])
    assert chosen.text_rows() == [every[2], every[0]]
    assert chosen.name == exporter.table(births).name


def test_the_table_of_exporters_gives_the_same_exporter(sets):
    from verso.ru.exporters import table as exporters_table

    for variable in KINDS:
        assert type(exporters_table.exporter_for(sets[variable])) is type(exporter_of(sets[variable]))
    assert exporter_of(sets["confessions"]) is None


def test_text_rows_write_none_and_floats_as_csv_does():
    table = CsvTable("t.csv", ["a", "b", "c", "d"], [[None, 5, 5.0, "пять"]])
    assert table.text_rows() == [["", "5", "5.0", "пять"]]


def test_write_table_is_the_file_export_writes(sets, tmp_path):
    births = sets["births"]
    path = Path(write_table(exporter_for(births).table(births), tmp_path))
    assert path == tmp_path / "Маниловка_1900_births_familio.csv"
    assert path.read_bytes() == (GOLDEN / "births.csv").read_bytes()


def test_tables_skip_other_kinds_and_take_an_alias_once(sets):
    made = tables(sets.values())
    # The roll, the name list and the cards write no familio CSV; the deaths are bound twice (an alias).
    assert [t.name for t in made] == [name for _, name in KINDS.values()]


def test_tables_filter_parish_and_years(sets):
    assert [t.name for t in tables(sets.values(), parish="Маниловка")] == [
        "Маниловка_1900_births_familio.csv", "Маниловка_1900_marriages_familio.csv"]
    assert [t.name for t in tables(sets.values(), years={1913})] == ["Хлестаковка_1913_deaths_familio.csv"]


def test_tables_reviewed_only_leaves_the_unreviewed_out(sets):
    births = sets["births"]
    unreviewed = [r for r in births.records if getattr(r, "reviewed", None) is False]
    assert unreviewed, "the fixture holds an unreviewed birth"
    every = tables([births])[0]
    proofread = tables([births], reviewed_only=True)[0]
    assert len(every.rows) == len(births.records)
    assert len(proofread.rows) == len(births.records) - len(unreviewed)


def test_tables_reviewed_only_leaves_an_unreviewed_divorce_out(sets):
    from verso.ru.dsl.records.divorces import divorce, divorce_records
    from verso.ru.domain import page, person
    book = sets["divorces"]
    every = tables([book])[0]
    held = divorce_records(book.archive, book.fund, book.inventory, book.case, book.village, book.church,
                           book.year, *page("2", divorce(2, 5, husband=person("Петръ"), wife=person("Анна")),
                                            reviewed=False))
    assert tables([book], reviewed_only=True)[0].text_rows() == every.text_rows(), "nothing held: every row"
    assert len(tables([held])[0].rows) == 1, "the CSV of a year writes every record"
    assert tables([held], reviewed_only=True)[0].rows == []


def test_merge_concatenates_same_name():
    one = CsvTable("a.csv", ["x"], [[1], [2]])
    two = CsvTable("a.csv", ["x"], [[3]])
    other = CsvTable("b.csv", ["x"], [[9]])
    merged = merge_tables([one, other, two])
    assert [(t.name, t.rows) for t in merged] == [("a.csv", [[1], [2], [3]]), ("b.csv", [[9]])]


def test_merge_refuses_other_headers():
    with pytest.raises(ValueError, match=r"a\.csv"):
        merge_tables([CsvTable("a.csv", ["x"], []), CsvTable("a.csv", ["y"], [])])
