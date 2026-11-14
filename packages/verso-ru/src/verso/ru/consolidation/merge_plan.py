#!/usr/bin/env python3
"""The Geni-side work a consolidation apply needs, read off a saved plan.

A fold is two halves of one operation: the config
releases a record's profile from terraform (`removed { destroy = false }`, the
plan's `forget`), and `geni profile merge` folds that still-live profile into
its canonical on Geni. Terraform does the first half and cannot do the second.
Until this module, the second half was worked out by hand from the plan JSON,
with throwaway Python: twelve merges, which eight of them go before the apply,
which four after, five detaches, and which unions Geni would fuse. This prints
that list.

What it reads, and the rules it applies:

1. **Every `geni_profile` the plan forgets is a merge** `keep ← dup`. The dup's
   id is the forgotten resource's `before.id`. The canonical comes from, in
   order: the config (`profiles_to_consolidate[*].profile_names`); an OLD
   res_name of a record the proofread renamed — the same date and record slot
   (`…_mk_births_19_god_parent_1`) as a record the config folds, the case of a
   hand-written `removed` in a `_moved_*_proofread.tf`; the unions the plan
   rebuilds around it (a partner or child swapped for another id of the same
   sex, or a union collapsing into the one its children join) — which is how a
   DISSOLVED canonical key is found, one the config no longer names
   (`canonical_a_1877` → `canonical_a_1874`); and, last, the config's
   own git history, for a dissolved key no union holds. `--into` names one by
   hand. When the config's answer and the unions' disagree the merge is a
   CONFLICT and is never run: the union may be bound to another couple
   (a union mis-binding).

   ⚠ The keeper's id is read under the CANONICAL address. In plan JSON
   `prior_state` and `resource_changes` already apply the `moved` blocks, so the
   keeper record's own res_name addresses nothing; its Geni id stands at the
   canonical's address (`previous_address` = the keeper).

2. **Before or after the apply.** A dup that is a partner or child of a union —
   one the plan re-keys, collapses or rebuilds, or one Geni lists on the
   profile and this state does not manage — is merged BEFORE the apply: state
   holds the union pointing at the stub, and Geni will not swap a partner in a
   full union («Marriage already has two partners»). A dup in no union (a
   godparent, a witness, a surety) is merged AFTER it: merging a profile
   terraform still manages turns its id into a redirect (the batch path:
   apply → merge → apply).

3. **Detaches after the apply.** A forgotten union stays on Geni. When the
   merges give it the same partners as a union the config keeps, Geni fuses the
   two itself; otherwise — a death record's father-only union, a census
   `_rsN_` single-parent union, a couple only one of whom folds — it stays
   beside the canonical marriage, and every child the plan also places in
   another union ends up with two parent unions: `geni profile detach-union`
   after the apply (Geni does not fuse a one-partner union into a parent's
   marriage — which union survives a fusion depends on the order of the merges).
   An update that drops a member from a union needs the same: the provider adds
   partners and children and never takes one out.

4. **`--run-before` / `--run-after`** execute the two halves: each merge with a
   pause (default 1 s), every `X merged into Y` logged to a TSV, and a survivor
   that is not the intended keep reported as a FLIP (Geni picks its own; the
   refresh follows the redirect). Each id is re-read first and followed
   through `merged_into`, so a flip in the first half does not turn the second
   half's merges into the canonical into `403`s on a husk, and a merge already
   done is skipped. After the before-merges every union the plan collapses or
   re-keys is read with `geni union get` (`geni profile unions` returns only
   web ids) and a husk — no partners, no children — is reported: a union the
   config keeps that Geni emptied means the hand-written block points the wrong
   way. `--run-after` merges the godparents, then detaches. `--check-unions`
   is that union check alone, read-only.

Read-only by default: it reads the plan and the config and prints commands.

Usage (from the repo root):
    python3 -m verso.ru.consolidation.merge_plan --village "Глуповы Горы"
    python3 -m verso.ru.consolidation.merge_plan --village X --plan X/terraform/geni/.plan-fast
    verso merge-plan --village X [--plan PATH] [--json] [--run-before | --run-after | --check-unions]
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import subprocess
import shlex
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from verso.core.tools import tool
from verso.ru.consolidation.plan import export_command, plan_command

BEFORE = "before"
AFTER = "after"
DONE = "done"
UNRESOLVED = "unresolved"
CONFLICT = "conflict"

_CHILD_KEYS = ("children", "adopted_children", "foster_children")


# ── The plan, as far as merges care ─────────────────────────────────────────


@dataclass(frozen=True)
class ProfileChange:
    """One `geni_profile` of the plan; `name` is the res_name."""

    name: str
    profile_id: str | None
    gender: str | None
    actions: tuple[str, ...]
    previous: str | None
    unions: tuple[str, ...]  # what Geni listed at the last refresh (managed or not)


@dataclass(frozen=True)
class UnionChange:
    """One `geni_union` of the plan. `after_*` is None when it leaves state."""

    address: str
    previous: str | None
    union_id: str | None
    actions: tuple[str, ...]
    before_partners: tuple[str, ...]
    before_children: tuple[str, ...]
    after_partners: tuple[str | None, ...] | None
    after_children: tuple[str | None, ...] | None

    @property
    def fate(self) -> str:
        a = self.actions
        if a == ("forget",):
            return "collapsed"
        if a == ("delete",):
            return "deleted"
        if "delete" in a and "create" in a:
            return "replaced"
        if a == ("create",):
            return "new"
        if self.previous:
            return "re-keyed"
        if a == ("update",):
            return "updated"
        return "unchanged"

    @property
    def before_members(self) -> tuple[str, ...]:
        return self.before_partners + self.before_children

    def after_known(self) -> set[str]:
        return {m for m in (self.after_partners or ()) + (self.after_children or ()) if m}

    def label(self) -> str:
        return f"{self.union_id or '(new)'} {self.address.removeprefix('geni_union.')}"


@dataclass
class PlanView:
    profiles: dict[str, ProfileChange]
    unions: list[UnionChange]
    genders: dict[str, str]          # profile id → "male" | "female"
    documents_replaced: int

    def gender(self, profile_id: str) -> str | None:
        return self.genders.get(profile_id)

    def name_of(self, profile_id: str) -> str | None:
        """The res_name that holds `profile_id` after the apply."""
        for p in self.profiles.values():
            if p.profile_id == profile_id and p.actions != ("forget",):
                return p.name
        return None


def _ids(value: Any) -> tuple[str, ...]:
    return tuple(v for v in (value or []) if isinstance(v, str))


def _after_ids(value: Any) -> tuple[str | None, ...]:
    return tuple(v if isinstance(v, str) else None for v in (value or []))


def read_plan(plan: Mapping[str, Any]) -> PlanView:
    profiles: dict[str, ProfileChange] = {}
    unions: list[UnionChange] = []
    documents_replaced = 0
    for rc in plan.get("resource_changes") or []:
        ch = rc.get("change") or {}
        actions: tuple[str, ...] = tuple(ch.get("actions") or [])
        if rc.get("type") == "geni_document" and "delete" in actions and "create" in actions:
            documents_replaced += 1
        before = ch.get("before") or {}
        after = ch.get("after")
        prev = rc.get("previous_address")
        if rc.get("type") == "geni_profile":
            pid = before.get("id") or (after or {}).get("id")
            profiles[rc.get("name", "")] = ProfileChange(
                name=rc.get("name", ""),
                profile_id=pid if isinstance(pid, str) else None,
                gender=before.get("gender") or (after or {}).get("gender"),
                actions=actions,
                previous=prev.removeprefix("geni_profile.") if prev else None,
                unions=_ids(before.get("unions")),
            )
        elif rc.get("type") == "geni_union":
            leaves = actions in (("forget",), ("delete",))
            after = after or {}
            unions.append(UnionChange(
                address=rc.get("address", ""),
                previous=prev,
                union_id=before.get("id") or None,
                actions=actions,
                before_partners=_ids(before.get("partners")),
                before_children=tuple(c for k in _CHILD_KEYS for c in _ids(before.get(k))),
                after_partners=None if leaves else _after_ids(after.get("partners")),
                after_children=None if leaves else tuple(
                    c for k in _CHILD_KEYS for c in _after_ids(after.get(k))),
            ))
    genders = {p.profile_id: p.gender for p in profiles.values() if p.profile_id and p.gender}
    return PlanView(profiles, unions, genders, documents_replaced)


# ── Who folds into whom ─────────────────────────────────────────────────────


def canonical_of(name: str, move_list: Mapping[str, str]) -> str | None:
    """Follow the move list to the canonical (CCN008 forbids chains; guard anyway)."""
    seen: set[str] = set()
    target = move_list.get(name)
    while target is not None and target in move_list and target not in seen:
        seen.add(target)
        target = move_list[target]
    return target


_DATE = re.compile(r"_\d{4}(?:_\d{1,2}){0,2}(?=_)")
_ANCHOR = re.compile(r"_(?:(?:mk|ext)_[a-z]+|rs|ir|list)_(?=\d)")


def record_slot(name: str) -> tuple[str, str] | None:
    """(date, record tail) of a per-record res_name — what a proofread rename keeps.

    `_1872_04_08_ivan_petrovich_sidorov_mk_births_19_god_parent_1` →
    (`_1872_04_08`, `_mk_births_19_god_parent_1`): the name between them is the
    reading, and a re-reading changes nothing else."""
    date = _DATE.match(name)
    if not date:
        return None
    anchor = _ANCHOR.search(name, date.end())
    if not anchor or anchor.start() == date.end():
        return None
    return name[:date.end()], name[anchor.start():]


def renamed_record(name: str, move_list: Mapping[str, str]) -> tuple[str, str] | None:
    """(canonical, new res_name) when `name` is the old name of a folded record."""
    slot = record_slot(name)
    if slot is None:
        return None
    hits = [r for r in move_list if r != name and record_slot(r) == slot]
    canonicals = {canonical_of(r, move_list) for r in hits} - {None}
    if len(canonicals) != 1:
        return None
    canonical = canonicals.pop()
    assert canonical is not None
    return canonical, sorted(hits)[0]


def union_evidence(view: PlanView, dup_ids: set[str]) -> dict[str, set[str]]:
    """dup id → the ids the plan's unions put in its place.

    A union that stays: a partner (or child) leaves and exactly one of the same
    sex arrives. A union that leaves (forget/delete): its children join the
    union that keeps most of them, and each dup partner maps to that union's
    partner of the same sex."""
    def same_sex(a: str, b: str) -> bool:
        ga, gb = view.gender(a), view.gender(b)
        return ga is None or gb is None or ga == gb

    found: dict[str, set[str]] = defaultdict(set)
    staying = [u for u in view.unions if u.after_partners is not None]
    for u in view.unions:
        if u.after_partners is None or u.after_children is None:
            continue
        for before, after in ((u.before_partners, u.after_partners),
                              (u.before_children, u.after_children)):
            known = {a for a in after if a}
            arrived = [a for a in known if a not in before]
            for gone in (b for b in before if b in dup_ids and b not in known):
                cands = [a for a in arrived if same_sex(gone, a)]
                if len(cands) == 1:
                    found[gone].add(cands[0])
    for u in view.unions:
        if u.after_partners is not None or not u.before_children:
            continue
        overlap = sorted(
            ((len(set(u.before_children) & {c for c in s.after_children or () if c}), s)
             for s in staying),
            key=lambda pair: -pair[0])
        if not overlap or overlap[0][0] == 0 or (
                len(overlap) > 1 and overlap[1][0] == overlap[0][0]):
            continue
        joined = overlap[0][1]
        for p in u.before_partners:
            if p not in dup_ids:
                continue
            cands = [q for q in joined.after_partners or () if q and q != p and same_sex(p, q)]
            if len(cands) == 1:
                found[p].add(cands[0])
    return found


def profile_names_in(source: str, key: str) -> list[str] | None:
    """`profile_names` of the entry `key` in a config's source, read without
    executing it (an old revision may import what no longer exists)."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values, strict=True):
            if not (isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Dict)):
                continue
            for k2, v2 in zip(v.keys, v.values, strict=True):
                if (isinstance(k2, ast.Constant) and k2.value == "profile_names"
                        and isinstance(v2, (ast.List, ast.Tuple))):
                    return [e.value for e in v2.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return None


def _git(cwd: Path, *args: str) -> str | None:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


def declared_in_history(config: Path, key: str, depth: int = 5) -> tuple[list[str], str] | None:
    """(`profile_names`, revision) of the last committed config that still declared
    `key`: HEAD when only the working tree dropped it, else the parent of each
    newest commit whose diff touches a line quoting the key."""
    found = _git(config.parent, "rev-parse", "--show-toplevel")
    if found is None:
        return None
    top = Path(found.strip()).resolve()
    rel = config.resolve().relative_to(top).as_posix()   # a pathspec from the top
    quoted = f"[\"']{re.escape(key)}[\"']"   # the key as a dict key, either quote
    log = _git(top, "log", "--format=%H", f"-G{quoted}", "--", rel) or ""
    revs = ["HEAD"] + [f"{h}^" for h in log.split()[:depth]]
    for rev in revs:
        text = _git(top, "show", f"{rev}:{rel}")
        if text is None:
            continue
        names = profile_names_in(text, key)
        if names is not None:
            return names, rev
    return None


# ── The plan of merges ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Merge:
    dup: str
    dup_id: str
    canonical: str | None
    keep_id: str | None
    via: str
    phase: str
    unions: tuple[str, ...] = ()
    note: str = ""

    def command(self) -> str:
        return f"geni profile merge -yes {self.keep_id} {self.dup_id}"


@dataclass(frozen=True)
class Detach:
    profile_id: str   # as it stands after the merges (a dup's keep)
    union_id: str
    union: str        # the union's address
    reason: str       # why the union keeps the member on Geni
    also_in: str = ""  # the union the plan also puts the member in

    def command(self) -> str:
        return f"geni profile detach-union -yes {self.profile_id} {self.union_id}"


@dataclass(frozen=True)
class UnionWatch:
    """A union whose fate the merges decide — read with `geni union get` after them."""

    union_id: str
    union: str
    fate: str
    expect: str              # "fuses" | "absorbs" | "stays" | "kept"
    partner_union: str = ""  # the other side of a fusion
    partner_union_id: str = ""


@dataclass
class MergePlan:
    documents_replaced: int = 0
    merges: list[Merge] = field(default_factory=list[Merge])
    detaches: list[Detach] = field(default_factory=list[Detach])
    watches: list[UnionWatch] = field(default_factory=list[UnionWatch])
    notes: list[str] = field(default_factory=list[str])

    def phase(self, phase: str) -> list[Merge]:
        return [m for m in self.merges if m.phase == phase]

    def merged(self) -> dict[str, str]:
        """dup id → keep id, for every merge the plan will run (or ran)."""
        return {m.dup_id: m.keep_id for m in self.merges
                if m.keep_id and m.phase in (BEFORE, AFTER, DONE)}


History = Callable[[str], tuple[list[str], str] | None]


def _holder_id(view: PlanView, canonical: str) -> str | None:
    """The canonical's Geni id — under the CANONICAL address, where `moved`
    already put the keeper's (module docstring, caution)."""
    p = view.profiles.get(canonical)
    if p is None or p.actions == ("forget",):
        return None
    return p.profile_id


def build(plan: Mapping[str, Any], move_list: Mapping[str, str], *,
          into: Mapping[str, str] | None = None,
          history: History | None = None) -> MergePlan:
    """Turn a plan JSON and the config's move list into the Geni-side work.

    `into` maps a forgotten res_name to a canonical res_name or a `profile-N`
    (the `--into` escape hatch); `history` answers a dissolved key's old
    `profile_names` (git in the CLI, a dict in tests)."""
    view = read_plan(plan)
    into = into or {}
    forgotten = [p for p in view.profiles.values()
                 if p.actions == ("forget",) and p.profile_id]
    dup_ids = {p.profile_id for p in forgotten if p.profile_id}
    evidence = union_evidence(view, dup_ids)
    holding: dict[str, list[UnionChange]] = defaultdict(list)
    for u in view.unions:
        for m in u.before_members:
            holding[m].append(u)
    managed = {u.union_id for u in view.unions if u.union_id}
    out = MergePlan(documents_replaced=view.documents_replaced)

    for p in sorted(forgotten, key=lambda p: p.name):
        assert p.profile_id is not None
        canonical, keep, via = _resolve(p, view, move_list, into, history, evidence)
        unions = tuple(
            f"{u.label()} ({u.fate}: {'partner' if p.profile_id in u.before_partners else 'child'})"
            for u in holding.get(p.profile_id, []))
        unions += tuple(f"{uid} (not in this state)" for uid in p.unions if uid not in managed)
        seen = evidence.get(p.profile_id, set())
        if keep is None:
            phase, note = UNRESOLVED, _unresolved_note(canonical, seen, view)
        elif keep == p.profile_id:
            phase, note = DONE, "state already follows the survivor (merged on Geni before this plan)"
        elif seen and keep not in seen and via != "--into":
            phase, note = CONFLICT, (
                f"the unions put {', '.join(sorted(seen))} in its place, not {keep} — "
                "a union bound to another couple?")
        else:
            phase = BEFORE if unions else AFTER
            note = (f"the unions put {', '.join(sorted(seen))} in its place; --into overrides"
                    if seen and keep not in seen else "")
        out.merges.append(Merge(p.name, p.profile_id, canonical, keep, via, phase, unions, note))

    _plan_unions(view, out)
    return out


def _unresolved_note(canonical: str | None, seen: set[str], view: PlanView) -> str:
    if len(seen) > 1:
        return f"the unions put {', '.join(sorted(seen))} in its place — name one with --into"
    if canonical is None:
        return "no canonical — a record dropped from the DSL? Name it with --into DUP=CANONICAL"
    if canonical not in view.profiles:
        return f"{canonical} is not a resource of this plan"
    return (f"{canonical} has no Geni id before the apply (this plan creates it) — pin its "
            "keeper to a record already in state")


def _resolve(p: ProfileChange, view: PlanView, move_list: Mapping[str, str],
             into: Mapping[str, str], history: History | None,
             evidence: Mapping[str, set[str]]) -> tuple[str | None, str | None, str]:
    assert p.profile_id is not None
    if p.name in into:
        target = into[p.name]
        if target.startswith("profile-"):
            return view.name_of(target), target, "--into"
        return target, _holder_id(view, target), "--into"
    canonical = canonical_of(p.name, move_list)
    if canonical is not None:
        return canonical, _holder_id(view, canonical), "config"
    renamed = renamed_record(p.name, move_list)
    if renamed is not None:
        return renamed[0], _holder_id(view, renamed[0]), f"renamed record → {renamed[1]}"
    seen = evidence.get(p.profile_id, set())
    if len(seen) == 1:
        keep = next(iter(seen))
        return view.name_of(keep), keep, "unions"
    if history is not None and not seen and record_slot(p.name) is None:
        declared = history(p.name)
        if declared is not None:
            names, rev = declared
            targets = {_folded_into(n, move_list, view) for n in names} - {None}
            if len(targets) == 1:
                canonical = targets.pop()
                assert canonical is not None
                return canonical, _holder_id(view, canonical), f"git {rev}: the key's records"
    return None, None, "—"


def _folded_into(name: str, move_list: Mapping[str, str], view: PlanView) -> str | None:
    """Where a record of an old config revision stands now: its canonical, its
    renamed self's canonical, or itself when it stands alone."""
    renamed = renamed_record(name, move_list)
    return (canonical_of(name, move_list) or (renamed[0] if renamed else None)
            or (name if name in view.profiles else None))


def _plan_unions(view: PlanView, out: MergePlan) -> None:
    """Fusions, detaches and the unions worth reading after the merges."""
    merged = out.merged()

    def m(x: str) -> str:
        return merged.get(x, x)

    post_children: dict[str, list[UnionChange]] = defaultdict(list)
    by_partners: dict[frozenset[str], UnionChange] = {}
    for u in view.unions:
        if u.after_children is None or u.after_partners is None:
            continue
        for c in u.after_children:
            if c:
                post_children[c].append(u)
        partners = u.after_partners
        if partners and all(partners) and "delete" not in u.actions:
            by_partners[frozenset(q for q in partners if q)] = u
    touched = set(merged)
    blocked = {mg.dup_id for mg in out.merges if mg.phase in (UNRESOLVED, CONFLICT)}
    detaches: dict[tuple[str, str], Detach] = {}

    def watch(w: UnionWatch) -> None:
        if w not in out.watches:
            out.watches.append(w)

    for u in view.unions:
        if u.fate != "collapsed" or not u.union_id:
            continue
        partners = frozenset(m(q) for q in u.before_partners)
        joined = by_partners.get(partners)
        if joined is not None and joined.union_id == u.union_id:
            continue  # one union under two addresses already
        if joined is not None and joined.union_id is None:
            out.notes.append(
                f"{u.label()}: the plan creates {joined.address} with the same partners — the "
                "provider adopts an existing union of theirs («Found existing union»); check "
                "which one after the apply")
            continue
        if joined is not None and joined.union_id:
            watch(UnionWatch(u.union_id, u.address, u.fate, "fuses",
                             joined.address, joined.union_id))
            watch(UnionWatch(joined.union_id, joined.address, joined.fate, "absorbs",
                             u.address, u.union_id))
            continue
        watch(UnionWatch(u.union_id, u.address, u.fate, "stays"))
        why = ("terraform forgets it, Geni keeps it: one partner, and no union of that "
               "partner alone to fuse with" if len(u.before_partners) == 1 else
               "terraform forgets it, Geni keeps it: its partners do not merge into the "
               "partners of one union the plan keeps")
        for c in u.before_children:
            others = [o for o in post_children.get(m(c), []) if o.address != u.address]
            if others:
                detaches.setdefault((m(c), u.union_id), Detach(
                    m(c), u.union_id, u.address, why, others[0].label()))
            else:
                out.notes.append(f"{u.label()}: {m(c)} keeps it as its only parent union, "
                                 "which terraform no longer manages")

    for u in view.unions:
        if (u.after_partners is None or not u.union_id or not u.before_members
                or "delete" in u.actions):
            continue
        kept = u.after_known()
        for x in u.before_members:
            if m(x) not in kept and x not in blocked:
                role = "partner" if x in u.before_partners else "child"
                detaches.setdefault((m(x), u.union_id), Detach(
                    m(x), u.union_id, u.address,
                    f"the plan drops a {role}, and the provider never takes a member "
                    "out of a union"))
        if u.fate in ("re-keyed", "updated") and touched & set(u.before_members):
            if not any(w.union_id == u.union_id for w in out.watches):
                watch(UnionWatch(u.union_id, u.address, u.fate, "kept"))
    out.detaches = list(detaches.values())


# ── Report ──────────────────────────────────────────────────────────────────


def _rule(title: str) -> str:
    return f"\n── {title} " + "─" * max(4, 76 - len(title))


def format_report(plan: MergePlan, *, village: str, source: str,
                  plan_json: str | None = None) -> str:
    lines = [f"merge-plan — {village} · {source}"]
    counts = {ph: len(plan.phase(ph)) for ph in (BEFORE, AFTER, DONE, UNRESOLVED, CONFLICT)}
    lines.append(
        f"{len(plan.merges)} profile(s) leave terraform alive (forget): "
        f"{counts[BEFORE]} merge before the apply, {counts[AFTER]} after, "
        f"{counts[DONE]} already merged, {counts[UNRESOLVED]} unresolved, "
        f"{counts[CONFLICT]} conflicting; {len(plan.detaches)} detach(es) after the apply.")
    if not plan.merges and not plan.detaches:
        lines.append("Nothing to do on Geni.")
        return "\n".join(lines)

    def merge_block(ms: Sequence[Merge]) -> None:
        for mg in ms:
            lines.append(f"# {mg.canonical or '?'} ← {mg.dup}  [{mg.via}]")
            for u in mg.unions:
                lines.append(f"#   in {u}")
            if mg.note:
                lines.append(f"#   {mg.note}")
            if mg.phase in (BEFORE, AFTER):
                lines.append(mg.command())
            elif mg.keep_id:
                lines.append(f"#   {mg.command()}")

    for title, phase in (("CONFLICT — not run; read the union first", CONFLICT),
                         ("UNRESOLVED — name the canonical with --into DUP=CANONICAL", UNRESOLVED)):
        if plan.phase(phase):
            lines.append(_rule(title))
            merge_block(plan.phase(phase))
    lines.append(_rule("1. Merge on Geni BEFORE the apply (the dup is in a union)"))
    merge_block(plan.phase(BEFORE) or [])
    if not plan.phase(BEFORE):
        lines.append("(none)")
    if plan.watches:
        lines.append(_rule("2. Then read these unions (geni union get) — or --check-unions"))
        for w in plan.watches:
            lines.append(f"{w.union_id}  {w.union.removeprefix('geni_union.')}  ({w.fate})  "
                         + _expectation(w))
    lines.append(_rule("3. Apply"))
    if plan.documents_replaced:
        lines.append(f"# {plan.documents_replaced} geni_document(s) replaced — push their text first "
                     "(verify-plan refuses a replace):")
        lines.append(f'verso document-sync --village "{village}" '
                     f'--plan "{plan_json or "<the plan JSON>"}"')
    module = shlex.quote(f"{village}/terraform/geni")
    lines.append(plan_command(village))
    lines.append(export_command(village))
    lines.append(f"verso verify-plan --village {shlex.quote(village)}")
    lines.append(f"terraform -chdir={module} apply .plan")
    lines.append(_rule("4. Merge on Geni AFTER the apply (no union: godparents, witnesses)"))
    merge_block(plan.phase(AFTER) or [])
    if not plan.phase(AFTER):
        lines.append("(none)")
    lines.append(_rule("5. Detach AFTER the apply"))
    last = None
    for d in plan.detaches:
        if (d.union_id, d.reason) != last:
            lines.append(f"# {d.union_id} {d.union.removeprefix('geni_union.')} — {d.reason}")
            last = (d.union_id, d.reason)
        if d.also_in:
            lines.append(f"#   {d.profile_id} is also a child of {d.also_in}")
        lines.append(d.command())
    if not plan.detaches:
        lines.append("(none)")
    for note in plan.notes:
        lines.append(f"# note: {note}")
    keeps = sorted({mg.keep_id for mg in plan.merges if mg.keep_id and mg.phase in (BEFORE, AFTER)})
    lines.append(_rule("6. Second tf-plan + tf-apply, then the merge conflicts"))
    lines.append("# Geni glues each absorbed `about` onto the survivor; the second apply rewrites it.")
    lines.append("# It does not always clear the conflicts: show, then resolve.")
    for k in keeps:
        lines.append(f"geni conflicts show {k}")
    if plan.merges or plan.detaches:
        lines.append("# ids as planned — a survivor flip changes them; --run-before/--run-after "
                     "re-read each through merged_into")
    return "\n".join(lines)


def _expectation(w: UnionWatch) -> str:
    if w.expect == "fuses":
        return f"→ Geni should fuse it into {w.partner_union_id} (expect: husk)"
    if w.expect == "absorbs":
        return f"← absorbs {w.partner_union_id}; terraform keeps it (expect: live)"
    if w.expect == "stays":
        return "→ stays on Geni beside the canonical union (expect: live; detach after the apply)"
    return "terraform keeps it (expect: live)"


# ── Geni ────────────────────────────────────────────────────────────────────


class GeniClient(Protocol):
    def profile(self, profile_id: str) -> dict[str, Any]: ...
    def union(self, union_id: str) -> dict[str, Any]: ...
    def merge(self, keep: str, dup: str) -> str: ...
    def detach(self, profile_id: str, union_id: str) -> str: ...


class GeniCli:
    """The go-geni CLI (`geni`), auth shared with the provider (~/.genealogy)."""

    def __init__(self, binary: str) -> None:
        self.binary = binary

    def _run(self, *args: str) -> str:
        proc = subprocess.run([self.binary, *args], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout).strip() or f"exit {proc.returncode}")
        return proc.stdout

    def profile(self, profile_id: str) -> dict[str, Any]:
        return json.loads(self._run("profile", "get", profile_id))

    def union(self, union_id: str) -> dict[str, Any]:
        return json.loads(self._run("union", "get", union_id))

    def merge(self, keep: str, dup: str) -> str:
        return self._run("profile", "merge", "-yes", keep, dup).strip()

    def detach(self, profile_id: str, union_id: str) -> str:
        return self._run("profile", "detach-union", "-yes", profile_id, union_id).strip()


_MERGED = re.compile(r"(profile-\d+) merged into (profile-\d+)")


def survivor_of(result: str) -> str | None:
    """`{"result":"profile-B merged into profile-A with conflicts"}` → profile-A."""
    hit = _MERGED.search(result)
    return hit.group(2) if hit else None


def live_id(geni: GeniClient, profile_id: str, hops: int = 5) -> str:
    """Follow `merged_into` to the profile that stands now."""
    current = profile_id
    for _ in range(hops):
        nxt = geni.profile(current).get("merged_into")
        if not nxt or nxt == current:
            break
        current = nxt
    return current


LOG_FIELDS = ("when", "phase", "action", "canonical", "keep", "dup", "survivor", "status", "result")


class Log:
    """Append-only TSV of everything run on Geni — the survivor-flip report."""

    def __init__(self, path: Path | None) -> None:
        self.path = path

    def write(self, **row: str) -> None:
        if self.path is None:
            return
        new = not self.path.exists()
        with self.path.open("a", encoding="utf-8", newline="") as fh:
            w: csv.DictWriter[str] = csv.DictWriter(fh, list(LOG_FIELDS), delimiter="\t",
                                                    lineterminator="\n", extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow({"when": datetime.now().isoformat(timespec="seconds"), **row})


@dataclass(frozen=True)
class Outcome:
    merge: Merge
    keep: str
    status: str          # merged | flip | skipped | failed
    survivor: str = ""
    detail: str = ""


def run_merges(merges: Iterable[Merge], geni: GeniClient, log: Log, *,
               pause: float = 1.0, sleep: Callable[[float], None] = time.sleep,
               say: Callable[[str], None] = print) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for mg in merges:
        if mg.phase not in (BEFORE, AFTER) or not mg.keep_id:
            continue
        try:
            keep = live_id(geni, mg.keep_id)
            dup_now = live_id(geni, mg.dup_id)
        except RuntimeError as e:
            outcomes.append(Outcome(mg, mg.keep_id, "failed", detail=str(e)))
            say(f"FAILED  {mg.canonical} ← {mg.dup}: {e}")
            continue
        if dup_now == keep:
            outcomes.append(Outcome(mg, keep, "skipped", keep, "already merged"))
            say(f"skip    {mg.canonical} ← {mg.dup}: already merged into {keep}")
            log.write(phase=mg.phase, action="merge", canonical=mg.canonical or "", keep=keep,
                      dup=mg.dup_id, survivor=keep, status="skipped", result="already merged")
            continue
        if dup_now != mg.dup_id:
            detail = f"{mg.dup_id} was merged into {dup_now}, not into {keep} — left alone"
            outcomes.append(Outcome(mg, keep, "skipped", dup_now, detail))
            say(f"skip    {mg.canonical} ← {mg.dup}: {detail}")
            continue
        try:
            result = geni.merge(keep, mg.dup_id)
        except RuntimeError as e:
            outcomes.append(Outcome(mg, keep, "failed", detail=str(e)))
            say(f"FAILED  {mg.canonical} ← {mg.dup}: {e}")
            log.write(phase=mg.phase, action="merge", canonical=mg.canonical or "", keep=keep,
                      dup=mg.dup_id, status="failed", result=str(e))
            sleep(pause)
            continue
        survivor = survivor_of(result) or ""
        status = "merged" if survivor == keep else "flip"
        outcomes.append(Outcome(mg, keep, status, survivor, result))
        say(f"{status:7} {mg.canonical} ← {mg.dup}: {result}")
        log.write(phase=mg.phase, action="merge", canonical=mg.canonical or "", keep=keep,
                  dup=mg.dup_id, survivor=survivor, status=status, result=result)
        sleep(pause)
    return outcomes


def format_flips(outcomes: Sequence[Outcome]) -> str:
    flips = [o for o in outcomes if o.status == "flip"]
    failed = [o for o in outcomes if o.status == "failed"]
    lines = [f"{sum(o.status in ('merged', 'flip') for o in outcomes)} merged, "
             f"{len(flips)} survivor flip(s), "
             f"{sum(o.status == 'skipped' for o in outcomes)} skipped, {len(failed)} failed."]
    for o in flips:
        lines.append(
            f"FLIP  {o.merge.canonical}: Geni kept {o.survivor} (the dup {o.merge.dup}), "
            f"not {o.keep}. No config change — the refresh follows the redirect; "
            "later merges and detaches into it follow merged_into.")
    for o in failed:
        lines.append(f"FAIL  {o.merge.canonical} ← {o.merge.dup}: {o.detail}")
    return "\n".join(lines)


def check_unions(watches: Sequence[UnionWatch], geni: GeniClient) -> list[str]:
    """Read each watched union; say which became a husk and whether that was the plan."""
    state: dict[str, bool | None] = {}
    lines: list[str] = []
    for w in watches:
        if w.union_id in state:
            continue
        try:
            u = geni.union(w.union_id)
            state[w.union_id] = bool(u.get("partners") or u.get("children"))
        except RuntimeError as e:
            state[w.union_id] = None
            lines.append(f"?     {w.union_id}  {e}")
    for w in watches:
        live = state.get(w.union_id)
        if live is None:
            continue
        name = w.union.removeprefix("geni_union.")
        word = "live" if live else "HUSK"
        if w.expect == "fuses":
            other = state.get(w.partner_union_id)
            if not live and other:
                verdict = f"✓ fused into {w.partner_union_id}, as the blocks expect"
            elif live and other is False:
                verdict = (f"⚠ Geni kept THIS union and emptied {w.partner_union_id}, which "
                           f"{w.partner_union} holds: rewrite the blocks — moved {{ from = "
                           f"{w.union} to = {w.partner_union} }} and removed{{destroy=false}} "
                           "for the address that held the husk")
            elif live:
                verdict = "⚠ not fused (yet): its children stand in two unions — detach after the apply"
            else:
                verdict = "⚠ both unions are empty"
        elif w.expect in ("absorbs", "kept"):
            verdict = "✓" if live else (
                f"⚠ terraform keeps {w.union} and Geni emptied it — the union block points "
                "at a husk (a fusion went the other way?)")
        else:  # stays
            verdict = ("✓ stays — detach its children after the apply" if live
                       else "emptied — nothing left to detach")
        lines.append(f"{word:5} {w.union_id}  {name}  {verdict}")
    return lines


def run_detaches(detaches: Iterable[Detach], geni: GeniClient, log: Log, *,
                 pause: float = 1.0, sleep: Callable[[float], None] = time.sleep,
                 say: Callable[[str], None] = print) -> int:
    """Detach each member (re-read through merged_into), then read every union
    detached from: one left with nothing is the husk the plan expects (an example run: a
    union emptied once its three children went)."""
    failures = 0
    emptied: list[str] = []
    for d in detaches:
        try:
            who = live_id(geni, d.profile_id)
            members = geni.union(d.union_id)
            if who not in (members.get("partners") or []) + (members.get("children") or []):
                say(f"skip    {who} is not in {d.union_id}")
                log.write(phase=AFTER, action="detach", keep=d.union_id, dup=who,
                          status="skipped", result="not a member")
                continue
            result = geni.detach(who, d.union_id)
        except RuntimeError as e:
            failures += 1
            say(f"FAILED  detach {d.profile_id} from {d.union_id}: {e}")
            log.write(phase=AFTER, action="detach", keep=d.union_id, dup=d.profile_id,
                      status="failed", result=str(e))
            sleep(pause)
            continue
        say(f"detach  {who} from {d.union_id}: {result}")
        log.write(phase=AFTER, action="detach", keep=d.union_id, dup=who,
                  status="detached", result=result)
        if d.union_id not in emptied:
            emptied.append(d.union_id)
        sleep(pause)
    for uid in emptied:
        try:
            u = geni.union(uid)
        except RuntimeError as e:
            say(f"?       {uid}: {e}")
            continue
        left = (u.get("partners") or []) + (u.get("children") or [])
        say(f"{uid}: " + ("now an empty husk — terraform no longer manages it" if not left
                          else "still holds " + ", ".join(left)))
    return failures


# ── CLI ─────────────────────────────────────────────────────────────────────


def load_plan(path: Path) -> dict[str, Any]:
    """A plan JSON, or a binary plan (`.plan`, `.plan-fast`) shown through terraform."""
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    proc = subprocess.run([tool("terraform"), f"-chdir={path.parent}", "show", "-json", path.name],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"terraform show -json {path} failed:\n{proc.stderr.strip()}")
    return json.loads(proc.stdout)


def load_move_list(config: Path) -> dict[str, str]:
    """record res_name → canonical, as the generator folds them (`make_consolidation`)."""
    from verso.core.pipeline.config import load_config
    from verso.ru.pipeline.translate import make_consolidation

    if not config.is_file():
        raise SystemExit(f"cannot load {config}")
    return dict(make_consolidation(load_config(config)).profile_move_list)


def _parse_into(pairs: Sequence[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        dup, sep, target = pair.partition("=")
        if not sep or not dup or not target:
            raise SystemExit(f"--into takes DUP=CANONICAL or DUP=profile-N, not {pair!r}")
        out[dup.removeprefix("geni_profile.")] = target.removeprefix("geni_profile.")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--village", required=True, help="village dir")
    ap.add_argument("--plan", help="plan JSON, or a binary .plan/.plan-fast "
                                   "(default: <village>/_plan.json)")
    ap.add_argument("--config", help="default: <village>/generate_config_names.py")
    ap.add_argument("--into", action="append", default=[], metavar="DUP=CANONICAL",
                    help="name the canonical (or profile-N) of a forgotten profile by hand")
    ap.add_argument("--json", action="store_true", help="machine-readable plan")
    run = ap.add_mutually_exclusive_group()
    run.add_argument("--run-before", action="store_true",
                     help="EXECUTE the before-apply merges, then read the unions")
    run.add_argument("--run-after", action="store_true",
                     help="EXECUTE the after-apply merges and the detaches")
    run.add_argument("--check-unions", action="store_true",
                     help="read the watched unions with `geni union get` (read-only)")
    ap.add_argument("--log", help="TSV log of what ran (default: <village>/_merge_plan_log.tsv)")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between Geni calls")
    ap.add_argument("--geni", default=None, help="path to the go-geni CLI")
    args = ap.parse_args(argv)

    village = Path(args.village)
    plan_path = Path(args.plan) if args.plan else village / "_plan.json"
    config = Path(args.config) if args.config else village / "generate_config_names.py"
    if not plan_path.exists():
        raise SystemExit(f"no plan at {plan_path} — {plan_command(village, fast=True)} (then --plan "
                         f"{shlex.quote(str(village / 'terraform' / 'geni' / '.plan-fast'))}), or "
                         f"{plan_command(village)} and {export_command(village)}")
    stamp = datetime.fromtimestamp(plan_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    if args.plan is None:
        newer = [p for p in (village / "terraform" / "geni" / n for n in (".plan", ".plan-fast"))
                 if p.exists() and p.stat().st_mtime > plan_path.stat().st_mtime]
        for p in newer:
            print(f"warning: {p} is newer than {plan_path} — pass --plan {p}", file=sys.stderr)

    move_list = load_move_list(config)

    def history(key: str) -> tuple[list[str], str] | None:
        return declared_in_history(config, key)

    plan = build(load_plan(plan_path), move_list, into=_parse_into(args.into), history=history)

    if args.json:
        print(json.dumps({"documents_replaced": plan.documents_replaced,
                          "merges": [asdict(m) for m in plan.merges],
                          "detaches": [asdict(d) for d in plan.detaches],
                          "watches": [asdict(w) for w in plan.watches],
                          "notes": plan.notes}, ensure_ascii=False, indent=2))
    else:
        print(format_report(plan, village=str(village), source=f"{plan_path} ({stamp})",
                            plan_json=str(plan_path) if plan_path.suffix == ".json" else None))

    blocked = bool(plan.phase(UNRESOLVED) or plan.phase(CONFLICT))
    if not (args.run_before or args.run_after or args.check_unions):
        return 1 if blocked else 0

    geni: GeniClient = GeniCli(args.geni or tool("geni"))
    log = Log(Path(args.log) if args.log else village / "_merge_plan_log.tsv")
    print()
    if args.check_unions:
        print("\n".join(check_unions(plan.watches, geni)) or "no unions to read")
        return 0
    if args.run_before:
        outcomes = run_merges(plan.phase(BEFORE), geni, log, pause=args.pause)
        print(format_flips(outcomes))
        if plan.watches:
            print("\nUnions after the merges (geni union get):")
            print("\n".join(check_unions(plan.watches, geni)))
        return 1 if any(o.status == "failed" for o in outcomes) else 0
    outcomes = run_merges(plan.phase(AFTER), geni, log, pause=args.pause)
    print(format_flips(outcomes))
    failures = run_detaches(plan.detaches, geni, log, pause=args.pause)
    return 1 if failures or any(o.status == "failed" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
