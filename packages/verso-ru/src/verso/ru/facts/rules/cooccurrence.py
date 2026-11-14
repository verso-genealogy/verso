"""Two predicates that keep meeting on the same subject.

It is handed two relational predicate TYPES and joins them; it does not know,
and may not ask, what kind of document produced them.
`tests/test_facts_layering.py` greps this file for any vocabulary that would
betray one — including the sentence that used to stand here, which named a
second pair of predicates by the role its people hold. The guard was right:
naming it is exactly the leak, and the call sites in `verso.ru.cli.facts` are where
a join belongs.

    правило = соединение двух утверждений об одном и том же участнике,
              повторяющееся в нескольких записях

Меняя пару предикатов, тем же кодом получают другой вопрос — без единой новой
строки здесь.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import (
    AssertionSet, Citation, Persona, Record, Relational)

@dataclass(frozen=True)
class Occurrence:
    """One entry in which the two sides met."""
    record: Record
    left: Persona
    right: Persona
    left_cite: Citation
    right_cite: Citation


@dataclass
class Pair:
    left_key: IdentityKey
    right_key: IdentityKey
    occurrences: list[Occurrence] = field(default_factory=list)


def cooccurrences(facts: AssertionSet, *, left: type[Relational], right: type[Relational],
                  identity: Identity, min_count: int = 2,
                  kin_guard: bool = False) -> list[Pair]:
    """Pairs whose two sides meet on one subject in >= min_count entries.

    The pair key is symmetric, so somebody holding the left side in one entry
    and the right side in another is one pair, not two. Each entry counts once
    per pair.

    `identity` decides what counts as one person. The rule does not care how —
    a folded written name and a canonical read out of the consolidation config
    are the same shape to it.

    `kin_guard` drops a pair the entry ITSELF already relates: their meeting
    then restates a relation the source states outright, and carries no
    independent weight.
    """
    groups: dict[frozenset[IdentityKey], Pair] = {}
    for record in facts.records():
        key = identity(record)
        stated: set[frozenset[IdentityKey]] = set()
        if kin_guard:
            for f in record.of(Relational):
                ka, kb = key(f.subject), key(f.other)
                if ka is not None and kb is not None and ka != kb:
                    stated.add(frozenset((ka, kb)))

        counted: set[frozenset[IdentityKey]] = set()
        for a in record.of(left):
            for b in record.of(right):
                if a.other != b.other:
                    continue
                ka, kb = key(a.subject), key(b.subject)
                if ka is None or kb is None or ka == kb:
                    continue
                pair = frozenset((ka, kb))
                if pair in counted or (kin_guard and pair in stated):
                    continue
                counted.add(pair)
                group = groups.get(pair)
                if group is None:
                    group = groups[pair] = Pair(left_key=ka, right_key=kb)
                group.occurrences.append(Occurrence(
                    record=record, left=a.subject, right=b.subject,
                    left_cite=a.cite, right_cite=b.cite))

    out = [g for g in groups.values() if len(g.occurrences) >= min_count]
    out.sort(key=lambda g: len(g.occurrences), reverse=True)
    return out
