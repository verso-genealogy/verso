"""A civil birth act states the parents' ages — as of the child's birth.

The extractor reads `father_age=` and `mother_age=` into `AgedYears` dated to the
birth the same record states; a record without a month states no date and so no
age; an author's `source_age_error=` withdraws both; and a burial's age check
compares only what burials state.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from calendar import Month

from verso.ru.consolidation.death_age import find_death_age_conflicts
from verso.ru.domain import person
from verso.ru.dsl.records.births import BirthRecords, birth, christening
from verso.ru.dsl.records.deaths import DeathRecords, death
from verso.ru.facts.checks.births import birth_claims_of
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.model import AgedYears, AssertionSet, FactDate, Persona, Record, Retracted
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative


def _act(num=1, *, year=1924, day: int | None = 14, month=Month.JANUARY, reviewed=True, **kw):
    return birth(num, Gender.MALE, day, None, b_month=month, year=year,
                 child=person("Иван"), father=person("Петр", "Иванов"),
                 mother=person("Мария", "Иванова"), reviewed=reviewed, **kw)


def _facts(*acts, drafts=False):
    return AssertionSet(facts_from_births([(a, "1924/births.py") for a in acts],
                                          village="Горюхино", drafts=drafts))


class ParentsAges(unittest.TestCase):
    def test_a_dated_birth_gives_both_ages_dated_to_it(self):
        ages = _facts(_act(father_age=31, mother_age=30)).of(AgedYears)
        parents = [a for a in ages if a.cite.locator in ("father", "mother")]
        self.assertEqual(["father", "mother"], [a.cite.locator for a in parents])
        self.assertEqual([31, 30], [a.age for a in parents])
        for a in parents:
            self.assertEqual(FactDate(year=1924, month=1, day=14), a.as_of)

    def test_each_age_follows_its_parents_link(self):
        facts = list(facts_from_births([(_act(father_age=31, mother_age=30), "b.py")],
                                       village="Горюхино"))
        kinds = [(type(f).__name__, f.cite.locator) for f in facts
                 if f.cite.locator in ("father", "mother")
                 and type(f).__name__ in ("ParentOf", "AgedYears")]
        self.assertEqual([("ParentOf", "father"), ("AgedYears", "father"),
                          ("ParentOf", "mother"), ("AgedYears", "mother")], kinds)

    def test_a_month_without_a_day_dates_the_month(self):
        a = _act(day=None, father_age=31)
        ages = [x for x in _facts(a).of(AgedYears) if x.cite.locator == "father"]
        self.assertEqual(1, len(ages))
        self.assertEqual(FactDate(year=1924, month=1, day=None), ages[0].as_of)

    def test_no_month_no_age(self):
        a = birth(1, Gender.MALE, 14, None, b_month=None, year=1924, child=person("Иван"),
                  father=person("Петр", "Иванов"), mother=person("Мария", "Иванова"),
                  father_age=31, mother_age=30)
        self.assertEqual([], [x for x in _facts(a).of(AgedYears)
                              if x.cite.locator in ("father", "mother")])

    def test_an_age_not_stated_is_not_asserted(self):
        self.assertEqual([], [x for x in _facts(_act(mother_age=30)).of(AgedYears)
                              if x.cite.locator == "father"])

    def test_the_authors_error_note_withdraws_both(self):
        facts = _facts(_act(father_age=31, mother_age=30, source_age_error="так в акте"))
        ages = [x for x in facts.of(AgedYears) if x.cite.locator in ("father", "mother")]
        self.assertEqual(2, len(ages))
        self.assertTrue(all(isinstance(x.basis, Retracted) for x in ages))
        self.assertEqual([], [x for x in facts.believed().of(AgedYears)
                              if x.cite.locator in ("father", "mother")])

    def test_an_unreviewed_act_asserts_nothing(self):
        act = _act(father_age=31, mother_age=30, reviewed=False)
        self.assertEqual([], list(_facts(act).of(AgedYears)))
        self.assertEqual(2, len(_facts(act, drafts=True).of(AgedYears)))


class AParentsAgeIsNotABurialsAge(unittest.TestCase):
    """A grandfather's act names the father's age at the child's birth: a burial check
    must neither compare it with the father's own birth nor cite a birth as a burial."""

    def _books(self):
        fathers_birth = birth(1, Gender.MALE, 1, None, b_month=Month.MARCH, year=1893,
                              child=person("Петр"), father=person("Иван", "Иванов"),
                              mother=person("Анна", "Иванова"))
        act = self._act(40)
        return fathers_birth, act

    @staticmethod
    def _act(father_age):
        return birth(2, Gender.MALE, 14, None, b_month=Month.JANUARY, year=1924,
                     child=person("Иван"), father=person("Петр", "Иванов"),
                     mother=person("Мария", "Иванова"), father_age=father_age,
                     relatives=[relative(person("Иван", "Иванов"), None, "отца")])

    @staticmethod
    def _burial(age):
        return [(DeathRecords("ЦГА", "1", "1", "2", "Горюхино", "Церковь", 1925, [
            death(1, Gender.MALE, 3, None, d_month=Month.MAY, year=1925,
                  deceased=person("Иван"), age=age,
                  relatives=[relative(person("Петр", "Иванов"), Relationship.FATHER)])]),
                 "1925/deaths.py")]

    @staticmethod
    def _book(*records):
        return [(BirthRecords("ЦГА", "1", "1", "1", "Горюхино", "Церковь", 1924, list(records)),
                 "1924/births.py")]

    def test_a_fitting_burial_next_to_a_parents_age_is_no_finding(self):
        self.assertEqual([], find_death_age_conflicts(self._book(*self._books()), self._burial(1)))

    def test_a_misread_burial_is_one_finding_and_cites_the_act_as_its_birth(self):
        found = find_death_age_conflicts(self._book(*self._books()), self._burial(10))
        self.assertEqual(1, len(found))
        self.assertEqual(("1925/deaths.py", "1924/births.py", "2"),
                         (found[0].death_source, found[0].birth_source, found[0].birth_record))

    def test_a_christenings_age_is_no_burials(self):
        christened = christening(5, Gender.MALE, 20, Month.JANUARY, age=11, year=1924,
                                 child=person("Иван"), father=person("Петр", "Иванов"))
        found = find_death_age_conflicts(self._book(self._books()[1], christened), self._burial(1))
        self.assertTrue(all(f.death_source == "1925/deaths.py" for f in found))
        self.assertEqual([], [f for f in found if f.birth_source != "1924/births.py"])

    def _fathers(self, act):
        facts = _facts(self._books()[0], act)
        # the father's own birth (entry 0, child) and the act's father (entry 1) are one man
        keyed = {a.subject: ("father",) for a in facts
                 if (a.cite.entry, a.cite.locator) in ((0, "child"), (1, "father"))}

        def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
            return lambda who: keyed.get(who, (str(who),))
        return birth_claims_of(facts, identity)

    def test_an_age_fitting_the_fathers_own_birth_is_no_finding(self):
        self.assertEqual([], self._fathers(self._act(31)))

    def test_an_age_not_fitting_it_is_one(self):
        self.assertEqual(1, len(self._fathers(self._act(40))))


class ParentAgesOutOfRange(unittest.TestCase):
    """`check=parent-ages`: the interval a stated age asserts lies wholly outside what a parent can be."""

    @staticmethod
    def _found(**kw):
        from verso.ru.facts.checks.parent_ages import parent_age_findings
        return parent_age_findings(_facts(_act(**kw)).believed())

    def test_a_mother_of_two_is_a_high_finding(self):
        [f] = self._found(mother_age=2)
        self.assertEqual(("mother", 2, "HIGH"), (f.role, f.age, f.confidence))
        self.assertEqual("mother", f.cite.locator)
        self.assertEqual((2.0, 3.0), (round(f.low_years, 6), round(f.high_years, 6)))

    def test_a_reading_age_bounds_cannot_parse_is_no_finding(self):
        for age in ("3…", "2[?](?)", "около 30", "?"):
            self.assertEqual([], self._found(mother_age=age, father_age=age), age)

    def test_the_mother_s_edges(self):
        self.assertEqual([], self._found(mother_age=13))
        self.assertEqual([], self._found(mother_age=50))
        self.assertEqual([], self._found(mother_age=52))
        self.assertEqual(["mother"], [f.role for f in self._found(mother_age=53)])
        self.assertEqual(["mother"], [f.role for f in self._found(mother_age=12)])

    def test_the_father_has_a_floor_and_no_ceiling(self):
        self.assertEqual(["father"], [f.role for f in self._found(father_age=14)])
        self.assertEqual([], self._found(father_age=15))
        self.assertEqual([], self._found(father_age=70))
        self.assertEqual([], self._found(father_age=95))

    def test_both_parents_are_said_apart(self):
        self.assertEqual(["father", "mother"], sorted(f.role for f in self._found(father_age=10, mother_age=60)))

    def test_the_authors_error_note_stands_it_down(self):
        self.assertEqual([], self._found(mother_age=2, father_age=9, source_age_error="так в акте"))

    def test_an_unreviewed_act_on_a_card_says_the_same(self):
        from verso.ru.facts.signals import signals_of
        act = _act(mother_age=2, reviewed=False)
        [s] = signals_of(act, record_id="r1:Горюхино/1-1-1/1924/birth/1", checks=["parent-ages"]).found
        self.assertEqual(("parent-ages", "out_of_range", "mother", "HIGH", "source_age_error"),
                         (s.check, s.variant, s.locator, s.confidence, s.stand_down))
        self.assertEqual("facts.signal.parent_ages.out_of_range_mother", s.key)
        self.assertEqual({"age": "2"}, s.said.params)
        self.assertEqual((), signals_of(_act(mother_age=2, source_age_error="так в акте"),
                                        record_id="x", checks=["parent-ages"]).found)

    def test_a_village_report_is_stable(self):
        from verso.ru.cli.facts import parent_ages_text
        facts = _facts(_act(mother_age=2), _act(2, father_age=40)).believed()
        first = parent_ages_text(facts)
        self.assertEqual(first, parent_ages_text(facts))
        self.assertTrue(first.startswith("parent-ages: 1"), first)


class ParentAgeDrift(unittest.TestCase):
    """`check=parent-age-drift`: two acts of one couple whose stated ages cannot be one pair of lives."""

    @staticmethod
    def _act(num, year, father_age, mother_age, *, father_patronymic=None):
        return birth(num, Gender.MALE, 1, None, b_month=Month.JUNE, year=year,
                     child=person("Иван"), father=person("Пётр", father_patronymic, "Пеночкин"),
                     mother=person("Анна", None, "Пеночкина"), father_age=father_age, mother_age=mother_age)

    def _drift(self, second, *, folded=None, first=None, extra=()):
        from verso.ru.facts.checks.parent_ages import parent_age_drift
        from verso.ru.facts.identity import kin_identity
        acts = [first or self._act(1, 1920, 26, 23), second, *extra]
        facts = _facts(*acts).believed()
        return parent_age_drift(facts, pair=kin_identity(), folded=folded)

    def test_ages_that_move_with_the_years_are_no_finding(self):
        self.assertEqual([], self._drift(self._act(2, 1924, 30, 27)))
        self.assertEqual([], self._drift(self._act(2, 1924, 31, 27)))

    def test_both_parents_far_off_is_high(self):
        found = self._drift(self._act(2, 1924, 38, 38))
        self.assertEqual([("father", "HIGH"), ("mother", "HIGH")], [(f.role, f.confidence) for f in found])
        self.assertTrue(all(f.gap_years > 2.0 for f in found))

    def test_one_parent_far_off_is_low(self):
        [f] = self._drift(self._act(2, 1924, 34, 27))
        self.assertEqual(("father", "LOW"), (f.role, f.confidence))
        self.assertAlmostEqual(3.0, f.gap_years, delta=0.05)
        self.assertEqual(("1", "2"), (f.first.record_num, f.second.record_num))

    def test_fathers_of_different_patronymics_are_no_couple(self):
        first = self._act(1, 1920, 26, 23, father_patronymic="Иванов")
        self.assertEqual([], self._drift(self._act(2, 1924, 38, 38, father_patronymic="Петров"), first=first))

    def test_a_couple_folded_into_one_person_is_birth_claims_business(self):
        def one_person(_record):
            def key(_persona: Persona):
                return ("одно", "", "")
            return key
        self.assertEqual([], self._drift(self._act(2, 1924, 38, 38), folded=one_person))

    def test_three_acts_compare_neighbours_and_one_outlier_is_two_findings(self):
        found = self._drift(self._act(2, 1922, 48, 25), extra=[self._act(3, 1924, 30, 27)])
        self.assertEqual([("father", "1", "2"), ("father", "2", "3")],
                         [(f.role, f.first.record_num, f.second.record_num) for f in found])
        self.assertEqual(1, len({f.couple for f in found}))

    def test_only_the_father_folded_leaves_the_mother_to_this_check(self):
        """A father folded into one person is `birth-claims`'; the mother can still be a namesake."""
        from verso.ru.facts.identity import kin_identity
        fathers = kin_identity()

        def father_only(record):
            of = fathers(record)

            def key(persona: Persona):
                named = of(persona)
                return ("петр", "", "сумин") if named is not None and named[0] == "петр" else None
            return key
        [f] = self._drift(self._act(2, 1924, 38, 38), folded=father_only)
        self.assertEqual(("mother", "LOW"), (f.role, f.confidence))

    def test_opposite_directions_are_low(self):
        """The father reads older, the mother younger, than the years allow: not one lie, so LOW."""
        found = self._drift(self._act(2, 1924, 38, 18))
        self.assertEqual([("father", "LOW"), ("mother", "LOW")], [(f.role, f.confidence) for f in found])

    def test_an_act_stating_one_parent_only_asks_that_role(self):
        found = self._drift(self._act(2, 1924, None, 38))
        self.assertEqual(["mother"], [f.role for f in found])

    def test_an_unreadable_age_is_no_finding_for_its_role(self):
        found = self._drift(self._act(2, 1924, "около 30", 38))
        self.assertEqual(["mother"], [f.role for f in found])

    def test_intervals_that_overlap_are_no_finding(self):
        self.assertEqual([], self._drift(self._act(2, 1921, 26, 23)))
        self.assertEqual([], self._drift(self._act(2, 1920, 26, 23)))

    def test_the_report_names_the_couple_as_the_record_does(self):
        from verso.ru.cli.facts import parent_age_drift_text
        text = parent_age_drift_text(self._drift(self._act(2, 1924, 38, 38)))
        self.assertIn("Пеночкин Петр + Пеночкина Анна", text)

    def test_a_withdrawn_act_is_not_compared(self):
        withdrawn = birth(2, Gender.MALE, 1, None, b_month=Month.JUNE, year=1924, child=person("Иван"),
                          father=person("Пётр", None, "Пеночкин"), mother=person("Анна", None, "Пеночкина"),
                          father_age=38, mother_age=38, source_age_error="так в акте")
        self.assertEqual([], self._drift(withdrawn))

    def test_the_report_groups_by_couple_and_is_stable(self):
        from verso.ru.cli.facts import parent_age_drift_text
        found = self._drift(self._act(2, 1922, 48, 25), extra=[self._act(3, 1924, 30, 27)])
        text = parent_age_drift_text(found)
        self.assertEqual(text, parent_age_drift_text(list(found)))
        self.assertTrue(text.startswith("parent-age-drift: 2 (пар: 1;"), text)
        self.assertEqual(1, sum(1 for line in text.splitlines() if " + " in line))
        self.assertEqual(2, text.count("[LOW]"))


if __name__ == "__main__":
    unittest.main()
