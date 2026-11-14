import csv
import os
import tempfile
import unittest
from calendar import Month

from verso.ru.exporters.csv import MarriageRecordsCsvExporter
from verso.ru.domain import Person, RecordDefaults, person, Gender
from verso.ru.dsl.records.marriages import Marriage, MarriageRecords, marriage, marriage_records, marriage_month
from verso.ru.relationship import Relationship, Relative, relative


class TestMarriages(unittest.TestCase):

    def test_female_groom_explicit_raises(self):
        """Groom with explicit FEMALE gender → ValueError."""
        with self.assertRaises(ValueError) as ctx:
            Marriage(1, 14, 1, person("Мария", gender=Gender.FEMALE), None)
        msg = str(ctx.exception)
        self.assertIn("groom gender", msg)
        self.assertIn("MALE", msg)

    def test_male_bride_explicit_raises(self):
        """Bride with explicit MALE gender → ValueError."""
        with self.assertRaises(ValueError) as ctx:
            Marriage(1, 14, 1, None, person("Иван", gender=Gender.MALE))
        msg = str(ctx.exception)
        self.assertIn("bride gender", msg)
        self.assertIn("FEMALE", msg)

    def test_error_message_contains_record_num_and_name(self):
        """Error message includes the record number and person name."""
        with self.assertRaises(ValueError) as ctx:
            Marriage(7, 10, 2, person("Анна", gender=Gender.FEMALE), None)
        msg = str(ctx.exception)
        self.assertIn("7", msg)
        self.assertIn("Анна", msg)

    def test_female_named_groom_raises(self):
        """Groom with a female name (auto-detected FEMALE) conflicts with MALE role → ValueError."""
        with self.assertRaises(ValueError):
            Marriage(1, 14, 1, person("Мария"), None)

    def test_male_named_bride_raises(self):
        """Bride with a male name (auto-detected MALE) conflicts with FEMALE role → ValueError."""
        with self.assertRaises(ValueError):
            Marriage(1, 14, 1, None, person("Иван"))

    def test_correct_genders_no_raise(self):
        """Male groom and female bride with explicit genders → no error."""
        m = Marriage(1, 14, 1, person("Иван", gender=Gender.MALE), person("Мария", gender=Gender.FEMALE))
        self.assertEqual(m.groom.gender, Gender.MALE)
        self.assertEqual(m.bride.gender, Gender.FEMALE)

    def test_no_groom_no_raise(self):
        """No groom → no validation, no error."""
        m = Marriage(1, 14, 1, None, person("Мария", gender=Gender.FEMALE))
        self.assertIsNone(m.groom)

    def test_no_bride_no_raise(self):
        """No bride → no validation, no error."""
        m = Marriage(1, 14, 1, person("Иван", gender=Gender.MALE), None)
        self.assertIsNone(m.bride)

    def test_marriage_factory_also_raises(self):
        """marriage() factory propagates the ValueError."""
        with self.assertRaises(ValueError):
            marriage(3, 5, 2, person("Прасковья", gender=Gender.FEMALE), None)

    def test_marriage_automatic_gender_assignment(self):
        groom = Person("Иван", name_modern_orth="Иван")
        bride = Person("Мария", name_modern_orth="Мария")
        witness1 = Person("Петр", name_modern_orth="Петр")
        witness2 = Person("Анна", name_modern_orth="Анна")

        m = Marriage(1, 14, 1, groom, bride, witness1=witness1, witness2=witness2)

        self.assertEqual(m.groom.gender, Gender.MALE)
        self.assertEqual(m.bride.gender, Gender.FEMALE)
        # Witnesses get gender auto-detected from names
        self.assertEqual(m.witness1.gender, Gender.MALE)  # Петр is male
        self.assertEqual(m.witness2.gender, Gender.FEMALE)  # Анна is female

    def test_marriage_with_marriage_numbers(self):
        groom = person("Фотий", patr_orig="Михайлов")
        bride = person("Анастасия", patr_orig="Антонова")

        m = marriage(7, 24, 1, groom, bride, groom_marriage_num=2, bride_marriage_num=2)

        self.assertEqual(m.groom_marriage_num, 2)
        self.assertEqual(m.bride_marriage_num, 2)
        self.assertEqual(m.record_num, 7)
        self.assertEqual(m.w_day, 24)
        self.assertEqual(m.w_month, 1)

    def test_marriage_with_comment(self):
        groom = person("Василий", patr_orig="Прокофьев")
        bride = person("Прасковья", patr_orig="Михайлова")

        m = marriage(8, 31, 1, groom, bride, bride_marriage_num=2, comment='Невеста "вдовая Михайлова"')

        self.assertEqual(m.comment, 'Невеста "вдовая Михайлова"')
        self.assertEqual(m.bride_marriage_num, 2)
        self.assertIsNone(m.groom_marriage_num)

    def test_bride_takes_groom_surname_defaults_to_true(self):
        """The flag defaults to True — matches Russian historical convention
        (brides almost always took the groom's surname). DSL records that
        differ opt out with `bride_takes_groom_surname=False`."""
        m = marriage(1, 14, w_month=Month.JANUARY,
                     groom=person("Иван", "Петров"),
                     bride=person("Мария", "Иванова"))
        self.assertTrue(m.bride_takes_groom_surname)

    def test_bride_takes_groom_surname_false_stored(self):
        """DSL can explicitly opt out of the default."""
        m = marriage(1, 14, w_month=Month.JANUARY,
                     groom=person("Иван", "Петров"),
                     bride=person("Мария", "Иванова"),
                     bride_takes_groom_surname=False)
        self.assertFalse(m.bride_takes_groom_surname)

    def test_marriage_dsl_helpers(self):
        groom = person("Никифор", patr_orig="Терентьев")
        bride = person("Иустина", patr_orig="Климова")
        w1 = person("Филипп", patr_orig="Архипов")
        w2 = person("Сидор", patr_orig="Калинин")

        m = marriage(1, 14, 1, groom, bride, witness1=w1, witness2=w2)

        self.assertIsInstance(m, Marriage)
        self.assertEqual(m.record_num, 1)
        self.assertEqual(m.w_day, 14)
        self.assertEqual(m.w_month, 1)
        self.assertIsNotNone(m.groom)
        self.assertIsNotNone(m.bride)
        self.assertIsNotNone(m.witness1)
        self.assertIsNotNone(m.witness2)

    def test_marriage_records_collection(self):
        m1 = marriage(1, 14, 1, person("Алексей"), person("Прасковья"))
        m2 = marriage(2, 15, 1, person("Иван"), person("Мария"))

        mr = marriage_records("Archive", "F", "I", "C", "Village", "Church", 1804, m1, m2)

        self.assertIsInstance(mr, MarriageRecords)
        self.assertEqual(len(mr.records), 2)
        self.assertEqual(mr.year, 1804)
        self.assertEqual(mr.village, "Village")

    def test_marriage_records_defaults(self):
        groom = person("Иван", patr_orig="Иванов")
        bride = person("Мария", patr_orig="Петрова")
        w1 = person("Петр", patr_orig="Сидоров", gender=Gender.MALE)
        w2 = person("Анна", patr_orig="Васильева", gender=Gender.FEMALE)

        # Groom has explicit status, should not be overwritten
        groom.status = "дворянин"

        m = marriage(1, 14, 1, groom, bride, witness1=w1, witness2=w2)

        # Apply defaults using RecordDefaults class
        _mr = marriage_records(
            "A", "F", "I", "C", "Заманиловка", "Ch", 1804, m,
            defaults=RecordDefaults(
                residence="Заманиловка",
                status_male="экономический крестьянин",
                status_female="экономическая крестьянка"
            )
        )

        # Check defaults were applied where empty
        self.assertEqual(groom.residence, "Заманиловка")
        self.assertEqual(groom.status, "дворянин")  # not overwritten
        self.assertEqual(bride.residence, "Заманиловка")
        self.assertEqual(bride.status, "экономическая крестьянка")
        self.assertEqual(w1.residence, "Заманиловка")
        self.assertEqual(w1.status, "экономический крестьянин")
        self.assertEqual(w2.residence, "Заманиловка")
        self.assertEqual(w2.status, "экономическая крестьянка")

    def test_marriage_none_persons(self):
        # Test with missing persons
        m = marriage(1, 14, 1, None, None)

        self.assertIsNone(m.groom)
        self.assertIsNone(m.bride)
        self.assertIsNone(m.witness1)
        self.assertIsNone(m.witness2)

    def test_record_defaults_apply_to_marriage(self):
        defaults = RecordDefaults(
            residence="Testville",
            status_male="male status",
            status_female="female status"
        )

        groom = person("Иван")
        bride = person("Мария")
        w1 = person("Петр")
        w2 = person("Анна")

        m = Marriage(1, 1, 1, groom, bride, witness1=w1, witness2=w2)
        defaults.apply_to_marriage(m)

        # All persons should get the defaults
        self.assertEqual(groom.residence, "Testville")
        self.assertEqual(groom.status, "male status")
        self.assertEqual(bride.residence, "Testville")
        self.assertEqual(bride.status, "female status")
        self.assertEqual(w1.residence, "Testville")
        self.assertEqual(w2.residence, "Testville")

    def test_csv_export_basic(self):
        """Test CSV export functionality and file generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple marriage record
            groom = person("Иванъ", patr_orig="Петровъ", residence="Тестово", status="крестьянин", gender=Gender.MALE)
            bride = person("Марія", patr_orig="Сидорова", residence="Тестово", status="крестьянка", gender=Gender.FEMALE)
            w1 = person("Яковъ", patr_orig="Федоровъ", residence="Тестово", status="крестьянин", gender=Gender.MALE)
            w2 = person("Анна", patr_orig="Иванова", residence="Тестово", status="крестьянка", gender=Gender.FEMALE)

            m = marriage(1, 15, 6, groom, bride, witness1=w1, witness2=w2)
            mr = marriage_records("Arch", "F", "I", "C", "Тестово", "Ch", 1800, m)

            # Export to CSV
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

                # Verify file was created
                self.assertTrue(os.path.exists(csv_path))
                self.assertEqual(os.path.basename(csv_path), "Тестово_1800_marriages.csv")

                # Read and verify CSV content
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                # Check header and data rows
                self.assertEqual(len(rows), 2)  # header + 1 record
                self.assertEqual(len(rows[0]), 40)  # 40 columns

                # Verify header
                self.assertEqual(rows[0][0], "№")
                self.assertEqual(rows[0][1], "Страница")
                self.assertEqual(rows[0][7], "Жених: Имя (ориг.)")
                self.assertEqual(rows[0][17], "Невеста: Имя (ориг.)")
                self.assertEqual(rows[0][34], "Священник: ФИО (ориг.)")
                self.assertEqual(rows[0][35], "Дьякон: ФИО (ориг.)")
                self.assertEqual(rows[0][36], "Дьячок: ФИО (ориг.)")
                self.assertEqual(rows[0][37], "Пономарь: ФИО (ориг.)")
                self.assertEqual(rows[0][38], "Комментарий")
                self.assertEqual(rows[0][39], "Имена в оригинале")

                # Verify data
                data = rows[1]
                self.assertEqual(data[0], "1")  # record number
                self.assertEqual(data[1], "")  # page (empty)
                self.assertEqual(data[2], "15")  # day
                self.assertEqual(data[3], "6")  # month
                self.assertEqual(data[7], "Иванъ")  # groom name orig
                self.assertEqual(data[8], "Петровъ")  # groom patronymic orig
                self.assertEqual(data[17], "Марія")  # bride name orig
                self.assertEqual(data[18], "Сидорова")  # bride patronymic orig

            finally:
                os.chdir(original_cwd)

    def test_csv_export_with_missing_data(self):
        """Test CSV export with partial/missing data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Marriage with only groom and bride, no witnesses
            groom = person("Петръ", patr_orig="Ивановъ", gender=Gender.MALE)
            bride = person("Елена", patr_orig="Федорова", gender=Gender.FEMALE)

            m = marriage(2, 20, 11, groom, bride, comment="Без свидетелей")
            mr = marriage_records("A", "F", "I", "C", "Village", "Ch", 1805, m,
                                  defaults=RecordDefaults(residence="Village", status_male="статус"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                # Verify witness fields are empty
                self.assertEqual(data[24], "")  # witness1 status
                self.assertEqual(data[25], "")  # witness1 residence
                self.assertEqual(data[26], "")  # witness1 FIO orig
                self.assertEqual(data[29], "")  # witness2 status

                # Verify comment
                self.assertEqual(data[38], "Без свидетелей")

                # Verify orig_names_str includes only groom and bride
                orig_names = data[39]
                self.assertIn("Петръ", orig_names)
                self.assertIn("Елена", orig_names)

            finally:
                os.chdir(original_cwd)

    def test_csv_export_with_marriage_numbers(self):
        """Test CSV export correctly includes marriage numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            groom = person("Фотий", patr_orig="Михайлов", gender=Gender.MALE)
            bride = person("Анна", patr_orig="Петрова", gender=Gender.FEMALE)

            # Second marriage for both
            m = marriage(3, 10, 5, groom, bride, groom_marriage_num=2, bride_marriage_num=2)
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1810, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                self.assertEqual(data[13], "2")  # groom marriage number
                self.assertEqual(data[23], "2")  # bride marriage number

            finally:
                os.chdir(original_cwd)

    def test_csv_export_orig_names_generation(self):
        """Test that orig_names_str is correctly generated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            groom = person("Дмитрій", patr_orig="Родіоновъ", gender=Gender.MALE)
            bride = person("Евдокія", patr_orig="Игнатова", gender=Gender.FEMALE)
            w1 = person("Сидоръ", patr_orig="Панкратовъ", gender=Gender.MALE)
            w2 = person("Филиппъ", patr_orig="Калининъ", gender=Gender.MALE)

            m = marriage(6, 24, 1, groom, bride, witness1=w1, witness2=w2)
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1804, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                orig_names = data[39]

                # Verify all names are present
                self.assertIn("Дмитрій Родіоновъ", orig_names)
                self.assertIn("Евдокія Игнатова", orig_names)
                self.assertIn("Сидоръ Панкратовъ", orig_names)
                self.assertIn("Филиппъ Калининъ", orig_names)

                # Verify semicolon separation
                self.assertEqual(orig_names.count(";"), 3)

            finally:
                os.chdir(original_cwd)

    def test_csv_export_multiple_records(self):
        """Test CSV export with multiple marriage records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            m1 = marriage(1, 1, 1, person("Иван", gender=Gender.MALE), person("Мария", gender=Gender.FEMALE))
            m2 = marriage(2, 2, 2, person("Петр", gender=Gender.MALE), person("Анна", gender=Gender.FEMALE))
            m3 = marriage(3, 3, 3, person("Федор", gender=Gender.MALE), person("Ксения", gender=Gender.FEMALE))

            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1800, m1, m2, m3,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

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

    def test_marriage_records_export_method(self):
        """Test MarriageRecords.export() method directly."""
        from verso.ru.exporters.csv import MarriageRecordsCsvExporter

        m = marriage(1, 10, 5, person("Иван", gender=Gender.MALE), person("Мария", gender=Gender.FEMALE))
        mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1800, m,
                              defaults=RecordDefaults(residence="V", status_male="s"))

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                exporter = MarriageRecordsCsvExporter()
                result = mr.export(exporter)

                # Verify result is a file path
                self.assertIsInstance(result, str)
                self.assertTrue(os.path.exists(result))

            finally:
                os.chdir(original_cwd)

    def test_marriage_edge_case_only_groom(self):
        """Test Marriage with only groom (bride missing)."""
        groom = person("Иван", gender=Gender.MALE)
        m = Marriage(1, 1, 1, groom, None)

        self.assertIsNotNone(m.groom)
        self.assertIsNone(m.bride)
        self.assertEqual(m.groom.gender, Gender.MALE)

    def test_marriage_edge_case_one_witness(self):
        """Test Marriage with only one witness."""
        groom = person("Петр", gender=Gender.MALE)
        bride = person("Мария", gender=Gender.FEMALE)
        w1 = person("Иван", gender=Gender.MALE)

        m = Marriage(1, 1, 1, groom, bride, witness1=w1, witness2=None)

        self.assertIsNotNone(m.witness1)
        self.assertIsNone(m.witness2)

    def test_csv_person_without_patronymic(self):
        """Test CSV export with persons missing patronymics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            groom = person("Иван", gender=Gender.MALE)  # No patronymic
            bride = person("Мария", patr_orig="Иванова", gender=Gender.FEMALE)

            m = marriage(1, 1, 1, groom, bride)
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1800, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                self.assertEqual(data[7], "Иван")  # groom name
                self.assertEqual(data[8], "")  # groom patronymic - empty
                self.assertEqual(data[18], "Иванова")  # bride patronymic

                # Verify orig_names_str handles missing patronymic
                orig_names = data[39]
                self.assertIn("Иван", orig_names)
                self.assertIn("Мария Иванова", orig_names)

            finally:
                os.chdir(original_cwd)

    def test_marriage_with_clergy(self):
        """Test that priest and sexton are stored; deacon/dyachok default to None."""
        groom = person("Иван", gender=Gender.MALE)
        bride = person("Мария", gender=Gender.FEMALE)
        pr = person("Василій", patr_orig="Петровъ")
        sx = person("Иванъ", patr_orig="Сидоровъ")

        m = marriage(1, 14, 1, groom, bride, priest=pr, sexton=sx)

        self.assertEqual(m.priest.name_orig, "Василій")
        self.assertEqual(m.priest.patr_orig, "Петровъ")
        self.assertEqual(m.priest.status, "священник")
        self.assertEqual(m.sexton.name_orig, "Иванъ")
        self.assertEqual(m.sexton.patr_orig, "Сидоровъ")
        self.assertEqual(m.sexton.status, "пономарь")
        self.assertIsNone(m.deacon)
        self.assertIsNone(m.dyachok)

    def test_marriage_default_clergy_none(self):
        """Test that all four clergy fields default to None."""
        m = marriage(1, 14, 1, person("Иван", gender=Gender.MALE), person("Мария", gender=Gender.FEMALE))

        self.assertIsNone(m.priest)
        self.assertIsNone(m.deacon)
        self.assertIsNone(m.dyachok)
        self.assertIsNone(m.sexton)

    def test_csv_export_with_clergy(self):
        """Test CSV clergy cols 34-37 populated; clergy comment aggregated at col 38."""
        with tempfile.TemporaryDirectory() as tmpdir:
            groom = person("Иванъ", patr_orig="Петровъ", gender=Gender.MALE)
            bride = person("Марія", patr_orig="Сидорова", gender=Gender.FEMALE)
            pr = person("Василій", patr_orig="Ивановъ", comment="Священник примечание")
            sx = person("Дмитрій", patr_orig="Федоровъ")

            m = marriage(1, 14, 1, groom, bride, priest=pr, sexton=sx, comment="Общий комментарий")
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1804, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                self.assertEqual(data[34], "Василій Ивановъ")   # priest
                self.assertEqual(data[35], "")                   # deacon (none)
                self.assertEqual(data[36], "")                   # dyachok (none)
                self.assertEqual(data[37], "Дмитрій Федоровъ")  # sexton
                # comment aggregated: record comment + priest comment
                self.assertIn("Общий комментарий", data[38])
                self.assertIn("Священник примечание", data[38])
            finally:
                os.chdir(original_cwd)

    def test_csv_export_clergy_empty(self):
        """Test CSV clergy cols 34-37 are empty when no clergy provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            groom = person("Иванъ", patr_orig="Петровъ", gender=Gender.MALE)
            bride = person("Марія", patr_orig="Сидорова", gender=Gender.FEMALE)

            m = marriage(1, 14, 1, groom, bride)
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1804, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                data = rows[1]
                self.assertEqual(data[34], "")  # priest
                self.assertEqual(data[35], "")  # deacon
                self.assertEqual(data[36], "")  # dyachok
                self.assertEqual(data[37], "")  # sexton
            finally:
                os.chdir(original_cwd)

    def test_marriage_with_page_number(self):
        """Test marriage record with page number."""
        m1 = marriage(1, 14, 1, person("Иван", gender=Gender.MALE), person("Мария", gender=Gender.FEMALE), page="2")
        self.assertEqual(m1.page, "2")

        m2 = marriage(2, 15, 2, person("Петр", gender=Gender.MALE), person("Анна", gender=Gender.FEMALE), page="2об")
        self.assertEqual(m2.page, "2об")

        m3 = marriage(3, 16, 3, person("Федор", gender=Gender.MALE), person("Ксения", gender=Gender.FEMALE))
        self.assertIsNone(m3.page)

    def test_relatives_stored_as_list(self):
        """relatives is stored as a list, defaults to []."""
        m = marriage(1, 14, 1, person("Иван"), person("Мария"))
        self.assertEqual(m.relatives, [])

        bf = person("Петр", "Максимов", last_name_orig="Плешивцев")
        rel = relative(bf, Relationship.FATHER, "невеста")
        m2 = marriage(2, 14, 1, person("Иван"), person("Мария"), relatives=[rel])
        self.assertEqual(len(m2.relatives), 1)
        self.assertIs(m2.relatives[0].person, bf)
        self.assertEqual(m2.relatives[0].relationship, Relationship.FATHER)
        self.assertEqual(m2.relatives[0].relationship_ref, "невеста")

    def test_relative_gender_autodetect(self):
        """Relative gender auto-detected from name, fallback to relationship."""
        bf = person("Петр")
        m = marriage(1, 14, 1, person("Иван"), person("Мария"),
                     relatives=[relative(bf, Relationship.FATHER, "невеста")])
        self.assertEqual(m.relatives[0].person.gender, Gender.MALE)

        # Unknown name falls back to relationship gender
        bf2 = person("Сидор")
        m2 = marriage(2, 14, 1, person("Иван"), person("Мария"),
                      relatives=[relative(bf2, Relationship.FATHER, "невеста")])
        self.assertEqual(m2.relatives[0].person.gender, Gender.MALE)

    def test_relative_gender_validation(self):
        """Female person with FATHER relationship raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            marriage(1, 14, 1, person("Иван"), person("Мария"),
                     relatives=[relative(person("Анна", gender=Gender.FEMALE), Relationship.FATHER, "невеста")])
        msg = str(ctx.exception)
        self.assertIn("relative gender", msg)
        self.assertIn("MALE", msg)

    def test_relative_mother_no_raise(self):
        """Female person with MOTHER relationship is valid."""
        mother = person("Мавра", "Федосеева", last_name_orig="Опоздалова", status="вдова")
        m = marriage(1, 14, 1, person("Иван"), person("Мария"),
                     relatives=[relative(mother, Relationship.MOTHER, "невеста")])
        self.assertEqual(m.relatives[0].person.gender, Gender.FEMALE)

    def test_relatives_defaults_applied(self):
        """RecordDefaults.apply_to_marriage() applies to relatives."""
        defaults = RecordDefaults(residence="Testville", status_male="male status")
        bf = person("Петр", "Максимов")
        m = Marriage(1, 1, 1, person("Иван"), person("Мария"),
                     relatives=[Relative(bf, Relationship.FATHER, "невеста")])
        defaults.apply_to_marriage(m)
        self.assertEqual(bf.residence, "Testville")
        self.assertEqual(bf.status, "male status")

    def test_multiple_relatives(self):
        """Multiple relatives are supported."""
        bf = person("Петр", "Максимов")
        bm = person("Мавра", "Федосеева", status="вдова")
        m = marriage(1, 14, 1, person("Иван"), person("Мария"),
                     relatives=[
                         relative(bf, Relationship.FATHER, "невеста"),
                         relative(bm, Relationship.MOTHER, "невеста"),
                     ])
        self.assertEqual(len(m.relatives), 2)

    def test_csv_familio_export_bride_father_relative(self):
        """CSV familio export populates columns 49-55 for bride's father relative."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

            bf = person("Петръ", "Максимовъ", last_name_orig="Плешивцевъ")
            groom = person("Иванъ", patr_orig="Петровъ", gender=Gender.MALE)
            bride = person("Феодора", patr_orig="Петрова", gender=Gender.FEMALE)

            m = marriage(1, 15, 2, groom, bride,
                         relatives=[relative(bf, Relationship.FATHER, "невеста")])
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1837, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvFamilioExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                headers = rows[0]
                idx_49 = headers.index("Отец невесты: Н.П.")
                idx_51 = headers.index("Отец невесты: Статус")
                idx_52 = headers.index("Отец невесты: Фамилия")
                idx_54 = headers.index("Отец невесты: Имя (совр.)")
                idx_55 = headers.index("Отец невесты: Отчество (совр.)")

                data = rows[1]
                self.assertEqual(data[idx_49], "V")  # residence
                self.assertEqual(data[idx_51], "s")  # status
                self.assertEqual(data[idx_52], "Плешивцев")  # last_name_modern
                self.assertEqual(data[idx_54], "Петр")  # canonical name
                self.assertEqual(data[idx_55], "Максимович")  # canonical patronymic

                # relative in orig_names
                orig_names_col = headers.index("Имена в оригинале")
                self.assertIn("Петръ Максимовъ", data[orig_names_col])
            finally:
                os.chdir(original_cwd)

    def test_csv_familio_export_mother_relative_in_comment(self):
        """CSV familio export puts non-father relative into comment column."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

            mother = person("Мавра", "Федосеева", last_name_orig="Опоздалова", status="вдова")
            groom = person("Иванъ", patr_orig="Петровъ", gender=Gender.MALE)
            bride = person("Екатерина", last_name_orig="Опоздалова")

            m = marriage(1, 15, 2, groom, bride,
                         relatives=[relative(mother, Relationship.MOTHER, "невеста")])
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1837, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvFamilioExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                headers = rows[0]
                comment_col = headers.index("Комментарий")
                data = rows[1]
                # Mother should appear in comment
                self.assertIn("мать", data[comment_col])
                self.assertIn("Мавра", data[comment_col])

                # Bride father columns should be empty
                idx_52 = headers.index("Отец невесты: Фамилия")
                self.assertEqual(data[idx_52], "")
            finally:
                os.chdir(original_cwd)

    def test_month_enum_usage(self):
        """Test that Month enum can be used instead of int for month values."""
        groom = Person("Иван", name_modern_orth="Иван", gender=Gender.MALE)
        bride = Person("Анна", name_modern_orth="Анна", gender=Gender.FEMALE)

        # Test with Month enum
        m = Marriage(1, 15, Month.JUNE, groom, bride)

        # Verify month value is equal to both enum and int
        self.assertEqual(m.w_month, 6)
        self.assertEqual(m.w_month, Month.JUNE)


    def test_marriage_with_ages(self):
        """Test that groom_age and bride_age are stored correctly."""
        groom = person("Иван", gender=Gender.MALE)
        bride = person("Мария", gender=Gender.FEMALE)

        m = marriage(1, 14, 1, groom, bride, groom_age=20, bride_age=18)

        self.assertEqual(m.groom_age, 20)
        self.assertEqual(m.bride_age, 18)

    def test_marriage_ages_default_none(self):
        """Test that groom_age and bride_age default to None."""
        m = marriage(1, 14, 1, person("Иван"), person("Мария"))

        self.assertIsNone(m.groom_age)
        self.assertIsNone(m.bride_age)

    def test_csv_familio_export_ages_populated(self):
        """Test Familio CSV columns 25 and 45 populated when ages are set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

            groom = person("Иванъ", patr_orig="Петровъ", gender=Gender.MALE)
            bride = person("Марія", patr_orig="Сидорова", gender=Gender.FEMALE)

            m = marriage(1, 15, 2, groom, bride, groom_age=20, bride_age=18)
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1865, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvFamilioExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                headers = rows[0]
                idx_groom_age = headers.index("Жених: Лет")
                idx_bride_age = headers.index("Невеста: Лет")

                data = rows[1]
                self.assertEqual(data[idx_groom_age], "20")
                self.assertEqual(data[idx_bride_age], "18")
            finally:
                os.chdir(original_cwd)

    def test_csv_familio_export_ages_empty_when_none(self):
        """Test Familio CSV age columns are empty when ages are None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

            groom = person("Иванъ", patr_orig="Петровъ", gender=Gender.MALE)
            bride = person("Марія", patr_orig="Сидорова", gender=Gender.FEMALE)

            m = marriage(1, 15, 2, groom, bride)
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1865, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvFamilioExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                headers = rows[0]
                idx_groom_age = headers.index("Жених: Лет")
                idx_bride_age = headers.index("Невеста: Лет")

                data = rows[1]
                self.assertEqual(data[idx_groom_age], "")
                self.assertEqual(data[idx_bride_age], "")
            finally:
                os.chdir(original_cwd)

    def test_csv_familio_export_string_ages_compound(self):
        """String ages like '19 лет 6 мес' split across Лет/Месяцев columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

            groom = person("Иванъ", patr_orig="Петровъ", gender=Gender.MALE)
            bride = person("Марія", patr_orig="Сидорова", gender=Gender.FEMALE)

            m = marriage(1, 15, 2, groom, bride,
                         groom_age="19 лет 6 мес", bride_age="17 лет 3 мес")
            mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1865, m,
                                  defaults=RecordDefaults(residence="V", status_male="s"))

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                csv_path = mr.export(MarriageRecordsCsvFamilioExporter())

                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                headers = rows[0]
                data = rows[1]
                self.assertEqual(data[headers.index("Жених: Лет")], "19")
                self.assertEqual(data[headers.index("Жених: Месяцев")], "6")
                self.assertEqual(data[headers.index("Невеста: Лет")], "17")
                self.assertEqual(data[headers.index("Невеста: Месяцев")], "3")
            finally:
                os.chdir(original_cwd)


    def test_groom_otrok_with_marriage_num_gt1_raises(self):
        """Groom with marriage_num > 1 and status containing 'отрок' → ValueError."""
        with self.assertRaises(ValueError) as ctx:
            marriage(1, 14, 1,
                     person("Иван", status="отрок"),
                     person("Мария"),
                     groom_marriage_num=2)
        msg = str(ctx.exception)
        self.assertIn("отрок", msg)
        self.assertIn("marriage_num=2", msg)

    def test_groom_otrok_with_marriage_num_1_ok(self):
        """Groom with marriage_num=1 and status 'отрок' is valid."""
        m = marriage(1, 14, 1,
                     person("Иван", status="отрок"),
                     person("Мария"),
                     groom_marriage_num=1)
        self.assertEqual(m.groom.status, "отрок")

    def test_groom_otrok_compound_status_raises(self):
        """Groom with marriage_num > 1 and compound status containing 'отрок' → ValueError."""
        with self.assertRaises(ValueError):
            marriage(1, 14, 1,
                     person("Иван", status="отрок из экономических крестьян"),
                     person("Мария"),
                     groom_marriage_num=2)

    def test_groom_no_otrok_with_marriage_num_gt1_ok(self):
        """Groom with marriage_num > 1 and non-отрок status is valid."""
        m = marriage(1, 14, 1,
                     person("Иван", status="крестьянин"),
                     person("Мария"),
                     groom_marriage_num=2)
        self.assertEqual(m.groom_marriage_num, 2)

    def test_bride_otrokovitsa_with_marriage_num_gt1_raises(self):
        """Bride with marriage_num > 1 and status containing 'отроковица' → ValueError."""
        with self.assertRaises(ValueError) as ctx:
            marriage(1, 14, 1,
                     person("Иван"),
                     person("Мария", status="отроковица"),
                     bride_marriage_num=2)
        msg = str(ctx.exception)
        self.assertIn("отроковица", msg)
        self.assertIn("marriage_num=2", msg)

    def test_bride_otrokovitsa_with_marriage_num_1_ok(self):
        """Bride with marriage_num=1 and status 'отроковица' is valid."""
        m = marriage(1, 14, 1,
                     person("Иван"),
                     person("Мария", status="отроковица"),
                     bride_marriage_num=1)
        self.assertEqual(m.bride.status, "отроковица")

    def test_bride_otrokovitsa_compound_status_raises(self):
        """Bride with marriage_num > 1 and compound status containing 'отроковица' → ValueError."""
        with self.assertRaises(ValueError):
            marriage(1, 14, 1,
                     person("Иван"),
                     person("Мария", status="отроковица из экономических крестьян"),
                     bride_marriage_num=2)

    def test_bride_no_otrokovitsa_with_marriage_num_gt1_ok(self):
        """Bride with marriage_num > 1 and non-отроковица status is valid."""
        m = marriage(1, 14, 1,
                     person("Иван"),
                     person("Мария", status="крестьянка"),
                     bride_marriage_num=2)
        self.assertEqual(m.bride_marriage_num, 2)


class TestMarriageMonthHelper(unittest.TestCase):
    def test_marriage_month_sets_month(self):
        """Test that marriage_month helper sets wedding month."""
        # Create marriages without month specified
        m1 = marriage(1, 14, groom=person("Иван", gender=Gender.MALE), bride=person("Мария", gender=Gender.FEMALE))
        m2 = marriage(2, 20, groom=person("Петр", gender=Gender.MALE), bride=person("Анна", gender=Gender.FEMALE))

        # Group by month
        january_marriages = marriage_month(Month.JANUARY, m1, m2)

        # Verify returns list
        self.assertIsInstance(january_marriages, list)
        self.assertEqual(len(january_marriages), 2)

        # Verify months are set
        self.assertEqual(january_marriages[0].w_month, Month.JANUARY)
        self.assertEqual(january_marriages[1].w_month, Month.JANUARY)

    def test_marriage_month_deep_copies(self):
        """Test that marriage_month creates deep copies."""
        m1 = marriage(1, 14, groom=person("Иван", gender=Gender.MALE), bride=person("Мария", gender=Gender.FEMALE))

        january_marriages = marriage_month(Month.JANUARY, m1)

        # Verify it's a different object
        self.assertIsNot(january_marriages[0], m1)
        self.assertIsNot(january_marriages[0].groom, m1.groom)

    def test_marriage_month_preserves_existing_month(self):
        """Test that marriage_month doesn't overwrite existing month."""
        # Create marriage with month already set
        m1 = marriage(1, 14, Month.FEBRUARY, groom=person("Иван", gender=Gender.MALE), bride=person("Мария", gender=Gender.FEMALE))

        # Try to group by January
        january_marriages = marriage_month(Month.JANUARY, m1)

        # Original month should be preserved
        self.assertEqual(january_marriages[0].w_month, Month.FEBRUARY)

    def test_marriage_supports_witness5_and_witness6(self):
        """Marriage stores witness5 and witness6, with auto gender detection on each."""
        groom = person("Иван", gender=Gender.MALE)
        bride = person("Мария", gender=Gender.FEMALE)
        w5 = person("Василий")  # auto-detect: MALE
        w6 = person("Давид")    # auto-detect: MALE
        m = Marriage(1, 14, 1, groom, bride, witness5=w5, witness6=w6)
        self.assertIs(m.witness5, w5)
        self.assertIs(m.witness6, w6)
        self.assertEqual(m.witness5.gender, Gender.MALE)
        self.assertEqual(m.witness6.gender, Gender.MALE)

    def test_marriage_factory_passes_witness5_and_witness6(self):
        """The marriage() factory threads witness5/witness6 into the Marriage."""
        groom = person("Иван", gender=Gender.MALE)
        bride = person("Мария", gender=Gender.FEMALE)
        w5 = person("Трифон")
        w6 = person("Климент")
        m = marriage(1, 14, 1, groom, bride, witness5=w5, witness6=w6)
        self.assertIs(m.witness5, w5)
        self.assertIs(m.witness6, w6)

    def test_marriage_supports_per_record_village_and_church_override(self):
        """marriage(village=..., church=...) is preserved on the resulting Marriage."""
        m = marriage(1, 14, 1,
                     groom=person("Иван", gender=Gender.MALE),
                     bride=person("Мария", gender=Gender.FEMALE),
                     village="Неелово", church="Покровская")
        self.assertEqual(m.village, "Неелово")
        self.assertEqual(m.church, "Покровская")

    def test_marriage_default_village_and_church_are_none(self):
        """Marriage without per-record village/church leaves both as None."""
        m = marriage(1, 14, 1,
                     groom=person("Иван", gender=Gender.MALE),
                     bride=person("Мария", gender=Gender.FEMALE))
        self.assertIsNone(m.village)
        self.assertIsNone(m.church)

    def test_record_defaults_apply_to_witness5_and_witness6(self):
        """RecordDefaults.apply_to_marriage populates witness5 and witness6."""
        defaults = RecordDefaults(residence="V", status_male="s")
        groom = person("Иван")
        bride = person("Мария")
        w5 = person("Василий")
        w6 = person("Давид")
        m = Marriage(1, 1, 1, groom, bride, witness5=w5, witness6=w6)
        defaults.apply_to_marriage(m)
        self.assertEqual(w5.residence, "V")
        self.assertEqual(w5.status, "s")
        self.assertEqual(w6.residence, "V")
        self.assertEqual(w6.status, "s")


class TestMarriageReviewedFlag(unittest.TestCase):
    def test_marriage_reviewed_is_unstated_until_its_record_set_resolves_it(self):
        m = marriage(1, 7, groom=person("Иван"), bride=person("Мария"))
        self.assertIsNone(m.reviewed)
        records = marriage_records("A", "1", "1", "1", "Тестовка", "Никольская", 1880, m)
        self.assertIs(True, records.records[0].reviewed)

    def test_marriage_reviewed_false_propagates_through_factory(self):
        m = marriage(1, 7, groom=person("Иван"), bride=person("Мария"), reviewed=False)
        self.assertFalse(m.reviewed)


if __name__ == '__main__':
    unittest.main()


class TestRelativeDrivenSurname(unittest.TestCase):
    """A partner with no surname of their own inherits the one their father
    relative carries — the rule Death.__init__ has always applied to the
    deceased (deaths.py), extended to the marriage partners."""

    def _m(self, groom=None, bride=None, relatives=None):
        return marriage(4, 26, groom=groom, bride=bride, relatives=relatives or [])

    def test_bride_takes_her_fathers_feminized_surname_as_maiden(self):
        # A marriage where the bride's maiden surname is derivable from her
        # father relative: Агафья Егорова, father Егоръ Никифоровъ Видоплясовъ.
        # It was left empty.
        m = self._m(
            groom=person("Григорій", "Петровъ", "Лясоточкинъ"),
            bride=person("Агафья", "Егорова"),
            relatives=[relative(person("Егоръ", "Никифоровъ", "Видоплясовъ"),
                                Relationship.FATHER, "невеста")],
        )
        self.assertEqual(m.bride.last_name_modern, "Видоплясова")
        self.assertFalse(m.bride.last_name_in_book)
        self.assertFalse(m.bride.last_name)

    def test_groom_takes_his_fathers_surname(self):
        m = self._m(
            groom=person("Марка", "Григорьевъ"),
            relatives=[relative(person("Григорій", "Ивановъ", "Брюхинъ"),
                                Relationship.FATHER, "жених")],
        )
        self.assertEqual(m.groom.last_name_modern, "Брюхин")
        self.assertFalse(m.groom.last_name_in_book)

    def test_a_partner_who_has_a_surname_keeps_it(self):
        m = self._m(
            groom=person("Марка", "Григорьевъ", "Семечкинъ"),
            relatives=[relative(person("Григорій", "Ивановъ", "Брюхинъ"),
                                Relationship.FATHER, "жених")],
        )
        self.assertEqual(m.groom.last_name, "Семечкинъ")
        self.assertEqual(m.groom.last_name_modern, "Семечкин")

    def test_the_other_partners_father_is_not_used(self):
        # A father refd to the BRIDE must never name the groom.
        m = self._m(
            groom=person("Марка", "Григорьевъ"),
            bride=person("Агафья", "Егорова"),
            relatives=[relative(person("Егоръ", "Никифоровъ", "Видоплясовъ"),
                                Relationship.FATHER, "невеста")],
        )
        self.assertFalse(m.groom.last_name_modern)

    def test_a_surnameless_father_derives_nothing(self):
        m = self._m(
            groom=person("Марка", "Григорьевъ"),
            relatives=[relative(person("Григорій", "Ивановъ"),
                                Relationship.FATHER, "жених")],
        )
        self.assertFalse(m.groom.last_name_modern)
