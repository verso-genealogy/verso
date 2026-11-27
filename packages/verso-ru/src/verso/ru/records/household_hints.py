"""The household page's three suggestions: whose a row is, a brother's patronymic, an age off the revision gap.

The review page draws a roll's household as a table and, as the reader types, offers what the roll's own
conventions imply (`ui-v1`'s rules `ref_hint`, `patronymic_hint`, `age_gap`; the parameters stand in the schema, which
is their single source). These are the library's answers; the App mirrors them in JS and a golden file holds the two
equal. A hint is a suggestion: nothing here writes into a record, and a figure the roll states is never replaced.

A household is read as the records JSON writes it: `members` is the household node's `persons` — each a persona
whose `link.written` holds the member's own columns and whose `written` the person's (`given`, `patronymic`, `surname`,
each `{"original": …}`). Which column is which the rule says: every field a function reads is a parameter naming its
item path (`role`, `number`, `ref`, `age`, … — `departure.year` walks into the group), as the page reads them, so the
two read the same columns. A role is the code the schema's rule names (`son`, `wife`). `index` is 0-based into
`members`.

`age_gap` reads the pair as CAI002 does (`census_age.link_age_pair`, the one place that says which members it skips),
so the page and the linter cannot disagree.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from verso.ru.linters.checks.census_age import CAI002_TOLERANCE, json_age_years, link_age_pair

__all__ = ["AgeGap", "age_gap", "patronymic_hint", "ref_hint"]

type Member = Mapping[str, Any]



@dataclass(frozen=True)
class AgeGap:
    """A member's ages a revision apart off the expected gap: `expected` the years the book's year implies,
    `found` the years between his two columns."""
    expected: int
    found: int


def _link(member: Member) -> Mapping[str, Any]:
    link = member.get("link", {}).get("written", {})
    return link if isinstance(link, Mapping) else {}


def _at(node: object, path: str) -> object:
    """The value at a dotted `path` of `node`, or None."""
    for key in path.split("."):
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _field(member: Member, path: str) -> object:
    """The member's item field at `path` (`role`, `departure.year`)."""
    return _at(_link(member), path)


def _whole(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def ref_hint(members: Sequence[Member], index: int, *, path: str, children: Collection[str],
             parents: Collection[str], spouse: str, min_gap: int, min_husband_age: int, max_wife_older: int,
             role: str, number: str, age: str) -> int | None:
    """The number of the man whose the row `index` is, where the roll leaves it unwritten (`path`, the field it fills).

    A child (a role of `children`) is the nearest man above (a role of `parents`) who has a wife in the household
    and is at least `min_gap` years older. A wife (`spouse`) is the nearest of them without one who is at least
    `min_husband_age` and not more than `max_wife_older` years younger than she is. Both ages written, or no hint. The
    head is never offered; nothing is offered where `path` is already written or the man has no number. `role`,
    `number` and `age` are the item fields a member's role, number and age are read from."""
    def number_of(man: Member) -> int | None:
        return _whole(_field(man, number))

    def age_of(member: Member) -> int | None:
        return json_age_years(_field(member, age))

    def married(man: Member) -> bool:
        own = number_of(man)
        return own is not None and any(_field(m, role) == spouse and _field(m, path) == own for m in members)

    row = members[index]
    if _field(row, path) is not None:
        return None
    years = age_of(row)
    if years is None:
        return None
    if _field(row, role) in children:
        def fits(man: Member, older: int) -> bool:
            return married(man) and older - years >= min_gap
    elif _field(row, role) == spouse:
        def fits(man: Member, older: int) -> bool:
            return not married(man) and older >= min_husband_age and years - older <= max_wife_older
    else:
        return None
    for man in reversed(members[:index]):
        older = age_of(man)
        if _field(man, role) in parents and older is not None and fits(man, older):
            return number_of(man)
    return None


def _patronymic(member: Member, path: str) -> str | None:
    """The written value of the item's person's field `path` (`person.patronymic.original`): its first step is the
    item's person, the rest the person's own path."""
    _person, _, rest = path.partition(".")
    value = _at(member.get("written", {}), rest)
    return value if isinstance(value, str) and value else None


def patronymic_hint(members: Sequence[Member], index: int, *, path: str, of_role: str, from_role: str, role: str,
                    number: str, ref: str) -> str | None:
    """A member of `of_role` (a brother) written with no patronymic (`path`) takes the written one of the member he is
    written under — the one his `ref` names, the member of `from_role` (the head) where it names none. `role`,
    `number` and `ref` are the item fields a member's role, number and reference are read from."""
    row = members[index]
    if _field(row, role) != of_role or _patronymic(row, path) is not None:
        return None
    under = _whole(_field(row, ref))
    if under is None and _field(row, ref) is not None:
        return None
    whose = next((m for m in members if m is not row and (
        _field(m, role) == from_role if under is None else _whole(_field(m, number)) == under)), None)
    return _patronymic(whose, path) if whose is not None else None


def age_gap(member: Member, book_year: int, *, gaps: Mapping[str, int], age: str, previous: str, departure_year: str,
            departure_reason: str, hidden: str, comment: str) -> AgeGap | None:
    """The member's two ages, where they are off the revision gap by more than a year (CAI002's finding); else None.

    `gaps` is the schema's table: a book's year → the year of the revision its previous-age column counts from. The
    other parameters are the item fields CAI002 reads — the two ages, the departure's two fields, the hidden mark, the
    comment its «прошлая РС» marker stands in."""
    previous_year = gaps.get(str(book_year))
    if previous_year is None:
        return None
    # The pair is read under the factory's names, which `link_age_pair` takes; a field not written is not there.
    read = {"age": age, "previous_age": previous, "departure_year": departure_year,
            "departure_reason": departure_reason, "hidden": hidden, "comment": comment}
    link = {name: value for name, at in read.items() if (value := _field(member, at)) is not None}
    pair = link_age_pair(link, book_year)
    if pair is None:
        return None
    expected = book_year - previous_year
    found = pair.age - pair.previous
    return None if abs(found - expected) <= CAI002_TOLERANCE else AgeGap(expected, found)
