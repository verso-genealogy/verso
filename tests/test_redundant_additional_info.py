"""Tests for RAI001 — dead `additional_info` entries.

`profiles_to_consolidate[*]["additional_info"]` is the layer that carries what
the sources do not: a Geni-recovered surname, a researched death bound, a
co-author's project membership. It merges with fill-in-if-missing semantics, so
a field it declares that the canonical already has is discarded in silence.
An entry that changes nothing is either stale or was meant to REPLACE a value —
which is `override`'s job, not this layer's.

These tests drive the REAL generator through `finalize()`, where the merge
actually happens.
"""
import unittest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.redundant_additional_info import (
    RedundantAdditionalInfo, exit_code_for_redundant_additional_info, format_redundant_additional_info_report)
from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator


def _ev(day=None, month=None, year=None):
    return GeniEvent(date=GeniDate(day=day, month=month, year=year))


def _run(additional_info, *, records):
    """Fold `records` into canonical "canon", then merge `additional_info`."""
    consolidation = Consolidation(
        profile_move_list={r.res_name: "canon" for r in records},
        profile_additional_info={"canon": additional_info},
    )
    gen = TerraformGenerator(consolidation=consolidation)
    for rec in records:
        gen._emit_profile("out.tf", rec)
    gen.finalize()
    return gen.redundant_additional_info


class EntryThatChangesNothing(unittest.TestCase):
    def test_surname_the_records_already_carry_is_flagged(self):
        findings = _run(
            [GeniProfile(last_name="Пошлепкина")],
            records=[GeniProfile(res_name="rec_a", first_name="Юлиана",
                                 last_name="Пошлепкина")])

        self.assertEqual([(f.canonical, f.index) for f in findings],
                         [("canon", 0)])
        self.assertEqual(findings[0].declared, ("last_name",))

    def test_surname_the_records_lack_is_not_flagged(self):
        # The load-bearing case this layer exists for: sources carry no
        # surname, additional_info supplies the Geni-recovered one.
        findings = _run(
            [GeniProfile(last_name="Пошлепкина")],
            records=[GeniProfile(res_name="rec_a", first_name="Юлиана")])

        self.assertEqual(findings, [])

    def test_death_bound_the_records_lack_is_not_flagged(self):
        findings = _run(
            [GeniProfile(death=_ev(year=1850))],
            records=[GeniProfile(res_name="rec_a", first_name="Марфа")])

        self.assertEqual(findings, [])

    def test_entry_filling_one_field_and_losing_another_is_not_flagged(self):
        """One surviving field makes the whole entry load-bearing."""
        findings = _run(
            [GeniProfile(last_name="Пошлепкина", birth_last_name="Пупырева")],
            records=[GeniProfile(res_name="rec_a", first_name="Юлиана",
                                 last_name="Пошлепкина")])

        self.assertEqual(findings, [])

    def test_each_entry_of_a_list_is_judged_on_its_own(self):
        findings = _run(
            [GeniProfile(last_name="Пошлепкина"),
             GeniProfile(birth_last_name="Пупырева")],
            records=[GeniProfile(res_name="rec_a", first_name="Юлиана",
                                 last_name="Пошлепкина")])

        self.assertEqual([f.index for f in findings], [0])

    def test_projects_already_present_are_flagged(self):
        findings = _run(
            [GeniProfile(projects=["project-1"])],
            records=[GeniProfile(res_name="rec_a", first_name="Анна",
                                 projects=["project-1"])])

        self.assertEqual([f.declared for f in findings], [("projects",)])

    def test_new_project_membership_is_not_flagged(self):
        findings = _run(
            [GeniProfile(projects=["project-2"])],
            records=[GeniProfile(res_name="rec_a", first_name="Анна",
                                 projects=["project-1"])])

        self.assertEqual(findings, [])


class NoCanonical(unittest.TestCase):
    def test_additional_info_for_a_canonical_no_record_reaches_is_skipped(self):
        consolidation = Consolidation(
            profile_additional_info={"ghost": [GeniProfile(last_name="X")]},
        )
        gen = TerraformGenerator(consolidation=consolidation)
        gen.finalize()

        self.assertEqual(gen.redundant_additional_info, [])


class Reporting(unittest.TestCase):
    def test_report_is_empty_without_findings(self):
        self.assertEqual(format_redundant_additional_info_report([]), "")

    def test_report_names_canonical_index_and_fields(self):
        text = format_redundant_additional_info_report([
            RedundantAdditionalInfo(canonical="canon", index=0,
                                    declared=("last_name",)),
        ])

        self.assertIn("RAI001", text)
        self.assertIn("canon[0] declares last_name", text)

    def test_exit_code_is_zero_unless_failing_is_requested(self):
        findings = [RedundantAdditionalInfo(canonical="c", index=0,
                                            declared=("last_name",))]

        self.assertEqual(
            exit_code_for_redundant_additional_info(
                findings, fail_on_conflicts=False), 0)
        self.assertEqual(
            exit_code_for_redundant_additional_info(
                findings, fail_on_conflicts=True), 7)
        self.assertEqual(
            exit_code_for_redundant_additional_info(
                [], fail_on_conflicts=True), 0)


if __name__ == "__main__":
    unittest.main()
