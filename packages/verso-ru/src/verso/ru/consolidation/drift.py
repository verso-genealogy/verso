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
  CONTENT          a real names/birth/death/baptism value differs → preserve via
                   additional_info (last_name / GeniEvent), or update the DSL
  DERIVED-NAME     only a birth/death event *name* recomputed (dates identical) → cosmetic
                   Geni-derived churn, safe to leave

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


def _date(ev: dict[str, Any] | None) -> tuple[Any, ...] | None:
    d = (ev or {}).get("date") if ev else None
    if not d:
        return None
    return (d.get("day"), d.get("month"), d.get("year"), d.get("range"))


def _last_name(names: dict[str, Any] | None) -> str:
    return (((names or {}).get("ru") or {}).get("last_name")) or ""


def classify(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, str]:
    """Return (category, detail) for one resource change/drift."""
    if before.get("id") != after.get("id") or before.get("guid") != after.get("guid"):
        return "MERGE", f"id {before.get('id')} → {after.get('id')}"
    if (before.get("projects") or []) != (after.get("projects") or []):
        b, a = set(before.get("projects") or []), set(after.get("projects") or [])
        return "PROJECT-REPLACE", f"+{sorted(b - a) or sorted(a - b)}"
    # real content vs derived-name-only
    real = []
    if _last_name(before.get("names")) != _last_name(after.get("names")):
        real.append("last_name")
    for f in ("birth", "baptism", "death"):
        if _date(before.get(f)) != _date(after.get(f)):
            real.append(f)
    if real:
        return "CONTENT", ",".join(real)
    return "DERIVED-NAME", "event name recompute only"


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
    for d in plan.get("resource_drift") or plan.get("resource_changes") or []:
        ch = d.get("change") or {}
        before, after = ch.get("before") or {}, ch.get("after") or {}
        cat, detail = classify(before, after)
        buckets[cat].append(f"  {d['address']}  ({detail})")

    order = ["MERGE", "PROJECT-REPLACE", "CONTENT", "DERIVED-NAME"]
    total = sum(len(v) for v in buckets.values())
    print(f"External drift: {total} resource(s)\n")
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
