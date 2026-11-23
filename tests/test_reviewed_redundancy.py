"""RVR001 — `reviewed=` that restates the value it would already inherit."""
from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from verso.ru.linters.checks.reviewed_redundancy import check_file_structured


def findings(source: str) -> list[dict[str, object]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "records.py"
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return check_file_structured(path)


def messages(source: str) -> list[str]:
    return [str(f["message"]) for f in findings(source)]


class ListedPersonAgainstPage(unittest.TestCase):
    def test_true_under_a_page_that_says_true(self):
        found = findings("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("6 об.",
                    listed_person(214, person("Нилъ", "Пахомов", "Ладаев"), reviewed=True),
                    reviewed=True,
                ),
                reviewed=False,
            )
        """)
        self.assertEqual(1, len(found))
        self.assertIn("redundant reviewed=True", str(found[0]["message"]))
        self.assertIn('page("6 об.")', str(found[0]["message"]))

    def test_false_under_a_page_that_says_false_is_flagged_too(self):
        # Holding a лист is as repeatable as releasing one, and the removal is
        # the same no-op in both directions.
        self.assertEqual(1, len(findings("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("8 об.",
                    listed_person(417, person("Харитонъ", "Игнатьев", "Тюфякинъ"), reviewed=False),
                    reviewed=False,
                ),
                reviewed=True,
            )
        """)))

    def test_entry_that_disagrees_with_its_page_is_load_bearing(self):
        # Every level states something different, so nothing repeats anything.
        self.assertEqual([], messages("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("8 об.",
                    listed_person(417, person("Харитонъ", "Игнатьев", "Тюфякинъ"), reviewed=True),
                    reviewed=False,
                ),
                reviewed=True,
            )
        """))

    def test_entry_released_inside_an_unreleased_page(self):
        # The 1917 sweep's normal shape: the лист is still open (file default
        # False, page silent) and single entries are released against an older
        # verified extract. Nothing is redundant here.
        self.assertEqual([], messages("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("8 об.",
                    listed_person(417, person("Харитонъ", "Игнатьев", "Тюфякинъ"), reviewed=True),
                ),
                reviewed=False,
            )
        """))


class AgainstTheRecordSet(unittest.TestCase):
    def test_page_repeating_the_file_level_value(self):
        found = findings("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("5 об.",
                    listed_person(1, person("Тимонъ", "Пахомовъ", "Абдулин")),
                    reviewed=True,
                ),
                reviewed=True,
            )
        """)
        self.assertEqual(1, len(found))
        self.assertIn("redundant reviewed=True on page(\"5 об.\")", str(found[0]["message"]))

    def test_page_repeating_the_unstated_default(self):
        # `name_list_records` defaults to reviewed=True; a page saying so again
        # is redundant even though the file states nothing.
        self.assertIn("defaults to reviewed=True", messages("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("5 об.",
                    listed_person(1, person("Тимонъ", "Пахомовъ", "Абдулин")),
                    reviewed=True,
                ),
            )
        """)[0])

    def test_entry_outside_any_page_compares_against_the_file(self):
        self.assertEqual(1, len(findings("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                listed_person(1, person("Тимонъ", "Пахомовъ", "Абдулин"), reviewed=False),
                reviewed=False,
            )
        """)))

    def test_census_household_uses_the_same_three_levels(self):
        # `census_records` defaults to reviewed=True, so both the page and the
        # household repeat it.
        found = messages("""
            census = census_records(
                "ГАТО", "10", "4", "4044", "Маниловка", 1858,
                *page("16об-17",
                    household("1", member(1, person("Егоръ"), CensusRole.HEAD), reviewed=True),
                    reviewed=True,
                ),
            )
        """)
        self.assertEqual(2, len(found))
        self.assertTrue(any("household()" in m for m in found), found)
        self.assertTrue(any('page("16об-17")' in m for m in found), found)


class VitalRecords(unittest.TestCase):
    """Births, marriages and deaths default to `None` since 2026-10-03, so they
    resolve through page() and their record set like households do."""

    def test_true_restated_at_every_level(self):
        found = messages("""
            births = birth_records(
                "ГАРО", "637", "606", "847", "Хлестаковка", 1860,
                *page("5",
                    birth(6, person("Тимонъ"), person("Харитонъ"), reviewed=True),
                    reviewed=True,
                ),
            )
        """)
        self.assertEqual(2, len(found))
        self.assertTrue(any("birth()" in m for m in found), found)
        self.assertTrue(any('page("5")' in m for m in found), found)

    def test_every_vital_kind_and_its_record_set(self):
        for records, call in (("birth_records", "christening(1, Gender.MALE, 5, age=20, reviewed=True)"),
                              ("marriage_records", "marriage(1, 7, reviewed=True)"),
                              ("death_records", "death(1, Gender.MALE, 5, reviewed=True)")):
            with self.subTest(records):
                found = messages(f"""
                    book = {records}(
                        "ГАРО", "637", "606", "847", "Хлестаковка", "Вознесенская", 1860,
                        {call},
                    )
                """)
                self.assertEqual(1, len(found), found)
                self.assertIn(f"{records} defaults to reviewed=True", found[0])

    def test_a_divorce_and_its_record_set(self):
        found = messages("""
            divorces = divorce_records(
                "ГАПО", "1605", "59", "59", "Заманиловка", "", 1923,
                divorce(1, 3, reviewed=True),
                *page("2", divorce(2, 5, reviewed=False), reviewed=False),
                divorce(3, 7, reviewed=False),
            )
        """)
        self.assertEqual(2, len(found), found)
        self.assertTrue(any("divorce()" in m and "divorce_records defaults to reviewed=True" in m
                            for m in found), found)
        self.assertTrue(any("divorce()" in m and 'page("2")' in m for m in found), found)


class NotOurs(unittest.TestCase):
    def test_an_own_hold_under_a_default_file_is_load_bearing(self):
        # The Маниловка sweep: `reviewed=False` on the record, nothing around it.
        self.assertEqual([], messages("""
            births = birth_records(
                "ГАРО", "637", "606", "847", "Хлестаковка", 1860,
                birth(6, person("Тимонъ"), person("Харитонъ"), reviewed=False),
            )
        """))

    def test_a_flag_we_cannot_read_is_left_alone(self):
        # The page disagrees with the file, so the only candidate is the entry —
        # and its value is a name we cannot resolve, so it stays.
        self.assertEqual([], messages("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("5 об.",
                    listed_person(1, person("Иванъ"), reviewed=SWEEP_OPEN),
                    reviewed=True,
                ),
                reviewed=False,
            )
        """))

    def test_unreadable_file_level_value_disables_the_whole_call(self):
        self.assertEqual([], messages("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("5 об.",
                    listed_person(1, person("Иванъ"), reviewed=True),
                ),
                reviewed=SWEEP_OPEN,
            )
        """))

    def test_no_reviewed_anywhere(self):
        self.assertEqual([], messages("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("5 об.",
                    listed_person(1, person("Тимонъ", "Пахомовъ", "Абдулин")),
                ),
            )
        """))

    def test_syntax_error_is_silent(self):
        self.assertEqual([], messages("records = name_list_records(\n"))


class Fix(unittest.TestCase):
    def test_every_finding_carries_a_removal_fix(self):
        found = findings("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("6 об.",
                    listed_person(214, person("Нилъ", "Пахомов", "Ладаев"), reviewed=True),
                    reviewed=True,
                ),
                reviewed=True,
            )
        """)
        self.assertEqual(2, len(found))
        for f in found:
            self.assertEqual({"remove_kwarg"}, {str(f["fix"]["type"])})  # type: ignore[index]
            self.assertEqual("reviewed", f["fix"]["kwarg"])  # type: ignore[index]

    def test_fix_column_is_a_character_offset_not_a_byte_offset(self):
        # The kwarg sits after Cyrillic text, so a byte offset would overshoot
        # and the editor would delete the wrong span.
        found = findings("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("6 об.",
                    listed_person(214, person("Нилъ", "Пахомов", "Ладаев"), reviewed=True),
                ),
                reviewed=True,
            )
        """)
        self.assertEqual(1, len(found))
        line = found[0]["line"]
        col = found[0]["fix"]["col"]  # type: ignore[index]
        source = textwrap.dedent("""
            records = name_list_records(
                "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
                *page("6 об.",
                    listed_person(214, person("Нилъ", "Пахомов", "Ладаев"), reviewed=True),
                ),
                reviewed=True,
            )
        """).splitlines()
        self.assertTrue(source[int(str(line)) - 1][int(str(col)):].startswith("reviewed="))


if __name__ == "__main__":
    unittest.main()
