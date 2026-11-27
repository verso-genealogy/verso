#!/usr/bin/env python3
"""Categorize external Geni drift from a saved Terraform plan.

Turns the manual `terraform show -json .plan | jq ...` triage into one command. Reads the JSON plan for a village's geni module and buckets
every externally-changed / to-be-changed resource into the reconciliation classes,
printing the fix recipe per class:

  MERGE            profile/union id or guid changed  → fold into the canonical
                   (add to profiles_to_consolidate, hand-author removed{destroy=false})
  PROJECT-REPLACE  projects delta forces a replace   → pin via additional_info if the
                   membership is an explicit link, else it's a co-author location-association
                   (apply "access denied") → needs lifecycle ignore_changes / accept replace
  CONTENT          a real value differs — a name field, an event's date or place, unions, about … →
                   preserve via additional_info (last_name / GeniEvent), or update the DSL
  DERIVED-NAME     only an event's *name* recomputed («Birth of …», the rest of it identical) →
                   cosmetic Geni-derived churn, safe to leave

Without a drift block (no refresh, or nothing changed on Geni) the plan's resource_changes are read
instead: its no-ops are skipped, and so is a value the plan leaves to be computed (`after_unknown`).

Usage:
    python -m verso.ru.consolidation.drift <village>/terraform/geni [--plan .plan]
    # or pipe a plan JSON:
    terraform -chdir=<dir> show -json .plan | python -m verso.ru.consolidation.drift -
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from typing import Any
from verso.core.tools import tool


def _load_plan(arg: str, plan_file: str) -> dict[str, Any]:
    if arg == "-":
        return json.load(sys.stdin)
    out = subprocess.run(
        [tool("terraform"), f"-chdir={arg}", "show", "-json", plan_file],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


# A profile's events: Geni recomputes an event's `name` («Birth of …») from the profile's names, so a
# difference in it alone is derived churn; every other field of the event is a real value.
_EVENTS = ("birth", "baptism", "death", "burial")
# Compared on their own (MERGE, PROJECT-REPLACE) before the content is.
_IDENTITY = ("id", "guid", "projects")


def _known(before: Any, after: Any, unknown: Any) -> Any:
    """`after` with each value the plan leaves unknown (`after_unknown`: computed on apply) taken from
    `before`: a value yet to be computed is no difference."""
    if unknown is True:
        return before
    if isinstance(unknown, dict) and isinstance(after, dict):
        b = before if isinstance(before, dict) else {}
        return {k: _known(b.get(k), v, unknown.get(k)) for k, v in after.items()} | {
            k: b.get(k) for k, u in unknown.items() if u is True and k not in after}
    return after


def _event(ev: Any) -> Any:
    return {k: v for k, v in ev.items() if k != "name"} if isinstance(ev, dict) else ev


def _names_diff(before: Any, after: Any) -> list[str]:
    """The name fields that differ, `ru.last_name`-style, over every locale."""
    b, a = before or {}, after or {}
    out = []
    for loc in sorted(set(b) | set(a)):
        bl, al = b.get(loc) or {}, a.get(loc) or {}
        out += [f"{loc}.{f}" for f in sorted(set(bl) | set(al)) if bl.get(f) != al.get(f)]
    return out


def classify(before: dict[str, Any], after: dict[str, Any],
             unknown: dict[str, Any] | None = None) -> tuple[str, str] | None:
    """Return (category, detail) for one resource change/drift, None when nothing differs: a no-op of the
    plan, or a change whose every difference is a value yet to be computed (`unknown`, the plan's
    `after_unknown`)."""
    after = _known(before, after, unknown or {})
    if before.get("id") != after.get("id") or before.get("guid") != after.get("guid"):
        return "MERGE", f"id {before.get('id')} → {after.get('id')}"
    if (before.get("projects") or []) != (after.get("projects") or []):
        b, a = set(before.get("projects") or []), set(after.get("projects") or [])
        return "PROJECT-REPLACE", f"+{sorted(b - a) or sorted(a - b)}"
    # real content vs derived-name-only
    real, derived = [], []
    for key in sorted(set(before) | set(after)):
        b, a = before.get(key), after.get(key)
        if key in _IDENTITY or b == a:
            continue
        if key == "names":
            real += _names_diff(b, a)
        elif key in _EVENTS:
            (real if _event(b) != _event(a) else derived).append(key)
        else:
            real.append(key)
    if real:
        return "CONTENT", ",".join(real)
    if derived:
        return "DERIVED-NAME", "event name recompute only"
    return None


_RECIPE = {
    "MERGE": "fold into the canonical (profiles_to_consolidate + removed{destroy=false})",
    "PROJECT-REPLACE": "additional_info projects if an EXPLICIT member; a co-author "
                       "location-association can't be linked (apply access-denied) → "
                       "lifecycle ignore_changes / accept the non-destructive replace",
    "CONTENT": "preserve the co-author value via additional_info (last_name / GeniEvent)",
    "DERIVED-NAME": "cosmetic Geni-recomputed event name — safe to leave",
}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    plan_file = ".plan"
    if "--plan" in args:
        i = args.index("--plan")
        plan_file = args[i + 1]
        args = args[:i] + args[i + 2:]
    plan = _load_plan(args[0], plan_file)

    # Drift (external Geni changes detected on refresh) is the authoritative view;
    # fall back to resource_changes when no drift block is present.
    buckets: dict[str, list[str]] = defaultdict(list)
    # A no-op or a read of resource_changes changes nothing: without a drift block every resource of the
    # plan is listed there, and each no-op once counted as DERIVED-NAME (В18).
    for d in plan.get("resource_drift") or plan.get("resource_changes") or []:
        ch = d.get("change") or {}
        if ch.get("actions") in (["no-op"], ["read"]):
            continue
        before, after = ch.get("before") or {}, ch.get("after") or {}
        found = classify(before, after, ch.get("after_unknown"))
        if found is None:
            continue
        cat, detail = found
        buckets[cat].append(f"  {d['address']}  ({detail})")

    order = ["MERGE", "PROJECT-REPLACE", "CONTENT", "DERIVED-NAME"]
    total = sum(len(v) for v in buckets.values())
    if plan.get("resource_drift"):
        print(f"External drift: {total} resource(s)\n")
    else:
        print(f"External drift: none in the plan; planned changes: {total} resource(s)\n")
    for cat in order:
        rows = buckets.get(cat, [])
        if not rows:
            continue
        print(f"── {cat} ({len(rows)}) — {_RECIPE[cat]}")
        print("\n".join(sorted(rows)))
        print()
    for cat in buckets:  # any unexpected category
        if cat not in order:
            print(f"── {cat} ({len(buckets[cat])})")
            print("\n".join(sorted(buckets[cat])))

    # Planned replaces (delete+create) live in resource_changes, not resource_drift.
    # They read as scary but are non-destructive (the provider re-adopts by guid);
    # almost always projects-forced — the PROJECT-REPLACE class.
    replaces = [c["address"] for c in (plan.get("resource_changes") or [])
                if (c.get("change") or {}).get("actions") == ["delete", "create"]]
    if replaces:
        print(f"\n── PLANNED-REPLACE ({len(replaces)}) — non-destructive (provider "
              f"re-adopts by guid); usually projects-forced (PROJECT-REPLACE)")
        print("\n".join(f"  {a}" for a in sorted(replaces)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
