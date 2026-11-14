"""One kinship vocabulary for every record kind.

Until 2026-09-28 births, marriages and deaths each kept their own table of what
a named relative's kinship says, and they had drifted: births and marriages
read a foster parent and a step-parent as a PARENT, deaths did not. The one
place it showed in the corpus is Заманиловка 1891, whose marriage book names a
groom's отчим — asserted as his father.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.dsl.records.marriages import marriage
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.common import KINSHIP_EDGE, kinship
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import (
    AssertionSet, Citation, FosterParentOf, KinOf, NameClaim, ParentOf, Persona)
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative


def _wedding(relationship: Relationship) -> AssertionSet:
    rec = marriage(1, 7, Month.MAY, groom=person("Иван", "Петров"),
                   bride=person("Анна", "Ильина"),
                   relatives=[relative(person("Семен", "Ильин"), relationship,
                                       relationship_ref="жениха")])
    rec.year = 1891
    return AssertionSet(facts_from_marriages([(rec, "m.py")], village="Тестовка"))


class OneTable(unittest.TestCase):
    def test_a_stepfather_is_kin_not_a_father(self):
        facts = _wedding(Relationship.STEP_FATHER)
        self.assertEqual((), facts.of(ParentOf))
        [kin] = facts.of(KinOf)
        self.assertEqual("отчим", kin.term)

    def test_a_father_is_still_a_father(self):
        self.assertEqual(1, len(_wedding(Relationship.FATHER).of(ParentOf)))

    def test_a_foster_parent_is_a_foster_parent_in_every_kind(self):
        b = birth(1, Gender.MALE, 1, 2, Month.MARCH, Month.MARCH, year=1880,
                  child=person("Иван"), father=person("Петр", "Иванов"),
                  relatives=[relative(person("Семен", "Ильин"),
                                      Relationship.FOSTER_FATHER,
                                      relationship_ref="младенца")])
        births = AssertionSet(facts_from_births([(b, "b.py")], village="Тестовка"))
        self.assertEqual(1, len(births.of(FosterParentOf)))
        d = death(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH, year=1880,
                  deceased=person("Иван"),
                  relatives=[relative(person("Семен", "Ильин"),
                                      Relationship.FOSTER_FATHER)])
        deaths = AssertionSet(facts_from_deaths([(d, "d.py")], village="Тестовка"))
        self.assertEqual(1, len(deaths.of(FosterParentOf)))

    def test_every_edge_of_the_table(self):
        cite = Citation(village="Т", source_file="x.py", record_kind="birth",
                        record_num="1", entry=0, year=1880, page=None,
                        locator="relative1")
        ref, anchor = Persona("x/relative1"), Persona("x/child")
        seen = {}
        for relationship in KINSHIP_EDGE:
            got = kinship(ref, anchor, relationship, cite)
            seen[KINSHIP_EDGE[relationship]] = [
                (type(a).__name__, a.subject == ref) for a in got]
        self.assertEqual([("ParentOf", True)], seen["parent"])
        self.assertEqual([("ParentOf", False)], seen["child"])
        self.assertEqual([("FosterParentOf", True)], seen["foster"])
        self.assertEqual([("SpouseOf", True), ("SpouseOf", False)], seen["spouse"])
        [unset] = kinship(ref, anchor, None, cite)
        assert isinstance(unset, KinOf)
        self.assertEqual("", unset.term)


class RelativesDoNotSpill(unittest.TestCase):
    def test_a_tenth_relative_of_a_death_is_a_relative_not_a_witness(self):
        """Ordinals once ran in ranges, and a tenth relative would have become
        the first witness; a persona is named by its slot now (`relative10`)."""
        d = death(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH, year=1880,
                  deceased=person("Иван"),
                  relatives=[relative(person(name), Relationship.SON)
                             for name in ("Петр", "Павел", "Семен", "Андрей", "Яков",
                                          "Фома", "Лука", "Марк", "Федор", "Илья")])
        facts = AssertionSet(facts_from_deaths([(d, "d.py")], village="Тестовка"))
        named = {a.subject.id.rpartition("/")[2] for a in facts.of(NameClaim)}
        self.assertEqual({"deceased", *(f"relative{i}" for i in range(1, 11))}, named)


if __name__ == "__main__":
    unittest.main()
