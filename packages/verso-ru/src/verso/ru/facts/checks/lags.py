"""Too long between two dates of one entry — `check=baptism-lag` / `check=burial-lag`.

From Gramps Verify (BaptTooLate, BuryTooLate), with the thresholds measured on
the corpus rather than taken from Gramps (120 and 14 days): a birth record
dates a birth and a christening, a death record a death and a burial, and the
distance between the two is a custom, which a misread day breaks.

Measured on the five villages (2026-09-30), both dates to the day:

* **burial − death** (1 685 records): 0 days 239, 1 day 771, 2 days 609,
  3 days 49 — the third day — then 5, 1, 3, 1, 3 for four to eight days and
  single records at 11, 14, 17 and 29. A finding is past `BURIAL_DAYS`; HIGH
  past `BURIAL_HIGH_DAYS`, where no weather or absent priest explains it
  (one record: died 3 March, buried 1 April).
* **christening − birth** (7 862 records): a peak at one and two days, a long
  shoulder to eleven (57), then 19 at twelve and a thin tail. Past
  `BAPTISM_DAYS` is a finding. The tail beyond three weeks is almost all one
  shape: the christening's day of the month is SMALLER than the birth's, so
  the DSL (`birth_month_year`) put the christening in the next month —
  born the 3rd, christened «the 2nd» of the month after. One of the two days
  is misread; that shape is HIGH (`month_carried`).

Negative distances — a christening before the birth, a burial before the
death — are `date-order`'s and not repeated here.

A lag the scan confirms carries `birth(lag_note=)` / `death(lag_note=)` and is
counted (`Lags.noted`), not reported again; both dates stay believed.
"""
from __future__ import annotations

from dataclasses import dataclass

from verso.ru.church_calendar.julian import JulianDate, days_between, is_valid
from verso.ru.facts.model import AssertionSet, BaptizedOn, BornOn, BuriedOn, Citation, DiedOn, FactDate

#: A burial more than this many days after the death is a finding …
BURIAL_DAYS = 3
#: … and HIGH past this many.
BURIAL_HIGH_DAYS = 9
#: A christening more than this many days after the birth is a finding.
BAPTISM_DAYS = 11


@dataclass(frozen=True)
class LagFinding:
    """`first` (birth, death) and `second` (christening, burial) of one entry,
    `days` apart. `month_carried`: the second's day of the month is smaller
    and its month the next one — the shape of a misread day."""
    cite: Citation
    kind: str  # "baptism" or "burial"
    first: JulianDate
    second: JulianDate
    days: int
    month_carried: bool

    @property
    def confidence(self) -> str:
        if self.kind == "burial":
            return "HIGH" if self.days > BURIAL_HIGH_DAYS else "LOW"
        return "HIGH" if self.month_carried else "LOW"


@dataclass(frozen=True)
class Lags:
    findings: list[LagFinding]
    #: Findings the author stood down with `lag_note=`.
    noted: int


def _day(date: FactDate) -> JulianDate | None:
    if date.year is None or date.month is None or date.day is None:
        return None
    return (date.year, date.month, date.day) if is_valid(date.year, date.month, date.day) else None


def _lags(facts: AssertionSet, *, kind: str, record_kind: str, early: type, late: type,
          threshold: int) -> Lags:
    found: list[LagFinding] = []
    noted = 0
    for record in facts.records():
        a, b = record.of(early), record.of(late)
        if not a or not b or a[0].cite.record_kind != record_kind:
            continue
        first, second = _day(a[0].date), _day(b[0].date)
        if first is None or second is None:
            continue
        days = days_between(first, second)
        if days <= threshold:
            continue
        if b[0].lag_note:
            noted += 1
            continue
        carried = second[1] == first[1] % 12 + 1 and second[2] < first[2]
        found.append(LagFinding(cite=a[0].cite, kind=kind, first=first, second=second,
                                days=days, month_carried=carried))
    found.sort(key=lambda f: (f.confidence != "HIGH", -f.days, f.cite.sort_key))
    return Lags(findings=found, noted=noted)


def baptism_lags(facts: AssertionSet) -> Lags:
    """Births christened more than `BAPTISM_DAYS` after the birth."""
    return _lags(facts, kind="baptism", record_kind="birth", early=BornOn, late=BaptizedOn,
                 threshold=BAPTISM_DAYS)


def burial_lags(facts: AssertionSet) -> Lags:
    """Deaths buried more than `BURIAL_DAYS` after the death."""
    return _lags(facts, kind="burial", record_kind="death", early=DiedOn, late=BuriedOn,
                 threshold=BURIAL_DAYS)
