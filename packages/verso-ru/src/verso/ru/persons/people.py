"""Autocomplete for a whole person: имя, отчество, фамилия — and with them the
status and the place the corpus writes beside them.

`verso.app.names` offers each field on its own, and so knows nothing of which
name, patronymic and surname belonged to one man. This index keeps the five
together, so one choice fills a godparent's whole row: «Іоаннъ Петровъ
Чичиковъ · крестьянинъ · Заманиловка».

It is read off the BUILT records, not the source text. Of the corpus's
statuses only about one in ten is a string literal — the rest are constants or
a book's `RecordDefaults` — and so is most of what a person's place is; a
mother's surname is her husband's, a roll member's patronymic his father's.
What the translator reads is what a person is, and that is what is offered.

* **Who is in it**: a person with a given name and at least a patronymic or a
  surname. The early books write no surnames, and a revision member is «Иванъ
  Петровъ» and nothing more; one with a name alone identifies nobody.
* **The newborn is not**: the child of a birth is named in the record and
  everything else about them — patronymic, surname, status, place — is the
  parents', derived. Who they are as a participant is said by a later record.
* **One row per way of writing them**: the same man written «крестьянинъ» in one
  book and «солдатъ» in another is two rows, since choosing them fills two
  different things.
* **Matching as in `names`**: every part typed is the start of the written
  form's, orthography aside, or of its modern form's — «петрович» finds
  «Петровъ». An empty part matches anything.
* **Only who could stand in the record**: someone whose place the village's
  books write (`places`) — a Заманиловка man is not offered in Глуповы Горы —
  and, given the record's day, one of whose lives can reach it
  (`verso.ru.persons.lives`): born, old enough for the slot, not yet dead. The
  record being edited is no evidence: its own appearances neither count nor
  shape a life.

Pure: built records in, suggestions out — `sightings_of` reads one loaded DSL
file's namespace; walking a corpus's files is `verso.ru.persons.corpus`'s job.
"""
from __future__ import annotations

import gc
import threading
from collections import Counter
from collections.abc import Generator, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verso.ru.domain.person import Person
from verso.ru.gender import Gender
from verso.ru.persons.lives import (
    Clue, Days, Life, after_death, apart, clues_of, lives_of, min_age, record_days, undated)
from verso.ru.naming.matching import match_key, name_sex

# The record attribute holding a birth's newborn (a christening's too).
NEWBORN = "child"
_SEX = {Gender.MALE: "м", Gender.FEMALE: "ж"}  # i18n: content — the sex as the index keys it


@dataclass(frozen=True)
class Seen:
    """One appearance of a person, as the built record holds it."""
    name: str
    patr: str
    surname: str
    status: str
    residence: str
    sex: str                         # «м», «ж» or «»
    modern: tuple[str, str, str]     # the three names in modern orthography

    @property
    def written(self) -> tuple[str, str, str, str, str]:
        return (self.name, self.patr, self.surname, self.status, self.residence)


def persons(record: object, *, newborn: bool = False) -> Iterator[Person]:
    """Every person a built record names, once each, the newborn aside unless
    asked for: an attribute that is a `Person`, or a list of them or of what
    carries one (`members`, `relatives`)."""
    found: set[int] = set()
    for attr, value in getattr(record, "__dict__", {}).items():
        if attr == NEWBORN and not newborn:
            continue
        items: tuple[Any, ...] | list[Any] = value if isinstance(value, (list, tuple)) else (value,)
        for item in items:
            person = item if isinstance(item, Person) else getattr(item, "person", None)
            if isinstance(person, Person) and id(person) not in found:
                found.add(id(person))
                yield person


def _text(value: object) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return "" if "?" in text else text


def seen(person: Person) -> Seen | None:
    """What the corpus can offer of `person`, or None when they have no given
    name, or neither a patronymic nor a surname. A maiden name alone is not a
    surname: it is not what the record calls her."""
    name = _text(person.name_orig)
    patr = _text(person.patr_orig) or _text(person.patr_old) or _text(person.patr_modern)
    surname = _text(person.last_name) or _text(person.last_name_modern)
    if not name or not (patr or surname):
        return None
    return Seen(name, patr, surname, _text(person.status), _text(person.residence),
                _SEX.get(person.gender, "") if person.gender else "",
                (_text(person.name_modern), _text(person.patr_modern), _text(person.last_name_modern)))


def sightings(records: list[Any], clues: Mapping[int, Clue], *,
              year: int | None) -> list[tuple[Seen | None, Clue, int | None]]:
    """Every appearance the index offers, with what it says of a life
    (`clues`, by `id(Person)`; one the facts layer did not read is dated by
    its file's `year`) and the place of its record among `records` — and, with
    no `Seen`, every other appearance the facts read: the newborn, whose
    christening dates the man he becomes."""
    out: list[tuple[Seen | None, Clue, int | None]] = []
    where: dict[int, int] = {}
    for ordinal, record in enumerate(records):
        for person in persons(record, newborn=True):
            if id(person) in where:
                continue
            where[id(person)] = ordinal
            found = seen(person) if person is not getattr(record, NEWBORN, None) else None
            if found is not None:
                out.append((found, clues.get(id(person)) or undated(person, year), ordinal))
            elif id(person) in clues:
                out.append((None, clues[id(person)], ordinal))
    out.extend((None, clue, None) for pid, clue in clues.items() if pid not in where)
    return out


def sightings_of(namespace: Mapping[str, Any], *, village: str, year: int, file: str) -> list[Sighting]:
    """What one loaded DSL file gives the people index: each person its records
    name, and what each appearance says of a life — read by the facts layer,
    the records still under review included (`drafts`): a sweep's people are
    offered while it is being read. Its personas are named by their records-JSON
    ids, a repeated number counted within this file (`RecordIds`). `file` — the
    file as the index keys a record (its path from the corpus's root)."""
    from verso.core.ratchet import runtime_records
    from verso.ru.facts.extract.common import SlotIndex
    from verso.ru.facts.model import AssertionSet
    from verso.ru.pipeline.facts import assertions_of
    from verso.core.records.ids import RecordIds

    books = list({id(v): (Path(file).name, v) for v in namespace.values()}.values())
    slots = SlotIndex()
    ids = RecordIds()
    ids.walk(namespace)
    facts = AssertionSet(assertions_of(books, village=village, slots=slots, drafts=True, ids=ids))
    return [Sighting(village, year, appearance, clue, None if ordinal is None else (file, ordinal))
            for appearance, clue, ordinal in sightings(runtime_records(namespace), clues_of(facts, slots, year=year),
                                                       year=year)]


@dataclass(frozen=True)
class RecordContext:
    """The record a person is asked for: its village (whose books' places a person
    must be of), its day as far as it is written, the slot (how old one must be,
    whether the dead may stand there), a sex where the slot gives one, and the
    record itself as the index keys it (`exclude`: it does not offer its own people)."""
    village: str
    year: int | None = None
    month: int | None = None
    day: int | None = None
    slot: str = ""
    gender: str = ""
    exclude: tuple[str, int] | None = None


@dataclass(frozen=True)
class PersonSuggestion:
    name: str
    patr: str
    surname: str
    status: str
    residence: str
    count: int          # in this village
    total: int          # in the corpus
    years: str          # «1849–1863», «1872», or «» when the files say no year


@dataclass(slots=True)
class _Person:
    written: tuple[str, str, str, str, str]
    keys: tuple[frozenset[str], frozenset[str], frozenset[str]]
    modern: tuple[str, str, str]                     # of its first sighting: whose keys it holds
    sexes: dict[str, int] = field(default_factory=dict)
    villages: dict[str, int] = field(default_factory=dict)
    years: dict[int, int] = field(default_factory=dict)
    total: int = 0
    sex: str = ""
    seen: list[int] = field(default_factory=list)   # its sightings, by index


@dataclass
class _Hit:
    """A person as the query sees them: less the appearances it excludes."""
    person: _Person
    count: int
    total: int
    years: Mapping[int, int]
    ons: list[Days]


@dataclass(frozen=True)
class Sighting:
    """One appearance as the index is built from it."""
    village: str
    year: int | None             # of its file
    seen: Seen | None            # what it offers; None for one read for the lives alone
    clue: Clue                   # what it says of a life
    record: tuple[str, int] | None = None   # (its file, the record's place in it)


class PeopleIndex:
    def __init__(self, found: Iterable[Sighting]) -> None:
        # The build makes some 700 000 objects that live as long as the index and form no cycle: the cyclic
        # collector, run as they come, would only walk them again and again (two full passes a build, over the
        # whole process's heap) — a third of the build and more.
        with _collector_paused():
            self._build(found)

    def _build(self, found: Iterable[Sighting]) -> None:
        self._rows = list(found)
        self._lives: list[Life]
        self._lives, self._holding = lives_of([r.clue for r in self._rows])
        self._groups: dict[object, list[int]] = {}
        self._records: dict[tuple[str, int], list[int]] = {}
        by: dict[tuple[str, str, str, str, str], _Person] = {}
        keys = _Keys()
        for i, r in enumerate(self._rows):
            if r.clue.key is not None:
                self._groups.setdefault(r.clue.key, []).append(i)
            if r.record is not None:
                self._records.setdefault(r.record, []).append(i)
            s = r.seen
            if s is None:
                continue
            entry = by.get(s.written)
            if entry is None:
                entry = by[s.written] = _Person(s.written, keys.of(s), s.modern)
            elif s.modern != entry.modern:   # one way of writing them, modernized otherwise elsewhere
                entry.keys = _union(entry.keys, keys.of(s))
            entry.sexes[s.sex] = entry.sexes.get(s.sex, 0) + 1
            entry.villages[r.village] = entry.villages.get(r.village, 0) + 1
            entry.total += 1
            if r.year is not None:
                entry.years[r.year] = entry.years.get(r.year, 0) + 1
            entry.seen.append(i)
        self._places: dict[str, set[str]] = {}
        for entry in by.values():
            # The sex most written, the first written of two as many (as `Counter.most_common` picks).
            entry.sex = max(((k, v) for k, v in entry.sexes.items() if k), key=_count, default=("", 0))[0]
            if entry.written[4]:
                for village in entry.villages:
                    self._places.setdefault(village, set()).add(entry.written[4])
        self._people = list(by.values())

    def __len__(self) -> int:
        return len(self._people)

    def places(self, village: str) -> set[str]:
        """The places `village`'s books write someone of — and the village."""
        return self._places.get(village, set()) | {village}

    def _here(self, e: _Person, village: str, places: set[str]) -> bool:
        """Whether `e` lived where `village`'s books look: a place they write,
        or, written with none, the village's own books."""
        residence = e.written[4]
        return residence in places if residence else e.villages.get(village, 0) > 0

    def _alive(self, mine: list[int], own: set[int], at: Days, min_age: float,
               dead_days: float | None = 0.0) -> bool:
        """Whether a life holding one of the sightings `mine` can stand in a
        record of `at`. Where the record left out (`own`) shares a name with
        them, their lives are read again without it: a record is not evidence
        for itself."""
        for key in dict.fromkeys(self._rows[i].clue.key for i in mine):
            group = self._groups.get(key, []) if key is not None else []
            ours = [i for i in mine if self._rows[i].clue.key == key]
            if own.isdisjoint(group):
                if any(self._lives[n].possible(at, min_age, dead_days)
                       for i in ours for n in self._holding.get(i, ())):
                    return True
                continue
            rest = [i for i in group if i not in own]
            found, holding = lives_of([self._rows[i].clue for i in rest])
            place = {i: j for j, i in enumerate(rest)}
            if any(found[n].possible(at, min_age, dead_days) for i in ours for n in holding.get(place[i], ())):
                return True
        return False

    def suggest(self, name: str, patr: str, surname: str, *, village: str, gender: str = "",
                limit: int = 8, exclude: tuple[str, int] | None = None,
                at: Days | None = None, min_age: float = 0.0,
                dead_days: float | None = 0.0) -> list[PersonSuggestion]:
        """The people whose given name, patronymic and surname each start with
        the part typed for it, of a place `village`'s books write and — given
        `at`, the days the record can have been written on — alive on it (or
        dead at most `dead_days`, `lives.after_death`) and `min_age` years old.
        Best first: those written exactly as typed — the
        record's own spelling, which a choice would otherwise overwrite — then
        the most written in the village, then in the corpus, then the nearest
        to `at` (without it, the latest).

        `exclude` — the record being edited, as (file, its place among the
        file's records): it does not offer its own people. One written
        elsewhere too stays, counted and dated without it; one written only
        there goes."""
        typed = tuple(part.strip() for part in (name, patr, surname))
        query = tuple(match_key(part) for part in typed)
        if not any(query):
            return []
        own = set(self._records.get(exclude, ())) if exclude is not None else set()
        hits: list[_Hit] = []
        places = self.places(village)
        for e in self._people:
            if not (all(not q or any(k.startswith(q) for k in keys)
                        for q, keys in zip(query, e.keys, strict=True))
                    and (not gender or not e.sex or e.sex == gender)
                    and self._here(e, village, places)):
                continue
            mine = [i for i in e.seen if i not in own] if own else e.seen
            if not mine:
                continue
            if at is not None and not self._alive(mine, own, at, min_age, dead_days):
                continue
            ons = [on for i in mine if (on := self._rows[i].clue.on) is not None]
            if len(mine) == len(e.seen):
                hits.append(_Hit(e, e.villages.get(village, 0), e.total, e.years, ons))
                continue
            villages = Counter(self._rows[i].village for i in mine)
            years = Counter(y for i in mine if (y := self._rows[i].year) is not None)
            hits.append(_Hit(e, villages[village], len(mine), years, ons))

        def differs(h: _Hit) -> int:
            return sum(1 for t, w in zip(typed, h.person.written, strict=False) if t and t != w)

        def when(h: _Hit) -> int:
            if at is not None:   # an appearance with no day at all comes last
                return min((apart(on, at) for on in h.ons), default=10**9)
            return -max(h.years, default=0)
        hits.sort(key=lambda h: (differs(h), -h.count, -h.total, when(h), h.person.written))
        return [PersonSuggestion(*h.person.written, h.count, h.total, _years(h.years)) for h in hits[:limit]]


    def suggest_for(self, name: str, patr: str, surname: str, context: RecordContext, *,
                    limit: int = 8) -> list[PersonSuggestion]:
        """`suggest` for a record: the sex is the slot's, else the given name's
        (`matching.name_sex`); the day, the age and the dead the slot allows are
        the record's; between one and fifty people."""
        return self.suggest(name, patr, surname, village=context.village,
                            gender=context.gender or name_sex(name), limit=max(1, min(limit, 50)),
                            exclude=context.exclude, at=record_days(context.year, context.month, context.day),
                            min_age=min_age(context.slot), dead_days=after_death(context.slot))


_pause_lock = threading.Lock()
_pauses = 0             # the builds under way
_resume = False         # whether the collector ran when the first of them began


@contextmanager
def _collector_paused() -> Generator[None]:
    """The cyclic collector held off while the block runs (`gc.disable`), and let run again when the last of the
    blocks under way in any thread ends — if it ran when the first began."""
    global _pauses, _resume
    with _pause_lock:
        if _pauses == 0:
            _resume = gc.isenabled()
            gc.disable()
        _pauses += 1
    try:
        yield
    finally:
        with _pause_lock:
            _pauses -= 1
            if _pauses == 0 and _resume:
                gc.enable()


def _count(item: tuple[str, int]) -> int:
    return item[1]


class _Keys:
    """The keys a sighting's three names are matched by (`match_key` of the written form and of the modern),
    each pair's computed once a build: of the corpus's ≈ 430 000 names some 11 000 differ. A pair's keys are
    one frozenset, shared by everyone written so."""

    def __init__(self) -> None:
        self._pairs: dict[tuple[str, str], frozenset[str]] = {}
        self._of: dict[tuple[str, str, str, str, str, str], tuple[frozenset[str], frozenset[str], frozenset[str]]] = {}

    def pair(self, text: str, modern: str) -> frozenset[str]:
        found = self._pairs.get((text, modern))
        if found is None:
            found = self._pairs[(text, modern)] = frozenset(match_key(t) for t in (text, modern) if t)
        return found

    def of(self, s: Seen) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        names = (s.name, s.patr, s.surname, *s.modern)
        found = self._of.get(names)
        if found is None:
            found = self._of[names] = (self.pair(s.name, s.modern[0]), self.pair(s.patr, s.modern[1]),
                                       self.pair(s.surname, s.modern[2]))
        return found


def _union(a: tuple[frozenset[str], frozenset[str], frozenset[str]],
           b: tuple[frozenset[str], frozenset[str], frozenset[str]]) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    return (a[0] | b[0], a[1] | b[1], a[2] | b[2])


def _years(years: Mapping[int, int]) -> str:
    if not years:
        return ""
    first, last = min(years), max(years)
    return str(first) if first == last else f"{first}–{last}"
