"""Core genealogy domain model: Person, Status, CauseOfDeath, RecordDefaults and
the record-construction factories (person/page/book) — split from the former
genealogy god-module. Re-exported here so callers keep
``from verso.ru.domain import Person, person, RecordDefaults, Gender, ...``; the DSL takes
its names from the facade, ``verso.ru.dsl``.

Gender is re-exported from :mod:`verso.ru.gender` for backward compatibility with the
old ``from genealogy import Gender`` surface.
"""

from verso.ru.domain.cause_of_death import NOT_IN_DOCUMENT, CauseOfDeath
from verso.ru.domain.event_date import EventDate
from verso.ru.domain.factories import _set_clergy_status, book, page, person
from verso.ru.domain.person import Person
from verso.ru.domain.record_defaults import RecordDefaults
from verso.ru.domain.side import Side
from verso.ru.domain.status import Status
from verso.ru.gender import Gender

__all__ = [
    "NOT_IN_DOCUMENT",
    "CauseOfDeath",
    "EventDate",
    "Gender",
    "Person",
    "RecordDefaults",
    "Side",
    "Status",
    "_set_clergy_status",
    "book",
    "page",
    "person",
]
