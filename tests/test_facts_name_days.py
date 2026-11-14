"""A newborn's name no saint near the birth supports — `check=name-days`."""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.church_calendar.julian import jdn
from verso.ru.church_calendar.svyatcy import Commemorated, Svyatcy
from verso.ru.cli.facts import format_name_days
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, birth_month, birth_records, christening
from verso.ru.facts.checks.name_days import name_day_findings, window
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.model import AssertionSet
from verso.ru.gender import Gender

M, F = Gender.MALE, Gender.FEMALE

_SVYATCY = Svyatcy([
    Commemorated(gender=F, headword="Агапия", name="Агапия", dates=((4, 16),)),
    Commemorated(gender=F, headword="Мария", name="Мария", dates=((4, 1), (7, 22))),
    Commemorated(gender=F, headword="Марина", name="Марина", dates=((7, 17),)),
    Commemorated(gender=M, headword="Иоанн", name="Иоанн", dates=((5, 8),)),
    Commemorated(gender=M, headword="Симеон", name="Симеон", dates=((9, 1),)),
])


def _facts(month: Month, *records) -> AssertionSet:
    book = birth_records("A", "1", "1", "1", "Тестовка", "Никольская", 1850,
                         *birth_month(month, *records))
    for r in book.records:
        if r.year is None:
            r.year = book.year
    return AssertionSet(facts_from_births([(r, "b.py") for r in book.records],
                                          village="Тестовка")).believed()


def _father():
    return person("Петр", "Иванов")


class TheWindow(unittest.TestCase):
    def test_runs_from_three_days_before_birth_past_the_eighth_day(self):
        """Born the 10th, christened the 11th: 7th … 10 + 7 + 3 = 20th."""
        self.assertEqual((jdn(1850, 4, 7), jdn(1850, 4, 20)),
                         window((1850, 4, 10), (1850, 4, 11)))

    def test_a_late_christening_extends_it(self):
        self.assertEqual((jdn(1850, 3, 29), jdn(1850, 4, 23)),
                         window((1850, 4, 1), (1850, 4, 20)))

    def test_without_a_birth_the_christening_is_the_only_anchor(self):
        self.assertEqual((jdn(1850, 4, 13), jdn(1850, 4, 19)),
                         window(None, (1850, 4, 16)))


class Findings(unittest.TestCase):
    def test_a_name_kept_inside_the_window_is_not_a_finding(self):
        facts = _facts(Month.APRIL, birth(1, F, 14, 16, child=person("Агапия"),
                                          father=_father()))
        result = name_day_findings(facts, _SVYATCY)
        self.assertEqual([], result.findings)
        self.assertEqual(1, result.checked)

    def test_the_eighth_day_counts(self):
        """Born 1 May, named on the 8th: Иоанн of 8 May is inside."""
        facts = _facts(Month.MAY, birth(1, M, 1, 2, child=person("Иван"), father=_father()))
        self.assertEqual([], name_day_findings(facts, _SVYATCY).findings)

    def test_a_name_far_from_all_its_saints_is_a_finding(self):
        """Марина born 1 June: the window ends 11 June, her saint is 17 July."""
        facts = _facts(Month.JUNE, birth(1, F, 1, 2, child=person("Марина"),
                                         father=_father()))
        [f] = name_day_findings(facts, _SVYATCY).findings
        self.assertEqual("Марина", f.name)
        self.assertEqual((7, 17), f.nearest)
        self.assertEqual(36, f.outside)

    def test_thirty_days_out_is_not_yet_a_finding(self):
        """Born 14 June: the window ends 24 June, 23 days before 17 July."""
        facts = _facts(Month.JUNE, birth(1, F, 14, 16, child=person("Марина"),
                                         father=_father()))
        self.assertEqual([], name_day_findings(facts, _SVYATCY).findings)

    def test_a_look_alike_kept_in_the_window_makes_it_high(self):
        facts = _facts(Month.APRIL, birth(1, F, 16, 17, child=person("Марина"),
                                          father=_father()))
        [f] = name_day_findings(facts, _SVYATCY).findings
        self.assertEqual([], [n.name for n in f.lookalikes])
        self.assertEqual("LOW", f.confidence)
        facts = _facts(Month.AUGUST, birth(1, M, 28, 29, child=person("Симон"),
                                           father=_father()))
        result = name_day_findings(facts, Svyatcy([
            Commemorated(gender=M, headword="Симон", name="Симон", dates=((5, 10),)),
            Commemorated(gender=M, headword="Симеон", name="Симеон", dates=((9, 1),)),
        ]))
        [f] = result.findings
        self.assertEqual("HIGH", f.confidence)
        self.assertEqual(["Симеон"], [n.name for n in f.lookalikes])

    def test_a_name_the_book_does_not_know_is_counted_apart(self):
        facts = _facts(Month.APRIL, birth(1, F, 14, 16, child=person("Саломея"),
                                          father=_father()))
        result = name_day_findings(facts, _SVYATCY)
        self.assertEqual([], result.findings)
        self.assertEqual(0, result.checked)
        self.assertEqual(1, sum(result.unknown.values()))

    def test_a_christening_entry_is_asked_from_its_one_date(self):
        facts = _facts(Month.APRIL, christening(1, F, 16, age=11, child=person("Агапия"),
                                                father=_father()))
        result = name_day_findings(facts, _SVYATCY)
        self.assertEqual(1, result.checked)
        self.assertEqual([], result.findings)

    def test_calendar_note_stands_the_finding_down(self):
        facts = _facts(Month.JUNE, birth(1, F, 1, 2, child=person("Марина"),
                                         father=_father(),
                                         calendar_note="переснято: Марина, так в подлиннике"))
        result = name_day_findings(facts, _SVYATCY)
        self.assertEqual([], result.findings)
        self.assertEqual(1, result.noted)

    def test_the_report_names_the_look_alike(self):
        facts = _facts(Month.AUGUST, birth(7, M, 28, 29, child=person("Симон"),
                                           father=_father()))
        result = name_day_findings(facts, Svyatcy([
            Commemorated(gender=M, headword="Симон", name="Симон", dates=((5, 10),)),
            Commemorated(gender=M, headword="Симеон", name="Симеон", dates=((9, 1),)),
        ]))
        text = format_name_days(result)
        self.assertIn("[HIGH] Симон (муж), р. 28.08.1850, кр. 29.08.1850", text)
        self.assertIn("в окне поминается: Симеон", text)
        self.assertIn("b.py №7", text)


if __name__ == "__main__":
    unittest.main()
