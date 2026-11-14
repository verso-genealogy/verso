"""One person holding two claims that cannot both be true.

The second general rule of this layer, and the one the whole design is
answerable to. Three of the checks it will carry are the same question wearing
different clothes — they gather the claims of one person and ask whether two of
them fit together, differing only in WHICH two predicates and in what «fit»
means. If that did not come out as one rule, the layer would have bought a
single join and a lot of ceremony.

So the rule takes both predicates as TYPE PARAMETERS and the incompatibility as
a FUNCTION. It cannot name either, and it does not know what makes two claims
incompatible: an order that cannot hold, a span too wide to be a life, two
values that exclude each other. The caller knows, and the caller is outside.

    правило = у одной личности два утверждения, которые не могут быть верны
              одновременно

Identity is a parameter, as everywhere here, and it is what makes this reach
past a single entry: with a name fold the rule compares what one entry says,
and with a config-backed identity it compares what a whole corpus says about
one person.

Two things it deliberately does NOT do. It does not read a basis — assertions
an author has withdrawn are gone before a rule sees them, filtered by
`AssertionSet.believed()`. And it does not decide what to report: the verdict
the caller's function returns is carried through untouched, so a report can
print the reason without the rule ever having a vocabulary for one.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import Assertion, AssertionSet


@dataclass(frozen=True)
class Contradiction:
    """Two claims of one person that the caller's test rejected.

    `verdict` is whatever that test returned — the rule carries it and never
    inspects it, which is how a report gets its wording without the rule
    holding any.
    """
    who: IdentityKey
    left: Assertion
    right: Assertion
    verdict: object


def held[A: Assertion](facts: AssertionSet, *, kind: type[A],
                       identity: Identity) -> dict[IdentityKey, tuple[A, ...]]:
    """Every claim of one shape, grouped by the person it is about.

    Exposed because a caller sometimes has to ask whether a person holds a
    claim of some shape AT ALL before deciding which comparison applies — and
    that question is about the person, not about the pair, so the rule cannot
    answer it inside `contradictions` without learning why.
    """
    out: dict[IdentityKey, list[A]] = {}
    for record in facts.records():
        key_of = identity(record)
        for claim in record.of(kind):
            who = key_of(claim.subject)
            if who is None:
                continue
            out.setdefault(who, []).append(claim)
    return {who: tuple(claims) for who, claims in out.items()}


def contradictions[A: Assertion, B: Assertion](
        facts: AssertionSet, *, left: type[A], right: type[B],
        identity: Identity,
        incompatible: Callable[[A, B], object | None],
) -> list[Contradiction]:
    """Pairs of one person's claims that cannot both be true.

    `incompatible(a, b)` returns the verdict when the two cannot stand
    together, and None when they can. Returning a value rather than a bool is
    what lets the caller carry its own reason out without the rule naming one.

    Ordered by the person, then by each claim's own total order, so a report of
    this is byte-stable whatever order the assertions arrived in.
    """
    lefts = held(facts, kind=left, identity=identity)
    rights = held(facts, kind=right, identity=identity)
    found: list[Contradiction] = []
    for who, mine in lefts.items():
        if left is right:
            # One shape on both sides: an unordered pair is ONE pair of
            # claims — asked in both orders, reported once, never as both
            # (a, b) and (b, a).
            others = cast(tuple[B, ...], mine)
            for i, a in enumerate(mine):
                for b in others[i + 1:]:
                    verdict = incompatible(a, b)
                    if verdict is not None:
                        found.append(Contradiction(who=who, left=a, right=b,
                                                   verdict=verdict))
                        continue
                    verdict = incompatible(cast(A, b), cast(B, a))
                    if verdict is not None:
                        found.append(Contradiction(who=who, left=b, right=a,
                                                   verdict=verdict))
            continue
        for a in mine:
            for b in rights.get(who, ()):
                verdict = incompatible(a, b)
                if verdict is not None:
                    found.append(Contradiction(who=who, left=a, right=b,
                                               verdict=verdict))
    found.sort(key=lambda c: (c.who, c.left.sort_key, c.right.sort_key))
    return found
