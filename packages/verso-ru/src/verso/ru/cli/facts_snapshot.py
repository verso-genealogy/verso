#!/usr/bin/env python3
"""The findings snapshot — a ratchet on the checks that read the assertions.

`<village>/facts_findings.tsv` holds the findings count of every check that
reads the assertions, taken from ONE translation of the village; CI runs
`--check` on every affected village. A count that moves has to be accepted in
the commit that moved it.

    python3 -m verso.ru.cli.facts_snapshot --village Горюхино           # write
    python3 -m verso.ru.cli.facts_snapshot --village Горюхино --check   # CI

Its own module because it is the one place that orchestrates every check —
the facts CLI's and the consolidation modules' alike — and neither of those
should import the other to make that possible.
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from verso.ru.cli.facts import kin_error_notes, village_path
from verso.ru.consolidation.death_age import find_death_age_conflicts, load_village_records
from verso.ru.consolidation.estate_conflicts import estate_conflicts_of
from verso.ru.consolidation.name_variants import loose_keys, name_variants_channel
from verso.ru.consolidation.reconcile import household_ordered_lists
from verso.ru.consolidation.union_duplicates import find_union_duplicates
from verso.ru.facts.checks.births import birth_claims_of
from verso.ru.facts.checks.dates import date_order_findings, unplaced_within
from verso.ru.facts.checks.deaths import death_claims
from verso.ru.facts.checks.fathers import father_findings
from verso.ru.facts.checks.lags import baptism_lags, burial_lags
from verso.ru.facts.checks.household_ages import household_age_findings
from verso.ru.facts.checks.parent_ages import parent_age_drift, parent_age_findings
from verso.ru.facts.checks.parenthood import children_spans, posthumous_births
from verso.ru.facts.checks.lives import Lives, households_of_canonicals, lives_of_canonicals
from verso.ru.facts.checks.reach import identity_reach
from verso.ru.facts.checks.reconcile import match, reconcile
from verso.ru.facts.checks.wedding_ages import wedding_age_findings
from verso.ru.facts.checks.wedding_calendar import wedding_calendar_findings
from verso.ru.facts.identity import kin_identity
from verso.ru.facts.projection import LooseIndex, consolidated_identity
from verso.ru.pipeline.facts import consolidated_facts, unpublished_kinds

SNAPSHOT_FILE = "facts_findings.tsv"

_SNAPSHOT_HEADER = """\
# Findings of the checks that read the assertions, on this village's records.
# CI fails when a count moves and this file does not: regenerate it with
#     verso facts-snapshot --village {village}
# and commit it WITH the change that moved it — a DSL edit, a fold, a check.
# A count that moves unexpectedly is the point: read the report before committing.
check\tfindings\thigh
"""


def snapshot_header(village_dir: Path) -> str:
    """The committed file's header: how to regenerate it, the village quoted for a shell."""
    return _SNAPSHOT_HEADER.format(village=shlex.quote(village_dir.name))


def findings_snapshot(village_dir: Path) -> str:
    """How many findings each facts-backed check holds on one village, from ONE
    translation.

    Parity between two implementations used to be measured by hand and
    recorded in commit messages, and a drift was found only when somebody
    happened to diff two runs (the namesake burial: Глуповы Горы 5 against
    3). A committed count turns every movement into a diff someone has to
    accept — a code change that moves one is visible in its own commit, and a
    DSL edit that moves one says so beside the edit.

    Counts, not reports: the reports are for reading, and a count is enough to
    say THAT something moved. `high` is `-` for a check that does not rank.
    """
    facts, gen, slots = consolidated_facts(village_dir)
    believed = facts.believed()
    identity = consolidated_identity(gen, slots.object_of)
    reach = identity_reach(facts, gen, slots, unpublished=unpublished_kinds())
    within, across = date_order_findings(facts, identity)
    # … and the entries of people the bridge places on nobody (a divorce's), asked alone: one a count.
    alone = {f.left.cite.record_id for f in unplaced_within(facts, identity)}
    births = birth_claims_of(believed, identity)
    households = households_of_canonicals(believed, identity)
    lives = lives_of_canonicals(believed, identity)
    groups = find_union_duplicates(
        gen.canonical_profiles(), gen.canonical_unions(), gen.resolve_canonical,
        households_of=lambda canon: households.get(canon, frozenset()),
        lives_of=lambda canon: lives.get(canon, Lives()))
    estates = [f for f in estate_conflicts_of(believed, identity,
                                              gen.canonical_profiles())
               if len(f.estates) >= 2]
    deaths = find_death_age_conflicts(*load_village_records(village_dir))
    reconciled = [r for r in reconcile(believed, identity, household_ordered_lists(gen))
                  if r.is_candidate]
    fathers = father_findings(believed, identity, kin_error_notes(gen))
    fathers_across = [f for f in fathers if f.across]
    two_deaths = death_claims(believed, identity)
    config = village_dir / "generate_config_names.py"
    loose = loose_keys(believed, identity, LooseIndex(
        gen, slots, config.read_text(encoding="utf-8") if config.is_file() else ""))
    variants = [r for r in match(believed, identity,
                                 name_variants_channel(lambda key: key in loose))
                if r.is_candidate]
    weddings = wedding_calendar_findings(believed)
    late_baptisms = baptism_lags(believed).findings
    late_burials = burial_lags(believed).findings
    posthumous = posthumous_births(believed, identity)
    spans = children_spans(believed, identity)
    wedding_ages = wedding_age_findings(believed).findings
    parent_ages = parent_age_findings(believed)
    household_ages = household_age_findings(believed)
    parent_drift = parent_age_drift(believed, pair=kin_identity(), folded=identity)

    rows: list[tuple[str, int, int | None]] = [
        ("baptism-lag", len(late_baptisms),
         sum(f.confidence == "HIGH" for f in late_baptisms)),
        ("birth-claims", len(births), sum(f.confidence == "HIGH" for f in births)),
        ("burial-lag", len(late_burials), sum(f.confidence == "HIGH" for f in late_burials)),
        ("children-span", len(spans), sum(f.confidence == "HIGH" for f in spans)),
        ("date-order-across", len(across), None),
        ("date-order-within", len(within) + len(alone), None),
        ("death-age", len(deaths), sum(f.confidence == "HIGH" for f in deaths)),
        ("death-claims", len(two_deaths), sum(f.confidence == "HIGH" for f in two_deaths)),
        ("estate-conflicts", len(estates), None),
        ("father-claims", len(fathers_across),
         sum(f.confidence == "HIGH" for f in fathers_across)),
        ("father-claims-within", sum(1 for f in fathers if f.within), None),
        ("household-ages", len(household_ages), sum(f.confidence == "HIGH" for f in household_ages)),
        ("identity-minted-twice", reach.minted_twice, None),
        ("identity-refused-beyond-clergy", reach.refused_beyond_clergy, None),
        ("identity-surplus", reach.surplus, None),
        ("name-variants", len(variants), sum(r.confidence == "HIGH" for r in variants)),
        ("parent-age-drift", len(parent_drift), sum(f.confidence == "HIGH" for f in parent_drift)),
        ("parent-ages", len(parent_ages), len(parent_ages)),
        ("posthumous-birth", len(posthumous),
         sum(f.confidence == "HIGH" for f in posthumous)),
        ("reconcile", len(reconciled), sum(r.confidence == "HIGH" for r in reconciled)),
        ("union-dups", sum(1 for g in groups if g.is_candidate), None),
        # The strict bans only: the weekday and eve findings are a triage list
        # the books themselves keep loosely, and would move with every year read.
        ("wedding-ages", len(wedding_ages), sum(f.confidence == "HIGH" for f in wedding_ages)),
        ("wedding-calendar-strict", weddings.strict, None),
    ]
    body = "".join(f"{name}\t{n}\t{'-' if high is None else high}\n"
                   for name, n, high in rows)
    return snapshot_header(village_dir) + body


def snapshot(village_dir: Path, *, check: bool) -> int:
    """Write `<village>/facts_findings.tsv`, or (`check`) fail when it is stale."""
    import difflib

    path = village_dir / SNAPSHOT_FILE
    fresh = findings_snapshot(village_dir)
    if not check:
        path.write_text(fresh, encoding="utf-8")
        print(f"→ {path}", file=sys.stderr)
        return 0
    committed = path.read_text(encoding="utf-8") if path.is_file() else ""
    if committed == fresh:
        return 0
    sys.stdout.writelines(difflib.unified_diff(
        committed.splitlines(keepends=True), fresh.splitlines(keepends=True),
        fromfile=f"{path} (committed)", tofile=f"{path} (records now)"))
    print(f"\n{village_dir.name}: the findings of the facts-backed checks moved. "
          f"Read the reports, then run `verso facts-snapshot --village {shlex.quote(village_dir.name)}` "
          f"and commit {SNAPSHOT_FILE} with the change.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--village", required=True)
    ap.add_argument("--check", action="store_true",
                    help=f"fail when <village>/{SNAPSHOT_FILE} no longer matches")
    args = ap.parse_args(argv)
    village_dir = village_path(args.village)
    if not village_dir.is_dir():
        print(f"error: village dir not found: {village_dir}", file=sys.stderr)
        return 2
    return snapshot(village_dir, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
