import csv
import os
import tempfile
import unittest
from calendar import Month

from verso.ru.exporters.csv import DeathRecordsCsvExporter
from verso.ru.dsl.records.deaths import Death, DeathRecords, death, death_records, death_month
from verso.ru.domain import Gender, RecordDefaults, person
from verso.ru.relationship import Relationship, relative


class TestDeathGenderAssignment(unittest.TestCase):
    def test_death_automatic_gender_assignment(self):
        """Test that gender is automatically assigned to deceased, and auto-detected for others."""
        deceased_person = person("Иван", patr_orig="Петров")
        relative_person = person("Мария", patr_orig="Иванова")
        witness1_person = person("Федор", patr_orig="Сидоров")
        witness2_person = person("Василий", patr_orig="Михайлов")

        d = Death(1, Gender.MALE, 15, 16, 6, 6, deceased_person, relatives=[relative(relative_person, None)], witness1=witness1_person, witness2=witness2_person)

        self.assertEqual(d.deceased.gender, Gender.MALE)
        # Relative and witnesses get gender auto-detected from names
        self.assertEqual(d.relative.gender, Gender.FEMALE)  # Мария is female
        self.assertEqual(d.witness1.gender, Gender.MALE)  # Федор is male
        self.assertEqual(d.witness2.gender, Gender.MALE)  # Василий is male


class TestDeathGenderValidation(unittest.TestCase):
    def test_male_record_female_explicit_deceased_raises(self):
        """Record gender MALE but deceased has explicit gender FEMALE → ValueError."""
        with self.assertRaises(ValueError) as ctx:
            Death(1, Gender.MALE, 15, 16, 6, 6, person("Мария", gender=Gender.FEMALE))
        msg = str(ctx.exception)
        self.assertIn("record gender", msg)
        self.assertIn("deceased gender", msg)

    def test_female_record_male_explicit_deceased_raises(self):
        """Record gender FEMALE but deceased has explicit gender MALE → ValueError."""
        with self.assertRaises(ValueError) as ctx:
            Death(5, Gender.FEMALE, 10, 11, 3, 3, person("Иван", gender=Gender.MALE))
        msg = str(ctx.exception)
        self.assertIn("record gender", msg)
        self.assertIn("deceased gender", msg)

    def test_error_message_contains_record_num_and_name(self):
        """Error message includes the record number and deceased name."""
        with self.assertRaises(ValueError) as ctx:
            Death(42, Gender.MALE, 1, 2, 1, 1, person("Анна", gender=Gender.FEMALE))
        msg = str(ctx.exception)
        self.assertIn("42", msg)
        self.assertIn("Анна", msg)

    def test_male_record_male_explicit_deceased_no_raise(self):
        """Record gender MALE and deceased has explicit gender MALE → no error."""
        d = Death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", gender=Gender.MALE))
        self.assertEqual(d.gender, Gender.MALE)

    def test_female_record_female_explicit_deceased_no_raise(self):
        """Record gender FEMALE and deceased has explicit gender FEMALE → no error."""
        d = Death(2, Gender.FEMALE, 10, 11, 3, 3, person("Мария", gender=Gender.FEMALE))
        self.assertEqual(d.gender, Gender.FEMALE)

    def test_male_record_auto_detected_female_name_raises(self):
        """Name-detected gender FEMALE conflicts with record gender MALE → ValueError."""
        with self.assertRaises(ValueError):
            Death(1, Gender.MALE, 15, 16, 6, 6, person("Мария"))

    def test_female_record_auto_detected_male_name_raises(self):
        """Name-detected gender MALE conflicts with record gender FEMALE → ValueError."""
        with self.assertRaises(ValueError):
            Death(1, Gender.FEMALE, 15, 16, 6, 6, person("Иван"))

    def test_no_deceased_no_raise(self):
        """No deceased person → no validation, no error."""
        d = Death(1, Gender.MALE, 15, 16, 6, 6, None)
        self.assertIsNone(d.deceased)

    def test_deceased_no_detectable_gender_no_raise(self):
        """Deceased person has no detectable gender → no validation error."""
        d = Death(1, Gender.MALE, 15, 16, 6, 6, person("?"))
        self.assertIsNotNone(d.deceased)

    def test_death_factory_also_raises(self):
        """death() factory propagates the ValueError from Death.__init__."""
        with self.assertRaises(ValueError):
            death(3, Gender.MALE, 5, 6, 2, 2, person("Прасковья", gender=Gender.FEMALE))


class TestDeathAgeField(unittest.TestCase):
    def test_death_with_age(self):
        """Test death record with age specified."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), age=45, witness1=None, witness2=None)
        self.assertEqual(d.age, 45)

    def test_death_without_age(self):
        """Test death record without age."""
        d = death(1, Gender.FEMALE, 20, 21, 7, 7, person("Мария", patr_orig="Иванова"), witness1=None, witness2=None)
        self.assertIsNone(d.age)


class TestDeathRelationshipField(unittest.TestCase):
    def test_death_with_relationship(self):
        """Test death record with relationship field."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), relatives=[relative(person("Мария", patr_orig="Иванова"), Relationship.WIFE)], witness1=None, witness2=None)
        self.assertEqual(d.relationship, "жена")

    def test_death_without_relationship(self):
        """Test death record without relationship."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), witness1=None, witness2=None)
        self.assertIsNone(d.relationship)


class TestDeathSurnameInheritance(unittest.TestCase):
    """Deceased children/wives inherit a surname from a related father/husband
    when they have none of their own (mirrors births.py)."""

    def test_deceased_son_inherits_father_surname(self):
        d = death(1, Gender.MALE, deceased=person("Петр"),
                  relatives=[relative(person("Семен", "Васильев", "Мижуев"), Relationship.FATHER)])
        self.assertEqual(d.deceased.last_name_modern, "Мижуев")
        # As-written form stays empty: the book recorded no surname.
        self.assertIsNone(d.deceased.last_name)
        self.assertIsNone(d.deceased.birth_last_name_modern)

    def test_deceased_daughter_inherits_feminized_father_surname(self):
        d = death(1, Gender.FEMALE, deceased=person("Марья"),
                  relatives=[relative(person("Максим", "Федоров", "Мижуев"), Relationship.FATHER)])
        # Daughters route the inherited surname to maiden_name.
        self.assertEqual(d.deceased.birth_last_name_modern, "Мижуева")
        self.assertIsNone(d.deceased.last_name_modern)
        self.assertIsNone(d.deceased.last_name)

    def test_deceased_wife_inherits_feminized_husband_surname(self):
        d = death(1, Gender.FEMALE, deceased=person("Анна"),
                  relatives=[relative(person("Иван", "Петров", "Мижуев"), Relationship.HUSBAND)])
        self.assertEqual(d.deceased.last_name_modern, "Мижуева")
        self.assertFalse(d.deceased.last_name_in_book)
        self.assertIsNone(d.deceased.last_name)

    def test_existing_deceased_surname_not_overwritten(self):
        d = death(1, Gender.MALE, deceased=person("Петр", last_name_orig="Прорехин"),
                  relatives=[relative(person("Семен", "Васильев", "Мижуев"), Relationship.FATHER)])
        self.assertEqual(d.deceased.last_name_modern, "Прорехин")
        self.assertEqual(d.deceased.last_name, "Прорехин")

    def test_no_inheritance_when_father_has_no_surname(self):
        d = death(1, Gender.MALE, deceased=person("Петр"),
                  relatives=[relative(person("Семен", "Васильев"), Relationship.FATHER)])
        self.assertIsNone(d.deceased.last_name_modern)
        self.assertIsNone(d.deceased.birth_last_name_modern)


class TestDeathDSLHelpers(unittest.TestCase):
    def test_death_dsl_helper(self):
        """Test death() factory function."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), age=45, relatives=[relative(person("Мария", patr_orig="Иванова"), Relationship.WIFE)],
                  witness1=person("Федор", patr_orig="Сидоров"), witness2=person("Василий", patr_orig="Михайлов"), comment="Test comment")
        self.assertIsInstance(d, Death)
        self.assertEqual(d.record_num, 1)
        self.assertEqual(d.gender, Gender.MALE)
        self.assertEqual(d.age, 45)
        self.assertEqual(d.relationship, "жена")
        self.assertEqual(d.comment, "Test comment")

    def test_death_records_dsl_helper(self):
        """Test death_records() factory function."""
        d1 = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=None, witness2=None)
        d2 = death(2, Gender.FEMALE, 20, 21, 7, 7, person("Мария"), witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d1, d2
        )

        self.assertIsInstance(dr, DeathRecords)
        self.assertEqual(len(dr.records), 2)
        self.assertEqual(dr.year, 1804)
        self.assertEqual(dr.village, "Заманиловка")


class TestDeathRecordsCollection(unittest.TestCase):
    def test_death_records_collection(self):
        """Test creating a collection of death records."""
        d1 = Death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=None, witness2=None)
        d2 = Death(2, Gender.FEMALE, 20, 21, 7, 7, person("Мария"), witness1=None, witness2=None)
        d3 = Death(3, Gender.MALE, 25, 26, 8, 8, person("Петр"), witness1=None, witness2=None)

        dr = DeathRecords(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804,
            [d1, d2, d3]
        )

        self.assertEqual(len(dr.records), 3)
        self.assertEqual(dr.records[0].deceased.name_orig, "Иван")
        self.assertEqual(dr.records[1].deceased.name_orig, "Мария")
        self.assertEqual(dr.records[2].deceased.name_orig, "Петр")


class TestDeathRecordsDefaults(unittest.TestCase):
    def test_death_records_defaults(self):
        """Test RecordDefaults application to death records."""
        d1 = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=None, witness2=None)
        d2 = death(2, Gender.FEMALE, 20, 21, 7, 7, person("Мария"), witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d1, d2,
            defaults=RecordDefaults(
                residence="Заманиловка",
                status_male="крестьянин",
                status_female="крестьянка"
            )
        )

        self.assertEqual(dr.records[0].deceased.residence, "Заманиловка")
        self.assertEqual(dr.records[0].deceased.status, "крестьянин")
        self.assertEqual(dr.records[1].deceased.residence, "Заманиловка")
        self.assertEqual(dr.records[1].deceased.status, "крестьянка")


class TestDeathNonePersons(unittest.TestCase):
    def test_death_none_persons(self):
        """Test death record with missing relative and witnesses."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), witness1=None, witness2=None)
        self.assertIsNotNone(d.deceased)
        self.assertIsNone(d.relative)
        self.assertIsNone(d.witness1)
        self.assertIsNone(d.witness2)


class TestRecordDefaultsApplyToDeath(unittest.TestCase):
    def test_record_defaults_apply_to_death(self):
        """Test RecordDefaults.apply_to_death() method directly."""
        defaults = RecordDefaults(
            residence="Заманиловка",
            status_male="крестьянин",
            status_female="крестьянка"
        )

        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", gender=Gender.MALE), relatives=[relative(person("Мария", gender=Gender.FEMALE), None)], witness1=person("Федор", gender=Gender.MALE), witness2=None)

        defaults.apply_to_death(d)

        self.assertEqual(d.deceased.residence, "Заманиловка")
        self.assertEqual(d.deceased.status, "крестьянин")
        self.assertEqual(d.relative.residence, "Заманиловка")
        self.assertEqual(d.relative.status, "крестьянка")
        self.assertEqual(d.witness1.residence, "Заманиловка")
        self.assertEqual(d.witness1.status, "крестьянин")


class TestDeathCSVExportBasic(unittest.TestCase):
    def test_csv_export_basic(self):
        """Test basic CSV generation with all 37 columns."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров", gender=Gender.MALE), age=45, relatives=[relative(person("Мария", patr_orig="Иванова", gender=Gender.FEMALE), Relationship.WIFE)], witness1=person("Федор", patr_orig="Сидоров", gender=Gender.MALE), witness2=person("Василий", patr_orig="Михайлов", gender=Gender.MALE))

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d,
            defaults=RecordDefaults(
                residence="Заманиловка",
                status_male="крестьянин",
                status_female="крестьянка"
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())
                self.assertTrue(os.path.exists(csv_file))

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                self.assertEqual(len(rows), 2)  # header + 1 record
                self.assertEqual(len(rows[0]), 42)  # 42 columns (incl. 4 clergy)
                self.assertEqual(rows[1][0], '1')  # record number
                self.assertEqual(rows[1][1], '')  # page (empty)
                self.assertEqual(rows[1][2], 'муж')  # gender
                self.assertEqual(rows[1][16], '45')  # age
                self.assertEqual(rows[1][17], 'жена')  # relationship
            finally:
                os.chdir(original_cwd)


class TestDeathCSVExportMissingData(unittest.TestCase):
    def test_csv_export_with_missing_data(self):
        """Test CSV export with missing relative and witnesses."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                # Check that relative and witness fields are empty
                self.assertEqual(rows[1][17], '')  # relationship
                self.assertEqual(rows[1][18], '')  # relative residence
                self.assertEqual(rows[1][26], '')  # witness1 status
                self.assertEqual(rows[1][31], '')  # witness2 status
            finally:
                os.chdir(original_cwd)


class TestDeathCSVExportBurialDateComment(unittest.TestCase):
    def test_csv_export_burial_date_comment(self):
        """Test auto-comment when burial date equals death date."""
        d = death(1, Gender.MALE, 15, 15, 6, 6, person("Иван", patr_orig="Петров"), witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                self.assertIn("Дата погребения не указана, взята дата смерти", rows[1][40])
            finally:
                os.chdir(original_cwd)

    def test_csv_export_burial_date_comment_with_user_comment(self):
        """Test auto-comment combined with user comment."""
        d = death(1, Gender.MALE, 15, 15, 6, 6, person("Иван", patr_orig="Петров"), witness1=None, witness2=None, comment="User comment")

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                comment = rows[1][40]
                self.assertIn("Дата погребения не указана, взята дата смерти", comment)
                self.assertIn("User comment", comment)
            finally:
                os.chdir(original_cwd)


class TestDeathCSVExportWithAge(unittest.TestCase):
    def test_csv_export_with_age(self):
        """Test CSV export with age field."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), age=45, witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                self.assertEqual(rows[1][16], '45')
            finally:
                os.chdir(original_cwd)


class TestDeathCSVExportWithRelationship(unittest.TestCase):
    def test_csv_export_with_relationship(self):
        """Test CSV export with relationship field."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван", patr_orig="Петров"), relatives=[relative(person("Мария", patr_orig="Иванова"), Relationship.WIFE)], witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                self.assertEqual(rows[1][17], 'жена')
            finally:
                os.chdir(original_cwd)


class TestDeathCSVExportMultipleRecords(unittest.TestCase):
    def test_csv_export_multiple_records(self):
        """Test exporting multiple death records."""
        d1 = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=None, witness2=None)
        d2 = death(2, Gender.FEMALE, 20, 21, 7, 7, person("Мария"), witness1=None, witness2=None)
        d3 = death(3, Gender.MALE, 17, 18, 8, 8, person("Фока"), witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d1, d2, d3
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                self.assertEqual(len(rows), 4)  # header + 3 records
                self.assertEqual(rows[1][0], '1')
                self.assertEqual(rows[2][0], '2')
                self.assertEqual(rows[3][0], '3')
            finally:
                os.chdir(original_cwd)


class TestDeathRecordsExportMethod(unittest.TestCase):
    def test_death_records_export_method(self):
        """Test DeathRecords.export() method directly."""
        from verso.ru.exporters.csv import DeathRecordsCsvExporter

        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=None, witness2=None)
        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                exporter = DeathRecordsCsvExporter()
                csv_file = dr.export(exporter)
                self.assertTrue(os.path.exists(csv_file))
            finally:
                os.chdir(original_cwd)


class TestDeathCSVPersonWithoutPatronymic(unittest.TestCase):
    def test_csv_person_without_patronymic(self):
        """Test CSV export with persons missing patronymic."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), relatives=[relative(person("Мария"), None)], witness1=None, witness2=None)

        dr = death_records(
            "ГАТО", "Ф. 181", "Оп. 1", "Д. 123",
            "Заманиловка", "Церковь", 1804, d
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())

                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                self.assertEqual(rows[1][10], 'Иван')  # deceased name
                self.assertEqual(rows[1][11], '')  # deceased patronymic (empty)
                self.assertEqual(rows[1][41], 'Иван; Мария')  # orig names
            finally:
                os.chdir(original_cwd)


class TestDeathEdgeCases(unittest.TestCase):
    def test_death_edge_case_only_deceased(self):
        """Test death record with only deceased, no relative or witnesses."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=None, witness2=None)
        self.assertIsNotNone(d.deceased)
        self.assertIsNone(d.relative)
        self.assertIsNone(d.witness1)
        self.assertIsNone(d.witness2)

    def test_death_edge_case_one_witness(self):
        """Test death record with only one witness."""
        d = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=person("Федор"), witness2=None)
        self.assertIsNotNone(d.deceased)
        self.assertIsNone(d.relative)
        self.assertIsNotNone(d.witness1)
        self.assertIsNone(d.witness2)


class TestDeathClergyFields(unittest.TestCase):
    def test_death_with_clergy(self):
        """Test death record stores clergy fields."""
        d = death(3, Gender.FEMALE, 9, 11,
                  deceased=person("Домна", "Фокина"),
                  age=74,
                  relatives=[relative(person("Несторъ", "Фокинъ"), Relationship.HUSBAND)],
                  witness1=person("Несторъ", "Фокинъ"),
                  witness2=person("Артемій", "Тихоновъ"),
                  priest=person("Василій", "Никифоровъ"),
                  deacon=person("Леонтій", "Матвѣевъ"),
                  dyachok=person("Кириллъ", "Сидоровъ"),
                  sexton=person("Маркелъ", "Прокопьевъ"))
        self.assertEqual(d.priest.name_orig, "Василій")
        self.assertEqual(d.deacon.name_orig, "Леонтій")
        self.assertEqual(d.dyachok.name_orig, "Кириллъ")
        self.assertEqual(d.sexton.name_orig, "Маркелъ")

    def test_death_without_clergy(self):
        """Clergy fields default to None."""
        d = death(1, Gender.MALE, 1, 2, deceased=person("Иван"), witness1=None, witness2=None)
        self.assertIsNone(d.priest)
        self.assertIsNone(d.deacon)
        self.assertIsNone(d.dyachok)
        self.assertIsNone(d.sexton)

    def test_csv_export_clergy_columns(self):
        """Clergy appear in the correct CSV columns (36-39)."""
        d = death(3, Gender.FEMALE, 9, 11,
                  deceased=person("Домна", "Фокина"),
                  priest=person("Василій", "Никифоровъ"),
                  deacon=person("Леонтій", "Матвѣевъ"),
                  dyachok=person("Кириллъ", "Сидоровъ"),
                  sexton=person("Маркелъ", "Прокопьевъ"))
        dr = death_records("А", "Ф", "О", "Д", "Заманиловка", "Церковь", 1812, d)

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())
                with open(csv_file, 'r', encoding='utf-8') as f:
                    rows = list(csv.reader(f))
                self.assertEqual(rows[1][36], "Василій Никифоровъ")
                self.assertEqual(rows[1][37], "Леонтій Матвѣевъ")
                self.assertEqual(rows[1][38], "Кириллъ Сидоровъ")
                self.assertEqual(rows[1][39], "Маркелъ Прокопьевъ")
            finally:
                os.chdir(original_cwd)

    def test_csv_export_clergy_empty_when_absent(self):
        """Clergy columns are empty when not provided."""
        d = death(1, Gender.MALE, 1, 2, deceased=person("Иван"), witness1=None, witness2=None)
        dr = death_records("А", "Ф", "О", "Д", "Заманиловка", "Церковь", 1812, d)

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_file = dr.export(DeathRecordsCsvExporter())
                with open(csv_file, 'r', encoding='utf-8') as f:
                    rows = list(csv.reader(f))
                self.assertEqual(rows[1][36], "")
                self.assertEqual(rows[1][37], "")
                self.assertEqual(rows[1][38], "")
                self.assertEqual(rows[1][39], "")
            finally:
                os.chdir(original_cwd)


class TestDeathPageNumber(unittest.TestCase):
    def test_death_with_page_number(self):
        """Test death record with page number."""
        d1 = death(1, Gender.MALE, 15, 16, 6, 6, person("Иван"), witness1=None, witness2=None, page="3")
        self.assertEqual(d1.page, "3")

        d2 = death(2, Gender.FEMALE, 20, 21, 7, 7, person("Мария"), witness1=None, witness2=None, page="3об")
        self.assertEqual(d2.page, "3об")

        d3 = death(3, Gender.MALE, 17, 18, 8, 8, person("Фока"), witness1=None, witness2=None)
        self.assertIsNone(d3.page)

    def test_month_enum_usage(self):
        """Test that Month enum can be used instead of int for month values."""
        deceased = person("Петр", gender=Gender.MALE)

        # Test with Month enum
        d = Death(1, Gender.MALE, 20, 21, Month.DECEMBER, Month.DECEMBER, deceased, witness1=None, witness2=None)

        # Verify month values are equal to both enum and int
        self.assertEqual(d.d_month, 12)
        self.assertEqual(d.d_month, Month.DECEMBER)
        self.assertEqual(d.b_month, 12)
        self.assertEqual(d.b_month, Month.DECEMBER)


class TestDeathMonthHelper(unittest.TestCase):
    def test_death_month_sets_months(self):
        """Test that death_month helper sets death and burial months."""
        # Create deaths without month specified (using ints instead of Month)
        d1 = death(1, Gender.MALE, 15, 16, 6, 6, deceased=person("Иван"), witness1=None, witness2=None)
        d2 = death(2, Gender.FEMALE, 20, 21, 7, 7, deceased=person("Мария"), witness1=None, witness2=None)

        # Group by month
        june_deaths = death_month(Month.JUNE, d1, d2)

        # Verify returns list
        self.assertIsInstance(june_deaths, list)
        self.assertEqual(len(june_deaths), 2)

        # Verify months are set (original records had int 6 and 7)
        # death_month should not overwrite if already set
        self.assertEqual(june_deaths[0].d_month, 6)  # Already was 6
        self.assertEqual(june_deaths[0].b_month, 6)  # Already was 6
        self.assertEqual(june_deaths[1].d_month, 7)  # Already was 7
        self.assertEqual(june_deaths[1].b_month, 7)  # Already was 7

    def test_death_month_sets_none_months(self):
        """Test that death_month sets months when they are None."""
        # Create death without months (should be created via Death class directly)
        d1 = Death(1, Gender.MALE, 15, 16, None, None, person("Иван"), witness1=None, witness2=None)

        # Group by month
        june_deaths = death_month(Month.JUNE, d1)

        # Verify months are set
        self.assertEqual(june_deaths[0].d_month, Month.JUNE)
        self.assertEqual(june_deaths[0].b_month, Month.JUNE)

    def test_death_month_deep_copies(self):
        """Test that death_month creates deep copies."""
        d1 = Death(1, Gender.MALE, 15, 16, None, None, person("Иван"), witness1=None, witness2=None)

        june_deaths = death_month(Month.JUNE, d1)

        # Verify it's a different object
        self.assertIsNot(june_deaths[0], d1)
        self.assertIsNot(june_deaths[0].deceased, d1.deceased)

    def test_death_month_preserves_existing_months(self):
        """Test that death_month doesn't overwrite existing months."""
        # Create death with months already set
        d1 = Death(1, Gender.MALE, 15, 16, Month.JULY, Month.JULY, person("Иван"), witness1=None, witness2=None)

        # Try to group by June
        june_deaths = death_month(Month.JUNE, d1)

        # Original months should be preserved
        self.assertEqual(june_deaths[0].d_month, Month.JULY)
        self.assertEqual(june_deaths[0].b_month, Month.JULY)


class TestDeathRelationshipGenderValidation(unittest.TestCase):
    def test_father_with_male_person_passes(self):
        d = Death(1, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("Петр"), Relationship.FATHER)])
        self.assertEqual(d.relative.gender, Gender.MALE)

    def test_father_with_female_person_raises(self):
        with self.assertRaises(ValueError) as ctx:
            Death(1, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("Мария"), Relationship.FATHER)])
        msg = str(ctx.exception)
        self.assertIn("relative", msg)
        self.assertIn("MALE", msg)

    def test_mother_with_female_person_passes(self):
        d = Death(1, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("Мария"), Relationship.MOTHER)])
        self.assertEqual(d.relative.gender, Gender.FEMALE)

    def test_mother_with_male_person_raises(self):
        with self.assertRaises(ValueError) as ctx:
            Death(1, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("Петр"), Relationship.MOTHER)])
        msg = str(ctx.exception)
        self.assertIn("relative", msg)
        self.assertIn("FEMALE", msg)

    def test_unknown_name_no_raise(self):
        d = Death(1, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("?"), Relationship.FATHER)])
        self.assertEqual(d.relative.gender, Gender.MALE)

    def test_no_relationship_no_raise(self):
        d = Death(1, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("Мария"), None)])
        self.assertEqual(d.relative.gender, Gender.FEMALE)

    def test_explicit_wrong_gender_raises(self):
        with self.assertRaises(ValueError):
            Death(1, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("?", gender=Gender.FEMALE), Relationship.FATHER)])

    def test_error_message_content(self):
        with self.assertRaises(ValueError) as ctx:
            Death(7, Gender.MALE, 1, 2, 1, 1, person("Иван"),
                  relatives=[relative(person("Мария"), Relationship.FATHER)])
        msg = str(ctx.exception)
        self.assertIn("7", msg)
        self.assertIn("relative", msg)
        self.assertIn(str(Relationship.FATHER), msg)


class TestDeathMultipleRelatives(unittest.TestCase):
    """Tests for the new relatives=[] list API."""

    def test_new_api_with_relatives_list(self):
        """relatives=[] should work directly."""
        from verso.ru.relationship import relative
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"),
                  relatives=[
                      relative(person("Петр"), Relationship.FATHER),
                      relative(person("Мария"), Relationship.MOTHER),
                  ])
        self.assertEqual(len(d.relatives), 2)
        self.assertEqual(d.relatives[0].person.name_orig, "Петр")
        self.assertEqual(d.relatives[1].person.name_orig, "Мария")

    def test_relative_property_returns_first(self):
        """The .relative property should return the first relative's person."""
        from verso.ru.relationship import relative
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"),
                  relatives=[
                      relative(person("Петр"), Relationship.FATHER),
                      relative(person("Мария"), Relationship.MOTHER),
                  ])
        self.assertEqual(d.relative.name_orig, "Петр")
        self.assertEqual(d.relationship, Relationship.FATHER)

    def test_no_relative_returns_none(self):
        """No relatives should give None for .relative and .relationship."""
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"))
        self.assertIsNone(d.relative)
        self.assertIsNone(d.relationship)

    def test_father_patronymic_derivation_with_relatives_list(self):
        """Father in relatives list should derive deceased patronymic."""
        from verso.ru.relationship import relative
        d = death(1, Gender.MALE, 5, 6,
                  deceased=person("Иван"),
                  relatives=[relative(person("Василий"), Relationship.FATHER)])
        self.assertEqual(d.deceased.patr_modern, "Васильевич")

    def test_gender_assignment_for_multiple_relatives(self):
        """All relatives should get gender assigned from relationship."""
        from verso.ru.relationship import relative
        father = person("Петр")
        mother = person("Мария")
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"),
                  relatives=[
                      relative(father, Relationship.FATHER),
                      relative(mother, Relationship.MOTHER),
                  ])
        self.assertEqual(d.relatives[0].person.gender, Gender.MALE)
        self.assertEqual(d.relatives[1].person.gender, Gender.FEMALE)

    def test_defaults_applied_to_all_relatives(self):
        """RecordDefaults should apply to all relatives in the list."""
        from verso.ru.relationship import relative
        father = person("Петр")
        mother = person("Мария")
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"),
                  relatives=[
                      relative(father, Relationship.FATHER),
                      relative(mother, Relationship.MOTHER),
                  ])
        defaults = RecordDefaults(residence="Заманиловка")
        defaults.apply_to_death(d)
        self.assertEqual(d.relatives[0].person.residence, "Заманиловка")
        self.assertEqual(d.relatives[1].person.residence, "Заманиловка")


class TestDeathHouseholdResidence(unittest.TestCase):
    """Death.__init__ propagates one household residence across the deceased
    and the relatives (witnesses excluded)."""

    def test_deceased_inherits_relative_residence(self):
        d = death(1, Gender.MALE, 5, 6,
                  deceased=person("Иван"), age=1,
                  relatives=[relative(person("Петр", residence="Собакевичево"), Relationship.FATHER)])
        self.assertEqual(d.deceased.residence, "Собакевичево")

    def test_relative_inherits_deceased_residence(self):
        d = death(1, Gender.MALE, 5, 6,
                  deceased=person("Иван", residence="Собакевичево"), age=1,
                  relatives=[relative(person("Петр"), Relationship.FATHER)])
        self.assertEqual(d.relative.residence, "Собакевичево")

    def test_explicit_residences_never_overwritten(self):
        d = death(1, Gender.FEMALE, 5, 6,
                  deceased=person("Мария", residence="Заманиловка"), age=17,
                  relatives=[relative(person("Петр", residence="Шпонькин Бор"), Relationship.HUSBAND)])
        self.assertEqual(d.deceased.residence, "Заманиловка")
        self.assertEqual(d.relative.residence, "Шпонькин Бор")

    def test_first_relative_with_residence_is_the_anchor(self):
        from verso.ru.relationship import relative
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1,
                  relatives=[
                      relative(person("Петр"), Relationship.FATHER),
                      relative(person("Мария", residence="Собакевичево"),
                               Relationship.MOTHER),
                  ])
        self.assertEqual(d.deceased.residence, "Собакевичево")
        self.assertEqual(d.relatives[0].person.residence, "Собакевичево")

    def test_record_defaults_do_not_override_inherited_residence(self):
        """RecordDefaults runs after __init__, so the household value wins."""
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1,
                  relatives=[relative(person("Петр", residence="Собакевичево"), Relationship.FATHER)])
        RecordDefaults(residence="Горюхино").apply_to_death(d)
        self.assertEqual(d.deceased.residence, "Собакевичево")
        self.assertEqual(d.relative.residence, "Собакевичево")

    def test_witnesses_do_not_inherit(self):
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1,
                  relatives=[relative(person("Петр", residence="Собакевичево"), Relationship.FATHER)],
                  witness1=person("Федор"))
        self.assertIsNone(d.witness1.residence)

    def test_no_residence_anywhere_stays_none(self):
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1,
                  relatives=[relative(person("Петр"), Relationship.FATHER)])
        self.assertIsNone(d.deceased.residence)
        self.assertIsNone(d.relative.residence)


class TestDeceasedStatusInheritance(unittest.TestCase):
    """Death.__init__ derives a statusless deceased child's сословие from the
    first FATHER relative with a status (else the first MOTHER), via
    statuses.child_status_for — mirroring the birth rule."""

    def test_deceased_son_derives_from_father(self):
        from corpus.statuses import MANILOV_LK_PEASANT_MALE, MANILOV_LK_PEASANT_SON
        d = death(1, Gender.MALE, 5, 6, deceased=person("Антон"), age=1,
                  relatives=[relative(person("Федор", status=MANILOV_LK_PEASANT_MALE), Relationship.FATHER)])
        self.assertEqual(d.deceased.status, MANILOV_LK_PEASANT_SON)

    def test_deceased_daughter_form_by_gender(self):
        from verso.ru.domain.statuses import (
            YASAK_PEASANT_DAUGHTER, YASAK_PEASANT_MALE)
        d = death(1, Gender.FEMALE, 5, 6, deceased=person("Анна"), age=1,
                  relatives=[relative(person("Петр", status=YASAK_PEASANT_MALE), Relationship.FATHER)])
        self.assertEqual(d.deceased.status, YASAK_PEASANT_DAUGHTER)

    def test_proprietor_peasants_dead_child_is_a_peasant_child(self):
        """A boy of 7 months, the son of a крестьянин собственника."""
        from verso.ru.domain.statuses import PEASANT_SON, PROPRIETOR_PEASANT_MALE
        d = death(2, Gender.MALE, 6, 8, deceased=person("Лука"), age="7 мес",
                  relatives=[relative(person("Прохор", status=PROPRIETOR_PEASANT_MALE), Relationship.FATHER)])
        self.assertEqual(d.deceased.status, PEASANT_SON)

    def test_mother_is_the_fallback(self):
        from verso.ru.domain.statuses import (
            YASAK_PEASANT_FEMALE, YASAK_PEASANT_SON)
        d = death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1,
                  relatives=[relative(person("Дарья", status=YASAK_PEASANT_FEMALE), Relationship.MOTHER)])
        self.assertEqual(d.deceased.status, YASAK_PEASANT_SON)

    def test_out_of_scope_father_blocks_mother_fallback(self):
        from verso.ru.relationship import relative
        from verso.ru.domain.statuses import DYACHOK, YASAK_PEASANT_FEMALE
        d = death(1, Gender.MALE, 5, 6, deceased=person("Семён"), age=1,
                  relatives=[
                      relative(person("Пётр", status=DYACHOK),
                               Relationship.FATHER),
                      relative(person("Дарья", status=YASAK_PEASANT_FEMALE),
                               Relationship.MOTHER),
                  ])
        self.assertIsNone(d.deceased.status)

    def test_husband_is_out_of_scope(self):
        """A wife's form (жена / законная жена) is the source's vocabulary
        choice, not a derivation."""
        from verso.ru.domain.statuses import YASAK_PEASANT_MALE
        d = death(1, Gender.FEMALE, 5, 6, deceased=person("Мария"), age=30,
                  relatives=[relative(person("Пётр", status=YASAK_PEASANT_MALE), Relationship.HUSBAND)])
        self.assertIsNone(d.deceased.status)

    def test_explicit_status_never_overwritten(self):
        from corpus.statuses import MANILOV_LK_PEASANT_MALE
        from verso.ru.domain.statuses import YASAK_PEASANT_SON
        d = death(1, Gender.MALE, 5, 6,
                  deceased=person("Иван", status=YASAK_PEASANT_SON), age=1,
                  relatives=[relative(person("Пётр", status=MANILOV_LK_PEASANT_MALE), Relationship.FATHER)])
        self.assertEqual(d.deceased.status, YASAK_PEASANT_SON)

    def test_record_defaults_do_not_override_derived_status(self):
        from corpus.statuses import MANILOV_KF_PEASANT_MALE, MANILOV_KF_PEASANT_SON
        from verso.ru.domain.statuses import YASAK_PEASANT_FEMALE, YASAK_PEASANT_MALE
        r = death_records(
            "a", "f", "i", "c", "Горюхино", "Ц", 1830,
            death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1,
                  relatives=[relative(person("Пётр", status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER)]),
            defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE,
                                    status_female=YASAK_PEASANT_FEMALE))
        self.assertEqual(r.records[0].deceased.status, MANILOV_KF_PEASANT_SON)


class TestDeathReviewedFlag(unittest.TestCase):
    def test_death_reviewed_is_unstated_until_its_record_set_resolves_it(self):
        d = death(1, Gender.MALE, deceased=person("Иван"))
        self.assertIsNone(d.reviewed)
        records = death_records("A", "1", "1", "1", "Тестовка", "Никольская", 1880, d)
        self.assertIs(True, records.records[0].reviewed)

    def test_death_reviewed_false_propagates_through_factory(self):
        d = death(1, Gender.MALE, deceased=person("Иван"), reviewed=False)
        self.assertFalse(d.reviewed)




class TestDeathCSVExportPersonComments(unittest.TestCase):
    def test_csv_export_keeps_the_comments_of_the_row_s_people(self):
        """The deceased's, the relative's and a witness's comment= reach the CSV's Комментарий (В15)."""
        d = death(
            1, Gender.MALE, 15, 16, 6, 6,
            person("Иван", patr_orig="Петров", gender=Gender.MALE, comment="запасный рядовой"),
            relatives=[relative(person("Мария", patr_orig="Иванова", gender=Gender.FEMALE, comment="солдатка"),
                                Relationship.WIFE)],
            witness1=person("Федор", patr_orig="Сидоров", gender=Gender.MALE, comment="отставной унтер-офицер"),
            witness2=None,
            comment="умер от горячки",
        )
        dr = death_records("ГАТО", "Ф. 181", "Оп. 1", "Д. 123", "Заманиловка", "Церковь", 1804, d)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = DeathRecordsCsvExporter().export(dr, tmpdir)
            with open(csv_file, encoding='utf-8') as f:
                rows = list(csv.reader(f))

        self.assertEqual(
            rows[1][40], "умер от горячки. запасный рядовой. солдатка. отставной унтер-офицер")


if __name__ == '__main__':
    unittest.main()
