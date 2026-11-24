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
keeps it as the text of the act (`marriage_date="14 марта 1926"`), and it is
read only in the forms a date is written in (`named_wedding`): a text it does
not know asserts NOTHING, never a guessed day. An author who has re-read the
scan and found the act's own two dates out of order withdraws this one
(`source_date_error=`) — the divorce's day is what the record hangs on, as a
death's is when its burial is withdrawn.

**The ages are of unknown basis.** An act of the registry's later form writes a
date or a year of birth, and the figure in `husband_age=` may be the
transcriber's subtraction; the DSL leaves no breadcrumb, so the assertion says
what the layer says wherever a value was derived in place. So is where each of
them lived: the record set's defaults fill it.

Not stated: that either of them was alive on the day. A marriage dissolved on
one spouse's word says nothing of where the other was.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.ages import age_recorded

from verso.ru.facts.extract.common import Entry, RecordId, SlotIndex, fact_date, reviewed, stated_unless
from verso.ru.facts.model import (
    AgedYears, Assertion, DivorcedOn, FactDate, MarriedOn, Persona, SpouseOf, Stated)

__all__ = ["RECORD_KIND", "facts_from_divorces", "named_wedding"]

RECORD_KIND = "divorce"

# The months as an act writes them: «14 марта 1926», «март 1926» — and as one of 1918–1919 may still
# spell them («іюня», «апрѣля», «генваря»).
_MONTHS: dict[str, int] = {word: number for number, words in enumerate((
    ("января", "январь"), ("февраля", "февраль"), ("марта", "март"), ("апреля", "апрель"),  # i18n: content — the months a record's text writes
    ("мая", "май"), ("июня", "июнь"), ("июля", "июль"), ("августа", "август"),  # i18n: content — the months a record's text writes
    ("сентября", "сентябрь"), ("октября", "октябрь"), ("ноября", "ноябрь"), ("декабря", "декабрь"),  # i18n: content — the months a record's text writes
), start=1) for word in words} | {  # i18n: content — the months in the old spelling
    "генваря": 1, "генварь": 1, "апрѣля": 4, "апрѣль": 4, "іюня": 6, "іюнь": 6, "іюля": 7, "іюль": 7}
_YEAR_END = r"\s*(?:г\.?|года)?"  # i18n: content — «1915 г.», «1915 года»
# The figures are the ASCII ones: `\d` would read a digit of any script as a day.
_IN_WORDS = re.compile(rf"(?:([0-9]{{1,2}})\s+)?(?:([а-яёіѣ]+)\s+)?([0-9]{{4}}){_YEAR_END}")  # i18n: content — a date in words
_IN_FIGURES = re.compile(rf"([0-9]{{1,2}})\.([0-9]{{1,2}})\.([0-9]{{4}}){_YEAR_END}")


def named_wedding(text: object) -> FactDate | None:
    """The day of the marriage as the act names it, or None.

    Read: «14 марта 1926», «март 1926», «1926», «14.03.1926», each with or
    without «г.». A day needs its month, a month must be one, and the day must
    exist in it. Anything else — «в феврале 1927 г.», «1915?», «24/II-1927» —
    is None: a wedding the layer cannot date is not asserted. So is a value
    that is no text at all — a figure typed where the act's words belong must
    not stop the reading of the village.
    """
    if not isinstance(text, str):
        return None
    written = text.strip().lower()
    if not written:
        return None
    figures = _IN_FIGURES.fullmatch(written)
    if figures:
        day, month, year = (int(part) for part in figures.groups())
        return _a_day(year, month, day)
    words = _IN_WORDS.fullmatch(written)
    if not words:
        return None
    day_text, month_word, year_text = words.groups()
    if int(year_text) == 0:
        return None
    if month_word is None:
        return None if day_text else FactDate(year=int(year_text))
    month = _MONTHS.get(month_word)
    if month is None:
        return None
    if day_text is None:
        return FactDate(year=int(year_text), month=month)
    return _a_day(int(year_text), month, int(day_text))


def _a_day(year: int, month: int, day: int) -> FactDate | None:
    """A date to the day, or None when the month has no such day."""
    if year == 0 or not 1 <= month <= 12:
        return None
    last = FactDate(year=year, month=month).latest
    if last is None or not 1 <= day <= last[2]:
        return None
    return FactDate(year=year, month=month, day=day)


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
    wed = named_wedding(getattr(rec, "marriage_date", None))

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
        if wed is not None:
            e.facts.append(MarriedOn(
                subject=ref, cite=e.cite(locator), date=wed,
                basis=stated_unless(getattr(rec, "source_date_error", None)),
                calendar_note=getattr(rec, "calendar_note", None) or None))
        if divorced and age_recorded(age):
            e.facts.append(AgedYears(subject=ref, cite=e.cite(locator), age=age, as_of=divorced,
                                     basis=Stated(basis_unknown=True)))
    return e.facts
