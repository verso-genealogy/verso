"""Ids of records v1, rule r1: a record named as it is cited, not where it lies.

    r1:<village>/<fund>-<inventory>-<case>[;<part>][/<year>]/<kind>/<number>[~k][/<role><slot>]
    r1:<village>/card/<criminal|wwi|wwii>/<catalog address key>[~k][/person]

The village is the record set's — the book's parish, not the corpus directory; the
shelfmark the record's own where it states one (`page(case=…)`), else the book's; the
part a roll's `archive_suffix` less the shelfmark, which tells the rolls of one case and
year apart; the year the book's, left out where its set states none. The number is
cited with the sex where the book numbers the sexes apart (`m12`, `f23`). A key the
village has met already takes `~2`, `~3` in export order — a scribe repeats numbers —
and a record without a number always counts (`_1`, `m_2`). A segment escapes `%`, `/`,
`~` and `;`.

So an id moves when the reading of a number, a sex, a shelfmark or a book's year is
corrected, and never on a corrected name. What is counted rather than cited moves with
the order it is counted in — years, files by name, records in file order: a repeat's
`~k` when another repeat of its key comes to stand before it (inserted, moved in its
file, its file renamed), and a numberless record's `_k` when another numberless record
of its book does. A record inserted or moved anywhere else, or a file renamed, moves no
other id. `r1` is the version of this RULE, not of the schema; a new rule is `r2`.

A document — a record set — is named by its book, `~k` from the second set of one book on. A village's sets of
cards state no year: each takes its file's directory (`card/1941/cards`), and is counted among its year's alone.

The records export (`verso.core.pipeline.records`) and the facts layer (`verso.ru.pipeline.facts`)
count with one walk (`walk`, `RecordIds`), so a persona of `facts.jsonl` is the persona
of the records JSON, byte for byte.

What a record is cited by is the plugin's: its `Citation` — the book (`book_key`), the
number (`entry_token`), the principal people and how a person is written — is
`plugins.dsl().cite`, the Russian books' `verso.ru.records.cite.R1`. The core spells, counts
and parses; `parse` reads a year where the third segment is all digits (a card's is its kind).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from typing import Any, NamedTuple, Protocol

from verso.core import plugins
from verso.core.messages import t

ID_SCHEME = "r1"

_ESCAPES = (("%", "%25"), ("/", "%2F"), ("~", "%7E"), (";", "%3B"))


def escape(segment: str) -> str:
    for raw, escaped in _ESCAPES:
        segment = segment.replace(raw, escaped)
    return segment


def unescape(segment: str) -> str:
    for raw, escaped in reversed(_ESCAPES):
        segment = segment.replace(escaped, raw)
    return segment


@dataclass(frozen=True)
class BookKey:
    village: str
    shelfmark: str
    part: str | None
    year: int | None
    kind: str

    def __str__(self) -> str:
        book = escape(self.shelfmark) + (f";{escape(self.part)}" if self.part else "")
        year = [] if self.year is None else [str(self.year)]
        return f"{ID_SCHEME}:" + "/".join([escape(self.village), book, *year, escape(self.kind)])


class Token(NamedTuple):
    prefix: str        # the sex where the book numbers the sexes apart, else ""
    number: str        # "" for a record without a number


class Citation(Protocol):
    """What a plugin's records are cited by, for rule r1."""

    def book_key(self, record_set: Any, record: Any | None) -> BookKey:
        """The book a record (or, with None, a record set) is cited from."""
        ...

    def entry_token(self, record: Any) -> Token:
        """How the source numbers a record."""
        ...

    def principals(self, record: Any) -> list[Any]:
        """The record's principal people (a child, a couple), any of them None."""
        ...

    def person_label(self, person: Any) -> str:
        """A person as the record writes them."""
        ...


def _cite() -> Citation:
    return plugins.dsl().cite


def book_key(record_set: Any, record: Any = None) -> BookKey:
    """The book a record (or a record set) is cited from: the plugin's citation."""
    return _cite().book_key(record_set, record)


def entry_token(record: Any) -> Token:
    """How the source numbers a record: the plugin's citation."""
    return _cite().entry_token(record)


class Ids:
    """The ids of one village: counts each key in the order asked, so a repeat takes `~k`."""

    def __init__(self) -> None:
        self._seen: Counter[tuple[str, str, str]] = Counter()
        self._books: Counter[str] = Counter()

    def record_id(self, book: BookKey, token: tuple[str, str]) -> str:
        prefix, number = token
        n = self._seen[(str(book), prefix, number)] = self._seen[(str(book), prefix, number)] + 1
        if not number:
            return f"{book}/{escape(prefix)}_{n}"
        return f"{book}/{escape(prefix + number)}" + ("" if n == 1 else f"~{n}")

    def of(self, record_set: Any, record: Any) -> str:
        """A record's id, counted as the next of its key."""
        return self.record_id(book_key(record_set, record), entry_token(record))

    def document_id(self, book: BookKey, file: str | None = None) -> str:
        """A record set's id: its book's, `~k` from the second set of the book on. A book that states no year
        (a village's cards) takes the year of its file's directory (`file`, as the records JSON writes it:
        `1941/…py`), so a set is counted among the sets of its year alone, and an export of some of the years
        numbers a set as the export of the whole village does."""
        directory, _, name = (file or "").partition("/")
        if book.year is None and name and directory.isdigit():
            book = replace(book, year=int(directory))
        n = self._books[str(book)] = self._books[str(book)] + 1
        return str(book) + ("" if n == 1 else f"~{n}")


def records_of(record_set: Any) -> list[Any]:
    """A record set's records, in its book's order: the list its kind names (`RecordKind.records`)."""
    kind = plugins.kind_of(record_set)
    assert kind is not None, type(record_set).__name__
    return list(getattr(record_set, kind.records))


def walk(namespace: Mapping[str, object]) -> Iterator[tuple[Any, Any]]:
    """(record set, record) for every record one DSL file binds, in the records export's
    order: the record sets as the module binds them, an alias once, each one's records in
    its book's order. Whatever else the namespace holds is passed over."""
    seen: set[int] = set()
    for value in namespace.values():
        if plugins.kind_of(value) is None or id(value) in seen:
            continue
        seen.add(id(value))
        for record in records_of(value):
            yield value, record


class RecordIds:
    """The id of every record walked, asked by the record itself.

    One per village, given its files in the export's order (`verso.core.pipeline.load.
    village_modules`: years, then files by name) — so a repeated number takes the `~k` the
    records JSON gives it. Held records count as the export counts them: an id does not
    move when a draft is read. Fewer files walked (one file, as Verso reads) count their
    repeats among themselves alone."""

    def __init__(self) -> None:
        self._ids = Ids()
        self._of: dict[int, tuple[object, str]] = {}

    def walk(self, namespace: Mapping[str, object]) -> None:
        """Count one DSL file's records (`walk`), after those walked before."""
        for record_set, record in walk(namespace):
            self._of[id(record)] = (record, self._ids.of(record_set, record))

    def __call__(self, record: object) -> str:
        held = self._of.get(id(record))
        if held is None or held[0] is not record:
            raise KeyError(str(t("records.ids.not_counted", cls=type(record).__name__)))
        return held[1]

    def __len__(self) -> int:
        return len(self._of)


def persona_id(record_id: str, role: str, slot: int | None) -> str:
    return f"{record_id}/{role}{'' if slot is None else slot}"


@dataclass(frozen=True)
class ParsedId:
    scheme: str
    village: str
    shelfmark: str
    part: str | None
    year: int | None
    kind: str
    token: str | None
    repeat: int | None
    persona: str | None


def parse(id_: str) -> ParsedId:
    """An id back into its parts; refuses another rule."""
    scheme, _, rest = id_.partition(":")
    if scheme != ID_SCHEME:
        raise ValueError(str(t("records.ids.unknown_scheme", scheme=scheme, known=ID_SCHEME)))
    segments = rest.split("/")
    village, book = segments[0], segments[1]
    shelfmark, _, part = book.partition(";")
    if re.fullmatch(r"[0-9]+", segments[2]):
        year, tail = int(segments[2]), segments[3:]
    else:                                 # a book whose set states no year (a card's is its kind)
        year, tail = None, segments[2:]
    kind, token_seg, persona = (tail + [None, None])[:3]
    token = repeat = None
    if token_seg is not None:
        raw, _, k = token_seg.partition("~")
        token, repeat = unescape(raw), (int(k) if k else None)
    return ParsedId(scheme, unescape(village), unescape(shelfmark), unescape(part) or None, year,
                    unescape(kind or ""), token, repeat, persona)


def person_label(person: Any) -> str:
    """A person as the record writes them: the plugin's citation."""
    return _cite().person_label(person)


def record_label(record: Any) -> str:
    """The record's principal people (the plugin's: a child, a couple, the deceased, a
    household's head), each as the record writes them."""
    cite = _cite()
    return " + ".join(label for p in cite.principals(record) if p is not None
                      for label in [cite.person_label(p)] if label)
