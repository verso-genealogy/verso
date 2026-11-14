"""A death record's named relative positions the dead person — or it doesn't.

The book names one relative to identify the deceased («жена Гавриила», «дочь
Ивана»), so that phrase is the whole evidence for the link. The translator used
to read it as a single bit — `rel_type == "муж"` meant spouse and EVERYTHING
else meant «this relative is the deceased's parent» — which silently turned a
stepmother into a mother, a foster father into a father, a father-in-law into a
father, and a relative whose kinship the record never stated into a parent.

The rule now maps the kinship it can express and emits NO union for the rest.
A missing edge is recoverable from another record; a false one has to be found
first, and it looks exactly like a true one.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.deaths import death, death_records, death_month
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, Relative
from verso.ru.targets.geni.translator import TerraformGenerator


_SHE = ("Матрона", "Платонова")
_HE = ("Пётр", "Платонов")


def _output(relationship: Relationship | None, *, relative=_SHE) -> str:
    records = death_records(
        "TestArchive", "1", "1", "1", "Тестовка", "Никольская", 1909,
        *death_month(
            Month.JUNE,
            death(2, Gender.FEMALE, 17, 19,
                  deceased=person("Прасковья"), age=11,
                  relatives=[Relative(person(*relative), relationship)]),
        ),
    )
    gen = TerraformGenerator(village_dir=None)
    gen.add_death_records(records)
    return gen.get_output("mk_1909_death.tf")


def _union(relationship: Relationship | None, *, relative=_SHE) -> str | None:
    """Just the `geni_union` block, so an assertion cannot match the document."""
    out = _output(relationship, relative=relative)
    start = out.find('resource "geni_union"')
    if start == -1:
        return None
    return out[start:out.index("\n}\n", start)]


class KinshipThatPositionsTheDeceased(unittest.TestCase):
    def test_husband_makes_the_deceased_a_partner(self):
        block = _union(Relationship.HUSBAND, relative=_HE)
        assert block is not None
        self.assertIn("mk_deaths_2_deceased.id,", block)
        self.assertNotIn("children", block)

    def test_father_makes_the_deceased_a_child(self):
        block = _union(Relationship.FATHER, relative=_HE)
        assert block is not None
        self.assertIn("children = [", block)
        self.assertNotIn("foster_children", block)
        self.assertIn("mk_deaths_2_deceased.id,", block)

    def test_foster_father_uses_the_foster_modifier(self):
        """Geni's parent modifier vocabulary is bio/adopt/foster, and приёмыш
        is exactly `foster` — the union carries the child, but not as flesh."""
        block = _union(Relationship.FOSTER_FATHER, relative=_HE)
        assert block is not None
        self.assertIn("foster_children = [", block)
        self.assertNotIn("\n  children = [", block)


class KinshipThatPositionsNobody(unittest.TestCase):
    """No union at all — the record names a relative it cannot place."""

    def test_stepmother_is_not_made_a_mother(self):
        """A мачеха is her stepchild's father's wife. Geni has no `step`
        modifier, and the child belongs in the FATHER's union — which this
        record does not name. So the record positions nobody."""
        self.assertIsNone(_union(Relationship.STEP_MOTHER))

    def test_father_in_law_is_not_made_a_father(self):
        """«свекор» makes the deceased his son's wife, two edges away."""
        self.assertIsNone(_union(Relationship.FATHER_IN_LAW, relative=_HE))

    def test_son_in_law_is_not_made_a_father(self):
        """«зять» runs the other way: the deceased is the relative's parent-in-law,
        so reading it as a parent edge inverts it."""
        self.assertIsNone(_union(Relationship.SON_IN_LAW, relative=_HE))

    def test_unstated_kinship_positions_nobody(self):
        """A relative with no relationship — `relative(person(…), None)` — is a
        transcription gap, not a claim of parenthood. 11 records in the corpus
        are this shape."""
        self.assertIsNone(_union(None))

    def test_the_relative_is_still_a_person(self):
        """No union does not mean no profile — the record still names them."""
        out = _output(Relationship.STEP_MOTHER)
        self.assertIn("mk_deaths_2_relative", out)
        self.assertIn("mk_deaths_2_deceased", out)
