#!/usr/bin/env python3
"""Tests for check_genders.py"""

import ast
import io
import sys
import tempfile
import unittest
from pathlib import Path

from verso.ru.linters.checks.genders import GenderChecker, check_file_structured, main


def check_code(code: str) -> list[str]:
    """Helper: parse code string, run GenderChecker, return errors."""
    tree = ast.parse(code)
    checker = GenderChecker(Path("test.py"))
    checker.visit(tree)
    return checker.errors


class TestMarriageGenders(unittest.TestCase):

    def test_female_named_groom_detected(self):
        code = 'marriage(1, 2, groom=person("Мария"), bride=person("Иван"))'
        errors = check_code(code)
        self.assertTrue(any('groom' in e for e in errors))

    def test_male_named_bride_detected(self):
        code = 'marriage(1, 2, groom=person("Иван"), bride=person("Петр"))'
        errors = check_code(code)
        self.assertTrue(any('bride' in e for e in errors))

    def test_explicit_female_gender_on_groom_detected(self):
        code = 'marriage(1, 2, groom=person("Иван", gender=Gender.FEMALE), bride=person("Мария"))'
        errors = check_code(code)
        self.assertTrue(any('groom' in e for e in errors))

    def test_explicit_male_gender_on_bride_detected(self):
        code = 'marriage(1, 2, groom=person("Иван"), bride=person("Мария", gender=Gender.MALE))'
        errors = check_code(code)
        self.assertTrue(any('bride' in e for e in errors))

    def test_correct_marriage_no_error(self):
        code = 'marriage(1, 2, groom=person("Иван"), bride=person("Мария"))'
        errors = check_code(code)
        self.assertEqual(errors, [])

    def test_missing_groom_no_error(self):
        code = 'marriage(1, 2, bride=person("Мария"))'
        errors = check_code(code)
        self.assertEqual(errors, [])

    def test_missing_bride_no_error(self):
        code = 'marriage(1, 2, groom=person("Иван"))'
        errors = check_code(code)
        self.assertEqual(errors, [])

    def test_unknown_name_with_question_mark_no_error(self):
        code = 'marriage(1, 2, groom=person("Ива?"), bride=person("Мари?"))'
        errors = check_code(code)
        self.assertEqual(errors, [])

    def test_groom_not_person_call_no_error(self):
        code = 'marriage(1, 2, groom=None, bride=person("Мария"))'
        errors = check_code(code)
        self.assertEqual(errors, [])


class TestBirthGenders(unittest.TestCase):

    def test_male_record_female_child_detected(self):
        code = 'birth(1, Gender.MALE, 1, 2, child=person("Мария"))'
        errors = check_code(code)
        self.assertTrue(any('child' in e for e in errors))

    def test_female_record_male_child_detected(self):
        code = 'birth(1, Gender.FEMALE, 1, 2, child=person("Иван"))'
        errors = check_code(code)
        self.assertTrue(any('child' in e for e in errors))

    def test_female_named_father_detected(self):
        code = 'birth(1, Gender.MALE, 1, 2, child=person("Иван"), father=person("Мария"))'
        errors = check_code(code)
        self.assertTrue(any('father' in e for e in errors))

    def test_male_named_mother_detected(self):
        code = 'birth(1, Gender.MALE, 1, 2, child=person("Иван"), mother=person("Петр"))'
        errors = check_code(code)
        self.assertTrue(any('mother' in e for e in errors))

    def test_correct_birth_no_error(self):
        code = 'birth(1, Gender.MALE, 1, 2, child=person("Иван"), father=person("Петр"), mother=person("Мария"))'
        errors = check_code(code)
        self.assertEqual(errors, [])

    def test_child_with_question_mark_no_error(self):
        code = 'birth(1, Gender.MALE, 1, 2, child=person("?"))'
        errors = check_code(code)
        self.assertEqual(errors, [])

    def test_correct_female_birth_no_error(self):
        code = 'birth(1, Gender.FEMALE, 1, 2, child=person("Мария"), father=person("Петр"), mother=person("Анна"))'
        errors = check_code(code)
        self.assertEqual(errors, [])


class TestDeathGenders(unittest.TestCase):

    def test_male_record_female_deceased_detected(self):
        code = 'death(1, Gender.MALE, 1, 2, deceased=person("Мария"))'
        errors = check_code(code)
        self.assertTrue(any('deceased' in e for e in errors))

    def test_female_record_male_deceased_detected(self):
        code = 'death(1, Gender.FEMALE, 1, 2, deceased=person("Иван"))'
        errors = check_code(code)
        self.assertTrue(any('deceased' in e for e in errors))

    def test_correct_male_death_no_error(self):
        code = 'death(1, Gender.MALE, 1, 2, deceased=person("Иван"))'
        errors = check_code(code)
        self.assertEqual(errors, [])

    def test_correct_female_death_no_error(self):
        code = 'death(1, Gender.FEMALE, 1, 2, deceased=person("Мария"))'
        errors = check_code(code)
        self.assertEqual(errors, [])


class TestDeathRelationshipGenders(unittest.TestCase):

    def test_female_relative_with_father_relationship_detected(self):
        code = 'death(1, Gender.MALE, 1, 2, relatives=[relative(person("Мария"), Relationship.FATHER)])'
        errors = check_code(code)
        self.assertTrue(any('relative' in e for e in errors))

    def test_male_relative_with_father_relationship_no_error(self):
        code = 'death(1, Gender.MALE, 1, 2, relatives=[relative(person("Иван"), Relationship.FATHER)])'
        errors = check_code(code)
        self.assertFalse(any('relative' in e for e in errors))

    def test_unknown_name_with_father_relationship_no_error(self):
        code = 'death(1, Gender.MALE, 1, 2, relatives=[relative(person("?"), Relationship.FATHER)])'
        errors = check_code(code)
        self.assertEqual(errors, [])


class TestBirthRelativesGenders(unittest.TestCase):

    def test_female_relative_with_father_detected(self):
        code = 'birth(1, Gender.MALE, 1, 2, relatives=[relative(person("Мария"), Relationship.FATHER)])'
        errors = check_code(code)
        self.assertTrue(any('relative' in e for e in errors))

    def test_male_relative_with_father_no_error(self):
        code = 'birth(1, Gender.MALE, 1, 2, relatives=[relative(person("Иван"), Relationship.FATHER)])'
        errors = check_code(code)
        self.assertFalse(any('relative' in e for e in errors))


def structured(code: str) -> list[dict[str, object]]:
    """Helper: write code to a temp file, return structured issues."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(code)
        path = Path(f.name)
    try:
        return check_file_structured(path)
    finally:
        path.unlink()


def span(line: str, issue: dict[str, object]) -> str:
    """Helper: the source text the issue's char columns select."""
    col, end_col = issue['col'], issue['end_col']
    assert isinstance(col, int) and isinstance(end_col, int)
    return line[col:end_col]


def for_role(issues: list[dict[str, object]], role: str) -> dict[str, object]:
    """Helper: the single issue whose message names `role`."""
    return next(i for i in issues if role in str(i['message']))


class TestStructuredIssues(unittest.TestCase):
    """The structured shape pins the offending `role=person(...)` argument with
    char columns, so IDE plugins highlight it instead of the whole line."""

    def test_issue_carries_level_line_and_message(self):
        code = 'birth(1, Gender.MALE, mother=person("Иван"))\n'
        issues = structured(code)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['level'], 'error')
        self.assertEqual(issues[0]['line'], 1)
        self.assertIn('expected FEMALE for mother', str(issues[0]['message']))

    def test_columns_span_the_whole_kwarg_argument(self):
        code = 'birth(1, Gender.MALE, mother=person("Иван"))\n'
        issue = structured(code)[0]
        self.assertEqual(span(code.splitlines()[0], issue), 'mother=person("Иван")')

    def test_columns_are_char_offsets_not_utf8_bytes(self):
        # Cyrillic ahead of the argument: a raw AST byte offset would overshoot.
        code = 'birth(1, Gender.MALE, father=person("Мария"), mother=person("Иван"))\n'
        line = code.splitlines()[0]
        issues = structured(code)
        self.assertEqual(span(line, for_role(issues, 'father')), 'father=person("Мария")')
        self.assertEqual(span(line, for_role(issues, 'mother')), 'mother=person("Иван")')

    def test_multiline_argument_stays_full_line(self):
        code = (
            'birth(1, Gender.MALE,\n'
            '      mother=person("Иван",\n'
            '                    status=SOLDIER_WIFE))\n'
        )
        issue = structured(code)[0]
        self.assertNotIn('col', issue)
        self.assertNotIn('end_col', issue)

    def test_positional_relative_pins_the_person_call(self):
        code = (
            'birth(1, Gender.MALE, child=person("Иван"), '
            'relatives=[relative(person("Иван"), Relationship.MOTHER)])\n'
        )
        issue = for_role(structured(code), 'relative')
        self.assertEqual(span(code.splitlines()[0], issue), 'person("Иван")')

    def test_clean_file_has_no_issues(self):
        code = 'birth(1, Gender.MALE, child=person("Иван"), mother=person("Мария"))\n'
        self.assertEqual(structured(code), [])

    def test_syntax_error_is_left_to_other_linters(self):
        self.assertEqual(structured('birth(1,\n'), [])


class TestParentSwapFix(unittest.TestCase):
    """A male in `mother=` (or a female in `father=`) is usually the wrong slot,
    so the issue offers a `replace_kwarg` fix swapping the two roles."""

    def test_male_mother_offers_swap_to_father(self):
        code = 'birth(1, Gender.MALE, mother=person("Стефан"))\n'
        fix = structured(code)[0]['fix']
        assert isinstance(fix, dict)
        self.assertEqual(fix['type'], 'replace_kwarg')
        self.assertEqual(fix['old'], 'mother=')
        self.assertEqual(fix['new'], 'father=')

    def test_female_father_offers_swap_to_mother(self):
        code = 'birth(1, Gender.MALE, father=person("Мария"))\n'
        fix = structured(code)[0]['fix']
        assert isinstance(fix, dict)
        self.assertEqual(fix['old'], 'father=')
        self.assertEqual(fix['new'], 'mother=')

    def test_fix_col_pins_the_kwarg_as_a_char_column(self):
        code = 'birth(1, Gender.MALE, child=person("Иван"), mother=person("Стефан"))\n'
        fix = structured(code)[0]['fix']
        assert isinstance(fix, dict)
        col = fix['col']
        assert isinstance(col, int)
        self.assertTrue(code.splitlines()[0].startswith('mother=', col))

    def test_no_swap_when_counterpart_kwarg_already_present(self):
        # Swapping would emit a duplicate `father=` — invalid Python.
        code = 'birth(1, Gender.MALE, father=person("Иван"), mother=person("Стефан"))\n'
        self.assertNotIn('fix', structured(code)[0])

    def test_no_swap_for_other_roles(self):
        code = 'marriage(1, 2, groom=person("Мария"), bride=person("Мария"))\n'
        for issue in structured(code):
            self.assertNotIn('fix', issue)

    def test_no_swap_when_person_starts_on_another_line(self):
        # The fix is applied by line + column; `mother=` is not on the issue's line.
        code = 'birth(1, Gender.MALE, mother=\n      person("Стефан"))\n'
        self.assertNotIn('fix', structured(code)[0])


class TestMainFunction(unittest.TestCase):

    def test_clean_file_returns_zero(self):
        code = 'marriage(1, 2, groom=person("Иван"), bride=person("Мария"))\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = Path(f.name)
        orig_argv = sys.argv
        try:
            sys.argv = ['check_genders.py', str(path)]
            result = main()
            self.assertEqual(result, 0)
        finally:
            sys.argv = orig_argv
            path.unlink()

    def test_file_with_violation_returns_one(self):
        code = 'marriage(1, 2, groom=person("Мария"), bride=person("Мария"))\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = Path(f.name)
        orig_argv = sys.argv
        try:
            sys.argv = ['check_genders.py', str(path)]
            result = main()
            self.assertEqual(result, 1)
        finally:
            sys.argv = orig_argv
            path.unlink()

    def test_errors_go_to_stderr(self):
        code = 'marriage(1, 2, groom=person("Мария"), bride=person("Мария"))\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = Path(f.name)
        orig_argv = sys.argv
        try:
            sys.argv = ['check_genders.py', str(path)]
            captured = io.StringIO()
            orig_stderr = sys.stderr
            sys.stderr = captured
            try:
                main()
            finally:
                sys.stderr = orig_stderr
            self.assertIn('groom', captured.getvalue())
        finally:
            sys.argv = orig_argv
            path.unlink()


if __name__ == '__main__':
    unittest.main()
