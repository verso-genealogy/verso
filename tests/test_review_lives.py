"""verso.ru.persons.lives — whether someone could be alive on the day of a record."""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.facts.checks.births import BirthSpan
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.common import SlotIndex
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.model import AssertionSet
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative
from verso.ru.persons.lives import Clue, Life, after_death, lives, lives_of, min_age, record_days, year_days

KEY = ("Горелово", "иван", "петрович", "")


def _born(year: int, age: float = 0.0) -> BirthSpan:
    span = record_days(year)
    assert span is not None
    return BirthSpan(span[0], span[1], age)


def _clue(year: int, *, born: int | None = None, age: float = 0.0, died: int | None = None,
          present: bool = True, newborn: bool = False, key=KEY) -> Clue:
    on = year_days(year)
    death_day = year_days(died) if died else None
    return Clue(key, on, _born(born, age) if born else None, death_day, present, newborn)


def _at(year: int):
    found = record_days(year)
    assert found is not None
    return found


def _possible(found: list[Life], year: int, min_years: float = 0.0) -> list[bool]:
    return [life.possible(_at(year), min_years) for life in found]


class Slots(unittest.TestCase):
    def test_only_an_adults_slot_asks_an_age(self):
        self.assertEqual(12, min_age("father"))
        self.assertEqual(12, min_age("god_parent3"))
        self.assertEqual(12, min_age("witness1"))
        self.assertEqual(0, min_age("deceased"))
        self.assertEqual(0, min_age("@3"))
        self.assertEqual(0, min_age("relatives"))
        self.assertEqual(0, min_age(""))


    def test_the_slots_that_name_the_dead(self):
        self.assertEqual(294, after_death("father"))          # a posthumous child
        self.assertIsNone(after_death("relatives"))           # a bride's late father
        self.assertIsNone(after_death("@4"))                  # a roll's dead since the last revision
        self.assertEqual(0, after_death("god_parent1"))
        self.assertEqual(0, after_death("mother"))


class Lives(unittest.TestCase):
    def test_a_death_closes_the_life_a_godparent_before_it_belongs_to(self):
        godparent = _clue(1840)
        burial = _clue(1850, born=1800, age=50, died=1850, present=False)
        found, holding = lives_of([godparent, burial])
        self.assertEqual(1, len(found))
        self.assertEqual([0], holding[0])
        self.assertEqual([True, False], [found[0].possible(_at(y)) for y in (1845, 1860)])

    def test_a_slot_that_names_the_dead(self):
        found = lives([_clue(1837, born=1817, age=20, died=1837, present=False)])
        at = _at(1838)
        self.assertEqual([False], [life.possible(at) for life in found])
        self.assertEqual([True], [life.possible(at, 12, after_death("father")) for life in found])
        self.assertEqual([False], [life.possible(_at(1840), 12, after_death("father")) for life in found])
        self.assertEqual([True], [life.possible(_at(1860), 0, after_death("relatives")) for life in found])

    def test_an_age_dates_the_birth(self):
        found = lives([_clue(1850, born=1840, age=10)])
        self.assertEqual([False], _possible(found, 1835))            # not yet born
        self.assertEqual([True], _possible(found, 1845))
        self.assertEqual([False], _possible(found, 1845, min_years=12))  # a boy of five is no father
        self.assertEqual([True], _possible(found, 1860, min_years=12))
        self.assertEqual([False], _possible(found, 1950))            # past a hundred

    def test_namesakes_born_apart_are_two_lives(self):
        self.assertEqual(2, len(lives([_clue(1834, born=1800, age=34), _clue(1858, born=1830, age=28)])))

    def test_two_christenings_are_two_children(self):
        first = _clue(1850, born=1850, newborn=True)
        second = _clue(1851, born=1851, newborn=True)
        self.assertEqual(2, len(lives([first, second])))

    def test_alive_after_a_death_is_another_life(self):
        buried = _clue(1850, born=1800, age=50, died=1850, present=False)
        groom = _clue(1860, born=1801, age=59)
        self.assertEqual(2, len(lives([buried, groom])))

    def test_an_undated_chain_ends_at_a_death(self):
        found = lives([_clue(1840), _clue(1845, died=1845, present=False), _clue(1850)])
        self.assertEqual(2, len(found))
        self.assertEqual([False, True], _possible(found, 1860))

    def test_an_undated_life_reaches_sixty_years(self):
        found = lives([_clue(1840)])
        # 1840 is the whole year: 1900 begins sixty years after it ends.
        self.assertEqual([True, False], [found[0].possible(_at(y)) for y in (1900, 1902)])
        self.assertEqual([True, False], [found[0].possible(_at(y)) for y in (1780, 1778)])

    def test_namesakes_eighty_years_apart_are_not_one_undated_life(self):
        found = lives([_clue(1799), _clue(1878)])
        self.assertEqual(2, len(found))
        self.assertEqual([False, True], _possible(found, 1900))

    def test_an_undated_appearance_fitting_two_lives_caps_neither(self):
        elder = _clue(1834, born=1800, age=34)
        younger = _clue(1834, born=1815, age=19)
        burial = _clue(1850, died=1850, present=False)
        found, holding = lives_of([elder, younger, burial])
        self.assertEqual(2, len(holding[2]))
        self.assertEqual([True, True], _possible(found, 1855))

    def test_an_old_mans_life_does_not_take_a_namesake_a_century_on(self):
        # A man of 65 in the 1719 roll is not the namesake who fathers children
        # in the 1770s: the undated appearances make a life of their own.
        found = lives([_clue(1719, born=1653, age=65), _clue(1772), _clue(1779, present=False), _clue(1791)])
        self.assertEqual(2, len(found))
        self.assertEqual([False, True], _possible(found, 1779, min_years=12))

    def test_a_relative_named_after_the_death_may_be_a_living_namesake(self):
        # A father is named at his son's wedding years after his burial — or it
        # is another man of his name: the appearance stays possible on its own.
        found = lives([_clue(1760, born=1720, age=40, died=1760, present=False), _clue(1790, present=False)])
        self.assertEqual([False, True], _possible(found, 1790))

    def test_the_chain_running_on_keeps_an_appearance_a_dated_life_also_takes(self):
        # A godmother from 1817 on, and a girl of twelve in the 1834 roll: the
        # godmother of 1833 may be either, so neither reading hides her in 1832.
        found = lives([_clue(1834, born=1822, age=12), _clue(1817), _clue(1824), _clue(1833)])
        self.assertEqual([True], [any(life.possible(_at(1832), 12) for life in found)])

    def test_one_dies_once(self):
        # Two women of one name, born about 1757, buried in 1808 and in 1814: two lives.
        found = lives([_clue(1808, born=1757, age=50, died=1808, present=False),
                       _clue(1814, born=1756, age=57, died=1814, present=False)])
        self.assertEqual(2, len(found))
        self.assertEqual([False, True], sorted(_possible(found, 1811)))

    def test_another_name_is_another_life(self):
        self.assertEqual(2, len(lives([_clue(1840), _clue(1840, key=("Горелово", "петр", "иванович", ""))])))


class FromTheRecords(unittest.TestCase):
    """What the facts layer reads of a record reaches the life it dates."""

    def _clues(self, births=(), deaths=()):
        slots = SlotIndex()
        facts = AssertionSet([*facts_from_births([(b, "b.py") for b in births], village="Горелово",
                                                 slots=slots, drafts=True),
                              *facts_from_deaths([(d, "d.py") for d in deaths], village="Горелово",
                                                 slots=slots, drafts=True)])
        from verso.ru.persons.lives import clues_of
        return clues_of(facts, slots, year=1880)

    def test_a_burial_dates_the_birth_and_the_death(self):
        deceased = person("Иван", "Петров", residence="Горелово")
        found = self._clues(deaths=[death(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH, year=1880,
                                          deceased=deceased, age=40)])
        clue = found[id(deceased)]
        assert clue.born is not None and clue.died is not None
        self.assertEqual((1839, 1840), (_year(clue.born.first), _year(clue.born.last)))
        self.assertEqual(1880, _year(clue.died[1]))
        self.assertFalse(clue.present)

    def test_a_withdrawn_age_dates_nothing(self):
        deceased = person("Иван", "Петров", residence="Горелово")
        found = self._clues(deaths=[death(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH, year=1880,
                                          deceased=deceased, age=40, source_age_error="не сходится")])
        self.assertIsNone(found[id(deceased)].born)

    def test_who_a_christening_puts_alive_on_its_day(self):
        father, godfather, priest = person("Петр", "Иванов"), person("Семен", "Ильин"), person("Иоанн", "Петров")
        child = person("Иван")
        record = birth(1, Gender.MALE, 1, 2, Month.MARCH, Month.MARCH, year=1880,
                       child=child, father=father, mother=person("Анна", "Ивановна"),
                       god_parent1=godfather, priest=priest, reviewed=False)
        found = self._clues(births=[record])
        self.assertTrue(found[id(godfather)].present)
        self.assertTrue(found[id(father)].present)      # dead, if at all, nine months before
        self.assertTrue(found[id(record.priest)].present)
        newborn = found[id(child)]
        self.assertTrue(newborn.newborn)
        assert newborn.born is not None
        self.assertEqual(1880, _year(newborn.born.first))

    def test_a_patronymic_made_of_the_father_keys_a_burial_and_not_a_birth(self):
        """В10: the newborn's, made of the father, is no key of his life; a deceased child's keys it as before."""
        child, daughter = person("Иван"), person("Марія", last_name_orig="Сидорова")
        record = birth(1, Gender.MALE, 1, 2, Month.MARCH, Month.MARCH, year=1880,
                       child=child, father=person("Петр", "Иванов"), reviewed=False)
        burial = death(1, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH, year=1880, deceased=daughter, age=20,
                       relatives=[relative(person("Петръ", "Ивановъ", "Сидоровъ"), Relationship.FATHER)])
        found = self._clues(births=[record], deaths=[burial])
        newborn, buried = found[id(child)].key, found[id(daughter)].key
        assert newborn is not None and buried is not None
        self.assertEqual(newborn[2], "")
        self.assertEqual(buried[2], "петровна")


def _year(day: int) -> int:
    from datetime import date
    return date.fromordinal(day).year


if __name__ == "__main__":
    unittest.main()
