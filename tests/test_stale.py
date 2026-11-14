#!/usr/bin/env python3
"""Unit tests for generated-artifact staleness checks (verso.ru.cli.stale).

"Stale" = a generated artifact is out of date with its DSL source. This is NOT
`make tf-drift`, which means external Geni drift (edits made on geni.com).
"""
from __future__ import annotations

import unittest
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import village_fixture
from verso.ru.cli import stale


class TfStaleTest(unittest.TestCase):
    def _dirs(self) -> tuple[Path, Path]:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        committed, fresh = root / "committed", root / "fresh"
        committed.mkdir()
        fresh.mkdir()
        return committed, fresh

    def test_identical_trees_are_clean(self):
        committed, fresh = self._dirs()
        (committed / "mk_1862_birth.tf").write_text("resource {}\n")
        (fresh / "mk_1862_birth.tf").write_text("resource {}\n")
        self.assertEqual(stale.tf_stale("Маниловка", committed, fresh), [])

    def test_changed_generated_file_is_stale(self):
        committed, fresh = self._dirs()
        (committed / "mk_1862_birth.tf").write_text("old\n")
        (fresh / "mk_1862_birth.tf").write_text("new\n")
        msgs = stale.tf_stale("Маниловка", committed, fresh)
        self.assertEqual(len(msgs), 1)
        self.assertIn("mk_1862_birth.tf", msgs[0])

    def test_hand_maintained_file_is_ignored(self):
        """main.tf/projects.tf/_moved_manual_*.tf are never generated -> not stale."""
        committed, fresh = self._dirs()
        for name in ("main.tf", "projects.tf", "managed.tf",
                     "_moved_manual_profiles.tf", "_moved_renames.tf",
                     "_moved_auto_renames.tf"):
            (committed / name).write_text("hand written\n")
        self.assertEqual(stale.tf_stale("Маниловка", committed, fresh), [])

    def test_moved_consolidated_unions_is_hand_maintained(self):
        """_moved_consolidated_PROFILES.tf is generated; _moved_consolidated_UNIONS.tf
        is not ("`generate` does NOT emit this file"). A `_moved_consolidated_` prefix
        would wrongly flag the hand-written unions file as a stale leftover."""
        committed, fresh = self._dirs()
        (committed / "_moved_consolidated_unions.tf").write_text("hand written\n")
        self.assertEqual(stale.tf_stale("Маниловка", committed, fresh), [])

    def test_missing_generated_moved_consolidated_profiles_is_stale(self):
        committed, fresh = self._dirs()
        (committed / "_moved_consolidated_profiles.tf").write_text("generated\n")
        msgs = stale.tf_stale("Маниловка", committed, fresh)
        self.assertEqual(len(msgs), 1)
        self.assertIn("no longer generated", msgs[0])

    def test_orphaned_confession_list_file_is_stale(self):
        """A committed `ir_*.tf` the generator no longer emits is a leftover.

        `CONFESSION_LIST` pins `file_prefix="ir"`, so an исповедная роспись
        emits `ir_<year>_1.tf` exactly as a ревизская сказка emits
        `rs_<year>_1.tf`. The two directions of this check are guarded
        differently: an uncommitted or changed file is caught by name whatever
        its prefix, but the LEFTOVER branch asks `_is_generated()` — so a
        confession-list file whose DSL was deleted, renamed, or (as in
        Глуповы Горы 1855) un-reviewed would sit in the tree forever with
        the check reporting OK.
        """
        committed, fresh = self._dirs()
        (committed / "ir_1855_1.tf").write_text("orphan\n")
        msgs = stale.tf_stale("Глуповы Горы", committed, fresh)
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("ir_1855_1.tf", msgs[0])
        self.assertIn("no longer generated", msgs[0])

    def test_leftover_generated_file_is_stale(self):
        """A committed mk_*.tf the generator no longer emits = deleted DSL."""
        committed, fresh = self._dirs()
        (committed / "mk_1799_birth.tf").write_text("orphan\n")
        msgs = stale.tf_stale("Маниловка", committed, fresh)
        self.assertEqual(len(msgs), 1)
        self.assertIn("mk_1799_birth.tf", msgs[0])
        self.assertIn("no longer generated", msgs[0])

    def test_missing_committed_file_is_stale(self):
        """The generator emits a file that was never committed."""
        committed, fresh = self._dirs()
        (fresh / "mk_1900_birth.tf").write_text("new year\n")
        msgs = stale.tf_stale("Маниловка", committed, fresh)
        self.assertEqual(len(msgs), 1)
        self.assertIn("mk_1900_birth.tf", msgs[0])


class CsvStaleTest(unittest.TestCase):
    def _village_and_mirror(self) -> tuple[Path, Path]:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        village, mirror = root / "Заманиловка", root / "mirror"
        (village / "1822").mkdir(parents=True)
        (mirror / "1822").mkdir(parents=True)
        return village, mirror

    def test_matching_csv_is_clean(self):
        village, mirror = self._village_and_mirror()
        name = "Заманиловка_1822_births_familio.csv"
        (village / "1822" / name).write_text("a,b\n1,2\n")
        (mirror / "1822" / name).write_text("a,b\n1,2\n")
        self.assertEqual(stale.csv_stale(str(village), mirror), [])

    def test_changed_csv_is_stale(self):
        village, mirror = self._village_and_mirror()
        name = "Заманиловка_1822_births_familio.csv"
        (village / "1822" / name).write_text("old\n")
        (mirror / "1822" / name).write_text("new\n")
        msgs = stale.csv_stale(str(village), mirror)
        self.assertEqual(len(msgs), 1)
        self.assertIn(name, msgs[0])

    def test_uncommitted_csv_is_ignored(self):
        """The committed CSV set is a CURATED SUBSET — CSVs exist only for the years
        actually submitted to Familio (Горюхино: 1754-1861). A DSL year with no
        committed CSV is normal and must NOT fail the check."""
        village, mirror = self._village_and_mirror()
        (mirror / "1822" / "Заманиловка_1822_births_familio.csv").write_text("new\n")
        self.assertEqual(stale.csv_stale(str(village), mirror), [])

    def test_committed_csv_no_longer_generated_is_stale(self):
        village, mirror = self._village_and_mirror()
        (village / "1822" / "Заманиловка_1822_births_familio.csv").write_text("orphan\n")
        msgs = stale.csv_stale(str(village), mirror)
        self.assertEqual(len(msgs), 1)
        self.assertIn("no longer generated", msgs[0])

    def test_changed_census_csv_is_stale(self):
        """A census / confession-list CSV is exporter output like a familio one.

        The check globbed `*_familio.csv` alone, so `Глуповы Горы_1838_census.csv`
        stayed two lines behind a Verso proofread with `make stale-check` green,
        and eight more census CSVs had drifted the same way unnoticed."""
        village, mirror = self._village_and_mirror()
        name = "Заманиловка_1822_census.csv"
        (village / "1822" / name).write_text("Лист,Двор\n34,96\n")
        (mirror / "1822" / name).write_text("Лист,Двор\n34об,96\n")
        msgs = stale.csv_stale(str(village), mirror)
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn(name, msgs[0])
        self.assertIn("stale", msgs[0])

    def test_census_csv_with_an_archive_suffix_is_compared(self):
        """Several дела of one roll year write `…_census_<archive_suffix>.csv`."""
        village, mirror = self._village_and_mirror()
        name = "Заманиловка_1822_census_746-8-140.csv"
        (village / "1822" / name).write_text("old\n")
        (mirror / "1822" / name).write_text("new\n")
        msgs = stale.csv_stale(str(village), mirror)
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn(name, msgs[0])

    def test_census_csv_renamed_by_its_archive_suffix_is_a_leftover(self):
        """The exporter appends `archive_suffix` since 2026-06-18, so a census
        CSV committed before then under the bare name is no longer written —
        while its new name, never committed, is not reported."""
        village, mirror = self._village_and_mirror()
        (village / "1822" / "Заманиловка_1822_census.csv").write_text("old\n")
        (mirror / "1822" / "Заманиловка_1822_census_837-4-5247.csv").write_text("new\n")
        msgs = stale.csv_stale(str(village), mirror)
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("Заманиловка_1822_census.csv", msgs[0])
        self.assertIn("no longer generated", msgs[0])

    def test_uncommitted_census_csv_is_ignored(self):
        village, mirror = self._village_and_mirror()
        (mirror / "1822" / "Заманиловка_1822_census.csv").write_text("new\n")
        self.assertEqual(stale.csv_stale(str(village), mirror), [])

    def test_csv_outside_a_year_directory_is_not_compared(self):
        """`familio_submissions/location.csv` is curated by hand — no DSL writes it."""
        village, mirror = self._village_and_mirror()
        (village / "familio_submissions").mkdir()
        (village / "familio_submissions" / "location.csv").write_text("place\n")
        (village / "1822" / "transcriptions").mkdir()
        (village / "1822" / "transcriptions" / "page.csv").write_text("x\n")
        self.assertEqual(stale.csv_stale(str(village), mirror), [])

    def test_committed_but_deleted_from_the_worktree_is_reported(self):
        village, mirror = self._village_and_mirror()
        rel = Path("1822") / "Заманиловка_1822_census.csv"
        (mirror / rel).write_text("x\n")   # the village's copy was deleted
        msgs = stale.csv_stale(str(village), mirror, committed={rel})
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("missing from the working tree", msgs[0])


class LineEndingTest(unittest.TestCase):
    """A CRLF/LF difference alone must NOT read as stale.

    git has core.autocrlf=input, so it strips CR when storing. The exporters
    reproduce it (csv.writer emits \\r\\n, surviving inside quoted multi-line
    fields). A fresh CI checkout therefore holds LF while regeneration produces
    CRLF — a raw byte compare would flag those files stale on EVERY run and CI
    would be permanently red. Verified against a real checkout before fixing.
    """

    def test_crlf_vs_lf_is_not_stale_csv(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        village, mirror = root / "Заманиловка", root / "mirror"
        (village / "1822").mkdir(parents=True)
        (mirror / "1822").mkdir(parents=True)
        name = "Заманиловка_1822_births_familio.csv"
        # committed: LF (as git stores it).  regenerated: CRLF (as the exporter writes it)
        (village / "1822" / name).write_bytes(b'a,b\n"x\ny",2\n')
        (mirror / "1822" / name).write_bytes(b'a,b\r\n"x\r\ny",2\r\n')
        self.assertEqual(stale.csv_stale(str(village), mirror), [])

    def test_crlf_vs_lf_is_not_stale_tf(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        committed, fresh = root / "c", root / "f"
        committed.mkdir()
        fresh.mkdir()
        (committed / "mk_1862_birth.tf").write_bytes(b"resource {\n}\n")
        (fresh / "mk_1862_birth.tf").write_bytes(b"resource {\r\n}\r\n")
        self.assertEqual(stale.tf_stale("Маниловка", committed, fresh), [])

    def test_real_content_change_is_still_stale(self):
        """Normalising line endings must not mask an actual content difference."""
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        committed, fresh = root / "c", root / "f"
        committed.mkdir()
        fresh.mkdir()
        (committed / "mk_1862_birth.tf").write_bytes(b"Arefiev\r\n")
        (fresh / "mk_1862_birth.tf").write_bytes(b"Orefiev\n")
        self.assertEqual(len(stale.tf_stale("Маниловка", committed, fresh)), 1)


class CsvContainmentTest(unittest.TestCase):
    """check_csv must never write into the caller's CWD, nor into the village.

    Until 0.1.0 the year files ran as programs, and several Горюхино census files
    exported to whatever CWD they inherited: the first run of this checker leaked
    8 census CSVs into the repo root, and it learned to chdir into a mirror. Since
    `verso export-csv` writes where it is told — the temporary directory.
    """

    def test_check_csv_writes_nothing_outside_its_temporary_directory(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        village = village_fixture.root(root) / "Маниловка"
        before = {p: p.read_bytes() for p in village.rglob("*") if p.is_file()}
        caller = root / "caller"
        caller.mkdir()
        prev = Path.cwd()
        os.chdir(caller)
        try:
            stale.check_csv(str(village))
        finally:
            os.chdir(prev)

        self.assertEqual(list(caller.iterdir()), [], "check_csv wrote into the caller's CWD")
        self.assertEqual({p: p.read_bytes() for p in village.rglob("*") if p.is_file()}, before,
                         "check_csv wrote into the village")
        self.assertEqual(Path.cwd(), prev, "check_csv did not restore the CWD")


class CommittedMeansGitIndexTest(unittest.TestCase):
    """"Committed" is git's index, not a directory listing.

    Globbing made an untracked file count as committed, so a tree passed
    `make stale-check` locally (the file is on disk) and failed in CI (a fresh
    checkout has no untracked files) — a guard that disagrees with itself
    depending on where it runs. `Заманиловка/terraform/geni/mk_1819_birth.tf`
    sat unstaged for weeks behind exactly this.
    """

    def _repo(self) -> Path:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        tf = root / "terraform" / "geni"
        tf.mkdir(parents=True)
        prev = Path.cwd()
        os.chdir(root)
        self.addCleanup(os.chdir, prev)
        return root

    def test_untracked_file_is_not_committed(self):
        self._repo()
        tf = Path("terraform/geni")
        (tf / "mk_1818_birth.tf").write_text("tracked\n")
        (tf / "mk_1819_birth.tf").write_text("untracked\n")
        subprocess.run(["git", "add", str(tf / "mk_1818_birth.tf")], check=True)
        self.assertEqual(stale.committed_tf_names(tf), {"mk_1818_birth.tf"})

    def test_subdirectory_entries_are_excluded(self):
        """`git ls-files` recurses; terraform/geni/ has a scans/ subdir."""
        self._repo()
        tf = Path("terraform/geni")
        (tf / "scans").mkdir()
        (tf / "mk_1818_birth.tf").write_text("x\n")
        (tf / "scans" / "nested.tf").write_text("y\n")
        subprocess.run(["git", "add", "-A"], check=True)
        self.assertEqual(stale.committed_tf_names(tf), {"mk_1818_birth.tf"})

    def test_non_ascii_paths_survive_quotepath(self):
        """Without `-z`, core.quotePath returns `"\\320\\232..."` for Cyrillic
        village directories and nothing would ever match."""
        root = self._repo()
        village = Path("Заманиловка/terraform/geni")
        (root / village).mkdir(parents=True)
        (village / "mk_1819_birth.tf").write_text("x\n")
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "config", "core.quotePath", "true"], check=True)
        self.assertEqual(stale.committed_tf_names(village), {"mk_1819_birth.tf"})

    def test_falls_back_to_glob_outside_a_repository(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        loose = Path(tmp.name)
        (loose / "mk_1818_birth.tf").write_text("x\n")
        self.assertEqual(stale.committed_tf_names(loose), {"mk_1818_birth.tf"})

    def test_tf_stale_flags_a_generated_but_untracked_file(self):
        self._repo()
        tf = Path("terraform/geni")
        fresh = Path("fresh")
        fresh.mkdir()
        for d in (tf, fresh):
            (d / "mk_1819_birth.tf").write_text("same\n")
        # Content matches — only the missing git entry should be reported.
        msgs = stale.tf_stale("Заманиловка", tf, fresh)
        self.assertEqual(len(msgs), 1)
        self.assertIn("mk_1819_birth.tf", msgs[0])
        self.assertIn("NOT committed", msgs[0])

    def test_committed_csvs_reads_the_index(self):
        """Only what git stores, and only directly in a year directory."""
        self._repo()
        village = Path("Горюхино")
        (village / "1816" / "transcriptions").mkdir(parents=True)
        (village / "familio_submissions").mkdir()
        tracked = [
            village / "1816" / "Горюхино_1816_census_36-5-793.csv",
            village / "1816" / "Горюхино_1816_births_familio.csv",
            village / "1816" / "transcriptions" / "page.csv",
            village / "familio_submissions" / "location.csv",
        ]
        for p in tracked:
            p.write_text("x\n")
        (village / "1816" / "Собакевичево_1816_census_43-6-587-part-1.csv").write_text("u\n")
        subprocess.run(["git", "add", *map(str, tracked)], check=True)
        self.assertEqual(stale.committed_csvs(village), {
            Path("1816/Горюхино_1816_census_36-5-793.csv"),
            Path("1816/Горюхино_1816_births_familio.csv"),
        })

    def test_committed_csvs_does_not_depend_on_the_cwd(self):
        """check_csv passes the village as an absolute path, from wherever it runs."""
        root = self._repo()
        village = root / "Заманиловка"
        (village / "1828").mkdir(parents=True)
        (village / "1828" / "Заманиловка_1828_census.csv").write_text("x\n")
        subprocess.run(["git", "add", "-A"], check=True)
        os.chdir(village / "1828")
        self.assertEqual(stale.committed_csvs(village),
                         {Path("1828/Заманиловка_1828_census.csv")})

    def test_csv_stale_ignores_an_untracked_csv(self):
        """An untracked CSV on disk is not committed, however stale it is —
        in CI it would not exist, and the check must answer the same here."""
        self._repo()
        village, mirror = Path("Заманиловка"), Path("mirror")
        for d in (village, mirror):
            (d / "1828").mkdir(parents=True)
        (village / "1828" / "Заманиловка_1828_births_familio.csv").write_text("old\n")
        (mirror / "1828" / "Заманиловка_1828_births_familio.csv").write_text("new\n")
        self.assertEqual(stale.csv_stale(str(village), mirror), [])

    def test_tracked_but_deleted_from_the_worktree_is_reported(self):
        committed = {"mk_1818_birth.tf"}
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        tf, fresh = root / "tf", root / "fresh"
        tf.mkdir()
        fresh.mkdir()
        (fresh / "mk_1818_birth.tf").write_text("x\n")   # tf/ copy deleted
        msgs = stale.tf_stale("Маниловка", tf, fresh, committed=committed)
        self.assertEqual(len(msgs), 1)
        self.assertIn("missing from the working tree", msgs[0])


if __name__ == "__main__":
    unittest.main()
