"""Tests for all_persons.py — relatives insertion in births and marriages."""
import sqlite3
import unittest
from calendar import Month

from verso.ru.cli.all_persons import create_db, insert_births, insert_marriages, insert_name_lists
from verso.ru.dsl.records.births import Birth, BirthRecords
from verso.ru.domain import Gender, Person
from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.relationship import Relationship, relative


def _person(name, last_name=None):
    return Person(name_orig=name, last_name=last_name)


def _make_birth_records(year, records):
    return BirthRecords(
        archive="ГАТО", fund="1049", inventory="3", case="1",
        village="Заманиловка", church="Покровская", year=year, records=records,
    )


def _make_marriage_records(year, records):
    return MarriageRecords(
        archive="ГАТО", fund="1049", inventory="3", case="1",
        village="Заманиловка", church="Покровская", year=year, records=records,
    )


class TestInsertBirthsWithRelatives(unittest.TestCase):
    def test_relatives_inserted(self):
        conn = sqlite3.connect(":memory:")
        create_db(conn)

        b = Birth(
            record_num=1, gender=Gender.MALE,
            b_day=5, b_month=Month.JANUARY,
            child=_person("Иван"),
            father=_person("Петр"),
            relatives=[relative(_person("Спиридон", "Петров"), Relationship.FATHER, "мать")],
        )
        records = _make_birth_records(1820, [b])
        count = insert_births(conn, records, "test.py")

        persons = conn.execute("SELECT role, last_name FROM persons").fetchall()
        roles = {r[0] for r in persons}
        self.assertIn("отец", roles)
        # child + father + relative = 3
        self.assertEqual(count, 3)
        # Check the relative's last name
        rel_row = conn.execute("SELECT last_name FROM persons WHERE role='отец' AND last_name='Петров'").fetchone()
        self.assertIsNotNone(rel_row)
        conn.close()

    def test_no_relatives(self):
        conn = sqlite3.connect(":memory:")
        create_db(conn)

        b = Birth(
            record_num=1, gender=Gender.FEMALE,
            child=_person("Мария"),
            father=_person("Иван"),
            god_parent1=_person("Анна"),
        )
        records = _make_birth_records(1820, [b])
        count = insert_births(conn, records, "test.py")
        # child + father + godparent = 3
        self.assertEqual(count, 3)
        conn.close()


class TestInsertMarriagesWithRelatives(unittest.TestCase):
    def test_relatives_inserted(self):
        conn = sqlite3.connect(":memory:")
        create_db(conn)

        m = Marriage(
            record_num=1, w_day=10, w_month=Month.FEBRUARY,
            groom=_person("Василий"),
            bride=_person("Евдокия"),
            witness1=_person("Сидор"),
            relatives=[relative(_person("Матфей", "Данилов"), Relationship.FATHER, "невеста")],
        )
        records = _make_marriage_records(1820, [m])
        count = insert_marriages(conn, records, "test.py")

        persons = conn.execute("SELECT role, last_name FROM persons").fetchall()
        roles = {r[0] for r in persons}
        self.assertIn("отец", roles)
        # groom + bride + witness + relative = 4
        self.assertEqual(count, 4)
        rel_row = conn.execute("SELECT last_name FROM persons WHERE role='отец' AND last_name='Данилов'").fetchone()
        self.assertIsNotNone(rel_row)
        conn.close()

    def test_no_relatives(self):
        conn = sqlite3.connect(":memory:")
        create_db(conn)

        m = Marriage(
            record_num=1, w_day=10,
            groom=_person("Василий"),
            bride=_person("Евдокия"),
            witness1=_person("Сидор"),
        )
        records = _make_marriage_records(1820, [m])
        count = insert_marriages(conn, records, "test.py")
        # groom + bride + witness = 3
        self.assertEqual(count, 3)
        conn.close()


class TestInsertNameLists(unittest.TestCase):
    def test_listed_person_inserted_with_generic_record_type(self):
        conn = sqlite3.connect(":memory:")
        create_db(conn)

        records = name_list_records(
            "ГАРО", "F", "I", "C", "Маниловка", 1917,
            listed_person(373, _person("Анастасия", "Телятникова"), age=62),
            document_type="Список избирателей на выборах в Учредительное собрание",
        )
        count = insert_name_lists(conn, records, "test.py")
        self.assertEqual(count, 1)

        row = conn.execute(
            "SELECT record_type, role, birth_date FROM persons"
        ).fetchone()
        self.assertEqual(row[0], "Именной список")
        self.assertEqual(row[1], "listed")
        self.assertEqual(row[2], "1855")
        conn.close()


if __name__ == "__main__":
    unittest.main()
