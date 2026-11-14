"""Which saints a name commemorates, and on which days — the святцы.

A child was named for a saint kept near the birth or the christening, so the
name a book gives and the day it gives are two readings that check each
other. The table is the «Алфавит имён всех святых» of the 1906 Требник
(`data/svyatcy_1906.tsv`, imported by `python -m verso.ru.cli.svyatcy import`;
provenance and licence in `data/LICENSE.svyatcy`). It is the Church's
calendar of 1906, not of 1780: a saint canonised in between adds a day to a
name that already had days, which can only make a check more lenient.

`Svyatcy` is pure — a check receives one and asks it; `load_svyatcy()` is the
one place that reads the file.

A name reaches the table through `Svyatcy.keys`: the names lexicon's base
(`matching_base`, so Иван finds Іѡа́ннъ and Прасковья finds Параске́ѵа), the
spellings the two sides disagree on, and `ALSO_KEPT` for the people's forms the
lexicon does not tie to their saint.
"""
from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from verso.ru.church_calendar.julian import JulianDate, from_jdn, is_leap, jdn, nearest_occurrence
from verso.ru.gender import Gender
from verso.ru.naming import matching_base

MonthDay = tuple[int, int]

# The 1906 Требник's alphabet of saints, shipped as package data.
DATA: Traversable = files("verso.ru.church_calendar") / "data" / "svyatcy_1906.tsv"

#: The people's forms → the book's names whose days ALSO count for them. Where
#: the lexicon folds a vernacular name and the book's form onto two different
#: bases, or knows the people's form and not the saint it came from. Added,
#: never substituted: the book has a Родион of its own (4 January, 10 November)
#: besides the Иродион of 8 April every April Родион of the corpus was named for.
#: Names, not keys: a key is the lexicon's answer, and a layer over the base may
#: answer otherwise (the base folds Юлиания onto Иулиания, a corpus the other
#: way), so a `Svyatcy` files them under the lexicon it files the book's names
#: under. Kept here rather than in a names layer: a base there renames res_names.
ALSO_KEPT: dict[tuple[Gender, str], tuple[str, ...]] = {
    (Gender.FEMALE, "Ульяна"): ("Иулиания",),       # Ульяна → Юлиана; Іꙋлїанїа
    (Gender.MALE, "Емельян"): ("Емилиан",),         # Емельян, Амельян; Є҆мїлїа́нъ
    (Gender.MALE, "Амельян"): ("Емилиан",),
    (Gender.MALE, "Перфил"): ("Порфирий",),         # Перфил; Порфѵ́рїй
    (Gender.MALE, "Парфён"): ("Парфений",),         # Парфён; Парѳе́нїй
    (Gender.MALE, "Созон"): ("Созонт",),            # Созон; Сѡзо́нтъ
    (Gender.MALE, "Эммануил"): ("Мануил",),         # Эммануил; Манꙋ́илъ
    (Gender.FEMALE, "Соломонида"): ("Соломония",),  # Соломонида, Салманида; Соломѡні́а
    (Gender.FEMALE, "Саломонида"): ("Соломония",),
    (Gender.FEMALE, "Салманида"): ("Соломония",),
    (Gender.FEMALE, "Марта"): ("Марфа",),           # Марта; Ма́рѳа
    (Gender.MALE, "Родион"): ("Иродион",),          # Родион, Радивон; Иродїѡ́нъ, 8 April
    (Gender.MALE, "Радивон"): ("Иродион",),
    (Gender.MALE, "Алимпий"): ("Алипий",),          # Алимпий, Олимпий; Алѷ́пїй
    (Gender.MALE, "Олимпий"): ("Алипий",),
    (Gender.MALE, "Исак"): ("Исакий",),             # Исак, Исаак; Ісаа́кїй
}


def _base(name: str, gender: Gender) -> str:
    """`matching_base` to its fixed point. names.csv holds chains (Иоаникий →
    Иоанникий → Анникий) and one pair pointing at each other (Семен ↔ Семён),
    so one step is not enough and an unguarded loop never ends."""
    seen: set[str] = set()
    while name not in seen:
        seen.add(name)
        name = matching_base(name, gender) or name
    return name


def name_key(name: str, gender: Gender) -> str:
    """The key a name is filed under. Never written anywhere.

    `matching_base` to its fixed point; then lower case, ё as е, «ь» before a
    vowel as «и» (Дарья ~ Дарїа, Агафья ~ Агафїа), and one letter for a
    doubled one (Агриппина ~ Агрѷпина).
    """
    key = _base(name, gender).lower().replace("ё", "е")
    key = re.sub(r"ь(?=[аеиоуыэюя])", "и", key)
    return re.sub(r"(.)\1", r"\1", key)


@dataclass(frozen=True)
class Commemorated:
    """One name of the alphabet: as printed, in modern letters, its days, and
    — for a form given beside another («[и҆лѝ Валенті́нъ]») — the headword it
    stands beside."""
    gender: Gender
    headword: str
    name: str
    dates: tuple[MonthDay, ...]
    variant_of: str | None = None


@dataclass(frozen=True)
class Near:
    """A name kept within a window of a day: the book's name in modern letters,
    the form our records compare by (`matching_base`: «Иоанн» → «Иван»), which
    day, and how many days from the one asked about (negative: before it)."""
    name: str
    base: str
    day: MonthDay
    offset: int
    key: str


class Svyatcy:
    """The alphabet, indexed by name key and by day."""

    def __init__(self, rows: Iterable[Commemorated]):
        self._dates: dict[tuple[Gender, str], set[MonthDay]] = {}
        self._shown: dict[tuple[Gender, str], str] = {}
        self._by_day: dict[tuple[Gender, MonthDay], list[str]] = {}
        for row in rows:
            k = (row.gender, name_key(row.name, row.gender))
            self._dates.setdefault(k, set()).update(row.dates)
            self._shown.setdefault(k, row.name)
            for day in row.dates:
                keys = self._by_day.setdefault((row.gender, day), [])
                if k[1] not in keys:
                    keys.append(k[1])
        self._also: dict[tuple[Gender, str], tuple[str, ...]] = {}
        for (gender, ours), theirs in ALSO_KEPT.items():
            k = (gender, name_key(ours, gender))
            extra = (name_key(n, gender) for n in theirs)
            self._also[k] = tuple(dict.fromkeys((*self._also.get(k, ()), *(e for e in extra if e != k[1]))))

    def __len__(self) -> int:
        return len(self._dates)

    def keys(self, name: str, gender: Gender) -> tuple[str, ...]:
        """Every key whose days count for the name: its own, then `ALSO_KEPT`'s, each under the lexicon the table was
        built under."""
        key = name_key(name, gender)
        return (key, *self._also.get((gender, key), ()))

    def knows(self, name: str, gender: Gender) -> bool:
        return any((gender, k) in self._dates for k in self.keys(name, gender))

    def commemorations(self, name: str, gender: Gender) -> tuple[MonthDay, ...]:
        days: set[MonthDay] = set()
        for k in self.keys(name, gender):
            days |= self._dates.get((gender, k), set())
        return tuple(sorted(days))

    def nearest(self, name: str, gender: Gender,
                around: JulianDate) -> tuple[int, MonthDay] | None:
        """Signed days from `around` to the nearest day the name is kept, and
        that day; None when the book does not know the name."""
        best: tuple[int, MonthDay] | None = None
        for m, d in self.commemorations(name, gender):
            offset = nearest_occurrence(m, d, around)
            if best is None or (abs(offset), offset) < (abs(best[0]), best[0]):
                best = (offset, (m, d))
        return best

    def names_near(self, around: JulianDate, gender: Gender,
                   before: int, after: int) -> list[Near]:
        """Every name of that gender kept from `before` days before `around` to
        `after` days after it, nearest first. A saint of 29 February is kept
        on the 28th in a common year."""
        found: dict[str, Near] = {}
        start = jdn(*around)
        for offset in range(-before, after + 1):
            y, m, d = from_jdn(start + offset)
            days = [(m, d)]
            if (m, d) == (2, 28) and not is_leap(y):
                days.append((2, 29))
            for day in days:
                for key in self._by_day.get((gender, day), ()):
                    if key not in found or abs(offset) < abs(found[key].offset):
                        shown = self._shown[(gender, key)]
                        found[key] = Near(shown, matching_base(shown, gender) or shown,
                                          day, offset, key)
        return sorted(found.values(), key=lambda n: (abs(n.offset), n.offset, n.name))


_GENDERS = {"M": Gender.MALE, "F": Gender.FEMALE}
COLUMNS = ("gender", "headword", "name", "dates", "variant_of")


def format_dates(dates: Iterable[MonthDay]) -> str:
    return ";".join(f"{m:02d}-{d:02d}" for m, d in dates)


def parse_dates(text: str) -> tuple[MonthDay, ...]:
    out: list[MonthDay] = []
    for part in text.split(";"):
        m, d = part.split("-")
        out.append((int(m), int(d)))
    return tuple(out)


def read_rows(path: Path | Traversable | None = None) -> list[Commemorated]:
    """The TSV as rows (the packaged one by default). Lines starting with «#» are provenance."""
    # Binary under a text wrapper: a Traversable opens text without `newline=`.
    with io.TextIOWrapper((DATA if path is None else path).open("rb"), encoding="utf-8", newline="") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    reader = csv.DictReader(lines, delimiter="\t")
    return [
        Commemorated(
            gender=_GENDERS[r["gender"]],
            headword=r["headword"],
            name=r["name"],
            dates=parse_dates(r["dates"]),
            variant_of=r["variant_of"] or None,
        )
        for r in reader
    ]


def load_svyatcy(path: Path | Traversable | None = None) -> Svyatcy:
    return Svyatcy(read_rows(path))
