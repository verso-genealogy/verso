"""Marriage record → assertions. The second data point, and the whole point is
this:

    the RULE does not change. Not one line.

`verso.ru.facts.rules.cooccurrence` is handed `WitnessedAt` where it was handed
`GodparentOf`, and that is the entire difference. If the marriage case had
needed a new branch in the rule, a new field on an assertion, or a predicate
that cannot be named in Russian as a relation, the idea would not generalise.

⚠ One genuine data loss surfaced here, and the fact model is what surfaced it.
The books list поручители «по женихѣ» and «по невѣстѣ» separately, but the DSL
flattened them into `witness1..6` and recorded the side nowhere. Since
2026-10-01 the DSL can say it — `witness3=person(…, side=Side.BRIDE)` — and a
witness who says it is attached to that party alone, as the record states. A
witness without `side=` is still attached to BOTH parties, and the basis says
exactly why rather than pretending the record said so.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.ages import age_recorded
from verso.ru.domain import Side

from verso.ru.facts.extract.common import (
    Entry, RecordId, SlotIndex, claim_clergy, fact_date, kinship, reviewed)
from verso.ru.facts.model import (
    AgedYears, Assertion, Derived, MarriedOn, Persona, SpouseOf, Stated, Surety, WitnessedAt)

__all__ = ["RECORD_KIND", "facts_from_marriages"]

RECORD_KIND = "marriage"

_WITNESS_SLOTS = tuple(f"witness{i}" for i in range(1, 7))

# «поручитель №6» → witness slot 6, the marriage counterpart of the births'
# «восприемника №N». Same treatment: parsed here, once.
_WITNESS_REF = re.compile(r"поручител\w*\s*№\s*(\d+)")  # i18n: content — the reference and role words the DSL writes


def facts_from_marriages(items: Iterable[tuple[Any, str]], *, village: str,
                         slots: SlotIndex | None = None, drafts: bool = False,
                         ids: RecordId | None = None) -> Iterator[Assertion]:
    for entry, (rec, source_file) in enumerate(items):
        if not (drafts or reviewed(rec)):
            continue
        yield from _facts_from_marriage(rec, village, source_file, entry, slots, ids)


def _facts_from_marriage(rec: Any, village: str, source_file: str, entry: int,
                         slots: SlotIndex | None = None,
                         ids: RecordId | None = None) -> list[Assertion]:
    e = Entry(rec, village=village, source_file=source_file,
              record_kind=RECORD_KIND, entry=entry, slots=slots, ids=ids)
    wed = fact_date(rec.w_day, rec.w_month, rec.year)

    groom_ref = e.claim(rec.groom, "groom") if rec.groom is not None else None
    # A bride takes the groom's surname by default (`bride_takes_groom_surname`),
    # derived in place — same unknowable basis as the mother's in a birth.
    bride_ref = (e.claim(rec.bride, "bride",
                         residence_basis=Stated(basis_unknown=True))
                 if rec.bride is not None else None)

    # The record IS the marriage: unlike a birth's co-parents, this is not an
    # inference. Both spouse facts are stated outright.
    spouse_facts: list[SpouseOf] = []
    if groom_ref is not None and bride_ref is not None:
        for subject, other, locator in ((groom_ref, bride_ref, "groom"),
                                        (bride_ref, groom_ref, "bride")):
            f = SpouseOf(subject=subject, cite=e.cite(locator), other=other, basis=Stated())
            e.facts.append(f)
            spouse_facts.append(f)
    for ref, locator, age in ((groom_ref, "groom", getattr(rec, "groom_age", None)),
                              (bride_ref, "bride", getattr(rec, "bride_age", None))):
        if ref is None or not wed:
            continue
        e.facts.append(MarriedOn(subject=ref, cite=e.cite(locator),
                                 date=wed, basis=Stated(),
                                 calendar_note=getattr(rec, "calendar_note", None) or None))
        # The age the book gives at the wedding, verbatim and dated to it — one
        # more statement of when this person was born, which until 2026-09-28
        # reached no check (~700 entries across the five villages).
        if age_recorded(age):
            e.facts.append(AgedYears(subject=ref, cite=e.cite(locator), age=age,
                                     as_of=wed, basis=Stated()))

    # The поручители. One whose side the record states (`side=`) vouched for
    # that party, and the book's word for it rides on the citation. One whose
    # side it does not state is attached to BOTH parties — see the module
    # docstring — and the basis carries that reason instead of the record being
    # made to say something it doesn't.
    side_unknown = Derived("marriage.witness-side-not-recorded",
                           Surety.ASSUMED, tuple(spouse_facts))
    for locator in _WITNESS_SLOTS:
        witness = getattr(rec, locator, None)
        if witness is None:
            continue
        ref = e.claim(witness, locator)
        side = getattr(witness, "side", None)
        if side is not None:
            party = groom_ref if side is Side.GROOM else bride_ref
            if party is not None:
                e.facts.append(WitnessedAt(
                    subject=ref, cite=e.cite(locator, stated_role=f"поручитель {side}"),  # i18n: content — the reference and role words the DSL writes
                    other=party, basis=Stated()))
            continue
        for party in (groom_ref, bride_ref):
            if party is not None:
                e.facts.append(WitnessedAt(subject=ref, cite=e.cite(locator),
                                           other=party, basis=side_unknown))

    for i, rel in enumerate(getattr(rec, "relatives", None) or []):
        locator = f"relative{i + 1}"
        ref = e.claim(rel.person, locator)
        anchor = _anchor_ref(e, rel.relationship_ref, groom_ref, bride_ref)
        if anchor is not None:
            e.facts.extend(kinship(ref, anchor, rel.relationship, e.cite(locator)))

    claim_clergy(e, rec, groom_ref)
    return e.facts


def _anchor_ref(e: Entry, ref_text: str | None, groom: Persona | None,
                bride: Persona | None) -> Persona | None:
    if not ref_text:
        return None
    m = _WITNESS_REF.search(ref_text)
    if m:
        return e.refs.get(f"witness{m.group(1)}")
    text = ref_text.strip().lower()
    if text.startswith("жених"):  # i18n: content — the reference and role words the DSL writes
        return groom
    if text.startswith("невест"):  # i18n: content — the reference and role words the DSL writes
        return bride
    return None
