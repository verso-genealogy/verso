import csv
import os
import tempfile
import unittest
from calendar import Month

from verso.ru.dsl.records.births import Birth, BirthRecords, christening
from verso.ru.ages import split_age as _split_age
from verso.ru.exporters.csv_familio import BirthRecordsCsvFamilioExporter, DeathRecordsCsvFamilioExporter, DivorceRecordsCsvFamilioExporter
from verso.ru.dsl.records.deaths import Death, DeathRecords
from verso.ru.dsl.records.divorces import Divorce, DivorceRecords
from verso.ru.gender import Gender
from verso.ru.domain import EventDate, Person
from verso.ru.relationship import Relationship, Relative


class TestBirthRecordsCsvFamilioExporter(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up after tests."""
        os.chdir(self.original_cwd)
        # Clean up temp files
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_exporter_creates_file_with_correct_name(self):
        """Test that exporter creates a file with the correct naming convention."""
        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        expected_filename = os.path.join(os.path.realpath(self.temp_dir), "Заманиловка_1804_births_familio.csv")
        self.assertEqual(os.path.realpath(filename), expected_filename)
        self.assertTrue(os.path.exists(filename))

    def test_header_count_matches_row_count(self):
        """Test that the number of headers matches the number of columns in each row."""
        child = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        father = Person("Петръ", "Васильевъ", name_modern_orth="Петр", patr_old="Васильев",
                        residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        mother = Person("Марія", "Петрова", name_modern_orth="Мария", patr_old="Петрова",
                        status="крестьянская жена", gender=Gender.FEMALE)
        god_parent1 = Person("Николай", "Иванов", name_modern_orth="Николай", patr_old="Иванов",
                             residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        god_parent2 = Person("Анна", "Сидорова", name_modern_orth="Анна", patr_old="Сидорова",
                             residence="Заманиловка", status="крестьянка", gender=Gender.FEMALE)

        birth = Birth(record_num=1, gender=Gender.MALE, b_day=15, k_day=17, b_month=Month.JANUARY,
                      k_month=Month.JANUARY, child=child, father=father, mother=mother, god_parent1=god_parent1,
                      god_parent2=god_parent2, page="12об")

        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[birth]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            data_row = next(reader)

            self.assertEqual(len(headers), len(data_row),
                           f"Header count ({len(headers)}) does not match row count ({len(data_row)})")

    def test_complete_birth_record_export(self):
        """Test export of a complete birth record with all fields populated."""
        child = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        father = Person("Петръ", "Васильевъ", last_name="Иванов", name_modern_orth="Петр", patr_old="Васильев",
                        residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        mother = Person("Марія", "Петрова", last_name="Иванова", name_modern_orth="Мария", patr_old="Петрова",
                        status="крестьянская жена", gender=Gender.FEMALE)
        god_parent1 = Person("Николай", "Ивановъ", name_modern_orth="Николай", patr_old="Иванов",
                             residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        god_parent2 = Person("Анна", "Сидорова", name_modern_orth="Анна", patr_old="Сидорова",
                             residence="Заманиловка", status="крестьянка", gender=Gender.FEMALE)

        birth = Birth(record_num=1, gender=Gender.MALE, b_day=15, k_day=17, b_month=Month.JANUARY,
                      k_month=Month.JANUARY, child=child, father=father, mother=mother, god_parent1=god_parent1,
                      god_parent2=god_parent2, page="12об", comment="Тестовый комментарий")

        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[birth]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Check key fields
            self.assertEqual(row[0], "")  # № п/п (empty in production)
            self.assertEqual(row[1], "ГАТО")  # Архив
            self.assertEqual(row[2], "284")  # Фонд
            self.assertEqual(row[3], "1")  # Опись
            self.assertEqual(row[4], "123")  # Дело
            self.assertEqual(row[5], "12об")  # Лист
            self.assertEqual(row[6], "Заманиловка")  # Н.П. события
            self.assertEqual(row[8], "Троицкая церковь")  # Церковь / Приход
            self.assertEqual(row[9], "рождение")  # Событие (lowercase)
            self.assertEqual(row[11], "муж")  # Пол
            self.assertEqual(row[12], "15")  # Рожд. День
            self.assertEqual(row[13], "1")  # Рожд. Месяц (1 = January)
            self.assertEqual(row[14], "1804")  # Рожд. Год
            self.assertEqual(row[15], "17")  # Крещ. День
            self.assertEqual(row[16], "1")  # Крещ. Месяц (1 = January)
            self.assertEqual(row[17], "1804")  # Крещ. Год
            self.assertEqual(row[18], "Иван")  # Имя реб. (совр. орф.)
            self.assertEqual(row[19], "Иоанн")  # Имя реб. (совр.)
            self.assertEqual(row[20], "Заманиловка")  # Отец: Н.П.
            self.assertEqual(row[22], "крестьянин")  # Отец: Статус
            self.assertEqual(row[23], "Иванов")  # Отец: Фамилия
            self.assertEqual(row[25], "Петр")  # Отец: Имя (совр. орф.)
            self.assertEqual(row[26], "Васильев")  # Отец: Отчество (совр. орф.)
            self.assertEqual(row[27], "Петр")  # Отец: Имя (совр.)
            self.assertEqual(row[28], "Васильевич")  # Отец: Отчество (совр.)
            self.assertEqual(row[29], "крестьянская жена")  # Мать: Статус
            self.assertEqual(row[30], "Иванова")  # Мать: Фамилия
            self.assertEqual(row[31], "Мария")  # Мать: Имя (совр. орф.)
            self.assertEqual(row[32], "Петрова")  # Мать: Отчество (совр. орф.)
            self.assertEqual(row[33], "Мария")  # Мать: Имя (совр.)
            self.assertEqual(row[34], "Петровна")  # Мать: Отчество (совр.)

            # Check godparents
            self.assertEqual(row[35], "крестьянин")  # Восприемник 1: Статус
            self.assertEqual(row[36], "Заманиловка")  # Восприемник 1: Н.П.
            self.assertEqual(row[38], "Николай")  # Восприемник 1: Имя (совр. орф.)
            self.assertEqual(row[39], "Иванов")  # Восприемник 1: Отчество (совр. орф.)
            self.assertEqual(row[42], "Николай Иванович")  # Восприемник 1: ФИО (совр.)

            self.assertEqual(row[43], "крестьянка")  # Восприемник 2: Статус
            self.assertEqual(row[44], "Заманиловка")  # Восприемник 2: Н.П.
            self.assertEqual(row[46], "Анна")  # Восприемник 2: Имя (совр. орф.)
            self.assertEqual(row[47], "Сидорова")  # Восприемник 2: Отчество (совр. орф.)
            self.assertEqual(row[50], "Анна Сидоровна")  # Восприемник 2: ФИО (совр.) - canonicalized

            # Check comment
            self.assertIn("Тестовый комментарий", row[79])  # Комментарий

    def test_minimal_birth_record_export(self):
        """Test export of a minimal birth record with only required fields."""
        child = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)

        birth = Birth(record_num=1, gender=Gender.MALE, b_day=15, k_day=15, b_month=Month.JANUARY,
                      k_month=Month.JANUARY, child=child, father=None, mother=None, god_parent1=None, god_parent2=None)

        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[birth]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)

            # Verify row has correct number of columns
            self.assertEqual(len(headers), len(row))

            # Check that child info is present
            self.assertEqual(row[18], "Иван")  # Имя реб. (совр. орф.)

            # Check that missing parents are empty strings
            self.assertEqual(row[22], "")  # Отец: Статус
            self.assertEqual(row[25], "")  # Отец: Имя (совр. орф.)
            self.assertEqual(row[29], "")  # Мать: Статус
            self.assertEqual(row[31], "")  # Мать: Имя (совр. орф.)

            # Comment field should be empty (no auto-comments in production code)
            self.assertEqual(row[79], "")

    def test_christening_record_uses_circa_birth_year_and_blank_birth_date(self):
        """A late/adult christening (age set, no birth date) leaves the
        Рожд. День/Месяц columns blank and puts a circa birth year
        (christening year − age) in Рожд. Год, keeping the real christening
        date in the Крещ. columns."""
        child = Person("Александръ", name_modern_orth="Александр", gender=Gender.MALE)

        record = christening(1, Gender.MALE, 24, Month.FEBRUARY, age=11, child=child)

        birth_records = BirthRecords(
            archive="ЦАНО", fund="1806", inventory="4", case="94",
            village="Нижняя Яичница", church="Николаевская",
            year=1900, records=[record],
        )

        filename = BirthRecordsCsvFamilioExporter().export(birth_records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

        self.assertEqual(row[12], "")      # Рожд. День (unknown)
        self.assertEqual(row[13], "")      # Рожд. Месяц (unknown)
        self.assertEqual(row[14], "1889")  # Рожд. Год = 1900 − 11 (circa)
        self.assertEqual(row[15], "24")    # Крещ. День
        self.assertEqual(row[16], "2")     # Крещ. Месяц (February)
        self.assertEqual(row[17], "1900")  # Крещ. Год

    def test_birth_export_includes_last_name_when_in_book_flag_default(self):
        """`Имена в оригинале` includes last_name by default (the book's
        ФИО carried the surname). Fixes the long-standing bug where the
        familio exporter built `name_orig + patr_orig` only, silently
        dropping every surname on round-trip."""
        from verso.ru.domain import person as _person
        child = _person("Иванъ")
        father = _person("Герасимъ", "Тихоновъ", last_name_orig="Мижуевъ")
        birth = Birth(record_num=1, gender=Gender.MALE, b_day=1, k_day=2,
                      b_month=Month.JANUARY, k_month=Month.JANUARY,
                      child=child, father=father)
        records = BirthRecords(archive="A", fund="1", inventory="1", case="1",
                               village="Горюхино", church="N", year=1838,
                               records=[birth])
        filename = BirthRecordsCsvFamilioExporter().export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        row = rows[1]
        # Column 80 (0-indexed) = "Имена в оригинале"
        self.assertIn("Герасимъ Тихоновъ Мижуевъ", row[80])

    def test_birth_export_omits_last_name_when_flag_false(self):
        """`last_name_in_book=False` → exporter drops surname from the
        `Имена в оригинале` token for that person."""
        from verso.ru.domain import person as _person
        child = _person("Иванъ")
        # Mother has known surname but it was NOT in the book's ФИО.
        mother = _person("Варвара", "Миронова",
                         last_name_orig="Мижуева",
                         last_name_in_book=False)
        father = _person("Герасимъ", "Тихоновъ", last_name_orig="Мижуевъ")
        birth = Birth(record_num=1, gender=Gender.MALE, b_day=1, k_day=2,
                      b_month=Month.JANUARY, k_month=Month.JANUARY,
                      child=child, father=father, mother=mother)
        records = BirthRecords(archive="A", fund="1", inventory="1", case="1",
                               village="Горюхино", church="N", year=1838,
                               records=[birth])
        filename = BirthRecordsCsvFamilioExporter().export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        row = rows[1]
        col_80 = row[80]
        self.assertIn("Герасимъ Тихоновъ Мижуевъ", col_80)  # father keeps
        self.assertIn("Варвара Миронова", col_80)           # mother present
        self.assertNotIn("Варвара Миронова Мижуева", col_80) # mother DROPS surname

    def test_birth_and_christening_same_date_comment(self):
        """Test that comments from record and persons are collected."""
        child = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE, comment="Младенец")
        father = Person("Петръ", "Васильевъ", name_modern_orth="Петр", patr_old="Васильев", gender=Gender.MALE,
                        comment="Отец болен")

        birth = Birth(record_num=1, gender=Gender.MALE, b_day=15, k_day=15, b_month=Month.JANUARY,
                      k_month=Month.JANUARY, child=child, father=father, mother=None, god_parent1=None,
                      god_parent2=None, comment="Крещен дома")

        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[birth]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            row = next(reader)

            comment = row[79]
            # Check that comments from record and persons are collected
            self.assertIn("Крещен дома", comment)
            self.assertIn("Младенец", comment)
            self.assertIn("Отец болен", comment)

    def test_original_names_field(self):
        """Test that original names are correctly concatenated."""
        child = Person("Іоаннъ", name_modern_orth="Иоанн", gender=Gender.MALE)
        father = Person("Петръ", "Васильевъ", name_modern_orth="Петр", patr_old="Васильев", gender=Gender.MALE)
        mother = Person("Марія", "Іванова", name_modern_orth="Мария", patr_old="Иванова", gender=Gender.FEMALE)
        god_parent1 = Person("Ѳедоръ", "Алексѣевъ", name_modern_orth="Фёдор", patr_old="Алексеев",
                             gender=Gender.MALE)
        god_parent2 = Person("Анна", name_modern_orth="Анна", gender=Gender.FEMALE)

        birth = Birth(record_num=1, gender=Gender.MALE, b_day=15, k_day=17, b_month=Month.JANUARY,
                      k_month=Month.JANUARY, child=child, father=father, mother=mother, god_parent1=god_parent1,
                      god_parent2=god_parent2)

        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[birth]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            row = next(reader)

            orig_names = row[80]  # Имена в оригинале
            # Check for "Имена в МК: " prefix
            self.assertTrue(orig_names.startswith("Имена в МК: "))
            self.assertIn("Іоаннъ", orig_names)
            self.assertIn("Петръ Васильевъ", orig_names)
            self.assertIn("Марія Іванова", orig_names)
            self.assertIn("Ѳедоръ Алексѣевъ", orig_names)
            self.assertIn("Анна", orig_names)

    def test_multiple_records_export(self):
        """Test export of multiple birth records."""
        child1 = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        child2 = Person("Марія", name_modern_orth="Мария", gender=Gender.FEMALE)

        birth1 = Birth(1, Gender.MALE, 15, 17, Month.JANUARY, Month.JANUARY, child1, None, None, None, None)
        birth2 = Birth(2, Gender.FEMALE, 20, 22, Month.FEBRUARY, Month.FEBRUARY, child2, None, None, None, None)

        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[birth1, birth2]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            rows = list(reader)

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "")  # № п/п is empty
            self.assertEqual(rows[1][0], "")  # № п/п is empty
            self.assertEqual(rows[0][10], "1")  # First record number (№ записи)
            self.assertEqual(rows[1][10], "2")  # Second record number (№ записи)
            self.assertEqual(rows[0][18], "Иван")  # First child name
            self.assertEqual(rows[1][18], "Мария")  # Second child name

    def test_empty_fields_handled_correctly(self):
        """Test that None values and missing fields don't cause errors."""
        child = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        father = Person("Петръ", patr_orig=None, last_name=None, name_modern_orth="Петр", patr_old=None,
                        residence=None, status=None, gender=Gender.MALE)

        birth = Birth(record_num=1, gender=Gender.MALE, b_day=15, k_day=17, b_month=Month.JANUARY,
                      k_month=Month.JANUARY, child=child, father=father, mother=None, god_parent1=None,
                      god_parent2=None, page=None)

        birth_records = BirthRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[birth]
        )

        exporter = BirthRecordsCsvFamilioExporter()
        filename = exporter.export(birth_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)

            # Verify no exceptions and all fields are present
            self.assertEqual(len(headers), len(row))
            self.assertEqual(row[5], "")  # Empty page
            self.assertEqual(row[23], "")  # Empty father last name
            self.assertEqual(row[26], "")  # Empty father patronymic


class TestMarriageRecordsCsvFamilioExporter(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up after tests."""
        os.chdir(self.original_cwd)
        # Clean up temp files
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_exporter_creates_file_with_correct_name(self):
        """Test that exporter creates a file with the correct naming convention."""
        from verso.ru.dsl.records.marriages import MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        marriage_records = MarriageRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[]
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(marriage_records)

        expected_filename = os.path.join(os.path.realpath(self.temp_dir), "Заманиловка_1804_marriages_familio.csv")
        self.assertEqual(os.path.realpath(filename), expected_filename)
        self.assertTrue(os.path.exists(filename))

    def test_header_count_matches_row_count(self):
        """Test that the number of headers matches the number of columns in each row."""
        from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        groom = Person("Иванъ", "Петровъ", name_modern_orth="Иван", patr_old="Петров", residence="Заманиловка",
                       status="крестьянин", gender=Gender.MALE)
        bride = Person("Марія", "Васильева", name_modern_orth="Мария", patr_old="Васильева",
                       residence="Заманиловка", status="крестьянская дочь", gender=Gender.FEMALE)
        witness1 = Person("Николай", "Сидоров", name_modern_orth="Николай", patr_old="Сидоров",
                          residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        witness2 = Person("Петръ", "Ивановъ", name_modern_orth="Петр", patr_old="Иванов", residence="Заманиловка",
                          status="крестьянин", gender=Gender.MALE)

        marriage = Marriage(
            record_num=1,
            w_day=11,
            w_month=Month.JANUARY,
            groom=groom,
            bride=bride,
            groom_marriage_num=1,
            bride_marriage_num=1,
            witness1=witness1,
            witness2=witness2,
            page="150об"
        )

        marriage_records = MarriageRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[marriage]
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(marriage_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            data_row = next(reader)

            self.assertEqual(len(headers), len(data_row),
                           f"Header count ({len(headers)}) does not match row count ({len(data_row)})")

    def test_complete_marriage_record_export(self):
        """Test export of a complete marriage record with all fields populated."""
        from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        groom = Person("Иванъ", "Петровъ", last_name="Сидоров", name_modern_orth="Иван", patr_old="Петров",
                       residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        bride = Person("Марія", "Васильева", last_name="Иванова", name_modern_orth="Мария",
                       patr_old="Васильева", residence="Заманиловка", status="крестьянская дочь",
                       gender=Gender.FEMALE)
        witness1 = Person("Николай", "Алексѣевъ", last_name="Петров", name_modern_orth="Николай",
                          patr_old="Алексеев", residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        witness2 = Person("Петръ", "Ивановъ", last_name="Николаев", name_modern_orth="Петр", patr_old="Иванов",
                          residence="Заманиловка", status="крестьянин", gender=Gender.MALE)

        marriage = Marriage(
            record_num=1,
            w_day=11,
            w_month=Month.JANUARY,
            groom=groom,
            bride=bride,
            groom_marriage_num=1,
            bride_marriage_num=1,
            witness1=witness1,
            witness2=witness2,
            page="150об",
            comment="Тестовый комментарий"
        )

        marriage_records = MarriageRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[marriage]
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(marriage_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Check key fields
            self.assertEqual(row[0], "")  # № п/п (empty)
            self.assertEqual(row[1], "ГАТО")  # Архив
            self.assertEqual(row[2], "284")  # Фонд
            self.assertEqual(row[3], "1")  # Опись
            self.assertEqual(row[4], "123")  # Дело
            self.assertEqual(row[5], "150об")  # Лист
            self.assertEqual(row[6], "Заманиловка")  # Н.П. события
            self.assertEqual(row[8], "Троицкая церковь")  # Церковь / Приход
            self.assertEqual(row[9], "брак")  # Событие
            self.assertEqual(row[10], "1")  # № записи
            self.assertEqual(row[11], "11")  # День
            self.assertEqual(row[12], "1")  # Месяц (1 = January)
            self.assertEqual(row[13], "1804")  # Год

            # Groom fields
            self.assertEqual(row[14], "Заманиловка")  # Жених: Н.П.
            self.assertEqual(row[16], "крестьянин")  # Жених: Статус
            self.assertEqual(row[17], "Сидоров")  # Жених: Фамилия
            self.assertEqual(row[19], "Иван")  # Жених: Имя (совр. орф.)
            self.assertEqual(row[20], "Петров")  # Жених: Отчество (совр. орф.)
            self.assertEqual(row[21], "Иоанн")  # Жених: Имя (совр.)
            self.assertEqual(row[22], "Петрович")  # Жених: Отчество (совр.)
            self.assertEqual(row[23], "1")  # Жених: Номер брака

            # Bride fields
            self.assertEqual(row[35], "Заманиловка")  # Невеста: Н.П.
            self.assertEqual(row[37], "крестьянская дочь")  # Невеста: Статус
            self.assertEqual(row[38], "Иванова")  # Невеста: Фамилия
            self.assertEqual(row[39], "Мария")  # Невеста: Имя (совр. орф.)
            self.assertEqual(row[40], "Васильева")  # Невеста: Отчество (совр. орф.)
            self.assertEqual(row[41], "Мария")  # Невеста: Имя (совр.)
            self.assertEqual(row[42], "Васильевна")  # Невеста: Отчество (совр.)
            self.assertEqual(row[43], "1")  # Невеста: Номер брака

            # Witness 1 fields
            self.assertEqual(row[55], "крестьянин")  # Поручитель 1: Статус
            self.assertEqual(row[56], "Заманиловка")  # Поручитель 1: Н.П.
            self.assertEqual(row[58], "Петров")  # Поручитель 1: Фамилия
            self.assertEqual(row[59], "Николай")  # Поручитель 1: Имя (совр. орф)
            self.assertEqual(row[60], "Алексеев")  # Поручитель 1: Отчество (совр. орф)
            self.assertEqual(row[63], "Петров Николай Алексеевич")  # Поручитель 1: ФИО (совр.)

            # Witness 2 fields
            self.assertEqual(row[64], "крестьянин")  # Поручитель 2: Статус
            self.assertEqual(row[65], "Заманиловка")  # Поручитель 2: Н.П.
            self.assertEqual(row[67], "Николаев")  # Поручитель 2: Фамилия
            self.assertEqual(row[72], "Николаев Петр Иванович")  # Поручитель 2: ФИО (совр.)

            # Check comment
            self.assertEqual(row[109], "Тестовый комментарий")  # Комментарий

    def test_minimal_marriage_record_export(self):
        """Test export of a minimal marriage record with only required fields."""
        from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        groom = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        bride = Person("Марія", name_modern_orth="Мария", gender=Gender.FEMALE)

        marriage = Marriage(
            record_num=1,
            w_day=11,
            w_month=Month.JANUARY,
            groom=groom,
            bride=bride
        )

        marriage_records = MarriageRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[marriage]
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(marriage_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)

            # Verify row has correct number of columns
            self.assertEqual(len(headers), len(row))

            # Check that groom/bride info is present
            self.assertEqual(row[19], "Иван")  # Жених: Имя (совр. орф.)
            self.assertEqual(row[39], "Мария")  # Невеста: Имя (совр. орф.)

            # Check that missing witnesses are empty strings
            self.assertEqual(row[55], "")  # Поручитель 1: Статус
            self.assertEqual(row[64], "")  # Поручитель 2: Статус

    def test_original_names_field(self):
        """Test that original names are correctly concatenated."""
        from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        groom = Person("Іоаннъ", "Петровъ", name_modern_orth="Иоанн", patr_old="Петров", gender=Gender.MALE)
        bride = Person("Марія", "Васильева", name_modern_orth="Мария", patr_old="Васильева",
                       gender=Gender.FEMALE)
        witness1 = Person("Ѳедоръ", "Алексѣевъ", name_modern_orth="Фёдор", patr_old="Алексеев",
                          gender=Gender.MALE)
        witness2 = Person("Николай", "Ивановъ", name_modern_orth="Николай", patr_old="Иванов",
                          gender=Gender.MALE)

        marriage = Marriage(
            record_num=1,
            w_day=11,
            w_month=Month.JANUARY,
            groom=groom,
            bride=bride,
            witness1=witness1,
            witness2=witness2
        )

        marriage_records = MarriageRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[marriage]
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(marriage_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            row = next(reader)

            orig_names = row[110]  # Имена в оригинале
            self.assertIn("Іоаннъ Петровъ", orig_names)
            self.assertIn("Марія Васильева", orig_names)
            self.assertIn("Ѳедоръ Алексѣевъ", orig_names)
            self.assertIn("Николай Ивановъ", orig_names)

    def test_multiple_records_export(self):
        """Test export of multiple marriage records."""
        from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        groom1 = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        bride1 = Person("Марія", name_modern_orth="Мария", gender=Gender.FEMALE)
        groom2 = Person("Петръ", name_modern_orth="Петр", gender=Gender.MALE)
        bride2 = Person("Анна", name_modern_orth="Анна", gender=Gender.FEMALE)

        marriage1 = Marriage(1, 11, Month.JANUARY, groom1, bride1)
        marriage2 = Marriage(2, 20, Month.FEBRUARY, groom2, bride2)

        marriage_records = MarriageRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[marriage1, marriage2]
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(marriage_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            rows = list(reader)

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "")  # № п/п is empty
            self.assertEqual(rows[1][0], "")  # № п/п is empty
            self.assertEqual(rows[0][10], "1")  # First record number (№ записи)
            self.assertEqual(rows[1][10], "2")  # Second record number (№ записи)
            self.assertEqual(rows[0][19], "Иван")  # First groom name
            self.assertEqual(rows[1][19], "Петр")  # Second groom name

    def test_empty_fields_handled_correctly(self):
        """Test that None values and missing fields don't cause errors."""
        from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        groom = Person("Иванъ", patr_orig=None, last_name=None, name_modern_orth="Иван", patr_old=None,
                       residence=None, status=None, gender=Gender.MALE)
        bride = Person("Марія", patr_orig=None, last_name=None, name_modern_orth="Мария", patr_old=None,
                       residence=None, status=None, gender=Gender.FEMALE)

        marriage = Marriage(
            record_num=1,
            w_day=11,
            w_month=Month.JANUARY,
            groom=groom,
            bride=bride,
            page=None
        )

        marriage_records = MarriageRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[marriage]
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(marriage_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)

            # Verify no exceptions and all fields are present
            self.assertEqual(len(headers), len(row))
            self.assertEqual(row[5], "")  # Empty page
            self.assertEqual(row[17], "")  # Empty groom last name
            self.assertEqual(row[20], "")  # Empty groom patronymic

    def test_marriage_with_six_witnesses_includes_all_in_imena_v_mk(self):
        """A marriage carrying witness5 and witness6 surfaces all six
        witnesses in the orig-names ('Имена в МК') comment fragment, even
        though the CSV has dedicated columns only for witnesses 1–4."""
        from verso.ru.dsl.records.marriages import marriage, marriage_records
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        m = marriage(
            1, 11, Month.JANUARY,
            groom=Person("Иванъ", "Петровъ", name_modern_orth="Иван",
                         patr_old="Петров", residence="V", gender=Gender.MALE),
            bride=Person("Марія", "Васильева", name_modern_orth="Мария",
                         patr_old="Васильева", residence="V", gender=Gender.FEMALE),
            witness1=Person("Трифон", "Кирилов", name_modern_orth="Трифон",
                            patr_old="Кирилов", gender=Gender.MALE),
            witness2=Person("Варлам", "Фатеев", name_modern_orth="Варлам",
                            patr_old="Фатеев", gender=Gender.MALE),
            witness3=Person("Михаил", "Ионин", name_modern_orth="Михаил",
                            patr_old="Ионин", gender=Gender.MALE),
            witness4=Person("Климент", "Филипов", name_modern_orth="Климент",
                            patr_old="Филипов", gender=Gender.MALE),
            witness5=Person("Василей", "Кандратьев", name_modern_orth="Василей",
                            patr_old="Кондратьев", gender=Gender.MALE),
            witness6=Person("Давид", "Сидоров", name_modern_orth="Давид",
                            patr_old="Сидоров", gender=Gender.MALE),
        )
        mr = marriage_records("A", "F", "I", "C", "V", "Ch", 1815, m)

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(mr)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)
        # Find the 'Имена в оригинале' (orig-names) column index dynamically
        # so the test isn't brittle to column re-numbering.
        orig_idx = headers.index("Имена в оригинале")
        names = row[orig_idx]
        self.assertIn("Василей", names)
        self.assertIn("Кандратьев", names)
        self.assertIn("Давид", names)
        self.assertIn("Сидоров", names)

    def _sided_row(self, *witnesses):
        from verso.ru.dsl.records.marriages import marriage, marriage_records
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        m = marriage(
            1, 11, Month.JANUARY,
            groom=Person("Иванъ", "Петровъ", name_modern_orth="Иван",
                         patr_old="Петров", residence="V", gender=Gender.MALE),
            bride=Person("Марія", "Васильева", name_modern_orth="Мария",
                         patr_old="Васильева", residence="V", gender=Gender.FEMALE),
            **{f"witness{n}": w for n, w in enumerate(witnesses, start=1)},
        )
        filename = MarriageRecordsCsvFamilioExporter().export(
            marriage_records("A", "F", "I", "C", "V", "Ch", 1864, m))
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)
        return dict(zip(headers, row, strict=True))

    @staticmethod
    def _witness(name, side=None, comment=None):
        return Person(name, "Ивановъ", patr_old="Иванов", gender=Gender.MALE,
                      side=side, comment=comment)

    def test_sides_lay_the_sureties_out_by_side(self):
        """2+2 by side: the bride's go to «Поручитель 4/5», the template's «по
        невесте №1/№2» — not to 3/4, which it reads as «по жениху №3» and «по
        невесте №1»."""
        from verso.ru.domain import Side

        row = self._sided_row(self._witness("Трифонъ", Side.GROOM),
                              self._witness("Варламъ", Side.GROOM),
                              self._witness("Михаилъ", Side.BRIDE),
                              self._witness("Климентъ", Side.BRIDE))
        self.assertIn("Трифон", row["Поручитель 1: ФИО (совр.)"])
        self.assertIn("Варлаам", row["Поручитель 2: ФИО (совр.)"])
        self.assertEqual("", row["Поручитель 3: ФИО (совр.)"])
        self.assertIn("Михаил", row["Поручитель 4: ФИО (совр.)"])
        self.assertIn("Климент", row["Поручитель 5: ФИО (совр.)"])

    def test_without_sides_the_slot_order_stands_and_slots_5_6_are_written(self):
        row = self._sided_row(*(self._witness(n) for n in
                                ("Трифонъ", "Варламъ", "Михаилъ", "Климентъ", "Давидъ")))
        self.assertIn("Михаил", row["Поручитель 3: ФИО (совр.)"])
        self.assertIn("Климент", row["Поручитель 4: ФИО (совр.)"])
        self.assertIn("Давид", row["Поручитель 5: ФИО (совр.)"])

    def test_the_side_is_written_back_into_the_comment(self):
        """What `comment="поручитель по жениху; …"` used to say, `side=` says now."""
        from verso.ru.domain import Side

        row = self._sided_row(self._witness("Трифонъ", Side.GROOM, "деревня не названа"),
                              self._witness("Михаилъ", Side.BRIDE))
        self.assertEqual("поручитель по жениху; деревня не названа; поручитель по невесте",
                         row["Комментарий"])

    def test_a_witness_without_a_side_takes_the_next_free_place(self):
        from verso.ru.domain import Side

        row = self._sided_row(self._witness("Трифонъ"),
                              self._witness("Михаилъ", Side.BRIDE))
        self.assertIn("Трифон", row["Поручитель 1: ФИО (совр.)"])
        self.assertIn("Михаил", row["Поручитель 4: ФИО (совр.)"])

    def test_marriage_per_record_village_overrides_csv_event_location(self):
        """When a Marriage carries village=, CSV column 'Н.П. события' uses
        that override; sibling records keep the records-level village."""
        from verso.ru.dsl.records.marriages import marriage, marriage_records
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter

        groom_a = Person("Иванъ", "Петровъ", name_modern_orth="Иван",
                         patr_old="Петров", residence="V", gender=Gender.MALE)
        bride_a = Person("Марія", "Васильева", name_modern_orth="Мария",
                         patr_old="Васильева", residence="V", gender=Gender.FEMALE)
        groom_b = Person("Иванъ", "Кузминъ", name_modern_orth="Иван",
                         patr_old="Казмин", residence="Ротозеево", gender=Gender.MALE)
        bride_b = Person("Федосья", "Осипова", name_modern_orth="Федосья",
                         patr_old="Осипова", residence="Горюхино", gender=Gender.FEMALE)
        mr = marriage_records(
            "A", "F", "I", "394", "Пробкино", "Христорождественская", 1815,
            marriage(11, 15, Month.FEBRUARY, groom=groom_a, bride=bride_a),
            marriage(3, 7, Month.FEBRUARY, groom=groom_b, bride=bride_b,
                     village="Неелово", church="Покровская"),
        )

        exporter = MarriageRecordsCsvFamilioExporter()
        filename = exporter.export(mr)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            rows = list(reader)
        np_idx = headers.index("Н.П. события")
        church_idx = headers.index("Церковь / Приход")
        # Find rows by groom name to avoid order dependence
        probkino_row = next(r for r in rows if r[19] == "Иван")  # has Васильева bride
        # Identify the per-village rows by looking up the bride's patronymic.
        bride_patr_idx = headers.index("Невеста: Отчество (совр. орф.)")
        neelovo_row = next(r for r in rows if r[bride_patr_idx] == "Осипова")
        probkino_row = next(r for r in rows if r[bride_patr_idx] == "Васильева")
        self.assertEqual(neelovo_row[np_idx], "Неелово")
        self.assertEqual(neelovo_row[church_idx], "Покровская")
        self.assertEqual(probkino_row[np_idx], "Пробкино")
        self.assertEqual(probkino_row[church_idx], "Христорождественская")


class TestDeathRecordsCsvFamilioExporter(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up after tests."""
        os.chdir(self.original_cwd)
        # Clean up temp files
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_exporter_creates_file_with_correct_name(self):
        """Test that exporter creates a file with the correct naming convention."""
        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        expected_filename = os.path.join(os.path.realpath(self.temp_dir), "Заманиловка_1804_deaths_familio.csv")
        self.assertEqual(os.path.realpath(filename), expected_filename)
        self.assertTrue(os.path.exists(filename))

    def test_header_count_matches_row_count(self):
        """Test that the number of headers matches the number of columns in each row."""
        deceased = Person("Иванъ", patr_orig="Петровъ", name_modern_orth="Иван", patr_old="Петров",
                          gender=Gender.MALE)
        relative = Person("Петръ", patr_orig="Васильевъ", name_modern_orth="Петр", patr_old="Васильев",
                          gender=Gender.MALE)
        witness1 = Person("Федоръ", patr_orig="Сидоровъ", name_modern_orth="Федор", patr_old="Сидоров",
                          gender=Gender.MALE)
        witness2 = Person("Анна", patr_orig="Иванова", name_modern_orth="Анна", patr_old="Иванова",
                          gender=Gender.FEMALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased,
            age=45,
            relatives=[Relative(relative, Relationship.FATHER)],
            witness1=witness1,
            witness2=witness2,
            page="3"
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            data_row = next(reader)

            # Verify header count is 65
            self.assertEqual(len(headers), 65)
            # Verify row count matches header count
            self.assertEqual(len(headers), len(data_row))

    def test_complete_death_record_export(self):
        """Test export of a complete death record with all optional fields."""
        deceased = Person("Иванъ", patr_orig="Петровъ", last_name="Сидоров", name_modern_orth="Иван",
                          patr_old="Петров", residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        relative = Person("Петръ", patr_orig="Васильевъ", last_name="Сидоров", name_modern_orth="Петр",
                          patr_old="Васильев", residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        witness1 = Person("Федоръ", patr_orig="Сидоровъ", name_modern_orth="Федор", patr_old="Сидоров",
                          residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        witness2 = Person("Анна", patr_orig="Иванова", name_modern_orth="Анна", patr_old="Иванова",
                          residence="Заманиловка", status="крестьянка", gender=Gender.FEMALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased,
            age=45,
            relatives=[Relative(relative, Relationship.FATHER)],
            witness1=witness1,
            witness2=witness2,
            page="3",
            comment="Тестовый комментарий"
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Verify specific field mappings
            self.assertEqual(row[0], "")  # № п/п (empty)
            self.assertEqual(row[1], "ГАТО")  # Архив
            self.assertEqual(row[2], "284")  # Фонд
            self.assertEqual(row[3], "1")  # Опись
            self.assertEqual(row[4], "123")  # Дело
            self.assertEqual(row[5], "3")  # Лист
            self.assertEqual(row[6], "Заманиловка")  # Н.П. события
            self.assertEqual(row[7], "")  # full_location
            self.assertEqual(row[8], "Троицкая церковь")  # Церковь / Приход
            self.assertEqual(row[9], "смерть")  # Событие
            self.assertEqual(row[10], "1")  # № записи
            self.assertEqual(row[11], "муж")  # Пол
            self.assertEqual(row[12], "15")  # День (death)
            self.assertEqual(row[13], str(Month.JUNE.value))  # Месяц (death)
            self.assertEqual(row[14], "1804")  # Год (death)
            self.assertEqual(row[15], "16")  # День (burial)
            self.assertEqual(row[16], str(Month.JUNE.value))  # Месяц (burial)
            self.assertEqual(row[17], "1804")  # Год (burial)
            self.assertEqual(row[18], "Заманиловка")  # Н.П. приписки (deceased)
            self.assertEqual(row[19], "")  # person_location
            self.assertEqual(row[20], "крестьянин")  # статус/чин (deceased)
            self.assertEqual(row[21], "Сидоров")  # Фамилия (deceased)
            self.assertEqual(row[22], "")  # Фамилия-2
            self.assertEqual(row[23], "Иван")  # Имя (совр. орф.) (deceased)
            self.assertEqual(row[24], "Петров")  # Отчество (совр. орф.) (deceased)
            self.assertEqual(row[25], "Иоанн")  # Имя (deceased) - canonical
            self.assertEqual(row[26], "Петрович")  # Отчество (deceased) - canonical
            self.assertEqual(row[27], "45")  # Лет
            self.assertEqual(row[28], "")  # Месяцев
            self.assertEqual(row[29], "")  # Недель
            self.assertEqual(row[30], "")  # Дней
            self.assertEqual(row[31], "отец")  # родство
            self.assertEqual(row[32], "Заманиловка")  # Н.П. приписки (relative)
            self.assertEqual(row[33], "")  # person_location
            self.assertEqual(row[34], "крестьянин")  # статус/чин (relative)
            self.assertEqual(row[35], "Сидоров")  # Фамилия (relative)
            self.assertEqual(row[36], "")  # Фамилия-2
            self.assertEqual(row[37], "Петр")  # Имя (совр. орф.) (relative)
            self.assertEqual(row[38], "Васильев")  # Отчество (совр. орф.) (relative)
            self.assertEqual(row[39], "Петр")  # Имя (relative) - canonical
            self.assertEqual(row[40], "Васильевич")  # Отчество (relative) - canonical
            self.assertEqual(row[41], "")  # Причина смерти
            self.assertEqual(row[42], "Федор")  # Имя (совр. орф.) (witness1)
            self.assertEqual(row[43], "Сидоров")  # Отчество (совр. орф.) (witness1)
            self.assertEqual(row[44], "Феодор")  # Имя (witness1) - canonical
            self.assertEqual(row[45], "Сидорович")  # Отчество (witness1) - canonical
            self.assertEqual(row[46], "Анна")  # Имя (совр. орф.) (witness2)
            self.assertEqual(row[47], "Иванова")  # Отчество (совр. орф.) (witness2)
            self.assertEqual(row[48], "Анна")  # Имя (witness2) - canonical
            self.assertEqual(row[49], "Ивановна")  # Отчество (witness2) - canonical
            # Clergy fields (50-61) should be empty
            for i in range(50, 62):
                self.assertEqual(row[i], "")
            self.assertEqual(row[62], "")  # Burial location
            self.assertEqual(row[63], "cвидетели: Федоръ Сидоровъ; Анна Иванова")  # пометки (witness names)
            # Имена в оригинале — surname included when last_name_in_book=True (default).
            self.assertEqual(row[64], "Имена в МК: Иванъ Петровъ Сидоров; Петръ Васильевъ Сидоров")

    def test_minimal_death_record_export(self):
        """Test export of a minimal death record with only required fields."""
        deceased = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)

            # Verify no errors and all fields are present
            self.assertEqual(len(headers), 65)
            self.assertEqual(len(row), 65)
            # Verify required fields
            self.assertEqual(row[10], "1")  # record_num
            self.assertEqual(row[11], "муж")  # gender
            self.assertEqual(row[23], "Иван")  # deceased name_modern
            self.assertEqual(row[25], "Иоанн")  # deceased canonical name
            # Verify optional fields are empty
            self.assertEqual(row[27], "")  # age
            self.assertEqual(row[31], "")  # relationship
            self.assertEqual(row[64], "Имена в МК: Иванъ")  # orig_names_str

    def test_auto_comment_for_same_date(self):
        """Test that original names field contains deceased info when death date equals burial date."""
        deceased = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=15,  # Same as death day
            b_month=Month.JUNE,  # Same as death month
            deceased=deceased
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Verify original names field
            self.assertEqual(row[64], "Имена в МК: Иванъ")

    def test_comment_concatenation(self):
        """Test that original names field is populated independently of comments."""
        deceased = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=15,  # Same as death day
            b_month=Month.JUNE,  # Same as death month
            deceased=deceased,
            comment="Тестовый комментарий"
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Verify original names field (comments don't affect this)
            self.assertEqual(row[64], "Имена в МК: Иванъ")

    def test_multiple_records_export(self):
        """Test export of multiple death records."""
        deceased1 = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        deceased2 = Person("Марья", name_modern_orth="Мария", gender=Gender.FEMALE)

        death1 = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased1
        )

        death2 = Death(
            record_num=2,
            gender=Gender.FEMALE,
            d_day=20,
            d_month=Month.JULY,
            b_day=21,
            b_month=Month.JULY,
            deceased=deceased2
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death1, death2]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row1 = next(reader)
            row2 = next(reader)

            # Verify record numbers
            self.assertEqual(row1[10], "1")
            self.assertEqual(row2[10], "2")
            # Verify each row has 65 columns
            self.assertEqual(len(row1), 65)
            self.assertEqual(len(row2), 65)

    def test_none_value_handling(self):
        """Test that None values are properly handled as empty strings."""
        deceased = Person("Иванъ", patr_orig=None, name_modern_orth="Иван", patr_old=None, residence=None,
                          status=None, gender=Gender.MALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased,
            age=None,
            witness1=None,
            witness2=None,
            page=None,
            comment=None
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        # Should not raise any exceptions
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Verify None fields are empty strings
            self.assertEqual(row[5], "")  # page
            self.assertEqual(row[18], "")  # deceased residence
            self.assertEqual(row[20], "")  # deceased status
            self.assertEqual(row[24], "")  # deceased patronymic modern
            self.assertEqual(row[27], "")  # age
            self.assertEqual(row[31], "")  # relationship
            self.assertEqual(row[64], "Имена в МК: Иванъ")  # orig_names_str

    def test_witness_name_separation(self):
        """Test that witness names are properly separated into individual fields."""
        deceased = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        witness1 = Person("Петръ", patr_orig="Ивановъ", name_modern_orth="Петр", patr_old="Иванов",
                          gender=Gender.MALE)
        witness2 = Person("Анна", patr_orig="Васильева", name_modern_orth="Анна", patr_old="Васильева",
                          gender=Gender.FEMALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased,
            witness1=witness1,
            witness2=witness2
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Witness 1
            self.assertEqual(row[42], "Петр")  # name_modern
            self.assertEqual(row[43], "Иванов")  # patr_modern
            self.assertEqual(row[44], "Петр")  # canonical name
            self.assertEqual(row[45], "Иванович")  # canonical patronymic
            # Witness 2
            self.assertEqual(row[46], "Анна")  # name_modern
            self.assertEqual(row[47], "Васильева")  # patr_modern
            self.assertEqual(row[48], "Анна")  # name_modern
            self.assertEqual(row[49], "Васильевна")  # canonical patronymic

    def test_empty_clergy_fields(self):
        """Test that clergy fields (columns 51-62) are empty."""
        deceased = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Verify clergy fields (50-61) are empty
            for i in range(50, 62):
                self.assertEqual(row[i], "", f"Column {i} should be empty")

    def test_empty_structural_fields(self):
        """Test that structural empty fields are correctly placed."""
        deceased = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)

        death = Death(
            record_num=1,
            gender=Gender.MALE,
            d_day=15,
            d_month=Month.JUNE,
            b_day=16,
            b_month=Month.JUNE,
            deceased=deceased
        )

        death_records = DeathRecords(
            archive="ГАТО",
            fund="284",
            inventory="1",
            case="123",
            village="Заманиловка",
            church="Троицкая церковь",
            year=1804,
            records=[death]
        )

        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(death_records)

        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

            # Verify structural empty fields
            self.assertEqual(row[7], "")  # full_location
            self.assertEqual(row[19], "")  # person_location (deceased)
            self.assertEqual(row[22], "")  # Фамилия-2 (deceased)
            self.assertEqual(row[33], "")  # person_location (relative)
            self.assertEqual(row[36], "")  # Фамилия-2 (relative)
            self.assertEqual(row[41], "")  # Cause of death
            self.assertEqual(row[62], "")  # Burial location
            self.assertEqual(row[63], "")  # пометки


class TestBirthClergyExport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def _export_birth(self, priest=None, deacon=None, dyachok=None):
        child = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        birth = Birth(
            record_num=1, gender=Gender.MALE, b_day=15, k_day=17,
            b_month=Month.JANUARY, k_month=Month.JANUARY, child=child,
            priest=priest, deacon=deacon, dyachok=dyachok,
        )
        records = BirthRecords(
            archive="ГАТО", fund="284", inventory="1", case="123",
            village="Заманиловка", church="Церковь", year=1804, records=[birth],
        )
        filename = BirthRecordsCsvFamilioExporter().export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            return next(reader)

    def test_priest_exported(self):
        priest = Person("Степан", "Космин", status="священник", gender=Gender.MALE)
        row = self._export_birth(priest=priest)
        self.assertEqual(row[71], "священник")
        # get_fio() returns canonical form
        self.assertIn("Стефан", row[72])
        self.assertNotEqual(row[72], "")

    def test_deacon_exported(self):
        deacon = Person("Иван", "Иванов", status="дьякон", gender=Gender.MALE)
        row = self._export_birth(deacon=deacon)
        self.assertEqual(row[75], "дьякон")
        self.assertIn("Иван", row[76])
        self.assertNotEqual(row[76], "")

    def test_dyachok_exported(self):
        dyachok = Person("Петр", "Петров", status="дьячок", gender=Gender.MALE)
        row = self._export_birth(dyachok=dyachok)
        self.assertEqual(row[77], "дьячок")
        self.assertIn("Петр", row[78])
        self.assertNotEqual(row[78], "")

    def test_no_clergy_empty(self):
        row = self._export_birth()
        for i in [71, 72, 75, 76, 77, 78]:
            self.assertEqual(row[i], "", f"Column {i} should be empty")


class TestMarriageClergyExport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def _export_marriage(self, priest=None, deacon=None, dyachok=None):
        from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
        from verso.ru.exporters.csv_familio import MarriageRecordsCsvFamilioExporter
        groom = Person("Иванъ", "Петровъ", name_modern_orth="Иван", patr_old="Петров",
                       residence="Заманиловка", status="крестьянин", gender=Gender.MALE)
        bride = Person("Марія", "Васильева", name_modern_orth="Мария", patr_old="Васильева",
                       residence="Заманиловка", status="крестьянская дочь", gender=Gender.FEMALE)
        marriage = Marriage(
            record_num=1, w_day=11, w_month=Month.JANUARY,
            groom=groom, bride=bride, page="10",
            priest=priest, deacon=deacon, dyachok=dyachok,
        )
        records = MarriageRecords(
            archive="ГАТО", fund="284", inventory="1", case="123",
            village="Заманиловка", church="Церковь", year=1804, records=[marriage],
        )
        filename = MarriageRecordsCsvFamilioExporter().export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            return next(reader)

    def test_priest_exported(self):
        priest = Person("Степан", "Космин", status="священник", gender=Gender.MALE)
        row = self._export_marriage(priest=priest)
        self.assertEqual(row[101], "священник")
        self.assertIn("Стефан", row[102])
        self.assertNotEqual(row[102], "")

    def test_no_clergy_empty(self):
        row = self._export_marriage()
        for i in [101, 102, 105, 106, 107, 108]:
            self.assertEqual(row[i], "", f"Column {i} should be empty")


class TestDeathClergyExport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def _export_death(self, priest=None, deacon=None, dyachok=None):
        deceased = Person("Иванъ", name_modern_orth="Иван", gender=Gender.MALE)
        death = Death(
            record_num=1, gender=Gender.MALE, d_day=15, d_month=Month.JUNE,
            b_day=16, b_month=Month.JUNE, deceased=deceased,
            priest=priest, deacon=deacon, dyachok=dyachok,
        )
        records = DeathRecords(
            archive="ГАТО", fund="284", inventory="1", case="123",
            village="Заманиловка", church="Церковь", year=1804, records=[death],
        )
        filename = DeathRecordsCsvFamilioExporter().export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            return next(reader)

    def test_priest_exported(self):
        priest = Person("Степан", "Космин", status="священник", gender=Gender.MALE)
        row = self._export_death(priest=priest)
        self.assertEqual(row[54], "священник")
        self.assertIn("Стефан", row[55])
        self.assertNotEqual(row[55], "")

    def test_deacon_exported(self):
        deacon = Person("Иван", "Иванов", status="дьякон", gender=Gender.MALE)
        row = self._export_death(deacon=deacon)
        self.assertEqual(row[58], "дьякон")
        self.assertIn("Иван", row[59])
        self.assertNotEqual(row[59], "")

    def test_no_clergy_empty(self):
        row = self._export_death()
        # Confession priest (50-53) always empty, burial priest (54-55), deacon (58-59), dyachok (60-61)
        for i in [50, 51, 54, 55, 58, 59, 60, 61]:
            self.assertEqual(row[i], "", f"Column {i} should be empty")


class TestSplitAge(unittest.TestCase):

    def test_split_age_none(self):
        self.assertEqual(_split_age(None), ("", "", "", ""))

    def test_split_age_years(self):
        self.assertEqual(_split_age(45), ("45", "", "", ""))

    def test_split_age_months(self):
        self.assertEqual(_split_age("6 м"), ("", "6", "", ""))

    def test_split_age_weeks(self):
        self.assertEqual(_split_age("2 н"), ("", "", "2", ""))

    def test_split_age_days(self):
        self.assertEqual(_split_age("3 д"), ("", "", "", "3"))

    def test_split_age_compound_years_months(self):
        self.assertEqual(_split_age("19 лет 6 мес"), ("19", "6", "", ""))

    def test_split_age_compound_all_units(self):
        self.assertEqual(_split_age("1 г 2 мес 3 нед 4 д"), ("1", "2", "3", "4"))

    def test_split_age_idiom_polgoda(self):
        self.assertEqual(_split_age("полгода"), ("", "6", "", ""))

    def test_split_age_idiom_poltora_goda(self):
        self.assertEqual(_split_age("полтора года"), ("1", "6", "", ""))

    def test_split_age_unparseable_falls_back(self):
        # Latin units, junk, etc. dump verbatim into Лет column.
        self.assertEqual(_split_age("19 yr"), ("19 yr", "", "", ""))
        self.assertEqual(_split_age("1/2"), ("1/2", "", "", ""))


class TestDeathRecordExportWithMonthAge(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)

    def test_death_record_export_with_month_age(self):
        deceased = Person("Ольга", name_modern_orth="Ольга", gender=Gender.FEMALE)
        death_rec = Death(
            record_num=1, gender=Gender.FEMALE, d_day=15, d_month=Month.AUGUST,
            deceased=deceased, age="6 м",
        )
        records = DeathRecords(
            archive="ГАТО", fund="284", inventory="1", case="123",
            village="Заманиловка", church="Успенская", year=1822, records=[death_rec],
        )
        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)
        self.assertEqual(row[27], "")   # Лет — empty for month age
        self.assertEqual(row[28], "6")  # Месяцев
        self.assertEqual(row[29], "")   # Недель
        self.assertEqual(row[30], "")   # Дней

    def test_death_record_export_with_year_age_unchanged(self):
        deceased = Person("Иван", name_modern_orth="Иван", gender=Gender.MALE)
        death_rec = Death(
            record_num=1, gender=Gender.MALE, d_day=15, d_month=Month.AUGUST,
            deceased=deceased, age=45,
        )
        records = DeathRecords(
            archive="ГАТО", fund="284", inventory="1", case="123",
            village="Заманиловка", church="Успенская", year=1822, records=[death_rec],
        )
        exporter = DeathRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)
        self.assertEqual(row[27], "45")  # Лет
        self.assertEqual(row[28], "")    # Месяцев
        self.assertEqual(row[29], "")    # Недель
        self.assertEqual(row[30], "")    # Дней


class TestDivorceRecordsCsvFamilioExporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_exporter_creates_file_with_correct_name(self):
        records = DivorceRecords(
            archive="ГАПО", fund="1605", inventory="59", case="59",
            village="Заманиловка", church="", year=1927, records=[]
        )
        exporter = DivorceRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        expected = os.path.join(os.path.realpath(self.temp_dir), "Заманиловка_1927_divorces_familio.csv")
        self.assertEqual(os.path.realpath(filename), expected)
        self.assertTrue(os.path.exists(filename))

    def test_header_count_matches_row_count(self):
        husband = Person("Федор", "Семенов", name_modern_orth="Федор", patr_old="Семенов",
                         last_name="Чичиков", residence="Заманиловка", gender=Gender.MALE)
        wife = Person("Агафья", "Андреева", name_modern_orth="Агафья", patr_old="Андреева",
                       last_name="Спорщикова", residence="Заманиловка", gender=Gender.FEMALE)
        d = Divorce(record_num=49, d_day=14, d_month=Month.JULY,
                    husband=husband, wife=wife, husband_age=19, wife_age=19,
                    marriage_date="24 февраля 1927", initiator="жена")
        records = DivorceRecords(
            archive="ГАПО", fund="1605", inventory="59", case="59",
            village="Заманиловка", church="", year=1927, records=[d]
        )
        exporter = DivorceRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            row = next(reader)
        self.assertEqual(len(headers), len(row))

    def test_complete_divorce_record_export(self):
        husband = Person("Федор", "Семенов", name_modern_orth="Федор", patr_old="Семенов",
                         last_name="Чичиков", residence="Заманиловка", gender=Gender.MALE)
        wife = Person("Евдокия", "Андреева", name_modern_orth="Евдокия", patr_old="Андреева",
                       last_name="Федулова", residence="Заманиловка", gender=Gender.FEMALE)
        d = Divorce(record_num=12, d_day=26, d_month=Month.MAY,
                    husband=husband, wife=wife, husband_age=22, wife_age=24,
                    marriage_date=EventDate(1930, Month.FEBRUARY, 13),
                    children="дочь Анна (2) при матери",
                    initiator="жена",
                    comment="Первый брак мужа")
        records = DivorceRecords(
            archive="ГАПО", fund="1605", inventory="59", case="59",
            village="Заманиловка", church="", year=1930, records=[d]
        )
        exporter = DivorceRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # skip headers
            row = next(reader)
        self.assertEqual(row[1], "ГАПО")                    # Архив
        self.assertEqual(row[2], "1605")                     # Фонд
        self.assertEqual(row[3], "59")                       # Опись
        self.assertEqual(row[4], "59")                       # Дело
        self.assertEqual(row[6], "Заманиловка")                # Н.П.
        self.assertEqual(row[7], "развод")                   # Событие
        self.assertEqual(row[8], "12")                       # № записи
        self.assertEqual(row[9], "26")                       # День
        self.assertEqual(row[11], "1930")                    # Год
        self.assertEqual(row[12], "Заманиловка")               # Муж: Н.П.
        self.assertEqual(row[13], "Чичиков")               # Муж: Фамилия
        self.assertEqual(row[14], "Феодор")                   # Муж: Имя
        self.assertEqual(row[15], "Семенович")               # Муж: Отчество
        self.assertEqual(row[16], "22")                      # Муж: Лет
        self.assertEqual(row[17], "Заманиловка")               # Жена: Н.П.
        self.assertEqual(row[18], "Федулова")                # Жена: Фамилия
        self.assertEqual(row[19], "Федулова")                # Жена: Фамилия (девичья)
        self.assertEqual(row[20], "Евдокия")                 # Жена: Имя
        self.assertEqual(row[21], "Андреевна")               # Жена: Отчество
        self.assertEqual(row[22], "24")                      # Жена: Лет
        self.assertEqual(row[23], "13 февраля 1930")         # Дата брака
        self.assertEqual(row[24], "дочь Анна (2) при матери")  # Дети
        self.assertEqual(row[25], "жена")                    # Инициатор
        self.assertEqual(row[26], "Первый брак мужа")        # Комментарий

    def test_minimal_divorce_record_export(self):
        husband = Person("Петр", "Герасимов", name_modern_orth="Петр", patr_old="Герасимов",
                         last_name="Чичиков", gender=Gender.MALE)
        wife = Person("Марфа", "Михайлова", name_modern_orth="Марфа", patr_old="Михайлова",
                       last_name="Вышивалкина", gender=Gender.FEMALE)
        d = Divorce(record_num=0, d_day=3, d_month=Month.JULY,
                    husband=husband, wife=wife, husband_age=29, wife_age=29)
        records = DivorceRecords(
            archive="ГАПО", fund="1605", inventory="59", case="59",
            village="Заманиловка", church="", year=1923, records=[d]
        )
        exporter = DivorceRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)
        self.assertEqual(row[23], "")  # no marriage_date
        self.assertEqual(row[24], "")  # no children
        self.assertEqual(row[25], "")  # no initiator
        self.assertEqual(row[26], "")  # no comment

    def test_comment_aggregation(self):
        husband = Person("Василий", name_modern_orth="Василий",
                         last_name="Лямкин", gender=Gender.MALE,
                         comment="отчество неразборчиво")
        wife = Person("Ксения", "Иванова", name_modern_orth="Ксения", patr_old="Иванова",
                       last_name="Чичикова", gender=Gender.FEMALE)
        d = Divorce(record_num=2, d_day=16, d_month=Month.JANUARY,
                    husband=husband, wife=wife,
                    comment="ЗАГС")
        records = DivorceRecords(
            archive="ГАПО", fund="1605", inventory="59", case="59",
            village="Заманиловка", church="", year=1926, records=[d]
        )
        exporter = DivorceRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)
        self.assertIn("ЗАГС", row[26])
        self.assertIn("отчество неразборчиво", row[26])

    def test_empty_records(self):
        records = DivorceRecords(
            archive="ГАПО", fund="1605", inventory="59", case="59",
            village="Заманиловка", church="", year=1927, records=[]
        )
        exporter = DivorceRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            rows = list(reader)
        self.assertEqual(len(headers), 27)
        self.assertEqual(len(rows), 0)

    def test_multiple_records(self):
        h1 = Person("Петр", "Тимофеев", name_modern_orth="Петр", patr_old="Тимофеев",
                     last_name="Макушкин", gender=Gender.MALE)
        w1 = Person("Ирина", "Васильева", name_modern_orth="Ирина", patr_old="Васильева",
                     last_name="Чичикова", gender=Gender.FEMALE)
        h2 = Person("Федор", "Семенов", name_modern_orth="Федор", patr_old="Семенов",
                     last_name="Чичиков", gender=Gender.MALE)
        w2 = Person("Евдокия", "Андреева", name_modern_orth="Евдокия", patr_old="Андреева",
                     last_name="Федулова", gender=Gender.FEMALE)
        d1 = Divorce(record_num=6, d_day=22, d_month=Month.APRIL,
                     husband=h1, wife=w1, husband_age=24, wife_age=27)
        d2 = Divorce(record_num=12, d_day=26, d_month=Month.MAY,
                     husband=h2, wife=w2, husband_age=22, wife_age=24)
        records = DivorceRecords(
            archive="ГАПО", fund="1605", inventory="59", case="59",
            village="Заманиловка", church="", year=1930, records=[d1, d2]
        )
        exporter = DivorceRecordsCsvFamilioExporter()
        filename = exporter.export(records)
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            rows = list(reader)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][8], "6")
        self.assertEqual(rows[1][8], "12")


if __name__ == '__main__':
    unittest.main()
