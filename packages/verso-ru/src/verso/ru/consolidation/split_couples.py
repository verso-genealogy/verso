#!/usr/bin/env python3
"""Flag one couple spread over two or more unions held by DIFFERENT profiles.

A fifth discovery channel, and like `union_duplicates` a structural one. The
other four all look for a duplicate PERSON; this one looks for a duplicate
COUPLE, because there is a class of duplicate that no person-level channel can
see:

- **The census half.** A revision or census household builds its union from its
  own per-record stubs, so the census «Алексій Сидоровъ × Аксинья Петрова» and
  the metric-book «Алексій Сидоровъ × Ксенія Петрова» are two husbands AND two
  wives. `verso candidates --sweep` rates a pair HIGH only on a SHARED spouse — and
  the halves share none; `union-dups` looks for two children inside one union —
  and the children sit in two. Before the first apply of Глуповы Горы
  (2026-09-24) 63 of ~75 members of the 1897 census stood beside their metric
  counterparts while every channel reported nothing new; this scan found them
  as 34 split couples.
- **The half fold.** A wave folds the wife on the strength of the husband and
  leaves the husband as per-record stubs (or the reverse). The canonical side
  then shares a spouse with nobody but itself, and the stub side is just as
  invisible — a wife folded «мужем, а не отчеством» while the
  husband stayed two stubs.

The key is the couple, not the person: each partner is keyed by the BASE of the
given name (`verso.ru.naming.matching_base`, so Егоръ and Георгій are one man) plus
the father the patronymic names, read off names.csv
(`verso.ru.naming.father_name_for_patronymic`) and folded the same way — so
«Игнатиевна»/«Игнатьевна» and «Егоровна»/«Георгиевна» agree. Two unions whose
partners match on both keys are one couple written twice — unless the dates
say otherwise:

- **Generations.** A father and son of the same name who both married a woman
  of the same name and patronymic are a real pattern in a small parish. When
  every pair of halves is at least `--generation-gap` years apart (default 25)
  by their dated evidence — children's births and the wedding — they are read
  as namesake couples and retired.

Everything else is a CANDIDATE: a signal, not a verdict.
Fold a split couple as a COUPLE — both spouses, on ages from the wedding or
the baptisms — and let `union-dups` find the children once the parents share
one union.

Runs on the translated + consolidated domain model produced by
`verso.ru.pipeline.translate.translate_village`, like `union_duplicates` and
`age_conflicts`: no terraform plan, no Geni refresh, no network. Read-only
.

Run:
    python3 -m verso.ru.consolidation.split_couples --village "Глуповы Горы"
    verso split-couples --village "Глуповы Горы" [--all] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterable

from verso.ru.consolidation.profile_reading import birth_year, display_name, partner_refs
from verso.ru.gender import Gender
from verso.ru.naming import father_name_for_patronymic, matching_base
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.messages import t

# Two halves whose dated evidence stands this many years apart are read as two
# namesake couples of different generations, not one couple written twice. A
# woman's childbearing span is about that long, so one couple's children cannot
# be spread wider — and Глуповы Горы's section L already retired its "same
# spouse's name, 35+ years apart" pairs on the same argument.
GENERATION_GAP_DEFAULT = 25

VERDICT_CANDIDATE = "CANDIDATE"
VERDICT_GENERATIONS = "GENERATIONS"

# Letters the corpus spells two ways; folded so a pre-reform spelling that
# survived into a canonical cannot split a key.
_FOLD = str.maketrans({"ѳ": "ф", "і": "и", "ѣ": "е", "ѵ": "и", "ё": "е",  # i18n: content — the old letters folded
                       "й": "и", "ъ": None})  # i18n: content — the old letters folded

_GENDERS = {"male": Gender.MALE, "female": Gender.FEMALE}

PartnerKey = tuple[str, str]


def _fold(text: str | None) -> str:
    return (text or "").strip().lower().translate(_FOLD)


def patronymic_key(patronymic: str | None) -> str:
    """Who the patronymic names as father, as a comparison key.

    The father's given name comes from names.csv (`father_name_for_patronymic`)
    and is folded through `matching_base`, so «Игнатиевна» and «Игнатьевна»,
    «Егоровна» and «Георгиевна» agree, while «Алексеевна» and «Александровна»
    stay apart. A patronymic the table does not know is compared as written.
    Never written anywhere.
    """
    father = father_name_for_patronymic(patronymic)
    if father:
        return _fold(matching_base(father, Gender.MALE))
    return _fold(patronymic)


def partner_key(profile: GeniProfile) -> PartnerKey | None:
    """(given-name base, father key), or None when either is missing.

    A partner with no patronymic cannot be told from their namesakes, and a
    couple keyed on given names alone pairs half the parish.
    """
    given = (profile.first_name or "").strip()
    father = patronymic_key(profile.middle_name)
    if not given or not father:
        return None
    base = matching_base(given, _GENDERS.get((profile.gender or "").lower()))
    return _fold(base), father


@dataclass(frozen=True)
class Child:
    res_name: str
    name: str
    birth_year: int | None


@dataclass(frozen=True)
class Half:
    """One couple as ONE pair of profiles holds it — possibly across several
    unions (a marriage record, a census household, each birth's parents)."""
    partners: tuple[str, str]
    names: tuple[str, str]
    unions: tuple[str, ...]
    children: tuple[Child, ...]
    # The dated evidence of the couple being a couple: its children's births
    # and its weddings. None when nothing is dated.
    span: tuple[int, int] | None


@dataclass(frozen=True)
class SplitCouple:
    key: tuple[PartnerKey, PartnerKey]
    label: str
    halves: tuple[Half, ...]
    # Profiles present in more than one half: the side that WAS folded.
    shared: tuple[str, ...]
    verdict: str
    reason: str

    @property
    def is_candidate(self) -> bool:
        return self.verdict == VERDICT_CANDIDATE


def _distance(a: tuple[int, int] | None, b: tuple[int, int] | None) -> int | None:
    """Years between two spans at their closest, or None when either is undated."""
    if a is None or b is None:
        return None
    return max(0, max(a[0], b[0]) - min(a[1], b[1]))


def _classify(halves: Iterable[Half], shared: tuple[str, ...],
              generation_gap: int) -> tuple[str, str]:
    halves = list(halves)
    gaps = [_distance(a.span, b.span)
            for i, a in enumerate(halves) for b in halves[i + 1:]]
    if gaps and all(g is not None and g >= generation_gap for g in gaps):
        closest = min(g for g in gaps if g is not None)
        return (VERDICT_GENERATIONS,
                str(t("consolidation.split_couples.generations", closest=closest)))
    if shared:
        return (VERDICT_CANDIDATE,
                str(t("consolidation.split_couples.half_fold", shared=", ".join(shared))))
    return (VERDICT_CANDIDATE,
            str(t("consolidation.split_couples.no_shared")))


def _span(years: Iterable[int | None]) -> tuple[int, int] | None:
    dated = [y for y in years if y is not None]
    return (min(dated), max(dated)) if dated else None


def find_split_couples(
        profiles: dict[str, GeniProfile],
        unions: dict[str, Any],
        resolve: Callable[[str], str],
        *,
        generation_gap: int = GENERATION_GAP_DEFAULT,
) -> list[SplitCouple]:
    """Couples whose two partners match on name keys across 2+ profile pairs.

    `resolve(ref)` normalises a union partner/child ref onto its canonical
    res_name; a resolved ref absent from `profiles` is external and its union
    skipped. Only two-partner unions are read — a one-parent union (a death
    record's father) names no couple. Candidates first, then by label.
    """
    # couple key → (partner pair) → accumulated unions / children / years
    groups: dict[tuple[PartnerKey, PartnerKey], dict[tuple[str, str], dict[str, Any]]] = \
        defaultdict(dict)
    for union_name, union in sorted(unions.items()):
        refs = partner_refs(union)
        if len(refs) != 2:
            continue
        sides = []
        for ref in refs:
            canon = resolve(ref)
            profile = profiles.get(canon)
            key = partner_key(profile) if profile is not None else None
            if key is None:
                break
            sides.append((key, canon))
        if len(sides) != 2 or sides[0][1] == sides[1][1]:
            continue
        sides.sort()
        couple = (sides[0][0], sides[1][0])
        pair = (sides[0][1], sides[1][1])
        acc = groups[couple].setdefault(
            pair, {"unions": set(), "children": {}, "years": []})
        acc["unions"].add(union_name)
        marriage = getattr(union, "marriage", None)
        if marriage is not None and getattr(marriage, "date", None) is not None:
            acc["years"].append(marriage.date.year)
        for ref in getattr(union, "children", None) or set():
            canon = resolve(ref)
            child = profiles.get(canon)
            if child is None:
                continue
            year = birth_year(child)
            acc["children"][canon] = Child(canon, display_name(child), year)
            acc["years"].append(year)

    found: list[SplitCouple] = []
    for couple, pairs in groups.items():
        if len(pairs) < 2:
            continue
        halves = tuple(
            Half(partners=pair,
                 names=(display_name(profiles[pair[0]]), display_name(profiles[pair[1]])),
                 unions=tuple(sorted(acc["unions"])),
                 children=tuple(sorted(acc["children"].values(),
                                       key=lambda c: (c.birth_year or 0, c.res_name))),
                 span=_span(acc["years"]))
            for pair, acc in sorted(pairs.items()))
        counts: dict[str, int] = defaultdict(int)
        for h in halves:
            for p in set(h.partners):
                counts[p] += 1
        shared = tuple(sorted(p for p, n in counts.items() if n > 1))
        verdict, reason = _classify(halves, shared, generation_gap)
        first = profiles[halves[0].partners[0]], profiles[halves[0].partners[1]]
        label = " × ".join(f"{p.first_name} {p.middle_name}".strip() for p in first)
        found.append(SplitCouple(couple, label, halves, shared, verdict, reason))
    found.sort(key=lambda s: (not s.is_candidate, s.label, s.key))
    return found


def _group_lines(s: SplitCouple, *, verdict: bool) -> list[str]:
    head = str(t("consolidation.split_couples.group", label=s.label, halves=len(s.halves)))
    lines = ["", f"{head}  [{s.verdict}]" if verdict else head, f"    {s.reason}"]
    for h in s.halves:
        span = f"{h.span[0]}–{h.span[1]}" if h.span else str(t("consolidation.split_couples.no_dates"))
        lines.append(f"    {h.partners[0]}  ×  {h.partners[1]}   ({span})")
        for c in h.children:
            born = c.birth_year if c.birth_year is not None else "?"
            lines.append(str(t("consolidation.split_couples.child", born=born, name=c.name, res_name=c.res_name)))
    return lines


def format_report(found: list[SplitCouple], *, all_groups: bool = False) -> str:
    """The candidates; with `all_groups`, also the groups the generation guard
    retired, each with its reason."""
    candidates = [s for s in found if s.is_candidate]
    retired = [s for s in found if not s.is_candidate]
    half_folds = sum(1 for s in candidates if s.shared)
    lines = [str(t("consolidation.split_couples.head", couples=len(found), candidates=len(candidates),
                   half_folds=half_folds, unshared=len(candidates) - half_folds, retired=len(retired)))]
    if not candidates:
        lines.append(str(t("consolidation.no_candidates")))
    else:
        lines.append("")
        lines.append(str(t("consolidation.split_couples.signal")))
        for s in candidates:
            lines += _group_lines(s, verdict=False)
    if all_groups and retired:
        lines.append("")
        lines.append(str(t("consolidation.split_couples.retired")))
        for s in retired:
            lines += _group_lines(s, verdict=True)
    return "\n".join(lines)


def findings_to_json(found: list[SplitCouple]) -> str:
    payload = [
        {
            "couple": s.label,
            "key": [list(k) for k in s.key],
            "verdict": s.verdict,
            "reason": s.reason,
            "shared": list(s.shared),
            "halves": [
                {
                    "partners": list(h.partners),
                    "names": list(h.names),
                    "unions": list(h.unions),
                    "span": list(h.span) if h.span else None,
                    "children": [
                        {"res_name": c.res_name, "name": c.name,
                         "birth_year": c.birth_year}
                        for c in h.children
                    ],
                }
                for h in s.halves
            ],
        }
        for s in found
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run(
        profiles: dict[str, GeniProfile],
        unions: dict[str, Any],
        resolve: Callable[[str], str],
        *,
        generation_gap: int = GENERATION_GAP_DEFAULT,
        as_json: bool = False,
        all_groups: bool = False,
) -> tuple[str, int]:
    found = find_split_couples(profiles, unions, resolve,
                               generation_gap=generation_gap)
    # JSON is machine output and always carries every group; `all_groups` is
    # about what a human reads.
    text = findings_to_json(found) if as_json \
        else format_report(found, all_groups=all_groups)
    return text, (1 if any(s.is_candidate for s in found) else 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag one couple spread over several unions held by "
                    "different profiles — a census household beside its metric "
                    "twin, or a half-done fold.")
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--generation-gap", type=int, default=GENERATION_GAP_DEFAULT,
                    help="halves this many years apart are read as namesake "
                         f"couples of different generations (default {GENERATION_GAP_DEFAULT})")
    ap.add_argument("--all", action="store_true", dest="all_groups",
                    help="include the groups the generation guard retired")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    from verso.ru.pipeline.translate import translate_village

    gen, _ = translate_village(Path(args.village))
    text, code = run(gen.canonical_profiles(), gen.canonical_unions(),
                     gen.resolve_canonical,
                     generation_gap=args.generation_gap, as_json=args.json,
                     all_groups=args.all_groups)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
