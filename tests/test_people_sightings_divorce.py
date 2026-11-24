"""The people index and an act of divorce: the facts read a divorce, the index of people a card offers does not.

`sightings_of` hands a file's record sets to the facts layer's reader. A divorce's people have no card on the review
page and no profile, and an age an act of the registry gives is of unknown basis — so a divorce beside a book adds
no one to the index and shapes no one's life in it.
"""
from __future__ import annotations

from calendar import Month

from verso.ru.domain import EventDate, person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.divorces import divorce, divorce_records
from verso.ru.gender import Gender
from verso.ru.persons.people import sightings_of


def _births():
    return birth_records(
        "ГА Глуповской области", "10", "4", "4070", "Маниловка", "Церковь", 1925,
        birth(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY, child=person("Иванъ"), father=person("Петръ", "Лукинъ"),
              god_parent1=person("Иванъ", "Петровъ", "Справкинъ")))


def _divorces():
    return divorce_records(
        "ГА Глуповской области", "10", "4", "4071", "Маниловка", "", 1925,
        divorce(1, 3, Month.JULY, husband=person("Иванъ", "Петровъ", "Справкинъ"), wife=person("Анна", "Ильина"),
                husband_age=30, wife_age=27, marriage_date=EventDate(1920, Month.SEPTEMBER, 12)))


def _seen(namespace):
    return sightings_of(namespace, village="Маниловка", year=1925, file="1925/manilovka_1925.py")


def test_a_divorce_adds_no_one_to_the_people_index():
    with_a_divorce = _seen({"births": _births(), "divorces": _divorces()})
    assert with_a_divorce == _seen({"births": _births()})
    assert with_a_divorce, "the book's people are there"
    assert _seen({"divorces": _divorces()}) == []


_LOADER_UNTOUCHED = '''
import sys
from calendar import Month
from verso.ru.domain import EventDate, person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.divorces import divorce, divorce_records
from verso.ru.gender import Gender
from verso.ru.persons.people import sightings_of

births = birth_records("ГА Глуповской области", "10", "4", "4070", "Маниловка", "Церковь", 1925,
                       birth(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY, child=person("Иванъ"),
                             father=person("Петръ", "Лукинъ")))
divorces = divorce_records("ГА Глуповской области", "10", "4", "4071", "Маниловка", "", 1925,
                           divorce(1, 3, Month.JULY, husband=person("Иванъ", "Петровъ"), wife=person("Анна", "Ильина"),
                                   marriage_date=EventDate(1920, Month.SEPTEMBER, 12)))
assert sightings_of({"births": births, "divorces": divorces}, village="Маниловка", year=1925,
                    file="1925/manilovka_1925.py")
print(sorted(m for m in sys.modules if m.startswith(("verso.core.pipeline.load", "verso.app_dsl", "corpus"))))
'''


def test_the_people_index_imports_no_loader_of_the_dsl():
    """verso-app asks the people index while it serves a request, and a server never loads the DSL there: the
    record sets it reads are named without `verso.core.pipeline.load` (nor the App's DSL adapter, nor a corpus's
    statuses — the modules its boundary refuses). A fresh interpreter, so no other test's imports hide one."""
    import subprocess
    import sys

    done = subprocess.run([sys.executable, "-c", _LOADER_UNTOUCHED], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "[]", done.stdout
