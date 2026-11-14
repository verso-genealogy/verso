"""Tests for check_ages.py — DSL linter for age/groom_age/bride_age literals."""

import inspect
import tempfile
import unittest
from pathlib import Path

from verso.ru.ages import AGE_KWARGS
from verso.ru.dsl.records import deaths, external_sources, marriages
from verso.ru.linters.checks.ages import (
    AGE_POSITIONS, check_file, check_file_structured, _integer_age_for, is_valid_age_string)


class TestIsValidAgeString(unittest.TestCase):
    """Lower-level test of the string-format predicate."""

    def test_bare_digits(self):
        self.assertTrue(is_valid_age_string("19"))
        self.assertTrue(is_valid_age_string("0"))

    def test_single_unit_short(self):
        self.assertTrue(is_valid_age_string("6 м"))
        self.assertTrue(is_valid_age_string("1 н"))
        self.assertTrue(is_valid_age_string("3 д"))

    def test_compound(self):
        self.assertTrue(is_valid_age_string("19 лет 6 мес"))
        self.assertTrue(is_valid_age_string("1 г 2 мес 3 нед 4 д"))
        self.assertTrue(is_valid_age_string("2 года 3 месяца"))

    def test_idioms(self):
        self.assertTrue(is_valid_age_string("полгода"))
        self.assertTrue(is_valid_age_string("полу года"))
        self.assertTrue(is_valid_age_string("полтора года"))

    def test_with_period(self):
        self.assertTrue(is_valid_age_string("6 мес."))
        self.assertTrue(is_valid_age_string("19 лет."))

    def test_empty(self):
        self.assertFalse(is_valid_age_string(""))
        self.assertFalse(is_valid_age_string("   "))

    def test_unknown_unit(self):
        self.assertFalse(is_valid_age_string("19 yr"))
        self.assertFalse(is_valid_age_string("19 mo"))
        self.assertFalse(is_valid_age_string("19 abc"))

    def test_junk(self):
        self.assertFalse(is_valid_age_string("abc"))
        self.assertFalse(is_valid_age_string("?"))
        self.assertFalse(is_valid_age_string("1/2"))
        self.assertFalse(is_valid_age_string("7?"))

    def test_negative(self):
        # leading "-" leaves non-whitespace before the first digit
        self.assertFalse(is_valid_age_string("-3 мес"))

    def test_trailing_junk(self):
        self.assertFalse(is_valid_age_string("19 лет old"))

    def test_duplicate_unit(self):
        self.assertFalse(is_valid_age_string("19 лет 19 лет"))


class TestCheckFile(unittest.TestCase):
    """End-to-end tests against the linter."""

    def _write_temp(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8',
        )
        f.write(content)
        f.close()
        return Path(f.name)

    def test_valid_int_age_no_violation(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age=45)\n'
        )
        try:
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_external_source_age_validated(self):
        # age on criminal_record()/wwi_record() is checked like death/marriage.
        p = self._write_temp(
            'criminal_record(person("X"), source_url="u", original_text="t", age=40)\n'
            'wwi_record(person("Y"), source_url="u", age="19 лет 6 мес")\n'
        )
        try:
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_external_source_invalid_age_flagged(self):
        p = self._write_temp(
            'criminal_record(person("X"), source_url="u", original_text="t", age="abc")\n'
            'wwi_record(person("Y"), source_url="u", age=-5)\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 2)
            self.assertTrue(all("age" in e for e in errors))
        finally:
            p.unlink()

    def test_valid_string_age_no_violation(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age="6 м")\n'
            'death(2, 0, 1, 1, deceased=person("X"), age="19 лет 6 мес")\n'
        )
        try:
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_valid_marriage_string_age(self):
        p = self._write_temp(
            'marriage(1, 1, 1, groom=person("X"), bride=person("Y"), '
            'groom_age="19 лет 6 мес", bride_age=17)\n'
        )
        try:
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_invalid_string_age(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age="abc")\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 1)
            self.assertIn("age='abc'", errors[0])
        finally:
            p.unlink()

    def test_negative_int_age(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age=-3)\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 1)
        finally:
            p.unlink()

    def test_bool_age_rejected(self):
        # bool is subclass of int; explicit reject
        p = self._write_temp(
            'marriage(1, 1, 1, groom=person("X"), bride=person("Y"), '
            'groom_age=True)\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 1)
        finally:
            p.unlink()

    def test_none_age_no_violation(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age=None)\n'
            'marriage(2, 1, 1, groom=person("X"), bride=person("Y"))\n'
        )
        try:
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_birth_age_not_checked(self):
        # birth() does not have age-related kwargs in this DSL.
        p = self._write_temp(
            'birth(1, 0, 1, 1, 1, 1, child=person("X"), age="abc")\n'
        )
        try:
            # No record func match → no violation.
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_non_literal_age_skipped(self):
        # Variables and expressions not flagged.
        p = self._write_temp(
            'AGE = 45\n'
            'death(1, 0, 1, 1, deceased=person("X"), age=AGE)\n'
        )
        try:
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_structured_output_shape(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age="abc")\n'
        )
        try:
            issues = check_file_structured(p)
            self.assertEqual(len(issues), 1)
            issue = issues[0]
            self.assertEqual(issue["level"], "error")
            self.assertEqual(issue["line"], 1)
            self.assertIn("age=", issue["message"])
        finally:
            p.unlink()

    def test_syntax_error_reported(self):
        p = self._write_temp("def(\n")
        try:
            issues = check_file_structured(p)
            self.assertEqual(len(issues), 1)
            self.assertIn("SyntaxError", issues[0]["message"])
        finally:
            p.unlink()


class TestIntegerAgeFor(unittest.TestCase):
    """Lower-level test of the AGE001 predicate."""

    def test_whole_year_forms(self):
        for s, expected in (("1 год", "1"), ("5 лет", "5"), ("3 года", "3"),
                            ("20 годов", "20"), ("1 г", "1"), ("7 л", "7"),
                            ("19 лет.", "19"), (" 4 года ", "4")):
            with self.subTest(s=s):
                self.assertEqual(_integer_age_for(s), expected)

    def test_bare_digits(self):
        self.assertEqual(_integer_age_for("70"), "70")
        self.assertEqual(_integer_age_for("0"), "0")

    def test_sub_year_and_compound_are_silent(self):
        # The integer cannot express these — they must stay strings.
        for s in ("1 мес", "3 дн", "1 нед", "6 м",
                  "19 лет 6 мес", "1 г 2 мес 3 нед 4 д"):
            with self.subTest(s=s):
                self.assertIsNone(_integer_age_for(s))

    def test_idioms_are_silent(self):
        # "полгода" carries a MONTHS component (split_age → ('', '6', '', '')),
        # so it is not a whole-year age however it reads.
        for s in ("полгода", "пол года", "полу года", "полтора года"):
            with self.subTest(s=s):
                self.assertIsNone(_integer_age_for(s))

    def test_junk_is_silent(self):
        # Malformed ages stay owned by the existing check, never AGE001.
        for s in ("abc", "?", "19 yr", "1/2", ""):
            with self.subTest(s=s):
                self.assertIsNone(_integer_age_for(s))


class TestAge001(unittest.TestCase):
    """AGE001 — a parseable age that should have been written as an integer."""

    def _write_temp(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8',
        )
        f.write(content)
        f.close()
        return Path(f.name)

    def test_flags_whole_year_string(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age="1 год")\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 1)
            self.assertIn("[AGE001]", errors[0])
            self.assertIn("age=1", errors[0])
            # death() is where the doubled unit actually renders
            self.assertIn("1 год лет", errors[0])
        finally:
            p.unlink()

    def test_flags_quoted_bare_number(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age="70")\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 1)
            self.assertIn("[AGE001]", errors[0])
            self.assertIn("age=70", errors[0])
        finally:
            p.unlink()

    def test_marriage_and_external_source_kwargs(self):
        p = self._write_temp(
            'marriage(1, 2, groom_age="20 лет", bride_age="18 лет")\n'
            'wwi_record(1, age="26 лет")\n'
            'wwii_record(1, age="30 лет")\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 4)
            self.assertTrue(all("[AGE001]" in e for e in errors))
            # The «Умерший» rendering is death-specific — don't claim it here.
            self.assertFalse(any("Умерший" in e for e in errors))
        finally:
            p.unlink()

    def test_valid_ages_stay_silent(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age=1)\n'
            'death(2, 0, 1, 1, deceased=person("X"), age="19 лет 6 мес")\n'
            'death(3, 0, 1, 1, deceased=person("X"), age="1 мес")\n'
            'death(4, 0, 1, 1, deceased=person("X"), age="3 дн")\n'
            'death(5, 0, 1, 1, deceased=person("X"), age="полгода")\n'
            'death(6, 0, 1, 1, deceased=person("X"), age="полтора года")\n'
            'death(7, 0, 1, 1, deceased=person("X"), age=None)\n'
        )
        try:
            self.assertEqual(check_file(p), [])
        finally:
            p.unlink()

    def test_malformed_age_is_not_reported_twice(self):
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("X"), age="19 yr")\n'
        )
        try:
            errors = check_file(p)
            self.assertEqual(len(errors), 1)
            self.assertNotIn("[AGE001]", errors[0])
        finally:
            p.unlink()

    def test_structured_issue_carries_range_and_fix(self):
        # A Cyrillic-heavy line: the AST col_offset is a BYTE offset and
        # overshoots, so a missing _char_col conversion puts the fix range past
        # the literal and the IDE edit lands on the wrong characters.
        p = self._write_temp(
            'death(1, 0, 1, 1, deceased=person("Феодора", "Николаева"), '
            'age="1 год")\n'
        )
        try:
            line = p.read_text(encoding="utf-8").splitlines()[0]
            issues = check_file_structured(p)
            self.assertEqual(len(issues), 1)
            issue = issues[0]
            self.assertEqual(issue["level"], "error")
            fix = issue["fix"]
            assert isinstance(fix, dict)
            self.assertEqual(fix["type"], "replace_kwarg")
            self.assertEqual(fix["new"], "1")
            # `old` is the verbatim source slice, quotes included, and the
            # reported range must actually span it.
            self.assertEqual(fix["old"], '"1 год"')
            col, end_col = issue["col"], issue["end_col"]
            assert isinstance(col, int) and isinstance(end_col, int)
            self.assertEqual(line[col:end_col], '"1 год"')
        finally:
            p.unlink()



def test_the_positions_read_are_the_factories():
    """`AGE_POSITIONS` names each age's place in `death()` and `marriage()`, and a card's age is keyword-only."""
    for factory in (deaths.death, marriages.marriage):
        names = list(inspect.signature(factory).parameters)
        assert {names.index(arg): arg for arg in AGE_KWARGS if arg in names} == AGE_POSITIONS[factory.__name__]
    for factory in (external_sources.criminal_record, external_sources.wwi_record, external_sources.wwii_record):
        assert inspect.signature(factory).parameters["age"].kind is inspect.Parameter.KEYWORD_ONLY


class TestPositionalAges(unittest.TestCase):
    def _structured(self, src: str) -> list[dict[str, object]]:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(src)
        p = Path(f.name)
        try:
            return check_file_structured(p)
        finally:
            p.unlink()

    def test_a_positional_death_age_is_read(self):
        issues = self._structured('death(1, Gender.MALE, 3, 4, None, None, person("Лука"), "70")\n')
        self.assertEqual([str(i["message"])[:8] for i in issues], ["[AGE001]"], issues)
        self.assertEqual(issues[0]["fix"], {"type": "replace_kwarg", "old": '"70"', "new": "70",
                                            "col": issues[0]["col"]})

    def test_a_positional_marriage_age_is_read(self):
        issues = self._structured('marriage(1, 7, None, person("Лука"), person("Дарья"), None, None, 20, "много")\n')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("bride_age='много' is not a recognized age", str(issues[0]["message"]))

    def test_a_positional_argument_of_another_call_is_no_age(self):
        self.assertEqual(self._structured('criminal_record(person("Лука"), "70")\n'), [])


if __name__ == "__main__":
    unittest.main()
