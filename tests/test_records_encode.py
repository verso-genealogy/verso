"""Records v1: the encoder (`verso.core.records.encode`)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import records_fixture as fixture
from tests.codepaths import child_env, pythonpath
from verso.ru.domain import Gender, person
from verso.ru.dsl.records.births import birth, birth_records
from verso.core.records.encode import FormatError, SharedEntity, encode_namespace
from verso.core.records.ids import Ids, persona_id

GOLDEN = Path(__file__).parent / "golden" / "records" / "fixture.json"


def _encode(ns: dict[str, object]) -> dict[str, Any]:
    return encode_namespace(ns, village="Маниловка", file="1900/fixture.py", sha256="0" * 64, ids=Ids())


def _records(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for d in doc["documents"] if "pages" in d for p in d["pages"] for r in p["records"]]


def test_the_fixture_encodes_as_the_golden_file():
    text = json.dumps(_encode(fixture.namespace()), ensure_ascii=False, indent=1) + "\n"
    if os.environ.get("RECORDS_GOLDEN") == "update":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8")
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_a_set_of_cards_takes_the_year_of_its_file():
    doc = _encode(fixture.namespace())
    assert [d["id"] for d in doc["documents"] if d.get("kind") == "external_sources"] == ["r1:Маниловка/card/1900/cards"]


def test_every_record_and_persona_carries_its_id_and_label():
    records = _records(_encode(fixture.namespace()))
    assert records[0]["id"] == "r1:Маниловка/47-9-755/1900/birth/m1" and records[0]["label"] == "Иванъ"
    assert all(p["id"] == persona_id(r["id"], p["role"], p.get("slot"))
               for r in records for p in r["persons"])
    ids = [r["id"] for r in records] + [p["id"] for r in records for p in r["persons"]]
    assert len(set(ids)) == len(ids)


def test_pages_are_runs_in_record_order():
    births = _encode(fixture.namespace())["documents"][0]
    assert [p["page"] for p in births["pages"]] == ["1", "1об", "1"]


def test_review_states():
    doc = _encode(fixture.namespace())
    births = [r for p in doc["documents"][0]["pages"] for r in p["records"]]
    assert [r["review"] for r in births] == ["reviewed", "held", "on_geni", "reviewed", "reviewed"]
    divorce = doc["documents"][3]["pages"][0]["records"][0]
    assert divorce["review"] == "reviewed"


def test_an_alias_is_written_once_and_named_twice():
    docs = _encode(fixture.namespace())["documents"]
    assert docs[-1] == {"variable": "zamanilovka_deaths_1913", "alias_of": "hlestakovka_deaths_1913"}


def test_a_shared_person_is_refused():
    p = person("Иванъ")
    b = birth(1, Gender.MALE, child=p, god_parent1=p)
    with pytest.raises(SharedEntity, match="один объект"):
        _encode({"x": birth_records("А", "1", "2", "3", "Маниловка", "Ц", 1900, b)})


def test_an_unknown_attribute_is_refused():
    rs = birth_records("А", "1", "2", "3", "Маниловка", "Ц", 1900, birth(1, Gender.MALE, child=person("Иванъ")))
    rs.records[0].novelty = 1  # type: ignore[attr-defined]
    with pytest.raises(FormatError, match=r"Birth\.novelty"):
        _encode({"x": rs})


def test_a_value_of_another_type_is_refused():
    rs = birth_records("А", "1", "2", "3", "Маниловка", "Ц", 1900, birth(1, Gender.MALE, child=person("Иванъ")))
    vars(rs.records[0])["b_day"] = "3"
    with pytest.raises(FormatError, match="b_day"):
        _encode({"x": rs})


def test_a_page_of_another_type_is_refused():
    # A page run's лист is a record's `page`, which the encoder writes at the run, not
    # in the record's node: the type check must reach it there.
    rs = birth_records("А", "1", "2", "3", "Маниловка", "Ц", 1900, birth(1, Gender.MALE, child=person("Иванъ")))
    vars(rs.records[0])["page"] = 5
    with pytest.raises(FormatError, match=r"x\.records\[0\]\.page: int"):
        _encode({"x": rs})


def test_the_output_does_not_depend_on_hash_seed():
    code = ("import json, records_fixture as f; from verso.core.records.encode import encode_namespace; "
            "from verso.core.records.ids import Ids; print(json.dumps(encode_namespace(f.namespace(), "
            "village='М', file='f.py', sha256='0', ids=Ids()), ensure_ascii=False))")
    here = Path(__file__).parent
    env = child_env(PYTHONPATH=os.pathsep.join([pythonpath(), str(here)]))
    outs = {subprocess.run([sys.executable, "-c", code], env={**env, "PYTHONHASHSEED": seed},
                           capture_output=True, text=True, check=True).stdout for seed in ("0", "1")}
    assert len(outs) == 1


def test_v1_writes_events_and_names_as_groups():
    """Records v1: a day and a month of one event are one object, a name its forms."""
    records = _records(_encode(fixture.namespace()))
    born = next(r for r in records if r["kind"] == "birth")
    assert born["written"]["number"] == 1 and "record_num" not in born["written"]
    # the day the call wrote and the month its section did, in one group (records v1.x)
    assert born["written"]["birth"] == {"day": 3, "month": "january"}
    assert born["written"]["baptism"] == {"day": 4, "month": "january"}
    assert {"birth.month", "baptism.month"} <= set(born["written"]["context"])
    assert "birth" not in born["derived"]
    father = next(p for p in born["persons"] if p["role"] == "father")
    assert father["written"]["given"] == {"original": "Петръ"}
    assert father["written"]["surname"] == {"original": "Сидоровъ"}
    assert father["derived"]["patronymic"] == {"old": "Иванов", "modern": "Иванович"}


def test_death_b_day_is_the_burial():
    died = next(r for r in _records(_encode(fixture.namespace())) if r["kind"] == "death")
    assert died["written"]["death"] == {"day": 2, "month": "march"}
    assert died["written"]["burial"] == {"day": 4, "month": "march"}
