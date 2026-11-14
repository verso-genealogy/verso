#!/usr/bin/env python3
"""Triage the geni_union deletes/replaces in a consolidation plan.

After folding profiles, per-record unions churn. This report classifies each
churned union straight from the plan payload (no Geni call) so the dangerous
ones are obvious before you hand-author `_moved_consolidated_unions.tf`:

  * husk          0 partners / 0 children  → safe destroy+create, no block needed
  * live-couple   partners, 0 children     → prefer a `moved` to keep the Geni id
  * live-children any children             → DANGER: needs a `moved` or
                                             removed{destroy=false}; a plain
                                             destroy detaches the children

Partner/children profile ids are resolved to their terraform resource names by
scanning the plan's own geni_profile changes, so the output is human-readable
(the manual `curl …/api/union-NNN` step this replaces returned bare ids).

A second section flags **mis-bindings**: a geni_union *update* where the partner
set AND the children set both change means this resource is bound to a different
couple's Geni union. That diff looks like a duplicate-profile pair to a naive
merge-worklist extractor, but the two partners are two different people — see
`collect_union_rebinds`.

Run it on a refreshed post-fold plan (`terraform -chdir=terraform/geni show -json .plan > _plan.json` from the village's directory, then this), or via
`verso triage-unions --village <v>`. Always exits 0 — it is a report, not a gate
(use `verso verify-plan` for the pass/fail gate).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verso.ru.consolidation.plan import plan_paths


@dataclass(frozen=True)
class UnionRebind:
    address: str
    union_id: str | None
    partners_removed: list[str]
    partners_added: list[str]
    children_removed: list[str]
    children_added: list[str]


@dataclass(frozen=True)
class UnionTriage:
    address: str
    action: str            # "delete" | "replace"
    union_id: str | None
    partners: list[str]    # resolved resource names (raw ids if unresolved)
    children: list[str]
    classification: str    # "husk" | "live-couple" | "live-children"


def _resource_name(address: str) -> str:
    return address.split(".", 1)[1] if "." in address else address


def _profile_id_to_name(plan: dict[str, Any]) -> dict[str, str]:
    """Map profile-NNN id → terraform resource name from the plan's geni_profile
    changes, so union partner/children ids render as readable names."""
    out: dict[str, str] = {}
    for rc in plan.get("resource_changes") or []:
        if rc.get("type") != "geni_profile":
            continue
        name = _resource_name(rc.get("address", ""))
        change = rc.get("change") or {}
        for side in ("before", "after"):
            pid = (change.get(side) or {}).get("id")
            if pid:
                out.setdefault(pid, name)
    return out


def _resolve(ids: Any, id_to_name: dict[str, str]) -> list[str]:
    if not isinstance(ids, list):
        return []
    return [str(id_to_name.get(i, i)) for i in ids]


def _classify(partners: list[str], children: list[str]) -> str:
    if children:
        return "live-children"
    if partners:
        return "live-couple"
    return "husk"


def collect_union_triage(plan: dict[str, Any]) -> list[UnionTriage]:
    """Classify every geni_union the plan would delete or replace."""
    id_to_name = _profile_id_to_name(plan)
    triage: list[UnionTriage] = []
    for rc in plan.get("resource_changes") or []:
        if rc.get("type") != "geni_union":
            continue
        actions = (rc.get("change") or {}).get("actions") or []
        if actions == ["delete"]:
            action = "delete"
        elif "delete" in actions and "create" in actions:
            action = "replace"
        else:
            continue
        before = (rc.get("change") or {}).get("before") or {}
        partners = _resolve(before.get("partners"), id_to_name)
        children = _resolve(before.get("children"), id_to_name)
        triage.append(UnionTriage(
            address=rc.get("address", ""),
            action=action,
            union_id=before.get("id"),
            partners=partners,
            children=children,
            classification=_classify(partners, children),
        ))
    triage.sort(key=lambda t: (t.classification, t.address))
    return triage


def _delta(before: Any, after: Any, id_to_name: dict[str, str]) -> tuple[list[str], list[str]]:
    """(removed, added) between two id lists, resolved to resource names."""
    b = set(before) if isinstance(before, list) else set()
    a = set(after) if isinstance(after, list) else set()
    return (sorted(_resolve(sorted(b - a), id_to_name)),
            sorted(_resolve(sorted(a - b), id_to_name)))


def collect_union_rebinds(plan: dict[str, Any]) -> list[UnionRebind]:
    """Flag every geni_union update where the partner set AND the children set
    both change — the signature of a **mis-binding**: this terraform resource
    is bound to the Geni union of a *different* couple.

    A benign duplicate fold changes only the partner (an id remapping to its
    canonical) and leaves the children alone; a newly transcribed child changes
    only the children. When both move together, the two partners are two
    different people, and "merging" them to flatten the diff destroys one of
    them — see the incident where the census half of a second wife
    was merged into the first wife. The fix is to re-bind the
    union (state rm + import the correct union id, or a `moved` block), never
    `geni profile merge`."""
    id_to_name = _profile_id_to_name(plan)
    rebinds: list[UnionRebind] = []
    for rc in plan.get("resource_changes") or []:
        if rc.get("type") != "geni_union":
            continue
        change = rc.get("change") or {}
        if (change.get("actions") or []) != ["update"]:
            continue
        before = change.get("before") or {}
        after = change.get("after") or {}
        p_removed, p_added = _delta(before.get("partners"), after.get("partners"), id_to_name)
        c_removed, c_added = _delta(before.get("children"), after.get("children"), id_to_name)
        if not (p_removed or p_added) or not (c_removed or c_added):
            continue
        rebinds.append(UnionRebind(
            address=rc.get("address", ""),
            union_id=before.get("id") or after.get("id"),
            partners_removed=p_removed,
            partners_added=p_added,
            children_removed=c_removed,
            children_added=c_added,
        ))
    rebinds.sort(key=lambda r: r.address)
    return rebinds


def format_rebinds(rebinds: list[UnionRebind]) -> str:
    if not rebinds:
        return "no union re-binding suspects (no partner+children co-change)."
    lines = [
        f"{len(rebinds)} suspected union MIS-BINDING (partner AND children both change):",
        "",
    ]
    for r in rebinds:
        uid = f" [{r.union_id}]" if r.union_id else ""
        lines.append(f"  {_resource_name(r.address)}{uid}")
        lines.append(f"    partners  -{r.partners_removed} +{r.partners_added}")
        lines.append(f"    children  -{r.children_removed} +{r.children_added}")
        lines.append("    → this resource is bound to ANOTHER couple's Geni union; "
                     "do NOT merge the two partners")
        lines.append("      (they are different people) — re-bind the union instead: "
                     "state rm + import the correct union id, or a moved block.")
    return "\n".join(lines)


_ADVICE = {
    "live-children": "DANGER: moved (preserve id) or removed{destroy=false} — a plain destroy detaches children",
    "live-couple": "prefer a moved block to keep the Geni union id",
    "husk": "safe: destroy+create, no block needed",
}


def format_triage(triage: list[UnionTriage]) -> str:
    if not triage:
        return "no geni_union deletes/replaces in this plan."
    order = {"live-children": 0, "live-couple": 1, "husk": 2}
    counts = {k: sum(1 for t in triage if t.classification == k) for k in order}
    lines = [
        f"{len(triage)} geni_union delete(s)/replace(s): "
        + ", ".join(f"{counts[k]} {k}" for k in order),
        "",
    ]
    for t in sorted(triage, key=lambda x: (order[x.classification], x.address)):
        uid = f" [{t.union_id}]" if t.union_id else ""
        lines.append(f"{t.classification:13} {t.action:7} {_resource_name(t.address)}{uid}")
        lines.append(f"              partners={t.partners or '[]'}  children={t.children or '[]'}")
        lines.append(f"              → {_ADVICE[t.classification]}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Triage geni_union deletes/replaces in a consolidation plan."
    )
    ap.add_argument("--village", default=None, help="village dir (default: cwd)")
    ap.add_argument("--plan", default=None,
                    help="plan JSON path (overrides the --village default)")
    args = ap.parse_args()

    if args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    else:
        plan = plan_paths(args.village).load_json()

    print(format_triage(collect_union_triage(plan)))
    print()
    print(format_rebinds(collect_union_rebinds(plan)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
