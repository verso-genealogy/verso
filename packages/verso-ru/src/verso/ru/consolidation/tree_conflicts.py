#!/usr/bin/env python3
"""Triage Geni **tree conflicts** and wire their resolution back into the config.

A *tree conflict* (Geni Merge Center, separate from a *data conflict*) is a
profile that, after a merge, ended up with **duplicate close relatives** — most
often two parent unions whose fathers/mothers are the same person duplicated
(`duplicate_parents`), or two duplicate spouses (`duplicate_spouse`). The
`geni` CLI surfaces them read-only:

    geni tree-conflicts list [-all]          # profiles with an unresolved tree conflict
    geni tree-conflicts show <profile-id>    # the duplicate relatives + suggested merges

There is **no** `tree-conflicts resolve`: resolution = merge the duplicate
relatives with `geni profile merge` (destructive; keep the larger subtree),
then **wire that merge back** into `<village>/generate_config_names.py` or the
next `terraform apply` destroys the live merged profile / recreates a duplicate
.

This tool is the **discovery/adjudication front-end**; it hands off to the same
consolidation back-end the rest of the pipeline uses. It:

  1. **Lists** every tree conflict and drops **stale** entries — the list lags,
     so a re-`show` returning `has_conflict: false` is skipped (~29% of the
     current account list are stale).
  2. **Maps** each duplicate relative's Geni guid back to its Terraform
     `geni_profile` resource (via `terraform state pull`) and then to its
     `profiles_to_consolidate` canonical key.
  3. **Reports**, per conflict: the vetted `geni profile compare`/`merge`
     commands (survivor = larger `subtree_size`, mirroring Geni's
     `suggested_actions`) **plus** the config-wiring stub (append the absorbed
     record's res_name to the survivor's canonical `profile_names`).
  4. With **`--write`**, appends the unambiguous (AUTO) profile folds into the
     config using the same writer `tf-consolidate-write` uses
     (`generate_moved_block: True`). It does **not** run the Geni merge (discovery
     is read-only, the merge stays manual) and does **not** author union blocks (delegated to
     `verso detector --write`, which needs a refreshed plan).

⚠️ Run `--write` **after** the Geni merge, never before: folding two profiles
that still carry distinct live guids would plan a destroy. This is now ENFORCED,
not just documented — `--write` re-fetches each AUTO fold's absorbed profile and
refuses to wire it unless the merge is verifiable (the guid 404s, or now resolves
to the survivor). The rule needed enforcing because `reports` holds only LIVE
conflicts, and a live conflict means the pair is still unmerged: once `--write`
wired an unmerged pair, which had to be reverted by hand. If the fetch fails it
fails SAFE (treated as unmerged).

A corollary worth knowing: once a merge fully clears a conflict, the pair drops
out of `reports` entirely, so `--write` cannot wire it either — that fold belongs
to `verso detector --write`, which groups shared-guid merges from the plan.
Canonical→canonical folds and profiles owned by another manager are flagged
REVIEW / UNMAPPED and left for `tf-consolidate-write` / manual handling.

Pure helpers (`parse_subtree`, `is_stale`, `parse_show`, `plan_folds`,
`build_new_entries`, `format_report`) are unit-tested in
`tests/test_tree_conflicts.py`.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verso.ru.naming import names_registry
from verso.ru.naming.orthography import canonicalize_name
from verso.ru.consolidation.conflict_capture import (
    _geni_json, guid_to_resource, resource_to_canonical)
from verso.ru.consolidation.detector import (
    _load_consolidate_config, write_new_entries_to_file)
from verso.ru.consolidation.plan import plan_paths

# Fold tiers.
AUTO = "AUTO"        # absorbed is a plain stub → safe to append to survivor's canonical
REVIEW = "REVIEW"    # absorbed is itself a canonical / folded elsewhere → tf-consolidate-write
UNMAPPED = "UNMAPPED"  # one side not in our Terraform (e.g. another manager's profile)
DONE = "DONE"        # already wired (absorbed already in survivor's canonical)

# Per-village allowlist of conflicts adjudicated as correct-and-unmergeable
# (e.g. a remarriage: two successive wives Geni reports as duplicate_spouse).
ADJUDICATED_FILE = "tree_conflicts_adjudicated.tsv"


class TreeConflictsUnavailable(RuntimeError):
    """Geni's tree-conflict endpoint failed — distinct from "no conflicts"."""
PLACEHOLDER = "PLACEHOLDER"  # a side is a synthetic tree node (empty parent slot) — a
#                              profile merge would 404; resolve by detach-union

# Geni renders an empty parent slot as a synthetic node named "Mother of X" /
# "Father of X" with a negative pseudo-guid like ``-129053048f``. It is NOT a real
# profile: `profile merge` against it 404s, and `detach-union` doesn't fuse it —
# the CLI can't resolve these. The fix is Geni's WEB Merge Center resolver
#, so we only flag them, not automate them.
_PLACEHOLDER_NAME_RE = re.compile(r"^(Mother|Father|Parent|Child|Wife|Husband) of ")
_PLACEHOLDER_GUID_RE = re.compile(r"^-\d+f?$")


# --------------------------------------------------------------------------- #
# Parsing (pure)
# --------------------------------------------------------------------------- #

def parse_subtree(value: Any) -> int:
    """`subtree_size` like ``"+112"`` → ``112``; missing/blank → ``0``."""
    if value is None:
        return 0
    s = str(value).strip().lstrip("+")
    try:
        return int(s)
    except ValueError:
        return 0


@dataclass(frozen=True)
class Candidate:
    guid: str          # 19-digit Geni id (== show's `profile_id`)
    short_id: str
    name: str
    subtree: int


@dataclass(frozen=True)
class RolePair:
    """One role's survivor + the relatives to absorb into it."""
    role: str          # father | mother | spouse
    survivor: Candidate
    absorbed: tuple[Candidate, ...]


def _candidate(p: dict[str, Any]) -> Candidate:
    return Candidate(
        guid=str(p.get("profile_id", "")),
        short_id=str(p.get("short_id", "")),
        name=p.get("name", "") or "",
        subtree=parse_subtree(p.get("subtree_size")),
    )


def is_stale(show: dict[str, Any]) -> bool:
    """A list entry whose `show` no longer reports a conflict (the list lags)."""
    return not show.get("has_conflict", False)


def is_placeholder(cand: Candidate) -> bool:
    """True for a synthetic empty-parent-slot node (not a mergeable profile)."""
    return bool(_PLACEHOLDER_GUID_RE.match(cand.guid)
                or _PLACEHOLDER_NAME_RE.match(cand.name))


def _dedup_by_guid(cands: list[Candidate]) -> list[Candidate]:
    """Collapse repeats of one profile (Geni lists the same relative in both
    parent unions) to a single candidate, keeping its largest subtree. Merging a
    guid into itself is not a real duplicate — those roles fall out below."""
    best: dict[str, Candidate] = {}
    for c in cands:
        prev = best.get(c.guid)
        if prev is None or c.subtree > prev.subtree:
            best[c.guid] = c
    # Preserve first-seen order (survivor tie-break keeps the first-listed).
    seen: set[str] = set()
    ordered: list[Candidate] = []
    for c in cands:
        if c.guid not in seen:
            seen.add(c.guid)
            ordered.append(best[c.guid])
    return ordered


def parse_show(show: dict[str, Any]) -> list[RolePair]:
    """Group each `duplicate_candidates` role into survivor (largest subtree) +
    the relatives absorbed into it. Roles with < 2 distinct profiles are skipped
    (a single guid repeated across both parent unions is a union duplicate, not a
    profile duplicate — out of scope for a profile merge)."""
    pairs: list[RolePair] = []
    for group in show.get("duplicate_candidates", []) or []:
        role = group.get("role", "") or ""
        cands = _dedup_by_guid([_candidate(p) for p in group.get("profiles", []) or []])
        if len(cands) < 2:
            continue
        # Survivor = largest attached subtree (mirrors Geni's suggested_actions);
        # stable on ties (keeps the first-listed). A synthetic placeholder never
        # wins (it can't survive a merge — it isn't a real profile).
        survivor = max(cands, key=lambda c: (not is_placeholder(c), c.subtree))
        absorbed = tuple(c for c in cands if c is not survivor)
        pairs.append(RolePair(role=role, survivor=survivor, absorbed=absorbed))
    return pairs


# --------------------------------------------------------------------------- #
# Wiring (pure)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Fold:
    """A survivor←absorbed pair resolved onto Terraform res_names + a tier."""
    role: str
    survivor: Candidate
    absorbed: Candidate
    survivor_res: str | None
    absorbed_res: str | None
    survivor_canonical: str | None
    tier: str
    name_mismatch: str | None = None

    @property
    def merge_cmd(self) -> str:
        return (f"geni profile merge profile-g{self.survivor.guid} "
                f"profile-g{self.absorbed.guid}")

    @property
    def compare_cmd(self) -> str:
        return (f"geni profile compare profile-g{self.survivor.guid} "
                f"profile-g{self.absorbed.guid}")

    @property
    def placeholder(self) -> Candidate | None:
        """The synthetic empty-slot side of this fold, if any."""
        if is_placeholder(self.absorbed):
            return self.absorbed
        if is_placeholder(self.survivor):
            return self.survivor
        return None


@dataclass
class ConflictReport:
    guid: str
    short_id: str
    name: str
    conflict_types: tuple[str, ...]
    folds: list[Fold] = field(default_factory=list)


_PATRONYMIC_RE = re.compile(r"(ович|евич|ьич|ич|овна|евна|ична|инична)$")  # i18n: content — patronymic endings: vocabulary


def _split_person_name(name: str) -> tuple[str | None, str | None]:
    """Split a Geni display name into (given, patronymic), ignoring the surname.

    Surnames are deliberately dropped: Мямлин/Ягодкин/Мелюзгин are one family across
    scribes, so a surname difference is never evidence of two people.
    """
    tokens = [t for t in re.split(r"\s+", (name or "").strip()) if t]
    if not tokens:
        return None, None
    given = tokens[0]
    patronymic = next((t for t in tokens[1:] if _PATRONYMIC_RE.search(t)), None)
    return given, patronymic


def _canonical_given(name: str) -> str:
    """Fold a given name onto its stamm so variants compare equal (Аксинья=Ксения): the first, by
    spelling, of its bases — and of the name itself where the lexicon holds it as canonical."""
    entries = names_registry._find_name_in_table(name)
    forms = {base for entry in entries for base in entry.bases}
    if entries and canonicalize_name(name) == name:
        forms.add(name)
    return min(forms) if forms else name


def _canonical_patronymic(patronymic: str) -> str:
    """Fold a patronymic onto its canonical modern form — the feminine one, so a man's and a
    woman's patronymic of one father fold alike.

    This is what keeps the guard quiet on orthography: names.csv funnels
    Илларионовна / Иларионовна / Ларионовна to one modern form, so a fold
    pairing those spellings is NOT flagged (that merge is correct).
    """
    return names_registry.feminine_patronymic(patronymic) or patronymic


def name_mismatch(survivor_name: str, absorbed_name: str) -> str | None:
    """Do these two names denote plainly different people?

    The tier (`_classify`) answers only whether the *wiring* is unambiguous — it
    never asks whether the two profiles are the same person. That gap let a fold
    pairing two successive wives of one man (a remarriage, not a duplicate)
    land in AUTO, whose report line reads as "safe to merge". Geni has no un-merge, so acting on that destroys a real
    person's identity.

    Returns a human-readable reason, or None when the names are compatible.
    Compares only components BOTH sides carry, on canonicalised forms, and
    ignores surnames — so it stays silent on orthographic variants and on the
    sparse stubs that carry a given name only.
    """
    s_given, s_patr = _split_person_name(survivor_name)
    a_given, a_patr = _split_person_name(absorbed_name)
    if s_given and a_given and _canonical_given(s_given) != _canonical_given(a_given):
        return f"given name {s_given} ≠ {a_given}"
    if s_patr and a_patr and _canonical_patronymic(s_patr) != _canonical_patronymic(a_patr):
        return f"patronymic {s_patr} ≠ {a_patr}"
    return None


def parse_adjudicated(text: str) -> set[tuple[str, str, str]]:
    """Parse the per-village known-good allowlist.

    Format: `focus_guid<TAB>role<TAB>absorbed_guid<TAB>reason`; `#` comments and
    blank lines ignored. A legitimate remarriage is a permanent, correct
    duplicate_spouse conflict — recording the verdict keeps it from resurfacing
    on every pass and drowning out real duplicates.
    """
    out: set[tuple[str, str, str]] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        out.add((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return out


def load_adjudicated(village_dir: str = ".") -> set[tuple[str, str, str]]:
    path = os.path.join(village_dir, ADJUDICATED_FILE)
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return parse_adjudicated(f.read())


def filter_adjudicated(reports: list[ConflictReport],
                       adjudicated: set[tuple[str, str, str]],
                       ) -> tuple[list[ConflictReport], int]:
    """Drop folds the allowlist marks as adjudicated. Returns (reports, hidden).

    Matching ignores survivor/absorbed direction: Geni picks its own survivor, so
    the same adjudicated pair can come back swapped on a later pass.
    """
    if not adjudicated:
        return reports, 0
    hidden = 0
    for report in reports:
        keep: list[Fold] = []
        for fold in report.folds:
            if ((report.guid, fold.role, fold.absorbed.guid) in adjudicated
                    or (report.guid, fold.role, fold.survivor.guid) in adjudicated):
                hidden += 1
                continue
            keep.append(fold)
        report.folds = keep
    return reports, hidden


def _classify(absorbed_res: str | None, survivor_res: str | None,
              survivor_canonical: str | None, config_keys: set[str],
              folded_index: dict[str, str]) -> str:
    if survivor_res is None or absorbed_res is None:
        return UNMAPPED
    if absorbed_res in config_keys:
        return REVIEW          # absorbed is itself a canonical cluster
    canon = folded_index.get(absorbed_res)
    if canon is not None:
        return DONE if canon == survivor_canonical else REVIEW
    return AUTO                 # plain standalone stub


def plan_folds(pairs: list[RolePair], guid_to_res: dict[str, str],
               config_keys: set[str], folded_index: dict[str, str]) -> list[Fold]:
    """Resolve each RolePair's guids → res_name → canonical, and tier the fold."""
    folds: list[Fold] = []
    for pair in pairs:
        survivor_res = guid_to_res.get(pair.survivor.guid)
        survivor_canonical = (
            folded_index.get(survivor_res, survivor_res)
            if survivor_res is not None else None
        )
        for absorbed in pair.absorbed:
            absorbed_res = guid_to_res.get(absorbed.guid)
            if is_placeholder(pair.survivor) or is_placeholder(absorbed):
                # A synthetic empty parent slot — not a mergeable profile.
                tier = PLACEHOLDER
            else:
                tier = _classify(absorbed_res, survivor_res, survivor_canonical,
                                 config_keys, folded_index)
            # Identity check, orthogonal to the tier: the tier grades the
            # WIRING, this grades whether it is one person at all.
            mismatch = (None if tier == PLACEHOLDER
                        else name_mismatch(pair.survivor.name, absorbed.name))
            folds.append(Fold(
                role=pair.role, survivor=pair.survivor, absorbed=absorbed,
                survivor_res=survivor_res, absorbed_res=absorbed_res,
                survivor_canonical=survivor_canonical, tier=tier,
                name_mismatch=mismatch,
            ))
    return folds


def merge_state(fetched: dict[str, Any] | None, survivor_guid: str) -> str:
    """Has the absorbed profile actually been merged into the survivor?

    ``fetched`` is ``geni profile get profile-g<absorbed_guid>``'s payload.
    A merged-away profile 404s (None/empty) or now resolves to the survivor's
    guid. Anything else is still a distinct live profile — the merge has NOT
    happened, and wiring the fold would plan a destroy.
    """
    if not fetched:
        return "merged"
    return "merged" if str(fetched.get("guid") or "") == survivor_guid else "distinct"


def fetch_merge_state(absorbed_guid: str, survivor_guid: str) -> str:
    try:
        fetched = _geni_json(["profile", "get", f"profile-g{absorbed_guid}"])
    except Exception:
        return "distinct"  # can't prove the merge → refuse to wire (fail safe)
    return merge_state(fetched if isinstance(fetched, dict) else None, survivor_guid)


def unmerged_absorbed(reports: list[ConflictReport],
                      state_fn: Any = fetch_merge_state) -> dict[str, str]:
    """AUTO folds whose Geni merge has not happened → {absorbed_res: reason}."""
    blocked: dict[str, str] = {}
    for report in reports:
        for fold in report.folds:
            if fold.tier != AUTO or not fold.absorbed_res:
                continue
            if state_fn(fold.absorbed.guid, fold.survivor.guid) != "merged":
                blocked[fold.absorbed_res] = (
                    f"{fold.absorbed.name} (guid {fold.absorbed.guid}) is still a "
                    f"distinct live profile — merge it into {fold.survivor.name} "
                    f"first: {fold.merge_cmd}")
    return blocked


def build_new_entries(reports: list[ConflictReport],
                      exclude_absorbed: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """AUTO folds → ``{survivor_canonical: {profile_names, generate_moved_block}}``
    for `write_new_entries_to_file` (the same shape `tf-consolidate-write` uses)."""
    entries: dict[str, dict[str, Any]] = {}
    for report in reports:
        for fold in report.folds:
            if fold.tier != AUTO or not fold.survivor_canonical or not fold.absorbed_res:
                continue
            if exclude_absorbed and fold.absorbed_res in exclude_absorbed:
                continue  # merge not confirmed — wiring it would plan a destroy
            entry = entries.setdefault(
                fold.survivor_canonical,
                {"profile_names": [], "generate_moved_block": True},
            )
            if fold.absorbed_res not in entry["profile_names"]:
                entry["profile_names"].append(fold.absorbed_res)
    return entries


# --------------------------------------------------------------------------- #
# Report (pure)
# --------------------------------------------------------------------------- #

def _res_line(label: str, cand: Candidate, res: str | None,
              canonical: str | None = None) -> str:
    who = f"{cand.name} (+{cand.subtree})"
    if res is None:
        return f"      {label}: {who}  → [not in our Terraform]"
    tail = f"  → canonical: {canonical}" if canonical and canonical != res else ""
    return f"      {label}: {who}\n          res: {res}{tail}"


def format_report(reports: list[ConflictReport], stale: int,
                  adjudicated: int = 0, failed: int = 0) -> str:
    lines: list[str] = []
    actionable = [r for r in reports if r.folds]
    head = (f"Tree conflicts: {len(reports)} inspected, {len(actionable)} actionable, "
            f"{stale} stale (has_conflict:false, skipped)")
    # Never hide a bound silently — say what was filtered out.
    head += (f", {adjudicated} adjudicated (allowlisted in {ADJUDICATED_FILE})."
             if adjudicated else ".")
    lines.append(head)
    if failed:
        lines.append(f"⚠ {failed} conflict(s) could not be read (`show` failed) — this "
                     "report is INCOMPLETE, not a clean queue.")
    lines.append("")

    tier_counts: dict[str, int] = {}
    for report in actionable:
        # `short_id` is the Merge Center's WEB id, not an API resource id —
        # rendering it as "profile-NNN" made it look like one, and passing it to
        # `geni tree-conflicts show` fails with an opaque 404. Label it.
        lines.append(f"● {report.name}  (web {report.short_id}, guid {report.guid})")
        lines.append(f"  conflict_types: {', '.join(report.conflict_types) or '—'}")
        for fold in report.folds:
            tier_counts[fold.tier] = tier_counts.get(fold.tier, 0) + 1
            if fold.tier == PLACEHOLDER:
                slot = fold.absorbed if is_placeholder(fold.absorbed) else fold.survivor
                real = fold.survivor if slot is fold.absorbed else fold.absorbed
                lines.append(f"  [PLACEHOLDER] {fold.role}: «{slot.name}» is a synthetic "
                             f"empty slot, NOT a profile. Real {fold.role}: {real.name}.")
                lines.append("      → not a merge (that 404s): detach the focus from its "
                             "empty-parent union (geni ≥ v1.23.0):")
                lines.append(f"        geni tree-conflicts resolve profile-g{report.guid}"
                             "   # add -dry-run to preview")
                continue
            lines.append(f"  [{fold.tier}] {fold.role}: "
                         f"keep {fold.survivor.name} (+{fold.survivor.subtree}) "
                         f"← absorb {fold.absorbed.name} (+{fold.absorbed.subtree})")
            lines.append(_res_line("survivor", fold.survivor, fold.survivor_res,
                                   fold.survivor_canonical))
            lines.append(_res_line("absorb  ", fold.absorbed, fold.absorbed_res))
            if fold.name_mismatch:
                # Withhold the merge command entirely — this is the line an agent
                # copies, and Geni has no un-merge.
                lines.append(f"      ⚠ NAME MISMATCH: {fold.name_mismatch} — these look "
                             "like DIFFERENT people, not a duplicate.")
                lines.append("        Two successive wives (a remarriage) present exactly "
                             "like this; check whether the record")
                lines.append("        date ranges are disjoint before doing anything.")
                lines.append(f"      1. {fold.compare_cmd}")
                lines.append("      2. merge withheld — if you vet them as one person, run "
                             "the merge by hand;")
                lines.append(f"         if they are two people, record the verdict in "
                             f"{ADJUDICATED_FILE}:")
                lines.append(f"         {report.guid}\t{fold.role}\t{fold.absorbed.guid}\t"
                             "<why they are different people>")
                continue
            lines.append(f"      1. {fold.compare_cmd}")
            lines.append(f"      2. {fold.merge_cmd}   # keep the larger subtree")
            if fold.tier == AUTO:
                lines.append(f"      3. wire: append \"{fold.absorbed_res}\" → "
                             f"\"{fold.survivor_canonical}\".profile_names "
                             f"(run with --write, AFTER the merge)")
            elif fold.tier == REVIEW:
                lines.append("      3. wire: canonical↔canonical or folded elsewhere — "
                             "run `verso detector --write` after the merge")
            elif fold.tier == DONE:
                lines.append("      3. wire: already folded onto the survivor's "
                             "canonical — nothing to do")
            else:  # UNMAPPED
                lines.append("      3. wire: a side is not in our Terraform (another "
                             "manager's profile) — vet + handle manually")
        lines.append("")

    if tier_counts:
        lines.append("Fold tiers: " + ", ".join(
            f"{k}={v}" for k, v in sorted(tier_counts.items())))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def fetch_list(collection: str, _json: Any = None) -> list[dict[str, Any]]:
    """List the account's tree conflicts.

    `null` means an EMPTY QUEUE, not an outage: `geni tree-conflicts list`
    aggregates pages into `var out []TreeConflict` (cmd/geni/resources.go), and
    Go marshals that nil slice as `null` when nothing was appended — exit 0, no
    stderr. Verified against Geni's own Merge Center page, which read
    «Конфликты древ (0)» at the same moment. A genuine failure exits non-zero and
    `_geni_json` already raises on that, so only a non-null, non-list payload is
    anomalous enough to stop the run.
    """
    args = ["tree-conflicts", "list", "-all"]
    if collection:
        args += ["-collection", collection]
    data = (_json or _geni_json)(args)
    if data is None:
        return []
    if not isinstance(data, list):
        raise TreeConflictsUnavailable(
            f"`geni tree-conflicts list` returned {type(data).__name__} "
            f"({data!r:.60}), which is neither a list nor the empty-queue null. "
            "Re-check the profile API to confirm auth is healthy, then retry.")
    return data


def fetch_show(profile_id: str) -> dict[str, Any]:
    return _geni_json(["tree-conflicts", "show", profile_id]) or {}


def gather(collection: str, limit: int, _list: Any = None,
           _show: Any = None) -> tuple[list[dict[str, Any]], int, int]:
    """(actionable show payloads, stale count, unreadable count).

    A `show` that fails (404s) yields `{}`; those are counted separately rather
    than silently dropped, so a wholly broken endpoint cannot masquerade as a
    clean queue.
    """
    listed = (_list or fetch_list)(collection)
    if limit:
        listed = listed[:limit]
    ids = [str(row.get("profile_id")) for row in listed if row.get("profile_id")]
    with ThreadPoolExecutor(max_workers=5) as pool:
        shows = list(pool.map(_show or fetch_show, ids))
    actionable = [s for s in shows if s and not is_stale(s)]
    stale = sum(1 for s in shows if s and is_stale(s))
    failed = sum(1 for s in shows if not s)
    return actionable, stale, failed


def build_reports(shows: list[dict[str, Any]], guid_to_res: dict[str, str],
                  config_keys: set[str], folded_index: dict[str, str]) -> list[ConflictReport]:
    reports: list[ConflictReport] = []
    for show in shows:
        focus = show.get("focus", {})
        pairs = parse_show(show)
        folds = plan_folds(pairs, guid_to_res, config_keys, folded_index)
        reports.append(ConflictReport(
            guid=str(focus.get("profile_id", "")),
            short_id=str(focus.get("short_id", "")),
            name=focus.get("name", "") or "",
            conflict_types=tuple(show.get("conflict_types", []) or []),
            folds=folds,
        ))
    reports.sort(key=lambda r: r.name)
    return reports


def filter_mapped(reports: list[ConflictReport]) -> list[ConflictReport]:
    """Drop UNMAPPED folds (neither side in our Terraform — another manager's
    profiles) and conflicts left with none. Keeps AUTO/REVIEW/DONE/PLACEHOLDER —
    the folds that touch our tree — so the signal isn't buried (most of a large
    account's tree conflicts are on ancestors we don't manage)."""
    out: list[ConflictReport] = []
    for r in reports:
        kept = [f for f in r.folds if f.tier != UNMAPPED]
        if kept:
            out.append(ConflictReport(r.guid, r.short_id, r.name,
                                      r.conflict_types, kept))
    return out


# --------------------------------------------------------------------------- #
# Manual triage (two-real-parent conflicts) — pure
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ParentInfo:
    """One parent of a parent-union, resolved to a res_name + life years."""
    name: str
    res_name: str | None    # our Terraform res_name, or None if external/placeholder
    birth_year: str
    death_year: str
    placeholder: bool


@dataclass(frozen=True)
class ParentUnionInfo:
    web_id: str             # the union's Geni web id (detach-union takes this)
    parents: tuple[ParentInfo, ...]


@dataclass(frozen=True)
class ManualConflict:
    """A two-real-parent conflict laid out for hand-assignment: the focus child
    plus each parent union with both parents' res_names + life years, so the
    reviewer can assign the child to the mother alive at its birth and detach the
    wrong union."""
    guid: str
    name: str
    birth_year: str
    death_year: str
    conflict_types: tuple[str, ...]
    unions: tuple[ParentUnionInfo, ...]


def _is_placeholder_pid(pid: str, name: str) -> bool:
    return bool(_PLACEHOLDER_GUID_RE.match(pid) or _PLACEHOLDER_NAME_RE.match(name))


def _parent_info(p: dict[str, Any], guid_to_res: dict[str, str]) -> ParentInfo:
    pid = str(p.get("profile_id", ""))
    name = p.get("name", "") or ""
    return ParentInfo(
        name=name,
        res_name=guid_to_res.get(pid),
        birth_year=str(p.get("birth_year") or ""),
        death_year=str(p.get("death_year") or ""),
        placeholder=bool(p.get("placeholder")) or _is_placeholder_pid(pid, name),
    )


def parse_manual(show: dict[str, Any], guid_to_res: dict[str, str]) -> ManualConflict:
    """Lay out one `show` payload as a ManualConflict (focus + parent unions)."""
    focus = show.get("focus", {})
    unions = tuple(
        ParentUnionInfo(
            web_id=str(u.get("web_union_id") or ""),
            parents=tuple(_parent_info(p, guid_to_res)
                          for p in u.get("parents", []) or []),
        )
        for u in show.get("parent_unions", []) or []
    )
    return ManualConflict(
        guid=str(focus.get("profile_id", "")),
        name=focus.get("name", "") or "",
        birth_year=str(focus.get("birth_year") or ""),
        death_year=str(focus.get("death_year") or ""),
        conflict_types=tuple(show.get("conflict_types", []) or []),
        unions=unions,
    )


def is_manual(c: ManualConflict) -> bool:
    """A two-real-parent conflict that touches our tree: ≥2 parent unions, no
    synthetic placeholder parent (those are `tree-conflicts resolve`'s job), and
    at least one parent mapped to our Terraform."""
    if len(c.unions) < 2:
        return False
    if any(p.placeholder for u in c.unions for p in u.parents):
        return False
    return any(p.res_name for u in c.unions for p in u.parents)


def _fmt_parent(p: ParentInfo) -> str:
    tag = (f"[{p.res_name}]" if p.res_name
           else "[PLACEHOLDER]" if p.placeholder else "[external]")
    return f"{p.name} (b{p.birth_year or '?'} d{p.death_year or '?'}) {tag}"


def format_manual(conflicts: list[ManualConflict], stale: int) -> str:
    """Per two-real-parent conflict: the focus child + each parent union (parents
    with res_name + life years) + a ready detach command per union. The reviewer
    keeps the union whose mother was alive at the child's birth and detaches the
    other (then adds the DSL secondary_ref_member routing)."""
    manual = [c for c in conflicts if is_manual(c)]
    lines = [
        f"Manual (two-real-parent) tree conflicts: {len(manual)} "
        f"({stale} stale skipped).",
        "Keep the parent-union whose MOTHER was alive at the child's birth year; "
        "detach the other. Then add the DSL routing so it stays fixed.",
        "",
    ]
    for c in manual:
        lines.append(f"● {c.name}  (guid {c.guid}, b{c.birth_year or '?'} "
                     f"d{c.death_year or '?'})  [{', '.join(c.conflict_types) or '—'}]")
        for u in c.unions:
            lines.append("    union " + (u.web_id or "?") + ": "
                         + " + ".join(_fmt_parent(p) for p in u.parents))
            lines.append(f"      detach if wrong:  geni profile detach-union -yes "
                         f"{c.guid} {u.web_id}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Triage Geni tree conflicts and wire their resolution into "
                    "the consolidation config.")
    parser.add_argument("--village", help="village dir (default: cwd)")
    parser.add_argument("--config", default="generate_config_names.py",
                        help="config file (default: generate_config_names.py)")
    parser.add_argument("--collection", default="managed",
                        help="viewing mode: managed|relatives|followed|collaborators")
    parser.add_argument("--limit", type=int, default=0,
                        help="cap conflicts inspected (0 = all)")
    parser.add_argument("--mapped-only", action="store_true",
                        help="hide UNMAPPED folds (another manager's ancestors) — "
                             "show only conflicts touching our tree")
    parser.add_argument("--manual", action="store_true",
                        help="two-real-parent triage: per conflict, both parent "
                             "unions with res_names + life years + ready detach "
                             "commands (for hand-assigning the child's mother)")
    parser.add_argument("--write", action="store_true",
                        help="append AUTO profile folds into the config "
                             "(run AFTER the Geni merge)")
    args = parser.parse_args()

    village_dir = Path(args.village).resolve() if args.village else Path.cwd()
    config_path = village_dir / args.config
    tf_dir = plan_paths(village_dir).tf_dir

    guid_to_res = guid_to_resource(tf_dir)
    if not guid_to_res:
        print(f"warning: no geni_profile guids from `terraform state pull` in {tf_dir}; "
              "every fold will be UNMAPPED.", file=sys.stderr)
    try:
        config = _load_consolidate_config(str(config_path))
        ptc = getattr(config, "profiles_to_consolidate", {}) or {}
    except FileNotFoundError:
        print(f"warning: {config_path} not found; canonical mapping unavailable.",
              file=sys.stderr)
        ptc = {}
    config_keys = set(ptc.keys())
    folded_index = resource_to_canonical(ptc)

    try:
        shows, stale, failed = gather(args.collection, args.limit)
    except TreeConflictsUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.manual:
        conflicts = [parse_manual(s, guid_to_res) for s in shows]
        conflicts.sort(key=lambda c: c.name)
        print(format_manual(conflicts, stale))
        return 0

    reports = build_reports(shows, guid_to_res, config_keys, folded_index)
    if args.mapped_only:
        reports = filter_mapped(reports)
    reports, adjudicated = filter_adjudicated(reports, load_adjudicated())
    print(format_report(reports, stale, adjudicated, failed))

    if args.write:
        # Wiring must follow the Geni merge. Verify it actually happened
        # rather than trusting the operator's ordering — folding two profiles
        # that still carry distinct live guids plans a DESTROY of one of them.
        blocked = unmerged_absorbed(reports)
        for absorbed_res, reason in sorted(blocked.items()):
            print(f"\n--write: REFUSING to wire \"{absorbed_res}\" — {reason}")
        new_entries = build_new_entries(reports, exclude_absorbed=set(blocked))
        if not new_entries:
            print("\n--write: no AUTO folds to append "
                  "(REVIEW/UNMAPPED folds are left for manual / tf-consolidate-write).")
        else:
            print(f"\n--write: appending {len(new_entries)} canonical fold(s) into "
                  f"{config_path.name} …")
            write_new_entries_to_file(new_entries, str(config_path))
            print("Now: `verso detector --write` (union blocks) → "
                  "a fresh plan exported to the village's `_plan.json` → "
                  "`verso verify-plan` (expect 0-destroy).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
