"""One person, two deaths that cannot be one — `facts-check check=death-claims`.

Pinned on a made-up village: a roll's told year within `date-order`'s slack is
one death, beyond it two; a gap under a year past the slack is LOW (on the
corpus the told year runs 3, 3, 3, 3, 4 … years early with no break); two
burial entries on two days are two people; and the pair `date-order` already
reports — a burial before another record's death — is not reported twice.
"""
from __future__ import annotations

import unittest
from calendar import Month
from collections.abc import Callable
from typing import Any

from verso.ru.domain import person
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.facts.checks.deaths import death_claims, gap_days
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import (
    Assertion, AssertionSet, DiedOn, FactDate, NameClaim, Persona, Record)
from verso.ru.gender import Gender


def _buried(year: int, d_day: int, b_day: int | None, month: Month = Month.MAY,
            num: int = 1) -> Any:
    return death_records("A", "1", "1", "1", "Тестовка", "Ц", year,
                         death(num, Gender.MALE, d_day, b_day, month,
                               month if b_day is not None else None,
                               deceased=person("Степанъ", "Давыдовъ"), age=40))


def _roll(year: int, died: int) -> Any:
    return census_records(
        "ГАТО", "12", "1", "1", "Тестовка", year,
        household("4",
                  member(1, person("Давыдъ", "Ивановъ"), CensusRole.HEAD, age=60),
                  member(2, person("Степанъ", "Давыдовъ"), CensusRole.SON,
                         previous_age=20, departure_year=died,
                         departure_reason="умер")))


def _facts(*books: tuple[Any, str]) -> AssertionSet:
    out: list[Assertion] = []
    for book, name in books:
        if hasattr(book, "households"):
            out += facts_from_census([(book, name)], village="Тестовка")
            continue
        for rec in book.records:
            if rec.year is None:
                rec.year = book.year
        out += facts_from_deaths([(r, name) for r in book.records], village="Тестовка")
    return AssertionSet(out)


def _stepan(facts: AssertionSet) -> Callable[[Record], Callable[[Persona], IdentityKey | None]]:
    """Every Степан is one canonical; everyone else stands alone."""
    keys: dict[Persona, IdentityKey] = {}
    for a in facts.of(NameClaim):
        keys[a.subject] = (("stepan",) if a.given == "Степан"
                           else (f"{a.cite.source_file}:{a.cite.locator}",))

    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        return keys.get
    return identity


def _found(*books: tuple[Any, str]) -> Any:
    facts = _facts(*books).believed()
    return death_claims(facts, _stepan(facts))


class OneDeath(unittest.TestCase):
    def test_a_told_year_within_the_slack_is_one_death(self):
        books = ((_buried(1824, 3, 5), "d.py"), (_roll(1834, 1822), "rs.py"))
        self.assertEqual(2, len(_facts(*books).of(DiedOn)))
        self.assertEqual([], _found(*books))

    def test_two_days_can_be_one_death_only_if_they_are_one_day(self):
        self.assertEqual(0, gap_days(FactDate(year=1824, month=5, day=3),
                                     FactDate(year=1824, month=5)))
        self.assertEqual(7, gap_days(FactDate(year=1824, month=5, day=3),
                                     FactDate(year=1824, month=5, day=10)))

    def test_one_record_never_contradicts_itself_here(self):
        self.assertEqual([], _found((_buried(1824, 3, 5), "d.py")))


class TwoDeaths(unittest.TestCase):
    def test_a_told_year_far_from_the_burial_is_two_people(self):
        """An infant «умер 1798» in the 1811 roll folded with a man buried
        in 1805."""
        [f] = _found((_buried(1805, 6, 8), "d.py"), (_roll(1811, 1798), "rs.py"))
        self.assertEqual("stepan", f.canonical)
        self.assertEqual("HIGH", f.confidence)
        self.assertGreater(f.gap, 365)

    def test_just_past_the_slack_is_low(self):
        [f] = _found((_buried(1823, 7, 9, Month.JULY), "d.py"),
                     (_roll(1834, 1820), "rs.py"))
        self.assertEqual("LOW", f.confidence)
        self.assertLess(f.gap, 365)

    def test_two_burial_entries_on_two_days_are_two_people(self):
        [f] = _found((_buried(1812, 10, None, Month.FEBRUARY, num=4), "d1.py"),
                     (_buried(1812, 20, None, Month.FEBRUARY, num=5), "d2.py"))
        self.assertEqual(10, f.gap)
        self.assertEqual("HIGH", f.confidence)

    def test_a_burial_before_the_other_death_is_date_order_s(self):
        """Buried in 1836, told dead ~1844: `date-order` reports the burial
        before the death, and this check does not repeat it."""
        books = ((_buried(1836, 5, 7), "d.py"), (_roll(1850, 1844), "rs.py"))
        a, b = _facts(*books).of(DiedOn)
        self.assertGreater(gap_days(a.date, b.date) or 0, 365)
        self.assertEqual([], _found(*books))


if __name__ == "__main__":
    unittest.main()
