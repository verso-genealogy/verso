"""Tests for ROV001 — redundant (dead) `override` fields.

`profiles_to_consolidate[*]["override"]` unconditionally replaces fields after
every merge. When it writes the value already present it changes nothing, and
silently re-imposes the old value if the DSL is later corrected. These tests
drive the REAL generator through `finalize()` so detection stays tied to what
actually renders.
"""
import unittest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.redundant_overrides import (
    RedundantOverride, exit_code_for_redundant_overrides, format_redundant_override_report)
from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator


def _ev(day=None, month=None, year=None):
    return GeniEvent(date=GeniDate(day=day, month=month, year=year))


def _run(override, *, records):
    """Fold `records` into canonical "canon" under `override`, then finalize."""
    consolidation = Consolidation(
        profile_move_list={r.res_name: "canon" for r in records},
        profile_overrides={"canon": override},
    )
    gen = TerraformGenerator(consolidation=consolidation)
    for rec in records:
        gen._emit_profile("out.tf", rec)
    gen.finalize()
    return gen.redundant_overrides


class DeadScalarOverride(unittest.TestCase):
    def test_override_matching_the_merged_value_is_flagged(self):
        findings = _run(
            GeniProfile(first_name="Иван"),
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 last_name="Марков")])

        self.assertEqual([(f.canonical, f.field) for f in findings],
                         [("canon", "first_name")])

    def test_override_changing_the_merged_value_is_not_flagged(self):
        findings = _run(
            GeniProfile(first_name="Иоанн"),
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 last_name="Марков")])

        self.assertEqual(findings, [])

    def test_override_supplying_a_value_absent_from_records_is_not_flagged(self):
        # The load-bearing case: sources carry no last_name, the override
        # supplies a Geni-recovered one. It changes the profile, so it is not
        # a no-op and ROV001 must leave it alone.
        findings = _run(
            GeniProfile(last_name="Молчалин"),
            records=[GeniProfile(res_name="rec_a", first_name="Фёдор")])

        self.assertEqual(findings, [])


class DeadCurrentResidenceOverride(unittest.TestCase):
    def test_identical_residence_is_flagged(self):
        findings = _run(
            GeniProfile(current_residence="село Горюхино"),
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 current_residence="село Горюхино")])

        self.assertEqual([f.field for f in findings], ["current_residence"])

    def test_differing_residence_is_not_flagged(self):
        findings = _run(
            GeniProfile(current_residence="село Собакевичево"),
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 current_residence="село Горюхино")])

        self.assertEqual(findings, [])


class DeadEventOverride(unittest.TestCase):
    """Events are mutated IN PLACE by `_apply_profile_overrides`, so the
    before-snapshot must be a deep copy or every event looks unchanged."""

    def test_identical_birth_is_flagged(self):
        findings = _run(
            GeniProfile(birth=_ev(13, 4, 1831)),
            records=[GeniProfile(res_name="rec_a", first_name="Савелий",
                                 birth=_ev(13, 4, 1831))])

        self.assertEqual([f.field for f in findings], ["birth"])

    def test_differing_birth_is_not_flagged(self):
        findings = _run(
            GeniProfile(birth=_ev(13, 4, 1831)),
            records=[GeniProfile(res_name="rec_a", first_name="Савелий",
                                 birth=_ev(1, 1, 1830))])

        self.assertEqual(findings, [])


class LooseDateEqualityIsNotEnough(unittest.TestCase):
    """`GeniDate.__eq__` compares only (day, month, year) — deliberately, for
    merge logic. An override that narrows a range to a circa year therefore
    compares EQUAL while genuinely changing the rendered date, so ROV001 must
    compare structurally instead of leaning on `==`."""

    def test_override_narrowing_a_range_is_not_flagged(self):
        wide = GeniDate(year=1805, circa=True, date_range="between",
                        end_year=1809, end_circa=True)
        narrow = GeniDate(year=1805, circa=True)
        self.assertEqual(wide, narrow)   # documents the loose ==

        findings = _run(
            GeniProfile(birth=GeniEvent(date=narrow)),
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 birth=GeniEvent(date=wide))])

        self.assertEqual(findings, [])

    def test_override_changing_only_the_location_is_not_flagged(self):
        findings = _run(
            GeniProfile(birth=GeniEvent(date=_ev(1, 1, 1800).date,
                                        location="село Простофилино")),
            records=[GeniProfile(res_name="rec_a", first_name="Иван",
                                 birth=GeniEvent(date=_ev(1, 1, 1800).date,
                                                 location="село Горюхино"))])

        self.assertEqual(findings, [])


class ConflictSuppressingOverrideIsNotDead(unittest.TestCase):
    """`resolved_by_override` treats any override carrying a field as an
    explicit resolution of a merge conflict on it. Such an override is
    load-bearing even when its value is a no-op: removing it would surface a
    real source disagreement. ROV001 fires only when removal changes neither
    the profile nor the conflict set."""

    def test_value_noop_that_silences_a_conflict_is_not_flagged(self):
        # Two records disagree on middle_name. The override pins the winner —
        # the value the merge would have kept anyway — so it is a value no-op,
        # but it is what marks the disagreement resolved.
        findings = _run(
            GeniProfile(middle_name="Андреевна"),
            records=[
                GeniProfile(res_name="rec_a", first_name="Агафья",
                            middle_name="Андреевна"),
                GeniProfile(res_name="rec_b", first_name="Агафья",
                            middle_name="Адриановна"),
            ])

        self.assertEqual(findings, [])

    def test_value_noop_without_any_conflict_is_still_flagged(self):
        # Same shape, but the records agree — nothing is being resolved, so
        # the override really is dead.
        findings = _run(
            GeniProfile(middle_name="Андреевна"),
            records=[
                GeniProfile(res_name="rec_a", first_name="Агафья",
                            middle_name="Андреевна"),
                GeniProfile(res_name="rec_b", first_name="Агафья",
                            middle_name="Андреевна"),
            ])

        self.assertEqual([f.field for f in findings], ["middle_name"])


class DeadNicknamesOverride(unittest.TestCase):
    def test_identical_nicknames_are_flagged(self):
        findings = _run(
            GeniProfile(nicknames=["Савва"]),
            records=[GeniProfile(res_name="rec_a", first_name="Савелий",
                                 nicknames=["Савва"])])

        self.assertEqual([f.field for f in findings], ["nicknames"])


class ReportAndExitCode(unittest.TestCase):
    def _one(self):
        return [RedundantOverride(canonical="canon", field="first_name",
                                  value="'Иван'")]

    def test_report_names_canonical_and_field(self):
        report = format_redundant_override_report(self._one())

        self.assertIn("ROV001", report)
        self.assertIn("canon.first_name", report)

    def test_empty_findings_render_no_report(self):
        self.assertEqual(format_redundant_override_report([]), "")

    def test_exit_code_zero_without_the_flag(self):
        self.assertEqual(
            exit_code_for_redundant_overrides(self._one(),
                                              fail_on_conflicts=False), 0)

    def test_exit_code_nonzero_with_the_flag(self):
        self.assertNotEqual(
            exit_code_for_redundant_overrides(self._one(),
                                              fail_on_conflicts=True), 0)

    def test_exit_code_zero_when_clean(self):
        self.assertEqual(
            exit_code_for_redundant_overrides([], fail_on_conflicts=True), 0)


class ExitCodePrecedence(unittest.TestCase):
    """Conflicts and ROV001 have distinct exit codes; when both are present
    the conflict code wins so existing CI signals do not change meaning."""

    def test_conflict_code_takes_precedence(self):
        from verso.core.targets.geni.consolidation_conflicts import (
            CONFLICT_FAIL_EXIT_CODE, ConsolidationConflict, exit_code_for_conflicts)
        conflicts = [ConsolidationConflict("canon", "last_name", "A", "B", "r")]
        findings = [RedundantOverride("canon", "first_name", "'Иван'")]

        combined = (exit_code_for_conflicts(conflicts, fail_on_conflicts=True)
                    or exit_code_for_redundant_overrides(
                        findings, fail_on_conflicts=True))

        self.assertEqual(combined, CONFLICT_FAIL_EXIT_CODE)

    def test_rov001_code_used_when_no_conflicts(self):
        from verso.core.targets.geni.consolidation_conflicts import exit_code_for_conflicts
        from verso.core.targets.geni.redundant_overrides import (
            REDUNDANT_OVERRIDE_FAIL_EXIT_CODE)
        findings = [RedundantOverride("canon", "first_name", "'Иван'")]

        combined = (exit_code_for_conflicts([], fail_on_conflicts=True)
                    or exit_code_for_redundant_overrides(
                        findings, fail_on_conflicts=True))

        self.assertEqual(combined, REDUNDANT_OVERRIDE_FAIL_EXIT_CODE)

    def test_the_two_codes_are_distinct(self):
        from verso.core.targets.geni.consolidation_conflicts import CONFLICT_FAIL_EXIT_CODE
        from verso.core.targets.geni.redundant_overrides import (
            REDUNDANT_OVERRIDE_FAIL_EXIT_CODE)

        self.assertNotEqual(CONFLICT_FAIL_EXIT_CODE,
                            REDUNDANT_OVERRIDE_FAIL_EXIT_CODE)


if __name__ == "__main__":
    unittest.main()
