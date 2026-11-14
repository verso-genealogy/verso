"""A stated magnitude, against the dated event another record places it from.

The generic shape of the corpus's cross-record date check: one document says
how old somebody was on a day, another says when that somebody began. Put side
by side, a unit confusion or a misread digit is obvious; one record at a time,
neither is visible at all.

The rule names no predicate. It is handed three of them — the dated origin, the
stated magnitude, and the kinships that make two records comparable — so the
same code serves every pair of documents where one dates a beginning and the
other states an age, without learning what either document is. Naming the pairs
here, even as illustration, is what `tests/test_facts_layering.py` forbids: an
example in a docstring is how a rule learns a vocabulary it must not have.

Two pieces of judgement stay OUTSIDE it, as parameters, because they are about
the sources rather than about the comparison:

* `bounds` turns a verbatim magnitude into the day interval it ASSERTS. A clerk
  writing «1 годъ» means "has completed one year", so the claim is [1, 2) years
  wide. Comparing a midpoint instead reports the parish's own truncation as an
  error — on Горюхино that alone produced a hundred and thirty of them, every
  record correct.
* `tolerance_days` / `tolerance_fraction` are the slack on top of that interval,
  for a clerk who rounds up.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import (
    AssertionSet, Citation, Dated, Persona, Quantified, Record, Relational)

Bounds = Callable[[object], tuple[float, float] | None]


@dataclass(frozen=True)
class Origin:
    """Where a person is placed from: one dated beginning, in one entry."""
    key: IdentityKey
    kin: frozenset[IdentityKey]
    at: date
    cite: Citation


@dataclass(frozen=True)
class Disagreement:
    subject: Persona
    subject_key: IdentityKey
    kin_key: IdentityKey | None
    cite: Citation
    origin: Origin
    stated: object
    stated_low: float
    stated_high: float
    elapsed: float
    gap: float
    confidence: str


def _as_date(at) -> date | None:
    if at is None:
        return None
    try:
        return date(*at)
    except ValueError:
        return None


def _kin_of(record: Record, who: Persona,
            links: Sequence[type[Relational]]) -> list[Persona]:
    """Everyone this entry relates TO `who` by one of `links`, in the order the
    entry names them.

    Incoming edges only — the subject of a link whose `other` is `who`. An
    edge `who` is the subject of points the other way (`who` is THEIR parent),
    and the one person it names is not someone `who` descends from. Until
    2026-09-28 this read as if it collected both directions; the outgoing
    branch could never fire, and this is what it always did.

    Order matters only for the report: the first is the one a reader will
    recognise the entry by.
    """
    out: list[Persona] = []
    for a in record.assertions:
        if isinstance(a, tuple(links)) and a.other == who and a.subject not in out:
            out.append(a.subject)
    return out


def collect_origins(facts: AssertionSet, *, origin: type[Dated],
                    links: Sequence[type[Relational]],
                    identity: Identity) -> list[Origin]:
    found: list[Origin] = []
    for record in facts.records():
        key_of = identity(record)
        for a in record.of(origin):
            key = key_of(a.subject)
            at = _as_date(a.date.midpoint)
            if key is None or at is None:
                continue
            kin = frozenset(k for p in _kin_of(record, a.subject, links)
                            if (k := key_of(p)) is not None)
            if not kin:
                continue
            found.append(Origin(key=key, kin=kin, at=at, cite=a.cite))
    return found


def disagreements(facts: AssertionSet, *, origin: type[Dated],
                  quantity: type[Quantified], links: Sequence[type[Relational]],
                  identity: Identity, bounds: Bounds,
                  matches: Callable[[IdentityKey, IdentityKey], bool],
                  tolerance_days: float,
                  tolerance_fraction: float,
                  namesake_ratio: float,
                  min_gap_days: float = 0.0) -> list[Disagreement]:
    """Every stated magnitude no candidate origin can account for.

    The slack (`tolerance_*`) and the ratio past which a magnitude belongs to a
    namesake are the caller's: they are measurements of the sources, and a
    default here would be a second copy of them to drift.

    A name reused in one family shows up as several origins; the magnitude
    belongs to whichever fits, so ONE fitting candidate clears the record and
    only a statement that fits none is reported — against the closest.
    """
    origins = collect_origins(facts, origin=origin, links=links, identity=identity)
    out: list[Disagreement] = []

    for record in facts.records():
        key_of = identity(record)
        for a in record.of(quantity):
            key = key_of(a.subject)
            asserted_at = _as_date(a.as_of.midpoint)
            span = bounds(a.age)
            if key is None or asserted_at is None or span is None:
                continue
            kin = _kin_of(record, a.subject, links)
            kin_keys = [k for p in kin if (k := key_of(p)) is not None]
            if not kin_keys:
                continue
            low, high = span

            candidates = [o for o in origins
                          if matches(o.key, key)
                          and any(matches(kk, ok) for kk in kin_keys for ok in o.kin)
                          and o.at <= asserted_at]
            if not candidates:
                continue

            def gap(o: Origin, _lo: float = low, _hi: float = high,
                    _at: date = asserted_at) -> float:
                elapsed = (_at - o.at).days
                return max(0.0, _lo - elapsed, elapsed - _hi)

            candidates.sort(key=gap)
            best = candidates[0]
            elapsed = float((asserted_at - best.at).days)
            allowed = max(tolerance_days, tolerance_fraction * low)
            if gap(best) <= allowed or gap(best) < min_gap_days:
                continue

            # A family that already gave the name twice is the wrong place to
            # argue from arithmetic, and a magnitude an order of magnitude off
            # is not a misread digit at all — both stay in the report, both
            # stop being the same claim as one made on an only child.
            reused = len(candidates) > 1
            namesake = elapsed > high * namesake_ratio
            out.append(Disagreement(
                subject=a.subject, subject_key=key,
                kin_key=kin_keys[0] if kin_keys else None,
                cite=a.cite, origin=best, stated=a.age,
                stated_low=low, stated_high=high, elapsed=elapsed,
                gap=gap(best), confidence="LOW" if (reused or namesake) else "HIGH"))

    out.sort(key=lambda d: (-d.gap, d.cite.sort_key))
    return out
