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
from verso.ru.dsl.records.divorces import divorce
from verso.ru.facts.checks.dates import date_order_findings, unplaced_within, within_entry
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.divorces import facts_from_divorces
from verso.ru.facts.identity import IdentityKey, name_identity, self_identity
from verso.ru.facts.model import AssertionSet, Persona, Record
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


def _divorced(number: int, day: int | None, month: Month | None, year: int, married: str | None, **more):
    return divorce(number, day, month, husband=person("Иван", "Петров"), wife=person(more.pop("wife", "Анна"), "Ильина"),
                   marriage_date=married, year=year, **more)


def _divorces(*records) -> AssertionSet:
    return AssertionSet(facts_from_divorces([(r, "divorces_1925.py") for r in records], village="Маниловка"))


def _refused(_persona: Persona) -> IdentityKey | None:
    return None


def _nobody(_record: Record):
    """An identity that places nobody: every appearance refused, as the bridge refuses a divorce's people."""
    return _refused


class DivorceBeforeItsMarriage(unittest.TestCase):
    """An act of divorce names the marriage it ends: dated after the divorce itself, the act contradicts itself."""

    def test_a_divorce_before_the_marriage_its_act_names(self):
        """Both spouses carry the two dates, and the entry is said once — as a wedding is asked once."""
        [f] = within_entry(_divorces(_divorced(1, 3, Month.JULY, 1925, "12 сентября 1925")))
        self.assertEqual(("divorce_before_marriage", "husband"), (f.kind, f.left.cite.locator))
        self.assertEqual((3, 12), (f.left.date.day, f.right.date.day))

    def test_an_act_naming_one_spouse_says_it_of_that_one(self):
        [f] = within_entry(_divorces(divorce(1, 3, Month.JULY, wife=person("Анна", "Ильина"),
                                             marriage_date="12 сентября 1925", year=1925)))
        self.assertEqual("wife", f.left.cite.locator)

    def test_a_marriage_before_the_divorce_is_no_finding(self):
        self.assertEqual([], within_entry(_divorces(_divorced(1, 3, Month.JULY, 1925, "12 сентября 1924"))))

    def test_a_year_alone_orders_nothing_inside_itself(self):
        self.assertEqual([], within_entry(_divorces(_divorced(1, None, None, 1925, "31 января 1925"))))
        self.assertEqual([], within_entry(_divorces(_divorced(1, 3, Month.JULY, 1925, "1925"))))

    def test_source_date_error_withdraws_it(self):
        facts = _divorces(_divorced(1, 3, Month.JULY, 1925, "12 сентября 1925", source_date_error="так в акте"))
        self.assertEqual([], within_entry(facts))

    def test_a_second_marriage_after_a_first_divorce_is_never_a_finding(self):
        """One man, two acts: divorced in 1925, married again in 1926 — the order of a life, and no contradiction.
        The ordering is asked inside one entry only."""
        facts = _divorces(_divorced(1, 3, Month.JULY, 1925, "24 февраля 1920"),
                          _divorced(2, 5, Month.MAY, 1930, "12 сентября 1926", wife="Ольга"))
        within, across = date_order_findings(facts, name_identity())
        self.assertEqual(({}, {}), (within, across))

    def test_it_is_in_the_within_class_of_the_village_s_reading_where_the_people_are_placed(self):
        facts = _divorces(_divorced(1, 3, Month.JULY, 1925, "12 сентября 1925"))
        within, across = date_order_findings(facts, self_identity())
        self.assertEqual({}, across)
        self.assertEqual(["divorce_before_marriage"] * 2, [kind for rows in within.values() for kind, *_ in rows])

    def test_people_no_identity_places_are_asked_alone(self):
        """A divorce's people have no profile: the bridge refuses them, and what their entry says of itself is
        asked all the same."""
        facts = _divorces(_divorced(1, 3, Month.JULY, 1925, "12 сентября 1925"),
                          _divorced(2, 5, Month.JULY, 1925, "12 сентября 1924", wife="Ольга"))
        self.assertEqual(({}, {}), date_order_findings(facts, _nobody))
        self.assertEqual(["divorce_before_marriage"], [f.kind for f in unplaced_within(facts, _nobody)])
        self.assertEqual([], unplaced_within(facts, self_identity()))


if __name__ == "__main__":
    unittest.main()
