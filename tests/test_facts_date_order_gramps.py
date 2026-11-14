"""The orderings `date-order` took from Gramps Verify, and a roll that counts the dead.

Every one is asked of one person's records, across entries — a wedding before
a birth, a death before a wedding or a christening, a roll counting alive
someone a record has buried.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable

from verso.ru.facts.checks.dates import date_order_findings
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import (
    AssertionSet, BaptizedOn, BornOn, BuriedOn, Citation, Derived, DiedOn, FactDate, MarriedOn, Persona, Record, Stated, Surety, SurvivedUntil)


def _cite(entry: int, year: int) -> Citation:
    return Citation(village="Тестовка", source_file=f"r{entry}.py", record_kind="k",
                    record_num=str(entry), entry=entry, year=year, locator="who")


def _who(entry: int) -> Persona:
    return Persona(f"r{entry}.py#0/0")


def _one_person(_record: Record) -> Callable[[Persona], IdentityKey | None]:
    return lambda _who: ("stepan",)


def _kinds(*assertions) -> list[str]:
    within, across = date_order_findings(AssertionSet(assertions), _one_person)
    inside = [k for rows in within.values() for k, *_ in rows]
    return sorted(k for rows in across.values() for k, *_ in rows) + inside


def _day(y: int, m: int, d: int) -> FactDate:
    return FactDate(year=y, month=m, day=d)


class GrampsOrderings(unittest.TestCase):
    def test_a_wedding_before_the_birth(self):
        self.assertEqual(["marriage_before_birth"], _kinds(
            MarriedOn(subject=_who(1), cite=_cite(1, 1820), date=_day(1820, 1, 20),
                      basis=Stated()),
            BornOn(subject=_who(2), cite=_cite(2, 1825), date=_day(1825, 3, 1),
                   basis=Stated())))

    def test_a_death_before_the_wedding(self):
        self.assertEqual(["death_before_marriage"], _kinds(
            DiedOn(subject=_who(1), cite=_cite(1, 1830), date=_day(1830, 5, 2),
                   basis=Stated()),
            MarriedOn(subject=_who(2), cite=_cite(2, 1835), date=_day(1835, 1, 20),
                      basis=Stated())))

    def test_a_burial_defers_to_a_dated_death(self):
        """With a death on record the burial row would say the same thing twice."""
        self.assertEqual(["death_before_marriage"], _kinds(
            DiedOn(subject=_who(1), cite=_cite(1, 1830), date=_day(1830, 5, 2),
                   basis=Stated()),
            BuriedOn(subject=_who(1), cite=_cite(1, 1830), date=_day(1830, 5, 4),
                     basis=Stated()),
            MarriedOn(subject=_who(2), cite=_cite(2, 1835), date=_day(1835, 1, 20),
                      basis=Stated())))

    def test_a_burial_alone_is_asked(self):
        self.assertEqual(["burial_before_baptism"], _kinds(
            BuriedOn(subject=_who(1), cite=_cite(1, 1832), date=_day(1832, 1, 3),
                     basis=Stated()),
            BaptizedOn(subject=_who(2), cite=_cite(2, 1832), date=_day(1832, 1, 4),
                       basis=Stated())))

    def test_a_roll_counting_the_dead_alive(self):
        self.assertEqual(["death_before_alive"], _kinds(
            DiedOn(subject=_who(1), cite=_cite(1, 1837), date=_day(1837, 12, 3),
                   basis=Stated()),
            SurvivedUntil(subject=_who(2), cite=_cite(2, 1850), date=_day(1850, 10, 1),
                          basis=Derived("counted in the roll", Surety.INFERRED, ()))))

    def test_one_day_is_not_before_itself(self):
        """Died and christened the same day: an emergency baptism, not a conflict."""
        self.assertEqual([], _kinds(
            DiedOn(subject=_who(1), cite=_cite(1, 1832), date=_day(1832, 1, 4),
                   basis=Stated()),
            BaptizedOn(subject=_who(2), cite=_cite(2, 1832), date=_day(1832, 1, 4),
                       basis=Stated())))


if __name__ == "__main__":
    unittest.main()
