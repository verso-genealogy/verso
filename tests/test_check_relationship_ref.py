#!/usr/bin/env python3
"""Tests for check_relationship_ref.py"""

import ast
import tempfile
import unittest
from pathlib import Path

from verso.ru.linters.checks.relationship_ref import (
    RelationshipRefChecker, check_file, check_file_structured, is_allowed, suggest)


def _walk(code: str) -> list[tuple[int, str, str | None]]:
    tree = ast.parse(code)
    checker = RelationshipRefChecker(Path("<test>"))
    checker.visit(tree)
    return checker.violations


class TestIsAllowed(unittest.TestCase):
    def test_exact_allowlist(self):
        for ref in ("жених", "невеста", "мать", "восприемница"):
            self.assertTrue(is_allowed(ref), ref)

    def test_pattern_allowlist(self):
        for ref in ("восприемника №1", "восприемника №2", "восприемника №10"):
            self.assertTrue(is_allowed(ref), ref)

    def test_disallowed(self):
        for ref in (
            "восприемника 2",         # missing №
            "воспреемника №1",        # misspelling
            "невесты",                 # wrong case
            "father of bride",         # English
            "восприемница 1",          # extra digit
            "",
        ):
            self.assertFalse(is_allowed(ref), ref)


class TestSuggest(unittest.TestCase):
    def test_missing_numero_sign(self):
        self.assertEqual(suggest("восприемника 2"), "восприемника №2")

    def test_misspelling(self):
        self.assertEqual(suggest("воспреемника №1"), "восприемника №1")

    def test_misspelling_plus_missing_numero(self):
        # "воспреемника 3" — both errors at once
        self.assertEqual(suggest("воспреемника 3"), "восприемника №3")

    def test_genitive_nevesta(self):
        self.assertEqual(suggest("невесты"), "невеста")

    def test_no_suggestion(self):
        self.assertIsNone(suggest("totally unrelated"))


class TestRelationshipRefChecker(unittest.TestCase):
    def test_canonical_refs_pass(self):
        cases = [
            'birth(1, child=person("X"), relatives=[relative(person("Y"), Relationship.FATHER, "восприемника №1")])',
            'birth(1, child=person("X"), relatives=[relative(person("Y"), Relationship.FATHER, "невеста")])',
            'birth(1, child=person("X"), relatives=[relative(person("Y"), Relationship.MOTHER, "мать")])',
            'birth(1, child=person("X"), relatives=[relative(person("Y"), Relationship.MOTHER, "восприемница")])',
            'marriage(1, relatives=[relative(person("Z"), Relationship.FATHER, "жених")])',
        ]
        for code in cases:
            self.assertEqual(_walk(code), [], code)

    def test_missing_numero_sign_flagged(self):
        # The exact case from Горюхино/1833 just before the linter was added.
        code = 'birth(17, child=person("X"), relatives=[relative(person("Y"), Relationship.FATHER, "восприемника 2")])'
        violations = _walk(code)
        self.assertEqual(len(violations), 1)
        _line, ref, suggestion = violations[0]
        self.assertEqual(ref, "восприемника 2")
        self.assertEqual(suggestion, "восприемника №2")

    def test_misspelling_flagged(self):
        code = 'birth(1, relatives=[relative(person("Y"), Relationship.FATHER, "воспреемника №1")])'
        violations = _walk(code)
        self.assertEqual(len(violations), 1)
        _line, ref, suggestion = violations[0]
        self.assertEqual(ref, "воспреемника №1")
        self.assertEqual(suggestion, "восприемника №1")

    def test_kwarg_form_flagged(self):
        code = (
            'birth(1, relatives=[relative(person("Y"), Relationship.FATHER, '
            'relationship_ref="невесты")])'
        )
        violations = _walk(code)
        self.assertEqual(len(violations), 1)
        _line, ref, suggestion = violations[0]
        self.assertEqual(ref, "невесты")
        self.assertEqual(suggestion, "невеста")

    def test_missing_ref_ignored(self):
        # No relationship_ref on the relative — bare relative is fine.
        code = 'birth(1, relatives=[relative(person("Y"), Relationship.FATHER)])'
        self.assertEqual(_walk(code), [])

    def test_relative_outside_record_ignored(self):
        # `relative()` not inside birth/marriage/death is left alone.
        code = 'standalone_relative = relative(person("Y"), Relationship.FATHER, "восприемника 2")'
        self.assertEqual(_walk(code), [])

    def test_marriage_record_canonical(self):
        code = 'marriage(1, relatives=[relative(person("Y"), Relationship.MOTHER, "невеста")])'
        self.assertEqual(_walk(code), [])

    def test_multiple_relatives_per_record(self):
        code = (
            'birth(1, relatives=['
            ' relative(person("A"), Relationship.FATHER, "восприемника №1"),'
            ' relative(person("B"), Relationship.MOTHER, "восприемница"),'
            ' relative(person("C"), Relationship.FATHER, "восприемника 2"),'
            '])'
        )
        violations = _walk(code)
        self.assertEqual(len(violations), 1)
        _line, ref, _suggestion = violations[0]
        self.assertEqual(ref, "восприемника 2")


class TestCheckFile(unittest.TestCase):
    def _write(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.close()
        return Path(f.name)

    def test_check_file_returns_path_line_message(self):
        path = self._write(
            'birth(1, relatives=[relative(person("Y"), Relationship.FATHER, "восприемника 2")])\n'
        )
        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertIn(str(path), errors[0])
            self.assertIn("восприемника 2", errors[0])
            self.assertIn('did you mean "восприемника №2"', errors[0])
        finally:
            path.unlink()

    def test_check_file_clean(self):
        path = self._write(
            'birth(1, relatives=[relative(person("Y"), Relationship.FATHER, "восприемника №1")])\n'
        )
        try:
            self.assertEqual(check_file(path), [])
        finally:
            path.unlink()

    def test_check_file_syntax_error(self):
        path = self._write("def broken(:\n")
        try:
            errors = check_file(path)
            self.assertEqual(len(errors), 1)
            self.assertIn("SyntaxError", errors[0])
        finally:
            path.unlink()

    def test_check_file_structured_includes_fix(self):
        path = self._write(
            'birth(1, relatives=[relative(person("Y"), Relationship.FATHER, "восприемника 2")])\n'
        )
        try:
            issues = check_file_structured(path)
            self.assertEqual(len(issues), 1)
            issue = issues[0]
            self.assertEqual(issue["level"], "error")
            self.assertIn("fix", issue)
            self.assertEqual(issue["fix"], {
                "type": "replace_kwarg",
                "old": '"восприемника 2"',
                "new": '"восприемника №2"',
            })
        finally:
            path.unlink()

    def test_check_file_structured_no_fix_when_no_suggestion(self):
        path = self._write(
            'birth(1, relatives=[relative(person("Y"), Relationship.FATHER, "totally bogus")])\n'
        )
        try:
            issues = check_file_structured(path)
            self.assertEqual(len(issues), 1)
            self.assertNotIn("fix", issues[0])
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
