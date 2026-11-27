"""An age written with a fraction, as a clerk wrote it: «2½», «5½ мес», «17¾».

Every reader of an age — the tabular split, the day interval, the census birth year, the linters — reads
the fraction as the number it is; the prose shown to a reader keeps the book's own form.
"""

import unittest

from verso.ru.ages import DAYS_PER_MONTH, DAYS_PER_YEAR, age_bounds, age_number, format_age, split_age, whole_years
from verso.ru.consolidation.candidates import _age_years
from verso.ru.linters.checks.ages import is_valid_age_string
from verso.ru.linters.checks.census_age import age_years_str
from verso.ru.targets.geni.translator.census_resolvers import _age_to_components, _age_to_years


def some(x: float | None) -> float:
    assert x is not None
    return x


class TestAgeNumber(unittest.TestCase):
    def test_numbers(self):
        for text, number in (("2", 2.0), ("2½", 2.5), ("½", 0.5), ("2¼", 2.25), ("2¾", 2.75),
                             ("⅓", 1 / 3), ("1⅔", 1 + 2 / 3), ("2.5", 2.5), ("2,5", 2.5), (" 17½ ", 17.5)):
            with self.subTest(text=text):
                self.assertAlmostEqual(some(age_number(text)), number)

    def test_not_numbers(self):
        for text in ("", "½½", "2½x", "1/2", "2 ½", "полгода", "-½", "2.5½"):
            with self.subTest(text=text):
                self.assertIsNone(age_number(text))


class TestSplitAge(unittest.TestCase):
    def test_fraction_before_a_unit(self):
        self.assertEqual(split_age("5½ мес"), ("", "5½", "", ""))
        self.assertEqual(split_age("½ года"), ("½", "", "", ""))
        self.assertEqual(split_age("1 г 2½ мес"), ("1", "2½", "", ""))

    def test_bare_fraction_stays_in_years(self):
        self.assertEqual(split_age("2½"), ("2½", "", "", ""))

    def test_junk_stays_verbatim(self):
        self.assertEqual(split_age("2½x мес"), ("2½x мес", "", "", ""))


class TestAgeBounds(unittest.TestCase):
    def test_a_fraction_is_exact(self):
        self.assertEqual(age_bounds("2½"), (2.5 * DAYS_PER_YEAR, 2.5 * DAYS_PER_YEAR))
        self.assertEqual(age_bounds("5½ мес"), (5.5 * DAYS_PER_MONTH, 5.5 * DAYS_PER_MONTH))
        self.assertEqual(age_bounds("½"), (0.5 * DAYS_PER_YEAR, 0.5 * DAYS_PER_YEAR))

    def test_whole_units_keep_their_width(self):
        self.assertEqual(age_bounds("1 г 2 мес"), (DAYS_PER_YEAR + 2 * DAYS_PER_MONTH, DAYS_PER_YEAR + 3 * DAYS_PER_MONTH))


class TestFormatAgeUnchanged(unittest.TestCase):
    """The reader's text stays the book's: a changed rendering would rewrite every document that carries it."""

    def test_verbatim(self):
        for age in ("2½", "17½", "5½ мес", "½ года", "1 г 2½ мес"):
            with self.subTest(age=age):
                self.assertEqual(format_age(age), age)


class TestWholeYears(unittest.TestCase):
    def test_a_fraction_is_no_whole_year(self):
        for age in ("2½", "2½ лет", "½"):
            with self.subTest(age=age):
                self.assertIsNone(whole_years(age))


class TestCensus(unittest.TestCase):
    def test_components(self):
        self.assertEqual(_age_to_components("20½"), (20, 6, 0, 0))
        self.assertEqual(_age_to_components("½"), (0, 6, 0, 0))
        self.assertEqual(_age_to_components("2¾ лет"), (2, 9, 0, 0))
        self.assertEqual(_age_to_components("4½ мес"), (0, 4, 0, 15))

    def test_years(self):
        self.assertAlmostEqual(some(_age_to_years("20½")), 20.5)

    def test_linter_years(self):
        self.assertEqual(age_years_str("20½"), 20)
        self.assertEqual(age_years_str("2½ года"), 2)
        self.assertEqual(age_years_str("6½ мес"), 0)

    def test_linter_reads_a_fraction_whole_or_not_at_all(self):
        for age in ("2 ½ лет", "2.5½ лет", "½½"):
            with self.subTest(age=age):
                self.assertIsNone(age_years_str(age))


class TestNoFractionNoChange(unittest.TestCase):
    """What the readers did with an age that writes no fraction, they still do."""

    def test_float_paths(self):
        self.assertEqual(age_bounds(-1), (-DAYS_PER_YEAR, 0.0))
        self.assertEqual(age_bounds("1e1"), (10 * DAYS_PER_YEAR, 11 * DAYS_PER_YEAR))
        self.assertIsNone(_age_years("34,5"))
        self.assertAlmostEqual(some(_age_years("34.5")), 34.5)
        self.assertEqual(_age_to_components("5."), (5, 0, 0, 0))
        self.assertEqual(_age_to_components("2.5"), (2, 6, 0, 0))
        self.assertEqual(_age_to_components("34,5"), (34, 6, 0, 0))
        self.assertEqual(age_years_str("34,5"), 34)


class TestLinters(unittest.TestCase):
    def test_a_fraction_is_a_valid_age(self):
        for age in ("2½", "½", "17¾", "5½ мес", "1 г 2½ мес", "½ года"):
            with self.subTest(age=age):
                self.assertTrue(is_valid_age_string(age))

    def test_junk_is_not(self):
        for age in ("½½", "2½x", "1/2", "2½ лет 3½ лет"):
            with self.subTest(age=age):
                self.assertFalse(is_valid_age_string(age))


class TestCandidates(unittest.TestCase):
    def test_years(self):
        self.assertAlmostEqual(some(_age_years("2½")), 2.5)
        self.assertAlmostEqual(some(_age_years("6½ мес")), 6.5 / 12)


if __name__ == "__main__":
    unittest.main()
