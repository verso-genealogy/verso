"""The people of the neighbouring years: a village's proofread people, as a reading vocabulary.

A reader reads a record better given the people the corpus already holds for its village in the nearest
years. The list is built from records-v1 documents (`verso.core.records`) and names the people of the record
being read as other records name them; what it never holds is that record itself, its other copy (a
консисторская копия, a duplicate book) or anything read off it: every record of the asked year is left out.
Only the names, a status the scribe wrote and the years leave a record; never a note, and never a record
not yet proofread.

Only the standard library is imported here, as in the rest of `verso.ru.reading`, so every caller builds
the list with one code. The places' canonical names are a parameter.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: The years asked for, ±.
WINDOW = 10
#: The list's ceiling in characters: about 20 thousand tokens, at some 1.7 characters a token for such name lists.
MAX_PEOPLE_CHARS = 34_000
NO_SURNAME = "—"
#: The roles of the clergy a record names; they are never in the list.
CLERGY = frozenset({"priest", "deacon", "dyachok", "sexton"})

_ORTHOGRAPHY = str.maketrans({"ѣ": "е", "Ѣ": "Е", "і": "и", "І": "И", "ѳ": "ф", "Ѳ": "Ф", "ѵ": "и", "Ѵ": "И",
                              "Ө": "Ф", "ө": "ф"})
_FINAL_HARD_SIGN = re.compile(r"[ъЪ](?=\s|$|[.,;])")


def _key(text: str) -> str:
    """The word whatever the orthography («Ѳедорова» and «Федорова» are one reading): the notes' `reading_key`
    (a test holds the two together), kept here so the package stays standard-library only."""
    folded = _FINAL_HARD_SIGN.sub("", text.translate(_ORTHOGRAPHY).replace("ѯ", "кс").replace("Ѯ", "Кс"))
    return folded.lower().replace("ё", "е").removesuffix("ъ")


@dataclass(frozen=True)
class Mention:
    """One person of one proofread record, as far as the list tells of them."""
    name: str
    patronymic: str | None
    surname: str | None
    status: str | None      # only one the scribe wrote, and not the book's default
    year: int               # the book's year


@dataclass(frozen=True)
class Entry:
    """One person of the list: a name as written, in every year the village's books name it."""
    name: str
    patronymic: str | None
    surname: str | None
    status: str | None
    years: tuple[int, ...]


@dataclass(frozen=True)
class PeopleList:
    village: str
    year: int               # the year being read: never one of the entries' years
    window: int             # the years asked for: ±window
    reach: int              # the years the ceiling let in: ±reach (≤ window)
    entries: tuple[Entry, ...]


def _value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("original") or value.get("text") or value.get("old")
    return value.strip() if isinstance(value, str) and value.strip() else None


def mentions(docs: Iterable[tuple[str, Mapping[str, Any]]], places: Mapping[str, str] | None = None, *,
             scope: str = "village") -> dict[str, dict[int, list[Mention]]]:
    """By village folder and book year, the people of its proofread records (`review == "reviewed"`: nothing
    unproofread enters, whoever asks): no clergy, a given name, a residence (written, derived, else the
    book's) that is the village itself (`scope="parish"`: any). `places` maps a place as written to its
    canonical name, so «Маниловка» and «Маниловка, село» are one."""
    canon: Mapping[str, str] = places or {}
    out: dict[str, dict[int, list[Mention]]] = defaultdict(lambda: defaultdict(list))
    for village, doc in docs:
        written = doc.get("written") or {}
        year = written.get("year")
        if not isinstance(year, int):
            continue
        defaults = written.get("defaults") or {}
        default_residence = _value(defaults.get("residence"))
        default_status = {"male": _value(defaults.get("status_male")), "female": _value(defaults.get("status_female"))}
        home = canon.get(village, village)
        for run in doc.get("pages", ()):
            for record in run.get("records", ()):
                if record.get("review") != "reviewed":  # only the proofread
                    continue
                for person in record.get("persons", ()):
                    if person.get("role") in CLERGY:
                        continue
                    w, d = person.get("written") or {}, person.get("derived") or {}
                    name = _value(w.get("given"))
                    residence = _value(w.get("residence")) or _value(d.get("residence")) or default_residence
                    if not name or not residence:
                        continue
                    if scope == "village" and canon.get(residence, residence) != home:
                        continue
                    status = _value(w.get("status"))
                    default = default_status.get(d.get("gender") or "")
                    if status and default and _key(status) == _key(default):
                        status = None
                    out[village][year].append(Mention(name, _value(w.get("patronymic")), _value(w.get("surname")),
                                                      status, year))
    return {v: dict(by_year) for v, by_year in out.items()}


# -- the list --------------------------------------------------------------------------------------

def _entries(by_year: Mapping[int, Sequence[Mention]], years: Iterable[int]) -> tuple[Entry, ...]:
    found: dict[tuple[str, str | None, str | None], tuple[str | None, set[int]]] = {}
    for year in sorted(years):
        for m in by_year.get(year, ()):
            status, seen = found.get((m.name, m.patronymic, m.surname), (None, set()))
            seen.add(year)
            found[(m.name, m.patronymic, m.surname)] = (status or m.status, seen)
    return tuple(Entry(n, p, s, status, tuple(sorted(seen))) for (n, p, s), (status, seen) in found.items())


def people_list(by_year: Mapping[int, Sequence[Mention]], village: str, year: int, window: int, *,
                max_chars: int = MAX_PEOPLE_CHARS) -> PeopleList:
    """The village's people of years `year`±1 … ±`window`, never `year` itself. The years go in by pairs,
    nearest first, each pair whole or not at all, while the list stays under `max_chars`; the nearest pair
    is in whatever its length."""
    years: list[int] = []
    reach = 0
    for k in range(1, window + 1):
        tried = years + [y for y in (year - k, year + k) if y in by_year]
        if k > 1 and len(render(PeopleList(village, year, window, k, _entries(by_year, tried)))) > max_chars:
            break
        years, reach = tried, k
    return PeopleList(village, year, window, reach, _entries(by_year, years))


_MASCULINE = re.compile(r"(ов|ев|ёв|ин|ын)$")


def _group(surname: str) -> str:
    key = _key(surname)
    return key[:-1] if key.endswith("а") and _MASCULINE.search(key[:-1]) else key


def render(people: PeopleList) -> str:
    """The list's lines: by surname (a wife's and a daughter's form with the husband's), alphabetical, the
    people without one last; each person once, with the years (two digits) and a written status."""
    groups: dict[str, list[Entry]] = defaultdict(list)
    for e in people.entries:
        groups[_group(e.surname) if e.surname else ""].append(e)

    def label(key: str, members: Sequence[Entry]) -> str:
        if not key:
            return NO_SURNAME
        spellings = Counter(e.surname for e in members if e.surname)
        masculine = Counter({s: n for s, n in spellings.items() if _key(s) == key})
        return min((masculine or spellings).items(), key=lambda kv: (-kv[1], kv[0]))[0]

    def person(e: Entry) -> str:
        years = ",".join(f"{y % 100:02d}" for y in e.years)
        return " ".join(filter(None, (e.name, e.patronymic))) + f" {years}" + (f" ({e.status})" if e.status else "")

    # alphabetical as a reader reads it: «Іосифъ» among the И, «Ѳоминъ» among the Ф (`reading_key`)
    lines = sorted(((label(k, ms), ms) for k, ms in groups.items() if k), key=lambda lm: (_key(lm[0]), lm[0]))
    if "" in groups:
        lines.append((NO_SURNAME, groups[""]))

    def order(e: Entry) -> tuple[str, ...]:
        return _key(e.name), _key(e.patronymic or ""), e.name, e.patronymic or ""

    return "\n".join(f"{lab}: " + "; ".join(person(e) for e in sorted(ms, key=order)) for lab, ms in lines)


PEOPLE_HEAD = ("Люди этого села из вычитанных записей соседних лет (±{span}, кроме года этой записи), по фамилиям; "
               "числа — годы записей (две последние цифры). Это словарь для чтения имён, а не ответ: пиши имя так, "
               "как оно написано в этой записи. Если имя, отчество или фамилию ты взял из списка, а на снимке их не "
               "разобрать, поставь «?».")


def people_text(people: PeopleList) -> str:
    """The frame and the list: one text part, first in the turn."""
    span = f"{people.reach}" if people.reach == people.window else f"{people.reach} из ±{people.window}"
    return PEOPLE_HEAD.format(span=span) + "\n" + render(people)
