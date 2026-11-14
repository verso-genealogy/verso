"""A synthetic corpus for the people index, of the pilot's size: ≈ 1300 books, 27 000 records — every name
invented, put together from syllables, in the books' orthography (ѣ, і, ѳ, the final ъ).

Not a test: what `test_people_index_build` builds the index from, and, run, the build timed (`main`). Deterministic by
its seed, so two runs build the same rows.
"""
from __future__ import annotations

import bisect
import random
from dataclasses import dataclass, replace

from verso.ru.facts.checks.births import BirthSpan
from verso.ru.persons.lives import Clue, record_days, year_days
from verso.ru.persons.people import Seen, Sighting

# i18n: content — invented names of the books' orthography
_MALE = ("Іоаннъ", "Василій", "Ѳедоръ", "Матѳей", "Петръ", "Алексѣй", "Андрей", "Григорій", "Тимоѳей", "Семенъ",
         "Ѳома", "Никифоръ", "Евѳимій", "Дмитрій", "Иларіонъ", "Савва", "Кузьма", "Пантелеймонъ", "Ѳеодосій",
         "Аѳанасій", "Михаилъ", "Гавріилъ", "Сергѣй", "Яковъ", "Захарій", "Лука", "Ѳилиппъ", "Прокопій",
         "Кириллъ", "Антоній", "Елисѣй", "Игнатій", "Трофимъ", "Мартинъ", "Карпъ", "Осипъ", "Власъ", "Лаврентій")
_FEMALE = ("Анна", "Марія", "Пелагея", "Агрипина", "Ѳекла", "Евдокія", "Параскева", "Ксенія", "Татіана", "Ірина",
           "Акилина", "Матрона", "Устинья", "Ѳеодосія", "Аграфена", "Наталія", "Ольга", "Варвара", "Евѳимія",
           "Домна", "Улита", "Соломонида", "Анисія", "Ѳедора", "Мавра", "Хіонія")
_HEADS = ("Бѣл", "Чер", "Мил", "Гор", "Кос", "Луп", "Дуб", "Вѣтр", "Ѳед", "Зим", "Сок", "Бар", "Лѣс", "Пѣт",
          "Кур", "Мух", "Ѳом", "Сер", "Мор", "Тих", "Глух", "Кис", "Жар", "Шир", "Ряб", "Хлѣб", "Дѣд", "Кал")
_MIDS = ("", "ан", "ус", "ел", "ох", "ов", "ушк", "ен", "ин", "ал", "уш", "ик", "ѣн", "ет")
_TAILS = ("", "ец", "ак", "ищ", "ов", "ун", "ар", "ил")
_ENDS = (("овъ", "ова"), ("инъ", "ина"), ("евъ", "ева"), ("скій", "ская"), ("ихъ", "ихъ"))
_STATUSES = ("крестьянинъ", "солдатъ", "мѣщанинъ", "однодворецъ", "дьячекъ", "отставной солдатъ",
             "государственный крестьянинъ", "вдова", "дворовый человѣкъ", "пономарь", "")
_PLACES = tuple(f"{h}{m}ово" for h in ("Заман", "Хлест", "Глуп", "Вѣтл", "Ѳедос", "Кривц", "Дуб")
                for m in ("ил", "ак", "ин", "ов", "ушк"))


def _modern(text: str) -> str:
    """The modern spelling as `Person` gives it: the letters, and no final ъ."""
    out = text
    for old, new in (("ѣ", "е"), ("Ѣ", "Е"), ("і", "и"), ("І", "И"), ("ѳ", "ф"), ("Ѳ", "Ф")):
        out = out.replace(old, new)
    return out.removesuffix("ъ")


def _root(name: str) -> str:
    """A father's name as his child's patronymic starts: «Петръ» → «Петр»."""
    base = name.removesuffix("ъ").removesuffix("ій").removesuffix("ей").removesuffix("а").removesuffix("ь")
    return base or name


@dataclass(frozen=True)
class _Man:
    """One invented person of a village's: as the books write them, and when they were born."""
    seen: Seen
    born: int


def _people(rnd: random.Random, village: str, stems: list[str], count: int) -> list[_Man]:
    out = []
    for _ in range(count):
        female = rnd.random() < 0.45
        name = rnd.choice(_FEMALE if female else _MALE)
        father = rnd.choice(_MALE)
        end = _ENDS[rnd.randrange(len(_ENDS))]
        surname = rnd.choice(stems) + end[1 if female else 0] if rnd.random() < 0.8 else ""
        residence = village if rnd.random() < 0.8 else rnd.choice(_PLACES)
        out.append(_Man(Seen(name, _root(father) + ("ова" if female else "овъ"), surname, rnd.choice(_STATUSES),
                             residence, "ж" if female else "м",
                             (_modern(name), _modern(_root(father)) + ("овна" if female else "ович"),
                              _modern(surname))),
                        rnd.randrange(1700, 1880)))
    return sorted(out, key=lambda m: m.born)


def _key(s: Seen) -> tuple[str, str, str, str] | None:
    return (s.residence, s.modern[0], s.modern[1], s.modern[2]) if s.surname else None


def pilot_sightings(*, books: int = 1300, records: int = 27_000, seed: int = 1847) -> list[Sighting]:
    """Every sighting of `records` records over `books` books: two to four people a record, of a village's
    people of age that year, now and then under another status; a newborn in a third of the records (dated,
    offering nothing); a birth a stated age gives one in four, a death one in twenty."""
    rnd = random.Random(seed)
    stems = sorted({f"{rnd.choice(_HEADS)}{rnd.choice(_MIDS)}{rnd.choice(_TAILS)}" for _ in range(2600)})
    folk = {v: _people(rnd, v, stems, max(40, records * 2 // len(_PLACES))) for v in _PLACES}
    out: list[Sighting] = []
    per_book = max(1, records // books)
    for book in range(books):
        village = _PLACES[book % len(_PLACES)]
        year = 1780 + book % 120
        file = f"{village}/{year}/book{book:04}.py"
        people = folk[village]
        births = [m.born for m in people]
        adults = people[bisect.bisect_left(births, year - 70):bisect.bisect_right(births, year - 18)] or people
        for ordinal in range(per_book):
            father: Seen | None = None
            for _ in range(rnd.choice((2, 3, 3, 4, 4))):
                man = rnd.choice(adults)
                seen = man.seen if rnd.random() < 0.7 else replace(man.seen, status=rnd.choice(_STATUSES))
                born = None
                if rnd.random() < 0.25:
                    age = max(0, year - man.born + rnd.randrange(-3, 4))
                    span = record_days(year - age)
                    assert span is not None
                    born = BirthSpan(span[0], span[1], float(age))
                died = year_days(year) if rnd.random() < 0.05 else None
                out.append(Sighting(village, year, seen,
                                    Clue(_key(seen), year_days(year), born, died,
                                         died is None and rnd.random() < 0.8, adult=rnd.random() < 0.6),
                                    (file, ordinal)))
                father = father or (seen if seen.sex == "м" else None)
            if father is not None and rnd.random() < 0.33:   # the newborn: the father's patronymic is theirs
                span = record_days(year)
                assert span is not None
                name = rnd.choice(_MALE)
                child = replace(father, name=name, modern=(_modern(name), father.modern[1], father.modern[2]))
                out.append(Sighting(village, year, None,
                                    Clue(_key(child), year_days(year), BirthSpan(span[0], span[1], 0.0),
                                         newborn=True),
                                    (file, ordinal)))
    return out


def main() -> None:
    """The build timed at the pilot's size: `python tests/people_synthetic.py`."""
    import statistics
    import time

    from verso.ru.persons.people import PeopleIndex
    rows = pilot_sightings()
    offering = [r.seen for r in rows if r.seen is not None]
    print(f"{len(rows)} sightings, {len(offering)} offering someone, {len({s.written for s in offering})} people")
    took = []
    for _ in range(7):
        start = time.perf_counter()
        PeopleIndex(rows)
        took.append(time.perf_counter() - start)
    print(f"build: best {min(took) * 1000:.0f} ms, median {statistics.median(took) * 1000:.0f} ms")


if __name__ == "__main__":
    main()
