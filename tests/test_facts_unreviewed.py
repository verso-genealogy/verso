"""An entry not yet checked against the scan asserts nothing — anywhere.

`reviewed=False` marks an entry transcribed and not yet checked. The translator
mints no profile for it, and the census extractor already skipped such a двор;
the births, marriages and deaths extractors read it anyway, so after the
Маниловка sweep of 2026-09-27 the bridge reported 3131 of its appearances as
«профиля не существует» — a third of the village. The legacy readers that
parity is measured against (`death_age`, the godparent linter, the sweep's
occurrences) read it too, which is how the two agreed on the wrong answer.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.births import BirthRecords, birth
from verso.ru.dsl.records.deaths import DeathRecords, death
from verso.ru.dsl.records.marriages import marriage
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import AssertionSet, NameClaim
from verso.ru.gender import Gender


def _birth(num, *, reviewed=True):
    return birth(num, Gender.MALE, 1, 2, Month.MARCH, Month.MARCH, year=1880,
                 child=person("Иван"), father=person("Петр", "Иванов"),
                 mother=person("Анна", "Ивановна"),
                 god_parent1=person("Семен", "Ильин"), reviewed=reviewed)


def _death(num, *, reviewed=True):
    return death(num, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH, year=1880,
                 deceased=person("Иван", "Петров"), age=40, reviewed=reviewed)


def _marriage(num, *, reviewed=True):
    rec = marriage(num, 7, Month.MAY, groom=person("Иван", "Петров"),
                   bride=person("Анна", "Ильина"), witness1=person("Семен", "Ильин"),
                   reviewed=reviewed)
    rec.year = 1880
    return rec


def _subjects(facts: AssertionSet) -> set[str]:
    return {a.cite.record_num for a in facts.of(NameClaim)}


class ExtractorsSkipUnreviewed(unittest.TestCase):
    def test_births(self):
        facts = AssertionSet(facts_from_births(
            [(_birth(1), "b.py"), (_birth(2, reviewed=False), "b.py")],
            village="Тестовка"))
        self.assertEqual({"1"}, _subjects(facts))

    def test_marriages(self):
        facts = AssertionSet(facts_from_marriages(
            [(_marriage(1), "m.py"), (_marriage(2, reviewed=False), "m.py")],
            village="Тестовка"))
        self.assertEqual({"1"}, _subjects(facts))

    def test_deaths(self):
        facts = AssertionSet(facts_from_deaths(
            [(_death(1), "d.py"), (_death(2, reviewed=False), "d.py")],
            village="Тестовка"))
        self.assertEqual({"1"}, _subjects(facts))

    def test_a_reviewed_entry_keeps_its_place(self):
        """The entry index is the extractor's traversal position; skipping an
        unreviewed entry must not renumber the ones after it, or every Persona
        of a village would move when one draft is added."""
        alone = AssertionSet(facts_from_births([(_birth(2), "b.py")],
                                               village="Тестовка"))
        after_draft = AssertionSet(facts_from_births(
            [(_birth(1, reviewed=False), "b.py"), (_birth(2), "b.py")],
            village="Тестовка"))
        self.assertEqual({a.cite.entry for a in alone}, {0})
        self.assertEqual({a.cite.entry for a in after_draft}, {1})


class DraftsAreReadOnRequest(unittest.TestCase):
    """Verso's people index offers the people of a sweep still under review,
    so it asks for them (`drafts=True`). Nothing else does: the default is the
    gate above."""

    def test_births(self):
        facts = AssertionSet(facts_from_births(
            [(_birth(1), "b.py"), (_birth(2, reviewed=False), "b.py")],
            village="Тестовка", drafts=True))
        self.assertEqual({"1", "2"}, _subjects(facts))

    def test_marriages(self):
        facts = AssertionSet(facts_from_marriages(
            [(_marriage(1, reviewed=False), "m.py")], village="Тестовка", drafts=True))
        self.assertEqual({"1"}, _subjects(facts))

    def test_deaths(self):
        facts = AssertionSet(facts_from_deaths(
            [(_death(1, reviewed=False), "d.py")], village="Тестовка", drafts=True))
        self.assertEqual({"1"}, _subjects(facts))


class LegacyReadersSkipUnreviewed(unittest.TestCase):
    def test_death_age_loader(self):
        from verso.ru.consolidation.death_age import _reviewed_only

        book = DeathRecords("A", "1", "1", "1", "Тестовка", "Никольская", 1880,
                            [_death(1), _death(2, reviewed=False)])
        kept = _reviewed_only(book)
        self.assertEqual([1], [r.record_num for r in kept.records])
        self.assertEqual(2, len(book.records), "the book itself is untouched")

    def test_sweep_occurrences(self):
        from verso.ru.consolidation.candidates import extract_occurrences

        book = BirthRecords("A", "1", "1", "1", "Тестовка", "Никольская", 1880,
                            [_birth(1), _birth(2, reviewed=False)])
        self.assertEqual({1}, {o.record_num for o in extract_occurrences(book, "b.py")})


if __name__ == "__main__":
    unittest.main()
