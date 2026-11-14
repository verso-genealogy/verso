"""Tests for the NGA001/NGA002 advisory name-gender-agreement linter."""
import tempfile
import unittest
from pathlib import Path

from verso.ru.linters.checks.name_gender_agreement import check_file_structured


def _lint(code: str) -> list[dict[str, object]]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(code)
        p = Path(f.name)
    return check_file_structured(p)


def _codes(code: str) -> list[str]:
    return [str(i["message"])[1:7] for i in _lint(code)]


class TestSurname(unittest.TestCase):
    def test_a_correction_that_stopped_short_of_the_surname(self):
        """A voter-list entry whose given name was corrected from female to male,
        the surname left feminine."""
        issues = _lint('listed_person(7, person("Степанъ", "Васильевъ", "Ежевикина"))')
        self.assertEqual(["NGA001"], [str(i["message"])[1:7] for i in issues])
        self.assertEqual("warning", issues[0]["level"])  # advisory, never an error

    def test_a_womans_name_with_a_mans_surname(self):
        self.assertEqual(["NGA001"],
                         _codes('person("Ксения", "Антонова", last_name_orig="Сопунов")'))

    def test_agreeing_forms_pass_in_either_orthography(self):
        for code in ('person("Степанъ", "Васильевъ", "Ежевикинъ")',
                     'person("Степанида", "Васильева", "Ежевикина")',
                     'person("Анна", "Никитина", last_name_orig="Чичикова")',
                     'person("Ѳеодоръ", "Ивановъ", last_name_orig="Хлопушкинъ")'):
            with self.subTest(code):
                self.assertEqual([], _codes(code))

    def test_a_surname_with_no_gendered_ending_says_nothing(self):
        self.assertEqual([], _codes('person("Мария", "Петрова", "Шевчукъ")'))

    def test_the_modern_surname_is_read_when_no_original_is_given(self):
        self.assertEqual(["NGA001"],
                         _codes('person("Иван", last_name_modern_orth="Сидорова")'))


class TestToken(unittest.TestCase):
    def test_the_token_is_the_word_in_the_other_sex(self):
        """What a reader points at — the IDEs' highlight: the surname or the patronymic that
        disagrees, whatever the message's language or quotes."""
        (surname,) = _lint('person("Степанъ", "Васильевъ", "Ежевикина")')
        (patronymic,) = _lint('person("Ѳеона", "Михайлова", gender=Gender.MALE)')
        self.assertEqual(["Ежевикина", "Михайлова"],
                         [getattr(i["message"], "token", None) for i in (surname, patronymic)])


class TestPatronymic(unittest.TestCase):
    def test_a_mans_name_with_a_womans_patronymic(self):
        self.assertEqual(["NGA002"], _codes('person("Степанъ", "Васильева")'))
        self.assertEqual(["NGA002"], _codes('person("Иван", "Петровна")'))

    def test_a_womans_name_with_a_mans_patronymic(self):
        self.assertEqual(["NGA002"], _codes('person("Анна", "Никитинъ")'))
        self.assertEqual(["NGA002"], _codes('person("Анна", "Никитичъ")'))

    def test_full_feminine_forms_are_feminine(self):
        self.assertEqual([], _codes('person("Анна", "Никитична")'))
        self.assertEqual([], _codes('person("Анна", "Ивановна")'))


class TestWhoIsChecked(unittest.TestCase):
    def test_the_explicit_gender_wins_over_the_name(self):
        self.assertEqual(["NGA001"], _codes(
            'person("Саша", last_name_orig="Петрова", gender=Gender.MALE)'))

    def test_an_unknown_or_doubtful_name_is_skipped(self):
        self.assertEqual([], _codes('person("Па?", "Никитин", last_name_orig="Егорова")'))
        self.assertEqual([], _codes('person("Зызыва", "Петрова", "Иванов")'))

    def test_a_doubtful_surname_is_skipped(self):
        self.assertEqual([], _codes('person("Иван", "Петров", "Сидорова?")'))


if __name__ == "__main__":
    unittest.main()
