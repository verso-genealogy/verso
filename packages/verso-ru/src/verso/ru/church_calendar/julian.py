"""Day arithmetic in the Julian calendar the books were kept in.

`datetime.date` is proleptic Gregorian. It has no 29 February 1800 — a day
the books hold — and counts every century February one day short of theirs,
and the checks that went through it (`date(...).toordinal()`) dropped such a
date without a word. A Julian Day Number has neither problem: it counts days,
not calendars, so a difference of two is a number of days and `% 7` is a
weekday whichever calendar named them.

A date here is a `(year, month, day)` triple of Julian numbering, the way the
DSL writes it.
"""
from __future__ import annotations

JulianDate = tuple[int, int, int]

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

#: `weekday()` values, Monday first as `datetime.date.weekday` counts.
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


def is_leap(year: int) -> bool:
    """Every fourth year, the centuries included."""
    return year % 4 == 0


def month_length(year: int, month: int) -> int:
    if month == 2 and is_leap(year):
        return 29
    return _MONTH_DAYS[month - 1]


def is_valid(year: int, month: int, day: int) -> bool:
    """Whether the day exists. The DSL checks a day against 1..31 only, so an
    «31 апреля» can reach a check; it is a misreading, not a date."""
    return 1 <= month <= 12 and 1 <= day <= month_length(year, month)


def jdn(year: int, month: int, day: int) -> int:
    """The Julian Day Number of a Julian-calendar date."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083


def day_number(date: JulianDate | None) -> int | None:
    """The JDN of a date that exists, or None — for the end of an interval
    that may be open or may name a day no month has (the DSL takes 31 April)."""
    if date is None or not is_valid(*date):
        return None
    return jdn(*date)


def from_jdn(n: int) -> JulianDate:
    """The Julian-calendar date of a Julian Day Number."""
    c = n + 32082
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = d - 4800 + m // 10
    return year, month, day


def weekday(year: int, month: int, day: int) -> int:
    """0 for Monday … 6 for Sunday — day 0 of the count was a Monday."""
    return jdn(year, month, day) % 7


def days_between(a: JulianDate, b: JulianDate) -> int:
    """How many days `b` lies after `a` (negative when before)."""
    return jdn(*b) - jdn(*a)


def anniversary(year: int, month: int, day: int) -> int:
    """The JDN of a fixed feast (`month`, `day`) in `year`. A feast of 29
    February is kept on the 28th in a common year, as the Church keeps it."""
    if month == 2 and day == 29 and not is_leap(year):
        day = 28
    return jdn(year, month, day)


def nearest_occurrence(month: int, day: int, around: JulianDate) -> int:
    """Signed days from `around` to the nearest yearly occurrence of the fixed
    feast (`month`, `day`) — negative when it fell before.

    The three candidate years cover a baptism in early January whose saint
    was kept in late December, and the reverse. Ties go to the earlier one,
    so the answer does not depend on iteration order.
    """
    here = jdn(*around)
    year = around[0]
    offsets = [anniversary(y, month, day) - here for y in (year - 1, year, year + 1)]
    return min(offsets, key=lambda d: (abs(d), d))
