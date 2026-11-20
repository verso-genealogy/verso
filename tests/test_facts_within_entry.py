"""`date-order` inside one entry, asked of the entry alone — `within_entry`.

The class «inside one entry» of `date_order_findings` is picked out AFTER the
consolidation: two claims of one canonical that one record made. A record read
alone has no consolidation, so the same orderings are asked on an identity
where every persona is its own person.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.facts.checks.dates import date_order_findings, within_entry
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.identity import self_identity
from verso.ru.facts.model import AssertionSet
from verso.ru.gender import Gender


def _born(b_day: int, k_day: int, **more):
    return birth(1, Gender.MALE, b_day, k_day, Month.OCTOBER, Month.OCTOBER, year=1850,
                 child=person("Иван"), father=person("Петр", "Иванов"), **more)


def _died(d_day: int, b_day: int, **more):
    return death(1, Gender.MALE, d_day, b_day, Month.MARCH, Month.MARCH, year=1850,
                 deceased=person("Иван"), **more)


def _births(*records) -> AssertionSet:
    return AssertionSet(facts_from_births([(r, "births_1850.py") for r in records], village="Маниловка"))


def _deaths(*records) -> AssertionSet:
    return AssertionSet(facts_from_deaths([(r, "deaths_1850.py") for r in records], village="Маниловка"))


class WithinEntry(unittest.TestCase):
    def test_a_christening_before_the_birth_is_found_in_its_entry(self):
        self.assertEqual(["baptism_before_birth"], [f.kind for f in within_entry(_births(_born(18, 11)))])

    def test_the_finding_holds_the_two_claims(self):
        [f] = within_entry(_births(_born(18, 11)))
        self.assertEqual((11, 18), (f.left.date.day, f.right.date.day))

    def test_source_date_error_withdraws_it(self):
        facts = _births(_born(18, 11, source_date_error="так в подлиннике"))
        self.assertEqual([], within_entry(facts))

    def test_a_christening_after_the_birth_is_no_finding(self):
        self.assertEqual([], within_entry(_births(_born(11, 18))))

    def test_a_burial_before_the_death(self):
        self.assertEqual(["burial_before_death"], [f.kind for f in within_entry(_deaths(_died(9, 8)))])

    def test_two_people_of_one_entry_are_never_compared(self):
        """The father's claims and the child's are two people's, whatever they are dated."""
        facts = _births(_born(11, 18))
        self.assertEqual([], within_entry(facts))
        self.assertGreater(len({a.subject for a in facts}), 1)

    def test_two_entries_are_never_compared(self):
        """A second entry naming the same child, christened before the first one's birth: across entries, not here."""
        other = birth(2, Gender.MALE, 1, 2, Month.OCTOBER, Month.OCTOBER, year=1850,
                      child=person("Иван"), father=person("Петр", "Иванов"))
        self.assertEqual([], within_entry(_births(_born(11, 18), other)))

    def test_it_equals_the_within_class_under_a_one_to_one_identity(self):
        facts = AssertionSet([*_births(_born(18, 11)), *_deaths(_died(9, 8))])
        within, across = date_order_findings(facts, self_identity())
        self.assertEqual({}, across)
        self.assertEqual(sorted(kind for rows in within.values() for kind, *_ in rows),
                         sorted(f.kind for f in within_entry(facts)))


if __name__ == "__main__":
    unittest.main()
