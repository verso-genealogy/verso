"""`verso export-csv` writes each DSL file's CSVs — what its `__main__` block wrote."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import village_fixture
from verso.ru import corpus_data
from verso.core.corpus_data import CorpusDataError
from verso.core.pipeline import records
from verso.core.pipeline.records import export_village as export_records
from verso.core.pipeline.load import load_module, record_namespace
from verso.ru.cli.export_csv import ExportError, export_file, export_village, main
from verso.ru.exporters.csv import CensusRecordsCsvExporter
from verso.ru.exporters.csv_familio import BirthRecordsCsvFamilioExporter
from verso.ru.exporters.table import exporter_for


BIRTHS = "1900/manilovka_births_1900.py"


def _csvs(directory: Path) -> dict[str, bytes]:
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(directory.rglob("*.csv"))}


def _village(tmp_path: Path) -> Path:
    return village_fixture.root(tmp_path) / "Маниловка"


def test_the_table_names_the_exporter_of_each_record_set(tmp_path: Path):
    module = load_module(_village(tmp_path) / BIRTHS)
    [births] = record_namespace(module).values()
    assert isinstance(exporter_for(births), BirthRecordsCsvFamilioExporter)
    roll = load_module(_village(tmp_path / "b") / "1858" / "manilovka_census_1858.py")
    assert isinstance(exporter_for(next(iter(record_namespace(roll).values()))), CensusRecordsCsvExporter)
    assert exporter_for(object()) is None


def test_a_file_with_nothing_to_export_writes_nothing(tmp_path: Path):
    village = tmp_path / "V"
    (village / "1917").mkdir(parents=True)
    path = village / "1917" / "v_name_lists_1917.py"
    path.write_text(
        "from verso.ru.dsl import listed_person, name_list_records, person\n\n"
        'v_list_1917 = name_list_records("ГАРО", "1", "2", "3", "V", 1917,\n'
        '                                listed_person(1, person("Іоаннъ")), document_type="список")\n'
        "\nfrom verso.ru.dsl import external_source_records\n\n"
        'v_cards = external_source_records("V")\n', encoding="utf-8")
    assert export_file(path, tmp_path / "out") == []
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())


def test_the_csv_lands_beside_its_file_by_default(tmp_path: Path):
    village = _village(tmp_path)
    for csv in village.rglob("*.csv"):
        csv.unlink()
    written = export_village(village)
    assert written and all(p.parent.parent == village for p in written)
    assert (village / "1900" / "Хлестаковка_1900_births_familio.csv") in written


def test_a_skipped_file_writes_no_csv(tmp_path: Path):
    village = _village(tmp_path)
    (village / "village.toml").write_text(f'schema = 1\n[csv]\nskip = ["{BIRTHS}"]\n', encoding="utf-8")
    assert corpus_data.village(village).csv_skip == (BIRTHS,)
    written = export_village(village, tmp_path / "out")
    assert written and not (tmp_path / "out" / "1900" / "Хлестаковка_1900_births_familio.csv").exists()
    assert (tmp_path / "out" / "1900" / "Хлестаковка_1900_deaths_familio.csv").exists()


def test_an_unknown_skip_is_refused(tmp_path: Path):
    village = _village(tmp_path)
    toml = village / "village.toml"
    toml.write_text('schema = 1\n[csv]\nskip = ["1900/nope.py"]\n', encoding="utf-8")
    with pytest.raises(CorpusDataError) as refused:
        corpus_data.village(village)
    assert str(refused.value) == f"{toml}: [csv] skip: нет файла 1900/nope.py"


def test_two_sets_writing_one_csv_are_refused(tmp_path: Path):
    path = _village(tmp_path) / BIRTHS
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    [assign] = [n for n in tree.body if isinstance(n, ast.Assign)]
    second = (ast.get_source_segment(text, assign) or "").replace("manilovka_births_1900 =", "manilovka_births_1900_b =", 1)
    path.write_text(text + "\n" + second + "\n", encoding="utf-8")
    with pytest.raises(ExportError) as refused:
        export_file(path, tmp_path / "out")
    assert str(refused.value) == f"{path}: два набора пишут Хлестаковка_1900_births_familio.csv"
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*.csv"))


def test_an_alias_of_one_set_is_written_once(tmp_path: Path):
    path = _village(tmp_path) / BIRTHS
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "\nother_name_1900 = manilovka_births_1900\n", encoding="utf-8")
    assert [p.name for p in export_file(path, tmp_path / "out")] == ["Хлестаковка_1900_births_familio.csv"]


def test_export_csv_reads_the_records_export(tmp_path: Path):
    a, b = _village(tmp_path / "a"), _village(tmp_path / "b")
    export_records(b, tmp_path / "rec")
    from_dsl = export_village(a, tmp_path / "out-a")
    with records.use(tmp_path / "rec"):
        from_json = export_village(b, tmp_path / "out-b")
    assert len(from_dsl) == len(from_json) >= 4
    assert _csvs(tmp_path / "out-a") == _csvs(tmp_path / "out-b")


def test_the_command_says_what_it_wrote(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    village = _village(tmp_path)
    (village / "village.toml").write_text(f'schema = 1\n[csv]\nskip = ["{BIRTHS}"]\n', encoding="utf-8")
    assert main(["--village", str(village), "--year", "1900", "--out", str(tmp_path / "out")]) == 0
    *generated, summary = capsys.readouterr().out.strip().splitlines()
    assert summary == f"{village}: CSV 2, файлов 2, пропущено 1"
    assert generated == [f"Generated {tmp_path / 'out' / '1900' / name}" for name in
                         ("Хлестаковка_1900_deaths_familio.csv", "Хлестаковка_1900_marriages_familio.csv")]
