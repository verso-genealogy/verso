"""Parents' ages in a birth: `birth(father_age=, mother_age=, source_age_error=)` — the DSL, Records JSON, the interface's schema."""
from __future__ import annotations

import json
from calendar import Month
from typing import Any

import records_fixture as fixture
from records_fixture import aged
from verso.core.records.encode import encode_namespace
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import replay_file
from verso.core.records import ui as ui_schema
from verso.ru.domain import Gender, person
from verso.ru.dsl.records.births import birth, christening


def _encode(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="Маниловка", file="1900/f.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _without_derived(node: Any) -> Any:
    if isinstance(node, list):
        return [_without_derived(x) for x in node]
    if not isinstance(node, dict):
        return node
    return {k: _without_derived(v) for k, v in node.items() if k != "derived"}


def test_a_birth_keeps_the_parents_ages_as_given():
    b = birth(1, Gender.MALE, 3, None, father=person("Петръ"), mother=person("Марья"),
              father_age=31, mother_age="30?", source_age_error="так в подлиннике")
    assert (b.father_age, b.mother_age, b.source_age_error) == (31, "30?", "так в подлиннике")
    plain = birth(1, Gender.MALE, 3, None)
    assert (plain.father_age, plain.mother_age, plain.source_age_error) == (None, None, None)


def test_a_christening_takes_no_parents_ages():
    c = christening(1, Gender.MALE, 3, Month.JANUARY, age=11)
    assert (c.father_age, c.mother_age, c.source_age_error) == (None, None, None)


def test_the_ages_are_in_records_json_and_replay():
    ns = aged()
    doc = _encode(ns)
    text = json.dumps(doc, ensure_ascii=False)
    assert '"father_age": 31' in text and '"mother_age": "30?"' in text
    assert first_difference(ns, replay_file(_without_derived(doc), context=False)) is None


def test_a_birth_without_the_fields_encodes_none_of_their_keys():
    doc = _encode(fixture.namespace())
    births = next(d for d in doc["documents"] if d["kind"] == "births")
    keys = {k for p in births["pages"] for r in p["records"] for side in ("written", "derived")
            for k in r.get(side, {})}
    assert keys and not keys & {"father_age", "mother_age", "source_age_error"}


def test_an_empty_age_error_is_no_note():
    assert birth(1, Gender.MALE, source_age_error="").source_age_error is None


def _kind(code: str) -> dict[str, Any]:
    return ui_schema.load_ui()["kinds"][code]


def test_the_ages_are_fields_of_the_parents_slots():
    kind = _kind("birth")
    fields = {f["path"]: f for f in kind["fields"]}
    assert fields["father_age"]["label"] == "ui.field.father_age"
    assert fields["mother_age"]["label"] == "ui.field.mother_age"
    assert fields["source_age_error"]["label"] == "ui.field.source_age_error_birth"
    assert fields["source_age_error"]["checks"] is True
    slots = {s["role"]: s for s in kind["slots"]}
    assert slots["father"]["row"] == ["father_age"] and slots["mother"]["row"] == ["mother_age"]
    assert not any("offer" in fields[p] for p in ("father_age", "mother_age", "source_age_error"))
    groom = next(sl for sl in _kind("marriage")["slots"] if sl["role"] == "groom")
    assert "groom_age" in groom["row"] and "offer" not in groom   # the same way: a row field of the slot


def test_a_not_recorded_mark_prints_nothing():
    from verso.ru.ages import parent_age_prose
    assert parent_age_prose("?") is None and parent_age_prose("-") is None and parent_age_prose(None) is None
    assert parent_age_prose(26) == "26 лет"
