#!/usr/bin/env python3
"""Find the canonical a name-list entry or an external card is a duplicate of.

The sixth discovery channel. A name list (1917 voter lists) and an external
card (судимость, ПМВ, ВОВ) each mint a deliberate duplicate of somebody the
metric books and rolls already hold — to be reconciled in the consolidation
pass (AGENTS.md). This proposes the reconciliation: for every person made only
of lists and cards, the canonicals whose records name them alike, with the
guards that retire a namesake. The rule is `verso.ru.facts.checks.reconcile`.

Read-only. A candidate is a SIGNAL, not a verdict: read
both, then fold by hand. `--audit-folded` runs the folds a human already made
through the same rule, as its oracle.

Run:
    python3 -m verso.ru.consolidation.reconcile --village Горюхино
    verso reconcile --village Маниловка [--all] [--json] [--audit-folded]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from verso.ru.ages import format_age
from verso.ru.consolidation.profile_reading import display_name as profile_name
from verso.ru.facts.checks.births import birth_span
from verso.ru.facts.checks.reconcile import (
    Audit, Backing, Reconciliation, Side, VERDICT_AMBIGUOUS, VERDICT_CANDIDATE, VERDICT_NONE, audit_folded, reconcile)
from verso.ru.facts.identity import display_name
from verso.ru.facts.model import AgedYears, BornOn, DiedOn, NameClaim, SurvivedUntil
from verso.ru.facts.projection import canonical_name, consolidated_identity
from verso.ru.messages import t

def _kind(kind: str) -> str:
    """A record kind as the report names it."""
    words = {"list": t("consolidation.reconcile.kind.list"), "external": t("consolidation.reconcile.kind.external"),
             "birth": t("consolidation.reconcile.kind.birth"), "marriage": t("consolidation.reconcile.kind.marriage"),
             "death": t("consolidation.reconcile.kind.death"), "census": t("consolidation.reconcile.kind.census")}
    return str(words[kind]) if kind in words else kind


def _named(side: Side) -> str:
    for c in side.claims:
        if isinstance(c, NameClaim) and c.given:
            return display_name(c)
    return "?"


def _born(side: Side) -> str:
    """The years this person's records place the birth in, widest first."""
    spans = [s for c in side.births if (s := birth_span(c)) is not None]
    if not spans:
        return str(t("consolidation.reconcile.no_birth"))
    first = min(s.first_year for s in spans)
    last = max(s.last_year for s in spans)
    return (str(t("consolidation.reconcile.born", year=first)) if first == last
            else str(t("consolidation.reconcile.born_between", first=first, last=last)))


def _source(side: Side) -> str:
    """Where the target was read: each list entry or card, with what it says."""
    parts: list[str] = []
    seen: set[tuple[object, ...]] = set()
    for c in side.claims:
        cite = c.cite
        if cite.record_id in seen:
            continue
        seen.add(cite.record_id)
        page = str(t("consolidation.leaf", page=cite.page)) if cite.page else ""
        said = []
        for a in side.claims:
            if a.cite.record_id != cite.record_id:
                continue
            if isinstance(a, AgedYears):
                said.append(str(t("consolidation.reconcile.said.age", age=format_age(a.age) or a.age, as_of=a.as_of)))
            elif isinstance(a, BornOn):
                said.append(str(t("consolidation.reconcile.said.born", date=a.date)))
            elif isinstance(a, DiedOn):
                said.append(str(t("consolidation.reconcile.said.died", date=a.date)))
            elif isinstance(a, SurvivedUntil) and not said:
                said.append(str(t("consolidation.reconcile.said.alive", date=a.date)))
        slot = (f" · {cite.locator}" if cite.record_kind not in ("list", "external")
                else "")
        parts.append(f"{_kind(cite.record_kind)} "
                     f"{cite.source_file} №{cite.record_num}{page}{slot}"
                     + (f" — {'; '.join(said)}" if said else ""))
    return "; ".join(parts)


def _person_line(side: Side, profiles: dict[str, Any]) -> str:
    res_name = canonical_name(side.key) or ""
    profile = profiles.get(res_name)
    name = profile_name(profile) if profile is not None else _named(side)
    records = len({c.cite.record_id for c in side.claims})
    return str(t("consolidation.reconcile.person", name=name, res_name=res_name, born=_born(side), records=records))


def household_ordered_lists(gen: Any) -> frozenset[str]:
    """The name-list files that run household by household
    (`name_list_records(household_order=True)`) — the only lists on which an
    entry's neighbour is evidence of kinship. A statement about the source,
    read in the wiring as `source_kin_error` is for `father-claims`."""
    from verso.ru.dsl.records.name_lists import NameListRecords

    return frozenset(Path(name).name for name, recs in gen.fed_sources
                     if isinstance(recs, NameListRecords)
                     and getattr(recs, "household_order", False))


def _relation(relation: str) -> str:
    """A neighbour's kinship (`verso.ru.facts.checks.neighbours`) as the report says it."""
    words = {"spouse": t("consolidation.reconcile.relation.spouse"),
             "parent": t("consolidation.reconcile.relation.parent"),
             "child": t("consolidation.reconcile.relation.child")}
    return str(words[relation]) if relation in words else relation


def _backing_line(b: Backing) -> str:
    if b.by_name:
        return str(t("consolidation.reconcile.backing_by_name", number=b.neighbour.number, name=b.neighbour.name,
                     relation=_relation(b.relation), canonical=canonical_name(b.canonical)))
    return str(t("consolidation.reconcile.backing", number=b.neighbour.number, name=b.neighbour.name,
                 canonical=canonical_name(b.canonical), relation=_relation(b.relation)))


def format_report(found: list[Reconciliation], profiles: dict[str, Any], *,
                  all_targets: bool = False, channel: str = "reconcile",
                  targets: str | None = None) -> str:
    if targets is None:
        targets = str(t("consolidation.reconcile.targets"))
    counts = {v: sum(1 for r in found if r.verdict == v)
              for v in (VERDICT_CANDIDATE, VERDICT_AMBIGUOUS, VERDICT_NONE)}
    high = sum(1 for r in found if r.is_candidate and r.confidence == "HIGH")
    backed = sum(1 for r in found if r.is_candidate and r.proposed[0].backed)
    by_list = str(t("consolidation.reconcile.by_neighbours", backed=backed)) if backed else ""
    lines = [str(t("consolidation.reconcile.head", channel=channel, count=len(found), targets=targets,
                   candidates=counts[VERDICT_CANDIDATE], high=high, by_list=by_list,
                   ambiguous=counts[VERDICT_AMBIGUOUS], none=counts[VERDICT_NONE])),
             str(t("consolidation.reconcile.signal"))]
    for r in found:
        if r.verdict == VERDICT_NONE and not all_targets:
            continue
        target = r.target
        label = (f"[{r.verdict} {r.confidence}]" if r.confidence else f"[{r.verdict}]")
        if r.through_neighbour:
            label += str(t("consolidation.reconcile.through_neighbour"))
        elif r.by_neighbours:
            label += str(t("consolidation.reconcile.chosen_by_neighbours"))
        lines += ["", f"■ {_named(target)} {label}",
                  f"    {_source(target)}",
                  str(t("consolidation.reconcile.record_profile", profile=canonical_name(target.key)))]
        if r.contested:
            lines.append(str(t("consolidation.reconcile.contested", entries=", ".join(r.contested))))
        proposed = r.proposed
        for m in r.matches:
            if m.retired is not None and not all_targets:
                continue
            if m.retired is not None:
                mark = f"✗ {m.retired}:"
            elif m in proposed:
                mark = "→"
            else:
                mark = str(t("consolidation.reconcile.also_by_name"))
            lines.append(f"  {mark} {_person_line(m.person, profiles)}")
            father = (str(t("consolidation.reconcile.father_agrees")) if m.father
                      else str(t("consolidation.reconcile.father_not_both")))
            birth = (str(t("consolidation.reconcile.birth_checked")) if m.birth_checked
                     else str(t("consolidation.reconcile.birth_unchecked")))
            lines.append(f"      {father}; {birth}"
                         + (f"; {m.reason}" if m.reason else ""))
            lines += [_backing_line(b) for b in m.backed]
    return "\n".join(lines)


def findings_to_json(found: list[Reconciliation]) -> str:
    def side(s: Side) -> dict[str, object]:
        return {"res_name": canonical_name(s.key), "name": _named(s),
                "born": _born(s), "kinds": sorted(s.kinds)}
    def backing(b: Backing) -> dict[str, object]:
        return {"entry": b.neighbour.number, "name": b.neighbour.name,
                "canonical": canonical_name(b.canonical), "relation": b.relation,
                "by_name": b.by_name}
    payload = [{"target": side(r.target), "verdict": r.verdict,
                "confidence": r.confidence, "by_neighbours": r.by_neighbours,
                "through_neighbour": r.through_neighbour,
                "contested": list(r.contested),
                "matches": [{**side(m.person), "retired": m.retired,
                             "reason": m.reason, "father": m.father,
                             "birth_checked": m.birth_checked,
                             "backed": [backing(b) for b in m.backed]}
                            for m in r.matches]}
               for r in found]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_audit(audits: list[Audit], profiles: dict[str, Any], *,
                 channel: str = "reconcile",
                 folded: str | None = None) -> str:
    if folded is None:
        folded = str(t("consolidation.reconcile.folded"))
    counts: dict[str, int] = {}
    for a in audits:
        counts[a.outcome] = counts.get(a.outcome, 0) + 1
    summary = ", ".join(f"{k} {counts.get(k, 0)}"
                        for k in ("FOUND", "AMONG", "OTHER", "MISSED"))
    lines = [str(t("consolidation.reconcile.audit_head", channel=channel, count=len(audits), folded=folded,
                   summary=summary))]
    for a in sorted(audits, key=lambda x: (x.outcome == "FOUND", x.outcome, x.canonical)):
        if a.outcome == "FOUND":
            continue
        canonical = canonical_name(a.canonical) or ""
        profile = profiles.get(canonical)
        name = profile_name(profile) if profile is not None else canonical
        lines += ["", str(t("consolidation.reconcile.audit_folded", outcome=a.outcome, name=_named(a.target),
                            canonical_name=name, canonical=canonical)),
                  f"    {_source(a.target)}",
                  f"    {a.reason}"]
        for m in a.result.proposed:
            if m.person.key != a.canonical:
                lines.append(str(t("consolidation.reconcile.channel_proposes", person=_person_line(m.person, profiles))))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--all", action="store_true", dest="all_targets",
                    help="also the targets nobody matches and the retired matches")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--audit-folded", action="store_true",
                    help="run the folds already made by hand through the rule")
    args = ap.parse_args(argv)

    from verso.ru.pipeline.facts import consolidated_facts

    facts, gen, slots = consolidated_facts(Path(args.village))
    believed = facts.believed()
    identity = consolidated_identity(gen, slots.object_of)
    profiles = gen.canonical_profiles()
    ordered = household_ordered_lists(gen)
    if args.audit_folded:
        audits = audit_folded(believed, identity, ordered_lists=ordered)
        print(format_audit(audits, profiles))
        return 1 if any(a.outcome != "FOUND" for a in audits) else 0
    found = reconcile(believed, identity, ordered)
    print(findings_to_json(found) if args.json
          else format_report(found, profiles, all_targets=args.all_targets))
    return 1 if any(r.is_candidate for r in found) else 0


if __name__ == "__main__":
    sys.exit(main())
