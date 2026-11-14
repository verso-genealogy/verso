"""The mechanism every extractor shares. Knows no record kind.

Splitting this out makes the per-kind cost measurable: whatever a new record
type costs is what its own `extract/*.py` weighs, not this.
"""
from __future__ import annotations

from calendar import Month
from collections.abc import Callable, Iterator
from typing import Any

from verso.ru.domain import Person
from verso.ru.dsl.records.reviewed import admitted
from verso.ru.gender import Gender
from verso.core.records.fields import role_of
from verso.core.records.ids import persona_id
from verso.ru.relationship import Relationship

from verso.ru.facts.model import (
    Assertion, Bound, Citation, Derived, FactDate, FosterParentOf, KinOf, NameClaim, OfficiatedAt, ParentOf, Persona, ResidedIn, Retracted, SpouseOf, Stated, Surety, Titled)

#: What a named relative's kinship says about the edge to the appearance it
#: hangs off — ONE table for every record kind. Until 2026-09-28 each extractor
#: kept its own, and they had drifted apart: births and marriages read a foster
#: parent and a step-parent as a PARENT, deaths did not. A stepfather is not a
#: father, and saying so is the one thing a missing edge cannot recover from.
#:
#: `"parent"`: the relative is that appearance's parent; `"child"`: the
#: reverse; `"foster"`: a foster parent. Every kinship not here — a
#: step-parent, an in-law, and an entry that names kin without saying which —
#: relates the two without saying how (`KinOf`, the source's word kept).
KINSHIP_EDGE: dict[Relationship, str] = {
    Relationship.FATHER: "parent",
    Relationship.MOTHER: "parent",
    Relationship.SON: "child",
    Relationship.DAUGHTER: "child",
    Relationship.FOSTER_FATHER: "foster",
    Relationship.FOSTER_MOTHER: "foster",
    Relationship.HUSBAND: "spouse",
    Relationship.WIFE: "spouse",
}

#: The причт, in slot order. Every record kind names them the same way and
#: none of them gets a profile.
CLERGY_SLOTS = ("priest", "deacon", "dyachok", "sexton")

#: A record's id (`verso.core.records.ids.RecordIds`, rule r1), asked by the record.
RecordId = Callable[[Any], str]

def fact_date(day: int | None, month: Month | None, year: int | None) -> FactDate:
    """A DSL date triple as the interval it asserts.

    A ZERO day or month means «not recorded», not «day nought»: that is the
    corpus's own spelling, visible in every res_name it produces
    (`_1840_00_00_…`), and the DSL writes it where a scribe left the column
    empty. One record does today — a death with `b_day=0` — and
    passing it through made the burial's latest possible day the 0th, which is
    before every real day of the month, so the burial «definitely preceded» a
    death 29 days later. A date that cannot be later than itself is not an
    interval, and the boundary is the place to say so.
    """
    return FactDate(year=year,
                    month=int(month) if month else None,
                    day=int(day) if day else None)


def reviewed(record: Any) -> bool:
    """Whether the author has checked this entry against the scan.

    An entry transcribed and not yet checked (`reviewed=False`) asserts
    nothing: the translator mints no profile for it (generator.py) and the
    census extractor skips such a двор. Reading it here would put claims into
    the layer the author has not yet stood behind — and, for the bridge, would
    count as a refusal every appearance nobody minted. A record the ratchet
    lists as already on Geni is read like any other: its profiles exist, and
    the bridge places it (`verso.ru.dsl.records.reviewed.admitted`).

    Every `facts_from_*` takes `drafts=True` to read such an entry anyway, and
    one caller passes it: Verso's people index (`verso.ru.persons.lives`), which
    offers the people a sweep is still reading and asserts nothing for the tree.
    """
    return admitted(record)


def event_fact_date(d: Any) -> FactDate:
    """A DSL `EventDate` (point or range, circa either end) as the interval it
    asserts. An absent date is the empty `FactDate`, which is falsy."""
    if d is None:
        return FactDate()
    raw = getattr(d, "date_range", None)
    month, month_end = getattr(d, "month", None), getattr(d, "month_end", None)
    return FactDate(
        year=d.year, month=int(month) if month else None,
        day=int(d.day) if getattr(d, "day", None) else None,
        circa=bool(getattr(d, "circa", False)),
        bound=Bound(raw) if raw in tuple(b.value for b in Bound) else None,
        end_year=getattr(d, "year_end", None),
        end_month=int(month_end) if month_end else None,
        end_day=int(d.day_end) if getattr(d, "day_end", None) else None,
        end_circa=bool(getattr(d, "circa_end", False)))


def stated_unless(reason: str | None) -> Stated | Retracted:
    """`Stated`, or withdrawn by the author's own «так в подлиннике» note.

    The withdrawal wraps the basis rather than dropping the assertion: the
    source still says it, and `why()` prints it under the reason."""
    return Retracted(reason, Stated()) if reason else Stated()


def kinship(ref: Persona, anchor: Persona, relationship: Relationship | None,
            cite: Citation) -> list[Assertion]:
    """The assertions one named relative supports, by `KINSHIP_EDGE`."""
    edge = KINSHIP_EDGE.get(relationship) if relationship is not None else None
    if edge == "parent":
        return [ParentOf(subject=ref, cite=cite, other=anchor, basis=Stated())]
    if edge == "child":
        return [ParentOf(subject=anchor, cite=cite, other=ref, basis=Stated())]
    if edge == "foster":
        return [FosterParentOf(subject=ref, cite=cite, other=anchor, basis=Stated())]
    if edge == "spouse":
        return [SpouseOf(subject=ref, cite=cite, other=anchor, basis=Stated()),
                SpouseOf(subject=anchor, cite=cite, other=ref, basis=Stated())]
    # An EMPTY term is an entry that fills the relative slot and leaves
    # `relationship=` unset. That is not «no kinship» — the entry names a
    # relative, which asserts kinship and declines to name it. The word is
    # kept for a reader; no rule may read it.
    return [KinOf(subject=ref, cite=cite, other=anchor,
                  term=str(relationship) if relationship else "", basis=Stated())]


def claim_clergy(e: Entry, record: Any, served: Persona | None) -> None:
    """The причт who served, and whom. Emitted because the vocabulary can carry
    them — the translator mints them no profile."""
    if served is None:
        return
    for locator in CLERGY_SLOTS:
        cleric = getattr(record, locator, None)
        if cleric is None:
            continue
        ref = e.claim(cleric, locator)
        e.facts.append(OfficiatedAt(subject=ref, cite=e.cite(locator),
                                    other=served, basis=Stated()))


def gender_of(p: Person) -> Gender | None:
    g = getattr(p, "gender", None)
    return g if isinstance(g, Gender) else None


def surname_basis(p: Person, anchor: Assertion | None) -> Stated | Derived:
    """`last_name_in_book=False` is the corpus's one surviving breadcrumb: the
    surname is known but was NOT in the book's ФИО, i.e. we concluded it."""
    if getattr(p, "last_name_modern", None) and not getattr(p, "last_name_in_book", True):
        return Derived("dsl.surname-inherited", Surety.ASSUMED,
                       (anchor,) if anchor else ())
    return Stated()


class SlotIndex:
    """Which DSL object each `Persona` was read from.

    The join key of the bridge between an appearance and the profile the
    translator minted for it. Both sides already hold the same `Person` object,
    so the join needs no vocabulary: not a record number, not a slot name, not a
    reconstructed res_name. `Person` is a plain class, so two same-named people
    in one entry are two keys, which is exactly the distinction an identity has
    to make.

    Provenance for a JOIN and never for a rule — it is filled by an extractor,
    read by `verso.ru.facts.projection`, and a rule cannot reach it at all: it does
    not travel on an assertion.
    """

    def __init__(self) -> None:
        self._person: dict[Persona, object] = {}

    def record(self, persona: Persona, obj: object) -> None:
        self._person.setdefault(persona, obj)

    def object_of(self, persona: Persona) -> object | None:
        return self._person.get(persona)

    def items(self) -> Iterator[tuple[Persona, object]]:
        """Every persona with the object it was read from — the join read the
        other way round, from a `Person` to what its record says of it."""
        return iter(self._person.items())

    def __len__(self) -> int:
        return len(self._person)


class Entry:
    """One document entry, mid-extraction. Holds the refs its slots resolve to.

    «Entry» is the provenance unit, which is not the same as a record of the
    book: a metric book's entry is one christening, a revision tale's is one
    household. `record_num`, `year` and `page` may therefore be passed in —
    a household states its own number and takes its year from the roll, where
    a christening carries both itself.

    `ids` gives the entry its id, the record's in the records JSON (rule r1):
    what every persona of it is named by. Without it — a test, a one-off
    reading — the entry is numbered by its place in the reading
    (`<file>#<entry>:<year>:<number>`), unique there and nowhere else. A record
    `ids` does not know is an error, not a fallback: a village's personas are
    named one way or the other, never both.
    """

    def __init__(self, record: Any, *, village: str, source_file: str,
                 record_kind: str, entry: int, record_num: object = None,
                 year: int | None = None, page: str | None = None,
                 slots: SlotIndex | None = None, ids: RecordId | None = None) -> None:
        self.record = record
        self.slots = slots
        self.village = village
        self.source_file = source_file
        self.record_kind = record_kind
        self.entry = entry
        if record_num is None:
            record_num = getattr(record, "record_num", None)
        self.record_num = "none" if record_num is None else str(record_num)
        self.year: int | None = year if year is not None else getattr(record, "year", None)
        self.page = page if page is not None else getattr(record, "page", None)
        self.source_id = (ids(record) if ids is not None
                          else f"{source_file}#{entry}:{self.year}:{self.record_num}")
        self.refs: dict[str, Persona] = {}
        self.facts: list[Assertion] = []

    def cite(self, locator: str, *, stated_role: str | None = None) -> Citation:
        return Citation(village=self.village, source_file=self.source_file,
                        record_kind=self.record_kind, record_num=self.record_num,
                        entry=self.entry, year=self.year,
                        page=self.page, locator=locator, stated_role=stated_role)

    def claim(self, p: Person, locator: str, *,
              slot: tuple[str, int | None] | None = None,
              residence_basis: Stated | None = None,
              name_basis: Stated | Derived | None = None,
              stated_role: str | None = None,
              status_basis: Stated | Derived | None = None,
              own_status: bool = True,
              calendar_note: str | None = None) -> Persona:
        """NameClaim (+ residence, + status) for one named appearance.

        The persona is named as the records JSON names it (`persona_id`): by
        the slot's attribute (`god_parent2` → `godparent2`, `relative1`), or
        by `slot` where the locator is not one — a roll's member (`member`,
        its number), a list's or a card's person (`person`).

        `own_status=False` for an appearance whose status the record does not
        state at all; `status_basis` for one whose appearance the record does
        not state (a reconstructed member). Otherwise the status is `Stated`,
        and `basis_unknown` when the book's defaults filled it in place.
        `calendar_note` rides on the claim that carries the given name.
        """
        ref = Persona(persona_id(self.source_id, *(slot or role_of(locator))))
        self.refs[locator] = ref
        if self.slots is not None:
            self.slots.record(ref, p)
        cite = self.cite(locator, stated_role=stated_role)
        name = NameClaim(subject=ref, cite=cite, basis=name_basis or Stated(),
                         given=getattr(p, "name_modern", None),
                         patronymic=getattr(p, "patr_modern", None),
                         surname=getattr(p, "last_name_modern", None),
                         birth_surname=getattr(p, "birth_last_name_modern", None),
                         gender=gender_of(p), calendar_note=calendar_note or None)
        self.facts.append(name)
        basis = surname_basis(p, name)
        if isinstance(basis, Derived):
            # Restate the name with its real basis — the first claim recorded
            # WHAT the record shows, this one records on whose authority.
            self.facts.append(NameClaim(subject=ref, cite=cite, basis=basis,
                                        given=None, patronymic=None,
                                        surname=getattr(p, "last_name_modern", None),
                                        gender=None))
        place = getattr(p, "residence", None)
        if place:
            self.facts.append(ResidedIn(subject=ref, cite=cite, place=place,
                                        basis=residence_basis or Stated()))
        status = getattr(p, "status", None)
        if own_status and status:
            self.facts.append(Titled(
                subject=ref, cite=cite, status=str(status),
                basis=status_basis or Stated(
                    basis_unknown=bool(getattr(p, "status_defaulted", False)))))
        return ref
