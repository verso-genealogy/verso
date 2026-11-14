"""Tests for verso.ru.cli.generate_timeline — the timeline exporter CLI.

End-to-end over a synthetic one-record village (the pattern from
`test_generate_familio_tf.py`): real DSL → real translation → real HTML, but
small enough to stay fast. The policy-level cases live in
`test_timeline_projection.py`; what is checked here is that the wiring holds and
the file that lands on disk is self-contained and reproducible.
"""

import re
import tempfile
import textwrap
import unittest
from pathlib import Path

from verso.ru.cli.generate_timeline import main as timeline_main
from verso.ru.pipeline.translate import translate_village


def _make_village(td: str) -> Path:
    """A minimal synthetic village: one birth record with father + mother,
    so the translation yields three profiles and one parents' union."""
    village = Path(td) / "Тестовка"
    year = village / "1800"
    year.mkdir(parents=True)
    (year / "test_births_1800.py").write_text(textwrap.dedent('''
        from calendar import Month
        from verso.ru.dsl import birth, birth_month, birth_records
        from verso.ru.dsl import Gender, person

        test_births_1800 = birth_records(
            "A", "1", "1", "1", "Тестовка", "N", 1800,
            *birth_month(Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      mother=person("Марья", "Петрова"))),
        )
    '''))
    return village


def _family_res_names(village: Path) -> tuple[str, str, str]:
    """Resolve the (father, mother, child) canonical res_names the translation
    actually mints, so the tests don't guess transliterations."""
    gen, _ = translate_village(village, strict=True)
    profiles = gen.canonical_profiles()
    father = next(r for r in profiles if r.endswith("_father"))
    mother = next(r for r in profiles if r.endswith("_mother"))
    child = next(r for r in profiles if r.endswith("_child"))
    return father, mother, child


def _write_kin(village: Path, names) -> None:
    entries = "".join(f'    "{n}": None,\n' for n in names)
    (village / "familio_kin.py").write_text(
        "KIN: dict[str, str | None] = {\n" + entries + "}\n"
    )


class TimelineCliTest(unittest.TestCase):
    def test_writes_a_self_contained_page_for_the_kin(self):
        with tempfile.TemporaryDirectory() as td:
            village = _make_village(td)
            father, mother, child = _family_res_names(village)
            _write_kin(village, [father, mother, child])

            self.assertEqual(timeline_main(["--village", str(village), "--strict"]), 0)

            page = village / "timeline.html"
            self.assertTrue(page.exists())
            html = page.read_text(encoding="utf-8")
            self.assertIn("Тестовка — родословная лента", html)
            # Everyone in the registry is drawn and named. The DSL normalises
            # the names it was given into «Имя Отчество», so these are the
            # forms the translation actually mints.
            for name in ("Петр Сидорович", "Мария Петровна", "Иоанн Петрович"):
                self.assertIn(name, html)
            # Three people, one union: a birth node each, one marriage node.
            self.assertEqual(html.count('class="n-birth'), 3)
            self.assertEqual(html.count('class="n-mar hue'), 1)

    def test_page_pulls_no_data_and_no_scripts_from_the_network(self):
        """It has to survive being opened from disk, mailed, or published under
        a strict CSP — so the only remote reference allowed is the webfont."""
        with tempfile.TemporaryDirectory() as td:
            village = _make_village(td)
            _write_kin(village, list(_family_res_names(village)))
            timeline_main(["--village", str(village)])
            html = (village / "timeline.html").read_text(encoding="utf-8")

            self.assertNotIn("<script src=", html)
            self.assertNotIn("fetch(", html)
            hosts = set(re.findall(r"https?://([^/\"\'\s>]+)", html))
            self.assertEqual(hosts, {"fonts.googleapis.com", "fonts.gstatic.com"})

    def test_output_is_byte_identical_across_runs(self):
        """The whole staleness story rests on this: no timestamps, no `random`,
        no salted hashing, no unordered iteration."""
        with tempfile.TemporaryDirectory() as td:
            village = _make_village(td)
            _write_kin(village, list(_family_res_names(village)))
            first = Path(td) / "first.html"
            second = Path(td) / "second.html"
            timeline_main(["--village", str(village), "--output", str(first)])
            timeline_main(["--village", str(village), "--output", str(second)])
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_output_path_is_overridable(self):
        with tempfile.TemporaryDirectory() as td:
            village = _make_village(td)
            _write_kin(village, list(_family_res_names(village)))
            target = Path(td) / "nested" / "custom.html"
            self.assertEqual(
                timeline_main(["--village", str(village), "--output", str(target)]), 0)
            self.assertTrue(target.exists())
            self.assertFalse((village / "timeline.html").exists())

    def test_missing_kin_registry_errors_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            village = _make_village(td)
            with self.assertRaises(FileNotFoundError):
                timeline_main(["--village", str(village)])


if __name__ == "__main__":
    unittest.main()
