import tempfile
import textwrap
import unittest
from pathlib import Path

from verso.ru.dsl.records.births import BirthRecords
from verso.ru.cli.generate_tf import main as generate_tf_main
from verso.core.pipeline import records as records_source
from verso.core.pipeline.load import discover_records
from verso.core.pipeline.records import export_village
from verso.ru.pipeline.translate import translate_village


class TestDSLDiscovery(unittest.TestCase):
    def test_finds_birth_records_without_running_main_side_effect(self):
        with tempfile.TemporaryDirectory() as td:
            village = Path(td) / "Тестовка"
            year = village / "1800"
            year.mkdir(parents=True)

            # The DSL file's `if __name__ == "__main__":` block writes a marker file.
            # If discovery runs it, the marker appears; if discovery skips it, no marker.
            marker = year / "SIDE_EFFECT_RAN"
            dsl = year / "test_births_1800.py"
            dsl.write_text(textwrap.dedent(f'''
                import os
                import sys
                from calendar import Month
                from verso.ru.dsl import birth, birth_month, birth_records
                from verso.ru.dsl import Gender, person

                test_births_1800 = birth_records(
                    "A", "1", "1", "1", "Тестовка", "N", 1800,
                    *birth_month(Month.MARCH,
                        birth(1, Gender.MALE, 10, 11,
                              child=person("Иван"),
                              father=person("Петр", "Сидоров"))),
                )

                if __name__ == "__main__":
                    open({str(marker)!r}, "w").write("ran")
            '''))

            found = list(discover_records(str(village)))

            self.assertFalse(marker.exists(),
                             "DSL __main__ side effect must not run during discovery")
            self.assertEqual(len(found), 1)
            _path, _name, records = found[0]
            self.assertIsInstance(records, BirthRecords)
            assert isinstance(records, BirthRecords)
            self.assertEqual(records.year, 1800)

    def test_an_aliased_record_set_is_discovered_once_under_its_first_name(self):
        # Заманиловка 1913: `zamanilovka_deaths_1913 = hlestakovka_deaths_1913`. One
        # book bound to two names is one book: read twice, the translator fed it
        # twice and the facts layer asserted its burial twice.
        with tempfile.TemporaryDirectory() as td:
            village = Path(td) / "Тестовка"
            year = village / "1800"
            year.mkdir(parents=True)
            (year / "test_births_1800.py").write_text(textwrap.dedent('''
                from calendar import Month
                from verso.ru.dsl import birth, birth_month, birth_records
                from verso.ru.dsl import Gender, person

                parish_births_1800 = birth_records(
                    "A", "1", "1", "1", "Тестовка", "N", 1800,
                    *birth_month(Month.MARCH,
                        birth(1, Gender.MALE, 10, 11,
                              child=person("Иван"),
                              father=person("Петр", "Сидоров"))),
                )

                test_births_1800 = parish_births_1800
            '''))

            found = list(discover_records(str(village)))
            self.assertEqual([name for _path, name, _records in found], ["parish_births_1800"])

            gen, _skipped = translate_village(village)
            self.assertEqual([name for name, _records in gen.fed_sources], ["test_births_1800.py"])

            with tempfile.TemporaryDirectory() as out:
                export_village(village, Path(out))
                with records_source.use(Path(out)):
                    from_json = list(discover_records(str(village)))
            self.assertEqual([name for _path, name, _records in from_json], ["parish_births_1800"])


class TestGenerateTfCli(unittest.TestCase):
    def _write_dsl(self, path: Path, var_name: str, village: str, year: int, record_num: int):
        path.write_text(textwrap.dedent(f'''
            import os, sys
            from calendar import Month
            from verso.ru.dsl import birth, birth_month, birth_records
            from verso.ru.dsl import Gender, person

            {var_name} = birth_records(
                "A", "1", "1", "1", {village!r}, "N", {year},
                *birth_month(Month.MARCH,
                    birth({record_num}, Gender.MALE, 10, 11,
                          child=person("Иван"),
                          father=person("Петр", "Сидоров"))),
            )

            if __name__ == "__main__":
                pass
        '''))

    def test_multi_book_year_combined_into_same_file(self):
        with tempfile.TemporaryDirectory() as td:
            village_dir = Path(td) / "V"
            year_dir = village_dir / "1754"
            year_dir.mkdir(parents=True)

            self._write_dsl(year_dir / "a_births_1754.py", "a_records", "V", 1754, 1)
            self._write_dsl(year_dir / "b_births_1754.py", "b_records", "V-Other", 1754, 99)

            output_dir = Path(td) / "out"
            rc = generate_tf_main([
                "--village", str(village_dir),
                "--output-dir", str(output_dir),
            ])
            self.assertEqual(rc, 0)

            tf = (output_dir / "mk_1754_birth.tf").read_text()
            self.assertIn("mk_births_1_child", tf)
            self.assertIn("mk_births_99_child", tf)

    def test_village_toml_projects_reach_every_profile(self):
        """The Geni projects of a village are its village.toml's, not a table keyed
        by the directory's name: every emitted profile carries them, in order."""
        with tempfile.TemporaryDirectory() as td:
            village_dir = Path(td) / "V"
            year_dir = village_dir / "1800"
            year_dir.mkdir(parents=True)
            self._write_dsl(year_dir / "a_births_1800.py", "a", "V", 1800, 1)
            (village_dir / "village.toml").write_text(
                'schema = 1\n[geni]\nprojects = ["data.geni_project.automatic_upload.id", '
                '"data.geni_project.gorjuhino.id"]\n', encoding="utf-8")

            output_dir = Path(td) / "out"
            rc = generate_tf_main([
                "--village", str(village_dir),
                "--output-dir", str(output_dir),
            ])
            self.assertEqual(rc, 0)

            tf = (output_dir / "mk_1800_birth.tf").read_text()
            self.assertIn(
                "projects = [data.geni_project.automatic_upload.id, data.geni_project.gorjuhino.id]",
                tf,
            )

    def test_generator_never_touches_unmanaged_files(self):
        with tempfile.TemporaryDirectory() as td:
            village_dir = Path(td) / "V"
            year_dir = village_dir / "1754"
            year_dir.mkdir(parents=True)
            self._write_dsl(year_dir / "a_births_1754.py", "a_records", "V", 1754, 1)

            output_dir = Path(td) / "out"
            output_dir.mkdir()
            # Pre-populate protected files with sentinel content.
            sentinel = "MANUAL - DO NOT OVERWRITE\n"
            for protected in ("managed.tf", "main.tf", "profiles.tf"):
                (output_dir / protected).write_text(sentinel)

            rc = generate_tf_main([
                "--village", str(village_dir),
                "--output-dir", str(output_dir),
            ])
            self.assertEqual(rc, 0)

            for protected in ("managed.tf", "main.tf", "profiles.tf"):
                self.assertEqual((output_dir / protected).read_text(), sentinel,
                                 f"{protected} was overwritten")
            # The generator still wrote its own file.
            self.assertTrue((output_dir / "mk_1754_birth.tf").exists())

    def test_full_run_deletes_orphan_year_files(self):
        """A full run drops stale mk_*/rs_* files for years that emit no
        content this run (e.g. a year re-transcribed entirely reviewed=False),
        while leaving protected manual files and the emitted year alone."""
        with tempfile.TemporaryDirectory() as td:
            village_dir = Path(td) / "V"
            year_dir = village_dir / "1754"
            year_dir.mkdir(parents=True)
            self._write_dsl(year_dir / "a_births_1754.py", "a_records", "V", 1754, 1)

            output_dir = Path(td) / "out"
            output_dir.mkdir()
            # Orphan generated files for a year with no DSL records, plus a
            # protected manual file that must never be deleted.
            (output_dir / "mk_1840_birth.tf").write_text("# orphan\n")
            (output_dir / "rs_1834_old.tf").write_text("# orphan census\n")
            (output_dir / "managed.tf").write_text("MANUAL\n")

            rc = generate_tf_main([
                "--village", str(village_dir),
                "--output-dir", str(output_dir),
            ])
            self.assertEqual(rc, 0)

            # Emitted year survives; orphans are removed; manual file untouched.
            self.assertTrue((output_dir / "mk_1754_birth.tf").exists())
            self.assertFalse((output_dir / "mk_1840_birth.tf").exists(),
                             "orphan mk_*.tf should be deleted on a full run")
            self.assertFalse((output_dir / "rs_1834_old.tf").exists(),
                             "orphan rs_*.tf should be deleted on a full run")
            self.assertEqual((output_dir / "managed.tf").read_text(), "MANUAL\n")

    def test_year_filtered_run_keeps_other_year_files(self):
        """A --year run must not delete other years' files (it only writes the
        requested year), so the orphan-cleanup is full-run only."""
        with tempfile.TemporaryDirectory() as td:
            village_dir = Path(td) / "V"
            for y in (1754, 1755):
                yd = village_dir / str(y)
                yd.mkdir(parents=True)
                self._write_dsl(yd / f"a_births_{y}.py", f"a_{y}", "V", y, 1)

            output_dir = Path(td) / "out"
            output_dir.mkdir()
            # Pretend 1755 was generated earlier.
            (output_dir / "mk_1755_birth.tf").write_text("# prior\n")

            rc = generate_tf_main([
                "--village", str(village_dir),
                "--output-dir", str(output_dir),
                "--year", "1754",
            ])
            self.assertEqual(rc, 0)

            self.assertTrue((output_dir / "mk_1754_birth.tf").exists())
            # 1755's file must survive a year-filtered run.
            self.assertTrue((output_dir / "mk_1755_birth.tf").exists(),
                            "year-filtered run must not delete other years")


class TestStrictSkipGuard(unittest.TestCase):
    """A DSL file that fails to import (e.g. a missing status constant) is
    skipped with a warning and silently drops all its records. --strict turns
    that into a hard failure so it can't slip through CI / `make generate`."""

    def _write_broken(self, path: Path):
        # References an undefined name → import fails → file is skipped.
        path.write_text(textwrap.dedent('''
            import sys
            from calendar import Month
            from verso.ru.dsl import birth, birth_month, birth_records
            from verso.ru.dsl import Gender, person

            broken = birth_records(
                "A", "1", "1", "1", "V", "N", 1800,
                *birth_month(Month.MARCH,
                    birth(1, Gender.MALE, 10, 11,
                          child=person("Иван", status=THIS_NAME_IS_NOT_DEFINED))),
            )
        '''))

    def test_discover_records_collects_skipped_files(self):
        with tempfile.TemporaryDirectory() as td:
            village = Path(td) / "V"
            year = village / "1800"
            year.mkdir(parents=True)
            self._write_broken(year / "broken_births_1800.py")

            skipped: list[tuple[Path, Exception]] = []
            found = list(discover_records(str(village), skipped=skipped))

            self.assertEqual(found, [])
            self.assertEqual(len(skipped), 1)
            path, exc = skipped[0]
            self.assertEqual(path.name, "broken_births_1800.py")
            self.assertIsInstance(exc, NameError)

    def test_strict_fails_on_skipped_file(self):
        with tempfile.TemporaryDirectory() as td:
            village = Path(td) / "V"
            year = village / "1800"
            year.mkdir(parents=True)
            self._write_broken(year / "broken_births_1800.py")
            output_dir = Path(td) / "out"

            rc = generate_tf_main([
                "--village", str(village),
                "--output-dir", str(output_dir),
                "--strict",
            ])

            self.assertEqual(rc, 2)
            # Aborted before writing the corrupted consolidated tree.
            self.assertFalse((output_dir / "consolidated_profiles_1.tf").exists())

    def test_non_strict_skips_without_failing(self):
        with tempfile.TemporaryDirectory() as td:
            village = Path(td) / "V"
            year = village / "1800"
            year.mkdir(parents=True)
            self._write_broken(year / "broken_births_1800.py")
            output_dir = Path(td) / "out"

            rc = generate_tf_main([
                "--village", str(village),
                "--output-dir", str(output_dir),
            ])

            self.assertEqual(rc, 0)


class BuildMovedConsolidatedProfiles(unittest.TestCase):
    """P3: the keeper-pin gotcha early warning — comparing the about-to-be-
    written moved blocks against the committed file (no live state needed)."""

    @staticmethod
    def _build(targets, previous=""):
        from types import SimpleNamespace

        from verso.ru.cli.generate_tf import build_moved_consolidated_profiles
        return build_moved_consolidated_profiles(
            SimpleNamespace(profiles_to_consolidate=targets), previous)

    @staticmethod
    def _prev(keeper, canonical):
        return (f"moved {{\n  from = geni_profile.{keeper}\n"
                f"  to   = geni_profile.{canonical}\n}}\n")

    def test_emits_moved_keeper_and_removed_for_rest(self):
        content, warnings = self._build({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan", "_c_ivan"]},
        })
        self.assertIn("from = geni_profile._a_ivan", content)
        self.assertIn("to   = geni_profile.ivan_petrov", content)
        self.assertIn("from = geni_profile._b_ivan", content)
        self.assertIn("destroy = false", content)
        self.assertEqual(warnings, [])

    def test_keeper_change_on_applied_canonical_warns(self):
        # Previously applied with keeper _b_ivan; a freshly merged _a_ivan now
        # sorts first → the moved would destroy _a_ivan on apply.
        content, warnings = self._build({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }, self._prev("_b_ivan", "ivan_petrov"))
        self.assertEqual(len(warnings), 1)
        self.assertIn("ivan_petrov", warnings[0])
        self.assertIn("_b_ivan", warnings[0])   # the keeper to pin
        self.assertIn("_a_ivan", warnings[0])   # the dangerous new first record
        # Output stays deterministic (uses profile_names[0]); the pin/gate is
        # the fix, not a silent rewrite.
        self.assertIn("from = geni_profile._a_ivan", content)

    def test_explicit_keeper_suppresses_warning(self):
        _content, warnings = self._build({
            "ivan_petrov": {"generate_moved_block": True, "keeper": "_b_ivan",
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }, self._prev("_b_ivan", "ivan_petrov"))
        self.assertEqual(warnings, [])

    def test_unchanged_keeper_no_warning(self):
        _content, warnings = self._build({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }, self._prev("_a_ivan", "ivan_petrov"))
        self.assertEqual(warnings, [])

    def test_new_canonical_absent_from_previous_no_warning(self):
        _content, warnings = self._build({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }, self._prev("_x", "someone_else"))
        self.assertEqual(warnings, [])

    def test_old_keeper_no_longer_a_record_no_warning(self):
        # Old keeper dropped from profile_names entirely — not the gotcha.
        _content, warnings = self._build({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }, self._prev("_gone_ivan", "ivan_petrov"))
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
