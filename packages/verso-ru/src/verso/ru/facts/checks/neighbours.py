"""A name list's neighbours, and the kin they vouch for.

A 1917 voter list runs a household in one stretch — husband, wife, the sons
and their wives — under one surname written once and then ditto'd. The list
states no kinship (`extract/name_lists.py` asserts none), so it cannot say who
is married to whom. But the corpus proper can: when the canonical a list entry
may be is the spouse, parent or child of the canonical its NEIGHBOUR may be,
the list's order and the metric books agree, and that is evidence neither has
alone. It is what a human does with an ambiguous entry: reads the household.

A NEIGHBOUR of an entry is another entry of the same list whose number is at
most `NEIGHBOUR_SPAN` away and whose surname is of the same family (the caller
says which surnames are — `reconcile` passes its own `_one_family`). The number,
not the position in the file: a list may be a selection (№ 27, then № 38), and
two lines a file puts together are not neighbours in the book.

KIN is read off the assertions — `SpouseOf` and `ParentOf`, placed on their
canonicals by the identity bridge — never off the Geni tree: a record the
corpus holds says who married whom and whose child someone is.

Where the list gives ages, the relation must fit them (`fits_ages`): spouses
at most `SPOUSE_MAX_GAP` years apart, a parent at least `PARENT_MIN_GAP` older.
One household often holds two women of one name — two entries for the same
name, a grandmother of 64 and her grandson's wife of 24 — and without the ages
the grandmother was read as the wife of the grandson beside her.

This module neither decides nor ranks: `reconcile` asks it who stands beside a
target and whom they are kin to, and weighs the answer.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from verso.ru.ages import DAYS_PER_YEAR, age_bounds
from verso.ru.facts.identity import Identity, IdentityKey, display_name
from verso.ru.facts.model import AgedYears, AssertionSet, Citation, NameClaim, ParentOf, SpouseOf
from verso.ru.naming.surnames import normalise_surname

#: How far apart two entries of one list may be numbered and still be read as
#: one household. Measured on the corpus of 2026-09-29 — see `verso/ru/facts/checks/
#: reconcile.py` for the numbers the span was chosen by.
NEIGHBOUR_SPAN = 4

#: What the neighbour's canonical is to the candidate.
SPOUSE = "spouse"
PARENT = "parent"
CHILD = "child"
#: What a canonical is to its kin, read from the other side.
INVERSE = {SPOUSE: SPOUSE, PARENT: CHILD, CHILD: PARENT}

#: The ages two entries of one household may state and still be spouses, and
#: the least a parent is older than a child. Wide on purpose — a widower's
#: second wife, a clerk's rounded age: the check is there to stop a grandmother
#: read as a young man's wife, not to judge a marriage.
SPOUSE_MAX_GAP = 20
PARENT_MIN_GAP = 14

#: kin[a][b] — what b is to a, for every pair of canonicals a record relates.
Kin = dict[IdentityKey, dict[IdentityKey, str]]

#: Whether two sets of surname roots name one family.
SameFamily = Callable[[frozenset[str], frozenset[str]], bool]


def kin_of_canonicals(facts: AssertionSet, identity: Identity) -> Kin:
    """Spouses, parents and children between canonicals, as the records state
    them. The first relation a pair is given wins, in record order."""
    kin: Kin = {}

    def add(a: IdentityKey | None, b: IdentityKey | None, what: str) -> None:
        if a is not None and b is not None and a != b:
            kin.setdefault(a, {}).setdefault(b, what)

    for record in facts.records():
        key_of = identity(record)
        for edge in record.of(SpouseOf):
            a, b = key_of(edge.subject), key_of(edge.other)
            add(a, b, SPOUSE)
            add(b, a, SPOUSE)
        for edge in record.of(ParentOf):
            parent, child = key_of(edge.subject), key_of(edge.other)
            add(parent, child, CHILD)
            add(child, parent, PARENT)
    return kin


@dataclass(frozen=True)
class ListEntry:
    """One entry of a name list, as far as neighbourhood needs it."""
    source_file: str
    number: int
    name: str
    roots: frozenset[str]
    record_id: tuple[object, ...]
    key: IdentityKey | None
    #: The age the list states, in years as an interval — None where unwritten.
    age: tuple[float, float] | None = None


def list_entries(facts: AssertionSet, identity: Identity,
                 wanted: Callable[[Citation], bool]) -> list[ListEntry]:
    """Every entry of the lists `wanted` names, with the person it is placed
    on. An entry whose number is not a number (none today) has no neighbours."""
    out: list[ListEntry] = []
    for record in facts.records():
        if not record.assertions or not wanted(record.assertions[0].cite):
            continue
        key_of = identity(record)
        ages = {a.subject: a.age for a in record.of(AgedYears)}
        for claim in record.of(NameClaim):
            cite = claim.cite
            if not cite.record_num.isdigit():
                continue
            roots = frozenset(normalise_surname(s) for s in (claim.surname,)
                              if s and s.strip() and "?" not in s)
            days = age_bounds(ages.get(claim.subject))
            age = (days[0] / DAYS_PER_YEAR, days[1] / DAYS_PER_YEAR) if days else None
            out.append(ListEntry(cite.source_file, int(cite.record_num),
                                 display_name(claim), roots, cite.record_id,
                                 key_of(claim.subject), age))
    return out


def fits_ages(own: tuple[float, float] | None, other: tuple[float, float] | None,
              relation: str) -> bool:
    """Whether two list ages allow `other` to be `own`'s `relation` — read
    charitably, each age the interval it states. An age not written allows
    anything."""
    if own is None or other is None:
        return True
    if relation == SPOUSE:
        return other[0] - own[1] <= SPOUSE_MAX_GAP and own[0] - other[1] <= SPOUSE_MAX_GAP
    if relation == PARENT:
        return other[1] - own[0] >= PARENT_MIN_GAP
    if relation == CHILD:
        return own[1] - other[0] >= PARENT_MIN_GAP
    return True


class Neighbourhood:
    """The entries of each list, and who stands beside a given one."""

    def __init__(self, entries: Iterable[ListEntry], same_family: SameFamily,
                 span: int = NEIGHBOUR_SPAN) -> None:
        self._by_file: dict[str, list[ListEntry]] = {}
        self._by_id: dict[tuple[object, ...], ListEntry] = {}
        for e in entries:
            self._by_file.setdefault(e.source_file, []).append(e)
            self._by_id[e.record_id] = e
        self._same_family = same_family
        self._span = span

    def entry(self, record_id: tuple[object, ...]) -> ListEntry | None:
        """The entry of a list in the neighbourhood, or None."""
        return self._by_id.get(record_id)

    def beside(self, own: ListEntry,
               person: IdentityKey | None = None) -> tuple[ListEntry, ...]:
        """The neighbours of an entry, `person` themself left out."""
        if not own.roots:
            return ()
        return tuple(sorted(
            (other for other in self._by_file[own.source_file]
             if other.record_id != own.record_id
             and (person is None or other.key != person)
             and abs(other.number - own.number) <= self._span
             and other.roots and self._same_family(own.roots, other.roots)),
            key=lambda e: e.number))
