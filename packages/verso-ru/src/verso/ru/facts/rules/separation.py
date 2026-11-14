"""Whom a source counted apart.

Nearly every predicate this layer carries JOINS people, and a rule built on one
argues that two appearances are the same person. Being counted into a group is
the opposite kind of evidence, and the corpus has almost none of it: a source
that writes two entries into one group has said there are TWO, on adjacent
lines, in its own hand. That outranks any similarity of names — which is a
prior, where this is a statement.

The rule is handed a predicate TYPE that carries a group and does not ask what
kind of group it is; `tests/test_facts_layering.py` greps this file for any
word that would betray one.

    правило = источник пересчитал этих двоих порознь внутри одной группы,
              значит их двое

Identity is a parameter, as everywhere here: two appearances the fold calls one
person are one member of the group, and a source cannot separate somebody from
themselves.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import AssertionSet, Grouped, Persona


@dataclass(frozen=True)
class Counted:
    """One group, and whom the source counted into it.

    `key` is the predicate's own payload, opaque here and meaningful to a
    report: the rule orders and compares groups without ever reading one.
    """
    key: object
    members: tuple[IdentityKey, ...]
    appearances: tuple[Persona, ...]

    def __len__(self) -> int:
        return len(self.members)


def counted_together(facts: AssertionSet, *, grouping: type[Grouped],
                     identity: Identity) -> list[Counted]:
    """Every group the source states, with the identities counted into it.

    Groups come back sorted by their payload's text, and members inside a group
    in first-seen order, so a report of this is byte-stable.
    """
    seen: dict[object, tuple[list[IdentityKey], list[Persona]]] = {}
    for record in facts.records():
        key_of = identity(record)
        for a in record.of(grouping):
            who = key_of(a.subject)
            if who is None:
                continue
            members, appearances = seen.setdefault(a.payload, ([], []))
            if who not in members:
                members.append(who)
                appearances.append(a.subject)
    return [Counted(key=k, members=tuple(m), appearances=tuple(p))
            for k, (m, p) in sorted(seen.items(), key=lambda kv: str(kv[0]))]


def counted_apart(facts: AssertionSet, *, grouping: type[Grouped],
                  identity: Identity) -> set[frozenset[IdentityKey]]:
    """Pairs the source itself separated, by counting both into one group.

    A set of unordered pairs rather than the groups: this is what a check that
    already has two candidates in hand needs to ask, and asking it this way
    means the check never learns the group either.
    """
    apart: set[frozenset[IdentityKey]] = set()
    for group in counted_together(facts, grouping=grouping, identity=identity):
        for i, a in enumerate(group.members):
            for b in group.members[i + 1:]:
                if a != b:
                    apart.add(frozenset((a, b)))
    return apart


def groups_of(facts: AssertionSet, *, grouping: type[Grouped],
              who: Iterable[Persona]) -> dict[Persona, tuple[object, ...]]:
    """Every group each named appearance was counted into.

    The shape a check wants when it starts from people rather than from groups.
    """
    wanted = set(who)
    found: dict[Persona, list[object]] = {p: [] for p in wanted}
    for a in facts.of(grouping):
        if a.subject in wanted:
            found[a.subject].append(a.payload)
    return {p: tuple(v) for p, v in found.items()}
