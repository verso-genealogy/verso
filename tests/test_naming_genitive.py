import unittest

from verso.ru.domain.factories import person
from verso.ru.gender import Gender
from verso.ru.naming.genitive import (
    genitive_given_name, genitive_patronymic, genitive_person_name)


class TestGenitiveGivenName(unittest.TestCase):
    def test_resolves_from_names_table(self):
        self.assertEqual(genitive_given_name("Василий"), "Василия")
        self.assertEqual(genitive_given_name("Марья"), "Марьи")
        self.assertEqual(genitive_given_name("Авдотья"), "Авдотьи")

    def test_prefers_the_row_whose_stem_matches_the_input_spelling(self):
        """names.csv holds several genitives per name and row order does not
        favour the input's own spelling — «Кузьма» leads with «Кузмы», «Семён»
        with «Семена», «Андриан» with its church form's «Адриана». Rendering a
        stem the profile does not show reads as a typo."""
        self.assertEqual(genitive_given_name("Кузьма"), "Кузьмы")
        self.assertEqual(genitive_given_name("Семён"), "Семёна")
        self.assertEqual(genitive_given_name("Андриан"), "Андриана")

    def test_grafts_the_ending_when_only_a_yo_folded_row_matches(self):
        """«Парфён» has no stem-exact row — «Парфена» (ё folded to е) and
        «Парфения» (a different name). The ending comes from the table, the
        stem from the input, so the ё survives."""
        self.assertEqual(genitive_given_name("Парфён"), "Парфёна")

    def test_fleeting_vowel_names_take_the_table_verbatim(self):
        """Here the genitive legitimately does not contain the nominative stem
        and no rule could derive it — only the table knows."""
        self.assertEqual(genitive_given_name("Лев"), "Льва")
        self.assertEqual(genitive_given_name("Павел"), "Павла")

    def test_declines_names_absent_from_the_table(self):
        """The Mordva / pre-Christian names of the early revisions are not in
        names.csv; standard declension covers them."""
        self.assertEqual(genitive_given_name("Бурмяй"), "Бурмяя")
        self.assertEqual(genitive_given_name("Адмак"), "Адмака")
        self.assertEqual(genitive_given_name("Пичкинза"), "Пичкинзы")

    def test_hushing_stem_takes_i_not_y(self):
        self.assertEqual(genitive_given_name("Вечкенза"), "Вечкензы")
        self.assertEqual(genitive_given_name("Кичка"), "Кички")

    def test_soft_sign_ending_declines_by_gender(self):
        self.assertEqual(genitive_given_name("Кудь", Gender.MALE), "Кудя")
        self.assertEqual(genitive_given_name("Кудь", Gender.FEMALE), "Куди")

    def test_empty_and_indeclinable_pass_through(self):
        self.assertEqual(genitive_given_name(None), "")
        self.assertEqual(genitive_given_name(""), "")
        self.assertEqual(genitive_given_name("Мокшо"), "Мокшо")


class TestGenitivePatronymic(unittest.TestCase):
    def test_modern_masculine(self):
        self.assertEqual(genitive_patronymic("Семёнович"), "Семёновича")
        self.assertEqual(genitive_patronymic("Ильич"), "Ильича")
        self.assertEqual(genitive_patronymic("Кузьмич"), "Кузьмича")

    def test_modern_feminine(self):
        self.assertEqual(genitive_patronymic("Семёновна"), "Семёновны")
        self.assertEqual(genitive_patronymic("Ильинична"), "Ильиничны")

    def test_old_possessive_forms(self):
        self.assertEqual(genitive_patronymic("Фомин"), "Фомина")
        self.assertEqual(genitive_patronymic("Семенов"), "Семенова")
        self.assertEqual(genitive_patronymic("Фомина"), "Фоминой")
        self.assertEqual(genitive_patronymic("Семенова"), "Семеновой")

    def test_unclassifiable_passes_through_verbatim(self):
        """A name that cannot be declined must never block generation."""
        self.assertEqual(genitive_patronymic("?"), "?")
        self.assertEqual(genitive_patronymic(None), "")


class TestGenitivePersonName(unittest.TestCase):
    def test_given_name_plus_modern_patronymic(self):
        self.assertEqual(
            genitive_person_name(person("Василий", "Семенов")),
            "Василия Семеновича",
        )

    def test_surname_is_not_included(self):
        """The reference points at somebody listed in the same household
        table, where given name + patronymic identifies them."""
        self.assertEqual(
            genitive_person_name(person("Кузьма", "Савельев", "Индюшев")),
            "Космы Савельевича",
        )

    def test_person_without_patronymic(self):
        self.assertEqual(genitive_person_name(person("Варвара")), "Варвары")

    def test_none_person(self):
        self.assertEqual(genitive_person_name(None), "")


if __name__ == "__main__":
    unittest.main()
