"""export-records: a village's record sets as records-v1 JSON (`verso.core.pipeline.records`)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import village_fixture
from verso.ru.cli import export_records
from verso.core.pipeline import records
from verso.core.pipeline.load import discover_records
from verso.core.pipeline.records import ExportError, export_village

EXTRA = '''\
from calendar import Month

from verso.ru.dsl import person
from verso.ru.dsl import divorce, divorce_records
from verso.ru.dsl import external_source_records, wwi_record
from verso.ru.dsl import listed_person, name_list_records

manilovka_divorces_1901 = divorce_records(
    "ГАПО", "1605", "59", "59", "Маниловка", "", 1901,
    divorce(1, 3, Month.JULY, husband=person("Иванъ"), wife=person("Анна"), husband_age=24, wife_age=29))
manilovka_name_lists_1901 = name_list_records(
    "ГАТО", "1", "1", "1", "Маниловка", 1901, listed_person(1, person("Петръ", "Ивановъ")),
    document_type="Список")
manilovka_external_sources_1901 = external_source_records(
    "Маниловка", wwi_record(person("Василій"), source_url="https://gwar.mil.ru/heroes/chelovek_plen1/"))
'''
BROKEN = 'from verso.ru.dsl import person\nx = person("Хщъ")\n'


@pytest.fixture
def village(tmp_path: Path) -> Path:
    root = village_fixture.root(tmp_path)
    manilovka = root / "Маниловка"
    (manilovka / "1901").mkdir()
    (manilovka / "1901" / "manilovka_extra_1901.py").write_text(EXTRA, encoding="utf-8")
    (manilovka / "1901" / "broken.py").write_text(BROKEN, encoding="utf-8")
    return manilovka


def test_export_writes_one_json_per_dsl_file_and_an_index(village: Path, tmp_path: Path):
    out = tmp_path / "rec"
    export_village(village, out)
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*.json")) == [
        "Маниловка/1858/manilovka_census_1858.json", "Маниловка/1899/manilovka_marriages_1899.json",
        "Маниловка/1900/manilovka_births_1900.json", "Маниловка/1900/manilovka_deaths_1900.json",
        "Маниловка/1900/manilovka_marriages_1900.json", "Маниловка/1901/manilovka_extra_1901.json",
        "Маниловка/index.json"]
    index = json.loads((out / "Маниловка" / "index.json").read_text(encoding="utf-8"))
    births = village / "1900" / "manilovka_births_1900.py"
    assert index["files"]["1900/manilovka_births_1900.py"] == hashlib.sha256(births.read_bytes()).hexdigest()
    assert "1901/broken.py" in index["files"]
    extra = json.loads((out / "Маниловка" / "1901" / "manilovka_extra_1901.json").read_text(encoding="utf-8"))
    assert [d["kind"] for d in extra["documents"]] == ["divorces", "name_list", "external_sources"]


def test_a_file_that_does_not_import_is_skipped_and_named(village: Path, tmp_path: Path):
    exported = export_village(village, tmp_path / "rec")
    assert list(exported.skipped) == ["1901/broken.py"]
    assert exported.skipped["1901/broken.py"].startswith("ValueError: Unrecognized first name")
    assert export_records.main(["--village", str(village), "--out", str(tmp_path / "rec2"), "--strict"]) == 1
    assert export_records.main(["--village", str(village), "--out", str(tmp_path / "rec3")]) == 0


def test_export_is_byte_stable(village: Path, tmp_path: Path):
    export_village(village, tmp_path / "a")
    export_village(village, tmp_path / "b")
    a = {p.relative_to(tmp_path / "a"): p.read_bytes() for p in (tmp_path / "a").rglob("*.json")}
    b = {p.relative_to(tmp_path / "b"): p.read_bytes() for p in (tmp_path / "b").rglob("*.json")}
    assert a == b


def test_a_second_export_replaces_the_first(village: Path, tmp_path: Path):
    out = tmp_path / "rec"
    export_village(village, out)
    (village / "1901" / "manilovka_extra_1901.py").unlink()
    export_village(village, out)
    assert not (out / "Маниловка" / "1901" / "manilovka_extra_1901.json").exists()


def test_a_foreign_directory_is_not_overwritten(village: Path, tmp_path: Path):
    out = tmp_path / "rec"
    (out / "Маниловка").mkdir(parents=True)
    (out / "Маниловка" / "notes.txt").write_text("мои заметки", encoding="utf-8")
    with pytest.raises(ExportError, match="не выгрузка записей"):
        export_village(village, out)
    assert (out / "Маниловка" / "notes.txt").exists()


def test_an_export_into_the_root_it_reads_from_is_refused(village: Path, tmp_path: Path):
    # VERSO_RECORDS on the export's own --out: the export would read the JSON it is about
    # to replace — it used to remove it first, then stop on the missing export.
    out = tmp_path / "rec"
    export_village(village, out)
    with records.use(tmp_path / "." / "rec"), pytest.raises(ExportError, match="VERSO_RECORDS"):
        export_village(village, out)
    assert (out / "Маниловка" / "index.json").is_file()


def test_discover_records_keeps_its_order(village: Path):
    assert [(p.name, name) for p, name, _ in discover_records(str(village))] == [
        ("manilovka_births_1900.py", "manilovka_births_1900"),
        ("manilovka_marriages_1899.py", "manilovka_marriages_1899"),
        ("manilovka_marriages_1900.py", "manilovka_marriages_1900"),
        ("manilovka_deaths_1900.py", "manilovka_deaths_1900"),
        ("manilovka_census_1858.py", "census"),
        ("manilovka_extra_1901.py", "manilovka_external_sources_1901"),
        ("manilovka_extra_1901.py", "manilovka_name_lists_1901")]


def test_the_cli_says_what_it_wrote(village: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert export_records.main(["--village", str(village), "--out", str(tmp_path / "rec")]) == 0
    assert "6 файлов" in capsys.readouterr().out


NOTED = '''\
from verso.ru.dsl import Gender, Month, birth, birth_month, birth_records, person

# An invented book: its notes are what the export binds.
manilovka_births_1902 = birth_records(
    "ГАРО", "1", "2", "3", "Маниловка", "Вознесенская", 1902,
    *birth_month(Month.MAY,
                 birth(1, Gender.MALE, 2, 3,
                       child=person("Иванъ"),
                       father=person("Петръ", "Ивановъ"),
                       mother=person("Анна", "Петрова")),  # в девичестве — неизвестно
                 # Второй **ребёнок** той же семьи.
                 birth(2, Gender.FEMALE, 4, 5,
                       child=person("Марія"),
                       father=person("Петръ", "Ивановъ"),
                       mother=person("Анна", "Петрова")),
                 ),
)
'''


def test_the_export_binds_the_files_notes_to_its_nodes(village: Path, tmp_path: Path):
    (village / "1902").mkdir()
    dsl = village / "1902" / "manilovka_births_1902.py"
    dsl.write_text(NOTED, encoding="utf-8")
    out = tmp_path / "rec"
    exported = export_village(village, out)
    doc = json.loads((out / "Маниловка" / "1902" / "manilovka_births_1902.json").read_text(encoding="utf-8"))
    assert doc["note"] == [{"text": "An invented book: its notes are what the export binds.",
                            "anchor": {"to": "file"}}]
    first, second = (r for run in doc["documents"][0]["pages"] for r in run["records"])
    assert first["note"] == [{"text": "в девичестве — неизвестно",
                              "anchor": {"to": "field", "record": 0, "arg": "mother"}}]
    assert second["note"] == [{"text": "Второй **ребёнок** той же семьи.", "anchor": {"to": "record", "record": 1}}]
    assert exported.unbound == {} and exported.manual_notes == 0
    # A note is the DSL file's text: an export read after it changes is stale.
    with records.use(out):
        records.read_namespace(dsl)
        dsl.write_text(NOTED.replace("Второй", "Вторая"), encoding="utf-8")
        with pytest.raises(records.StaleRecords):
            records.read_namespace(dsl)


ARGS = '''\
from verso.ru.dsl import (
    Gender, Month, birth, birth_month, birth_records, marriage, marriage_month, marriage_records, person)

manilovka_births_1903 = birth_records(
    "ГАРО", "1", "2", "3", "Маниловка", "Вознесенская", 1903,
    *birth_month(Month.JUNE,
                 birth(1, Gender.MALE,
                       2,  # день рождения
                       3, child=person("Иванъ"),
                       father=person("Петръ", "Ивановъ"),
                       god_parent1=person("Петръ", "Ивановъ"),  # восприемник из соседней деревни
                       god_parent2=person("Анна", "Петрова"),
                       ),
                 ),
)
manilovka_marriages_1903 = marriage_records(
    "ГАРО", "1", "2", "4", "Маниловка", "Вознесенская", 1903,
    *marriage_month(Month.JUNE,
                    marriage(1, 7, groom=person("Петръ", "Ивановъ"),
                             bride=person("Анна", "Петрова"),
                             groom_marriage_num=2,  # второй брак жениха
                             # свидетель — родня
                             witness1=person("Петръ", "Ивановъ"))),
)
'''


def test_an_argument_note_names_what_the_json_names(village: Path, tmp_path: Path):
    (village / "1903").mkdir()
    (village / "1903" / "manilovka_args_1903.py").write_text(
        ARGS, encoding="utf-8")
    out = tmp_path / "rec"
    export_village(village, out)
    doc = json.loads((out / "Маниловка" / "1903" / "manilovka_args_1903.json").read_text(encoding="utf-8"))
    by_text: dict[str, dict[str, object]] = {}
    checked = 0
    for document in doc["documents"]:
        for run in document["pages"]:
            for record in run["records"]:
                keys = _written_keys(record["written"])
                slots = {p["id"].rpartition("/")[2] for p in record["persons"]}
                for note in record.get("note", []):
                    by_text[note["text"]] = note["anchor"]
                    arg = note["anchor"].get("arg")
                    if note["anchor"]["to"] in ("argument", "field"):
                        assert arg in keys | slots, (note, keys, slots)
                        checked += 1
    assert checked == 4
    assert by_text["день рождения"]["arg"] == "birth.day"
    assert by_text["восприемник из соседней деревни"]["arg"] == "godparent1"
    assert by_text["второй брак жениха"]["arg"] in _written_keys(
        doc["documents"][1]["pages"][0]["records"][0]["written"])
    assert by_text["свидетель — родня"]["arg"] == "witness1"


def _written_keys(written: dict[str, object]) -> set[str]:
    return {f"{k}.{sub}" if isinstance(v, dict) else k
            for k, v in written.items() for sub in (v if isinstance(v, dict) else [None])}
