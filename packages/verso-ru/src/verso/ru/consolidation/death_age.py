#!/usr/bin/env python3
"""Flag a death record whose stated age disagrees with a birth record of the
same child in the same village.

The third date check, and the only one that compares TWO records rather than
one profile against itself:

* `date_order`   — events inside ONE profile (крещение раньше рождения);
* `age_conflicts` — a parent's age at a child's birth;
* `death_age`    — the age a burial states against the birth the corpus holds.

**Why it exists.** The unit of a ч.3 age is a per-дело convention, not a
fact of the fond, and it is read off the scan by eye. One book documents «a bare
number means years» for its later years — and an earlier book breaks it: a child
carries a bare «4» four months after his own christening in the same book. The
same proofread corrected a burial read «1 мес» that is «11 мѣс» on the scan (a
girl born in September, buried in July of the next year). Both are invisible to
a reader working one record at a time and obvious the moment the two records are
put side by side.

**What it does NOT do.** It does not guess identity from names alone: a death
record is paired with a birth only when the child's given name AND the named
parent both match, which is the same structural bar `union_duplicates` uses.
Scribes round ages generously — five and a half months for five months nine
days — so the tolerance is deliberately loose: this hunts unit confusion and
gross misreadings, not the ordinary slop of a parish clerk.

Read-only and network-free: it reads the DSL, not terraform state. The
comparison itself is the facts layer's (`find_death_age_conflicts`); this
module keeps the loader, the report and the helpers its neighbours share.

Run:
    python3 -m verso.ru.consolidation.death_age --village "Глуповы Горы"
    python3 -m verso.ru.consolidation.death_age --village "Горюхино" --json
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from verso.ru.ages import DAYS_PER_MONTH, DAYS_PER_YEAR
from verso.ru.dsl.records.reviewed import admitted
from verso.ru.facts.checks.stated_age import (
    DEFAULT_TOLERANCE_DAYS, DEFAULT_TOLERANCE_FRACTION, NAMESAKE_RATIO, stated_age_findings)
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.model import AgedYears, AssertionSet
from verso.ru.naming import matching_base
from verso.ru.relationship import Relationship, Relative
from verso.ru.messages import t

# «4» meaning four months read as four years is off by exactly this factor, and
# saying so in the report turns a number into a diagnosis.
MONTHS_PER_YEAR = 12
#: How near the ratio of the time lived to the stated age must come to twelve (or to a twelfth), as a share of
#: it, for a finding to be called an age read in the wrong unit.
UNIT_RATIO_TOLERANCE = 0.25

# The kinships under which a burial's relative can be the deceased's PARENT —
# the only kin a birth record names, so the only ones that pair a burial with a
# birth or file the deceased among a couple's children. A wife's burial names
# her husband, and he is the father in their children's births: pairing on him
# set a woman of fifty, buried years after her daughter's birth, against that
# birth.
#
# An UNSET relationship stays in. A dozen entries fill the relative slot and
# leave `relationship=` empty — the entry names kin and declines to say which —
# and some of those are fathers. `verso.ru.facts.extract.deaths` reads them the
# same way.
PARENT_RELATIONSHIPS: frozenset[Relationship | None] = frozenset(
    {Relationship.FATHER, Relationship.MOTHER, None})


def parents_named(rec) -> list[Relative]:
    """The relatives a death record names who may be the deceased's parents."""
    return [r for r in getattr(rec, "relatives", None) or []
            if r.relationship in PARENT_RELATIONSHIPS]


def _norm(s: str | None) -> str:
    """Fold a name for comparison: case, ё, and surrounding space."""
    return (s or "").strip().lower().replace("ё", "е")  # i18n: content — a letter folded


@dataclass(frozen=True)
class PersonKey:
    """Given name + patronymic, with the surname kept apart.

    The surname is compared only when BOTH sides carry one. A revision list
    records no surnames at all, so a canonical built from one has a bare
    name+patronymic while a later metric book names the same man WITH the
    podvorye surname — the asymmetry `name_variants` was written for.
    """
    name: str
    patronymic: str
    surname: str
    # The spelling the scribe used. Excluded from equality and hashing on
    # purpose: it must not split «Егоръ» from «Георгій» when these keys are
    # used to group a household, but every report has to show the reader the
    # form they will find in the DSL, not the fold.
    written: str = field(default="", compare=False)

    @property
    def display(self) -> str:
        return self.written or self.name

    def matches(self, other: PersonKey) -> bool:
        if not self.name or not other.name or self.name != other.name:
            return False
        # A missing patronymic on either side is not evidence of difference:
        # a child in a birth record carries none at all.
        if self.patronymic and other.patronymic and self.patronymic != other.patronymic:
            return False
        if self.surname and other.surname and self.surname != other.surname:
            return False
        return True


def person_key(p) -> PersonKey | None:
    """Identity for comparison — the name FOLDED to its base form.

    The DSL keeps the spelling the scribe used, so one man is «Егоръ Петровъ»
    in one book and «Георгій Петровъ» in another, and «Алексѣй» in one year
    and «Алексій» in the next. Comparing the written forms makes every such man
    two people, which is how these checks under-reported until 2026-09-05.
    `matching_base` folds through the «Имя-основа» column of names.csv; it is a
    comparison key and is never written anywhere.
    """
    if p is None:
        return None
    written = (getattr(p, "name_modern", None) or "").strip()
    if not written:
        return None
    folded = _norm(matching_base(written, getattr(p, "gender", None)))
    if not folded:
        return None
    return PersonKey(
        name=folded,
        patronymic=_norm(getattr(p, "patr_modern", None)),
        surname=_norm(getattr(p, "last_name_modern", None)
                      or getattr(p, "birth_last_name_modern", None)),
        written=_norm(written),
    )


def as_date(year: int | None, month, day) -> date | None:
    """A record's (year, month, day) as a date, defaulting to mid-period.

    A record dated only to the year is still worth comparing — it pins the age
    to within a year, which is far tighter than the errors this check hunts.
    """
    if not year:
        return None
    m = int(month) if month else 7
    d = int(day) if day else 15
    try:
        return date(year, m, min(d, 28))
    except ValueError:
        return None


@dataclass(frozen=True)
class BirthFact:
    key: PersonKey
    parents: tuple[PersonKey, ...]
    born: date
    year: int
    record_num: str
    source: str


@dataclass(frozen=True)
class DeathAgeFinding:
    kind: str
    confidence: str
    child: str
    parent: str
    death_year: int
    death_record: str
    death_source: str
    birth_year: int
    birth_record: str
    birth_source: str
    stated_age: str
    stated_days: float
    stated_days_max: float
    elapsed_days: float
    gap_days: float
    hint: str


def _display(p) -> str:
    if p is None:
        return "?"
    bits = [getattr(p, "name_modern", None), getattr(p, "patr_modern", None),
            getattr(p, "last_name_modern", None)]
    return " ".join(b for b in bits if b) or "?"


def collect_births(birth_record_sets) -> list[BirthFact]:
    facts: list[BirthFact] = []
    for records, source in birth_record_sets:
        for rec in records.records:
            # The newborn as the book writes him (В10): a patronymic made of «Иванъ» would part him from his
            # burial, whose father the book spells «Іоаннъ».
            written = getattr(rec, "written_child", None)
            child = person_key(written() if written is not None else getattr(rec, "child", None))
            if child is None:
                continue
            year = getattr(rec, "year", None) or records.year
            born = as_date(year, getattr(rec, "b_month", None), getattr(rec, "b_day", None))
            if born is None:
                continue
            parents = tuple(k for k in (person_key(getattr(rec, "father", None)),
                                        person_key(getattr(rec, "mother", None))) if k)
            if not parents:
                continue
            facts.append(BirthFact(
                key=child, parents=parents, born=born, year=year,
                record_num=str(getattr(rec, "record_num", "") or "?"), source=source))
    return facts


def _unit_hint(stated: float, elapsed: float) -> str:
    """Name the failure when the two ages differ by a whole unit of measure."""
    if elapsed <= 0:
        return ""
    ratio = stated / elapsed
    if abs(ratio - MONTHS_PER_YEAR) <= MONTHS_PER_YEAR * UNIT_RATIO_TOLERANCE:
        return str(t("consolidation.death_age.hint.years_for_months"))
    if abs(ratio - 1.0 / MONTHS_PER_YEAR) <= UNIT_RATIO_TOLERANCE / MONTHS_PER_YEAR:
        return str(t("consolidation.death_age.hint.months_for_years"))
    if stated < elapsed and elapsed - stated >= 240:
        return str(t("consolidation.death_age.hint.tens_unread"))
    return str(t("consolidation.death_age.hint.disagrees"))


def _entries(record_sets) -> list[tuple[object, str, object]]:
    """(record, source, book) for every entry, in the order the books give them.

    Each entry is dated by its book when it omits the year — the contract
    `verso.ru.cli.facts` applies when it loads a village, and the one this check
    always read (`rec.year or records.year`)."""
    out = []
    for records, source in record_sets:
        for rec in records.records:
            if getattr(rec, "year", None) is None:
                rec.year = records.year
            out.append((rec, source, records))
    return out


def find_death_age_conflicts(
        birth_record_sets,
        death_record_sets,
        *,
        tolerance_days: float = DEFAULT_TOLERANCE_DAYS,
        tolerance_fraction: float = DEFAULT_TOLERANCE_FRACTION,
        min_gap_days: float = 0.0,
) -> list[DeathAgeFinding]:
    """Burials whose stated age no birth of the same child can account for.

    The comparison is the facts layer's: the records are read into
    assertions (`BornOn`, `AgedYears`, the parent links) and handed to
    `verso.ru.facts.rules.stated_age` through `verso.ru.facts.checks.stated_age`,
    which names no predicate and never sees a record. This function only
    reads the entries and draws the report — who is compared, which birth
    fits best, what the gap is and how confident, all come from there.

    Until 2026-09-28 the same comparison lived here a second time, and the two
    had to be kept in step by hand: a namesake burial and «pair only through a
    parent» were each fixed in both. One implementation cannot drift.
    """
    births = _entries(birth_record_sets)
    deaths = _entries(death_record_sets)
    # Only a death record states a burial's age. A birth entry's ages (a parent's
    # in a civil act, a christening's) are no burial's, and a finding on one
    # would index a death record that is not there.
    facts = AssertionSet(
        [a for a in facts_from_births([(rec, src) for rec, src, _ in births],
                                      village="", slots=None)
         if not isinstance(a, AgedYears)]
        + list(facts_from_deaths([(rec, src) for rec, src, _ in deaths],
                                 village="", slots=None)))
    found = stated_age_findings(facts, tolerance_days=tolerance_days,
                                tolerance_fraction=tolerance_fraction)

    findings: list[tuple[int, DeathAgeFinding]] = []
    for d in found:
        # The citation's entry is the position in the list handed to the
        # extractor, which is how a finding finds its record again.
        rec, source, _ = deaths[d.cite.entry]
        born, born_source, _ = births[d.origin.cite.entry]
        parents = parents_named(rec)
        findings.append((d.cite.entry, DeathAgeFinding(
            kind="stated_age_vs_birth",
            confidence=d.confidence,
            child=_display(getattr(rec, "deceased", None)),
            parent=_display(parents[0].person) if parents else "?",
            death_year=getattr(rec, "year", 0) or 0,
            death_record=str(getattr(rec, "record_num", "") or "?"),
            death_source=source,
            birth_year=getattr(born, "year", 0) or 0,
            birth_record=str(getattr(born, "record_num", "") or "?"),
            birth_source=born_source,
            stated_age=str(getattr(rec, "age", "")),
            stated_days=d.stated_low,
            stated_days_max=d.stated_high,
            elapsed_days=d.elapsed,
            gap_days=round(d.gap, 1),
            hint=_unit_hint(d.stated_low, d.elapsed),
        )))
    # The order the burials were read in, then HIGH first and the widest
    # disagreement first: an only child whose two records are years apart is
    # a reading to fix, a reused name is a household to read, and a month of
    # slack is neither.
    findings.sort(key=lambda pair: pair[0])
    out = [f for _, f in findings]
    out.sort(key=lambda f: (f.confidence != "HIGH", -f.gap_days))
    return [f for f in out if f.gap_days >= min_gap_days]


def _human(days: float) -> str:
    if days < 60:
        return str(t("consolidation.death_age.days", n=days))
    if days < 400:
        return str(t("consolidation.death_age.months", n=days / DAYS_PER_MONTH))
    return str(t("consolidation.death_age.years", n=days / DAYS_PER_YEAR))


def _span(low: float, high: float) -> str:
    """The interval an age asserts, in one unit so the two ends are comparable."""
    if high <= low:
        return _human(low)
    unit, name = ((DAYS_PER_YEAR, t("consolidation.death_age.unit.years")) if low >= 400
                  else (DAYS_PER_MONTH, t("consolidation.death_age.unit.months")) if low >= 60
                  else (1.0, t("consolidation.death_age.unit.days")))
    return f"{low / unit:.1f}–{high / unit:.1f} {name}"


def format_report(findings: list[DeathAgeFinding]) -> str:
    if not findings:
        return ("death-age-check: OK — 0 findings "
                "(no burial age contradicts a birth record of the same child).")
    high = sum(1 for f in findings if f.confidence == "HIGH")
    lines = [f"death-age-check: {len(findings)} finding(s) — {high} HIGH, "
             f"{len(findings) - high} LOW\n"]
    for f in findings:
        lines.append(str(t("consolidation.death_age.child", confidence=f.confidence, child=f.child, parent=f.parent)))
        lines.append(str(t("consolidation.death_age.birth", year=f.birth_year, record=f.birth_record,
                           source=f.birth_source)))
        lines.append(str(t("consolidation.death_age.death", year=f.death_year, record=f.death_record,
                           source=f.death_source)))
        lines.append(str(t("consolidation.death_age.stated", stated=f.stated_age,
                           span=_span(f.stated_days, f.stated_days_max), elapsed=_human(f.elapsed_days),
                           gap=_human(f.gap_days))))
        lines.append(f"  → {f.hint}\n")
    lines.append(str(t("consolidation.death_age.low", ratio=NAMESAKE_RATIO)))
    lines.append(str(t("consolidation.death_age.signal")))
    return "\n".join(lines)


def findings_to_json(findings: list[DeathAgeFinding]) -> str:
    return json.dumps([f.__dict__ for f in findings], ensure_ascii=False, indent=2)


def _reviewed_only(book):
    """The book with its unreviewed entries left out, the original untouched.

    An entry transcribed and not yet checked against the scan (`reviewed=False`)
    asserts nothing anywhere else in the pipeline — the translator mints no
    profile for it and the facts layer extracts nothing from it — so it must
    not argue with a birth or a burial here either.
    """
    kept = [r for r in book.records if admitted(r)]
    if len(kept) == len(book.records):
        return book
    trimmed = copy.copy(book)
    trimmed.records = kept
    return trimmed


def load_village_records(village_dir: Path):
    """(birth sets, death sets) for a village, each item a (records, source) pair.

    Unreviewed entries are left out (`_reviewed_only`), unless the village's
    ratchet lists them as already on Geni (`admit_listed`)."""
    from verso.core.pipeline.load import admit_listed, load_module
    from verso.ru.dsl.kinds import SOURCE_PATTERNS
    from verso.core import ratchet
    from verso.ru.dsl.records.births import BirthRecords
    from verso.ru.dsl.records.deaths import DeathRecords
    from verso.core.records.sets import record_sets

    listed = ratchet.by_file(ratchet.read_list(village_dir / ratchet.LIST_FILE))

    def collect(pattern: str, expected):
        found = []
        for path in sorted(village_dir.glob(pattern)):
            try:
                mod, name = load_module(path), path.stem
            except Exception as exc:  # a broken year must not hide the rest
                print(f"WARNING: failed to load {path}: {exc}", file=sys.stderr)
                continue
            admit_listed(path, village_dir, mod, listed)
            source = str(path.relative_to(village_dir))
            obj = getattr(mod, name, None)
            if isinstance(obj, expected):
                found.append((_reviewed_only(obj), source))
                continue
            for value in record_sets(vars(mod), expected).values():
                found.append((_reviewed_only(value), source))
        return found

    return (collect(SOURCE_PATTERNS[0], BirthRecords),
            collect(SOURCE_PATTERNS[2], DeathRecords))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag a burial whose stated age contradicts the birth "
                    "record of the same child.")
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--tolerance-days", type=float, default=DEFAULT_TOLERANCE_DAYS,
                    help=f"absolute slack in days (default {DEFAULT_TOLERANCE_DAYS:g})")
    ap.add_argument("--tolerance-fraction", type=float, default=DEFAULT_TOLERANCE_FRACTION,
                    help=f"relative slack (default {DEFAULT_TOLERANCE_FRACTION:g})")
    ap.add_argument("--min-gap-days", type=float, default=0.0,
                    help="report only disagreements at least this wide, in days "
                         "— the triage knob for a corpus with many years read")
    args = ap.parse_args(argv)

    births, deaths = load_village_records(Path(args.village))
    findings = find_death_age_conflicts(
        births, deaths,
        tolerance_days=args.tolerance_days,
        tolerance_fraction=args.tolerance_fraction,
        min_gap_days=args.min_gap_days)
    print(findings_to_json(findings) if args.json else format_report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
