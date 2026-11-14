#!/usr/bin/env python3
"""Unit tests for the pre-apply consolidation safety gate (verify_plan).

Plan-driven and deterministic — no Geni/network access — so the invariants that
guard against these failure modes (keeper-pin profile destroy, a union delete
that still holds a child, an un-synced document force-replace) are tested.
"""
from __future__ import annotations

import unittest

from verso.ru.consolidation import verify_plan as vp


def _rc(rtype, name, actions, before=None, after=None):
    return {
        "address": f"{rtype}.{name}",
        "type": rtype,
        "change": {"actions": actions, "before": before, "after": after},
    }


def _plan(*changes):
    return {"resource_changes": list(changes)}


class CheckPlan(unittest.TestCase):
    def _kinds(self, violations):
        return {v.kind for v in violations}

    def test_clean_plan_has_no_violations(self):
        plan = _plan(
            _rc("geni_profile", "ivan", ["update"], {"id": "p1"}, {"id": "p1"}),
            _rc("geni_union", "ivan_and_anna", ["no-op"], {"id": "u1"}, {"id": "u1"}),
        )
        self.assertEqual(vp.check_plan(plan), [])

    def test_profile_delete_is_an_error(self):
        # The keeper-pin gotcha: a real Geni profile would be deleted.
        plan = _plan(
            _rc("geni_profile", "_1897_ivan_rs_5_5_family_member", ["delete"],
                {"id": "profile-123"}, None),
        )
        violations = vp.check_plan(plan)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, "error")
        self.assertEqual(violations[0].kind, "profile_delete")

    def test_removed_destroy_false_is_not_a_delete(self):
        # removed{destroy=false} shows as "no longer managed" — a no-op action,
        # NOT a delete — and must not trip the gate.
        plan = _plan(
            _rc("geni_profile", "absorbed_stub", ["no-op"], {"id": "p9"}, {"id": "p9"}),
        )
        self.assertEqual(vp.check_plan(plan), [])

    def test_union_delete_with_children_is_an_error(self):
        plan = _plan(
            _rc("geni_union", "fedor_2_1912", ["delete"],
                {"id": "union-913", "children": ["profile-alexey"]}, None),
        )
        violations = vp.check_plan(plan)
        self.assertEqual([v.severity for v in violations], ["error"])
        self.assertEqual(violations[0].kind, "union_delete_with_children")
        self.assertIn("1 child", violations[0].detail)

    def test_childless_union_delete_is_a_warning_not_error(self):
        plan = _plan(
            _rc("geni_union", "husk_d7_1904", ["delete"],
                {"id": "union-1", "children": []}, None),
        )
        violations = vp.check_plan(plan)
        self.assertEqual([v.severity for v in violations], ["warning"])
        self.assertEqual(violations[0].kind, "union_delete")

    def test_document_force_replace_is_an_error(self):
        plan = _plan(
            _rc("geni_document", "birth_of_x", ["delete", "create"],
                {"id": "document-1", "text": "old"}, {"text": "new"}),
        )
        violations = vp.check_plan(plan)
        self.assertEqual([v.severity for v in violations], ["error"])
        self.assertEqual(violations[0].kind, "document_replace")

    def test_document_update_in_place_is_not_flagged(self):
        plan = _plan(
            _rc("geni_document", "birth_of_y", ["update"],
                {"id": "document-2", "text": "t"}, {"id": "document-2", "text": "t"}),
        )
        self.assertEqual(vp.check_plan(plan), [])

    def test_report_and_exit_severity(self):
        clean = vp.check_plan(_plan())
        self.assertIn("OK", vp.format_report(clean))
        bad = vp.check_plan(_plan(
            _rc("geni_profile", "x", ["delete"], {"id": "p1"}, None),
        ))
        self.assertIn("ERROR", vp.format_report(bad))
        self.assertTrue(any(v.severity == "error" for v in bad))


class PlanJsonStaleness(unittest.TestCase):
    def _paths(self, tmp):
        from verso.ru.consolidation.plan import plan_paths
        p = plan_paths(tmp)
        p.tf_dir.mkdir(parents=True, exist_ok=True)
        return p

    def test_stale_when_json_older_than_plan(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = self._paths(tmp)
            p.plan_json.write_text("{}", encoding="utf-8")
            p.plan_bin.write_bytes(b"plan")
            os.utime(p.plan_json, (1000, 1000))   # json older
            os.utime(p.plan_bin, (2000, 2000))    # .plan newer
            self.assertTrue(vp.plan_json_is_stale(p))

    def test_fresh_when_json_newer(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = self._paths(tmp)
            p.plan_json.write_text("{}", encoding="utf-8")
            p.plan_bin.write_bytes(b"plan")
            os.utime(p.plan_bin, (1000, 1000))
            os.utime(p.plan_json, (2000, 2000))   # json newer → fresh
            self.assertFalse(vp.plan_json_is_stale(p))

    def test_not_stale_when_no_plan_bin(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = self._paths(tmp)
            p.plan_json.write_text("{}", encoding="utf-8")
            self.assertFalse(vp.plan_json_is_stale(p))


if __name__ == "__main__":
    unittest.main()


def _pv(*unions):
    """A plan whose post-apply state (planned_values) holds these unions."""
    return {
        "resource_changes": [],
        "planned_values": {"root_module": {"resources": [
            {"address": f"geni_union.{name}", "type": "geni_union",
             "name": name, "values": {"id": name, "children": children}}
            for name, children in unions
        ]}},
    }


class MultiParentChild(unittest.TestCase):
    """A child in two parent unions IS a Geni duplicate_parents conflict.

    Every such conflict was visible in the plan as exactly this shape before it
    ever reached Geni.
    """

    def _kinds(self, violations):
        return {v.kind for v in violations}

    def test_child_in_two_unions_is_an_error(self):
        plan = _pv(
            ("ivan_and_marija_29_1891", ["profile-stefanida"]),
            ("stefanida_and_ivan_d19_1891", ["profile-stefanida"]),
        )
        violations = vp.check_plan(plan)
        self.assertIn("multi_parent_child", self._kinds(violations))
        v = next(x for x in violations if x.kind == "multi_parent_child")
        self.assertEqual(v.severity, "error")
        self.assertIn("profile-stefanida", v.detail + v.address)

    def test_child_in_one_union_is_clean(self):
        self.assertEqual(vp.check_plan(_pv(
            ("ivan_and_marija_29_1891", ["profile-stefanida", "profile-petr"]),
            ("other_union", ["profile-anna"]),
        )), [])

    def test_childless_and_unknown_unions_tolerated(self):
        # `children: null` is a marriage-only union; a missing key is unknown
        # (computed at apply) — neither may crash or false-positive.
        plan = {
            "resource_changes": [],
            "planned_values": {"root_module": {"resources": [
                {"address": "geni_union.a", "type": "geni_union", "name": "a",
                 "values": {"id": "a", "children": None}},
                {"address": "geni_union.b", "type": "geni_union", "name": "b",
                 "values": {"id": "b"}},
            ]}},
        }
        self.assertEqual(vp.check_plan(plan), [])

    def test_unknown_child_ids_are_not_bucketed_together(self):
        # A child profile being CREATED has no id at plan time, so terraform
        # emits `null` inside the union's children list. Several such unions
        # are several DIFFERENT unknown children — bucketing them by the shared
        # `None` key invented a "child in 3 parent unions" error for three
        # unrelated couples each with one new baby. Only a real, known id may
        # be grouped.
        plan = _pv(
            ("efim_and_tatjana_21_1841", [None]),
            ("prohor_and_ekaterina_22_1841", [None]),
            ("prohor_and_agafja_23_1841", [None]),
        )
        self.assertEqual(vp.check_plan(plan), [])

    def test_known_child_still_flagged_alongside_unknown_siblings(self):
        # Dropping unknowns must not blind the check to a real duplicate.
        plan = _pv(
            ("u1", [None, "profile-x"]),
            ("u2", ["profile-x", None]),
        )
        offenders = [v for v in vp.check_plan(plan) if v.kind == "multi_parent_child"]
        self.assertEqual(len(offenders), 1)
        self.assertIn("profile-x", offenders[0].address + offenders[0].detail)

    def test_reports_each_offending_child_once(self):
        plan = _pv(
            ("u1", ["profile-x", "profile-y"]),
            ("u2", ["profile-x"]),
            ("u3", ["profile-x"]),
        )
        offenders = [v for v in vp.check_plan(plan) if v.kind == "multi_parent_child"]
        self.assertEqual(len(offenders), 1)
        self.assertIn("3", offenders[0].detail)
