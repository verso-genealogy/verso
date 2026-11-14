"""Name list («именной список») → assertions.

A flat roster from one dated document — the 1917 voter lists today. It names
a person and, sometimes, an age; it states no kinship and no event, so the
extractor asserts little, and that is the point: a list entry is one more
appearance of somebody the metric books already hold, and what it can
contribute to finding them is a name, a place, an age on a known day, and the
fact that they were alive on that day.

What it deliberately does NOT assert:

- **A birth.** The age is a statement made on the list's date; the birth year
  the translator derives from it (`list year − age`) is arithmetic, and the
  checks do that arithmetic themselves from `AgedYears`.
- **A household.** Горюхино's list runs husband, wife, children — but the
  DSL records the grouping only as Python comments, and a roster's order is
  not a statement of kinship. Two entries of one list are two people; that is
  read off the citation (one list per file), not asserted. Where a list
  declares it runs by households (`household_order=True`), `verso reconcile`
  weighs an entry's neighbours against the kin the metric books state
  (`checks/neighbours.py`) — evidence for a match, still no kinship asserted.
- **Where the entry lives, as stated.** `NameListRecords` fills an empty
  residence with the list's village in place, leaving no breadcrumb, so every
  `ResidedIn` here is `Stated(basis_unknown=True)`.
"""
from __future__ import annotations

from calendar import Month
from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.ages import age_recorded

from verso.ru.facts.extract.common import Entry, RecordId, SlotIndex, fact_date, reviewed
from verso.ru.facts.model import (
    AgedYears, Assertion, Derived, Stated, SurvivedUntil, Surety)

__all__ = ["RECORD_KIND", "facts_from_name_lists"]

RECORD_KIND = "list"


def facts_from_name_lists(items: Iterable[tuple[Any, str]], *, village: str,
                          slots: SlotIndex | None = None, drafts: bool = False,
                          ids: RecordId | None = None) -> Iterator[Assertion]:
    """`items` are whole `NameListRecords`: an entry takes its date from the
    list around it. The entry index runs over every entry of every list, the
    unreviewed included, so holding a лист back renumbers nobody."""
    entry = 0
    for records, source_file in items:
        month = records.record_month
        on = fact_date(records.record_day, Month(month) if month else None,
                       records.year)
        for listed in records.entries:
            if drafts or reviewed(listed):
                yield from _facts_from_entry(listed, on, records.year, village,
                                             source_file, entry, slots, ids)
            entry += 1


def _facts_from_entry(listed: Any, on: Any, year: int, village: str,
                      source_file: str, entry: int,
                      slots: SlotIndex | None, ids: RecordId | None) -> list[Assertion]:
    e = Entry(listed, village=village, source_file=source_file,
              record_kind=RECORD_KIND, entry=entry, record_num=listed.number,
              year=year, page=listed.page, slots=slots, ids=ids)
    ref = e.claim(listed.person, "listed", slot=("person", None),
                  residence_basis=Stated(basis_unknown=True))
    cite = e.cite("listed")
    named = e.facts[0]
    if age_recorded(listed.age) and on:
        e.facts.append(AgedYears(subject=ref, cite=cite, age=listed.age, as_of=on,
                                 basis=Stated()))
    if on:
        # On the roll on its date — alive then. Not a death bound and not a
        # birth: the same inference a revision's listing makes.
        e.facts.append(SurvivedUntil(
            subject=ref, cite=cite, date=on,
            basis=Derived("list.listed-alive", Surety.INFERRED, (named,))))
    return e.facts
