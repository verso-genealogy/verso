"""One person, two deaths that cannot be one — `facts-check check=death-claims`.

The third over-merge channel, beside `birth-claims` and `father-claims`. A
person dies once and is buried once, so two records of one canonical that date
the death — or the burial — on days that cannot be one day describe two people
folded together. The sweep says the same of two burial entries
(`candidates.two_burials_conflict`: «человек умирает один раз, это тёзки»);
this reads it off the assertions, from every kind of record that dates a death:
a burial entry, a roll listing someone as dead since the last revision (a year
told to the counter), a war card.

A death is compared with a death and a burial with a burial. The two are days
apart in one life, and how many is not ours to guess — a gap between one
record's death and another's burial proves nothing a death-to-death gap would
not. A told year is read at `date-order`'s measured slack (`as_read`, ±2).

One class is `date-order`'s and is not repeated here: a burial in one record
before the death another record gives («погребение раньше смерти», between
records). The two checks together are every pair of records that cannot share
one death.

Measured on the five villages (2026-09-28): in Горюхино every finding is a
roll's told year against a metric burial, and the roll's year EARLIER than the
burial by 3 years four times, by 4 four times, then 5, 6 and 7. The other side
— told later, `date-order`'s measurement — runs 1 year ×14, 2 ×5, 3 never, so
the slack stops at 2; on this side nothing breaks at 3. A gap under a year past
the slack is therefore LOW: the counter may simply have misremembered.
"""
from __future__ import annotations

from dataclasses import dataclass

from verso.ru.church_calendar.julian import day_number
from verso.ru.facts.checks.dates import as_read, definitely_before
from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import AssertionSet, BuriedOn, DiedOn, FactDate
from verso.ru.facts.projection import canonical_name
from verso.ru.facts.rules.disagreement import contradictions, held

#: How far past the told-year slack a gap stays LOW — see the module docstring.
NEAR_SLACK_DAYS = 365

#: A claim that a life ended on a day.
Ended = DiedOn | BuriedOn


def gap_days(a: FactDate, b: FactDate) -> int | None:
    """Days between the nearest days two dates can mean, a told year read at
    its slack: 0 when they can be one day, None when either is open-ended.

    Counted in Julian days: `date(...).toordinal()` had no 29 February 1800 and
    dropped such a death without a word."""
    x, y = as_read(a), as_read(b)
    xe, xl = day_number(x.earliest), day_number(x.latest)
    ye, yl = day_number(y.earliest), day_number(y.latest)
    if xe is None or xl is None or ye is None or yl is None:
        return None
    return max(0, ye - xl, xe - yl)


@dataclass(frozen=True)
class DeathFinding:
    """A person two of whose records date the death, or the burial, on days
    that cannot be one. `pairs` are (claim, claim, days apart)."""
    canonical: str
    claims: tuple[Ended, ...]
    pairs: tuple[tuple[Ended, Ended, int], ...]

    @property
    def gap(self) -> int:
        return max(days for _, _, days in self.pairs)

    @property
    def confidence(self) -> str:
        """LOW when every pair rests on a told year and misses it by under a
        year past the slack; HIGH otherwise."""
        def near(a: Ended, b: Ended, days: int) -> bool:
            return (a.date.circa or b.date.circa) and days < NEAR_SLACK_DAYS
        return "LOW" if all(near(*p) for p in self.pairs) else "HIGH"


def _date_orders(facts: AssertionSet, identity: Identity) -> set[frozenset[object]]:
    """The record pairs `date-order` already reports: a burial in one before
    the death the other gives."""
    def before(a: BuriedOn, b: DiedOn) -> bool | None:
        return True if definitely_before(a.date, b.date) else None
    return {frozenset((c.left.cite.record_id, c.right.cite.record_id))
            for c in contradictions(facts, left=BuriedOn, right=DiedOn,
                                    identity=identity, incompatible=before)
            if c.left.cite.record_id != c.right.cite.record_id}


def death_claims(facts: AssertionSet, identity: Identity) -> list[DeathFinding]:
    """People whose records date two deaths (or two burials); widest gap
    first, HIGH first. `facts` should be the believed assertions."""
    theirs = _date_orders(facts, identity)

    def apart(a: Ended, b: Ended) -> int | None:
        if a.cite.record_id == b.cite.record_id:
            return None
        if frozenset((a.cite.record_id, b.cite.record_id)) in theirs:
            return None
        days = gap_days(a.date, b.date)
        return days if days else None

    pairs: dict[IdentityKey, list[tuple[Ended, Ended, int]]] = {}
    for kind in (DiedOn, BuriedOn):
        for c in contradictions(facts, left=kind, right=kind, identity=identity,
                                incompatible=apart):
            assert isinstance(c.verdict, int)
            assert isinstance(c.left, (DiedOn, BuriedOn))
            assert isinstance(c.right, (DiedOn, BuriedOn))
            pairs.setdefault(c.who, []).append((c.left, c.right, c.verdict))
    deaths = held(facts, kind=DiedOn, identity=identity)
    burials = held(facts, kind=BuriedOn, identity=identity)
    found: list[DeathFinding] = []
    for who, found_pairs in pairs.items():
        name = canonical_name(who)
        if name is None:
            continue
        # Record by record, and inside one the death before its burial.
        claims: list[Ended] = sorted((*deaths.get(who, ()), *burials.get(who, ())),
                                     key=lambda a: (a.cite.sort_key, isinstance(a, BuriedOn)))
        found.append(DeathFinding(canonical=name, claims=tuple(claims),
                                  pairs=tuple(found_pairs)))
    found.sort(key=lambda f: (f.confidence != "HIGH", -f.gap, f.canonical))
    return found
