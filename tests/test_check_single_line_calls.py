#!/usr/bin/env python3
"""Tests for check_single_line_calls.py"""

import ast
import tempfile
import unittest
from pathlib import Path

from verso.ru.linters.checks.single_line_calls import Checker, check_file, KNOWN_CAUSES


class TestChecker(unittest.TestCase):
    """Tests for the Checker AST visitor."""

    def check_code(self, code: str) -> list[tuple[int, int, str]]:
        """Helper to run Checker on code string and return violations."""
        tree = ast.parse(code)
        checker = Checker()
        checker.visit(tree)
        return checker.violations

    def test_single_line_person_call_passes(self):
        """Single-line person() calls should not produce violations."""
        code = 'person("Ivan", patr="Petrovich", status="крестьянин")'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_multi_line_person_call_detected(self):
        """Multi-line person() calls should be detected."""
        code = '''person("Ivan",
       patr="Petrovich")'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        start, end, name = violations[0]
        self.assertEqual(name, "person")
        self.assertEqual(start, 1)
        self.assertEqual(end, 2)

    def test_multi_line_spanning_many_lines(self):
        """person() calls spanning multiple lines should report correct range."""
        code = '''person(
    "Ivan",
    patr="Petrovich",
    status="крестьянин"
)'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        start, end, _name = violations[0]
        self.assertEqual(start, 1)
        self.assertEqual(end, 5)

    def test_multiple_violations_detected(self):
        """Multiple multi-line person() calls should all be detected."""
        code = '''person("Ivan",
       patr="Petrovich")
x = 1
person("Maria",
       patr="Ivanovna")'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 2)

    def test_other_functions_ignored(self):
        """Non-person functions should not trigger violations."""
        code = '''some_other_function("arg1",
                        "arg2",
                        "arg3")'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_nested_person_call_detected(self):
        """person() nested inside other calls should be detected."""
        code = '''result = process(person("Ivan",
                         patr="Petrovich"))'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][2], "person")

    def test_method_call_person_detected(self):
        """obj.person() method calls should also be detected."""
        code = '''obj.person("Ivan",
          patr="Petrovich")'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_single_line_with_long_args_passes(self):
        """Long single-line calls should pass."""
        code = 'person("Иван", patr="Петрович", patr_orig="Петровъ", status="крестьянин", residence="с. Горюхино")'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_empty_file_passes(self):
        """Empty files should produce no violations."""
        violations = self.check_code("")
        self.assertEqual(violations, [])

    def test_file_without_person_passes(self):
        """Files without person() calls should pass."""
        code = '''
def foo():
    return bar(1, 2, 3)

x = something(
    a=1,
    b=2
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_single_line_person_in_list(self):
        """person() in a list on single line should pass."""
        code = '[person("Ivan", patr="P"), person("Maria", patr="I")]'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_multi_line_person_in_list_detected(self):
        """Multi-line person() in a list should be detected."""
        code = '''[person("Ivan",
         patr="P")]'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)


class TestCheckFile(unittest.TestCase):
    """Tests for the check_file function."""

    def test_valid_file_returns_no_errors(self):
        """Valid file should return empty error list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('person("Ivan", patr="Petrovich")\n')
            f.flush()
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(errors, [])
        finally:
            path.unlink()

    def test_invalid_file_returns_errors(self):
        """File with violations should return errors."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('person("Ivan",\n       patr="Petrovich")\n')
            f.flush()
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertIn("person() spans lines 1-2", errors[0])
            self.assertIn(str(path), errors[0])
        finally:
            path.unlink()

    def test_syntax_error_handled(self):
        """Syntax errors should be caught and reported."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def broken(\n')
            f.flush()
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertIn("SyntaxError", errors[0])
        finally:
            path.unlink()

    def test_error_format_includes_path_and_line(self):
        """Error messages should include file path and line number."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('x = 1\nperson("Ivan",\n       patr="P")\n')
            f.flush()
            path = Path(f.name)

        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            # Format should be: path:line: message
            self.assertRegex(errors[0], r'.+\.py:2: person\(\) spans lines 2-3')
        finally:
            path.unlink()


class TestConstantUsageCheck(unittest.TestCase):
    """Tests for the 'use constant instead of string literal' lint rule."""

    def check_code(self, code: str) -> list[tuple[int, str, str, str, int]]:
        tree = ast.parse(code)
        checker = Checker()
        checker.visit(tree)
        return checker.const_violations

    def test_string_literal_matching_constant_is_flagged(self):
        """String literal that matches a known constant should produce a violation."""
        code = 'person("Марія", "Иванова", status="девка из экономических крестьян")'
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        _, kw_arg, literal, const_name, _ = violations[0]
        self.assertEqual(kw_arg, "status")
        self.assertEqual(literal, "девка из экономических крестьян")
        self.assertEqual(const_name, "ECON_PEASANT_GIRL")

    def test_constant_reference_not_flagged(self):
        """Using the constant itself (not a string literal) should not produce a violation."""
        code = 'person("Марія", "Иванова", status=ECON_PEASANT_GIRL)'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_unknown_status_string_not_flagged(self):
        """String literals not in known constants should not produce a violation."""
        code = 'person("Марія", "Иванова", status="какой-то уникальный статус")'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_non_status_keyword_not_flagged(self):
        """String matching a known constant in a non-status keyword should not be flagged."""
        code = 'person("Марія", "Иванова", residence="девка из экономических крестьян")'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_status_male_keyword_is_checked(self):
        """status_male= keyword should also be checked for known constants."""
        code = 'birth_records(defaults=RecordDefaults(status_male="экономический крестьянин"))'
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        _, kw_arg, _, const_name, _ = violations[0]
        self.assertEqual(kw_arg, "status_male")
        self.assertEqual(const_name, "ECON_PEASANT_MALE")

    def test_status_female_keyword_is_checked(self):
        """status_female= keyword should also be checked for known constants."""
        code = 'RecordDefaults(status_female="экономическая крестьянка")'
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        _, kw_arg, _, const_name, _ = violations[0]
        self.assertEqual(kw_arg, "status_female")
        self.assertEqual(const_name, "ECON_PEASANT_FEMALE")

    def test_marital_status_literal_flagged_with_constant(self):
        """marital_status= literal matching a known constant → use-constant fix."""
        code = 'wwi_record(person("Иван"), marital_status="женат")'
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        _, kw_arg, literal, const_name, _ = violations[0]
        self.assertEqual(kw_arg, "marital_status")
        self.assertEqual(literal, "женат")
        self.assertEqual(const_name, "MARRIED")

    def test_marital_status_constant_reference_not_flagged(self):
        code = 'wwi_record(person("Иван"), marital_status=MARRIED)'
        self.assertEqual(self.check_code(code), [])

    def test_check_file_reports_constant_violations(self):
        """check_file should report use-constant violations in its error list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('person("Марія", "Иванова", status="девка из экономических крестьян")\n')
            f.flush()
            path = Path(f.name)
        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertIn("ECON_PEASANT_GIRL", errors[0])
            self.assertIn("девка из экономических крестьян", errors[0])
        finally:
            path.unlink()


class TestRedundantDefaults(unittest.TestCase):
    """Tests for detecting person() fields that duplicate RecordDefaults values."""

    def check_code(self, code: str) -> list[tuple[int, str, str, int]]:
        tree = ast.parse(code)
        checker = Checker()
        checker.visit(tree)
        return checker.redundant_violations

    def test_redundant_residence_flagged(self):
        code = '''
birth_records("A", "F", "I", "C", "Заманиловка", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                child=person("Иван"),
                father=person("Петр", "Иванов", residence="Заманиловка")),
        ),
    ),
    defaults=RecordDefaults(residence="Заманиловка", status_male=ECON_PEASANT_MALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        self.assertIn("residence", violations[0][2])
        self.assertIn("Заманиловка", violations[0][2])

    def test_non_default_residence_not_flagged(self):
        code = '''
birth_records("A", "F", "I", "C", "Заманиловка", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                father=person("Петр", "Иванов", residence="Собакевичево")),
        ),
    ),
    defaults=RecordDefaults(residence="Заманиловка"),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_redundant_residence_in_relative_flagged(self):
        code = '''
birth_records("A", "F", "I", "C", "Заманиловка", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                child=person("Иван"),
                father=person("Петр", "Иванов"),
                god_parent1=person("Сидор", "Алексеев"),
                relatives=[relative(person("Афанасий", "Назаров", residence="Заманиловка"), Relationship.FATHER, "восприемника №1")]),
        ),
    ),
    defaults=RecordDefaults(residence="Заманиловка", status_male=ECON_PEASANT_MALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        self.assertIn("residence", violations[0][2])
        self.assertIn("Заманиловка", violations[0][2])

    def test_non_default_residence_in_relative_not_flagged(self):
        code = '''
birth_records("A", "F", "I", "C", "Заманиловка", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                child=person("Иван"),
                father=person("Петр", "Иванов"),
                relatives=[relative(person("Афанасий", "Назаров", residence="Ротозейск"), Relationship.FATHER, "восприемника №1")]),
        ),
    ),
    defaults=RecordDefaults(residence="Заманиловка"),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_relative_status_not_flagged_against_status_male(self):
        # Relative status should NOT trigger redundancy against status_male — the
        # relative's gender depends on Relationship.FATHER/MOTHER/etc., which is
        # outside this checker's scope.
        code = '''
birth_records("A", "F", "I", "C", "Заманиловка", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                child=person("Иван"),
                father=person("Петр", "Иванов"),
                relatives=[relative(person("Афанасий", "Назаров", status="ясачный крестьянин"), Relationship.FATHER, "восприемника №1")]),
        ),
    ),
    defaults=RecordDefaults(status_male="ясачный крестьянин"),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_redundant_status_male_flagged(self):
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                father=person("Петр", "Иванов", status="ясачный крестьянин")),
        ),
    ),
    defaults=RecordDefaults(status_male="ясачный крестьянин"),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        self.assertIn("status", violations[0][2])

    def test_redundant_status_constant_flagged(self):
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                father=person("Петр", "Иванов", status=ECON_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_different_status_not_flagged(self):
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                father=person("Петр", "Иванов", status="купец")),
        ),
    ),
    defaults=RecordDefaults(status_male="ясачный крестьянин"),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_no_defaults_no_violations(self):
        code = 'person("Иван", "Петров", residence="Заманиловка", status="крестьянин")'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_redundant_cause_of_death_flagged(self):
        code = '''
death_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *death_month(Month.JANUARY,
            death(1, Gender.MALE, 1, 2,
                deceased=person("Иван"), cause_of_death="натуральная"),
        ),
    ),
    defaults=RecordDefaults(cause_of_death="натуральная"),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        self.assertIn("cause_of_death", violations[0][2])

    def test_redundant_cause_of_death_reports_kwarg_line(self):
        """Violation line should be the kwarg's line, not the death() call start."""
        code = '''
death_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *death_month(Month.JANUARY,
            death(1, Gender.MALE, 1, 2,
                deceased=person("Иван"),
                age=75,
                cause_of_death="натуральная"),
        ),
    ),
    defaults=RecordDefaults(cause_of_death="натуральная"),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        line = violations[0][0]
        # cause_of_death= is on line 9, death() starts on line 5
        self.assertGreater(line, 5, f"should report kwarg line, not call start line 5; got {line}")

    def test_check_file_reports_redundant_violations(self):
        code = '''
birth_records("A", "F", "I", "C", "Заманиловка", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                father=person("Петр", "Иванов", residence="Заманиловка")),
        ),
    ),
    defaults=RecordDefaults(residence="Заманиловка"),
)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            path = Path(f.name)
        try:
            errors = check_file(path)
            redundant_errors = [e for e in errors if "redundant" in e.lower()]
            self.assertEqual(len(redundant_errors), 1)
        finally:
            path.unlink()


class TestRedundantDefaultsRoleAware(unittest.TestCase):
    """Tests for role-aware redundant status detection (groom/bride vs witness)."""

    def check_code(self, code: str) -> list[tuple[int, str, str, int]]:
        tree = ast.parse(code)
        checker = Checker()
        checker.visit(tree)
        return checker.redundant_violations

    def test_redundant_status_col_targets_correct_kwarg_on_multi_status_line(self):
        """Regression: a single death() line with two status= kwargs — the
        deceased's (not redundant) and the witness's (redundant) — must report
        `col` at the WITNESS's status, not the first status on the line. Uses
        Cyrillic names so the AST byte-offset → char-column conversion is exercised."""
        source = (
            'death_records(1840,\n'
            '    deaths=[\n'
            '        death(19, Gender.MALE, 4, 5, '
            'deceased=person("Макар", status=ECON_PEASANT_BOY), '
            'witness1=person("Лука", "Фомин", status=ECON_PEASANT_MALE)),\n'
            '    ],\n'
            '    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE),\n'
            ')\n'
        )
        checker = Checker(source)
        checker.visit(ast.parse(source))
        self.assertEqual(len(checker.redundant_violations), 1)
        line, _func, message, col = checker.redundant_violations[0]
        self.assertIn("ECON_PEASANT_MALE", message)
        target_line = source.splitlines()[line - 1]
        # col must land on the witness's redundant status=, not the deceased's.
        self.assertTrue(
            target_line[col:].startswith("status=ECON_PEASANT_MALE"),
            f"col {col} pointed at {target_line[col:col + 26]!r}",
        )

    def test_deceased_female_name_status_female_is_redundant(self):
        """A female deceased whose status matches status_female is redundant."""
        code = '''
death_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *death_month(Month.JANUARY,
            death(1, Gender.FEMALE, 1, 2,
                deceased=person("Пелагея", "Игнатова", status=YASAK_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        self.assertIn("status", violations[0][2])

    def test_deceased_male_name_status_male_is_redundant(self):
        """Regression: a male deceased matching status_male is still flagged."""
        code = '''
death_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *death_month(Month.JANUARY,
            death(1, Gender.MALE, 1, 2,
                deceased=person("Иван", "Петров", status=YASAK_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_deceased_female_nondefault_status_not_flagged(self):
        """A female deceased with a status != status_female is not redundant."""
        code = '''
death_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *death_month(Month.JANUARY,
            death(1, Gender.FEMALE, 1, 2,
                deceased=person("Пелагея", "Игнатова", status=ECON_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_groom_status_matching_status_groom_is_redundant(self):
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                groom=person("Иван", "Петров", status=ECON_PEASANT_BOY)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE, status_groom=ECON_PEASANT_BOY),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_groom_status_matching_status_male_not_redundant_when_groom_differs(self):
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                groom=person("Иван", "Петров", status=ECON_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE, status_groom=ECON_PEASANT_BOY),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_bride_status_matching_status_bride_is_redundant(self):
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                bride=person("Мария", "Иванова", status=ECON_PEASANT_GIRL)),
        ),
    ),
    defaults=RecordDefaults(status_female=ECON_PEASANT_FEMALE, status_bride=ECON_PEASANT_GIRL),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_bride_status_matching_status_female_not_redundant_when_bride_differs(self):
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                bride=person("Мария", "Иванова", status=ECON_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_female=ECON_PEASANT_FEMALE, status_bride=ECON_PEASANT_GIRL),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_witness_status_matching_status_male_is_redundant(self):
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                witness1=person("Петр", "Иванов", status=ECON_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE, status_groom=ECON_PEASANT_BOY),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_witness5_and_witness6_status_matching_status_male_is_redundant(self):
        """witness5/witness6 are recognized by the linter the same way
        witness1..witness4 are: a male-named witness with status==status_male
        gets flagged as redundant."""
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                witness5=person("Василий", "Кондратьев", status=ECON_PEASANT_MALE),
                witness6=person("Давид", "Сидоров", status=ECON_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE, status_groom=ECON_PEASANT_BOY),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 2)

    def test_father_status_matching_status_male_is_redundant(self):
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                father=person("Петр", "Иванов", status=ECON_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_mother_status_matching_status_mother_is_redundant(self):
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                mother=person("Мария", "Иванова", status=ECON_PEASANT_LEGAL_WIFE)),
        ),
    ),
    defaults=RecordDefaults(status_female=ECON_PEASANT_FEMALE, status_mother=ECON_PEASANT_LEGAL_WIFE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_mother_status_matching_status_female_not_redundant_when_mother_differs(self):
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                mother=person("Мария", "Иванова", status=ECON_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_female=ECON_PEASANT_FEMALE, status_mother=ECON_PEASANT_LEGAL_WIFE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_mother_status_matching_status_female_is_redundant_when_no_status_mother(self):
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                mother=person("Мария", "Иванова", status=ECON_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_female=ECON_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_no_status_groom_means_status_male_applies_to_groom(self):
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                groom=person("Иван", "Петров", status=ECON_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)


    def test_witness4_female_name_status_female_is_redundant(self):
        """witness4 with female name and status_female default should be flagged."""
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                witness4=person("Пелагея", "Игнатова", status=YASAK_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)
        self.assertIn("redundant", violations[0][2])

    def test_witness3_female_name_status_female_is_redundant(self):
        """witness3 with female name and status_female default should be flagged."""
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                witness3=person("Анна", "Иванова", status=YASAK_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_witness4_male_name_status_male_is_redundant(self):
        """witness4 with male name and status_male default should be flagged."""
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                witness4=person("Николай", "Михайлов", status=YASAK_PEASANT_MALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)

    def test_witness4_female_name_nondefault_status_not_redundant(self):
        """witness4 with female name but non-default status should NOT be flagged."""
        code = '''
marriage_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *marriage_month(Month.JANUARY,
            marriage(1, 14,
                witness4=person("Пелагея", "Игнатова", status=MANILOV_PS_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_godparent_female_name_status_female_is_redundant(self):
        """god_parent1 with female name and status_female default should be flagged."""
        code = '''
birth_records("A", "F", "I", "C", "К", "Ц", 1800,
    *page("1",
        *birth_month(Month.JANUARY,
            birth(1, Gender.MALE, 1, 2,
                god_parent1=person("Мария", "Иванова", status=ECON_PEASANT_FEMALE)),
        ),
    ),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE, status_female=ECON_PEASANT_FEMALE),
)
'''
        violations = self.check_code(code)
        self.assertEqual(len(violations), 1)



class TestRedundantDefaultsNewbornStatus(unittest.TestCase):
    """A written status the newborn's (or the deceased child's) is derived
    from is not redundant: Birth/Death.__init__ derive before the defaults run."""

    _KAZ = ("status_male=KAZENNYJ_PEASANT_MALE, status_female=KAZENNYJ_PEASANT_FEMALE, "
            "status_mother=KAZENNYJ_PEASANT_LEGAL_WIFE")

    def check_code(self, code: str) -> list[tuple[int, str, str, int]]:
        tree = ast.parse(code)
        checker = Checker()
        checker.visit(tree)
        return checker.redundant_violations

    def _births(self, father: str, mother: str) -> list[tuple[int, str, str, int]]:
        return self.check_code(f'''
birth_records("A", "F", "I", "C", "К", "Ц", 1862,
    *birth_month(Month.NOVEMBER,
        birth(61, Gender.FEMALE, 8, 9,
            child=person("Фекла"),
            father={father},
            mother={mother}),
    ),
    defaults=RecordDefaults({self._KAZ}),
)
''')

    def test_mother_the_newborn_derives_from_is_not_flagged(self):
        violations = self._births('person("Назаръ", "Кузьминъ")',
                                  'person("Мелания", "Кузьмина", status=KAZENNYJ_PEASANT_LEGAL_WIFE)')
        self.assertEqual(violations, [])

    def test_of_two_redundant_parents_only_the_mother_is_flagged(self):
        violations = self._births('person("Назаръ", "Кузьминъ", status=KAZENNYJ_PEASANT_MALE)',
                                  'person("Мелания", "Кузьмина", status=KAZENNYJ_PEASANT_LEGAL_WIFE)')
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("KAZENNYJ_PEASANT_LEGAL_WIFE", violations[0][2])

    def test_deceased_child_of_a_father_with_a_status_is_not_flagged(self):
        # Without its own status the boy derives «солдатский сын» from his
        # father's — not the book's «казенный крестьянин».
        violations = self.check_code('''
death_records("A", "F", "I", "C", "К", "Ц", 1862,
    *death_month(Month.JANUARY,
        death(1, Gender.MALE, 1, 2,
            deceased=person("Иван", status=KAZENNYJ_PEASANT_MALE),
            relatives=[relative(person("Петр", "Иванов", status=SOLDIER), Relationship.FATHER)]),
    ),
    defaults=RecordDefaults(status_male=KAZENNYJ_PEASANT_MALE, status_female=KAZENNYJ_PEASANT_FEMALE),
)
''')
        self.assertEqual(violations, [])


@unittest.skipUnless(KNOWN_CAUSES, "causes_of_death.py not available")
class TestCauseOfDeathConstantCheck(unittest.TestCase):
    """Tests for cause-of-death constant suggestions."""

    def check_code(self, code: str) -> list[tuple[int, str, str, str, int]]:
        tree = ast.parse(code)
        checker = Checker()
        checker.visit(tree)
        return checker.const_violations

    def test_cause_of_death_literal_matching_constant_flagged(self):
        code = 'death(1, Gender.MALE, cause_of_death="оспа")'
        violations = self.check_code(code)
        cause_violations = [v for v in violations if v[1] == "cause_of_death"]
        self.assertEqual(len(cause_violations), 1)
        self.assertEqual(cause_violations[0][3], "SMALLPOX")

    def test_cause_of_death_alias_flagged(self):
        """Alias form like 'от колики' should map to the base constant COLIC."""
        code = 'death(1, Gender.MALE, cause_of_death="от колики")'
        violations = self.check_code(code)
        cause_violations = [v for v in violations if v[1] == "cause_of_death"]
        self.assertEqual(len(cause_violations), 1)
        self.assertEqual(cause_violations[0][3], "COLIC")

    def test_prereform_spelling_resolves_to_the_same_constant(self):
        """«отъ», ъ, ѣ and і spellings find the modern row, not a row of their own."""
        for literal, const in (("отъ чахотки", "CONSUMPTION"), ("кашлемъ", "COUGH"),
                               ("отъ слабосилія", "DEBILITY"), ("отъ дряхлости", "DECREPITUDE"),
                               ("отъ горла", "THROAT"), ("отъ поносу", "DIARRHEA"),
                               ("От чахотки", "CONSUMPTION"), ("от колик", "COLIC")):
            with self.subTest(literal=literal):
                violations = self.check_code(f'death(1, Gender.MALE, cause_of_death="{literal}")')
                self.assertEqual([(v[1], v[2], v[3]) for v in violations],
                                 [("cause_of_death", literal, const)])

    def test_unknown_prereform_cause_not_flagged(self):
        """A cause with no constant stays text, whatever its spelling."""
        for literal in ("отъ боли въ желудкѣ", "отъ рака", "от кошки"):
            with self.subTest(literal=literal):
                self.assertEqual(
                    self.check_code(f'death(1, Gender.MALE, cause_of_death="{literal}")'), [])

    def test_cause_of_death_constant_not_flagged(self):
        code = 'death(1, Gender.MALE, cause_of_death=SMALLPOX)'
        violations = self.check_code(code)
        self.assertEqual(violations, [])

    def test_unknown_cause_not_flagged(self):
        code = 'death(1, Gender.MALE, cause_of_death="неизвестная болезнь")'
        violations = self.check_code(code)
        cause_violations = [v for v in violations if v[1] == "cause_of_death"]
        self.assertEqual(cause_violations, [])

    def test_status_keyword_not_matched_as_cause(self):
        """status= keyword should not trigger cause-of-death check."""
        code = 'person("Иван", status="оспа")'
        violations = self.check_code(code)
        cause_violations = [v for v in violations if v[1] == "cause_of_death"]
        self.assertEqual(cause_violations, [])


if __name__ == '__main__':
    unittest.main()
