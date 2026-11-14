"""`union-dups`: the same-household guard read off the rolls.

The guard's evidence — «оба — члены двора N одной ревизии» — is a statement the
roll makes, taken from `EnumeratedIn` and placed on a canonical by the
consolidation bridge. Until 2026-09-25 it could also be recovered from res_names;
on the live corpus both readings gave byte-identical reports on all five
villages, three states running, and the res_name one was removed. These tests
pin the places where the roll can say what a res_name could not.
"""
from __future__ import annotations

import random
import unittest

from collections.abc import Callable

from verso.ru.facts.checks.lives import households_of_canonicals, lives_of_canonicals
from verso.ru.consolidation import union_duplicates as ud
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import (
    Assertion, AssertionSet, BaptizedOn, BornOn, Citation, DiedOn, EnumeratedIn, FactDate, Persona, Record, Stated, SurvivedUntil)
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.union import GeniUnion


def _listed(roll: str, entry: int, ordinal: int, *, group: str = "7",
            year: int = 1850, month: int = 10, day: int = 1) -> tuple[Persona, Assertion]:
    who = Persona(f"{roll}#{entry}/member{ordinal}")
    cite = Citation(village="Тестовка", source_file=roll, record_kind="census",
                    record_num=group, entry=entry, year=year,
                    locator=f"member{ordinal}")
    return who, EnumeratedIn(subject=who, cite=cite, group=group, within=roll,
                             as_of=FactDate(year=year, month=month, day=day),
                             basis=Stated())


def _bridge(placed: dict[Persona, str]) -> Callable[[Record], Callable[[Persona], IdentityKey | None]]:
    """The consolidation bridge, reduced to its answer: which canonical an
    appearance landed on, or a refusal."""
    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        def key(who: Persona) -> IdentityKey | None:
            canon = placed.get(who)
            return (canon,) if canon is not None else None
        return key
    return identity


def _profile(res_name: str, given: str, born: int) -> GeniProfile:
    return GeniProfile(res_name=res_name, first_name=given,
                       birth=GeniEvent(date=GeniDate(year=born)))


def _pair(a: str, b: str, given: str = "Настасья") -> tuple[dict[str, GeniProfile], dict[str, GeniUnion]]:
    profiles = {a: _profile(a, given, 1834), b: _profile(b, given, 1835)}
    return profiles, {"u": GeniUnion(res_name="u", partner_1="dad", children={a, b})}


def _verdict(profiles: dict[str, GeniProfile], unions: dict[str, GeniUnion],
             households: dict[str, frozenset[ud.Household]]) -> ud.UnionDuplicate:
    return ud.find_union_duplicates(
        profiles, unions, lambda r: r,
        households_of=lambda canon: households.get(canon, frozenset()))[0]


class TheRollSeparates(unittest.TestCase):
    def test_two_entries_of_one_household_are_two_people(self):
        a, fa = _listed("r1850.py", 0, 5)
        b, fb = _listed("r1850.py", 0, 6)
        households = households_of_canonicals(
            AssertionSet([fa, fb]), _bridge({a: "nastja_a", b: "nastja_b"}))
        found = _verdict(*_pair("nastja_a", "nastja_b"), households)
        self.assertEqual(ud.VERDICT_SAME_HOUSEHOLD, found.verdict)
        # The roll's own number, the roll, and its date.
        self.assertIn("двора 7 одного списка (r1850.py, 01.10.1850)", found.reason)

    def test_a_lettered_household_keeps_the_rolls_own_spelling(self):
        """«1в», not the `1v` a res_name would transliterate it to."""
        a, fa = _listed("r.py", 0, 1, group="1в")
        b, fb = _listed("r.py", 0, 2, group="1в")
        households = households_of_canonicals(
            AssertionSet([fa, fb]), _bridge({a: "x", b: "y"}))
        self.assertEqual({("1850-10-01", "1в", "r.py")}, set(households["x"]))

    def test_a_canonical_is_seen_in_its_household_without_a_move_list(self):
        """The hole of 2026-08-23, closed by the bridge rather than by
        rebuilding what the canonical absorbed: the appearance knows whose it
        is, so there is no res_name to have lost."""
        a, fa = _listed("r1850.py", 0, 5)
        b, fb = _listed("r1850.py", 0, 6)
        rec = "_1850_10_01_anastasija_vasilevna_rs_7_5_family_member"
        households = households_of_canonicals(
            AssertionSet([fa, fb]),
            _bridge({a: rec, b: "anastasija_vasilevna_4"}))
        found = _verdict(*_pair(rec, "anastasija_vasilevna_4"), households)
        self.assertEqual(ud.VERDICT_SAME_HOUSEHOLD, found.verdict)


class WhatAResNameCannotSay(unittest.TestCase):
    def test_two_rolls_numbering_a_household_alike_stay_two(self):
        """A двор number recurs across дела and villages. A res_name
        spells date and number and has nowhere for the roll, so the removed
        reading from res_names called two children of different rolls one
        household — a guard retiring a pair it had no evidence against."""
        a = "_1745_03_01_ivan_rs_1_2_family_member"
        b = "_1745_03_01_ivan_rs_1_3_family_member"
        profiles, unions = _pair(a, b, given="Иван")

        pa, fa = _listed("d1.py", 0, 2, group="1", year=1745, month=3, day=1)
        pb, fb = _listed("d2.py", 0, 3, group="1", year=1745, month=3, day=1)
        households = households_of_canonicals(
            AssertionSet([fa, fb]), _bridge({pa: a, pb: b}))
        self.assertTrue(_verdict(profiles, unions, households).is_candidate)

    def test_a_reconstructed_member_separates_nobody(self):
        """A `hidden=True` member has a profile and a household-shaped res_name,
        but the scribe never wrote them: the roll asserts no `EnumeratedIn`,
        and «перечислил их отдельно» is not true of somebody not listed."""
        written = "_1850_10_01_nastasja_rs_7_5_family_member"
        ours = "_1850_10_01_nastasja_rs_7_6_family_member"
        profiles, unions = _pair(written, ours)

        pw, fw = _listed("r1850.py", 0, 5)
        households = households_of_canonicals(
            AssertionSet([fw]), _bridge({pw: written}))
        self.assertTrue(_verdict(profiles, unions, households).is_candidate)

    def test_an_appearance_the_bridge_refuses_is_counted_nowhere(self):
        a, fa = _listed("r1850.py", 0, 5)
        _refused, fb = _listed("r1850.py", 0, 6)
        households = households_of_canonicals(
            AssertionSet([fa, fb]), _bridge({a: "nastja_a"}))
        self.assertEqual({"nastja_a"}, set(households))


class Stable(unittest.TestCase):
    def test_arrival_order_does_not_move_the_reason(self):
        """A pair counted together twice — two revisions — is named by the
        smallest household, whatever order the assertions came in."""
        rows = [_listed("r1834.py", 0, 1, year=1834, month=2, day=20),
                _listed("r1834.py", 0, 2, year=1834, month=2, day=20),
                _listed("r1850.py", 1, 1, group="9"),
                _listed("r1850.py", 1, 2, group="9")]
        placed = {rows[0][0]: "a", rows[1][0]: "b", rows[2][0]: "a", rows[3][0]: "b"}
        reasons = set()
        for seed in range(6):
            shuffled = [f for _who, f in rows]
            random.Random(seed).shuffle(shuffled)
            households = households_of_canonicals(AssertionSet(shuffled), _bridge(placed))
            reasons.add(_verdict(*_pair("a", "b"), households).reason)
        self.assertEqual(1, len(reasons))
        self.assertIn("двора 7 одного списка (r1834.py, 20.02.1834)", reasons.pop())


if __name__ == "__main__":
    unittest.main()


def _dated(kind: type, source: str, entry: int, date: FactDate) -> tuple[Persona, Assertion]:
    who = Persona(f"{source}#{entry}/member1")
    cite = Citation(village="Тестовка", source_file=source, record_kind="x",
                    record_num=str(entry), entry=entry, year=date.year,
                    locator="child")
    return who, kind(subject=who, cite=cite, date=date, basis=Stated())


class TheRecordsTellTheirLives(unittest.TestCase):
    """`lives_of_canonicals`: the baptisms, deaths and signs of life the
    second and third guards of `union-dups` stand on."""

    def _lives(self, *pairs: tuple[Persona, Assertion]) -> ud.Lives:
        placed = {who: "canon" for who, _ in pairs}
        return lives_of_canonicals(AssertionSet([a for _, a in pairs]),
                                   _bridge(placed))["canon"]

    def test_a_birth_christened_in_the_same_entry_is_a_baptism(self):
        born = _dated(BornOn, "births_1864.py", 58, FactDate(year=1864, month=6, day=21))
        christened = _dated(BaptizedOn, "births_1864.py", 58, FactDate(year=1864, month=6, day=22))
        lives = self._lives(born, christened)
        self.assertEqual(len(lives.baptisms), 1)
        (_key, first, last, said), = lives.baptisms
        self.assertEqual((first, last), ((1864, 6, 21), (1864, 6, 21)))
        self.assertIn("births_1864.py №58", said)

    def test_a_birth_nobody_christened_is_not_a_baptism(self):
        """A roll that writes a birth date (РС 1850 copies them from the metric
        book) christens nobody — it cannot separate two children."""
        lives = self._lives(_dated(BornOn, "census_1850.py", 7,
                                   FactDate(year=1840, month=3, day=1)))
        self.assertEqual(lives.baptisms, frozenset())

    def test_a_told_death_is_read_with_its_slack(self):
        """A сказка's «умер около 1830» can be as late as 1832, as in date-order."""
        lives = self._lives(_dated(DiedOn, "census_1834.py", 3,
                                   FactDate(year=1830, circa=True)))
        (last, _said), = lives.died_by
        self.assertEqual(last[0], 1832)

    def test_a_sign_of_life_is_its_earliest_day(self):
        lives = self._lives(_dated(SurvivedUntil, "census_1834.py", 3,
                                   FactDate(year=1834, month=2, day=20)))
        self.assertIn((1834, 2, 20), {day for day, _ in lives.alive_at})

    def test_a_death_is_also_a_sign_of_life_until_it(self):
        lives = self._lives(_dated(DiedOn, "deaths_1839.py", 5,
                                   FactDate(year=1839, month=4, day=2)))
        self.assertIn((1839, 4, 2), {day for day, _ in lives.alive_at})
        self.assertIn((1839, 4, 2), {day for day, _ in lives.died_by})


class TheOnlyReading(unittest.TestCase):
    """The rolls are what `union-dups` reads. The res_name reading it kept
    behind `--legacy` for one wave was removed on 2026-09-25."""

    class _Gen:
        def canonical_profiles(self):
            return {}

        def canonical_unions(self):
            return {}

        def resolve_canonical(self, ref):
            return ref

    def test_it_reads_the_rolls(self):
        from unittest import mock
        with mock.patch("verso.ru.consolidation.union_duplicates.union_evidence",
                        return_value=(self._Gen(), {}, {})) as facts:
            ud.main(["--village", "Тестовка"])
        facts.assert_called_once()

    def test_the_legacy_flag_is_gone(self):
        with self.assertRaises(SystemExit):
            ud.main(["--village", "Тестовка", "--legacy"])
