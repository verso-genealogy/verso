"""Tests for verso.ru.ages.format_age — DSL age → reader-facing Russian prose."""

import unittest

from verso.ru.ages import age_recorded, agree, format_age, split_age


class TestAgree(unittest.TestCase):
    """Russian numeral agreement: 1 год / 3 года / 5 лет."""

    def _year(self, n):
        return agree(n, "год", "года", "лет")

    def test_one_form(self):
        for n in (1, 21, 31, 101, 121):
            with self.subTest(n=n):
                self.assertEqual(self._year(n), "год")

    def test_few_form(self):
        for n in (2, 3, 4, 22, 23, 24, 102):
            with self.subTest(n=n):
                self.assertEqual(self._year(n), "года")

    def test_many_form(self):
        for n in (0, 5, 9, 10, 20, 25, 100, 111):
            with self.subTest(n=n):
                self.assertEqual(self._year(n), "лет")

    def test_teens_take_many_despite_last_digit(self):
        # 11–14 are the classic trap: they end in 1–4 but take «лет».
        for n in (11, 12, 13, 14, 111, 112, 113, 114):
            with self.subTest(n=n):
                self.assertEqual(self._year(n), "лет")


class TestFormatAge(unittest.TestCase):

    def test_integer_years_agree(self):
        cases = {1: "1 год", 2: "2 года", 3: "3 года", 4: "4 года",
                 5: "5 лет", 11: "11 лет", 12: "12 лет", 21: "21 год",
                 22: "22 года", 45: "45 лет", 73: "73 года", 90: "90 лет"}
        for age, expected in cases.items():
            with self.subTest(age=age):
                self.assertEqual(format_age(age), expected)

    def test_absent_values_render_nothing(self):
        # Callers guard on the rendered value, so every "not recorded" spelling
        # must come back as None rather than as the string "None".
        for age in (None, "", "   ", "?", "-"):
            with self.subTest(age=age):
                self.assertIsNone(format_age(age))

    def test_bool_is_not_an_age(self):
        self.assertIsNone(format_age(True))
        self.assertIsNone(format_age(False))

    def test_quoted_number(self):
        self.assertEqual(format_age("70"), "70 лет")
        self.assertEqual(format_age("1"), "1 год")

    def test_sub_year_units_expand_and_agree(self):
        cases = {"1 мес": "1 месяц", "2 мес": "2 месяца", "6 мес": "6 месяцев",
                 "6 м": "6 месяцев", "1 нед": "1 неделя", "3 нед": "3 недели",
                 "5 недель": "5 недель", "1 н": "1 неделя",
                 "3 дн": "3 дня", "1 д": "1 день", "10 дней": "10 дней"}
        for age, expected in cases.items():
            with self.subTest(age=age):
                self.assertEqual(format_age(age), expected)

    def test_compound(self):
        self.assertEqual(format_age("19 лет 6 мес"), "19 лет 6 месяцев")
        self.assertEqual(format_age("1 г 2 мес"), "1 год 2 месяца")
        self.assertEqual(format_age("43 года 11 мес"), "43 года 11 месяцев")

    def test_idioms_pass_through_verbatim(self):
        # Already prose. Re-deriving from the parsed slots would turn every
        # `age="6 мес"` into «полгода», which the source did not say.
        for age in ("полгода", "пол года", "полу года", "полтора года"):
            with self.subTest(age=age):
                self.assertEqual(format_age(age), age)

    def test_six_months_is_not_rewritten_as_an_idiom(self):
        self.assertEqual(split_age("полгода"), ("", "6", "", ""))
        self.assertEqual(format_age("6 мес"), "6 месяцев")

    def test_fractional_years(self):
        self.assertEqual(format_age(0.5), "полгода")
        self.assertEqual(format_age(1.5), "1 год 6 месяцев")
        self.assertEqual(format_age(56.5), "56 лет 6 месяцев")
        self.assertEqual(format_age(2.25), "2 года 3 месяца")

    def test_whole_float_treated_as_integer(self):
        self.assertEqual(format_age(45.0), "45 лет")

    def test_decimal_age_as_a_string(self):
        # Census half-years reach the translator as strings, not floats — the
        # revision lists write "2.5", and Маниловка 1858 writes "34,5".
        self.assertEqual(format_age("0.5"), "полгода")
        self.assertEqual(format_age("2.5"), "2 года 6 месяцев")
        self.assertEqual(format_age("56.5"), "56 лет 6 месяцев")
        self.assertEqual(format_age("34,5"), "34 года 6 месяцев")

    def test_fraction_rounding_carries_into_years(self):
        # .96 of a year rounds to 12 months, which must become a whole year
        # rather than «0 лет 12 месяцев».
        self.assertEqual(format_age(2.96), "3 года")

    def test_unparseable_source_literal_passes_through(self):
        # Faithful 1719 transcriptions («от роду году»), not formatting errors.
        for age in ("году", "полугоду", "с годом"):
            with self.subTest(age=age):
                self.assertEqual(format_age(age), age)


class TestAgeRecorded(unittest.TestCase):
    """«Is there a figure at all?» — not «can it be rendered?»."""

    def test_the_transcribers_placeholders_are_not_ages(self):
        for age in (None, "", "?", "-", "  ?  ", False):
            with self.subTest(age=age):
                self.assertFalse(age_recorded(age))

    def test_a_figure_too_small_to_render_is_still_a_figure(self):
        """0.02 of a year is a week-old infant. `format_age` has no words for
        it and returns None, which is why it cannot answer this question."""
        for age in (0, "0", 0.02, "0.02", "полгода", "году"):
            with self.subTest(age=age):
                self.assertTrue(age_recorded(age))


if __name__ == "__main__":
    unittest.main()
