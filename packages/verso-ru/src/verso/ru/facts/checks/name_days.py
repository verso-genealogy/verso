"""A newborn's name no saint near the birth supports — `facts-check check=name-days`.

A child was named for a saint the Church kept around the birth or the
christening, so a birth record's name and its dates are two readings that
check each other against something the record did not write: the святцы
(`verso.ru.church_calendar.svyatcy`, the 1906 Требник). Report-only — the count
moves with every year of the sweep, so it is not in `facts_findings.tsv`.

The window is measured, not chosen, on the 8 026 births of the five villages
whose name the святцы know (2026-09-30). Relative to the birth, the nearest
saint of the child's name falls on the day itself 1 289 times, and again on
days +6 and +7 (461, 539) before dropping at +8 (293): the name was given on
the eighth day. So the window runs from `BEFORE` days before the birth to
`AFTER` days past the later of the christening and the eighth day. 79.5 % of
the births have a saint of their name inside it; given another record's day
of the same year, 25.8 % would.

A miss is usually practice, not error, and the report is a triage list. Of the
256 births whose nearest saint lies more than `FAR_DAYS` outside the window,
reading the month one off explains two; the rest are names given out of
season (Екатерина in May, Варвара in June, Татьяна in August) or a people's
form the table did not yet tie to its saint (Родион → Иродион, Алимпий →
Алипий: `ALSO_KEPT`). A look-alike name kept inside the window is not more
common among the real misses than among random days (128 against 549), so it
is shown to speed the re-crop — «Симон», born 28 August, three days before
Симеон Столпник — and marks the finding HIGH as the one worth reading first,
not as proof. A name the святцы do not know is counted apart, never a finding.

`birth(calendar_note=)` stands a finding down once the scan confirms the name.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from verso.ru.church_calendar.julian import JulianDate, anniversary, from_jdn, is_valid, jdn
from verso.ru.church_calendar.svyatcy import MonthDay, Near, Svyatcy
from verso.ru.facts.model import AssertionSet, BaptizedOn, BornOn, Citation, FactDate, NameClaim
from verso.ru.gender import Gender

#: Days before the birth a saint may be kept and still have named the child.
BEFORE = 3
#: Days past the later of the christening and the eighth day.
AFTER = 3
#: The eighth day: a child born on day 0 was named on day 7.
NAMING_DAY = 7
#: A finding lies more than this many days outside the window — where the
#: real misses run at a tenth of what random days produce.
FAR_DAYS = 30
#: How alike a name kept in the window must look to be offered as a reading.
LOOKALIKE_RATIO = 0.7
LOOKALIKES_SHOWN = 3


@dataclass(frozen=True)
class NameDayFinding:
    """A child whose name's nearest saint lies `outside` days beyond the
    window; `lookalikes` are the names kept inside it that the ink could be."""
    cite: Citation
    name: str
    gender: Gender
    born: JulianDate | None
    christened: JulianDate | None
    outside: int
    nearest: MonthDay
    lookalikes: tuple[Near, ...]

    @property
    def confidence(self) -> str:
        return "HIGH" if self.lookalikes else "LOW"


@dataclass(frozen=True)
class NameDays:
    findings: list[NameDayFinding]
    #: Births the check could ask: a name the святцы know and a dated day.
    checked: int
    #: Names the святцы do not know, with how many births carry each.
    unknown: Counter[tuple[str, Gender]]
    #: Findings the author stood down with `calendar_note=`.
    noted: int


def _day(date: FactDate | None) -> JulianDate | None:
    if date is None or date.year is None or date.month is None or date.day is None:
        return None
    return (date.year, date.month, date.day) if is_valid(date.year, date.month, date.day) else None


def window(born: JulianDate | None, christened: JulianDate) -> tuple[int, int]:
    """The window as Julian day numbers. With no birth, `christened` is the
    only anchor, and the eighth day cannot be counted."""
    end = jdn(*christened) + AFTER
    if born is None:
        return jdn(*christened) - BEFORE, end
    return jdn(*born) - BEFORE, max(end, jdn(*born) + NAMING_DAY + AFTER)


def _outside(days: tuple[MonthDay, ...], year: int, start: int, end: int) -> tuple[int, MonthDay]:
    """How far the nearest of `days` (non-empty) lies outside [start, end]."""
    gaps = [(max(start - at, at - end, 0), (m, d))
            for m, d in days for y in (year - 1, year, year + 1)
            for at in (anniversary(y, m, d),)]
    return min(gaps)


def _lookalikes(svyatcy: Svyatcy, name: str, gender: Gender,
                start: int, end: int) -> tuple[Near, ...]:
    own = set(svyatcy.keys(name, gender))
    low = name.lower()
    scored: list[tuple[float, Near]] = []
    for n in svyatcy.names_near(from_jdn(start), gender, 0, end - start):
        if n.key in own:
            continue
        ratio = max(SequenceMatcher(None, low, n.name.lower()).ratio(),
                    SequenceMatcher(None, low, n.base.lower()).ratio())
        if ratio >= LOOKALIKE_RATIO:
            scored.append((ratio, n))
    scored.sort(key=lambda t: (-t[0], t[1].name))
    return tuple(n for _, n in scored[:LOOKALIKES_SHOWN])


def name_day_findings(facts: AssertionSet, svyatcy: Svyatcy) -> NameDays:
    """Every birth whose child's name no saint near its days supports.

    `facts` is what a check reads — `believed()` — so a christening the author
    withdrew leaves the window to the birth alone.
    """
    findings: list[NameDayFinding] = []
    unknown: Counter[tuple[str, Gender]] = Counter()
    checked = noted = 0
    for record in facts.records():
        dated = record.of(BornOn) + record.of(BaptizedOn)
        if not dated or dated[0].cite.record_kind != "birth":
            continue
        child = dated[0].subject
        claims = [a for a in record.about(child) if isinstance(a, NameClaim) and a.given]
        if not claims:
            continue
        claim = claims[0]
        name, gender = claim.given or "", claim.gender
        if gender is None:
            continue
        born = _day(record.of(BornOn)[0].date) if record.of(BornOn) else None
        christened = _day(record.of(BaptizedOn)[0].date) if record.of(BaptizedOn) else None
        anchor = christened or born
        if anchor is None:
            continue
        days = svyatcy.commemorations(name, gender)
        if not days:
            unknown[(name, gender)] += 1
            continue
        checked += 1
        start, end = window(born, anchor)
        outside, nearest = _outside(days, (born or anchor)[0], start, end)
        if outside <= FAR_DAYS:
            continue
        if claim.calendar_note:
            noted += 1
            continue
        findings.append(NameDayFinding(
            cite=dated[0].cite, name=name, gender=gender, born=born,
            christened=christened, outside=outside, nearest=nearest,
            lookalikes=_lookalikes(svyatcy, name, gender, start, end)))
    findings.sort(key=lambda f: (f.confidence != "HIGH", -f.outside, f.cite.sort_key))
    return NameDays(findings=findings, checked=checked, unknown=unknown, noted=noted)
