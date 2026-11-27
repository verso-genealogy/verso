import unittest
from unittest.mock import patch
from verso.ru.gender import Gender
from verso.ru.naming import names_registry
from verso.ru.naming.lexicon import IGNORE_LIST, Layer, NameEntry, PatronymicEntry
from verso.ru.naming import modernize_orthography, canonicalize_name, canonicalize_patronymic, derive_patronymic, get_gender_from_name, get_gender_from_old_patronymic, validate_first_name, validate_old_patronymic, _find_name_in_table, name_from_genitive, degenitivize_patronymic, degenitivize_surname, feminize_surname, find_old_patronymic_by_modern, derive_old_patronymic

def with_ignored(names=None, patronymics=()):
    """The tests' lexicon with a layer on top that lists these names (name → sex) and
    patronymics as the old ignore lists did — substituted for `current_lexicon`."""
    layer = Layer("test", {(sex, n): NameEntry(sex, n, source=IGNORE_LIST) for n, sex in (names or {}).items()}, {},
                  {(None, p): PatronymicEntry(None, p) for p in patronymics})
    lexicon = names_registry.current_lexicon().with_layer(layer)
    return patch.object(names_registry, 'current_lexicon', lambda: lexicon)


class TestNamingUtils(unittest.TestCase):

    def test_modernize_orthography(self):
        # Basic character replacements
        self.assertEqual(modernize_orthography("Сергѣй"), "Сергей")
        self.assertEqual(modernize_orthography("Дементій"), "Дементий")
        self.assertEqual(modernize_orthography("Өедоръ"), "Федор")
        self.assertEqual(modernize_orthography("ѵпатовъ"), "ипатов")
        self.assertEqual(modernize_orthography("Алеѯандръ"), "Александр")
        self.assertEqual(modernize_orthography("Алеѯѣй"), "Алексей")

        # Trailing 'ъ'
        self.assertEqual(modernize_orthography("Ивановъ"), "Иванов")
        self.assertEqual(modernize_orthography("Петровъ,"), "Петров,")
        self.assertEqual(modernize_orthography("Сидоровъ."), "Сидоров.")
        # ...before a doubtful reading's «?» (В19)
        self.assertEqual(modernize_orthography("Маруговъ?"), "Маругов?")
        self.assertEqual(modernize_orthography("Ѳедоръ??"), "Федор??")
        self.assertEqual(modernize_orthography("Ѳедоръ? Алексѣевъ?"), "Федор? Алексеев?")

        # Combined
        self.assertEqual(modernize_orthography("Ѳедоръ Алексѣевъ"), "Федор Алексеев")

        # Case preservation
        self.assertEqual(modernize_orthography("ІОАННЪ"), "ИОАНН")

    def test_canonicalize_name(self):
        # Name variants with Имя-основа return the base form
        self.assertEqual(canonicalize_name("Абакум"), "Аввакум")  # Имя-основа column has "Аввакум"

        # Name variants (with Имя-основа) return the canonical base form
        self.assertEqual(canonicalize_name("Авдотья"), "Евдокия")  # variant of Евдокия
        self.assertEqual(canonicalize_name("Агрепина"), "Агрипина")  # variant of Агрипина

        # Names that are already canonical (in Имя column) return themselves
        self.assertEqual(canonicalize_name("Иоанн"), "Иоанн")
        self.assertEqual(canonicalize_name("Мария"), "Мария")
        self.assertEqual(canonicalize_name("Августа"), "Августа")

        # Names not in table return as-is
        self.assertEqual(canonicalize_name("НесуществующееИмя"), "НесуществующееИмя")

        # Placeholders
        self.assertEqual(canonicalize_name("?"), "?")
        self.assertEqual(canonicalize_name(""), "")

    def test_canonicalize_patronymic(self):
        # Male - auto-detects gender from endings, uses names.csv table for conversion
        self.assertEqual(canonicalize_patronymic("Иванов"), "Иванович")
        self.assertEqual(canonicalize_patronymic("Сергеев"), "Сергеевич")
        self.assertEqual(canonicalize_patronymic("Никитин"), "Никитич")  # from table
        self.assertEqual(canonicalize_patronymic("Иванович"), "Иванович")  # already canonical

        # Female - auto-detects gender from endings, uses names.csv table for conversion
        self.assertEqual(canonicalize_patronymic("Иванова"), "Ивановна")
        self.assertEqual(canonicalize_patronymic("Сергеева"), "Сергеевна")
        self.assertEqual(canonicalize_patronymic("Никитина"), "Никитична")  # from table
        self.assertEqual(canonicalize_patronymic("Ивановна"), "Ивановна")  # already canonical

    def test_canonicalize_patronymic_not_found_raises_error(self):
        """Should raise ValueError for unrecognized patronymics (old form)"""
        # Use old form ending that doesn't exist in names table
        with self.assertRaises(ValueError) as ctx:
            canonicalize_patronymic("Фиктивов")  # Old form "-ов" not in table
        self.assertIn("Cannot canonicalize patronymic", str(ctx.exception))
        self.assertIn("not found in names table", str(ctx.exception))

    def test_canonicalize_full_form_patronymic_via_stamm(self):
        # A full «-ович/-евич» form (gwar WWI / noble records) resolves through
        # its stamm (the father's short patronymic) to the registered canonical,
        # exactly as the short input would: the base keeps the patronymic of
        # Абрам as «Абрамович» (it is a name of its own, folded onto Авраам as a
        # given name alone), the short «Абрамов» gives the same.
        self.assertEqual(canonicalize_patronymic("Абрамович"), "Абрамович")
        self.assertEqual(canonicalize_patronymic("Абрамович"),
                         canonicalize_patronymic("Абрамов"))  # same as short form
        self.assertEqual(canonicalize_patronymic("Николаевич"), "Николаевич")
        self.assertEqual(canonicalize_patronymic("Тимофеевич"), "Тимофеевич")

    def test_canonicalize_patronymic_of_the_ignore_list_is_algorithmic(self):
        """A patronymic patronymics_ignore.csv lists skips the table lookup (the list, not a
        word in the code)."""
        with with_ignored(patronymics=['Плутоватов']):
            self.assertEqual("Плутоватович", canonicalize_patronymic("Плутоватов"))
        with self.assertRaises(ValueError):
            canonicalize_patronymic("Плутоватов")

    def test_canonicalize_patronymic_none_input(self):
        """Should return empty string for None input"""
        self.assertEqual("", canonicalize_patronymic(None))

    def test_canonicalize_patronymic_placeholder(self):
        """Should return placeholder as-is"""
        self.assertEqual("?", canonicalize_patronymic("?"))

    def test_modernize_orthography_none_input(self):
        """Should return empty string for None input"""
        self.assertEqual("", modernize_orthography(None))

    def test_modernize_orthography_empty_string(self):
        """Should return empty string for empty input"""
        self.assertEqual("", modernize_orthography(""))

    def test_modernize_orthography_barred_o(self):
        """Should convert barred O (Ө) lookalike for Fita"""
        self.assertEqual("Федор", modernize_orthography("Өедоръ"))

    def test_modernize_orthography_multiple_consecutive(self):
        """Should handle multiple consecutive old characters"""
        self.assertEqual("еи", modernize_orthography("ѣі"))

    def test_derive_patronymic(self):
        # Male child - uses names.csv table
        self.assertEqual(derive_patronymic("Иван", Gender.MALE), "Иванович")
        self.assertEqual(derive_patronymic("Савва", Gender.MALE), "Саввич")
        self.assertEqual(derive_patronymic("Никита", Gender.MALE), "Никитич")
        self.assertEqual(derive_patronymic("Сергей", Gender.MALE), "Сергеевич")
        self.assertEqual(derive_patronymic("Илья", Gender.MALE), "Ильич")

        # Female child - uses names.csv table
        self.assertEqual(derive_patronymic("Иван", Gender.FEMALE), "Ивановна")
        self.assertEqual(derive_patronymic("Савва", Gender.FEMALE), "Саввична")  # from table (not Саввишна)
        self.assertEqual(derive_patronymic("Никита", Gender.FEMALE), "Никитична")
        self.assertEqual(derive_patronymic("Сергей", Gender.FEMALE), "Сергеевна")
        self.assertEqual(derive_patronymic("Илья", Gender.FEMALE), "Ильинична")

        # Placeholders
        self.assertEqual(derive_patronymic("?", Gender.MALE), "?")

    def test_get_gender_from_name(self):
        # Male names - search in Имя column
        self.assertEqual(get_gender_from_name("Иван"), Gender.MALE)
        self.assertEqual(get_gender_from_name("Петр"), Gender.MALE)
        self.assertEqual(get_gender_from_name("Сергей"), Gender.MALE)

        # Female names - search in Имя column
        self.assertEqual(get_gender_from_name("Мария"), Gender.FEMALE)
        self.assertEqual(get_gender_from_name("Анна"), Gender.FEMALE)
        self.assertEqual(get_gender_from_name("Екатерина"), Gender.FEMALE)

        # Variant names are now independent records with Имя-основа
        self.assertEqual(get_gender_from_name("Арон"), Gender.MALE)  # variant of Аарон

        # Not found
        self.assertIsNone(get_gender_from_name("НесуществующееИмя"))

        # Placeholders
        self.assertIsNone(get_gender_from_name("?"))
        self.assertIsNone(get_gender_from_name(""))

class TestGenderDetection(unittest.TestCase):
    """Test gender detection from patronymics"""

    def test_get_gender_from_old_patronymic_male(self):
        """Should detect male from old-form patronymics"""
        # Test known male patronymics
        self.assertEqual(Gender.MALE, get_gender_from_old_patronymic("Иванов"))
        self.assertEqual(Gender.MALE, get_gender_from_old_patronymic("Петров"))
        self.assertEqual(Gender.MALE, get_gender_from_old_patronymic("Сергеев"))

    def test_get_gender_from_old_patronymic_female(self):
        """Should detect female from old-form patronymics"""
        # Test known female patronymics
        self.assertEqual(Gender.FEMALE, get_gender_from_old_patronymic("Иванова"))
        self.assertEqual(Gender.FEMALE, get_gender_from_old_patronymic("Петрова"))
        self.assertEqual(Gender.FEMALE, get_gender_from_old_patronymic("Сергеева"))

    def test_get_gender_from_old_patronymic_not_found(self):
        """Should return None for unrecognized patronymics"""
        self.assertIsNone(get_gender_from_old_patronymic("НеизвестноеОтчество"))

    def test_get_gender_from_old_patronymic_placeholder(self):
        """Should return None for placeholder patronymics"""
        self.assertIsNone(get_gender_from_old_patronymic("?"))

    def test_get_gender_from_old_patronymic_empty(self):
        """Should return None for empty/None input"""
        self.assertIsNone(get_gender_from_old_patronymic(""))
        self.assertIsNone(get_gender_from_old_patronymic(None))


class TestFindNameInTable(unittest.TestCase):

    def test_returns_empty_list_for_unknown_name(self):
        self.assertEqual(_find_name_in_table("НесуществующееИмя"), [])

    def test_returns_empty_list_for_empty_input(self):
        self.assertEqual(_find_name_in_table(""), [])

    def test_returns_list_for_unambiguous_name(self):
        entries = _find_name_in_table("Иван")
        self.assertIsInstance(entries, list)
        self.assertEqual(len(entries), 1)
        self.assertIs(entries[0].sex, Gender.MALE)

    def test_returns_multiple_rows_for_ambiguous_name(self):
        # "Лука" exists as both male and female in the names table
        entries = _find_name_in_table("Лука")
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 1)
        self.assertEqual({e.sex for e in entries}, {Gender.MALE, Gender.FEMALE})


class TestGetGenderFromNameAmbiguity(unittest.TestCase):

    def test_returns_none_for_ambiguous_name(self):
        # "Лука" exists as both male and female — gender cannot be determined
        self.assertIsNone(get_gender_from_name("Лука"))

    def test_returns_gender_for_unambiguous_male(self):
        self.assertEqual(get_gender_from_name("Иван"), Gender.MALE)

    def test_returns_gender_for_unambiguous_female(self):
        self.assertEqual(get_gender_from_name("Мария"), Gender.FEMALE)


class TestCanonicalizeNameWithGender(unittest.TestCase):

    def test_male_gender_returns_male_canonical(self):
        # "Лука" male has no Имя-основа, so returns "Лука" itself
        self.assertEqual(canonicalize_name("Лука", Gender.MALE), "Лука")

    def test_female_gender_returns_female_canonical(self):
        # "Лука" female has Имя-основа = "Гликерия"
        self.assertEqual(canonicalize_name("Лука", Gender.FEMALE), "Гликерия")

    def test_no_gender_prefers_canonical_row(self):
        # Without gender, prefer the row where the name is already canonical
        # (empty Имя-основа) over one that maps to a different name
        self.assertEqual(canonicalize_name("Лука"), "Лука")

    def test_gender_filter_unambiguous_name(self):
        # For names with only one gender, the result is the same with or without gender
        self.assertEqual(canonicalize_name("Иван", Gender.MALE), "Иоанн")
        self.assertEqual(canonicalize_name("Иван"), "Иоанн")

    def test_gender_filter_no_matching_row_falls_back_to_name(self):
        # Passing the wrong gender for a name that only exists in the opposite gender
        # yields no matching rows → falls back to returning the name as-is
        self.assertEqual(canonicalize_name("Иван", Gender.FEMALE), "Иван")

    def test_none_gender_behaves_same_as_no_gender(self):
        self.assertEqual(canonicalize_name("Иван", None), canonicalize_name("Иван"))


class TestValidation(unittest.TestCase):
    """Test name and patronymic validation"""

    def test_validate_first_name_valid(self):
        """Should return True for names in table"""
        self.assertTrue(validate_first_name("Иван"))
        self.assertTrue(validate_first_name("Мария"))
        self.assertTrue(validate_first_name("Петр"))

    def test_validate_first_name_invalid(self):
        """Should return False for names not in table"""
        self.assertFalse(validate_first_name("ФиктивноеИмя"))

    def test_validate_first_name_placeholder(self):
        """Should return True for placeholder values"""
        self.assertTrue(validate_first_name("?"))

    def test_validate_first_name_empty(self):
        """Should return True for empty/None (special case)"""
        self.assertTrue(validate_first_name(""))
        self.assertTrue(validate_first_name(None))

    def test_validate_old_patronymic_valid(self):
        """Should return True for patronymics in table"""
        self.assertTrue(validate_old_patronymic("Иванов"))
        self.assertTrue(validate_old_patronymic("Иванова"))
        self.assertTrue(validate_old_patronymic("Петров"))
        self.assertTrue(validate_old_patronymic("Петрова"))

    def test_validate_old_patronymic_invalid(self):
        """Should return False for patronymics not in table"""
        self.assertFalse(validate_old_patronymic("Фиктивович"))

    def test_validate_old_patronymic_full_form(self):
        """Full «-ович/-евич» forms validate with accept_full=True when their
        stamm is registered; the default stays strict (short-only)."""
        self.assertTrue(validate_old_patronymic("Абрамович", accept_full=True))
        self.assertTrue(validate_old_patronymic("Давидович", accept_full=True))
        self.assertTrue(validate_old_patronymic("Николаевич", accept_full=True))
        self.assertTrue(validate_old_patronymic("Тимофеевич", accept_full=True))
        # Default (importer) stays strict — full forms rejected.
        self.assertFalse(validate_old_patronymic("Абрамович"))
        # An unmapped stamm stays invalid even with accept_full (typos surface).
        self.assertFalse(validate_old_patronymic("Хрюнделевич", accept_full=True))

    def test_get_gender_from_full_form_patronymic(self):
        """Gender inference resolves a full «-ович» form via its stamm."""
        self.assertEqual(Gender.MALE, get_gender_from_old_patronymic("Абрамович"))
        self.assertEqual(Gender.MALE, get_gender_from_old_patronymic("Николаевич"))

    def test_validate_old_patronymic_placeholder(self):
        """Should return True for placeholder values"""
        self.assertTrue(validate_old_patronymic("?"))

    def test_validate_old_patronymic_empty(self):
        """Should return True for empty/None (special case)"""
        self.assertTrue(validate_old_patronymic(""))
        self.assertTrue(validate_old_patronymic(None))


class TestNamesIgnoreList(unittest.TestCase):
    """Tests for names_ignore.csv integration (Шумила is the live fixture in that file)."""

    def test_validate_first_name_accepts_ignored_name(self):
        """Name in ignore list passes validation even if absent from names.csv."""
        self.assertTrue(validate_first_name("Шумила"))

    def test_validate_first_name_rejects_name_absent_from_both(self):
        """Name absent from both names.csv and ignore list still fails."""
        self.assertFalse(validate_first_name("АбсолютноФиктивноеИмя"))

    def test_get_gender_from_name_returns_male_for_ignored_male_name(self):
        """Gender М in ignore list is returned as MALE."""
        with with_ignored({'ТестМуж': Gender.MALE}):
            self.assertEqual(get_gender_from_name('ТестМуж'), Gender.MALE)

    def test_get_gender_from_name_returns_female_for_ignored_female_name(self):
        """Gender Ж in ignore list is returned as FEMALE."""
        with with_ignored({'ТестЖен': Gender.FEMALE}):
            self.assertEqual(get_gender_from_name('ТестЖен'), Gender.FEMALE)

    def test_get_gender_from_name_returns_none_for_ignored_name_without_gender(self):
        """Ignore-list entry with no gender yields None (suppresses gender-mismatch checks)."""
        with with_ignored({'ТестБезПола': None}):
            self.assertIsNone(get_gender_from_name('ТестБезПола'))

    def test_ignored_name_takes_precedence_over_names_table(self):
        """When a name appears in both the ignore list and names.csv, ignore-list gender wins."""
        # Иван is male in names.csv; patch ignore list to claim it is female
        with with_ignored({'Иван': Gender.FEMALE}):
            self.assertEqual(get_gender_from_name('Иван'), Gender.FEMALE)


class TestPartialIllegibility(unittest.TestCase):
    """Names/patronymics with embedded '?' (partially unreadable characters)."""

    def test_validate_first_name_partial(self):
        self.assertTrue(validate_first_name("Федо?"))
        self.assertTrue(validate_first_name("Алекс?й"))

    def test_validate_old_patronymic_partial(self):
        self.assertTrue(validate_old_patronymic("Иванов?"))
        self.assertTrue(validate_old_patronymic("?ванова"))

    def test_canonicalize_name_partial_returns_asis(self):
        self.assertEqual(canonicalize_name("Федо?"), "Федо?")

    def test_canonicalize_patronymic_partial_returns_asis(self):
        self.assertEqual(canonicalize_patronymic("Иванов?"), "Иванов?")
        self.assertEqual(canonicalize_patronymic("Федо?ов"), "Федо?ов")

    def test_get_gender_from_name_partial_returns_none(self):
        self.assertIsNone(get_gender_from_name("Федо?"))

    def test_derive_patronymic_partial_name_returns_question(self):
        self.assertEqual(derive_patronymic("Федо?", Gender.MALE), "?")
        self.assertEqual(derive_patronymic("Федо?", Gender.FEMALE), "?")


class TestGenitiveConversions(unittest.TestCase):
    """Tests for genitive-to-nominative conversion functions."""

    def test_name_from_genitive_known(self):
        # "Павла" is the genitive of "Павел" in names.csv
        self.assertEqual(name_from_genitive("Павла"), "Павел")

    def test_name_from_genitive_ivan(self):
        # "Ивана" is the genitive of "Иван"
        self.assertEqual(name_from_genitive("Ивана"), "Иван")

    def test_name_from_genitive_vasily(self):
        # "Василия" is the genitive of "Василий"
        self.assertEqual(name_from_genitive("Василия"), "Василий")

    def test_name_from_genitive_ioann(self):
        # "Иоанна" is the genitive of "Иоанн"
        self.assertEqual(name_from_genitive("Иоанна"), "Иоанн")

    def test_name_from_genitive_not_found(self):
        self.assertIsNone(name_from_genitive("НесуществующееИмяВРодительном"))

    def test_name_from_genitive_empty(self):
        self.assertIsNone(name_from_genitive(""))

    def test_degenitivize_patronymic_ioannova(self):
        self.assertEqual(degenitivize_patronymic("Иоаннова"), "Иоаннов")

    def test_degenitivize_patronymic_semenova(self):
        self.assertEqual(degenitivize_patronymic("Семенова"), "Семенов")

    def test_degenitivize_patronymic_ivanova(self):
        self.assertEqual(degenitivize_patronymic("Иванова"), "Иванов")

    def test_degenitivize_patronymic_no_trailing_a(self):
        # If no trailing 'а', return as-is
        self.assertEqual(degenitivize_patronymic("Иванов"), "Иванов")

    def test_degenitivize_patronymic_empty(self):
        self.assertEqual(degenitivize_patronymic(""), "")

    def test_degenitivize_surname_indjushev(self):
        self.assertEqual(degenitivize_surname("Индюшева"), "Индюшев")

    def test_degenitivize_surname_ljapkin(self):
        self.assertEqual(degenitivize_surname("Ляпкина"), "Ляпкин")

    def test_degenitivize_surname_oy_ending(self):
        # Genitive ending -ой (e.g. "Лагутиной" adj-form)
        self.assertEqual(degenitivize_surname("Лагутиной"), "Лагутин")

    def test_degenitivize_surname_no_change(self):
        # Surname not ending in 'а' or 'ой' — return as-is
        self.assertEqual(degenitivize_surname("Индюшев"), "Индюшев")

    def test_degenitivize_surname_empty(self):
        self.assertEqual(degenitivize_surname(""), "")


class TestFindOldPatronymicByModern(unittest.TestCase):
    """Tests for reverse lookup: modern patronymic → old form."""

    def test_kuzmich_male(self):
        result = find_old_patronymic_by_modern("Кузьмич")
        self.assertIsNotNone(result)
        # Should return one of the old forms (Казьмин, Козьмин, etc.)
        self.assertTrue(result.endswith("ин"), f"Expected old male form ending in -ин, got '{result}'")

    def test_kuzminichna_female(self):
        result = find_old_patronymic_by_modern("Кузьминична")
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("ина"), f"Expected old female form ending in -ина, got '{result}'")

    def test_stepanovich(self):
        self.assertEqual(find_old_patronymic_by_modern("Степанович"), "Степанов")

    def test_nikitich(self):
        self.assertEqual(find_old_patronymic_by_modern("Никитич"), "Никитин")

    def test_ivanovich(self):
        self.assertEqual(find_old_patronymic_by_modern("Иванович"), "Иванов")

    def test_ivanova(self):
        self.assertEqual(find_old_patronymic_by_modern("Ивановна"), "Иванова")

    def test_unknown_returns_none(self):
        self.assertIsNone(find_old_patronymic_by_modern("НесуществующееОтчество"))

    def test_empty_returns_none(self):
        self.assertIsNone(find_old_patronymic_by_modern(""))
        self.assertIsNone(find_old_patronymic_by_modern(None))


class TestPatronymicsIgnore(unittest.TestCase):
    """Tests for the patronymics_ignore.csv mechanism: legitimate-but-non-dictionary patronymics
    (Mordva/regional, pre-reform variants, modern-in-old slot, genitive forms) must pass
    validation AND canonicalize without raising, falling through to algorithmic conversion."""

    def test_validate_accepts_ignore_list_entry(self):
        """validate_old_patronymic returns True for Шумилов (not in names.csv)."""
        self.assertTrue(validate_old_patronymic("Шумилов"))

    def test_validate_accepts_volodimirov_prerefrom_variant(self):
        """Pre-reform Володимиров passes validation via ignore list."""
        self.assertTrue(validate_old_patronymic("Володимиров"))

    def test_validate_rejects_modern_form_not_in_ignore_list(self):
        """Modern canonical forms are NOT accepted by default — the importer
        pipeline relies on this strictness to flag DSL/CSV authoring errors."""
        self.assertFalse(validate_old_patronymic("Ивановна"))
        self.assertFalse(validate_old_patronymic("Иванович"))

    def test_validate_accepts_full_form_with_accept_full(self):
        """With accept_full=True (hand-authored DSL: Person / names linter) a full
        «-ович/-евна» form whose stamm is registered validates — gwar WWI / noble
        records keep it verbatim. An UNKNOWN stamm still rejects (typos surface)."""
        self.assertTrue(validate_old_patronymic("Иванович", accept_full=True))
        self.assertTrue(validate_old_patronymic("Ивановна", accept_full=True))
        self.assertFalse(validate_old_patronymic("Фиктивович", accept_full=True))

    def test_canonicalize_ignore_list_entry_uses_algorithmic_fallback(self):
        """canonicalize_patronymic('Шумилов') returns 'Шумилович' via -ов + ич fallback."""
        self.assertEqual(canonicalize_patronymic("Шумилов"), "Шумилович")

    def test_canonicalize_ignore_list_female_entry(self):
        """canonicalize_patronymic('Пасмурова') returns 'Пасмуровна' via -ова → -овна fallback."""
        self.assertEqual(canonicalize_patronymic("Пасмурова"), "Пасмуровна")

    def test_unknown_patronymic_still_raises(self):
        """A patronymic NOT in ignore list still raises (preserves strictness for new records)."""
        with self.assertRaises(ValueError):
            canonicalize_patronymic("НесуществующееОтчество")


class TestDeriveOldPatronymic(unittest.TestCase):
    """Tests for derive_old_patronymic: direct old-form from father's name row."""

    def test_folk_form_gavril(self):
        """Гаврил → Гаврилов (not Гавриилов from canonical Гавриил row)."""
        self.assertEqual(derive_old_patronymic("Гаврил", Gender.MALE), "Гаврилов")

    def test_canonical_form_gavriil(self):
        """Гавриил → Гавриилов."""
        self.assertEqual(derive_old_patronymic("Гавриил", Gender.MALE), "Гавриилов")

    def test_female_emelyan(self):
        """Емельян + female → correct female old-form."""
        result = derive_old_patronymic("Емельян", Gender.FEMALE)
        self.assertTrue(result.endswith("а"), f"Expected female old-form ending in -а, got '{result}'")

    def test_kozma(self):
        """Козма → Козмин (not Казьмин from canonical Кузьма row)."""
        self.assertEqual(derive_old_patronymic("Козма", Gender.MALE), "Козмин")

    def test_empty_name(self):
        self.assertEqual(derive_old_patronymic("", Gender.MALE), "")
        self.assertEqual(derive_old_patronymic(None, Gender.MALE), "")

    def test_question_mark(self):
        self.assertEqual(derive_old_patronymic("Иван?", Gender.MALE), "")


class TestFeminizeSurname(unittest.TestCase):
    """Russian masculine → feminine surname transform. Used by
    Birth.__init__ when a daughter inherits her father's surname."""

    def test_ov_ending(self):
        self.assertEqual(feminize_surname("Иванов"), "Иванова")
        self.assertEqual(feminize_surname("Лавочников"), "Лавочникова")

    def test_ev_ending(self):
        self.assertEqual(feminize_surname("Яковлев"), "Яковлева")
        self.assertEqual(feminize_surname("Сергеев"), "Сергеева")

    def test_in_ending(self):
        self.assertEqual(feminize_surname("Обмишулин"), "Обмишулина")
        self.assertEqual(feminize_surname("Никчемушкин"), "Никчемушкина")

    def test_skiy_ending(self):
        self.assertEqual(feminize_surname("Достоевский"), "Достоевская")

    def test_tskiy_ending(self):
        self.assertEqual(feminize_surname("Высоцкий"), "Высоцкая")

    def test_oy_adjectival_ending(self):
        # Adjectival surnames ending in -ой take feminine -ая.
        self.assertEqual(feminize_surname("Кривой"), "Кривая")
        self.assertEqual(feminize_surname("Толстой"), "Толстая")

    def test_non_matching_returned_unchanged(self):
        # Already-feminine or non-standard: no transform.
        self.assertEqual(feminize_surname("Иванова"), "Иванова")
        self.assertEqual(feminize_surname("Смит"), "Смит")

    def test_empty_returned_unchanged(self):
        self.assertEqual(feminize_surname(""), "")
        self.assertEqual(feminize_surname(None), None)


if __name__ == '__main__':
    unittest.main()


class TestDoubtfulReadingModernized(unittest.TestCase):
    def test_person_fields_drop_the_hard_sign_before_the_question_mark(self):
        """A doubtful reading keeps its «?» and loses its ъ in the modern fields (В19)."""
        from verso.ru.domain import Person
        p = Person("Ѳедоръ", patr_orig="Петровъ", last_name="Свиристеловъ?", gender=Gender.MALE)
        self.assertEqual(p.last_name_modern, "Свиристелов?")
        self.assertEqual(p.name_modern, "Федор")
