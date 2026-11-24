"""What the site draws, read off records v1: the books, their entries and every mention of a person.

A book is what its records are cited from — the id of a record less its token — not a DSL file: two
record sets of one shelfmark, year and kind are one book, and a record that states a shelfmark of
its own stands in that one's book. A mention is a persona of a record: the site folds nobody into
a person.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from verso.core.records import ids
from verso.ru.gender import Gender
from verso.ru.messages import t
from verso.ru.naming.patronymics import derive_patronymic
from verso.ru.site import urls
from verso.ru.site.errors import SiteError

Node = Mapping[str, Any]

# The kinds of a record's id, in the order a year lists its books.
KINDS = ("birth", "marriage", "death", "divorce", "household", "listed")
UNREVIEWED = ("held", "on_geni")
REVIEWS = ("reviewed", *UNREVIEWED)        # what the export says of a record (verso.core.records.encode.review)
_NAME = ("given", "patronymic", "surname")


_OLD_LETTERS = str.maketrans("ёѣіѳѵ", "ееифи")  # i18n: content — the letters the 1918 reform dropped
_HARD_SIGN = re.compile(r"ъ\b")  # i18n: content — the hard sign that ends a word


def fold(text: str) -> str:
    """A name as a search compares it: lower case, the pre-reform letters as their modern ones, no
    hard sign at a word's end — «Ѳеодоръ» and «Феодор» are one."""
    return _HARD_SIGN.sub("", unicodedata.normalize("NFC", text).lower().translate(_OLD_LETTERS))


class DuplicatePath(SiteError):
    """Two books whose ids make one path."""


class NotAnExport(SiteError):
    """A record node that does not say whether it was read against its scan (`review`): the export writes it
    of the built record, and no key of `written` says it instead — a leaf released inside a held set, a set's
    own flag, the list of what reached a tree unread are all in it."""


@dataclass(frozen=True)
class Entry:
    id: str
    anchor: str
    leaf: str | None
    node: Node
    review: str
    book_id: str
    doc: Node            # the record set it was written in
    file: str            # the DSL file of that set, in the village

    @property
    def unreviewed(self) -> bool:
        return self.review in UNREVIEWED


@dataclass(frozen=True)
class Book:
    id: str
    path: str
    village: str         # the book's parish, which is not always the corpus's directory
    shelfmark: str
    part: str | None
    year: int | None
    kind: str
    docs: tuple[Node, ...]
    entries: tuple[Entry, ...]

    @property
    def is_cards(self) -> bool:
        return self.shelfmark == urls.CARD

    @property
    def written(self) -> Node:
        return self.docs[0]["written"]

    @property
    def shelf(self) -> dict[str, str]:
        """The shelfmark the book is cited by, part by part: its records' own where they state one — the book is
        the one its records are cited from, not the record set they were written in — else the set's."""
        own = self.entries[0].node.get("written", {}) if self.entries else {}
        return {key: str(own.get(key) or self.written.get(key) or "")
                for key in ("archive", "fund", "inventory", "case")}

    @property
    def church(self) -> str:
        own = self.entries[0].node.get("written", {}) if self.entries else {}
        return str(own.get("church") or self.written.get("church") or "")

    @property
    def set_kind(self) -> str:
        """The kind of its record set (`births`, `census`, …): the key of its title in `ui-v1`."""
        return self.docs[0]["kind"]

    @property
    def civil(self) -> bool:
        return bool(self.written.get("civil"))

    @property
    def unreviewed(self) -> int:
        return sum(1 for entry in self.entries if entry.unreviewed)

    @property
    def files(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(entry.file for entry in self.entries))


@dataclass(frozen=True)
class Mention:
    entry: Entry
    persona: Node
    role: str
    as_written: str
    modern: str
    given: str
    patronymic: str      # in the book's form («Петров»), the key of who is written with no surname
    surname: str


@dataclass(frozen=True)
class Site:
    village: str
    books: tuple[Book, ...]
    mentions: tuple[Mention, ...]

    def book(self, book_id: str) -> Book:
        return next(book for book in self.books if book.id == book_id)

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(sorted({book.year for book in self.books if book.year is not None}))

    @property
    def records(self) -> int:
        return sum(len(book.entries) for book in self.books)

    @property
    def unreviewed(self) -> int:
        return sum(book.unreviewed for book in self.books)


def form(persona: Node, part: str, form_: str) -> tuple[str, str] | None:
    """A form of a part of a persona's name and where it stands: `("Петръ", "w")` where the record
    writes it, `("Петров", "d")` where the library derived it."""
    for side, mark in (("written", "w"), ("derived", "d")):
        value = (persona.get(side, {}).get(part) or {}).get(form_)
        if value:
            return str(value), mark
    return None


def hidden(persona: Node) -> bool:
    """A member written for the kinship alone, who does not stand in the document."""
    return bool(((persona.get("link") or {}).get("written") or {}).get("hidden"))


def name_parts(persona: Node) -> list[tuple[str, str]]:
    """The name as the source writes it, part by part with its mark; the modern forms where it
    writes none."""
    parts = [found for part in _NAME if (found := form(persona, part, "original"))]
    return parts or modern_parts(persona)


def modern_parts(persona: Node) -> list[tuple[str, str]]:
    parts = [form(persona, "given", "modern"), form(persona, "patronymic", "modern"),
             form(persona, "surname", "modern") or form(persona, "maiden_surname", "modern")]
    return [(text, "d") for text, _ in filter(None, parts)]


def _text(parts: Iterable[tuple[str, str]]) -> str:
    return " ".join(text for text, _ in parts)


def _mention(entry: Entry, persona: Node) -> Mention:
    def first(*asks: tuple[str, str]) -> str:
        # «?» — a name the reader could not make out — is no name to index a person by.
        return next((found[0] for part, form_ in asks if (found := form(persona, part, form_))
                     and any(char.isalnum() for char in found[0])), "")
    if not persona.get("role"):
        raise NotAnExport(str(t("site.not_an_export", record=entry.id, file=entry.file)))
    return Mention(entry, persona, persona["role"], _text(name_parts(persona)), _text(modern_parts(persona)),
                   given=first(("given", "modern"), ("given", "original")),
                   patronymic=first(("patronymic", "old"), ("patronymic", "original")),
                   surname=first(("surname", "modern"), ("maiden_surname", "modern"), ("surname", "original")))


def _order(book: Book) -> tuple[Any, ...]:
    kind = KINDS.index(book.kind) if book.kind in KINDS else len(KINDS)
    return (book.is_cards, book.year or 0, kind, book.kind, book.village, book.shelfmark, book.part or "")


_BIRTHS = frozenset({"birth", "christening"})
_GENDERS = {"male": Gender.MALE, "female": Gender.FEMALE}


def infant_patronymic(node: Node) -> Node:
    """A record of a birth with its child's patronymic said — the father's, as the library derives it
    (`derive_patronymic`, what the Geni translator and the CSV give the child) — where the record writes none
    and the export derived none: marked derived, as the surname the child takes from the father. `node` itself
    where there is nothing to say (no father, a father's name not read, no sex), else a copy: the export is
    read, never rewritten."""
    if node.get("kind") not in _BIRTHS:
        return node
    persons = node.get("persons", [])
    child = next((p for p in persons if p.get("role") == "child"), None)
    father = next((p for p in persons if p.get("role") == "father"), None)
    gender = _GENDERS.get(str((node.get("written") or {}).get("gender")))
    if child is None or father is None or gender is None:
        return node
    if any(any(((child.get(side) or {}).get("patronymic") or {}).values()) for side in ("written", "derived")):
        return node                                  # a form with a value; `person("Иван", None)` writes none
    given = form(father, "given", "modern")
    patronymic = derive_patronymic(given[0], gender) if given else ""
    if not patronymic or "?" in patronymic:
        return node
    derived = {**(child.get("derived") or {}), "patronymic": {"modern": patronymic}}
    return {**node, "persons": [{**p, "derived": derived} if p is child else p for p in persons]}


def load(files: Iterable[Node], *, village: str) -> Site:
    """The site of `files` — records-v1 file nodes of one village, in any order."""
    docs: dict[str, list[Node]] = {}
    entries: dict[str, list[Entry]] = {}
    for file in sorted(files, key=lambda f: str(f["file"])):
        for doc in file["documents"]:
            if "alias_of" in doc:
                continue
            for run in doc.get("pages", []):
                for node in map(infant_patronymic, run["records"]):
                    book_id = urls.book_of(node["id"])
                    leaf = node.get("written", {}).get("page") or run.get("page")
                    if node.get("review") not in REVIEWS:
                        raise NotAnExport(str(t("site.not_an_export", record=node["id"], file=file["file"])))
                    entries.setdefault(book_id, []).append(Entry(
                        node["id"], urls.anchor(node["id"]), None if leaf is None else str(leaf), node,
                        node["review"], book_id, doc, str(file["file"])))
                    if not any(doc is known for known in docs.setdefault(book_id, [])):
                        docs[book_id].append(doc)
    books: list[Book] = []
    paths: dict[str, str] = {}
    for book_id, found in entries.items():
        parsed = ids.parse(book_id)
        path = urls.book_path(book_id)
        if path in paths:
            raise DuplicatePath(str(t("site.duplicate_path", path=path, first=paths[path], second=book_id)))
        paths[path] = book_id
        books.append(Book(book_id, path, parsed.village, parsed.shelfmark, parsed.part, parsed.year, parsed.kind,
                          tuple(docs[book_id]), tuple(found)))
    books.sort(key=_order)
    mentions = tuple(_mention(entry, persona) for book in books for entry in book.entries
                     for persona in entry.node.get("persons", []) if not hidden(persona))
    return Site(village, tuple(books), mentions)
