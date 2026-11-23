#!/usr/bin/env python3
"""Flag two children of one couple born impossibly close together.

**Why it exists.** A burial gives an age, not a date, and the unit is often
left off — so most of what a deep year yields is a birth year *derived* by
subtraction. Nothing checks those. The one thing that does check them is the
family itself: a woman cannot bear two children five months apart, so an age
whose implied birth lands next to a recorded sibling has the wrong unit.

That is the argument this check automates, and it was made by hand while
reading a deep year. A boy is buried in February at a bare «4½». Read as months
he was born about October of the year before — and the same parents christen a
girl the following April. Five months apart is impossible, so the «4½» is
years. The reasoning is mechanical; only the reading was not.

Its sibling `death_age` compares a stated age against the birth record OF THE
SAME CHILD. This one compares it against the OTHER children, which is the only
evidence available when the child has no birth record of their own — the usual
case in the years before a sweep reaches them.

Read-only and network-free: it reads the DSL, not terraform state.

Run:
    python3 -m verso.ru.consolidation.sibling_spacing --village "Глуповы Горы"
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from verso.ru.ages import DAYS_PER_YEAR, age_bounds
from verso.ru.consolidation.death_age import (
    BirthFact, PersonKey, as_date, collect_births, load_village_records, parents_named, person_key)
from verso.ru.messages import t

#: Shortest interval between two live births to one mother that the records can
#: mean literally. Nine months is the biological floor; the corpus is full of
#: couples at eleven and twelve, so anything under this is a reading error or a
#: pair of twins rather than a tight sequence.
DEFAULT_MIN_GAP_DAYS = 270

#: Two children entered on the same day (or a day apart) are twins — the books
#: record them as consecutive numbers, and the corpus holds several pairs.
TWIN_DAYS = 2


@dataclass(frozen=True)
class Sibling:
    """A child of a known couple, whether the date is recorded or derived."""
    # The scribe's spelling, for the report. NEVER compare two siblings on it:
    # one boy is «Иванъ» in his birth record and «Иоаннъ» in his burial, and
    # comparing written forms made him two children born the same day. Identity
    # goes through `key`, which is folded to the base name.
    name: str
    key: PersonKey
    low: date              # earliest the birth can be
    high: date             # latest it can be (equal to `low` when recorded)
    derived: bool          # True when the date comes from a burial age
    year: int
    record_num: str
    source: str

    @property
    def when(self) -> str:
        if not self.derived:
            return self.low.isoformat()
        return f"{self.low.isoformat()}…{self.high.isoformat()}"


@dataclass(frozen=True)
class SpacingConflict:
    parents: str
    a: Sibling
    b: Sibling
    gap_days: int
    hint: str


def _parents_key(*keys: PersonKey | None) -> tuple[PersonKey, ...]:
    return tuple(k for k in keys if k is not None)


def _label(keys: tuple[PersonKey, ...]) -> str:
    return " + ".join(
        " ".join(bit for bit in (k.display, k.patronymic, k.surname) if bit).title()
        for k in keys)


def identifies_a_household(parents: tuple[PersonKey, ...]) -> bool:
    """Whether a parent key names ONE couple rather than a common name.

    A father entered alone and without a surname — «Василий Григорьевичъ» — is
    not a household: the early Заманиловка books hold several of him, and folding
    them together invents siblings three days apart. Требуется либо оба
    родителя, либо фамилия.
    """
    if len(parents) >= 2:
        return True
    return bool(parents) and bool(parents[0].surname)


def recorded_siblings(births: list[BirthFact]) -> dict[tuple[PersonKey, ...], list[Sibling]]:
    by_parents: dict[tuple[PersonKey, ...], list[Sibling]] = {}
    for b in births:
        if not identifies_a_household(b.parents):
            continue
        by_parents.setdefault(b.parents, []).append(Sibling(
            name=b.key.display, key=b.key, low=b.born, high=b.born, derived=False,
            year=b.year, record_num=b.record_num, source=b.source))
    return by_parents


def derived_siblings(death_record_sets) -> list[tuple[tuple[PersonKey, ...], Sibling]]:
    """Children whose birth is known only by subtraction from a burial age."""
    out: list[tuple[tuple[PersonKey, ...], Sibling]] = []
    for records, source in death_record_sets:
        for rec in records.records:
            # Same contract as death-age-check: a declared source_age_error
            # says the age has been re-read on the scan and the disagreement
            # argued out, so the birth this check would derive from it is not
            # the corpus's claim about a sibling.
            if getattr(rec, "source_age_error", None):
                continue
            child = person_key(getattr(rec, "deceased", None))
            if child is None:
                continue
            parents = _parents_key(*(person_key(r.person) for r in parents_named(rec)))
            if not parents:
                continue
            year = getattr(rec, "year", None) or records.year
            died = as_date(year, getattr(rec, "d_month", None), getattr(rec, "d_day", None))
            bounds = age_bounds(getattr(rec, "age", None))
            if died is None or bounds is None:
                continue
            low_days, high_days = bounds
            # The age is a floor plus the width of its smallest unit, so the
            # birth is an interval: subtracting the WIDER age gives the earlier
            # bound. Only a collision that survives the whole interval counts.
            out.append((parents, Sibling(
                name=child.display, key=child,
                low=died - timedelta(days=high_days),
                high=died - timedelta(days=low_days),
                derived=True, year=year,
                record_num=str(getattr(rec, "record_num", "") or "?"), source=source)))
    return out


def max_separation(a: Sibling, b: Sibling) -> int:
    """The FURTHEST apart the two births can be placed, in days.

    A derived birth is an interval, and the question is whether the records can
    be read consistently at all — so the placement that matters is the one most
    favourable to THEM. Measuring the closest approach instead makes every pair
    of vague intervals collide: it is what produced 508 findings on Заманиловка
    before this was fixed.
    """
    return max((b.high - a.low).days, (a.high - b.low).days)


# How far outside a couple's RECORDED births their real childbearing may reach.
# The records are a sample, not a roster — a child who died before the sweep
# reached their birth year has no birth record at all, and whole years of a
# дело go unread — so the true span is wider than the one the corpus holds.
# Three years is a birth interval or two on each side: wide enough not to
# reject a real child, narrow enough that an 1859 couple stops competing for a
# 1905 burial.
CHILDBEARING_SLACK = timedelta(days=3 * 365)


def bears_children_around(children: list[Sibling], sib: Sibling) -> bool:
    """Does this couple's recorded childbearing overlap `sib`'s possible birth?

    Used only to break a tie between several couples a one-parent burial
    matches. A burial names one parent, and the same man can head two
    households — successive wives, or a grandson carrying his grandfather's
    name — so the dates are the only thing left to tell them apart.
    """
    if not children:
        return False
    low = min(c.low for c in children) - CHILDBEARING_SLACK
    high = max(c.high for c in children) + CHILDBEARING_SLACK
    return sib.low <= high and sib.high >= low


def find_spacing_conflicts(
        birth_record_sets,
        death_record_sets,
        *,
        min_gap_days: int = DEFAULT_MIN_GAP_DAYS,
) -> list[SpacingConflict]:
    families = recorded_siblings(collect_births(birth_record_sets))
    for parents, sib in derived_siblings(death_record_sets):
        if not identifies_a_household(parents):
            continue
        # Attach a derived child to a family only when the corpus already knows
        # that couple by a birth; a lone burial names no siblings to compare.
        #
        # A burial names ONE parent, so a partial key can match several known
        # couples — the same man's two wives, or
        # the same name two generations apart. PersonKey compares a surname
        # only when both sides carry one, so a burial naming a father with a
        # surname matched the surname-less father of a birth 46 years earlier,
        # and twins were filed under a couple from two generations back. Taking
        # the first match made that silent and arbitrary.
        #
        # Which couple it is cannot be known from the record, so when more than
        # one matches, attach to NONE — the same way an ambiguous stripped key
        # is treated as a miss in `Consolidation._stripped_index`. A missed
        # finding costs a signal; a wrong one costs an afternoon.
        matched = [(known, children) for known, children in families.items()
                   if all(any(p.matches(k) for k in known) for p in parents)]
        if len(matched) > 1:
            matched = [m for m in matched if bears_children_around(m[1], sib)]
        if len(matched) != 1:
            continue
        children = matched[0][1]
        # A child who already has a birth record in this family needs no
        # date derived from their burial — the recorded one is better, and
        # the derived one would collide with their own twin. That is the
        # twin case: one date exact and one rounded out of a burial age,
        # 38 days apart and not a finding.
        if any(c.key.matches(sib.key) and not c.derived for c in children):
            continue
        children.append(sib)

    findings: list[SpacingConflict] = []
    for parents, children in families.items():
        ordered = sorted(children, key=lambda c: (c.low, c.name))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if a.key.matches(b.key):
                    # The same child recorded twice — a birth and its own
                    # burial, or a name reused. `death_age` and `union_dups`
                    # own that question; arithmetic says nothing here.
                    continue
                gap = max_separation(a, b)
                if gap > min_gap_days:
                    continue
                if gap <= TWIN_DAYS and not (a.derived or b.derived):
                    continue  # twins, entered as consecutive numbers
                findings.append(SpacingConflict(
                    parents=_label(parents), a=a, b=b, gap_days=gap,
                    hint=_hint(a, b)))
    findings.sort(key=lambda f: (f.gap_days, f.parents))
    return findings


def _hint(a: Sibling, b: Sibling) -> str:
    derived = [s for s in (a, b) if s.derived]
    if not derived:
        return str(t("consolidation.sibling_spacing.hint.two_records"))
    if len(derived) == 2:
        return str(t("consolidation.sibling_spacing.hint.two_burials"))
    d = derived[0]
    unit = (str(t("consolidation.sibling_spacing.unit.years")) if d.high - d.low >= timedelta(days=DAYS_PER_YEAR * 0.9)
            else str(t("consolidation.sibling_spacing.unit.other")))
    return str(t("consolidation.sibling_spacing.hint.one_burial", name=d.name, unit=unit))


def format_report(findings: list[SpacingConflict], *, min_gap_days: int) -> str:
    if not findings:
        return (f"sibling-spacing: OK — 0 findings "
                f"(no two children of one couple within {min_gap_days} days).")
    lines = [f"sibling-spacing: {len(findings)} finding(s)\n"]
    for f in findings:
        lines.append(f"{f.parents}")
        for s in (f.a, f.b):
            mark = (str(t("consolidation.sibling_spacing.from_burial")) if s.derived
                    else str(t("consolidation.sibling_spacing.from_birth")))
            lines.append(f"    {s.name:<14} {s.when:<23} {mark}, "
                         f"{s.year} № {s.record_num} [{s.source}]")
        lines.append(str(t("consolidation.sibling_spacing.gap", days=f.gap_days, hint=f.hint)))
    lines.append(str(t("consolidation.sibling_spacing.twins")))
    return "\n".join(lines)


def findings_to_json(findings: list[SpacingConflict]) -> str:
    return json.dumps([
        {"parents": f.parents, "gap_days": f.gap_days, "hint": f.hint,
         "children": [{"name": s.name, "from": s.low.isoformat(), "to": s.high.isoformat(),
                       "derived": s.derived, "year": s.year, "record": s.record_num,
                       "source": s.source} for s in (f.a, f.b)]}
        for f in findings], ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag two children of one couple born impossibly close — the "
                    "check on a birth year derived from a burial age.")
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--min-gap-days", type=int, default=DEFAULT_MIN_GAP_DAYS,
                    help=f"shortest believable interval (default {DEFAULT_MIN_GAP_DAYS})")
    args = ap.parse_args(argv)

    births, deaths = load_village_records(Path(args.village))
    findings = find_spacing_conflicts(births, deaths, min_gap_days=args.min_gap_days)
    print(findings_to_json(findings) if args.json
          else format_report(findings, min_gap_days=args.min_gap_days))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
