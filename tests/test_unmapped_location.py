import ast
import tempfile
import unittest
from pathlib import Path
from typing import cast

import verso.ru.linters.checks.unmapped_location as check

# A known place of the corpus (corpus/places.toml) used as the in-scope parish.
HOME = "Нижняя Яичница"


def _records(*body: str, village: str = HOME, defaults: str | None = None) -> str:
    """Wrap snippets in a birth_records whose parish `village` decides scope."""
    inner = ",\n".join(body)
    tail = f",\n    defaults=RecordDefaults(residence={defaults!r})" if defaults else ""
    return f'birth_records("a", "f", "i", "c", "{village}", "Ц", 1900,\n{inner}{tail})\n'


def _collect_src(src: str):
    return check._collect(ast.parse(src), src.splitlines())


def _collect_person(person_call: str, village: str = HOME):
    src = _records(f"    birth(1, Gender.MALE, father={person_call})", village=village)
    return _collect_src(src)


class TestDetection(unittest.TestCase):
    """In-scope (parish is a known location) → person residences are checked."""

    def test_mapped_residence_ok(self):
        self.assertEqual(_collect_person('person("Иван", residence="Нижняя Яичница")'), [])

    def test_unmapped_residence_flagged(self):
        issues = _collect_person('person("Иван", residence="с. Ляхова")')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("ULC001", str(issues[0]["message"]))
        self.assertIn("с. Ляхова", str(issues[0]["message"]))

    def test_the_message_says_the_corpus_lacks_the_place(self):
        # The places are the corpus's (corpus/places.toml), not geni/locations.py; the place
        # stands in «ёлочки», which is how Verso finds the finding its offer answers.
        issues = _collect_person('person("Иван", residence="с. Ляхова")')
        self.assertEqual(str(issues[0]["message"]),
                         "[ULC001] место жительства: «с. Ляхова» нет среди мест корпуса — в TF уйдёт без блока "
                         "location. Добавьте место или напишите известное.")
        # Verso's offer finds the place in it: tests/test_review_validate.py.

    def test_positional_residence_flagged(self):
        # residence is positional index 6 of person()
        issues = _collect_person('person("И", "П", "Г", None, None, None, "с. Ляхова")')
        self.assertEqual(len(issues), 1, issues)

    def test_empty_none_and_absent_residence_ignored(self):
        self.assertEqual(_collect_person('person("Иван", residence="")'), [])
        self.assertEqual(_collect_person('person("Иван", residence=None)'), [])
        self.assertEqual(_collect_person('person("Иван")'), [])

    def test_unmapped_default_residence_flagged(self):
        issues = _collect_src(_records("    birth(1, Gender.MALE)", defaults="Деревня Игрек"))
        self.assertTrue(any("Деревня Игрек" in str(i["message"]) for i in issues), issues)

    def test_known_default_residence_ok(self):
        self.assertEqual(
            _collect_src(_records("    birth(1, Gender.MALE)", defaults=HOME)), [])


def _collect_member(member_args: str, village: str = HOME):
    src = (f'census_records("a", "f", "i", "d", "{village}", 1857,\n'
           f'  household(member(1, person("Иван"), CensusRole.HEAD{member_args}),\n'
           f'    family_id="1"))\n')
    return _collect_src(src)


class TestCensusMemberPlaces(unittest.TestCase):
    """member(origin=) / member(destination=) resolve through the same
    _location() as residences — unknown names silently drop the member's
    birth location / current-residence override."""

    def test_mapped_origin_ok(self):
        self.assertEqual(_collect_member(', origin="Горюхино"'), [])

    def test_unmapped_origin_flagged(self):
        issues = _collect_member(', origin="Выдумкино"')
        self.assertEqual(len(issues), 1, issues)
        msg = str(issues[0]["message"])
        self.assertIn("ULC001", msg)
        self.assertIn("откуда прибыл", msg)
        self.assertIn("Выдумкино", msg)

    def test_prose_origin_flagged(self):
        # a roll-shaped case: the prose string is passed whole to _location()
        # and silently drops — flag it like any other unmapped place
        issues = _collect_member(', origin="род. в с. Лапшово"')
        self.assertEqual(len(issues), 1, issues)

    def test_mapped_destination_ok(self):
        self.assertEqual(_collect_member(', destination="Горюхино"'), [])

    def test_unmapped_destination_flagged(self):
        issues = _collect_member(', destination="Выдумкино"')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("куда выбыл", str(issues[0]["message"]))

    def test_positional_origin_flagged(self):
        # origin is positional index 8 of member()
        issues = _collect_member(', None, 30, None, None, None, "Выдумкино"')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("откуда прибыл", str(issues[0]["message"]))

    def test_empty_none_and_absent_origin_ignored(self):
        self.assertEqual(_collect_member(', origin=""'), [])
        self.assertEqual(_collect_member(', origin=None'), [])
        self.assertEqual(_collect_member(''), [])

    def test_census_out_of_scope_village_skipped(self):
        self.assertEqual(
            _collect_member(', origin="Выдумкино"', village="Неведомово"), [])

    def test_issue_col_pins_the_flagged_literal_not_first_occurrence(self):
        # The same place name may appear earlier on the line (e.g. inside
        # departure_reason prose). The issue's col/end_col must span the
        # flagged kwarg's own string literal so IDE plugins highlight the
        # right occurrence — not the first substring match.
        line = ('member(1, person("Иванъ"), CensusRole.HEAD, '
                'departure_reason="переведён в деревню Небывалые Выселки", '
                'destination="Небывалые Выселки")')
        src = (f'census_records("a", "f", "i", "d", "{HOME}", 1858,\n'
               f'  household({line},\n'
               f'    family_id="1"))\n')
        collected = _collect_src(src)
        self.assertEqual(len(collected), 1, collected)
        issue = collected[0]
        self.assertIn("col", issue, issue)
        self.assertIn("end_col", issue, issue)
        col = cast(int, issue["col"])
        end_col = cast(int, issue["end_col"])
        line_text = src.split("\n")[cast(int, issue["line"]) - 1]
        self.assertEqual(line_text[col:end_col], '"Небывалые Выселки"')
        self.assertGreater(col, line_text.index("Небывалые Выселки"))


class TestScoping(unittest.TestCase):
    """Scope is decided by the parish village, from content — not the file path."""

    def test_csv_village_out_of_scope(self):
        # a parish absent from the corpus's places → whole file skipped. (Заманиловка,
        # the original fixture here, is a mapped TF village since 2026-07-15.)
        self.assertEqual(
            _collect_person('person("Иван", residence="с. Ляхова")', village="Неведомово"), [])

    def test_no_record_list_out_of_scope(self):
        self.assertEqual(_collect_src('person("Иван", residence="с. Ляхова")'), [])

    def test_tf_village_in_scope(self):
        self.assertEqual(
            len(_collect_person('person("Иван", residence="с. Ляхова")', village=HOME)), 1)

    def test_temp_path_still_flags(self):
        # The IntelliJ plugin lints an unsaved buffer via a temp file in the
        # system temp dir (no <village>/terraform/ parent). Scope is content-based,
        # so the warning must still fire there.
        src = _records('    birth(1, Gender.MALE, father=person("Иван", residence="с. Ляхова"))')
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(src)
            tmp = Path(f.name)
        try:
            out = check.check_file(tmp)
            self.assertEqual(len(out), 1, out)
            self.assertIn("ULC001", out[0])
            structured = check.check_file_structured(tmp)
            self.assertEqual(structured[0]["level"], "warn")
        finally:
            tmp.unlink()


if __name__ == "__main__":
    unittest.main()
