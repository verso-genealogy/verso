"""The cross-record age check, by construction.

Since 2026-09-28 this IS `make death-age-check`: `death_age.find_death_age_conflicts`
reads the entries and hands the assertions to `stated_age_findings`. Before the
switch the two implementations matched byte for byte, text and JSON, on all five
villages (Горюхино 70, Заманиловка 103, Нижняя Яичница 3, Глуповы Горы 3,
Маниловка 2). These pin the behaviour the report rests on; `tests/test_death_age.py`
drives the same path through the report's own entry point.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.facts.checks.stated_age import stated_age_findings
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, birth_month, birth_records
from verso.ru.dsl.records.deaths import death, death_month, death_records
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.model import AgedYears, AssertionSet
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative

DAD = ("Пётр", "Ивановъ")


def _facts(*, born_day: int, born_month: Month, born_year: int,
           died_day: int, died_month: Month, died_year: int,
           age: object, child: str = "Анна",
           extra_births: tuple[object, ...] = (),
           source_age_error: str | None = None,
           namesake: str | None = None,
           relationship: Relationship = Relationship.FATHER) -> AssertionSet:
    b = birth_records("A", "1", "1", "1", "Тестовка", "Никольская", born_year,
                      *birth_month(born_month,
                                   birth(1, Gender.FEMALE, born_day, None,
                                         child=person(child),
                                         father=person(*DAD)),
                                   *extra_births))
    d = death_records("A", "1", "1", "1", "Тестовка", "Никольская", died_year,
                      *death_month(died_month,
                                   death(9, Gender.FEMALE, died_day, died_day,
                                         died_month, died_month,
                                         deceased=person(child), age=age,
                                         source_age_error=source_age_error,
                                         namesake=namesake,
                                         relatives=[relative(person(*DAD),
                                                             relationship)])))
    for rec in list(b.records) + list(d.records):
        if rec.year is None:
            rec.year = b.year if rec in b.records else d.year
    return AssertionSet(
        list(facts_from_births([(r, "b.py") for r in b.records], village="Тестовка"))
        + list(facts_from_deaths([(r, "d.py") for r in d.records], village="Тестовка")))


def _run(facts: AssertionSet):
    """The check as `make facts-check` wires it — not a copy of the wiring,
    which is what would drift from it."""
    return stated_age_findings(facts)


class AgreementIsSilence(unittest.TestCase):
    def test_an_age_that_fits_is_not_reported(self):
        facts = _facts(born_day=10, born_month=Month.MARCH, born_year=1890,
                       died_day=20, died_month=Month.MARCH, died_year=1895, age=5)
        self.assertEqual([], _run(facts))

    def test_a_truncated_age_is_read_as_the_interval_it_asserts(self):
        """«1 годъ» means [1, 2) years — comparing a point would report the
        clerk's own truncation as an error."""
        facts = _facts(born_day=1, born_month=Month.JANUARY, born_year=1890,
                       died_day=1, died_month=Month.NOVEMBER, died_year=1891,
                       age=1)
        self.assertEqual([], _run(facts))


class DisagreementIsReported(unittest.TestCase):
    def test_years_written_where_months_were_meant(self):
        """A bare «4» four months after the christening: the per-дело unit
        convention does not hold for that year."""
        facts = _facts(born_day=10, born_month=Month.MARCH, born_year=1894,
                       died_day=20, died_month=Month.JULY, died_year=1894, age=4)
        found = _run(facts)
        self.assertEqual(1, len(found))
        self.assertEqual("HIGH", found[0].confidence)

    def test_an_age_an_order_of_magnitude_off_is_a_namesake_not_a_misreading(self):
        """No slip of the pen turns eleven months into thirty-three years."""
        facts = _facts(born_day=10, born_month=Month.MARCH, born_year=1860,
                       died_day=20, died_month=Month.JULY, died_year=1893,
                       age="11 мес")
        found = _run(facts)
        self.assertEqual(1, len(found))
        self.assertEqual("LOW", found[0].confidence)


class OnlyAParentPairs(unittest.TestCase):
    def test_a_wife_is_not_set_against_her_husbands_daughter(self):
        """A woman of fifty buried as a WIFE, against the birth of her daughter
        of the same name — linked only through the husband, who is the girl's
        father. The same two records through a father are a finding;
        through a husband they are two people."""
        def burial(relationship: Relationship) -> AssertionSet:
            return _facts(born_day=1, born_month=Month.FEBRUARY, born_year=1880,
                          died_day=20, died_month=Month.JANUARY, died_year=1903,
                          age=50, relationship=relationship)
        self.assertEqual(1, len(_run(burial(Relationship.FATHER))))
        self.assertEqual([], _run(burial(Relationship.HUSBAND)))


class TheAuthorCanStandItDown(unittest.TestCase):
    def test_a_retracted_age_produces_no_finding(self):
        """`source_age_error` withdraws the age itself — the rule needs no
        special case, because `believed()` never hands it over."""
        facts = _facts(born_day=10, born_month=Month.MARCH, born_year=1894,
                       died_day=20, died_month=Month.JULY, died_year=1894, age=4,
                       source_age_error="сверено по скану, так в подлиннике")
        self.assertEqual([], _run(facts))

    def test_a_namesake_burial_produces_no_finding(self):
        """`namesake` says the age is RIGHT and the burial is of a second child
        of that name, whose christening the corpus does not hold.
        `death-age-check` stands down on it; so must its re-statement."""
        facts = _facts(born_day=10, born_month=Month.MARCH, born_year=1894,
                       died_day=20, died_month=Month.JULY, died_year=1896,
                       age="1 мес",
                       namesake="возраст сверен по скану — погребена вторая дочь")
        self.assertEqual([], _run(facts))

    def test_a_namesake_age_is_not_a_retraction(self):
        """The age still stands and still dates the birth, so it stays in
        `believed()` for every other reader — modelling a namesake as a
        `Retracted` age would silence the check and drop the birth with it."""
        facts = _facts(born_day=10, born_month=Month.MARCH, born_year=1894,
                       died_day=20, died_month=Month.JULY, died_year=1896,
                       age="1 мес", namesake="погребена вторая дочь")
        ages = facts.believed().of(AgedYears)
        self.assertEqual(["1 мес"], [a.age for a in ages])


class NamedKinIsNotAParent(unittest.TestCase):
    def test_a_father_in_law_does_not_pair_a_burial_with_a_birth(self):
        """A kinship the source NAMES and which is not parenthood — свекор,
        зять, мачеха — relates the two and says nobody descends from anybody.
        Paired through a свекор, Анна's burial would be set against the birth
        of a same-named girl whose father shares his name."""
        def burial(relationship: Relationship) -> AssertionSet:
            return _facts(born_day=10, born_month=Month.MARCH, born_year=1894,
                          died_day=20, died_month=Month.JULY, died_year=1894,
                          age=4, relationship=relationship)
        self.assertEqual(1, len(_run(burial(Relationship.FATHER))))
        self.assertEqual([], _run(burial(Relationship.FATHER_IN_LAW)))


class ReusedNames(unittest.TestCase):
    def test_one_fitting_candidate_clears_the_record(self):
        """A family that gave the name twice: the burial belongs to whichever
        birth fits, so only a burial fitting NONE of them is a finding."""
        second = birth_month(Month.MARCH,
                             birth(2, Gender.FEMALE, 10, None,
                                   child=person("Анна"), father=person(*DAD)))
        facts = _facts(born_day=10, born_month=Month.MARCH, born_year=1890,
                       died_day=20, died_month=Month.MARCH, died_year=1895,
                       age=5, extra_births=tuple(second))
        self.assertEqual([], _run(facts))
