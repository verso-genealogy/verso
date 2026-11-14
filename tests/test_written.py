"""What a DSL call wrote, kept on the object it built (`verso.core.written`)."""
from __future__ import annotations

import inspect
from calendar import Month

from verso.ru.domain import Gender, RecordDefaults, page, person
from verso.ru.domain.event_date import EventDate
from verso.ru.domain.statuses import KAZENNYJ_PEASANT_MALE
from verso.ru.dsl.records.births import birth, birth_month, birth_records, christening
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.dsl.records.divorces import divorce, divorce_records
from verso.ru.dsl.records.external_sources import (
    criminal_record, external_source_records, wwi_record, wwii_record)
from verso.ru.dsl.records.marriages import marriage, marriage_records
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.relationship import Relationship, relative
from verso.core.written import is_value, written_of

DECORATED = (person, relative, birth, christening, marriage, death, divorce, member, household,
             listed_person, criminal_record, wwi_record, wwii_record, birth_records,
             marriage_records, death_records, divorce_records, census_records, name_list_records,
             external_source_records)


def test_written_holds_what_the_call_passes():
    p = person("Иванъ", "Петровъ", status=KAZENNYJ_PEASANT_MALE)
    assert written_of(p) == {"name_orig": "Иванъ", "patr_orig": "Петровъ",
                             "status": KAZENNYJ_PEASANT_MALE}
    assert written_of(person("Иванъ", gender=None)) == {"name_orig": "Иванъ", "gender": None}


def test_persons_and_varargs_are_not_written():
    b = birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))
    assert written_of(b) == {"record_num": 1, "gender": Gender.MALE, "b_day": 3, "k_day": 4}
    rs = birth_records("А", "1", "2", "3", "Маниловка", "Церковь", 1900, b,
                       defaults=RecordDefaults(residence="Маниловка"))
    written = written_of(rs)
    assert written is not None
    assert list(written) == ["archive", "fund", "inventory", "case", "village", "church", "year",
                             "defaults"]
    assert isinstance(written["defaults"], RecordDefaults)


def test_a_relative_and_a_member_write_their_own_fields():
    assert written_of(relative(person("Петръ"), Relationship.FATHER, "мать")) == {
        "relationship": Relationship.FATHER, "relationship_ref": "мать"}
    assert written_of(member(1, person("Иванъ"), CensusRole.HEAD, age=59)) == {
        "number": 1, "role": CensusRole.HEAD, "age": 59}


def test_written_survives_the_wrappers():
    [r] = page("12", *birth_month(Month.MAY, birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))))
    assert r.page == "12" and r.b_month is Month.MAY
    assert written_of(r) == {"record_num": 1, "gender": Gender.MALE, "b_day": 3, "k_day": 4}
    assert written_of(r.child) == {"name_orig": "Иванъ"}


def test_written_comes_last_among_the_attributes():
    assert list(vars(person("Иванъ")))[-1] == "_written"


def test_what_counts_as_a_value():
    assert is_value(None) and is_value("x") and is_value(5) and is_value(0.5) and is_value(True)
    assert is_value(KAZENNYJ_PEASANT_MALE) and is_value(Month.MAY) and is_value(["Other"])
    assert is_value(EventDate(1915)) and is_value(RecordDefaults(residence="Маниловка"))
    assert not is_value(person("Иванъ"))
    assert not is_value([relative(person("Петръ"), Relationship.FATHER)])


def test_an_object_built_without_a_factory_has_no_written():
    assert written_of(EventDate(1915)) is None


def test_signatures_are_unchanged():
    # Verso reads the DSL's parameters with inspect (verso.ru.dsl.signatures).
    for fn in DECORATED:
        original = inspect.unwrap(fn)
        assert original is not fn and original.__name__ == fn.__name__
        assert inspect.signature(fn) == inspect.signature(original)
