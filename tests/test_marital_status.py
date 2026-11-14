"""Tests for the MST001 marital_status linter + the marital-status constants."""
import tempfile
import unittest
from pathlib import Path

from verso.ru.domain.marital_status import MARITAL_STATUSES, MARRIED, SINGLE, WIDOW
from verso.ru.linters.checks.marital_status import check_file_structured


def _lint(code: str) -> list[dict[str, object]]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(code)
        p = Path(f.name)
    return check_file_structured(p)


class TestMaritalStatusConstants(unittest.TestCase):
    def test_canonical_values(self):
        self.assertEqual(MARRIED, "женат")
        self.assertEqual(SINGLE, "холост")
        self.assertEqual(WIDOW, "вдова")
        self.assertIn(MARRIED, MARITAL_STATUSES)


class TestMst001(unittest.TestCase):
    def test_known_literal_not_flagged_by_mst001(self):
        # A recognised literal is single_line_calls' "use constant" job, not MST001.
        issues = _lint('wwi_record(person("Иван"), source_url="x", '
                       'marital_status="женат")')
        self.assertEqual(issues, [])

    def test_unknown_literal_flagged_without_fix(self):
        issues = _lint('wwi_record(person("Иван"), source_url="x", '
                       'marital_status="в браке")')
        self.assertTrue(any("unknown marital_status" in str(i["message"])
                            for i in issues))
        self.assertNotIn("fix", issues[0])

    def test_constant_reference_accepted(self):
        issues = _lint('wwi_record(person("Иван"), source_url="x", '
                       'marital_status=MARRIED)')
        self.assertEqual(issues, [])

    def test_wwii_record_checked(self):
        issues = _lint('wwii_record(person("Иван"), source_url="x", '
                       'marital_status="в браке")')
        self.assertTrue(any("MST001" in str(i["message"]) for i in issues))

    def test_census_member_checked(self):
        issues = _lint('member(1, person("Иван"), HEAD, 40, '
                       'marital_status="вдовый")')
        self.assertTrue(any("MST001" in str(i["message"]) for i in issues))

    def test_no_marital_status_clean(self):
        issues = _lint('wwi_record(person("Иван"), source_url="x")')
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
