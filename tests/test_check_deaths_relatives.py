import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.deaths_relatives as check_deaths_relatives


def _deaths(*death_lines: str) -> str:
    """Wrap death() snippets in a death_records call."""
    body = ",\n".join(death_lines)
    return (
        'death_records("a", "f", "i", "c", "Заманиловка", "Церковь", 1816,\n'
        f"{body})\n"
    )


class TestCheckDeathsRelatives(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_deaths_relatives.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _structured(self, src: str) -> list[dict[str, object]]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_deaths_relatives.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()

    def test_flags_every_relative_past_the_first(self):
        """`add_death_records` emits relatives[0] only; the rest vanish without
        a profile, a union or a mention in the document body."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, None, deceased=person("Иван"), age=2,\n'
            "          relatives=[relative(person(\"Пётр\"), Relationship.FATHER),\n"
            "                     relative(person(\"Анна\"), Relationship.MOTHER),\n"
            "                     relative(person(\"Марфа\"), Relationship.WIFE)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(all("DRL001" in e for e in errors), errors)
        # Names the dropped relationship and the one that survives.
        self.assertIn("MOTHER", errors[0])
        self.assertIn("WIFE", errors[1])
        self.assertTrue(all("(FATHER)" in e for e in errors), errors)

    def test_single_relative_is_clean(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, None, deceased=person("Иван"), age=40,\n'
            "          relatives=[relative(person(\"Пётр\"), Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_no_relatives_is_clean(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, None, deceased=person("Иван"), age=40)',
        )
        self.assertEqual(self._check(src), [])

    def test_anchors_on_the_dropped_entry_not_the_record(self):
        """Pointing at the record (or at relatives[0], which is emitted fine)
        would send the reader to the wrong line."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, None, deceased=person("Иван"), age=2,\n'
            "          relatives=[relative(person(\"Пётр\"), Relationship.FATHER),\n"
            "                     relative(person(\"Анна\"), Relationship.MOTHER)])",
        )
        issues = self._structured(src)
        self.assertEqual(len(issues), 1, issues)
        # Line 3 of the wrapper: death_records( / death( / relatives=[... FATHER
        # / ... MOTHER  → the MOTHER line.
        self.assertEqual(issues[0]["line"], 4)

    def test_reported_as_error_not_advisory(self):
        """Silent data loss is not a style nit — it must show red."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, None, deceased=person("Иван"), age=2,\n'
            "          relatives=[relative(person(\"Пётр\"), Relationship.FATHER),\n"
            "                     relative(person(\"Анна\"), Relationship.MOTHER)])",
        )
        issues = self._structured(src)
        self.assertEqual([i["level"] for i in issues], ["error"])

    def test_falls_back_to_a_positional_label(self):
        """A relationship the AST cannot resolve to `Relationship.X` still gets
        a usable message rather than crashing."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, None, deceased=person("Иван"), age=2,\n'
            "          relatives=[relative(person(\"Пётр\"), rel_a),\n"
            "                     relative(person(\"Анна\"), rel_b)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("#2", errors[0])

    def test_syntax_error_is_left_to_other_linters(self):
        self.assertEqual(self._structured("death(("), [])



class TestPositionalRelatives(TestCheckDeathsRelatives):
    def test_relatives_in_their_place_are_read(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, None, None, None, person("Иван"), 2,\n'
            "          [relative(person(\"Пётр\"), Relationship.FATHER),\n"
            "           relative(person(\"Анна\"), Relationship.MOTHER)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("MOTHER", errors[0])


if __name__ == "__main__":
    unittest.main()
