#!/usr/bin/env python3
"""Pre-apply safety gate for a consolidation plan.

Reads the terraform plan JSON and asserts the invariants a Geni-merge
reconciliation must hold before `terraform apply`, turning the manual "grep the plan
for destroys" review into an automated gate:

  * 0 geni_profile deletes — a fold MOVEs the keeper and removed{destroy=false}
    the rest. A profile delete means a real Geni profile would be deleted: the
    keeper-pin gotcha (a record sorted to profile_names[0] alongside an
    already-in-state canonical), or a DSL rename with no moved block.
  * 0 geni_union deletes that still hold children on Geni — destroying such a
    union detaches its children; it needs a moved (preserve the id) or a
    removed{destroy=false}. A CHILDLESS union destroy+create is within-tree-safe
    (reported as a warning, not a failure).
  * 0 geni_document force-replaces — a replace loses the Geni doc id/created_at;
    push the text via `verso.ru.consolidation.document_sync` first.
  * 0 field erasures — an in-place update that EMPTIES a field Geni holds: a
    co-author's surname, baptism or wedding date the config does not carry, a
    wife detached from her union, or a value the generator stopped emitting (a
    fold that lost a card's occupation). The four checks above never compare
    values, so a plan they pass could still erase all of that. `--allow-erasure`
    (`verso verify-plan --allow-erasure`) is the acknowledgement for an intended loss:
    the erasures stay in the report, as warnings, and nothing else is relaxed.

Pure/plan-driven (no network): the union child counts come from the plan's
`before.children`, so the gate is deterministic and unit-testable.

Exit code: 1 if any ERROR-level violation, else 0.

Usage (from a village dir, or the repo root with --village):
  python3 -m verso.ru.consolidation.verify_plan
  python3 -m verso.ru.consolidation.verify_plan --village "Нижняя Яичница"
  python3 -m verso.ru.consolidation.verify_plan --plan path/to/_plan.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from verso.ru.consolidation.plan import export_command, plan_paths


@dataclass(frozen=True)
class Violation:
    severity: str  # "error" | "warning"
    kind: str
    address: str
    detail: str


def _actions(rc: dict[str, Any]) -> list[str]:
    return (rc.get("change") or {}).get("actions") or []


def _is_delete(rc: dict[str, Any]) -> bool:
    return _actions(rc) == ["delete"]


def _is_replace(rc: dict[str, Any]) -> bool:
    a = _actions(rc)
    return "delete" in a and "create" in a


def _live_union_id_groups(plan: dict[str, Any]) -> dict[str, list[str]]:
    """geni_union Geni id → [live resource addresses] for unions that will still
    exist after apply with a KNOWN existing id (no-op / update). >1 address for
    one id means Geni fused two unions (their partners were merged) and two
    resources now claim it — the "Marriage already has two partners" collision.
    Only visible on a REFRESHED plan (pre-refresh state still has distinct ids).
    """
    groups: dict[str, list[str]] = {}
    for rc in plan.get("resource_changes") or []:
        if rc.get("type") != "geni_union":
            continue
        if _actions(rc) not in (["no-op"], ["update"]):
            continue  # create/replace ids are unknown; delete/forget won't exist
        ch = rc.get("change") or {}
        uid = ((ch.get("after") or {}).get("id")
               or (ch.get("before") or {}).get("id"))
        if uid:
            groups.setdefault(uid, []).append(rc.get("address", ""))
    return {uid: addrs for uid, addrs in groups.items() if len(addrs) > 1}


def _multi_parent_children(plan: dict[str, Any]) -> dict[str, list[str]]:
    """Children that the POST-APPLY state would place in >1 parent union.

    Read from `planned_values` (what will exist after apply), not from
    `resource_changes` — the offending pair is usually one pre-existing union
    plus one being created, so neither side alone shows the problem.

    A `children: null` union is marriage-only; a union whose `children` key is
    absent is still unknown at plan time (computed at apply) and is skipped —
    a small blind spot, but on a real village plan only a handful of unions are
    unresolved while the rest are fully known.

    The same blind spot applies ELEMENT-WISE: a child profile being created has
    no id yet, so terraform emits `null` inside an otherwise-known children
    list. Those nulls must be dropped, not grouped — several unions each
    awaiting their own new baby are several different children, and bucketing
    them under the shared `None` key reported a phantom "child in 3 parent
    unions" for three unrelated couples.
    """
    owners: dict[str, list[str]] = {}
    root = (plan.get("planned_values") or {}).get("root_module") or {}
    for res in root.get("resources") or []:
        if res.get("type") != "geni_union":
            continue
        values = res.get("values") or {}
        if "children" not in values:
            continue  # unknown until apply
        for child in values.get("children") or []:
            if not child:
                continue  # id unknown until apply — see the docstring
            owners.setdefault(child, []).append(
                res.get("address") or res.get("name") or "?")
    return {c: a for c, a in owners.items() if len(a) > 1}


# Attributes the provider reads back from Geni and never sends (`computed`, or
# `optional,computed` and not written by the generator): an emptied value here is
# a re-read, not a loss. `name` is an event's name, which Geni derives from the
# profile's; `labels` and `content_type` are a document's.
_COMPUTED = frozenset({
    "id", "guid", "created_at", "updated_at", "url", "unions", "deleted",
    "merged_into", "name", "latitude", "longitude", "labels", "content_type",
})
# Compared whole, never field by field: a range narrowed to a point empties
# `range`/`end_year` and loses nothing, and a `place_name` giving way to our
# structured address of the same place empties `place_name` and loses nothing.
_ATOMIC = frozenset({"date", "location", "current_residence"})


def _unknown(unknown: Any) -> bool:
    """Any part of the value is known only after apply."""
    if unknown is True:
        return True
    if isinstance(unknown, dict):
        return any(_unknown(u) for u in unknown.values())
    if isinstance(unknown, list):
        return any(_unknown(u) for u in unknown)
    return False


def _has_content(value: Any, unknown: Any = None) -> bool:
    """Carries something a reader would miss. A flag (`circa`, `alive`) says
    nothing on its own, and a value known only after apply counts as content."""
    if _unknown(unknown):
        return True
    if isinstance(value, dict):
        u = unknown if isinstance(unknown, dict) else {}
        return any(_has_content(v, u.get(k)) for k, v in value.items()
                   if k not in _COMPUTED)
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _show(value: Any) -> str:
    if isinstance(value, dict):
        value = {k: v for k, v in value.items()
                 if k not in _COMPUTED and _has_content(v)}
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= 60 else text[:57] + "..."


def _erased(before: Any, after: Any, unknown: Any,
            path: tuple[str, ...]) -> list[tuple[tuple[str, ...], str]]:
    """(path, what is lost) for every part of `before` the update empties.

    A part known only after apply is skipped; its known siblings are not — every
    refreshed profile update has an unknown `unions`."""
    if unknown is True or not _has_content(before):
        return []
    if isinstance(before, list):
        after_list: list[Any] = after if isinstance(after, list) else []
        lost = [m for m in before if m not in after_list]
        gained = [m for m in after_list if m not in before]  # a null is a member being created
        if len(lost) > len(gained):
            return [(path, f"−{len(lost) - len(gained)} of {len(before)}: "
                           + ", ".join(str(m) for m in lost))]
        return []
    if not _has_content(after, unknown):
        return [(path, _show(before))]
    if not isinstance(before, dict) or (path and path[-1] in _ATOMIC):
        return []  # a changed value, or a date/location reshaped: not an erasure
    after_dict: dict[str, Any] = after if isinstance(after, dict) else {}
    u = unknown if isinstance(unknown, dict) else {}
    found: list[tuple[tuple[str, ...], str]] = []
    for key, value in before.items():
        if key not in _COMPUTED:
            found += _erased(value, after_dict.get(key), u.get(key), path + (key,))
    return found


def _at(value: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _erasures(plan: dict[str, Any], severity: str) -> list[Violation]:
    """In-place updates that empty a field Geni holds.

    Only an `update` can: `forget` releases a resource (removed{destroy=false}),
    and a delete or replace is the structural checks' business. Whose value it
    is comes from the refresh — a value `resource_drift` brought in was edited on
    Geni since the last apply (a co-author, or a merge); any other one this config
    applied earlier and no longer carries. A fast plan (-refresh=false) sees only
    the second kind.
    """
    stored = {d.get("address"): (d.get("change") or {}).get("before") or {}
              for d in plan.get("resource_drift") or []}
    violations: list[Violation] = []
    for rc in plan.get("resource_changes") or []:
        if _actions(rc) != ["update"]:
            continue
        ch = rc.get("change") or {}
        before = ch.get("before") or {}
        found = _erased(before, ch.get("after") or {}, ch.get("after_unknown") or {}, ())
        if not found:
            continue
        addr = rc.get("address", "")
        items: list[str] = []
        for path, lost in found:
            edited = addr in stored and _at(stored[addr], path) != _at(before, path)
            whose = ("edited on Geni since the last apply" if edited
                     else "applied from this config before")
            items.append(f"{'.'.join(path)} «{lost}» ({whose})")
        violations.append(Violation(
            severity, "field_erasure", addr,
            "would EMPTY what Geni holds: " + "; ".join(items)
            + " — keep it (additional_info, or fix the generator that dropped it), "
              "or, if the loss is intended, apply with erase_ok=1",
        ))
    return violations


def check_plan(plan: dict[str, Any], *,
               allow_erasure: bool = False) -> list[Violation]:
    """Return the consolidation-safety violations in a terraform plan.

    `allow_erasure` reports a field erasure as a warning instead of an error —
    the acknowledgement for a loss that is intended. It touches no other check.
    """
    violations: list[Violation] = _erasures(
        plan, "warning" if allow_erasure else "error")
    for child, addrs in sorted(_multi_parent_children(plan).items()):
        violations.append(Violation(
            "error", "multi_parent_child", child,
            f"would end up in {len(addrs)} parent unions "
            f"({', '.join(sorted(addrs))}) — that IS a Geni duplicate_parents "
            "conflict, created by the apply. Usually a per-record parent stub "
            "(a death/birth record naming the same father) that was never "
            "folded into his canonical: add the record to the canonical's "
            "profile_names, then removed{destroy=false} the now-collapsed "
            "per-record union",
        ))
    for uid, addrs in sorted(_live_union_id_groups(plan).items()):
        violations.append(Violation(
            "error", "union_shared_id", ", ".join(sorted(addrs)),
            f"{len(addrs)} live union resources share Geni id {uid} — Geni fused "
            "the unions when their partners merged; one resource must keep it and "
            "the other(s) need a moved/removed block or a `state rm` before apply "
            "(else apply fails with 'Marriage already has two partners')",
        ))
    for rc in plan.get("resource_changes") or []:
        rtype = rc.get("type")
        addr = rc.get("address", "")
        if rtype == "geni_profile" and _is_delete(rc):
            violations.append(Violation(
                "error", "profile_delete", addr,
                "a real Geni profile would be DELETED — a fold must moved the "
                "keeper + removed{destroy=false} the rest (check the keeper pin), "
                "or a renamed record needs a moved block",
            ))
        elif rtype == "geni_union" and _is_delete(rc):
            before = (rc.get("change") or {}).get("before") or {}
            children = before.get("children") or []
            if children:
                violations.append(Violation(
                    "error", "union_delete_with_children", addr,
                    f"union still holds {len(children)} child(ren) on Geni — a "
                    "plain destroy would detach them; use a moved (preserve the "
                    "id) or removed{destroy=false}",
                ))
            else:
                violations.append(Violation(
                    "warning", "union_delete", addr,
                    "childless union destroy+create (within-tree usually safe; "
                    "add a moved/removed block to preserve the Geni id)",
                ))
        elif rtype == "geni_document" and _is_replace(rc):
            violations.append(Violation(
                "error", "document_replace", addr,
                "force-replace loses the Geni doc id/created_at — push the text "
                "via `verso document-sync` first",
            ))
    return violations


def format_report(violations: list[Violation]) -> str:
    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]
    lines: list[str] = []
    for v in violations:
        marker = "ERROR" if v.severity == "error" else "warn "
        lines.append(f"{marker}  {v.kind:26}  {v.address}")
        lines.append(f"         {v.detail}")
    if not errors:
        lines.append(
            "consolidation plan OK: no profile deletes, no union-with-children "
            "destroys, no document replaces, no child left with two parents, "
            "no field emptied."
        )
    lines.append(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    return "\n".join(lines)


def plan_json_is_stale(paths: Any) -> bool:
    """True if `_plan.json` exists but is older than the `.plan` it should mirror
    (both present). A `terraform plan` that didn't re-export leaves it behind."""
    if not (paths.plan_bin.exists() and paths.plan_json.exists()):
        return False
    return paths.plan_json.stat().st_mtime < paths.plan_bin.stat().st_mtime


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pre-apply safety gate for a consolidation plan."
    )
    ap.add_argument("--village", default=None, help="village dir (default: cwd)")
    ap.add_argument("--plan", default=None,
                    help="plan JSON path (overrides the --village default)")
    ap.add_argument("--allow-erasure", action="store_true",
                    help="report field erasures as warnings, not errors — for a "
                         "loss that is intended (verso verify-plan --allow-erasure)")
    ap.add_argument("--json", action="store_true",
                    help="emit the violations as JSON instead of the human report "
                         "(used by verso.ru.consolidation.apply_converge, which halts or "
                         "continues based on the `kind` field)")
    args = ap.parse_args()

    if args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    else:
        paths = plan_paths(args.village)
        # Guard the footgun: `terraform plan` writes .plan but does NOT re-export
        # _plan.json, so a hand `terraform plan` after editing _moved_*.tf leaves a
        # STALE _plan.json — the gate would verify a plan that no longer matches.
        if plan_json_is_stale(paths):
            print(f"ERROR  stale_plan_json  {paths.plan_json} is older than "
                  f"{paths.plan_bin} — re-export before verifying:\n"
                  f"         {export_command(paths.village_dir)}", file=sys.stderr)
            return 1
        plan = paths.load_json()

    violations = check_plan(plan, allow_erasure=args.allow_erasure)
    if args.json:
        print(json.dumps([asdict(v) for v in violations], ensure_ascii=False, indent=2))
    else:
        print(format_report(violations))
    return 1 if any(v.severity == "error" for v in violations) else 0


if __name__ == "__main__":
    sys.exit(main())
