#!/usr/bin/env python3
"""Flag a canonical parent whose age at a child's birth is implausible.

Whole-village analog of TWO Geni tree inconsistencies — «Person had a child at
very old age» (too OLD) and «Ребёнок родился в слишком раннем возрасте» (too
YOUNG). Both are the same computation (parent age at each child's birth), so
they live in one check. Operates on the translated + consolidated domain model
(`GeniProfile` / `GeniUnion`) produced by
`verso.ru.pipeline.translate.translate_village` — the same network-free path
`generate_familio_tf` uses (no terraform plan, no Geni refresh).

For each canonical union, for each present partner, every child is attributed
to that partner; the parent's age at each child's birth is
`child.birth.year - parent.birth.year`. A `too_old` finding fires when a female
parent was older than `mother_max` (default 50) or a male / unknown-gender
parent older than `father_max` (default 70); a `too_young` finding fires below
`mother_min` / `father_min` (default 12). Unknown gender uses the lenient
father bounds to avoid false positives. Findings are aggregated per parent per
direction.

The finding is a SIGNAL, not a verdict. Too-old names two repairable ends — a
wrong/uncertain parent birth year, or an over-merge (two same-named people
fused into one canonical during consolidation). Too-young usually means a
wrong parent birth year or a mis-attached child (e.g. a «father at 9»).

A parent whose birth is a wide circa RANGE (an "unknown birth" placeholder,
e.g. 1836–1890) is tested only at the CHARITABLE end — the latest possible
birth for too-old, the earliest for too-young — so an unknown birth never
fabricates an extreme age. This removed 8 Маниловка and ~60 Горюхино false
positives that the naive range-start read produced.

Discovery is read-only.

Run:
    python3 -m verso.ru.consolidation.age_conflicts --village Маниловка
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from verso.ru.consolidation.profile_reading import (
    birth_is_approximate, birth_year, birth_year_latest, display_name, partner_refs)
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.messages import t

MOTHER_MAX_DEFAULT = 50
FATHER_MAX_DEFAULT = 70
# A parent younger than this at a child's birth is flagged as implausibly young
# (Geni's «Ребёнок родился в слишком раннем возрасте»). 12 is the biological
# floor; Geni's own line is 15 — raise with --mother-min/--father-min to match.
MOTHER_MIN_DEFAULT = 12
FATHER_MIN_DEFAULT = 12


@dataclass(frozen=True)
class ChildAge:
    res_name: str
    name: str
    birth_year: int
    age: int


@dataclass(frozen=True)
class AgeConflict:
    parent: str
    parent_name: str
    parent_birth_year: int
    approximate: bool
    role: str  # "mother" | "father" | "parent"
    children: tuple[ChildAge, ...]
    direction: str = "too_old"  # "too_old" | "too_young"

    @property
    def max_age(self) -> int:
        return max(c.age for c in self.children)

    @property
    def min_age(self) -> int:
        return min(c.age for c in self.children)


def find_age_conflicts(
        profiles: dict[str, GeniProfile],
        unions: dict[str, object],
        resolve,
        *,
        mother_max: int = MOTHER_MAX_DEFAULT,
        father_max: int = FATHER_MAX_DEFAULT,
        mother_min: int = MOTHER_MIN_DEFAULT,
        father_min: int = FATHER_MIN_DEFAULT,
) -> list[AgeConflict]:
    """Parents whose age at a child's birth is outside the plausible range.

    Flags a parent who was too OLD (age > mother_max / father_max) — Geni's
    «Person had a child at very old age» — or too YOUNG (age < mother_min /
    father_min) — Geni's «Ребёнок родился в слишком раннем возрасте». Unknown
    gender uses the lenient father bounds.

    `resolve(ref)` normalises a union partner/child ref onto its canonical
    res_name; a resolved ref absent from `profiles` is external and skipped.
    Aggregates per parent per direction across all their unions. Findings are
    sorted worst-first: too-old (highest age) before too-young (lowest age).
    """
    # parent canonical res_name -> {child canonical res_name}
    parent_children: dict[str, set[str]] = {}
    for union in unions.values():
        child_names = {resolve(c) for c in (getattr(union, "children", None) or set())}
        for pref in partner_refs(union):
            pcanon = resolve(pref)
            if pcanon not in profiles:
                continue  # external / co-managed partner — no birth year we own
            bucket = parent_children.setdefault(pcanon, set())
            bucket.update(child_names)

    findings: list[AgeConflict] = []
    for parent_name, children in parent_children.items():
        parent = profiles[parent_name]
        p_early = birth_year(parent)          # range start — parent as OLD as possible
        p_late = birth_year_latest(parent)    # range end   — parent as YOUNG as possible
        if p_early is None or p_late is None:
            continue
        gender = (parent.gender or "").lower()
        if gender == "female":
            cmax, cmin, role = mother_max, mother_min, "mother"
        elif gender == "male":
            cmax, cmin, role = father_max, father_min, "father"
        else:
            cmax, cmin, role = father_max, father_min, "parent"  # unknown → lenient

        too_old: list[ChildAge] = []
        too_young: list[ChildAge] = []
        for cname in children:
            child = profiles.get(cname)
            if child is None:
                continue  # external child — no birth year we own
            c_early = birth_year(child)
            c_late = birth_year_latest(child)
            if c_early is None or c_late is None:
                continue
            # Flag only when the age is out of range at the CHARITABLE end —
            # BOTH profiles read in the direction that makes the age plausible,
            # so two wide ranges never fabricate an extreme age:
            #   too-old   → smallest age: child born as EARLY as possible,
            #               parent as LATE as possible;
            #   too-young → largest age:  child born as LATE as possible,
            #               parent as EARLY as possible.
            # Reading the child at its range START for both directions (as this
            # did before) makes every child with a wide estimate look older than
            # it can be shown to be: a godparent window [1854..1908] compared
            # against a mother's [1864..1892] produced a bogus age of -10.
            age_old = c_early - p_late
            age_young = c_late - p_early
            if age_old > cmax:
                too_old.append(ChildAge(res_name=cname, name=display_name(child),
                                        birth_year=c_early, age=age_old))
            elif age_young < cmin:
                too_young.append(ChildAge(res_name=cname, name=display_name(child),
                                          birth_year=c_late, age=age_young))

        # Report the birth year that produced the (conservative) ages: the
        # latest for too-old, the earliest for too-young — so «р. YYYY» is
        # consistent with the printed ages.
        for direction, flagged, p_report in (
                ("too_old", too_old, p_late),
                ("too_young", too_young, p_early)):
            if not flagged:
                continue
            flagged.sort(key=lambda c: c.age)
            findings.append(AgeConflict(
                parent=parent_name,
                parent_name=display_name(parent),
                parent_birth_year=p_report,
                approximate=birth_is_approximate(parent),
                direction=direction,
                role=role,
                children=tuple(flagged),
            ))

    # Worst-first: all too-old (highest age first) before all too-young
    # (lowest age first).
    findings.sort(key=lambda f: (0, -f.max_age) if f.direction == "too_old"
                  else (1, f.min_age))
    return findings


def _role(role: str) -> str:
    words = {"mother": t("consolidation.age_conflicts.role.mother"), "father": t("consolidation.age_conflicts.role.father"),
             "parent": t("consolidation.age_conflicts.role.parent")}
    return str(words[role]) if role in words else role


def _hint(direction: str) -> str:
    if direction == "too_old":
        return str(t("consolidation.age_conflicts.hint.too_old"))
    if direction == "too_young":
        return str(t("consolidation.age_conflicts.hint.too_young"))
    return ""


def _band(direction: str) -> str:
    if direction == "too_old":
        return str(t("consolidation.age_conflicts.band.too_old"))
    if direction == "too_young":
        return str(t("consolidation.age_conflicts.band.too_young"))
    return direction


def format_report(findings: list[AgeConflict]) -> str:
    if not findings:
        return ("age-conflicts: OK — 0 findings (no parent with an implausible "
                "age at a child's birth).")
    lines = [f"age-conflicts: {len(findings)} finding(s)\n"]
    for f in findings:
        approx = " (~circa)" if f.approximate else ""
        lines.append(str(t("consolidation.age_conflicts.parent", name=f.parent_name, born=f.parent_birth_year,
                           approx=approx, role=_role(f.role), children=len(f.children), min_age=f.min_age,
                           max_age=f.max_age, band=_band(f.direction))))
        for c in f.children:
            lines.append(str(t("consolidation.age_conflicts.child", name=c.name, born=c.birth_year, age=c.age)))
        lines.append(_hint(f.direction))
    return "\n".join(lines)


def findings_to_json(findings: list[AgeConflict]) -> str:
    payload = [
        {
            "parent": f.parent,
            "parent_name": f.parent_name,
            "parent_birth_year": f.parent_birth_year,
            "approximate": f.approximate,
            "direction": f.direction,
            "role": f.role,
            "min_age": f.min_age,
            "max_age": f.max_age,
            "children": [
                {"res_name": c.res_name, "name": c.name,
                 "birth_year": c.birth_year, "age": c.age}
                for c in f.children
            ],
        }
        for f in findings
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run(profiles, unions, resolve, *, mother_max, father_max,
        mother_min=MOTHER_MIN_DEFAULT, father_min=FATHER_MIN_DEFAULT, as_json):
    findings = find_age_conflicts(profiles, unions, resolve,
                                  mother_max=mother_max, father_max=father_max,
                                  mother_min=mother_min, father_min=father_min)
    text = findings_to_json(findings) if as_json else format_report(findings)
    return text, (1 if findings else 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag a parent whose age at a child's birth is implausible — "
                    "too old (Geni's «very old age») or too young (Geni's "
                    "«ребёнок родился в слишком раннем возрасте»).")  # i18n: content — Geni's own warning, quoted
    ap.add_argument("--village", default=".",
                    help="village dir (default: cwd)")
    ap.add_argument("--mother-max", type=int, default=MOTHER_MAX_DEFAULT,
                    help=f"max mother age at childbirth (default {MOTHER_MAX_DEFAULT})")
    ap.add_argument("--father-max", type=int, default=FATHER_MAX_DEFAULT,
                    help=f"max father/unknown age at childbirth (default {FATHER_MAX_DEFAULT})")
    ap.add_argument("--mother-min", type=int, default=MOTHER_MIN_DEFAULT,
                    help=f"min mother age at childbirth (default {MOTHER_MIN_DEFAULT})")
    ap.add_argument("--father-min", type=int, default=FATHER_MIN_DEFAULT,
                    help=f"min father/unknown age at childbirth (default {FATHER_MIN_DEFAULT})")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    from verso.ru.pipeline.translate import translate_village

    gen, _ = translate_village(Path(args.village))
    text, code = run(gen.canonical_profiles(), gen.canonical_unions(),
                     gen.resolve_canonical,
                     mother_max=args.mother_max, father_max=args.father_max,
                     mother_min=args.mother_min, father_min=args.father_min,
                     as_json=args.json)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
