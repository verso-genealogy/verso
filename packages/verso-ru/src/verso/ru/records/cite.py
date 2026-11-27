"""Rule r1 as the Russian books' records are cited: the book, the number, the principal
people and how a person is written — moved verbatim out of `verso.core.records.ids`, which
spells, counts and parses the ids and asks this for the rest (`plugins.dsl().cite`).

A record is cited by its book — the record set's village, the record's own shelfmark where it
states one (`page(case=…)`), else the book's, a roll's part, the book's year, the kind — and
by its number, with the sex where the book numbers the sexes apart (births, deaths). A card of
an external catalog is cited by its catalog address.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from verso.core.records import FormatError
from verso.core.records.fields import code
from verso.core.records.ids import BookKey, Token
from verso.ru.dsl.kinds import KINDS
from verso.ru.dsl.records.births import Birth
from verso.ru.dsl.records.census import CensusHousehold, CensusRole
from verso.ru.dsl.records.deaths import Death
from verso.ru.dsl.records.divorces import Divorce
from verso.ru.dsl.records.external_sources import ExternalSourceRecord, ExternalSourceRecords
from verso.ru.dsl.records.marriages import Marriage
from verso.ru.dsl.records.name_lists import ListedPerson
from verso.ru.messages import t

CARD = "card"

# A record's kind in its id is its RecordKind's code (verso.ru.dsl.kinds); a card is cited by
# its catalog address instead (`book_key`).
_KIND_OF_RECORD: dict[type, str] = {cls: kind.code for kind in KINDS if kind.code != CARD for cls in kind.record_types}
_KIND_OF_SET: dict[type, str] = {kind.set_type: kind.code for kind in KINDS if kind.code != CARD}
_SEX = {"MALE": "m", "FEMALE": "f"}


def _kind(record_set: object, record: object | None) -> str:
    if record is not None:
        for cls, kind in _KIND_OF_RECORD.items():
            if isinstance(record, cls):           # a Christening is a Birth: one numbering
                return kind
    return _KIND_OF_SET[type(record_set)]


def book_key(record_set: Any, record: Any = None) -> BookKey:
    """The book a record (or a record set) is cited from."""
    if isinstance(record_set, ExternalSourceRecords):
        if record is None:
            return BookKey(record_set.village, CARD, None, None, "cards")
        return BookKey(record_set.village, CARD, None, None, code(record.kind))
    fund, inventory, case = (getattr(record, attr, None) or getattr(record_set, attr)
                             for attr in ("fund", "inventory", "case"))
    shelfmark = f"{fund}-{inventory}-{case}"
    suffix = getattr(record_set, "archive_suffix", None)
    part = None
    if suffix and suffix != shelfmark:
        part = suffix.removeprefix(f"{shelfmark}-")
    return BookKey(record_set.village, shelfmark, part, record_set.year, _kind(record_set, record))


def url_key(url: str) -> str:
    """A catalog address as a key: its last path segment, then the query's names and values."""
    parts = urlsplit(url)
    segment = next((s for s in reversed(parts.path.split("/")) if s), "")
    pairs = [pair.partition("=") for pair in parts.query.split("&") if pair]
    words = [segment, *(w for name, _, value in pairs for w in (name, value))]
    return re.sub(r"[^\w.-]", "-", "-".join(w for w in words if w))


def entry_token(record: Any) -> Token:
    """How the source numbers a record: sex and number, a household's or a list's number,
    a card's catalog address."""
    if isinstance(record, ExternalSourceRecord):
        url = record.citation.source_url
        return Token("", url_key(url) if url else "")
    if isinstance(record, CensusHousehold):
        return Token("", "" if record.family_id in (None, "") else str(record.family_id))
    if isinstance(record, ListedPerson):
        return Token("", str(record.number))
    number = getattr(record, "record_num", None)
    prefix = ""
    if isinstance(record, (Birth, Death)):
        prefix = _SEX.get(getattr(record.gender, "name", ""), "")
        if not prefix:
            sheet = str(t("records.cite.leaf", page=record.page)) if record.page else ""
            raise FormatError(t("records.cite.no_sex", kind=type(record).__name__, number=number, sheet=sheet))
    return Token(prefix, "" if number is None else str(number))


def person_label(person: Any) -> str:
    """A person as the record writes them; the modern forms where it wrote none."""
    written = [person.name_orig, person.patr_orig, person.last_name]
    if not any(written):
        written = [person.name_modern, person.patr_modern, person.last_name_modern]
    return " ".join(part for part in written if part)


def _principals(record: Any) -> list[Any]:
    if isinstance(record, Birth):
        return [record.written_child()]          # the newborn as the book writes him (В10)
    if isinstance(record, Marriage):
        return [record.groom, record.bride]
    if isinstance(record, Death):
        return [record.deceased]
    if isinstance(record, Divorce):
        return [record.husband, record.wife]
    if isinstance(record, CensusHousehold):
        heads = [m for m in record.members if m.role is CensusRole.HEAD] or record.members[:1]
        return [m.person for m in heads[:1]]
    return [getattr(record, "person", None)]


class R1Citation:
    """Rule r1 of the Russian books, as the core asks it (`verso.core.records.ids.Citation`)."""

    def book_key(self, record_set: Any, record: Any | None) -> BookKey:
        return book_key(record_set, record)

    def entry_token(self, record: Any) -> Token:
        return entry_token(record)

    def principals(self, record: Any) -> list[Any]:
        return _principals(record)

    def person_label(self, person: Any) -> str:
        return person_label(person)


R1 = R1Citation()
