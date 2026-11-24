"""What each canonical's records say that separates two namesakes.

`union-dups`' guards: the households a roll counted the person into
(`EnumeratedIn` — «оба — члены двора N одной ревизии» is the corpus's strongest
evidence that two same-named people are two), their own baptisms, by when they
had died, and when they are still seen alive. Placed on canonicals by whatever
identity the caller hands in — the consolidation bridge, in practice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from verso.ru.facts.checks.dates import as_read
from verso.ru.facts.labels import record_number
from verso.ru.facts.projection import canonical_name
from verso.ru.facts.model import (
    AssertionSet, BaptizedOn, BornOn, BuriedOn, DiedOn, EnumeratedIn, MarriedOn, SurvivedUntil)
from verso.ru.facts.rules.disagreement import held
from verso.ru.facts.rules.separation import counted_together
from verso.ru.messages import t

#: One household a roll counted somebody into: (the roll's date as ISO
#: `YYYY-MM-DD`, `00` for what it does not state; the household's own number as
#: the roll writes it, «1в»; the roll — the source file). The roll keeps apart
#: two rolls that number a household alike on one date (one year's двор 1 can
#: be four дела of two villages), and the reason names it.
Household = tuple[str, str, str]


#: A calendar point, (year, month, day) — what `FactDate.earliest`/`latest`
#: give, so two of them compare in order.
Day = tuple[int, int, int]

#: One of the profile's OWN baptisms: an entry that records both the birth and
#: the christening of this person. (the entry's key; the birth as the earliest
#: and latest day it can mean; how the reason names it.)
Baptism = tuple[str, Day, Day, str]

#: A dated statement about a life, as the bound it sets and how the reason
#: names it. On a death: the LATEST day it can be. On a sign of life: the
#: EARLIEST.
LifeMark = tuple[Day, str]


@dataclass(frozen=True)
class Lives:
    """What a profile's records say that can tell two namesakes apart, besides
    a двор: whose baptisms they are, by when they had died, and when they are
    still seen alive. Read off the assertions (`lives_of_canonicals`), so it is
    every record the canonical stands for, not the one its res_name came from.
    """
    baptisms: frozenset[Baptism] = frozenset()
    died_by: frozenset[LifeMark] = frozenset()
    alive_at: frozenset[LifeMark] = frozenset()


def _iso(d: Any) -> str:
    return f"{d.year or 0:04d}-{d.month or 0:02d}-{d.day or 0:02d}"


def households_of_canonicals(facts: AssertionSet,
                             identity: Any) -> dict[str, frozenset[Household]]:
    """Every household a roll counted each canonical into.

    What `union-dups` stands its same-household guard on: the roll's own
    statement («числился во дворѣ N»), placed on a canonical by the bridge
    rather than recovered from the res_names the canonical stands for. The
    roll is part of the key, so two rolls numbering a household alike on one
    date stay two. A member we reconstructed (`hidden=True`) was never written
    by the scribe, asserts no `EnumeratedIn`, and so separates nobody. And a
    canonical that absorbed a member needs no move list to be seen in its
    household — the bridge already knows whose appearance it was.

    The group is keyed by the predicate's whole payload; the (date, number,
    roll) handed out beside it is what the reason line prints.
    """
    named: dict[object, EnumeratedIn] = {}
    for a in facts.of(EnumeratedIn):
        named.setdefault(a.payload, a)
    out: dict[str, set[Household]] = {}
    for group in counted_together(facts, grouping=EnumeratedIn, identity=identity):
        listed = named[group.key]
        household = (_iso(listed.as_of), listed.group, listed.within)
        for who in group.members:
            if (canon := canonical_name(who)) is not None:
                out.setdefault(canon, set()).add(household)
    return {canon: frozenset(held) for canon, held in out.items()}


def _cite_label(c: Any) -> str:
    page = str(t("facts.leaf", page=c.page)) if c.page else ""
    return f"{c.source_file} {record_number(c)}{page}"


def lives_of_canonicals(facts: AssertionSet, identity: Any) -> dict[str, Lives]:
    """What each canonical's records say about its baptisms, death and life.

    The evidence `union-dups` separates two namesakes on besides a двор, read
    off the assertions and placed by the bridge like `EnumeratedIn`:

    - its OWN baptisms — an entry holding both a `BornOn` and a `BaptizedOn`
      for the person; one entry is one christening, whatever it is called;
    - by when it had died — the latest day each `DiedOn`/`BuriedOn` can mean;
    - when it is still seen alive — the earliest day of each sign of life:
      a roll counting it (`SurvivedUntil`), a wedding, a birth or baptism, a
      death of its own.

    A circa year (a сказка's told death) is read with `date-order`'s measured
    slack, both ways, so neither side is shortened to make a pair fit.
    """
    baptisms: dict[str, set[Any]] = {}
    died: dict[str, set[Any]] = {}
    alive: dict[str, set[Any]] = {}

    christened = held(facts, kind=BaptizedOn, identity=identity)
    for who, births in held(facts, kind=BornOn, identity=identity).items():
        canon = canonical_name(who)
        if canon is None:
            continue
        entries = {c.cite.record_id for c in christened.get(who, ())}
        for b in births:
            first, last = b.date.earliest, b.date.latest
            if b.cite.record_id in entries and first is not None and last is not None:
                baptisms.setdefault(canon, set()).add(
                    (repr(b.cite.record_id), first, last,
                     str(t("facts.lives.christened_at", cite=_cite_label(b.cite), date=b.date))))

    ended = ((DiedOn, str(t("facts.lives.died"))), (BuriedOn, str(t("facts.lives.buried"))))
    for kind, verb in ended:
        for who, claims in held(facts, kind=kind, identity=identity).items():
            canon = canonical_name(who)
            if canon is None:
                continue
            for c in claims:
                last = as_read(c.date).latest
                if last is not None:
                    died.setdefault(canon, set()).add(
                        (last, f"{verb} {c.date} [{_cite_label(c.cite)}]"))

    seen = ((SurvivedUntil, str(t("facts.lives.alive"))), (MarriedOn, str(t("facts.lives.married"))),
            (BornOn, str(t("facts.lives.born"))), (BaptizedOn, str(t("facts.lives.christened"))), *ended)
    for kind, verb in seen:
        for who, claims in held(facts, kind=kind, identity=identity).items():
            canon = canonical_name(who)
            if canon is None:
                continue
            for c in claims:
                first = as_read(c.date).earliest
                if first is not None:
                    alive.setdefault(canon, set()).add(
                        (first, f"{verb} {c.date} [{_cite_label(c.cite)}]"))

    return {canon: Lives(baptisms=frozenset(baptisms.get(canon, ())),
                         died_by=frozenset(died.get(canon, ())),
                         alive_at=frozenset(alive.get(canon, ())))
            for canon in baptisms.keys() | died.keys() | alive.keys()}


def two_baptisms(a: Lives, b: Lives) -> tuple[str, str] | None:
    """Two entries, each christening one of the pair, on births that cannot be
    one day. A metric book enumerates one baptism per entry the way a сказка
    enumerates one member per line — the rule `candidates.two_baptisms_conflict`
    already applies to the sweep — so the parents reused the name. The same
    birth copied twice (one day in both) proves nothing and is left alone."""
    for key_a, first_a, last_a, said_a in sorted(a.baptisms):
        for key_b, first_b, last_b, said_b in sorted(b.baptisms):
            if key_a != key_b and (last_a < first_b or last_b < first_a):
                return said_a, said_b
    return None


def outlived(dead: Lives, alive: Lives) -> tuple[str, str] | None:
    """A death of one, and a sign of the other's life after its latest day —
    which a single person cannot give. Name reuse is the case the dates above
    already see by year; this reads the day, and every sign of life (a roll
    that counts them, a wedding, a death of their own), not only a birth."""
    for last, said_death in sorted(dead.died_by):
        for first, said_life in sorted(alive.alive_at):
            if last < first:
                return said_death, said_life
    return None
