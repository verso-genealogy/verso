"""One person as an identity folds them, and the triage view built on it.

`Conclusion` is the layer's name for what a canonical IS in the sources — the
key and every claim whose subject it is. `make facts-why person=<res_name>`
prints one, record by record, with each claim's basis.
"""
from __future__ import annotations

import unittest
from calendar import Month
from typing import Any

from verso.ru.cli.facts import explain_person
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.common import SlotIndex
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.identity import conclusions
from verso.ru.facts.model import AgedYears, AssertionSet, BornOn, DiedOn
from verso.ru.facts.projection import canonical_key, canonical_name, consolidated_identity
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative


class _Consolidation:
    def __init__(self) -> None:
        self.profile_move_list: dict[str, str] = {}


class _Gen:
    """A translation that minted `name` for every appearance of Анна and folds
    them all into `anna`."""

    def __init__(self, minted: dict[int, str]) -> None:
        self._minted = minted
        self.consolidation = _Consolidation()

    def profile_minted_for(self, person: object) -> str | None:
        return self._minted.get(id(person))

    def resolve_canonical(self, res_name: str) -> str:
        return "anna" if res_name.startswith("anna") else res_name

    def canonical_profiles(self) -> dict[str, Any]:
        return {}


def _corpus() -> tuple[AssertionSet, _Gen, SlotIndex]:
    slots = SlotIndex()
    born = birth(3, Gender.FEMALE, 10, 12, Month.MARCH, Month.MARCH, year=1890,
                 child=person("Анна"), father=person("Петр", "Иванов"))
    died = death(7, Gender.FEMALE, 20, 21, Month.JULY, Month.JULY, year=1894,
                 deceased=person("Анна"), age=4,
                 relatives=[relative(person("Петр", "Иванов"), Relationship.FATHER)])
    facts = AssertionSet(
        list(facts_from_births([(born, "b.py")], village="Тестовка", slots=slots))
        + list(facts_from_deaths([(died, "d.py")], village="Тестовка", slots=slots)))
    gen = _Gen({id(born.child): "anna_b3", id(died.deceased): "anna_d7"})
    return facts, gen, slots


class TheConclusion(unittest.TestCase):
    def test_both_records_fold_into_one_person(self):
        facts, gen, slots = _corpus()
        found = conclusions(facts, consolidated_identity(gen, slots.object_of))
        anna = found[canonical_key("anna")]
        self.assertEqual("anna", canonical_name(anna.key))
        self.assertEqual(2, len(anna.personas))
        self.assertEqual(1, len(anna.of(BornOn)))
        self.assertEqual(1, len(anna.of(DiedOn)))
        self.assertEqual(["4"], [str(a.age) for a in anna.of(AgedYears)])

    def test_the_key_shape_is_known_in_one_place(self):
        self.assertIsNone(canonical_name(None))
        self.assertIsNone(canonical_name(("",)))
        self.assertEqual(("x",), canonical_key("x"))


class TheTriageView(unittest.TestCase):
    def test_every_record_is_read_out_in_time_order_with_its_basis(self):
        facts, gen, slots = _corpus()
        report = explain_person(facts, gen, slots, "anna")
        self.assertIn("(anna): 2 явления в 2 записях", report)
        self.assertLess(report.index("1890 · birth"), report.index("1894 · death"))
        self.assertIn("AgedYears", report)
        self.assertIn("ЗАПИСАНО", report)
        # The relation the record holds TO her is shown too: her father.
        self.assertIn("ParentOf(Петр Иванович → Анна", report)

    def test_an_unknown_canonical_says_so(self):
        facts, gen, slots = _corpus()
        self.assertIn("не сведено", explain_person(facts, gen, slots, "nobody"))


if __name__ == "__main__":
    unittest.main()
