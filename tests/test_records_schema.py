"""Records v1: the JSON Schema (`verso.core.records.schema`)."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import records_fixture as fixture
from tests.codepaths import child_env
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.core.records.schema import SCHEMA_FILE, build_schema, load_schema, main


def _doc() -> dict[str, Any]:
    return encode_namespace(fixture.namespace(), village="Маниловка", file="1900/fixture.py",
                            sha256="0" * 64, ids=Ids())


def _first_record(d: dict[str, Any]) -> dict[str, Any]:
    return d["documents"][0]["pages"][0]["records"][0]


def test_the_committed_schema_is_the_ru_vocabularys():
    """The schema is the plugin's vocabulary's, and lies beside it (verso/ru/records/)."""
    committed = json.loads(files("verso.ru.records").joinpath(SCHEMA_FILE).read_text(encoding="utf-8"))
    assert committed == build_schema() == load_schema()


def test_the_schema_is_a_valid_2020_12_schema():
    Draft202012Validator.check_schema(load_schema())


def test_the_fixture_is_valid():
    Draft202012Validator(load_schema()).validate(_doc())


def test_an_index_is_valid():
    index = {"schema": "records-v1", "village": "Маниловка", "files": {"1900/a.py": "0" * 64},
             "skipped": {"1901/b.py": "ValueError: …"}, "inputs": {"code": "0" * 64}}
    Draft202012Validator(load_schema()).validate(index)


DAMAGES: list[Callable[[dict[str, Any]], object]] = [
    lambda d: _first_record(d)["derived"].update(novelty=1),
    lambda d: _first_record(d)["written"].update(gender="муж"),
    lambda d: _first_record(d).pop("id"),
    lambda d: _first_record(d).update(kind="baptism"),
    lambda d: _first_record(d).update(id="1900/fixture.py#0"),          # not r1
    lambda d: _first_record(d)["persons"][0].update(role=None),
    lambda d: d.update(schema="records-v9"),
]


@pytest.mark.parametrize("damage", DAMAGES)
def test_a_damaged_file_is_invalid(damage: Callable[[dict[str, Any]], object]):
    doc = copy.deepcopy(_doc())
    damage(doc)
    assert list(Draft202012Validator(load_schema()).iter_errors(doc))


def test_validate_names_each_bad_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    good, bad = _doc(), copy.deepcopy(_doc())
    _first_record(bad).pop("id")
    (tmp_path / "Маниловка" / "1900").mkdir(parents=True)
    (tmp_path / "Маниловка" / "1900" / "good.json").write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "Маниловка" / "1900" / "bad.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    assert main(["--validate", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "bad.json" in out and "good.json" not in out


def test_the_library_does_not_import_jsonschema():
    code = "import sys, verso.core.records.schema, verso.core.records.decode; print('jsonschema' in sys.modules)"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                          env=child_env())
    assert done.stdout.strip() == "False"


def test_schema_v1_has_no_cyrillic():
    """The schema carries no interface text: a field's and an enum's label is a catalog key."""
    from verso.core.records.schema import SCHEMA_FILE, load_schema

    assert SCHEMA_FILE == "records-v1.json"
    text = json.dumps(load_schema(), ensure_ascii=False)
    assert not any("\u0400" <= ch <= "\u04ff" for ch in text)


def test_every_dsl_attribute_has_one_key():
    """The ru table follows the three rules of records v1: an event's day, month and year
    are one object; a name's forms are one object; no abbreviation is left."""
    import re

    from verso.core.records.fields import vocabulary

    events = {"birth", "baptism", "marriage", "death", "burial", "divorce", "record", "arrival", "departure"}
    names = {"given", "patronymic", "surname", "maiden_surname"}
    for cls, keys in vocabulary().json_keys.items():
        assert len(set(keys.values())) == len(keys), cls
        for attr, key in keys.items():
            head, dot, _ = key.partition(".")
            if dot:
                assert head in events | names, (cls.__name__, attr, key)
            assert not re.search(r"(^|_)(num|orig|patr)($|_)|^[bkwd]_", key), (cls.__name__, attr, key)
