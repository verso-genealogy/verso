import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.deaths_burial_date as check_deaths_burial_date


def _deaths(*blocks: str, year: int = 1890) -> str:
    """Wrap month blocks (or bare death() calls) in a death_records call."""
    body = ",\n".join(blocks)
    return (
        f'death_records("a", "f", "i", "c", "Заманиловка", "Церковь", {year},\n'
        f"{body})\n"
    )


def _block(month: str, *death_lines: str) -> str:
    body = ",\n".join(f"                 {d}" for d in death_lines)
    return f"    *death_month({month},\n{body})"


class TestCheckDeathsBurialDate(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_deaths_burial_date.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _structured(self, src: str) -> list[dict[str, object]]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_deaths_burial_date.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()

    # --- DBD001: the three shapes the facts layer found on 2026-09-22 -------

    def test_swapped_days_in_one_month(self):
        """A death as first read: «померъ 9 | погребенъ 8»."""
        src = _deaths(_block("Month.JANUARY", "death(1, Gender.MALE, 9, 8)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD001]", errors[0])
        self.assertIn("burial 8 JANUARY precedes death 9 JANUARY", errors[0])

    def test_month_override_on_the_wrong_side(self):
        """The override sat on d_month, so b_month inherited the block and the
        burial fell a month before the death."""
        src = _deaths(_block(
            "Month.AUGUST",
            "death(3, Gender.FEMALE, 30, 1, d_month=Month.SEPTEMBER)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD001]", errors[0])
        self.assertIn("burial 1 AUGUST precedes death 30 SEPTEMBER", errors[0])
        self.assertIn("b_month still inherits Month.AUGUST", errors[0])

    def test_the_override_moved_to_b_month_is_clean(self):
        src = _deaths(_block(
            "Month.AUGUST",
            "death(3, Gender.FEMALE, 30, 1, b_month=Month.SEPTEMBER)"))
        self.assertEqual(self._check(src), [])

    def test_next_month_burial_not_expressed(self):
        """Died 31 August, buried 1 September."""
        src = _deaths(_block("Month.AUGUST", "death(7, Gender.FEMALE, 31, 1)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD001]", errors[0])
        self.assertIn("b_month=Month.SEPTEMBER", errors[0])

    def test_next_month_burial_stated_is_clean(self):
        src = _deaths(_block(
            "Month.AUGUST",
            "death(57, Gender.FEMALE, 31, 1, b_month=Month.SEPTEMBER)"))
        self.assertEqual(self._check(src), [])

    def test_explicit_burial_month_before_the_death_month(self):
        src = _deaths(_block(
            "Month.MAY", "death(3, Gender.MALE, 2, 28, b_month=Month.APRIL)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("burial 28 APRIL precedes death 2 MAY", errors[0])

    def test_month_order_alone_when_the_burial_day_is_missing(self):
        """No burial day, but the inherited month still dates the burial —
        to the whole of August, every day of which precedes 2 September."""
        src = _deaths(_block(
            "Month.AUGUST",
            "death(6, Gender.FEMALE, 2, None, d_month=Month.SEPTEMBER)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("burial AUGUST precedes death 2 SEPTEMBER", errors[0])

    def test_positional_months_are_read(self):
        src = _deaths(_block(
            "Month.JANUARY",
            "death(1, Gender.MALE, 9, 8, Month.JANUARY, Month.FEBRUARY)"))
        self.assertEqual(self._check(src), [])

    def test_explicit_none_month_inherits_like_the_dsl(self):
        """`death_month_year` fills a month only when it is None, so an
        explicit None is the same as leaving it out."""
        src = _deaths(_block(
            "Month.JANUARY", "death(1, Gender.MALE, 9, 8, b_month=None)"))
        self.assertEqual(len(self._check(src)), 1)

    def test_death_month_year_block(self):
        src = _deaths(
            "    *death_month_year(Month.MARCH, 1889,\n"
            "                      death(1, Gender.MALE, 9, 8))")
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD001]", errors[0])

    def test_same_day_and_later_burial_are_clean(self):
        src = _deaths(_block(
            "Month.JANUARY",
            "death(1, Gender.MALE, 9, 9)",
            "death(2, Gender.MALE, 9, 11)",
            "death(3, Gender.MALE, 9, None)",
            "death(4, Gender.MALE, None, 3)",
            "death(5, Gender.MALE)"))
        self.assertEqual(self._check(src), [])

    def test_unknown_month_cannot_order(self):
        """In a `death_month(None, …)` block «9 | 8» may be a burial in the
        next month — with no month there is nothing to compare."""
        src = _deaths(_block("None", "death(1, Gender.MALE, 9, 8)"))
        self.assertEqual(self._check(src), [])

    def test_zero_day_means_not_recorded(self):
        """A death carrying b_day=0: an empty column, not a day nought that
        precedes every real day of the month."""
        src = _deaths(_block("Month.MAY", "death(4, Gender.MALE, 29, 0)"))
        self.assertEqual(self._check(src), [])

    def test_death_outside_any_month_block(self):
        src = _deaths(
            "    death(1, Gender.MALE, 9, 8, d_month=Month.MAY, b_month=Month.MAY)")
        self.assertEqual(len(self._check(src)), 1)
        src = _deaths("    death(1, Gender.MALE, 9, 8)")
        self.assertEqual(self._check(src), [])

    # --- the year boundary -------------------------------------------------

    def test_january_burial_after_a_december_death(self):
        """One `year` serves both dates, so a January burial reads as January
        of the SAME year — eleven months before the death. Flagged, with the
        way out that does not state a false date."""
        src = _deaths(_block(
            "Month.DECEMBER",
            "death(1, Gender.MALE, 31, 2, b_month=Month.JANUARY)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD001]", errors[0])
        self.assertIn("one year for both dates", errors[0])
        self.assertIn("comment=", errors[0])

    def test_december_block_does_not_advise_b_month_january(self):
        """`b_month=Month.JANUARY` would only move the burial to January of
        the same year — the advice has to be the year-boundary one."""
        src = _deaths(_block("Month.DECEMBER", "death(1, Gender.MALE, 31, 2)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertNotIn("b_month=Month.JANUARY", errors[0])
        self.assertIn("one year for both dates", errors[0])

    # --- DBD002: a day its month does not have ------------------------------

    def test_day_the_month_does_not_have(self):
        """A death as first read: day «31.» under November."""
        src = _deaths(_block(
            "Month.NOVEMBER", "death(9, Gender.FEMALE, 31, None)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD002]", errors[0])
        self.assertIn("NOVEMBER has no day 31", errors[0])

    def test_impossible_day_is_not_also_reported_as_an_order(self):
        """31 November is later than every November burial day, so the order
        check would fire too; one finding is the one worth reading."""
        src = _deaths(_block("Month.NOVEMBER", "death(50, Gender.FEMALE, 31, 2)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD002]", errors[0])

    def test_burial_day_the_month_does_not_have(self):
        src = _deaths(_block(
            "Month.JANUARY",
            "death(1, Gender.MALE, 28, 30, b_month=Month.FEBRUARY)"))
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[DBD002]", errors[0])
        self.assertIn("burial", errors[0])

    def test_february_29_follows_the_julian_calendar(self):
        """The books are Old Style: 1800 was a leap year there."""
        src = _deaths(_block("Month.FEBRUARY", "death(3, Gender.MALE, 29, None)"),
                      year=1800)
        self.assertEqual(self._check(src), [])
        src = _deaths(_block("Month.FEBRUARY", "death(3, Gender.MALE, 29, None)"),
                      year=1801)
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("FEBRUARY 1801 has no day 29", errors[0])

    def test_record_year_resolves_innermost_first(self):
        # death_month_year's year beats the book's…
        src = _deaths(
            "    *death_month_year(Month.FEBRUARY, 1800,\n"
            "                      death(3, Gender.MALE, 29, None))", year=1801)
        self.assertEqual(self._check(src), [])
        # …and the record's own year= beats both.
        src = _deaths(_block(
            "Month.FEBRUARY", "death(3, Gender.MALE, 29, None, year=1801)"),
            year=1800)
        self.assertEqual(len(self._check(src)), 1)

    def test_day_past_31_needs_no_month(self):
        src = _deaths(_block("None", "death(1, Gender.MALE, 32, None)"))
        self.assertEqual(len(self._check(src)), 1)

    # --- the book's own contradiction --------------------------------------

    def test_source_date_error_stands_down(self):
        """Re-read on the scan, the book itself buries before the death."""
        src = _deaths(_block(
            "Month.JANUARY",
            'death(1, Gender.MALE, 9, 8, source_date_error="так в подлиннике")',
            'death(2, Gender.MALE, 31, None, d_month=Month.NOVEMBER, '
            'source_date_error="так в подлиннике")'))
        self.assertEqual(self._check(src), [])

    def test_empty_source_date_error_does_not(self):
        """`Death` treats an empty reason as no reason (the facts layer tests
        it for truth), so the linter does too."""
        src = _deaths(_block(
            "Month.JANUARY", 'death(1, Gender.MALE, 9, 8, source_date_error="")'))
        self.assertEqual(len(self._check(src)), 1)

    # --- output shape -------------------------------------------------------

    def test_structured_output_is_a_hard_error_on_the_death_line(self):
        src = _deaths(_block(
            "Month.JANUARY",
            "death(1, Gender.MALE, 9, 9)",
            "death(2, Gender.MALE, 9, 8)"))
        issues = self._structured(src)
        self.assertEqual(len(issues), 1, issues)
        self.assertEqual(issues[0]["level"], "error")
        self.assertEqual(issues[0]["line"], 4)

    def test_syntax_error_is_left_to_other_linters(self):
        self.assertEqual(self._structured("death(\n"), [])


if __name__ == "__main__":
    unittest.main()
