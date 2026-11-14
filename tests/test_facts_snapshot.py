"""The findings snapshot is a ratchet: a count that moves fails until accepted.

`verso facts-snapshot` writes `<village>/facts_findings.tsv`; CI runs
`--snapshot-check` on every affected village. What the counts ARE is measured on
the corpus by that CI step; this pins the contract around them.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from verso.ru.cli import facts_snapshot as cli


class SnapshotContract(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp()) / "Тестовка"
        self.dir.mkdir()
        self.addCleanup(lambda: [p.unlink() for p in self.dir.iterdir()])

    def _with(self, text: str):
        def fake(_village_dir: Path) -> str:
            return text
        return mock.patch.object(cli, "findings_snapshot", fake)

    def test_write_then_check_is_clean(self):
        with self._with("check\tfindings\thigh\ndeath-age\t3\t3\n"):
            self.assertEqual(0, cli.snapshot(self.dir, check=False))
            self.assertEqual(0, cli.snapshot(self.dir, check=True))

    def test_a_moved_count_fails_the_check(self):
        with self._with("check\tfindings\thigh\ndeath-age\t3\t3\n"):
            cli.snapshot(self.dir, check=False)
        with self._with("check\tfindings\thigh\ndeath-age\t4\t3\n"), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            self.assertEqual(1, cli.snapshot(self.dir, check=True))

    def test_a_missing_snapshot_fails_the_check(self):
        with self._with("check\tfindings\thigh\n"), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            self.assertEqual(1, cli.snapshot(self.dir, check=True))

    def test_the_committed_file_says_how_to_regenerate_it(self):
        header = cli._SNAPSHOT_HEADER.format(village="Тестовка")
        self.assertIn("verso facts-snapshot --village Тестовка", header)
        self.assertTrue(header.endswith("check\tfindings\thigh\n"))

    def test_a_village_of_two_words_is_quoted_in_the_header(self):
        header = cli.snapshot_header(Path("Две Тестовки"))
        self.assertIn("verso facts-snapshot --village 'Две Тестовки'\n", header)

    def test_a_village_of_two_words_is_quoted_in_the_check_hint(self):
        village = self.dir.parent / "Две Тестовки"
        village.mkdir()
        self.addCleanup(lambda: [q.unlink() for q in village.iterdir()] and None)
        with self._with("check\tfindings\thigh\n"), mock.patch("sys.stdout"), \
                mock.patch("sys.stderr") as err:
            cli.snapshot(village, check=True)
        said = "".join(call.args[0] for call in err.write.call_args_list)
        self.assertIn("`verso facts-snapshot --village 'Две Тестовки'`", said)


if __name__ == "__main__":
    unittest.main()
