"""The birth a revision/confession-list line dates (functional core).

A roll line can date a birth four ways, most specific first:

  1. a typed `birth_day`/`birth_month`(/`birth_year`) → an exact date;
  2. a typed `birth_year` alone → a circa year;
  3. the previous revision's year minus `previous_age` → a circa year;
  4. the roll's own date minus the current `age` → a circa date.

Two retractions change that. `source_age_error=` withdraws every age the line
states and any date written beside them, so the line dates nothing.
`previous_age_error=` withdraws the previous figure alone: the birth falls back
to the current age, or to nothing when the current column only repeats the
previous one. The document and the «Возраст» line print the source as written;
only the date is withheld.

`withheld_member_birth` names what a retraction took away, so RIG001 can say
that an `ignore` entry repeats a retraction instead of «no record carries it».
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from verso.ru.census_revisions import prev_revision_year
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.ru.targets.geni.translator.census_resolvers import (
    _age_to_years, _birth_date_from_age, _resolve_previous_age)

_NONE: Mapping[int, int | None] = MappingProxyType({})


def _same_figure(age: Any, previous: float | None) -> bool:
    """The importer's copy: one figure in both columns is one age."""
    if age is None or previous is None:
        return False
    current = float(age) if isinstance(age, (int, float)) else _age_to_years(age)
    return current == previous


def member_birth(m: Any, *, year: int, page_month: int | None, page_day: int | None,
                 location: Any, honour_retractions: bool = True,
                 prev_revision: Mapping[int, int | None] = _NONE) -> GeniEvent | None:
    """The birth event line `m` of a roll taken in `year` dates.

    Carries `location` alone when no date can be derived, and None when there
    is neither. `honour_retractions=False` is the line read as if nobody had
    withdrawn anything — what the translator emitted before 2026-09-25.
    `prev_revision` — the village's exceptions to the revision chain
    (`census_revisions.prev_revision_year`, village.toml `[census] prev_revision`).
    """
    t_day = getattr(m, "birth_day", None)
    t_month = getattr(m, "birth_month", None)
    t_year = getattr(m, "birth_year", None)
    prev_age = _resolve_previous_age(m)
    age = m.age
    if honour_retractions:
        if getattr(m, "source_age_error", None):
            return GeniEvent(location=location) if location else None
        if getattr(m, "previous_age_error", None):
            if _same_figure(age, prev_age):
                age = None
            prev_age = None
    prev_year = prev_revision_year(year, prev_revision)
    try:
        if t_day is not None or t_month is not None:
            return GeniEvent(
                date=GeniDate(day=t_day, month=t_month,
                              year=t_year if t_year is not None else year),
                location=location)
        if t_year is not None:
            return GeniEvent(date=GeniDate(year=t_year, circa=True), location=location)
        if prev_age is not None and prev_year is not None:
            # `prev_age` is a float (handles «5 нед»); the year rounds down.
            return GeniEvent(date=GeniDate(year=int(prev_year - prev_age), circa=True),
                             location=location)
        # The roll's date minus the age, Y/M/W/D-aware: a record month/day
        # gives an infant a circa month (and day); a bare year keeps a year.
        bd = (_birth_date_from_age(year, page_month, page_day, age)
              if age is not None else None)
        if bd is not None:
            b_year, b_month, b_day = bd
            return GeniEvent(date=GeniDate(day=b_day, month=b_month, year=b_year,
                                           circa=True),
                             location=location)
    except (TypeError, ValueError):
        pass
    return GeniEvent(location=location) if location else None


def withheld_member_birth(m: Any, *, year: int, page_month: int | None,
                          page_day: int | None,
                          prev_revision: Mapping[int, int | None] = _NONE) -> tuple[GeniDate, str] | None:
    """The date a retraction on `m` withheld, and the kwarg that withheld it.

    None when the line carries no retraction, or when honouring it changed
    nothing (a `previous_age_error` on a line dated by its typed birth year).
    """
    if getattr(m, "source_age_error", None):
        why = "source_age_error"
    elif getattr(m, "previous_age_error", None):
        why = "previous_age_error"
    else:
        return None
    before = member_birth(m, year=year, page_month=page_month, page_day=page_day,
                          location=None, honour_retractions=False, prev_revision=prev_revision)
    after = member_birth(m, year=year, page_month=page_month, page_day=page_day,
                         location=None, prev_revision=prev_revision)
    if before is None or before.date is None:
        return None
    if after is not None and after.date == before.date:
        return None
    return before.date, why
