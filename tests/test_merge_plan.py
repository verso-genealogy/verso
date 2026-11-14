"""verso.ru.consolidation.merge_plan — the Geni-side work of a consolidation apply.

The synthetic plan is a miniature of a consolidation apply, whose merges and
detaches were worked out by hand from the plan JSON: a census head folded into
his canonical (a single-partner union left behind), a couple folded on both
sides (two unions Geni fuses), a renamed record, a dissolved canonical key, a
godparent, and a partner the plan drops.
"""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from verso.ru.consolidation import merge_plan as mp

# Geni ids — the canonicals' and the stubs' (dups).
NESTOR, VERA = "profile-1000008", "profile-1000012"       # canonical couple 1819
AVDEJ, AKSINJA = "profile-1000005", "profile-1000001"     # canonical couple 1827
FEOFAN, PRASKOVJA = "profile-1000004", "profile-1000073"  # Nestor's children, canonical
SILANTIJ, AGAFJA = "profile-1000006", "profile-1000014"    # the second couple, canonical
CHILD_1874, CHILD_1877, CHILD_1879 = "profile-1000013", "profile-1000009", "profile-1000007"
LUKJAN, GURIJ, SPIRIDON = "profile-1000011", "profile-1000029", "profile-1000038"
SON = "profile-1000016"

NESTOR_1858 = "profile-1000048"    # roll of 1858, household 21, member 1 → nestor_1780
EVGRAF_1858 = "profile-1000049"    # roll of 1858, member 2 → avdej_1811
AGRAFENA_1858 = "profile-1000046"  # roll of 1858, member 10, re-read «Аксинья» → aksinja_1811
SILANTIJ_1877 = "profile-1000003"   # dissolved key silantij_jakimovich_1877
OLGA_1877 = "profile-1000002"      # dissolved key olga_kondratievna_1877
GODPARENT = "profile-1000015"      # 1842 godfather → avdej_1811
LUKJAN_GP = "profile-1000010"      # 1872 godfather «Титъ Лукьяновъ», re-read Лукьянъ

MOVE_LIST = {
    "_1819_08_01_nestor_lavrentievich_mk_births_42_father": "nestor_1780",
    "_1858_01_18_nestor_lavrentievich_rs_21_1_family_member": "nestor_1780",
    "_1827_07_01_avdej_nestorovich_mk_marriages_6_groom": "avdej_1811",
    "_1858_01_18_evgraf_nestorovich_rs_21_2_family_member": "avdej_1811",
    "_1842_01_04_avdej_nestorovich_mk_births_1_god_parent_1": "avdej_1811",
    "_1827_07_01_aksinja_savelievna_mk_marriages_6_bride": "aksinja_1811",
    "_1858_01_18_aksinja_savelievna_rs_21_10_family_member": "aksinja_1811",
    "_1872_04_08_lukjan_jakimovich_mk_births_19_god_parent_1": "lukjan_jakimovich",
}


def _profile(name: str, pid: str, actions: tuple[str, ...] = ("no-op",), *,
             gender: str = "male", previous: str | None = None,
             unions: tuple[str, ...] = ()) -> dict[str, Any]:
    before = {"id": pid, "gender": gender, "unions": list(unions)}
    rc: dict[str, Any] = {
        "address": f"geni_profile.{name}", "type": "geni_profile", "name": name,
        "change": {"actions": list(actions), "before": before,
                   "after": None if actions == ("forget",) else dict(before)},
    }
    if previous:
        rc["previous_address"] = f"geni_profile.{previous}"
    return rc


def _union(name: str, uid: str | None, actions: tuple[str, ...], partners: list[str],
           children: list[str], after_partners: list[str | None] | None = None,
           after_children: list[str | None] | None = None, *,
           previous: str | None = None) -> dict[str, Any]:
    before = None if uid is None else {"id": uid, "partners": partners, "children": children}
    leaves = actions in (("forget",), ("delete",))
    after = None if leaves else {
        "id": uid,
        "partners": partners if after_partners is None else after_partners,
        "children": children if after_children is None else after_children,
    }
    rc: dict[str, Any] = {"address": f"geni_union.{name}", "type": "geni_union", "name": name,
                          "change": {"actions": list(actions), "before": before, "after": after}}
    if previous:
        rc["previous_address"] = f"geni_union.{previous}"
    return rc


def z2_plan() -> dict[str, Any]:
    return {"resource_changes": [
        # Canonicals. nestor_1780 is NEW this wave: `moved` from its keeper record, so
        # the keeper's id stands at the canonical address and the keeper's own
        # res_name addresses nothing (the CAUTION in the module docstring).
        _profile("nestor_1780", NESTOR, ("update",),
                 previous="_1819_08_01_nestor_lavrentievich_mk_births_42_father"),
        _profile("vera_1783", VERA, gender="female"),
        _profile("avdej_1811", AVDEJ, ("update",)),
        _profile("aksinja_1811", AKSINJA, gender="female"),
        _profile("feofan_1820", FEOFAN),
        _profile("praskovja_1807", PRASKOVJA, gender="female"),
        _profile("son_1840", SON),
        _profile("silantij_jakimovich_1874", SILANTIJ, ("update",)),
        _profile("agafja_kondratievna", AGAFJA, ("update",), gender="female"),
        _profile("child_1874", CHILD_1874),
        _profile("child_1877", CHILD_1877),
        _profile("child_1879", CHILD_1879, gender="female"),
        _profile("lukjan_jakimovich", LUKJAN),
        _profile("gurij_1840", GURIJ),
        _profile("spiridon_1830", SPIRIDON, gender="female"),
        # Stubs leaving terraform alive.
        _profile("_1858_01_18_nestor_lavrentievich_rs_21_1_family_member", NESTOR_1858, ("forget",)),
        _profile("_1858_01_18_evgraf_nestorovich_rs_21_2_family_member", EVGRAF_1858, ("forget",)),
        _profile("_1858_01_18_agrafena_savelievna_rs_21_10_family_member", AGRAFENA_1858, ("forget",),
                 gender="female"),
        _profile("silantij_jakimovich_1877", SILANTIJ_1877, ("forget",)),
        _profile("olga_kondratievna_1877", OLGA_1877, ("forget",), gender="female"),
        _profile("_1842_01_04_avdej_nestorovich_mk_births_1_god_parent_1", GODPARENT, ("forget",)),
        _profile("_1872_04_08_tit_lukjanovich_kuvshinnikov_mk_births_19_god_parent_1", LUKJAN_GP, ("forget",)),
        # Unions.
        _union("nestor_1780_and_vera_1783", "union-200015", ("update",), [NESTOR, VERA], [],
               after_children=[AVDEJ, FEOFAN, PRASKOVJA]),
        _union("_1858_01_18_nestor_lavrentievich_rs_21_1_family_member", "union-200004", ("forget",),
               [NESTOR_1858], [FEOFAN, EVGRAF_1858, PRASKOVJA]),
        _union("avdej_1811_and_aksinja_1811", "union-200001", ("update",), [AVDEJ, AKSINJA], [],
               after_children=[SON], previous="avdej_and_aksinja_m6_1827"),
        _union("evgraf_nestorovich_rs2_1858", "union-200005", ("forget",),
               [AGRAFENA_1858, EVGRAF_1858], [SON]),
        _union("silantij_jakimovich_1874_and_agafja_kondratievna", "union-200006", ("update",),
               [AGAFJA, SILANTIJ], [CHILD_1874],
               after_children=[CHILD_1874, CHILD_1877, CHILD_1879]),
        _union("silantij_jakimovich_1877_and_olga_kondratievna_1877", "union-200002", ("forget",),
               [OLGA_1877, SILANTIJ_1877], [CHILD_1877, CHILD_1879]),
        _union("spiridon_rs41_1858", "union-200003", ("update",), [GURIJ, SPIRIDON], [],
               after_partners=[SPIRIDON]),
        {"address": "geni_document.ir_1838", "type": "geni_document", "name": "ir_1838",
         "change": {"actions": ["delete", "create"], "before": {"id": "document-1"},
                    "after": {}}},
    ]}


def _by_dup(plan: mp.MergePlan) -> dict[str, mp.Merge]:
    return {m.dup_id: m for m in plan.merges}


def test_each_forgotten_stub_is_a_merge_into_its_canonical() -> None:
    merges = _by_dup(mp.build(z2_plan(), MOVE_LIST))
    assert {d: (m.keep_id, m.canonical) for d, m in merges.items()} == {
        NESTOR_1858: (NESTOR, "nestor_1780"),
        EVGRAF_1858: (AVDEJ, "avdej_1811"),
        AGRAFENA_1858: (AKSINJA, "aksinja_1811"),
        SILANTIJ_1877: (SILANTIJ, "silantij_jakimovich_1874"),
        OLGA_1877: (AGAFJA, "agafja_kondratievna"),
        GODPARENT: (AVDEJ, "avdej_1811"),
        LUKJAN_GP: (LUKJAN, "lukjan_jakimovich"),
    }
    assert merges[NESTOR_1858].command() == f"geni profile merge -yes {NESTOR} {NESTOR_1858}"


def test_keeper_id_is_read_under_the_canonical_address() -> None:
    # The keeper record's res_name is nowhere in the plan: `moved` already put its
    # id at the canonical's address.
    view = mp.read_plan(z2_plan())
    assert "_1819_08_01_nestor_lavrentievich_mk_births_42_father" not in view.profiles
    assert mp._holder_id(view, "nestor_1780") == NESTOR


def test_union_members_merge_before_the_apply_and_godparents_after() -> None:
    merges = _by_dup(mp.build(z2_plan(), MOVE_LIST))
    before = {d for d, m in merges.items() if m.phase == mp.BEFORE}
    after = {d for d, m in merges.items() if m.phase == mp.AFTER}
    assert before == {NESTOR_1858, EVGRAF_1858, AGRAFENA_1858, SILANTIJ_1877, OLGA_1877}
    assert after == {GODPARENT, LUKJAN_GP}
    assert any("collapsed: partner" in u for u in merges[NESTOR_1858].unions)


def test_a_union_geni_lists_but_this_state_does_not_manage_counts_too() -> None:
    plan = {"resource_changes": [
        _profile("tit_1800", "profile-1"),
        _profile("_1842_01_04_tit_mk_births_1_god_parent_1", "profile-2", ("forget",),
                 unions=("union-77",)),
    ]}
    merge = mp.build(plan, {"_1842_01_04_tit_mk_births_1_god_parent_1": "tit_1800"}).merges[0]
    assert merge.phase == mp.BEFORE
    assert merge.unions == ("union-77 (not in this state)",)


def test_old_name_of_a_renamed_record_finds_the_new_name_s_canonical() -> None:
    merges = _by_dup(mp.build(z2_plan(), MOVE_LIST))
    assert merges[AGRAFENA_1858].via == (
        "renamed record → _1858_01_18_aksinja_savelievna_rs_21_10_family_member")
    assert merges[LUKJAN_GP].via.startswith("renamed record")


def test_a_dissolved_key_is_found_through_the_union_its_children_join() -> None:
    merges = _by_dup(mp.build(z2_plan(), MOVE_LIST))
    assert merges[SILANTIJ_1877].via == "unions"
    assert merges[OLGA_1877].keep_id == AGAFJA  # by sex, not by order


def test_record_slot() -> None:
    assert mp.record_slot("_1872_04_08_tit_lukjanovich_kuvshinnikov_mk_births_19_god_parent_1") == (
        "_1872_04_08", "_mk_births_19_god_parent_1")
    assert mp.record_slot("_1838_06_28_zinaida_nikanorovna_ir_19_103_family_member") == (
        "_1838_06_28", "_ir_19_103_family_member")
    assert mp.record_slot("_1917_uljana_ermilovna_ezhevikina_list_110_listed") == (
        "_1917", "_list_110_listed")
    assert mp.record_slot("_1915_10_26_savelij_falaleev_ext_gwar_4_external") == (
        "_1915_10_26", "_ext_gwar_4_external")
    assert mp.record_slot("silantij_jakimovich_1877") is None


def test_single_partner_union_left_behind_is_detached_after_the_apply() -> None:
    plan = mp.build(z2_plan(), MOVE_LIST)
    detaches = {(d.profile_id, d.union_id) for d in plan.detaches}
    # Евграф (a dup) is detached as the canonical he merges into.
    assert {(FEOFAN, "union-200004"), (AVDEJ, "union-200004"), (PRASKOVJA, "union-200004")} <= detaches
    d = next(d for d in plan.detaches if d.profile_id == FEOFAN)
    assert d.command() == f"geni profile detach-union -yes {FEOFAN} union-200004"
    assert "one partner" in d.reason
    assert d.also_in.startswith("union-200015")


def test_a_couple_folded_on_both_sides_fuses_and_needs_no_detach() -> None:
    plan = mp.build(z2_plan(), MOVE_LIST)
    assert not any(d.union_id in ("union-200005", "union-200002") for d in plan.detaches)
    fuses = {(w.union_id, w.partner_union_id) for w in plan.watches if w.expect == "fuses"}
    assert fuses == {("union-200005", "union-200001"), ("union-200002", "union-200006")}
    assert any(w.union_id == "union-200004" and w.expect == "stays" for w in plan.watches)


def test_a_partner_the_plan_drops_is_detached_after_the_apply() -> None:
    plan = mp.build(z2_plan(), MOVE_LIST)
    dropped = [d for d in plan.detaches if d.union_id == "union-200003"]
    assert [d.profile_id for d in dropped] == [GURIJ]
    assert "drops a partner" in dropped[0].reason


def test_a_child_with_no_other_parent_union_is_not_detached() -> None:
    plan = {"resource_changes": [
        _profile("father", "profile-1"),
        _profile("_1842_09_13_father_mk_deaths_38_relative", "profile-2", ("forget",)),
        _profile("infant", "profile-3"),
        _union("infant_and_father_d38_1842", "union-5", ("forget",), ["profile-2"], ["profile-3"]),
    ]}
    out = mp.build(plan, {"_1842_09_13_father_mk_deaths_38_relative": "father"})
    assert out.detaches == []
    assert any("only parent union" in n for n in out.notes)


def test_config_and_unions_disagreeing_is_a_conflict_and_never_run() -> None:
    # The config folds the stub into `tit`, but the union swaps it for `ermolaj`.
    plan = {"resource_changes": [
        _profile("tit", "profile-1"),
        _profile("ermolaj", "profile-2"),
        _profile("_1850_01_01_tit_mk_births_3_father", "profile-9", ("forget",)),
        _union("u", "union-1", ("update",), ["profile-9"], [], after_partners=["profile-2"]),
    ]}
    out = mp.build(plan, {"_1850_01_01_tit_mk_births_3_father": "tit"})
    assert out.merges[0].phase == mp.CONFLICT
    assert "profile-2" in out.merges[0].note
    assert mp.run_merges(out.merges, FakeGeni(), mp.Log(None), pause=0, say=lambda _: None) == []
    # --into is the operator's decision and overrides the cross-check.
    out = mp.build(plan, {"_1850_01_01_tit_mk_births_3_father": "tit"},
                   into={"_1850_01_01_tit_mk_births_3_father": "tit"})
    assert out.merges[0].phase == mp.BEFORE


def test_unresolved_and_already_merged() -> None:
    plan = {"resource_changes": [
        _profile("tit", "profile-1"),
        _profile("_1850_01_01_lost_mk_births_3_child", "profile-8", ("forget",)),
        # A refreshed plan after the merge: state already follows the survivor.
        _profile("_1850_01_01_tit_mk_births_4_father", "profile-1", ("forget",)),
    ]}
    out = _by_dup(mp.build(plan, {"_1850_01_01_tit_mk_births_4_father": "tit"}))
    assert out["profile-8"].phase == mp.UNRESOLVED
    assert "--into" in out["profile-8"].note
    assert out["profile-1"].phase == mp.DONE


def test_into_names_a_canonical_or_a_profile() -> None:
    plan = {"resource_changes": [
        _profile("tit", "profile-1"),
        _profile("_1850_01_01_lost_mk_births_3_child", "profile-8", ("forget",)),
    ]}
    for target in ("tit", "profile-1"):
        merge = mp.build(plan, {}, into={"_1850_01_01_lost_mk_births_3_child": target}).merges[0]
        assert (merge.keep_id, merge.canonical, merge.phase) == ("profile-1", "tit", mp.AFTER)


def test_a_dissolved_key_in_no_union_is_found_in_the_config_history() -> None:
    plan = {"resource_changes": [
        _profile("tit_gp_1817", "profile-1"),
        _profile("tit_gp_1820", "profile-2", ("forget",)),
    ]}
    moves = {"_1820_01_01_tit_mk_births_3_god_parent_1": "tit_gp_1817"}

    def history(key: str) -> tuple[list[str], str] | None:
        return (["_1820_01_01_tit_mk_births_3_god_parent_1"], "abc^") if key == "tit_gp_1820" else None

    merge = mp.build(plan, moves, history=history).merges[0]
    assert (merge.keep_id, merge.canonical, merge.phase) == ("profile-1", "tit_gp_1817", mp.AFTER)
    assert merge.via == "git abc^: the key's records"


def test_profile_names_in_reads_the_config_without_running_it() -> None:
    source = (
        "from nowhere import GeniProfile\n"
        "profiles_to_consolidate = {\n"
        "    'a': {'profile_names': ['x', 'y'], 'preference': GeniProfile(last_name='Z')},\n"
        "}\n"
        "profiles_to_consolidate.update({'b': {'profile_names': ['z']}})\n")
    assert mp.profile_names_in(source, "a") == ["x", "y"]
    assert mp.profile_names_in(source, "b") == ["z"]
    assert mp.profile_names_in(source, "c") is None


def test_declared_in_history_reads_the_revision_before_the_key_was_dropped(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=tmp_path, check=True, capture_output=True)

    config = tmp_path / "village" / "generate_config_names.py"
    config.parent.mkdir()
    git("init", "-q")
    config.write_text("profiles_to_consolidate = {'old_key': {'profile_names': ['r1', 'r2']}}\n")
    git("add", ".")
    git("commit", "-qm", "add")
    config.write_text("profiles_to_consolidate = {'new_key': {'profile_names': ['r1', 'r2']}}\n")
    git("commit", "-qam", "dissolve")
    found = mp.declared_in_history(config, "old_key")
    assert found is not None and found[0] == ["r1", "r2"] and found[1].endswith("^")
    assert mp.declared_in_history(config, "never_there") is None
    # Dropped in the working tree only: HEAD still declares it.
    config.write_text("profiles_to_consolidate = {}\n")
    assert mp.declared_in_history(config, "new_key") == (["r1", "r2"], "HEAD")


def test_report_orders_the_work() -> None:
    text = mp.format_report(mp.build(z2_plan(), MOVE_LIST), village="Глуповы Горы",
                            source="plan.json", plan_json="plan.json")
    sections = [text.index(f"── {n}.") for n in range(1, 7)]
    assert sections == sorted(sections)
    assert text.index(f"merge -yes {NESTOR} {NESTOR_1858}") < sections[1]
    assert sections[3] < text.index(f"merge -yes {AVDEJ} {GODPARENT}") < sections[4]
    assert sections[4] < text.index(f"detach-union -yes {FEOFAN} union-200004") < sections[5]
    assert "1 geni_document(s) replaced" in text
    assert f"geni conflicts show {NESTOR}" in text



def test_the_apply_step_runs_the_gate_in_the_village_module() -> None:
    """Step 3 is typed from the workspace root: each terraform line names the village's module, the plan
    is saved and exported where verify-plan reads it, the gate runs before the apply, and the apply takes
    the plan the gate read — never a bare `terraform apply`."""
    text = mp.format_report(mp.build(z2_plan(), MOVE_LIST), village="Глуповы Горы",
                            source="plan.json", plan_json="plan.json")
    step = text[text.index("── 3."):text.index("── 4.")]
    module = "-chdir='Глуповы Горы/terraform/geni'"
    expected = [f"terraform {module} plan -out=.plan",
                f"terraform {module} show -json .plan > 'Глуповы Горы/_plan.json'",
                "verso verify-plan --village 'Глуповы Горы'",
                f"terraform {module} apply .plan"]
    said = [line for line in step.splitlines() if line.startswith(("terraform", "verso verify-plan"))]
    assert said == expected


# ── Running it ─────────────────────────────────────────────────────────────


def _quiet(_: str) -> None:
    pass


class FakeGeni:
    """Geni as far as merge_plan talks to it. `flip` lists keeps Geni absorbs."""

    def __init__(self, flip: set[str] | None = None,
                 unions: dict[str, dict[str, Any]] | None = None) -> None:
        self.merged_into: dict[str, str] = {}
        self.flip = flip or set()
        self.unions = unions or {}
        self.calls: list[tuple[str, ...]] = []

    def profile(self, profile_id: str) -> dict[str, Any]:
        return {"id": profile_id, "merged_into": self.merged_into.get(profile_id)}

    def union(self, union_id: str) -> dict[str, Any]:
        return self.unions.get(union_id, {"id": union_id})

    def merge(self, keep: str, dup: str) -> str:
        self.calls.append(("merge", keep, dup))
        survivor, absorbed = (dup, keep) if keep in self.flip else (keep, dup)
        self.merged_into[absorbed] = survivor
        return json.dumps({"result": f"{absorbed} merged into {survivor} with conflicts"})

    def detach(self, profile_id: str, union_id: str) -> str:
        self.calls.append(("detach", profile_id, union_id))
        u = self.unions[union_id]
        u["children"] = [c for c in u.get("children") or [] if c != profile_id]
        return json.dumps({"status": "detached"})


def test_run_merges_reports_a_flip_and_follows_it(tmp_path: Path) -> None:
    plan = mp.build(z2_plan(), MOVE_LIST)
    geni = FakeGeni(flip={AVDEJ})
    log = mp.Log(tmp_path / "log.tsv")
    out = mp.run_merges(plan.phase(mp.BEFORE), geni, log, pause=0, say=lambda _: None)
    flip = next(o for o in out if o.status == "flip")
    assert (flip.keep, flip.survivor) == (AVDEJ, EVGRAF_1858)
    assert "FLIP  avdej_1811" in mp.format_flips(out)

    # After the flip the godfather goes to the survivor, not into the husk (a 403).
    after = mp.run_merges(plan.phase(mp.AFTER), geni, log, pause=0, say=lambda _: None)
    assert ("merge", EVGRAF_1858, GODPARENT) in geni.calls
    assert all(o.status == "merged" for o in after)

    # A re-run skips what is done.
    again = mp.run_merges(plan.phase(mp.BEFORE), geni, log, pause=0, say=lambda _: None)
    assert {o.status for o in again} == {"skipped"}

    rows = list(csv.DictReader((tmp_path / "log.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert rows[0].keys() >= {"keep", "dup", "survivor", "status"}
    assert [r["status"] for r in rows].count("flip") == 1


def test_check_unions_says_which_way_geni_fused() -> None:
    plan = mp.build(z2_plan(), MOVE_LIST)
    geni = FakeGeni(unions={
        "union-200001": {"id": "union-200001", "partners": [AVDEJ, AKSINJA], "children": [SON]},
        "union-200005": {"id": "union-200005"},                                   # husk: as planned
        "union-200002": {"id": "union-200002", "partners": [SILANTIJ, AGAFJA]},  # Geni kept it
        "union-200006": {"id": "union-200006"},                                   # ...and emptied ours
        "union-200004": {"id": "union-200004", "partners": [NESTOR], "children": [FEOFAN]},
    })
    lines = mp.check_unions(plan.watches, geni)
    text = "\n".join(lines)
    assert "HUSK  union-200005" in text and "✓ fused into union-200001" in text
    assert "⚠ Geni kept THIS union and emptied union-200006" in text
    assert any(line.startswith("HUSK  union-200006") and "points at a husk" in line for line in lines)
    assert "✓ stays" in text


def test_run_detaches_follows_merges_and_skips_non_members() -> None:
    geni = FakeGeni(unions={"union-200004": {"id": "union-200004", "children": [EVGRAF_1858, FEOFAN]}})
    geni.merged_into[AVDEJ] = EVGRAF_1858   # the flip of the before-merges
    detaches = [mp.Detach(AVDEJ, "union-200004", "geni_union.x", "why"),
                mp.Detach(PRASKOVJA, "union-200004", "geni_union.x", "why")]
    said: list[str] = []
    failures = mp.run_detaches(detaches, geni, mp.Log(None), pause=0, say=said.append)
    assert failures == 0
    assert geni.calls == [("detach", EVGRAF_1858, "union-200004")]
    assert said[-1] == f"union-200004: still holds {FEOFAN}"
    mp.run_detaches([mp.Detach(FEOFAN, "union-200004", "geni_union.x", "why")], geni,
                    mp.Log(None), pause=0, say=said.append)
    assert said[-1] == "union-200004: now an empty husk — terraform no longer manages it"


def test_main_reads_a_village(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    village = tmp_path / "Село"
    village.mkdir()
    (village / "generate_config_names.py").write_text(
        "profile_move_list = {}\n"
        f"profiles_to_consolidate = {{k: {{'profile_names': []}} for k in {sorted(set(MOVE_LIST.values()))!r}}}\n"
        + "".join(f"profiles_to_consolidate[{v!r}]['profile_names'].append({k!r})\n"
                  for k, v in MOVE_LIST.items()),
        encoding="utf-8")
    (village / "_plan.json").write_text(json.dumps(z2_plan()), encoding="utf-8")
    assert mp.main(["--village", str(village)]) == 0
    out = capsys.readouterr().out
    assert f"geni profile merge -yes {NESTOR} {NESTOR_1858}" in out
    assert mp.main(["--village", str(village), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["merges"]) == 7 and len(data["detaches"]) == 4


# ── A larger synthetic plan ────────────────────────────────────────────────


def test_z2_reproduces_the_merges_worked_out_by_hand() -> None:
    """tests/data/merge_plan_z2.json is a synthetic fast plan cut to what matters.
    The merges are the ones worked out by hand; the detaches are the ones run
    after the apply (Прасковья, Авдей, Феофан; Нифонт; Гурий from Спиридон's union)."""
    data = json.loads((Path(__file__).parent / "data" / "merge_plan_z2.json").read_text("utf-8"))
    plan = mp.build(data["plan"], data["move_list"])
    pairs = {ph: {(m.keep_id, m.dup_id) for m in plan.phase(ph)} for ph in (mp.BEFORE, mp.AFTER)}
    assert pairs[mp.BEFORE] == {(f"profile-{k}", f"profile-{d}") for k, d in (
        ("1000050", "1000044"), ("1000077", "1000035"),
        ("1000074", "1000072"), ("1000056", "1000064"),
        ("1000081", "1000037"), ("1000054", "1000017"),
        ("1000043", "1000028"), ("1000051", "1000059"))}
    assert pairs[mp.AFTER] == {(f"profile-{k}", f"profile-{d}") for k, d in (
        ("1000077", "1000062"), ("1000030", "1000019"),
        ("1000045", "1000024"), ("1000047", "1000075"))}
    assert {(d.profile_id, d.union_id) for d in plan.detaches} == {
        ("profile-1000079", "union-200033"), ("profile-1000077", "union-200033"),
        ("profile-1000060", "union-200033"), ("profile-1000041", "union-200034"),
        ("profile-1000070", "union-200018")}
    # Geni kept 200013 and 200010, as the moved blocks expect.
    assert {(w.union_id, w.partner_union_id) for w in plan.watches if w.expect == "fuses"} == {
        ("union-200023", "union-200013"), ("union-200016", "union-200010")}
    assert plan.documents_replaced == 26


def test_z2_flips_carry_into_the_after_apply_work() -> None:
    """Geni flipped two of the eight: Авдей kept 1000035 (the 1858 stub) and
    Силантий 1000028. The godfather's merge and Авдей's detach then go to
    the survivors — the 403 on a husk the batch path warns about, avoided."""
    data = json.loads((Path(__file__).parent / "data" / "merge_plan_z2.json").read_text("utf-8"))
    plan = mp.build(data["plan"], data["move_list"])
    unions = {"union-200033": {"children": ["profile-1000060", "profile-1000035",
                                               "profile-1000079"]}}
    geni = FakeGeni(flip={"profile-1000077", "profile-1000043"}, unions=unions)
    before = mp.run_merges(plan.phase(mp.BEFORE), geni, mp.Log(None), pause=0, say=_quiet)
    assert sorted((o.keep, o.survivor) for o in before if o.status == "flip") == [
        ("profile-1000043", "profile-1000028"),
        ("profile-1000077", "profile-1000035")]
    mp.run_merges(plan.phase(mp.AFTER), geni, mp.Log(None), pause=0, say=_quiet)
    assert ("merge", "profile-1000035", "profile-1000062") in geni.calls
    mp.run_detaches([d for d in plan.detaches if d.union_id == "union-200033"], geni,
                    mp.Log(None), pause=0, say=_quiet)
    assert ("detach", "profile-1000035", "union-200033") in geni.calls
    assert unions["union-200033"]["children"] == []
