from __future__ import annotations

import unittest

from verso.ru.gender import Gender
from verso.ru.naming import canonicalize_name, father_name_for_patronymic, matching_base, names_registry
from verso.ru.naming.layer_files import base as names_base
from verso.ru.naming.lexicon import Layer, Lexicon, NameEntry

M, F = Gender.MALE, Gender.FEMALE


class FoldsVariants(unittest.TestCase):
    """The spellings the sweep actually has to reconcile across years."""

    def test_old_church_forms(self):
        for written, base in (("Алексей", "Алексий"), ("Иван", "Иоанн"),
                              ("Федор", "Феодор")):
            self.assertEqual(base, matching_base(written, M), written)

    def test_female_forms(self):
        self.assertEqual("Пелагия", matching_base("Пелагея", F))
        self.assertEqual("Параскева", matching_base("Прасковья", F))

    def test_a_base_form_folds_to_itself(self):
        for name in ("Алексий", "Иоанн", "Феодор", "Георгий"):
            self.assertEqual(name, matching_base(name, M))

    def test_a_name_absent_from_the_table_is_returned_as_written(self):
        self.assertEqual("Небывалий", matching_base("Небывалий", M))

    def test_empty_and_uncertain(self):
        self.assertEqual("", matching_base(None))
        self.assertEqual("", matching_base(""))
        self.assertEqual("Иван?", matching_base("Иван?"))


class DiffersFromCanonicalizeName(unittest.TestCase):
    """Where the two disagree is the whole reason this function exists."""

    def test_egor_folds_here_but_not_in_canonicalize_name(self):
        # The two functions answer differently only where an entry writes a canonical form of its own. The base writes
        # none: it folds Егор onto Георгий in both (res_names of the base alone are built from Георгий). A corpus that
        # keeps «Егор» as the form its res_names are built from — a documentary form — says so in a layer: Егор with
        # the base Георгий and the canonical form Егор. canonicalize_name keeps it, matching_base folds the man with
        # his household written both ways.
        layer = Layer("corpus", {(M, "Егор"): NameEntry(M, "Егор", ("Георгий",), canonical="Егор")}, {}, {})
        with names_registry.answering(Lexicon.of([names_base().load(), layer])):
            self.assertEqual("Егор", canonicalize_name("Егор"))
            self.assertEqual("Георгий", matching_base("Егор", M))
            self.assertEqual("Георгий", matching_base("Георгий", M))


class GenderGuards(unittest.TestCase):
    """«Лука» is М on its own row and Ж mapping to Гликерия."""

    def test_gender_keeps_luka_male(self):
        self.assertEqual("Лука", matching_base("Лука", M))

    def test_without_gender_an_ambiguous_name_is_left_alone(self):
        self.assertEqual("Лука", matching_base("Лука"))

    def test_an_unambiguous_name_still_folds_without_gender(self):
        self.assertEqual("Иоанн", matching_base("Иван"))
        self.assertEqual("Георгий", matching_base("Егор"))


class UsedByThePersonKey(unittest.TestCase):
    def test_person_key_folds_the_name_and_keeps_the_written_form(self):
        from verso.ru.consolidation.death_age import person_key
        from verso.ru.domain import person

        egor = person_key(person("Егор", "Максимов", last_name_orig="Бекешев"))
        georgiy = person_key(person("Георгий", "Максимов", last_name_orig="Бекешев"))
        assert egor is not None and georgiy is not None
        self.assertTrue(egor.matches(georgiy))
        self.assertEqual(egor, georgiy)              # equal as a dict key
        self.assertEqual("егор", egor.written)       # but reports say «Егор»
        self.assertEqual("георгий", georgiy.written)

    def test_the_written_form_is_out_of_equality(self):
        from verso.ru.consolidation.death_age import PersonKey
        a = PersonKey("георгий", "максимович", "кекев", written="егор")
        b = PersonKey("георгий", "максимович", "кекев", written="георгий")
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual({a, b}, {a})

    def test_display_falls_back_to_the_folded_name(self):
        from verso.ru.consolidation.death_age import PersonKey
        self.assertEqual("георгий", PersonKey("георгий", "", "").display)


class FatherNameForPatronymic(unittest.TestCase):
    """The father a patronymic names, read off the lexicon — its comparison twin."""

    def test_short_and_full_forms_name_one_father(self):
        self.assertEqual(father_name_for_patronymic("Иванов"), "Иоанн")
        self.assertEqual(father_name_for_patronymic("Ивановна"), "Иоанн")
        self.assertEqual(father_name_for_patronymic("Иванович"), "Иоанн")

    def test_spelling_drift_of_one_patronymic_names_one_father(self):
        self.assertEqual(father_name_for_patronymic("Алексеевна"),
                         father_name_for_patronymic("Алексиевна"))
        self.assertEqual(father_name_for_patronymic("Матвеевна"),
                         father_name_for_patronymic("Матфеевна"))

    def test_a_variant_father_answers_with_its_base(self):
        self.assertEqual(father_name_for_patronymic("Матвеевич"), "Матфей")

    def test_unknown_or_illegible_is_none(self):
        self.assertIsNone(father_name_for_patronymic("Нерапиевна"))
        self.assertIsNone(father_name_for_patronymic("Ив?новна"))
        self.assertIsNone(father_name_for_patronymic(""))


if __name__ == "__main__":
    unittest.main()
