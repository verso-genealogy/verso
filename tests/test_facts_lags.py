"""Too long between two dates of one entry — `baptism-lag`, `burial-lag`."""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.cli.facts import signal_report
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.facts.checks.lags import baptism_lags, burial_lags
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.model import AssertionSet, BaptizedOn, BuriedOn
from verso.ru.gender import Gender


def _births(*records) -> AssertionSet:
    return AssertionSet(facts_from_births([(r, "b.py") for r in records],
                                          village="Тестовка")).believed()


def _deaths(*records) -> AssertionSet:
    return AssertionSet(facts_from_deaths([(r, "d.py") for r in records],
                                          village="Тестовка")).believed()


def _born(num: int, b_day: int, k_day: int, b_month: Month, k_month: Month | None = None, **more):
    return birth(num, Gender.MALE, b_day, k_day, b_month, k_month or b_month, year=1850,
                 child=person("Иван"), father=person("Петр", "Иванов"), **more)


def _died(num: int, d_day: int, b_day: int, d_month: Month, b_month: Month | None = None, **more):
    return death(num, Gender.MALE, d_day, b_day, d_month, b_month or d_month, year=1850,
                 deceased=person("Иван"), **more)


class BaptismLag(unittest.TestCase):
    def test_a_week_is_the_custom(self):
        self.assertEqual([], baptism_lags(_births(_born(1, 3, 10, Month.MAY))).findings)

    def test_twelve_days_is_a_finding(self):
        [f] = baptism_lags(_births(_born(1, 3, 15, Month.MAY))).findings
        self.assertEqual(12, f.days)
        self.assertEqual("LOW", f.confidence)

    def test_a_smaller_day_in_the_next_month_is_high(self):
        """Born the 3rd, christened «the 2nd» — of the month after."""
        [f] = baptism_lags(_births(_born(1, 3, 2, Month.MAY, Month.JUNE))).findings
        self.assertTrue(f.month_carried)
        self.assertEqual("HIGH", f.confidence)
        self.assertEqual(30, f.days)

    def test_a_christening_before_the_birth_is_date_order_s(self):
        self.assertEqual([], baptism_lags(_births(_born(1, 10, 3, Month.MAY, Month.MAY))).findings)


class BurialLag(unittest.TestCase):
    def test_the_third_day_is_the_custom(self):
        self.assertEqual([], burial_lags(_deaths(_died(1, 3, 6, Month.MARCH))).findings)

    def test_a_week_is_low(self):
        [f] = burial_lags(_deaths(_died(1, 3, 10, Month.MARCH))).findings
        self.assertEqual((7, "LOW"), (f.days, f.confidence))

    def test_a_month_is_high(self):
        """Died 3 March, buried 1 April."""
        [f] = burial_lags(_deaths(_died(9, 3, 1, Month.MARCH, Month.APRIL))).findings
        self.assertEqual((29, "HIGH"), (f.days, f.confidence))

    def test_the_report(self):
        text = signal_report("burial-lag", burial_lags(_deaths(_died(9, 3, 1, Month.MARCH, Month.APRIL))))
        self.assertIn("[HIGH] Погребение 01.04.1850 — через 29 дн. после смерти 03.03.1850.", text)
        self.assertIn("d.py №9", text)


class LagNote(unittest.TestCase):
    """`lag_note=`: the two dates were re-read on the scan and stand — the finding is counted, not reported."""

    def test_a_late_christening_with_a_note_is_counted_not_reported(self):
        got = baptism_lags(_births(_born(1, 3, 20, Month.JANUARY, lag_note="так в подлиннике")))
        self.assertEqual(([], 1), (got.findings, got.noted))

    def test_a_late_burial_with_a_note_is_counted_not_reported(self):
        got = burial_lags(_deaths(_died(9, 3, 1, Month.MARCH, Month.APRIL, lag_note="так в подлиннике")))
        self.assertEqual(([], 1), (got.findings, got.noted))

    def test_a_note_withdraws_no_date(self):
        """Unlike `source_date_error=`, the note is no retraction: both dates stay believed."""
        births = _births(_born(1, 3, 20, Month.JANUARY, lag_note="так в подлиннике"))
        deaths = _deaths(_died(9, 3, 1, Month.MARCH, Month.APRIL, lag_note="так в подлиннике"))
        self.assertEqual(1, len(births.of(BaptizedOn)))
        self.assertEqual(1, len(deaths.of(BuriedOn)))

    def test_an_empty_note_is_no_note(self):
        got = baptism_lags(_births(_born(1, 3, 20, Month.JANUARY, lag_note="")))
        self.assertEqual((1, 0), (len(got.findings), got.noted))

    def test_a_note_on_a_timely_christening_counts_nothing(self):
        got = baptism_lags(_births(_born(1, 3, 5, Month.JANUARY, lag_note="так в подлиннике")))
        self.assertEqual(([], 0), (got.findings, got.noted))

    def test_without_a_note_nothing_is_noted(self):
        got = burial_lags(_deaths(_died(9, 3, 1, Month.MARCH, Month.APRIL)))
        self.assertEqual((1, 0), (len(got.findings), got.noted))


if __name__ == "__main__":
    unittest.main()
