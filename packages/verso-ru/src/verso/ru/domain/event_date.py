"""`EventDate` — a DSL value object mirroring a Geni event date.

A single point in time or a range, with optional circa, expressed as one object
instead of separate year/month/day kwargs. Months are `calendar.Month`.

Pure value object: it holds data only. The terraform translator converts it to a
`GeniDate` (`verso/core/targets/geni/date.py`) — keeping the domain → terraform dependency
one-way.
"""
from __future__ import annotations

import re
from calendar import Month, monthrange
from typing import ClassVar


class EventDate:
    # A value, not an entity: `_written` keeps it, the records JSON writes it whole (verso.core.written).
    _record_value: ClassVar[bool] = True

    def __init__(
        self,
        year: int | None = None,
        month: Month | None = None,
        day: int | None = None,
        *,
        year_end: int | None = None,
        month_end: Month | None = None,
        day_end: int | None = None,
        circa: bool = False,
        circa_end: bool = False,
        date_range: str | None = None,
    ):
        self.year = year
        self.month = month
        self.day = day
        self.year_end = year_end
        self.month_end = month_end
        self.day_end = day_end
        self.circa = circa
        self.circa_end = circa_end
        # When an end bound is given without an explicit range kind, it's a
        # closed "between" range (matches GeniDate's range rendering).
        if date_range is None and (year_end or month_end or day_end):
            date_range = "between"
        self.date_range = date_range

    @property
    def has_range(self) -> bool:
        return bool(self.year_end or self.month_end or self.day_end)


# --------------------------------------------------------------------------- #
# A date as a record's text writes it — and back
# --------------------------------------------------------------------------- #

_GENITIVE = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",  # i18n: content — the months as a date writes them
             "сентября", "октября", "ноября", "декабря")  # i18n: content — the months as a date writes them
_NOMINATIVE = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",  # i18n: content — a month named alone
               "сентябрь", "октябрь", "ноябрь", "декабрь")  # i18n: content — a month named alone
# The old spelling an act of 1918–1919 may still write («іюня», «апрѣля», «генваря»).
_OLD_SPELLING = {"генваря": 1, "генварь": 1, "апрѣля": 4, "апрѣль": 4, "іюня": 6, "іюнь": 6, "іюля": 7, "іюль": 7}  # i18n: content — the months in the old spelling
_MONTH_WORDS: dict[str, int] = {
    **{w: i for i, w in enumerate(_GENITIVE, 1)}, **{w: i for i, w in enumerate(_NOMINATIVE, 1)}, **_OLD_SPELLING}
_YEAR_END = r"\s*(?:г\.?|года)?"  # i18n: content — «1915 г.», «1915 года»
# The figures are the ASCII ones: `\d` would read a digit of any script as a day.
_IN_WORDS = re.compile(rf"(?:([0-9]{{1,2}})\s+)?(?:([а-яёіѣ]+)\s+)?([0-9]{{4}}){_YEAR_END}")  # i18n: content — a date in words
_IN_FIGURES = re.compile(rf"([0-9]{{1,2}})\.([0-9]{{1,2}})\.([0-9]{{4}}){_YEAR_END}")
_CIRCA, _BEFORE, _AFTER = "около", "до", "после"  # i18n: content — how a date that is no point is written


def _julian_month_end(year: int, month: int) -> int:
    """The last day of a month in the Julian calendar the books were kept in: 1900 has its 29 February."""
    return 29 if month == 2 and year % 4 == 0 else monthrange(year, month)[1]


def _point(year: int | None, month: Month | None, day: int | None) -> str:
    if year is None:
        return ""
    if month is None:
        return str(year)
    if day is None:
        return f"{_NOMINATIVE[int(month) - 1]} {year}"
    return f"{day} {_GENITIVE[int(month) - 1]} {year}"


def written_date(date: EventDate) -> str:
    """`date` as a record's text writes a date: «24 февраля 1927», «февраль 1927», «1927»; «около 1915»;
    «до 1915», «после мая 1915»; a range «1914–1915», or «3 мая 1914 – 1 июня 1914» where an end names more than
    a year. A day without its month is not written. What the CSV and the people's database write for an
    `EventDate` of a field that once held text (`divorce(marriage_date=)`), so a file moved to the structure
    writes the same bytes."""
    start = _point(date.year, date.month, date.day)
    if date.circa and start:
        start = f"{_CIRCA} {start}"
    if date.date_range == "before":
        return f"{_BEFORE} {start}"
    if date.date_range == "after":
        after = (f"{_GENITIVE[int(date.month) - 1]} {date.year}" if date.month and not date.day else start)
        return f"{_AFTER} {after}"
    if date.has_range:
        year_end = date.year_end if date.year_end is not None else date.year
        if date.month is None and date.month_end is None:
            return f"{start}–{year_end}"
        return f"{start} – {_point(year_end, date.month_end, date.day_end)}"
    return start


def date_text(value: object) -> str:
    """A field that holds a date as an `EventDate` or — as DSL v1 still allows — as text, written as text: the
    `EventDate` by `written_date`, a text as it is, nothing as "". What a table (a CSV, the people's database)
    writes of `divorce(marriage_date=)`."""
    if isinstance(value, EventDate):
        return written_date(value)
    return str(value) if value else ""


def read_written_date(text: object) -> EventDate | None:
    """A date written as text, as an `EventDate` — or None where the text is not one.

    Read: «24 февраля 1927», «февраль 1927», «1927», «24.02.1927», each with or without «г.», the months also in
    the old spelling. A day needs its month, a month must be one, the day must exist in it (by the Julian
    calendar), the year is not nought. Anything else — «в феврале 1927 г.», «1915?», «24/II-1927», a value that is
    no text — is None: a date is never guessed. What the linter offers in place of a text (`divorce(marriage_date=)`).
    """
    if not isinstance(text, str):
        return None
    written = text.strip().lower()
    figures = _IN_FIGURES.fullmatch(written)
    if figures:
        day, month, year = (int(part) for part in figures.groups())
        return _a_day(year, month, day)
    words = _IN_WORDS.fullmatch(written)
    if not words:
        return None
    day_text, month_word, year_text = words.groups()
    year = int(year_text)
    if year == 0:
        return None
    if month_word is None:
        return None if day_text else EventDate(year)
    month = _MONTH_WORDS.get(month_word)
    if month is None:
        return None
    if day_text is None:
        return EventDate(year, Month(month))
    return _a_day(year, month, int(day_text))


def _a_day(year: int, month: int, day: int) -> EventDate | None:
    if year == 0 or not 1 <= month <= 12 or not 1 <= day <= _julian_month_end(year, month):
        return None
    return EventDate(year, Month(month), day)
