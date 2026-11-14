#!/usr/bin/env python3
"""Flag a consolidated profile whose source records disagree about its ESTATE.

A cluster in `profiles_to_consolidate` asserts "all these records are one
person". Sometimes they are not, and the cheapest tell is the сословие: one
landlord's serf and another landlord's serf are two different people far more
often than they are one person the scribe mis-booked.

This is the systematic form of a check that was being done by hand during the
recurring-godparent sweep. It found a woman whose records split between two
landlords across seven entries — and, run over the whole village, it shows how
common the pattern is, which is exactly the context a single cluster lacks.

**A finding is a SIGNAL, not a verdict.** In some books the scribe's estate
attributions are demonstrably unreliable: a man who is one beyond doubt (the
same wife across four consecutive births) can be booked to FOUR different
landlords, one of them twice (Манилова → Плюшкина → Троекурова → Манилова).
So a finding means "read the records", not "unmerge". Before rejecting a
consolidation on estate grounds, test the same hypothesis against a person in
the same record series whose identity is NOT in question; if their estate
wanders too, the estate is noise here.

What is deliberately NOT a conflict:

* **ясачный → казённый.** Горюхино's population was reclassified from ясачные
  to казённые крестьяне in 1841; both map to one `state` estate.
* **экономический ↔ государственный.** Экономические крестьяне were the
  secularised church peasants, folded into the state peasantry long before our
  books; the word outlived the category, so Заманиловка's scribes write both for
  the same people and in no fixed order — «государственная» in the 1850 roll,
  «экономическая» at her burial in 1864. Kept apart, every one of Заманиловка's
  32 findings was this pair and nothing else.
* **Military-family and role descriptors** (солдатка, солдатская дочь, девица,
  вдова, женка, отрок, …). «Солдатка» describes a husband's service, not her
  fiscal estate, and a peasant woman legitimately becomes one mid-life — e.g.
  `tatjana_karpovna` is ясачная крестьянка in 1831/1837 and солдатка in
  1839/1841, one woman. These classify as UNKNOWN and never conflict.
* **Role variation inside one estate** (крестьянин / крестьянка / девка из
  крестьян / законная жена крестьянина помещика X) — same owner, same estate.

Only estate-bearing statuses are compared, and only when they disagree on the
estate axis: two different landlords, or a landlord against a state
(ясачный, казённый, экономический, государственный) peasant.

The statuses come from the records themselves — a `Titled` assertion per
appearance, placed on its canonical by the consolidation bridge, so every record
type is covered without the check knowing about any of them — and WHO conflicts
is decided by `verso.ru.facts.rules.disagreement`, the rule that knows neither which
two claims it compares nor why they cannot both hold. A line resting on a
revision member we reconstructed (`hidden=True`, not in the roll) is marked
«восстановлен». (Until 2026-09-25 the statuses could also be parsed out of the
consolidated profile's `about`, one «Титул/звание: …» line per folded record;
that reading found the same people on two successive states of the corpus and
was removed.)

Discovery is read-only.

Run:
    python3 -m verso.ru.consolidation.estate_conflicts --village Горюхино
    verso estate-conflicts --village Горюхино [--pairs] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verso.ru import corpus_data
from verso.ru.domain.estates import estate_of, family_root
from verso.ru.facts.checks.estates import estates_in_conflict
from verso.ru.facts.identity import Identity
from verso.ru.facts.model import AssertionSet, Derived, Titled
from verso.ru.facts.projection import canonical_name, consolidated_identity
from verso.ru.messages import t

@dataclass(frozen=True)
class SourceStatus:
    """One source record's stated status for this person."""

    source: str      # where it was read: DSL file, entry and лист
    role: str        # the slot the person fills there, e.g. "god_parent1"
    status: str      # how the record styles them, verbatim
    estate: str      # classified estate key
    year: int | None # the record's year, for chronological ordering


@dataclass(frozen=True)
class EstateConflict:
    """A canonical profile whose records disagree on the estate axis."""

    res_name: str
    name: str
    estates: tuple[str, ...]           # distinct estate keys, sorted
    records: tuple[SourceStatus, ...]  # every estate-bearing record, in order

    @property
    def landlord_count(self) -> int:
        return sum(1 for e in self.estates if e.startswith("landlord:"))


def _display_name(profile) -> str:
    parts = [getattr(profile, "first_name", None),
             getattr(profile, "middle_name", None),
             getattr(profile, "last_name", None)]
    return " ".join(p for p in parts if p) or "?"


def assemble(res_name: str, profile: object,
             rows: Iterable[SourceStatus]) -> EstateConflict:
    """One finding for a canonical profile, from the estate-bearing rows it
    rests on, in time order.

    Kept apart from the rule that decides WHO conflicts, so that whatever
    decided it, the report names the person and orders the evidence one way.
    """
    records = tuple(sorted(rows, key=lambda r: (r.year or 0, r.source)))
    return EstateConflict(res_name=res_name, name=_display_name(profile),
                          estates=tuple(sorted({r.estate for r in records})),
                          records=records)


def worst_first(findings: Iterable[EstateConflict]) -> list[EstateConflict]:
    """Most distinct estates first, then most records.

    Load-bearing beyond taste: `format_pairs` truncates to the top pairs by
    count, and among equal counts `Counter.most_common` keeps first-seen order —
    so this order decides WHICH pairs a `--pairs` report shows.
    """
    return sorted(findings,
                  key=lambda f: (-len(f.estates), -len(f.records), f.res_name))


def _estate_row(claim: Titled) -> SourceStatus:
    """One `Titled` as the row a report prints: where it was read, how the
    record styles the person, and the сословие that implies.

    The row names its source by the citation — file and entry — and not by
    the heading the translator writes into `about`: that heading is the
    translator's vocabulary, and a second copy of it here is the disease the
    facts layer exists to cure. A line resting on a member we reconstructed
    says so.
    """
    c = claim.cite
    page = str(t("consolidation.leaf", page=c.page)) if c.page else ""
    ours = str(t("consolidation.estate_conflicts.reconstructed")) if isinstance(claim.basis, Derived) else ""
    return SourceStatus(source=f"{c.source_file} №{c.record_num}{page}",
                        role=f"{c.locator}{ours}", status=claim.status,
                        estate=estate_of(claim.status) or "", year=c.year)


def estate_conflicts_of(facts: AssertionSet, identity: Identity,
                        profiles: dict[str, Any]) -> list[EstateConflict]:
    """Canonicals whose records style them into two сословия, from `Titled`.

    WHO conflicts is `verso.ru.facts.checks.estates`' to say (the disagreement
    rule over `Titled` twice); WHAT to print is every estate-bearing claim the
    person holds, one row each.
    """
    return worst_first(
        assemble(res_name, profiles.get(res_name), [_estate_row(c) for c in claims])
        for who, claims in estates_in_conflict(facts, identity).items()
        for res_name in (canonical_name(who) or "",))


def estate_findings(village_dir: Path) -> list[EstateConflict]:
    """`estate-conflicts`: one translation, the bridge, and the check."""
    from verso.ru.pipeline.facts import consolidated_facts

    facts, gen, slots = consolidated_facts(village_dir)
    return estate_conflicts_of(facts.believed(),
                               consolidated_identity(gen, slots.object_of),
                               gen.canonical_profiles())




def format_report(findings: list[EstateConflict]) -> str:
    if not findings:
        return ("estate-conflicts: OK — 0 findings (no consolidated profile "
                "mixes estates).")
    lines = [f"estate-conflicts: {len(findings)} finding(s)\n"]
    for f in findings:
        lines.append(str(t("consolidation.estate_conflicts.finding", name=f.name, res_name=f.res_name,
                           estates=t("counted.estates", count=len(f.estates)),
                           in_records=t("counted.in_records", count=len(f.records)))))
        for r in f.records:
            src = r.source or "?"
            role = f" · {r.role}" if r.role else ""
            lines.append(f"    {src}{role}\n        {r.status}   [{r.estate}]")
        lines.append(str(t("consolidation.estate_conflicts.hint")))
    return "\n".join(lines)


def findings_to_json(findings: list[EstateConflict]) -> str:
    return json.dumps([
        {
            "res_name": f.res_name,
            "name": f.name,
            "estates": list(f.estates),
            "landlord_count": f.landlord_count,
            "records": [
                {"source": r.source, "role": r.role, "status": r.status,
                 "estate": r.estate, "year": r.year}
                for r in f.records
            ],
        }
        for f in findings
    ], ensure_ascii=False, indent=2)


def format_pairs(findings: list[EstateConflict], limit: int = 30) -> str:
    """Rank the estate PAIRS that co-occur, worst first.

    A raw finding list is per-person and, in a village whose scribe is loose
    with estates, runs to hundreds of rows — too many to read. The same data
    keyed on the pair of estates collapses to a couple of dozen rows, each of
    which is one genealogical question about the landowning family («are these
    two spellings one owner?»). Answer a top row and hundreds of findings
    resolve at once via `[owner_aliases]` (corpus/estates.toml).
    """
    import collections
    pairs: collections.Counter[tuple[str, str]] = collections.Counter()
    for f in findings:
        for i, a in enumerate(f.estates):
            for b in f.estates[i + 1:]:
                pairs[(a, b)] += 1
    if not pairs:
        return "estate-conflicts: OK — 0 findings."
    lines = [f"estate-conflicts: {len(findings)} finding(s) over "
             f"{len(pairs)} distinct estate pair(s)\n",
             "profiles  flag  estate A  ✕  estate B"]
    for (a, b), n in pairs.most_common(limit):
        lines.append(f"{n:8}  {_pair_flag(a, b):4}  {a}  ✕  {b}")
    if len(pairs) > limit:
        lines.append(f"... and {len(pairs) - limit} more pair(s)")
    lines.append(
        "\nflags:\n"
        "  ALIAS  the two sides share a given name + patronymic — probably ONE owner\n"
        "         under maiden and married surnames. Confirm against the landowning\n"
        "         family, then add it to [owner_aliases] of corpus/estates.toml to retire every finding it\n"
        "         causes at once.\n"
        "  SAME   both sides are the same gentry surname — WEAK evidence. An estate\n"
        "         divided among relatives passes serfs between them legitimately\n"
        "         (dowry, inheritance, division), so one peasant appearing under two\n"
        "         owners of one family is ordinary, not a merge error.\n"
        "  ----   different landowning families — the STRONGEST form of this finding.")
    return "\n".join(lines)


def _owner_families(estate: str) -> set[str]:
    """Every gentry family a `landlord:` owner belongs to, as normalised stems.

    A married daughter belongs to TWO: the family named in her status (her
    husband's) and the one she was born into. Returning a set rather than one
    surname is what lets her pair as same-household with BOTH her brother and
    her husband — picking either surname alone mis-flags the other pair.
    """
    if not estate.startswith("landlord:"):
        return set()
    owner = estate[len("landlord:"):]
    parts = owner.split()
    families = {family_root(parts[-1])} if parts else set()
    if (maiden := corpus_data.estates().maiden_families.get(owner)):
        families.add(family_root(maiden))
    return families


def _owner_given_patr(estate: str) -> str | None:
    """Given name + patronymic of a `landlord:` estate, surname dropped."""
    if not estate.startswith("landlord:"):
        return None
    parts = estate[len("landlord:"):].split()
    return " ".join(parts[:-1]) if len(parts) > 1 else None


def _pair_flag(a: str, b: str) -> str:
    """Severity marker for an estate pair (see `format_pairs` legend)."""
    ga, gb = _owner_given_patr(a), _owner_given_patr(b)
    if ga and gb and ga == gb:
        return "ALIAS"
    if _owner_families(a) & _owner_families(b):
        return "SAME"
    return "----"


def render(findings: list[EstateConflict], *, as_json: bool,
           min_estates: int = 2, pairs: bool = False) -> tuple[str, int]:
    """The report for findings however they were found."""
    findings = [f for f in findings if len(f.estates) >= min_estates]
    if as_json:
        text = findings_to_json(findings)
    elif pairs:
        text = format_pairs(findings)
    else:
        text = format_report(findings)
    return text, (1 if findings else 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag consolidated profiles whose source records disagree "
                    "about the person's estate (сословие).")  # i18n: content — the word the help explains
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--min-estates", type=int, default=2,
                    help="report only profiles mixing at least this many "
                         "distinct estates (default 2)")
    ap.add_argument("--pairs", action="store_true",
                    help="summarise as ranked estate PAIRS instead of per-person "
                         "findings — the triage view")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    findings = estate_findings(Path(args.village))
    text, code = render(findings, as_json=args.json,
                        min_estates=args.min_estates, pairs=args.pairs)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
