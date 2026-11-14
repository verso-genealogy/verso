"""CST001/CST002 — consolidation entries that match no produced record.

The check's value rests on two things: collecting exactly the config entries
that are supposed to name a real record (and no others), and asking the
resolver itself which of them matched, rather than re-implementing its
matching rules.
"""
from __future__ import annotations

from types import SimpleNamespace

from verso.ru.consolidation.stale_stubs import (
    Finding, baseline_path, declared_references, findings_for, format_report, load_baseline, suggest, write_baseline)
from verso.ru.targets.geni.translator.consolidation import Consolidation


def _gcn(**kw):
    return SimpleNamespace(
        profiles_to_consolidate=kw.get("profiles_to_consolidate", {}),
        profile_move_list=kw.get("profile_move_list", {}),
        union_move_list_v2=kw.get("union_move_list_v2", {}),
        unions_to_consolidate=kw.get("unions_to_consolidate", {}),
    )


def test_declared_references_collects_stubs_but_never_canonical_targets():
    gcn = _gcn(
        profiles_to_consolidate={
            # synthetic canonical key — a name NO record produces, and that is
            # the normal shape of a multi-stub cluster, not an error.
            "grigorij_ivanovich_chichikov": {
                "profile_names": ["_1834_stub_a", "_1841_stub_b"],
            },
        },
        profile_move_list={"_1850_stub_c": "grigorij_ivanovich_chichikov"},
        union_move_list_v2={"u_stub": "canonical_union"},
    )
    profiles, unions = declared_references(gcn)
    assert set(profiles) == {"_1834_stub_a", "_1841_stub_b", "_1850_stub_c"}
    assert "grigorij_ivanovich_chichikov" not in profiles   # target, not a stub
    assert set(unions) == {"u_stub"}
    assert "canonical_union" not in unions
    assert "profile_names" in profiles["_1834_stub_a"]      # where it came from


def test_declared_references_ignores_non_dict_entries():
    gcn = _gcn(profiles_to_consolidate={"x": "not-a-dict", "y": {"profile_names": ["s"]}})
    profiles, _ = declared_references(gcn)
    assert set(profiles) == {"s"}


# --- hit recording: the resolver reports what it actually matched ------------

def test_hit_recorded_for_a_literal_match_only():
    c = Consolidation(profile_move_list={"live_stub": "target", "dead_stub": "target"})
    assert c.move_to_new_name("live_stub") == "target"
    assert c.hit_profile_keys == {"live_stub"}          # dead_stub matched nothing


def test_alias_match_is_credited_to_the_original_config_key():
    # The config spells it «Илларион»; the translator emits «Иларион». The
    # alias expansion makes the lookup succeed — and the hit must be reported
    # against the key the config actually contains, or the check would call a
    # working entry stale.
    key = "_1840_01_01_illarion_petrovich_mk_births_1_father"
    c = Consolidation(profile_move_list={key: "target"})
    emitted = key.replace("illarion", "ilarion")
    assert emitted in c.profile_move_list                 # alias was expanded
    assert c.move_to_new_name(emitted) == "target"
    assert c.hit_profile_keys == {key}


def test_stripped_last_name_fallback_is_credited_to_the_original_key():
    # Config key carries a surname the emitted res_name lacks; `_resolve_target`
    # falls back to the stripped form.
    key = "_1840_01_01_ivan_petrovich_lodaev_mk_births_1_father"
    c = Consolidation(profile_move_list={key: "target"})
    emitted = "_1840_01_01_ivan_petrovich_mk_births_1_father"
    assert c.move_to_new_name(emitted) == "target"
    assert c.hit_profile_keys == {key}


def test_union_redirect_records_its_hit():
    c = Consolidation(union_move_list_v2={"u_live": "canonical", "u_dead": "canonical"})
    assert c.union_redirect_target("u_live") == "canonical"
    assert c.union_redirect_target("nope") is None
    assert c.hit_union_keys == {"u_live"}


# --- baseline round-trip ----------------------------------------------------

def test_baseline_round_trip_and_comment_stripping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Село").mkdir()
    findings = [Finding("CST001", "b_stub", "profile_move_list"),
                Finding("CST002", "a_union", "union_move_list_v2")]
    p = write_baseline("Село", findings)
    assert p == baseline_path("Село")
    text = p.read_text(encoding="utf-8")
    assert text.startswith("#")                       # explanatory header
    assert load_baseline("Село") == {"b_stub", "a_union"}   # comments dropped


def test_missing_baseline_is_an_empty_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Село").mkdir()
    assert load_baseline("Село") == set()


# --- suggest(): conservative same-record matching ---------------------------

def test_suggest_pairs_the_same_record_under_a_new_spelling():
    corpus = {
        "_1745_00_00_kirill_ostapovich_rs_13_1_family_member",
        "_1745_00_00_denis_ivanovich_rs_1_7_family_member",
    }
    assert suggest("_1745_00_00_kirill_astapovich_rs_13_1_family_member", corpus) == \
        "_1745_00_00_kirill_ostapovich_rs_13_1_family_member"


def test_suggest_declines_when_the_record_tail_differs():
    # Same person, DIFFERENT record number: pointing a fold at the wrong record
    # is worse than not folding, so the matcher must stay silent.
    corpus = {"_1745_00_00_kirill_ostapovich_rs_13_2_family_member"}
    assert suggest("_1745_00_00_kirill_astapovich_rs_13_1_family_member", corpus) is None


def test_suggest_declines_when_two_names_share_the_record_slot():
    corpus = {
        "_1834_04_08_ksenija_ionichna_rs_2_6_family_member",
        "_1834_04_08_matrona_emeljanovna_rs_2_6_family_member",
    }
    assert suggest("_1834_04_08_ksenija_ionovna_rs_2_6_family_member", corpus) is None


def test_suggest_declines_for_a_canonical_shaped_key():
    # No document anchor at all — a leftover canonical name, not a record stub.
    assert suggest("marja_prokopievna", {"marja_prokopievna_sundukina"}) is None


def test_suggest_pairs_a_census_record_that_gained_its_date():
    # Rule 2: same person, same census slot, the bare `_YYYY_00_00_` prefix
    # filled in with the real date. These are LOST FOLDS — the duplicate is
    # live in the tree — so the matcher must find them.
    corpus = {"_1834_02_20_daniil_vasilevich_rs_25_24_family_member"}
    assert suggest("_1834_00_00_daniil_vasilevich_rs_25_24_family_member", corpus) == \
        "_1834_02_20_daniil_vasilevich_rs_25_24_family_member"


def test_suggest_declines_a_date_fill_in_across_years():
    corpus = {"_1835_02_20_daniil_vasilevich_rs_25_24_family_member"}
    assert suggest("_1834_00_00_daniil_vasilevich_rs_25_24_family_member", corpus) is None


def test_suggest_never_varies_name_and_date_at_once():
    # Both parts differ — that is a guess, not a rename.
    corpus = {"_1834_02_20_daniil_vasilievich_rs_25_24_family_member"}
    assert suggest("_1834_00_00_daniil_vasilevich_rs_25_24_family_member", corpus) is None


def test_suggest_pairs_a_union_by_its_record_marker():
    # A union res_name moves when either partner's name does — here the wife
    # gained her married surname. The trailing record marker (`_2_1909`) is
    # what pins the candidate to the same wedding.
    corpus = {
        "andrej_ivanovich_tjufjakin_and_feodosija_efimovna_tjufjakina_2_1909",
        "andrej_ivanovich_tjufjakin_and_feodosija_efimovna_tjufjakina_5_1911",
    }
    assert suggest("andrej_ivanovich_tjufjakin_and_feodosija_efimovna_2_1909", corpus) == \
        "andrej_ivanovich_tjufjakin_and_feodosija_efimovna_tjufjakina_2_1909"


def test_suggest_declines_a_union_with_a_different_record_marker():
    corpus = {"andrej_ivanovich_tjufjakin_and_feodosija_efimovna_tjufjakina_3_1909"}
    assert suggest("andrej_ivanovich_tjufjakin_and_feodosija_efimovna_2_1909", corpus) is None


def test_suggest_declines_a_union_that_differs_by_two_tokens():
    # Two tokens apart is a different couple, not a rename.
    corpus = {"petr_ivanovich_sundukin_and_marfa_petrovna_sundukina_2_1909"}
    assert suggest("andrej_ivanovich_tjufjakin_and_feodosija_efimovna_2_1909", corpus) is None


# --- findings_for / format_report: the half `generate_tf` reuses -------------

def test_findings_for_reports_only_what_the_resolver_missed():
    # Split out of find_stale so a caller holding a finished translation pays
    # nothing for the answer — which is what lets `tf-generate` report a dead
    # fold in the same command that writes the tree it left the duplicate in.
    gcn = _gcn(
        profiles_to_consolidate={"canon": {"profile_names": ["_hit", "_miss"]}},
        union_move_list_v2={"u_hit": "canon_union", "u_miss": "canon_union"},
    )
    cons = Consolidation(
        profile_move_list={"_hit": "canon", "_miss": "canon"},
        union_move_list_v2={"u_hit": "canon_union", "u_miss": "canon_union"},
    )
    cons.in_profile_move_list("_hit")
    cons.union_redirect_target("u_hit")

    findings = findings_for(gcn, cons)
    assert [(f.code, f.ref) for f in findings] == [
        ("CST001", "_miss"), ("CST002", "u_miss")]


def test_findings_for_without_a_consolidation_is_empty():
    assert findings_for(_gcn(profiles_to_consolidate={"c": {"profile_names": ["s"]}}),
                        None) == []


def test_format_report_is_empty_when_nothing_is_new():
    assert format_report("Горюхино", [], baselined=98) == ""


def test_format_report_names_the_entry_and_its_declaring_construct():
    report = format_report(
        "Глуповы Горы",
        [Finding("CST001", "_1875_x_mk_births_15_mother", 'profiles_to_consolidate["a"]')],
        baselined=0,
    )
    assert "_1875_x_mk_births_15_mother" in report
    assert 'profiles_to_consolidate["a"]' in report
    assert "folds nothing" in report
