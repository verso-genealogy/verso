"""Ages at the wedding the law or the family cannot hold — `check=wedding-ages`."""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.cli.facts import format_wedding_ages
from verso.ru.domain import person
from verso.ru.dsl.records.marriages import marriage
from verso.ru.facts.checks.wedding_ages import minimum_age, wedding_age_findings
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import AssertionSet, FactDate


def _facts(year: int, groom_age: int | str, bride_age: int | str, **more) -> AssertionSet:
    rec = marriage(1, 20, Month.OCTOBER, person("Иван", "Петров"), person("Анна", "Ильина"),
                   groom_age=groom_age, bride_age=bride_age, **more)
    rec.year = year
    return AssertionSet(facts_from_marriages([(rec, "m.py")], village="Тестовка")).believed()


class TheMinimumFollowsTheDecrees(unittest.TestCase):
    def test_by_date(self):
        self.assertIsNone(minimum_age(FactDate(year=1760, month=5, day=1), "groom"))
        self.assertEqual(15, minimum_age(FactDate(year=1800, month=5, day=1), "groom"))
        self.assertEqual(13, minimum_age(FactDate(year=1800, month=5, day=1), "bride"))
        self.assertEqual(15, minimum_age(FactDate(year=1830, month=7, day=18), "groom"))
        self.assertEqual(18, minimum_age(FactDate(year=1830, month=7, day=19), "groom"))
        self.assertEqual(16, minimum_age(FactDate(year=1850, month=1, day=1), "bride"))


class UnderAge(unittest.TestCase):
    def test_the_half_year_the_books_allow(self):
        self.assertEqual([], wedding_age_findings(_facts(1885, "17 лет 6 мес", 18)).findings)
        self.assertEqual([], wedding_age_findings(_facts(1905, 17, 15)).findings)

    def test_further_short_is_a_finding(self):
        [f] = wedding_age_findings(_facts(1888, "17 л 3 мес", 18)).findings
        self.assertEqual(("under_age", "groom", 18, "HIGH"),
                         (f.kind, f.role, f.minimum, f.confidence))

    def test_before_1830_a_groom_of_sixteen_is_of_age(self):
        self.assertEqual([], wedding_age_findings(_facts(1820, 16, 14)).findings)

    def test_before_1774_nothing_is_asked(self):
        self.assertEqual([], wedding_age_findings(_facts(1760, 12, 11)).findings)


class AgeGap(unittest.TestCase):
    def test_fifteen_years_is_the_corpus_s_widest_and_fine(self):
        self.assertEqual([], wedding_age_findings(_facts(1891, 32, 17)).findings)

    def test_past_twenty_is_low(self):
        [f] = wedding_age_findings(_facts(1891, 50, 22)).findings
        self.assertEqual(("age_gap", 28.0, "LOW"), (f.kind, f.gap_years, f.confidence))

    def test_the_report(self):
        text = format_wedding_ages(wedding_age_findings(_facts(1888, "17 л 3 мес", 18)).findings)
        self.assertIn("[HIGH] 20.10.1888, жених «17 л 3 мес» — моложе 18", text)
        self.assertIn("m.py №1", text)


class AgeNote(unittest.TestCase):
    """`age_note=`: the ages were re-read on the scan and stand — the entry's findings are counted, not reported."""

    def test_an_under_age_groom_with_a_note_is_counted_not_reported(self):
        got = wedding_age_findings(_facts(1850, 16, 18, age_note="так в подлиннике"))
        self.assertEqual(([], 1), (got.findings, got.noted))

    def test_one_note_stands_down_every_finding_of_the_entry(self):
        """A groom of 50 and a bride of 14 in 1850: she is under age and they are far apart."""
        self.assertEqual(2, len(wedding_age_findings(_facts(1850, 50, 14)).findings))
        got = wedding_age_findings(_facts(1850, 50, 14, age_note="так в подлиннике"))
        self.assertEqual(([], 2), (got.findings, got.noted))

    def test_a_note_withdraws_no_age(self):
        from verso.ru.facts.model import AgedYears
        self.assertEqual(2, len(_facts(1850, 16, 18, age_note="так в подлиннике").of(AgedYears)))

    def test_an_empty_note_is_no_note(self):
        got = wedding_age_findings(_facts(1850, 16, 18, age_note=""))
        self.assertEqual((1, 0), (len(got.findings), got.noted))


if __name__ == "__main__":
    unittest.main()
