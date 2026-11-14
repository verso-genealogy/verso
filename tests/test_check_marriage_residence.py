import inspect
import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.marriage_residence as check_marriage_residence
from verso.ru.dsl.records import marriages


def _marriages(body: str) -> str:
    return (
        'marriage_records("a", "f", "i", "c", "Горюхино", "Церковь", 1840,\n'
        f"{body},\n"
        '    defaults=RecordDefaults(residence="Горюхино"))\n'
    )


class TestCheckMarriageResidence(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_marriage_residence.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def test_party_and_parent_in_different_villages_flagged(self):
        """The shape: bride in Ротозеево, her father elsewhere."""
        src = _marriages(
            '    marriage(9, 21, groom=person("Мартын", "Сидоров"),\n'
            '             bride=person("Мелания", "Иванова", residence="Ротозеево"),\n'
            '             relatives=[relative(person("Поликарп", "Фомин", '
            'residence="Горюхино"), Relationship.FATHER, "невеста")])',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("MRA001", errors[0])
        self.assertIn("Ротозеево", errors[0])
        self.assertIn("Горюхино", errors[0])

    def test_matching_villages_ok(self):
        src = _marriages(
            '    marriage(11, 22, groom=person("Макар", residence="Ухабовка"),\n'
            '             bride=person("Агафья", residence="Ухабовка"),\n'
            '             relatives=[relative(person("Лука", '
            'residence="Ухабовка"), Relationship.FATHER, "жених")])',
        )
        self.assertEqual(self._check(src), [])

    def test_implicit_party_never_compared(self):
        """The clergy case: a пономарь groom (implicit residence) whose father
        is a former deacon of Захолустье — legitimately two parishes. No
        inheritance exists in marriages, so an implicit side is never compared."""
        src = _marriages(
            '    marriage(14, 23, groom=person("Фёдор", "Никитин", status=SEXTON),\n'
            '             bride=person("Надежда", "Петрова"),\n'
            '             relatives=[relative(person("Никита", "Яковлев", '
            'status=DEACON, residence="Захолустье"), Relationship.FATHER, "жених")])',
        )
        self.assertEqual(self._check(src), [])

    def test_implicit_parent_never_compared(self):
        src = _marriages(
            '    marriage(9, 21, groom=person("Мартын"),\n'
            '             bride=person("Мелания", residence="Ротозеево"),\n'
            '             relatives=[relative(person("Поликарп", "Фомин"), '
            'Relationship.FATHER, "невеста")])',
        )
        self.assertEqual(self._check(src), [])

    def test_ref_pairs_the_right_party(self):
        """The bride's father is compared to the BRIDE — the groom being from
        another village is what a marriage is."""
        src = _marriages(
            '    marriage(9, 21, groom=person("Мартын", residence="Горюхино"),\n'
            '             bride=person("Мелания", residence="Ротозеево"),\n'
            '             relatives=[relative(person("Поликарп", '
            'residence="Ротозеево"), Relationship.FATHER, "невеста")])',
        )
        self.assertEqual(self._check(src), [])

    def test_non_parent_relatives_skipped(self):
        src = _marriages(
            '    marriage(9, 21, groom=person("Мартын", residence="Горюхино"),\n'
            '             bride=person("Мелания"),\n'
            '             relatives=[relative(person("Анна", '
            'residence="Захолустье"), Relationship.WIFE, "восприемника №6")])',
        )
        self.assertEqual(self._check(src), [])

    def test_syntax_error_is_left_to_single_line_calls(self):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write("marriage(1,\n")
            f.close()
            issues = check_marriage_residence.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()
        self.assertEqual(issues, [])

    def test_structured_issues_are_errors(self):
        """MRA001 is a contradiction, not a redundancy — red in the IDE."""
        src = _marriages(
            '    marriage(9, 21, groom=person("Мартын"),\n'
            '             bride=person("Мелания", residence="Ротозеево"),\n'
            '             relatives=[relative(person("Поликарп", '
            'residence="Горюхино"), Relationship.FATHER, "невеста")])',
        )
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            issues = check_marriage_residence.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()
        self.assertEqual([i["level"] for i in issues], ["error"])



def test_the_positions_read_are_the_factorys():
    names = list(inspect.signature(marriages.marriage).parameters)
    assert (names.index("groom"), names.index("bride"), names.index("relatives")) == (
        check_marriage_residence.GROOM_AT, check_marriage_residence.BRIDE_AT, check_marriage_residence.RELATIVES_AT)


if __name__ == "__main__":
    unittest.main()
