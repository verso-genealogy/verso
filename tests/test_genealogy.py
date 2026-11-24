import unittest

from verso.ru.dsl.records.births import Birth, birth_month_year
from verso.ru.dsl.records.deaths import Death, death_month_year
from verso.ru.gender import Gender
from verso.ru.domain import EventDate, Person, RecordDefaults, Status, person, page, book
from verso.ru.dsl.records.marriages import Marriage, marriage_month_year
from verso.ru.relationship import Relative


class TestGenealogy(unittest.TestCase):

    def test_person_canonical_patronymic_male(self):
        # Standard -ov/-ev -> -ович/-евич
        p1 = Person("Иванъ", "Ивановъ", name_modern_orth="Иван", patr_old="Иванов", gender=Gender.MALE)
        self.assertEqual(p1.patr_modern, "Иванович")
        p2 = Person("Сергѣй", "Васильевъ", name_modern_orth="Сергей", patr_old="Васильев", gender=Gender.MALE)
        self.assertEqual(p2.patr_modern, "Васильевич")

        # -in converted via table (Никитин -> Никитич)
        p3 = Person("Яковъ", "Никитинъ", name_modern_orth="Яков", patr_old="Никитин", gender=Gender.MALE)
        self.assertEqual(p3.patr_modern, "Никитич")

        # Already canonical - use old form "Петровъ" which converts to "Петрович"
        p4 = Person("Петръ", "Петровъ", name_modern_orth="Петр", patr_old="Петров", gender=Gender.MALE)
        self.assertEqual(p4.patr_modern, "Петрович")

        # Placeholders
        p5 = Person("", "?", name_modern_orth="", patr_old="?", gender=Gender.MALE)
        self.assertEqual(p5.patr_modern, "?")

    def test_person_canonical_patronymic_female(self):
        # Standard -ova/-eva -> -овна/-евна
        p1 = Person("Анна", "Иванова", name_modern_orth="Анна", patr_old="Иванова", gender=Gender.FEMALE)
        self.assertEqual(p1.patr_modern, "Ивановна")
        p2 = Person("Марія", "Сергѣева", name_modern_orth="Мария", patr_old="Сергеева", gender=Gender.FEMALE)
        self.assertEqual(p2.patr_modern, "Сергеевна")

        # -ina converted via table (Никитина -> Никитична)
        p3 = Person("Дарья", "Никитина", name_modern_orth="Дарья", patr_old="Никитина", gender=Gender.FEMALE)
        self.assertEqual(p3.patr_modern, "Никитична")

        # Already canonical - use old form "Петрова" which converts to "Петровна"
        p4 = Person("Елена", "Петрова", name_modern_orth="Елена", patr_old="Петрова", gender=Gender.FEMALE)
        self.assertEqual(p4.patr_modern, "Петровна")

    def test_person_dsl_helper(self):
        # Basic usage with valid name
        p = person("Іванъ", name_modern_orth="Иван")
        self.assertIsInstance(p, Person)
        self.assertEqual(p.name_orig, "Іванъ")
        self.assertEqual(p.name_modern, "Иван")

        # With all parameters using placeholders and valid names
        p2 = person("?", patr_orig="?", last_name_orig="LN", name_modern_orth="?", patr_old="?", residence="R", status="S")
        self.assertIsInstance(p2, Person)
        self.assertEqual(p2.name_orig, "?")
        self.assertEqual(p2.name_modern, "?")
        self.assertEqual(p2.patr_orig, "?")
        self.assertEqual(p2.patr_modern, "?")
        self.assertEqual(p2.last_name, "LN")
        self.assertEqual(p2.residence, "R")
        self.assertEqual(p2.status, "S")

    def test_person_auto_modernize_orthography(self):
        # Name only - auto-modernizes
        p1 = person("Дементій")
        self.assertEqual(p1.name_orig, "Дементій")
        self.assertEqual(p1.name_modern, "Дементий")

        # Name with patronymic - both auto-modernize
        p2 = person("Петръ", patr_orig="Сидоровъ")
        self.assertEqual(p2.name_orig, "Петръ")
        self.assertEqual(p2.name_modern, "Петр")
        self.assertEqual(p2.patr_orig, "Сидоровъ")
        self.assertEqual(p2.patr_old, "Сидоров")
        self.assertEqual(p2.patr_modern, "Сидорович")

        # Explicit name_modern overrides auto-modernization
        p3 = person("Ѳедоръ", name_modern_orth="Фёдор")
        self.assertEqual(p3.name_orig, "Ѳедоръ")
        self.assertEqual(p3.name_modern, "Фёдор")  # custom, not "Федор"

        # With all fields including residence and status
        p4 = person("Іоаннъ", patr_orig="Алексѣевъ", residence="Заманиловка", status="крестьянин")
        self.assertEqual(p4.name_modern, "Иоанн")
        self.assertEqual(p4.patr_old, "Алексеев")
        self.assertEqual(p4.patr_modern, "Алексеевич")
        self.assertEqual(p4.residence, "Заманиловка")
        self.assertEqual(p4.status, "крестьянин")

    def test_page_function_with_birth_records(self):
        # Create Birth records without page numbers
        child = Person("Иван", name_modern_orth="Иван")
        father = Person("Петр", name_modern_orth="Петр")
        mother = Person("Мария", name_modern_orth="Мария")

        child_female = Person("Анна", name_modern_orth="Анна")
        b1 = Birth(1, Gender.MALE, 1, 2, 1, 1, child, father, mother, None, None)
        b2 = Birth(2, Gender.FEMALE, 3, 4, 2, 2, child_female, father, mother, None, None)

        # Initially, page should be None
        self.assertIsNone(b1.page)
        self.assertIsNone(b2.page)

        # Apply page number using page() function - returns deep copies
        result = page("123", b1, b2)

        # Check that originals are unchanged
        self.assertIsNone(b1.page)
        self.assertIsNone(b2.page)

        # Check that result is a list of copies with page numbers set
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].page, "123")
        self.assertEqual(result[1].page, "123")
        self.assertIsNot(result[0], b1)
        self.assertIsNot(result[1], b2)

    def test_page_function_with_marriage_records(self):
        # Create Marriage records without page numbers
        groom = Person("Иван", name_modern_orth="Иван")
        bride = Person("Анна", name_modern_orth="Анна")

        m1 = Marriage(1, 5, 6, groom, bride)
        m2 = Marriage(2, 7, 8, groom, bride)

        # Initially, page should be None
        self.assertIsNone(m1.page)
        self.assertIsNone(m2.page)

        # Apply page number using page() function - returns deep copies
        result = page("456", m1, m2)

        # Check that originals are unchanged
        self.assertIsNone(m1.page)
        self.assertIsNone(m2.page)

        # Check that result is a list of copies with page numbers set
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].page, "456")
        self.assertEqual(result[1].page, "456")
        self.assertIsNot(result[0], m1)
        self.assertIsNot(result[1], m2)

    def test_page_function_with_death_records(self):
        # Create Death records without page numbers
        deceased = Person("Петр", name_modern_orth="Петр")
        relative = Person("Иван", name_modern_orth="Иван")

        deceased_female = Person("Мария", name_modern_orth="Мария")
        d1 = Death(1, Gender.MALE, 10, 12, 5, 5, deceased, relatives=[Relative(relative, None)], witness1=None, witness2=None)
        d2 = Death(2, Gender.FEMALE, 15, 17, 6, 6, deceased_female, relatives=[Relative(relative, None)], witness1=None, witness2=None)

        # Initially, page should be None
        self.assertIsNone(d1.page)
        self.assertIsNone(d2.page)

        # Apply page number using page() function - returns deep copies
        result = page("789", d1, d2)

        # Check that originals are unchanged
        self.assertIsNone(d1.page)
        self.assertIsNone(d2.page)

        # Check that result is a list of copies with page numbers set
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].page, "789")
        self.assertEqual(result[1].page, "789")
        self.assertIsNot(result[0], d1)
        self.assertIsNot(result[1], d2)

    def test_page_function_with_single_record(self):
        # Test with a single Birth record
        child = Person("Иван", name_modern_orth="Иван")
        b = Birth(1, Gender.MALE, 1, 2, 1, 1, child, None, None, None, None)

        result = page("42", b)

        # Check original is unchanged
        self.assertIsNone(b.page)

        # Check result is a copy with page set
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].page, "42")
        self.assertIsNot(result[0], b)

    def test_page_function_preserves_existing_page(self):
        # Test that page() does NOT overwrite existing page numbers
        child = Person("Иван", name_modern_orth="Иван")
        b = Birth(1, Gender.MALE, 1, 2, 1, 1, child, None, None, None, None, page="old_page")

        self.assertEqual(b.page, "old_page")

        result = page("new_page", b)

        # Original unchanged
        self.assertEqual(b.page, "old_page")

        # Copy preserves the old page (does not overwrite)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0].page, "old_page")
        self.assertIsNot(result[0], b)

    def test_page_function_with_complex_page_numbers(self):
        # Test with various page number formats (strings with ranges, etc.)
        child = Person("Иван", name_modern_orth="Иван")
        b1 = Birth(1, Gender.MALE, 1, 2, 1, 1, child, None, None, None, None)
        b2 = Birth(2, Gender.MALE, 1, 2, 1, 1, child, None, None, None, None)

        # Test with page range
        result1 = page("123-124", b1)
        self.assertIsNone(b1.page)  # Original unchanged
        self.assertEqual(result1[0].page, "123-124")

        # Test with page with verso/recto
        result2 = page("50об", b2)
        self.assertIsNone(b2.page)  # Original unchanged
        self.assertEqual(result2[0].page, "50об")

    def test_person_get_fio(self):
        """Test get_fio() method with various combinations of surname, name, and patronymic."""

        # Test 1: Complete FIO (surname + name + patronymic)
        p1 = person("Василий", "Ивановъ", last_name_orig="Болтуновъ")
        self.assertEqual(p1.get_fio(), "Болтунов Василий Иванович")

        # Test 2: No surname (name + patronymic only)
        p2 = person("Иванъ", "Петровъ")
        self.assertEqual(p2.get_fio(), "Иоанн Петрович")

        # Test 3: No patronymic (surname + name only)
        p3 = person("Петръ", last_name_orig="Чичиковъ")
        self.assertEqual(p3.get_fio(), "Чичиков Петр")

        # Test 4: Only name (no surname, no patronymic)
        p4 = person("Марія")
        self.assertEqual(p4.get_fio(), "Мария")

        # Test 5: Empty strings
        p5 = Person("", "", last_name="", name_modern_orth="", patr_old="")
        self.assertEqual(p5.get_fio(), "")

        # Test 6: Explicit None values
        p6 = Person("Иванъ", patr_orig=None, last_name="Смиренниковъ", name_modern_orth="Иван", patr_old=None)
        self.assertEqual(p6.get_fio(), "Смиренников Иоанн")

        # Test 7: Female patronymic conversion
        p7 = person("Марія", "Иванова", last_name_orig="Петрова")
        self.assertEqual(p7.get_fio(), "Петрова Мария Ивановна")

        # Test 8: Historical orthography auto-modernization
        p8 = person("Петръ", "Іоанновъ", last_name_orig="Чичиковъ")
        self.assertEqual(p8.get_fio(), "Чичиков Петр Иоаннович")

        # Test 9: Placeholder values
        p9 = person("?", "?", last_name_orig="?")
        self.assertEqual(p9.get_fio(), "? ? ?")

        # Test 10: Mixed None and valid values
        p10 = person("Дарья", patr_orig=None, patr_old=None, last_name_orig="Болтунова")
        self.assertEqual(p10.get_fio(), "Болтунова Дария")


class TestPersonValidation(unittest.TestCase):
    """Test Person class validation logic"""

    def test_gender_mismatch_with_name(self):
        """Person should raise ValueError when explicit gender conflicts with name"""
        # Maria is female, but we're passing Gender.MALE
        with self.assertRaises(ValueError) as ctx:
            person("Марія", gender=Gender.MALE)
        self.assertIn("Gender mismatch", str(ctx.exception))
        self.assertIn("name", str(ctx.exception).lower())

    def test_gender_mismatch_with_patronymic(self):
        """Person should raise ValueError when explicit gender conflicts with patronymic"""
        # "Иванова" is female patronymic (old form), but passing Gender.MALE
        with self.assertRaises(ValueError) as ctx:
            person("?", patr_orig="Иванова", gender=Gender.MALE)
        self.assertIn("Gender mismatch", str(ctx.exception))
        self.assertIn("patronymic", str(ctx.exception).lower())

    def test_gender_errors_carry_a_code(self):
        """What the error is, for a reader that does not read its text (Verso's sex offer)."""
        from verso.ru.dsl.statuses import PEASANT_FEMALE
        cases = ((lambda: person("Марія", gender=Gender.MALE), "gender.name"),
                 (lambda: person("?", patr_orig="Иванова", gender=Gender.MALE), "gender.patronymic"),
                 (lambda: person("?", status=PEASANT_FEMALE, gender=Gender.MALE), "gender.status"))
        for make, code in cases:
            with self.assertRaises(ValueError) as ctx:
                make()
            self.assertEqual(code, getattr(ctx.exception, "verso_code", None))

    def test_gender_auto_detection_from_name(self):
        """Person should auto-detect gender from name when not provided"""
        p = person("Иванъ")  # Male name
        self.assertEqual(Gender.MALE, p.gender)

        p = person("Марія")  # Female name
        self.assertEqual(Gender.FEMALE, p.gender)

    def test_placeholder_names_are_valid(self):
        """Person should accept placeholder value '?'"""
        p1 = person("?")
        self.assertIsNotNone(p1)

    def test_placeholder_patronymics_are_valid(self):
        """Person should accept placeholder patronymic '?'"""
        p = person("Иванъ", patr_orig="?")
        self.assertIsNotNone(p)
        self.assertEqual("?", p.patr_old)
        self.assertEqual("?", p.patr_modern)

    def test_partial_illegibility_in_name_is_valid(self):
        p = person("Федо?")
        self.assertIsNotNone(p)
        self.assertEqual(p.name_modern, "Федо?")

    def test_partial_illegibility_in_patronymic_is_valid(self):
        p = person("Иванъ", "Иванов?")
        self.assertIsNotNone(p)
        self.assertEqual(p.patr_old, "Иванов?")
        self.assertEqual(p.patr_modern, "Иванов?")


class TestStatus(unittest.TestCase):
    """Test Status class and gender validation in Person"""

    def test_status_is_string_compatible(self):
        """Status must behave exactly like a str"""
        s = Status("крестьянин")
        self.assertEqual(s, "крестьянин")
        self.assertEqual(str(s), "крестьянин")
        self.assertIsInstance(s, str)

    def test_status_stores_gender(self):
        s = Status("крестьянин", Gender.MALE)
        self.assertEqual(s.gender, Gender.MALE)

    def test_status_gender_defaults_to_none(self):
        s = Status("нищ и слеп")
        self.assertIsNone(s.gender)

    def test_status_gender_matches_explicit_person_gender(self):
        """No error when status gender matches explicit gender"""
        p = person("Иванъ", "Ивановъ", status=Status("крестьянин", Gender.MALE), gender=Gender.MALE)
        self.assertIsNotNone(p)

    def test_status_gender_matches_inferred_person_gender(self):
        """No error when status gender matches gender inferred from name"""
        p = person("Иванъ", "Ивановъ", status=Status("крестьянин", Gender.MALE))
        self.assertIsNotNone(p)

    def test_status_gender_mismatch_with_explicit_gender_raises(self):
        """ValueError when status gender contradicts explicit person gender"""
        with self.assertRaises(ValueError) as ctx:
            person("Иванъ", "Ивановъ", status=Status("крестьянка", Gender.FEMALE), gender=Gender.MALE)
        self.assertIn("implies gender", str(ctx.exception))

    def test_status_gender_mismatch_with_inferred_gender_raises(self):
        """ValueError when status gender contradicts gender inferred from name"""
        with self.assertRaises(ValueError) as ctx:
            person("Марія", "Иванова", status=Status("крестьянин", Gender.MALE))
        self.assertIn("implies gender", str(ctx.exception))

    def test_plain_string_status_no_validation(self):
        """Plain str status never triggers gender validation"""
        p = person("Марія", "Иванова", status="крестьянин")
        self.assertIsNotNone(p)

    def test_status_without_gender_no_validation(self):
        """Status with gender=None never triggers gender validation"""
        p = person("Марія", "Иванова", status=Status("крестьянин"))
        self.assertIsNotNone(p)

    def test_status_object_with_gender_assigns_person_gender(self):
        """When Status carries a gender and the person has no other
        gender signal (no explicit kwarg, ambiguous name, no
        patronymic), the Status's gender wins. Used for hidden census
        ancestors where role=None and the only gender indicator is the
        masculine/feminine status word."""
        p = person("Пичкинза", status=Status("ясачный крестьянин", Gender.MALE))
        self.assertEqual(p.gender, Gender.MALE)

    def test_status_string_lookup_assigns_person_gender(self):
        """A plain string status that matches a registered Status
        constant (via statuses module) also drives gender derivation.
        Lets DSL files keep the more readable plain-string form."""
        # Trigger statuses module load so its Status constants register
        # themselves in the Status._gender_registry.
        import verso.ru.domain.statuses as statuses  # noqa: F401
        p = person("Пичкинза", status="ясачный крестьянин")
        self.assertEqual(p.gender, Gender.MALE)


class TestRecordDefaults(unittest.TestCase):
    """Test RecordDefaults functionality"""

    def test_apply_to_person_sets_residence(self):
        """apply_to_person should set residence when person's is None"""
        from verso.ru.domain import RecordDefaults

        defaults = RecordDefaults(residence="Заманиловка")
        p = person("Иванъ")
        self.assertIsNone(p.residence)

        defaults.apply_to_person(p)
        self.assertEqual("Заманиловка", p.residence)

    def test_apply_to_person_sets_male_status(self):
        """apply_to_person should set status_male for males"""
        from verso.ru.domain import RecordDefaults

        defaults = RecordDefaults(status_male="крестьянин")
        p = person("Иванъ")  # Male
        self.assertIsNone(p.status)

        defaults.apply_to_person(p)
        self.assertEqual("крестьянин", p.status)

    def test_apply_to_person_sets_female_status(self):
        """apply_to_person should set status_female for females"""
        from verso.ru.domain import RecordDefaults

        defaults = RecordDefaults(status_female="крестьянка")
        p = person("Марія")  # Female
        self.assertIsNone(p.status)

        defaults.apply_to_person(p)
        self.assertEqual("крестьянка", p.status)

    def test_apply_to_person_preserves_existing_values(self):
        """apply_to_person should not overwrite existing values"""
        from verso.ru.domain import RecordDefaults

        defaults = RecordDefaults(residence="Заманиловка", status_male="крестьянин")
        p = person("Иванъ", residence="Москва", status="дворянин")

        defaults.apply_to_person(p)
        self.assertEqual("Москва", p.residence)  # Not overwritten
        self.assertEqual("дворянин", p.status)  # Not overwritten

    def test_apply_to_person_handles_none_person(self):
        """apply_to_person should handle None person gracefully"""
        from verso.ru.domain import RecordDefaults

        defaults = RecordDefaults(residence="Заманиловка")
        defaults.apply_to_person(None)  # Should not raise

    def test_apply_to_birth_all_persons(self):
        """apply_to_birth should apply defaults to all persons in birth record"""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(residence="Заманиловка")
        b = Birth(record_num=1, gender=Gender.MALE, b_day=1, k_day=2, b_month=Month.JANUARY, k_month=Month.JANUARY,
                  child=person("Иванъ"), father=person("Петръ"), mother=person("Марія"), god_parent1=person("Сидоръ"),
                  god_parent2=person("Анна"), page=None)

        defaults.apply_to_birth(b)

        # Check all persons got residence
        self.assertEqual("Заманиловка", b.child.residence)
        self.assertEqual("Заманиловка", b.father.residence)
        self.assertEqual("Заманиловка", b.mother.residence)
        self.assertEqual("Заманиловка", b.god_parent1.residence)
        self.assertEqual("Заманиловка", b.god_parent2.residence)

    def test_apply_to_birth_relatives_get_defaults(self):
        """apply_to_birth should apply defaults to relative persons too"""
        from verso.ru.domain import RecordDefaults
        from calendar import Month
        from verso.ru.relationship import Relative, Relationship

        defaults = RecordDefaults(residence="Горюхино", status_male="крестьянин")
        rel_person = person("Сидоръ", "Ивановъ")
        rel = Relative(rel_person, Relationship.FATHER)
        b = Birth(record_num=1, gender=Gender.MALE, b_day=1, k_day=2, b_month=Month.JANUARY, k_month=Month.JANUARY,
                  child=person("Иванъ"), father=person("Петръ"), page=None, relatives=[rel])

        defaults.apply_to_birth(b)

        self.assertEqual("Горюхино", rel_person.residence)
        self.assertEqual("крестьянин", str(rel_person.status))

    def test_apply_to_marriage_bride_special_status(self):
        """apply_to_marriage should apply special bride status"""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(
            status_male="крестьянин",
            status_bride="крестьянская дочь"
        )
        m = Marriage(
            record_num=1,
            w_day=1, w_month=Month.JANUARY,
            groom=person("Иванъ"),
            bride=person("Марія"),
            witness1=person("Петръ"),
            witness2=person("Сидоръ"),
            page=None
        )

        defaults.apply_to_marriage(m)

        self.assertEqual("крестьянин", m.groom.status)
        self.assertEqual("крестьянская дочь", m.bride.status)  # Special bride status

    def test_apply_to_birth_mother_special_status(self):
        """apply_to_birth should apply special mother status only to the mother"""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(
            status_female="крестьянка",
            status_mother="законная жена крестьянина",
        )
        b = Birth(record_num=1, gender=Gender.MALE, b_day=1, k_day=2,
                  b_month=Month.JANUARY, k_month=Month.JANUARY,
                  child=person("Иванъ"), father=person("Петръ"),
                  mother=person("Марія"), god_parent2=person("Анна"),
                  page=None)

        defaults.apply_to_birth(b)

        self.assertEqual("законная жена крестьянина", b.mother.status)  # Special mother status
        self.assertEqual("крестьянка", b.god_parent2.status)  # Godmother keeps status_female

    def test_apply_to_birth_mother_status_falls_back_to_female(self):
        """mother status should fall back to status_female when status_mother unset"""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(status_female="крестьянка")
        b = Birth(record_num=1, gender=Gender.MALE, b_day=1, k_day=2,
                  b_month=Month.JANUARY, k_month=Month.JANUARY,
                  child=person("Иванъ"), mother=person("Марія"), page=None)

        defaults.apply_to_birth(b)

        self.assertEqual("крестьянка", b.mother.status)

    def test_apply_to_birth_mother_explicit_status_preserved(self):
        """an explicit mother status must never be overwritten by status_mother"""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(status_mother="законная жена крестьянина")
        b = Birth(record_num=1, gender=Gender.MALE, b_day=1, k_day=2,
                  b_month=Month.JANUARY, k_month=Month.JANUARY,
                  child=person("Иванъ"),
                  mother=person("Марія", status="солдатская жена"),
                  page=None)

        defaults.apply_to_birth(b)

        self.assertEqual("солдатская жена", b.mother.status)

    def test_apply_to_death_all_persons(self):
        """apply_to_death should apply defaults to all persons in death record"""
        from verso.ru.domain import RecordDefaults
        from verso.ru.relationship import Relationship
        from calendar import Month

        defaults = RecordDefaults(residence="Заманиловка", status_male="крестьянин")
        d = Death(
            record_num=1, gender=Gender.MALE,
            d_day=1, d_month=Month.JANUARY,
            b_day=2, b_month=Month.JANUARY,
            deceased=person("Иванъ"),
            relatives=[Relative(person("Петръ"), Relationship.FATHER)],
            witness1=person("Сидоръ"),
            witness2=person("Андрей"),
            page=None
        )

        defaults.apply_to_death(d)

        self.assertEqual("Заманиловка", d.deceased.residence)
        self.assertEqual("Заманиловка", d.relative.residence)
        self.assertEqual("Заманиловка", d.witness1.residence)
        self.assertEqual("Заманиловка", d.witness2.residence)

    def test_apply_to_death_leaves_cause_none_when_default_unset(self):
        """RecordDefaults that does NOT set `cause_of_death` must NOT
        invent a default cause on the Death record. Pre-1800 МК
        documents had no cause-of-death column; their DSLs rely on
        this contract to omit `cause_of_death =` from the emitted
        terraform output (legacy parity)."""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(
            residence="Собакевичево",
            status_male="ясачный крестьянин",
            status_female="ясачная крестьянка",
            # cause_of_death intentionally NOT set
        )
        d = Death(
            record_num=1, gender=Gender.MALE,
            d_day=5, d_month=Month.JANUARY,
            deceased=person("Иван", "Петров"),
        )
        self.assertIsNone(d.cause_of_death,
                          "pre-condition: Death.cause_of_death starts None")
        defaults.apply_to_death(d)
        self.assertIsNone(d.cause_of_death,
                          "RecordDefaults without cause_of_death must "
                          "leave Death.cause_of_death = None")

    def test_apply_to_death_propagates_explicit_cause_default(self):
        """Regression sibling: when RecordDefaults DOES set
        `cause_of_death`, propagation still works (Death.cause_of_death
        was None → picks up the default)."""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(
            residence="Собакевичево",
            cause_of_death="оспа",
        )
        d = Death(
            record_num=1, gender=Gender.MALE,
            d_day=5, d_month=Month.JANUARY,
            deceased=person("Иван", "Петров"),
        )
        defaults.apply_to_death(d)
        self.assertEqual(d.cause_of_death, "оспа")

    def test_apply_to_death_does_not_override_per_record_cause(self):
        """When the Death record carries an explicit `cause_of_death`,
        the default does NOT overwrite it."""
        from verso.ru.domain import RecordDefaults
        from calendar import Month

        defaults = RecordDefaults(cause_of_death="натуральная")
        d = Death(
            record_num=1, gender=Gender.MALE,
            d_day=5, d_month=Month.JANUARY,
            deceased=person("Иван", "Петров"),
            cause_of_death="оспа",
        )
        defaults.apply_to_death(d)
        self.assertEqual(d.cause_of_death, "оспа",
                         "explicit per-record cause must win over default")

    def test_apply_to_death_not_in_document_suppresses_default(self):
        """`cause_of_death=NOT_IN_DOCUMENT` opts a record out of the
        RecordDefaults fallback. The marker is consumed (cleared to None)
        so downstream emission omits the field."""
        from verso.ru.domain import RecordDefaults, NOT_IN_DOCUMENT
        from calendar import Month

        defaults = RecordDefaults(cause_of_death="натуральная")
        d = Death(
            record_num=1, gender=Gender.MALE,
            d_day=5, d_month=Month.JANUARY,
            deceased=person("Иван", "Петров"),
            cause_of_death=NOT_IN_DOCUMENT,
        )
        defaults.apply_to_death(d)
        self.assertIsNone(d.cause_of_death,
                          "NOT_IN_DOCUMENT marker must clear cause_of_death "
                          "to None so downstream emitters skip the field")


class TestGetCanonicalName(unittest.TestCase):
    """Test that get_canonical_name passes gender to canonicalize_name."""

    def test_unambiguous_male_name(self):
        p = person("Иванъ")
        self.assertEqual(p.get_canonical_name(), "Иоанн")

    def test_unambiguous_female_name(self):
        p = person("Марія")
        self.assertEqual(p.get_canonical_name(), "Мария")

    def test_ambiguous_name_male_gender(self):
        # "Лука" exists as both male and female; male has no Имя-основа → returns "Лука"
        p = Person("Лука", gender=Gender.MALE)
        self.assertEqual(p.get_canonical_name(), "Лука")

    def test_ambiguous_name_female_gender(self):
        # "Лука" female has Имя-основа = "Гликерия"
        p = Person("Лука", gender=Gender.FEMALE)
        self.assertEqual(p.get_canonical_name(), "Гликерия")

    def test_ambiguous_name_no_gender_returns_canonical(self):
        # Without gender, canonical row (empty Имя-основа) wins: "Лука" stays "Лука"
        p = Person("Лука")
        self.assertEqual(p.get_canonical_name(), "Лука")


class TestBookFunction(unittest.TestCase):
    """Test book() function for grouping records by metric book."""

    def test_book_sets_priest_on_birth(self):
        """book() should set priest on birth records that don't have one."""
        child = Person("Иван", name_modern_orth="Иван")
        b = Birth(1, Gender.MALE, 1, 2, 1, 1, child, None, None, None, None)
        self.assertIsNone(b.priest)

        priest = person("Харитон", "Лукин")
        result = book("12", priest, b)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].priest.name_modern, "Харитон")
        self.assertEqual(result[0].priest.status, "священник")
        self.assertEqual(result[0].book, "12")
        # Original unchanged
        self.assertIsNone(b.priest)
        self.assertIsNone(b.book)

    def test_book_sets_priest_on_death(self):
        """book() should set priest on death records."""
        deceased = Person("Петр", name_modern_orth="Петр")
        d = Death(1, Gender.MALE, 10, 12, 5, 5, deceased, witness1=None, witness2=None)
        self.assertIsNone(d.priest)

        priest = person("Тимон", "Пахомов")
        result = book("14", priest, d)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].priest.name_modern, "Тимон")
        self.assertEqual(result[0].priest.status, "священник")
        self.assertEqual(result[0].book, "14")

    def test_book_sets_priest_on_marriage(self):
        """book() should set priest on marriage records."""
        groom = Person("Иван", name_modern_orth="Иван")
        bride = Person("Анна", name_modern_orth="Анна")
        m = Marriage(1, 5, 6, groom, bride)
        self.assertIsNone(m.priest)

        priest = person("Харитон", "Лукин")
        result = book("1", priest, m)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].priest.name_modern, "Харитон")
        self.assertEqual(result[0].book, "1")

    def test_book_does_not_override_existing_priest(self):
        """book() should not override priest if already set on a record."""
        child = Person("Иван", name_modern_orth="Иван")
        existing_priest = person("Иван", "Никитин")
        b = Birth(1, Gender.MALE, 1, 2, 1, 1, child, None, None, None, None, priest=existing_priest)
        self.assertIsNotNone(b.priest)

        new_priest = person("Харитон", "Лукин")
        result = book("12", new_priest, b)

        # Priest should remain the original one
        self.assertEqual(result[0].priest.name_modern, "Иван")
        # But book should still be set
        self.assertEqual(result[0].book, "12")

    def test_book_does_not_override_existing_book(self):
        """book() should not override book if already set on a record."""
        child = Person("Иван", name_modern_orth="Иван")
        b = Birth(1, Gender.MALE, 1, 2, 1, 1, child, None, None, None, None, book="existing")

        priest = person("Харитон", "Лукин")
        result = book("12", priest, b)

        self.assertEqual(result[0].book, "existing")

    def test_book_with_multiple_records(self):
        """book() should set priest and book on all records."""
        child1 = Person("Иван", name_modern_orth="Иван")
        child2 = Person("Анна", name_modern_orth="Анна")
        b1 = Birth(1, Gender.MALE, 1, 2, 1, 1, child1, None, None, None, None)
        b2 = Birth(2, Gender.FEMALE, 3, 4, 2, 2, child2, None, None, None, None)

        priest = person("Харитон", "Лукин")
        result = book("12", priest, b1, b2)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].priest.name_modern, "Харитон")
        self.assertEqual(result[0].book, "12")
        self.assertEqual(result[1].priest.name_modern, "Харитон")
        self.assertEqual(result[1].book, "12")


class TestMonthYearFunctions(unittest.TestCase):
    """Test *_month_year() functions for setting year on records."""

    def test_birth_month_year_sets_year(self):
        from calendar import Month
        child = Person("Иван", name_modern_orth="Иван")
        b = Birth(1, Gender.MALE, 14, 15, None, None, child, None, None, None, None)
        self.assertIsNone(b.year)
        result = birth_month_year(Month.NOVEMBER, 1797, b)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].year, 1797)
        self.assertEqual(result[0].b_month, Month.NOVEMBER)
        # Original unchanged
        self.assertIsNone(b.year)

    def test_birth_month_year_does_not_override_existing_year(self):
        from calendar import Month
        child = Person("Иван", name_modern_orth="Иван")
        b = Birth(1, Gender.MALE, 14, 15, None, None, child, None, None, None, None, year=1796)
        result = birth_month_year(Month.DECEMBER, 1797, b)
        self.assertEqual(result[0].year, 1796)

    def test_death_month_year_sets_year(self):
        from calendar import Month
        deceased = Person("Петр", name_modern_orth="Петр")
        d = Death(1, Gender.MALE, 10, 12, None, None, deceased, witness1=None, witness2=None)
        self.assertIsNone(d.year)
        result = death_month_year(Month.NOVEMBER, 1797, d)
        self.assertEqual(result[0].year, 1797)
        self.assertEqual(result[0].d_month, Month.NOVEMBER)

    def test_marriage_month_year_sets_year(self):
        from calendar import Month
        groom = Person("Иван", name_modern_orth="Иван")
        bride = Person("Анна", name_modern_orth="Анна")
        m = Marriage(1, 5, None, groom, bride)
        self.assertIsNone(m.year)
        result = marriage_month_year(Month.NOVEMBER, 1798, m)
        self.assertEqual(result[0].year, 1798)
        self.assertEqual(result[0].w_month, Month.NOVEMBER)

    def test_marriage_month_year_does_not_override(self):
        from calendar import Month
        groom = Person("Иван", name_modern_orth="Иван")
        bride = Person("Анна", name_modern_orth="Анна")
        m = Marriage(1, 5, None, groom, bride, year=1797)
        result = marriage_month_year(Month.NOVEMBER, 1798, m)
        self.assertEqual(result[0].year, 1797)

    def test_birth_month_year_none_year_acts_like_birth_month(self):
        from calendar import Month
        child = Person("Иван", name_modern_orth="Иван")
        b = Birth(1, Gender.MALE, 14, 15, None, None, child, None, None, None, None)
        result = birth_month_year(Month.JANUARY, None, b)
        self.assertIsNone(result[0].year)
        self.assertEqual(result[0].b_month, Month.JANUARY)


class TestCensusRecords(unittest.TestCase):
    """Test CensusRecords constructor behavior."""

    def _make_records(self, village, households):
        from verso.ru.dsl.records.census import CensusRecords
        return CensusRecords(
            archive="РГАДА", fund="350", inventory="2", case="100",
            village=village, year=1719, households=households,
        )

    def test_residence_set_from_village(self):
        """Members without residence get village as residence."""
        from verso.ru.dsl.records.census import household, member, CensusRole
        p = person("Иванъ")
        self.assertIsNone(p.residence)
        h = household(None, member(1, p, CensusRole.HEAD, age=40))
        records = self._make_records("Заманиловка", [h])
        self.assertEqual(records.households[0].members[0].person.residence, "Заманиловка")

    def test_existing_residence_preserved(self):
        """Members with existing residence are not overwritten."""
        from verso.ru.dsl.records.census import household, member, CensusRole
        p = person("Иванъ", residence="Москва")
        h = household(None, member(1, p, CensusRole.HEAD, age=40))
        records = self._make_records("Заманиловка", [h])
        self.assertEqual(records.households[0].members[0].person.residence, "Москва")

    def test_deep_copy_no_mutation(self):
        """Original household members are not mutated."""
        from verso.ru.dsl.records.census import household, member, CensusRole
        p = person("Иванъ")
        h = household(None, member(1, p, CensusRole.HEAD, age=40))
        self._make_records("Заманиловка", [h])
        # Original person should still have no residence
        self.assertIsNone(p.residence)
        # Household's deep-copied member should also be unaffected
        self.assertIsNone(h.members[0].person.residence)

    def test_multiple_households(self):
        """Residence propagates across all households."""
        from verso.ru.dsl.records.census import household, member, CensusRole
        h1 = household(None, member(1, person("Иванъ"), CensusRole.HEAD, age=40))
        h2 = household(None, member(1, person("Петръ"), CensusRole.HEAD, age=35),
                       member(2, person("Марія", residence="Околесица"), CensusRole.WIFE, ref_member=1, age=30))
        records = self._make_records("Заманиловка", [h1, h2])
        self.assertEqual(records.households[0].members[0].person.residence, "Заманиловка")
        self.assertEqual(records.households[1].members[0].person.residence, "Заманиловка")
        self.assertEqual(records.households[1].members[1].person.residence, "Околесица")


class TestDivorceRecords(unittest.TestCase):

    def test_divorce_basic(self):
        from verso.ru.dsl.records.divorces import Divorce
        d = Divorce(
            record_num=23,
            d_day=9,
            husband=Person("Тихон", "Игнатьев", name_modern_orth="Тихон", patr_old="Игнатьев", gender=Gender.MALE),
            wife=Person("Анисья", "Лукина", name_modern_orth="Анисья", patr_old="Лукина", gender=Gender.FEMALE),
            husband_age=23,
            wife_age=21,
        )
        self.assertEqual(d.record_num, 23)
        self.assertEqual(d.d_day, 9)
        self.assertEqual(d.husband_age, 23)
        self.assertEqual(d.wife_age, 21)
        self.assertEqual(d.husband.gender, Gender.MALE)
        self.assertEqual(d.wife.gender, Gender.FEMALE)

    def test_divorce_with_extras(self):
        from verso.ru.dsl.records.divorces import Divorce
        d = Divorce(
            record_num=7,
            d_day=18,
            husband=Person("Нил", "Пахомов", name_modern_orth="Нил", patr_old="Пахомов", gender=Gender.MALE),
            wife=Person("Фекла", "Сидорова", name_modern_orth="Фекла", patr_old="Сидорова", gender=Gender.FEMALE),
            marriage_date="5 марта 1929",
            children="сын Пётр (3) при отце",
            initiator="муж",
        )
        self.assertEqual(d.marriage_date, "5 марта 1929")
        self.assertEqual(d.children, "сын Пётр (3) при отце")
        self.assertEqual(d.initiator, "муж")

    def test_divorce_gender_auto_detection(self):
        from verso.ru.dsl.records.divorces import Divorce
        d = Divorce(
            record_num=1,
            husband=Person("Нил", "Пахомов", name_modern_orth="Нил", patr_old="Пахомов"),
            wife=Person("Татьяна", "Фокина", name_modern_orth="Татьяна", patr_old="Фокина"),
        )
        self.assertEqual(d.husband.gender, Gender.MALE)
        self.assertEqual(d.wife.gender, Gender.FEMALE)

    def test_divorce_month(self):
        from calendar import Month
        from verso.ru.dsl.records.divorces import Divorce, divorce_month
        d = Divorce(record_num=1, d_day=5)
        results = divorce_month(Month.JULY, d)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].d_month, Month.JULY)
        # Original should be unaffected
        self.assertIsNone(d.d_month)

    def test_divorce_records_defaults(self):
        from verso.ru.dsl.records.divorces import divorce, divorce_records
        from verso.ru.domain import RecordDefaults
        rec = divorce(4, 8,
                      husband=person("Игнатий", "Леонтьев"),
                      wife=person("Фекла", "Сидорова"))
        records = divorce_records(
            "ГАПО", "1605", "59", "59", "Заманиловка", "", 1925,
            rec,
            defaults=RecordDefaults(residence="Заманиловка"),
        )
        self.assertEqual(len(records.records), 1)
        self.assertEqual(records.records[0].husband.residence, "Заманиловка")
        self.assertEqual(records.records[0].wife.residence, "Заманиловка")

    def test_divorce_records_preserves_existing_residence(self):
        from verso.ru.dsl.records.divorces import divorce, divorce_records
        from verso.ru.domain import RecordDefaults
        rec = divorce(4, 8,
                      husband=person("Игнатий", "Леонтьев", residence="Шпонькин Бор"),
                      wife=person("Фекла", "Сидорова"))
        records = divorce_records(
            "ГАПО", "1605", "59", "59", "Заманиловка", "", 1925,
            rec,
            defaults=RecordDefaults(residence="Заманиловка"),
        )
        self.assertEqual(records.records[0].husband.residence, "Шпонькин Бор")
        self.assertEqual(records.records[0].wife.residence, "Заманиловка")


class TestInsertDivorces(unittest.TestCase):

    def setUp(self):
        import sqlite3
        self.conn = sqlite3.connect(":memory:")
        from verso.ru.cli.all_persons import create_db
        create_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_insert_divorces_creates_divorce_row(self):
        from verso.ru.cli.all_persons import insert_divorces
        from verso.ru.dsl.records.divorces import Divorce, DivorceRecords
        from calendar import Month
        d = Divorce(
            record_num=23, d_day=9, d_month=Month.AUGUST,
            husband=Person("Тихон", "Игнатьев", name_modern_orth="Тихон", patr_old="Игнатьев",
                           last_name="Чичиков", gender=Gender.MALE, residence="Заманиловка"),
            wife=Person("Анисья", "Лукина", name_modern_orth="Анисья", patr_old="Лукина",
                         last_name="Спорщикова", gender=Gender.FEMALE, residence="Заманиловка"),
            husband_age=23, wife_age=21,
            marriage_date=EventDate(1925, Month.MAY, 9), initiator="жена",
        )
        records = DivorceRecords("ГАПО", "1605", "59", "59", "Заманиловка", "", 1927, [d])
        count = insert_divorces(self.conn, records, "1927/zamanilovka_divorces_1927.py")
        self.assertEqual(count, 2)  # husband + wife

        rows = self.conn.execute("SELECT * FROM divorces").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], 23)   # record_num
        self.assertEqual(rows[0][3], 9)    # d_day
        self.assertEqual(rows[0][4], 8)    # d_month (August)
        self.assertEqual(rows[0][5], 23)   # husband_age
        self.assertEqual(rows[0][6], 21)   # wife_age
        self.assertEqual(rows[0][7], "9 мая 1925")  # marriage_date
        self.assertEqual(rows[0][9], "жена")  # initiator

    def test_insert_divorces_creates_persons(self):
        from verso.ru.cli.all_persons import insert_divorces
        from verso.ru.dsl.records.divorces import Divorce, DivorceRecords
        from calendar import Month
        d = Divorce(
            record_num=5, d_day=21, d_month=Month.FEBRUARY,
            husband=Person("Савелий", name_modern_orth="Савелий",
                           last_name="Лямкин", gender=Gender.MALE, residence="Заманиловка"),
            wife=Person("Татьяна", "Фокина", name_modern_orth="Татьяна", patr_old="Фокина",
                         last_name="Чичикова", gender=Gender.FEMALE, residence="Заманиловка"),
        )
        records = DivorceRecords("ГАПО", "1605", "59", "59", "Заманиловка", "", 1926, [d])
        insert_divorces(self.conn, records, "1926/zamanilovka_divorces_1926.py")

        persons = self.conn.execute(
            "SELECT record_type, role, fio, residence FROM persons ORDER BY role"
        ).fetchall()
        self.assertEqual(len(persons), 2)

        husband = next(p for p in persons if p[1] == "муж")
        self.assertEqual(husband[0], "развод")
        self.assertIn("Савва", husband[2])

        wife = next(p for p in persons if p[1] == "жена")
        self.assertEqual(wife[0], "развод")
        self.assertIn("Татиана", wife[2])

    def test_insert_divorces_empty(self):
        from verso.ru.cli.all_persons import insert_divorces
        from verso.ru.dsl.records.divorces import DivorceRecords
        records = DivorceRecords("ГАПО", "1605", "59", "59", "Заманиловка", "", 1927, [])
        count = insert_divorces(self.conn, records, "test.py")
        self.assertEqual(count, 0)
        rows = self.conn.execute("SELECT count(*) FROM divorces").fetchone()[0]
        self.assertEqual(rows, 0)


class TestBirthRelativeExport(unittest.TestCase):
    """Test that birth CSV export includes relative data."""

    def test_birth_with_relative_exports_to_csv(self):
        """Birth with a relative should populate relative columns in CSV."""
        import csv
        import tempfile
        from calendar import Month
        from verso.ru.exporters.csv_familio import BirthRecordsCsvFamilioExporter
        from verso.ru.dsl.records.births import birth, birth_records, birth_month
        from verso.ru.relationship import relative, Relationship

        records = birth_records(
            "Архив", "Фонд", "Опись", "Дело", "Горюхино", "Церковь", 1836,
            *page("1",
                  *birth_month(Month.FEBRUARY,
                               birth(6, Gender.FEMALE, 11, 13,
                                     child=person("Анисья"),
                                     father=person("Тимон", "Пахомов"),
                                     god_parent1=person("Фекла", "Савельева"),
                                     relatives=[relative(
                                         person("Савелий", "Игнатьев", status="пономарь"),
                                         Relationship.FATHER, "восприемника №1")])),
                  ),
        )

        # Export by running in the temp dir
        exporter = BirthRecordsCsvFamilioExporter()
        import os
        old_cwd = os.getcwd()
        tmpdir = tempfile.mkdtemp()
        os.chdir(tmpdir)
        try:
            exporter.export(records)
        finally:
            os.chdir(old_cwd)
        path = os.path.join(tmpdir, "Горюхино_1836_births_familio.csv")

        with open(path, encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)

        # Find relative columns by header
        rel1_whose_idx = headers.index("Родственник 1: Чей родственник")
        rel1_rel_idx = headers.index("Родственник 1: Родство")
        rel1_status_idx = headers.index("Родственник 1: Статус")
        _rel1_residence_idx = headers.index("Родственник 1: Н.П.")
        rel1_fio_idx = headers.index("Родственник 1: ФИО (совр.)")

        self.assertEqual(row[rel1_whose_idx], "восприемника №1")
        self.assertEqual(row[rel1_rel_idx], "отец")
        self.assertEqual(row[rel1_status_idx], "пономарь")
        self.assertIn("Савва", row[rel1_fio_idx])

        # Verify Relative 2 columns are empty when only 1 relative
        rel2_whose_idx = headers.index("Родственник 2: Чей родственник")
        self.assertEqual(row[rel2_whose_idx], "")

        import shutil
        shutil.rmtree(tmpdir)


    def test_birth_with_two_relatives_exports_both(self):
        """Birth with 2 relatives should populate both Rel1 and Rel2 columns."""
        import csv
        import tempfile
        from calendar import Month
        from verso.ru.exporters.csv_familio import BirthRecordsCsvFamilioExporter
        from verso.ru.dsl.records.births import birth, birth_records, birth_month
        from verso.ru.relationship import relative, Relationship

        records = birth_records(
            "Архив", "Фонд", "Опись", "Дело", "Горюхино", "Церковь", 1836,
            *page("1",
                  *birth_month(Month.FEBRUARY,
                               birth(8, Gender.MALE, 14, 15,
                                     child=person("Харитон"),
                                     father=person("Тихон", "Игнатьев"),
                                     relatives=[
                                         relative(person("Нил", "Лукин", status="священник"),
                                                  Relationship.FATHER, "восприемника №1"),
                                         relative(person("Пахом", "Сидоров", status="диакон"),
                                                  Relationship.HUSBAND, "восприемника №2"),
                                     ])),
                  ),
        )

        exporter = BirthRecordsCsvFamilioExporter()
        import os
        old_cwd = os.getcwd()
        tmpdir = tempfile.mkdtemp()
        os.chdir(tmpdir)
        try:
            exporter.export(records)
        finally:
            os.chdir(old_cwd)
        path = os.path.join(tmpdir, "Горюхино_1836_births_familio.csv")

        with open(path, encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)

        # Relative 1
        rel1_fio_idx = headers.index("Родственник 1: ФИО (совр.)")
        self.assertIn("Нил", row[rel1_fio_idx])

        # Relative 2
        rel2_whose_idx = headers.index("Родственник 2: Чей родственник")
        rel2_rel_idx = headers.index("Родственник 2: Родство")
        rel2_fio_idx = headers.index("Родственник 2: ФИО (совр.)")
        self.assertEqual(row[rel2_whose_idx], "восприемника №2")
        self.assertEqual(row[rel2_rel_idx], "муж")
        self.assertIn("Пахом", row[rel2_fio_idx])

        import shutil
        shutil.rmtree(tmpdir)


if __name__ == '__main__':
    unittest.main()


class RecordDefaultsGenderCoupling(unittest.TestCase):
    """RecordDefaults must re-trigger the status→gender inference.

    Person.__init__ resolves gender as a cascade ending in a status-based
    fallback, but RecordDefaults assigns `status` AFTER __init__ has run — so
    hoisting a repeated status into defaults silently dropped gender for anyone
    whose name/patronymic/role could not resolve it (the single-named archaic hidden
    ancestors in the early censuses: Бурмяй, Пичкинза, Тазей, Верияс).
    """

    def test_gender_from_status_is_reusable(self):
        from verso.ru.domain.statuses import YASAK_PEASANT_MALE
        p = Person("Бурмяй", status=YASAK_PEASANT_MALE)
        self.assertEqual(p.gender, Gender.MALE)
        self.assertEqual(p.gender_from_status(), Gender.MALE)

    def test_unresolvable_name_without_status_has_no_gender(self):
        # Baseline: the name alone cannot resolve it, so gender stays unset.
        self.assertIsNone(Person("Бурмяй").gender)

    def test_defaults_restore_gender_that_init_could_not_infer(self):
        from verso.ru.domain.statuses import YASAK_PEASANT_MALE
        p = Person("Бурмяй")
        self.assertIsNone(p.gender)
        RecordDefaults(status_male=YASAK_PEASANT_MALE).apply_to_person(p)
        self.assertEqual(p.status, YASAK_PEASANT_MALE)
        self.assertEqual(p.gender, Gender.MALE,
                         "defaults must re-run the status→gender fallback")

    def test_explicit_gender_is_not_overwritten(self):
        from verso.ru.domain.statuses import YASAK_PEASANT_MALE
        p = Person("Анна", gender=Gender.FEMALE)
        RecordDefaults(status_male=YASAK_PEASANT_MALE,
                       status_female=YASAK_PEASANT_MALE).apply_to_person(p)
        self.assertEqual(p.gender, Gender.FEMALE)

    def test_resolvable_female_still_picks_the_female_default(self):
        from verso.ru.domain.statuses import YASAK_PEASANT_FEMALE, YASAK_PEASANT_MALE
        p = Person("Марфа")
        self.assertEqual(p.gender, Gender.FEMALE)
        RecordDefaults(status_male=YASAK_PEASANT_MALE,
                       status_female=YASAK_PEASANT_FEMALE).apply_to_person(p)
        self.assertEqual(p.status, YASAK_PEASANT_FEMALE)


def test_an_unknown_name_is_named_as_it_was_checked():
    """The refusal names the name it looked up — the modern form, written or made of the original — never
    'None' for a name written in the original alone."""
    import pytest
    with pytest.raises(ValueError, match=r"^Unrecognized first name 'Хщ' \(original: 'Хщъ'\)$"):
        person("Хщъ")
    with pytest.raises(ValueError, match=r"^Unrecognized first name 'Хщы' \(original: 'Хщъ'\)$"):
        person("Хщъ", name_modern_orth="Хщы")
    with pytest.raises(ValueError, match=r"^Unrecognized patronymic 'Хщев' \(original: 'Хщевъ'\)$"):
        person("Петръ", "Хщевъ")
