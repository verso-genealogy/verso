import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.birth_redundancy as check_birth_redundancy


def _birth(body: str) -> str:
    """Wrap a birth(...) snippet in the minimal imports the AST checker
    needs to parse (it never executes the DSL, so names aren't validated)."""
    return (
        "from genealogy import person, Gender\n"
        "from births import birth\n"
        f"{body}\n"
    )


class TestCheckBirthRedundancy(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_birth_redundancy.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _structured(self, src: str) -> list[dict[str, object]]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_birth_redundancy.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()

    # ---- positive (flag) cases -------------------------------------------

    def test_mother_surname_redundant_flagged(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Мария", last_name_orig="Пошлепкина", last_name_in_book=False))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("redundant", errors[0])
        self.assertIn("last_name_orig", errors[0])

    def test_son_surname_redundant_flagged(self):
        # Son inherits father's surname UN-feminized; pre-rev ъ modernizes away.
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван", last_name_orig="Сундукинъ", last_name_in_book=False),\n'
            '          father=person("Петр", last_name_orig="Сундукинъ"),\n'
            '          mother=person("Мария"))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("last_name_orig", errors[0])

    def test_daughter_surname_redundant_flagged(self):
        # Daughter: derived = feminize(father) when mother has no surname.
        src = _birth(
            'b = birth(1, Gender.FEMALE, 1, 2,\n'
            '          child=person("Мария", last_name_orig="Пошлепкина", last_name_in_book=False),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Анна"))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("last_name_orig", errors[0])

    def test_daughter_matches_mother_surname_flagged(self):
        # Daughter derived from mother's surname (not father's).
        src = _birth(
            'b = birth(1, Gender.FEMALE, 1, 2,\n'
            '          child=person("Мария", last_name_orig="Наковалкина", last_name_in_book=False),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Анна", last_name_modern_orth="Наковалкина"))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("last_name_orig", errors[0])

    def test_last_name_modern_orth_redundant_flagged(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Мария", last_name_modern_orth="Пошлепкина", last_name_in_book=False))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("last_name_modern_orth", errors[0])

    def test_lone_last_name_in_book_false_flagged(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Мария", last_name_in_book=False))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("last_name_in_book", errors[0])

    # ---- negative (no-flag) cases ----------------------------------------

    def test_no_flag_when_in_book_default(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Мария", last_name_orig="Пошлепкина"))'
        )
        self.assertEqual(self._check(src), [])

    def test_no_flag_when_surname_differs(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Мария", last_name_orig="Иванова", last_name_in_book=False))'
        )
        self.assertEqual(self._check(src), [])

    def test_no_flag_when_father_has_no_surname(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр"),\n'
            '          mother=person("Мария", last_name_orig="Пошлепкина", last_name_in_book=False))'
        )
        self.assertEqual(self._check(src), [])

    def test_no_flag_son_with_feminized_surname(self):
        # A son surname must equal F (un-feminized); feminize(F) must NOT match.
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван", last_name_orig="Пошлепкина", last_name_in_book=False),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Мария"))'
        )
        self.assertEqual(self._check(src), [])

    def test_no_flag_outside_birth(self):
        src = (
            "from genealogy import person\n"
            "from marriages import marriage\n"
            'm = marriage(1, 10,\n'
            '             groom=person("Иван", last_name_orig="Пошлепкин"),\n'
            '             bride=person("Мария", last_name_orig="Пошлепкина", last_name_in_book=False))\n'
        )
        self.assertEqual(self._check(src), [])

    # ---- residence redundancy --------------------------------------------

    def test_mother_residence_redundant_flagged(self):
        # Mother residence == father residence → Birth.__init__ would derive it.
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", residence="Собакевичево"),\n'
            '          mother=person("Мария", residence="Собакевичево"))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('redundant residence="Собакевичево"', errors[0])

    def test_child_residence_redundant_matches_father_flagged(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван", residence="Собакевичево"),\n'
            '          father=person("Петр", residence="Собакевичево"),\n'
            '          mother=person("Мария"))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('redundant residence="Собакевичево"', errors[0])

    def test_child_residence_redundant_matches_mother_flagged(self):
        # Father has no residence → child derives from the mother's.
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван", residence="Горюхино"),\n'
            '          father=person("Петр"),\n'
            '          mother=person("Мария", residence="Горюхино"))'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('redundant residence="Горюхино"', errors[0])

    def test_no_flag_when_residence_differs(self):
        # Bride from another village: mother residence != father residence.
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", residence="Собакевичево"),\n'
            '          mother=person("Мария", residence="Заманиловка"))'
        )
        self.assertEqual(self._check(src), [])

    def test_no_flag_when_no_parent_residence(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван", residence="Собакевичево"),\n'
            '          father=person("Петр"),\n'
            '          mother=person("Мария"))'
        )
        self.assertEqual(self._check(src), [])

    def test_structured_emits_remove_kwarg_fix_for_residence(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", residence="Собакевичево"),\n'
            '          mother=person("Мария", residence="Собакевичево"))'
        )
        issues = self._structured(src)
        self.assertEqual(len(issues), 1, issues)
        # `col` is the CHARACTER column of `residence=` — the line is Cyrillic,
        # so the AST's byte offset would overshoot.
        self.assertEqual(
            issues[0]["fix"],
            {"type": "remove_kwarg", "kwarg": "residence",
             "col": src.splitlines()[5].index("residence=")},
        )

    # ---- structured fix --------------------------------------------------

    def test_structured_emits_remove_kwarg_fix(self):
        src = _birth(
            'b = birth(1, Gender.MALE, 1, 2,\n'
            '          child=person("Иван"),\n'
            '          father=person("Петр", last_name_orig="Пошлепкин"),\n'
            '          mother=person("Мария", last_name_orig="Пошлепкина", last_name_in_book=False))'
        )
        issues = self._structured(src)
        self.assertEqual(len(issues), 1, issues)
        self.assertEqual(
            issues[0]["fix"],
            {"type": "remove_kwarg", "kwarg": "last_name_orig",
             "col": src.splitlines()[5].index("last_name_orig=")},
        )


if __name__ == "__main__":
    unittest.main()
