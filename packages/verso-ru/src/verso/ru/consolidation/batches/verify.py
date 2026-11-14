#!/usr/bin/env python3
"""Verify that a saved terraform plan only mutates allowlisted fields.

Called by `Горюхино/batches/apply_approved.sh` after a `-target=` plan,
before apply. Halts the apply if:
  * any resource action is `delete` (and `create` unless `--allow-creates`),
  * any update touches a top-level field outside the `--allow` allowlist.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from verso.core.tools import tool

VILLAGE_DIR = Path.cwd()  # village dir (run from the village; apply_approved.sh cds there)
TF_DIR = VILLAGE_DIR / "terraform" / "geni"


def cmd_verify_plan(args: argparse.Namespace) -> int:
    """Show which top-level fields are being modified by a saved plan.

    Reads `terraform show -json <planfile>` and walks `resource_changes`.
    For each resource action, shows: action, count of resources, and the
    set of top-level fields that differ between `before` and `after`.

    Allowlist (--allow): comma-separated list of field names that are OK
    to change (e.g. `projects,baptism,birth` for the import-block path).
    Returns exit code 1 if ANY change touches a non-allowlisted field.
    """
    planfile = args.planfile
    result = subprocess.run(
        [tool("terraform"), f"-chdir={TF_DIR}", "show", "-json", planfile],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"terraform show failed: {result.stderr}", file=sys.stderr)
        return 2

    plan = json.loads(result.stdout)
    changes = plan.get("resource_changes", []) or []

    allow_set = {f.strip() for f in (args.allow or "").split(",") if f.strip()}

    # action_type → field_name → count
    action_field_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    action_counts: dict[str, int] = defaultdict(int)
    unexpected_examples: dict[str, list[str]] = defaultdict(list)

    for ch in changes:
        actions = ch.get("change", {}).get("actions", [])
        action_key = "+".join(actions)
        action_counts[action_key] += 1
        before = ch.get("change", {}).get("before") or {}
        after = ch.get("change", {}).get("after") or {}
        # Only deep-diff for update-shaped actions; create/delete are obvious.
        if "update" in actions or actions == ["no-op"]:
            changed_fields: list[str] = []
            for k in set(before.keys()) | set(after.keys()):
                if before.get(k) != after.get(k):
                    changed_fields.append(k)
            for k in changed_fields:
                action_field_counts[action_key][k] += 1
            unexpected = [k for k in changed_fields if k not in allow_set]
            if unexpected and len(unexpected_examples[action_key]) < 5:
                addr = ch.get("address", "?")
                unexpected_examples[action_key].append(
                    f"  {addr}: {sorted(unexpected)}"
                )

    print(f"Resource actions in {planfile}:")
    for action, count in sorted(action_counts.items()):
        print(f"  {action:30}{count}")

    print("\nFields changed (per action):")
    for action, fields in sorted(action_field_counts.items()):
        print(f"  {action}:")
        for fld, cnt in sorted(fields.items(), key=lambda x: -x[1]):
            marker = "  " if fld in allow_set else "⚠ "
            print(f"    {marker}{fld:25}{cnt}")

    # Reject create/delete actions by default — those mutate Geni. With
    # --allow-creates, allow creates but still reject deletes (so dependency
    # profile/union creates pulled in by -target= can be applied alongside
    # update-shaped doc changes).
    forbidden_actions: set[str] = {"delete"}
    if not args.allow_creates:
        forbidden_actions.add("create")
    forbidden_count = sum(
        cnt for action, cnt in action_counts.items()
        if any(a in forbidden_actions for a in action.split("+"))
    )
    if forbidden_count:
        word = "create/delete" if not args.allow_creates else "delete"
        print(f"\n⚠ {forbidden_count} resource(s) slated for {word} — "
              "would mutate Geni. Halting.")
        for ch in changes:
            actions = ch.get("change", {}).get("actions", [])
            if any(a in forbidden_actions for a in actions):
                print(f"  {'+'.join(actions):10} {ch.get('address', '?')}")
                if forbidden_count > 20:
                    break
    if args.allow_creates:
        create_count = sum(
            cnt for action, cnt in action_counts.items()
            if "create" in action.split("+") and "delete" not in action.split("+")
        )
        if create_count:
            print(f"\n   (allow-creates: {create_count} dependency create(s) "
                  "permitted alongside updates)")

    unexpected_total = sum(
        cnt for fields in action_field_counts.values()
        for fld, cnt in fields.items() if fld not in allow_set
    )
    if unexpected_total:
        print(f"\n⚠ {unexpected_total} unexpected field change(s) (not in allowlist).")
        for action, examples in unexpected_examples.items():
            print(f"\n  {action} examples:")
            for ex in examples:
                print(ex)

    if forbidden_count or unexpected_total:
        return 1
    if allow_set:
        print(f"\n✓ All field changes are in allowlist ({sorted(allow_set)}).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="verify_plan",
        description=__doc__.split("\n\n")[0] if __doc__ else None,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser(
        "verify-plan",
        help="Show field-level changes in a saved binary plan; exit 1 if "
             "any change touches a non-allowlisted field",
    )
    pv.add_argument("planfile", help="Path to a saved terraform plan file")
    pv.add_argument(
        "--allow", default="projects,baptism,birth",
        help="Comma-separated allowlist of top-level field names that may change",
    )
    pv.add_argument(
        "--allow-creates", action="store_true",
        help="Allow create actions in the plan (still rejects deletes). Use when "
             "targeted updates pull in profile/union creates as dependencies.",
    )
    pv.set_defaults(func=cmd_verify_plan)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
