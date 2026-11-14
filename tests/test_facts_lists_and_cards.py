"""Name lists and external catalog cards: what they assert, and what they don't.

Both are «deliberate duplicates, reconciled onto the canonical in the
consolidation pass» — the records a reconciliation channel starts from. Until
2026-09-28 the facts layer did not read either, so Горюхино's 842 list entries
and 55 cards stood outside every check.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.domain.event_date import EventDate
from verso.ru.dsl.records.external_sources import (
    external_source_records, wwi_record, wwii_record)
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.facts.extract.external_sources import facts_from_external_sources
from verso.ru.facts.extract.name_lists import facts_from_name_lists
from verso.ru.facts.model import (
    AgedYears, AssertionSet, BornOn, Derived, DiedOn, NameClaim, ResidedIn, Stated, SurvivedUntil)

_URL = "https://gwar.mil.ru/heroes/1"


def _list(*entries, reviewed: bool = True) -> AssertionSet:
    book = name_list_records("ГА", "1", "1", "1", "Тестовка", 1917, *entries,
                             document_type="Список избирателей",
                             record_day=10, record_month=10, reviewed=reviewed)
    return AssertionSet(facts_from_name_lists([(book, "l.py")], village="Тестовка"))


def _cards(*cards) -> AssertionSet:
    return AssertionSet(facts_from_external_sources(
        [(external_source_records("Тестовка", *cards), "e.py")], village="Тестовка"))


class AListEntry(unittest.TestCase):
    def test_an_age_is_stated_on_the_lists_day_and_no_birth_is_claimed(self):
        facts = _list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"), age=40))
        [aged] = facts.of(AgedYears)
        self.assertEqual(40, aged.age)
        self.assertEqual((1917, 10, 10), aged.as_of.earliest)
        self.assertEqual((), facts.of(BornOn))

    def test_without_an_age_it_says_who_and_that_they_were_alive(self):
        facts = _list(listed_person(1, person("Иванъ", "Петровъ")))
        self.assertEqual((), facts.of(AgedYears))
        [alive] = facts.of(SurvivedUntil)
        assert isinstance(alive.basis, Derived)
        self.assertEqual("list.listed-alive", alive.basis.rationale)
        self.assertEqual("list", facts.of(NameClaim)[0].cite.record_kind)

    def test_the_residence_the_list_fills_in_is_of_unknown_basis(self):
        [place] = _list(listed_person(1, person("Иванъ"))).of(ResidedIn)
        self.assertEqual("Тестовка", place.place)
        self.assertEqual(Stated(basis_unknown=True), place.basis)

    def test_an_unreviewed_entry_asserts_nothing_and_renumbers_nobody(self):
        book = name_list_records("ГА", "1", "1", "1", "Тестовка", 1917,
                                 listed_person(1, person("Иванъ"), reviewed=False),
                                 listed_person(2, person("Петръ")),
                                 document_type="Список избирателей")
        facts = AssertionSet(facts_from_name_lists([(book, "l.py")], village="Т"))
        self.assertEqual({"2"}, {a.cite.record_num for a in facts})
        self.assertEqual({1}, {a.cite.entry for a in facts})


class ACard(unittest.TestCase):
    def test_a_stated_birth_year_is_the_year_not_a_circa(self):
        facts = _cards(wwi_record(person("Иванъ", "Петровъ"), source_url=_URL,
                                  birth_year=1890, date=EventDate(1915, Month.MAY, 3)))
        [born] = facts.of(BornOn)
        self.assertEqual((1890, 1, 1), born.date.earliest)
        self.assertEqual((1890, 12, 31), born.date.latest)
        self.assertFalse(born.date.circa)

    def test_a_birth_date_is_taken_as_written(self):
        facts = _cards(wwii_record(person("Иванъ"), source_url=_URL,
                                   birth_date=EventDate(1901, Month.MARCH, 7),
                                   date=EventDate(1944, Month.JUNE, 1)))
        self.assertEqual((1901, 3, 7), facts.of(BornOn)[0].date.earliest)

    def test_an_age_is_stated_on_the_cards_day(self):
        facts = _cards(wwi_record(person("Иванъ"), source_url=_URL, age=25,
                                  date=EventDate(1915, Month.MAY, 3)))
        self.assertEqual((1915, 5, 3), facts.of(AgedYears)[0].as_of.earliest)

    def test_killed_is_a_death_and_not_a_sign_of_life(self):
        facts = _cards(wwi_record(person("Иванъ"), source_url=_URL,
                                  casualty_reason="убит",
                                  date=EventDate(1915, Month.MAY, 3)))
        self.assertEqual(1, len(facts.of(DiedOn)))
        self.assertEqual((), facts.of(SurvivedUntil))

    def test_missing_is_not_a_death(self):
        facts = _cards(wwi_record(person("Иванъ"), source_url=_URL,
                                  casualty_reason="пропал без вести",
                                  date=EventDate(1915, Month.MAY, 3)))
        self.assertEqual((), facts.of(DiedOn))
        self.assertEqual(1, len(facts.of(SurvivedUntil)))

    def test_draft_and_feat_are_days_alive_too(self):
        facts = _cards(wwii_record(person("Иванъ"), source_url=_URL,
                                   date=EventDate(1985, Month.MARCH, 11),
                                   draft_date=EventDate(1941, Month.JULY, 1),
                                   feat_date=EventDate(1943, Month.AUGUST, 5)))
        self.assertEqual(3, len(facts.of(SurvivedUntil)))

    def test_an_undated_card_dates_nothing(self):
        facts = _cards(wwi_record(person("Иванъ"), source_url=_URL, age=25))
        self.assertEqual((), facts.of(AgedYears))
        self.assertEqual((), facts.of(SurvivedUntil))
        self.assertEqual(1, len(facts.of(NameClaim)))


if __name__ == "__main__":
    unittest.main()


class AWeddingAge(unittest.TestCase):
    """The age a marriage book gives the groom and the bride — one more
    statement of when each was born, which reached no check until 2026-09-28."""

    def test_each_spouse_s_age_is_stated_on_the_wedding_day(self):
        from verso.ru.dsl.records.marriages import marriage
        from verso.ru.facts.extract.marriages import facts_from_marriages

        rec = marriage(1, 7, Month.MAY, groom=person("Иванъ", "Петровъ"),
                       bride=person("Анна", "Ильина"), groom_age=18, bride_age="?")
        rec.year = 1887
        facts = AssertionSet(facts_from_marriages([(rec, "m.py")], village="Т"))
        [aged] = facts.of(AgedYears)
        self.assertEqual(18, aged.age)
        self.assertEqual("groom", aged.cite.locator)
        self.assertEqual((1887, 5, 7), aged.as_of.earliest)
