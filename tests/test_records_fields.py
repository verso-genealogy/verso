"""The field table of records v1 (`verso.core.records.fields`)."""
from __future__ import annotations

import inspect
from calendar import Month
from collections.abc import Iterator

import pytest

from verso.ru.domain import Gender, person
from verso.ru.domain.side import Side
from verso.ru.dsl.records.births import Birth, birth
from verso.ru.dsl.records.census import CensusRole, member
from verso.ru.dsl.records.external_sources import ExternalSourceKind, WwiDocumentType, WwiiDocumentType
from verso.core.records.fields import (
    PERSON, ListOf, attr_of, carries_persons, code, enum_code, member_of, param_of_key, param_spec, role_of,
    written_key)
from verso.ru.records.vocabulary import SPECS, VOCABULARY
from verso.ru.relationship import Relationship, relative

CONDITIONAL = ("_written", "on_geni")
ENUMS = (Gender, Month, Relationship, CensusRole, Side, ExternalSourceKind, WwiDocumentType,
         WwiiDocumentType)


def test_codes_are_member_names_in_lower_case_and_unique():
    for enum in ENUMS:
        codes = [code(m) for m in enum]
        assert codes == [m.name.lower() for m in enum]
        assert len(set(codes)) == len(codes)
    assert enum_code(WwiiDocumentType) == "wwii_document_type"
    assert member_of(Month, "may") is Month.MAY
    assert member_of((WwiDocumentType, WwiiDocumentType),
                     "wwii_document_type.pow_card") is WwiiDocumentType.POW_CARD


def test_an_unknown_code_is_refused():
    with pytest.raises(ValueError, match="gender"):
        member_of(Gender, "муж")


def test_roles_round_trip():
    assert role_of("god_parent2") == ("godparent", 2)
    assert role_of("child") == ("child", None)
    assert role_of("relatives", item=True) == ("relative", None)
    assert role_of("members", item=True) == ("member", None)
    assert attr_of(SPECS[Birth], "godparent", 2) == "god_parent2"
    assert attr_of(SPECS[Birth], "child", None) == "child"


def test_every_factory_parameter_is_described():
    for spec in SPECS.values():
        for fn in spec.factories:
            for name, p in inspect.signature(fn).parameters.items():
                if p.kind is p.VAR_POSITIONAL or carries_persons(spec.cls, name):
                    continue
                param_spec(spec.cls, name)      # KeyError: the parameter is not described


def test_a_person_slot_carries_persons():
    assert carries_persons(Birth, "child") and carries_persons(Birth, "relatives")
    assert not carries_persons(Birth, "b_day")
    assert SPECS[Birth].fields[[f.name for f in SPECS[Birth].fields].index("child")].type == PERSON
    assert isinstance(SPECS[Birth].fields[-1].type, ListOf)


def _built() -> Iterator[object]:
    gp = person("Петръ", "Ивановъ")
    b = birth(1, Gender.MALE, 3, 4, child=person("Иванъ"), father=person("Петръ"), god_parent1=gp,
              relatives=[relative(person("Иванъ"), Relationship.FATHER, "восприемника №1")])
    yield b
    yield b.child
    yield b.relatives[0]
    yield member(1, person("Иванъ"), CensusRole.HEAD, age=59)


def test_fields_follow_the_vars_order_of_built_objects():
    for obj in _built():
        names = [k for k in vars(obj) if k not in CONDITIONAL]
        assert names == [f.name for f in SPECS[type(obj)].fields], type(obj).__name__


def test_a_kinds_records_attribute_is_its_specs():
    """A record set's kind (verso.ru.dsl.kinds) and its vocabulary name one list of records."""
    from verso.ru.dsl.kinds import KINDS
    for kind in KINDS:
        assert VOCABULARY.specs[kind.set_type].records_attr == kind.records, kind.code


def _param_of_key_by_scan(cls: type, key: str) -> str:
    """`param_of_key` as it was written before its inverse was kept (0.1.29): the renamed keys inverted and the
    factory parameters scanned on every call."""
    renamed = {k: attr for attr, k in VOCABULARY.json_names.get(cls, {}).items()}
    if key not in renamed:
        return key
    attr = renamed[key]
    for param, target in VOCABULARY.param_to_attr.get(cls, {}).items():
        if target == attr:
            return param
    return attr


def test_the_kept_inverse_answers_as_the_scan_did():
    """`Vocabulary.params_of_keys` is the scan's answer for every key a class can be written under — each field's key,
    each factory parameter's — and for a key no field has."""
    for cls, spec in SPECS.items():
        keys = {VOCABULARY.json_keys[cls][f.name] for f in spec.fields}
        keys |= {written_key(cls, p) for fn in spec.factories for p in inspect.signature(fn).parameters}
        for key in sorted(keys | {"no_such_key"}):
            assert param_of_key(cls, key) == _param_of_key_by_scan(cls, key), (cls.__name__, key)
