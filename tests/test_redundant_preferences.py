"""Tests for RPF001 — dead `preference` pins.

`profiles_to_consolidate[*]["preference"]` pins a name field on the record that
SEEDS the canonical. A pin writing the value the seed already carried leaves
the profile bit-identical, so nothing downstream can differ — that, and only
that, is what the check claims. These tests drive the REAL generator so the
claim stays tied to the code path that actually runs.
"""
import unittest

from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.redundant_preferences import (
    RedundantPreference, exit_code_for_redundant_preferences, format_redundant_preference_report)
from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator


def _run(preference, *, records, override=None):
    """Fold `records` into canonical "canon" under `preference`, then finalize.

    The FIRST record seeds the canonical, which is what a pin acts on.
    """
    consolidation = Consolidation(
        profile_move_list={r.res_name: "canon" for r in records},
        profile_preferences={"canon": preference},
        profile_overrides={"canon": override} if override else {},
    )
    gen = TerraformGenerator(consolidation=consolidation)
    for rec in records:
        gen._emit_profile("out.tf", rec)
    gen.finalize()
    return gen.redundant_preferences


class PinRestatingTheSeed(unittest.TestCase):
    def test_pin_matching_the_seed_is_flagged(self):
        findings = _run(
            {"last_name": "Кувшинников"},
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 last_name="Кувшинников")])

        self.assertEqual([(f.canonical, f.field) for f in findings],
                         [("canon", "last_name")])

    def test_pin_changing_the_seed_is_not_flagged(self):
        findings = _run(
            {"last_name": "Кувшинников"},
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 last_name="Кувшиников")])

        self.assertEqual(findings, [])

    def test_pin_filling_a_blank_seed_is_not_flagged(self):
        # The seed carries no surname at all, so the pin is the only thing
        # putting one there. Whether some later path would have supplied the
        # same value is exactly what this check refuses to guess about.
        findings = _run(
            {"last_name": "Кувшинников"},
            records=[GeniProfile(res_name="rec_a", first_name="Иван")])

        self.assertEqual(findings, [])

    def test_only_the_dead_field_of_a_multi_field_pin_is_flagged(self):
        findings = _run(
            {"first_name": "Иван", "last_name": "Кувшинников"},
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 last_name="Кувшиников")])

        self.assertEqual([f.field for f in findings], ["first_name"])

    def test_the_seed_is_the_first_record_not_the_last(self):
        # rec_a seeds; rec_b never reaches `_apply_preference`. A pin agreeing
        # with rec_b but not rec_a is live, and reporting it would delete the
        # very thing choosing between two readings.
        findings = _run(
            {"last_name": "Кувшинников"},
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 last_name="Кувшиников"),
                     GeniProfile(res_name="rec_b", first_name="Иван",
                                 last_name="Кувшинников")])

        self.assertEqual(findings, [])


class NicknameShadowedByItsOwnPin(unittest.TestCase):
    def test_nickname_equal_to_the_pin_of_the_same_field_is_flagged(self):
        findings = _run(
            {"middle_name": "Флорович", "nicknames": ["Флорович"]},
            records=[GeniProfile(res_name="rec_a", first_name="Филипп",
                                 middle_name="Фралович")])

        self.assertEqual(
            [(f.field, f.value) for f in findings],
            [("nicknames", "Флорович")])

    def test_nickname_differing_from_every_pin_is_not_flagged(self):
        # The corpus-absent alias case: deliberately pre-populated as curated
        # history, and never a finding.
        findings = _run(
            {"middle_name": "Флорович", "nicknames": ["Фралович"]},
            records=[GeniProfile(res_name="rec_a", first_name="Филипп",
                                 middle_name="Фралович")])

        self.assertEqual(findings, [])


class NeverSeededCanonical(unittest.TestCase):
    def test_preference_on_a_canonical_no_record_reaches_is_not_flagged(self):
        """That cluster is stale wholesale — CST001's finding, not this one."""
        consolidation = Consolidation(
            profile_preferences={"ghost": {"last_name": "Кувшинников"}},
        )
        gen = TerraformGenerator(consolidation=consolidation)
        gen.finalize()

        self.assertEqual(gen.redundant_preferences, [])


class Reporting(unittest.TestCase):
    def test_report_is_empty_without_findings(self):
        self.assertEqual(format_redundant_preference_report([]), "")

    def test_report_names_canonical_field_and_value(self):
        text = format_redundant_preference_report([
            RedundantPreference(canonical="canon", field="last_name",
                                value="Кувшинников", reason="because"),
        ])

        self.assertIn("RPF001", text)
        self.assertIn("canon.last_name = Кувшинников", text)
        self.assertIn("because", text)

    def test_exit_code_is_zero_unless_failing_is_requested(self):
        findings = [RedundantPreference(canonical="c", field="last_name",
                                        value="X", reason="r")]

        self.assertEqual(
            exit_code_for_redundant_preferences(
                findings, fail_on_conflicts=False), 0)
        self.assertEqual(
            exit_code_for_redundant_preferences(
                findings, fail_on_conflicts=True), 6)
        self.assertEqual(
            exit_code_for_redundant_preferences([], fail_on_conflicts=True), 0)


if __name__ == "__main__":
    unittest.main()
