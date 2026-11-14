"""`EventDate` — a DSL value object mirroring a Geni event date.

A single point in time or a range, with optional circa, expressed as one object
instead of separate year/month/day kwargs. Months are `calendar.Month`.

Pure value object: it holds data only. The terraform translator converts it to a
`GeniDate` (`verso/core/targets/geni/date.py`) — keeping the domain → terraform dependency
one-way.
"""
from __future__ import annotations

from typing import ClassVar

from calendar import Month


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
