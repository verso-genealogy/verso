"""Two records of one person that cannot both say when that person was born.

`birth-claims` is the third caller of `verso.ru.facts.rules.disagreement` and the
corpus's first check for a fold that went too far. What these tests pin is the
judgement the caller brings and the rule does not: what an age ASSERTS, how
much slack two claims get, when an old age is the parish's habit rather than a
second person, and that two columns of one roll are not this check's to compare.
"""
from __future__ import annotations

import random
import unittest
from collections.abc import Callable
from datetime import date

from verso.ru.cli.facts import (
    BirthTree, birth_tree, format_birth_claims, geni_date_literal, geni_date_ru)
from verso.ru.facts.checks.births import birth_claims_of, birth_pairs, birth_span
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import (
    AgedYears, AssertionSet, BornOn, Citation, FactDate, Persona, Record, Retracted, Stated)
from verso.core.targets.geni.date import GeniDate


def _cite(source_file: str, entry: int = 1) -> Citation:
    return Citation(village="Тестовка", source_file=source_file, record_kind="k",
                    record_num=str(entry), entry=entry, year=1816, locator="who")


def _who(source_file: str, entry: int = 1) -> Persona:
    return Persona(f"{source_file}#{entry}/child")


def _aged(age: float | int | str, as_of: FactDate, source_file: str,
          entry: int = 1) -> AgedYears:
    return AgedYears(subject=_who(source_file, entry), cite=_cite(source_file, entry),
                     basis=Stated(), age=age, as_of=as_of)


def _born(on: FactDate, source_file: str, entry: int = 1) -> BornOn:
    return BornOn(subject=_who(source_file, entry), cite=_cite(source_file, entry),
                  basis=Stated(), date=on)


def _one_person(_record: Record) -> Callable[[Persona], IdentityKey | None]:
    """Every appearance folded into one canonical — what a config fold does."""
    return lambda _who: ("the_canonical",)


def _by_persona(_record: Record) -> Callable[[Persona], IdentityKey | None]:
    """Every appearance its own person — nothing was folded."""
    return lambda who: (str(who),)


def _found(*claims, identity=_one_person, min_gap_years: float = 0.0):
    return birth_claims_of(AssertionSet(claims), identity, min_gap_years=min_gap_years)


class AnAgeIsTheIntervalItAsserts(unittest.TestCase):
    """«1 годъ» is anyone who has completed one year and not two."""

    def test_a_birth_inside_the_asserted_year_is_covered(self):
        span = birth_span(_aged(1, FactDate(year=1876, month=6, day=15), "d.py"))
        assert span is not None
        self.assertLessEqual(span.first, date(1874, 6, 16).toordinal())
        self.assertGreaterEqual(span.last, date(1875, 6, 14).toordinal())

    def test_a_birth_two_years_before_is_not(self):
        span = birth_span(_aged(1, FactDate(year=1876, month=6, day=15), "d.py"))
        assert span is not None
        self.assertGreater(span.first, date(1874, 6, 1).toordinal())

    def test_a_dated_birth_is_its_own_interval(self):
        span = birth_span(_born(FactDate(year=1832), "r.py"))
        assert span is not None
        self.assertEqual((date(1832, 1, 1).toordinal(), date(1832, 12, 31).toordinal()),
                         (span.first, span.last))
        self.assertEqual(0.0, span.stated_years)

    def test_an_age_the_parser_declines_places_nothing(self):
        self.assertIsNone(birth_span(_aged("году", FactDate(year=1719), "r.py")))

    def test_an_undated_age_places_nothing(self):
        self.assertIsNone(birth_span(_aged(40, FactDate(), "r.py")))


class TheSlackGrowsWithTheAge(unittest.TestCase):
    def test_two_readings_three_years_apart_at_forty_stand_together(self):
        """Allowed max(2, 20 % of 38) = 7.6 years."""
        self.assertEqual([], _found(
            _aged(38, FactDate(year=1834, month=2, day=28), "rs1834.py"),
            _born(FactDate(year=1792), "mk1792.py")))

    def test_two_readings_three_years_apart_in_childhood_do_not(self):
        """A child is 5 in the 1850 roll and born in 1840 by the metric book —
        the 2-year floor is all the slack a child's age gets."""
        found = _found(_aged(5, FactDate(year=1850), "rs1850.py"),
                       _born(FactDate(year=1840), "mk1840.py"))
        self.assertEqual(1, len(found))


class APersonTwoRecordsCannotBeOneLife(unittest.TestCase):
    def test_a_girl_of_eight_who_is_77_in_the_next_roll(self):
        """A girl of 8 in the 1816 roll who is 77 in the 1834 one."""
        found = _found(_aged(8, FactDate(year=1816), "rs1816.py"),
                       _aged(77, FactDate(year=1834, month=1, day=30), "rs1834.py"))
        self.assertEqual(1, len(found))
        self.assertEqual("HIGH", found[0].confidence)
        self.assertGreater(found[0].widest.years, 40)

    def test_nothing_is_compared_across_two_people(self):
        self.assertEqual([], _found(
            _aged(8, FactDate(year=1816), "rs1816.py"),
            _aged(77, FactDate(year=1834, month=1, day=30), "rs1834.py"),
            identity=_by_persona))

    def test_two_columns_of_one_roll_are_cai002_s_not_this_check_s(self):
        self.assertEqual([], _found(
            _aged(8, FactDate(year=1816), "rs1834.py"),
            _aged(77, FactDate(year=1834), "rs1834.py")))

    def test_a_withdrawn_claim_is_gone_before_the_rule_sees_it(self):
        withdrawn = BornOn(subject=_who("mk1733.py"), cite=_cite("mk1733.py"),
                           basis=Retracted(reason="так в подлиннике", retracts=Stated()),
                           date=FactDate(year=1733))
        facts = AssertionSet([withdrawn, _born(FactDate(year=1774), "rs1816.py")])
        self.assertEqual(1, len(birth_claims_of(facts, _one_person)))
        self.assertEqual([], birth_claims_of(facts.believed(), _one_person))


class TheOldAreMadeOlder(unittest.TestCase):
    """Over seventy the books overstate an age by up to 30 %; past that it is
    two people, whatever the ages."""

    def test_ninety_at_burial_against_sixty_eight_in_the_roll_is_low(self):
        """A man «90» at burial in 1818, 68 in the 1816 roll."""
        found = _found(_aged(90, FactDate(year=1818, month=6, day=8), "mk1818.py"),
                       _aged(68, FactDate(year=1816), "rs1834.py"))
        self.assertEqual(["LOW"], [f.confidence for f in found])

    def test_ninety_eight_at_burial_against_twenty_six_is_high(self):
        """A man of about 44 buried at «98»."""
        found = _found(_aged(98, FactDate(year=1813, month=9, day=27), "mk1813.py"),
                       _aged(26, FactDate(year=1795), "rs1811.py"))
        self.assertEqual(["HIGH"], [f.confidence for f in found])

    def test_one_strong_gap_beside_a_weak_one_makes_the_person_high(self):
        found = _found(_aged(90, FactDate(year=1818, month=6, day=8), "mk1818.py"),
                       _aged(68, FactDate(year=1816), "rs1834.py"),
                       _born(FactDate(year=1790), "mk1790.py"))
        self.assertEqual(["HIGH"], [f.confidence for f in found])


class TheReport(unittest.TestCase):
    CLAIMS = (
        _aged(77, FactDate(year=1834, month=1, day=30), "rs1834.py"),
        _aged(8, FactDate(year=1816), "rs1816.py"),
        _aged(59, FactDate(year=1816, month=6, day=1), "rs1816b.py"),
    )

    def test_one_finding_per_person_listing_every_claim_earliest_birth_first(self):
        found = _found(*self.CLAIMS)
        self.assertEqual(1, len(found))
        self.assertEqual([77, 59, 8], [c.age for c in found[0].claims
                                       if isinstance(c, AgedYears)])

    def test_min_gap_drops_the_narrow(self):
        self.assertEqual([], _found(*self.CLAIMS, min_gap_years=60))

    def test_it_is_byte_stable_whatever_order_the_claims_arrive_in(self):
        claims = list(self.CLAIMS) + [
            _aged(5, FactDate(year=1850), "rs1850.py"),
            _born(FactDate(year=1840), "mk1840.py")]
        expected = format_birth_claims(_found(*claims), str)
        for seed in range(5):
            random.Random(seed).shuffle(claims)
            self.assertEqual(expected, format_birth_claims(_found(*claims), str))

    def test_nothing_found_says_so(self):
        self.assertIn("0 findings", format_birth_claims([], str))


def _tree(emitted: dict[str, tuple[GeniDate | None, ...]], *,
          shown: GeniDate | None = None) -> BirthTree:
    """Every record's profile minted under its source file, all folded into
    `the_canonical` — the shape `birth_tree` reads off a translation."""
    return BirthTree(
        shown=lambda canonical: shown if canonical == "the_canonical" else None,
        minted=lambda who: who.id.split("#")[0],
        emitted=lambda res_name: emitted.get(res_name, ()),
        folded=lambda _canonical: tuple(sorted(emitted)))


def _report(*claims, tree: BirthTree) -> list[str]:
    return format_birth_claims(_found(*claims), str, tree).splitlines()


class WhatGeniShowsIsReadAsAReaderSaysIt(unittest.TestCase):
    def test_a_range_between_two_told_years(self):
        self.assertEqual("между ок. 1784 и ок. 01.1796", geni_date_ru(GeniDate(
            year=1784, circa=True, end_month=1, end_year=1796, end_circa=True,
            date_range="between")))

    def test_a_birth_record_s_day(self):
        self.assertEqual("17.05.1904", geni_date_ru(GeniDate(day=17, month=5, year=1904)))

    def test_a_burial_age_s_month(self):
        self.assertEqual("ок. 06.1728", geni_date_ru(GeniDate(month=6, year=1728, circa=True)))

    def test_an_open_bound(self):
        self.assertEqual("после 1834", geni_date_ru(GeniDate(year=1834, date_range="after")))
        self.assertEqual("до 1884", geni_date_ru(GeniDate(year=1884, date_range="before")))

    def test_no_date_says_so(self):
        self.assertEqual("без даты рождения", geni_date_ru(None))


class TheIgnoreValueIsTheDerivedDateSpelledInFull(unittest.TestCase):
    """`GeniDate.__eq__` would accept a sloppier spelling; the report prints
    every field, so the pasted entry states what it drops."""

    def test_a_roll_age(self):
        self.assertEqual("GeniDate(year=1784, circa=True)",
                         geni_date_literal(GeniDate(year=1784, circa=True)))

    def test_a_burial_age(self):
        self.assertEqual("GeniDate(month=6, year=1728, circa=True)",
                         geni_date_literal(GeniDate(month=6, year=1728, circa=True)))

    def test_a_birth_record(self):
        self.assertEqual("GeniDate(day=17, month=5, year=1904)",
                         geni_date_literal(GeniDate(day=17, month=5, year=1904)))

    def test_a_range(self):
        self.assertEqual(
            'GeniDate(year=1780, end_year=1800, date_range="between")',
            geni_date_literal(GeniDate(year=1780, end_year=1800, date_range="between")))


class TheReportPrintsTheTreeSide(unittest.TestCase):
    """Two lookups every reviewed finding needed by hand: what Geni shows now,
    and the `ignore` value that drops one record's birth."""

    GIRL = _aged(8, FactDate(year=1816), "rs1816.py")
    OLD_WOMAN = _aged(77, FactDate(year=1834, month=1, day=30), "rs1834.py")

    def test_geni_s_birth_under_the_header_and_an_ignore_under_each_claim(self):
        lines = _report(self.GIRL, self.OLD_WOMAN, tree=_tree(
            {"rs1816.py": (GeniDate(year=1808, circa=True),),
             "rs1834.py": (GeniDate(year=1757, circa=True),)},
            shown=GeniDate(year=1757, circa=True, end_year=1808, end_circa=True,
                           date_range="between")))
        self.assertEqual("    на Geni: между ок. 1757 и ок. 1808", lines[3])
        self.assertEqual(["        ignore: GeniDate(year=1757, circa=True)",
                          "        ignore: GeniDate(year=1808, circa=True)"],
                         [lines[5], lines[7]])

    def test_without_a_tree_the_report_is_what_it_was(self):
        lines = format_birth_claims(_found(self.GIRL, self.OLD_WOMAN), str).splitlines()
        self.assertFalse([line for line in lines if "на Geni" in line or "ignore" in line])

    def test_a_value_another_folded_record_shares_warns_that_it_drops_both(self):
        """`GeniDate.__eq__` reads day, month and year only: an entry for the
        1834 roll's circa 1757 also drops a witness window opening in 1757."""
        lines = _report(self.GIRL, self.OLD_WOMAN, tree=_tree(
            {"rs1816.py": (GeniDate(year=1808, circa=True),),
             "rs1834.py": (GeniDate(year=1757, circa=True),),
             "witness1800.py": (GeniDate(year=1757, end_year=1780,
                                         date_range="between"),)}))
        self.assertTrue(lines[5].endswith("⚠ снимет и дату: witness1800.py"), lines[5])
        self.assertNotIn("⚠", lines[7])

    def test_two_claims_of_one_record_do_not_warn_about_each_other(self):
        previous = _aged(59, FactDate(year=1816), "rs1834.py")
        lines = _report(self.GIRL, self.OLD_WOMAN, previous, tree=_tree(
            {"rs1816.py": (GeniDate(year=1808, circa=True),),
             "rs1834.py": (GeniDate(year=1757, circa=True),)}))
        self.assertFalse([line for line in lines if "снимет" in line])

    def test_a_record_whose_birth_comes_from_another_of_its_figures_is_flagged(self):
        """A roll dates the birth by the CURRENT age: a wrong previous-revision
        age leaves the profile's date alone, and its printed value would drop
        the good one."""
        previous = _aged(26, FactDate(year=1834), "rs1850.py")
        current = _aged(62, FactDate(year=1850), "rs1850.py")
        lines = _report(previous, current, _born(FactDate(year=1788), "mk1788.py"),
                        tree=_tree({"rs1850.py": (GeniDate(year=1788, circa=True),),
                                    "mk1788.py": (GeniDate(year=1788),)}))
        flagged = [line for line in lines if "не из этого показания" in line]
        self.assertEqual(1, len(flagged))
        self.assertEqual("26 (на ??.??.1834)",
                         lines[lines.index(flagged[0]) - 1].split("  →")[0].strip())

    def test_a_record_that_gave_its_profile_no_birth_has_nothing_to_drop(self):
        lines = _report(self.GIRL, self.OLD_WOMAN, tree=_tree(
            {"rs1816.py": (None,), "rs1834.py": (GeniDate(year=1757, circa=True),)}))
        self.assertIn("снимать нечего", lines[7])

    def test_it_is_byte_stable_whatever_order_the_claims_arrive_in(self):
        claims = [self.GIRL, self.OLD_WOMAN, _aged(59, FactDate(year=1816), "rs1834.py")]
        tree = _tree({"rs1816.py": (GeniDate(year=1808, circa=True),),
                      "rs1834.py": (GeniDate(year=1757, circa=True),),
                      "witness1800.py": (GeniDate(year=1757),)})
        expected = format_birth_claims(_found(*claims), str, tree)
        for seed in range(5):
            random.Random(seed).shuffle(claims)
            self.assertEqual(expected, format_birth_claims(_found(*claims), str, tree))


class TheTreeIsReadOffTheTranslation(unittest.TestCase):
    """End to end through the translator: the printed value is the one its
    `ignore` compares with, so pasting it drops that record's birth and
    RIG001 has nothing to say."""

    ROLL = GeniDate(year=1732, circa=True)
    BURIAL = GeniDate(month=7, year=1710, circa=True)

    def _translate(self, ignore: list[dict[str, object]] | None = None):
        from verso.ru.domain import person
        from verso.ru.facts.extract.common import SlotIndex
        from verso.core.targets.geni.event import GeniEvent
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        gen = TerraformGenerator(
            village_dir="Тестовка",
            consolidation=Consolidation(profile_ignores={"canon": ignore or []}))
        slots = SlotIndex()
        for entry, (document, day, born) in enumerate(
                (("rs", 0, self.ROLL), ("mk_deaths", 5, self.BURIAL)), start=1):
            p = person("Марѳа", "Лазарева")
            profile = gen._profile_from_person(
                p, year=1750, month=7, day=day, document_name=document,
                record_number=str(entry), role="deceased",
                birth=GeniEvent(date=born))
            gen.consolidation.profile_move_list[profile.res_name] = "canon"
            slots.record(_who(document, entry), p)
            gen._emit_profile("out.tf", profile)
        gen.finalize()
        return gen, slots

    def test_the_bridge_names_each_record_s_own_birth_and_the_fold_s(self):
        gen, slots = self._translate()
        tree = birth_tree(gen, slots)
        res_name = tree.minted(_who("mk_deaths", 2))
        assert res_name is not None
        self.assertEqual(["GeniDate(month=7, year=1710, circa=True)"],
                         [geni_date_literal(d) for d in tree.emitted(res_name) if d])
        self.assertEqual(2, len(tree.folded("canon")))
        self.assertEqual(gen.canonical_profiles()["canon"].birth.date,
                         tree.shown("canon"))

    def test_the_printed_value_pasted_into_ignore_drops_that_birth(self):
        gen, slots = self._translate()
        tree = birth_tree(gen, slots)
        res_name = tree.minted(_who("mk_deaths", 2))
        assert res_name is not None
        (derived,) = tree.emitted(res_name)
        assert derived is not None
        pasted = eval(geni_date_literal(derived), {"GeniDate": GeniDate})
        gen, _ = self._translate([{"birth.date": pasted}])
        shown = gen.canonical_profiles()["canon"].birth.date
        self.assertEqual(geni_date_literal(self.ROLL), geni_date_literal(shown))
        self.assertEqual([], gen.redundant_ignores)

    def test_the_fold_does_not_rewrite_what_a_record_carried_in(self):
        gen, slots = self._translate()
        tree = birth_tree(gen, slots)
        self.assertEqual(
            "между ок. 07.1710 и ок. 1732", geni_date_ru(tree.shown("canon")))
        res_name = tree.minted(_who("rs", 1))
        assert res_name is not None
        self.assertEqual(["GeniDate(year=1732, circa=True)"],
                         [geni_date_literal(d) for d in tree.emitted(res_name) if d])


class ThePairingsAreATable(unittest.TestCase):
    def test_a_dated_birth_and_an_age_are_compared_once_each_way_round(self):
        self.assertEqual([(BornOn, BornOn), (BornOn, AgedYears), (AgedYears, AgedYears)],
                         birth_pairs())


if __name__ == "__main__":
    unittest.main()
