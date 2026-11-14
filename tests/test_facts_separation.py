"""The one kind of evidence in this corpus that separates people.

Everything else the layer carries argues that two appearances are the same
person. A source that counts two entries into one group has said there are two,
and the rule that reads it may not know what kind of group it was handed.
"""
from __future__ import annotations

import unittest

from collections.abc import Callable

from verso.ru.facts.identity import IdentityKey, canonical_fold, name_identity
from verso.ru.facts.model import (
    Assertion, AssertionSet, Citation, EnumeratedIn, FactDate, Grouped, NameClaim, Persona, Record, Stated)
from verso.ru.facts.rules.separation import (
    counted_apart, counted_together, groups_of)


def _cite(entry: int, locator: str) -> Citation:
    return Citation(village="Тестовка", source_file="r.py", record_kind="k",
                    record_num="7", entry=entry, year=1834, locator=locator)


def _listed(entry: int, ordinal: int, given: str, *, group: str = "7",
            within: str = "r.py") -> list[Assertion]:
    who = Persona(f"r.py#{entry}/member{ordinal}")
    cite = _cite(entry, f"member{ordinal}")
    return [
        NameClaim(subject=who, cite=cite, basis=Stated(), given=given,
                  patronymic=None, surname=None, gender=None),
        EnumeratedIn(subject=who, cite=cite, group=group, within=within,
                     as_of=FactDate(year=1834), basis=Stated()),
    ]


def _facts(*rows) -> AssertionSet:
    out = []
    for r in rows:
        out += r
    return AssertionSet(out)


#: Every appearance is its own person. What a check that already holds two
#: distinct people hands in — which is the only way the group test is ever
#: asked, and the next test says why.
def _apart(_record: Record) -> Callable[[Persona], IdentityKey]:
    def key(who: Persona) -> IdentityKey:
        return (str(who),)
    return key


class CountingSeparates(unittest.TestCase):
    def test_two_entries_of_one_group_are_two(self):
        facts = _facts(_listed(0, 1, "Настасья"), _listed(0, 2, "Настасья"))
        self.assertEqual(1, len(counted_apart(
            facts, grouping=EnumeratedIn, identity=_apart)))

    def test_a_name_fold_cannot_ask_this_question(self):
        """Two «Настасьи» fold to one key, so the fold has already decided they
        are one person and the group has nothing left to separate. That is why
        the guard applies this test to two profiles it holds, never to names —
        and why identity being a parameter is not a formality here.
        """
        facts = _facts(_listed(0, 1, "Настасья"), _listed(0, 2, "Настасья"))
        self.assertEqual(set(), counted_apart(
            facts, grouping=EnumeratedIn,
            identity=name_identity(canonical_fold)))

    def test_one_person_is_not_separated_from_themselves(self):
        facts = _facts(_listed(0, 1, "Настасья"))
        self.assertEqual(set(), counted_apart(
            facts, grouping=EnumeratedIn, identity=_apart))

    def test_two_groups_separate_nobody(self):
        facts = _facts(_listed(0, 1, "Настасья", group="7"),
                       _listed(1, 2, "Настасья", group="8"))
        self.assertEqual(set(), counted_apart(
            facts, grouping=EnumeratedIn, identity=_apart))

    def test_the_same_number_in_two_rolls_separates_nobody(self):
        """The oracle's key has nowhere to put the roll and fuses these two."""
        facts = _facts(_listed(0, 1, "Настасья", group="7", within="a.py"),
                       _listed(1, 2, "Настасья", group="7", within="b.py"))
        self.assertEqual(set(), counted_apart(
            facts, grouping=EnumeratedIn, identity=_apart))


class TheRuleReadsNoGroupName(unittest.TestCase):
    def test_groups_come_back_keyed_on_an_opaque_payload(self):
        facts = _facts(_listed(0, 1, "Настасья"), _listed(0, 2, "Дарья"))
        groups = counted_together(facts, grouping=EnumeratedIn,
                                  identity=_apart)
        self.assertEqual(1, len(groups))
        self.assertEqual(2, len(groups[0]))
        self.assertEqual(("r.py", "7", "??.??.1834"), groups[0].key)

    def test_it_takes_any_predicate_that_carries_a_group(self):
        """The rule is handed a TYPE. A second grouping predicate would cost a
        line at the call site and nothing here — which only holds while the
        grouping predicates share a base the rule can name instead of them."""
        self.assertEqual(
            {"EnumeratedIn"},
            {c.__name__ for c in Grouped.__subclasses__()})

    def test_groups_are_ordered_so_a_report_is_byte_stable(self):
        facts = _facts(_listed(1, 1, "Дарья", group="9"),
                       _listed(0, 1, "Настасья", group="8"))
        keys = [g.key for g in counted_together(
            facts, grouping=EnumeratedIn, identity=_apart)]
        self.assertEqual(sorted(keys, key=str), keys)


class StartingFromPeople(unittest.TestCase):
    def test_groups_of_one_appearance(self):
        rows = _listed(0, 1, "Настасья")
        facts = _facts(rows)
        who = rows[0].subject
        self.assertEqual({who: (("r.py", "7", "??.??.1834"),)},
                         groups_of(facts, grouping=EnumeratedIn, who=[who]))

    def test_an_appearance_in_no_group_comes_back_empty(self):
        facts = _facts(_listed(0, 1, "Настасья"))
        stranger = Persona("elsewhere/member9")
        self.assertEqual({stranger: ()},
                         groups_of(facts, grouping=EnumeratedIn, who=[stranger]))


if __name__ == "__main__":
    unittest.main()
