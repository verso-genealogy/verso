"""A retracted age derives no birth date.

`member(source_age_error=)`, `member(previous_age_error=)` and
`death(source_age_error=)` say that an age the record states is the scribe's
slip. The facts layer has always withdrawn the age and the birth computed from
it; the translator now drops that birth too, so a retraction no longer needs a
twin `ignore` entry in the consolidation config to keep the wrong date off Geni.

What the record SAYS is untouched: the document and the profile's «Возраст»
line still print the age as written.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.core.targets.geni.date import GeniDate
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_month, death_records
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative
from verso.ru.targets.geni.translator import TerraformGenerator

SLIP = "так в сказке; крещение и соседние ревизии дают другое"


def _census(*members, year: int = 1834) -> TerraformGenerator:
    gen = TerraformGenerator()
    gen.add_census_records(census_records(
        "ГАТО", "12", "1", "1", "Тестовка", year,
        household("7", *members)))
    gen.finalize()
    return gen


def _deaths(*records) -> TerraformGenerator:
    gen = TerraformGenerator()
    recs = death_records("TestArchive", "1", "1", "1", "Тестовка", "Никольская",
                         1875, *death_month(Month.MARCH, *records))
    gen.add_death_records(recs)
    gen.finalize()
    return gen


def _births(gen: TerraformGenerator) -> list[GeniDate | None]:
    return [d for dates in gen.emitted_birth_dates().values() for d in dates]


def _only_birth(gen: TerraformGenerator) -> GeniDate | None:
    births = _births(gen)
    assert len(births) == 1, births
    return births[0]


def _outputs(gen: TerraformGenerator) -> str:
    return "\n".join(text for _, text in gen.iter_outputs())


class ARetractedRollLineDerivesNoBirth(unittest.TestCase):
    def test_without_a_retraction_the_previous_age_dates_the_birth(self):
        """The baseline: 1834 − 18 years back to 1816, minus 33."""
        gen = _census(member(1, person("Фока", "Герасимовъ"), CensusRole.HEAD,
                             age=51, previous_age=33))
        self.assertEqual(GeniDate(year=1783, circa=True), _only_birth(gen))

    def test_source_age_error_drops_the_birth(self):
        gen = _census(member(1, person("Фока", "Герасимовъ"), CensusRole.HEAD,
                             age=51, previous_age=33, source_age_error=SLIP))
        self.assertIsNone(_only_birth(gen))

    def test_it_drops_a_typed_birth_date_too(self):
        """The facts layer withdraws the line's BornOn as well — a date the
        clerk wrote on the same line stands or falls with its ages."""
        gen = _census(member(1, person("Прокопий"), CensusRole.HEAD, age=45,
                             previous_age=25, birth_day=19,
                             birth_month=Month.AUGUST, birth_year=1805,
                             source_age_error=SLIP), year=1850)
        self.assertIsNone(_only_birth(gen))

    def test_the_document_still_prints_the_age(self):
        plain = _outputs(_census(member(1, person("Фока", "Герасимовъ"),
                                        CensusRole.HEAD, age=51, previous_age=33)))
        retracted = _outputs(_census(member(1, person("Фока", "Герасимовъ"),
                                            CensusRole.HEAD, age=51, previous_age=33,
                                            source_age_error=SLIP)))
        self.assertIn("Возраст: 51 год", retracted)
        self.assertEqual(plain.count("51"), retracted.count("51"))
        self.assertEqual(plain.count("33"), retracted.count("33"))


class ARetractedPreviousAgeFallsBackToTheCurrentOne(unittest.TestCase):
    def test_the_current_age_dates_the_birth_instead(self):
        """A head listed «15 → 37» in 1850, the 15 carried from an earlier roll."""
        gen = _census(member(1, person("Тихонъ"), CensusRole.HEAD, age=37,
                             previous_age=15, previous_age_error=SLIP), year=1850)
        self.assertEqual(GeniDate(year=1813, circa=True), _only_birth(gen))

    def test_a_copied_age_leaves_nothing_to_date_by(self):
        """One figure in both columns is the previous revision's age alone."""
        gen = _census(member(1, person("Лука"), CensusRole.HEAD, age=22,
                             previous_age=22, departure_year=1821,
                             departure_reason="отдан в рекруты",
                             previous_age_error=SLIP))
        self.assertIsNone(_only_birth(gen))

    def test_a_typed_birth_year_is_not_the_previous_age(self):
        gen = _census(member(1, person("Лука"), CensusRole.HEAD, age=37,
                             previous_age=15, birth_year=1813,
                             previous_age_error=SLIP), year=1850)
        self.assertEqual(GeniDate(year=1813, circa=True), _only_birth(gen))


class ARetractedBurialAgeDerivesNoBirth(unittest.TestCase):
    def _death(self, **kw):
        return death(6, Gender.MALE, 11, 13, Month.MARCH, Month.MARCH,
                     deceased=person("Власий"), age=3,
                     relatives=[relative(person("Тимон", "Игнатьевъ"), Relationship.FATHER)], **kw)

    def test_without_a_retraction_the_age_dates_the_birth(self):
        births = _births(_deaths(self._death()))
        self.assertIn(GeniDate(month=3, year=1872, circa=True), births)

    def test_source_age_error_drops_the_deceased_birth(self):
        births = _births(_deaths(self._death(source_age_error=SLIP)))
        self.assertNotIn(GeniDate(month=3, year=1872, circa=True), births)

    def test_and_the_parents_bound_falls_back_to_the_record_year(self):
        """A parent is bounded by the deceased's estimated birth — `between
        1812 and 1857` off a child of 3. With the age withdrawn only the
        record year bounds him, as for a burial that states no age at all."""
        def parent(**kw):
            dated = [d for d in _births(_deaths(self._death(**kw)))
                     if d is not None and d.synthetic]
            self.assertEqual(1, len(dated), dated)
            return dated[0]

        plain = parent()
        self.assertEqual(("between", 1812, 1857),
                         (plain.date_range, plain.year, plain.end_year))
        retracted = parent(source_age_error=SLIP)
        self.assertEqual(("before", 1860), (retracted.date_range, retracted.year))

    def test_the_document_still_prints_the_age(self):
        retracted = _outputs(_deaths(self._death(source_age_error=SLIP)))
        self.assertIn("Возраст: 3 года", retracted)


class ANamesakeIsNotARetraction(unittest.TestCase):
    """`death(namesake=)`: the age is right and the burial is of a second
    child of that name. It stands `death-age-check` down and nothing else."""

    def _death(self, **kw):
        return death(4, Gender.FEMALE, 9, 11, Month.MARCH, Month.MARCH,
                     deceased=person("Агафья"), age="1 мес",
                     relatives=[relative(person("Савва", "Леонтьевъ"), Relationship.FATHER)], **kw)

    def test_the_age_still_dates_the_birth(self):
        plain = _births(_deaths(self._death()))
        namesake = _births(_deaths(self._death(namesake="погребена тёзка")))
        self.assertEqual([vars(d) if d else None for d in plain],
                         [vars(d) if d else None for d in namesake])

    def test_the_facts_layer_still_believes_the_age(self):
        from verso.ru.facts.extract.deaths import facts_from_deaths
        from verso.ru.facts.model import AgedYears, AssertionSet
        recs = death_records("TestArchive", "1", "1", "1", "Тестовка", "Никольская",
                             1875, *death_month(Month.MARCH,
                                                self._death(namesake="тёзка")))
        for r in recs.records:
            r.year = r.year or recs.year
        facts = AssertionSet(facts_from_deaths([(r, "d.py") for r in recs.records],
                                               village="Тестовка"))
        self.assertEqual(1, len(facts.believed().of(AgedYears)))


if __name__ == "__main__":
    unittest.main()


class WhatARetractionWithholds(unittest.TestCase):
    """`withheld_member_birth` names the date a retraction took away."""

    def _withheld(self, **kw) -> tuple[GeniDate, str] | None:
        from verso.ru.targets.geni.translator.member_birth import withheld_member_birth
        return withheld_member_birth(
            member(1, person("Фока"), CensusRole.HEAD, **kw),
            year=1834, page_month=None, page_day=None)

    def test_a_whole_line_retraction(self):
        self.assertEqual((GeniDate(year=1783, circa=True), "source_age_error"),
                         self._withheld(age=51, previous_age=33, source_age_error=SLIP))

    def test_a_previous_age_retraction_that_moved_the_date(self):
        self.assertEqual((GeniDate(year=1803, circa=True), "previous_age_error"),
                         self._withheld(age=35, previous_age=13, previous_age_error=SLIP))

    def test_nothing_when_the_date_did_not_move(self):
        """A typed birth year dates the line either way."""
        self.assertIsNone(self._withheld(age=37, previous_age=15, birth_year=1813,
                                         previous_age_error=SLIP))

    def test_nothing_without_a_retraction(self):
        self.assertIsNone(self._withheld(age=51, previous_age=33))


class AnIgnoreThatRepeatsARetractionIsNamed(unittest.TestCase):
    """RIG001 says WHY: the `ignore` repeats a retraction on a folded record."""

    def _findings(self, ignored: GeniDate):
        from verso.ru.targets.geni.translator import Consolidation
        line = member(1, person("Фока", "Герасимовъ"), CensusRole.HEAD,
                      age=51, previous_age=33, source_age_error=SLIP)
        res_name = next(iter(_census(line).emitted_birth_dates()))
        entry = {"first_name": "", "middle_name": "", "last_name": "",
                 "birth_last_name": "", "title": "", "birth.date": ignored,
                 "death.date": None, "baptism.date": None, "burial.date": None}
        gen = TerraformGenerator(consolidation=Consolidation(
            profile_move_list={res_name: "canon"},
            profile_ignores={"canon": [entry]}))
        gen.add_census_records(census_records(
            "ГАТО", "12", "1", "1", "Тестовка", 1834, household("7", line)))
        gen.finalize()
        return res_name, gen.redundant_ignores

    def test_the_report_names_the_retraction_and_the_record(self):
        res_name, findings = self._findings(GeniDate(year=1783, circa=True))
        self.assertEqual(1, len(findings))
        self.assertIn("source_age_error", findings[0].because)
        self.assertIn(res_name, findings[0].because)

    def test_a_dead_ignore_no_retraction_explains_stays_bare(self):
        _, findings = self._findings(GeniDate(year=1700, circa=True))
        self.assertEqual(1, len(findings))
        self.assertEqual("", findings[0].because)

    def test_the_reason_reaches_the_report(self):
        from verso.core.targets.geni.redundant_ignores import format_redundant_ignore_report
        _, findings = self._findings(GeniDate(year=1783, circa=True))
        report = format_redundant_ignore_report(findings)
        self.assertIn("canon[0] declares birth.date — the date is already withheld by "
                      "`source_age_error=`", report)
