"""A child the parent's records cannot have — `posthumous-birth`, `children-span`."""
from __future__ import annotations

import unittest
from collections.abc import Callable

from verso.ru.cli.facts import format_children_span, format_posthumous
from verso.ru.facts.checks.parenthood import children_spans, posthumous_births
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import (
    Assertion, AssertionSet, BornOn, BuriedOn, Citation, DiedOn, FactDate, ParentOf, Persona, Record, Stated)

_KSENIA = ("ksenia",)
_IVAN = ("ivan",)


def _cite(kind: str, entry: int, year: int, locator: str) -> Citation:
    return Citation(village="Тестовка", source_file=f"{kind}{entry}.py", record_kind=kind,
                    record_num=str(entry), entry=entry, year=year, locator=locator)


def _birth(entry: int, y: int, m: int, d: int, *, mother: bool = True,
           father: bool = False) -> list[Assertion]:
    child = Persona(f"b{entry}/0")
    facts: list[Assertion] = [BornOn(subject=child, cite=_cite("birth", entry, y, "child"),
                                     date=FactDate(year=y, month=m, day=d), basis=Stated())]
    for on, locator, ordinal in ((father, "father", 1), (mother, "mother", 2)):
        if on:
            facts.append(ParentOf(subject=Persona(f"b{entry}/{ordinal}"),
                                  cite=_cite("birth", entry, y, locator), other=child,
                                  basis=Stated()))
    return facts


def _death(entry: int, who: int, y: int, m: int, d: int, *, buried: bool = False) -> list[Assertion]:
    kind = BuriedOn if buried else DiedOn
    return [kind(subject=Persona(f"d{entry}/{who}"), cite=_cite("death", entry, y, "deceased"),
                 date=FactDate(year=y, month=m, day=d), basis=Stated())]


def _identity(record: Record) -> Callable[[Persona], IdentityKey | None]:
    """Every mother (ordinal 2) and every death is Ксения; fathers are Иван."""
    def who(p: Persona) -> IdentityKey | None:
        record, _, ordinal = p.id.rpartition("/")
        if record.startswith("d"):
            return _KSENIA if ordinal == "0" else _IVAN
        return {"2": _KSENIA, "1": _IVAN}.get(ordinal)
    return who


def _facts(*groups: list[Assertion]) -> AssertionSet:
    return AssertionSet(a for g in groups for a in g)


class PosthumousBirth(unittest.TestCase):
    def test_a_child_after_the_mothers_death(self):
        [f] = posthumous_births(_facts(_death(1, 0, 1844, 11, 14),
                                       _birth(2, 1847, 2, 22)), _identity)
        self.assertEqual(("mother", 830, "HIGH"), (f.role, f.days, f.confidence))

    def test_a_father_may_die_before_the_birth(self):
        """A posthumous child: born 195 days after the father died."""
        facts = _facts(_death(1, 1, 1826, 10, 5), _birth(2, 1827, 4, 18, mother=False, father=True))
        self.assertEqual([], posthumous_births(facts, _identity))

    def test_but_not_a_year_after(self):
        facts = _facts(_death(1, 1, 1824, 1, 1), _birth(2, 1827, 4, 18, mother=False, father=True))
        [f] = posthumous_births(facts, _identity)
        self.assertEqual("father", f.role)

    def test_the_burial_stands_in_for_an_undated_death(self):
        facts = _facts(_death(1, 0, 1844, 11, 14, buried=True), _birth(2, 1847, 2, 22))
        self.assertEqual(1, len(posthumous_births(facts, _identity)))

    def test_the_latest_death_the_records_allow_is_used(self):
        """Two deaths on one fold: judged against the later one."""
        facts = _facts(_death(1, 0, 1830, 1, 1), _death(3, 0, 1850, 1, 1),
                       _birth(2, 1847, 2, 22))
        self.assertEqual([], posthumous_births(facts, _identity))

    def test_the_report(self):
        found = posthumous_births(_facts(_death(1, 0, 1844, 11, 14), _birth(2, 1847, 2, 22)),
                                  _identity)
        text = format_posthumous(found, lambda r: "Ксения Лукинична")
        self.assertIn("[HIGH] Ксения Лукинична (ksenia), мать — ребёнок 22.02.1847 "
                      "[birth2.py №2], через 830 дн. после смерти 14.11.1844 "
                      "[death1.py №1]", text)


class ChildrenSpan(unittest.TestCase):
    def test_a_long_but_possible_span_is_fine(self):
        facts = _facts(_birth(1, 1850, 1, 1), _birth(2, 1876, 6, 1))
        self.assertEqual([], children_spans(facts, _identity))

    def test_longer_than_a_woman_bears(self):
        facts = _facts(_birth(1, 1850, 1, 1), _birth(2, 1865, 1, 1), _birth(3, 1881, 6, 1))
        [f] = children_spans(facts, _identity)
        self.assertEqual((3, 31.4, "HIGH"), (f.children, f.years, f.confidence))
        self.assertIn("3 детей за 31.4 г.", format_children_span([f], lambda r: r))

    def test_fathers_are_not_asked(self):
        facts = _facts(_birth(1, 1850, 1, 1, mother=False, father=True),
                       _birth(2, 1890, 1, 1, mother=False, father=True))
        self.assertEqual([], children_spans(facts, _identity))


if __name__ == "__main__":
    unittest.main()
