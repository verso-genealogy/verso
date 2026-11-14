"""Two сословия held by one canonical — the check behind `estate-conflicts`.

WHO conflicts is the disagreement rule's to say: two claims of one person that
cannot both hold. It is handed `Titled` twice and an incompatibility it cannot
read — two statuses whose estates, as `verso.ru.domain.estates.estate_of`
classifies them (owner aliases included), are both known and differ. A
role-only status («солдатка», «вдова») names no estate and so contradicts
nothing. What a report prints for each is `verso.ru.consolidation.estate_conflicts`'.
"""
from __future__ import annotations

from verso.ru.domain.estates import estate_of
from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import AssertionSet, Titled
from verso.ru.facts.rules.disagreement import contradictions, held


def _differ(a: Titled, b: Titled) -> tuple[str, str] | None:
    ea, eb = estate_of(a.status), estate_of(b.status)
    return (ea, eb) if ea is not None and eb is not None and ea != eb else None


def estates_in_conflict(facts: AssertionSet,
                        identity: Identity) -> dict[IdentityKey, tuple[Titled, ...]]:
    """Each person whose records style them into two сословия, with every
    estate-bearing `Titled` they hold — the question `held` exists for, since
    what to print is about the person and not about a pair."""
    conflicted = {c.who for c in contradictions(
        facts, left=Titled, right=Titled, identity=identity, incompatible=_differ)}
    claims = held(facts, kind=Titled, identity=identity)
    return {who: tuple(t for t in claims[who] if estate_of(t.status))
            for who in conflicted}
