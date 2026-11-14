#!/usr/bin/env python3
"""SMB001 — consolidation entries whose `moved` / `removed` blocks no longer
address anything in terraform state.

An entry carrying `generate_moved_block: True` makes
`_moved_consolidated_profiles.tf` emit one `moved { from = <keeper> to =
<canonical> }` plus a `removed { destroy = false }` for every other declared
record. Those blocks exist to survive ONE apply: the `moved` carries the
keeper's live Geni id onto the canonical address, and each `removed` stops
terraform destroying a duplicate that Geni has already merged away.

After that apply, state holds the canonical alone. A `moved` whose `from` is
absent from state is a documented no-op, and so is a `removed` for an address
state never mentions — so the entry keeps generating blocks that can never do
anything again. Every one of the 354 flagged entries across the three applied
villages was in exactly that condition when this check was written (Горюхино
191, Маниловка 110, Нижняя Яичница 53 — 1595 blocks, 10 472 lines of generated
Terraform).

**Why this cannot be a static check.** `stale_stubs` (CST001/CST002) and
`lint_config` (CCN) both answer questions the repo already contains. This one
does not: "the fold has already been applied" is recorded only in terraform
state. Nothing in the DSL or the config distinguishes a pending fold from a
landed one — the config text is identical either way. Hence the state dump,
which is cheap (a plain S3 read, no refresh, no Geni auth, no provider calls)
but keeps the check out of CI, where `terraform init -backend=false` means
there is no state to read.

**Reporting by default; `--prune` is the opt-in codemod.** An inert entry is
safe to prune — dropping the flag changes nothing but
`_moved_consolidated_profiles.tf`, verified by regenerating a village with every
flag stripped — but the blocks are also the recovery path if state is ever
rolled back to a pre-consolidation version, and they cost nothing at plan time.
So the plain run counts and lists, and exits 0 unless asked for `--strict`.
Горюхино was pruned 2026-08-20 (191 entries); Маниловка and Нижняя Яичница were not.

**A LIVE entry must not be touched.** One address still in state means the fold
has NOT been applied yet, and the blocks are the only thing standing between
the next apply and a destroyed Geni profile.
A `removed` on an in-state address is load-bearing on its own, even when the
`moved` source is long gone.

Run:
    python3 -m verso.ru.consolidation.stale_moved --village Горюхино
    python3 -m verso.ru.consolidation.stale_moved --village Маниловка --json
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

from verso.core.pipeline.config import CONFIG_FILE, ConsolidationBlock, consolidation_state_blocks, load_config
from verso.core.tools import tool

CODE = "SMB001"


class EntryStatus(NamedTuple):
    """One consolidation entry's state-continuity blocks, judged against state."""

    canonical: str
    blocks: int            # how many moved/removed blocks the entry generates
    addresses: list[str]   # every address those blocks name
    live_addresses: list[str]  # the subset still present in terraform state

    @property
    def is_inert(self) -> bool:
        return not self.live_addresses

    def line(self) -> str:
        return f"[{CODE}] {self.canonical} — {self.blocks} block(s), no address in state"


def find_inert(
    blocks: list[ConsolidationBlock], state: set[str]
) -> tuple[list[EntryStatus], list[EntryStatus]]:
    """Group *blocks* by canonical and split into (inert, live).

    Inert = not one address the entry names survives in *state*, so every block
    it generates is a permanent no-op. Live = at least one does, which means the
    fold has not been applied and the blocks are still load-bearing.
    """
    order: list[str] = []
    addresses: dict[str, list[str]] = {}
    for b in blocks:
        if b.canonical not in addresses:
            order.append(b.canonical)
            addresses[b.canonical] = []
        addresses[b.canonical].append(b.frm)

    inert: list[EntryStatus] = []
    live: list[EntryStatus] = []
    for canonical in order:
        addrs = addresses[canonical]
        entry = EntryStatus(
            canonical=canonical,
            blocks=len(addrs),
            addresses=addrs,
            live_addresses=[a for a in addrs if a in state],
        )
        (inert if entry.is_inert else live).append(entry)
    return inert, live


_PRUNED_KEYS = ("generate_moved_block", "keeper")

#: A key/value the codemod is willing to delete: the whole pair on one line.
#: The config is generated in this shape; anything else is left for a human.
_SINGLE_LINE = re.compile(
    r'^\s*"(?:generate_moved_block|keeper)"\s*:\s*(?:True|False|"[^"]*")\s*,\s*(?:#.*)?$'
)


def _comment_notes(text: str, canonicals: set[str]) -> list[str]:
    """Comments inside a pruned entry that still name `generate_moved_block` or
    `keeper`. Read from the OUTPUT, so the line numbers address the file the
    caller is about to open."""
    tree = ast.parse(text)
    lines = text.splitlines()
    notes: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "profiles_to_consolidate"
                and isinstance(node.value, ast.Dict)):
            continue
        for key_node, value_node in zip(node.value.keys, node.value.values, strict=False):
            if not (isinstance(key_node, ast.Constant) and key_node.value in canonicals):
                continue
            if not isinstance(value_node, ast.Dict):
                continue
            end = max((getattr(n, "end_lineno", 0) or 0) for n in ast.walk(value_node))
            # A leading comment block belongs to the entry it precedes.
            start = key_node.lineno
            while start > 1 and lines[start - 2].lstrip().startswith("#"):
                start -= 1
            for ln in range(start, end + 1):
                if "#" not in lines[ln - 1]:
                    continue
                after = lines[ln - 1].split("#", 1)[1]
                if any(k in after for k in _PRUNED_KEYS):
                    notes.append(
                        f"{key_node.value}: comment at line {ln} names a pruned "
                        f"key: {after.strip()}"
                    )
    return notes


def prune_source(src: str, canonicals: set[str]) -> tuple[str, list[str]]:
    """Delete the `generate_moved_block` / `keeper` lines of the named entries.

    Line-based rather than an `ast.unparse` round-trip: `generate_config_names.py`
    is ~27k hand-annotated lines and unparsing would erase every comment in the
    file. `ast` is still what LOCATES the lines, so an entry is identified by its
    real dict key, never by a text match.

    Returns `(new_source, notes)`. A key whose value is not a single-line literal
    is left in place and reported — the codemod never guesses at a shape it was
    not built for. Comments still naming a pruned key are reported too: they
    describe behaviour the entry no longer has, and only a human can rewrite
    them. Both kinds of note carry OUTPUT line numbers.
    """
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    drop: set[int] = set()          # 1-based line numbers, in the INPUT
    skipped: list[str] = []

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "profiles_to_consolidate"
                and isinstance(node.value, ast.Dict)):
            continue
        for key_node, value_node in zip(node.value.keys, node.value.values, strict=False):
            if not (isinstance(key_node, ast.Constant) and key_node.value in canonicals):
                continue
            if not isinstance(value_node, ast.Dict):
                continue
            for k, v in zip(value_node.keys, value_node.values, strict=False):
                if not (isinstance(k, ast.Constant) and k.value in _PRUNED_KEYS):
                    continue
                start, end = k.lineno, getattr(v, "end_lineno", v.lineno)
                if start != end or not _SINGLE_LINE.match(lines[start - 1].rstrip("\n")):
                    skipped.append(
                        f"{key_node.value}: {k.value!r} is not a single-line "
                        f"literal — left in place"
                    )
                    continue
                drop.add(start)

    out = "".join(t for i, t in enumerate(lines, start=1) if i not in drop)
    return out, skipped + _comment_notes(out, canonicals)


def read_state(village: str) -> set[str]:
    """`geni_profile.*` addresses in the village's terraform state.

    `state list` reads the S3 state object directly — no refresh, no provider
    calls, so it needs neither Geni auth nor a plan.
    """
    module = Path(village) / "terraform" / "geni"
    proc = subprocess.run(
        [tool("terraform"), f"-chdir={module}", "state", "list"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"`terraform state list` failed in {module}:\n{proc.stderr.strip()}"
        )
    prefix = "geni_profile."
    return {
        ln.strip()[len(prefix):]
        for ln in proc.stdout.splitlines()
        if ln.strip().startswith(prefix)
    }


def _load_config(village: str) -> Any:
    """`<village>/generate_config_names.py`, loaded fresh (`verso.core.pipeline.config`)."""
    return load_config(Path(village) / CONFIG_FILE)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--village", required=True)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--state-file", help="read addresses from a `terraform state list` "
                                         "dump instead of shelling out")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any entry is inert (default: report only)")
    ap.add_argument("--prune", action="store_true",
                    help="DELETE `generate_moved_block`/`keeper` from every inert "
                         "entry (rewrites generate_config_names.py). Regenerate and "
                         "diff afterwards: only _moved_consolidated_profiles.tf may move")
    args = ap.parse_args(argv)

    blocks = consolidation_state_blocks(_load_config(args.village))
    if args.state_file:
        prefix = "geni_profile."
        state = {
            ln.strip()[len(prefix):]
            for ln in Path(args.state_file).read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith(prefix)
        }
    else:
        state = read_state(args.village)

    inert, live = find_inert(blocks, state)
    total_blocks = sum(e.blocks for e in inert)

    if args.prune:
        if not inert:
            print(f"{args.village}: nothing to prune.")
            return 0
        cfg = Path(args.village) / "generate_config_names.py"
        before = cfg.read_text(encoding="utf-8")
        after, notes = prune_source(before, {e.canonical for e in inert})
        cfg.write_text(after, encoding="utf-8")
        removed_lines = len(before.splitlines()) - len(after.splitlines())
        print(f"{args.village}: pruned {len(inert)} inert entr"
              f"{'y' if len(inert) == 1 else 'ies'} "
              f"({removed_lines} lines, {sum(e.blocks for e in inert)} generated "
              f"blocks) → {cfg}")
        if notes:
            print(f"\n{len(notes)} item(s) need a human — comments describing "
                  "behaviour the entry no longer has, and any key the codemod "
                  "declined to touch:")
            for n in notes:
                print(f"  {n}")
        print("\nNow: `verso lint-config` + `verso generate-tf` and check the diff "
              "touches\nONLY _moved_consolidated_profiles.tf.")
        return 0

    if args.json:
        print(json.dumps({
            "village": args.village,
            "entries": len(inert) + len(live),
            "inert": [e._asdict() for e in inert],
            "live": [e._asdict() for e in live],
        }, ensure_ascii=False))
        return 1 if (args.strict and inert) else 0

    if live:
        print(f"{args.village}: {len(live)} entr"
              f"{'y' if len(live) == 1 else 'ies'} still LOAD-BEARING — do not "
              f"prune (the fold has not been applied):")
        for e in live:
            print(f"  {e.canonical} — in state: {', '.join(e.live_addresses)}")
        print()

    if not inert:
        print(f"{args.village}: no inert state-continuity blocks "
              f"({len(live)} entries still load-bearing).")
        return 0

    print(f"{args.village}: {len(inert)} of {len(inert) + len(live)} "
          f"`generate_moved_block` entries are INERT — {total_blocks} block(s) "
          f"whose addresses have all left terraform state:")
    for e in inert:
        print(f"  {e.line()}")
    print(
        "\nEach generates only no-ops: its fold was applied, so state holds the "
        "canonical\nalone. Dropping `generate_moved_block` (and any `keeper`) "
        "touches nothing but\n_moved_consolidated_profiles.tf — but the blocks "
        "are also the recovery path if\nstate is rolled back to a "
        "pre-consolidation version, so pruning is a judgement\ncall, not "
        "automatic. Always regenerate and diff the tree after editing."
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
