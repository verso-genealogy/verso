"""Tests for the village.db staleness guard and the strict-failure hints."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from verso.ru.cli.all_persons import newer_than_db
from verso.ru.cli.find_person import stale_warning
from verso.ru.cli.generate_tf import strict_failure_hints
from verso.ru.dsl.kinds import SOURCE_PATTERNS


class TestNewerThanDb(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.village = Path(self.tmp.name)
        (self.village / "1818").mkdir()
        self.dsl = self.village / "1818" / "x_births_1818.py"
        self.dsl.write_text("# dsl", encoding="utf-8")
        self.db = self.village / "village.db"
        sqlite3.connect(self.db).close()

    def tearDown(self):
        self.tmp.cleanup()

    def _set_mtime(self, path: Path, when: float):
        os.utime(path, (when, when))

    def test_fresh_db_reports_nothing(self):
        self._set_mtime(self.dsl, 1000)
        self._set_mtime(self.db, 2000)
        self.assertEqual(newer_than_db(self.village, self.db), [])

    def test_edited_dsl_makes_the_db_stale(self):
        self._set_mtime(self.db, 1000)
        self._set_mtime(self.dsl, 2000)
        self.assertEqual(newer_than_db(self.village, self.db), [self.dsl])

    def test_missing_db_is_not_reported_as_stale(self):
        # find_person already has a dedicated "run all_persons" error for this;
        # the staleness guard must not double-report it.
        self.db.unlink()
        self.assertEqual(newer_than_db(self.village, self.db), [])

    def test_every_record_family_is_watched(self):
        # A record family present in SOURCE_PATTERNS but not actually globbed would
        # make edits to that family invisible to the guard.
        self._set_mtime(self.db, 1000)
        for i, pattern in enumerate(SOURCE_PATTERNS):
            with self.subTest(pattern=pattern):
                name = pattern.replace("*/", "").replace("*", f"v{i}")
                f = self.village / "1818" / name
                f.write_text("# dsl", encoding="utf-8")
                self._set_mtime(f, 2000)
                self.assertIn(f, newer_than_db(self.village, self.db))
                f.unlink()

    def test_all_persons_and_find_person_share_one_pattern_list(self):
        # Imported from all_persons, never re-declared in find_person — the two
        # drifting apart is how external_sources/name_lists went unindexed before.
        import verso.ru.cli.find_person as fp
        self.assertIs(fp.newer_than_db, newer_than_db)


class TestStaleWarning(unittest.TestCase):

    def test_names_the_count_and_the_fix(self):
        msg = stale_warning([Path("a_births_1818.py")], "Заманиловка")
        self.assertIn("older than 1 DSL file", msg)
        self.assertIn("verso all-persons 'Заманиловка'", msg)
        # The point of the guard: an empty result must not be read as absence.
        self.assertIn("NOT", msg)

    def test_truncates_a_long_list(self):
        files = [Path(f"f{i}_births_1818.py") for i in range(10)]
        msg = stale_warning(files, "Заманиловка")
        self.assertIn("older than 10 DSL file", msg)
        self.assertIn("+7 more", msg)


class TestStrictFailureHints(unittest.TestCase):

    def test_name_registry_failure_points_at_dsllint(self):
        exc = ValueError("Unrecognized patronymic 'Видоплясов' (original: 'Видоплясовъ')")
        lines = "\n".join(strict_failure_hints([(Path("К/1818/d.py"), exc)]))
        self.assertIn("verso dsllint", lines)
        self.assertIn("names.csv", lines)
        self.assertIn("К/1818/d.py", lines)

    def test_import_failure_points_at_the_import_block(self):
        lines = "\n".join(strict_failure_hints(
            [(Path("x.py"), ModuleNotFoundError("No module named 'z'"))]))
        self.assertIn("import block", lines)
        self.assertNotIn("names.csv", lines)

    def test_unknown_failure_still_gets_a_recipe(self):
        lines = "\n".join(strict_failure_hints([(Path("x.py"), RuntimeError("boom"))]))
        self.assertIn("verso dsllint", lines)

    def test_mixed_failures_get_both_recipes(self):
        lines = "\n".join(strict_failure_hints([
            (Path("a.py"), ValueError("Unrecognized patronymic 'X'")),
            (Path("b.py"), ImportError("cannot import name 'SMALLPOX'")),
        ]))
        self.assertIn("names.csv", lines)
        self.assertIn("import block", lines)


if __name__ == "__main__":
    unittest.main()
