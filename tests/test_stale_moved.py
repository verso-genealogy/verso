#!/usr/bin/env python3
"""Unit tests for `verso.ru.consolidation.stale_moved`.

The check answers one question per consolidation entry: do the `moved` /
`removed{destroy=false}` blocks it generates still address anything in
terraform state? Once the fold has been applied, state holds only the
canonical, so every block the entry emits is a permanent no-op.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from verso.core.pipeline.config import consolidation_state_blocks
from verso.ru.consolidation.stale_moved import find_inert, prune_source


def _gcn(targets):
    return SimpleNamespace(profiles_to_consolidate=targets)


class ConsolidationStateBlocks(unittest.TestCase):
    """The block model must mirror `build_moved_consolidated_profiles` exactly —
    it is the same function's first half, so the check cannot drift from the
    generator it is checking."""

    def test_first_name_moves_and_the_rest_are_removed(self):
        blocks = consolidation_state_blocks(_gcn({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan", "_c_ivan"]},
        }))
        self.assertEqual(
            [(b.kind, b.frm, b.canonical) for b in blocks],
            [("moved", "_a_ivan", "ivan_petrov"),
             ("removed", "_b_ivan", "ivan_petrov"),
             ("removed", "_c_ivan", "ivan_petrov")],
        )

    def test_explicit_keeper_is_the_moved_source(self):
        blocks = consolidation_state_blocks(_gcn({
            "ivan_petrov": {"generate_moved_block": True,
                            "keeper": "_b_ivan",
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }))
        moved = [b for b in blocks if b.kind == "moved"]
        self.assertEqual([b.frm for b in moved], ["_b_ivan"])
        self.assertEqual([b.frm for b in blocks if b.kind == "removed"], ["_a_ivan"])

    def test_adopt_external_emits_no_moved(self):
        blocks = consolidation_state_blocks(_gcn({
            "ivan_petrov": {"generate_moved_block": True, "adopt_external": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }))
        self.assertEqual({b.kind for b in blocks}, {"removed"})

    def test_entry_without_the_flag_emits_nothing(self):
        self.assertEqual(consolidation_state_blocks(_gcn({
            "ivan_petrov": {"profile_names": ["_a_ivan", "_b_ivan"]},
        })), [])


class FindInert(unittest.TestCase):
    def test_entry_whose_addresses_left_state_is_inert(self):
        """The applied fold: state holds the canonical alone, so both the
        `moved` and every `removed` are permanent no-ops."""
        blocks = consolidation_state_blocks(_gcn({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }))
        inert, live = find_inert(blocks, {"ivan_petrov"})
        self.assertEqual([e.canonical for e in inert], ["ivan_petrov"])
        self.assertEqual(live, [])
        self.assertEqual(inert[0].blocks, 2)

    def test_one_address_still_in_state_keeps_the_entry_live(self):
        """A fold that has NOT been applied: the stub is still its own state
        entry, and the moved block is the only thing that carries its Geni id
        onto the canonical."""
        blocks = consolidation_state_blocks(_gcn({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }))
        inert, live = find_inert(blocks, {"_a_ivan", "ivan_petrov"})
        self.assertEqual(inert, [])
        self.assertEqual([e.canonical for e in live], ["ivan_petrov"])
        self.assertEqual(live[0].live_addresses, ["_a_ivan"])

    def test_a_removed_block_alone_keeps_the_entry_live(self):
        """`removed{destroy=false}` on an in-state address is load-bearing on
        its own — dropping it lets the next apply destroy a live Geni profile."""
        blocks = consolidation_state_blocks(_gcn({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
        }))
        inert, live = find_inert(blocks, {"_b_ivan"})
        self.assertEqual(inert, [])
        self.assertEqual([e.live_addresses for e in live], [["_b_ivan"]])

    def test_entries_are_reported_separately(self):
        blocks = consolidation_state_blocks(_gcn({
            "ivan_petrov": {"generate_moved_block": True,
                            "profile_names": ["_a_ivan", "_b_ivan"]},
            "anna_petrova": {"generate_moved_block": True,
                             "profile_names": ["_a_anna", "_b_anna"]},
        }))
        inert, live = find_inert(blocks, {"_a_anna"})
        self.assertEqual([e.canonical for e in inert], ["ivan_petrov"])
        self.assertEqual([e.canonical for e in live], ["anna_petrova"])


if __name__ == "__main__":
    unittest.main()


class PruneSource(unittest.TestCase):
    """The codemod deletes exactly two single-line keys from exactly the named
    entries. It is line-based on purpose: the config is 27k hand-annotated
    lines, and an ast.unparse round-trip would reformat every comment away."""

    ENTRY = '''\
profiles_to_consolidate = {
    # Иван Петров — folded 1850.
    "ivan_petrov": {
        "generate_moved_block": True,
        "keeper": "_b_ivan",
        "profile_names": [
            "_a_ivan",
            "_b_ivan",
        ],
    },
    "anna_petrova": {
        "generate_moved_block": True,
        "profile_names": ["_a_anna", "_b_anna"],
    },
}
'''

    def test_removes_both_keys_from_the_named_entry(self):
        out, skipped = prune_source(self.ENTRY, {"ivan_petrov"})
        self.assertNotIn('"generate_moved_block": True,\n        "keeper"', out)
        self.assertNotIn('"keeper": "_b_ivan"', out)
        self.assertEqual(skipped, [])
        # the entry itself, its comment and its names survive untouched
        self.assertIn("# Иван Петров — folded 1850.", out)
        self.assertIn('"_a_ivan",', out)
        self.assertIn('"ivan_petrov": {', out)

    def test_leaves_unnamed_entries_alone(self):
        out, _ = prune_source(self.ENTRY, {"ivan_petrov"})
        anna = out[out.index('"anna_petrova"'):]
        self.assertIn('"generate_moved_block": True,', anna)

    def test_pruned_source_still_parses_and_keeps_the_fold(self):
        import ast
        out, _ = prune_source(self.ENTRY, {"ivan_petrov", "anna_petrova"})
        ns: dict[str, Any] = {}
        exec(compile(ast.parse(out), "<pruned>", "exec"), ns)
        self.assertEqual(
            ns["profiles_to_consolidate"]["ivan_petrov"],
            {"profile_names": ["_a_ivan", "_b_ivan"]},
        )
        self.assertNotIn("generate_moved_block", ns["profiles_to_consolidate"]["anna_petrova"])

    def test_multiline_value_is_skipped_not_guessed(self):
        src = '''\
profiles_to_consolidate = {
    "ivan_petrov": {
        "generate_moved_block": (
            True
        ),
        "profile_names": ["_a_ivan"],
    },
}
'''
        out, skipped = prune_source(src, {"ivan_petrov"})
        self.assertEqual(out, src)
        self.assertEqual(len(skipped), 1)
        self.assertIn("ivan_petrov", skipped[0])

    def test_comment_mentioning_the_flag_is_reported(self):
        src = '''\
profiles_to_consolidate = {
    # generate_moved_block emits removed{destroy=false} for the groom_father.
    "ivan_petrov": {
        "generate_moved_block": True,
        "profile_names": ["_a_ivan"],
    },
}
'''
        out, skipped = prune_source(src, {"ivan_petrov"})
        self.assertNotIn('"generate_moved_block": True,', out)
        self.assertTrue(any("comment" in s for s in skipped), skipped)

    def test_comment_note_line_number_points_into_the_OUTPUT(self):
        """Notes are read after the deletion, so their line numbers address the
        file the user is about to open — not the one that no longer exists."""
        src = '''\
profiles_to_consolidate = {
    "filler": {
        "generate_moved_block": True,
        "keeper": "_a_filler",
        "profile_names": ["_a_filler", "_b_filler"],
    },
    # keeper — запись о смерти, её id пережил слияние.
    "ivan_petrov": {
        "generate_moved_block": True,
        "profile_names": ["_a_ivan"],
    },
}
'''
        out, notes = prune_source(src, {"filler", "ivan_petrov"})
        comment_notes = [n for n in notes if "comment" in n]
        self.assertEqual(len(comment_notes), 1, notes)
        reported = int(comment_notes[0].split("line ")[1].split(" ")[0])
        self.assertIn("keeper — запись о смерти", out.splitlines()[reported - 1])
