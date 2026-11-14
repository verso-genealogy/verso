#!/usr/bin/env python3
"""Unit tests for verso.ru.consolidation.detector helpers.

Covers the union-block suggester (suggest_union_blocks) and the profile_names
normalizer (_sort_profile_names_body) — the two pieces that previously had to
be re-derived by hand each consolidation cycle.
"""

from __future__ import annotations

import unittest

from verso.ru.consolidation import detector as cp


def _union(name, actions, before_id=None, after_id=None):
    change = {"actions": actions, "before": None, "after": None}
    if before_id is not None:
        change["before"] = {"id": before_id, "partners": []}
    if after_id is not None or actions == ["create"]:
        change["after"] = {"id": after_id, "partners": []}
    return {"address": f"geni_union.{name}", "type": "geni_union", "change": change}


class SuggestUnionBlocks(unittest.TestCase):
    def test_lone_collapse_onto_survivor_is_removed(self):
        """A per-record union sharing a surviving canonical's id → removed."""
        plan = {
            "resource_changes": [
                _union("anna_and_boris_d5_1840", ["delete"], before_id="union-1"),
                _union("anna_and_boris", ["no-op"], before_id="union-1", after_id="union-1"),
            ]
        }
        moved, removed, notes = cp.suggest_union_blocks(plan)
        self.assertEqual(moved, [])
        self.assertEqual(removed, ["anna_and_boris_d5_1840"])
        self.assertEqual(notes, [])

    def test_same_id_rename_is_moved(self):
        """A delete + create carrying the same resolved id → moved."""
        plan = {
            "resource_changes": [
                _union("clim_and_dora_10_1840", ["delete"], before_id="union-2"),
                _union(
                    "clim_and__1840_07_07_dora_mk_births_10_mother",
                    ["create"],
                    after_id="union-2",
                ),
            ]
        }
        moved, removed, notes = cp.suggest_union_blocks(plan)
        self.assertEqual(
            moved,
            [("clim_and_dora_10_1840", "clim_and__1840_07_07_dora_mk_births_10_mother")],
        )
        self.assertEqual(removed, [])
        self.assertEqual(notes, [])

    def test_idless_rename_picks_best_match_and_collapses_rest(self):
        """Two deletes on one id + an id-less create: the create renames the
        best-matching delete (moved), the other collapsed delete is removed."""
        plan = {
            "resource_changes": [
                _union("egor_ivanovich_and_anna_petrovna_41_1839", ["delete"], before_id="union-3"),
                _union("grigorij_egorovich_and_egor_ivanovich_d5_1840", ["delete"], before_id="union-3"),
                _union(
                    "egor_ivanovich_2_and__1839_10_12_anna_petrovna_mk_births_41_mother",
                    ["create"],
                    after_id=None,
                ),
            ]
        }
        moved, removed, notes = cp.suggest_union_blocks(plan)
        self.assertEqual(
            moved,
            [(
                "egor_ivanovich_and_anna_petrovna_41_1839",
                "egor_ivanovich_2_and__1839_10_12_anna_petrovna_mk_births_41_mother",
            )],
        )
        self.assertEqual(removed, ["grigorij_egorovich_and_egor_ivanovich_d5_1840"])
        self.assertEqual(notes, [])

    def test_standalone_delete_without_match_is_noted(self):
        plan = {
            "resource_changes": [
                _union("orphan_and_nobody_d9_1840", ["delete"], before_id="union-9"),
            ]
        }
        moved, removed, notes = cp.suggest_union_blocks(plan)
        self.assertEqual((moved, removed), ([], []))
        self.assertEqual(len(notes), 1)
        self.assertIn("orphan_and_nobody_d9_1840", notes[0])

    def test_format_emits_terraform_blocks(self):
        out = cp.format_union_blocks(
            [("a_b_10_1840", "a_and_b")], ["c_d_d5_1840"], []
        )
        self.assertIn("moved {", out)
        self.assertIn("from = geni_union.a_b_10_1840", out)
        self.assertIn("to   = geni_union.a_and_b", out)
        self.assertIn("removed {", out)
        self.assertIn("destroy = false", out)


def _punion(name, actions, before_id=None, after_id=None, partners=None, children=None):
    """Like _union but carries Geni partner/children profile ids — exercises the
    partner-identity matching that distinguishes a true rename from a sibling's
    union with the same surname/patronymic tokens."""

    def payload(i):
        return {"id": i, "partners": list(partners or []), "children": list(children or [])}

    change = {"actions": actions, "before": None, "after": None}
    if before_id is not None or actions == ["delete"]:
        change["before"] = payload(before_id)
    if after_id is not None or actions == ["create"]:
        change["after"] = payload(after_id)
    return {"address": f"geni_union.{name}", "type": "geni_union", "change": change}


class SuggestUnionBlocksByPartners(unittest.TestCase):
    """P1: match renames by shared Geni partner ids, not resource-name tokens —
    siblings share surname+patronymic tokens but have disjoint partner sets."""

    def test_sibling_with_disjoint_partners_is_not_moved(self):
        # Fedor's family union (partner Fedor + child) and Grigorij's 1909
        # marriage create share {vladimirovich, ljapkin} tokens but NO partner.
        # The real rename is Grigorij's own union (same two partners).
        plan = {
            "resource_changes": [
                _punion(
                    "fedor_vladimirovich_ljapkin_2_1912", ["delete"],
                    before_id="union-913",
                    partners=["profile-fedor"], children=["profile-alexey"],
                ),
                _punion(
                    "grigorij_vladimirovich_ljapkin_and_evdokija_prokopievna_meshkovina_m2_1909",
                    ["delete"], before_id="union-892",
                    partners=["profile-grigorij", "profile-evdokija"],
                ),
                _punion(
                    "grigorij_vladimirovich_ljapkin_and__1909_01_09_evdokija_prokopievna_ljapkina_mk_marriages_2_bride",
                    ["create"], after_id=None,
                    partners=["profile-grigorij", "profile-evdokija"],
                ),
            ]
        }
        moved, removed, notes = cp.suggest_union_blocks(plan)
        # The real rename pairs the two same-partner unions; Fedor is never the
        # moved-from for Grigorij's create.
        self.assertEqual(
            moved,
            [(
                "grigorij_vladimirovich_ljapkin_and_evdokija_prokopievna_meshkovina_m2_1909",
                "grigorij_vladimirovich_ljapkin_and__1909_01_09_evdokija_prokopievna_ljapkina_mk_marriages_2_bride",
            )],
        )
        self.assertNotIn("fedor_vladimirovich_ljapkin_2_1912", removed)
        # Fedor's union still holds a child → REVIEW note, never a bare destroy.
        self.assertTrue(any("fedor_vladimirovich_ljapkin_2_1912" in n for n in notes))
        self.assertTrue(any("child" in n for n in notes))

    def test_partner_match_beats_higher_name_overlap(self):
        # A decoy create shares MORE name tokens, but a different create shares
        # the partner ids — partner identity must win.
        plan = {
            "resource_changes": [
                _punion(
                    "ivan_petrov_and_anna_ivanova_5_1910", ["delete"],
                    before_id="union-1",
                    partners=["profile-ivan", "profile-anna"],
                ),
                _punion(  # decoy: more name overlap, disjoint partners
                    "ivan_petrov_and_maria_petrova_god_parent_1", ["create"],
                    after_id=None, partners=["profile-ivan2", "profile-maria"],
                ),
                _punion(  # true rename: fewer shared tokens, same partners
                    "ivan_p_and__1910_anna_mk_births_5_mother", ["create"],
                    after_id=None, partners=["profile-ivan", "profile-anna"],
                ),
            ]
        }
        moved, _removed, _notes = cp.suggest_union_blocks(plan)
        self.assertEqual(
            moved, [("ivan_petrov_and_anna_ivanova_5_1910", "ivan_p_and__1910_anna_mk_births_5_mother")]
        )

    def test_same_partner_collapse_is_removed_not_flagged(self):
        # Two per-year unions of the SAME couple sharing one Geni id + one
        # create: one renames (moved), the other (shared partners) collapses
        # (removed), no REVIEW.
        plan = {
            "resource_changes": [
                _punion("vas_and_anis_1_1915", ["delete"], before_id="union-7",
                        partners=["profile-vas", "profile-anis"]),
                _punion("vas_and_anis_1_1917", ["delete"], before_id="union-7",
                        partners=["profile-vas", "profile-anis"]),
                _punion("vas_and_anis", ["create"], after_id=None,
                        partners=["profile-vas", "profile-anis"]),
            ]
        }
        moved, removed, notes = cp.suggest_union_blocks(plan)
        self.assertEqual(len(moved), 1)
        self.assertEqual(
            removed,
            [m for m in ["vas_and_anis_1_1915", "vas_and_anis_1_1917"] if m != moved[0][0]],
        )
        self.assertEqual(notes, [])

    def test_disjoint_partner_in_same_id_group_is_flagged_not_removed(self):
        # Same Geni id group, but one delete is a DIFFERENT couple (disjoint
        # partners) caught in the group — it must be flagged, never silently
        # removed (forgetting it would have masked a real problem).
        plan = {
            "resource_changes": [
                _punion("vas_and_anis_1_1915", ["delete"], before_id="union-7",
                        partners=["profile-vas", "profile-anis"]),
                _punion("foreign_and_other_d1_1915", ["delete"], before_id="union-7",
                        partners=["profile-x", "profile-y"], children=["profile-kid"]),
                _punion("vas_and_anis", ["create"], after_id=None,
                        partners=["profile-vas", "profile-anis"]),
            ]
        }
        moved, removed, notes = cp.suggest_union_blocks(plan)
        self.assertEqual(moved, [("vas_and_anis_1_1915", "vas_and_anis")])
        self.assertNotIn("foreign_and_other_d1_1915", removed)
        self.assertTrue(any("foreign_and_other_d1_1915" in n and "child" in n for n in notes))

    def test_no_partner_info_falls_back_to_name_tokens(self):
        # When the plan carries no partner ids (older fixtures), behaviour is
        # unchanged: name-token matching still pairs the rename.
        plan = {
            "resource_changes": [
                _punion("egor_and_anna_41_1839", ["delete"], before_id="union-3"),
                _punion("egor_2_and__1839_anna_mk_births_41_mother", ["create"], after_id=None),
            ]
        }
        moved, _removed, notes = cp.suggest_union_blocks(plan)
        self.assertEqual(
            moved, [("egor_and_anna_41_1839", "egor_2_and__1839_anna_mk_births_41_mother")]
        )
        self.assertEqual(notes, [])


class TfMoveCommands(unittest.TestCase):
    """state-mv suggestions: unions use the partner-id pairs from
    suggest_union_blocks (not difflib), so a sibling with overlapping payload is
    never paired; non-union types still use signature similarity."""

    def test_union_uses_partner_id_pairs_not_fuzzy(self):
        added = [("geni_union.grig_and_evdokija_new", {"partners": ["p-g", "p-e"]})]
        removed = [
            ("geni_union.grig_and_evdokija_m2_1909", {"partners": ["p-g", "p-e"]}),
            ("geni_union.fedor_2_1912", {"partners": ["p-f"], "children": ["p-c"]}),
        ]
        union_moves = [("grig_and_evdokija_m2_1909", "grig_and_evdokija_new")]
        pairs = cp.tf_move_commands(added, removed, union_moves)
        self.assertIn(
            ("geni_union.grig_and_evdokija_m2_1909", "geni_union.grig_and_evdokija_new"), pairs)
        # The sibling (disjoint partners) is never paired with the create.
        self.assertNotIn(
            ("geni_union.fedor_2_1912", "geni_union.grig_and_evdokija_new"), pairs)

    def test_union_not_in_moves_gets_no_state_mv(self):
        # Unions never fall through to fuzzy matching.
        added = [("geni_union.new_couple", {"partners": ["p-a", "p-b"]})]
        removed = [("geni_union.old_couple", {"partners": ["p-a", "p-b"]})]
        self.assertEqual(cp.tf_move_commands(added, removed, union_moves=[]), [])

    def test_union_move_requires_both_ends_present(self):
        added = [("geni_union.new_couple", {"partners": ["p-a"]})]
        pairs = cp.tf_move_commands(added, [], union_moves=[("old_couple", "new_couple")])
        self.assertEqual(pairs, [])

    def test_profile_rename_still_fuzzy_matches(self):
        added = [("geni_profile._1920_hitretsova_gp",
                  {"first_name": "Анастасия", "last_name": "Хитрецова"})]
        removed = [("geni_profile._1920_hitretsovy_gp",
                    {"first_name": "Анастасия", "last_name": "Хитрецовы"})]
        self.assertEqual(
            cp.tf_move_commands(added, removed, union_moves=[]),
            [("geni_profile._1920_hitretsovy_gp", "geni_profile._1920_hitretsova_gp")],
        )


class SortProfileNamesBody(unittest.TestCase):
    def test_already_sorted_returns_none(self):
        body = '\n            "_a",\n            "_b",\n        '
        self.assertIsNone(cp._sort_profile_names_body(body))

    def test_unsorted_is_reordered(self):
        body = '\n            "_b",\n            "_a",\n        '
        out = cp._sort_profile_names_body(body)
        self.assertIsNotNone(out)
        self.assertLess(out.index('"_a"'), out.index('"_b"'))

    def test_comment_travels_with_its_entry(self):
        # Comment annotates "_a" (the second source line); after sorting "_a"
        # to the front, the comment must come with it — and the quoted string
        # inside the comment must NOT be treated as a list entry.
        body = (
            '\n            "_b",\n'
            '            # explains "_a" translit\n'
            '            "_a",\n        '
        )
        out = cp._sort_profile_names_body(body)
        self.assertIsNotNone(out)
        self.assertLess(out.index('"_a"'), out.index('"_b"'))
        self.assertIn('# explains', out)
        self.assertLess(out.index("# explains"), out.index('"_a"'))
        # membership preserved: only _a and _b are real entries
        import re

        assert out is not None
        entries = re.findall(r'^\s*"([^"]+)",', out, re.MULTILINE)
        self.assertEqual(sorted(entries), ["_a", "_b"])

    def test_malformed_glued_bracket_is_repaired(self):
        # Last entry has the closing bracket glued on (real-world mess); the
        # rebuilt body must sort it in and leave a clean close-indent.
        body = '\n            "_b",\n            "_a",'
        out = cp._sort_profile_names_body(body)
        self.assertIsNotNone(out)
        self.assertLess(out.index('"_a"'), out.index('"_b"'))
        self.assertTrue(out.endswith("        "))


class DocumentChanges(unittest.TestCase):
    def _doc(self, name, actions, before, after):
        return {
            "address": f"geni_document.{name}",
            "type": "geni_document",
            "change": {"actions": actions, "before": before, "after": after},
        }

    def test_force_replace_with_text_delta_is_flagged(self):
        plan = {
            "resource_changes": [
                self._doc(
                    "marriage_of_x",
                    ["delete", "create"],
                    {"id": "document-1", "text": "old"},
                    {"text": "new"},
                ),
            ]
        }
        docs = cp.collect_document_changes(plan)
        self.assertEqual(docs, [("marriage_of_x", ["text"])])
        warn = cp.format_document_warning(docs)
        self.assertIn("verso document-sync", warn)          # A command a person types
        self.assertIn("marriage_of_x", warn)

    def test_noop_or_unchanged_doc_not_flagged(self):
        plan = {
            "resource_changes": [
                self._doc("a", ["no-op"], {"id": "document-2", "text": "t"}, {"text": "t"}),
                self._doc(
                    "b", ["delete", "create"], {"id": "document-3", "text": "t"}, {"text": "t"}
                ),
            ]
        }
        self.assertEqual(cp.collect_document_changes(plan), [])
        self.assertEqual(cp.format_document_warning([]), "")


class NormalizeSortProfileNames(unittest.TestCase):
    """End to end over a real file, which `_sort_profile_names_body` alone
    never covered — and the annotated declaration is why the whole thing
    silently did nothing outside Горюхино."""

    HEADER = 'from verso.core.targets.geni import GeniProfile\n\n'
    BODY = (
        '    "canon": {\n'
        '        "profile_names": [\n'
        '            "_1899_b",\n'
        '            # why this one folds\n'
        '            "_1888_a",\n'
        '        ],\n'
        '    },\n'
        '}\n'
    )

    def _write(self, declaration):
        import tempfile
        import pathlib
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "generate_config_names.py"
        p.write_text(self.HEADER + declaration + self.BODY, encoding="utf-8")
        return p

    def test_sorts_an_annotated_declaration(self):
        p = self._write("profiles_to_consolidate: dict[str, object] = {\n")
        self.assertTrue(cp.normalize_sort_profile_names(str(p)))
        out = p.read_text(encoding="utf-8")
        self.assertLess(out.index('"_1888_a"'), out.index('"_1899_b"'))

    def test_sorts_a_bare_declaration(self):
        p = self._write("profiles_to_consolidate = {\n")
        self.assertTrue(cp.normalize_sort_profile_names(str(p)))
        out = p.read_text(encoding="utf-8")
        self.assertLess(out.index('"_1888_a"'), out.index('"_1899_b"'))

    def test_the_comment_travels_with_its_entry(self):
        p = self._write("profiles_to_consolidate: dict[str, object] = {\n")
        cp.normalize_sort_profile_names(str(p))
        lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(lines[lines.index('"_1888_a",') - 1], "# why this one folds")

    def test_a_second_run_changes_nothing(self):
        p = self._write("profiles_to_consolidate: dict[str, object] = {\n")
        self.assertTrue(cp.normalize_sort_profile_names(str(p)))
        once = p.read_text(encoding="utf-8")
        self.assertFalse(cp.normalize_sort_profile_names(str(p)))
        self.assertEqual(p.read_text(encoding="utf-8"), once)


if __name__ == "__main__":
    unittest.main()
