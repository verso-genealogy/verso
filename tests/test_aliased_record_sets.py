"""A record set bound to two names is one book, for every reader of a module's variables.

Заманиловка/1913/zamanilovka_deaths_1913.py ends with `zamanilovka_deaths_1913 =
hlestakovka_deaths_1913`. The readers below look up the variable named after the
file first, and scan every variable only when there is none — and the scan took the
book once per name. Here neither name is the file's, so the scan is what runs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from verso.ru.cli import all_persons
from verso.ru.consolidation import death_age, stale_claims
from verso.ru.dsl.records.births import BirthRecords
from verso.core.records.sets import record_sets

ALIASED = '''\
from calendar import Month

from verso.ru.dsl import Gender, person
from verso.ru.dsl import birth, birth_month, birth_records

parish_births_1800 = birth_records(
    "A", "1", "1", "1", "Тестовка", "N", 1800,
    *birth_month(Month.MARCH,
                 birth(1, Gender.MALE, 10, 11, child=person("Иван"),
                       father=person("Петр", "Сидоров"))),
)

village_births_1800 = parish_births_1800
'''


@pytest.fixture
def village(tmp_path: Path) -> Path:
    village = tmp_path / "Тестовка"
    (village / "1800").mkdir(parents=True)
    (village / "1800" / "test_births_1800.py").write_text(ALIASED, encoding="utf-8")
    return village


def test_record_sets_keeps_the_first_name():
    book = BirthRecords("A", "1", "1", "1", "Тестовка", "N", 1800, [])
    namespace = {"first": book, "label": "first", "second": book, "other": 1}
    assert record_sets(namespace, BirthRecords) == {"first": book}


def test_village_db_holds_the_book_once(village: Path):
    with mock.patch("sys.argv", ["all_persons", str(village)]):
        all_persons.main()
    with sqlite3.connect(village / "village.db") as conn:
        assert conn.execute("SELECT count(*) FROM births").fetchone()[0] == 1


def test_claim_check_reads_the_book_once(village: Path):
    assert len(stale_claims.load_all_records(village)) == 1


def test_death_age_check_reads_the_book_once(village: Path):
    births, deaths = death_age.load_village_records(village)
    assert (len(births), len(deaths)) == (1, 0)
