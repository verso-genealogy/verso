"""What a death record asserts, and what it declines to assert.

Three claims, each of which the pipeline around this extractor gets wrong
today, and each pinned here so it cannot come back.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.deaths import death, death_month, death_records
from verso.ru.facts.model import (
    AgedYears, AssertionSet, BuriedOn, DiedOn, FosterParentOf, KinOf, NameClaim, ParentOf, Retracted, SpouseOf)
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative


def _facts(*records, **kw) -> AssertionSet:
    recs = death_records("TestArchive", "1", "1", "1", "Тестовка", "Никольская",
                         1875, *death_month(Month.MARCH, *records), **kw)
    for r in recs.records:
        # The per-record year falls back to the book year — the same contract
        # `verso.ru.cli.facts` applies when it loads a village.
        if r.year is None:
            r.year = recs.year
    return AssertionSet(facts_from_deaths(
        [(r, "d.py") for r in recs.records], village="Тестовка"))


def _one(records, kind):
    got = _facts(*records).of(kind)
    return got


class BurialIsNotBirth(unittest.TestCase):
    def test_a_burial_gets_its_own_predicate(self):
        d = death(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Иван", "Петров"))
        buried = _one([d], BuriedOn)
        died = _one([d], DiedOn)
        self.assertEqual(1, len(buried))
        self.assertEqual((1875, 3, 5), buried[0].date.earliest)
        self.assertEqual((1875, 3, 3), died[0].date.earliest)

    def test_a_death_record_asserts_no_birth_date(self):
        """`b_day`/`b_month` are the burial here and the birth in a birth
        record — 3198 burials were filed as birth dates on that collision."""
        from verso.ru.facts.model import BornOn
        d = death(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Иван", "Петров"))
        self.assertEqual((), _one([d], BornOn))


class AgeIsEvidence(unittest.TestCase):
    def test_the_scribes_own_string_survives(self):
        d = death(1, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Анна"), age="полгода")
        aged = _one([d], AgedYears)
        self.assertEqual("полгода", aged[0].age)

    def test_an_age_the_author_withdrew_is_retracted(self):
        """`source_age_error` withdraws the age itself, so everything derived
        from it inherits the withdrawal — it is not a finding-level mute."""
        d = death(1, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Анна"), age=40,
                  source_age_error="возраст сверен по скану, не сходится")
        aged = _one([d], AgedYears)
        self.assertIsInstance(aged[0].basis, Retracted)

    def test_a_rule_never_sees_a_withdrawn_age(self):
        d = death(1, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Анна"), age=40, source_age_error="не сходится")
        self.assertEqual((), _facts(d).believed().of(AgedYears))


class TheSourceContradictsItself(unittest.TestCase):
    """A book that buries the deceased before killing them: the scan says the
    BOOK does — the burial's day a day before the death's, both figures clear.
    There is nothing to fix in the transcription, so the author withdraws the
    burial the way a birth withdraws its christening.
    """

    def test_a_burial_the_author_withdrew_is_retracted(self):
        d = death(1, Gender.MALE, 14, 13, Month.MARCH, Month.MARCH,
                  deceased=person("Лукьянъ"),
                  source_date_error="погребёнъ 13, умеръ 14 — так в подлиннике")
        buried = _one([d], BuriedOn)
        self.assertIsInstance(buried[0].basis, Retracted)

    def test_a_rule_never_sees_a_withdrawn_burial(self):
        d = death(1, Gender.MALE, 14, 13, Month.MARCH, Month.MARCH,
                  deceased=person("Лукьянъ"),
                  source_date_error="так в подлиннике")
        self.assertEqual((), _facts(d).believed().of(BuriedOn))

    def test_the_death_it_contradicts_is_still_believed(self):
        """Narrower than muting the record: withdrawing the burial leaves the
        death — and every other assertion of the entry — standing."""
        d = death(1, Gender.MALE, 14, 13, Month.MARCH, Month.MARCH,
                  deceased=person("Лукьянъ"), age=31,
                  source_date_error="так в подлиннике")
        believed = _facts(d).believed()
        self.assertEqual(1, len(believed.of(DiedOn)))
        self.assertEqual(1, len(believed.of(AgedYears)))

    def test_an_undeclared_burial_is_plain_stated(self):
        d = death(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Лукьянъ"))
        self.assertNotIsInstance(_one([d], BuriedOn)[0].basis, Retracted)


def _with(rel_person, relationship):
    return death(1, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH,
                 deceased=person("Анна"),
                 relatives=[relative(rel_person, relationship)])


class KinshipPlacesOrDeclines(unittest.TestCase):
    def test_a_father_is_a_parent(self):
        got = _one([_with(person("Пётр", "Иванов"), Relationship.FATHER)], ParentOf)
        self.assertEqual(1, len(got))

    def test_a_husband_is_a_spouse_both_ways(self):
        got = _one([_with(person("Пётр", "Иванов"), Relationship.HUSBAND)], SpouseOf)
        self.assertEqual(2, len(got))

    def test_a_foster_father_is_not_a_father(self):
        recs = [_with(person("Пётр", "Иванов"), Relationship.FOSTER_FATHER)]
        self.assertEqual(1, len(_one(recs, FosterParentOf)))
        self.assertEqual((), _one(recs, ParentOf))

    def test_a_son_reverses_the_direction(self):
        """«сынъ» makes the DECEASED the parent — the direction the old union
        rule inverted for the corpus's one зять."""
        got = _one([_with(person("Пётр", "Иванов"), Relationship.SON)], ParentOf)
        self.assertEqual(1, len(got))
        self.assertTrue(got[0].subject.id.endswith("/deceased"), "the deceased is the parent")

    def test_kin_the_model_cannot_place_is_not_a_parent(self):
        for rel in (Relationship.FATHER_IN_LAW, Relationship.SON_IN_LAW,
                    Relationship.STEP_MOTHER):
            with self.subTest(str(rel)):
                p = person("Марфа", "Платонова") if rel is Relationship.STEP_MOTHER \
                    else person("Пётр", "Иванов")
                recs = [_with(p, rel)]
                self.assertEqual((), _one(recs, ParentOf))
                kin = _one(recs, KinOf)
                self.assertEqual(1, len(kin))
                self.assertEqual(str(rel), kin[0].term)

    def test_an_unstated_kinship_is_kinship_all_the_same(self):
        """12 records fill the relative slot and leave `relationship=` unset.

        That is not «no kinship»: naming a relative asserts one and declines to
        say which. Emitting nothing lost two real Заманиловка findings before the
        oracle caught it — but it is still not a claim of PARENTHOOD, which is
        what the translator reads it as.
        """
        d = death(1, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Анна"), relatives=[relative(person("Пётр", "Иванов"), None)])
        self.assertEqual((), _one([d], ParentOf))
        kin = _one([d], KinOf)
        self.assertEqual(1, len(kin))
        self.assertEqual("", kin[0].term, "related, manner unstated")
        self.assertEqual(2, len(_one([d], NameClaim)), "both are still people")


class EveryRelativeIsRead(unittest.TestCase):
    def test_a_second_relative_is_not_dropped(self):
        """The translator emits `relatives[0]` alone and DRL001 guards that
        limit; reproducing it here would state the limit, not the source."""
        d = death(1, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH,
                  deceased=person("Анна"),
                  relatives=[relative(person("Пётр", "Иванов"), Relationship.FATHER),
                             relative(person("Марфа", "Иванова"), Relationship.MOTHER)])
        self.assertEqual(2, len(_one([d], ParentOf)))
