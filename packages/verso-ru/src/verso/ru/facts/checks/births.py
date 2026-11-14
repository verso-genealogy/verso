"""Two birth claims one life cannot hold — `facts-check check=birth-claims`.

The first channel that looks for a fold that went TOO FAR: every record a
canonical was folded from still says when the person was born (`BornOn`, and
each `AgedYears` read as the birth interval it asserts through `age_bounds`),
and two of them too far apart are two people. The slack is measured, not
chosen; the constants below say where each number came from.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from verso.ru.ages import DAYS_PER_YEAR, age_bounds
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import AgedYears, Assertion, AssertionSet, BornOn
from verso.ru.facts.rules.disagreement import contradictions, held


#: The two kinds of claim that place a birth, paired as `birth-claims` compares
#: them. Named HERE, as `_orderings` names its four: the rule takes both as type
#: parameters, and a third kind of claim costs a line in this table.
def birth_pairs() -> list[tuple[Any, Any]]:
    return [(BornOn, BornOn), (BornOn, AgedYears), (AgedYears, AgedYears)]


#: How far two birth claims of one person may sit apart before they cannot both
#: be true: two years, or a fifth of the older stated age, whichever is wider.
#: Measured, not chosen, on the Горюхино people a burial and a сказка both give
#: an age: below forty the two agree to within a year almost always; from forty
#: they spread by five years either way; so the slack has to grow with the age.
#: The gap it is compared to is already net of what each age ASSERTS («40 лѣтъ»
#: is [40, 41) years), so the slack is only for a clerk who misjudged.
BIRTH_SLACK_YEARS = 2.0
_BIRTH_SLACK_FRACTION = 0.20

#: From this age a stated age is weak evidence of an EARLIER birth. Over seventy,
#: the Горюхино burials name a man older than his сказка did 34 times and
#: younger 11 — the old are made older — while from sixty to sixty-nine the two
#: err either way about equally.
_OLD_AGE_YEARS = 70.0

#: How far the old are made older, as a ratio of the stated age to the age the
#: other record implies. Measured on the 286 Горюхино ages of sixty and over
#: that another record reads younger: 244 overstate by at most a tenth, 27 by a
#: fifth, 11 by 30 % — and then nothing until 1.40 (two), and 2.2 and 2.95 (two
#: more, a 44-year-old buried at «98» and a girl of eight in one roll who is 77
#: in the next). Up to the break it is the parish's habit; past it, two people.
_OLD_AGE_OVERSTATEMENT = 1.3


@dataclass(frozen=True)
class BirthSpan:
    """The days a birth claim allows, and the age it was read from (0 for a
    birth the record dates itself).

    The days are proleptic-Gregorian ordinals of the Julian-numbered dates —
    NOT Julian days. Moving them to `verso.ru.church_calendar.julian` is right
    (`DAYS_PER_YEAR` is exactly the Julian year, so year boundaries come out
    exact) but not neutral: an age that is a multiple of two years lands on
    a half day, and `round` then pushes a boundary into the next year. That
    needs floor/ceil and its own before/after; read the ends through
    `first_year`/`last_year` so the unit stays this class's business.
    """
    first: int
    last: int
    stated_years: float

    @property
    def first_year(self) -> int:
        return date.fromordinal(self.first).year

    @property
    def last_year(self) -> int:
        return date.fromordinal(self.last).year


def birth_span(claim: Any) -> BirthSpan | None:
    """A claim about a birth as the interval of days it can mean.

    A dated birth is its own interval. A stated age is the interval it asserts
    (`age_bounds` — the parser `death-age-check` uses, so the two cannot read
    one age two ways) subtracted from the interval of the day it was stated on.
    None when either end cannot be placed: an age the parser declines, or a
    date open at one end.
    """
    def days(at: tuple[int, int, int] | None) -> int | None:
        try:
            return date(*at).toordinal() if at is not None else None
        except ValueError:
            return None

    if isinstance(claim, AgedYears):
        span = age_bounds(claim.age)
        lo, hi = days(claim.as_of.earliest), days(claim.as_of.latest)
        if span is None or lo is None or hi is None:
            return None
        return BirthSpan(first=round(lo - span[1]), last=round(hi - span[0]),
                         stated_years=span[0] / DAYS_PER_YEAR)
    lo, hi = days(claim.date.earliest), days(claim.date.latest)
    if lo is None or hi is None:
        return None
    return BirthSpan(first=lo, last=hi, stated_years=0.0)


def birth_slack_years(stated_years: float) -> float:
    """How far apart two births of one person may be read, when the older of
    their ages is `stated_years` (0 for a birth the record dates itself)."""
    return max(BIRTH_SLACK_YEARS, _BIRTH_SLACK_FRACTION * stated_years)


def years_apart(x: BirthSpan, y: BirthSpan) -> float:
    """The years between the nearest ends of two birth spans; 0 when they meet."""
    return max(0, y.first - x.last, x.first - y.last) / DAYS_PER_YEAR


@dataclass(frozen=True)
class BirthGap:
    """Why two birth claims cannot both stand: how far apart, what was allowed,
    and whether the earlier birth rests on an old age overstated the way the
    books overstate one — not by more."""
    years: float
    allowed: float
    weak: bool


def birth_gap(a: Any, b: Any) -> BirthGap | None:
    """The incompatibility `birth-claims` hands the rule.

    Two claims read from ONE entry are not compared: a roll's two age columns
    are CAI002's to check against each other while the record is typed, and
    the question here is whether two entries describe one person.
    """
    if a.cite.record_id == b.cite.record_id:
        return None
    x, y = birth_span(a), birth_span(b)
    if x is None or y is None:
        return None
    years = years_apart(x, y)
    allowed = birth_slack_years(max(x.stated_years, y.stated_years))
    if years <= allowed:
        return None
    earlier, later = (x, y) if x.last < y.first else (y, x)
    said = earlier.stated_years
    # The age the later-placed record gives the person on the day the old age
    # was stated, compared midpoint to midpoint.
    implied = said - ((later.first + later.last)
                      - (earlier.first + earlier.last)) / 2 / DAYS_PER_YEAR
    return BirthGap(years=years, allowed=allowed,
                    weak=(said >= _OLD_AGE_YEARS and implied > 0
                          and said <= _OLD_AGE_OVERSTATEMENT * implied))


@dataclass(frozen=True)
class BirthFinding:
    """One person whose records place their birth where it cannot all be."""
    who: IdentityKey
    widest: BirthGap
    claims: tuple[Assertion, ...]
    confidence: str


def birth_claims_of(facts: AssertionSet, identity: Any, *,
                    min_gap_years: float = 0.0) -> list[BirthFinding]:
    """People holding two birth claims that cannot both be true, widest first.

    WHO is the disagreement rule's to say, over the three pairings of
    `_birth_pairs`. A person is reported once, by their widest gap, and LOW
    when every gap they hold rests on an old age made older by no more than
    the books make one — the way a parish errs, not the way two people differ.
    WHAT is printed is every birth claim they hold, which is the question
    `held` answers.
    """
    gaps: dict[IdentityKey, list[BirthGap]] = {}
    for left, right in birth_pairs():
        for c in contradictions(facts, left=left, right=right,
                                identity=identity, incompatible=birth_gap):
            gaps.setdefault(c.who, []).append(cast(BirthGap, c.verdict))

    claims: dict[IdentityKey, list[Assertion]] = {}
    for kind in dict.fromkeys(k for pair in birth_pairs() for k in pair):
        for who, held_claims in held(facts, kind=kind, identity=identity).items():
            if who in gaps:
                claims.setdefault(who, []).extend(held_claims)

    def placed(claim: Assertion) -> tuple[int, tuple[object, ...]]:
        span = birth_span(claim)
        return (span.first if span is not None else 0, claim.sort_key)

    found: list[BirthFinding] = []
    for who, held_gaps in gaps.items():
        # Of two equal gaps, the one allowed less is the harder contradiction.
        widest = max(held_gaps, key=lambda g: (g.years, -g.allowed))
        if widest.years < min_gap_years:
            continue
        found.append(BirthFinding(
            who=who, widest=widest,
            claims=tuple(sorted(claims[who], key=placed)),
            confidence="LOW" if all(g.weak for g in held_gaps) else "HIGH"))
    found.sort(key=lambda f: (-f.widest.years, f.who))
    return found
