#!/usr/bin/env python3
"""Extract assertions from a village's records and ask a rule about them.

All of `verso.ru.facts` is pure; this is where the filesystem lives — discovering
DSL modules, translating the village for the `[N loose]` annotations, and
writing the report. Same division as `verso.ru.cli.generate_timeline` over
`verso.ru.timeline`.

    python3 -m verso.ru.cli.facts --village Горюхино
    python3 -m verso.ru.cli.facts --village Горюхино --kind marriage --join witness×witness
    python3 -m verso.ru.cli.facts --village Горюхино --dump         # → <village>/facts.jsonl
    python3 -m verso.ru.cli.facts --village Горюхино --why 1911:66
    python3 -m verso.ru.cli.facts --village Горюхино --basis-census
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from verso.core import workspace
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.external_sources import facts_from_external_sources
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.extract.name_lists import facts_from_name_lists
from verso.core.records.ids import RecordIds
from verso.ru.facts.identity import (
    canonical_fold, conclusions, display_name, kin_identity, matching_fold, name_identity)
from verso.ru.facts.checks import FACTS_CHECKS
from verso.ru.facts.checks.births import BirthFinding, birth_claims_of, birth_span
from verso.ru.facts.checks.dates import OrderFindings, WithinFinding, date_order_findings, unplaced_within
from verso.ru.facts.checks.deaths import DeathFinding, death_claims
from verso.ru.facts.checks.fathers import FatherClaim, FatherFinding, father_findings
from verso.ru.facts.checks.lags import BAPTISM_DAYS, BURIAL_DAYS, Lags, baptism_lags, burial_lags
from verso.ru.facts.checks.name_days import FAR_DAYS, NameDays, name_day_findings
from verso.ru.facts.checks.parent_ages import (
    DRIFT_SLACK_YEARS, FATHER_MIN, MOTHER_MAX, MOTHER_MIN, DriftFinding, parent_age_drift, parent_age_findings)
from verso.ru.facts.checks.parenthood import (
    FATHER_DAYS, MOTHER_SPAN_YEARS, PosthumousFinding, SpanFinding, children_spans, posthumous_births)
from verso.ru.facts.checks.reach import identity_reach
from verso.ru.facts.checks.wedding_ages import DISPENSATION_YEARS, GAP_YEARS, WeddingAges, wedding_age_findings
from verso.ru.facts.checks.wedding_calendar import WeddingCalendar, wedding_calendar_findings
from verso.ru.facts.model import (
    Assertion, AssertionSet, Citation, Derived, DiedOn, GodparentOf, NameClaim, ParentOf, Persona, Record, Relational, ResidedIn, Retracted, SpouseOf, WitnessedAt, why)
from verso.ru.facts.projection import (
    LooseIndex, canonical_key, canonical_name, consolidated_identity)
from verso.ru.facts.rules.cooccurrence import Occurrence, Pair, cooccurrences
from verso.ru.facts.signals import Signal, signal_of
from verso.ru.pipeline.facts import consolidated_facts, unpublished_kinds
from verso.core.tools import tool
from verso.ru.facts.labels import record_number
from verso.ru.messages import t

if TYPE_CHECKING:
    from verso.core.targets.geni.date import GeniDate

def village_path(arg: str) -> Path:
    """A `--village` argument as a directory: an absolute path as given, a name
    under the workspace's root."""
    return Path(arg) if Path(arg).is_absolute() else workspace.current().root / arg

#: The rule takes its two predicates as parameters; these are the call sites,
#: and the only place in the codebase where a join is named. Adding one costs a
#: line here and nothing in the rule.
JOINS: dict[str, tuple[type[Relational], type[Relational]]] = {
    "parent×godparent": (ParentOf, GodparentOf),
    "parent×witness": (ParentOf, WitnessedAt),
    "spouse×witness": (SpouseOf, WitnessedAt),
    "witness×witness": (WitnessedAt, WitnessedAt),
    "parent×parent": (ParentOf, ParentOf),
}

_SLOT = re.compile(r"(\d+)$")


# --------------------------------------------------------------------------- #
# Loading — the only I/O
# --------------------------------------------------------------------------- #


def _iter_records(village_dir: Path, wanted: type[Any],
                  ids: RecordIds | None = None) -> list[tuple[Any, str]]:
    """(record, source_filename) for every entry of one kind across all years.

    The per-record year falls back to the book year, exactly as the DSL's own
    consumers do — a record that omits it is dated by its container. `ids`
    counts every record's id in the same walk (`discover_records`). A kind the
    translator does not read (a divorce) is taken from that walk too.
    """
    from verso.core.pipeline.load import discover_records

    skipped: list[tuple[Path, Exception]] = []
    out: list[tuple[Any, str]] = []
    beside: list[tuple[Path, str, object]] = []
    fed = list(discover_records(str(village_dir), skipped=skipped, ids=ids, untranslated=beside))
    for dsl_path, _name, found in (*fed, *beside):
        if not isinstance(found, wanted):
            continue
        records = cast(Any, found)
        for r in records.records:
            if r.year is None:
                r.year = records.year
            out.append((r, dsl_path.name))
    for path, exc in skipped:
        print(f"warning: skipping {path}: {exc}", file=sys.stderr)
    return out


def _iter_books(village_dir: Path, wanted: type[Any],
                ids: RecordIds | None = None) -> list[tuple[Any, str]]:
    """(records object, source_filename) for every book of one kind.

    A household roll is read whole: a двор takes its year, its dates and its
    previous revision from the roll around it, so the unit handed to the
    extractor is the file's `CensusRecords`, not a record inside it.
    """
    from verso.core.pipeline.load import discover_records

    skipped: list[tuple[Path, Exception]] = []
    out: list[tuple[Any, str]] = []
    for dsl_path, _name, found in discover_records(str(village_dir), skipped=skipped, ids=ids):
        if isinstance(found, wanted):
            out.append((found, dsl_path.name))
    for path, exc in skipped:
        print(f"warning: skipping {path}: {exc}", file=sys.stderr)
    return out


def load(village_dir: Path, kind: str = "birth") -> AssertionSet:
    """One kind's assertions, each persona named by its records-JSON id: the
    ids are counted over the whole village in the walk that loads it."""
    from verso.ru.dsl.records.births import BirthRecords
    from verso.ru.dsl.records.census import CensusRecords
    from verso.ru.dsl.records.deaths import DeathRecords
    from verso.ru.dsl.records.marriages import MarriageRecords

    ids = RecordIds()
    village = village_dir.name
    if kind == "birth":
        return AssertionSet(facts_from_births(
            _iter_records(village_dir, BirthRecords, ids), village=village, ids=ids))
    if kind == "death":
        return AssertionSet(facts_from_deaths(
            _iter_records(village_dir, DeathRecords, ids), village=village, ids=ids))
    if kind == "divorce":
        from verso.ru.dsl.records.divorces import DivorceRecords
        from verso.ru.facts.extract.divorces import facts_from_divorces
        return AssertionSet(facts_from_divorces(
            _iter_records(village_dir, DivorceRecords, ids), village=village, ids=ids))
    if kind == "census":
        return AssertionSet(facts_from_census(
            _iter_books(village_dir, CensusRecords, ids), village=village, ids=ids))
    if kind == "list":
        from verso.ru.dsl.records.name_lists import NameListRecords
        return AssertionSet(facts_from_name_lists(
            _iter_books(village_dir, NameListRecords, ids), village=village, ids=ids))
    if kind == "external":
        from verso.ru.dsl.records.external_sources import ExternalSourceRecords
        return AssertionSet(facts_from_external_sources(
            _iter_books(village_dir, ExternalSourceRecords, ids), village=village, ids=ids))
    return AssertionSet(facts_from_marriages(
        _iter_records(village_dir, MarriageRecords, ids), village=village, ids=ids))


def run(facts: AssertionSet, *, min_count: int, fold: Any = canonical_fold,
        kin_guard: bool = False, join: str = "parent×godparent") -> list[Pair]:
    left, right = JOINS[join]
    return cooccurrences(facts.believed(), left=left, right=right,
                         identity=name_identity(fold), min_count=min_count,
                         kin_guard=kin_guard)


# --------------------------------------------------------------------------- #
# Display — rebuilt from NameClaim assertions, never from a DSL object
# --------------------------------------------------------------------------- #


Side = list[tuple[Occurrence, Persona]]


def _claim(occ: Occurrence, who: Persona) -> NameClaim | None:
    claims = [a for a in occ.record.about(who) if isinstance(a, NameClaim) and a.given]
    return claims[0] if claims else None


def _display(occ: Occurrence, who: Persona, fold: Any = canonical_fold) -> str:
    claim = _claim(occ, who)
    return display_name(claim, fold) if claim else "?"


def _best(pairs: Side, fold: Any = canonical_fold) -> str:
    """The most informative spelling of one side — prefer one with a surname."""
    for occ, who in pairs:
        claim = _claim(occ, who)
        if claim and (claim.surname or "").strip():
            return display_name(claim, fold)
    return _display(*pairs[0], fold) if pairs else "?"


def _identifiable(pairs: Side) -> bool:
    return any((c.surname or "").strip() for occ, who in pairs if (c := _claim(occ, who)))


def _residence(occ: Occurrence, who: Persona) -> str:
    for a in occ.record.about(who):
        if isinstance(a, ResidedIn):
            return a.place
    return "?"


def _slot(occ: Occurrence) -> str:
    m = _SLOT.search(occ.right_cite.locator)
    return m.group(1) if m else "?"


def format_report(groups: list[Pair], min_count: int, index: LooseIndex | None,
                  labels: tuple[str, str, str] = ("parent", "godparent", "gp"),
                  unit: str = "births",
                  compare: Callable[[list[str]], str | None] | None = None) -> str:
    """The recurring-pair report — the format the godparent co-occurrence check
    printed before the facts layer took it over, kept so a triage note written
    against it still reads."""
    left_label, right_label, slot_label = labels
    lines = [f"Recurring {right_label}↔{left_label} pairs "
             f"(≥{min_count} {unit}): {len(groups)}", ""]
    for g in groups:
        occs = sorted(g.occurrences,
                      key=lambda o: (o.left_cite.year or 0, o.left_cite.record_num))
        # Insertion order, not display order: the legacy check reads
        # `g.parents()`, so a pair whose earliest-by-number record is the terse
        # one would otherwise be titled differently.
        lefts = [(o, o.left) for o in g.occurrences]
        rights = [(o, o.right) for o in g.occurrences]
        head = f"■ {_best(lefts)}  ✕  {_best(rights)}   — {len(occs)} {unit}"
        if index is not None:
            head += f"   [{sum(index.is_loose(o.right) for o in occs)} loose]"
        lines.append(head)
        for o in occs:
            rec = o.right_cite.record_num
            lines.append(
                f"    {o.right_cite.year} · rec {rec if rec != 'none' else None} · "
                f"{right_label}={_display(o, o.right)} ({slot_label}{_slot(o)}) · "
                f"{left_label}={_display(o, o.left)} · "
                f"{_residence(o, o.right)} · {o.right_cite.source_file}")
            if index is not None:
                name = index.resolve(o.right)
                if name is None:
                    lines.append("        (not in the generated tree — already consolidated)")
                else:
                    mark = "LOOSE" if name not in index.config_text else "folded"
                    lines.append(f"        {mark}: {name}")
        if compare is not None and index is not None:
            url = compare([n for o in g.occurrences if (n := index.resolve(o.right))])
            if url:
                lines.append(f"    compare: {url}")
        lines.append("")
    return "\n".join(lines)


def state_compare(village_dir: Path) -> Callable[[list[str]], str | None]:
    """A `/merge/compare` URL between two of a pair's standing profiles, from
    `terraform state` — best effort, None when state cannot be read.

    Keyed on the res_names the bridge resolved, so no resource name is parsed:
    a folded record has no standing profile and takes no part.
    """
    import subprocess

    guids: dict[str, str] = {}
    try:
        out = subprocess.run(
            [tool("terraform"), f"-chdir={village_dir / 'terraform' / 'geni'}", "state", "pull"],
            capture_output=True, text=True, timeout=180)
        state = json.loads(out.stdout)
        for res in state.get("resources", []):
            if res.get("type") == "geni_profile":
                guid = res.get("instances", [{}])[0].get("attributes", {}).get("guid")
                if guid:
                    guids[res["name"]] = guid
    except Exception:
        guids = {}

    def compare(names: list[str]) -> str | None:
        found = list(dict.fromkeys(guids[n] for n in names if n in guids))
        if len(found) < 2:
            return None
        return f"https://www.geni.com/merge/compare/{found[0]}?to={found[1]}"
    return compare


# --------------------------------------------------------------------------- #
# Cross-record rules — these read more than one kind, so they load their own
# --------------------------------------------------------------------------- #


def identity_census(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check identity` — see `identity_report`."""
    return identity_report(*consolidated_facts(village_dir))


def identity_report(facts: AssertionSet, gen: Any, slots: Any) -> tuple[str, int]:
    """`verso facts --check identity`, drawn from `identity_reach`."""
    r = identity_reach(facts, gen, slots, unpublished=unpublished_kinds())
    minted = r.total - sum(r.refused.values())
    lines = [
        str(t("cli.facts.identity.appearances", total=r.total)),
        str(t("cli.facts.identity.placed", minted=minted, share=minted * 100.0 / max(r.total, 1))),
        str(t("cli.facts.identity.refused", refused=sum(r.refused.values()))),
    ]
    lines += [f"      {kind} · {slot}: {n}"
              for (kind, slot), n in sorted(r.refused.items(), key=lambda kv: -kv[1])]
    lines += [str(t("cli.facts.identity.unpublished", kind=kind, count=n)) for kind, n in sorted(r.unpublished.items())]
    lines += [
        str(t("cli.facts.identity.reached", placed=len(r.placed), canonicals=len(gen.canonical_profiles()))),
        str(t("cli.facts.identity.folded", folded=sum(1 for v in r.placed.values() if len(v) > 1))),
        str(t("cli.facts.identity.repeated_number", repeated=r.repeated_number)),
        str(t("cli.facts.identity.surplus", surplus=r.surplus)),
        str(t("cli.facts.identity.minted_twice", twice=r.minted_twice)),
    ]
    return "\n".join(lines), (1 if r.surplus or r.minted_twice else 0)


def date_order(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check date-order` — see `date_order_findings`."""
    facts, gen, slots = consolidated_facts(village_dir)
    identity = consolidated_identity(gen, slots.object_of)
    return date_order_report(*date_order_findings(facts, identity), gen,
                             alone=entries_alone(facts, unplaced_within(facts, identity)))


#: An entry whose people the bridge places on nobody, with what it says of itself out of order: how the
#: report names it (its people, its file and number), then its findings.
type EntryAlone = tuple[str, list[WithinFinding]]


def entries_alone(facts: AssertionSet, found: list[WithinFinding]) -> list[EntryAlone]:
    """`unplaced_within`'s findings entry by entry, each named by the people it is about — as the record
    writes them, for no canonical names them."""
    grouped: dict[tuple[str, str, int, str, int], list[WithinFinding]] = {}
    for f in found:
        grouped.setdefault(f.left.cite.record_id, []).append(f)
    # Everyone the entry names, not only whoever a finding was said of: a couple's finding is said once.
    named: dict[tuple[str, str, int, str, int], dict[Persona, NameClaim]] = {}
    for claim in facts.of(NameClaim):
        if claim.given and claim.cite.record_id in grouped:
            named.setdefault(claim.cite.record_id, {}).setdefault(claim.subject, claim)
    out: list[EntryAlone] = []
    for record_id, group in grouped.items():
        cite = group[0].left.cite
        who = ", ".join(display_name(claim) for claim in named.get(record_id, {}).values()) or "?"
        out.append((f"{who} ({cite.source_file} {record_number(cite)})", group))
    return out


def date_order_report(within: OrderFindings, across: OrderFindings,
                      gen: Any, *, alone: Sequence[EntryAlone] = ()) -> tuple[str, int]:
    from verso.ru.consolidation.profile_reading import display_name

    profiles = gen.canonical_profiles()

    def name_of(res_name: str) -> str:
        profile = profiles.get(res_name)
        return display_name(profile) if profile is not None else res_name

    if not within and not across and not alone:
        return ("date-order: OK — 0 findings "
                "(no record dates an event before an earlier life event).", 0)
    lines = [str(t("cli.facts.date_order.head", within=len(within) + len(alone), across=len(across)))]
    if within or alone:
        lines += ["", str(t("cli.facts.date_order.within"))]
        for res_name in sorted(within):
            lines.append(f"  {name_of(res_name)} ({res_name}):")
            for kind, _event, _reference, a, b in within[res_name]:
                signal = signal_of(WithinFinding(kind=kind, left=a, right=b))
                lines.append(f"      {signal.said}  [{kind}]  {a.cite.source_file} {record_number(a.cite)}")
                lines.append(f"      → {signal.why}")
        # The entries of people no canonical holds (a record the tree does not publish): the same class,
        # each finding said once though both of a couple carry it.
        for who, findings in alone:
            lines.append(f"  {who}:")
            for f in findings:             # `within_entry` says a couple's finding once
                signal = signal_of(f)
                lines.append(f"      {signal.said}  [{f.kind}]  {f.left.cite.source_file} {record_number(f.left.cite)}")
                lines.append(f"      → {signal.why}")
    if across:
        lines += ["", str(t("cli.facts.date_order.across"))]
        for res_name in sorted(across):
            lines.append(f"  {name_of(res_name)} ({res_name}):")
            for _kind, event, reference, a, b in across[res_name]:
                lines.append(
                    f"      {event} {a.date} [{a.cite.source_file} "
                    f"{record_number(a.cite)}] < {reference} {b.date} "
                    f"[{b.cite.source_file} {record_number(b.cite)}]")
    return "\n".join(lines), 1


def _birth_claim_line(claim: Any) -> str:
    from verso.ru.facts.model import AgedYears

    c = claim.cite
    page = str(t("cli.facts.leaf", page=c.page)) if c.page else ""
    said = (str(t("cli.facts.birth.age_on", age=claim.age, as_of=claim.as_of)) if isinstance(claim, AgedYears)
            else str(t("cli.facts.birth.born", date=claim.date)))
    span = birth_span(claim)
    implied = ""
    if span is not None and isinstance(claim, AgedYears):
        first, last = span.first_year, span.last_year
        implied = (str(t("cli.facts.birth.implied_year", year=first)) if first == last
                   else str(t("cli.facts.birth.implied_years", first=first, last=last)))
    return f"{said}{implied}  [{c.source_file} {record_number(c)}{page} · {c.locator}]"


@dataclass(frozen=True)
class BirthTree:
    """What the translation made of a finding — the two things its triage
    otherwise looks up by hand. Read by the CLI and never by the rule, which
    must not learn that a tree exists.

    `shown` is a canonical's generated `birth.date`: what `_pick_best_date`
    kept over the fold, after overrides — the date the next apply puts on
    Geni. `minted` is the res_name a claim's record minted its profile under
    (the `profile_minted_for` bridge), `emitted` the birth each emission under
    a res_name carried into the fold, and `folded` every res_name folded into a
    canonical, sorted. An `ignore` entry is compared with the `emitted` value,
    so that value is what the report prints — never one recomputed here.
    """
    shown: Callable[[str], GeniDate | None]
    minted: Callable[[Persona], str | None]
    emitted: Callable[[str], tuple[GeniDate | None, ...]]
    folded: Callable[[str], tuple[str, ...]]


def birth_tree(gen: Any, slots: Any) -> BirthTree:
    """The `BirthTree` of one finished translation — the one the bridge used."""
    profiles = gen.canonical_profiles()
    emitted: dict[str, tuple[GeniDate | None, ...]] = gen.emitted_birth_dates()
    folded: dict[str, list[str]] = {}
    for res_name in emitted:
        folded.setdefault(gen.resolve_canonical(res_name), []).append(res_name)

    def shown(canonical: str) -> GeniDate | None:
        profile = profiles.get(canonical)
        return profile.birth.date if profile is not None and profile.birth else None

    def minted(who: Persona) -> str | None:
        obj = slots.object_of(who)
        return gen.profile_minted_for(obj) if obj is not None else None

    return BirthTree(shown=shown, minted=minted,
                     emitted=lambda res_name: emitted.get(res_name, ()),
                     folded=lambda canonical: tuple(sorted(folded.get(canonical, ()))))


def geni_date_ru(d: GeniDate | None) -> str:
    """A `GeniDate` as a reader says it: «между ок. 1784 и ок. 01.1796»."""
    if d is None or d.year is None:
        return str(t("cli.facts.date.none"))

    def point(day: int | None, month: int | None, year: int | None,
              circa: bool) -> str:
        # A day is printed only beside its month, as the books never date one alone.
        parts = [f"{x:02d}" for x in (day, month) if x] if month else []
        body = ".".join([*parts, str(year or "?")])
        return str(t("cli.facts.date.circa", date=body)) if circa else body

    start = point(d.day, d.month, d.year, d.circa)
    if d.date_range == "between" and d.end_year:
        return str(t("cli.facts.date.between", start=start,
                     end=point(d.end_day, d.end_month, d.end_year, d.end_circa)))
    if d.date_range in ("between", "after"):
        return str(t("cli.facts.date.after", start=start))
    if d.date_range == "before":
        return str(t("cli.facts.date.before", start=start))
    return start


def geni_date_literal(d: GeniDate) -> str:
    """The `GeniDate(...)` to paste into an `ignore` entry: every field the
    date carries, in constructor order, so the entry equals it exactly."""
    fields = [("day", d.day), ("month", d.month), ("year", d.year),
              ("circa", d.circa or None), ("end_day", d.end_day),
              ("end_month", d.end_month), ("end_year", d.end_year),
              ("end_circa", d.end_circa or None),
              ("date_range", f'"{d.date_range}"' if d.date_range else None),
              ("synthetic", d.synthetic or None)]
    return f"GeniDate({', '.join(f'{k}={v}' for k, v in fields if v)})"


def _ignore_line(claim: Assertion, canonical: str, tree: BirthTree) -> str:
    """The `ignore` value that drops the birth this claim's record gave its
    profile, and the two ways pasting it could drop the wrong one.

    A record derives ONE birth, and not always from the claim in hand: a roll
    dates it by the current age, so a wrong previous-revision age leaves the
    profile's date untouched — withdrawing that age is the whole fix, and the
    printed value would drop the good birth. That is flagged when the value
    falls outside the years the claim itself implies. And `GeniDate.__eq__`
    compares day, month and year and nothing else, so one entry removes every
    folded birth that shares them — a second roll's agreeing age, a witness's
    adult window starting that year.
    """
    res_name = tree.minted(claim.subject)
    if res_name is None or not tree.emitted(res_name):
        return str(t("cli.facts.ignore.no_profile"))
    dates = [d for d in tree.emitted(res_name) if d is not None]
    if not dates:
        return str(t("cli.facts.ignore.no_birth"))
    literals = sorted(dict.fromkeys(geni_date_literal(d) for d in dates))
    line = "ignore: " + str(t("cli.facts.ignore.or")).join(literals)
    if len(literals) > 1:
        line += str(t("cli.facts.ignore.shared_res_name"))
    span = birth_span(claim)
    if span is not None and not all(
            d.year is not None and span.first_year <= d.year <= span.last_year
            for d in dates):
        line += str(t("cli.facts.ignore.not_from_this_claim"))
    also = [other for other in tree.folded(canonical) if other != res_name
            and any(d is not None and d in dates for d in tree.emitted(other))]
    if also:
        line += str(t("cli.facts.ignore.drops_also", also=", ".join(also)))
    return line


def format_birth_claims(found: list[BirthFinding],
                        name_of: Callable[[str], str],
                        tree: BirthTree | None = None) -> str:
    if not found:
        return "birth-claims: OK — 0 findings (no person's records disagree about their birth)."
    high = sum(1 for f in found if f.confidence == "HIGH")
    lines = [str(t("cli.facts.birth_claims.head", count=len(found), high=high, low=len(found) - high))]
    for f in found:
        res_name = canonical_name(f.who) or ""
        lines.append("")
        lines.append(str(t("cli.facts.birth_claims.finding", confidence=f.confidence, name=name_of(res_name),
                             res_name=res_name, years=f.widest.years, allowed=f.widest.allowed)))
        if tree is not None:
            lines.append(str(t("cli.facts.birth_claims.on_geni", date=geni_date_ru(tree.shown(res_name)))))
        for c in f.claims:
            lines.append(f"    {_birth_claim_line(c)}")
            if tree is not None:
                lines.append(f"        {_ignore_line(c, res_name, tree)}")
    return "\n".join(lines)


def birth_claims(village_dir: Path, *, min_gap_years: float = 0.0) -> tuple[str, int]:
    """`verso facts --check birth-claims`: one translation, the bridge, the rule.

    NOT a port of `age-conflicts`, and it replaces nothing. That check asks
    about the tree Geni shows — a canonical's ONE birth, picked by the order of
    the fold, against children the census routing gave it — and of its forty
    parents this one finds none. This asks what the tree cannot: the records a
    canonical was folded from, each still saying when the person was born, and
    two of them too far apart to be one life. It is the corpus's first check
    for a fold that went too far; every discovery channel looks for folds that
    have not been made.

    Each finding also prints the two answers its triage needs from the tree —
    the birth Geni shows now, and per claim the `ignore` value that would drop
    that record's birth from the fold — read off the SAME translation the
    bridge consulted (`birth_tree`), so neither is a second opinion.
    """
    from verso.ru.consolidation.profile_reading import display_name
    from verso.ru.facts.projection import consolidated_identity

    facts, gen, slots = consolidated_facts(village_dir)
    found = birth_claims_of(facts.believed(),
                            consolidated_identity(gen, slots.object_of),
                            min_gap_years=min_gap_years)
    profiles = gen.canonical_profiles()

    def name_of(res_name: str) -> str:
        profile = profiles.get(res_name)
        return display_name(profile) if profile is not None else res_name

    return (format_birth_claims(found, name_of, birth_tree(gen, slots)),
            (1 if found else 0))


def _father_said(c: FatherClaim) -> str:
    return (f"{c.said} [{c.cite.source_file} {record_number(c.cite)} · {c.cite.locator}"
            f"{str(t('cli.facts.father.derived_dot')) if c.derived else ''}]")


def format_father_claims(found: list[FatherFinding],
                         name_of: Callable[[str], str]) -> str:
    across = [f for f in found if f.across]
    within = [f for f in found if f.within]
    noted = [f for f in found if f.acknowledged]
    high = sum(1 for f in across if f.confidence == "HIGH")
    if not across and not within:
        return ("father-claims: OK — 0 findings (every person's records agree on "
                "who the father is)"
                + (str(t("cli.facts.father.ok_noted", noted=len(noted))) if noted else "") + ".")
    lines = [str(t("cli.facts.father.head", across=len(across), high=high, low=len(across) - high,
                   within=len(within)))
             + (str(t("cli.facts.father.head_noted", noted=len(noted))) if noted else "")]
    if across:
        lines += ["", str(t("cli.facts.father.across"))]
        for f in across:
            lines += ["", f"[{f.confidence}] {name_of(f.canonical)} ({f.canonical})"]
            for group in f.groups:
                records = len({c.cite.record_id for c in group})
                shown = "; ".join(dict.fromkeys(_father_said(c) for c in group))
                lines.append(str(t("cli.facts.father.group", records=records, shown=shown)))
    if within:
        lines += ["", str(t("cli.facts.father.within"))]
        for f in within:
            by_record: dict[tuple[object, ...], list[FatherClaim]] = {}
            for a, b in f.within:
                for c in (a, b):
                    claims = by_record.setdefault(c.cite.record_id, [])
                    if c not in claims:
                        claims.append(c)
            for claims in by_record.values():
                cite = claims[0].cite
                said = "; ".join(f"{c.said} ({c.cite.locator}"
                                 f"{str(t('cli.facts.father.derived_comma')) if c.derived else ''})"
                                 for c in claims)
                lines.append(f"  {name_of(f.canonical)} ({f.canonical}): {said}  "
                             f"[{cite.source_file} {record_number(cite)}]")
    if noted:
        lines += ["", str(t("cli.facts.father.noted"))]
        for f in noted:
            for a, b, note in dict.fromkeys(f.acknowledged):
                lines.append(str(t("cli.facts.father.noted_pair", name=name_of(f.canonical), canonical=f.canonical,
                                   first=a.said, second=b.said, file=a.cite.source_file,
                                   number=record_number(a.cite), note=note)))
    return "\n".join(lines)


def kin_error_notes(gen: Any) -> Callable[[Citation], str | None]:
    """The `source_kin_error=` of the entry a citation points into.

    The note stands a within-record pair down; it is read here, in the wiring,
    because it names no single assertion to withdraw — the entry is faithful
    and one of its two kin names is the scribe's slip, the note does not say
    which (`death(namesake=)` is kept out of stated-age the same way)."""
    from verso.ru.dsl.records.marriages import MarriageRecords

    notes: dict[tuple[str, str], str] = {}
    for name, recs in gen.fed_sources:
        if not isinstance(recs, MarriageRecords):
            continue
        for r in recs.records:
            note = getattr(r, "source_kin_error", None)
            if note:
                notes[(Path(name).name, str(r.record_num))] = note

    def note_of(cite: Citation) -> str | None:
        if cite.record_kind != "marriage":
            return None
        return notes.get((cite.source_file, cite.record_num))
    return note_of


def _days(days: int) -> str:
    return str(t("cli.facts.span.days", count=days))


def _span(days: int) -> str:
    return _days(days) if days < 365 else str(t("cli.facts.span.years", years=days / 365.25))


def format_death_claims(found: list[DeathFinding],
                        name_of: Callable[[str], str]) -> str:
    if not found:
        return ("death-claims: OK — 0 findings (every person's records can share "
                "one death).")
    high = sum(1 for f in found if f.confidence == "HIGH")
    lines = [str(t("cli.facts.death_claims.head", count=len(found), high=high, low=len(found) - high)),
             str(t("cli.facts.death_claims.note"))]
    for f in found:
        lines += ["", str(t("cli.facts.death_claims.finding", confidence=f.confidence, name=name_of(f.canonical),
                            canonical=f.canonical, gap=_span(f.gap)))]
        for c in f.claims:
            word = str(t("cli.facts.death_claims.death") if isinstance(c, DiedOn) else t("cli.facts.death_claims.burial"))
            told = str(t("cli.facts.death_claims.told")) if c.date.circa else ""
            lines.append(f"    {word} {c.date}{told} [{c.cite.source_file} "
                         f"{record_number(c.cite)} · {c.cite.locator}]")
    return "\n".join(lines)


def death_claims_report(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check death-claims`: one translation, the bridge, the check."""
    from verso.ru.consolidation.profile_reading import display_name

    facts, gen, slots = consolidated_facts(village_dir)
    found = death_claims(facts.believed(), consolidated_identity(gen, slots.object_of))
    profiles = gen.canonical_profiles()

    def name_of(res_name: str) -> str:
        profile = profiles.get(res_name)
        return display_name(profile) if profile is not None else res_name

    return format_death_claims(found, name_of), (1 if found else 0)


def _dmy(day: tuple[int, int, int] | None) -> str:
    return f"{day[2]:02d}.{day[1]:02d}.{day[0]}" if day else "—"


def format_signals(signals: Sequence[Signal], *, head: str) -> str:
    """The findings of one check as a report: `head`; why each kind of finding met is worth a second look, once
    each and under its level; how a finding the scan confirms is answered — the field of the record that stands it
    down, the one a card's «Так в подлиннике» writes; then every finding in the words of its signal — the words a
    record's card says (`verso.ru.facts.signals.signal_of`) — with the lines that help the re-reading and where it
    was read."""
    whys = dict((s.why, s.confidence) for s in reversed(signals))
    lines = [head, *(f"{whys[why]} — {why}" for why in dict.fromkeys(s.why for s in signals))]
    lines += [str(t("cli.facts.stand_down", field=field))
              for field in dict.fromkeys(s.stand_down for s in signals if s.stand_down)]
    for s in signals:
        page = str(t("cli.facts.leaf", page=s.cite.page)) if s.cite.page else ""
        lines += ["", f"[{s.confidence}] {s.said}", *(f"    {detail}" for detail in s.details),
                  f"    {s.cite.source_file} {record_number(s.cite)}{page}"]
    return "\n".join(lines)


def _noted(field: str, noted: int) -> str:
    """The tail of a report's first line: how many findings the author's note stood down."""
    return str(t("cli.facts.noted", field=field, noted=noted)) if noted else ""


def _head(check: str, result: NameDays | WeddingCalendar | Lags | WeddingAges) -> str:
    """A check's own first line: what it asked, how many it found at each level, what the notes stood down."""
    found = result.findings
    high = sum(1 for f in found if f.confidence == "HIGH")
    if isinstance(result, NameDays):
        unknown_births = sum(result.unknown.values())
        tail = (str(t("cli.facts.name_days.unknown", births=t("counted.births", count=unknown_births),
                      names=t("counted.names", count=len(result.unknown))))
                if result.unknown else "")
        noted = str(t("cli.facts.calendar_noted", noted=result.noted)) if result.noted else ""
        of_births = t("counted.of_births", count=result.checked)
        if not found:
            return str(t("cli.facts.name_days.ok", of_births=of_births, tail=tail, noted=noted))
        return str(t("cli.facts.name_days.head", count=len(found), of_births=of_births, far=FAR_DAYS, high=high,
                     low=len(found) - high, tail=tail, noted=noted))
    if isinstance(result, WeddingCalendar):
        noted = str(t("cli.facts.calendar_noted", noted=result.noted)) if result.noted else ""
        if not found:
            return str(t("cli.facts.wedding_calendar.ok", of_weddings=t("counted.of_weddings", count=result.checked),
                         noted=noted))
        return str(t("cli.facts.wedding_calendar.head", strict=t("counted.weddings", count=result.strict),
                     loose=len(found) - result.strict, of_dated=t("counted.of_dated", count=result.checked), noted=noted))
    if isinstance(result, Lags):
        tail = _noted("lag_note", result.noted)
        if not found:
            return f"{check}: OK — 0 findings{tail}."
        if check == "baptism-lag":
            return str(t("cli.facts.lags.baptism_head", check=check, count=len(found), days=BAPTISM_DAYS, high=high,
                         low=len(found) - high)) + tail
        return str(t("cli.facts.lags.burial_head", check=check, count=len(found), days=BURIAL_DAYS, high=high,
                     low=len(found) - high)) + tail
    tail = _noted("age_note", result.noted)
    if not found:
        return ("wedding-ages: OK — 0 findings (no age half a year under the minimum, no "
                f"spouses more than {GAP_YEARS:g} years apart){tail}.")
    return str(t("cli.facts.wedding_ages.head", count=len(found), high=high, dispensation=DISPENSATION_YEARS,
                 low=len(found) - high, gap=GAP_YEARS)) + tail


def signal_report(check: str, result: NameDays | WeddingCalendar | Lags | WeddingAges) -> str:
    """The report of one of the checks a record answers alone (`verso.ru.facts.signals.CHECKS`): its line of
    counts, and its findings as `format_signals` prints them."""
    return format_signals([signal_of(f) for f in result.findings], head=_head(check, result))


def wedding_calendar_report(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check wedding-calendar`: the same loader as the snapshot,
    whose strict count it must match."""
    facts, _gen, _slots = consolidated_facts(village_dir)
    result = wedding_calendar_findings(facts.believed())
    return signal_report("wedding-calendar", result), (1 if result.findings else 0)


def lags_report(village_dir: Path, kind: str) -> tuple[str, int]:
    """`verso facts --check baptism-lag|burial-lag`: the snapshot's loader."""
    facts, _gen, _slots = consolidated_facts(village_dir)
    believed = facts.believed()
    lags = baptism_lags(believed) if kind == "baptism" else burial_lags(believed)
    return signal_report(f"{kind}-lag", lags), (1 if lags.findings else 0)


def _where(cite: Citation) -> str:
    return f"{cite.source_file} {record_number(cite)}"


def format_posthumous(found: list[PosthumousFinding], name_of: Callable[[str], str]) -> str:
    if not found:
        return ("posthumous-birth: OK — 0 findings (no child born after its mother's death "
                f"or {FATHER_DAYS}+ days after its father's).")
    high = sum(1 for f in found if f.confidence == "HIGH")
    lines = [str(t("cli.facts.posthumous.head", count=len(found), high=high, low=len(found) - high)),
             str(t("cli.facts.posthumous.note", days=FATHER_DAYS))]
    for f in found:
        role = str(t("cli.facts.posthumous.mother") if f.role == "mother" else t("cli.facts.posthumous.father"))
        lines += ["", str(t("cli.facts.posthumous.finding", confidence=f.confidence, name=name_of(f.parent),
                            parent=f.parent, role=role, born=_dmy(f.born), child=_where(f.child_cite),
                            days=_days(f.days), died=_dmy(f.died), death=_where(f.death_cite)))]
    return "\n".join(lines)


def format_children_span(found: list[SpanFinding], name_of: Callable[[str], str]) -> str:
    if not found:
        return (f"children-span: OK — 0 findings (no mother's children born more than "
                f"{MOTHER_SPAN_YEARS:g} years apart).")
    high = sum(1 for f in found if f.confidence == "HIGH")
    lines = [str(t("cli.facts.children_span.head", count=len(found), years=MOTHER_SPAN_YEARS, high=high,
                   low=len(found) - high)),
             str(t("cli.facts.children_span.note"))]
    for f in found:
        (d1, c1), (d2, c2) = f.first, f.last
        lines += ["", str(t("cli.facts.children_span.finding", confidence=f.confidence, name=name_of(f.parent),
                            parent=f.parent, children=f.children, years=f.years, first=_dmy(d1),
                            first_where=_where(c1), last=_dmy(d2), last_where=_where(c2)))]
    return "\n".join(lines)


def parenthood_report(village_dir: Path, check: str) -> tuple[str, int]:
    """`verso facts --check posthumous-birth|children-span`: one translation, the
    bridge, the check."""
    from verso.ru.consolidation.profile_reading import display_name

    facts, gen, slots = consolidated_facts(village_dir)
    believed = facts.believed()
    identity = consolidated_identity(gen, slots.object_of)
    profiles = gen.canonical_profiles()

    def name_of(res_name: str) -> str:
        profile = profiles.get(res_name)
        return display_name(profile) if profile is not None else res_name

    if check == "posthumous-birth":
        posthumous = posthumous_births(believed, identity)
        return format_posthumous(posthumous, name_of), (1 if posthumous else 0)
    spans = children_spans(believed, identity)
    return format_children_span(spans, name_of), (1 if spans else 0)


def wedding_ages_report(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check wedding-ages`: the snapshot's loader."""
    facts, _gen, _slots = consolidated_facts(village_dir)
    ages = wedding_age_findings(facts.believed())
    return signal_report("wedding-ages", ages), (1 if ages.findings else 0)


def parent_ages_text(facts: AssertionSet) -> str:
    """The report of `parent-ages` over assertions a reader may believe: its line of counts, its findings."""
    found = parent_age_findings(facts)
    params = {"mother_min": MOTHER_MIN, "mother_max": MOTHER_MAX, "father_min": FATHER_MIN}
    if not found:
        return str(t("cli.facts.parent_ages.ok", **params))
    head = str(t("cli.facts.parent_ages.head", count=len(found), high=sum(f.confidence == "HIGH" for f in found),
                 **params))
    return format_signals([signal_of(f) for f in found], head=head)


def parent_ages_report(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check parent-ages`: the snapshot's loader."""
    facts, _gen, _slots = consolidated_facts(village_dir)
    believed = facts.believed()
    return parent_ages_text(believed), (1 if parent_age_findings(believed) else 0)


def parent_age_drift_text(found: list[DriftFinding]) -> str:
    """The report of `parent-age-drift`: its line of counts, then one group per couple, its rows in date order."""
    if not found:
        return str(t("cli.facts.parent_age_drift.ok", slack=DRIFT_SLACK_YEARS))
    couples = dict.fromkeys(f.couple for f in found)
    high = sum(f.confidence == "HIGH" for f in found)
    lines = [str(t("cli.facts.parent_age_drift.head", count=len(found), couples=len(couples), slack=DRIFT_SLACK_YEARS,
                   high=high, low=len(found) - high)),
             str(t("cli.facts.parent_age_drift.note"))]
    for couple in sorted(couples):
        rows = [f for f in found if f.couple == couple]
        lines += ["", " + ".join(rows[0].names)]
        lines += [_drift_row(f) for f in rows]
    return "\n".join(lines)


def _drift_row(f: DriftFinding) -> str:
    role = str(t("cli.facts.parent_age_drift.father") if f.role == "father" else t("cli.facts.parent_age_drift.mother"))
    return str(t("cli.facts.parent_age_drift.finding", confidence=f.confidence, role=role, first=f.first_age,
                 second=f.second_age, years=f.gap_years, first_where=_where(f.first), second_where=_where(f.second)))


def parent_age_drift_report(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check parent-age-drift`: the snapshot's loader, the consolidation's fold passed beside the
    couple's key."""
    facts, gen, slots = consolidated_facts(village_dir)
    believed = facts.believed()
    found = parent_age_drift(believed, pair=kin_identity(), folded=consolidated_identity(gen, slots.object_of))
    return parent_age_drift_text(found), (1 if found else 0)


def name_days_report(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check name-days`: the births alone — no translation."""
    from verso.ru.church_calendar.svyatcy import load_svyatcy

    result = name_day_findings(load(village_dir, "birth").believed(), load_svyatcy())
    return signal_report("name-days", result), (1 if result.findings else 0)


def father_claims_report(village_dir: Path) -> tuple[str, int]:
    """`verso facts --check father-claims`: one translation, the bridge, the check."""
    from verso.ru.consolidation.profile_reading import display_name

    facts, gen, slots = consolidated_facts(village_dir)
    found = father_findings(facts.believed(), consolidated_identity(gen, slots.object_of),
                            kin_error_notes(gen))
    profiles = gen.canonical_profiles()

    def name_of(res_name: str) -> str:
        profile = profiles.get(res_name)
        return display_name(profile) if profile is not None else res_name

    report = format_father_claims(found, name_of)
    return report, (1 if any(f.across or f.within for f in found) else 0)


# --------------------------------------------------------------------------- #
# Side channels
# --------------------------------------------------------------------------- #


def _assertion_id(a: Assertion) -> str:
    return f"{type(a).__name__}|{a.subject}|{a.payload}"


def _as_json(a: Assertion) -> dict[str, object]:
    basis = a.basis
    if isinstance(basis, Derived):
        b: dict[str, object] = {"kind": "derived", "rationale": basis.rationale,
                                "surety": basis.surety.name,
                                "because": [_assertion_id(x) for x in basis.because]}
    elif isinstance(basis, Retracted):
        b = {"kind": "retracted", "reason": basis.reason}
    else:
        b = {"kind": "stated", "basis_unknown": basis.basis_unknown}
    payload = a.payload
    return {
        "predicate": type(a).__name__,
        "subject": str(a.subject),
        "payload": str(payload) if payload is not None else None,
        "cite": {"village": a.cite.village, "source_file": a.cite.source_file,
                 "record_kind": a.cite.record_kind, "record_num": a.cite.record_num,
                 "entry": a.cite.entry, "year": a.cite.year, "page": a.cite.page,
                 "locator": a.cite.locator},
        "basis": b,
    }


def dump(facts: AssertionSet, path: Path) -> int:
    with path.open("w", encoding="utf-8") as fh:
        for a in facts.sorted():
            fh.write(json.dumps(_as_json(a), ensure_ascii=False, sort_keys=True) + "\n")
    return len(facts)


def basis_census(facts: AssertionSet) -> str:
    total = len(facts)
    if not total:
        return str(t("cli.facts.basis.none"))
    unknown_by: dict[str, int] = {}
    for a in facts:
        if not isinstance(a.basis, (Derived, Retracted)) and a.basis.basis_unknown:
            unknown_by[type(a).__name__] = unknown_by.get(type(a).__name__, 0) + 1
    unknown = sum(unknown_by.values())
    derived: dict[str, int] = {}
    for a in facts:
        if isinstance(a.basis, Derived):
            key = f"{a.basis.rationale} ({a.basis.surety.name})"
            derived[key] = derived.get(key, 0) + 1
    retracted = sum(1 for a in facts if isinstance(a.basis, Retracted))
    stated = total - unknown - retracted - sum(derived.values())
    out = [str(t("cli.facts.basis.total", total=total)),
           str(t("cli.facts.basis.stated", stated=stated)),
           str(t("cli.facts.basis.unknown", unknown=unknown, share=unknown * 100.0 / total))]
    # Which in-place derivation costs most: the price of the basis the DSL
    # constructors fill without a breadcrumb, per predicate, largest first.
    out += [f"      {name}: {n}"
            for name, n in sorted(unknown_by.items(), key=lambda kv: (-kv[1], kv[0]))]
    out += [str(t("cli.facts.basis.retracted", retracted=retracted)),
            str(t("cli.facts.basis.derived"))]
    out += [f"    {rule}: {n}" for rule, n in sorted(derived.items())]
    return "\n".join(out)


def explain(facts: AssertionSet, spec: str) -> str:
    year, _, num = spec.partition(":")
    out: list[str] = []
    for record in facts.records():
        cite = record.assertions[0].cite
        if str(cite.year) != year or cite.record_num != num:
            continue
        out.append(str(t("cli.facts.explain.record", village=cite.village, file=cite.source_file, year=cite.year,
                         number=record_number(cite, sign=False))))
        render = functools.partial(_render, record)
        out += [why(a, render=render) for a in record.assertions]
        out.append("")
    return "\n".join(out) or str(t("cli.facts.explain.not_found", spec=spec))


def explain_person(facts: AssertionSet, gen: Any, slots: Any, res_name: str) -> str:
    """Everything the records say about one canonical, record by record.

    The triage view a `birth-claims`, `date-order` or `estate-conflicts`
    finding needs and used to be assembled by hand: for each record folded
    into the canonical, every assertion about that appearance — the claims it
    is the subject of, and the relations others hold TO it (its parents, its
    spouse) — each with its basis read out by `why()`, a withdrawn claim
    included under its reason.
    """
    from verso.ru.consolidation.profile_reading import display_name as profile_name

    identity = consolidated_identity(gen, slots.object_of)
    person = conclusions(facts, identity).get(canonical_key(res_name))
    if person is None:
        return str(t("cli.facts.explain.nothing_folded", res_name=res_name))
    mine = set(person.personas)
    by_record: dict[tuple[object, ...], Record] = {}
    for record in facts.records():
        if any(a.subject in mine for a in record.assertions):
            by_record[record.assertions[0].cite.record_id] = record

    profile = gen.canonical_profiles().get(res_name)
    lines = [str(t("cli.facts.explain.person", name=profile_name(profile) if profile is not None else res_name,
                   res_name=res_name, appearances=t("counted.appearances", count=len(mine)),
                   in_records=t("counted.in_records", count=len(by_record))))]
    # In time order, as a life is read: the record's year, then its citation.
    for record in sorted(by_record.values(),
                         key=lambda r: (r.assertions[0].cite.year or 0,
                                        r.assertions[0].cite.sort_key)):
        here = [a for a in record.assertions
                if a.subject in mine
                or (isinstance(a, Relational) and a.other in mine)]
        c = next(a.cite for a in here if a.subject in mine)
        page = str(t("cli.facts.leaf", page=c.page)) if c.page else ""
        lines.append("")
        lines.append(f"{c.year} · {c.record_kind} · {c.source_file} "
                     f"{record_number(c)}{page} · {c.locator}")
        render = functools.partial(_render, record)
        lines += ["    " + line for a in here
                  for line in why(a, render=render).splitlines()]
    return "\n".join(lines)


def _render(record: Record, a: Assertion) -> str:
    who = _name_of(record, a.subject)
    payload = a.payload
    if isinstance(a, Relational):
        payload = _name_of(record, a.other)
    elif isinstance(a, NameClaim):
        payload = " ".join(str(x) for x in (a.surname, a.given, a.patronymic) if x)
    return f"{type(a).__name__}({who} → {payload})"


def _name_of(record: Record, who: Persona) -> str:
    claims = [a for a in record.about(who) if isinstance(a, NameClaim) and a.given]
    return display_name(claims[0]) if claims else str(who)


# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--village", required=True)
    ap.add_argument("--kind", choices=("birth", "marriage", "death", "census",
                                       "list", "external", "divorce"),
                    default="birth")
    ap.add_argument("--join", choices=sorted(JOINS), default=None,
                    help="which two predicates to join (default: the kind's own)")
    ap.add_argument("--min-count", type=int, default=2)
    ap.add_argument("--require-surname", action="store_true",
                    help="drop pairs with no surname on one side — they cannot "
                         "distinguish families and are most of the raw output")
    ap.add_argument("--loose-only", action="store_true",
                    help="only pairs with at least one record that still stands "
                         "as its own profile, unnamed by the consolidation config "
                         "— the actionable backlog")
    ap.add_argument("--state", action="store_true",
                    help="add a Geni /merge/compare URL per pair from terraform "
                         "state (best effort)")
    ap.add_argument("--kin-guard", action="store_true",
                    help="drop a pair the record itself already relates")
    ap.add_argument("--matching-base", action="store_true",
                    help="fold names the sweep's way (Егоръ ≡ Георгій)")  # i18n: content — the names it folds, as an example
    ap.add_argument("--dump", action="store_true", help="→ <village>/facts.jsonl")
    ap.add_argument("--basis-census", action="store_true")
    ap.add_argument("--why", metavar="YEAR:NUM")
    ap.add_argument("--why-person", metavar="RES_NAME",
                    help="everything the records say about one canonical, "
                         "record by record, with each claim's basis")
    ap.add_argument("--check",
                    choices=FACTS_CHECKS,
                    help="a cross-record rule, which reads more than one kind")
    ap.add_argument("--min-gap", type=float, default=0.0, metavar="YEARS",
                    help="birth-claims: only people whose widest gap is at least this")
    args = ap.parse_args(argv)

    village_dir = village_path(args.village)
    if not village_dir.is_dir():
        print(f"error: village dir not found: {village_dir}", file=sys.stderr)
        return 2

    if args.why_person:
        print(explain_person(*consolidated_facts(village_dir), args.why_person))
        return 0
    if args.check == "identity":
        report, code = identity_census(village_dir)
        print(report)
        return code
    if args.check == "date-order":
        report, code = date_order(village_dir)
        print(report)
        return code
    if args.check == "death-claims":
        report, code = death_claims_report(village_dir)
        print(report)
        return code
    if args.check == "father-claims":
        report, code = father_claims_report(village_dir)
        print(report)
        return code
    if args.check == "name-days":
        report, code = name_days_report(village_dir)
        print(report)
        return code
    if args.check == "wedding-calendar":
        report, code = wedding_calendar_report(village_dir)
        print(report)
        return code
    if args.check in ("baptism-lag", "burial-lag"):
        report, code = lags_report(village_dir, args.check.removesuffix("-lag"))
        print(report)
        return code
    if args.check in ("posthumous-birth", "children-span"):
        report, code = parenthood_report(village_dir, args.check)
        print(report)
        return code
    if args.check == "wedding-ages":
        report, code = wedding_ages_report(village_dir)
        print(report)
        return code
    if args.check == "parent-age-drift":
        report, code = parent_age_drift_report(village_dir)
        print(report)
        return code
    if args.check == "parent-ages":
        report, code = parent_ages_report(village_dir)
        print(report)
        return code
    if args.check == "birth-claims":
        report, code = birth_claims(village_dir, min_gap_years=args.min_gap)
        print(report)
        return code

    if args.dump or args.basis_census or args.why:
        return _side_channel(village_dir, args)
    if args.kind == "divorce":
        print(t("cli.facts.kind_answers_no_pairs", kind=args.kind), file=sys.stderr)
        return 2

    # One translation feeds both the assertions and the bridge that says which
    # of them still stand as a profile of their own: the join key is the DSL
    # object, so the two readers must share one walk.
    everything, gen, slots = consolidated_facts(village_dir)
    facts = AssertionSet(a for a in everything if a.cite.record_kind == args.kind)
    config = village_dir / "generate_config_names.py"
    index = LooseIndex(gen, slots, config.read_text() if config.is_file() else "")

    join = args.join or {"birth": "parent×godparent",
                         "marriage": "witness×witness",
                         "death": "parent×parent",
                         "census": "parent×parent",
                         "list": "parent×parent",
                         "external": "parent×parent"}[args.kind]
    fold = matching_fold if args.matching_base else canonical_fold
    groups = run(facts, min_count=args.min_count, fold=fold,
                 kin_guard=args.kin_guard, join=join)
    if args.require_surname:
        groups = [g for g in groups
                  if _identifiable([(o, o.left) for o in g.occurrences])
                  and _identifiable([(o, o.right) for o in g.occurrences])]
    if args.loose_only:
        groups = [g for g in groups if any(index.is_loose(o.right) for o in g.occurrences)]

    left_label, right_label = join.split("×")
    slot_label = "gp" if right_label == "godparent" else right_label[0]
    unit = {"birth": "births", "marriage": "weddings", "death": "burials",
            "census": "households", "list": "lists",
            "external": "cards"}[args.kind]
    print(format_report(groups, args.min_count, index,
                        labels=(left_label, right_label, slot_label), unit=unit,
                        compare=state_compare(village_dir) if args.state else None))
    return 0


def _side_channel(village_dir: Path, args: argparse.Namespace) -> int:
    """`--dump`, `--basis-census`, `--why`: one kind's assertions, no translation."""
    facts = load(village_dir, args.kind)
    if args.dump:
        path = village_dir / "facts.jsonl"
        print(t("cli.facts.dumped", count=dump(facts, path), path=path), file=sys.stderr)
        return 0
    if args.basis_census:
        print(basis_census(facts))
        return 0
    print(explain(facts, args.why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
