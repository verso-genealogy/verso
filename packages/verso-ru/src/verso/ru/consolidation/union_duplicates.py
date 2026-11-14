#!/usr/bin/env python3
"""Flag two same-named people sitting inside ONE union — probably one person.

A third discovery channel, structural rather than name-based. `make
consolidation-sweep` and the exact name+patronymic+surname matcher both start
from "this name appears twice in the village", which in a village of eight Ivan
Ivanoviches is a weak prior. This one starts from the union: it already asserts
that both children have the SAME two parents, so a shared given name is strong
evidence they are one person recorded twice — once by the metric book and once
by a revision, or once at birth and once at death.

Two date guards do the triage, and both encode rules the project already
learned the hard way:

- **Name reuse.** If one child died BEFORE the other was born, the parents gave
  the dead child's name to the next one. Not a duplicate (two
  birth records are two children — a namesake pair born four years apart to
  the day is exactly this).
- **Ordinary siblings.** Birth years two or more apart, both dated, is far more
  likely two children than one — a revision's age drift is ±1, not ±2.
- **Two members of one household.** When both come from the SAME household of
  the SAME revision, the scribe enumerated them on adjacent lines, so the source
  itself says there are two. The rolls really do give two LIVING children one
  name — a двор holding a girl of 16 and another of 14 of the same name, two
  boys of 7 and 6 whose names differ by a letter, twin girls the transcriber
  marked «близнец». The guard reads the rolls themselves
  (`verso.ru.facts`, `EnumeratedIn` placed on its canonical by the consolidation
  bridge), so it sees every record a profile stands for — a canonical that
  absorbed a member is still in that member's household — no res_name is
  parsed, the roll is part of the key, and a member we reconstructed
  (`hidden=True`) — whom the scribe never wrote — separates nobody. (Until
  2026-09-25 the guard could also recover households from res_names and the
  move list; that reading matched this one byte for byte on two successive
  states of the corpus and was removed.)

Two more read the records rather than the dates, off the same assertions
(`verso.ru.facts.checks.lives.lives_of_canonicals`), and run last so a pair the guards above
retired keeps its reason:

- **Two baptisms.** Each has an entry christening them, on births that cannot
  be one day. One entry is one christening, as one line of a сказка is one
  member, so the parents reused the name (`candidates.two_baptisms_conflict`
  is the sweep's form of this rule). The same birth copied into two entries is
  one day in both and proves nothing.
- **Alive after death.** One died, and the other is seen alive after the latest
  day that death can mean — counted by a roll, married, born, dead in their own
  turn. Name reuse by year is the special case the date guard sees; this reads
  the day and every sign of life. A сказка's told death year is widened by
  `date-order`'s measured slack.

Everything surviving the guards is reported as CANDIDATE. That is a signal,
not a verdict: read the households before folding. The
verdict still needs a human — the point of the check is that it narrows a whole
village to a dozen pairs worth reading.

Runs on the translated + consolidated domain model produced by
`verso.ru.pipeline.translate.translate_village`, like `age_conflicts` and
`date_order`: no terraform plan, no Geni refresh, no network. Read-only
.

Run:
    python3 -m verso.ru.consolidation.union_duplicates --village Горюхино
    verso union-duplicates --village Горюхино [--all] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterable

from verso.ru.consolidation.profile_reading import (
    birth_is_approximate, birth_year, death_year, display_name, partner_refs)
from verso.ru.facts.checks.lives import (
    Household, Lives, households_of_canonicals, lives_of_canonicals, outlived, two_baptisms)
from verso.ru.facts.projection import consolidated_identity
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.messages import t

# Two dated births this many years apart are read as separate children rather
# than one person recorded twice. A revision's age drift runs to about a year;
# two is already beyond it.
SIBLING_GAP_DEFAULT = 2

# How far a birth year derived from a stated age may sit from the truth. Same
# drift the gap above is sized against — a revision's age is about a year out,
# and a girl is the case: born in one year by her metric, «13 лет» in a census
# fifteen years later. Applied as a half-width, so a derived year covers [y-1, y+1].
_AGE_DRIFT_YEARS = 1

VERDICT_CANDIDATE = "CANDIDATE"
VERDICT_REUSED_NAME = "REUSED_NAME"
VERDICT_SIBLINGS = "SIBLINGS"
VERDICT_SAME_HOUSEHOLD = "SAME_HOUSEHOLD"
VERDICT_TWO_BAPTISMS = "TWO_BAPTISMS"
VERDICT_ALIVE_AFTER_DEATH = "ALIVE_AFTER_DEATH"

def _readable(iso: str) -> str:
    """`1850-10-01` → «01.10.1850»; a date the roll gives only in part keeps
    only that part; anything else comes back as it came."""
    parts = iso.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return iso
    year, month, day = parts
    if int(month) and int(day):
        return f"{day}.{month}.{year}"
    return f"{month}.{year}" if int(month) else year


def _no_households(_canon: str) -> frozenset[Household]:
    return frozenset()


def _no_lives(_canon: str) -> Lives:
    return Lives()


@dataclass(frozen=True)
class Member:
    res_name: str
    name: str
    birth_year: int | None
    death_year: int | None
    # True when the birth year was DERIVED — a census age subtracted from the
    # revision year, not a date the scribe wrote. `birth_year` flattens both to
    # an int, and comparing them as equal-authority numbers is what made the
    # sibling guard retire a real duplicate.
    approximate: bool = False
    # Every household a roll counted this profile into — through any record it
    # stands for, not only the one its res_name was minted from.
    households: frozenset[Household] = frozenset()
    lives: Lives = field(default_factory=Lives)


@dataclass(frozen=True)
class UnionDuplicate:
    union: str
    given_name: str
    partners: tuple[str, ...]
    members: tuple[Member, ...]
    verdict: str
    reason: str

    @property
    def is_candidate(self) -> bool:
        return self.verdict == VERDICT_CANDIDATE


def _classify(members: Iterable[Member], sibling_gap: int) -> tuple[str, str]:
    """CANDIDATE unless the records already separate these people."""
    members = list(members)
    households = [m.households for m in members]
    for i, a in enumerate(households):
        for b in households[i + 1:]:
            shared = a & b
            if shared:
                date, household, roll = sorted(shared)[0]
                where = ", ".join(p for p in (roll, _readable(date)) if p)
                return (VERDICT_SAME_HOUSEHOLD,
                        str(t("consolidation.union_dups.same_household", household=household, where=where)))
    for a in members:
        for b in members:
            if a is b:
                continue
            if a.death_year is not None and b.birth_year is not None \
                    and a.death_year < b.birth_year:
                return (VERDICT_REUSED_NAME,
                        str(t("consolidation.union_dups.reused_name", died=a.name, death_year=a.death_year,
                              born=b.name, birth_year=b.birth_year)))
    years = [m.birth_year for m in members if m.birth_year is not None]
    if len(years) == len(members) and len(set(years)) == len(years):
        # A year DERIVED from an age is an interval, not a date: the drift this
        # gap is sized against is exactly what the derivation carries. So widen
        # the derived years and ask how close the births can be read — if even
        # at their closest they stay a gap apart, they are separate children.
        # A girl born in one year by her metric and «13 лет» in a census fifteen
        # years later reads consistently at one year and is one girl; a census
        # entry and a birth five years apart cannot be read closer than four.
        lows = [m.birth_year - (_AGE_DRIFT_YEARS if m.approximate else 0)
                for m in members if m.birth_year is not None]
        highs = [m.birth_year + (_AGE_DRIFT_YEARS if m.approximate else 0)
                 for m in members if m.birth_year is not None]
        closest = max(0, max(lows) - min(highs))
        if closest >= sibling_gap:
            spread = max(years) - min(years)
            drift = "" if closest == spread else str(t("consolidation.union_dups.drift", spread=spread,
                                                         closest=closest))
            return (VERDICT_SIBLINGS,
                    str(t("consolidation.union_dups.siblings", closest=closest, drift=drift)))
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            both = two_baptisms(a.lives, b.lives)
            if both is not None:
                return (VERDICT_TWO_BAPTISMS,
                        str(t("consolidation.union_dups.two_baptisms", first=both[0], second=both[1])))
    for a in members:
        for b in members:
            if a is b:
                continue
            apart = outlived(a.lives, b.lives)
            if apart is not None:
                return (VERDICT_ALIVE_AFTER_DEATH,
                        str(t("consolidation.union_dups.alive_after_death", first=a.name, first_said=apart[0],
                              second=b.name, second_said=apart[1])))
    approx = [m.name for m in members if m.approximate and m.birth_year is not None]
    if approx:
        return (VERDICT_CANDIDATE,
                str(t("consolidation.union_dups.candidate_approximate", names=", ".join(approx))))
    return VERDICT_CANDIDATE, str(t("consolidation.union_dups.candidate"))


def find_union_duplicates(
        profiles: dict[str, GeniProfile],
        unions: dict[str, Any],
        resolve: Callable[[str], str],
        *,
        sibling_gap: int = SIBLING_GAP_DEFAULT,
        households_of: Callable[[str], frozenset[Household]] | None = None,
        lives_of: Callable[[str], Lives] | None = None,
) -> list[UnionDuplicate]:
    """Groups of union children who share a given name.

    `resolve(ref)` normalises a union child/partner ref onto its canonical
    res_name; a resolved ref absent from `profiles` is external and skipped.
    `households_of(canonical)` names every household a roll counted that
    canonical into — the evidence the same-household guard stands on
    (`verso.ru.facts.checks.lives.households_of_canonicals`); without it no pair is
    separated by a household. `lives_of(canonical)` is what its records say
    about its baptisms, death and later life (`verso.ru.facts.checks.lives.lives_of_canonicals`);
    without it the two guards that read them stay silent.
    Results are sorted candidates-first, then by union name for stability.
    """
    counted_in = households_of or _no_households
    life_of = lives_of or _no_lives
    found: list[UnionDuplicate] = []
    for union_name, union in sorted(unions.items()):
        by_given: dict[str, list[Member]] = defaultdict(list)
        for ref in sorted(getattr(union, "children", None) or set()):
            canon = resolve(ref)
            profile = profiles.get(canon)
            if profile is None:
                continue  # external / co-managed child — not ours to judge
            given = (profile.first_name or "").strip()
            if not given:
                continue
            by_given[given].append(Member(
                res_name=canon,
                name=display_name(profile),
                birth_year=birth_year(profile),
                death_year=death_year(profile),
                approximate=birth_is_approximate(profile),
                households=counted_in(canon),
                lives=life_of(canon),
            ))
        partners = tuple(resolve(p) for p in partner_refs(union))
        for given, members in sorted(by_given.items()):
            unique = {m.res_name: m for m in members}
            if len(unique) < 2:
                continue
            verdict, reason = _classify(unique.values(), sibling_gap)
            found.append(UnionDuplicate(
                union=union_name,
                given_name=given,
                partners=partners,
                members=tuple(sorted(unique.values(), key=lambda m: m.res_name)),
                verdict=verdict,
                reason=reason,
            ))
    found.sort(key=lambda d: (not d.is_candidate, d.union, d.given_name))
    return found


def _group_lines(d: UnionDuplicate, *, verdict: bool) -> list[str]:
    head = str(t("consolidation.union_dups.group", name=d.given_name, union=d.union))
    lines = ["", f"{head}  [{d.verdict}]" if verdict else head]
    if verdict:
        lines.append(f"    {d.reason}")
    lines.append(str(t("consolidation.union_dups.parents",
                       parents=", ".join(d.partners) or str(t("consolidation.union_dups.single_parent")))))
    for m in d.members:
        born = m.birth_year if m.birth_year is not None else "?"
        died = str(t("consolidation.union_dups.died", year=m.death_year)) if m.death_year is not None else ""
        lines.append(str(t("consolidation.union_dups.member", born=born, died=died, name=m.name)))
        lines.append(f"          {m.res_name}")
    return lines


def format_report(found: list[UnionDuplicate], *, all_groups: bool = False) -> str:
    """The candidates; with `all_groups`, then every group a guard retired,
    each with the verdict and the reason — the only way to read WHY a pair was
    let go without switching to JSON."""
    candidates = [d for d in found if d.is_candidate]
    retired = [d for d in found if not d.is_candidate]
    counts: dict[str, int] = defaultdict(int)
    for d in found:
        counts[d.verdict] += 1
    lines = [str(t("consolidation.union_dups.head", groups=len(found), candidates=len(candidates),
                   reused=counts[VERDICT_REUSED_NAME], siblings=counts[VERDICT_SIBLINGS],
                   household=counts[VERDICT_SAME_HOUSEHOLD], baptisms=counts[VERDICT_TWO_BAPTISMS],
                   alive=counts[VERDICT_ALIVE_AFTER_DEATH]))]
    if not candidates:
        lines.append(str(t("consolidation.no_candidates")))
    else:
        lines.append("")
        lines.append(str(t("consolidation.union_dups.signal")))
        for d in candidates:
            lines += _group_lines(d, verdict=False)
    if all_groups and retired:
        lines.append("")
        lines.append(str(t("consolidation.union_dups.retired")))
        for d in retired:
            lines += _group_lines(d, verdict=True)
    return "\n".join(lines)


def findings_to_json(found: list[UnionDuplicate]) -> str:
    payload = [
        {
            "union": d.union,
            "given_name": d.given_name,
            "partners": list(d.partners),
            "verdict": d.verdict,
            "reason": d.reason,
            "members": [
                {
                    "res_name": m.res_name,
                    "name": m.name,
                    "birth_year": m.birth_year,
                    "death_year": m.death_year,
                }
                for m in d.members
            ],
        }
        for d in found
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run(
        profiles: dict[str, GeniProfile],
        unions: dict[str, Any],
        resolve: Callable[[str], str],
        *,
        sibling_gap: int,
        as_json: bool,
        all_groups: bool,
        households_of: Callable[[str], frozenset[Household]] | None = None,
        lives_of: Callable[[str], Lives] | None = None,
) -> tuple[str, int]:
    found = find_union_duplicates(profiles, unions, resolve,
                                  sibling_gap=sibling_gap,
                                  households_of=households_of,
                                  lives_of=lives_of)
    # JSON is machine output and always carries every group; `all_groups` is
    # about what a human reads.
    text = findings_to_json(found) if as_json \
        else format_report(found, all_groups=all_groups)
    return text, (1 if any(d.is_candidate for d in found) else 0)


def union_evidence(village_dir: Path) -> tuple[
        Any, dict[str, frozenset[Household]], dict[str, Lives]]:
    """The translation, and what each canonical's records say that separates
    namesakes: its households read off the rolls, and its lives.

    One discovery for all three, as everywhere the bridge is used: the
    translation `union-dups` reads its unions from is the one whose minting
    the bridge consults.
    """
    from verso.ru.pipeline.facts import consolidated_facts

    facts, gen, slots = consolidated_facts(village_dir)
    believed = facts.believed()
    identity = consolidated_identity(gen, slots.object_of)
    return (gen, households_of_canonicals(believed, identity),
            lives_of_canonicals(believed, identity))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag two same-named people inside one union — the union "
                    "already asserts shared parents, so a shared given name is "
                    "strong evidence of one person recorded twice.")
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--sibling-gap", type=int, default=SIBLING_GAP_DEFAULT,
                    help="birth years this far apart are read as separate children "
                         f"(default {SIBLING_GAP_DEFAULT})")
    ap.add_argument("--all", action="store_true", dest="all_groups",
                    help="include the groups the date guards retired")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    gen, households, lives = union_evidence(Path(args.village))
    text, code = run(gen.canonical_profiles(), gen.canonical_unions(),
                     gen.resolve_canonical,
                     sibling_gap=args.sibling_gap, as_json=args.json,
                     all_groups=args.all_groups,
                     households_of=lambda canon: households.get(canon, frozenset()),
                     lives_of=lambda canon: lives.get(canon, Lives()))
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
