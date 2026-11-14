#!/usr/bin/env python3
"""Unit tests for the union-triage report (P6).

Plan-driven and deterministic — no Geni/network access — replacing the manual
`curl …/api/union-NNN` partner/children lookups used to triage husk vs live
unions during a consolidation.
"""
from __future__ import annotations

import unittest

from verso.ru.consolidation import triage_unions as tu


def _profile(name, pid):
    return {
        "address": f"geni_profile.{name}",
        "type": "geni_profile",
        "change": {"actions": ["update"], "before": {"id": pid}, "after": {"id": pid}},
    }


def _union(name, actions, before=None):
    return {
        "address": f"geni_union.{name}",
        "type": "geni_union",
        "change": {"actions": actions, "before": before, "after": None},
    }


def _plan(*changes):
    return {"resource_changes": list(changes)}


def _union_update(name, before, after, union_id="u1"):
    """A `geni_union` the plan would update in place, with explicit
    before/after partner and children sets."""
    return {
        "address": f"geni_union.{name}",
        "type": "geni_union",
        "change": {
            "actions": ["update"],
            "before": {"id": union_id, **before},
            "after": {"id": union_id, **after},
        },
    }


class CollectUnionTriage(unittest.TestCase):
    def _by_name(self, plan):
        return {t.address.split(".")[-1]: t for t in tu.collect_union_triage(plan)}

    def test_husk_couple_children_classification(self):
        plan = _plan(
            _union("husk_d7", ["delete"], {"id": "u1", "partners": [], "children": []}),
            _union("couple_m1", ["delete"],
                   {"id": "u2", "partners": ["profile-a", "profile-b"], "children": []}),
            _union("family_1912", ["delete"],
                   {"id": "u3", "partners": ["profile-a"], "children": ["profile-c"]}),
        )
        t = self._by_name(plan)
        self.assertEqual(t["husk_d7"].classification, "husk")
        self.assertEqual(t["couple_m1"].classification, "live-couple")
        self.assertEqual(t["family_1912"].classification, "live-children")

    def test_partner_children_ids_resolved_to_resource_names(self):
        plan = _plan(
            _profile("fedor", "profile-a"),
            _profile("alexey_child", "profile-c"),
            _union("fedor_2_1912", ["delete"],
                   {"id": "u3", "partners": ["profile-a"], "children": ["profile-c"]}),
        )
        t = tu.collect_union_triage(plan)[0]
        self.assertEqual(t.partners, ["fedor"])
        self.assertEqual(t.children, ["alexey_child"])

    def test_unresolved_id_kept_as_is(self):
        plan = _plan(_union("x", ["delete"],
                            {"id": "u", "partners": ["profile-zzz"], "children": []}))
        self.assertEqual(tu.collect_union_triage(plan)[0].partners, ["profile-zzz"])

    def test_replace_action_included(self):
        plan = _plan(_union("y", ["delete", "create"],
                            {"id": "u", "partners": ["profile-a"], "children": []}))
        triage = tu.collect_union_triage(plan)
        self.assertEqual(len(triage), 1)
        self.assertEqual(triage[0].action, "replace")

    def test_noop_and_update_unions_ignored(self):
        plan = _plan(
            _union("noop", ["no-op"], {"id": "u"}),
            _union("upd", ["update"], {"id": "u"}),
        )
        self.assertEqual(tu.collect_union_triage(plan), [])

    def test_format_flags_danger_for_children(self):
        plan = _plan(_union("family_1912", ["delete"],
                            {"id": "u3", "partners": ["profile-a"], "children": ["profile-c"]}))
        out = tu.format_triage(tu.collect_union_triage(plan))
        self.assertIn("live-children", out)
        self.assertIn("DANGER", out)

    def test_empty_plan_reports_nothing(self):
        self.assertIn("no geni_union", tu.format_triage(tu.collect_union_triage(_plan())))


class CollectUnionRebinds(unittest.TestCase):
    """A union whose partner AND children both change is bound to a DIFFERENT
    couple's Geni union — a mis-binding, not a duplicate profile. Merging the
    two partners to make the diff go away destroys a real person."""

    def _names(self, plan):
        return [r.address.split(".")[-1] for r in tu.collect_union_rebinds(plan)]

    def test_partner_and_children_both_change_is_flagged(self):
        plan = _plan(_union_update(
            "ilarion_platonovich_and_evdokija_sergeevna",
            {"partners": ["profile-ilarion", "profile-irina"],
             "children": ["profile-feodora"]},
            {"partners": ["profile-ilarion", "profile-evdokija"],
             "children": ["profile-evdokija-jr"]},
        ))
        self.assertEqual(
            self._names(plan), ["ilarion_platonovich_and_evdokija_sergeevna"])

    def test_partner_only_change_is_not_flagged(self):
        """The benign duplicate fold: a partner id remaps to its canonical
        while the union keeps the same children."""
        plan = _plan(_union_update(
            "fold",
            {"partners": ["profile-a", "profile-dup"], "children": ["profile-c"]},
            {"partners": ["profile-a", "profile-canonical"], "children": ["profile-c"]},
        ))
        self.assertEqual(self._names(plan), [])

    def test_children_only_change_is_not_flagged(self):
        """Adding a newly transcribed child to an existing couple."""
        plan = _plan(_union_update(
            "new_child",
            {"partners": ["profile-a", "profile-b"], "children": ["profile-c"]},
            {"partners": ["profile-a", "profile-b"],
             "children": ["profile-c", "profile-d"]},
        ))
        self.assertEqual(self._names(plan), [])

    def test_rebind_reports_both_deltas_resolved_to_names(self):
        plan = _plan(
            _profile("irina_vasilevna_tjulkina", "profile-irina"),
            _profile("evdokija_sergeevna", "profile-evdokija"),
            _union_update(
                "ilarion_and_evdokija",
                {"partners": ["profile-ilarion", "profile-irina"],
                 "children": ["profile-feodora"]},
                {"partners": ["profile-ilarion", "profile-evdokija"],
                 "children": ["profile-evdokija-jr"]},
            ),
        )
        r = tu.collect_union_rebinds(plan)[0]
        self.assertEqual(r.union_id, "u1")
        self.assertEqual(r.partners_removed, ["irina_vasilevna_tjulkina"])
        self.assertEqual(r.partners_added, ["evdokija_sergeevna"])
        self.assertEqual(r.children_removed, ["profile-feodora"])
        self.assertEqual(r.children_added, ["profile-evdokija-jr"])

    def test_format_warns_against_merging_the_partners(self):
        plan = _plan(_union_update(
            "ilarion_and_evdokija",
            {"partners": ["profile-ilarion", "profile-irina"],
             "children": ["profile-feodora"]},
            {"partners": ["profile-ilarion", "profile-evdokija"],
             "children": ["profile-evdokija-jr"]},
        ))
        out = tu.format_rebinds(tu.collect_union_rebinds(plan))
        self.assertIn("MIS-BINDING", out)
        self.assertIn("do NOT merge", out)

    def test_no_rebinds_reports_nothing(self):
        self.assertIn("no union re-binding",
                      tu.format_rebinds(tu.collect_union_rebinds(_plan())))


if __name__ == "__main__":
    unittest.main()
