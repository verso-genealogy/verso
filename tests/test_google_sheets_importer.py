#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import verso.ru.importers.google_sheets as gsi


def _make_row(**kwargs) -> list[str]:
    """Build a fake spreadsheet row (list of empty strings) with selected columns filled in.
    Keyword arg names are column-constant names, e.g. D_DEC_NAME="Иван".
    """
    row = [""] * 200
    for const_name, val in kwargs.items():
        idx = getattr(gsi, const_name)
        if idx is not None:
            row[idx] = val
    return row


class TestHelpers(unittest.TestCase):

    def test_get_normal_access(self):
        row = ["a", "b", "c"]
        self.assertEqual(gsi._get(row, 1), "b")

    def test_get_strips_whitespace(self):
        row = ["a", "  hello  "]
        self.assertEqual(gsi._get(row, 1), "hello")

    def test_get_out_of_bounds_returns_default(self):
        row = ["a"]
        self.assertEqual(gsi._get(row, 99), "")
        self.assertEqual(gsi._get(row, 99, default="x"), "x")

    def test_get_none_index_returns_default(self):
        row = ["a", "b"]
        self.assertEqual(gsi._get(row, None), "")

    def test_int_or_none_valid(self):
        self.assertEqual(gsi._int_or_none("5"), 5)
        self.assertEqual(gsi._int_or_none("42"), 42)

    def test_int_or_none_zero_returns_none(self):
        self.assertIsNone(gsi._int_or_none("0"))

    def test_int_or_none_non_numeric_returns_none(self):
        self.assertIsNone(gsi._int_or_none("abc"))
        self.assertIsNone(gsi._int_or_none(""))
        self.assertIsNone(gsi._int_or_none(None))

    def test_parse_age_integer(self):
        self.assertEqual(gsi._parse_age("50"), 50)

    def test_parse_age_months(self):
        self.assertEqual(gsi._parse_age("6 м"), "6 м")

    def test_parse_age_weeks(self):
        self.assertEqual(gsi._parse_age("2 н"), "2 н")

    def test_parse_age_days(self):
        self.assertEqual(gsi._parse_age("3 д"), "3 д")

    def test_parse_age_zero(self):
        self.assertIsNone(gsi._parse_age("0"))

    def test_parse_age_empty(self):
        self.assertIsNone(gsi._parse_age(""))

    def test_parse_age_invalid(self):
        self.assertIsNone(gsi._parse_age("abc"))

    def test_q_basic(self):
        self.assertEqual(gsi._q("hello"), '"hello"')

    def test_q_escapes_double_quotes(self):
        self.assertEqual(gsi._q('say "hi"'), '"say \\"hi\\""')

    def test_q_escapes_backslashes(self):
        self.assertEqual(gsi._q('a\\b'), '"a\\\\b"')

    def test_q_replaces_newlines_with_space(self):
        self.assertEqual(gsi._q("line1\nline2"), '"line1 line2"')

    def test_varname_basic(self):
        self.assertEqual(gsi._varname("Заманиловка", "deaths", 1784), "zamanilovka_deaths_1784")

    def test_varname_strips_selo_prefix(self):
        self.assertEqual(gsi._varname("село Горюхино", "births", 1796), "goryukhino_births_1796")

    def test_varname_strips_derevnya_prefix(self):
        result = gsi._varname("деревня Собакевичево", "marriages", 1810)
        self.assertIn("sobakevichevo_marriages_1810", result)

    def test_page_sort_key_numeric_order(self):
        self.assertLess(gsi._page_sort_key("7"), gsi._page_sort_key("8"))
        self.assertLess(gsi._page_sort_key("7"), gsi._page_sort_key("7об"))
        self.assertLess(gsi._page_sort_key("7об"), gsi._page_sort_key("8"))

    def test_page_sort_key_ob_suffix(self):
        key_plain = gsi._page_sort_key("7")
        key_ob = gsi._page_sort_key("7об")
        self.assertEqual(key_plain, (7, 0))
        self.assertEqual(key_ob, (7, 1))


class TestPersonCall(unittest.TestCase):

    def test_name_only(self):
        result = gsi._person_call("Иван")
        self.assertEqual(result, 'person("Иван")')

    def test_name_and_patr(self):
        result = gsi._person_call("Иван", "Иванов")
        self.assertEqual(result, 'person("Иван", "Иванов")')

    def test_name_patr_and_explicit_last_name(self):
        result = gsi._person_call("Иван", "Иванов", last_name="Чичиков")
        self.assertIn('person("Иван", "Иванов"', result)
        self.assertIn('last_name_orig="Чичиков"', result)

    def test_status_not_in_skip_statuses_included(self):
        result = gsi._person_call("Иван", status="купец")
        self.assertIn('status="купец"', result)

    def test_status_in_skip_statuses_omitted(self):
        skip = frozenset(["купец"])
        result = gsi._person_call("Иван", status="купец", skip_statuses=skip)
        self.assertNotIn("status=", result)

    def test_imena_placeholder_becomes_question_mark(self):
        result = gsi._person_call("Имена")
        self.assertEqual(result, 'person("?")')

    def test_title_word_as_name_takes_real_name_from_patr(self):
        result = gsi._person_call("священник", "Иоанн")
        self.assertIn('person("Иоанн"', result)
        self.assertIn('status="священник"', result)

    def test_patr_that_looks_like_surname_becomes_last_name_orig(self):
        # "Фиктивов" cannot be canonicalized → treated as surname
        result = gsi._person_call("Иван", "Фиктивов")
        self.assertIn('last_name_orig="Фиктивов"', result)
        # It should NOT appear as a positional (quoted) arg before last_name_orig
        before_kwarg = result.split("last_name_orig=")[0]
        self.assertNotIn('"Фиктивов"', before_kwarg)

    def test_empty_name_returns_none(self):
        result = gsi._person_call("")
        self.assertIsNone(result)

    def test_comment_included(self):
        result = gsi._person_call("Иван", comment="доп. запись")
        self.assertIn('comment="доп. запись"', result)

    def test_residence_emitted_when_set(self):
        result = gsi._person_call("Иван", residence="село Другое")
        self.assertIn('residence="село Другое"', result)

    def test_residence_none_omitted(self):
        result = gsi._person_call("Иван", residence=None)
        self.assertNotIn("residence=", result)

    def test_residence_emitted_before_status(self):
        result = gsi._person_call("Иван", residence="село Другое", status="крестьянин")
        self.assertLess(result.index("residence="), result.index("status="))

    def test_residence_emitted_after_last_name(self):
        result = gsi._person_call("Иван", last_name="Чичиков", residence="село Другое")
        self.assertLess(result.index("last_name_orig="), result.index("residence="))


class TestPersonNamesSet(unittest.TestCase):

    def test_name_and_full_form_both_in_set(self):
        result = gsi._person_names_set(("Антон", "Иванов"))
        self.assertIn("Антон", result)
        self.assertIn("Антон Иванов", result)

    def test_placeholder_excluded(self):
        result = gsi._person_names_set(("?", ""))
        self.assertEqual(result, set())

    def test_empty_name_excluded(self):
        result = gsi._person_names_set(("", "Иванов"))
        self.assertEqual(result, set())

    def test_name_without_patr(self):
        result = gsi._person_names_set(("Мария", ""))
        self.assertIn("Мария", result)
        self.assertNotIn("Мария ", result)

    def test_multiple_pairs_unioned(self):
        result = gsi._person_names_set(("Иван", "Иванов"), ("Петр", "Петров"))
        self.assertIn("Иван", result)
        self.assertIn("Иван Иванов", result)
        self.assertIn("Петр", result)
        self.assertIn("Петр Петров", result)


class TestParseOrigNames(unittest.TestCase):

    def test_empty_string_returns_empty_dict(self):
        result = gsi._parse_orig_names("", False, False, False, False, False)
        self.assertEqual(result, {})

    def test_none_string_returns_empty_dict(self):
        result = gsi._parse_orig_names(None, True, True, False, False, False)
        self.assertEqual(result, {})

    def test_standard_child_father_mother(self):
        orig = "Имена в МК: Иван; Петр Иванов; Мария Петрова"
        result = gsi._parse_orig_names(orig, True, True, True, False, False)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Петр", "Иванов", ""))
        self.assertEqual(result["mother"], ("Мария", "Петрова", ""))

    def test_godparents_parsed(self):
        orig = "Имена в МК: Алексей; Федор Иванов; Анна Петрова; Григорий Сидоров; Варвара Миронова"
        result = gsi._parse_orig_names(orig, True, True, True, True, True)
        self.assertEqual(result["gp1"], ("Григорий", "Сидоров", ""))
        self.assertEqual(result["gp2"], ("Варвара", "Миронова", ""))

    def test_part_count_mismatch_returns_empty_dict(self):
        # 2 parts but 3 roles expected → ambiguous mapping → return {}
        # The scenario: child (Леонтий) had no orig entry,
        # but father (Прохор Макаров) and gp1 (Ларион Савельев) did.
        # The old code wrongly assigned "Прохор Макаров" → child.
        orig = "Имена в МК: Прохор Макаров; Ларион Савельев"
        result = gsi._parse_orig_names(orig, True, True, False, True, False)
        self.assertEqual(result, {})

    def test_more_parts_than_roles_ignores_trailing_legacy(self):
        # 3 parts but only 2 roles expected → extra parts ignored (e.g. priest name)
        orig = "Имена в МК: Иван; Петр Иванов; лишнее"
        result = gsi._parse_orig_names(orig, True, True, False, False, False)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Петр", "Иванов", ""))

    def test_exact_match_two_roles(self):
        # 2 parts and exactly 2 roles → positional mapping should work
        orig = "Имена в МК: Иван; Петр Иванов"
        result = gsi._parse_orig_names(orig, True, True, False, False, False)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Петр", "Иванов", ""))

    def test_colon_only_prefix_no_names_returns_empty_dict(self):
        # "Имена в МК:" without trailing space — must not be parsed as a name
        result = gsi._parse_orig_names("Имена в МК:", True, True, False, False, False)
        self.assertEqual(result, {})

    def test_three_part_name_extracts_surname(self):
        orig = "Имена в МК: Иван; Герасим Тихонов Мижуев"
        result = gsi._parse_orig_names(orig, True, True, False, False, False)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Герасим", "Тихонов", "Мижуев"))

    def test_three_part_name_with_multiple_roles(self):
        orig = "Имена в МК: Иван; Герасим Тихонов Мижуев; Варвара Миронова"
        result = gsi._parse_orig_names(orig, True, True, True, False, False)
        self.assertEqual(result["father"], ("Герасим", "Тихонов", "Мижуев"))
        self.assertEqual(result["mother"], ("Варвара", "Миронова", ""))

    def test_extra_trailing_parts_ignored(self):
        orig = "Имена в МК: Иван; Герасим Тихонов Мижуев; Варвара Миронова; Никита Романов Мижуев; Анна Кириллова; Влас Андреев"
        result = gsi._parse_orig_names(orig, True, True, True, True, True)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Герасим", "Тихонов", "Мижуев"))
        self.assertEqual(result["mother"], ("Варвара", "Миронова", ""))
        self.assertEqual(result["gp1"], ("Никита", "Романов", "Мижуев"))
        self.assertEqual(result["gp2"], ("Анна", "Кириллова", ""))

    def test_more_parts_than_roles_ignores_trailing(self):
        orig = "Имена в МК: Иван; Петр Иванов; лишнее"
        result = gsi._parse_orig_names(orig, True, True, False, False, False)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Петр", "Иванов", ""))

    def test_child_missing_from_orig_detected_by_first_part_having_patronymic(self):
        # Illegitimate birth: child has canonical name "Серафима" but no orig entry.
        # Orig starts with mother "Домна Назарова" (2 tokens = not a child name).
        orig = "Имена в МК: Домна Назарова; Роман Захаров; Аксинья Лаврентьева; Влас Андреев"
        result = gsi._parse_orig_names(orig, True, False, True, True, True)
        self.assertNotIn("child", result)  # child skipped — no orig entry
        self.assertEqual(result["mother"], ("Домна", "Назарова", ""))
        self.assertEqual(result["gp1"], ("Роман", "Захаров", ""))
        self.assertEqual(result["gp2"], ("Аксинья", "Лаврентьева", ""))

    def test_child_present_in_orig_when_single_token(self):
        # Normal case: child IS in orig (single-token "Иван"), mapping works.
        orig = "Имена в МК: Иван; Петр Иванов; Мария Петрова"
        result = gsi._parse_orig_names(orig, True, True, True, False, False)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Петр", "Иванов", ""))

    def test_child_skipped_when_all_parts_have_patronymics(self):
        # All orig parts are 2+ tokens — first one can't be a child.
        orig = "Имена в МК: Герасим Тихонов; Анна Петрова"
        result = gsi._parse_orig_names(orig, True, True, False, False, False)
        self.assertNotIn("child", result)
        self.assertEqual(result["father"], ("Герасим", "Тихонов", ""))

    def test_father_missing_from_orig_detected_by_canon_hint(self):
        # Father "Леонтий" has no orig entry. Orig starts with mother "Софья Гордеева".
        # Canon hint for father is "Леонтий" which doesn't match "Софья" → skip father.
        orig = "Имена в МК: Тихон; Софья Гордеева; Корнилий Савельев; Фекла Елисеева; Евграф Мартынов"
        result = gsi._parse_orig_names(orig, True, True, True, True, True,
                                        canon_names={"father": "Леонтий"})
        self.assertEqual(result["child"], ("Тихон", "", ""))
        self.assertNotIn("father", result)
        self.assertEqual(result["mother"], ("Софья", "Гордеева", ""))
        self.assertEqual(result["gp1"], ("Корнилий", "Савельев", ""))
        self.assertEqual(result["gp2"], ("Фекла", "Елисеева", ""))

    def test_father_variant_spelling_accepted(self):
        # Father canon="Феоктист", orig="Фоким Макаров" (different spelling of same person).
        # Both are male → gender matches → should NOT skip.
        orig = "Имена в МК: Аксинья; Фоким Макаров; Ульяна Нестерова"
        result = gsi._parse_orig_names(orig, True, True, False, True, False,
                                        canon_names={"father": "Феоктист"})
        self.assertEqual(result["child"], ("Аксинья", "", ""))
        self.assertEqual(result["father"], ("Фоким", "Макаров", ""))
        self.assertEqual(result["gp1"], ("Ульяна", "Нестерова", ""))

    def test_father_gender_mismatch_skips(self):
        # Father canon="Леонтий" (male), orig starts with "Софья" (female) → skip father.
        orig = "Имена в МК: Тихон; Софья Гордеева; Корнилий Савельев"
        result = gsi._parse_orig_names(orig, True, True, True, True, False,
                                        canon_names={"father": "Леонтий"})
        self.assertEqual(result["child"], ("Тихон", "", ""))
        self.assertNotIn("father", result)
        self.assertEqual(result["mother"], ("Софья", "Гордеева", ""))
        self.assertEqual(result["gp1"], ("Корнилий", "Савельев", ""))

    def test_canon_hint_matches_allows_mapping(self):
        # Father "Петр" matches first token of "Петр Иванов" → normal mapping.
        orig = "Имена в МК: Иван; Петр Иванов"
        result = gsi._parse_orig_names(orig, True, True, False, False, False,
                                        canon_names={"father": "Петр"})
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Петр", "Иванов", ""))

    def test_comment_text_in_orig_not_parsed_as_name(self):
        # Orig has real names + trailing comment "Населенный пункт восприемника не указан"
        orig = "Имена в МК: Иван; Петр Иванов; Населенный пункт восприемника не указан"
        result = gsi._parse_orig_names(orig, True, True, False, False, False)
        self.assertEqual(result["child"], ("Иван", "", ""))
        self.assertEqual(result["father"], ("Петр", "Иванов", ""))
        self.assertEqual(len(result), 3)  # child, father, _comments
        self.assertIn("Населенный пункт восприемника не указан", result["_comments"])

    def test_lowercase_orig_part_not_parsed_as_name(self):
        # Orig has "Отчество неразборчиво написано" — starts with uppercase but is a comment
        orig = "Имена в МК: Михаил; Иван Семенов; Отчество отца неразборчиво написано"
        result = gsi._parse_orig_names(orig, True, True, False, True, False)
        self.assertEqual(result["child"], ("Михаил", "", ""))
        self.assertEqual(result["father"], ("Иван", "Семенов", ""))
        self.assertNotIn("gp1", result)

    def test_nezakonnorozhdennaya_not_parsed_as_child_name(self):
        # "Незаконнорожденная" in orig should not become a child name
        orig = "Имена в МК: Незаконнорожденная; Мария Иванова"
        result = gsi._parse_orig_names(orig, True, False, True, False, False)
        # "Незаконнорожденная" is a single token but it's not a real name
        # The child should be skipped or the function should detect it's not a name
        self.assertNotIn("child", result)

    def test_deceased_missing_from_orig_in_death_context(self):
        # Death of unnamed child: deceased "Нил" has no orig, orig starts with mother "Ефимия Елисеева".
        # Using canon_names to detect.
        orig = "Имена в МК: Ефимия Елисеева"
        result = gsi._parse_orig_names(orig, True, False, False, False, False,
                                        canon_names={"child": "Нил"})
        # "Ефимия Елисеева" has a patronymic AND doesn't match canon "Нил" → child skipped
        self.assertNotIn("child", result)


class TestPatrDerivesFromFather(unittest.TestCase):

    def test_female_patronymic_matches_father(self):
        # "Васильевна" derives from father "Василий" for a female
        self.assertTrue(gsi._patr_derives_from_father("Васильевна", "Василий", "жен"))

    def test_male_patronymic_matches_father(self):
        # "Иванов" (short form) → canonical "Иванович" derives from "Иван" for male
        self.assertTrue(gsi._patr_derives_from_father("Иванов", "Иван", "муж"))

    def test_patronymic_does_not_match_different_father(self):
        # "Петрова" does not derive from "Иван"
        self.assertFalse(gsi._patr_derives_from_father("Петрова", "Иван", "жен"))

    def test_empty_patronymic_returns_false(self):
        self.assertFalse(gsi._patr_derives_from_father("", "Иван", "муж"))

    def test_empty_father_name_returns_false(self):
        self.assertFalse(gsi._patr_derives_from_father("Иванов", "", "муж"))


class TestExtractWitnessesFromComment(unittest.TestCase):

    def test_empty_string(self):
        witnesses, remaining = gsi._extract_witnesses_from_comment("")
        self.assertEqual(witnesses, [])
        self.assertEqual(remaining, "")

    def test_no_keyword_unchanged(self):
        comment = "просто комментарий"
        witnesses, remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(witnesses, [])
        self.assertEqual(remaining, comment)

    def test_svideteli_colon_extracts_two_witnesses(self):
        comment = "свидетели: Иван Иванов, Федор Петров"
        witnesses, remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 2)
        self.assertEqual(witnesses[0][0], "Иван")
        self.assertEqual(witnesses[0][1], "Иванов")
        self.assertIsNone(witnesses[0][2])
        self.assertEqual(witnesses[1][0], "Федор")
        self.assertEqual(witnesses[1][1], "Петров")
        self.assertEqual(remaining, "")

    def test_svidatel_inline_extracts_one_witness_and_keeps_remaining(self):
        comment = "Матвей Осипов - свидетель Осип Казмин"
        witnesses, remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 1)
        self.assertEqual(witnesses[0][0], "Осип")
        self.assertEqual(witnesses[0][1], "Казмин")
        self.assertEqual(remaining, "Матвей Осипов")

    def test_status_word_prefix_parsed(self):
        comment = "свидетели: диакон Иоанн Петров"
        witnesses, _remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 1)
        self.assertEqual(witnesses[0][0], "Иоанн")
        self.assertEqual(witnesses[0][1], "Петров")
        self.assertEqual(witnesses[0][2], "диакон")

    def test_at_most_two_witnesses_extracted(self):
        comment = "свидетели: Иван Иванов, Петр Петров, Сидор Сидоров"
        witnesses, _ = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 2)

    def test_witnesses_separated_by_и(self):
        comment = "Свидетели: Стефан Ларионов и Иван Ларионов"
        witnesses, remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 2)
        self.assertEqual(witnesses[0][0], "Стефан")
        self.assertEqual(witnesses[0][1], "Ларионов")
        self.assertEqual(witnesses[1][0], "Иван")
        self.assertEqual(witnesses[1][1], "Ларионов")
        self.assertEqual(remaining, "")

    def test_trailing_commentary_after_witnesses_preserved(self):
        comment = "Свидетели: Стефан Ларионов и Иван Ларионов, есть подозрение что эта страница из другой МК"
        witnesses, remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 2)
        self.assertEqual(witnesses[0][0], "Стефан")
        self.assertEqual(witnesses[1][0], "Иван")
        self.assertIn("есть подозрение", remaining)

    def test_non_name_token_stops_witness_parsing(self):
        comment = "Свидетели: Яков Михеев и Антон Афанасьев, возраст не виден"
        witnesses, remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 2)
        self.assertIn("возраст не виден", remaining)

    def test_single_witness_with_trailing_commentary(self):
        comment = "Второй свидетель: Павел Яковлев, есть подозрение"
        witnesses, remaining = gsi._extract_witnesses_from_comment(comment)
        self.assertEqual(len(witnesses), 1)
        self.assertEqual(witnesses[0][0], "Павел")
        self.assertIn("есть подозрение", remaining)


class TestFormatDeathRow(unittest.TestCase):

    def _text(self, row, skip_statuses=frozenset(), cause_default="натуральная", default_village=""):
        lines = gsi._format_death_row(row, skip_statuses, cause_default, default_village=default_village)
        return "\n".join(lines)

    def test_minimal_deceased_with_age(self):
        row = _make_row(
            D_RECORD_NUM="1", D_GENDER="муж", D_D_DAY="5", D_D_MONTH="3",
            D_DEC_NAME="Иван", D_DEC_PATR="Иванов", D_AGE="50",
        )
        text = self._text(row)
        self.assertIn('deceased=person("Иван", "Иванов")', text)
        self.assertIn("age=50", text)

    def test_minimal_deceased_with_month_age(self):
        row = _make_row(
            D_RECORD_NUM="1", D_GENDER="муж", D_D_DAY="5", D_D_MONTH="3",
            D_DEC_NAME="Иван", D_DEC_PATR="Иванов", D_AGE="6 м",
        )
        text = self._text(row)
        self.assertIn('deceased=person("Иван", "Иванов")', text)
        self.assertIn('age="6 м"', text)

    def test_with_relative_and_relationship(self):
        row = _make_row(
            D_RECORD_NUM="2", D_GENDER="жен", D_D_DAY="1", D_D_MONTH="1",
            D_DEC_NAME="Мария", D_DEC_PATR="Иванова",
            D_REL_NAME="Антон", D_REL_PATR="Иванов", D_RELATIONSHIP="муж",
        )
        text = self._text(row)
        self.assertIn('relatives=[relative(person("Антон", "Иванов"), Relationship.HUSBAND)]', text)

    def test_comment_matching_relative_full_name_suppressed(self):
        row = _make_row(
            D_RECORD_NUM="3", D_GENDER="жен", D_DEC_NAME="Мария",
            D_REL_NAME="Антон", D_REL_PATR="Иванов", D_RELATIONSHIP="муж",
            D_COMMENT="Антон Иванов",
        )
        text = self._text(row)
        self.assertNotIn("comment=", text)

    def test_comment_matching_relative_first_name_only_suppressed(self):
        row = _make_row(
            D_RECORD_NUM="4", D_GENDER="жен", D_DEC_NAME="Мария",
            D_REL_NAME="Антон", D_REL_PATR="Иванов", D_RELATIONSHIP="муж",
            D_COMMENT="Антон",
        )
        text = self._text(row)
        self.assertNotIn("comment=", text)

    def test_comment_not_in_names_not_suppressed(self):
        row = _make_row(
            D_RECORD_NUM="5", D_GENDER="муж", D_DEC_NAME="Иван",
            D_COMMENT="дополнительная запись",
        )
        text = self._text(row)
        self.assertIn("comment=", text)
        self.assertIn("дополнительная запись", text)

    def test_cause_equals_default_omitted(self):
        row = _make_row(
            D_RECORD_NUM="6", D_GENDER="муж", D_DEC_NAME="Иван",
            D_CAUSE="натуральная",
        )
        text = self._text(row, cause_default="натуральная")
        self.assertNotIn("cause_of_death=", text)

    def test_cause_differs_from_default_included(self):
        row = _make_row(
            D_RECORD_NUM="7", D_GENDER="муж", D_DEC_NAME="Иван",
            D_CAUSE="горячка",
        )
        text = self._text(row, cause_default="натуральная")
        self.assertIn('cause_of_death=FEVER', text)

    def test_witnesses_from_dedicated_columns(self):
        row = _make_row(
            D_RECORD_NUM="8", D_GENDER="муж", D_DEC_NAME="Иван",
            D_W1_NAME="Петр", D_W1_PATR="Петров",
            D_W2_NAME="Федор", D_W2_PATR="Иванов",
        )
        text = self._text(row)
        self.assertIn('witness1=person("Петр", "Петров")', text)
        self.assertIn('witness2=person("Федор", "Иванов")', text)

    def test_witnesses_extracted_from_comment(self):
        row = _make_row(
            D_RECORD_NUM="9", D_GENDER="муж", D_DEC_NAME="Иван",
            D_COMMENT="свидетели: Петр Петров, Федор Иванов",
        )
        text = self._text(row)
        self.assertIn('witness1=person("Петр", "Петров")', text)
        self.assertIn('witness2=person("Федор", "Иванов")', text)
        # Comment itself should not appear (it was consumed by witness extraction)
        self.assertNotIn("свидетели:", text)

    def test_patronymic_suppressed_when_derivable_from_father(self):
        # deceased "Ирина Васильевна", father "Василий Филипов"
        # "Васильевна" derives from "Василий" → should be omitted
        row = _make_row(
            D_RECORD_NUM="2", D_GENDER="жен", D_D_DAY="23", D_D_MONTH="3",
            D_DEC_NAME="Ирина", D_DEC_PATR="Васильевна",
            D_DEC_STATUS="дочь девица из экономических крестьян",
            D_AGE="16",
            D_REL_NAME="Василий", D_REL_PATR="Филипов", D_RELATIONSHIP="отец",
        )
        text = self._text(row)
        self.assertIn('"Ирина"', text)
        self.assertNotIn('"Васильевна"', text)
        self.assertIn('relatives=[relative(person("Василий", "Филипов")', text)

    def test_patronymic_kept_when_not_derivable_from_father(self):
        # Patronymic doesn't match father's name → keep it
        row = _make_row(
            D_RECORD_NUM="3", D_GENDER="жен", D_D_DAY="1", D_D_MONTH="5",
            D_DEC_NAME="Анна", D_DEC_PATR="Петрова",
            D_REL_NAME="Иван", D_REL_PATR="Иванов", D_RELATIONSHIP="отец",
        )
        text = self._text(row)
        self.assertIn('"Петрова"', text)

    def test_patronymic_kept_when_relationship_is_not_father(self):
        # Same-name patronymic but relationship is husband → keep patronymic
        row = _make_row(
            D_RECORD_NUM="4", D_GENDER="жен", D_D_DAY="1", D_D_MONTH="5",
            D_DEC_NAME="Анна", D_DEC_PATR="Иванова",
            D_REL_NAME="Иван", D_REL_PATR="Иванов", D_RELATIONSHIP="муж",
        )
        text = self._text(row)
        self.assertIn('"Иванова"', text)

    def test_three_token_orig_name_uses_second_token_as_patronymic(self):
        # orig_names "Афанасий Иванов Ежевикин" (name + short patr + surname).
        # Old code did split(" ", 1) → patr="Иванов Ежевикин" → treated as surname → lost.
        # Fix: take only the second token as patr; third token is already in last_name column.
        row = _make_row(
            D_RECORD_NUM="3", D_GENDER="муж", D_D_DAY="10", D_D_MONTH="4",
            D_DEC_NAME_CANON="Афанасий",
            D_DEC_LAST_NAME="Ежевикин",
            D_DEC_PATR_CANON="Иванович",
            D_AGE="69",
            D_ORIG_NAMES="Имена в МК: Афанасий Иванов Ежевикин",
        )
        text = self._text(row)
        self.assertIn('"Иванов"', text)
        self.assertNotIn('"Иванович"', text)
        self.assertIn('last_name_orig="Ежевикин"', text)

    def test_orig_names_colon_only_falls_back_to_canonical(self):
        # Regression: "Имена в МК:" (no trailing space) must not override the
        # canonical name from D_DEC_NAME_CANON / D_DEC_PATR_CANON.
        # Before the fix the first token "Имена" triggered the "?" placeholder,
        # hiding a perfectly good canonical name in the sheet.
        row = _make_row(
            D_RECORD_NUM="2", D_GENDER="жен", D_D_DAY="12", D_D_MONTH="4",
            D_DEC_NAME_CANON="Ирина", D_DEC_PATR_CANON="Иванова",
            D_DEC_STATUS="вдова из экономических крестьян",
            D_AGE="78",
            D_ORIG_NAMES="Имена в МК:",
        )
        text = self._text(row)
        self.assertNotIn('person("?"', text)
        self.assertIn('"Ирина"', text)

    def test_deceased_non_default_residence_emitted(self):
        row = _make_row(
            D_RECORD_NUM="10", D_GENDER="муж", D_D_DAY="1", D_D_MONTH="1",
            D_DEC_NAME="Иван", D_DEC_PATR="Иванов",
            D_DEC_RESIDENCE="другое село",
        )
        text = self._text(row, default_village="заманиловка")
        self.assertIn('residence="другое село"', text)

    def test_deceased_default_residence_omitted(self):
        row = _make_row(
            D_RECORD_NUM="11", D_GENDER="муж", D_D_DAY="2", D_D_MONTH="2",
            D_DEC_NAME="Петр", D_DEC_PATR="Петров",
            D_DEC_RESIDENCE="заманиловка",
        )
        text = self._text(row, default_village="заманиловка")
        self.assertNotIn("residence=", text)

    def test_relative_non_default_residence_emitted(self):
        row = _make_row(
            D_RECORD_NUM="12", D_GENDER="жен", D_D_DAY="3", D_D_MONTH="3",
            D_DEC_NAME="Мария", D_DEC_PATR="Иванова",
            D_REL_NAME="Антон", D_REL_PATR="Иванов", D_RELATIONSHIP="муж",
            D_REL_RESIDENCE="иное село",
        )
        text = self._text(row, default_village="заманиловка")
        self.assertIn('residence="иное село"', text)

    def test_residence_comparison_case_insensitive(self):
        row = _make_row(
            D_RECORD_NUM="13", D_GENDER="муж", D_D_DAY="4", D_D_MONTH="4",
            D_DEC_NAME="Сидор", D_DEC_PATR="Сидоров",
            D_DEC_RESIDENCE="Заманиловка",
        )
        text = self._text(row, default_village="заманиловка")
        self.assertNotIn("residence=", text)


class TestFormatBirthRow(unittest.TestCase):

    def _text(self, row, skip_statuses=frozenset(), default_village=""):
        lines = gsi._format_birth_row(row, skip_statuses, default_village=default_village)
        return "\n".join(lines)

    def test_child_only(self):
        row = _make_row(
            B_RECORD_NUM="1", B_GENDER="муж",
            B_B_DAY="5", B_K_DAY="6",
            B_CHILD_NAME="Алексей",
        )
        text = self._text(row)
        self.assertIn('birth(', text)
        self.assertIn('child=person("Алексей")', text)

    def test_full_row_all_persons(self):
        row = _make_row(
            B_RECORD_NUM="2", B_GENDER="жен",
            B_CHILD_NAME="Анна",
            B_FATHER_NAME="Иван", B_FATHER_PATR="Иванов",
            B_MOTHER_NAME="Мария", B_MOTHER_PATR="Иванова",
            B_GP1_NAME="Петр", B_GP1_PATR="Петров",
            B_GP2_NAME="Авдотья", B_GP2_PATR="Иванова",
        )
        text = self._text(row)
        self.assertIn("child=", text)
        self.assertIn("father=", text)
        self.assertIn("mother=", text)
        self.assertIn("god_parent1=", text)
        self.assertIn("god_parent2=", text)

    def test_comment_matching_godparent_name_suppressed(self):
        row = _make_row(
            B_RECORD_NUM="3", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_GP1_NAME="Иван", B_GP1_PATR="Иванов",
            B_COMMENT="Иван Иванов",
        )
        text = self._text(row)
        self.assertNotIn("comment=", text)

    def test_unrelated_comment_emitted(self):
        row = _make_row(
            B_RECORD_NUM="4", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_COMMENT="запись неразборчива",
        )
        text = self._text(row)
        self.assertIn("comment=", text)
        self.assertIn("запись неразборчива", text)

    def test_orig_names_colon_only_falls_back_to_canonical(self):
        # Regression: "Имена в МК:" must not be parsed as a name for birth rows.
        row = _make_row(
            B_RECORD_NUM="5", B_GENDER="муж",
            B_CHILD_NAME_CANON="Алексей",
            B_FATHER_NAME_CANON="Иван", B_FATHER_PATR_CANON="Иванов",
            B_ORIG_NAMES="Имена в МК:",
        )
        text = self._text(row)
        self.assertNotIn('person("?"', text)
        self.assertIn('"Алексей"', text)

    def test_father_non_default_residence_emitted(self):
        row = _make_row(
            B_RECORD_NUM="10", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_FATHER_NAME="Иван", B_FATHER_PATR="Иванов",
            B_FATHER_RESIDENCE="село Другое",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertIn('residence="село Другое"', text)

    def test_father_default_residence_omitted(self):
        row = _make_row(
            B_RECORD_NUM="11", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_FATHER_NAME="Иван", B_FATHER_PATR="Иванов",
            B_FATHER_RESIDENCE="село Заманиловка",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertNotIn("residence=", text)

    def test_gp1_non_default_residence_emitted(self):
        row = _make_row(
            B_RECORD_NUM="12", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_GP1_NAME="Никита", B_GP1_PATR="Иванов",
            B_GP1_RESIDENCE="деревня Собакевичево",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertIn('residence="деревня Собакевичево"', text)

    def test_gp2_non_default_residence_emitted(self):
        row = _make_row(
            B_RECORD_NUM="13", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_GP2_NAME="Авдотья", B_GP2_PATR="Иванова",
            B_GP2_RESIDENCE="деревня Собакевичево",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertIn('residence="деревня Собакевичево"', text)

    def test_gp1_default_residence_omitted(self):
        row = _make_row(
            B_RECORD_NUM="14", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_GP1_NAME="Никита", B_GP1_PATR="Иванов",
            B_GP1_RESIDENCE="село Заманиловка",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertNotIn("residence=", text)

    def test_residence_comparison_is_case_insensitive(self):
        row = _make_row(
            B_RECORD_NUM="15", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_FATHER_NAME="Иван",
            B_FATHER_RESIDENCE="СЕЛО ЗАМАНИЛОВКА",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertNotIn("residence=", text)

    def test_mother_never_gets_residence(self):
        row = _make_row(
            B_RECORD_NUM="16", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_MOTHER_NAME="Мария", B_MOTHER_PATR="Иванова",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertNotIn("residence=", text)

    def test_non_empty_residence_emitted_when_no_default_village(self):
        row = _make_row(
            B_RECORD_NUM="17", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_FATHER_NAME="Иван",
            B_FATHER_RESIDENCE="село Заманиловка",
        )
        # default_village="" → any non-empty residence is "non-default"
        text = self._text(row)
        self.assertIn('residence="село Заманиловка"', text)

    def test_orig_names_part_count_mismatch_uses_canonical_and_orig_as_comment(self):
        # Regression: a record whose child (Леонтий) had no orig entry but
        # father and gp1 did. Old code wrongly assigned "Прохор Макаров" → child.
        # New code: child heuristic detects "Прохор Макаров" has a space → not a child.
        # Father gets "Прохор Макаров" from orig, gp1 gets "Ларион Савельев".
        row = _make_row(
            B_RECORD_NUM="11", B_GENDER="муж",
            B_B_DAY="4", B_K_DAY="8",
            B_CHILD_NAME_CANON="Леонтий",
            B_FATHER_NAME="Прохор", B_FATHER_PATR="Макаров",
            B_GP1_FIO="Илларион Савельевич",
            B_ORIG_NAMES="Имена в МК: Прохор Макаров; Ларион Савельев",
        )
        text = self._text(row)
        self.assertIn('child=person("Леонтий")', text)
        self.assertIn('father=person("Прохор", "Макаров")', text)
        self.assertIn('god_parent1=person("Ларион", "Савельев")', text)
        self.assertNotIn('"Прохор Макаров"', text)  # not assigned as single string


    def test_long_form_canonical_patr_dropped(self):
        # Long-form modern patronymics (e.g. "Иванович" from *_PATR_CANON) are silently
        # dropped because genealogy.py's validate_old_patronymic would reject them.
        row = _make_row(
            B_RECORD_NUM="18", B_GENDER="муж",
            B_CHILD_NAME="Алексей",
            B_FATHER_NAME="Иван", B_FATHER_PATR="Иванович",  # long-form in raw col
        )
        text = self._text(row)
        self.assertIn('"Иван"', text)
        self.assertNotIn('"Иванович"', text)


class TestFormatMarriageRow(unittest.TestCase):

    def _text(self, row, skip_statuses=frozenset(), default_village=""):
        lines = gsi._format_marriage_row(row, skip_statuses, default_village=default_village)
        return "\n".join(lines)

    def test_groom_and_bride(self):
        row = _make_row(
            M_RECORD_NUM="1", M_W_DAY="5",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Иванова",
        )
        text = self._text(row)
        self.assertIn("groom=", text)
        self.assertIn("bride=", text)

    def test_with_witnesses(self):
        row = _make_row(
            M_RECORD_NUM="2", M_W_DAY="10",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Иванова",
            M_W1_NAME="Федор", M_W1_PATR="Петров",
            M_W2_NAME="Иван", M_W2_PATR="Сидоров",
        )
        text = self._text(row)
        self.assertIn("witness1=", text)
        self.assertIn("witness2=", text)

    def test_comment_matching_witness_name_suppressed(self):
        row = _make_row(
            M_RECORD_NUM="3", M_W_DAY="12",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Иванова",
            M_W1_NAME="Федор", M_W1_PATR="Петров",
            M_COMMENT="Федор Петров",
        )
        text = self._text(row)
        self.assertNotIn("comment=", text)

    def test_unrelated_comment_emitted(self):
        row = _make_row(
            M_RECORD_NUM="4", M_W_DAY="15",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Иванова",
            M_COMMENT="документ повреждён",
        )
        text = self._text(row)
        self.assertIn("comment=", text)
        self.assertIn("документ повреждён", text)

    def test_groom_age_emitted(self):
        row = _make_row(
            M_RECORD_NUM="1", M_W_DAY="20",
            M_GROOM_NAME="Федот", M_GROOM_PATR="Ларионов",
            M_BRIDE_NAME="Фекла", M_BRIDE_PATR="Антонова",
            M_GROOM_AGE="18",
        )
        text = self._text(row)
        self.assertIn("groom_age=18", text)

    def test_bride_age_emitted(self):
        row = _make_row(
            M_RECORD_NUM="1", M_W_DAY="20",
            M_GROOM_NAME="Федот", M_GROOM_PATR="Ларионов",
            M_BRIDE_NAME="Фекла", M_BRIDE_PATR="Антонова",
            M_BRIDE_AGE="17",
        )
        text = self._text(row)
        self.assertIn("bride_age=17", text)

    def test_age_omitted_when_blank(self):
        row = _make_row(
            M_RECORD_NUM="1", M_W_DAY="20",
            M_GROOM_NAME="Федот", M_GROOM_PATR="Ларионов",
            M_BRIDE_NAME="Фекла", M_BRIDE_PATR="Антонова",
        )
        text = self._text(row)
        self.assertNotIn("groom_age=", text)
        self.assertNotIn("bride_age=", text)

    def test_orig_names_colon_only_falls_back_to_canonical(self):
        # Regression: "Имена в МК:" must not be parsed as a name for marriage rows.
        row = _make_row(
            M_RECORD_NUM="5", M_W_DAY="3",
            M_GROOM_NAME_CANON="Иван", M_GROOM_PATR_CANON="Иванов",
            M_BRIDE_NAME_CANON="Мария", M_BRIDE_PATR_CANON="Петрова",
            M_ORIG_NAMES="Имена в МК:",
        )
        text = self._text(row)
        self.assertNotIn('person("?"', text)
        self.assertIn('"Иван"', text)

    def test_groom_non_default_residence_emitted(self):
        row = _make_row(
            M_RECORD_NUM="6", M_W_DAY="1",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_GROOM_RESIDENCE="деревня Собакевичево",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertIn('residence="деревня Собакевичево"', text)

    def test_groom_default_residence_omitted(self):
        row = _make_row(
            M_RECORD_NUM="7", M_W_DAY="2",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_GROOM_RESIDENCE="село Заманиловка",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertNotIn("residence=", text)

    def test_bride_non_default_residence_emitted(self):
        row = _make_row(
            M_RECORD_NUM="8", M_W_DAY="3",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова",
            M_BRIDE_RESIDENCE="деревня Собакевичево",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertIn('residence="деревня Собакевичево"', text)

    def test_w1_non_default_residence_emitted(self):
        row = _make_row(
            M_RECORD_NUM="9", M_W_DAY="4",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова",
            M_W1_NAME="Федор", M_W1_PATR="Сидоров",
            M_W1_RESIDENCE="деревня Собакевичево",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertIn('residence="деревня Собакевичево"', text)

    def test_w2_non_default_residence_emitted(self):
        row = _make_row(
            M_RECORD_NUM="10", M_W_DAY="5",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова",
            M_W2_NAME="Иван", M_W2_PATR="Наковалкин",
            M_W2_RESIDENCE="деревня Собакевичево",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertIn('residence="деревня Собакевичево"', text)

    def test_residence_comparison_case_insensitive(self):
        row = _make_row(
            M_RECORD_NUM="11", M_W_DAY="6",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_GROOM_RESIDENCE="Село Заманиловка",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова",
        )
        text = self._text(row, default_village="село Заманиловка")
        self.assertNotIn("residence=", text)


class TestGetWorksheet(unittest.TestCase):

    def setUp(self):
        self.mock_gspread = MagicMock()
        self.patcher = patch.dict("sys.modules", {"gspread": self.mock_gspread})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_matching_sheet_returned(self):
        ws1 = MagicMock()
        ws1.title = "рождение"
        ws2 = MagicMock()
        ws2.title = "Смерть"
        self.mock_gspread.oauth.return_value.open_by_key.return_value.worksheets.return_value = [ws1, ws2]
        result = gsi._get_worksheet("FAKE_ID", "Смерть")
        self.assertIs(result, ws2)

    def test_matching_is_case_insensitive(self):
        ws = MagicMock()
        ws.title = "РОЖДЕНИЕ"
        self.mock_gspread.oauth.return_value.open_by_key.return_value.worksheets.return_value = [ws]
        result = gsi._get_worksheet("FAKE_ID", "рождение")
        self.assertIs(result, ws)

    def test_no_match_raises_value_error(self):
        ws = MagicMock()
        ws.title = "рождение"
        self.mock_gspread.oauth.return_value.open_by_key.return_value.worksheets.return_value = [ws]
        with self.assertRaises(ValueError):
            gsi._get_worksheet("FAKE_ID", "НетТакого")

    def test_oauth_called_once_with_no_args(self):
        ws = MagicMock()
        ws.title = "брак"
        self.mock_gspread.oauth.return_value.open_by_key.return_value.worksheets.return_value = [ws]
        gsi._get_worksheet("FAKE_ID", "брак")
        self.mock_gspread.oauth.assert_called_once_with()


class TestFetchRows(unittest.TestCase):

    def _make_ws(self, rows):
        ws = MagicMock()
        ws.get_all_values.return_value = rows
        return ws

    def test_filter_by_year_returns_matching_rows(self):
        header1 = [""] * 20
        header2 = [""] * 20
        data_row = [""] * 20
        data_row[14] = "1784"
        other_row = [""] * 20
        other_row[14] = "1800"
        ws = self._make_ws([header1, header2, data_row, other_row])
        result = gsi._fetch_rows(ws, 1784, 14)
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], data_row)

    def test_year_mismatch_returns_empty(self):
        header1 = [""] * 20
        header2 = [""] * 20
        data_row = [""] * 20
        data_row[14] = "1800"
        ws = self._make_ws([header1, header2, data_row])
        result = gsi._fetch_rows(ws, 1784, 14)
        self.assertEqual(result, [])

    def test_filter_by_year_and_village(self):
        header1 = [""] * 20
        header2 = [""] * 20
        row_a = [""] * 20
        row_a[14] = "1784"
        row_a[6] = "Заманиловка"
        row_b = [""] * 20
        row_b[14] = "1784"
        row_b[6] = "Горюхино"
        ws = self._make_ws([header1, header2, row_a, row_b])
        result = gsi._fetch_rows(ws, 1784, 14, village_filter="Заманиловка")
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], row_a)

    def test_village_filter_case_insensitive(self):
        header1 = [""] * 20
        header2 = [""] * 20
        data_row = [""] * 20
        data_row[14] = "1784"
        data_row[6] = "ЗАМАНИЛОВКА"
        ws = self._make_ws([header1, header2, data_row])
        result = gsi._fetch_rows(ws, 1784, 14, village_filter="заманиловка")
        self.assertEqual(len(result), 1)

    def test_village_mismatch_returns_empty(self):
        header1 = [""] * 20
        header2 = [""] * 20
        data_row = [""] * 20
        data_row[14] = "1784"
        data_row[6] = "Горюхино"
        ws = self._make_ws([header1, header2, data_row])
        result = gsi._fetch_rows(ws, 1784, 14, village_filter="Заманиловка")
        self.assertEqual(result, [])


class TestFetchRowsFromCsv(unittest.TestCase):

    def test_reads_csv_and_filters_by_year(self):
        import csv
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
            writer = csv.writer(f)
            writer.writerow([""] * 20)  # header
            row1 = [""] * 20
            row1[14] = "1838"
            row1[6] = "Горюхино"
            row1[18] = "Иван"
            writer.writerow(row1)
            row2 = [""] * 20
            row2[14] = "1837"
            writer.writerow(row2)
            path = Path(f.name)
        try:
            rows = gsi._fetch_rows_from_csv(str(path), 1838, 14, header_rows=1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][18], "Иван")
        finally:
            path.unlink()

    def test_filters_by_village(self):
        import csv
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
            writer = csv.writer(f)
            writer.writerow([""] * 20)
            row1 = [""] * 20
            row1[14] = "1838"
            row1[6] = "Горюхино"
            writer.writerow(row1)
            row2 = [""] * 20
            row2[14] = "1838"
            row2[6] = "Собакевичево"
            writer.writerow(row2)
            path = Path(f.name)
        try:
            rows = gsi._fetch_rows_from_csv(str(path), 1838, 14, village_filter="Горюхино", header_rows=1)
            self.assertEqual(len(rows), 1)
        finally:
            path.unlink()


def _facade(output: str) -> set[str]:
    """The names a generated file imports from the DSL's facade (DSL v1)."""
    import ast
    return {a.name for n in ast.parse(output).body if isinstance(n, ast.ImportFrom) and n.module == "verso.ru.dsl"
            for a in n.names}


class TestGenerateDeaths(unittest.TestCase):

    def test_output_contains_imports(self):
        row = _make_row(D_DEC_NAME="Иван", D_GENDER="муж", D_D_MONTH="3")
        output = gsi.generate_deaths([row], "ГАТО", "1", "1", "1", "Заманиловка", "Церковь", 1784)
        self.assertNotIn("import os", output)
        self.assertNotIn("import sys", output)
        self.assertNotIn("__main__", output)
        self.assertLessEqual({"death", "death_records", "death_month"}, _facade(output))

    def test_output_contains_variable_and_record(self):
        row = _make_row(D_DEC_NAME="Иван", D_GENDER="муж", D_D_MONTH="3")
        output = gsi.generate_deaths([row], "ГАТО", "1", "1", "1", "Заманиловка", "Церковь", 1784)
        self.assertIn("zamanilovka_deaths_1784 = death_records(", output)
        self.assertIn("death(", output)

    def test_relationship_import_added_when_needed(self):
        row = _make_row(
            D_DEC_NAME="Мария", D_GENDER="жен", D_D_MONTH="5",
            D_REL_NAME="Антон", D_RELATIONSHIP="муж",
        )
        output = gsi.generate_deaths([row], "", "", "", "", "Заманиловка", "", 1784)
        self.assertLessEqual({"Relationship", "relative"}, _facade(output))

    def test_relative_without_relationship(self):
        # The sheet names the relative and leaves «кем приходится» empty:
        # the list still carries them, with no relationship.
        row = _make_row(
            D_DEC_NAME="Мария", D_GENDER="жен", D_D_MONTH="5", D_REL_NAME="Антон",
        )
        output = gsi.generate_deaths([row], "", "", "", "", "Заманиловка", "", 1784)
        self.assertIn("relative", _facade(output))
        self.assertNotIn("Relationship", _facade(output))
        self.assertIn('relatives=[relative(person("Антон"), None)]', output)

    def test_relationship_import_absent_when_not_needed(self):
        row = _make_row(D_DEC_NAME="Иван", D_GENDER="муж", D_D_MONTH="3")
        output = gsi.generate_deaths([row], "", "", "", "", "Заманиловка", "", 1784)
        self.assertNotIn("Relationship", _facade(output))


class TestGenerateBirths(unittest.TestCase):

    def test_output_contains_imports(self):
        row = _make_row(B_CHILD_NAME="Алексей", B_GENDER="муж", B_B_MONTH="4")
        output = gsi.generate_births([row], "ГАТО", "1", "1", "1", "Заманиловка", "Церковь", 1804)
        self.assertNotIn("import os", output)
        self.assertNotIn("__main__", output)
        self.assertLessEqual({"birth", "birth_month", "birth_records"}, _facade(output))

    def test_output_contains_variable_and_record(self):
        row = _make_row(B_CHILD_NAME="Алексей", B_GENDER="муж", B_B_MONTH="4")
        output = gsi.generate_births([row], "ГАТО", "1", "1", "1", "Заманиловка", "Церковь", 1804)
        self.assertIn("zamanilovka_births_1804 = birth_records(", output)
        self.assertIn("birth(", output)

    def test_person_import_present_when_names_exist(self):
        row = _make_row(B_CHILD_NAME="Алексей", B_GENDER="муж")
        output = gsi.generate_births([row], "", "", "", "", "Заманиловка", "", 1804)
        self.assertIn("person", _facade(output))


class TestGenerateMarriages(unittest.TestCase):

    def test_output_contains_imports(self):
        row = _make_row(M_GROOM_NAME="Петр", M_W_MONTH="5")
        output = gsi.generate_marriages([row], "ГАТО", "1", "1", "1", "Заманиловка", "Церковь", 1810)
        self.assertNotIn("import os", output)
        self.assertNotIn("__main__", output)
        self.assertLessEqual({"marriage", "marriage_records", "marriage_month"}, _facade(output))

    def test_output_contains_variable_and_record(self):
        row = _make_row(M_GROOM_NAME="Петр", M_W_MONTH="5")
        output = gsi.generate_marriages([row], "ГАТО", "1", "1", "1", "Заманиловка", "Церковь", 1810)
        self.assertIn("zamanilovka_marriages_1810 = marriage_records(", output)
        self.assertIn("marriage(", output)


class TestClergyPersonCall(unittest.TestCase):

    def test_name_and_patr(self):
        result = gsi._clergy_person_call("Степан Космин")
        self.assertEqual(result, 'person("Степан", "Космин")')

    def test_name_only(self):
        result = gsi._clergy_person_call("Иоанн")
        self.assertEqual(result, 'person("Иоанн")')

    def test_empty_returns_none(self):
        self.assertIsNone(gsi._clergy_person_call(""))

    def test_three_word_fio(self):
        # "Петров Сын" is not a valid old patronymic, so it gets dropped
        result = gsi._clergy_person_call("Иван Петров Сын")
        self.assertEqual(result, 'person("Иван")')

    def test_valid_old_patronymic_kept(self):
        result = gsi._clergy_person_call("Степан Космин")
        self.assertEqual(result, 'person("Степан", "Космин")')

    def test_canonical_patronymic_converted_to_old_form(self):
        # "Кузьмич" is a modern patronymic that maps to the old form "Кузьмин" (the base's form for Кузьма)
        result = gsi._clergy_person_call("Степан Кузьмич")
        self.assertEqual(result, 'person("Степан", "Кузьмин")')

    def test_whitespace_stripped(self):
        result = gsi._clergy_person_call("  Степан   Космин  ")
        self.assertEqual(result, 'person("Степан", "Космин")')


class TestFormatBirthRowClergy(unittest.TestCase):

    def _text(self, row):
        lines = gsi._format_birth_row(row)
        return "\n".join(lines)

    def test_priest_emitted(self):
        row = _make_row(
            B_RECORD_NUM="1", B_GENDER="муж", B_CHILD_NAME="Алексей",
            B_PRIEST_FIO="Степан Космин",
        )
        text = self._text(row)
        self.assertIn('priest=person("Степан", "Космин")', text)

    def test_deacon_emitted(self):
        row = _make_row(
            B_RECORD_NUM="1", B_GENDER="муж", B_CHILD_NAME="Алексей",
            B_DEACON_FIO="Иван Иванов",
        )
        text = self._text(row)
        self.assertIn('deacon=person("Иван", "Иванов")', text)

    def test_dyachok_emitted(self):
        row = _make_row(
            B_RECORD_NUM="1", B_GENDER="муж", B_CHILD_NAME="Алексей",
            B_DYACHOK_FIO="Петр Петров",
        )
        text = self._text(row)
        self.assertIn('dyachok=person("Петр", "Петров")', text)

    def test_empty_clergy_omitted(self):
        row = _make_row(
            B_RECORD_NUM="1", B_GENDER="муж", B_CHILD_NAME="Алексей",
        )
        text = self._text(row)
        self.assertNotIn("priest=", text)
        self.assertNotIn("deacon=", text)
        self.assertNotIn("dyachok=", text)

    def test_priest_name_only(self):
        row = _make_row(
            B_RECORD_NUM="1", B_GENDER="муж", B_CHILD_NAME="Алексей",
            B_PRIEST_FIO="Иоанн",
        )
        text = self._text(row)
        self.assertIn('priest=person("Иоанн")', text)


class TestFormatMarriageRowClergy(unittest.TestCase):

    def _text(self, row):
        lines = gsi._format_marriage_row(row)
        return "\n".join(lines)

    def test_priest_emitted(self):
        row = _make_row(
            M_RECORD_NUM="1", M_W_DAY="5",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Иванова",
            M_PRIEST_FIO="Степан Космин",
        )
        text = self._text(row)
        self.assertIn('priest=person("Степан", "Космин")', text)

    def test_empty_clergy_omitted(self):
        row = _make_row(
            M_RECORD_NUM="1", M_W_DAY="5",
            M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов",
            M_BRIDE_NAME="Мария", M_BRIDE_PATR="Иванова",
        )
        text = self._text(row)
        self.assertNotIn("priest=", text)
        self.assertNotIn("deacon=", text)
        self.assertNotIn("dyachok=", text)


class TestFormatDeathRowClergy(unittest.TestCase):

    def _text(self, row):
        lines = gsi._format_death_row(row)
        return "\n".join(lines)

    def test_priest_emitted(self):
        row = _make_row(
            D_RECORD_NUM="1", D_GENDER="муж", D_D_DAY="5", D_D_MONTH="3",
            D_DEC_NAME="Иван", D_DEC_PATR="Иванов",
            D_PRIEST_FIO="Николай Космин",
        )
        text = self._text(row)
        self.assertIn('priest=person("Николай", "Космин")', text)

    def test_empty_clergy_omitted(self):
        row = _make_row(
            D_RECORD_NUM="1", D_GENDER="муж", D_D_DAY="5", D_D_MONTH="3",
            D_DEC_NAME="Иван", D_DEC_PATR="Иванов",
        )
        text = self._text(row)
        self.assertNotIn("priest=", text)
        self.assertNotIn("deacon=", text)
        self.assertNotIn("dyachok=", text)


def _make_row_cols(cols_obj, **kwargs) -> list[str]:
    """Build a fake row using a column config dataclass (e.g. BirthColumns).
    Keyword arg names are field names on the dataclass, e.g. CHILD_NAME="Мария".
    """
    row = [""] * 200
    for field_name, val in kwargs.items():
        idx = getattr(cols_obj, field_name)
        if idx is not None:
            row[idx] = val
    return row


# ─── Tests for new helpers ────────────────────────────────────────────────────


class TestSplitFio(unittest.TestCase):

    def test_name_and_patr(self):
        self.assertEqual(gsi._split_fio("Иван Петров"), ("Иван", "Петров"))

    def test_single_name(self):
        self.assertEqual(gsi._split_fio("Иван"), ("Иван", ""))

    def test_empty(self):
        self.assertEqual(gsi._split_fio(""), ("", ""))

    def test_none(self):
        self.assertEqual(gsi._split_fio(None), ("", ""))

    def test_whitespace_only(self):
        self.assertEqual(gsi._split_fio("   "), ("", ""))

    def test_strips_whitespace(self):
        self.assertEqual(gsi._split_fio("  Иван  Петров  "), ("Иван", "Петров"))

    def test_surname_first_fio_reordered(self):
        """Surname-first FIO like 'Манилов Семен Петрович' should extract name+patr."""
        self.assertEqual(gsi._split_fio("Манилов Семен Петрович"), ("Семен", "Петрович"))


class TestParseAgeV2(unittest.TestCase):

    def test_years(self):
        self.assertEqual(gsi._parse_age_v2("33", "", "", ""), 33)

    def test_months(self):
        self.assertEqual(gsi._parse_age_v2("", "6", "", ""), "6 м")

    def test_weeks(self):
        self.assertEqual(gsi._parse_age_v2("", "", "2", ""), "2 н")

    def test_days(self):
        self.assertEqual(gsi._parse_age_v2("", "", "", "3"), "3 д")

    def test_years_takes_priority(self):
        self.assertEqual(gsi._parse_age_v2("5", "6", "2", "1"), 5)

    def test_months_takes_priority_over_weeks(self):
        self.assertEqual(gsi._parse_age_v2("", "3", "2", ""), "3 м")

    def test_all_empty(self):
        self.assertIsNone(gsi._parse_age_v2("", "", "", ""))

    def test_all_zero(self):
        self.assertIsNone(gsi._parse_age_v2("0", "0", "0", "0"))


class TestFetchRowsHeaderRows(unittest.TestCase):

    def test_default_skips_2_header_rows(self):
        ws = MagicMock()
        ws.get_all_values.return_value = [
            ["h1", "", "", "", "", "", "", "", "", "", "", "", "", "", "1800"],
            ["h2", "", "", "", "", "", "", "", "", "", "", "", "", "", "1800"],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "1800"],
        ]
        rows = gsi._fetch_rows(ws, 1800, 14)
        self.assertEqual(len(rows), 1)

    def test_header_rows_3_skips_3_rows(self):
        ws = MagicMock()
        ws.get_all_values.return_value = [
            ["h1", "", "", "", "", "", "", "", "", "", "", "", "", "", "1800"],
            ["h2", "", "", "", "", "", "", "", "", "", "", "", "", "", "1800"],
            ["h3", "", "", "", "", "", "", "", "", "", "", "", "", "", "1800"],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "1800"],
        ]
        rows = gsi._fetch_rows(ws, 1800, 14, header_rows=3)
        self.assertEqual(len(rows), 1)


# ─── Tests for familio-standard (v2) format ──────────────────────────────────

STANDARD_BIRTH_COLS = gsi.FORMAT_FAMILIO_STANDARD.birth_cols
STANDARD_MARRIAGE_COLS = gsi.FORMAT_FAMILIO_STANDARD.marriage_cols
STANDARD_DEATH_COLS = gsi.FORMAT_FAMILIO_STANDARD.death_cols


class TestFormatBirthRowStandard(unittest.TestCase):
    """Tests for _format_birth_row with familio-standard column config."""

    def _text(self, row, **kw):
        lines = gsi._format_birth_row(row, cols=STANDARD_BIRTH_COLS, **kw)
        return "\n".join(lines)

    def test_basic_birth_no_canon_columns(self):
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="жен", B_DAY="1", K_DAY="3",
                             CHILD_NAME="Мария",
                             FATHER_NAME="Леонтий", FATHER_PATR="Андреев",
                             FATHER_STATUS="ясачный крестьянин",
                             ORIG_NAMES="Имена в МК: Марья; Леонтий Андреев")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('child=person("Марья")', text)
        self.assertIn('father=person("Леонтий", "Андреев"', text)

    def test_godparent_fio_only(self):
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Иван",
                             GP1_FIO="Семен Тихонов", GP1_STATUS="ясачный крестьянин",
                             GP2_FIO="Анна Петрова",
                             ORIG_NAMES="Имена в МК: Иван; Семен Тихонов; Анна Петрова")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('god_parent1=person("Семен", "Тихонов"', text)
        self.assertIn('god_parent2=person("Анна", "Петрова"', text)

    def test_godparent_fio_single_name(self):
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Петр",
                             GP1_FIO="Семен",
                             ORIG_NAMES="Имена в МК: Петр; Семен")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('god_parent1=person("Семен")', text)

    def test_clergy_at_v2_positions(self):
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Иван",
                             PRIEST_FIO="Степан Космин")
        text = self._text(row, default_village="Горюхино")
        self.assertIn("priest=person(", text)

    def test_comment_from_v2_position(self):
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Иван",
                             COMMENT="некая пометка")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('comment="некая пометка"', text)

    def test_non_default_residence(self):
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Иван",
                             FATHER_NAME="Петр", FATHER_PATR="Иванов",
                             FATHER_RESIDENCE="Собакевичево")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('residence="Собакевичево"', text)

    def test_godparent_surname_from_orig_names(self):
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="1", K_DAY="2",
                             CHILD_NAME="Иван",
                             FATHER_NAME="Михаил", FATHER_PATR="Матвеев",
                             FATHER_LAST_NAME="Мижуев",
                             GP1_FIO="Мижуев Василий Яковлевич",
                             ORIG_NAMES="Имена в МК: Иван; Михаил Матвеев Мижуев; Василий Яковлев Мижуев")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('god_parent1=person("Василий", "Яковлев", last_name_orig="Мижуев"', text)

    def test_orig_comment_stripped_from_surname(self):
        """Comments after " - " in orig_names should not become last_name_orig."""
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="жен", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Татьяна",
                             GP1_FIO="Дмитрий Флорович",
                             ORIG_NAMES="Имена в МК: Татиана; Димитрий Фролов - имя трудно разобрать из-за повреждения страницы")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('god_parent1=person("Димитрий", "Фролов")', text)
        self.assertNotIn("имя трудно", text.split("comment=")[0] if "comment=" in text else text)

    def test_child_variant_spelling_accepted(self):
        """Child orig "Матрена" should be accepted even if canon is "Макрина"."""
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="10", GENDER="жен", B_DAY="13", K_DAY="16",
                             CHILD_NAME="Макрина",
                             FATHER_NAME="Герасим", FATHER_PATR="Мартынов", FATHER_LAST_NAME="Чмокин",
                             ORIG_NAMES="Имена в МК: Матрена; Герасим Мартынов Чмокин; Домна Нестерова Чмокина")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('child=person("Матрена")', text)
        self.assertIn('father=person("Герасим", "Мартынов", last_name_orig="Чмокин"', text)


    def test_male_status_auto_swapped_for_female_person(self):
        """When a Status constant is male but the person is female, swap to female form."""
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="жен", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Мария",
                             GP1_FIO="Домна Тимофеевна",
                             GP1_STATUS="крестьянин помещицы Лукерьи Кузьминичны Маниловой",
                             ORIG_NAMES="Имена в МК: Мария; Домна Тимофеева")
        text = self._text(row, default_village="Горюхино")
        # Should NOT have the male status, should have female form or no status
        self.assertNotIn('status="крестьянин помещицы', text)

    def test_record_gender_auto_swapped_for_female_child(self):
        """When record gender is MALE but child name is female, swap to FEMALE."""
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="2", GENDER="муж", B_DAY="30", K_DAY="2",
                             CHILD_NAME="Анастасия",
                             ORIG_NAMES="Имена в МК: Настасья")
        text = self._text(row, default_village="Горюхино")
        self.assertIn("Gender.FEMALE", text)
        self.assertNotIn("Gender.MALE", text)


class TestFormatMarriageRowStandard(unittest.TestCase):
    """Tests for _format_marriage_row with familio-standard column config."""

    def _text(self, row, **kw):
        lines = gsi._format_marriage_row(row, cols=STANDARD_MARRIAGE_COLS, **kw)
        return "\n".join(lines)

    def test_basic_marriage(self):
        row = _make_row_cols(STANDARD_MARRIAGE_COLS,
                             RECORD_NUM="1", W_DAY="10",
                             GROOM_NAME="Никита", GROOM_PATR="Тарасьев",
                             GROOM_STATUS="солдат",
                             BRIDE_NAME="Анастасия", BRIDE_PATR="Савельева",
                             BRIDE_STATUS="девка",
                             ORIG_NAMES="Имена в МК: Микита Тарасов; Настасья Савельева")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('groom=person("Микита", "Тарасов"', text)
        self.assertIn('bride=person("Настасья", "Савельева"', text)

    def test_witness_fio_only(self):
        row = _make_row_cols(STANDARD_MARRIAGE_COLS,
                             RECORD_NUM="1", W_DAY="10",
                             GROOM_NAME="Иван", GROOM_PATR="Петров",
                             BRIDE_NAME="Мария", BRIDE_PATR="Иванова",
                             W1_FIO="Семен Тихонов", W1_STATUS="ясачный крестьянин",
                             W2_FIO="Максим Федоров",
                             ORIG_NAMES="Имена в МК: Иван Петров; Мария Иванова; Семен Тихонов; Максим Федоров")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('witness1=person("Семен", "Тихонов"', text)
        self.assertIn('witness2=person("Максим", "Федоров"', text)

    def test_marriage_num(self):
        row = _make_row_cols(STANDARD_MARRIAGE_COLS,
                             RECORD_NUM="1", W_DAY="10",
                             GROOM_NAME="Георгий", GROOM_PATR="Павлов",
                             GROOM_MARRIAGE_NUM="2",
                             BRIDE_NAME="Агафья", BRIDE_PATR="Федорова",
                             ORIG_NAMES="Имена в МК: Георгий Павлов; Агафья Федорова")
        text = self._text(row, default_village="Горюхино")
        self.assertIn("groom_marriage_num=2", text)


    def test_groom_bride_orig_misalignment_detected_by_gender(self):
        """When groom canonical is male but orig[0] is female, groom uses canonical."""
        row = _make_row_cols(STANDARD_MARRIAGE_COLS,
                             RECORD_NUM="9", W_DAY="11",
                             GROOM_NAME="Евстафий", GROOM_PATR="Гордеев",
                             GROOM_STATUS="отрок из ясачных крестьян",
                             BRIDE_NAME="Фекла", BRIDE_PATR="Прохорова",
                             BRIDE_STATUS="девка из ясачных крестьян",
                             ORIG_NAMES="Имена в МК: Фекла Прохорова; Леонтий Герасимов; Тарас Нестеров; Домна Ионова")
        text = self._text(row, default_village="Горюхино")
        # Groom should use canonical "Евстафий" not orig "Фекла"
        self.assertIn('groom=person("Евстафий", "Гордеев"', text)
        self.assertIn('bride=person("Фекла", "Прохорова"', text)

    def test_witness_male_with_female_status_auto_swapped(self):
        """W2 has female status 'крестьянка' but male witness 'Макар' — auto-swap to 'крестьянин'."""
        row = _make_row_cols(STANDARD_MARRIAGE_COLS,
                             RECORD_NUM="1", W_DAY="17",
                             GROOM_NAME="Корнилий", GROOM_PATR="Евграфович",
                             GROOM_STATUS="отрок из крестьян помещицы Лукерьи Кузьминичны Маниловой",
                             BRIDE_NAME="Ксения", BRIDE_PATR="Романовна",
                             BRIDE_STATUS="девка из крестьян помещицы Лукерьи Кузьминичны Маниловой",
                             W1_FIO="Влас Назарович",
                             W1_STATUS="крестьянин помещицы Лукерьи Кузьминичны Маниловой",
                             W2_FIO="Макар Тимофеевич",
                             W2_STATUS="крестьянка помещицы Лукерьи Кузьминичны Маниловой",
                             ORIG_NAMES="Имена в МК: Корнилий Евграфов; Влас Назаров; Макар Тимофеев; Домна Тимофеева")
        text = self._text(row, default_village="Горюхино")
        # Макар is male — status must be swapped to крестьянин
        self.assertIn('witness1=person("Влас", "Назаров"', text)
        self.assertIn('witness2=person("Макар", "Тимофеев"', text)
        self.assertIn('status="крестьянин помещицы Лукерьи Кузьминичны Маниловой"', text.split("witness2")[1])
        self.assertNotIn('крестьянка', text.split("witness2")[1])

    def test_non_name_orig_part_preserved_as_comment(self):
        """When orig_names has a non-name part (comment text), preserve as record comment."""
        row = _make_row_cols(STANDARD_MARRIAGE_COLS,
                             RECORD_NUM="3", W_DAY="10",
                             GROOM_NAME="?",
                             GROOM_MARRIAGE_NUM="1",
                             BRIDE_NAME="Елена", BRIDE_PATR="Леонтьева",
                             BRIDE_STATUS="девка из ясачных крестьян",
                             BRIDE_MARRIAGE_NUM="1",
                             ORIG_NAMES="Имена в МК: имя жениха неразборчиво написано; Елена Леонтьева")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('groom=person("?"', text)
        self.assertIn('bride=person("Елена", "Леонтьева"', text)
        self.assertIn('comment="Имя жениха неразборчиво написано"', text)


class TestFormatDeathRowStandard(unittest.TestCase):
    """Tests for _format_death_row with familio-standard column config."""

    def _text(self, row, **kw):
        lines = gsi._format_death_row(row, cols=STANDARD_DEATH_COLS, **kw)
        return "\n".join(lines)

    def test_basic_death_with_age_years(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="муж", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Ефим", DEC_PATR="Михайлов",
                             DEC_STATUS="ясачный крестьянин",
                             AGE_YEARS="33",
                             ORIG_NAMES="Имена в МК: Ефим Михайлов")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('deceased=person("Ефим", "Михайлов"', text)
        self.assertIn("age=33", text)

    def test_age_months(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="жен", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Мария",
                             AGE_MONTHS="6")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('age="6 м"', text)

    def test_age_weeks(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="муж", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Иван",
                             AGE_WEEKS="2")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('age="2 н"', text)

    def test_age_days(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="муж", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Иван",
                             AGE_DAYS="3")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('age="3 д"', text)

    def test_no_witness_columns_falls_back_to_comment(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="муж", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Иван", DEC_PATR="Петров",
                             AGE_YEARS="50",
                             COMMENT="свидетели: Григорий Иванов, Федор Петров")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('witness1=person("Григорий", "Иванов")', text)
        self.assertIn('witness2=person("Федор", "Петров")', text)

    def test_relative_with_relationship(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="жен", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Мария",
                             AGE_YEARS="2",
                             RELATIONSHIP="отец",
                             REL_NAME="Василий", REL_PATR="Иванов",
                             REL_STATUS="ясачный крестьянин",
                             ORIG_NAMES="Имена в МК: Мария; Василий Иванов")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('relatives=[relative(person("Василий", "Иванов"', text)
        self.assertIn("Relationship.FATHER)]", text)

    def test_clergy_at_v2_positions(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="муж", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Иван",
                             PRIEST_FIO="Степан Космин")
        text = self._text(row, default_village="Горюхино")
        self.assertIn("priest=person(", text)

    def test_cause_of_death(self):
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="муж", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Иван",
                             AGE_YEARS="50",
                             CAUSE="горячка")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('cause_of_death=FEVER', text)

    def test_deceased_orig_skipped_when_canon_name_differs(self):
        """Deceased "Нил" has no orig entry; orig has only mother "Ефимия Елисеева".
        The importer should use canonical "Нил" for deceased, not "Ефимия"."""
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="19", GENDER="муж", D_DAY="12", D_MONTH="9",
                             DEC_NAME="Нил",
                             DEC_STATUS="солдатский сын",
                             AGE_YEARS="2",
                             RELATIONSHIP="мать",
                             REL_NAME="Ефимия", REL_PATR="Елисеева",
                             REL_STATUS="солдатская жена",
                             ORIG_NAMES="Имена в МК: Ефимия Елисеева")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('deceased=person("Нил"', text)
        self.assertIn('relatives=[relative(person("Ефимия", "Елисеева"', text)

    def test_orig_dash_comment_preserved_as_record_comment(self):
        """When orig_names has ' - ' text and no explicit comment, preserve as comment."""
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="2", GENDER="муж", D_DAY="10", D_MONTH="5",
                             DEC_NAME="Сергей", DEC_LAST_NAME="Кевлев",
                             DEC_STATUS="крестьянин помещика Нила Евграфовича Манилова",
                             AGE_YEARS="82",
                             ORIG_NAMES="Имена в МК: Сергей Кевлев - отчество неразборчиво написано")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('deceased=person("Сергей", last_name_orig="Кевлев"', text)
        self.assertIn('comment="отчество неразборчиво написано"', text)

    def test_orig_dash_comment_not_override_explicit_comment(self):
        """When both explicit comment and orig ' - ' text exist, keep explicit comment."""
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="3", GENDER="муж", D_DAY="5", D_MONTH="3",
                             DEC_NAME="Иван",
                             AGE_YEARS="40",
                             COMMENT="особое примечание",
                             ORIG_NAMES="Имена в МК: Иван - имя неразборчиво")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('comment="особое примечание"', text)
        self.assertNotIn('имя неразборчиво', text)

    def test_non_name_orig_preserved_as_comment(self):
        """When orig_names is a non-name string (no 'Имена в МК:'), preserve as comment."""
        row = _make_row_cols(STANDARD_DEATH_COLS,
                             RECORD_NUM="1", GENDER="жен", D_DAY="9", D_MONTH="1",
                             DEC_NAME="Анна",
                             DEC_STATUS="крестьянка помещика",
                             ORIG_NAMES="Возраст не виден из-за корешка книги")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('deceased=person("Анна"', text)
        self.assertIn('comment="Возраст не виден из-за корешка книги"', text)


# ─── Tests for custom defaults ───────────────────────────────────────────────


class TestGenerateBirthsCustomDefaults(unittest.TestCase):

    def _output(self, **kwargs):
        row = _make_row(B_CHILD_NAME="Иван", B_GENDER="муж", B_B_MONTH="3",
                        B_FATHER_NAME="Петр", B_FATHER_PATR="Иванов",
                        B_FATHER_STATUS="ясачный крестьянин")
        return gsi.generate_births([row], "", "", "", "", "Горюхино", "", 1754, **kwargs)

    def test_default_statuses_in_record_defaults(self):
        output = self._output()
        self.assertIn('status_male="экономический крестьянин"', output)
        self.assertIn('status_female="экономическая крестьянка"', output)

    def test_custom_statuses_in_record_defaults(self):
        output = self._output(status_male="ясачный крестьянин",
                              status_female="ясачная крестьянка")
        self.assertIn('status_male="ясачный крестьянин"', output)
        self.assertIn('status_female="ясачная крестьянка"', output)
        self.assertNotIn("экономический", output)

    def test_custom_status_suppressed_in_person_call(self):
        output = self._output(status_male="ясачный крестьянин",
                              status_female="ясачная крестьянка")
        # Father has status="ясачный крестьянин" which matches the default → suppressed
        self.assertNotIn('status="ясачный крестьянин"', output)


class TestGenerateMarriagesCustomDefaults(unittest.TestCase):

    def _output(self, **kwargs):
        row = _make_row(M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов", M_W_MONTH="1",
                        M_GROOM_STATUS="ясачный крестьянин",
                        M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова",
                        M_BRIDE_STATUS="девка из ясачных крестьян")
        return gsi.generate_marriages([row], "", "", "", "", "Горюхино", "", 1800, **kwargs)

    def test_default_statuses_in_record_defaults(self):
        output = self._output()
        self.assertIn('status_male="экономический крестьянин"', output)
        self.assertIn('status_bride="девка из экономических крестьян"', output)

    def test_custom_statuses_in_record_defaults(self):
        output = self._output(status_male="ясачный крестьянин",
                              status_female="девица из ясачных крестьян",
                              status_bride="девка из ясачных крестьян")
        self.assertIn('status_male="ясачный крестьянин"', output)
        self.assertIn('status_female="девица из ясачных крестьян"', output)
        self.assertIn('status_bride="девка из ясачных крестьян"', output)

    def test_custom_status_suppressed_in_person_call(self):
        output = self._output(status_male="ясачный крестьянин",
                              status_bride="девка из ясачных крестьян")
        # Groom status matches default → suppressed
        self.assertNotIn('status="ясачный крестьянин"', output)
        # Bride status matches default → suppressed
        self.assertNotIn('status="девка из ясачных крестьян"', output)

    def test_custom_status_groom_in_record_defaults(self):
        output = self._output(status_groom="отрок из ясачных крестьян")
        self.assertIn('status_groom="отрок из ясачных крестьян"', output)

    def test_status_groom_suppressed_in_person_call(self):
        row = _make_row(M_GROOM_NAME="Петр", M_GROOM_PATR="Иванов", M_W_MONTH="1",
                        M_GROOM_STATUS="отрок из ясачных крестьян",
                        M_BRIDE_NAME="Мария", M_BRIDE_PATR="Петрова")
        output = gsi.generate_marriages([row], "", "", "", "", "Горюхино", "", 1800,
                                        status_groom="отрок из ясачных крестьян")
        self.assertNotIn('status="отрок из ясачных крестьян"', output)

    def test_no_status_groom_by_default(self):
        output = self._output()
        self.assertNotIn("status_groom", output)


class TestGenerateDeathsCustomDefaults(unittest.TestCase):

    def _output(self, **kwargs):
        row = _make_row(D_DEC_NAME="Иван", D_DEC_PATR="Петров", D_GENDER="муж",
                        D_D_MONTH="5", D_DEC_STATUS="ясачный крестьянин", D_AGE="50")
        return gsi.generate_deaths([row], "", "", "", "", "Горюхино", "", 1754, **kwargs)

    def test_default_statuses_in_record_defaults(self):
        output = self._output()
        self.assertIn('status_male="экономический крестьянин"', output)
        self.assertIn('cause_of_death=NATURAL', output)

    def test_custom_statuses_in_record_defaults(self):
        output = self._output(status_male="ясачный крестьянин",
                              status_female="ясачная крестьянка")
        self.assertIn('status_male="ясачный крестьянин"', output)
        self.assertIn('status_female="ясачная крестьянка"', output)

    def test_custom_cause_of_death(self):
        output = self._output(cause_of_death="горячка")
        self.assertIn('cause_of_death=FEVER', output)

    def test_custom_status_suppressed_in_person_call(self):
        output = self._output(status_male="ясачный крестьянин")
        # Deceased status matches custom default → suppressed
        self.assertNotIn('status="ясачный крестьянин"', output)


class TestGodparentSurnameColumn(unittest.TestCase):
    """Tests for GP1/GP2 surname from dedicated last_name column."""

    def _text(self, row, **kw):
        lines = gsi._format_birth_row(row, cols=STANDARD_BIRTH_COLS, **kw)
        return "\n".join(lines)

    def test_gp1_surname_from_dedicated_column(self):
        """GP1 surname should be read from GP1_LAST_NAME column."""
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Иван",
                             GP1_NAME="Семен", GP1_PATR="Петров",
                             GP1_LAST_NAME="Манилов",
                             GP1_FIO="Манилов Семен Петрович")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('last_name_orig="Манилов"', text)

    def test_gp2_surname_from_dedicated_column(self):
        """GP2 surname should be read from GP2_LAST_NAME column."""
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Иван",
                             GP2_NAME="Анна", GP2_PATR="Ивановна",
                             GP2_LAST_NAME="Манилова",
                             GP2_FIO="Манилова Анна Ивановна")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('last_name_orig="Манилова"', text)

    def test_gp1_no_surname_when_column_empty(self):
        """No last_name_orig when GP1_LAST_NAME is empty."""
        row = _make_row_cols(STANDARD_BIRTH_COLS,
                             RECORD_NUM="1", GENDER="муж", B_DAY="5", K_DAY="7",
                             CHILD_NAME="Иван",
                             GP1_NAME="Семен", GP1_PATR="Тихонов",
                             GP1_FIO="Семен Тихонов")
        text = self._text(row, default_village="Горюхино")
        self.assertNotIn('last_name_orig', text)


class TestFixStatusGender(unittest.TestCase):
    """Tests for _fix_status_gender swapping status to match person gender."""

    def test_yasak_male_to_female(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("ясачный крестьянин", Gender.FEMALE)
        self.assertEqual(result, "ясачная крестьянка")

    def test_yasak_female_to_male(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("ясачная крестьянка", Gender.MALE)
        self.assertEqual(result, "ясачный крестьянин")

    def test_econ_male_to_female(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("экономический крестьянин", Gender.FEMALE)
        self.assertEqual(result, "экономическая крестьянка")

    def test_econ_female_to_male(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("экономическая крестьянка", Gender.MALE)
        self.assertEqual(result, "экономический крестьянин")

    def test_generic_krestyanin_to_krestyanka(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("крестьянин помещика Манилова", Gender.FEMALE)
        self.assertEqual(result, "крестьянка помещика Манилова")

    def test_no_swap_when_gender_matches(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("ясачный крестьянин", Gender.MALE)
        self.assertEqual(result, "ясачный крестьянин")

    def test_no_swap_when_unrecognized(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("помещик", Gender.FEMALE)
        # помещик is detected as male but no swap rule exists for it
        self.assertEqual(result, "помещик")

    def test_none_gender_no_swap(self):
        result = gsi._fix_status_gender("ясачный крестьянин", None)
        self.assertEqual(result, "ясачный крестьянин")

    def test_empty_status(self):
        from verso.ru.gender import Gender
        result = gsi._fix_status_gender("", Gender.FEMALE)
        self.assertEqual(result, "")


class TestDetectStatusGenderCoversAllStatuses(unittest.TestCase):
    """Verify _detect_status_gender recognizes all statuses from statuses.py."""

    def test_all_known_statuses_detected(self):
        from verso.ru.gender import Gender
        from verso.ru.domain import Status
        import verso.ru.domain.statuses as statuses

        missed = []
        for name in dir(statuses):
            obj = getattr(statuses, name)
            if not isinstance(obj, Status):
                continue
            text = str(obj)
            expected = Gender.MALE if obj.gender == Gender.MALE else Gender.FEMALE
            detected = gsi._detect_status_gender(text)
            if detected != expected:
                missed.append(f"{name}: '{text}' — expected {expected}, got {detected}")

        self.assertEqual(missed, [], "Undetected statuses:\n" + "\n".join(missed))


class TestBrideSkipStatuses(unittest.TestCase):
    """Bride status_female should be preserved, not replaced by status_bride."""

    def test_bride_status_female_not_stripped(self):
        """When bride has status_female ('ясачная крестьянка'), it should be
        preserved in the person() call, not stripped and replaced by status_bride."""
        cols = gsi.FORMAT_FAMILIO_STANDARD.marriage_cols
        row = _make_row_cols(cols,
                             RECORD_NUM="1", W_DAY="5",
                             GROOM_NAME="Иван", GROOM_PATR="Петров",
                             BRIDE_NAME="Мария", BRIDE_PATR="Иванова",
                             BRIDE_STATUS="ясачная крестьянка")
        lines = gsi._format_marriage_row(
            row, skip_statuses=frozenset(["ясачный крестьянин", "ясачная крестьянка",
                                          "девка из ясачных крестьян"]),
            bride_skip_statuses=frozenset(["ясачный крестьянин", "девка из ясачных крестьян"]),
            default_village="Горюхино", cols=cols)
        text = "\n".join(lines)
        self.assertIn('status="ясачная крестьянка"', text)

    def test_bride_status_bride_stripped(self):
        """When bride has status_bride ('девка из ясачных крестьян'), it IS stripped."""
        cols = gsi.FORMAT_FAMILIO_STANDARD.marriage_cols
        row = _make_row_cols(cols,
                             RECORD_NUM="1", W_DAY="5",
                             GROOM_NAME="Иван", GROOM_PATR="Петров",
                             BRIDE_NAME="Мария", BRIDE_PATR="Иванова",
                             BRIDE_STATUS="девка из ясачных крестьян")
        lines = gsi._format_marriage_row(
            row, skip_statuses=frozenset(["ясачный крестьянин", "ясачная крестьянка",
                                          "девка из ясачных крестьян"]),
            bride_skip_statuses=frozenset(["ясачный крестьянин", "девка из ясачных крестьян"]),
            default_village="Горюхино", cols=cols)
        text = "\n".join(lines)
        self.assertNotIn('status=', text)


class TestWitnessSurnameColumn(unittest.TestCase):
    """Tests for witness surname from dedicated last_name column."""

    def _text(self, row, **kw):
        cols = gsi.FORMAT_FAMILIO_STANDARD.marriage_cols
        lines = gsi._format_marriage_row(row, cols=cols, **kw)
        return "\n".join(lines)

    def test_w1_surname_from_dedicated_column(self):
        """W1 surname should be read from W1_LAST_NAME column."""
        cols = gsi.FORMAT_FAMILIO_STANDARD.marriage_cols
        row = _make_row_cols(cols,
                             RECORD_NUM="1", W_DAY="5",
                             GROOM_NAME="Петр", GROOM_PATR="Иванов",
                             W1_NAME="Михаил", W1_PATR="Алексеев",
                             W1_LAST_NAME="Сидоров",
                             W1_FIO="Сидоров Михаил Алексеевич")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('last_name_orig="Сидоров"', text)

    def test_w2_surname_from_dedicated_column(self):
        """W2 surname should be read from W2_LAST_NAME column."""
        cols = gsi.FORMAT_FAMILIO_STANDARD.marriage_cols
        row = _make_row_cols(cols,
                             RECORD_NUM="1", W_DAY="5",
                             GROOM_NAME="Петр", GROOM_PATR="Иванов",
                             W2_NAME="Анна", W2_PATR="Илларионова",
                             W2_LAST_NAME="Пеночкина",
                             W2_FIO="Пеночкина Анна Илларионовна")
        text = self._text(row, default_village="Горюхино")
        self.assertIn('last_name_orig="Пеночкина"', text)

    def test_w1_no_surname_when_column_empty(self):
        """No last_name_orig when W1_LAST_NAME is empty."""
        cols = gsi.FORMAT_FAMILIO_STANDARD.marriage_cols
        row = _make_row_cols(cols,
                             RECORD_NUM="1", W_DAY="5",
                             GROOM_NAME="Петр", GROOM_PATR="Иванов",
                             W1_NAME="Семен", W1_PATR="Тихонов",
                             W1_FIO="Семен Тихонов")
        text = self._text(row, default_village="Горюхино")
        # witness1 should not have last_name_orig
        self.assertNotIn('last_name_orig', text.split("witness1=")[1].split(")")[0])


class TestPatrShouldBeLastname(unittest.TestCase):
    """Tests for _patr_should_be_lastname detecting surnames vs patronymics."""

    def test_valid_patr_same_gender_not_lastname(self):
        """Male name + male patronymic → not a lastname."""
        self.assertFalse(gsi._patr_should_be_lastname("Стефан", "Марков"))

    def test_valid_patr_same_gender_standard(self):
        """Male name + male patronymic (standard form) → not a lastname."""
        self.assertFalse(gsi._patr_should_be_lastname("Иван", "Петров"))

    def test_surname_not_canonicalizable(self):
        """Name + non-patronymic string → is a lastname."""
        self.assertTrue(gsi._patr_should_be_lastname("Иван", "Шилохвостов"))

    def test_opposite_gender_patr_valid_swap(self):
        """Female name + male patronymic (swappable) → not a lastname."""
        self.assertFalse(gsi._patr_should_be_lastname("Мария", "Иванов"))

    def test_opposite_gender_patr_no_swap(self):
        """Male name + female non-patronymic → is a lastname."""
        self.assertTrue(gsi._patr_should_be_lastname("Иван", "Шилохвостова"))

    def test_empty_inputs(self):
        self.assertFalse(gsi._patr_should_be_lastname("", "Петров"))
        self.assertFalse(gsi._patr_should_be_lastname("Иван", ""))


if __name__ == "__main__":
    unittest.main()


def test_no_module_imports_gspread_at_import():
    """gspread is the extra [sheets]: the library imports it inside a function only, so a
    module loads without it."""
    import ast

    from tests.codepaths import code_files, module_name

    def module_level(node: ast.AST):
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                yield child
                yield from module_level(child)

    found = [f"{module_name(path)}:{node.lineno}" for path in code_files("verso.core", "verso.ru")
             for node in module_level(ast.parse(path.read_text(encoding="utf-8")))
             if (isinstance(node, ast.Import) and any(a.name.split(".")[0] == "gspread" for a in node.names))
             or (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "gspread")]
    assert found == []
