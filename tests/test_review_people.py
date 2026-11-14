"""verso.ru.persons.people — a whole person offered under the review page's name fields."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from verso.ru.domain.person import Person
from verso.ru.facts.checks.births import BirthSpan
from verso.ru.naming import matching
from verso.ru.persons import lives
from verso.ru.persons.lives import Clue, record_days, year_days
from verso.ru.persons.people import PeopleIndex, RecordContext, Seen, Sighting, persons, seen, sightings


def _person(name: str, patr: str | None = None, surname: str | None = None, *,
            status: str | None = None, residence: str | None = None, **kw: object) -> Person:
    return Person(name, patr, surname, residence=residence, status=status, **kw)  # type: ignore[arg-type]


def _seen(name: str, patr: str = "", surname: str = "", status: str = "", residence: str = "",
          sex: str = "", modern: tuple[str, str, str] = ("", "", "")) -> Seen:
    return Seen(name, patr, surname, status, residence, sex, modern)


class Persons(unittest.TestCase):
    def test_slots_lists_and_what_carries_a_person(self):
        father, godfather, aunt = _person("Иванъ", "Петровъ"), _person("Петръ", "Ивановъ"), _person("Анна", "Петрова")
        record = SimpleNamespace(father=father, god_parent1=godfather, relatives=[SimpleNamespace(person=aunt)],
                                 page="12об", record_num=3)
        self.assertEqual([father, godfather, aunt], list(persons(record)))

    def test_the_newborn_is_left_out(self):
        child, father = _person("Василій"), _person("Иванъ", "Петровъ")
        self.assertEqual([father], list(persons(SimpleNamespace(child=child, father=father))))

    def test_one_person_twice_is_counted_once(self):
        head = _person("Иванъ", "Петровъ")
        record = SimpleNamespace(head=head, members=[SimpleNamespace(person=head)])
        self.assertEqual([head], list(persons(record)))


class Appearance(unittest.TestCase):
    def test_the_five_fields_and_the_modern_names(self):
        found = seen(_person("Іоаннъ", "Петровъ", "Милушкинъ", status="крестьянинъ", residence="Хлестаково"))
        assert found is not None
        self.assertEqual(("Іоаннъ", "Петровъ", "Милушкинъ", "крестьянинъ", "Хлестаково"), found.written)
        self.assertEqual("м", found.sex)
        self.assertEqual("Иоанн", found.modern[0])
        self.assertEqual("Петрович", found.modern[1])

    def test_a_name_alone_says_too_little(self):
        self.assertIsNone(seen(_person("Іоаннъ")))
        self.assertIsNotNone(seen(_person("Іоаннъ", None, "Милушкинъ")))

    def test_a_maiden_name_alone_is_not_a_surname(self):
        self.assertIsNone(seen(_person("Анна", birth_last_name_modern_orth="Петрова")))

    def test_an_uncertain_part_is_none(self):
        found = seen(_person("Іоаннъ", "Петровъ?", "Милушкинъ"))
        assert found is not None
        self.assertEqual("", found.patr)

    def test_sightings_walk_the_records(self):
        record = SimpleNamespace(child=_person("Василій"), father=_person("Іоаннъ", "Петровъ"),
                                 mother=_person("Анастасія"))
        found = sightings([SimpleNamespace(), record], {}, year=1880)
        self.assertEqual([("Іоаннъ", 1)], [(s.name, n) for s, _, n in found if s is not None])


def _clue(s: Seen, year: int | None, *, born: int | None = None, age: float = 0.0,
          died: int | None = None) -> Clue:
    span = record_days(born) if born else None
    return Clue((s.residence, s.name, s.patr, s.surname), year_days(year),
                BirthSpan(span[0], span[1], age) if span else None,
                year_days(died) if died else None,
                died is None)


def _index(*rows: tuple[str, int | None, Seen, int]) -> PeopleIndex:
    """Each row one record, `n` times naming `s`: ("<village>/<year>", its row number)."""
    return PeopleIndex(Sighting(village, year, s, _clue(s, year), (f"{village}/{year}", k))
                       for k, (village, year, s, n) in enumerate(rows) for _ in range(n))


IVAN = _seen("Іоаннъ", "Петровъ", "Милушкинъ", "крестьянинъ", "Хлестаково", "м", ("Иоанн", "Петрович", "Милушкин"))
IVAN_SOLDIER = _seen("Іоаннъ", "Петровъ", "Милушкинъ", "солдатъ", "Маниловка", "м", ("Иоанн", "Петрович", "Милушкин"))
ANNA = _seen("Анна", "Петрова", "Милушкина", "крестьянка", "Маниловка", "ж", ("Анна", "Петровна", "Милушкина"))
REVISION = _seen("Иванъ", "Петровъ", "", "", "Заманиловка", "м", ("Иван", "Петрович", ""))
# A man of Хлестаково, which Маниловка's books write, known from Заманиловка's alone.
GUEST = _seen("Иванъ", "Петровъ", "Важновъ", "крестьянинъ", "Хлестаково", "м", ("Иван", "Петрович", "Важнов"))
INDEX = _index(("Маниловка", 1900, IVAN, 3), ("Маниловка", 1904, IVAN, 1), ("Маниловка", 1910, IVAN_SOLDIER, 1),
               ("Маниловка", 1901, ANNA, 2), ("Заманиловка", 1834, REVISION, 9), ("Заманиловка", 1850, GUEST, 5))


def _names(name="", patr="", surname="", village="Маниловка", gender="", limit=8):
    return [(p.name, p.patr, p.surname, p.status)
            for p in INDEX.suggest(name, patr, surname, village=village, gender=gender, limit=limit)]


class Suggesting(unittest.TestCase):
    def test_orthography_does_not_count(self):
        self.assertIn(("Іоаннъ", "Петровъ", "Милушкинъ", "крестьянинъ"), _names("иоан", "петр"))

    def test_the_modern_form_finds_the_written_one(self):
        self.assertIn(("Іоаннъ", "Петровъ", "Милушкинъ", "крестьянинъ"), _names("", "петрович", "милушк"))

    def test_every_part_typed_must_match(self):
        self.assertEqual([], _names("иоан", "петр", "чич"))
        self.assertEqual([("Анна", "Петрова", "Милушкина", "крестьянка")], _names("ан", "", "мил"))

    def test_an_empty_part_matches_a_person_who_lacks_it(self):
        self.assertIn(("Иванъ", "Петровъ", "", ""), _names("иван", "петр", village="Заманиловка"))
        self.assertIn(("Иванъ", "Петровъ", "Важновъ", "крестьянинъ"), _names("иван", "петр", village="Заманиловка"))

    def test_sex_filters(self):
        self.assertEqual(["Анна"], [n for n, *_ in _names("", "петр", "мил", gender="ж")])
        self.assertNotIn("Анна", [n for n, *_ in _names("", "петр", "мил", gender="м")])

    def test_two_statuses_are_two_rows_and_the_village_comes_first(self):
        found = INDEX.suggest("иоан", "петр", "", village="Маниловка")
        self.assertEqual(["крестьянинъ", "солдатъ"], [p.status for p in found])
        self.assertEqual((4, 4, "1900–1904"), (found[0].count, found[0].total, found[0].years))
        self.assertEqual("1910", found[1].years)
        other = INDEX.suggest("иван", "петр", "", village="Маниловка")
        self.assertEqual([("Важновъ", 0, 5)], [(p.surname, p.count, p.total) for p in other])

    def test_the_spelling_typed_comes_first(self):
        # «Іоанъ» is the record's own spelling: the person written so leads,
        # though the village writes «Іоаннъ» nine times as often — a choice
        # would otherwise overwrite what the scribe wrote.
        rare = _seen("Іоанъ", "Петровъ", "Милушкинъ", sex="м", modern=("Иоан", "Петрович", "Милушкин"))
        index = _index(("Маниловка", 1900, IVAN, 9), ("Маниловка", 1901, rare, 1))
        found = index.suggest("Іоанъ", "петр", "", village="Маниловка")
        self.assertEqual(["Іоанъ", "Іоаннъ"], [p.name for p in found])
        found = index.suggest("иоан", "петр", "", village="Маниловка")
        self.assertEqual(["Іоаннъ", "Іоанъ"], [p.name for p in found])   # nothing as typed: the village decides

    def test_the_record_edited_does_not_offer_its_own(self):
        # ANNA is written only in the record left out: she goes.
        self.assertEqual([], INDEX.suggest("ан", "", "кук", village="Маниловка", exclude=("Маниловка/1901", 3)))
        # IVAN is written elsewhere too: he stays, counted without it — and now
        # ties with the soldier, whom the later year puts first.
        found = INDEX.suggest("иоан", "петр", "", village="Маниловка", exclude=("Маниловка/1900", 0))
        self.assertEqual([("солдатъ", 1, 1, "1910"), ("крестьянинъ", 1, 1, "1904")],
                         [(p.status, p.count, p.total, p.years) for p in found])

    def test_a_record_left_out_elsewhere_keeps_the_village_count(self):
        index = _index(("Заманиловка", 1850, GUEST, 4), ("Заманиловка", 1851, GUEST, 1), ("Маниловка", 1900, IVAN, 1))
        found = index.suggest("иван", "петр", "", village="Маниловка", exclude=("Заманиловка/1850", 0))
        self.assertEqual([(0, 1, "1851")], [(p.count, p.total, p.years) for p in found])
        found = index.suggest("иван", "петр", "важн", village="Заманиловка", exclude=("Заманиловка/1850", 0))
        self.assertEqual([(1, 1)], [(p.count, p.total) for p in found])

    def test_a_record_left_out_is_no_evidence_of_a_life(self):
        # Seen in 1850 and in 1900 alone: in a record of 1905 he is alive by the
        # 1900 record — unless that is the record being edited.
        index = _index(("Заманиловка", 1840, GUEST, 1), ("Заманиловка", 1900, GUEST, 1))
        at = record_days(1905)
        self.assertEqual(1, len(index.suggest("иван", "петр", "", village="Заманиловка", at=at)))
        self.assertEqual([], index.suggest("иван", "петр", "", village="Заманиловка", at=at,
                                           exclude=("Заманиловка/1900", 1)))

    def test_the_limit_and_nothing_typed(self):
        self.assertEqual(1, len(_names("", "петр", "", limit=1)))
        self.assertEqual([], _names())


class Place(unittest.TestCase):
    """Only who lived where the village's books look."""

    def test_the_places_a_village_writes(self):
        self.assertEqual({"Хлестаково", "Маниловка"}, INDEX.places("Маниловка"))
        self.assertEqual({"Заманиловка", "Хлестаково"}, INDEX.places("Заманиловка"))
        self.assertEqual({"Горюхино"}, INDEX.places("Горюхино"))

    def test_another_villages_people_are_not_offered(self):
        # «Иванъ Петровъ» of the Заманиловка revision lived where Маниловка's books never look.
        self.assertNotIn(("Иванъ", "Петровъ", "", ""), _names("иван", "петр"))
        self.assertEqual([], _names("иван", "петр", village="Горюхино"))

    def test_a_place_the_village_writes_is_offered_from_any_books(self):
        self.assertIn(("Иванъ", "Петровъ", "Важновъ", "крестьянинъ"), _names("иван", "петр"))

    def test_no_place_written_is_the_own_villages(self):
        nowhere = _seen("Иванъ", "Петровъ", "Важновъ", sex="м", modern=("Иван", "Петрович", "Важнов"))
        index = _index(("Заманиловка", 1850, nowhere, 1), ("Маниловка", 1850, IVAN, 1))
        self.assertEqual(["Важновъ"], [p.surname for p in index.suggest("иван", "петр", "", village="Заманиловка")])
        self.assertEqual([], [p.surname for p in index.suggest("иван", "петр", "", village="Маниловка")
                              if p.surname == "Важновъ"])


def _at(year: int):
    found = record_days(year)
    assert found is not None
    return found


class Life(unittest.TestCase):
    """Given the record's day: only who can be alive on it."""

    def test_no_day_no_filter(self):
        self.assertEqual(4, len(_names("", "петр")))

    def test_a_day_out_of_reach_of_every_appearance(self):
        # Seen 1834 and nothing dates the birth: not in a record of 1900.
        self.assertEqual([], INDEX.suggest("иван", "петр", "", village="Заманиловка", at=_at(1900),
                                           exclude=("Заманиловка/1850", 5)))
        self.assertEqual(["", "Важновъ"],
                         sorted(p.surname for p in INDEX.suggest("иван", "петр", "", village="Заманиловка",
                                                                 at=_at(1880))))

    def test_dead_and_unborn_are_not_offered(self):
        groom = _seen("Петръ", "Ивановъ", "Ляпкинъ", "", "Маниловка", "м", ("Петр", "Иванович", "Ляпкин"))
        index = PeopleIndex([Sighting("Маниловка", 1880, groom, _clue(groom, 1880, born=1860, age=20)),
                             Sighting("Маниловка", 1890, None, _clue(groom, 1890, born=1860, age=30, died=1890))])
        # The ages are read with birth-claims' slack: a fifth of thirty is six years.
        found = [[p.surname for p in index.suggest("петр", "иван", "", village="Маниловка", at=_at(y))]
                 for y in (1852, 1855, 1885, 1891)]
        self.assertEqual([[], ["Ляпкинъ"], ["Ляпкинъ"], []], found)

    def test_an_adults_slot_asks_twelve_years(self):
        boy = _seen("Петръ", "Ивановъ", "Ляпкинъ", "", "Маниловка", "м", ("Петр", "Иванович", "Ляпкин"))
        index = PeopleIndex([Sighting("Маниловка", 1850, boy, _clue(boy, 1850, born=1846, age=4))])
        self.assertEqual([], index.suggest("петр", "иван", "", village="Маниловка", at=_at(1851), min_age=12))
        self.assertEqual(1, len(index.suggest("петр", "иван", "", village="Маниловка", at=_at(1851))))

    def test_the_nearest_to_the_day_comes_first(self):
        found = INDEX.suggest("иоан", "петр", "", village="Маниловка", at=_at(1911))
        self.assertEqual(["крестьянинъ", "солдатъ"], [p.status for p in found])   # the village count first
        early = _seen("Іоаннъ", "Петровъ", "Милушкинъ", "дьячокъ", "Маниловка", "м", ("Иоанн", "Петрович", "Милушкин"))
        index = _index(("Маниловка", 1860, early, 1), ("Маниловка", 1910, IVAN_SOLDIER, 1))
        self.assertEqual(["дьячокъ", "солдатъ"],
                         [p.status for p in index.suggest("иоан", "петр", "", village="Маниловка", at=_at(1865))])
        self.assertEqual(["солдатъ", "дьячокъ"],
                         [p.status for p in index.suggest("иоан", "петр", "", village="Маниловка", at=_at(1905))])


class Sightings(unittest.TestCase):
    def test_the_newborn_is_read_for_the_life_alone(self):
        child, father = _person("Василій"), _person("Иванъ", "Петровъ")
        clue = Clue(None, year_days(1880))
        found = sightings([SimpleNamespace(child=child, father=father)], {id(child): clue}, year=1880)
        self.assertEqual((None, clue, 0), found[0])
        offered, undated, _ = found[1]
        self.assertEqual("Иванъ", offered.name if offered else None)
        self.assertEqual(year_days(1880), undated.on)   # read by nobody: dated by its file



# Sixty women named «Анна» of one village «С», each her own: the ceiling of fifty shows.
ANNAS = _index(*[("С", 1900, _seen("Анна", "Иванова", f"Пробина{i}", sex="ж"), 1) for i in range(60)])


class SuggestFor(unittest.TestCase):
    """A record's context in one value (`RecordContext`): what the page sends with a query."""

    def test_suggest_for_keeps_the_limit_between_one_and_fifty(self):
        self.assertEqual(1, len(ANNAS.suggest_for("а", "", "", RecordContext("С"), limit=0)))
        self.assertEqual(50, len(ANNAS.suggest_for("а", "", "", RecordContext("С"), limit=500)))

    def test_suggest_for_is_the_old_query_with_the_sex_of_the_given_name(self):
        ctx = RecordContext("С", year=1900, month=3, slot="mother")
        self.assertEqual(ANNAS.suggest("Анна", "", "", village="С", gender=matching.name_sex("Анна"), limit=8,
                                       at=lives.record_days(1900, 3), min_age=lives.min_age("mother"),
                                       dead_days=lives.after_death("mother")),
                         ANNAS.suggest_for("Анна", "", "", ctx))
        self.assertEqual([], ANNAS.suggest_for("Анна", "", "", RecordContext("С", gender="м")))


if __name__ == "__main__":
    unittest.main()
