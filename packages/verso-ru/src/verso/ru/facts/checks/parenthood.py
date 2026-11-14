"""A child the parent's records cannot have — `check=posthumous-birth` / `check=children-span`.

From Gramps Verify (DeadParent, LargeChildrenSpan), asked of the canonical a
birth record's parent was folded into: the over-merge signals no other channel
sends. `age-conflicts` needs the parent's birth, and most mothers of the books
have none; these two need only the children and the parent's death.

* **posthumous-birth.** A child born after its mother's death, or more than
  `FATHER_DAYS` after its father's (the longest pregnancy the law allowed a
  posthumous child). The parent's death is the LATEST its records allow — a
  told year read at `date-order`'s slack — so a fold whose records disagree on
  the death is judged charitably. Measured 2026-09-30: fathers 3, all within
  the limit (194, 4 and 4 days: posthumous children, not errors); mothers 1 —
  a child christened 824 days after her burial, in a knot `father-claims`
  already reports.
* **children-span.** A mother whose children's births lie more than
  `MOTHER_SPAN_YEARS` apart — longer than a woman bears. The corpus holds no
  break to measure against: its 400 mothers of two children or more run
  continuously to 26.5 years (one mother of four children) — so the check
  finds nothing today and stands guard over the next
  fold. Fathers are not asked: a widower marries again, and their spans run
  on to 33 years with nothing to separate a second wife from a second man.
"""
from __future__ import annotations

from dataclasses import dataclass

from verso.ru.church_calendar.julian import JulianDate, day_number, from_jdn
from verso.ru.facts.checks.dates import as_read
from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import AssertionSet, BaptizedOn, BornOn, BuriedOn, Citation, DiedOn, ParentOf
from verso.ru.facts.projection import canonical_name
from verso.ru.facts.rules.disagreement import held

#: How long after the father's death a child may still be his: 294 days, the
#: posthumous-birth limit Gramps uses.
FATHER_DAYS = 294
#: A mother's children born further apart than this are two mothers.
MOTHER_SPAN_YEARS = 28.0
#: … and past this, no reading of the dates saves the fold.
MOTHER_SPAN_HIGH_YEARS = 30.0
_DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class PosthumousFinding:
    """A child born `days` after the parent's last possible death, beyond what
    the parent's role allows."""
    parent: str
    role: str  # "father" or "mother"
    child_cite: Citation
    born: JulianDate
    died: JulianDate
    death_cite: Citation
    days: int

    @property
    def confidence(self) -> str:
        allowed = FATHER_DAYS if self.role == "father" else 0
        return "HIGH" if self.days > allowed + 30 else "LOW"


@dataclass(frozen=True)
class SpanFinding:
    """A mother whose children's births span `years`."""
    parent: str
    first: tuple[JulianDate, Citation]
    last: tuple[JulianDate, Citation]
    children: int
    years: float

    @property
    def confidence(self) -> str:
        return "HIGH" if self.years > MOTHER_SPAN_HIGH_YEARS else "LOW"


def _child_day(record_born: tuple[BornOn, ...],
               record_baptized: tuple[BaptizedOn, ...]) -> tuple[int, Citation] | None:
    for claim in (*record_born, *record_baptized):
        if claim.date.day is not None and (n := day_number(claim.date.earliest)) is not None:
            return n, claim.cite
    return None


def _births_by_parent(facts: AssertionSet, identity: Identity
                      ) -> dict[tuple[str, IdentityKey], dict[tuple[str, str, int, str, int],
                                                              tuple[int, Citation]]]:
    """Per (role, parent canonical), each birth record's child day."""
    out: dict[tuple[str, IdentityKey], dict[tuple[str, str, int, str, int],
                                            tuple[int, Citation]]] = {}
    for record in facts.records():
        born, baptized = record.of(BornOn), record.of(BaptizedOn)
        dated = born or baptized
        if not dated or dated[0].cite.record_kind != "birth":
            continue
        child = _child_day(born, baptized)
        if child is None:
            continue
        who = identity(record)
        for parent in record.of(ParentOf):
            role = parent.cite.locator
            key = who(parent.subject)
            if key is None or role not in ("father", "mother"):
                continue
            out.setdefault((role, key), {})[parent.cite.record_id] = child
    return out


def _last_death(key: IdentityKey, deaths: dict[IdentityKey, tuple[DiedOn, ...]],
                burials: dict[IdentityKey, tuple[BuriedOn, ...]]
                ) -> tuple[int, Citation] | None:
    """The latest day the parent's records allow for the death — the burial
    when no death is dated."""
    claims = deaths.get(key, ()) or burials.get(key, ())
    ends = [(n, c.cite) for c in claims
            if (latest := as_read(c.date).latest) is not None
            and (n := day_number(latest)) is not None]
    return max(ends, key=lambda t: t[0]) if ends else None


def posthumous_births(facts: AssertionSet, identity: Identity) -> list[PosthumousFinding]:
    deaths = held(facts, kind=DiedOn, identity=identity)
    burials = held(facts, kind=BuriedOn, identity=identity)
    found: list[PosthumousFinding] = []
    for (role, key), children in _births_by_parent(facts, identity).items():
        end = _last_death(key, deaths, burials)
        if end is None:
            continue
        allowed = FATHER_DAYS if role == "father" else 0
        for child_day, cite in children.values():
            days = child_day - end[0]
            if days > allowed:
                found.append(PosthumousFinding(
                    parent=canonical_name(key) or "", role=role, child_cite=cite,
                    born=from_jdn(child_day), died=from_jdn(end[0]), death_cite=end[1],
                    days=days))
    found.sort(key=lambda f: (f.confidence != "HIGH", -f.days, f.parent))
    return found


def children_spans(facts: AssertionSet, identity: Identity) -> list[SpanFinding]:
    found: list[SpanFinding] = []
    for (role, key), children in _births_by_parent(facts, identity).items():
        if role != "mother" or len(children) < 2:
            continue
        first = min(children.values(), key=lambda t: t[0])
        last = max(children.values(), key=lambda t: t[0])
        years = (last[0] - first[0]) / _DAYS_PER_YEAR
        if years > MOTHER_SPAN_YEARS:
            found.append(SpanFinding(
                parent=canonical_name(key) or "", children=len(children),
                first=(from_jdn(first[0]), first[1]), last=(from_jdn(last[0]), last[1]),
                years=round(years, 1)))
    found.sort(key=lambda f: (f.confidence != "HIGH", -f.years, f.parent))
    return found
