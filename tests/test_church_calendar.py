"""The Julian calendar and the paschalion (`verso.ru.church_calendar`)."""
import unittest
from datetime import date

from dateutil.easter import EASTER_JULIAN, easter

from verso.ru.church_calendar import julian, paschalion
from verso.ru.church_calendar.julian import (
    MONDAY, SATURDAY, SUNDAY, WEDNESDAY, days_between, from_jdn, is_valid, jdn, nearest_occurrence, weekday)
from verso.ru.church_calendar.paschalion import pascha, wedding_ban

#: A Gregorian ordinal plus this is the Julian Day Number of that day.
_ORDINAL_TO_JDN = 1721425


class JulianDayNumbers(unittest.TestCase):
    def test_a_known_date_against_the_gregorian_calendar(self):
        """23 April 1850 O.S. is 5 May 1850 N.S. — twelve days apart."""
        self.assertEqual(jdn(1850, 4, 23), date(1850, 5, 5).toordinal() + _ORDINAL_TO_JDN)

    def test_the_offset_grows_to_thirteen_after_the_century_leap_day(self):
        """1900 is a Julian leap year and a Gregorian common one."""
        self.assertEqual(jdn(1900, 2, 29), date(1900, 3, 13).toordinal() + _ORDINAL_TO_JDN)
        self.assertEqual(jdn(1900, 3, 1), date(1900, 3, 14).toordinal() + _ORDINAL_TO_JDN)

    def test_round_trip_over_the_corpus_years(self):
        for n in range(jdn(1700, 1, 1), jdn(1920, 1, 1)):
            self.assertEqual(jdn(*from_jdn(n)), n)

    def test_29_february_1800_exists(self):
        self.assertTrue(is_valid(1800, 2, 29))
        self.assertEqual(from_jdn(jdn(1800, 2, 29) + 1), (1800, 3, 1))

    def test_31_april_does_not(self):
        self.assertFalse(is_valid(1850, 4, 31))

    def test_weekday_of_new_year_1900(self):
        """1 January 1900 O.S. = 13 January 1900 N.S., a Saturday."""
        self.assertEqual(weekday(1900, 1, 1), SATURDAY)
        self.assertEqual(weekday(1900, 1, 1), date(1900, 1, 13).weekday())

    def test_days_between(self):
        self.assertEqual(days_between((1800, 2, 28), (1800, 3, 1)), 2)
        self.assertEqual(days_between((1801, 2, 28), (1801, 3, 1)), 1)


class NearestOccurrence(unittest.TestCase):
    def test_across_the_new_year(self):
        """A saint of 30 December is two days before a baptism of 1 January."""
        self.assertEqual(nearest_occurrence(12, 30, (1850, 1, 1)), -2)
        self.assertEqual(nearest_occurrence(1, 2, (1849, 12, 31)), 2)

    def test_a_29_february_saint_in_a_common_year_is_kept_on_the_28th(self):
        self.assertEqual(nearest_occurrence(2, 29, (1850, 2, 28)), 0)
        self.assertEqual(nearest_occurrence(2, 29, (1852, 2, 28)), 1)

    def test_a_tie_goes_to_the_earlier_feast(self):
        """Two feasts on either side are the caller's problem; one feast is
        never equidistant from itself, but the rule must be deterministic."""
        self.assertEqual(nearest_occurrence(7, 2, (1850, 7, 2)), 0)


class Pascha(unittest.TestCase):
    def test_agrees_with_dateutil_over_the_corpus(self):
        for year in range(1700, 1918):
            d = easter(year, EASTER_JULIAN)
            self.assertEqual(pascha(year), (d.month, d.day), year)

    def test_1850(self):
        self.assertEqual(pascha(1850), (4, 23))

    def test_pascha_is_a_sunday(self):
        for year in range(1700, 1918):
            self.assertEqual(weekday(year, *pascha(year)), SUNDAY, year)


class WeddingBans(unittest.TestCase):
    def kind(self, y: int, m: int, d: int) -> str | None:
        ban = wedding_ban(y, m, d)
        return ban.kind if ban else None

    def test_clean_monday_1850_opens_great_lent(self):
        """Pascha 23 April 1850 − 48 days = 6 March, a Monday."""
        self.assertEqual(weekday(1850, 3, 6), MONDAY)
        self.assertEqual(self.kind(1850, 3, 6), "great_lent")
        self.assertEqual(self.kind(1850, 3, 5), "cheesefare_week")
        self.assertEqual(self.kind(1850, 2, 27), "cheesefare_week")
        self.assertEqual(self.kind(1850, 2, 26), "meatfare_sunday")

    def test_holy_saturday_and_bright_week(self):
        self.assertEqual(self.kind(1850, 4, 22), "great_lent")
        self.assertEqual(self.kind(1850, 4, 23), "bright_week")
        self.assertEqual(self.kind(1850, 4, 29), "bright_week")

    def test_krasnaya_gorka_is_open(self):
        """Фомино воскресенье, the traditional first wedding day after Pascha."""
        self.assertIsNone(wedding_ban(1850, 4, 30))

    def test_apostles_fast_at_its_shortest(self):
        """The latest Julian Pascha is 25 April, so the fast opens 21 June."""
        latest = max(range(1700, 1918), key=lambda y: pascha(y))
        self.assertEqual(pascha(latest), (4, 25))
        self.assertEqual(self.kind(latest, 6, 21), "apostles_fast")
        self.assertEqual(self.kind(latest, 6, 28), "apostles_fast")
        self.assertNotEqual(self.kind(latest, 6, 20), "apostles_fast")
        self.assertNotEqual(self.kind(latest, 6, 29), "apostles_fast")

    def test_fixed_fasts_and_svyatki(self):
        self.assertEqual(self.kind(1850, 8, 1), "dormition_fast")
        self.assertEqual(self.kind(1850, 8, 14), "dormition_fast")
        self.assertEqual(self.kind(1850, 11, 15), "nativity_fast")
        self.assertEqual(self.kind(1850, 12, 24), "nativity_fast")
        self.assertEqual(self.kind(1850, 12, 25), "svyatki")
        self.assertEqual(self.kind(1851, 1, 6), "svyatki")
        self.assertNotEqual(self.kind(1851, 1, 7), "svyatki")

    def test_one_day_fasts_are_strict(self):
        for m, d in ((8, 29), (9, 14)):
            ban = wedding_ban(1850, m, d)
            assert ban is not None
            self.assertEqual(ban.kind, "one_day_fast")
            self.assertTrue(ban.strict)

    def test_eves_and_weekdays_are_not_strict(self):
        ban = wedding_ban(1850, 9, 7)
        assert ban is not None
        self.assertEqual(ban.kind, "feast_eve")
        self.assertFalse(ban.strict)

    def test_an_ordinary_autumn_week(self):
        """October after Покров, the peasant wedding season: Monday, Wednesday,
        Friday and Sunday are open; Tuesday, Thursday and Saturday are eves."""
        kinds = {weekday(1850, 10, d): self.kind(1850, 10, d) for d in range(8, 15)}
        self.assertIsNone(kinds[MONDAY])
        self.assertIsNone(kinds[WEDNESDAY])
        self.assertIsNone(kinds[SUNDAY])
        self.assertEqual(kinds[julian.TUESDAY], "fast_day_eve")
        self.assertEqual(kinds[julian.THURSDAY], "fast_day_eve")
        self.assertEqual(kinds[SATURDAY], "sunday_eve")

    def test_ascension_eve(self):
        """Ascension is P+39; its eve, P+38, is a Wednesday."""
        eve = from_jdn(jdn(1850, *pascha(1850)) + 38)
        self.assertEqual(weekday(*eve), WEDNESDAY)
        self.assertEqual(self.kind(*eve), "feast_eve")

    def test_labels_are_the_books_words(self):
        self.assertEqual(paschalion.GREAT_LENT.label, "Великий пост")


if __name__ == "__main__":
    unittest.main()
