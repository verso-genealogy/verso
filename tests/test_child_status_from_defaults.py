"""A child's сословие derived from parents the book's defaults styled.

`Birth.__init__` and `Death.__init__` derive a statusless child's status from a
parent's WRITTEN status. Parents left to the book's `RecordDefaults` had none
then, so the child fell to the ADULT default — «крестьянин» where the record
means «крестьянский сын». `RecordDefaults.apply_to_birth` / `apply_to_death`
now style the parents first and derive the child from them.
"""
from __future__ import annotations

import unittest

from corpus.statuses import GOLOVLEV_PEASANT, GOLOVLEV_PEASANT_FEMALE, GOLOVLEV_PEASANT_SON
from verso.ru.domain import Gender, RecordDefaults, person
from verso.ru.domain.statuses import (
    PEASANT_DAUGHTER, PEASANT_FEMALE, PEASANT_MALE, PEASANT_SON, PEASANT_WIFE, PRIEST)
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.relationship import Relationship, relative

_PEASANTS = RecordDefaults(status_male=PEASANT_MALE, status_female=PEASANT_FEMALE, status_mother=PEASANT_WIFE)


def _child(*births, defaults=_PEASANTS):
    return [b.child for b in birth_records("ГАВО", "1", "1", "1", "Глуповы Горы", "Покровская", 1839,
                                           *births, defaults=defaults).records]


def _deceased(*deaths, defaults=_PEASANTS):
    return [d.deceased for d in death_records("ГАВО", "1", "1", "1", "Глуповы Горы", "Покровская", 1839,
                                              *deaths, defaults=defaults).records]


class Births(unittest.TestCase):
    def test_parents_on_the_default_give_the_childs_form(self):
        son, daughter = _child(
            birth(1, Gender.MALE, 1, 2, child=person("Иванъ"), father=person("Петръ"), mother=person("Марія")),
            birth(2, Gender.FEMALE, 1, 2, child=person("Анна"), father=person("Петръ"), mother=person("Марія")))
        self.assertEqual(PEASANT_SON, son.status)
        self.assertEqual(PEASANT_DAUGHTER, daughter.status)
        self.assertTrue(son.status_defaulted)    # it rests on the book's default

    def test_with_no_father_the_mother_on_her_default_is_asked(self):
        [daughter] = _child(birth(1, Gender.FEMALE, 1, 2, child=person("Анна"), mother=person("Марія")))
        self.assertEqual(PEASANT_DAUGHTER, daughter.status)

    def test_an_owners_book_gives_the_owners_child_form(self):
        [son] = _child(birth(1, Gender.MALE, 1, 2, child=person("Иванъ"), father=person("Петръ")),
                       defaults=RecordDefaults(status_male=GOLOVLEV_PEASANT, status_female=GOLOVLEV_PEASANT_FEMALE))
        self.assertEqual(GOLOVLEV_PEASANT_SON, son.status)

    def test_a_father_out_of_scope_is_not_passed_over_for_the_mother(self):
        # A priest's child has no derived form; it keeps the book's default, as
        # before, rather than taking the mother's estate.
        [son] = _child(birth(1, Gender.MALE, 1, 2, child=person("Иванъ"),
                             father=person("Іоаннъ", status=PRIEST), mother=person("Марія")))
        self.assertEqual(PEASANT_MALE, son.status)

    def test_a_book_with_no_statuses_leaves_the_child_without_one(self):
        [son] = _child(birth(1, Gender.MALE, 1, 2, child=person("Иванъ"), father=person("Петръ")),
                       defaults=RecordDefaults(residence="Глуповы Горы"))
        self.assertIsNone(son.status)


class Deaths(unittest.TestCase):
    def test_a_dead_child_of_a_father_on_the_default(self):
        [daughter] = _deceased(death(1, Gender.FEMALE, 1, 2, deceased=person("Анна"), age=2,
                                     relatives=[relative(person("Петръ"), Relationship.FATHER)]))
        self.assertEqual(PEASANT_DAUGHTER, daughter.status)

    def test_a_wife_is_not_her_husbands_child(self):
        [wife] = _deceased(death(1, Gender.FEMALE, 1, 2, deceased=person("Марія"), age=40,
                                 relatives=[relative(person("Петръ"), Relationship.HUSBAND)]))
        self.assertEqual(PEASANT_FEMALE, wife.status)


if __name__ == "__main__":
    unittest.main()
