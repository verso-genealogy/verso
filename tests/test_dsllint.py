#!/usr/bin/env python3
"""Tests for dsllint.py — unified DSL linter wrapper."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


from tests.codepaths import child_env



class TestCheckFileJson(unittest.TestCase):
    """Test check_file_json() which runs all 3 linters on a file."""

    def _write_temp(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_clean_file_returns_empty_issues(self):
        from verso.ru.linters.dsllint import check_file_json
        # A file with no DSL calls should produce no issues
        p = self._write_temp("x = 1\n")
        try:
            results = check_file_json(p)
            for r in results:
                self.assertEqual(r["issues"], [], f"linter {r['linter']} should have no issues")
        finally:
            p.unlink()

    def test_multiline_person_detected(self):
        from verso.ru.linters.dsllint import check_file_json
        code = '''\
from genealogy import person
p = person(
    "Иван",
    "Петров",
)
'''
        p = self._write_temp(code)
        try:
            results = check_file_json(p)
            slc = next(r for r in results if r["linter"] == "single_line_calls")
            self.assertTrue(len(slc["issues"]) > 0, "should detect multi-line person()")
            self.assertEqual(slc["issues"][0]["line"], 2)
        finally:
            p.unlink()

    def test_syntax_error_reported(self):
        from verso.ru.linters.dsllint import check_file_json
        p = self._write_temp("def foo(\n")
        try:
            results = check_file_json(p)
            all_issues = [i for r in results for i in r["issues"]]
            self.assertTrue(len(all_issues) > 0, "syntax error should be reported")
            self.assertTrue(any("SyntaxError" in i["message"] for i in all_issues))
        finally:
            p.unlink()

    def test_all_linters_present(self):
        from verso.ru.linters.dsllint import check_file_json
        p = self._write_temp("x = 1\n")
        try:
            results = check_file_json(p)
            linters = {r["linter"] for r in results}
            self.assertEqual(linters, {
                "single_line_calls", "genders", "names", "relationship_ref",
                "ages", "hidden_flag", "parent_member", "birth_redundancy",
                "deaths_residence", "deaths_relatives", "deaths_burial_date",
                "marriage_residence", "parent_status",
                "census_redundancy", "census_status_redundancy", "census_age",
                "census_member_lines",
                "census_parent_link",
                "residence_title",
                "unmapped_location", "external_sources",
                "name_lists", "patronymic_form", "name_gender_agreement",
                "marital_status",
                "status_redundancy", "status_orthography", "relative_attachment",
                "reviewed_redundancy", "retractions",
                "witness_side", "witness_side_advisory", "civil_register",
                "civil_register_advisory", "dsl_imports", "divorces",
            })
        finally:
            p.unlink()

    def test_results_have_correct_file_path(self):
        from verso.ru.linters.dsllint import check_file_json
        p = self._write_temp("x = 1\n")
        try:
            results = check_file_json(p)
            for r in results:
                self.assertEqual(r["file"], str(p))
        finally:
            p.unlink()


class TestCliJsonOutput(unittest.TestCase):
    """Test the CLI --json mode produces valid JSON."""

    def _write_temp(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_json_flag_produces_valid_json(self):
        p = self._write_temp("x = 1\n")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "verso.ru.linters.dsllint", "--json", str(p)],
                capture_output=True, text=True, cwd=tempfile.gettempdir(), env=child_env(),
            )
            data = json.loads(result.stdout)
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 36)
        finally:
            p.unlink()

    def test_import_stays_dependency_light(self):
        # The IDE plugins (vscode-dsllint, intellij-dsllint) run dsllint.py
        # with a BARE python3 that has no venv packages installed. Importing
        # the linter registry must therefore never transitively pull the
        # translator package (whose __init__ imports third-party
        # dateutil) — when it does, dsllint crashes at import
        # outside the venv and the IDE silently shows ZERO warnings.
        code = (
            "import sys; import verso.ru.linters.dsllint; "
            "bad = [m for m in ('dateutil', "
            "'verso.ru.targets.geni.translator') if m in sys.modules]; "
            "print(','.join(bad))"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                cwd=tempfile.gettempdir(), env=child_env())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "",
                         f"heavy modules leaked into dsllint import: {result.stdout}")

    def test_json_with_errors(self):
        code = '''\
from genealogy import person
p = person(
    "Иван",
)
'''
        p = self._write_temp(code)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "verso.ru.linters.dsllint", "--json", str(p)],
                capture_output=True, text=True, cwd=tempfile.gettempdir(), env=child_env(),
            )
            data = json.loads(result.stdout)
            slc = next(r for r in data if r["linter"] == "single_line_calls")
            self.assertTrue(len(slc["issues"]) > 0)
        finally:
            p.unlink()

    def test_no_json_flag_outputs_to_stderr(self):
        code = '''\
from genealogy import person
p = person(
    "Иван",
)
'''
        p = self._write_temp(code)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "verso.ru.linters.dsllint", str(p)],
                capture_output=True, text=True, cwd=tempfile.gettempdir(), env=child_env(),
            )
            # Without --json, errors go to stderr, not stdout
            self.assertEqual(result.stdout.strip(), "")
            self.assertIn("person()", result.stderr)
        finally:
            p.unlink()

    def test_nonexistent_file(self):
        result = subprocess.run(
            [sys.executable, "-m", "verso.ru.linters.dsllint", "--json", "/nonexistent/file.py"],
            capture_output=True, text=True, cwd=tempfile.gettempdir(), env=child_env(),
        )
        data = json.loads(result.stdout)
        self.assertIsInstance(data, list)


class TestFixMetadata(unittest.TestCase):
    """Test that fixable issues include fix metadata."""

    def _write_temp(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_const_violation_has_fix(self):
        from verso.ru.linters.dsllint import check_file_json
        code = '''\
from genealogy import person
from births import birth, birth_records
from statuses import ECON_PEASANT_MALE, ECON_PEASANT_FEMALE
from genealogy import RecordDefaults
r = birth_records("A", "1", "1", "1", "V", "C", 1800,
    birth(1, "муж", 1, 1, child=person("Иван"), father=person("Петр", "Иванов", status="экономический крестьянин")),
    defaults=RecordDefaults(status_male=ECON_PEASANT_MALE, status_female=ECON_PEASANT_FEMALE))
'''
        p = self._write_temp(code)
        try:
            results = check_file_json(p)
            slc = next(r for r in results if r["linter"] == "single_line_calls")
            const_issues = [i for i in slc["issues"] if "fix" in i and i["fix"]["type"] == "replace_kwarg"]
            self.assertTrue(len(const_issues) > 0, "should have a replace_kwarg fix")
            fix = const_issues[0]["fix"]
            self.assertEqual(fix["type"], "replace_kwarg")
            self.assertEqual(fix["kwarg"], "status")  # the field: what Verso decides by
            self.assertIn('"', fix["old"])  # old is a quoted string literal
            self.assertTrue(fix["new"].isupper() or "_" in fix["new"])  # new is a constant name
        finally:
            p.unlink()

    def test_redundant_violation_has_fix(self):
        from verso.ru.linters.dsllint import check_file_json
        code = '''\
from genealogy import person, RecordDefaults
from births import birth, birth_records
from statuses import ECON_PEASANT_MALE, ECON_PEASANT_FEMALE
r = birth_records("A", "1", "1", "1", "V", "C", 1800,
    birth(1, "муж", 1, 1, child=person("Иван"), father=person("Петр", "Иванов", residence="V")),
    defaults=RecordDefaults(residence="V", status_male=ECON_PEASANT_MALE, status_female=ECON_PEASANT_FEMALE))
'''
        p = self._write_temp(code)
        try:
            results = check_file_json(p)
            slc = next(r for r in results if r["linter"] == "single_line_calls")
            remove_issues = [i for i in slc["issues"] if "fix" in i and i["fix"]["type"] == "remove_kwarg"]
            self.assertTrue(len(remove_issues) > 0, "should have a remove_kwarg fix")
            fix = remove_issues[0]["fix"]
            self.assertEqual(fix["type"], "remove_kwarg")
            self.assertIn(fix["kwarg"], ("residence", "status", "cause_of_death"))
        finally:
            p.unlink()

    def test_non_fixable_issue_has_no_fix(self):
        from verso.ru.linters.dsllint import check_file_json
        code = '''\
from genealogy import person
p = person(
    "Иван",
    "Петров",
)
'''
        p = self._write_temp(code)
        try:
            results = check_file_json(p)
            slc = next(r for r in results if r["linter"] == "single_line_calls")
            self.assertTrue(len(slc["issues"]) > 0)
            for issue in slc["issues"]:
                self.assertNotIn("fix", issue, "multi-line person() should not have a fix")
        finally:
            p.unlink()


class TestCrashSurfacing(unittest.TestCase):
    """A crashed check must report itself as an error finding in JSON mode —
    never silently pass as 'no issues' (the pre-registry wrapper swallowed
    every Exception into an empty issue list)."""

    def _write_temp(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_crashed_linter_reports_error_issue(self):
        from unittest import mock

        from verso.ru.linters import dsllint

        def boom(_path: Path):
            raise RuntimeError("simulated check bug")

        patched = tuple(
            dsllint.Linter(lt.name, boom, lt.plain, lt.advisory)
            if lt.name == "genders" else lt
            for lt in dsllint.LINTERS
        )
        p = self._write_temp("x = 1\n")
        try:
            with mock.patch.object(dsllint, "LINTERS", patched):
                results = dsllint.check_file_json(p)
            genders = next(r for r in results if r["linter"] == "genders")
            self.assertEqual(len(genders["issues"]), 1)
            issue = genders["issues"][0]
            self.assertEqual(issue["level"], "error")
            self.assertIn("crashed", issue["message"])
            self.assertIn("simulated check bug", issue["message"])
            # The other linters are unaffected
            names = next(r for r in results if r["linter"] == "names")
            self.assertEqual(names["issues"], [])
        finally:
            p.unlink()

    def test_raised_syntax_error_stays_quiet(self):
        """A check that RAISES SyntaxError (instead of self-reporting it, as
        most checks do) must not add a 'crashed' finding — the file's syntax
        error is already reported by the checks that handle it."""
        from unittest import mock

        from verso.ru.linters import dsllint

        def raises_syntax_error(_path: Path):
            raise SyntaxError("unexpected EOF")

        patched = tuple(
            dsllint.Linter(lt.name, raises_syntax_error, lt.plain, lt.advisory)
            if lt.name == "genders" else lt
            for lt in dsllint.LINTERS
        )
        p = self._write_temp("x = 1\n")
        try:
            with mock.patch.object(dsllint, "LINTERS", patched):
                results = dsllint.check_file_json(p)
            genders = next(r for r in results if r["linter"] == "genders")
            self.assertEqual(genders["issues"], [])
        finally:
            p.unlink()


if __name__ == '__main__':
    unittest.main()


def test_json_issue_keys(tmp_path):
    """Every finding of `dsllint --json` carries its code, params and token, after the message
    and before the columns and the fix; the rest is as before."""
    from verso.ru.linters.dsllint import check_file_json
    dsl = tmp_path / "v_births_1850.py"
    dsl.write_text('from verso.ru.dsl import birth_records, birth, person, Gender\n'
                   'b = birth_records("A", "1", "2", "3", "V", 1850,\n'
                   '    birth(1, Gender.MALE, 1, 2, child=person("Иван"), marital_status="бобыль"),\n'
                   '    birth(2, Gender.MALE, 1, 2, child=person("Иван",\n'
                   '        "Петров")))\n', encoding="utf-8")
    issues = [i for r in check_file_json(dsl) for i in r["issues"]]
    assert issues
    for issue in issues:
        keys = list(issue)
        assert keys[:6] == ["level", "line", "message", "code", "params", "token"], keys
        assert set(keys[6:]) <= {"col", "end_col", "fix"}
        assert issue["code"] and isinstance(issue["params"], dict)
    assert json.loads(json.dumps(issues, ensure_ascii=False)) == issues
