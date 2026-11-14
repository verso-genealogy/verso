"""TDD for months/weeks/days-aware age → birth-date arithmetic.

Covers the shared helpers in verso.ru.targets.geni.translator.census_resolvers:
  - _age_to_components: parse an age value to (years, months, weeks, days)
  - _age_to_years:      weeks/days-aware float
  - _birth_date_from_age: calendar-correct (ref_date − age) → (year, month, day)
"""
import unittest

from verso.ru.targets.geni.translator.census_resolvers import (
    _age_to_components, _age_to_years, _birth_date_from_age)


class TestAgeToComponents(unittest.TestCase):
    def test_compound_years_months(self):
        self.assertEqual(_age_to_components("14 лет 4 мес"), (14, 4, 0, 0))

    def test_weeks_only(self):
        self.assertEqual(_age_to_components("5 нед"), (0, 0, 5, 0))

    def test_days_only(self):
        self.assertEqual(_age_to_components("10 дн"), (0, 0, 0, 10))

    def test_bare_int(self):
        self.assertEqual(_age_to_components(55), (55, 0, 0, 0))

    def test_fractional_year_splits_to_months(self):
        # The death path relies on 1.5 → 1 year + 6 months.
        self.assertEqual(_age_to_components(1.5), (1, 6, 0, 0))

    def test_unparseable_is_none(self):
        self.assertIsNone(_age_to_components("?"))
        self.assertIsNone(_age_to_components(None))


class TestAgeToYearsWeeksDaysAware(unittest.TestCase):
    def _years(self, age) -> float:
        v = _age_to_years(age)
        self.assertIsNotNone(v)
        assert v is not None  # narrow for the type checker
        return v

    def test_weeks_contribute(self):
        self.assertAlmostEqual(self._years("1 нед"), 7 / 365.25, places=4)

    def test_days_contribute(self):
        self.assertAlmostEqual(self._years("10 дн"), 10 / 365.25, places=4)

    def test_years_plus_weeks(self):
        self.assertAlmostEqual(self._years("1 год 26 нед"), 1 + 26 * 7 / 365.25, places=3)

    def test_months_still_work(self):
        self.assertAlmostEqual(self._years("6 мес"), 0.5, places=3)

    def test_bare_int(self):
        self.assertEqual(_age_to_years(55), 55.0)

    def test_unparseable_is_none(self):
        self.assertIsNone(_age_to_years("?"))


class TestBirthDateFromAge(unittest.TestCase):
    def test_years_and_months_yield_year_month_no_day(self):
        # 1857-11-06 − 14y4m = 1843-07-06 → drop the (spurious) day.
        self.assertEqual(_birth_date_from_age(1857, 11, 6, "14 лет 4 мес"), (1843, 7, None))

    def test_interval_under_one_month_keeps_day(self):
        # 1857-11-06 − 3 нед (21 days, < 1 month) = 1857-10-16 → keep the day.
        self.assertEqual(_birth_date_from_age(1857, 11, 6, "3 нед"), (1857, 10, 16))
        # 10 дн (< 1 month): 1857-11-06 − 10 = 1857-10-27.
        self.assertEqual(_birth_date_from_age(1857, 11, 6, "10 дн"), (1857, 10, 27))

    def test_interval_at_least_one_month_drops_day(self):
        # 5 нед (35 days ≥ 1 month) → year+month only, no day.
        self.assertEqual(_birth_date_from_age(1857, 11, 6, "5 нед"), (1857, 10, None))
        # 3 мес → months present → not < 1 month → no day.
        self.assertEqual(_birth_date_from_age(1857, 11, 6, "3 мес"), (1857, 8, None))

    def test_whole_years_yield_year_only(self):
        # A bare-year age carries no month info — don't fabricate the census
        # month onto the birth: 1857 − 55 = 1802, year only.
        self.assertEqual(_birth_date_from_age(1857, 11, 6, 55), (1802, None, None))

    def test_year_only_reference_gives_year_only(self):
        # No reference month → can't compute a month; floor the age in years.
        self.assertEqual(_birth_date_from_age(1857, None, None, "3 мес"), (1857, None, None))
        self.assertEqual(_birth_date_from_age(1857, None, None, "14 лет 4 мес"), (1843, None, None))

    def test_month_without_day_reference_no_day_even_when_short(self):
        # ref has month but no day → day proxy is meaningless, so omit it.
        self.assertEqual(_birth_date_from_age(1857, 11, None, "5 нед"), (1857, 10, None))

    def test_bare_year_keeps_ref_month_for_death_legacy(self):
        # Death records keep the (death) month for bare-year ages as legacy
        # parity: died May 1812 aged 45 → circa May 1767.
        self.assertEqual(
            _birth_date_from_age(1812, 5, 6, 45, bare_year_keeps_ref_month=True),
            (1767, 5, None),
        )
        # Census (default) drops it.
        self.assertEqual(_birth_date_from_age(1812, 5, 6, 45), (1767, None, None))

    def test_unparseable_is_none(self):
        self.assertIsNone(_birth_date_from_age(1857, 11, 6, "?"))


if __name__ == "__main__":
    unittest.main()
