"""A book of the civil registry — `birth_records(..., civil=True)` and its kin.

A ZAGS book records the same events as a parish one, with the same people, so it is the same
record kinds. What differs is the second date of an entry: a parish book christens and buries,
a civil one REGISTERS. With `civil=True` that date is the registration's — the translator emits
no baptism or burial from it, the documents are titled after the civil book, the CSVs leave the
christening and burial columns empty, and the facts layer asserts no baptism or burial.
"""
from __future__ import annotations

import csv
import json
import re
import tempfile
import unittest
from calendar import Month

from verso.core.records.decode import decode_file
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.domain import Gender, person
from verso.ru.dsl.records.births import birth, birth_month, birth_records
from verso.ru.dsl.records.deaths import death, death_month, death_records
from verso.ru.dsl.records.marriages import marriage, marriage_month, marriage_records
from verso.ru.exporters.csv_familio import BirthRecordsCsvFamilioExporter, DeathRecordsCsvFamilioExporter
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.model import AssertionSet, BaptizedOn, BornOn, BuriedOn, DiedOn
from verso.ru.targets.geni.translator import TerraformGenerator


def _flag(civil: bool) -> dict[str, bool]:
    """A parish book as one is written: without the flag."""
    return {"civil": True} if civil else {}


def _births(*, civil: bool, k_day: int | None = 9):
    return birth_records(
        "А", "10", "2", "33", "Горюхино", "", 1920,
        *birth_month(Month.MARCH,
                     birth(14, Gender.MALE, 4, k_day,
                           child=person("Петр"),
                           father=person("Иван", "Семенов", "Ковыльков"),
                           mother=person("Мария", "Андреева"))),
        **_flag(civil),
    )


def _deaths(*, civil: bool):
    return death_records(
        "А", "10", "2", "34", "Горюхино", "", 1920,
        *death_month(Month.APRIL,
                     death(3, Gender.MALE, 11, 13,
                           deceased=person("Семен", "Петров", "Ковыльков"), age=60)),
        **_flag(civil),
    )


def _marriages(*, civil: bool):
    return marriage_records(
        "А", "10", "2", "35", "Горюхино", "", 1920,
        *marriage_month(Month.MAY,
                        marriage(7, 16,
                                 groom=person("Андрей", "Иванов", "Ковыльков"), groom_age=22,
                                 bride=person("Анна", "Петрова", "Синицына"), bride_age=19)),
        **_flag(civil),
    )


def _text_body(output: str) -> str:
    block = re.search(r"text\s*=\s*<<-EOT\n(.+?)\n\s*EOT", output, re.DOTALL)
    assert block is not None, output
    return block.group(1)


class TheFlag(unittest.TestCase):
    def test_a_book_is_parish_unless_it_says_civil(self):
        book = _births(civil=False)
        self.assertFalse(book.civil)
        self.assertFalse(book.records[0].civil)

    def test_civil_reaches_every_record_of_every_kind(self):
        for book in (_births(civil=True), _deaths(civil=True), _marriages(civil=True)):
            self.assertTrue(book.civil)
            self.assertTrue(all(r.civil for r in book.records))

    def test_the_records_json_keeps_it(self):
        ns = {"births": _births(civil=True), "deaths": _deaths(civil=True)}
        doc = encode_namespace(ns, village="Горюхино", file="1920/f.py", sha256="0" * 64, ids=Ids())
        back = decode_file(json.loads(json.dumps(doc, ensure_ascii=False)))
        self.assertTrue(back["births"].civil)
        self.assertTrue(back["births"].records[0].civil)
        self.assertTrue(back["deaths"].records[0].civil)

    def test_a_parish_book_writes_no_civil_field_into_the_json(self):
        doc = encode_namespace({"births": _births(civil=False)}, village="Горюхино", file="1920/f.py",
                               sha256="0" * 64, ids=Ids())
        self.assertNotIn("civil", json.dumps(doc, ensure_ascii=False))


class TheTranslator(unittest.TestCase):
    def _birth_output(self, **kw) -> str:
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(_births(**kw))
        return gen.get_output("mk_1920_birth.tf")

    def test_a_civil_birth_has_no_baptism(self):
        self.assertNotIn("baptism", self._birth_output(civil=True))
        self.assertIn("baptism", self._birth_output(civil=False))

    def test_a_civil_birth_is_titled_after_the_civil_book(self):
        output = self._birth_output(civil=True)
        self.assertIn('title       = "Книга ЗАГС Горюхино 1920: рождение Петр"', output)
        self.assertNotIn("Метрическая книга", output)
        self.assertIn("<strong>ЗАГС Горюхино 1920:</strong> рождение", output)
        self.assertNotIn("<strong>МК ", output)

    def test_the_second_date_of_a_civil_birth_is_its_registration(self):
        text = _text_body(self._birth_output(civil=True))
        self.assertIn("Дата рождения: 4.3.1920", text)
        self.assertIn("Дата регистрации: 9.3.1920", text)
        self.assertNotIn("крещ", text.lower())

    def test_a_registration_not_written_is_not_printed(self):
        text = _text_body(self._birth_output(civil=True, k_day=None))
        self.assertNotIn("Дата регистрации", text)

    def test_a_civil_death_has_no_burial(self):
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(_deaths(civil=True))
        output = gen.get_output("mk_1920_death.tf")
        self.assertNotIn("burial", output)
        self.assertIn("Книга ЗАГС Горюхино 1920: смерть", output)
        self.assertIn("<strong>ЗАГС Горюхино 1920:</strong>", output)
        self.assertIn("Дата регистрации: 13.4.1920", _text_body(output))

    def test_a_parish_death_keeps_its_burial(self):
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(_deaths(civil=False))
        self.assertIn("burial", gen.get_output("mk_1920_death.tf"))

    def test_a_civil_marriage_is_registered_not_wed(self):
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(_marriages(civil=True))
        output = gen.get_output("mk_1920_marriage.tf")
        self.assertIn("Книга ЗАГС Горюхино 1920: брак", output)
        self.assertNotIn("Метрическая книга", output)
        text = _text_body(output)
        self.assertIn("Дата регистрации: 16.5.1920", text)
        self.assertNotIn("венчания", text)


class TheCsv(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _rows(self, exporter, book) -> list[dict[str, str]]:
        path = exporter.export(book, target_dir=self.dir)
        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            return [list(zip(header, row, strict=True)) for row in reader]  # type: ignore[misc]

    @staticmethod
    def _col(row, name: str, nth: int = 0) -> str:
        return [v for k, v in row if k == name][nth]

    def test_a_civil_birth_has_no_christening_columns(self):
        row = self._rows(BirthRecordsCsvFamilioExporter(), _births(civil=True))[0]
        for name in ("Крещ. День", "Крещ. Месяц", "Крещ. Год"):
            self.assertEqual(self._col(row, name), "", name)
        self.assertIn("зарегистрировано 9.3.1920", self._col(row, "Комментарий"))
        self.assertEqual(self._col(row, "Рожд. День"), "4")

    def test_a_parish_birth_keeps_them(self):
        row = self._rows(BirthRecordsCsvFamilioExporter(), _births(civil=False))[0]
        self.assertEqual(self._col(row, "Крещ. День"), "9")
        self.assertNotIn("зарегистрировано", self._col(row, "Комментарий"))

    def test_a_civil_birth_registered_on_no_written_day_says_nothing(self):
        row = self._rows(BirthRecordsCsvFamilioExporter(), _births(civil=True, k_day=None))[0]
        self.assertEqual(self._col(row, "Крещ. Месяц"), "")
        self.assertNotIn("зарегистрировано", self._col(row, "Комментарий"))

    def test_a_civil_death_has_no_burial_columns(self):
        row = self._rows(DeathRecordsCsvFamilioExporter(), _deaths(civil=True))[0]
        # The death's three columns, then the burial's, are headed alike.
        self.assertEqual([self._col(row, n, 0) for n in ("День", "Месяц", "Год")], ["11", "4", "1920"])
        self.assertEqual([self._col(row, n, 1) for n in ("День", "Месяц", "Год")], ["", "", ""])
        self.assertIn("зарегистрировано 13.4.1920", self._col(row, "пометки"))


class TheFacts(unittest.TestCase):
    @staticmethod
    def _facts(extract, book) -> AssertionSet:
        for r in book.records:
            r.year = r.year or book.year
        return AssertionSet(extract([(r, "f.py") for r in book.records], village="Горюхино"))

    def test_a_civil_birth_asserts_the_birth_and_no_baptism(self):
        facts = self._facts(facts_from_births, _births(civil=True))
        self.assertEqual(len(facts.of(BornOn)), 1)
        self.assertEqual(facts.of(BaptizedOn), ())

    def test_a_civil_death_asserts_the_death_and_no_burial(self):
        facts = self._facts(facts_from_deaths, _deaths(civil=True))
        self.assertEqual(len(facts.of(DiedOn)), 1)
        self.assertEqual(facts.of(BuriedOn), ())

    def test_a_parish_book_still_baptizes_and_buries(self):
        self.assertEqual(len(self._facts(facts_from_births, _births(civil=False)).of(BaptizedOn)), 1)
        self.assertEqual(len(self._facts(facts_from_deaths, _deaths(civil=False)).of(BuriedOn)), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
