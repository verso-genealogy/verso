"""The rule's behaviour, pinned by construction.

Ported from the prototype that established it: these six cases are the ones
the legacy `check-godparent-cooccurrence` pinned (it was retired on 2026-09-28,
when the report moved onto the assertions), plus what the second record kind
and the pluggable identity added. The report around the rule is
`tests/test_facts_cooccurrence_report.py`. The grep guard
that used to live here is now `tests/test_facts_layering.py`, which checks the
whole package rather than one file.
"""
from __future__ import annotations

import unittest

from verso.ru.domain import Person

from verso.ru.facts.rules.cooccurrence import cooccurrences
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.identity import canonical_fold, name_identity
from verso.ru.facts.model import (
    AssertionSet, Derived, GodparentOf, ParentOf, Persona, Record, SpouseOf, Stated, WitnessedAt)


# Vocabulary the RULE may not contain. Each entry names a thing that only
# exists because a metric book has that shape — the ladder this spike claims
# to have removed.
_FORBIDDEN = (
    r"\bbirth", r"god_parent", r"godparent", r"\bfather\b", r"\bmother\b",
    r"\bchild\b", r"\bbaptiz", r"record_kind", r"locator", r"\bwitness",
    r"\bgroom\b", r"\bbride\b", r"\bdeceased\b", r"\bcensus\b",
    r"отец", r"мать", r"восприемник", r"рожден",
)


def _person(name: str, patr: str | None = None, last: str | None = None) -> Person:
    return Person(name, patr, last)


class _Birth:
    """The parts of `verso.ru.dsl.records.births.Birth` the extractor reads.

    Hand-built rather than constructed through `birth()` so a case states only
    what it is about; the real constructor derives residence, surname, status
    and gender in place, which is exactly what §1.5 of the plan prices.
    """

    def __init__(self, *, record_num, year, child=None, father=None, mother=None,
                 god_parents=(), relatives=()):
        self.record_num = record_num
        self.year = year
        self.child = child
        self.father = father
        self.mother = mother
        for i in range(1, 5):
            setattr(self, f"god_parent{i}", god_parents[i - 1] if i <= len(god_parents) else None)
        self.relatives = list(relatives)
        self.b_day = self.b_month = self.k_day = self.k_month = self.k_year = None
        self.page = None
        self.priest = self.deacon = self.dyachok = self.sexton = None
        self.is_christening = False
        self.christening_age = None


def _pairs(births, **kw):
    facts = AssertionSet(facts_from_births(
        [(b, "test_births.py") for b in births], village="Тест"))
    return cooccurrences(facts, left=ParentOf, right=GodparentOf,
                         identity=name_identity(canonical_fold), **kw)


class RuleParity(unittest.TestCase):
    """The six behaviours `tests/test_check_godparent_cooccurrence.py` pins."""

    def test_pair_needs_min_count_distinct_records(self) -> None:
        one = _Birth(record_num=1, year=1840, child=_person("Иван"),
                     father=_person("Пётр", "Ивановъ"),
                     god_parents=[_person("Фома", "Ильинъ")])
        self.assertEqual([], _pairs([one]))
        two = _Birth(record_num=2, year=1841, child=_person("Анна"),
                     father=_person("Пётр", "Ивановъ"),
                     god_parents=[_person("Фома", "Ильинъ")])
        self.assertEqual(1, len(_pairs([one, two])))

    def test_pair_is_symmetric_across_records(self) -> None:
        """Godparent in one record, parent in another — one pair, not two."""
        a = _Birth(record_num=1, year=1840, child=_person("Иван"),
                   father=_person("Пётр", "Ивановъ"),
                   god_parents=[_person("Фома", "Ильинъ")])
        b = _Birth(record_num=2, year=1841, child=_person("Анна"),
                   father=_person("Фома", "Ильинъ"),
                   god_parents=[_person("Пётр", "Ивановъ")])
        found = _pairs([a, b])
        self.assertEqual(1, len(found))
        self.assertEqual(2, len(found[0].occurrences))

    def test_one_record_counts_once_per_pair(self) -> None:
        """The same godparent in two slots of ONE record is one occurrence."""
        twice = _Birth(record_num=1, year=1840, child=_person("Иван"),
                       father=_person("Пётр", "Ивановъ"),
                       god_parents=[_person("Фома", "Ильинъ"), _person("Фома", "Ильинъ")])
        other = _Birth(record_num=2, year=1841, child=_person("Анна"),
                       father=_person("Пётр", "Ивановъ"),
                       god_parents=[_person("Фома", "Ильинъ")])
        found = _pairs([twice, other])
        self.assertEqual(1, len(found))
        self.assertEqual(2, len(found[0].occurrences))

    def test_a_person_is_not_paired_with_themselves(self) -> None:
        same = [_Birth(record_num=n, year=1840 + n, child=_person("Иван"),
                       father=_person("Пётр", "Ивановъ"),
                       god_parents=[_person("Пётр", "Ивановъ")]) for n in (1, 2)]
        self.assertEqual([], _pairs(same))

    def test_both_parents_pair_with_one_godparent(self) -> None:
        both = [_Birth(record_num=n, year=1840 + n, child=_person("Иван"),
                       father=_person("Пётр", "Ивановъ"),
                       mother=_person("Анна", "Иванова"),
                       god_parents=[_person("Фома", "Ильинъ")]) for n in (1, 2)]
        self.assertEqual(2, len(_pairs(both)))

    def test_nameless_side_is_dropped(self) -> None:
        anon = [_Birth(record_num=n, year=1840 + n, child=_person("Иван"),
                       father=_person("Пётр", "Ивановъ"),
                       god_parents=[None]) for n in (1, 2)]
        self.assertEqual([], _pairs(anon))


class _Marriage:
    """The parts of `verso.ru.dsl.records.marriages.Marriage` the extractor reads."""

    def __init__(self, *, record_num, year, groom=None, bride=None,
                 witnesses=(), relatives=()):
        self.record_num = record_num
        self.year = year
        self.groom = groom
        self.bride = bride
        for i in range(1, 7):
            setattr(self, f"witness{i}", witnesses[i - 1] if i <= len(witnesses) else None)
        self.relatives = list(relatives)
        self.w_day = self.w_month = None
        self.page = None
        self.priest = self.deacon = self.dyachok = self.sexton = None


def _wedding_facts(marriages):
    return AssertionSet(facts_from_marriages(
        [(m, "test_marriages.py") for m in marriages], village="Тест"))


class MarriagesReuseTheSameRule(unittest.TestCase):
    """The second data point: a different record kind, and the rule is the
    SAME FILE, unchanged — only the two predicate types differ."""

    def _couple(self, n):
        return dict(groom=_person("Пётр", "Ивановъ", "Сундукин"),
                    bride=_person("Анна", "Иванова", "Алтынова"), record_num=n)

    def test_recurring_witness_pair_is_found_by_the_birth_rule(self) -> None:
        pair = [_person("Фома", "Ильинъ", "Колючкин"), _person("Иванъ", "Петровъ", "Тихоходов")]
        weddings = [_Marriage(year=1840 + n, witnesses=pair, **self._couple(n))
                    for n in (1, 2)]
        found = cooccurrences(_wedding_facts(weddings),
                              left=WitnessedAt, right=WitnessedAt, identity=name_identity(canonical_fold))
        self.assertEqual(1, len(found))
        self.assertEqual(2, len(found[0].occurrences), "one wedding counts once")

    def test_a_parent_pairs_with_a_witness_the_same_way_a_godparent_does(self) -> None:
        from verso.ru.relationship import Relationship, relative

        father = _person("Захаръ", "Васильевъ", "Егозин")
        witness = _person("Фома", "Ильинъ", "Колючкин")
        weddings = [
            _Marriage(year=1840 + n, witnesses=[witness],
                      relatives=[relative(father, Relationship.FATHER, "жених")],
                      **self._couple(n))
            for n in (1, 2)]
        found = cooccurrences(_wedding_facts(weddings),
                              left=ParentOf, right=WitnessedAt, identity=name_identity(canonical_fold))
        self.assertEqual(1, len(found))

    def test_the_witness_side_is_declared_derived_not_stated(self) -> None:
        """The books separate поручители «по женихѣ» from «по невѣстѣ»; the DSL
        does not. The model must say so rather than imply the record did."""
        m = _Marriage(year=1840, witnesses=[_person("Фома", "Ильинъ")], **self._couple(1))
        witnessed = _wedding_facts([m]).of(WitnessedAt)
        self.assertEqual(2, len(witnessed), "attached to both parties")
        for a in witnessed:
            self.assertIsInstance(a.basis, Derived)
            self.assertEqual("marriage.witness-side-not-recorded",
                             cast_derived(a.basis).rationale)

    def test_a_declared_side_attaches_the_witness_to_that_party_only(self) -> None:
        """`side=` is the record stating whom the поручитель stood for."""
        from verso.ru.domain import Side

        by_bride = Person("Фома", "Ильинъ", side=Side.BRIDE)
        m = _Marriage(year=1840, witnesses=[by_bride], **self._couple(1))
        facts = _wedding_facts([m])
        witnessed = facts.of(WitnessedAt)
        self.assertEqual(1, len(witnessed), "attached to the bride alone")
        bride = next(f.subject for f in facts.of(SpouseOf) if f.cite.locator == "bride")
        self.assertEqual(bride, witnessed[0].other)
        self.assertIsInstance(witnessed[0].basis, Stated)
        self.assertEqual("поручитель по невесте", witnessed[0].cite.stated_role)

    def test_two_sureties_of_one_side_meet_and_across_sides_they_do_not(self) -> None:
        """The witness×witness join pairs only those who vouched for one party."""
        from verso.ru.domain import Side

        def wedding(n: int) -> _Marriage:
            return _Marriage(year=1840 + n, witnesses=[
                Person("Фома", "Ильинъ", "Колючкин", side=Side.GROOM),
                Person("Иванъ", "Петровъ", "Тихоходов", side=Side.BRIDE)], **self._couple(n))
        found = cooccurrences(_wedding_facts([wedding(1), wedding(2)]),
                              left=WitnessedAt, right=WitnessedAt,
                              identity=name_identity(canonical_fold))
        self.assertEqual([], found)

class IdentityIsAStrategy(unittest.TestCase):
    """The rule must not care HOW appearances become people.

    Пункт 2: the checks that hurt most read the tree AFTER consolidation, so a
    fact's subject has to be resolvable to the same person the translator
    produced. That is a different `Identity`, not a different rule.
    """

    def test_the_rule_accepts_an_identity_that_ignores_names_entirely(self) -> None:
        """A deliberately perverse identity: everyone in a record is one person
        per slot. The rule still runs and still counts records once."""
        def by_ordinal(record: Record):
            def key(ref: Persona) -> tuple[str, None]:
                return (f"person-{ref.id.rpartition('/')[2]}", None)
            return key

        births = [_Birth(record_num=n, year=1840 + n, child=_person("Иван"),
                         father=_person("Пётр", "Ивановъ"),
                         god_parents=[_person("Фома", "Ильинъ")]) for n in (1, 2)]
        facts = AssertionSet(facts_from_births(
            [(b, "test_births.py") for b in births], village="Тест"))
        found = cooccurrences(facts, left=ParentOf, right=GodparentOf,
                              identity=by_ordinal)
        self.assertEqual(1, len(found))
        self.assertEqual([("person-father", None), ("person-godparent1", None)],
                         sorted([found[0].left_key, found[0].right_key]))


def cast_derived(basis) -> Derived:
    assert isinstance(basis, Derived)
    return basis


if __name__ == "__main__":
    unittest.main()
