#!/usr/bin/env python3
"""Tests for check_names.py"""

import ast
import tempfile
import unittest
from pathlib import Path

from verso.ru.linters.checks.names import NameChecker, check_file


class TestNameChecker(unittest.TestCase):
    """Tests for the NameChecker AST visitor."""

    def check_code(self, code: str) -> list[str]:
        """Helper to run NameChecker on code string and return errors."""
        tree = ast.parse(code)
        checker = NameChecker(Path("test.py"))
        checker.visit(tree)
        return checker.errors

    def test_valid_name_and_patronymic_no_errors(self):
        """Known name and patronymic should produce no errors."""
        errors = self.check_code('person("Иванъ", "Ивановъ")')
        self.assertEqual(errors, [])

    def test_unknown_patronymic_reported(self):
        """Unknown patronymic should produce an error."""
        errors = self.check_code('person("Иванъ", "ФиктивовичУ")')
        self.assertEqual(len(errors), 1)
        self.assertIn("Unknown patronymic", errors[0])
        self.assertIn("ФиктивовичУ", errors[0])

    def test_unknown_first_name_reported(self):
        """Unknown first name should produce an error."""
        errors = self.check_code('person("ФиктивноеИмяХ", "Ивановъ")')
        self.assertEqual(len(errors), 1)
        self.assertIn("Unknown first name", errors[0])
        self.assertIn("ФиктивноеИмяХ", errors[0])

    def test_patr_old_suppresses_patronymic_check(self):
        """Explicit patr_old override should skip patronymic validation."""
        errors = self.check_code(
            'person("Иванъ", "НеизвестныйОтецов", patr_old="СверхРедкийович")'
        )
        # No patronymic error because patr_old was provided
        patronymic_errors = [e for e in errors if "Unknown patronymic" in e]
        self.assertEqual(patronymic_errors, [])

    def test_question_mark_name_no_error(self):
        """'?' as first name should produce no error."""
        errors = self.check_code('person("?", "Ивановъ")')
        name_errors = [e for e in errors if "Unknown first name" in e]
        self.assertEqual(name_errors, [])

    def test_question_mark_patronymic_no_error(self):
        """'?' as patronymic should produce no error."""
        errors = self.check_code('person("Иванъ", "?")')
        self.assertEqual(errors, [])

    def test_no_patr_orig_no_patronymic_error(self):
        """Missing patr_orig (keyword-only other args) should not produce patronymic error."""
        errors = self.check_code('person("Иванъ", last_name_orig="Чичиков")')
        patronymic_errors = [e for e in errors if "Unknown patronymic" in e]
        self.assertEqual(patronymic_errors, [])

    def test_name_modern_orth_overrides_name_check(self):
        """name_modern_orth should be validated instead of name_orig."""
        # name_modern_orth="Иван" is valid; name_orig is irrelevant for validation
        errors = self.check_code('person("ХХХ", "Ивановъ", name_modern_orth="Иван")')
        name_errors = [e for e in errors if "Unknown first name" in e]
        self.assertEqual(name_errors, [])

    def test_invalid_name_modern_orth_reported(self):
        """Invalid name_modern_orth should produce an error."""
        errors = self.check_code('person("Иванъ", "Ивановъ", name_modern_orth="НеверноеИмя")')
        self.assertEqual(len(errors), 1)
        self.assertIn("Unknown first name", errors[0])
        self.assertIn("НеверноеИмя", errors[0])

    def test_old_orthography_modernized_before_check(self):
        """Old orthography in name_orig should be modernized before validation."""
        # "Ивановъ" modernizes to "Иванов" which is a valid patronymic
        errors = self.check_code('person("Иванъ", "Ивановъ")')
        self.assertEqual(errors, [])

    def test_error_message_includes_original_form(self):
        """Error message should include the original (pre-modernization) form."""
        errors = self.check_code('person("Иванъ", "НеизвестныйОтецовъ")')
        self.assertEqual(len(errors), 1)
        # Should show modernized form and original with ъ
        self.assertIn("НеизвестныйОтецов", errors[0])
        self.assertIn("НеизвестныйОтецовъ", errors[0])

    def test_empty_file_no_errors(self):
        """Empty code should produce no errors."""
        errors = self.check_code("")
        self.assertEqual(errors, [])

    def test_no_person_calls_no_errors(self):
        """Code without person() calls should produce no errors."""
        code = 'x = some_other_func("arg1", "arg2")\ny = 1'
        errors = self.check_code(code)
        self.assertEqual(errors, [])

    def test_non_string_arg_skipped(self):
        """Non-string-literal args (variables, etc.) should not produce errors."""
        errors = self.check_code('person(name_var, patr_var)')
        self.assertEqual(errors, [])

    def test_both_unknown_produces_two_errors(self):
        """Both unknown name and patronymic should produce two errors."""
        errors = self.check_code('person("НеизвестноеИмяЩ", "НеизвестныйОтецовЩ")')
        self.assertEqual(len(errors), 2)

    def test_line_number_in_error(self):
        """Error should include correct line number."""
        code = 'x = 1\nperson("Иванъ", "НеизвестныйОтецовъ")'
        errors = self.check_code(code)
        self.assertEqual(len(errors), 1)
        self.assertIn(":2:", errors[0])

    def test_partial_illegibility_in_name_no_error(self):
        """Name with embedded '?' should not be flagged."""
        errors = self.check_code('person("Федо?", "Ивановъ")')
        self.assertEqual(errors, [])

    def test_partial_illegibility_in_patronymic_no_error(self):
        """Patronymic with embedded '?' should not be flagged."""
        errors = self.check_code('person("Иванъ", "Иванов?")')
        self.assertEqual(errors, [])


class TestNamePatrGenderCrossCheck(unittest.TestCase):
    """Tests for name vs patronymic gender cross-check."""

    def check_code(self, code: str) -> list[str]:
        tree = ast.parse(code)
        checker = NameChecker(Path("test.py"))
        checker.visit(tree)
        return checker.errors

    def _gender_mismatch_errors(self, errors: list[str]) -> list[str]:
        return [e for e in errors if "name-patronymic gender mismatch" in e]

    def test_name_patr_gender_match_no_error(self):
        errors = self._gender_mismatch_errors(self.check_code('person("Марія", "Иванова")'))
        self.assertEqual(errors, [])

    def test_name_patr_gender_mismatch_detected(self):
        errors = self._gender_mismatch_errors(self.check_code('person("Марія", "Ивановъ")'))
        self.assertEqual(len(errors), 1)
        self.assertIn("жен", errors[0])
        self.assertIn("муж", errors[0])

    def test_name_patr_gender_mismatch_reverse(self):
        errors = self._gender_mismatch_errors(self.check_code('person("Иванъ", "Иванова")'))
        self.assertEqual(len(errors), 1)

    def test_name_gender_unknown_skips_check(self):
        errors = self._gender_mismatch_errors(self.check_code('person("?", "Ивановъ")'))
        self.assertEqual(errors, [])

    def test_patr_gender_unknown_skips_check(self):
        errors = self._gender_mismatch_errors(self.check_code('person("Иванъ", "?")'))
        self.assertEqual(errors, [])

    def test_no_patr_skips_check(self):
        errors = self._gender_mismatch_errors(self.check_code('person("Иванъ")'))
        self.assertEqual(errors, [])

    def test_get_status_gender_resolves_plain_string(self):
        """`_get_status_gender` returns the gender registered for a
        plain-string status (e.g. `"ясачный крестьянин"` →
        `Gender.MALE`). Required for catching female-name + masculine-
        status mismatches in census DSLs that use plain strings rather
        than Status constants."""
        from verso.ru.domain import Gender
        # Trigger statuses module load so the registry is populated.
        import verso.ru.domain.statuses as statuses  # noqa: F401
        tree = ast.parse('person("Иванъ", status="ясачный крестьянин")')
        stmt_node = tree.body[0]
        assert isinstance(stmt_node, ast.Expr)
        person_call = stmt_node.value
        checker = NameChecker(Path("test.py"))
        self.assertEqual(
            checker._get_status_gender(person_call), Gender.MALE,
        )

    def test_plain_string_status_gender_mismatch_detected(self):
        """A female name with a plain-string masculine status (the
        common census typo: `Марья + ясачный крестьянин`) is reported
        as a gender-status mismatch. Currently the linter is silent."""
        import verso.ru.domain.statuses as statuses  # noqa: F401
        errors = self.check_code(
            'person("Марья", "Нечаева", status="ясачный крестьянин")',
        )
        mismatches = [e for e in errors if "gender-status mismatch" in e]
        self.assertEqual(len(mismatches), 1, mismatches)
        self.assertIn("ясачный крестьянин", mismatches[0])

    def test_plain_string_status_gender_match_no_error(self):
        """A female name with a feminine plain-string status produces
        no mismatch error (regression guard)."""
        import verso.ru.domain.statuses as statuses  # noqa: F401
        errors = self.check_code(
            'person("Марья", "Нечаева", status="ясачная крестьянка")',
        )
        mismatches = [e for e in errors if "gender-status mismatch" in e]
        self.assertEqual(mismatches, [])


class TestCheckFile(unittest.TestCase):
    """Tests for the check_file function."""

    def test_valid_file_returns_no_errors(self):
        """File with valid names produces no errors."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write('person("Иванъ", "Ивановъ")\n')
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(errors, [])
        finally:
            path.unlink()

    def test_invalid_patronymic_returns_error(self):
        """File with unknown patronymic produces an error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write('person("Иванъ", "ФиктивнейшийОтецовъ")\n')
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertIn("Unknown patronymic", errors[0])
            self.assertIn(str(path), errors[0])
        finally:
            path.unlink()

    def test_syntax_error_caught_and_reported(self):
        """Syntax error in file is caught and reported."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write('def broken(\n')
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertIn("SyntaxError", errors[0])
        finally:
            path.unlink()

    def test_error_format_includes_path_and_line(self):
        """Error format should be path:line: message."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write('x = 1\nperson("Иванъ", "НеизвестнейшийОтецов")\n')
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertRegex(errors[0], r'.+\.py:2: Unknown patronymic')
        finally:
            path.unlink()


class TestCyrillicValidation(unittest.TestCase):
    """Tests for Cyrillic-only character validation in person name fields."""

    def check_code(self, code: str) -> list[str]:
        tree = ast.parse(code)
        checker = NameChecker(Path("test.py"))
        checker.visit(tree)
        return checker.errors

    def _cyrillic_errors(self, errors: list[str]) -> list[str]:
        return [e for e in errors if "non-Cyrillic" in e]

    # --- Valid cases ---

    def test_valid_cyrillic_name_no_error(self):
        errors = self._cyrillic_errors(self.check_code('person("Иванъ", "Ивановъ")'))
        self.assertEqual(errors, [])

    def test_prereform_letters_allowed(self):
        errors = self._cyrillic_errors(self.check_code('person("Ѳеодоръ", "Тимоѳеевъ")'))
        self.assertEqual(errors, [])

    def test_question_mark_allowed(self):
        errors = self._cyrillic_errors(self.check_code('person("?")'))
        self.assertEqual(errors, [])

    def test_partial_question_mark_allowed(self):
        errors = self._cyrillic_errors(self.check_code('person("Федо?")'))
        self.assertEqual(errors, [])

    def test_hyphenated_name_allowed(self):
        errors = self._cyrillic_errors(self.check_code('person("Анна-Марія")'))
        self.assertEqual(errors, [])

    def test_none_name_skipped(self):
        errors = self._cyrillic_errors(self.check_code('person(last_name_orig="Петровъ")'))
        self.assertEqual(errors, [])

    # --- Invalid cases ---

    def test_latin_in_name_orig_detected(self):
        errors = self._cyrillic_errors(self.check_code('person("Иванs")'))
        self.assertEqual(len(errors), 1)
        self.assertIn("name_orig", errors[0])

    def test_latin_in_patr_orig_detected(self):
        errors = self._cyrillic_errors(self.check_code('person("Иванъ", "Ивановx")'))
        self.assertEqual(len(errors), 1)
        self.assertIn("patr_orig", errors[0])

    def test_latin_in_last_name_orig_detected(self):
        errors = self._cyrillic_errors(
            self.check_code('person("Иванъ", "Ивановъ", "ПетровR")')
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("last_name_orig", errors[0])

    def test_digit_in_name_detected(self):
        errors = self._cyrillic_errors(self.check_code('person("Иван1")'))
        self.assertEqual(len(errors), 1)

    def test_latin_in_name_modern_orth_detected(self):
        errors = self._cyrillic_errors(
            self.check_code('person("Иванъ", name_modern_orth="ИванX")')
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("name_modern_orth", errors[0])

    def test_latin_in_last_name_modern_orth_detected(self):
        errors = self._cyrillic_errors(
            self.check_code('person("Иванъ", last_name_modern_orth="ПетровQ")')
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("last_name_modern_orth", errors[0])

    def test_error_message_includes_value(self):
        errors = self._cyrillic_errors(self.check_code('person("Иванs")'))
        self.assertEqual(len(errors), 1)
        self.assertIn("Иванs", errors[0])

    def test_error_includes_line_number(self):
        errors = self._cyrillic_errors(self.check_code('x = 1\nperson("ИванX")'))
        self.assertEqual(len(errors), 1)
        self.assertIn(":2:", errors[0])


if __name__ == '__main__':
    unittest.main()
