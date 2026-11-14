"""Pre-apply audit: for every union the plan wants to create, ask Geni whether
the same couple already has a union there. If so, the create will almost
certainly fail with "Error adding child" (Geni rejects attaching a child that
already has parents elsewhere) — recommend `terraform import` instead.

Usage:
    # after `terraform -chdir=terraform/geni show -json .plan > _plan.json` (from the village's directory) populates _plan.json
    python3 Горюхино/batches/audit_existing_unions.py

Skips creates whose partners are still `(known after apply)` (i.e. both
partners are being created in the same apply — nothing to look up yet).
"""

from __future__ import annotations

import json
import subprocess
from typing import Any
from verso.ru.consolidation.plan import plan_paths
from verso.core.tools import tool



def union_creates(plan):
    for rc in plan["resource_changes"]:
        if rc.get("type") != "geni_union":
            continue
        if rc["change"]["actions"] != ["create"]:
            continue
        partners = rc["change"]["after"].get("partners") or []
        # Skip if any partner is unresolved at plan time.
        if any(p is None or not str(p).startswith("profile-") for p in partners):
            continue
        yield rc["address"], partners, rc["change"]["after"].get("children") or []


def shared_unions(profile_a: str, profile_b: str) -> dict[str, Any]:
    """Wrap `geni union intersect` and return its parsed JSON map."""
    result = subprocess.run(
        [tool("geni"), "union", "intersect", profile_a, profile_b],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout) or {}
    except json.JSONDecodeError:
        return {}


def main() -> int:
    plan = plan_paths().load_json()
    findings = []
    for addr, partners, children in union_creates(plan):
        if len(partners) != 2:
            continue  # geni unions are always two-partner; defensive
        shared = shared_unions(partners[0], partners[1])
        if not shared:
            continue
        for uid, body in shared.items():
            geni_kids = set(body.get("children") or [])
            extras = geni_kids - set(children)
            findings.append({
                "address": addr,
                "existing_union": uid,
                "geni_children_count": len(geni_kids),
                "plan_children_count": len(children),
                "extra_on_geni": sorted(extras),
            })

    if not findings:
        print("No pre-existing Geni unions match planned creates. Apply should be clean.")
        return 0

    print(f"Found {len(findings)} planned union(s) that already exist on Geni:\n")
    for f in findings:
        print(f"  {f['address']}")
        print(f"    existing → {f['existing_union']}")
        print(f"    children: {f['plan_children_count']} in plan, {f['geni_children_count']} on Geni")
        if f["extra_on_geni"]:
            print(f"    Geni has {len(f['extra_on_geni'])} child(ren) not in plan:")
            for pid in f["extra_on_geni"]:
                print(f"      - {pid}")
            print(f"    → declare in unions_to_consolidate['{f['address'].split('.', 1)[1]}']['undocumented_children']")
        print(f"    suggested fix: terraform import {f['address']} {f['existing_union']}")
        print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
