"""One person holding two claims that cannot both be true.

The rule is the FAIL gate of the whole plan: three checks are meant to come out
of it, so what these tests pin is the generality — that it names no predicate,
compares only claims of ONE person, and carries the caller's verdict without
looking at it.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable

from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import (
    AssertionSet, BaptizedOn, BornOn, Citation, DiedOn, FactDate, Persona, Record, Retracted, Stated)
from verso.ru.facts.rules.disagreement import contradictions, held


def _cite(entry: int) -> Citation:
    return Citation(village="Тестовка", source_file="r.py", record_kind="k",
                    record_num=str(entry), entry=entry, year=1875, locator="who")


def _who(entry: int, ordinal: int = 0) -> Persona:
    return Persona(f"r.py#{entry}/{ordinal}")


def _by_persona(_record: Record) -> Callable[[Persona], IdentityKey | None]:
    """Every appearance its own person."""
    return lambda who: (str(who),)


def _one_person(_record: Record) -> Callable[[Persona], IdentityKey | None]:
    """Everybody is the same person — the coarsest fold there is."""
    return lambda _who: ("everybody",)


def _nobody(_record: Record) -> Callable[[Persona], IdentityKey | None]:
    """The refusing identity: it can place nobody."""
    return lambda _who: None


def _order(a, b) -> str | None:
    return "before" if a.date.definitely_before(b.date) else None


class ItComparesOnlyOnePersonSClaims(unittest.TestCase):
    def test_a_rejected_pair_is_reported_with_the_caller_s_verdict(self):
        who = _who(1)
        facts = AssertionSet([
            BaptizedOn(subject=who, cite=_cite(1), date=FactDate(year=1875, month=1, day=3),
                       basis=Stated()),
            BornOn(subject=who, cite=_cite(1), date=FactDate(year=1875, month=1, day=9),
                   basis=Stated()),
        ])
        found = contradictions(facts, left=BaptizedOn, right=BornOn,
                               identity=_by_persona, incompatible=_order)
        self.assertEqual(1, len(found))
        self.assertEqual("before", found[0].verdict)
        self.assertEqual((str(who),), found[0].who)

    def test_a_compatible_pair_is_not_reported(self):
        who = _who(1)
        facts = AssertionSet([
            BaptizedOn(subject=who, cite=_cite(1), date=FactDate(year=1875, month=1, day=9),
                       basis=Stated()),
            BornOn(subject=who, cite=_cite(1), date=FactDate(year=1875, month=1, day=3),
                   basis=Stated()),
        ])
        self.assertEqual([], contradictions(facts, left=BaptizedOn, right=BornOn,
                                            identity=_by_persona,
                                            incompatible=_order))

    def test_two_different_people_are_never_compared(self):
        """The whole shape of the rule: it is about ONE person's claims."""
        facts = AssertionSet([
            BaptizedOn(subject=_who(1), cite=_cite(1),
                       date=FactDate(year=1875, month=1, day=3), basis=Stated()),
            BornOn(subject=_who(2), cite=_cite(2),
                   date=FactDate(year=1875, month=1, day=9), basis=Stated()),
        ])
        self.assertEqual([], contradictions(facts, left=BaptizedOn, right=BornOn,
                                            identity=_by_persona,
                                            incompatible=_order))

    def test_a_coarser_fold_makes_the_same_facts_disagree(self):
        """Identity is a parameter, and it is what gives the rule its reach:
        the same two claims are one person's contradiction or two people's
        ordinary lives depending on the fold it is handed."""
        facts = AssertionSet([
            BaptizedOn(subject=_who(1), cite=_cite(1),
                       date=FactDate(year=1875, month=1, day=3), basis=Stated()),
            BornOn(subject=_who(2), cite=_cite(2),
                   date=FactDate(year=1875, month=1, day=9), basis=Stated()),
        ])
        self.assertEqual(1, len(contradictions(
            facts, left=BaptizedOn, right=BornOn, identity=_one_person,
            incompatible=_order)))

    def test_an_appearance_the_identity_refuses_is_dropped(self):
        facts = AssertionSet([
            BaptizedOn(subject=_who(1), cite=_cite(1),
                       date=FactDate(year=1875, month=1, day=3), basis=Stated()),
            BornOn(subject=_who(1), cite=_cite(1),
                   date=FactDate(year=1875, month=1, day=9), basis=Stated()),
        ])
        self.assertEqual([], contradictions(facts, left=BaptizedOn, right=BornOn,
                                            identity=_nobody,
                                            incompatible=_order))

    def test_one_claim_is_not_compared_with_itself(self):
        """With the same predicate on both sides, the pair (a, a) must not be
        offered to the test — an event never precedes itself, but a caller
        should not have to know that the rule might ask."""
        who = _who(1)
        early = DiedOn(subject=who, cite=_cite(1),
                       date=FactDate(year=1875, month=1, day=3), basis=Stated())
        late = DiedOn(subject=who, cite=_cite(2),
                      date=FactDate(year=1875, month=9, day=3), basis=Stated())
        found = contradictions(AssertionSet([early, late]), left=DiedOn,
                               right=DiedOn, identity=_by_persona,
                               incompatible=_order)
        self.assertEqual(1, len(found))
        self.assertIs(early, found[0].left)
        self.assertIs(late, found[0].right)


class ASameShapePairIsOnePair(unittest.TestCase):
    def test_a_symmetric_test_reports_the_pair_once(self):
        """Two deaths a year apart, one person: with the same predicate on
        both sides the pair is ONE pair of claims — reported once, not as
        (a, b) and again as (b, a)."""
        who = _who(1)
        a = DiedOn(subject=who, cite=_cite(1), date=FactDate(year=1875), basis=Stated())
        b = DiedOn(subject=who, cite=_cite(2), date=FactDate(year=1876), basis=Stated())
        found = contradictions(AssertionSet([a, b]), left=DiedOn, right=DiedOn,
                               identity=_by_persona,
                               incompatible=lambda x, y: "two deaths")
        self.assertEqual(1, len(found))

    def test_an_asymmetric_test_is_asked_both_ways(self):
        """The order the records arrived in does not decide which way the test
        is asked: a later death listed first is still caught."""
        who = _who(1)
        late = DiedOn(subject=who, cite=_cite(1),
                      date=FactDate(year=1875, month=9, day=3), basis=Stated())
        early = DiedOn(subject=who, cite=_cite(2),
                       date=FactDate(year=1875, month=1, day=3), basis=Stated())
        found = contradictions(AssertionSet([late, early]), left=DiedOn,
                               right=DiedOn, identity=_by_persona,
                               incompatible=_order)
        self.assertEqual(1, len(found))
        self.assertIs(early, found[0].left)


class ItNeverReadsABasis(unittest.TestCase):
    def test_a_withdrawn_claim_is_gone_before_the_rule_sees_it(self):
        """`believed()` is the caller's filter, and it is what makes an
        author's «так в подлиннике» cost a rule nothing."""
        who = _who(1)
        facts = AssertionSet([
            BaptizedOn(subject=who, cite=_cite(1),
                       date=FactDate(year=1875, month=1, day=3),
                       basis=Retracted("так в подлиннике", Stated())),
            BornOn(subject=who, cite=_cite(1),
                   date=FactDate(year=1875, month=1, day=9), basis=Stated()),
        ])
        self.assertEqual(1, len(contradictions(
            facts, left=BaptizedOn, right=BornOn, identity=_by_persona,
            incompatible=_order)))
        self.assertEqual([], contradictions(
            facts.believed(), left=BaptizedOn, right=BornOn,
            identity=_by_persona, incompatible=_order))


class HeldGroupsByPerson(unittest.TestCase):
    def test_it_groups_a_person_s_claims_of_one_shape(self):
        who = _who(1)
        facts = AssertionSet([
            DiedOn(subject=who, cite=_cite(1), date=FactDate(year=1875), basis=Stated()),
            DiedOn(subject=who, cite=_cite(2), date=FactDate(year=1880), basis=Stated()),
            BornOn(subject=who, cite=_cite(1), date=FactDate(year=1800), basis=Stated()),
        ])
        grouped = held(facts, kind=DiedOn, identity=_one_person)
        self.assertEqual({("everybody",)}, set(grouped))
        self.assertEqual(2, len(grouped[("everybody",)]))

    def test_a_person_holding_no_such_claim_is_absent(self):
        facts = AssertionSet([
            BornOn(subject=_who(1), cite=_cite(1), date=FactDate(year=1800),
                   basis=Stated()),
        ])
        self.assertEqual({}, held(facts, kind=DiedOn, identity=_by_persona))


class TheReportIsByteStable(unittest.TestCase):
    def test_findings_are_ordered_by_person_then_by_claim(self):
        facts = AssertionSet([
            BaptizedOn(subject=_who(9), cite=_cite(9),
                       date=FactDate(year=1875, month=1, day=3), basis=Stated()),
            BornOn(subject=_who(9), cite=_cite(9),
                   date=FactDate(year=1875, month=1, day=9), basis=Stated()),
            BaptizedOn(subject=_who(1), cite=_cite(1),
                       date=FactDate(year=1875, month=1, day=3), basis=Stated()),
            BornOn(subject=_who(1), cite=_cite(1),
                   date=FactDate(year=1875, month=1, day=9), basis=Stated()),
        ])
        found = contradictions(facts, left=BaptizedOn, right=BornOn,
                               identity=_by_persona, incompatible=_order)
        self.assertEqual([c.who for c in found], sorted(c.who for c in found))


class TheOrderingsAreATable(unittest.TestCase):
    """The orderings live in `verso.ru.facts.checks.dates`, not in the rule. One
    more costs a line there — and a hint, which this pins so it cannot be
    forgotten."""

    def test_every_ordering_brings_its_own_advice(self):
        from verso.ru.facts.checks.dates import HINTS, orderings
        kinds = {kind for _l, _r, kind, _e, _f in orderings()}
        self.assertEqual(kinds, set(HINTS))

    def test_the_table_holds_the_four_the_oracle_asks_then_gramps_five(self):
        from verso.ru.facts.checks.dates import orderings
        self.assertEqual(
            ["baptism_before_birth", "death_before_birth",
             "burial_before_death", "burial_before_birth",
             "marriage_before_birth", "death_before_marriage",
             "burial_before_marriage", "death_before_baptism",
             "burial_before_baptism", "death_before_alive", "burial_before_alive"],
            [kind for _l, _r, kind, _e, _f in orderings()])



class ACircaYearIsReadWithItsSlack(unittest.TestCase):
    """A сказка's «умер въ 1846» is a year told to the counter years later. On
    the 140 Горюхино people whose death a сказка and a metric book both give,
    the сказка is later than the burial by 1 year 14 times, by 2 five times, by
    3 never — and then by 4 to 8. So a circa year may not order anything
    within two years of it, and beyond that it may."""

    @staticmethod
    def _before(a: FactDate, b: FactDate) -> bool:
        from verso.ru.facts.checks.dates import definitely_before
        return definitely_before(a, b)

    def test_a_burial_two_years_before_a_told_death_year_is_its_slack(self):
        self.assertFalse(self._before(FactDate(year=1840, month=4, day=8),
                                      FactDate(year=1842, circa=True)))

    def test_six_years_is_two_people(self):
        """A man buried 8 April 1840, dead in 1846 by the 1850 сказка — the
        kind of gap a fold of two namesakes leaves."""
        self.assertTrue(self._before(FactDate(year=1840, month=4, day=8),
                                     FactDate(year=1846, circa=True)))

    def test_two_read_dates_get_no_slack(self):
        self.assertTrue(self._before(FactDate(year=1840, month=4, day=8),
                                     FactDate(year=1841)))


if __name__ == "__main__":
    unittest.main()
