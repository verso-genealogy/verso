"""Death record → assertions.

Three things this extractor states that the pipeline around it does not, and
each one is a bug the fact model makes unrepresentable rather than merely
known:

**A burial is not a birth.** `b_day`/`b_month` are the BURIAL in a death record
and the BIRTH in a birth record — the same two
attribute names, two meanings, one copy-paste apart. 3198 of the corpus's 3466
burials carry a date that differs from the death date, and every one of them
reached no consumer but the CSV exporters. `BuriedOn` and `BornOn` are two
predicates; the confusion has no way to be typed.

**An age is evidence, not a birth year.** `AgedYears` keeps the scribe's own
string. What the age implies about a birth is arithmetic, and arithmetic
belongs in a `Derived` assertion with this one among its premises.

**A relative the record cannot place is not a parent.** The translator reads
every kinship except «муж» as «this relative is the deceased's parent», which
inverts a зять and overstates a свекор and a мачеха. Here each kinship maps to
the predicate it actually supports, and an unstated one maps to nothing: a
missing edge is recoverable from another record, a false one has to be noticed
first, and it looks exactly like a true one.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.relationship import Relationship

from verso.ru.facts.extract.common import (
    Entry, RecordId, SlotIndex, claim_clergy, fact_date, kinship, reviewed, stated_unless)
from verso.ru.facts.model import (
    AgedYears, Assertion, BuriedOn, Derived, DiedOn, NameClaim, Persona, Stated, Surety)

__all__ = ["RECORD_KIND", "facts_from_deaths"]

RECORD_KIND = "death"

_WITNESS_SLOTS = ("witness1", "witness2")


def facts_from_deaths(items: Iterable[tuple[Any, str]], *, village: str,
                      slots: SlotIndex | None = None, drafts: bool = False,
                      ids: RecordId | None = None) -> Iterator[Assertion]:
    for entry, (record, source_file) in enumerate(items):
        if not (drafts or reviewed(record)):
            continue
        yield from _facts_from_death(record, village, source_file, entry, slots, ids)


def _facts_from_death(rec: Any, village: str, source_file: str, entry: int,
                      slots: SlotIndex | None = None,
                      ids: RecordId | None = None) -> list[Assertion]:
    e = Entry(rec, village=village, source_file=source_file,
              record_kind=RECORD_KIND, entry=entry, slots=slots, ids=ids)
    died = fact_date(rec.d_day, rec.d_month, rec.year)
    # A book of the civil registry (`civil=True`) registers the death: its
    # second date buries no one, so it asserts no burial.
    buried = None if getattr(rec, "civil", False) else fact_date(rec.b_day, rec.b_month, rec.year)

    deceased: Persona | None = None
    if rec.deceased is not None:
        # `Death.__init__` propagates one household residence across the
        # deceased and every relative, in place — so which of them the source
        # actually named is no longer knowable. Witnesses and clergy are
        # excluded from that propagation, so theirs stands as stated.
        deceased = e.claim(rec.deceased, "deceased",
                           residence_basis=Stated(basis_unknown=True))
        _patronymic_basis(e, rec, deceased)
        if died:
            e.facts.append(DiedOn(subject=deceased, cite=e.cite("deceased"),
                                  date=died, basis=Stated()))
        if buried:
            # An author who has re-read the scan and found the SOURCE's own two
            # dates inconsistent withdraws the BURIAL: «погребёнъ 8, умеръ 9 —
            # так в подлиннике». The transcription is faithful and there is
            # nothing to fix, so the date cannot order anything — but the source
            # still says it, which is why this wraps the basis instead of
            # dropping the assertion. The burial is withdrawn rather than the
            # death for the same reason births withdraws the christening: the
            # death date is what the rest of the record hangs on.
            reason = getattr(rec, "source_date_error", None)
            e.facts.append(BuriedOn(
                subject=deceased, cite=e.cite("deceased"), date=buried,
                basis=stated_unless(reason)))
        if rec.age is not None:
            # An author who has re-read the scan and still cannot reconcile the
            # age withdraws it — and everything derived from it inherits that.
            basis = stated_unless(getattr(rec, "source_age_error", None))
            # A namesake is NOT that: the age is right and stays believed; the
            # note only says whose christening it may not be measured from.
            e.facts.append(AgedYears(subject=deceased, cite=e.cite("deceased"),
                                     age=rec.age, as_of=died, basis=basis,
                                     namesake=getattr(rec, "namesake", None)))

    # EVERY relative, not just the first. The translator emits `relatives[0]`
    # alone (DRL001 exists to guard that limit); a record that names two states
    # two, and dropping one here would reproduce the limit rather than the source.
    #
    # свекор, зять, мачеха and the rest land on `KinOf` (see `KINSHIP_EDGE`),
    # and so do the twelve entries that leave `relationship=` unset: emitting
    # nothing there lost two real findings in Заманиловка, and the check that
    # reproduces `death-age-check` is what surfaced the mistake.
    for i, rel in enumerate(getattr(rec, "relatives", None) or []):
        locator = f"relative{i + 1}"
        ref = e.claim(rel.person, locator,
                      residence_basis=Stated(basis_unknown=True))
        if deceased is not None:
            e.facts.extend(kinship(ref, deceased, rel.relationship, e.cite(locator)))

    for locator in _WITNESS_SLOTS:
        witness = getattr(rec, locator, None)
        if witness is not None:
            e.claim(witness, locator)

    claim_clergy(e, rec, deceased)
    return e.facts


def _patronymic_basis(e: Entry, rec: Any, deceased: Persona) -> None:
    """Restate a patronymic `Death.__init__` derived from a father relative.

    The breadcrumb is indirect and negative — `patr_orig` stays empty while
    `patr_modern` fills in — and the translator reads the same absence to
    decide the deceased was a child. Stating it outright costs one assertion
    and saves the next reader from having to know that convention.
    """
    person = rec.deceased
    if getattr(person, "patr_orig", None) or not getattr(person, "patr_modern", None):
        return
    if not any(r.relationship == Relationship.FATHER
               for r in (getattr(rec, "relatives", None) or [])):
        return
    e.facts.append(NameClaim(
        subject=deceased, cite=e.cite("deceased"),
        basis=Derived("dsl.patronymic-from-father", Surety.ASSUMED, ()),
        given=None, patronymic=person.patr_modern, surname=None, gender=None))
