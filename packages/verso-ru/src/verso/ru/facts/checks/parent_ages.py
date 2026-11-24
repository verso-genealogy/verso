"""A parent's age no birth can have — `check=parent-ages`.

A civil birth act states each parent's age (`birth(father_age=, mother_age=)`): an
`AgedYears` dated to the child's birth, cited at the locator «father» or «mother».
Read as the interval it asserts (`verso.ru.ages.age_bounds`: «14» is [14, 15)
years), the age is a finding when the WHOLE interval lies outside what a parent
can be: a mother is 13 to 52, a father at least 15 and no older than the
book can say (a father of seventy is a father of seventy). `high <= minimum` or
`low > maximum`: «отцу 14» is a finding, «матери 52» is not, «53» is.

An age `age_bounds` cannot read («3…», «около 30») asserts no interval and no
finding. The author's `source_age_error=` retracts both ages of the act, so
nothing is left here to find.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from verso.ru.ages import DAYS_PER_YEAR, age_bounds
from verso.ru.facts.checks.births import BirthSpan, birth_span, years_apart
from verso.ru.facts.identity import Identity, IdentityKey, display_name, kin_matches
from verso.ru.facts.model import AgedYears, AssertionSet, Citation, Derived, NameClaim, Persona, Record, SpouseOf

MOTHER_MIN = 13
MOTHER_MAX = 52
FATHER_MIN = 15

_ROLES = ("father", "mother")


@dataclass(frozen=True)
class ParentAgeFinding:
    """The stated `age` of the `role`'s parent: the years it asserts, `[low_years, high_years)`, lie outside
    what a birth allows."""
    subject: str
    cite: Citation
    role: Literal["father", "mother"]
    age: object
    low_years: float
    high_years: float
    confidence: str = "HIGH"


def parent_age_findings(facts: AssertionSet) -> list[ParentAgeFinding]:
    found: list[ParentAgeFinding] = []
    for claim in facts.of(AgedYears):
        role = claim.cite.locator
        if claim.cite.record_kind != "birth" or role not in _ROLES:
            continue
        bounds = age_bounds(claim.age)
        if bounds is None:
            continue
        low, high = round(bounds[0] / DAYS_PER_YEAR, 6), round(bounds[1] / DAYS_PER_YEAR, 6)
        minimum = MOTHER_MIN if role == "mother" else FATHER_MIN
        if high <= minimum or (role == "mother" and low > MOTHER_MAX):
            found.append(ParentAgeFinding(
                subject=str(claim.subject), cite=claim.cite, role=role,  # type: ignore[arg-type]
                age=claim.age, low_years=low, high_years=high))
    found.sort(key=lambda f: (f.cite.sort_key, f.role))
    return found


#: Two acts of one couple state ages whose birth intervals lie further apart than this: the same pair of lives
#: cannot have both. Its own constant, not `birth_slack_years`: that one allows a lifetime's drift in an old
#: age; this compares two statements a few years apart — measured, 136 of 164 couples with two acts differ by up
#: to three years, 28 by four or more.
DRIFT_SLACK_YEARS = 2.0

_CO_PARENTS = "birth.co-parents-are-spouses"


@dataclass(frozen=True)
class DriftFinding:
    """The `role`'s ages in two neighbouring acts of one couple: the birth intervals they imply are
    `gap_years` apart (`years_apart` of `birth_span` — 0 where they meet)."""
    couple: tuple[IdentityKey, IdentityKey]
    role: Literal["father", "mother"]
    first: Citation
    second: Citation
    gap_years: float
    confidence: str
    first_age: float | int | str | None
    second_age: float | int | str | None
    #: The couple as the group's first act names them: the father's and the mother's display name.
    names: tuple[str, str]


@dataclass(frozen=True)
class _Act:
    sort: tuple[object, ...]
    father: IdentityKey
    mother: IdentityKey
    names: tuple[str, str]
    spans: dict[str, tuple[BirthSpan, AgedYears]]
    folded: dict[str, IdentityKey | None]


def _named(record: Record, who: Persona) -> str:
    claims = [a for a in record.about(who) if isinstance(a, NameClaim) and a.given]
    return display_name(claims[0]) if claims else "?"


def _acts(facts: AssertionSet, pair: Identity, folded: Identity | None) -> list[_Act]:
    acts: list[_Act] = []
    for record in facts.records():
        people: dict[str, Persona] = {}
        for link in record.of(SpouseOf):
            if (isinstance(link.basis, Derived) and link.basis.rationale == _CO_PARENTS
                    and link.cite.locator in _ROLES):
                people[link.cite.locator] = link.subject
        if len(people) != 2:
            continue
        key = pair(record)
        father, mother = key(people["father"]), key(people["mother"])
        if father is None or mother is None:
            continue
        spans: dict[str, tuple[BirthSpan, AgedYears]] = {}
        for claim in record.of(AgedYears):
            span = birth_span(claim) if claim.cite.locator in _ROLES and claim.subject == people[claim.cite.locator] else None
            if span is not None:
                spans[claim.cite.locator] = (span, claim)
        if not spans:
            continue
        who = folded(record) if folded is not None else None
        names = tuple(_named(record, people[role]) for role in _ROLES)
        dated = next(iter(spans.values()))[1]
        acts.append(_Act(
            sort=(dated.as_of.earliest or (0, 0, 0), dated.cite.sort_key),
            father=father, mother=mother, names=names, spans=spans,  # type: ignore[arg-type]
            folded={role: (who(people[role]) if who is not None else None) for role in _ROLES}))
    return acts


def parent_age_drift(facts: AssertionSet, *, pair: Identity, folded: Identity | None = None) -> list[DriftFinding]:
    """Couples whose two neighbouring acts state ages the same lives cannot have.

    A couple is the father and mother of one birth (the `SpouseOf` the extractor derives from two parents); two
    acts are of one couple when both parents match by `kin_matches` — a patronymic compares only where both
    state it. A couple's acts are ordered by date and neighbours compared, by role. A role whose parent `folded`
    already places on one person at both acts is `birth-claims`' question and is not asked here — per role, not
    per couple: a father folded into one person is that check's, while the mother can still be a namesake and
    is asked. HIGH when both
    parents drift past `DRIFT_SLACK_YEARS` the same way; otherwise LOW.
    """
    groups: list[tuple[tuple[IdentityKey, IdentityKey], list[_Act]]] = []
    for act in _acts(facts, pair, folded):
        # Greedy: an act joins the first group whose FIRST act it matches. `kin_matches` is not transitive —
        # a missing patronymic matches both of two that differ — so the grouping depends on the order of the
        # acts; the first act speaks for its group.
        for couple, members in groups:
            if kin_matches(couple[0], act.father) and kin_matches(couple[1], act.mother):
                members.append(act)
                break
        else:
            groups.append(((act.father, act.mother), [act]))
    found: list[DriftFinding] = []
    for couple, members in groups:
        members.sort(key=lambda a: a.sort)
        for before, after in pairwise(members):
            drifted: list[tuple[str, float, int]] = []
            for role in _ROLES:
                if role not in before.spans or role not in after.spans:
                    continue
                if before.folded[role] is not None and before.folded[role] == after.folded[role]:
                    continue
                (x, _a), (y, _b) = before.spans[role], after.spans[role]
                gap = years_apart(x, y)
                if gap > DRIFT_SLACK_YEARS:
                    drifted.append((role, gap, 1 if y.first + y.last > x.first + x.last else -1))
            high = len(drifted) == 2 and drifted[0][2] == drifted[1][2]
            for role, gap, _direction in drifted:
                found.append(DriftFinding(
                    couple=couple, role=role,  # type: ignore[arg-type]
                    first=before.spans[role][1].cite, second=after.spans[role][1].cite,
                    gap_years=round(gap, 1), confidence="HIGH" if high else "LOW",
                    first_age=before.spans[role][1].age, second_age=after.spans[role][1].age, names=before.names))
    return found
