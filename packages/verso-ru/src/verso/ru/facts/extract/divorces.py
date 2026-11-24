"""Divorce record → assertions.

An act of divorce is the one record of the books that ENDS something, and it
says three things the layer keeps apart:

**These two were spouses, and on this day they ceased to be.** `SpouseOf` both
ways — the relation has no term, and an act that dissolves a marriage states
that there was one — and `DivorcedOn` for each of them, dated as the record
dates it: the court's decree where the act names one, the day of the act
otherwise.

**The marriage the act names is a later document's claim about a wedding.**
The source says so, and nothing is concluded here, so it is `MarriedOn` and
`Stated` — what makes it a later claim is its citation, this record. The DSL
holds it as an `EventDate` (`marriage_date=EventDate(1926, Month.MARCH, 14)`),
the interval it asserts read as an external card's dates are. A text — what
DSL v1 wrote before, deprecated — asserts NOTHING: no date is ever guessed
from one. An author who has re-read the scan and found the act's own two
dates out of order withdraws this one (`source_date_error=`) — the divorce's
day is what the record hangs on, as a death's is when its burial is withdrawn.

**The ages are of unknown basis.** An act of the registry's later form writes a
date or a year of birth, and the figure in `husband_age=` may be the
transcriber's subtraction; the DSL leaves no breadcrumb, so the assertion says
what the layer says wherever a value was derived in place. So is where each of
them lived: the record set's defaults fill it.

Not stated: that either of them was alive on the day. A marriage dissolved on
one spouse's word says nothing of where the other was.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.ages import age_recorded

from verso.ru.domain.event_date import EventDate
from verso.ru.facts.extract.common import (
    Entry, RecordId, SlotIndex, event_fact_date, fact_date, reviewed, stated_unless)
from verso.ru.facts.model import (
    AgedYears, Assertion, DivorcedOn, MarriedOn, Persona, SpouseOf, Stated)

__all__ = ["RECORD_KIND", "facts_from_divorces"]

RECORD_KIND = "divorce"

def _figure(value: object) -> int | None:
    """A day or a month as the DSL holds it, or None — not recorded — where it holds none or holds words
    («3?», «июль»): a divorce whose day cannot be read is still read, and the village's reading with it."""
    try:
        return int(value) if value else None  # pyright: ignore[reportArgumentType]
    except (TypeError, ValueError):
        return None


def facts_from_divorces(items: Iterable[tuple[Any, str]], *, village: str,
                        slots: SlotIndex | None = None, drafts: bool = False,
                        ids: RecordId | None = None) -> Iterator[Assertion]:
    for entry, (rec, source_file) in enumerate(items):
        if not (drafts or reviewed(rec)):
            continue
        yield from _facts_from_divorce(rec, village, source_file, entry, slots, ids)


def _facts_from_divorce(rec: Any, village: str, source_file: str, entry: int,
                        slots: SlotIndex | None = None,
                        ids: RecordId | None = None) -> list[Assertion]:
    e = Entry(rec, village=village, source_file=source_file,
              record_kind=RECORD_KIND, entry=entry, slots=slots, ids=ids)
    # A day means nothing without its month, as in `named_wedding`.
    month = _figure(rec.d_month)
    divorced = fact_date(_figure(rec.d_day) if month else None, month, rec.year)
    # The wedding the act names, as an `EventDate`; a text (DSL v1's, deprecated) asserts nothing — never parsed.
    named = getattr(rec, "marriage_date", None)
    wed = event_fact_date(named) if isinstance(named, EventDate) else None

    # The record set's defaults fill a residence in place (`divorce_records`),
    # so which of the two the act itself wrote is no longer knowable.
    spouses: list[tuple[str, Persona, Any]] = [
        (locator, e.claim(who, locator, residence_basis=Stated(basis_unknown=True)), age)
        for locator, who, age in (("husband", rec.husband, rec.husband_age),
                                  ("wife", rec.wife, rec.wife_age))
        if who is not None]
    if len(spouses) == 2:
        (his, husband, _), (hers, wife, _) = spouses
        e.facts.append(SpouseOf(subject=husband, cite=e.cite(his), other=wife, basis=Stated()))
        e.facts.append(SpouseOf(subject=wife, cite=e.cite(hers), other=husband, basis=Stated()))
    for locator, ref, age in spouses:
        if divorced:
            e.facts.append(DivorcedOn(subject=ref, cite=e.cite(locator), date=divorced, basis=Stated()))
        if wed:
            e.facts.append(MarriedOn(
                subject=ref, cite=e.cite(locator), date=wed,
                basis=stated_unless(getattr(rec, "source_date_error", None)),
                calendar_note=getattr(rec, "calendar_note", None) or None))
        if divorced and age_recorded(age):
            e.facts.append(AgedYears(subject=ref, cite=e.cite(locator), age=age, as_of=divorced,
                                     basis=Stated(basis_unknown=True)))
    return e.facts
