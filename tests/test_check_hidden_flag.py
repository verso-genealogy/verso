import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.hidden_flag as check_hidden_flag


class TestCheckHiddenFlag(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_hidden_flag.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def test_string_record_number_flagged(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(12, person("Трофим"), CensusRole.BROTHER, "?", '
            'record_number="27-12")\n'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1)
        self.assertIn("record_number must be int", errors[0])

    def test_otsutstvuet_comment_without_hidden_flagged(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(3, person("Андрей"), CensusRole.SON, "?", '
            'comment="Отсутствует в РС 1834; персона добавлена вручную.")\n'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1)
        self.assertIn("hidden=True", errors[0])

    def test_otsutstvuet_comment_with_hidden_true_passes(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(3, person("Андрей"), CensusRole.SON, "?", '
            'hidden=True, '
            'comment="Отсутствует в РС 1834; персона добавлена вручную.")\n'
        )
        self.assertEqual(self._check(src), [])

    def test_int_record_number_passes(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(1, person("Иван"), CensusRole.HEAD, 30, '
            'record_number=42)\n'
        )
        self.assertEqual(self._check(src), [])

    def test_plain_member_passes(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(1, person("Иван"), CensusRole.HEAD, 30)\n'
        )
        self.assertEqual(self._check(src), [])

    def test_hidden_true_alone_passes(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(1, person("Семен"), None, "?", hidden=True)\n'
        )
        self.assertEqual(self._check(src), [])


if __name__ == "__main__":
    unittest.main()
