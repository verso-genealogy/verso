"""Ages at the wedding the law or the family cannot hold — `check=wedding-ages`.

From Gramps Verify (EarlyMarriage, LargeAgeGapFamily), asked of the ages a
marriage record states for the groom and the bride (`AgedYears` dated to the
wedding), read as the interval each asserts (`verso.ru.ages.age_bounds`: «17»
is [17, 18) years).

**Under age.** The minimum is set by the DATE of the wedding: from the
Synod's decree of 17 December 1774 a groom of 15 and a bride of 13, from
the decree of 19 July 1830 18 and 16; before 1774 nothing is asked. The
books keep a half-year short of it as their own custom — the half-year a
bishop could dispense: of the 24 ages stated under the minimum (22 grooms of
17, written «17 лет 6 мес» to «17 л 10 мес» or a bare «17», and two brides
of 15), all but one lie within half a year of it. So a finding is an age
whose upper end falls more than `DISPENSATION_YEARS` short — measured
2026-09-30, one: a groom of «17 л 2 мес». A misread
age, or a marriage the book records against the rule; either is worth the
re-crop.

**Spouses far apart.** Measured on the 351 weddings that state both ages:
302 within five years, 38 within ten, 10 within fifteen, one at fifteen, no
bride ten or more years older. A gap past `GAP_YEARS` is a LOW finding,
standing guard: a widower may marry young, and the books hold none today.

Ages the scan confirms carry `marriage(age_note=)`: the entry's findings are
counted (`WeddingAges.noted`), not reported again; both ages stay believed.
"""
from __future__ import annotations

from dataclasses import dataclass

from verso.ru.ages import DAYS_PER_YEAR, age_bounds
from verso.ru.facts.model import AgedYears, AssertionSet, Citation, FactDate, MarriedOn

#: (from this date, groom, bride) — the minimum age of marriage in force.
MINIMUM_AGES: tuple[tuple[tuple[int, int, int], int, int], ...] = (
    ((1830, 7, 19), 18, 16),
    ((1774, 12, 17), 15, 13),
)
#: How far short of the minimum the books go by custom.
DISPENSATION_YEARS = 0.5
#: Spouses further apart than this are a finding.
GAP_YEARS = 20.0


def minimum_age(married: FactDate, role: str) -> int | None:
    """The minimum age for `role` on the wedding's day, or None before 1774 or
    when the date is too vague to place against a decree."""
    if married.year is None:
        return None
    day = (married.year, married.month or 12, married.day or 31)
    for since, groom, bride in MINIMUM_AGES:
        if day >= since:
            return groom if role == "groom" else bride
    return None


@dataclass(frozen=True)
class WeddingAgeFinding:
    """`kind` "under_age": `role`'s stated `age` ends `short_years` before the
    minimum. `kind` "age_gap": the two stated ages are `gap_years` apart."""
    cite: Citation
    kind: str
    married: FactDate
    role: str | None = None
    age: object = None
    minimum: int | None = None
    ages: tuple[object, object] | None = None
    gap_years: float = 0.0

    @property
    def confidence(self) -> str:
        return "HIGH" if self.kind == "under_age" else "LOW"


@dataclass(frozen=True)
class WeddingAges:
    findings: list[WeddingAgeFinding]
    #: Findings the author stood down with `age_note=`.
    noted: int


def wedding_age_findings(facts: AssertionSet) -> WeddingAges:
    kept: list[WeddingAgeFinding] = []
    noted = 0
    for record in facts.records():
        found: list[WeddingAgeFinding] = []
        wed = record.of(MarriedOn)
        if not wed:
            continue
        married = wed[0].date
        stated: dict[str, tuple[float, float, object]] = {}
        for claim in record.of(AgedYears):
            role = claim.cite.locator
            bounds = age_bounds(claim.age)
            if role not in ("groom", "bride") or bounds is None:
                continue
            low, high = bounds[0] / DAYS_PER_YEAR, bounds[1] / DAYS_PER_YEAR
            stated[role] = (low, high, claim.age)
            minimum = minimum_age(married, role)
            if minimum is not None and high <= minimum - DISPENSATION_YEARS:
                found.append(WeddingAgeFinding(
                    cite=claim.cite, kind="under_age", married=married, role=role,
                    age=claim.age, minimum=minimum))
        if "groom" in stated and "bride" in stated:
            groom = (stated["groom"][0] + stated["groom"][1]) / 2
            bride = (stated["bride"][0] + stated["bride"][1]) / 2
            if abs(groom - bride) > GAP_YEARS:
                found.append(WeddingAgeFinding(
                    cite=wed[0].cite, kind="age_gap", married=married,
                    ages=(stated["groom"][2], stated["bride"][2]),
                    gap_years=round(abs(groom - bride), 1)))
        # One note speaks for the entry: it stands down every finding its ages make.
        if any(claim.age_note for claim in record.of(AgedYears)):
            noted += len(found)
        else:
            kept += found
    kept.sort(key=lambda f: (f.confidence != "HIGH", f.cite.sort_key))
    return WeddingAges(findings=kept, noted=noted)
