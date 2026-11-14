"""Tests for Geni tree-conflict triage and merge-wiring.

A tree conflict is a profile that, after a merge, ended up with duplicate close
relatives (two parent unions, or two spouses). `tree_conflicts` lists them,
drops stale entries, maps each duplicate relative's guid back to its Terraform
res_name / canonical key, and emits the vetted merge + config-wiring per fold.
These tests cover the pure core (no `geni`/terraform I/O).
"""
import unittest
from collections.abc import Callable
from typing import Any

from verso.ru.gender import Gender
from verso.ru.naming import names_registry
from verso.ru.naming.layer_files import base
from verso.ru.naming.lexicon import FormsEntry, Layer, Lexicon, NameEntry
from verso.ru.consolidation.tree_conflicts import (
    TreeConflictsUnavailable, fetch_list, gather, AUTO, DONE, PLACEHOLDER, REVIEW, UNMAPPED, Candidate, ConflictReport, build_new_entries, build_reports, filter_adjudicated, filter_mapped, format_report, is_placeholder, is_stale, name_mismatch, parse_adjudicated, parse_show, parse_subtree, plan_folds)


# A `duplicate_parents` show payload: father A (bigger subtree) vs father B,
# mother C vs mother D (bigger).
DUP_PARENTS = {
    "focus": {"profile_id": "600A", "short_id": "1", "name": "Акилина Брюхина"},
    "conflict_types": ["duplicate_parents"],
    "has_conflict": True,
    "duplicate_candidates": [
        {"role": "father", "profiles": [
            {"profile_id": "600FA", "short_id": "fa", "name": "Григорий Иванович",
             "subtree_size": "+211"},
            {"profile_id": "600FB", "short_id": "fb", "name": "Григорий Иванович",
             "subtree_size": "+112"},
        ]},
        {"role": "mother", "profiles": [
            {"profile_id": "600MC", "short_id": "mc", "name": "Мария Климентовна"},
            {"profile_id": "600MD", "short_id": "md", "name": "Мария Климентовна",
             "subtree_size": "+31"},
        ]},
    ],
}

# The same shape, but the candidates are plainly DIFFERENT people — the father
# pair disagrees on patronymic, the mother pair on given name — the shape a
# remarriage leaves (successive wives).
DUP_PARENTS_MISMATCH = {
    "focus": {"profile_id": "600A", "short_id": "1", "name": "Акилина Брюхина"},
    "conflict_types": ["duplicate_parents"],
    "has_conflict": True,
    "duplicate_candidates": [
        {"role": "father", "profiles": [
            {"profile_id": "600FA", "short_id": "fa", "name": "Григорий Иванович",
             "subtree_size": "+211"},
            {"profile_id": "600FB", "short_id": "fb", "name": "Григорий Тимофеевич",
             "subtree_size": "+112"},
        ]},
        {"role": "mother", "profiles": [
            {"profile_id": "600MC", "short_id": "mc", "name": "Мария Климентовна"},
            {"profile_id": "600MD", "short_id": "md", "name": "Феодосия",
             "subtree_size": "+31"},
        ]},
    ],
}

DUP_SPOUSE = {
    "focus": {"profile_id": "600S", "short_id": "9", "name": "Михаил Кувшинников"},
    "conflict_types": ["duplicate_spouse"],
    "has_conflict": True,
    "duplicate_candidates": [
        {"role": "spouse", "profiles": [
            {"profile_id": "600W1", "short_id": "w1", "name": "Мавра", "subtree_size": "+5"},
            {"profile_id": "600W2", "short_id": "w2", "name": "Мавра", "subtree_size": "+2"},
        ]},
    ],
}

STALE = {"focus": {"profile_id": "600Z", "name": "Иван Феодулов"},
         "conflict_types": [], "has_conflict": False, "duplicate_candidates": []}


class TestParseSubtree(unittest.TestCase):
    def test_plus_prefixed(self):
        self.assertEqual(parse_subtree("+112"), 112)
        self.assertEqual(parse_subtree("+0"), 0)

    def test_missing_or_garbage(self):
        self.assertEqual(parse_subtree(None), 0)
        self.assertEqual(parse_subtree(""), 0)
        self.assertEqual(parse_subtree("n/a"), 0)


class TestIsStale(unittest.TestCase):
    def test_has_conflict_false_is_stale(self):
        self.assertTrue(is_stale(STALE))
        self.assertTrue(is_stale({}))

    def test_has_conflict_true_is_actionable(self):
        self.assertFalse(is_stale(DUP_PARENTS))
        self.assertFalse(is_stale(DUP_SPOUSE))


class TestParseShow(unittest.TestCase):
    def test_survivor_is_larger_subtree(self):
        pairs = parse_show(DUP_PARENTS)
        self.assertEqual([p.role for p in pairs], ["father", "mother"])
        # Assert on guids, not names: a genuine duplicate pair shares a name, so
        # only the guid identifies which candidate won.
        father = pairs[0]
        self.assertEqual(father.survivor.guid, "600FA")  # +211 > +112
        self.assertEqual([a.guid for a in father.absorbed], ["600FB"])
        mother = pairs[1]
        # missing subtree_size (→0) loses to +31
        self.assertEqual(mother.survivor.guid, "600MD")
        self.assertEqual([a.guid for a in mother.absorbed], ["600MC"])

    def test_duplicate_spouse_shape(self):
        pairs = parse_show(DUP_SPOUSE)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].role, "spouse")
        self.assertEqual(pairs[0].survivor.guid, "600W1")  # +5 > +2

    def test_singleton_role_skipped(self):
        show = {"has_conflict": True, "duplicate_candidates": [
            {"role": "father", "profiles": [{"profile_id": "x", "name": "n"}]}]}
        self.assertEqual(parse_show(show), [])

    def test_same_guid_repeated_is_not_a_duplicate(self):
        # Geni lists one father in both parent unions → same guid twice. That is
        # a union duplicate, not a profile duplicate: no self-merge is emitted.
        show = {"has_conflict": True, "duplicate_candidates": [
            {"role": "father", "profiles": [
                {"profile_id": "600FA", "name": "Фёдор", "subtree_size": "+3"},
                {"profile_id": "600FA", "name": "Фёдор", "subtree_size": "+3"},
            ]}]}
        self.assertEqual(parse_show(show), [])

    def test_dedup_keeps_largest_subtree_per_guid(self):
        show = {"has_conflict": True, "duplicate_candidates": [
            {"role": "father", "profiles": [
                {"profile_id": "600FA", "name": "A", "subtree_size": "+3"},
                {"profile_id": "600FA", "name": "A", "subtree_size": "+9"},
                {"profile_id": "600FB", "name": "B", "subtree_size": "+1"},
            ]}]}
        pairs = parse_show(show)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].survivor.guid, "600FA")
        self.assertEqual(pairs[0].survivor.subtree, 9)
        self.assertEqual([a.guid for a in pairs[0].absorbed], ["600FB"])


# state: guid → res_name. FA/FB are plain stubs; MD is a canonical key; MC is
# already folded into MD.
GUID_TO_RES = {
    "600FA": "father_a_rec", "600FB": "father_b_rec",
    "600MD": "mother_d_canon", "600MC": "mother_c_rec",
}
# 600W2 intentionally absent (another manager's profile → UNMAPPED).
GUID_TO_RES_SPOUSE = {"600W1": "wife_1_rec"}

CONFIG_KEYS = {"mother_d_canon"}
FOLDED_INDEX = {"mother_c_rec": "mother_d_canon"}  # MC already folds into MD


class TestPlanFolds(unittest.TestCase):
    def test_auto_when_absorbed_is_plain_stub(self):
        folds = plan_folds(parse_show(DUP_PARENTS)[:1], GUID_TO_RES,
                           set(), {})
        self.assertEqual(len(folds), 1)
        f = folds[0]
        self.assertEqual(f.tier, AUTO)
        self.assertEqual(f.survivor_res, "father_a_rec")
        self.assertEqual(f.absorbed_res, "father_b_rec")
        self.assertEqual(f.survivor_canonical, "father_a_rec")  # standalone = own canon
        self.assertIn("profile-g600FA", f.merge_cmd)
        self.assertIn("profile-g600FB", f.merge_cmd)

    def test_done_when_already_folded_onto_survivor(self):
        # mother role: survivor MD (canonical), absorbed MC already folds into MD.
        folds = plan_folds(parse_show(DUP_PARENTS)[1:], GUID_TO_RES,
                           CONFIG_KEYS, FOLDED_INDEX)
        self.assertEqual(folds[0].tier, DONE)
        self.assertEqual(folds[0].survivor_canonical, "mother_d_canon")

    def test_review_when_absorbed_is_a_canonical(self):
        # survivor FA plain, absorbed FB flagged as a canonical key.
        folds = plan_folds(parse_show(DUP_PARENTS)[:1], GUID_TO_RES,
                           {"father_b_rec"}, {})
        self.assertEqual(folds[0].tier, REVIEW)

    def test_review_when_folded_into_a_different_canonical(self):
        folds = plan_folds(parse_show(DUP_PARENTS)[:1], GUID_TO_RES,
                           set(), {"father_b_rec": "some_other_canon"})
        self.assertEqual(folds[0].tier, REVIEW)

    def test_unmapped_when_a_side_missing_from_state(self):
        folds = plan_folds(parse_show(DUP_SPOUSE), GUID_TO_RES_SPOUSE, set(), {})
        self.assertEqual(folds[0].tier, UNMAPPED)
        self.assertIsNone(folds[0].absorbed_res)


class TestBuildNewEntries(unittest.TestCase):
    def test_only_auto_folds_are_written(self):
        reports = build_reports([DUP_PARENTS], GUID_TO_RES, CONFIG_KEYS, FOLDED_INDEX)
        entries = build_new_entries(reports)
        # father fold is AUTO → append father_b_rec to father_a_rec; mother is DONE.
        self.assertEqual(set(entries), {"father_a_rec"})
        self.assertEqual(entries["father_a_rec"]["profile_names"], ["father_b_rec"])
        self.assertTrue(entries["father_a_rec"]["generate_moved_block"])

    def test_canonical_key_never_in_its_own_profile_names(self):
        reports = build_reports([DUP_PARENTS], GUID_TO_RES, CONFIG_KEYS, FOLDED_INDEX)
        entries = build_new_entries(reports)
        for canon, entry in entries.items():
            self.assertNotIn(canon, entry["profile_names"])

    def test_no_entries_when_all_review_or_unmapped(self):
        reports = build_reports([DUP_SPOUSE], GUID_TO_RES_SPOUSE, set(), {})
        self.assertEqual(build_new_entries(reports), {})


class TestBuildReports(unittest.TestCase):
    def test_reports_sorted_by_name_and_carry_types(self):
        reports = build_reports([DUP_SPOUSE, DUP_PARENTS], GUID_TO_RES, set(), {})
        self.assertEqual([r.name for r in reports],
                         ["Акилина Брюхина", "Михаил Кувшинников"])
        self.assertEqual(reports[0].conflict_types, ("duplicate_parents",))


class TestFormatReport(unittest.TestCase):
    def _reports(self):
        return build_reports([DUP_PARENTS], GUID_TO_RES, set(), {})

    def test_report_shows_counts_and_merge_and_wiring(self):
        out = format_report(self._reports(), stale=3)
        self.assertIn("1 actionable", out)
        self.assertIn("3 stale", out)
        self.assertIn("geni profile merge profile-g600FA profile-g600FB", out)
        # AUTO wiring line names the res_name and the canonical.
        self.assertIn('append "father_b_rec"', out)
        self.assertIn('"father_a_rec".profile_names', out)

    def test_empty_when_no_actionable(self):
        out = format_report([ConflictReport(guid="z", short_id="", name="X",
                                            conflict_types=())], stale=1)
        self.assertIn("0 actionable", out)


# A duplicate_parents conflict on a child where the father repeats (same guid →
# not a duplicate) and the mother has a real profile + a synthetic empty slot.
DUP_PARENTS_PH = {
    "focus": {"profile_id": "600A", "short_id": "402711896", "name": "Александра Индюшева"},
    "conflict_types": ["duplicate_parents"],
    "has_conflict": True,
    "duplicate_candidates": [
        {"role": "father", "profiles": [
            {"profile_id": "600FA", "short_id": "fa", "name": "Василий Индюшев", "subtree_size": "+1"},
            {"profile_id": "600FA", "short_id": "fa", "name": "Василий Индюшев", "subtree_size": "+1"},
        ]},
        {"role": "mother", "profiles": [
            {"profile_id": "-129053048f", "name": "Mother of Александра Индюшева"},
            {"profile_id": "600MOM", "short_id": "mom", "name": "Елена Индюшева"},
        ]},
    ],
}


class TestPlaceholder(unittest.TestCase):
    def test_is_placeholder_by_guid_and_name(self):
        self.assertTrue(is_placeholder(Candidate("-129053048f", "", "X", 0)))
        self.assertTrue(is_placeholder(Candidate("-42", "", "X", 0)))
        self.assertTrue(is_placeholder(Candidate("600", "", "Mother of Y", 0)))
        self.assertTrue(is_placeholder(Candidate("600", "", "Father of Y", 0)))

    def test_real_profile_is_not_placeholder(self):
        self.assertFalse(is_placeholder(Candidate("6000000999950891712", "m", "Елена", 3)))

    def test_survivor_is_never_the_placeholder(self):
        pairs = parse_show(DUP_PARENTS_PH)
        # father role deduped away (same guid twice); only mother remains.
        self.assertEqual([p.role for p in pairs], ["mother"])
        self.assertEqual(pairs[0].survivor.name, "Елена Индюшева")
        self.assertTrue(is_placeholder(pairs[0].absorbed[0]))

    def test_plan_folds_tiers_placeholder(self):
        folds = plan_folds(parse_show(DUP_PARENTS_PH), {"600MOM": "elena_indjusheva"},
                           set(), {})
        self.assertEqual([f.tier for f in folds], [PLACEHOLDER])
        self.assertIsNotNone(folds[0].placeholder)

    def test_report_recommends_resolve_not_merge(self):
        reports = build_reports([DUP_PARENTS_PH], {"600MOM": "elena_indjusheva"}, set(), {})
        out = format_report(reports, stale=0)
        # detach via `tree-conflicts resolve`, keyed on the focus guid
        self.assertIn("tree-conflicts resolve profile-g600A", out)
        # never suggest merging the synthetic slot
        self.assertNotIn("profile merge profile-g-129053048f", out)
        self.assertIn("PLACEHOLDER", out)

    def test_placeholder_never_written(self):
        reports = build_reports([DUP_PARENTS_PH], {"600MOM": "elena_indjusheva"}, set(), {})
        self.assertEqual(build_new_entries(reports), {})


class TestFilterMapped(unittest.TestCase):
    def test_drops_unmapped_folds_and_empty_conflicts(self):
        # DUP_PARENTS with no guids mapped → all UNMAPPED → dropped entirely.
        reports = build_reports([DUP_PARENTS], {}, set(), {})
        self.assertEqual(filter_mapped(reports), [])

    def test_keeps_conflicts_with_a_mapped_fold(self):
        reports = build_reports([DUP_PARENTS_PH], {"600MOM": "elena_indjusheva"}, set(), {})
        kept = filter_mapped(reports)
        self.assertEqual(len(kept), 1)
        self.assertTrue(all(f.tier != UNMAPPED for f in kept[0].folds))


# A two-real-parent conflict: focus child with two parent
# unions, each father+mother, carrying life years and web ids.
MANUAL_SHOW = {
    "focus": {"profile_id": "600CH", "name": "Пётр Семёнович", "birth_year": 1824,
              "death_year": 1850},
    "conflict_types": ["duplicate_parents"],
    "has_conflict": True,
    "parent_unions": [
        {"web_union_id": "600U1", "parents": [
            {"profile_id": "600F", "name": "Семён", "birth_year": 1806, "death_year": 1853},
            {"profile_id": "600M1", "name": "Ульяна", "birth_year": 1801, "death_year": 1840},
        ]},
        {"web_union_id": "600U2", "parents": [
            {"profile_id": "600F", "name": "Семён", "birth_year": 1806, "death_year": 1853},
            {"profile_id": "600M2", "name": "Дарья", "birth_year": 1804, "death_year": 1853},
        ]},
    ],
}
MANUAL_G2R = {"600F": "semen", "600M1": "uljana_daniilovna",
              "600M2": "_1853_10_01_darja_leontievna_rs_65_5_family_member"}


class TestParseManual(unittest.TestCase):
    def test_lays_out_focus_and_unions_with_res_and_years(self):
        from verso.ru.consolidation.tree_conflicts import parse_manual
        c = parse_manual(MANUAL_SHOW, MANUAL_G2R)
        self.assertEqual((c.name, c.guid, c.birth_year, c.death_year),
                         ("Пётр Семёнович", "600CH", "1824", "1850"))
        self.assertEqual(len(c.unions), 2)
        webs = {u.web_id for u in c.unions}
        self.assertEqual(webs, {"600U1", "600U2"})
        # mothers resolved to res_names + death years (the assignment signal)
        m1 = c.unions[0].parents[1]
        self.assertEqual((m1.name, m1.res_name, m1.death_year),
                         ("Ульяна", "uljana_daniilovna", "1840"))

    def test_is_manual_true_for_two_real_parent(self):
        from verso.ru.consolidation.tree_conflicts import is_manual, parse_manual
        self.assertTrue(is_manual(parse_manual(MANUAL_SHOW, MANUAL_G2R)))

    def test_is_manual_false_when_a_placeholder_parent(self):
        from verso.ru.consolidation.tree_conflicts import is_manual, parse_manual
        ph = {
            "focus": {"profile_id": "x", "name": "X"},
            "conflict_types": ["duplicate_parents"], "has_conflict": True,
            "parent_unions": [
                {"web_union_id": "u1", "parents": [
                    {"profile_id": "600F", "name": "F"},
                    {"profile_id": "-129f", "name": "Mother of X"}]},
                {"web_union_id": "u2", "parents": [
                    {"profile_id": "600F", "name": "F"},
                    {"profile_id": "600M", "name": "M"}]},
            ],
        }
        self.assertFalse(is_manual(parse_manual(ph, {"600F": "f", "600M": "m"})))

    def test_is_manual_false_when_nothing_mapped(self):
        from verso.ru.consolidation.tree_conflicts import is_manual, parse_manual
        self.assertFalse(is_manual(parse_manual(MANUAL_SHOW, {})))


class TestFormatManual(unittest.TestCase):
    def test_shows_years_res_and_detach_per_union(self):
        from verso.ru.consolidation.tree_conflicts import format_manual, parse_manual
        out = format_manual([parse_manual(MANUAL_SHOW, MANUAL_G2R)], stale=2)
        self.assertIn("1 (", out)                      # one manual conflict
        self.assertIn("2 stale skipped", out)
        self.assertIn("Ульяна (b1801 d1840) [uljana_daniilovna]", out)
        # a ready detach command for each union, keyed on the focus guid
        self.assertIn("detach-union -yes 600CH 600U1", out)
        self.assertIn("detach-union -yes 600CH 600U2", out)

    def test_empty_when_no_manual(self):
        from verso.ru.consolidation.tree_conflicts import format_manual, parse_manual
        out = format_manual([parse_manual(MANUAL_SHOW, {})], stale=0)
        self.assertIn("0 (", out)


if __name__ == "__main__":
    unittest.main()


class MergeGuard(unittest.TestCase):
    """`--write` must refuse to wire a fold whose Geni merge has not happened.

    Folding two profiles that still carry distinct live guids plans a DESTROY of
    one of them. The module docstring already required
    "run --write AFTER the merge", but nothing enforced it: `reports` holds only
    LIVE conflicts, and a live conflict means the pair is still unmerged — so
    --write could structurally only ever write pre-merge folds.
    """

    def test_absorbed_still_live_and_distinct_is_unmerged(self):
        from verso.ru.consolidation.tree_conflicts import merge_state
        fetched = {"guid": "6000000999066365665", "id": "profile-2"}
        self.assertEqual(
            merge_state(fetched, survivor_guid="6000000999692871460"), "distinct")

    def test_absorbed_missing_means_merged_away(self):
        from verso.ru.consolidation.tree_conflicts import merge_state
        # `geni profile get` 404s once the profile has been merged away.
        self.assertEqual(
            merge_state(None, survivor_guid="6000000999692871460"), "merged")
        self.assertEqual(
            merge_state({}, survivor_guid="6000000999692871460"), "merged")

    def test_absorbed_now_resolving_to_survivor_is_merged(self):
        from verso.ru.consolidation.tree_conflicts import merge_state
        fetched = {"guid": "6000000999692871460", "id": "profile-1"}
        self.assertEqual(
            merge_state(fetched, survivor_guid="6000000999692871460"), "merged")

    def test_excluded_absorbed_res_is_not_written(self):
        reports = build_reports([DUP_PARENTS], GUID_TO_RES, CONFIG_KEYS, FOLDED_INDEX)
        entries_all = build_new_entries(reports)
        self.assertTrue(entries_all, "fixture should yield an AUTO fold")
        absorbed = next(iter(entries_all.values()))["profile_names"][0]
        self.assertEqual(
            build_new_entries(reports, exclude_absorbed={absorbed}), {})


# ── Name-agreement guard ────────────────────────────────────────────────────
# The tier says only whether WIRING is unambiguous; it never asked whether the
# two profiles are the same person. That let a fold pairing two plainly
# different women (two successive wives, a remarriage) land in AUTO, whose
# report line reads as "safe to merge".
# `name_mismatch` is the identity check, deliberately orthogonal to the tier.

M = Gender.MALE


class TestNameMismatch(unittest.TestCase):
    def test_different_given_names_are_flagged(self):
        self.assertIsNotNone(name_mismatch("Дарья Петровна", "Анна Ивановна"))
        self.assertIsNotNone(name_mismatch("Агафья Илларионовна", "Ксения"))

    def test_different_patronymics_are_flagged(self):
        self.assertIsNotNone(
            name_mismatch("Евдокия Сергеевна Тюлькина", "Ирина Васильевна Тюлкина"))

    def test_orthographic_variants_are_not_flagged(self):
        # The whole point: Илларионовна/Иларионовна are ONE patronymic (a lexicon that
        # funnels both spellings of the father to one modern form — the base alone
        # keeps them apart, so a layer says it here), so a fold pairing them
        # must stay clean — that merge was correct.
        layer = Layer("corpus", {(M, "Илларион"): NameEntry(M, "Илларион", ("Иларион",))}, {
            (M, "Илларион"): FormsEntry(M, "Илларион", None, "Иларионович", "Иларионовна", "Илларионов", "Илларионова"),
            (M, "Иларион"): FormsEntry(M, "Иларион", None, "Иларионович", "Иларионовна", "Иларионов", "Иларионова")}, {})
        with names_registry.answering(Lexicon.of([base().load(), layer])):
            self.assertIsNone(
                name_mismatch("Агафья Илларионовна", "Агафья Иларионовна Ежевикина"))
        self.assertIsNone(name_mismatch("Аксинья Петровна", "Ксения Петровна"))

    def test_surname_difference_alone_is_not_a_mismatch(self):
        # Мямлин/Ягодкин/Мелюзгин are the same family across scribes.
        self.assertIsNone(
            name_mismatch("Терентий Мефодиевич Мямлин", "Терентий Мефодиевич Ягодкин"))

    def test_missing_component_cannot_disagree(self):
        # A bare given name carries no patronymic to compare — not evidence of two
        # people, so it must not be flagged.
        self.assertIsNone(name_mismatch("Мавра", "Мавра Ивановна"))
        self.assertIsNone(name_mismatch("Феодосия", "Феодосия"))

    def test_unknown_names_do_not_crash_or_false_flag(self):
        self.assertIsNone(name_mismatch("Зюзя Кукуевна", "Зюзя Кукуевна"))


class TestFoldCarriesMismatch(unittest.TestCase):
    def test_mismatched_fold_is_flagged_but_keeps_its_tier(self):
        # father role pairs two different patronymics, mother role two different
        # given names.
        folds = plan_folds(parse_show(DUP_PARENTS_MISMATCH), GUID_TO_RES, set(), {})
        father, mother = folds[0], folds[1]
        self.assertEqual(father.tier, AUTO)          # tier unchanged
        self.assertIsNotNone(father.name_mismatch)   # but flagged
        self.assertIsNotNone(mother.name_mismatch)

    def test_matching_fold_is_not_flagged(self):
        folds = plan_folds(parse_show(DUP_SPOUSE), GUID_TO_RES_SPOUSE, set(), {})
        self.assertIsNone(folds[0].name_mismatch)    # Мавра ← Мавра

    def test_report_warns_instead_of_recommending_the_merge(self):
        reports = build_reports([DUP_PARENTS_MISMATCH], GUID_TO_RES, set(), {})
        out = format_report(reports, stale=0)
        self.assertIn("NAME MISMATCH", out)
        # the bare merge command must NOT be offered for a mismatched fold
        self.assertNotIn("geni profile merge profile-g600FA profile-g600FB", out)

    def test_report_still_recommends_a_clean_merge(self):
        reports = build_reports([DUP_SPOUSE], GUID_TO_RES_SPOUSE, set(), {})
        out = format_report(reports, stale=0)
        self.assertNotIn("NAME MISMATCH", out)
        self.assertIn("geni profile merge profile-g600W1 profile-g600W2", out)


# ── Adjudicated (known-good) allowlist ──────────────────────────────────────
# A legitimate remarriage is a permanent duplicate_spouse conflict: correct, and
# unresolvable by merging. Without a way to record that verdict it resurfaces in
# full on every pass, competing with real duplicates.

class TestAdjudicated(unittest.TestCase):
    def test_allowlisted_fold_is_dropped(self):
        reports = build_reports([DUP_SPOUSE], GUID_TO_RES_SPOUSE, set(), {})
        kept, hidden = filter_adjudicated(reports, {("600S", "spouse", "600W2")})
        self.assertEqual(hidden, 1)
        self.assertEqual([r for r in kept if r.folds], [])

    def test_non_matching_entry_keeps_the_fold(self):
        reports = build_reports([DUP_SPOUSE], GUID_TO_RES_SPOUSE, set(), {})
        kept, hidden = filter_adjudicated(reports, {("600S", "spouse", "somebody")})
        self.assertEqual(hidden, 0)
        self.assertEqual(len(kept[0].folds), 1)

    def test_direction_is_ignored_so_a_survivor_flip_stays_adjudicated(self):
        # Geni picks its own survivor, so the pair can come back swapped.
        reports = build_reports([DUP_SPOUSE], GUID_TO_RES_SPOUSE, set(), {})
        _, hidden = filter_adjudicated(reports, {("600S", "spouse", "600W1")})
        self.assertEqual(hidden, 1)

    def test_hidden_count_is_reported_not_silent(self):
        self.assertIn("adjudicated", format_report([], stale=0, adjudicated=2))

    def test_parses_tsv_skipping_comments_and_blanks(self):
        text = ("# focus\trole\tabsorbed\treason\n"
                "\n"
                "600S\tspouse\t600W2\tremarriage: Евдокия d. before 1849\n")
        self.assertEqual(parse_adjudicated(text), {("600S", "spouse", "600W2")})


# ── Endpoint failure vs a genuinely empty queue ─────────────────────────────
# `geni tree-conflicts list` prints `null` for an EMPTY queue: the CLI
# aggregates pages into `var out []TreeConflict` (a nil slice) which Go marshals
# as null, with exit 0 and no stderr. That is success, not failure — confirmed
# against Geni's own Merge Center page reading «Конфликты древ (0)».
# A real failure exits non-zero, which `_geni_json` already raises on. So only a
# non-null, non-list payload is anomalous.

def _stub_json(payload: Any) -> Callable[[list[str]], Any]:
    """A `_geni_json` stand-in returning `payload`. A typed def, not a lambda —
    the repo runs pyright in strict mode, where an unannotated lambda parameter
    is an error (reportUnknownLambdaType)."""
    def _call(_args: list[str]) -> Any:
        return payload
    return _call


class TestEndpointFailure(unittest.TestCase):
    def test_null_is_an_empty_queue_not_a_failure(self):
        # go-geni's nil-slice quirk. Treating this as an outage would block every
        # run once the queue is finally clear.
        self.assertEqual(fetch_list("managed", _json=_stub_json(None)), [])

    def test_non_list_response_raises(self):
        with self.assertRaises(TreeConflictsUnavailable):
            fetch_list("managed", _json=_stub_json({"error": "nope"}))

    def test_genuinely_empty_list_is_fine(self):
        self.assertEqual(fetch_list("managed", _json=_stub_json([])), [])

    def test_failed_shows_are_counted_not_silently_dropped(self):
        # every `show` 404s → 0 actionable, but the failures must be surfaced
        def _list(_collection: str) -> list[dict[str, Any]]:
            return [{"profile_id": "600S"}]

        def _show(_profile_id: str) -> dict[str, Any]:
            return {}

        _, stale, failed = gather("managed", 0, _list=_list, _show=_show)
        self.assertEqual(stale, 0)
        self.assertEqual(failed, 1)

    def test_report_surfaces_failed_shows(self):
        self.assertIn("could not be read", format_report([], stale=0, failed=3))
