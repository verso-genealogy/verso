import inspect
import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.deaths_residence as check_deaths_residence
from verso.ru.dsl.records import deaths


def _deaths(*death_lines: str) -> str:
    """Wrap death() snippets in a death_records with a RecordDefaults residence."""
    body = ",\n".join(death_lines)
    return (
        'death_records("a", "f", "i", "c", "Заманиловка", "Церковь", 1816,\n'
        f"{body},\n"
        '    defaults=RecordDefaults(residence="Заманиловка"))\n'
    )


class TestCheckDeathsResidence(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_deaths_residence.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _structured(self, src: str) -> list[dict[str, object]]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_deaths_residence.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()

    # --- DRA001: contradictory explicit residences ---

    def test_differing_explicit_residences_flagged(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Заманиловка"), age=1, relatives=[relative(person("Петр", '
            'residence="Шпонькин Бор"), Relationship.FATHER)])',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("DRA001", errors[0])
        self.assertIn("Шпонькин Бор", errors[0])

    def test_second_relative_contradicting_anchor_flagged(self):
        src = _deaths(
            "    death(1, Gender.MALE, 5, 6, deceased=person(\"Иван\"), age=1,\n"
            "          relatives=[relative(person(\"Петр\", "
            'residence="Шпонькин Бор"), Relationship.FATHER),\n'
            '                     relative(person("Мария", residence="Елатьма"), '
            "Relationship.MOTHER)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("DRA001", errors[0])
        self.assertIn("Елатьма", errors[0])

    def test_contradiction_suppresses_redundancy_message(self):
        """A mismatched deceased gets DRA001 only — never also DRA002."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Заманиловка"), age=1, relatives=[relative(person("Петр", '
            'residence="Шпонькин Бор"), Relationship.FATHER)])',
        )
        errors = self._check(src)
        self.assertFalse([e for e in errors if "DRA002" in e], errors)

    # --- DRA002: deceased repeats the household anchor ---

    def test_equal_explicit_residences_flag_the_relative(self):
        """The deceased is the record's subject and keeps the residence in the
        DSL; the relative's copy is the redundant one."""
        src = _deaths(
            '    death(1, Gender.FEMALE, 12, 14, deceased=person("Пелагея", '
            'residence="Собакевичево"), age="3 мес", relatives=[relative(person("Прохор", '
            '"Лукин", residence="Собакевичево"), Relationship.FATHER)])',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("DRA002", errors[0])
        self.assertIn("relative lives at the deceased's residence", errors[0])

    def test_redundant_residence_fix_is_col_pinned_to_the_relative(self):
        """Both kwargs sit on one line — the remove fix must carry a col that
        pins the RELATIVE's occurrence, or the IDE would strip the deceased's."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Шпонькин Бор"), age=1, relatives=[relative(person("Петр", '
            'residence="Шпонькин Бор"), Relationship.FATHER)])',
        )
        issues = self._structured(src)
        self.assertEqual(len(issues), 1, issues)
        fix = issues[0]["fix"]
        self.assertEqual(fix["type"], "remove_kwarg")  # type: ignore[index]
        self.assertEqual(fix["kwarg"], "residence")  # type: ignore[index]
        line = src.splitlines()[int(issues[0]["line"]) - 1]  # type: ignore[arg-type]
        col = int(fix["col"])  # type: ignore[index]
        self.assertTrue(line[col:].startswith('residence="Шпонькин Бор"'))
        # …and it is the SECOND occurrence on the line (the relative's)
        self.assertGreater(col, line.find('residence="Шпонькин Бор"'))

    def test_positional_relative_residence_flagged_without_fix(self):
        # person(first, patr, last, first_modern, patr_modern, last_modern,
        #        residence, ...) — residence is positional index 6.
        positional = ('person("Петр", "", "", "", "", "", "Шпонькин Бор")')
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            f'residence="Шпонькин Бор"), age=1, relatives=[relative({positional}, '
            "Relationship.FATHER)])",
        )
        issues = self._structured(src)
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("DRA002", str(issues[0]["message"]))
        self.assertNotIn("fix", issues[0])

    def test_relatives_list_form_flags_redundant_relative(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Шпонькин Бор"), age=1, '
            'relatives=[relative(person("Петр", residence="Шпонькин Бор"), '
            "Relationship.FATHER)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("DRA002", errors[0])

    def test_contradicted_record_flags_no_redundancy(self):
        """The anchor is the FIRST relative stating a residence: removing the father's copy would hand him the
        mother's village, so only DRA001 is said."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Шпонькин Бор"), age=1, '
            'relatives=[relative(person("Петр", residence="Шпонькин Бор"), Relationship.FATHER), '
            'relative(person("Мария", residence="Елатьма"), Relationship.MOTHER)])',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("DRA001", errors[0])

    # --- clean records ---

    def test_implicit_deceased_residence_ok(self):
        """The generator derives it — nothing to report."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1, '
            'relatives=[relative(person("Петр", residence="Шпонькин Бор"), '
            "Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_implicit_relative_residence_ok(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Шпонькин Бор"), age=1, relatives=[relative(person("Петр"), '
            "Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_no_relative_ok(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Шпонькин Бор"), age=70)',
        )
        self.assertEqual(self._check(src), [])

    def test_no_residence_anywhere_ok(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1, '
            'relatives=[relative(person("Петр"), Relationship.FATHER)])',
        )
        self.assertEqual(self._check(src), [])

    def test_witness_residence_ignored(self):
        """Witnesses legitimately come from other villages."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1, '
            'relatives=[relative(person("Петр", residence="Шпонькин Бор"), '
            "Relationship.FATHER)], "
            'witness1=person("Федор", residence="Елатьма"))',
        )
        self.assertEqual(self._check(src), [])

    def test_dra002_is_a_warning(self):
        """A redundant kwarg shows yellow in the IDE (like ULC001)."""
        src = _deaths(
            '    death(1, Gender.FEMALE, 12, 14, deceased=person("Пелагея", '
            'residence="Собакевичево"), age="3 мес", relatives=[relative(person("Прохор", '
            '"Лукин", residence="Собакевичево"), Relationship.FATHER)])',
        )
        issues = self._structured(src)
        self.assertEqual([i["level"] for i in issues], ["warn"])

    def test_dra001_is_an_error(self):
        """Contradictory villages are a true data error — red in the IDE,
        even while the linter stays advisory in text mode / CI."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'residence="Заманиловка"), age=1, relatives=[relative(person("Петр", '
            'residence="Шпонькин Бор"), Relationship.FATHER)])',
        )
        issues = self._structured(src)
        self.assertEqual([i["level"] for i in issues], ["error"])

    def test_syntax_error_is_left_to_single_line_calls(self):
        """A half-typed IDE buffer must not produce one duplicate per linter —
        single_line_calls reports the SyntaxError once."""
        self.assertEqual(self._structured("death(1, Gender.MALE,\n"), [])



def test_the_positions_read_are_the_factorys():
    names = list(inspect.signature(deaths.death).parameters)
    assert (names.index("deceased"), names.index("relatives")) == (
        check_deaths_residence.DECEASED_AT, check_deaths_residence.RELATIVES_AT)


if __name__ == "__main__":
    unittest.main()
