"""External catalog card (судимость, ПМВ, ВОВ) → assertions.

One person attested by one entry of a published catalog: the criminal-record
gazette, a WWI hero card, a WWII award or casualty card. Like a list entry it
states no kinship; unlike one it often states the birth (a WWII card's «дата
рождения», an explicit year) and always an event on a day — the card's own date,
the draft, the feat.

- **The birth**, when the card gives it: `BornOn` from `birth_date` or
  `birth_year`, as written. The translator emits such a year circa as a
  matching aid; the card itself says the year, so the assertion does not widen
  it. An age on the card is `AgedYears` on the card's date — the arithmetic to
  a birth is the checks'.
- **The event.** A card whose «причина выбытия» says убит, умер or погиб dates a
  DEATH to the card's date — the translator's rule, verbatim. Every other dated
  event (the card's date, the draft, the feat) is a day the person was alive:
  `SurvivedUntil`, derived. «Пропал без вести» is not a death.
- **The place**, only where the card names one: `ExternalSourceRecord` does not
  default a residence, so what is there was written.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.ages import age_recorded

from verso.ru.facts.extract.common import (
    Entry, RecordId, SlotIndex, event_fact_date, reviewed)
from verso.ru.facts.model import (
    AgedYears, Assertion, BornOn, Derived, DiedOn, FactDate, Stated, SurvivedUntil, Surety)

__all__ = ["RECORD_KIND", "facts_from_external_sources"]

RECORD_KIND = "external"

#: The words in a card's «причина выбытия» that make it a death — the same
#: three the translator reads (`add_external_source_records`).
_FATAL = ("убит", "умер", "погиб")  # i18n: content — the cards' words for a death


def facts_from_external_sources(items: Iterable[tuple[Any, str]], *, village: str,
                                slots: SlotIndex | None = None, drafts: bool = False,
                                ids: RecordId | None = None) -> Iterator[Assertion]:
    """`items` are whole `ExternalSourceRecords` (one DSL file each). The entry
    index runs over every card of every file, unreviewed ones included."""
    entry = 0
    for records, source_file in items:
        for card in records.records:
            if drafts or reviewed(card):
                yield from _facts_from_card(card, village, source_file, entry, slots, ids)
            entry += 1


def _facts_from_card(card: Any, village: str, source_file: str, entry: int,
                     slots: SlotIndex | None, ids: RecordId | None) -> list[Assertion]:
    e = Entry(card, village=village, source_file=source_file,
              record_kind=RECORD_KIND, entry=entry, record_num=card.res_key,
              year=card.event_year, page=card.page, slots=slots, ids=ids)
    ref = e.claim(card.person, "external", slot=("person", None))
    cite = e.cite("external")
    named = e.facts[0]

    born = (event_fact_date(card.birth_date) if card.birth_date is not None
            else FactDate(year=card.birth_year) if card.birth_year else FactDate())
    if born:
        e.facts.append(BornOn(subject=ref, cite=cite, date=born, basis=Stated()))

    on = event_fact_date(card.date)
    if age_recorded(card.age) and on:
        e.facts.append(AgedYears(subject=ref, cite=cite, age=card.age, as_of=on,
                                 basis=Stated()))

    fatal = any(w in (card.casualty_reason or "").lower() for w in _FATAL)
    if fatal and on:
        e.facts.append(DiedOn(subject=ref, cite=cite, date=on, basis=Stated()))
    alive = [d for d in (None if fatal else on,
                         event_fact_date(getattr(card, "draft_date", None)),
                         event_fact_date(getattr(card, "feat_date", None))) if d]
    for day in alive:
        e.facts.append(SurvivedUntil(
            subject=ref, cite=cite, date=day,
            basis=Derived("card.alive-at-event", Surety.INFERRED, (named,))))
    return e.facts
