"""The recurring-pair report around the co-occurrence rule.

`make check-godparent-cooccurrence` has printed this report from the facts
layer since 2026-09-28; before, a linter module printed the same bytes from the
DSL. What that module pinned and the rule does not — how a pair is titled,
which pairs `--require-surname` keeps, and whether a record still stands as a
profile of its own — is pinned here.
"""
from __future__ import annotations

import unittest
from typing import Any

from verso.ru.cli.facts import LooseIndex, _best, _identifiable, format_report
from verso.ru.domain import Person, person
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.common import SlotIndex
from verso.ru.facts.identity import canonical_fold, name_identity
from verso.ru.facts.model import AssertionSet, GodparentOf, ParentOf
from verso.ru.facts.rules.cooccurrence import Pair, cooccurrences
from verso.ru.gender import Gender
from verso.ru.dsl.records.births import birth


def _births(*records: Any, slots: SlotIndex | None = None) -> AssertionSet:
    return AssertionSet(facts_from_births(
        [(b, f"{i}.py") for i, b in enumerate(records)], village="Тест", slots=slots))


def _b(num: int, father: Person, gp: Person, year: int = 1840) -> Any:
    return birth(num, Gender.MALE, 1, 1, child=person("Иван"), father=father,
                 mother=person("Анна", "Гордеева"), god_parent1=gp, year=year)


def _groups(facts: AssertionSet, min_count: int = 2) -> list[Pair]:
    return cooccurrences(facts.believed(), left=ParentOf, right=GodparentOf,
                         identity=name_identity(canonical_fold), min_count=min_count)


def _father_pair(groups: list[Pair], father: str) -> Pair:
    [g] = [g for g in groups if g.left_key[0] == father or g.right_key[0] == father]
    return g


class TheSpellingOfOnePerson(unittest.TestCase):
    def test_a_spelling_variant_is_one_person(self):
        """Капиталина and Капитолина share a canonical name (the lexicon)."""
        facts = _births(_b(1, person("Петр", "Иванов"), person("Капиталина")),
                        _b(2, person("Петр", "Иванов"), person("Капитолина")))
        groups = _groups(facts)
        self.assertEqual(1, len([g for g in groups if len(g.occurrences) == 2
                                 and g.left_key[0] == "Петр"]))


class RequireSurnameReadsEveryRecord(unittest.TestCase):
    """`--require-surname` judges a pair by ALL its records, not one: the
    Подколесин pair's earliest record (1831) names neither surname while its
    1839/1841 ones name both, and keying on the first dropped it and eight
    other real Горюхино findings."""

    def test_a_pair_named_in_a_later_record_survives_and_is_titled_by_it(self):
        terse_f, terse_g = person("Федор", "Петров"), person("Яков", "Пименов")
        named_f = person("Федор", "Петров", last_name_orig="Подколесин")
        named_g = person("Яков", "Пименов", last_name_orig="Суетливцев")
        facts = _births(_b(1, terse_f, terse_g), _b(2, named_f, named_g),
                        _b(3, named_f, named_g))
        g = _father_pair(_groups(facts, min_count=3), "Феодор")
        gps = [(o, o.right) for o in g.occurrences]
        self.assertTrue(_identifiable(gps))
        self.assertEqual("Суетливцев Иаков Пименович", _best(gps))

    def test_a_pair_no_record_ever_names_is_dropped(self):
        f, gp = person("Иван", "Иванов"), person("Анна", "Иванова")
        facts = _births(*(_b(i, f, gp) for i in (1, 2, 3)))
        g = _father_pair(_groups(facts, min_count=3), "Иоанн")
        self.assertFalse(_identifiable([(o, o.right) for o in g.occurrences]))


class _Consolidation:
    def __init__(self, folded: set[str]) -> None:
        self._folded = folded

    def in_profile_move_list(self, res_name: str) -> bool:
        return res_name in self._folded


class _Gen:
    """The two questions `LooseIndex` asks of a translation."""

    def __init__(self, minted: dict[int, str], folded: set[str]) -> None:
        self._minted = minted
        self.consolidation = _Consolidation(folded)

    def profile_minted_for(self, person: object) -> str | None:
        return self._minted.get(id(person))


class StandingIsAskedOfTheBridge(unittest.TestCase):
    """Whether a record still stands as a profile of its own comes from the
    res_name the translator minted for it and whether the config folded that
    res_name — never from a regex over the generated files, which found
    nothing in a village with no tree (Заманиловка: 1436 of 1436 «already
    consolidated»)."""

    def _index(self, *, folded: bool,
               named_in_config: bool) -> tuple[LooseIndex, Any, AssertionSet]:
        slots = SlotIndex()
        # One Person per entry, as the DSL builds them: the bridge's join key
        # is the object, so the two appearances are two keys.
        facts = _births(
            _b(34, person("Михаил", "Климентов"),
               person("Мануил", "Иудин", last_name_orig="Копейкин")),
            _b(35, person("Михаил", "Климентов"),
               person("Мануил", "Иудин", last_name_orig="Копейкин")), slots=slots)
        name = "_1840_01_01_manuil_iudich_kopejkin_mk_births_34_god_parent_1"
        who = facts.of(GodparentOf)[0].subject
        obj = slots.object_of(who)
        gen = _Gen({id(obj): name}, {name} if folded else set())
        config = f'X = ["{name}"]' if named_in_config else "{}"
        return LooseIndex(gen, slots, config), who, facts

    def test_a_standing_unnamed_record_is_loose(self):
        index, who, _ = self._index(folded=False, named_in_config=False)
        self.assertEqual("_1840_01_01_manuil_iudich_kopejkin_mk_births_34_god_parent_1",
                         index.resolve(who))
        self.assertTrue(index.is_loose(who))

    def test_a_record_the_config_names_stands_but_is_not_loose(self):
        index, who, _ = self._index(folded=False, named_in_config=True)
        self.assertIsNotNone(index.resolve(who))
        self.assertFalse(index.is_loose(who))

    def test_a_folded_record_does_not_stand(self):
        index, who, _ = self._index(folded=True, named_in_config=True)
        self.assertIsNone(index.resolve(who))
        self.assertFalse(index.is_loose(who))

    def test_the_report_marks_each_record(self):
        """Record 34 stands, loose; record 35 was minted nothing here, so it
        has no profile of its own to stand under."""
        index, _, facts = self._index(folded=False, named_in_config=False)
        report = format_report(_groups(facts), 2, index)
        self.assertIn("— 2 births   [1 loose]", report)
        self.assertIn("LOOSE: _1840_01_01_manuil_iudich_kopejkin_mk_births_34_god_parent_1",
                      report)
        self.assertIn("(not in the generated tree — already consolidated)", report)

    def test_no_index_no_marks(self):
        _, _, facts = self._index(folded=False, named_in_config=False)
        report = format_report(_groups(facts), 2, None)
        self.assertIn("— 2 births", report)
        self.assertNotIn("loose]", report)


if __name__ == "__main__":
    unittest.main()
