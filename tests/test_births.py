import csv
import os
import tempfile
import unittest
from calendar import Month

from verso.ru.exporters.csv import BirthRecordsCsvExporter
from verso.ru.dsl.records.births import Birth, BirthRecords, birth, birth_records, birth_month, Relative, relative
from verso.ru.domain import Person, RecordDefaults, person, Gender
from verso.ru.relationship import Relationship


class TestBirths(unittest.TestCase):
    def test_birth_automatic_gender_assignment(self):
        child = Person("Иван", name_modern_orth="Иван")
        father = Person("Петр", name_modern_orth="Петр")
        mother = Person("Мария", name_modern_orth="Мария")
        god1 = Person("Георгий", name_modern_orth="Георгий")
        god2 = Person("Анна", name_modern_orth="Анна")

        b = Birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, child, father, mother, god1, god2)

        self.assertEqual(b.child.gender, Gender.MALE)
        self.assertEqual(b.father.gender, Gender.MALE)
        self.assertEqual(b.mother.gender, Gender.FEMALE)
        self.assertEqual(b.god_parent1.gender, Gender.MALE)
        self.assertEqual(b.god_parent2.gender, Gender.FEMALE)

    def test_derive_child_patronymic(self):
        # Male child - uses names.csv table
        f1 = Person("Савва", name_modern_orth="Савва")
        b1 = Birth(1, Gender.MALE, 1, 1, Month.JANUARY, Month.JANUARY, Person("?", name_modern_orth="?"), f1, None, None, None)
        self.assertEqual(b1.derive_child_patronymic(), "Саввич")

        f2 = Person("Илья", name_modern_orth="Илья")
        b2 = Birth(2, Gender.MALE, 1, 1, Month.JANUARY, Month.JANUARY, Person("?", name_modern_orth="?"), f2, None, None, None)
        self.assertEqual(b2.derive_child_patronymic(), "Ильич")

        f3 = Person("Сергей", name_modern_orth="Сергей")
        b3 = Birth(3, Gender.MALE, 1, 1, Month.JANUARY, Month.JANUARY, Person("?", name_modern_orth="?"), f3, None, None, None)
        self.assertEqual(b3.derive_child_patronymic(), "Сергеевич")

        # Female child - uses names.csv table
        f4 = Person("Никита", name_modern_orth="Никита")
        b4 = Birth(4, Gender.FEMALE, 1, 1, Month.JANUARY, Month.JANUARY, Person("?", name_modern_orth="?"), f4, None, None, None)
        self.assertEqual(b4.derive_child_patronymic(), "Никитична")

        f5 = Person("Иван", name_modern_orth="Иван")
        b5 = Birth(5, Gender.FEMALE, 1, 1, Month.JANUARY, Month.JANUARY, Person("?", name_modern_orth="?"), f5, None, None, None)
        self.assertEqual(b5.derive_child_patronymic(), "Ивановна")

        f6 = Person("Савва", name_modern_orth="Савва")
        b6 = Birth(6, Gender.FEMALE, 1, 1, Month.JANUARY, Month.JANUARY, Person("?", name_modern_orth="?"), f6, None, None, None)
        self.assertEqual(b6.derive_child_patronymic(), "Саввична")  # from table

        # Placeholder father — derive returns None so the child profile
        # ends up with no `middle_name` field rather than `middle_name = "?"`.
        f7 = Person("?", name_modern_orth="?")
        b7 = Birth(7, Gender.MALE, 1, 1, Month.JANUARY, Month.JANUARY, Person("?", name_modern_orth="?"), f7, None, None, None)
        self.assertIsNone(b7.derive_child_patronymic())

    def test_dsl_helpers(self):
        p = person("Іванъ", name_modern_orth="Иван")
        self.assertIsInstance(p, Person)

        p6 = person("?", "?", name_modern_orth="?", patr_old="?", residence="R", status="S")
        self.assertEqual(p6.status, "S")

        b = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, None, None, None, None, None, comment="Test")
        self.assertEqual(b.comment, "Test")

        br = birth_records("A", "F", "I", "C", "V", "Ch", 1800, b)
        self.assertEqual(len(br.records), 1)

    def test_birth_records_defaults(self):
        # Create persons without residence/status
        child = person("Иван")
        father = person("Петр", patr_orig="Сидоров")
        mother = person("Мария", patr_orig="Иванова")
        god1 = person("Яков", patr_orig="Федоров")
        god2 = person("Анна", patr_orig="Петрова")

        # Father has explicit status, should not be overwritten
        father.status = "дьячок"

        b = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, child, father, mother, god1, god2)

        # Apply defaults using RecordDefaults class with gender-specific status
        br = birth_records("A", "F", "I", "C", "V", "Ch", 1800, b,
                            defaults=RecordDefaults(
                                residence="Заманиловка",
                                status_male="крестьянин",
                                status_female="крестьянка"
                            ))

        # Check defaults were applied where empty (on the record in br, not original objects)
        rec = br.records[0]
        self.assertEqual(rec.child.residence, "Заманиловка")
        self.assertEqual(rec.child.status, "крестьянин")  # male child
        self.assertEqual(rec.father.residence, "Заманиловка")
        self.assertEqual(rec.father.status, "дьячок")  # not overwritten
        self.assertEqual(rec.mother.residence, "Заманиловка")
        self.assertEqual(rec.mother.status, "крестьянка")  # female gets status_female
        self.assertEqual(rec.god_parent1.residence, "Заманиловка")
        self.assertEqual(rec.god_parent1.status, "крестьянин")  # male
        self.assertEqual(rec.god_parent2.residence, "Заманиловка")
        self.assertEqual(rec.god_parent2.status, "крестьянка")  # female gets status_female

    def test_birth_dsl_helpers(self):
        b = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, None, None, None, None, None, comment="Test")
        self.assertIsInstance(b, Birth)
        self.assertEqual(b.comment, "Test")
        self.assertEqual(b.record_num, 1)
        self.assertEqual(b.gender, Gender.MALE)

    def test_birth_records_collection(self):
        b1 = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, person("Иван"), person("Петр"), person("Мария"), person("Алексей"), person("Анна"))
        b2 = birth(2, Gender.FEMALE, 3, 4, Month.FEBRUARY, Month.FEBRUARY, person("Дарья"), person("Яков"), person("Екатерина"), person("Федор"), person("Ксения"))

        br = birth_records("Archive", "F", "I", "C", "Village", "Church", 1804, b1, b2)

        self.assertIsInstance(br, BirthRecords)
        self.assertEqual(len(br.records), 2)
        self.assertEqual(br.year, 1804)
        self.assertEqual(br.village, "Village")

    def test_birth_none_persons(self):
        # Test with missing persons (no mother, godparents)
        child = person("Иван")
        father = person("Петр")

        b = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, child, father, None, None, None)

        self.assertIsNotNone(b.child)
        self.assertIsNotNone(b.father)
        self.assertIsNone(b.mother)
        self.assertIsNone(b.god_parent1)
        self.assertIsNone(b.god_parent2)

    def test_record_defaults_apply_to_birth(self):
        defaults = RecordDefaults(
            residence="Testville",
            status_male="male status",
            status_female="female status"
        )

        child = person("Иван")
        father = person("Федор")
        mother = person("Мария")
        god1 = person("Яков")
        god2 = person("Анна")

        b = Birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, child, father, mother, god1, god2)
        defaults.apply_to_birth(b)

        # All persons should get the defaults
        self.assertEqual(child.residence, "Testville")
        self.assertEqual(child.status, "male status")
        self.assertEqual(father.residence, "Testville")
        self.assertEqual(father.status, "male status")
        self.assertEqual(mother.residence, "Testville")
        self.assertEqual(mother.status, "female status")
        self.assertEqual(god1.residence, "Testville")
        self.assertEqual(god2.residence, "Testville")

    def test_child_inherits_father_residence(self):
        # A newborn lives where the family lives: prefer the father's residence.
        child = person("Иван")
        father = person("Петр", residence="Собакевичево")
        mother = person("Мария", residence="Собакевичево")
        b = Birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY,
                  child, father, mother, None, None)
        self.assertEqual(b.child.residence, "Собакевичево")

    def test_child_falls_back_to_mother_residence(self):
        # Father has no residence → child inherits the mother's.
        child = person("Иван")
        father = person("Петр")
        mother = person("Мария", residence="Горюхино")
        b = Birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY,
                  child, father, mother, None, None)
        self.assertEqual(b.child.residence, "Горюхино")

    def test_child_residence_stays_none_without_parent_residence(self):
        child = person("Иван")
        father = person("Петр")
        mother = person("Мария")
        b = Birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY,
                  child, father, mother, None, None)
        self.assertIsNone(b.child.residence)

    def test_explicit_child_residence_not_overridden(self):
        child = person("Иван", residence="Заманиловка")
        father = person("Петр", residence="Собакевичево")
        mother = person("Мария", residence="Собакевичево")
        b = Birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY,
                  child, father, mother, None, None)
        self.assertEqual(b.child.residence, "Заманиловка")

    def test_csv_export_basic(self):
        """Test CSV export functionality and file generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple birth record
            child = person("Іоаннъ", residence="Тестово", gender=Gender.MALE)
            father = person("Петръ", patr_orig="Ивановъ", residence="Тестово", status="крестьянин", gender=Gender.MALE)
            mother = person("Марія", patr_orig="Сидорова", residence="Тестово", status="крестьянка", gender=Gender.FEMALE)
            god1 = person("Яковъ", patr_orig="Федоровъ", residence="Тестово", status="крестьянин", gender=Gender.MALE)
            god2 = person("Анна", patr_orig="Петрова", residence="Тестово", status="крестьянка", gender=Gender.FEMALE)

            b = birth(1, Gender.MALE, 15, 16, Month.JUNE, Month.JUNE, child, father, mother, god1, god2)
            br = birth_records("Arch", "F", "I", "C", "Тестово", "Ch", 1800, b)

            # Export to CSV
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = br.export(BirthRecordsCsvExporter())

                # Verify file was created
                self.assertTrue(os.path.exists(csv_path))
                self.assertEqual(os.path.basename(csv_path), "Тестово_1800_births.csv")

                # Read and verify CSV content
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                # Check header and data rows
                self.assertEqual(len(rows), 2)  # header + 1 record
                self.assertEqual(len(rows[0]), 36)  # 36 columns

                # Verify header
                self.assertEqual(rows[0][0], "№")
                self.assertEqual(rows[0][1], "Страница")
                self.assertEqual(rows[0][7], "Имя реб. (совр. орф.)")
                self.assertEqual(rows[0][13], "Отец: Имя (совр. орф.)")
                self.assertEqual(rows[0][29], "Священник: ФИО (ориг.)")
                self.assertEqual(rows[0][30], "Дьякон: ФИО (ориг.)")
                self.assertEqual(rows[0][31], "Дьячок: ФИО (ориг.)")
                self.assertEqual(rows[0][32], "Пономарь: ФИО (ориг.)")
                self.assertEqual(rows[0][33], "Родственники")
                self.assertEqual(rows[0][34], "Комментарий")
                self.assertEqual(rows[0][35], "Имена в оригинале")

                # Verify data
                data = rows[1]
                self.assertEqual(data[0], "1")  # record number
                self.assertEqual(data[1], "")  # page (empty)
                self.assertEqual(data[2], Gender.MALE)  # gender
                self.assertEqual(data[3], "15")  # birth day
                self.assertEqual(data[4], "6")  # birth month
                self.assertEqual(data[13], "Петр")  # father name modern
                # Clergy fields empty (no clergy in this record)
                self.assertEqual(data[29], "")  # priest
                self.assertEqual(data[30], "")  # deacon
                self.assertEqual(data[31], "")  # dyachok
                self.assertEqual(data[32], "")  # sexton
                # Verify orig_names_str contains original names
                self.assertIn("Іоаннъ", data[35])  # child name in orig_names
                self.assertIn("Петръ", data[35])  # father name in orig_names

            finally:
                os.chdir(original_cwd)

    def test_csv_export_with_missing_data(self):
        """Test CSV export with partial/missing data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Birth with no mother and only one godparent
            child = person("Петръ", gender=Gender.MALE)
            father = person("Іоаннъ", patr_orig="Федоровъ", gender=Gender.MALE)
            god1 = person("Василій", patr_orig="Сидоровъ", gender=Gender.MALE)

            b = birth(2, Gender.MALE, 20, 21, Month.NOVEMBER, Month.NOVEMBER, child, father, None, god1, None, comment="Мать не указана")
            br = birth_records("A", "F", "I", "C", "Village", "Ch", 1805, b,
                               defaults=RecordDefaults(residence="Village", status_male="статус"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = br.export(BirthRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                # Verify mother fields are empty
                self.assertEqual(data[17], "")  # mother status
                self.assertEqual(data[18], "")  # mother surname
                self.assertEqual(data[19], "")  # mother name

                # Verify godparent2 fields are empty
                self.assertEqual(data[25], "")  # godparent2 status
                self.assertEqual(data[27], "")  # godparent2 FIO sovr. orf.

                # Clergy fields empty (no clergy in this record)
                self.assertEqual(data[29], "")  # priest
                self.assertEqual(data[30], "")  # deacon
                self.assertEqual(data[31], "")  # dyachok
                self.assertEqual(data[32], "")  # sexton

                # Verify comment includes auto-generated message
                comment = data[34]
                self.assertIn("Мать не указана", comment)

            finally:
                os.chdir(original_cwd)

    def test_csv_export_multiple_records(self):
        """Test CSV export with multiple birth records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            b1 = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, person("Иван"), person("Петр"), person("Мария"), person("Алексей"), person("Анна"))
            b2 = birth(2, Gender.FEMALE, 3, 4, Month.FEBRUARY, Month.FEBRUARY, person("Дарья"), person("Яков"), person("Екатерина"), person("Федор"), person("Ксения"))
            b3 = birth(3, Gender.MALE, 5, 6, Month.MARCH, Month.MARCH, person("Михаил"), person("Андрей"), person("Мария"), person("Григорий"), person("Евдокия"))

            br = birth_records("A", "F", "I", "C", "V", "Ch", 1800, b1, b2, b3,
                               defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = br.export(BirthRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                # Header + 3 records
                self.assertEqual(len(rows), 4)

                # Verify record numbers
                self.assertEqual(rows[1][0], "1")
                self.assertEqual(rows[2][0], "2")
                self.assertEqual(rows[3][0], "3")

            finally:
                os.chdir(original_cwd)

    def test_birth_records_export_method(self):
        """Test BirthRecords.export() method directly."""
        from verso.ru.exporters.csv import BirthRecordsCsvExporter

        b = birth(1, Gender.MALE, 10, 11, Month.MAY, Month.MAY, person("Иван"), person("Федор"), person("Мария"), person("Яков"), person("Анна"))
        br = birth_records("A", "F", "I", "C", "V", "Ch", 1800, b,
                           defaults=RecordDefaults(residence="V", status_male="s"))

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                exporter = BirthRecordsCsvExporter()
                result = br.export(exporter)

                # Verify result is a file path
                self.assertIsInstance(result, str)
                self.assertTrue(os.path.exists(result))

            finally:
                os.chdir(original_cwd)

    def test_csv_person_without_patronymic(self):
        """Test CSV export with persons missing patronymics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            child = person("Іоаннъ", gender=Gender.MALE)
            father = person("Петръ", gender=Gender.MALE)  # No patronymic
            mother = person("Марія", patr_orig="Иванова", gender=Gender.FEMALE)

            b = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, child, father, mother, None, None)
            br = birth_records("A", "F", "I", "C", "V", "Ch", 1800, b,
                               defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = br.export(BirthRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                self.assertEqual(data[14], "")  # father patronymic modern - empty

                # Verify orig_names_str handles missing patronymic
                orig_names = data[35]
                self.assertIn("Іоаннъ", orig_names)
                self.assertIn("Петръ", orig_names)
                self.assertIn("Марія Иванова", orig_names)

            finally:
                os.chdir(original_cwd)

    def test_birth_with_page_number(self):
        """Test birth record with page number."""
        b1 = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY, person("Иван"), person("Петр"), person("Мария"), person("Алексей"), person("Анна"),
                   page="1")
        self.assertEqual(b1.page, "1")

        b2 = birth(2, Gender.FEMALE, 3, 4, Month.FEBRUARY, Month.FEBRUARY, person("Дарья"), person("Яков"), person("Екатерина"), person("Федор"), person("Ксения"),
                   page="1об")
        self.assertEqual(b2.page, "1об")

        b3 = birth(3, Gender.MALE, 5, 6, Month.MARCH, Month.MARCH, person("Михаил"), person("Андрей"), person("Мария"), person("Григорий"), person("Евдокия"))
        self.assertIsNone(b3.page)

    def test_month_enum_usage(self):
        """Test that Month enum can be used instead of int for month values."""
        child = Person("Иван", name_modern_orth="Иван")
        father = Person("Петр", name_modern_orth="Петр")
        mother = Person("Мария", name_modern_orth="Мария")

        # Test with Month enum
        b = Birth(1, Gender.MALE, 15, 16, Month.MARCH, Month.MARCH, child, father, mother, None, None)

        # Verify month values are equal to both enum and int
        self.assertEqual(b.b_month, 3)
        self.assertEqual(b.b_month, Month.MARCH)
        self.assertEqual(b.k_month, 3)
        self.assertEqual(b.k_month, Month.MARCH)

    def test_get_birth_location_prefers_father_then_mother_then_default(self):
        # Father has explicit residence — wins over mother and default.
        b = birth(1, Gender.MALE, 10, 11,
                  child=person("Иван"),
                  father=person("Петр", "Сидоров", residence="Горюхино"),
                  mother=person("Анна", "Петрова", residence="Алгасово"))
        self.assertEqual(b.get_birth_location(default="Собакевичево"), "Горюхино")

        # Father has no residence — fall to mother.
        b = birth(1, Gender.FEMALE, 10, 11,
                  child=person("Мария"),
                  father=person("Петр", "Сидоров"),
                  mother=person("Анна", "Петрова", residence="Алгасово"))
        self.assertEqual(b.get_birth_location(default="Собакевичево"), "Алгасово")

        # Neither parent has residence — caller default wins.
        b = birth(1, Gender.MALE, 10, 11,
                  child=person("Иван"),
                  father=person("Петр", "Сидоров"))
        self.assertEqual(b.get_birth_location(default="Собакевичево"), "Собакевичево")

        # No parents at all — default wins.
        b = birth(1, Gender.MALE, 10, 11, child=person("Иван"))
        self.assertEqual(b.get_birth_location(default="Собакевичево"), "Собакевичево")

        # No default provided and no residences — None.
        b = birth(1, Gender.MALE, 10, 11, child=person("Иван"))
        self.assertIsNone(b.get_birth_location())


class TestBirthMonthHelper(unittest.TestCase):
    def test_birth_month_sets_months(self):
        """Test that birth_month helper sets birth and christening months."""
        # Create births without month specified
        b1 = birth(1, Gender.MALE, 15, 16, child=person("Иван"), father=person("Петр"), mother=person("Мария"), god_parent1=None, god_parent2=None)
        b2 = birth(2, Gender.FEMALE, 20, 21, child=person("Дарья"), father=person("Яков"), mother=person("Екатерина"), god_parent1=None, god_parent2=None)

        # Group by month
        march_births = birth_month(Month.MARCH, b1, b2)

        # Verify returns list
        self.assertIsInstance(march_births, list)
        self.assertEqual(len(march_births), 2)

        # Verify months are set
        self.assertEqual(march_births[0].b_month, Month.MARCH)
        self.assertEqual(march_births[0].k_month, Month.MARCH)
        self.assertEqual(march_births[1].b_month, Month.MARCH)
        self.assertEqual(march_births[1].k_month, Month.MARCH)

    def test_birth_month_deep_copies(self):
        """Test that birth_month creates deep copies."""
        b1 = birth(1, Gender.MALE, 15, 16, child=person("Иван"), father=person("Петр"), mother=person("Мария"), god_parent1=None, god_parent2=None)

        march_births = birth_month(Month.MARCH, b1)

        # Verify it's a different object
        self.assertIsNot(march_births[0], b1)
        self.assertIsNot(march_births[0].child, b1.child)

    def test_birth_month_preserves_existing_months(self):
        """Test that birth_month doesn't overwrite existing months."""
        # Create birth with months already set
        b1 = birth(1, Gender.MALE, 15, 16, Month.APRIL, Month.APRIL, child=person("Иван"), father=person("Петр"), mother=person("Мария"), god_parent1=None, god_parent2=None)

        # Try to group by March
        march_births = birth_month(Month.MARCH, b1)

        # Original months should be preserved
        self.assertEqual(march_births[0].b_month, Month.APRIL)
        self.assertEqual(march_births[0].k_month, Month.APRIL)


class TestRelatives(unittest.TestCase):
    def test_relative_class(self):
        p = person("Спиридонъ", patr_orig="Петровъ")
        rel = Relative(p, Relationship.FATHER, "мать")
        self.assertIs(rel.person, p)
        self.assertEqual(rel.relationship, Relationship.FATHER)
        self.assertEqual(rel.relationship_ref, "мать")

    def test_relative_factory(self):
        p = person("Спиридонъ", patr_orig="Петровъ")
        rel = relative(p, Relationship.FATHER, "мать")
        self.assertIsInstance(rel, Relative)
        self.assertEqual(rel.relationship, Relationship.FATHER)
        self.assertEqual(rel.relationship_ref, "мать")

    def test_birth_default_relatives_empty(self):
        b = birth(1, Gender.MALE, child=person("Иван"), father=person("Петр"), mother=person("Мария"),
                  god_parent1=None, god_parent2=None)
        self.assertEqual(b.relatives, [])

    def test_birth_relatives_none_becomes_empty_list(self):
        b = birth(1, Gender.MALE, child=person("Иван"), father=person("Петр"), mother=person("Мария"),
                  god_parent1=None, god_parent2=None, relatives=None)
        self.assertIsInstance(b.relatives, list)
        self.assertEqual(b.relatives, [])

    def test_birth_with_relatives(self):
        p = person("Спиридонъ", patr_orig="Петровъ")
        b = birth(1, Gender.MALE, child=person("Иван"), father=None, mother=person("Мария"),
                  god_parent1=None, god_parent2=None,
                  relatives=[relative(p, Relationship.FATHER, "мать")])
        self.assertEqual(len(b.relatives), 1)
        self.assertEqual(b.relatives[0].relationship, Relationship.FATHER)
        self.assertEqual(b.relatives[0].relationship_ref, "мать")

    def test_csv_export_with_relatives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = person("Спиридонъ", patr_orig="Петровъ", gender=Gender.MALE)
            child = person("Іоаннъ", gender=Gender.MALE)
            mother = person("Марія", gender=Gender.FEMALE)
            b = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY,
                      child=child, father=None, mother=mother,
                      god_parent1=None, god_parent2=None,
                      relatives=[relative(p, Relationship.FATHER, "мать")])
            br = birth_records("A", "F", "I", "C", "V", "Ch", 1800, b)

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = br.export(BirthRecordsCsvExporter())
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                data = rows[1]
                self.assertEqual(data[33], "отец мать: Спиридонъ Петровъ")
                self.assertIn("Спиридонъ Петровъ", data[35])
            finally:
                os.chdir(original_cwd)

    def test_csv_export_relatives_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            child = person("Іоаннъ", gender=Gender.MALE)
            father = person("Петръ", gender=Gender.MALE)
            b = birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY,
                      child=child, father=father, mother=None,
                      god_parent1=None, god_parent2=None)
            br = birth_records("A", "F", "I", "C", "V", "Ch", 1800, b)

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = br.export(BirthRecordsCsvExporter())
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                data = rows[1]
                self.assertEqual(data[33], "")
            finally:
                os.chdir(original_cwd)


class TestBirthGenderValidation(unittest.TestCase):
    def _make_birth(self, record_gender, child=None, father=None, mother=None):
        return Birth(1, record_gender, 1, 2, Month.JANUARY, Month.JANUARY, child, father, mother, None, None)

    def test_male_record_female_child_name_raises(self):
        with self.assertRaises(ValueError):
            self._make_birth(Gender.MALE, child=person("Мария"))

    def test_female_record_male_child_name_raises(self):
        with self.assertRaises(ValueError):
            self._make_birth(Gender.FEMALE, child=person("Иван"))

    def test_female_named_father_raises(self):
        with self.assertRaises(ValueError):
            self._make_birth(Gender.MALE, child=person("Иван"), father=person("Мария"))

    def test_male_named_mother_raises(self):
        with self.assertRaises(ValueError):
            self._make_birth(Gender.MALE, child=person("Иван"), mother=person("Иван"))

    def test_explicit_female_child_with_male_record_raises(self):
        with self.assertRaises(ValueError):
            self._make_birth(Gender.MALE, child=person("?", gender=Gender.FEMALE))

    def test_correct_genders_no_raise(self):
        b = self._make_birth(Gender.MALE, child=person("Иван"), father=person("Петр"), mother=person("Мария"))
        self.assertEqual(b.child.gender, Gender.MALE)
        self.assertEqual(b.father.gender, Gender.MALE)
        self.assertEqual(b.mother.gender, Gender.FEMALE)

    def test_unknown_child_name_no_raise(self):
        b = self._make_birth(Gender.MALE, child=person("?"))
        self.assertEqual(b.child.gender, Gender.MALE)

    def test_error_message_contains_record_num_and_name_child(self):
        with self.assertRaises(ValueError) as ctx:
            self._make_birth(Gender.MALE, child=person("Мария"))
        msg = str(ctx.exception)
        self.assertIn("1", msg)
        self.assertIn("child", msg)

    def test_error_message_father(self):
        with self.assertRaises(ValueError) as ctx:
            self._make_birth(Gender.MALE, child=person("Иван"), father=person("Мария"))
        self.assertIn("father", str(ctx.exception))

    def test_error_message_mother(self):
        with self.assertRaises(ValueError) as ctx:
            self._make_birth(Gender.MALE, child=person("Иван"), mother=person("Иван"))
        self.assertIn("mother", str(ctx.exception))

    def test_birth_factory_also_raises(self):
        with self.assertRaises(ValueError):
            birth(1, Gender.MALE, 1, 2, Month.JANUARY, Month.JANUARY,
                  child=person("Мария"), father=None, mother=None)


class TestBirthRelativesGenderValidation(unittest.TestCase):
    def test_relative_father_male_passes(self):
        b = birth(1, Gender.MALE, child=person("Иван"),
                  relatives=[relative(person("Петр"), Relationship.FATHER)])
        self.assertEqual(b.relatives[0].person.gender, Gender.MALE)

    def test_relative_father_female_raises(self):
        with self.assertRaises(ValueError) as ctx:
            birth(1, Gender.MALE, child=person("Иван"),
                  relatives=[relative(person("Мария"), Relationship.FATHER)])
        msg = str(ctx.exception)
        self.assertIn("relative", msg)
        self.assertIn("MALE", msg)

    def test_relative_mother_male_raises(self):
        with self.assertRaises(ValueError) as ctx:
            birth(1, Gender.MALE, child=person("Иван"),
                  relatives=[relative(person("Петр"), Relationship.MOTHER)])
        msg = str(ctx.exception)
        self.assertIn("relative", msg)
        self.assertIn("FEMALE", msg)

    def test_relative_unknown_name_no_raise(self):
        b = birth(1, Gender.MALE, child=person("Иван"),
                  relatives=[relative(person("?"), Relationship.FATHER)])
        self.assertEqual(b.relatives[0].person.gender, Gender.MALE)

    def test_birth_reviewed_is_unstated_until_its_record_set_resolves_it(self):
        # `None`, so a `page(reviewed=…)` around it can reach it; the record
        # set then resolves what is left to its own default, `True`.
        b = birth(1, Gender.MALE, child=person("Иван"))
        self.assertIsNone(b.reviewed)
        records = birth_records("A", "1", "1", "1", "Тестовка", "Никольская", 1880, b)
        self.assertIs(True, records.records[0].reviewed)

    def test_birth_reviewed_false_propagates_through_factory(self):
        b = birth(1, Gender.MALE, child=person("Иван"), reviewed=False)
        self.assertFalse(b.reviewed)


class TestChildStatusInheritance(unittest.TestCase):
    """Birth.__init__ derives a statusless child's сословие from the consulted
    parent (father with a status, else mother) via statuses.child_status_for."""

    def test_son_and_daughter_derive_from_father(self):
        from corpus.statuses import SOBAKEVICH_UK_PEASANT_DAUGHTER, SOBAKEVICH_UK_PEASANT_MALE, SOBAKEVICH_UK_PEASANT_SON
        b = birth(1, Gender.MALE, child=person("Иван"),
                  father=person("Пётр", status=SOBAKEVICH_UK_PEASANT_MALE))
        self.assertEqual(b.child.status, SOBAKEVICH_UK_PEASANT_SON)
        g = birth(2, Gender.FEMALE, child=person("Анна"),
                  father=person("Пётр", status=SOBAKEVICH_UK_PEASANT_MALE))
        self.assertEqual(g.child.status, SOBAKEVICH_UK_PEASANT_DAUGHTER)

    def test_mother_is_the_fallback_when_father_absent(self):
        from verso.ru.domain.statuses import YASAK_PEASANT_GIRL, YASAK_PEASANT_SON
        b = birth(1, Gender.MALE, child=person("Фёдор"),
                  mother=person("Дарья", status=YASAK_PEASANT_GIRL))
        self.assertEqual(b.child.status, YASAK_PEASANT_SON)

    def test_father_with_out_of_scope_status_blocks_mother_fallback(self):
        """A clergy household's child must not inherit the mother's peasant
        estate — the father's status defines the household."""
        from verso.ru.domain.statuses import DYACHOK, YASAK_PEASANT_FEMALE
        b = birth(1, Gender.MALE, child=person("Семён"),
                  father=person("Пётр", status=DYACHOK),
                  mother=person("Дарья", status=YASAK_PEASANT_FEMALE))
        self.assertIsNone(b.child.status)

    def test_proprietor_peasants_child_is_a_peasant_child(self):
        from verso.ru.domain.statuses import (
            PEASANT_DAUGHTER, PEASANT_SON, PROPRIETOR_PEASANT_MALE)
        b = birth(1, Gender.MALE, child=person("Иван"),
                  father=person("Пётр", status=PROPRIETOR_PEASANT_MALE))
        self.assertEqual(b.child.status, PEASANT_SON)
        g = birth(2, Gender.FEMALE, child=person("Дарья"),
                  father=person("Никита", status=PROPRIETOR_PEASANT_MALE))
        self.assertEqual(g.child.status, PEASANT_DAUGHTER)

    def test_explicit_child_status_is_never_overwritten(self):
        from corpus.statuses import SOBAKEVICH_UK_PEASANT_MALE
        from verso.ru.domain.statuses import YASAK_PEASANT_SON
        b = birth(1, Gender.MALE,
                  child=person("Яков", status=YASAK_PEASANT_SON),
                  father=person("Пётр", status=SOBAKEVICH_UK_PEASANT_MALE))
        self.assertEqual(b.child.status, YASAK_PEASANT_SON)

    def test_record_defaults_do_not_override_the_derived_status(self):
        """birth_records applies RecordDefaults AFTER __init__, so the derived
        сословие beats the parish default — same ordering as residence."""
        from corpus.statuses import MANILOV_KF_PEASANT_MALE, MANILOV_KF_PEASANT_SON
        from verso.ru.domain.statuses import YASAK_PEASANT_FEMALE, YASAK_PEASANT_MALE
        r = birth_records(
            "a", "f", "i", "c", "Горюхино", "Ц", 1830,
            birth(1, Gender.MALE, child=person("Иван"),
                  father=person("Пётр", status=MANILOV_KF_PEASANT_MALE)),
            defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE,
                                    status_female=YASAK_PEASANT_FEMALE))
        self.assertEqual(r.records[0].child.status, MANILOV_KF_PEASANT_SON)

    def test_no_parents_keeps_parish_default_behaviour(self):
        from verso.ru.domain.statuses import YASAK_PEASANT_MALE
        r = birth_records(
            "a", "f", "i", "c", "Горюхино", "Ц", 1830,
            birth(1, Gender.MALE, child=person("Илья")),
            defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE))
        self.assertEqual(r.records[0].child.status, YASAK_PEASANT_MALE)

    def test_free_text_parent_status_resolves(self):
        from verso.ru.domain.statuses import YASAK_PEASANT_SON
        b = birth(1, Gender.MALE, child=person("Иван"),
                  father=person("Пётр", status="ясачный крестьянин"))
        self.assertEqual(b.child.status, YASAK_PEASANT_SON)

    def test_unknown_free_text_parent_status_derives_nothing(self):
        b = birth(1, Gender.MALE, child=person("Иван"),
                  father=person("Пётр", status="крестьянин помещика Кузьмы Тентетникова"))
        self.assertIsNone(b.child.status)


class TestMotherSurnameInheritance(unittest.TestCase):
    def test_mother_without_surname_inherits_feminized_father_surname(self):
        b = birth(
            1, Gender.MALE,
            child=person("Иван"),
            father=person("Петр", last_name_orig="Сидоров"),
            mother=person("Мария"),
        )
        self.assertEqual(b.mother.last_name_modern, "Сидорова")

    def test_inherited_mother_surname_marks_last_name_in_book_false(self):
        b = birth(
            1, Gender.MALE,
            child=person("Иван"),
            father=person("Петр", last_name_orig="Сидоров"),
            mother=person("Мария"),
        )
        self.assertFalse(b.mother.last_name_in_book)

    def test_mother_with_explicit_surname_is_not_overridden(self):
        b = birth(
            1, Gender.MALE,
            child=person("Иван"),
            father=person("Петр", last_name_orig="Сидоров"),
            mother=person("Мария", last_name_orig="Иванова"),
        )
        self.assertEqual(b.mother.last_name, "Иванова")
        self.assertEqual(b.mother.last_name_modern, "Иванова")
        self.assertTrue(b.mother.last_name_in_book)

    def test_mother_without_father_keeps_no_surname(self):
        b = birth(
            1, Gender.MALE,
            child=person("Иван"),
            mother=person("Мария"),
        )
        self.assertIsNone(b.mother.last_name)
        self.assertIsNone(b.mother.last_name_modern)




class TestGodparentSurnameFromRelative(unittest.TestCase):
    """A godparent with no surname inherits from the father or husband named
    as their relative — the deaths.py rule, applied to births."""

    def test_godparent_takes_the_fathers_surname(self):
        b = birth(1, Gender.MALE, 3, 5,
                  child=person("Иванъ"),
                  god_parent1=person("Тарасъ", "Ивановъ"),
                  relatives=[relative(person("Иванъ", "Петровъ", "Абрамовъ"),
                                      Relationship.FATHER, "восприемника №1")])
        self.assertEqual(b.god_parent1.last_name_modern, "Абрамов")
        self.assertFalse(b.god_parent1.last_name_in_book)

    def test_godmother_takes_her_husbands_feminized_surname(self):
        b = birth(1, Gender.MALE, 3, 5,
                  child=person("Иванъ"),
                  god_parent2=person("Матрена", "Степанова"),
                  relatives=[relative(person("Никита", "Ивановъ", "Подушкинъ"),
                                      Relationship.HUSBAND, "восприемника №2")])
        self.assertEqual(b.god_parent2.last_name_modern, "Подушкина")
        self.assertFalse(b.god_parent2.last_name_in_book)

    def test_a_godparent_with_a_surname_keeps_it(self):
        b = birth(1, Gender.MALE, 3, 5,
                  child=person("Иванъ"),
                  god_parent1=person("Тарасъ", "Ивановъ", "Мешочкинъ"),
                  relatives=[relative(person("Иванъ", "Петровъ", "Абрамовъ"),
                                      Relationship.FATHER, "восприемника №1")])
        self.assertEqual(b.god_parent1.last_name, "Мешочкинъ")

    def test_a_relative_refd_to_another_godparent_is_not_used(self):
        b = birth(1, Gender.MALE, 3, 5,
                  child=person("Иванъ"),
                  god_parent1=person("Тарасъ", "Ивановъ"),
                  god_parent2=person("Матрена", "Степанова"),
                  relatives=[relative(person("Иванъ", "Петровъ", "Абрамовъ"),
                                      Relationship.FATHER, "восприемника №2")])
        self.assertFalse(b.god_parent1.last_name_modern)


class TestInfantPatronymic(unittest.TestCase):
    """A newborn takes the father's name as its patronymic, both forms, as a deceased child does (В10)."""

    def _birth(self, gender=Gender.MALE, child=None, father=None):
        return Birth(1, gender, 5, 6, Month.MAY, Month.MAY,
                     child=child or person("Иванъ" if gender == Gender.MALE else "Марія"),
                     father=father if father is not None else person("Ѳома", "Петровъ"))

    def test_son_and_daughter(self):
        son, daughter = self._birth(), self._birth(Gender.FEMALE)
        self.assertEqual((son.child.patr_orig, son.child.patr_old, son.child.patr_modern), (None, "Фомин", "Фомич"))
        self.assertEqual((daughter.child.patr_old, daughter.child.patr_modern), ("Фомина", "Фоминична"))
        self.assertTrue(son.child_patronymic_derived())

    def test_a_written_patronymic_stays(self):
        b = self._birth(child=person("Иванъ", "Сергѣевъ"))
        self.assertEqual((b.child.patr_old, b.child.patr_modern), ("Сергеев", "Сергеевич"))
        self.assertFalse(b.child_patronymic_derived())

    def test_the_written_child_has_none_and_the_record_keeps_it(self):
        b = self._birth()
        bare = b.written_child()
        self.assertIsNot(bare, b.child)
        self.assertEqual((bare.patr_old, bare.patr_modern, bare.name_orig), ("", "", "Иванъ"))
        self.assertEqual(b.child.patr_modern, "Фомич")

    def test_a_patronymic_written_in_its_modern_spelling_is_the_records(self):
        """`person("Иванъ", patr_old="Фомин")` writes one: it is no derivation, though it reads the same."""
        b = self._birth(child=person("Иванъ", patr_old="Фомин"))
        self.assertFalse(b.child_patronymic_derived())
        self.assertIs(b.written_child(), b.child)

    def test_none_without_a_father_or_his_name(self):
        no_father = Birth(1, Gender.MALE, 5, 6, Month.MAY, Month.MAY, child=person("Иванъ"))
        unread = self._birth(father=person("?"))
        for b in (no_father, unread):
            self.assertEqual((b.child.patr_old, b.child.patr_modern), ("", ""))
            self.assertFalse(b.child_patronymic_derived())


if __name__ == '__main__':
    unittest.main()
