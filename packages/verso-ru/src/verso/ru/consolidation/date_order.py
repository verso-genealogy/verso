#!/usr/bin/env python3
"""Flag a canonical profile whose christening/death/burial is dated before an
earlier life event — whole-tree analog of Geni's «Event occurred before birth
date» inconsistency.

Per-profile sibling of `age_conflicts`: same network-free `translate_village`
→ `canonical_profiles()` input, but compares event dates WITHIN one profile.
The motivating case is a December birth christened in early January whose DSL
record omits `k_year=`, so the baptism defaults to the birth year and lands in
January BEFORE the December birth (christening 1913-01-01 <
birth 1913-12-31). The fix is almost always a local
DSL edit, not an over-merge. Discovery is read-only.

It reads the TREE on purpose: the dates a canonical carries after the fold,
config overrides and derived estimates are what Geni checks. The records'
own claims are `verso facts --check date-order` — including two records
of one canonical that disagree, which a folded profile cannot show.

Run:
    python3 -m verso.ru.consolidation.date_order --village "Нижняя Яичница"
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from verso.ru.consolidation.profile_reading import display_name
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.messages import t


def _earliest(d: GeniDate | None):
    if d is None or d.year is None:
        return None
    return (d.year, d.month or 1, d.day or 1)


def _latest(d: GeniDate | None):
    if d is None or d.year is None:
        return None
    return (d.year, d.month or 12, d.day or 31)


def definitely_before(a: GeniDate | None, b: GeniDate | None) -> bool:
    """True iff date `a` lies entirely before date `b` (non-overlapping
    intervals). Uncomparable (missing year) → False, so partial dates never
    produce a false positive."""
    la, eb = _latest(a), _earliest(b)
    return la is not None and eb is not None and la < eb


@dataclass(frozen=True)
class OrderViolation:
    kind: str
    event: str
    event_date: tuple[int, int | None, int | None]
    reference: str
    reference_date: tuple[int, int | None, int | None]


@dataclass(frozen=True)
class DateOrderConflict:
    res_name: str
    name: str
    violations: tuple[OrderViolation, ...]


def _date_tuple(d: GeniDate | None) -> tuple[int, int | None, int | None]:
    """(year, month, day) of a date already known to carry a year — every call
    site is guarded by a `definitely_before(...)` that guarantees it."""
    assert d is not None and d.year is not None
    return (d.year, d.month, d.day)


def find_date_order_conflicts(profiles: dict[str, GeniProfile]) -> list[DateOrderConflict]:
    findings: list[DateOrderConflict] = []
    for res_name in sorted(profiles):
        p = profiles[res_name]
        # The record itself declares the SOURCE's dates inconsistent (a
        # christening the scribe dated before the birth). The transcription is
        # faithful and there is nothing to fix, so reporting it forever would
        # keep this check off CI for the sake of a slip made ~200 years ago.
        if getattr(p, "source_date_error", None):
            continue
        birth = p.birth.date if p.birth else None
        violations: list[OrderViolation] = []

        if p.baptism and definitely_before(p.baptism.date, birth):
            violations.append(OrderViolation(
                kind="baptism_before_birth", event=str(t("consolidation.event.baptism")),
                event_date=_date_tuple(p.baptism.date), reference=str(t("consolidation.event.birth")),
                reference_date=_date_tuple(birth)))

        if p.death and definitely_before(p.death.date, birth):
            violations.append(OrderViolation(
                kind="death_before_birth", event=str(t("consolidation.event.death")),
                event_date=_date_tuple(p.death.date), reference=str(t("consolidation.event.birth")),
                reference_date=_date_tuple(birth)))

        if p.burial:
            death = p.death.date if p.death else None
            if death is not None and definitely_before(p.burial.date, death):
                violations.append(OrderViolation(
                    kind="burial_before_death", event=str(t("consolidation.event.burial")),
                    event_date=_date_tuple(p.burial.date), reference=str(t("consolidation.event.death")),
                    reference_date=_date_tuple(death)))
            elif death is None and definitely_before(p.burial.date, birth):
                violations.append(OrderViolation(
                    kind="burial_before_birth", event=str(t("consolidation.event.burial")),
                    event_date=_date_tuple(p.burial.date), reference=str(t("consolidation.event.birth")),
                    reference_date=_date_tuple(birth)))

        if violations:
            findings.append(DateOrderConflict(
                res_name=res_name, name=display_name(p),
                violations=tuple(violations)))
    return findings


def _fmt(date) -> str:
    y, m, d = date
    parts = [str(y)]
    if m:
        parts.append(f"{m:02d}")
    if d:
        parts.append(f"{d:02d}")
    return "-".join(parts)


def format_report(findings: list[DateOrderConflict]) -> str:
    if not findings:
        return "date-conflicts: OK — 0 findings (no event dated before an earlier life event)."
    lines = [f"date-conflicts: {len(findings)} finding(s)\n"]
    for f in findings:
        lines.append(f"{f.name} ({f.res_name}):")
        for v in f.violations:
            lines.append(f"    {v.event} {_fmt(v.event_date)} < "
                         f"{v.reference} {_fmt(v.reference_date)}  [{v.kind}]")
        lines.append(str(t("consolidation.date_order.hint")))
    return "\n".join(lines)


def findings_to_json(findings: list[DateOrderConflict]) -> str:
    payload = [
        {
            "res_name": f.res_name,
            "name": f.name,
            "violations": [
                {"kind": v.kind, "event": v.event, "event_date": list(v.event_date),
                 "reference": v.reference, "reference_date": list(v.reference_date)}
                for v in f.violations
            ],
        }
        for f in findings
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run(profiles, *, as_json):
    findings = find_date_order_conflicts(profiles)
    text = findings_to_json(findings) if as_json else format_report(findings)
    return text, (1 if findings else 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag a profile whose christening/death/burial is dated "
                    "before an earlier life event (Geni's «event before birth»).")
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    from verso.ru.pipeline.translate import translate_village

    gen, _ = translate_village(Path(args.village))
    text, code = run(gen.canonical_profiles(), as_json=args.json)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
