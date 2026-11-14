"""Pre-apply audit: surface Geni-side pending tree/record/smart matches that
touch profiles managed by this Terraform project.

Geni's auto-matcher periodically suggests duplicate-candidate profiles for our
managed profiles. Those matches are the signal that a real-world person ended
up represented by two or more `geni_profile` resources — usually because the
same person was extracted from several metric-book records and each event
created a fresh profile.

This script:
1. Calls `geni matches list` once to get all pending matches the API knows
   about for the authenticated user.
2. Loads `_plan.json` to discover which guids appear in the project (either
   already in state or being created in this plan).
3. Reports the intersection so a merge or consolidation decision can be made
   before apply.

Usage:
    # after `terraform -chdir=terraform/geni show -json .plan > _plan.json` (from the village's directory) populates _plan.json
    python3 Горюхино/batches/audit_pending_matches.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from verso.ru.consolidation.plan import plan_paths
from verso.core.tools import tool



def fetch_pending_matches() -> list[dict[str, Any]]:
    result = subprocess.run(
        [tool("geni"), "matches", "list"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"geni matches list failed: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout) or []
    except json.JSONDecodeError:
        return []


def plan_profile_guids(plan: dict[str, Any]) -> set[str]:
    """All guids referenced by geni_profile resources in plan or prior state."""
    guids: set[str] = set()
    for rc in plan.get("resource_changes", []):
        if rc.get("type") != "geni_profile":
            continue
        for slot in ("before", "after"):
            v = rc["change"].get(slot) or {}
            g = v.get("guid")
            if g:
                guids.add(str(g))
    return guids


def main() -> int:
    matches = fetch_pending_matches()
    if not matches:
        print("No pending matches reported by Geni.")
        return 0

    project_guids = plan_profile_guids(plan_paths().load_json())

    relevant = [m for m in matches if m.get("profile_guid") in project_guids]
    foreign = [m for m in matches if m.get("profile_guid") not in project_guids]

    if not relevant:
        print(f"{len(matches)} pending Geni match(es), none touch Terraform-managed profiles.")
        return 0

    print(f"Found {len(relevant)} Terraform-managed profile(s) with pending Geni matches:\n")
    for m in relevant:
        guid = m["profile_guid"]
        name = m.get("name", "")
        life = m.get("lifespan_text", "")
        t = m.get("tree_match_count", 0)
        r = m.get("record_match_count", 0)
        s = m.get("smart_match_count", 0)
        print(f"  {guid}  {name}  {life}")
        print(f"    matches: tree={t} record={r} smart={s}")
        print(f"    inspect: geni matches for-profile {guid}")
        print()

    if foreign:
        print(f"({len(foreign)} additional pending match(es) outside this project — ignored.)")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
