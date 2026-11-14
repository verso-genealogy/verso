"""Tests for the PAF001 advisory patronymic-form linter."""
import tempfile
import unittest
from pathlib import Path

from verso.ru.linters.checks.patronymic_form import check_file_structured


def _lint(code: str) -> list[dict[str, object]]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(code)
        p = Path(f.name)
    return check_file_structured(p)


def _has_paf001(issues: list[dict[str, object]]) -> bool:
    return any("PAF001" in str(i["message"]) for i in issues)


class TestPaf001(unittest.TestCase):
    def test_full_form_on_peasant_status_warns(self):
        issues = _lint('person("Тихон", "Игнатьевичъ", "Феоктистовъ", '
                       'status=PEASANT_MALE)')
        self.assertTrue(_has_paf001(issues))
        self.assertEqual(issues[0]["level"], "warning")  # advisory, never error

    def test_full_form_without_status_warns(self):
        # gwar WWI cards usually carry no status — still flagged (advisory).
        issues = _lint('person("Харитон", "Тимоновичъ", "Кашеваровъ", '
                       'residence="Горюхино")')
        self.assertTrue(_has_paf001(issues))

    def test_full_form_on_landlord_peasant_warns(self):
        # A peasant OF a noble landlord is still a peasant, despite the surname
        # in the status constant.
        issues = _lint('person("Иван", "Абрамовичъ", "Вертушин", '
                       'status=MANILOV_PS_PEASANT_MALE)')
        self.assertTrue(_has_paf001(issues))

    def test_full_form_on_noble_status_is_clean(self):
        issues = _lint('person("Иван", "Абрамовичъ", "Вертушин", status=LANDLORD)')
        self.assertFalse(_has_paf001(issues))

    def test_full_form_on_clergy_string_status_is_clean(self):
        issues = _lint('person("Иван", "Абрамовичъ", "Вертушин", status="священник")')
        self.assertFalse(_has_paf001(issues))

    def test_short_form_never_warns(self):
        issues = _lint('person("Иван", "Абрамовъ", "Вертушин", status=PEASANT_MALE)')
        self.assertFalse(_has_paf001(issues))

    def test_placeholder_patronymic_clean(self):
        issues = _lint('person("Иван", "?", "Вертушин", status=PEASANT_MALE)')
        self.assertFalse(_has_paf001(issues))

    def test_soviet_civil_registry_record_is_exempt(self):
        # A ЗАГС book of 1925 writes every name with the full form: the
        # полуотчество rule died with the estates (decree of 24.11.1917).
        issues = _lint('birth_records("ГАПО", "5434", "7", "75", "Обломовка", "", 1925,\n'
                       '    birth(4, Gender.FEMALE, 17,\n'
                       '          father=person("Нил", "Тимонович", "Кочевряжкин")))')
        self.assertFalse(_has_paf001(issues))

    def test_census_before_the_decree_still_warns(self):
        # census_records carries the year one slot earlier (no church); a 1917
        # card is still of the estate era.
        issues = _lint('census_records("ГАПО", "302", "3", "8274", "Обломовка", 1917,\n'
                       '    household("19", member(1, person("Пахом", "Лукич", "Кочевряжкин"),'
                       ' None)))')
        self.assertTrue(_has_paf001(issues))

    def test_metric_book_before_the_decree_still_warns(self):
        issues = _lint('birth_records("ГАРО", "627", "279", "1", "Маниловка", "", 1916,\n'
                       '    birth(1, Gender.MALE, 3,\n'
                       '          father=person("Иван", "Абрамовичъ", "Вертушин")))')
        self.assertTrue(_has_paf001(issues))


if __name__ == "__main__":
    unittest.main()
