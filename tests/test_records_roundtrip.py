"""Records v1: the decoder and the round trip (`verso.core.records.decode`, `verso.core.records.graph`)."""
from __future__ import annotations

import copy
import json
from typing import Any

import pytest

import records_fixture as fixture
from verso.ru.domain.cause_of_death import CauseOfDeath
from verso.ru.domain.status import Status
from verso.ru.dsl.records.census import CensusRole
from verso.ru.dsl.records.external_sources import ExternalSourceKind, WwiiDocumentType
from verso.ru.gender import Gender
from verso.core.records.decode import FormatError, decode_file, decode_value
from verso.core.records.encode import encode_namespace
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.ru.relationship import Relationship


def _encode(ns: dict[str, Any]) -> dict[str, Any]:
    return encode_namespace(ns, village="Маниловка", file="1900/fixture.py", sha256="0" * 64, ids=Ids())


def _round_trip(ns: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    doc = _encode(ns)
    return doc, decode_file(json.loads(json.dumps(doc, ensure_ascii=False)))


def _objects(value: object, seen: set[int] | None = None) -> list[object]:
    seen = set() if seen is None else seen
    if id(value) in seen or isinstance(value, (str, int, float)) or value is None:
        return []
    seen.add(id(value))
    if isinstance(value, dict):
        return [o for v in value.values() for o in _objects(v, seen)]
    if isinstance(value, list):
        return [o for v in value for o in _objects(v, seen)]
    if not hasattr(value, "__dict__"):
        return []
    return [value, *(o for v in vars(value).values() for o in _objects(v, seen))]


def test_the_fixture_comes_back_as_the_same_graph():
    ns = fixture.namespace()
    _, back = _round_trip(ns)
    assert first_difference(ns, back) is None


def test_the_encoding_is_a_fixed_point():
    doc, back = _round_trip(fixture.namespace())
    assert _encode(back) == doc


def test_decoded_objects_keep_attribute_order():
    ns = fixture.namespace()
    _, back = _round_trip(ns)
    pairs = list(zip(_objects(ns), _objects(back), strict=True))
    assert pairs
    for a, b in pairs:
        assert list(vars(a)) == list(vars(b)), type(a).__name__


def test_look_alike_values_survive_the_round_trip():
    ns = fixture.namespace()
    _, back = _round_trip(ns)
    deaths, back_deaths = ns["hlestakovka_deaths_1913"].records, back["hlestakovka_deaths_1913"].records
    for a, b in zip(deaths, back_deaths, strict=True):
        assert type(b.age) is type(a.age) and b.age == a.age                    # 5, 0.5, "15.5", 5.0
        assert type(b.cause_of_death) is type(a.cause_of_death)                 # CauseOfDeath "", str
        assert b.cause_of_death == a.cause_of_death
    assert type(back_deaths[0].cause_of_death) is CauseOfDeath and back_deaths[0].cause_of_death == ""
    births, back_births = ns["births"].records, back["births"].records
    assert [type(r.record_num) for r in back_births] == [type(r.record_num) for r in births]   # 1 … "4а"
    assert back_births[0].comment == births[0].comment and "\r" in back_births[0].comment
    father = back_births[0].father
    assert type(father.status) is Status and father.status.gender is not None
    clergy_free_mother = back["confessions"].households[0].members[1].person
    assert type(clergy_free_mother.status) is Status


def test_a_decoded_status_leaves_the_gender_registry_alone():
    # A DSL file's own constant registers its words when the file runs; the JSON is
    # data, and reading it must not teach every later plain-string status a gender.
    before = dict(Status._gender_registry)
    status = decode_value({"text": "небывалое званіе", "gender": "female"}, "status")
    assert type(status) is Status and status == "небывалое званіе" and status.gender is Gender.FEMALE
    assert Status._gender_registry == before


def test_a_value_decodes_to_its_own_fields_enum():
    _, back = _round_trip(fixture.namespace())
    members = back["confessions"].households[0].members
    assert members[0].role is CensusRole.HEAD
    assert back["hlestakovka_deaths_1913"].records[2].relatives[0].relationship is Relationship.FATHER
    card = back["cards"].records[1]
    assert card.document_type is WwiiDocumentType.POW_CARD and card.kind is ExternalSourceKind.WWII


def test_an_alias_decodes_to_one_object_under_both_names():
    _, back = _round_trip(fixture.namespace())
    assert back["zamanilovka_deaths_1913"] is back["hlestakovka_deaths_1913"]


def test_on_geni_is_present_only_where_it_was():
    ns = fixture.namespace()
    _, back = _round_trip(ns)
    assert [hasattr(r, "on_geni") for r in back["births"].records] == \
           [hasattr(r, "on_geni") for r in ns["births"].records] == [False, False, True, False, False]


def test_first_difference_names_the_path():
    ns = fixture.namespace()
    other = copy.deepcopy(ns)
    other["births"].records[0].child.name_orig = "Петръ"
    assert first_difference(ns, other) == "births.records[0].child.name_orig: 'Иванъ' ≠ 'Петръ'"


def test_first_difference_sees_a_split_alias():
    ns = fixture.namespace()
    other = dict(ns)
    other["zamanilovka_deaths_1913"] = copy.deepcopy(ns["hlestakovka_deaths_1913"])
    assert first_difference(ns, other) is not None


def test_a_page_of_another_type_is_refused():
    doc = json.loads(json.dumps(_encode(fixture.namespace()), ensure_ascii=False))
    doc["documents"][0]["pages"][0]["page"] = 1
    with pytest.raises(FormatError, match=r"births\.pages\[0\]\.page: int"):
        decode_file(doc)


def test_another_schema_version_is_refused():
    doc = _encode(fixture.namespace())
    doc["schema"] = "records-v9"
    with pytest.raises(FormatError, match="records-v1"):
        decode_file(doc)
