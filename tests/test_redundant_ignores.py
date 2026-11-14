"""Tests for RIG001 — `ignore` entries that never fire.

An ignore entry is dead iff its predicate never matched an incoming value at
ANY call site. There are three such sites — the seed-scrub, the merge, and
conflict detection — and instrumenting only some of them would report live
entries as dead. Each site therefore gets its own test, and each is
constructed so that ONLY that site consults `ignore`:

- seed-scrub: a single record, so no merge and no conflict detection run;
- merge: `existing` lacks the field, so the conflict check short-circuits on
  `existing.<attr>` before ever reaching `is_ignored_value`;
- conflict detection: an event-date (`birth.date`) ignore on two records
  whose dates genuinely differ. Event dates are ALSO consulted by the
  seed-scrub and the merge (an ignored date is dropped, not merely left out
  of the report — `tests/test_ignore_event_dates.py`), so this site is no
  longer the only one that can fire for a date; the test still pins that
  it fires.
"""
import unittest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.redundant_ignores import (
    RedundantIgnore, exit_code_for_redundant_ignores, format_redundant_ignore_report, matches_ignore)
from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator


def _ignore(**fields):
    """One ignore entry in the shape `generate_tf` builds."""
    entry = {"first_name": "", "middle_name": "", "last_name": "",
             "birth_last_name": "", "title": "",
             "birth.date": None, "death.date": None,
             "baptism.date": None, "burial.date": None}
    entry.update(fields)
    return entry


def _run(ignore_entries, *, records):
    consolidation = Consolidation(
        profile_move_list={r.res_name: "canon" for r in records},
        profile_ignores={"canon": ignore_entries},
    )
    gen = TerraformGenerator(consolidation=consolidation)
    for rec in records:
        gen._emit_profile("out.tf", rec)
    gen.finalize()
    return gen.redundant_ignores


class NeverMatchingEntryIsFlagged(unittest.TestCase):
    def test_value_no_record_carries_is_flagged(self):
        findings = _run(
            [_ignore(middle_name="Кондратьевич")],
            records=[
                GeniProfile(res_name="rec_a", first_name="Игнатий",
                            middle_name="Никифорович"),
                GeniProfile(res_name="rec_b", first_name="Игнатий",
                            middle_name="Никифорович"),
            ])

        self.assertEqual([(f.canonical, f.index) for f in findings],
                         [("canon", 0)])
        self.assertEqual(findings[0].declared, ("middle_name",))

    def test_multi_field_entry_flagged_only_when_no_field_matches(self):
        findings = _run(
            [_ignore(first_name="Марина", middle_name="Прохоровна")],
            records=[
                GeniProfile(res_name="rec_a", first_name="Марина",
                            middle_name="Ивановна"),
                GeniProfile(res_name="rec_b", first_name="Марина",
                            middle_name="Ивановна"),
            ])

        # `first_name` matched, so the entry is live even though
        # `middle_name` never did.
        self.assertEqual(findings, [])


class EntryFiringAtEachSiteIsNotFlagged(unittest.TestCase):
    """One test per call site. If a future refactor stops routing a site
    through `matches_ignore`, exactly one of these turns red."""

    def test_fires_at_the_seed_scrub_site(self):
        # The seed-scrub blanks an ignored value on the FIRST record so a
        # later variant can fill it in. A single record exercises only this
        # site — nothing merges, so no conflict detection runs either.
        findings = _run(
            [_ignore(middle_name="Кондратьевич")],
            records=[GeniProfile(res_name="rec_a", first_name="Игнатий",
                                 middle_name="Кондратьевич")])

        self.assertEqual(findings, [])

    def test_fires_at_the_merge_site(self):
        # `existing` lacks last_name, so the conflict check short-circuits on
        # `existing.last_name` before reaching is_ignored_value. Only
        # `_is_ignored` in the merge consults the rule.
        findings = _run(
            [_ignore(last_name="Ляпкин")],
            records=[
                GeniProfile(res_name="rec_a", first_name="Иван"),
                GeniProfile(res_name="rec_b", first_name="Иван",
                            last_name="Ляпкин"),
            ])

        self.assertEqual(findings, [])

    def test_fires_at_the_conflict_detection_site(self):
        # Two records with genuinely differing birth dates, the incoming one
        # ignored: conflict detection consults the rule (and so, since event
        # dates are dropped by the merge too, does the merge).
        findings = _run(
            [_ignore(**{"birth.date": GeniDate(day=2, month=9, year=1833)})],
            records=[
                GeniProfile(res_name="rec_a", first_name="Андрей",
                            birth=GeniEvent(
                                date=GeniDate(day=27, month=9, year=1833))),
                GeniProfile(res_name="rec_b", first_name="Андрей",
                            birth=GeniEvent(
                                date=GeniDate(day=2, month=9, year=1833))),
            ])

        self.assertEqual(findings, [])


class MatchesIgnorePredicate(unittest.TestCase):
    def test_records_every_matching_entry_not_just_the_first(self):
        seen: set[tuple[str, int]] = set()
        ignore = [_ignore(last_name="Индюшев"), _ignore(last_name="Индюшев")]

        self.assertTrue(matches_ignore("last_name", "Индюшев", ignore,
                                       seen=seen, canonical="canon"))
        self.assertEqual(seen, {("canon", 0), ("canon", 1)})

    def test_records_nothing_when_no_entry_matches(self):
        seen: set[tuple[str, int]] = set()

        self.assertFalse(matches_ignore("last_name", "Индюшев",
                                        [_ignore(last_name="Ляпкин")],
                                        seen=seen, canonical="canon"))
        self.assertEqual(seen, set())

    def test_works_without_a_sink(self):
        self.assertTrue(
            matches_ignore("last_name", "Индюшев", [_ignore(last_name="Индюшев")]))


class ReportAndExitCode(unittest.TestCase):
    def _one(self):
        return [RedundantIgnore(canonical="canon", index=0,
                                declared=("middle_name",))]

    def test_report_names_canonical_and_fields(self):
        report = format_redundant_ignore_report(self._one())

        self.assertIn("RIG001", report)
        self.assertIn("canon", report)
        self.assertIn("middle_name", report)

    def test_empty_findings_render_no_report(self):
        self.assertEqual(format_redundant_ignore_report([]), "")

    def test_exit_code_zero_without_the_flag(self):
        self.assertEqual(
            exit_code_for_redundant_ignores(self._one(),
                                            fail_on_conflicts=False), 0)

    def test_exit_code_nonzero_with_the_flag(self):
        self.assertNotEqual(
            exit_code_for_redundant_ignores(self._one(),
                                            fail_on_conflicts=True), 0)

    def test_exit_code_is_distinct_from_the_others(self):
        from verso.core.targets.geni.consolidation_conflicts import (
            CONFLICT_FAIL_EXIT_CODE)
        from verso.core.targets.geni.redundant_ignores import (
            REDUNDANT_IGNORE_FAIL_EXIT_CODE)
        from verso.core.targets.geni.redundant_overrides import (
            REDUNDANT_OVERRIDE_FAIL_EXIT_CODE)

        self.assertEqual(
            len({CONFLICT_FAIL_EXIT_CODE, REDUNDANT_OVERRIDE_FAIL_EXIT_CODE,
                 REDUNDANT_IGNORE_FAIL_EXIT_CODE}), 3)


class ExitCodePrecedence(unittest.TestCase):
    """Conflicts win over ROV001, which wins over RIG001, so an existing CI
    signal never changes meaning when a new check starts firing."""

    def test_rov001_takes_precedence_over_rig001(self):
        from verso.core.targets.geni.redundant_overrides import (
            REDUNDANT_OVERRIDE_FAIL_EXIT_CODE, RedundantOverride, exit_code_for_redundant_overrides)
        overrides = [RedundantOverride("canon", "first_name", "'Иван'")]
        ignores = [RedundantIgnore("canon", 0, ("middle_name",))]

        combined = (exit_code_for_redundant_overrides(
                        overrides, fail_on_conflicts=True)
                    or exit_code_for_redundant_ignores(
                        ignores, fail_on_conflicts=True))

        self.assertEqual(combined, REDUNDANT_OVERRIDE_FAIL_EXIT_CODE)

    def test_rig001_code_used_when_nothing_else_fires(self):
        from verso.core.targets.geni.redundant_ignores import (
            REDUNDANT_IGNORE_FAIL_EXIT_CODE)
        from verso.core.targets.geni.redundant_overrides import (
            exit_code_for_redundant_overrides)
        ignores = [RedundantIgnore("canon", 0, ("middle_name",))]

        combined = (exit_code_for_redundant_overrides(
                        [], fail_on_conflicts=True)
                    or exit_code_for_redundant_ignores(
                        ignores, fail_on_conflicts=True))

        self.assertEqual(combined, REDUNDANT_IGNORE_FAIL_EXIT_CODE)


if __name__ == "__main__":
    unittest.main()
