"""WS1: make_consolidation augments profile_move_list from the
profiles_to_consolidate buckets, so a fold takes effect even when the
detector's --write only appended to the buckets (the sync trap)."""

from __future__ import annotations

from types import SimpleNamespace

from verso.ru.pipeline.translate import make_consolidation


def _gcn(*, buckets, move_list):
    return SimpleNamespace(
        profiles_to_consolidate=buckets,
        profile_move_list=move_list,
        union_move_list_v2={},
        unions_to_consolidate={},
    )


def test_bucket_stub_folds_without_explicit_move_list_entry():
    gcn = _gcn(
        buckets={"canonical_x": {"profile_names": [
            "_1900_01_01_stub_a", "_1901_01_01_stub_b",
        ]}},
        move_list={},  # the trap: buckets populated, move_list empty
    )
    c = make_consolidation(gcn)
    assert c.in_profile_move_list("_1900_01_01_stub_a")
    assert c._resolve_target("_1900_01_01_stub_a") == "canonical_x"
    assert c._resolve_target("_1901_01_01_stub_b") == "canonical_x"


def test_explicit_move_list_entry_wins_over_bucket():
    # setdefault semantics: an explicit move_list target is never overridden by
    # a bucket fold (preserves legacy stripped-key configs' behaviour exactly).
    gcn = _gcn(
        buckets={"canon": {"profile_names": ["_stub"]}},
        move_list={"_stub": "explicit_target"},
    )
    c = make_consolidation(gcn)
    assert c._resolve_target("_stub") == "explicit_target"


def test_non_dict_bucket_entry_ignored():
    gcn = _gcn(buckets={"weird": "not-a-dict"}, move_list={})
    make_consolidation(gcn)  # must not raise


def test_the_core_config_builds_no_consolidation():
    """The translator's Consolidation is the plugin's to build; the core's config
    loader knows no translator."""
    from verso.core.pipeline import config
    assert make_consolidation.__module__ == "verso.ru.pipeline.translate"
    assert not hasattr(config, "make_consolidation")
