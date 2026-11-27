"""The household page's three suggestions: whose a row is, a brother's patronymic, an age off the revision gap.

The review page draws a roll's household as a table and, as the reader types, offers what the roll's own
conventions imply (`ui-v1`'s rules `ref_hint`, `patronymic_hint`, `age_gap`; the parameters stand in the schema, which
is their single source). These are the library's answers; the App mirrors them in JS and a golden file holds the two
equal. A hint is a suggestion: nothing here writes into a record, and a figure the roll states is never replaced.

A household is read as the records JSON writes it: `members` is the household node's `persons` — each a persona
whose `link.written` holds the member's own columns (`number`, `role`, `ref_member`, `age`, `previous_age`,
`departure`, `hidden`, `comment`) and whose `written` the person's (`given`, `patronymic`, `surname`, each
`{"original": …}`). A role is the code the schema's rule names (`son`, `wife`). `index` is 0-based into `members`.

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


def _role(member: Member) -> object:
    return _link(member).get("role")


def _number(member: Member) -> int | None:
    number = _link(member).get("number")
    return number if isinstance(number, int) and not isinstance(number, bool) else None


def _age(member: Member) -> int | None:
    return json_age_years(_link(member).get("age"))


def _has_wife(members: Sequence[Member], man: Member, spouse: str) -> bool:
    number = _number(man)
    return number is not None and any(
        _role(m) == spouse and _link(m).get("ref_member") == number for m in members)


def ref_hint(members: Sequence[Member], index: int, *, children: Collection[str], parents: Collection[str],
             spouse: str, min_gap: int) -> int | None:
    """The number of the man whose the row `index` is, where the roll leaves it unwritten.

    A child (a role of `children`) is the nearest man above (a role of `parents`) who has a wife in the household
    and is at least `min_gap` years older — both ages written, or no hint. A wife (`spouse`) is the nearest man
    above without one. The head is never offered; nothing is offered where `ref_member` is already written or
    the man has no number."""
    row = members[index]
    link = _link(row)
    if link.get("ref_member") is not None:
        return None
    role = link.get("role")
    if role in children:
        age = _age(row)
        if age is None:
            return None

        def fits(man: Member) -> bool:
            older = _age(man)
            return _has_wife(members, man, spouse) and older is not None and older - age >= min_gap
    elif role == spouse:
        def fits(man: Member) -> bool:
            return not _has_wife(members, man, spouse)
    else:
        return None
    for man in reversed(members[:index]):
        if _role(man) in parents and fits(man):
            return _number(man)
    return None


def _patronymic(member: Member) -> str | None:
    written = member.get("written", {}).get("patronymic")
    value = written.get("original") if isinstance(written, Mapping) else None
    return value if isinstance(value, str) and value else None


def patronymic_hint(members: Sequence[Member], index: int, *, role: str, from_role: str) -> str | None:
    """A member of `role` (a brother of the head) written with no patronymic takes the written one of the member of
    `from_role` (the head)."""
    if _role(members[index]) != role or _patronymic(members[index]) is not None:
        return None
    head = next((m for m in members if _role(m) == from_role), None)
    return _patronymic(head) if head is not None else None


def age_gap(member: Member, book_year: int, *, gaps: Mapping[str, int]) -> AgeGap | None:
    """The member's two ages, where they are off the revision gap by more than a year (CAI002's finding); else None.

    `gaps` is the schema's table: a book's year → the year of the revision its previous-age column counts from."""
    previous_year = gaps.get(str(book_year))
    if previous_year is None:
        return None
    link = dict(_link(member))
    departure = link.pop("departure", None)
    if isinstance(departure, Mapping):                 # the JSON groups it; the checks read its two keys flat
        link.update({f"departure_{k}": v for k, v in departure.items() if k in ("year", "reason")})
    pair = link_age_pair(link, book_year)
    if pair is None:
        return None
    expected = book_year - previous_year
    found = pair.age - pair.previous
    return None if abs(found - expected) <= CAI002_TOLERANCE else AgeGap(expected, found)
