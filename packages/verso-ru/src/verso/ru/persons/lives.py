"""Whether someone could be alive on the day of a record — for Verso's people index.

`verso.ru.persons.people` offers a whole person under a name field. Offered from the
whole corpus, it put a man buried fifty years before the record beside one not
yet born. This module says, for each appearance, what the corpus knows of a
life, and whether that life can reach a given day.

* **What one appearance says** (`Clue`) is the facts layer's reading of it, not
  a second reading of the DSL: the days its entry can have been written on
  (`entry_days`), a birth from its own date or stated age (`birth_span`), a
  death from its own burial or a roll's «умер» (`as_read`), and whether it puts
  the person alive on the day — at the font, the wedding, the cradle, the
  newborn's father, the причт, or counted alive in a roll (`_ALIVE_SLOTS`). A
  named relative is not: one is named after death as often as not. A retracted age
  (`source_age_error=`) dates nothing: only `believed()` is read.
* **Which appearances are one life** is asked by the record-level identity rule
  the cross-record checks share (`death_age.person_key`: the given name folded
  to its base, Егоръ = Георгій) plus the place written. A form without a
  surname never joins one with: a village holds hundreds of namesakes by name
  and patronymic. Inside one such name, appearances that date a birth form
  lives by `birth-claims`' own tolerance (`years_apart` within
  `birth_slack_years`) — namesakes born years apart are two lives, and so are
  two birth records, since nobody is christened twice. Appearances that date no
  birth (a godparent, a father) join the one life that can reach their day —
  born by it, old enough for the slot, not past a hundred on it, seen within
  `UNDATED_WINDOW_YEARS` of it — and that they do not contradict (present
  after its death is a contradiction), or every one of several, then capping
  none of them. With no such life — or only lives dead by then, which a
  relative is named after — they chain in date order, a death closing one, and
  so does an appearance further than `UNDATED_WINDOW_YEARS` from the chain's
  first. One the running chain takes as well as a dated life is in both: a
  godmother of 1817–1833 is not the girl of twelve the 1834 roll names.
* **When a life can be offered** (`Life.possible`): not when it is certainly
  unborn (younger than the slot's minimum on the day, the birth's slack
  allowed), older than `MAX_AGE_YEARS`, or dead before the day; and a life
  whose birth nothing dates, not when every appearance of it lies more than
  `UNDATED_WINDOW_YEARS` from the day.

Pure: assertions in, verdicts out. Loading modules is `verso.app_dsl.service`'s job.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from verso.ru.ages import DAYS_PER_YEAR
from verso.ru.consolidation.age_conflicts import FATHER_MIN_DEFAULT, MOTHER_MIN_DEFAULT
from verso.ru.consolidation.death_age import person_key
from verso.ru.facts.checks.births import BirthSpan, birth_slack_years, birth_span, years_apart
from verso.ru.facts.checks.dates import as_read
from verso.ru.facts.checks.parenthood import FATHER_DAYS
from verso.ru.facts.checks.reconcile import PRESENT_SLOTS, entry_days
from verso.ru.facts.model import (
    AgedYears, Assertion, AssertionSet, BornOn, BuriedOn, DiedOn, FactDate, OfficiatedAt, Persona, SurvivedUntil)

#: No one is offered older than this on the day of the record. The corpus's
#: oldest stated ages stop short of it, and the books make the old older
#: (`births._OLD_AGE_OVERSTATEMENT`), so it is a bound, not a guess.
MAX_AGE_YEARS = 100

#: A life whose birth nothing dates — a godparent, a father the metric books
#: name and nothing else does — is not offered for a record further than this
#: from every one of its appearances. Chosen as a heuristic: someone
#: who takes part in the books as an adult rarely stands in them sixty years
#: apart.
UNDATED_WINDOW_YEARS = 60

#: The slots only an adult fills, and how old they must be on the day: the
#: youngest parent `age-conflicts` accepts. A deceased, a member of a двор and
#: a named relative may be any age.
ADULT_SLOTS = ("father", "mother", "god_parent", "groom", "bride", "witness")
ADULT_YEARS = min(FATHER_MIN_DEFAULT, MOTHER_MIN_DEFAULT)

#: The slot of a christening's newborn: one life holds one.
_NEWBORN = "child"

#: Who a record puts alive on its day. `PRESENT_SLOTS` — at the font, the
#: wedding, the cradle — and the newborn's father too: reconcile leaves him out,
#: since he may die before the birth, but by no more than nine months
#: (`parenthood.FATHER_DAYS`), which a list of suggestions need not tell from
#: alive. The причт is present by `OfficiatedAt`, a roll's living by
#: `SurvivedUntil`. Not a relative: a father is named at his son's wedding
#: thirty years after his burial.
_ALIVE_SLOTS = (*PRESENT_SLOTS, "father")

Days = tuple[int, int]
LifeKey = tuple[str, str, str, str]


#: The slots a record may fill with someone already dead, and for how long
#: after the death, in days (None: any time). A newborn's father, by the
#: longest pregnancy the law allowed (`parenthood.FATHER_DAYS`); a named
#: relative — a deceased's father, a bride's late father — and a roll's member,
#: which lists the dead since the last revision, at any time.
_NAMED_DEAD: tuple[tuple[str, float | None], ...] = (
    ("father", FATHER_DAYS), ("relatives", None), ("@", None))


def min_age(slot: str) -> float:
    """How old the person offered for `slot` (a record's argument — «father»,
    «god_parent2», «@3» for a roll member) must be on the day."""
    return float(ADULT_YEARS) if slot.startswith(ADULT_SLOTS) else 0.0


def after_death(slot: str) -> float | None:
    """How many days after their death `slot` may still name someone: 0 for
    who must be alive on the day, None for a slot that names the dead."""
    return next((days for prefix, days in _NAMED_DEAD if slot.startswith(prefix)), 0.0)


def _ordinal(day: tuple[int, int, int]) -> int:
    """A (y, m, d) the facts layer reads in the Julian calendar, as the
    proleptic ordinal `BirthSpan` counts in. A Julian 29 February of a year the
    Gregorian calendar keeps common is the 28th and a day."""
    y, m, d = day
    try:
        return date(y, m, d).toordinal()
    except ValueError:
        return date(y, m, 28).toordinal() + d - 28


def days_of(fact: FactDate) -> Days | None:
    """The days a date can mean, or None when it is open at an end."""
    first, last = fact.earliest, fact.latest
    if first is None or last is None:
        return None
    return _ordinal(first), _ordinal(last)


def record_days(year: int | None, month: int | None = None, day: int | None = None) -> Days | None:
    """The days a record dated (year, month, day) can have been written on."""
    if not year:
        return None
    return days_of(FactDate(year=year, month=month or None, day=(day or None) if month else None))


def year_days(year: int | None) -> Days | None:
    return record_days(year)


def life_key(person: Any) -> LifeKey | None:
    """Which appearances may be one life: the place written, and the three
    names by `person_key` — the given name folded to its base form."""
    found = person_key(person)
    if found is None:
        return None
    residence = " ".join(str(getattr(person, "residence", None) or "").split())
    return (residence, found.name, found.patronymic, found.surname)


@dataclass(frozen=True)
class Clue:
    """What one appearance says of a life."""
    key: LifeKey | None
    on: Days | None                  # the days the entry can have been written on
    born: BirthSpan | None = None    # the birth it dates, if any
    died: Days | None = None         # the days the death it records can be (0: open before)
    present: bool = False            # alive on the day of the entry
    newborn: bool = False            # the child a christening names
    adult: bool = False              # in a slot only an adult fills (`ADULT_SLOTS`)


def undated(person: Any, year: int | None) -> Clue:
    """An appearance the facts layer did not read: dated by its file alone."""
    return Clue(life_key(person), year_days(year))


def clues_of(facts: AssertionSet, slots: Any, *, year: int | None = None) -> dict[int, Clue]:
    """`id(Person)` → what its appearance says, for every persona `slots` read.
    `year` dates an entry whose claims date nothing (its file's year)."""
    believed = facts.believed()
    days = {rid: (_ordinal(first), _ordinal(last)) for rid, (first, last) in entry_days(believed).items()}
    own: dict[Persona, list[Assertion]] = {}
    for a in believed:
        own.setdefault(a.subject, []).append(a)
    fallback = year_days(year)
    out: dict[int, Clue] = {}
    for persona, person in slots.items():
        claims = own.get(persona, [])
        cite = claims[0].cite if claims else None
        on = _written_on(days.get(cite.record_id), year_days(cite.year)) or fallback if cite else fallback
        locator = cite.locator if cite else ""
        spans = [s for c in claims if isinstance(c, (BornOn, AgedYears)) and (s := birth_span(c)) is not None]
        born = (BirthSpan(min(s.first for s in spans), max(s.last for s in spans),
                          max(s.stated_years for s in spans)) if spans else None)
        # A roll's dead since the last revision died BEFORE it: a date with
        # no first day.
        deaths = [(_ordinal(first) if (first := read.earliest) else 0, _ordinal(last))
                  for c in claims if isinstance(c, (DiedOn, BuriedOn))
                  and (last := (read := as_read(c.date)).latest) is not None]
        present = (locator.startswith(_ALIVE_SLOTS)
                   or any(isinstance(c, (SurvivedUntil, OfficiatedAt)) for c in claims))
        died = (min(d[0] for d in deaths), min(d[1] for d in deaths)) if deaths else None
        out[id(person)] = Clue(life_key(person), on, born, died,
                               present, locator == _NEWBORN, locator.startswith(ADULT_SLOTS))
    return out


def _written_on(claimed: Days | None, filed: Days | None) -> Days | None:
    """The days an entry was written on: those its dated claims span, kept
    inside the year it is filed under. A roll's claims reach back to its
    members' births and its dead's deaths; the year is the roll's."""
    if claimed is None or filed is None:
        return claimed or filed
    first, last = max(claimed[0], filed[0]), min(claimed[1], filed[1])
    return (first, last) if first <= last else filed


@dataclass
class Life:
    """One person as far as the appearances can tell: the clues it holds."""
    members: list[int] = field(default_factory=list)
    births: list[BirthSpan] = field(default_factory=list)
    ons: list[Days] = field(default_factory=list)
    deaths: list[Days] = field(default_factory=list)
    died: int | None = None          # the latest day it can have ended
    last_present: int | None = None
    newborn: bool = False
    # What `add` keeps of the lists above, for the questions asked of a life once for every clue of its name:
    # the earliest of its days, the earliest and the latest day of its births.
    _first_on: Days | None = field(default=None, init=False, repr=False, compare=False)
    _born_first: int | None = field(default=None, init=False, repr=False, compare=False)
    _born_last: int | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.ons:
            self._first_on = min(self.ons)
        if self.births:
            self._born_first = min(b.first for b in self.births)
            self._born_last = max(b.last for b in self.births)

    def add(self, i: int, c: Clue, *, cap: bool = True) -> None:
        self.members.append(i)
        if c.born is not None:
            self.births.append(c.born)
            if self._born_first is None or c.born.first < self._born_first:
                self._born_first = c.born.first
            if self._born_last is None or c.born.last > self._born_last:
                self._born_last = c.born.last
        if c.on is not None:
            self.ons.append(c.on)
            if self._first_on is None or c.on < self._first_on:
                self._first_on = c.on
            if c.present:
                self.last_present = max(self.last_present or c.on[0], c.on[0])
        if cap and c.died is not None:
            self.deaths.append(c.died)
            self.died = c.died[1] if self.died is None else min(self.died, c.died[1])
        self.newborn = self.newborn or c.newborn

    def consistent(self, c: Clue) -> bool:
        """Whether `c` can be this life: not alive after its death, nor dead
        before it was last alive, nor dead on days its death cannot be — one
        dies once (`death-claims`; a roll's told year read at its slack)."""
        if c.present and c.on is not None and self.died is not None and c.on[0] > self.died:
            return False
        if c.died is None:
            return True
        if self.last_present is not None and self.last_present > c.died[1]:
            return False
        return all(apart(c.died, d) == 0 for d in self.deaths)

    def takes_birth(self, c: Clue) -> bool:
        assert c.born is not None
        if c.newborn and self.newborn:
            return False
        return (all(years_apart(b, c.born) <= birth_slack_years(max(b.stated_years, c.born.stated_years))
                    for b in self.births)
                and self.consistent(c))

    def reaches(self, c: Clue) -> bool:
        """Whether a life nothing dates the birth of can stretch to `c`: no
        further from its first appearance than `UNDATED_WINDOW_YEARS`. A man
        seen in 1799 and a namesake seen in 1878 are not one undated life."""
        if c.on is None or self._first_on is None:
            return True
        return apart(self._first_on, c.on) <= UNDATED_WINDOW_YEARS * DAYS_PER_YEAR

    def admits(self, c: Clue) -> bool:
        """Whether an appearance that dates no birth can be this life: born by
        its day — `ADULT_YEARS` before it, in an adult's slot: a bride of 1816
        is not the girl born in 1815 — and not past `MAX_AGE_YEARS` on it (a
        man of the 1719 roll aged 65 is no father in 1779), within
        `UNDATED_WINDOW_YEARS` of something the life was seen at, and not
        contradicting its death."""
        if c.on is not None and self._born_first is not None and self._born_last is not None:
            # The birth as the ages state it, without `birth-claims`' slack:
            # the slack is for two stated ages that disagree, and read into an
            # adult's slot it makes a boy of seven a godfather. An appearance
            # left out goes to the chain, and is offered by its own day.
            youngest = ADULT_YEARS if c.adult else 0
            if (self._born_first + youngest * DAYS_PER_YEAR > c.on[1]
                    or self._born_last + MAX_AGE_YEARS * DAYS_PER_YEAR < c.on[0]):
                return False
            # Seen within the window: some day of the life `apart` from c's by at most it — the latest
            # first, the nearest as the clues come in date order.
            window = UNDATED_WINDOW_YEARS * DAYS_PER_YEAR
            first, last = c.on[0] - window, c.on[1] + window
            if self.ons and not any(on[1] >= first and on[0] <= last for on in reversed(self.ons)):
                return False
        return self.consistent(c)

    def dead_before(self, c: Clue) -> bool:
        """Whether this life had ended by `c`'s day."""
        return self.died is not None and c.on is not None and self.died < c.on[0]

    def _born(self) -> Days:
        slack = birth_slack_years(max(b.stated_years for b in self.births)) * DAYS_PER_YEAR
        return (round(min(b.first for b in self.births) - slack),
                round(max(b.last for b in self.births) + slack))

    def possible(self, at: Days, min_years: float = 0.0, dead_days: float | None = 0.0) -> bool:
        """Whether this life can stand in a record written on `at`, in a slot
        that needs `min_years` of age and names someone dead at most
        `dead_days` (`after_death`; None: at any time)."""
        first, last = at
        if dead_days is not None and self.died is not None and self.died + dead_days < first:
            return False
        if self.births:
            born_first, born_last = self._born()
            return (born_first + min_years * DAYS_PER_YEAR <= last
                    and born_last + MAX_AGE_YEARS * DAYS_PER_YEAR >= first)
        if not self.ons:
            return True
        window = UNDATED_WINDOW_YEARS * DAYS_PER_YEAR
        return any(apart(on, at) <= window for on in self.ons)


def apart(a: Days, b: Days) -> int:
    """The days between the nearest ends of two spans; 0 when they meet."""
    return max(0, b[0] - a[1], a[0] - b[1])


def lives(clues: Sequence[Clue]) -> list[Life]:
    """The lives `clues` hold, each holding the indices of its clues; a clue
    fitting several lives is in each."""
    groups: dict[LifeKey, list[int]] = {}
    out: list[Life] = []
    for i, c in enumerate(clues):
        if c.key is None:
            life = Life()
            life.add(i, c)
            out.append(life)
        else:
            groups.setdefault(c.key, []).append(i)
    for members in groups.values():
        if len(members) == 1:       # most names: one appearance, one life — what `_lives_of_one_name` makes of it
            life = Life()
            life.add(members[0], clues[members[0]])
            out.append(life)
        else:
            out.extend(_lives_of_one_name(clues, members))
    return out


def _lives_of_one_name(clues: Sequence[Clue], members: Iterable[int]) -> list[Life]:
    members = list(members)
    dated: list[Life] = []
    for i in sorted((i for i in members if clues[i].born is not None),
                    key=lambda i: (_born_key(clues[i]), i)):
        c = clues[i]
        home = next((life for life in dated if life.takes_birth(c)), None)
        if home is None:
            home = Life()
            dated.append(home)
        home.add(i, c)
    chain: list[Life] = []
    for i in sorted((i for i in members if clues[i].born is None),
                    key=lambda i: (_on_key(clues[i]), i)):
        c = clues[i]
        fits = [life for life in dated if life.admits(c)]
        going = chain[-1] if chain and chain[-1].consistent(c) and chain[-1].reaches(c) else None
        # One life to go to caps it with this appearance's death; several —
        # the undated chain running on among them — are each only possible.
        if len(fits) == 1 and going is None:
            fits[0].add(i, c)
        else:
            for life in fits:
                life.add(i, c, cap=False)
        # Named after every death it could be — a relative — it may as well be
        # a living namesake: it lives on in the chain too.
        if fits and going is None and not all(life.dead_before(c) for life in fits):
            continue
        if going is not None:
            going.add(i, c, cap=not fits)
        else:
            life = Life()
            life.add(i, c)
            chain.append(life)
    return dated + chain


def _born_key(c: Clue) -> tuple[int, int]:
    assert c.born is not None
    return c.born.first, c.born.last


def _on_key(c: Clue) -> tuple[int, int]:
    return c.on if c.on is not None else (0, 0)


def lives_of(clues: Sequence[Clue]) -> tuple[list[Life], Mapping[int, list[int]]]:
    """The lives, and for each clue index the lives holding it."""
    found = lives(clues)
    holding: dict[int, list[int]] = {}
    for n, life in enumerate(found):
        for i in life.members:
            holding.setdefault(i, []).append(n)
    return found, holding
