"""The two things the facts model adds that the spike did not have.

`FactDate` because every date comparison in the consolidation checks is
charitable-interval arithmetic, and 38% of Горюхино's birth dates and 77% of
its death events are ranges rather than points. `Retracted` because an author's
«так в подлиннике» is a statement about a record, and the checks that honour it
withdraw a derived VALUE rather than suppressing a finding.
"""
from __future__ import annotations

import unittest

from verso.ru.facts.model import (
    Assertion, AssertionSet, BornOn, Bound, Citation, Derived, FactDate, Persona, Retracted, Stated, Surety, why)

CITE = Citation(village="Тест", source_file="t.py", record_kind="birth",
                record_num="1", entry=0, year=1875, locator="child")
WHO = Persona("t.py#0:1875:1/child")


class Interval(unittest.TestCase):
    def test_a_bare_year_spans_the_whole_year(self):
        d = FactDate(year=1875)
        self.assertEqual((1875, 1, 1), d.earliest)
        self.assertEqual((1875, 12, 31), d.latest)

    def test_a_month_spans_to_a_conservative_28th(self):
        """28 is right for every month — the same lower bound GeniDate uses."""
        d = FactDate(year=1875, month=2)
        self.assertEqual((1875, 2, 1), d.earliest)
        self.assertEqual((1875, 2, 28), d.latest)

    def test_a_full_date_is_a_point(self):
        d = FactDate(year=1875, month=3, day=17)
        self.assertEqual((1875, 3, 17), d.earliest)
        self.assertEqual((1875, 3, 17), d.latest)

    def test_before_is_unbounded_below(self):
        d = FactDate(year=1875, bound=Bound.BEFORE)
        self.assertIsNone(d.earliest)
        self.assertEqual((1875, 12, 31), d.latest)

    def test_after_is_unbounded_above(self):
        """«был жив в 1850» — 77% of Горюхино's death events are this."""
        d = FactDate(year=1850, bound=Bound.AFTER)
        self.assertEqual((1850, 1, 1), d.earliest)
        self.assertIsNone(d.latest)

    def test_between_runs_to_its_far_end(self):
        d = FactDate(year=1848, bound=Bound.BETWEEN, end_year=1883)
        self.assertEqual((1848, 1, 1), d.earliest)
        self.assertEqual((1883, 12, 31), d.latest)

    def test_circa_is_an_approximation_not_a_range(self):
        d = FactDate(year=1898, month=9, circa=True)
        self.assertEqual((1898, 9, 1), d.earliest)
        self.assertEqual((1898, 9, 30), d.latest)
        self.assertIsNone(d.bound)

    def test_a_dayless_month_runs_to_that_month_s_own_end(self):
        """The 28th is the last day that EXISTS in every month, not the latest
        day an April date can mean. Reading it as the latest made a burial
        dated «апрель 1794» fall entirely before a death on the 29th — 182
        findings across two villages, one shape, none real."""
        self.assertEqual((1794, 4, 30), FactDate(year=1794, month=4).latest)
        self.assertEqual((1794, 1, 31), FactDate(year=1794, month=1).latest)
        self.assertEqual((1794, 2, 28), FactDate(year=1794, month=2).latest)
        self.assertEqual((1796, 2, 29), FactDate(year=1796, month=2).latest)

    def test_a_julian_century_february_has_twenty_nine_days(self):
        """The books are Julian: 1700, 1800 and 1900 are leap years there and
        common years in the proleptic Gregorian `monthrange`. Горюхино 1800
        buries «??.02» (the month block's February, no day) someone who died
        on the 29th — and with a 28-day February the burial preceded it."""
        for year in (1700, 1800, 1900):
            with self.subTest(year=year):
                self.assertEqual((year, 2, 29), FactDate(year=year, month=2).latest)
        self.assertEqual((1801, 2, 28), FactDate(year=1801, month=2).latest)
        self.assertEqual((1600, 2, 29), FactDate(year=1600, month=2).latest)

    def test_a_february_burial_does_not_precede_a_death_on_the_29th(self):
        february = FactDate(year=1800, month=2)
        self.assertFalse(february.definitely_before(FactDate(year=1800, month=2, day=29)))

    def test_a_dayless_month_no_longer_precedes_the_end_of_itself(self):
        april = FactDate(year=1794, month=4)
        self.assertFalse(april.definitely_before(FactDate(year=1794, month=4, day=29)))
        self.assertTrue(april.definitely_before(FactDate(year=1794, month=5, day=1)))

    def test_a_range_END_keeps_the_conservative_28th(self):
        """Pinned to `GeniDate.to_end_datetime`, which chose it deliberately —
        an interval that silently disagrees with the oracle's is the risk the
        bridge exists to hold shut."""
        d = FactDate(year=1860, month=5, bound=Bound.BETWEEN,
                     end_year=1861, end_month=7)
        self.assertEqual((1861, 7, 28), d.latest)


class Comparison(unittest.TestCase):
    def test_disjoint_intervals_do_not_overlap(self):
        self.assertFalse(FactDate(year=1875).overlaps(FactDate(year=1876)))

    def test_a_wide_range_overlaps_a_point_inside_it(self):
        wide = FactDate(year=1848, bound=Bound.BETWEEN, end_year=1883)
        self.assertTrue(wide.overlaps(FactDate(year=1860, month=5, day=2)))

    def test_an_open_end_overlaps_anything_after_it(self):
        alive = FactDate(year=1850, bound=Bound.AFTER)
        self.assertTrue(alive.overlaps(FactDate(year=1900)))
        self.assertFalse(alive.overlaps(FactDate(year=1800)))

    def test_definitely_before_needs_no_overlap_at_all(self):
        self.assertTrue(FactDate(year=1875).definitely_before(FactDate(year=1876)))
        self.assertFalse(FactDate(year=1875).definitely_before(FactDate(year=1875)))

    def test_an_open_range_is_never_definitely_before(self):
        """A lower bound cannot settle an ordering — that is the whole point."""
        alive = FactDate(year=1850, bound=Bound.AFTER)
        self.assertFalse(alive.definitely_before(FactDate(year=1900)))


def _born(basis) -> Assertion:
    return BornOn(subject=WHO, cite=CITE, basis=basis, date=FactDate(year=1875))


class Retraction(unittest.TestCase):
    def test_a_rule_never_sees_a_retracted_assertion(self):
        kept = _born(Stated())
        gone = _born(Retracted("возраст сверен при 12×", Stated()))
        believed = AssertionSet([kept, gone]).believed()
        self.assertEqual([kept], list(believed))

    def test_why_prints_the_retraction_over_what_the_source_said(self):
        text = why(_born(Retracted("«1 мѣсяцъ» читается верно", Stated())))
        self.assertIn("ОТОЗВАНО: «1 мѣсяцъ» читается верно", text)
        self.assertIn("было ЗАПИСАНО", text)

    def test_a_retraction_can_withdraw_a_derived_value(self):
        """`sibling_spacing` withdraws a birth year derived from a burial age,
        not a finding — so the retraction wraps the derivation."""
        premise = _born(Stated())
        derived = Derived("death.age-subtracted", Surety.ASSUMED, (premise,))
        text = why(_born(Retracted("возраст не сходится", derived)))
        self.assertIn("ОТОЗВАНО", text)
        self.assertIn("было ВЫВЕДЕНО (death.age-subtracted, ASSUMED)", text)

    def test_an_unretracted_derivation_still_prints_its_premises(self):
        premise = _born(Stated())
        text = why(_born(Derived("birth.co-parents-are-spouses",
                                 Surety.INFERRED, (premise,))))
        self.assertIn("ВЫВЕДЕНО (birth.co-parents-are-spouses, INFERRED)", text)
        self.assertIn("← ", text)
