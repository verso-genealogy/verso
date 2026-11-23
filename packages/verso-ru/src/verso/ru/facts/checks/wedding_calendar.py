"""A wedding dated on a day the Church did not marry — `verso facts --check wedding-calendar`.

The books record what the priest did, and he did not marry in a fast, in
Bright Week or in Святки. A wedding dated there is almost always a misread
month or day; the paschalion (`verso.ru.church_calendar.paschalion`) says which
days those are, the movable ones included.

Measured on the 1 883 weddings of the five villages dated to the day and
before 1918 (2026-09-30):

* 33 fall in a STRICT ban (HIGH) — Петров пост 8, Великий пост 7,
  Рождественский 6, сырная седмица 5, Святки 5, Светлая седмица 2. Some are
  one misreading repeated: one leaf marries four couples within two days,
  in the second week of a Lent — a January read as February would put all
  four in the мясоед.
* The weekday rule is kept, not absolutely: 2.5 % of weddings fall on a
  Saturday where a random day would give 14 %, but Tuesday and Thursday
  still carry 184 (9.8 % against 28.6 %). One day misread either way turns a
  Wednesday into a Tuesday, so these are LOW — a list, not a verdict. Eves of
  great feasts and Meatfare Sunday are LOW for the same reason.

Only the strict count is in `facts_findings.tsv`: it moves when a newly read
year holds a Lent wedding, which is exactly when someone should look. A
wedding the scan confirms carries `marriage(calendar_note=)` and is not
reported again.
"""
from __future__ import annotations

from dataclasses import dataclass

from verso.ru.church_calendar.julian import JulianDate, from_jdn, is_valid, jdn, weekday
from verso.ru.church_calendar.paschalion import WeddingBan, wedding_ban
from verso.ru.facts.model import AssertionSet, Citation, MarriedOn

#: The last year of the Julian church books this check reads.
LAST_YEAR = 1917


@dataclass(frozen=True)
class WeddingFinding:
    """A wedding on a banned day, and the nearby readings of the date that
    would not be: the same day a month either side (`other_months`), a day
    either side (`other_days`)."""
    cite: Citation
    day: JulianDate
    ban: WeddingBan
    other_months: tuple[JulianDate, ...]
    other_days: tuple[JulianDate, ...]

    @property
    def confidence(self) -> str:
        return "HIGH" if self.ban.strict else "LOW"


@dataclass(frozen=True)
class WeddingCalendar:
    findings: list[WeddingFinding]
    #: Weddings dated to the day (one per entry), the ones the check could ask.
    checked: int
    #: Findings the author stood down with `calendar_note=`.
    noted: int

    @property
    def strict(self) -> int:
        return sum(1 for f in self.findings if f.ban.strict)


def _open(day: JulianDate, *, strict_only: bool) -> bool:
    ban = wedding_ban(*day)
    return ban is None or (strict_only and not ban.strict)


def _month_either_side(day: JulianDate) -> tuple[JulianDate, ...]:
    y, m, d = day
    out: list[JulianDate] = []
    for dm in (-1, 1):
        mm, yy = m + dm, y
        if mm == 0:
            mm, yy = 12, y - 1
        elif mm == 13:
            mm, yy = 1, y + 1
        if is_valid(yy, mm, d) and _open((yy, mm, d), strict_only=True):
            out.append((yy, mm, d))
    return tuple(out)


def _day_either_side(day: JulianDate) -> tuple[JulianDate, ...]:
    n = jdn(*day)
    return tuple(other for other in (from_jdn(n - 1), from_jdn(n + 1))
                 if _open(other, strict_only=False))


def wedding_calendar_findings(facts: AssertionSet) -> WeddingCalendar:
    """Every wedding dated to a day on which the Church did not marry.

    Groom and bride carry the same `MarriedOn`, so an entry is asked once.
    """
    findings: list[WeddingFinding] = []
    seen: set[tuple[str, str, int, str, int]] = set()
    checked = noted = 0
    for married in facts.of(MarriedOn):
        rid = married.cite.record_id
        if rid in seen:
            continue
        seen.add(rid)
        d = married.date
        if d.year is None or d.month is None or d.day is None or d.year > LAST_YEAR:
            continue
        if not is_valid(d.year, d.month, d.day):
            continue
        checked += 1
        day = (d.year, d.month, d.day)
        ban = wedding_ban(*day)
        if ban is None:
            continue
        if married.calendar_note:
            noted += 1
            continue
        findings.append(WeddingFinding(
            cite=married.cite, day=day, ban=ban,
            other_months=_month_either_side(day) if ban.strict else (),
            other_days=_day_either_side(day) if not ban.strict else ()))
    findings.sort(key=lambda f: (not f.ban.strict, f.cite.sort_key))
    return WeddingCalendar(findings=findings, checked=checked, noted=noted)


WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")  # i18n: content — the calendar's weekday abbreviations: vocabulary


def weekday_name(day: JulianDate) -> str:
    return WEEKDAYS[weekday(*day)]
