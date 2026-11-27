"""A father's and a child's ages within one roll — `check=household-ages`.

A revision tale or a confession list states every member's age on the day it was taken (and, a revision
before, the previous column): `AgedYears`, dated to the roll or to the revision before it. Where the roll's own
word makes one member the child of another (`ParentOf` with a `Stated` basis, never the parent the household
reconstructs), the two ages at ONE date say how old the father was at the birth: read as the intervals they
assert (`verso.ru.ages.age_bounds`: «23» is [23, 24) years), the difference is a finding when the WHOLE interval
lies under the age of fatherhood (`FATHER_MIN`), and, when it lies at or below zero, the child is older than its
father.

Fathers only: a roll asserts no mothers — a wife is stated only as her husband's spouse, a son named at her is
the head's. A member gone before the roll (his current column blank) is compared at the previous revision, by
both previous ages; a member with no age, or an age `age_bounds` cannot read, is not compared. The author's
`source_age_error=` withdraws a member's ages, and with them every finding that stands on them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from verso.ru.ages import DAYS_PER_YEAR, age_bounds
from verso.ru.facts.checks.parent_ages import FATHER_MIN
from verso.ru.facts.model import AgedYears, AssertionSet, Citation, FactDate, NameClaim, ParentOf, Persona, Stated
from verso.ru.gender import Gender


@dataclass(frozen=True)
class HouseholdAgeFinding:
    """The `parent`'s age beside the `child`'s, taken at one date of one roll: the years the father was at the
    birth lie in `(gap_low, gap_high)`. `cite` is the father's age, where a note stands it down; `child_cite` the
    child's, which names the child among the household's members."""
    parent: str
    child: str
    cite: Citation
    child_cite: Citation
    gap_low: float
    gap_high: float
    kind: Literal["too_young", "child_older"]
    confidence: str


def _years(age: object) -> tuple[float, float] | None:
    bounds = age_bounds(age)
    if bounds is None:
        return None
    return bounds[0] / DAYS_PER_YEAR, bounds[1] / DAYS_PER_YEAR


def _dated(facts: AssertionSet) -> dict[Persona, dict[FactDate, AgedYears]]:
    """Every member's ages by the date they are taken on. An age with no date (the roll does not date the
    column of one gone before it) compares with nothing."""
    ages: dict[Persona, dict[FactDate, AgedYears]] = {}
    for claim in facts.of(AgedYears):
        if claim.as_of:
            ages.setdefault(claim.subject, {}).setdefault(claim.as_of, claim)
    return ages


def household_age_findings(facts: AssertionSet) -> list[HouseholdAgeFinding]:
    """The pairs of a roll's father and child whose ages at one date no birth can have; `facts` are the
    assertions a reader may believe (`AssertionSet.believed()`)."""
    males = {c.subject for c in facts.of(NameClaim) if c.gender == Gender.MALE}
    ages = _dated(facts)
    found: list[HouseholdAgeFinding] = []
    seen: set[tuple[Persona, Persona]] = set()
    for link in facts.of(ParentOf):
        pair = (link.subject, link.other)
        if not isinstance(link.basis, Stated) or link.subject not in males or pair in seen:
            continue
        seen.add(pair)
        father, child = ages.get(link.subject, {}), ages.get(link.other, {})
        for date in sorted(father.keys() & child.keys(), key=lambda d: d.earliest or (0, 0, 0), reverse=True):
            old, young = _years(father[date].age), _years(child[date].age)
            if old is None or young is None:
                continue                       # an age nothing reads asserts nothing: try the other column
            low, high = round(old[0] - young[1], 6), round(old[1] - young[0], 6)
            if high <= FATHER_MIN:
                found.append(HouseholdAgeFinding(
                    parent=str(link.subject), child=str(link.other), cite=father[date].cite,
                    child_cite=child[date].cite, gap_low=low, gap_high=high,
                    kind="child_older" if high <= 0 else "too_young", confidence="HIGH"))
            break                              # the latest date both are aged at speaks for the pair
    found.sort(key=lambda f: (f.cite.sort_key, f.child))
    return found
