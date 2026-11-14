"""Too long between two dates of one entry — `baptism-lag`, `burial-lag`."""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.cli.facts import format_lags
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.facts.checks.lags import baptism_lags, burial_lags
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.model import AssertionSet
from verso.ru.gender import Gender


def _births(*records) -> AssertionSet:
    return AssertionSet(facts_from_births([(r, "b.py") for r in records],
                                          village="Тестовка")).believed()


def _deaths(*records) -> AssertionSet:
    return AssertionSet(facts_from_deaths([(r, "d.py") for r in records],
                                          village="Тестовка")).believed()


def _born(num: int, b_day: int, k_day: int, b_month: Month, k_month: Month | None = None):
    return birth(num, Gender.MALE, b_day, k_day, b_month, k_month or b_month, year=1850,
                 child=person("Иван"), father=person("Петр", "Иванов"))


def _died(num: int, d_day: int, b_day: int, d_month: Month, b_month: Month | None = None):
    return death(num, Gender.MALE, d_day, b_day, d_month, b_month or d_month, year=1850,
                 deceased=person("Иван"))


class BaptismLag(unittest.TestCase):
    def test_a_week_is_the_custom(self):
        self.assertEqual([], baptism_lags(_births(_born(1, 3, 10, Month.MAY))))

    def test_twelve_days_is_a_finding(self):
        [f] = baptism_lags(_births(_born(1, 3, 15, Month.MAY)))
        self.assertEqual(12, f.days)
        self.assertEqual("LOW", f.confidence)

    def test_a_smaller_day_in_the_next_month_is_high(self):
        """Born the 3rd, christened «the 2nd» — of the month after."""
        [f] = baptism_lags(_births(_born(1, 3, 2, Month.MAY, Month.JUNE)))
        self.assertTrue(f.month_carried)
        self.assertEqual("HIGH", f.confidence)
        self.assertEqual(30, f.days)

    def test_a_christening_before_the_birth_is_date_order_s(self):
        self.assertEqual([], baptism_lags(_births(_born(1, 10, 3, Month.MAY, Month.MAY))))


class BurialLag(unittest.TestCase):
    def test_the_third_day_is_the_custom(self):
        self.assertEqual([], burial_lags(_deaths(_died(1, 3, 6, Month.MARCH))))

    def test_a_week_is_low(self):
        [f] = burial_lags(_deaths(_died(1, 3, 10, Month.MARCH)))
        self.assertEqual((7, "LOW"), (f.days, f.confidence))

    def test_a_month_is_high(self):
        """Died 3 March, buried 1 April."""
        [f] = burial_lags(_deaths(_died(9, 3, 1, Month.MARCH, Month.APRIL)))
        self.assertEqual((29, "HIGH"), (f.days, f.confidence))

    def test_the_report(self):
        text = format_lags(burial_lags(_deaths(_died(9, 3, 1, Month.MARCH, Month.APRIL))),
                           "burial")
        self.assertIn("[HIGH] ум. 03.03.1850, погр. 01.04.1850 — 29 дн.", text)
        self.assertIn("d.py №9", text)


if __name__ == "__main__":
    unittest.main()
