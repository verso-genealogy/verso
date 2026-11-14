"""WS4: verify_plan flags two live union resources sharing one Geni id
(Geni fused them when partners merged → apply-time collision)."""

from __future__ import annotations

from verso.ru.consolidation.verify_plan import check_plan


def _union(addr, actions, uid):
    return {
        "type": "geni_union", "address": addr,
        "change": {"actions": actions,
                   "before": {"id": uid, "children": []},
                   "after": {"id": uid}},
    }


def test_flags_two_live_unions_sharing_an_id():
    plan = {"resource_changes": [
        _union("geni_union.egor_jak_1864", ["update"], "union-830"),
        _union("geni_union.egor_nik_and_pelageja", ["no-op"], "union-830"),
    ]}
    v = check_plan(plan)
    shared = [x for x in v if x.kind == "union_shared_id"]
    assert len(shared) == 1
    assert shared[0].severity == "error"
    assert "union-830" in shared[0].detail
    assert "egor_jak_1864" in shared[0].address and "egor_nik_and_pelageja" in shared[0].address


def test_distinct_ids_are_clean():
    plan = {"resource_changes": [
        _union("geni_union.a", ["no-op"], "union-1"),
        _union("geni_union.b", ["update"], "union-2"),
    ]}
    assert [x for x in check_plan(plan) if x.kind == "union_shared_id"] == []


def test_forgotten_duplicate_does_not_count():
    # a removed{destroy=false} dup shows as action "forget" — it won't exist
    # after apply, so it must NOT trip the shared-id check.
    plan = {"resource_changes": [
        _union("geni_union.survivor", ["no-op"], "union-1"),
        _union("geni_union.dup", ["forget"], "union-1"),
    ]}
    assert [x for x in check_plan(plan) if x.kind == "union_shared_id"] == []
