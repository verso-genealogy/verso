"""A divorce record → assertions (`verso.ru.facts.extract.divorces`).

What an act of divorce says: these two were spouses, the day the marriage was
dissolved, how old each was — and, where the act names it, the day they had
married. That last one is a later document's claim about a wedding: it is read
only in the forms a date is written in, and anything else asserts nothing.
"""
from __future__ import annotations

from calendar import Month
from typing import Any

import pytest

from verso.ru.domain import person
from verso.ru.dsl.records.divorces import divorce
from verso.ru.facts.extract.divorces import RECORD_KIND, facts_from_divorces, named_wedding
from verso.ru.facts.model import (
    AgedYears, AssertionSet, DivorcedOn, FactDate, MarriedOn, NameClaim, ResidedIn, SpouseOf, Stated)


def _divorce(number: int = 1, day: int | None = 3, month: Month | None = Month.JULY, **more: Any) -> Any:
    more.setdefault("husband", person("Иванъ", "Петровъ", residence="Горюхино"))
    more.setdefault("wife", person("Анна", "Иванова", residence="Горюхино"))
    more.setdefault("year", 1925)
    return divorce(number, day, month, **more)


def _facts(*records: Any, drafts: bool = False) -> AssertionSet:
    return AssertionSet(facts_from_divorces([(r, "divorces_1925.py") for r in records], village="Горюхино",
                                            drafts=drafts))


@pytest.mark.parametrize("text, date", [
    ("24 февраля 1927", FactDate(year=1927, month=2, day=24)),
    ("7 ноября 1915 г.", FactDate(year=1915, month=11, day=7)),
    ("7 Ноября 1915 года", FactDate(year=1915, month=11, day=7)),
    ("07.11.1915", FactDate(year=1915, month=11, day=7)),
    ("февраль 1927", FactDate(year=1927, month=2)),
    ("февраля 1927", FactDate(year=1927, month=2)),
    ("1915", FactDate(year=1915)),
    ("  1915 г. ", FactDate(year=1915)),
])
def test_the_wedding_an_act_names_is_read_in_the_forms_a_date_is_written_in(text: str, date: FactDate) -> None:
    assert named_wedding(text) == date


@pytest.mark.parametrize("text", [None, "", "в феврале 1927 г.", "1915?", "24/II-1927", "31 февраля 1927",
                                  "24 фебруария 1927", "32.01.1927", "24 февраля", "около 1915"])
def test_anything_else_names_no_wedding(text: str | None) -> None:
    assert named_wedding(text) is None


def test_a_divorce_asserts_the_couple_the_day_and_the_ages() -> None:
    facts = _facts(_divorce(husband_age=30, wife_age=27, marriage_date="24 февраля 1920"))
    assert {a.cite.record_kind for a in facts} == {RECORD_KIND} == {"divorce"}
    assert {a.cite.locator for a in facts} == {"husband", "wife"}
    divorced = facts.of(DivorcedOn)
    assert [(a.cite.locator, a.date, a.basis) for a in divorced] == [
        ("husband", FactDate(year=1925, month=7, day=3), Stated()),
        ("wife", FactDate(year=1925, month=7, day=3), Stated())]
    husband, wife = (a.subject for a in divorced)
    assert {(a.subject, a.other) for a in facts.of(SpouseOf)} == {(husband, wife), (wife, husband)}
    assert all(a.basis == Stated() for a in facts.of(SpouseOf))
    assert [(a.cite.locator, a.date, a.basis) for a in facts.of(MarriedOn)] == [
        ("husband", FactDate(year=1920, month=2, day=24), Stated()),
        ("wife", FactDate(year=1920, month=2, day=24), Stated())]
    assert [(a.cite.locator, a.age, a.as_of, a.basis) for a in facts.of(AgedYears)] == [
        ("husband", 30, FactDate(year=1925, month=7, day=3), Stated(basis_unknown=True)),
        ("wife", 27, FactDate(year=1925, month=7, day=3), Stated(basis_unknown=True))]
    assert [a.given for a in facts.of(NameClaim)] == ["Иван", "Анна"]


def test_where_they_lived_is_of_unknown_basis() -> None:
    """The record set's defaults fill a residence in place: which of the two the act wrote is not knowable."""
    assert [(a.place, a.basis) for a in _facts(_divorce()).of(ResidedIn)] == [
        ("Горюхино", Stated(basis_unknown=True))] * 2


def test_a_divorce_dated_to_the_year_alone_is_dated_so() -> None:
    facts = _facts(_divorce(day=None, month=None, husband_age=35))
    assert {a.date for a in facts.of(DivorcedOn)} == {FactDate(year=1925)}
    assert [a.as_of for a in facts.of(AgedYears)] == [FactDate(year=1925)]


def test_a_divorce_with_one_spouse_asserts_what_it_has() -> None:
    facts = _facts(_divorce(wife=None, husband_age=30, wife_age=27, marriage_date="1920"))
    assert facts.of(SpouseOf) == ()
    assert [a.cite.locator for a in facts.of(DivorcedOn)] == ["husband"]
    assert [a.cite.locator for a in facts.of(MarriedOn)] == ["husband"]
    assert [a.cite.locator for a in facts.of(AgedYears)] == ["husband"]


def test_a_date_of_marriage_it_cannot_read_asserts_no_wedding() -> None:
    facts = _facts(_divorce(marriage_date="в феврале 1920 г."))
    assert facts.of(MarriedOn) == () and len(facts.of(DivorcedOn)) == 2


def test_source_date_error_withdraws_the_wedding_and_keeps_the_divorce() -> None:
    facts = _facts(_divorce(marriage_date="12 сентября 1925", source_date_error="так в акте"))
    assert len(facts.of(MarriedOn)) == 2 and facts.believed().of(MarriedOn) == ()
    assert len(facts.believed().of(DivorcedOn)) == 2


def test_calendar_note_rides_on_the_wedding() -> None:
    facts = _facts(_divorce(marriage_date="7 ноября 1915", calendar_note="суббота, так в акте"))
    assert {a.calendar_note for a in facts.of(MarriedOn)} == {"суббота, так в акте"}
    assert {a.calendar_note for a in _facts(_divorce(marriage_date="7 ноября 1915")).of(MarriedOn)} == {None}


def test_an_unreviewed_divorce_asserts_nothing_and_is_read_as_a_draft() -> None:
    held = _divorce(husband_age=30, marriage_date="1920", reviewed=False)
    assert len(_facts(held)) == 0
    assert len(_facts(held, drafts=True)) == len(_facts(_divorce(husband_age=30, marriage_date="1920")))


def test_two_divorces_of_one_file_are_two_entries() -> None:
    facts = _facts(_divorce(1), _divorce(2))
    assert len({a.subject for a in facts}) == 4 and len(facts.records()) == 2
