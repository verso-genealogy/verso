"""A christening entry states a baptism, and an age if it gives one — no birth.

`christening()` records a late or adult baptism in the birth register. The DSL
routes it through `Birth`, and `birth_month()` fills its `b_month` with the
section month, so reading `b_*` as a birth dated a boy christened at eleven to
the month of his baptism, with a `Stated` basis. The translator never did: it
emits a circa birth `year − age`, or none at all.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, birth_month, birth_records, christening
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.model import AgedYears, AssertionSet, BaptizedOn, BornOn
from verso.ru.gender import Gender


def _facts(*records) -> AssertionSet:
    book = birth_records("A", "1", "1", "1", "Тестовка", "Никольская", 1900,
                         *birth_month(Month.MAY, *records))
    for r in book.records:
        if r.year is None:
            r.year = book.year
    return AssertionSet(facts_from_births([(r, "b.py") for r in book.records],
                                          village="Тестовка"))


class AChristeningStatesNoBirth(unittest.TestCase):
    def test_an_adult_baptism_asserts_the_age_not_a_birth(self):
        facts = _facts(christening(1, Gender.MALE, 24, age=11,
                                   child=person("Тимофей"),
                                   father=person("Павел", "Андреев")))
        self.assertEqual((), facts.of(BornOn))
        [aged] = facts.of(AgedYears)
        self.assertEqual(11, aged.age)
        self.assertEqual((1900, 5, 24), aged.as_of.earliest)
        [baptized] = facts.of(BaptizedOn)
        self.assertEqual((1900, 5, 24), baptized.date.earliest)

    def test_a_christening_without_an_age_asserts_nothing_about_the_birth(self):
        facts = _facts(christening(1, Gender.FEMALE, 17, child=person("Александра"),
                                   father=person("Андрей", "Леонтьев")))
        self.assertEqual((), facts.of(BornOn))
        self.assertEqual((), facts.of(AgedYears))
        self.assertEqual(1, len(facts.of(BaptizedOn)))

    def test_an_ordinary_birth_still_states_its_birth(self):
        facts = _facts(birth(1, Gender.FEMALE, 20, 22, child=person("Анна"),
                             father=person("Петр", "Иванов")))
        [born] = facts.of(BornOn)
        self.assertEqual((1900, 5, 20), born.date.earliest)
        self.assertEqual((), facts.of(AgedYears))


if __name__ == "__main__":
    unittest.main()
