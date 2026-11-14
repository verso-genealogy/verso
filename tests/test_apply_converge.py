"""Tests for the two classifiers that make `apply_converge` terminate.

The loop itself is not unit-tested (it shells out to terraform against live Geni);
what is testable — and what actually decides whether the loop halts, retries or
mutates — is the pair of classifiers.
"""

import unittest

from verso.ru.consolidation.apply_converge import (
    AUTO_FIXABLE, classify_apply_output, gate_decision)

# Every error category verify_plan can emit. If a new one is added there and NOT
# added here, test_every_known_category_is_classified fails — which is the point:
# an unclassified category must never silently fall through to "keep applying".
ALL_KINDS = [
    "document_replace",
    "profile_delete",
    "union_delete_with_children",
    "union_shared_id",
    "multi_parent_child",
]


def violation(kind, severity="error"):
    return {"severity": severity, "kind": kind, "address": "x", "detail": "y"}


class TestGateDecision(unittest.TestCase):

    def test_clean_plan_proceeds(self):
        self.assertEqual(gate_decision([])[0], "ok")

    def test_document_replace_is_the_only_auto_fix(self):
        decision, kinds = gate_decision([violation("document_replace")] * 3)
        self.assertEqual(decision, "sync")
        self.assertEqual(kinds, {"document_replace"})

    def test_destructive_categories_halt(self):
        for kind in ALL_KINDS:
            if kind in AUTO_FIXABLE:
                continue
            with self.subTest(kind=kind):
                self.assertEqual(gate_decision([violation(kind)])[0], "halt")

    def test_mixed_halts_even_though_most_are_auto_fixable(self):
        # 664 document replaces + a single profile delete must NOT be auto-synced
        # and applied: the delete would destroy a live profile.
        mixed = [violation("document_replace")] * 664 + [violation("profile_delete")]
        self.assertEqual(gate_decision(mixed)[0], "halt")

    def test_warnings_do_not_block(self):
        self.assertEqual(gate_decision([violation("whatever", "warning")])[0], "ok")

    def test_every_known_category_is_classified(self):
        for kind in ALL_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(gate_decision([violation(kind)])[0], {"sync", "halt"})


class TestClassifyApplyOutput(unittest.TestCase):

    def test_clean_output(self):
        self.assertEqual(classify_apply_output("Apply complete! 11 changed."), (0, []))

    def test_transient_classes(self):
        # Verbatim provider lines observed 2026-08-02.
        out = (
            "│ #1: received 429 status, retry in 10 seconds\n"
            "│ #2: incapsula blocked request\n"
            "│ #1: received 500 status, retry in 1 seconds\n"
        )
        transient, permanent = classify_apply_output(out)
        self.assertEqual(transient, 3)
        self.assertEqual(permanent, [])

    def test_access_denied_is_permanent(self):
        transient, permanent = classify_apply_output("│ #1: access denied\n")
        self.assertEqual(transient, 0)
        self.assertEqual(len(permanent), 1)

    def test_permanent_wins_over_transient_on_the_same_line(self):
        # A line naming both must not be dismissed as retryable.
        _t, permanent = classify_apply_output("received 429 status then access denied")
        self.assertEqual(len(permanent), 1)

    def test_permanent_messages_are_deduplicated(self):
        out = "│ #1: access denied\n" * 27
        _t, permanent = classify_apply_output(out)
        self.assertEqual(len(permanent), 1)

    def test_mixed_run_reports_both(self):
        out = (
            "geni_profile.a: Modifications complete after 11s\n"
            "│ #1: received 429 status, retry in 10 seconds\n"
            "│ #1: access denied\n"
        )
        transient, permanent = classify_apply_output(out)
        self.assertEqual(transient, 1)
        self.assertEqual(len(permanent), 1)

    def test_case_insensitive(self):
        _t, permanent = classify_apply_output("│ #1: Access Denied")
        self.assertEqual(len(permanent), 1)


if __name__ == "__main__":
    unittest.main()
