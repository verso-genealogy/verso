#!/usr/bin/env python3
"""Proactively find consolidation candidates — for the persons of one year's
record type (`--tf-file terraform/geni/mk_1840_birth.tf`, or `--year 1840
--type birth`), or for the whole village (`--sweep`, `verso candidates --sweep`).

The existing `verso.ru.consolidation.detector` is *reactive* — it only groups
`geni_profile` resources once Terraform already shows them sharing one Geni id
(i.e. after a merge happened on Geni). This tool is *proactive*: for every
target person it searches for the same individual **locally** (across all
years/record-types in our own DSL).

Local matching is the default and the real signal. Geni is OPT-IN via
`--geni-matches`, which uses Geni's tree-match engine (`matches for-profile`)
for targets already in state. We deliberately do NOT use `geni profile search`:
since we manage this tree, name search returns mostly our own profiles +
duplicates + namesakes with no family-graph corroboration — empirically noise.

The decisive signal is the **family graph**, not the name. Name+patronymic
alone over-matches: two namesakes of one village share a name and a
patronymic as often as not. So scoring is *relative-aware*: a shared spouse is near-decisive, a
shared parent/child strongly boosts, and a name-only match with no relative,
surname, or date corroboration is capped at LOW confidence ("name-only —
verify") and never auto-drafted.

Pipeline:
  1. Translate the village once (`translate_village`) and read per-person
     *occurrences* (one per record role = one `geni_profile`) from the SAME
     record objects the translator read, each placed on the profile it minted
     for that object (`profile_minted_for`) — no res_name is parsed, and a
     village without a generated tree (Заманиловка) is placed like any other.
  2. Target set = the persons of the requested year × record type, or everyone.
  3. Skip persons already merged in `generate_config_names.py`.
  4. For each target, gather same-block local candidates and score them on
     relative overlap (+ surname / date / gender corroboration).
  5. (opt-in `--geni-matches`) attach Geni tree-match candidates per target.
  6. Emit `<village>/<base>.candidates.json` + a human-readable preliminary
     report, and `<village>/<base>_consolidation_report.md` with a draft.

`--synthesize <verdicts.json>` re-reads the candidates plus AI verdicts and
writes the final `<base>_consolidation_report.md` + ready-to-paste
`profiles_to_consolidate` draft entries. This tool never edits config files.

Run:
    python3 -m verso.ru.consolidation.candidates --village Горюхино --sweep
    python3 -m verso.ru.consolidation.candidates --village Горюхино --tf-file terraform/geni/mk_1840_birth.tf
    python3 -m verso.ru.consolidation.candidates --village Горюхино --year 1840 --type birth --geni-matches
"""
from __future__ import annotations

import argparse
import collections
import datetime
import difflib
import itertools
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verso.ru.dsl.records.births import BirthRecords
from verso.ru.dsl.records.census import CensusRecords, CensusRole
from verso.ru.dsl.records.marriages import MarriageRecords
from verso.ru.dsl.records.deaths import DeathRecords
from verso.ru.dsl.records.reviewed import admitted
from verso.ru.domain import Person
from verso.core.tools import tool
from verso.ru.gender import Gender
from verso.ru.naming import feminize_surname, degenitivize_surname, modernize_orthography
from verso.ru.naming.transliteration import generate_res_name
from verso.ru.ages import split_age as _split_age
from verso.ru.ages import age_bounds
from verso.ru.facts.checks.stated_age import (
    DEFAULT_TOLERANCE_DAYS, DEFAULT_TOLERANCE_FRACTION)

# Ceiling on the slack allowed between a burial's stated age and the time
# actually lived. It is the flat ±1 year the interval reading replaced: that
# tolerance was far too loose for an infant and about right for a child, so the
# interval tightens the one end without letting the other drift.
_MAX_AGE_SLACK_DAYS = 365.25

PLACEHOLDER_NAMES = {"?", "[имя]", "", None}  # i18n: content — the placeholder the DSL writes for an unread name

# A relative naming more occurrences than this is too common to discriminate
# («Иван Иванов» as a father), so it is not used as a blocking key. Skips are
# counted and reported — never silently dropped.
REL_FANOUT_MAX = 200

# Person identity key = (canonical given name, canonical patronymic).
# Surname-agnostic on purpose — surnames vary/are omitted in the books, and
# relatives carry the discriminating weight. The same key as
# `verso.ru.facts.identity.name_identity(canonical_fold)`.
PersonKey = tuple


def person_key(p: Person | None) -> PersonKey | None:
    if p is None:
        return None
    try:
        given = p.get_canonical_name()
    except Exception:
        given = p.name_modern
    if not given or given in PLACEHOLDER_NAMES:
        return None
    return (given, p.patr_modern)


def _surname(p: Person | None) -> str | None:
    if p is None:
        return None
    return p.last_name_modern or getattr(p, "birth_last_name_modern", None)


def surnames_match(a: str | None, b: str | None) -> bool:
    """Tolerant surname comparison across gender/genitive/orthography variants.

    Also collapses the soft sign (Пузыркин ~ Пузырькин): the books spell the same
    surname both ways, and none of modernize_orthography / feminize_surname /
    degenitivize_surname touch a medial ь."""
    if not a or not b:
        return False

    def variants(s: str) -> set[str]:
        s = modernize_orthography(s)
        out = {s, feminize_surname(s), degenitivize_surname(s)}
        out.add(degenitivize_surname(feminize_surname(s)))
        out |= {v.replace("ь", "") for v in list(out) if v}  # i18n: content — a letter folded
        return {v for v in out if v}

    return bool(variants(a) & variants(b))


# --------------------------------------------------------------------------- #
# Occurrence model: one per (record, role) = one geni_profile resource
# --------------------------------------------------------------------------- #

@dataclass
class Occurrence:
    key: PersonKey               # (canonical given, patr_modern)
    name: str                    # display FIO
    given: str
    patr: str | None
    surname: str | None
    gender: str | None
    rec_type: str                # birth | marriage | death
    record_num: object
    role: str                    # child/father/mother/god_parent_N/groom/bride/...
    year: int | None
    source_file: str
    parents: set[PersonKey] = field(default_factory=set)
    spouses: set[PersonKey] = field(default_factory=set)
    children: set[PersonKey] = field(default_factory=set)
    other_rel: set[PersonKey] = field(default_factory=set)
    birth_date: tuple[int | None, int | None, int | None] | None = None  # (y, m, d) where derivable
    death_date: tuple[int | None, int | None, int | None] | None = None
    # A death record's `b_day`/`b_month` are the BURIAL, not the birth — the
    # same attribute names mean the birth in a birth record, which is how a
    # burial once ended up filed as `birth_date`.
    burial_date: tuple[int | None, int | None, int | None] | None = None
    age: float | str | None = None  # death-record age (for infant born-and-died span check)
    residence: str | None = None
    stub: str | None = None      # the geni_profile res_name the translator minted
    # Census only: the сказка records this member as gone since the previous
    # revision (departure_year/departure_reason, usually «умер»). Such an entry
    # may legitimately post-date the person's own death record.
    departed: bool = False
    # Census only: where a departing member went. Always ANOTHER settlement —
    # a woman «выдана замуж в том же селе» carries a departure_reason but no
    # destination. After this, no later record of our parish is her.
    destination: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name, "given": self.given, "patr": self.patr,
            "surname": self.surname, "gender": self.gender,
            "rec_type": self.rec_type, "record_num": self.record_num,
            "role": self.role, "year": self.year, "source_file": self.source_file,
            "parents": sorted(f"{g} {p or ''}".strip() for g, p in self.parents),
            "spouses": sorted(f"{g} {p or ''}".strip() for g, p in self.spouses),
            "children": sorted(f"{g} {p or ''}".strip() for g, p in self.children),
            "birth_date": self.birth_date, "death_date": self.death_date,
            "burial_date": self.burial_date,
            "age": self.age, "residence": self.residence, "stub": self.stub,
        }


#: The res_name the translator minted for a DSL person object, or None.
StubOf = Callable[[Any], str | None] | None


def _make_occ(p: Person | None, *, rec_type, record_num, role, year,
              source_file, stub_of: StubOf = None) -> Occurrence | None:
    # `person_key(None)` already returns None, so the explicit check below is
    # redundant at runtime — it just states the correlation the reads after it
    # depend on (a non-None key implies a non-None person).
    if p is None:
        return None
    k = person_key(p)
    if k is None:
        return None
    g = p.gender
    return Occurrence(
        key=k, name=(p.get_fio() or "?"), given=k[0], patr=k[1],
        surname=_surname(p), gender=(g.value if isinstance(g, Gender) else g),
        rec_type=rec_type, record_num=record_num, role=role, year=year,
        source_file=source_file, residence=p.residence,
        stub=stub_of(p) if stub_of is not None else None,
    )


def _rel_buckets(rel_list, subject_occ: Occurrence):
    """Fold a record's `relatives=[Relative(...)]` into the subject's buckets."""
    from verso.ru.relationship import Relationship
    for rel in rel_list or []:
        rk = person_key(rel.person)
        if rk is None:
            continue
        r = rel.relationship
        if r in (Relationship.FATHER, Relationship.MOTHER,
                 Relationship.FOSTER_FATHER, Relationship.FOSTER_MOTHER):
            subject_occ.parents.add(rk)
        elif r in (Relationship.HUSBAND, Relationship.WIFE):
            subject_occ.spouses.add(rk)
        elif r in (Relationship.SON, Relationship.DAUGHTER):
            subject_occ.children.add(rk)
        else:
            subject_occ.other_rel.add(rk)


def _reviewed(entry) -> bool:
    """An entry (or двор) not yet checked against the scan mints no profile —
    the translator skips it — so it yields no occurrence either."""
    return admitted(entry)


def extract_occurrences(records, source_file: str,
                        stub_of: StubOf = None) -> list[Occurrence]:
    """All person-occurrences (one per emitted geni_profile) from one records
    container. Builds relative sets from the record's own structure. `stub_of`
    places each on the profile the translator minted for that very object
    (`TerraformGenerator.profile_minted_for`) — asked, never rebuilt."""
    occs: list[Occurrence] = []
    if isinstance(records, BirthRecords):
        for b in records.records:
            if not _reviewed(b):
                continue
            year = b.year if b.year is not None else records.year
            ck = person_key(b.child)
            fk = person_key(b.father)
            mk = person_key(b.mother)
            child = _make_occ(b.child, rec_type="birth", record_num=b.record_num,
                              role="child", year=year, source_file=source_file, stub_of=stub_of)
            if child:
                if fk:
                    child.parents.add(fk)
                if mk:
                    child.parents.add(mk)
                child.birth_date = (year, getattr(b.b_month, "value", None), b.b_day)
                occs.append(child)
            father = _make_occ(b.father, rec_type="birth", record_num=b.record_num,
                               role="father", year=year, source_file=source_file, stub_of=stub_of)
            if father:
                if mk:
                    father.spouses.add(mk)
                if ck:
                    father.children.add(ck)
                occs.append(father)
            mother = _make_occ(b.mother, rec_type="birth", record_num=b.record_num,
                               role="mother", year=year, source_file=source_file, stub_of=stub_of)
            if mother:
                if fk:
                    mother.spouses.add(fk)
                if ck:
                    mother.children.add(ck)
                occs.append(mother)
            for slot, attr in enumerate(("god_parent1", "god_parent2",
                                         "god_parent3", "god_parent4"), start=1):
                gp = getattr(b, attr, None)
                o = _make_occ(gp, rec_type="birth", record_num=b.record_num,
                              role=f"god_parent_{slot}", year=year, source_file=source_file, stub_of=stub_of)
                if o:
                    occs.append(o)
    elif isinstance(records, MarriageRecords):
        for m in records.records:
            if not _reviewed(m):
                continue
            year = m.year if m.year is not None else records.year
            gk = person_key(m.groom)
            bk = person_key(m.bride)
            groom = _make_occ(m.groom, rec_type="marriage", record_num=m.record_num,
                              role="groom", year=year, source_file=source_file, stub_of=stub_of)
            if groom:
                if bk:
                    groom.spouses.add(bk)
                _rel_buckets(m.relatives, groom)
                occs.append(groom)
            bride = _make_occ(m.bride, rec_type="marriage", record_num=m.record_num,
                              role="bride", year=year, source_file=source_file, stub_of=stub_of)
            if bride:
                if gk:
                    bride.spouses.add(gk)
                _rel_buckets(m.relatives, bride)
                occs.append(bride)
            for n in range(1, 7):
                w = getattr(m, f"witness{n}", None)
                o = _make_occ(w, rec_type="marriage", record_num=m.record_num,
                              role=f"witness_{n}", year=year, source_file=source_file, stub_of=stub_of)
                if o:
                    occs.append(o)
    elif isinstance(records, DeathRecords):
        for d in records.records:
            if not _reviewed(d):
                continue
            year = d.year if d.year is not None else records.year
            dec = _make_occ(d.deceased, rec_type="death", record_num=d.record_num,
                            role="deceased", year=year, source_file=source_file, stub_of=stub_of)
            if dec:
                _rel_buckets(d.relatives, dec)
                dec.death_date = (year, getattr(d.d_month, "value", None), d.d_day)
                dec.age = d.age
                # A civil book's second date is the registration, not a burial.
                if (d.b_day is not None or d.b_month is not None) and not getattr(d, "civil", False):
                    dec.burial_date = (year, getattr(d.b_month, "value", None), d.b_day)
                occs.append(dec)
            for n, rel in enumerate(d.relatives or [], start=1):
                o = _make_occ(rel.person, rec_type="death", record_num=d.record_num,
                              role="relative" if n == 1 else f"relative_{n}",
                              year=year, source_file=source_file, stub_of=stub_of)
                if o:
                    occs.append(o)
    elif isinstance(records, CensusRecords):
        occs.extend(_census_occurrences(records, source_file, stub_of))
    return occs


# Census role sets — mirror `_resolve_parent_ref` (census_resolvers.py) and the
# hidden-spouse convention: `ref_member` IS the parent only for child roles; on
# a hidden NON-child-role member it encodes the SPOUSE (widow/mother pairing).
_C_CHILD_ROLES = {CensusRole.SON, CensusRole.DAUGHTER,
                  CensusRole.STEPSON, CensusRole.STEPDAUGHTER}
_C_SIBLING_ROLES = {CensusRole.BROTHER, CensusRole.SISTER,
                    CensusRole.NIECE, CensusRole.NEPHEW, CensusRole.COUSIN}


def _census_display_ids(records) -> list[str]:
    """Mirror the translator's household numbering: an explicit `family_id`
    is used literally and does not advance the numeric counter."""
    out: list[str] = []
    numeric = 0
    for h in records.households:
        if h.family_id:
            out.append(h.family_id)
        else:
            numeric += 1
            out.append(str(numeric))
    return out


def _census_parent_num(m, members_by_num, head_num) -> int | None:
    """The member number of `m`'s in-household parent (translator mirror), or
    None. Child roles with no ref default to the HEAD."""
    pm = getattr(m, "parent_member", None)
    if pm is not None:
        return pm
    rm = m.ref_member
    if m.role in _C_CHILD_ROLES:
        return rm if rm is not None else head_num
    if rm is None:
        return None
    t = members_by_num.get(rm)
    if t is not None and t.is_hidden():
        return rm
    if m.role in _C_SIBLING_ROLES and t is not None:
        tpm = getattr(t, "parent_member", None)
        if tpm is not None:
            return tpm
    return None


def _census_occurrences(records, source_file: str,
                        stub_of: StubOf = None) -> list[Occurrence]:
    """One occurrence per VISIBLE census member (hidden reconstructions are
    used as relationship nodes — their person keys land in relatives' buckets —
    but are not themselves emitted as match targets/candidates)."""
    occs: list[Occurrence] = []
    display_ids = _census_display_ids(records)
    for h, display_id in zip(records.households, display_ids, strict=True):
        if not _reviewed(h):
            continue
        members = list(h.members)
        by_num = {m.number: m for m in members}
        head = next((m for m in members if m.role == CensusRole.HEAD), None)
        head_num = head.number if head else None

        # spouse pairs: WIFE/HUSBAND via ref (default HEAD), plus the hidden
        # ancestor + widow convention (hidden non-child role, ref = spouse)
        spouse_of: dict[int, set[int]] = collections.defaultdict(set)
        pairs: list[tuple[int | None, int | None]] = []
        for m in members:
            if m.role in (CensusRole.WIFE, CensusRole.HUSBAND):
                pairs.append((m.number, m.ref_member if m.ref_member is not None
                              else head_num))
            elif m.is_hidden() and m.role not in _C_CHILD_ROLES \
                    and m.ref_member is not None:
                pairs.append((m.number, m.ref_member))
        for a, b in pairs:
            if a is None or b is None or a == b:
                continue
            # A ref_member pointing outside the household is a DSL data bug
            # (e.g. a parent_member=16 in a 7-member household). Drop the link
            # rather than crash on the dereference below; the census
            # parent-link linter owns the report.
            if a not in by_num or b not in by_num:
                continue
            spouse_of[a].add(b)
            spouse_of[b].add(a)
        # parent links (both parents where the parent's spouse is known).
        # HEAD participates too: with an explicit `parent_member` it is the
        # child of a hidden reconstructed father (the family-5/10/11 shape).
        parent_nums: dict[int, set[int]] = collections.defaultdict(set)
        for m in members:
            p = _census_parent_num(m, by_num, head_num)
            if p is None or p == m.number or p not in by_num:
                continue
            parent_nums[m.number].add(p)
            other = spouse_of.get(p, set())
            # only ONE co-parent is safe to infer; skip when ambiguous
            if len(other) == 1:
                parent_nums[m.number].add(next(iter(other)))

        occ_by_num: dict[int, Occurrence] = {}
        for m in members:
            if m.is_hidden():
                continue
            o = _make_occ(m.person, rec_type="census", record_num=display_id,
                          role=f"member_{m.number}", year=records.year,
                          source_file=source_file, stub_of=stub_of)
            if o is None:
                continue
            o.departed = bool(getattr(m, "departure_year", None)
                              or getattr(m, "departure_reason", None))
            o.destination = getattr(m, "destination", None) or None
            yrs = _age_years(m.age)
            if yrs is not None and records.year:
                o.birth_date = (records.year - int(yrs), None, None)
            occ_by_num[m.number] = o
            occs.append(o)
        for num, o in occ_by_num.items():
            m = by_num[num]
            for s in spouse_of.get(num, ()):
                sk = person_key(by_num[s].person)
                if sk:
                    o.spouses.add(sk)
            for p in parent_nums.get(num, ()):
                pk = person_key(by_num[p].person)
                if pk:
                    o.parents.add(pk)
            for c_num, pnums in parent_nums.items():
                if num in pnums:
                    ck = person_key(by_num[c_num].person)
                    if ck:
                        o.children.add(ck)
    return occs


def load_occurrences(gen: Any) -> list[Occurrence]:
    """Every person-occurrence of the village, read from the SAME record objects
    the translator read (`gen.fed_sources`) and placed on the profile it minted
    for each (`profile_minted_for`).

    Until 2026-09-28 the sweep walked the DSL a second time and then looked for
    each occurrence's profile in the generated `.tf` tree: a regex over
    `resource "geni_profile"` names, a tail regex per record kind (`_mk_…`,
    `_rs|ir_…_family_member`), the year prefix, and a transliterated name token
    rebuilt with `generate_res_name`. Заманиловка has no generated tree, so there
    27 054 of its 27 687 occurrences had no profile and the draft was always
    empty; and a stub the regex resolved wrongly was a wrong fold proposed."""
    out: list[Occurrence] = []
    for name, records in gen.fed_sources:
        out.extend(extract_occurrences(records, Path(name).name,
                                       stub_of=gen.profile_minted_for))
    return out


def by_stub(occs: list[Occurrence], consolidation: Any) -> dict[str, Occurrence]:
    """Each occurrence under the profile it was minted for — and, where the
    config folds it under another spelling (a renamed name token: the config's
    `illarion` for the `ilarion` the translator now mints), under that spelling
    too, so a cluster's `profile_names` reach their records."""
    out: dict[str, Occurrence] = {}
    for o in occs:
        if not o.stub:
            continue
        out[o.stub] = o
        spelled = consolidation.config_name_for(o.stub)
        if spelled and spelled != o.stub:
            out.setdefault(spelled, o)
    return out


def union_child_index(unions: dict[str, Any]) -> dict[str, str]:
    """{child profile res_name: union res_name} from the translated unions —
    children and foster children both, the first union by name where a child
    sits in two. When a record folds into a canonical, the block that needs a
    removed{}/moved{} is the union holding it as a child.

    Read from the translation, not the files it wrote: the HCL regex it
    replaces skipped every res_name with a hyphen in it (a double surname, an
    «843-7-434» дело) — 174 children in Горюхино — and had nothing to read in
    Заманиловка."""
    idx: dict[str, str] = {}
    for name, union in sorted(unions.items()):
        for child in sorted(set(getattr(union, "children", None) or ())
                            | set(getattr(union, "foster_children", None) or ())):
            idx.setdefault(child, name)
    return idx


# --------------------------------------------------------------------------- #
# Already-consolidated awareness
# --------------------------------------------------------------------------- #

def load_consolidated_clusters(village_dir: Path | None = None) -> dict[str, list[str]]:
    """{canonical: [profile_names]} from the village's generate_config_names.

    `village_dir` must be given whenever the process is not already running
    with the village as cwd — otherwise the cwd's config is read, and with none
    there every existing cluster gets re-proposed (a warning says so)."""
    from verso.core.pipeline.config import CONFIG_FILE, village_config

    where = village_dir if village_dir is not None else Path.cwd()
    try:
        gcn = village_config(where)
    except Exception as exc:
        print(f"warning: could not import generate_config_names: {exc}", file=sys.stderr)
        return {}
    if gcn is None:
        print(f"warning: no {CONFIG_FILE} in {where}", file=sys.stderr)
        return {}
    out: dict[str, list[str]] = {}
    for canonical, data in getattr(gcn, "profiles_to_consolidate", {}).items():
        out[canonical] = [n for n in (data.get("profile_names") or [])
                          if isinstance(n, str)]
    return out


def load_consolidated_stubs(village_dir: Path | None = None) -> set[str]:
    """Every per-record stub already folded into a canonical, so we don't
    re-propose merging it."""
    stubs: set[str] = set()
    for canonical, names in load_consolidated_clusters(village_dir).items():
        stubs.add(canonical)
        for n in names:
            stubs.add(n.lstrip("_"))
            stubs.add(n)
    return stubs


# --------------------------------------------------------------------------- #
# Local relative-aware scoring
# --------------------------------------------------------------------------- #

@dataclass
class Scored:
    cand: Occurrence
    score: int
    confidence: str          # high | medium | low
    evidence: list[str]


def keys_compatible(t: Occurrence, c: Occurrence) -> str | None:
    """`"exact"` | `"patronymic-variant"` | None.

    The canonical GIVEN name must always match. The patronymic is allowed to
    differ because the books genuinely disagree about it for one person —
    Агафья Менеевна/Моисеевна, Евдокия Минаевна/Матвеевна, Прасковья
    Сергеевна/Егоровна were each one woman under two patronymics. A variant
    pair is only ever scored when the family graph corroborates it (see
    `score_pair`)."""
    if t.key[0] != c.key[0]:
        return None
    return "exact" if t.key[1] == c.key[1] else "patronymic-variant"


# Roles that only a LIVING person can hold. `relative` is deliberately absent
# («умершего Ксенофонта дочь» names the dead all the time), as are father /
# mother (a posthumous child's record names the dead father).
_ALIVE_ROLES = ("child", "groom", "bride", "god_parent", "witness")


def _implies_alive(o: Occurrence) -> bool:
    if o.rec_type == "census":
        # A сказка enumerates members who died since the previous revision;
        # only an entry WITHOUT a departure note implies a living person.
        return not o.departed
    return o.role.startswith(_ALIVE_ROLES)


def post_death_conflict(t: Occurrence, c: Occurrence) -> bool:
    """True when one occurrence is a death record and the other post-dates it
    while implying the person was still alive — impossible for one person.

    The typical case: a child dead at «полгода», then a living daughter aged 1
    in a сказка taken years later. Same father, same surname, and the
    relative-aware scorer called it HIGH. A death record ends a timeline;
    only a posthumous сказка listing may follow it."""
    for dead_occ, other in ((t, c), (c, t)):
        if dead_occ.rec_type != "death" or dead_occ.role != "deceased":
            continue
        if dead_occ.year is None or other.year is None:
            continue
        if other.year > dead_occ.year and _implies_alive(other):
            return True
    return False


def two_baptisms_conflict(t: Occurrence, c: Occurrence) -> bool:
    """True when both occurrences are the CHILD of a birth record — two
    separate baptismal entries, hence two children.

    A metric book enumerates one baptism per entry, exactly as a сказка
    enumerates one member per line. Two entries are therefore two people even
    when everything else agrees: parents reuse a dead child's given name, and
    the shared-parent bonus alone then scores the pair HIGH.

    The class is large. In one sweep wave it produced 5 of 13 proposals —
    namesake children of one couple born a year or more apart — plus a pair of
    namesakes more than ten years apart, where the two even had different mothers,
    the father having remarried.

    Note this does NOT block the legitimate infant fold: that pairs a birth
    record's `child` with a DEATH record's `deceased`, which the born-and-died
    matcher handles separately."""
    return (t.rec_type == "birth" and c.rec_type == "birth"
            and t.role == "child" and c.role == "child")


def two_burials_conflict(t: Occurrence, c: Occurrence) -> bool:
    """True when both occurrences are the DECEASED of a death record dated
    differently — two burials, hence two namesakes.

    A person is buried once. Часть 3 enumerates one burial per entry exactly
    as часть 1 enumerates one baptism (`two_baptisms_conflict`), so two
    entries on two dates are two people however well the rest agrees — and it
    does agree, because a namesake is usually a relative: same surname, often
    the same father. The shared-parent bonus alone then scores the pair HIGH.

    On one village this was 5 of the 13 auto-drafted clusters, every one of
    them already rejected by hand in the consolidation config
    («человек умирает один раз, это тёзки») — five namesake pairs buried
    years apart.

    Same-date pairs stay eligible: two death records of ONE day may be one
    burial transcribed twice, which is a genuine duplicate. So the gate needs
    positive evidence of two dates — a component the two records both state
    and state differently. A component only one of them records proves
    nothing and is not read as a disagreement.

    Note this does NOT block the legitimate infant fold, which pairs a birth
    record's `child` with a death record's `deceased`, nor a death record's
    `relative` (the bereaved father is named, not buried)."""
    if not (t.rec_type == "death" and c.rec_type == "death"
            and t.role == "deceased" and c.role == "deceased"):
        return False
    return any(a is not None and b is not None and a != b
               for a, b in zip(_burial_date(t), _burial_date(c), strict=True))


def _burial_date(o: Occurrence) -> tuple[int | None, int | None, int | None]:
    """(year, month, day) of the burial, as far as the record states it."""
    y, m, d = o.death_date or (None, None, None)
    return (y if y is not None else o.year, m, d)


# Roles that place the person IN this parish when the record was written.
# Wider than _ALIVE_ROLES: bearing or fathering a child here means living here,
# whereas a birth record may name a father who died before it. `relative` stays
# out — naming an absent woman as someone's kin says nothing about where she is.
_PRESENCE_ROLES = _ALIVE_ROLES + ("mother", "father")


def _implies_presence(o: Occurrence) -> bool:
    if o.rec_type == "census":
        # Being enumerated in the сказка is presence — unless this very entry
        # is the record of leaving.
        return not o.destination
    return o.role.startswith(_PRESENCE_ROLES)


def left_village_conflict(t: Occurrence, c: Occurrence) -> bool:
    """True when one occurrence is a census member recorded as having left for
    another settlement, and the other post-dates it while placing the person in
    our parish.

    The typical case: a woman listed in a revision with destination
    «Брехаловка», «выдана замуж в той же округе» — matched to a bride of a
    later wedding and a wife in a later census. Another member of the same
    household is also «выдана замуж» but stayed in the village, and carries no
    destination: the departure REASON is not the signal, the destination is."""
    for gone, other in ((t, c), (c, t)):
        if gone.rec_type != "census" or not gone.destination:
            continue
        if gone.year is None or other.year is None:
            continue
        if other.year > gone.year and _implies_presence(other):
            return True
    return False


def learn_surname_variants(existing_clusters: dict[str, list[str]],
                           occ_by_stub: dict[str, Occurrence] | None
                           ) -> dict[tuple[str, str], int]:
    """{(surname_a, surname_b): number of clusters holding both}.

    Two surnames of one household are two family names, not spellings of
    one name, so `surnames_match` can never connect them — but a consolidated
    cluster holding both IS the curator's statement that they co-refer. Reading
    that back closes the loop: every merge confirmed teaches the next sweep.

    SURNAMES ONLY, and deliberately so. The given name is the blocking key, so
    teaching it variants would invent candidate pairs; the surname merely
    corroborates a pair the family graph already produced. Measured on
    Горюхино the learned pairs are family-specific — «Михайлович ~
    Онисимович» holds in one family and nowhere else — so they must never gate."""
    out: collections.Counter[tuple[str, str]] = collections.Counter()
    if not occ_by_stub:
        return {}
    for names in existing_clusters.values():
        surnames = {o.surname for n in names
                    if (o := occ_by_stub.get(n)) is not None and o.surname}
        for a, b in itertools.combinations(sorted(surnames), 2):
            if not surnames_match(a, b):   # the rules already cover this pair
                out[(a, b)] += 1
    return dict(out)


def _render_keys(keys: set[PersonKey]) -> str:
    """Render a set of relative keys as evidence — SORTED.

    Every caller passes a set intersection, whose iteration order is salted per
    interpreter. Rendering it raw made two consecutive sweeps of Глуповы Горы
    differ by 62 lines of pure shuffling, which is the whole readable diff a
    scorer change has to be reviewed through."""
    return ", ".join(sorted(f"{g} {p or ''}".strip() for g, p in keys))


def _key_order(k: PersonKey) -> tuple[str, str]:
    """Sort key for a PersonKey. `sorted()` on the tuples themselves raises once
    two share a given name and one has no patronymic (None vs str)."""
    return (k[0], k[1] or "")


def _cand_order(c: Occurrence) -> tuple[str, ...]:
    """Total order over candidates, used to break a tie in the score.

    Records genuinely score the same, and a stable sort then simply preserves
    whatever order the pool was filled in — which, for the sweep, comes out of
    the relative index. Name the order instead of inheriting it.

    This is load-bearing past presentation, because both callers truncate to
    `top_n`: with more tied candidates than slots, the tie-break decides WHICH
    of them the reader sees. That choice used to be re-rolled every run (42 of
    Заманиловка's 3777 targets showed a different tied MEDIUM candidate run to
    run); it is now fixed. Scores, confidences and the drafted HIGH clusters are
    untouched."""
    return (c.stub or "", c.source_file, c.rec_type, str(c.record_num), c.role)


def score_pair(t: Occurrence, c: Occurrence, *,
               allow_patronymic_variant: bool = False,
               surname_aliases: dict[tuple[str, str], int] | None = None) -> Scored | None:
    kind = keys_compatible(t, c)
    if kind is None:
        return None
    if kind == "patronymic-variant" and not allow_patronymic_variant:
        return None
    if t.gender and c.gender and t.gender != c.gender:
        return None
    # Same physical resource? skip (same record + role + type).
    if (t.rec_type, t.record_num, t.role) == (c.rec_type, c.record_num, c.role):
        return None
    # Two members of the SAME census household are distinct individuals by
    # definition (the сказка enumerates them separately) — never merge
    # candidates, even as тёзки with shared parents (e.g. «Иванъ Никитинъ
    # малый», the namesake brother).
    if (t.rec_type == "census" and c.rec_type == "census"
            and t.record_num == c.record_num and t.source_file == c.source_file):
        return None
    # A death record ends the timeline: nothing implying a living person may
    # follow it. Catches the necronym (parents reusing a dead child's name),
    # which family overlap alone scores HIGH.
    if post_death_conflict(t, c):
        return None
    # Two baptismal entries are two children — see two_baptisms_conflict.
    if two_baptisms_conflict(t, c):
        return None
    # Two burial entries on two dates are two namesakes — see
    # two_burials_conflict.
    if two_burials_conflict(t, c):
        return None
    # Likewise once the сказка records her as married out to another
    # settlement: her later life belongs to that parish's books, not ours.
    if left_village_conflict(t, c):
        return None
    score = 0
    ev: list[str] = []
    spouse = t.spouses & c.spouses
    parent = t.parents & c.parents
    child = t.children & c.children
    if spouse:
        score += 100
        ev.append("shared spouse: " + _render_keys(spouse))
    if parent:
        score += 60
        ev.append("shared parent: " + _render_keys(parent))
    if child:
        score += 40
        ev.append("shared child: " + _render_keys(child))
    sn = surnames_match(t.surname, c.surname)
    if sn:
        score += 20
        ev.append(f"surname match: {t.surname} ~ {c.surname}")
    elif surname_aliases and t.surname and c.surname:
        # A surname pair the rules cannot derive but the consolidated clusters
        # already record (two family names of one household). Corroboration only — worth less than
        # a real surname match, and never enough on its own to reach `high`.
        seen = surname_aliases.get((min(t.surname, c.surname), max(t.surname, c.surname)))
        if seen:
            score += 15
            ev.append(f"learned surname variant ({seen} cluster(s)): "
                      f"{t.surname} ~ {c.surname}")
    date_ev = _date_proximity(t, c)
    if date_ev:
        score += date_ev[0]
        ev.append(date_ev[1])

    has_family = bool(spouse or parent or child)

    if kind == "patronymic-variant":
        # The name no longer corroborates — the family graph is carrying the
        # whole pair, so demand it outright.
        if not has_family:
            return None
        ev.insert(0, f"patronymic variant: {t.patr or '—'} vs {c.patr or '—'}")
        if spouse:
            conf = "high"
        else:
            # Half-siblings share a mother but not a patronymic, which looks
            # exactly like this. Never auto-draft it (only `high` reaches
            # draft_config) — a human decides.
            conf = "medium"
            ev.append("half-sibling? — different patronymic, no shared spouse")
        return Scored(cand=c, score=score, confidence=conf, evidence=ev)

    if spouse or (parent and sn) or (child and sn):
        conf = "high"
    elif has_family or (sn and date_ev):
        conf = "medium"
    else:
        conf = "low"
        ev.append("name-only — verify")
    return Scored(cand=c, score=score, confidence=conf, evidence=ev)


def _date_proximity(t: Occurrence, c: Occurrence):
    for attr, label, near in (("birth_date", "birth", 2), ("death_date", "death", 2)):
        a, b = getattr(t, attr), getattr(c, attr)
        if a and b and a[0] and b[0]:
            if abs(a[0] - b[0]) <= near:
                return (15, f"{label} year ≈ ({a[0]} vs {b[0]})")
    return None


def relative_keys(o: Occurrence) -> set[PersonKey]:
    """The person's family graph: everyone they are recorded next to."""
    return o.parents | o.spouses | o.children


def find_local_candidates(target: Occurrence, pool_by_key: dict[Any, list[Occurrence]],
                          consolidated: set[str], top_n: int = 6, *,
                          rel_index: dict[PersonKey, list[Occurrence]] | None = None,
                          fanout_skipped: collections.Counter[PersonKey] | None = None,
                          surname_aliases: dict[tuple[str, str], int] | None = None) -> list[Scored]:
    """Exact-key candidates always; when `rel_index` is given, also pairs that
    share a relative (which is what lets a patronymic variant through).

    `rel_index` maps a relative's PersonKey -> occurrences naming them, and is
    expected to be scoped to one given-name bucket so the pairwise comparison
    stays bounded."""
    pool: list[Occurrence] = list(pool_by_key.get(target.key, []))
    allow_variant = rel_index is not None
    if rel_index is not None:
        seen = {id(o) for o in pool}
        for r in sorted(relative_keys(target), key=_key_order):
            bucket = rel_index.get(r) or []
            if len(bucket) > REL_FANOUT_MAX:
                # A name like «Иван Иванов» as a parent is not discriminating.
                if fanout_skipped is not None:
                    fanout_skipped[r] = len(bucket)
                continue
            for o in bucket:
                if id(o) not in seen:
                    seen.add(id(o))
                    pool.append(o)

    out: list[Scored] = []
    for c in pool:
        if c is target:
            continue
        if c.stub and (c.stub in consolidated or c.stub.lstrip("_") in consolidated):
            continue
        s = score_pair(target, c, allow_patronymic_variant=allow_variant,
                       surname_aliases=surname_aliases)
        if s is not None:
            out.append(s)
    out.sort(key=lambda s: (-s.score, _cand_order(s.cand)))
    return out[:top_n]


# --------------------------------------------------------------------------- #
# Infant born-and-died pairing (birth `child` ↔ death `deceased`, one infant)
# --------------------------------------------------------------------------- #
#
# A child born and died within the parish appears as a birth-`child` profile AND
# a death-`deceased` profile — one person, two resources. The primary person_key
# can't pair them: the deceased is often `person("Мария")` with the patronymic
# auto-derived from the FATHER relative while the birth child carries a different
# (or no) patronymic, so their keys differ. We pair on a patronymic-agnostic
# (given, parent-given) key and gate on age ≈ (death_year − birth_year).

def _age_years(age) -> float | None:
    """Death-record age (Russian text like "8 мес"/"2 года 6 мес", or a number)
    → fractional years, or None if unparseable. Wraps csv_familio._split_age,
    which puts an unparseable value verbatim in slot 0 (so a non-numeric slot 0
    means 'uncheckable')."""
    if age is None:
        return None
    y, m, w, d = _split_age(age)

    def num(x):
        try:
            return float(x) if x else 0.0
        except ValueError:
            return None

    yv = num(y)
    if yv is None:  # verbatim / unparseable
        return None
    return yv + (num(m) or 0.0) / 12 + (num(w) or 0.0) / 52 + (num(d) or 0.0) / 365


def _norm_parents(occ: Occurrence) -> frozenset[PersonKey]:
    """Parent keys normalized to (given, None) — patronymic-agnostic, so a father
    recorded as "Иван" in one record and "Иван Петров" in the other still
    matches."""
    return frozenset((g, None) for (g, _p) in occ.parents)


def infant_keys(occ: Occurrence) -> list[tuple[str, str]]:
    """One (canonical given, parent-given) key per parent. A birth-`child`
    indexes under each parent; a death-`deceased` infant under its (usually
    single, from the FATHER relative) parent. They meet on a shared parent
    given-name. Empty (path disabled) unless the occurrence is a birth child or
    death deceased that records at least one parent."""
    if occ.role not in ("child", "deceased") or not occ.parents:
        return []
    return [(occ.given, g) for (g, _p) in occ.parents]


def infant_variant_keys(occ: Occurrence) -> list[tuple[str, str]]:
    """Parent-only buckets, so an infant whose death record mis-names it can
    still meet its birth record. Deliberately separate from `infant_keys`: this
    bucket is far coarser, and `score_infant_pair` only accepts a pair out of it
    when the shared parent is pinned down by a patronymic (see there)."""
    if occ.role not in ("child", "deceased") or not occ.parents:
        return []
    return [("", g) for (g, _p) in occ.parents]


def _name_variant_reason(t: Occurrence, c: Occurrence) -> str | None:
    """Why a differing given name is still worth pairing, or None to drop it.

    Two shapes actually occur in these books; anything else is two siblings:
      * the names are near-homographs the scribe could slip between
        (Мавра/Марья, Акилина/Акулина, Марья/Марфа);
      * one record carries a PARENT's given name into the child's slot —
        a death record that names a daughter «Марья», which is her mother's name.
    """
    for a, b in ((t, c), (c, t)):
        if any(a.given == g for g, _p in b.parents) or \
                any(a.given == g for g, _p in a.parents):
            return f"child's name repeats a parent's ({a.given})"
    ratio = difflib.SequenceMatcher(None, t.given.lower(), c.given.lower()).ratio()
    if ratio >= 0.6:
        return f"near-homograph names (similarity {ratio:.2f})"
    return None


def _parent_pinned(t: Occurrence, c: Occurrence) -> bool:
    """True when some shared parent is identified beyond a bare given name —
    both records state a patronymic for them and the two agree.

    A given name alone is not enough to license pairing two DIFFERENTLY named
    infants: every second man in these parishes is «Иван», and siblings share
    parents by definition."""
    def by_given(o: Occurrence) -> dict[str, set[str]]:
        out: dict[str, set[str]] = collections.defaultdict(set)
        for g, p in o.parents:
            if p:
                out[g].add(p)
        return out

    a, b = by_given(t), by_given(c)
    return any(a[g] & b[g] for g in set(a) & set(b))


def _exact_span_days(birth: tuple[int | None, int | None, int | None] | None,
                     death: tuple[int | None, int | None, int | None] | None
                     ) -> int | None:
    """Birth→death span in whole days, or None when either side lacks a month
    (then only the whole-year span is available).

    A missing day is taken as mid-month, so the imprecision is centred rather
    than biased toward either end."""
    if not birth or not death or birth[0] is None or death[0] is None:
        return None
    if birth[1] is None or death[1] is None:
        return None
    try:
        b = datetime.date(birth[0], birth[1], birth[2] or 15)
        d = datetime.date(death[0], death[1], death[2] or 15)
    except ValueError:
        return None
    return (d - b).days



def _parent_patronymic_conflicts(t: Occurrence, c: Occurrence) -> list[str]:
    """Shared-given-name parents whose patronymics disagree across the two
    records, reported only when BOTH sides state one.

    Never a gate: one man can be written under two patronymics in different
    years — same wife across all the records — and be merged. But the
    infant matcher blocks on the parent's GIVEN NAME alone, so a disagreement
    is worth putting in front of a reader."""
    def by_given(o: Occurrence) -> dict[str, set[str]]:
        out: dict[str, set[str]] = collections.defaultdict(set)
        for g, p in o.parents:
            if p:
                out[g].add(p)
        return out

    a, b = by_given(t), by_given(c)
    out = []
    for given in sorted(set(a) & set(b)):
        if not (a[given] & b[given]):
            out.append(f"parent patronymic differs: {given} "
                       f"{'/'.join(sorted(a[given]))} vs "
                       f"{'/'.join(sorted(b[given]))} — verify")
    return out


def score_infant_pair(t: Occurrence, c: Occurrence) -> Scored | None:
    """Score a birth-child ↔ death-deceased pair as the same infant. Decisive
    signal = shared parent; hard gate = recorded age ≈ year span."""
    if {t.role, c.role} != {"child", "deceased"}:
        return None
    name_variant = t.given != c.given
    variant_reason = None
    if name_variant:
        # Differently named infants of a merely same-given-named parent are
        # siblings, not one child. Only a patronymic-pinned shared parent
        # licenses looking further — and even then the names must be explicable.
        if not _parent_pinned(t, c):
            return None
        variant_reason = _name_variant_reason(t, c)
        if variant_reason is None:
            return None
    if t.gender and c.gender and t.gender != c.gender:
        return None
    if (t.rec_type, t.record_num, t.role) == (c.rec_type, c.record_num, c.role):
        return None
    shared = _norm_parents(t) & _norm_parents(c)
    if not shared:
        return None
    score = 60
    ev = ["shared parent: " + ", ".join(g for g, _ in sorted(shared))]
    if surnames_match(t.surname, c.surname):
        score += 20
        ev.append(f"surname match: {t.surname} ~ {c.surname}")
    ev += _parent_patronymic_conflicts(t, c)
    birth_occ, death_occ = (t, c) if t.role == "child" else (c, t)
    by = birth_occ.birth_date[0] if birth_occ.birth_date else birth_occ.year
    dy = death_occ.death_date[0] if death_occ.death_date else death_occ.year
    ay = _age_years(death_occ.age)
    if by and dy:
        exact_days = _exact_span_days(birth_occ.birth_date, death_occ.death_date)
        exact = None if exact_days is None else exact_days / 365.25
        span = exact if exact is not None else float(dy - by)
        if span < 0:
            return None  # death before birth → different person
        # With both dates full, read the age as the INTERVAL it asserts («1 нед»
        # = [7, 14) days) rather than as a point. The ±1-YEAR tolerance below is
        # there only to absorb the whole-year span's own coarseness, and it
        # reaches across the entire first year of life — which is where every
        # infant record sits. That is how a burial at one week old came out HIGH
        # against a birth 255 days earlier (Глуповы Горы, 1915/1916).
        stated = age_bounds(death_occ.age) if exact_days is not None else None
        if exact_days is not None and stated is not None:
            low, high = stated
            gap = max(0.0, low - exact_days, exact_days - high)
            # The interval still needs slack around it, because a clerk rounds:
            # read strictly, Мавра — buried at 96 days under «1 мес», and one
            # child by every other reading — would be thrown out.
            #
            # Capped at a year, and the cap is load-bearing in the other
            # direction. death_age's fraction is calibrated for a check that
            # must not cry wolf; here it would ASSERT an identity, and 20% of
            # a stated nine years is ±1.8 — looser than the flat ±1 year this
            # replaced. Tightening infancy must not loosen childhood.
            slack = min(max(DEFAULT_TOLERANCE_DAYS, DEFAULT_TOLERANCE_FRACTION * low),
                        _MAX_AGE_SLACK_DAYS)
            if gap > slack:
                return None  # age contradicts the span → reject (necronym/gap-year)
            score += 15
            ev.append(f"age {death_occ.age} ≈ span {span:.2f}y")
            conf = "high"
        elif ay is not None:
            if abs(ay - span) <= 1.0:
                score += 15
                shown = f"{span:.2f}" if exact is not None else f"{span:.0f}"
                ev.append(f"age {death_occ.age} ≈ span {shown}y")
                conf = "high"
            else:
                return None  # age contradicts the span → reject (necronym/gap-year)
        else:
            conf = "medium"
            ev.append(f"age unknown; span {span}y — verify")
    else:
        conf = "medium"
        ev.append("birth/death year unknown — verify")
    if name_variant:
        # Never auto-draft a pair the source disagrees with on the child's own
        # name: it is equally the shape of two siblings. The reader decides.
        conf = "low"
        score -= 15
        ev.append(f"given name differs: {t.given} vs {c.given} — {variant_reason}; "
                  f"verify (scribal slip, or two children?)")
    return Scored(cand=c, score=score, confidence=conf, evidence=ev)


def find_infant_candidates(target: Occurrence,
                           infant_pool: dict[tuple[str, str], list[Occurrence]],
                           consolidated: set[str], top_n: int = 4) -> list[Scored]:
    tkeys = infant_keys(target) + infant_variant_keys(target)
    if not tkeys:
        return []
    seen: set[int] = set()
    cands: list[Occurrence] = []
    for k in tkeys:
        for c in infant_pool.get(k, []):
            if c is target or id(c) in seen:
                continue
            if {target.role, c.role} != {"child", "deceased"}:
                continue
            seen.add(id(c))
            if c.stub and (c.stub in consolidated or c.stub.lstrip("_") in consolidated):
                continue
            cands.append(c)
    # Necronym guard: a parent who re-used a dead child's name yields >1 candidate
    # of the same given name; never auto-draft those — cap at medium. Counted over
    # same-named candidates only, so the coarse parent-only bucket (which collects
    # every infant of that parent) cannot demote an otherwise clean pair.
    cap_medium = sum(1 for c in cands if c.given == target.given) > 1
    out: list[Scored] = []
    for c in cands:
        s = score_infant_pair(target, c)
        if s is None:
            continue
        if cap_medium and s.confidence == "high":
            s.confidence = "medium"
            s.evidence = list(s.evidence) + [
                "multiple same-name infants of this parent — verify (necronym?)"
            ]
        out.append(s)
    out.sort(key=lambda s: (-s.score, _cand_order(s.cand)))
    return out[:top_n]


# --------------------------------------------------------------------------- #
# Geni tree-match lookup (cached)
# --------------------------------------------------------------------------- #
#
# We deliberately do NOT use `geni profile search` (search-by-name): because we
# manage this tree, a name search returns mostly our own profiles + duplicates
# plus unrelated namesakes — no family-graph corroboration, so no usable signal
# (empirically ~half noise, the rest our own un-consolidated duplicates that the
# LOCAL matcher already finds with relative evidence). Instead `--geni-matches`
# uses Geni's own tree-match engine (`matches for-profile`), which only fires on
# genuine candidate duplicates and returns each candidate's immediate_family.

def _load_geni_cache(cache_path: Path) -> dict[str, Any]:
    try:
        return json.loads(cache_path.read_text())
    except (OSError, ValueError):
        return {}


def _save_geni_cache(cache: dict[str, Any], cache_path: Path) -> None:
    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    except OSError:
        pass


def _geni(args: list[str], cache: dict[str, Any], cache_key: str) -> Any:
    if cache_key in cache:
        return cache[cache_key]
    env = {**os.environ, "GENI_WEB_CONSENT": "accepted"}
    try:
        res = subprocess.run([tool("geni"), *args], capture_output=True, text=True,
                             timeout=60, env=env)
        data = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
    except Exception as exc:
        data = {"error": str(exc)}
    cache[cache_key] = data
    return data


def build_state_guid_index(tf_dir: Path) -> dict[str, str]:
    """{resource_name: guid} from `terraform state pull`. Maps a resolved stub
    to the live Geni guid so we can ask Geni for that profile's tree matches."""
    try:
        out = subprocess.run(
            [tool("terraform"), f"-chdir={tf_dir}", "state", "pull"],
            capture_output=True, text=True, timeout=180,
        )
        state = json.loads(out.stdout)
    except Exception:
        return {}
    idx: dict[str, str] = {}
    for res in state.get("resources", []):
        if res.get("type") != "geni_profile":
            continue
        for inst in res.get("instances", []):
            guid = inst.get("attributes", {}).get("guid")
            if guid:
                idx[res["name"]] = str(guid)
    return idx


def geni_matches(guid: str, cache: dict[str, Any]) -> list[dict[str, Any]]:
    """Geni tree-match candidates for one in-state profile guid."""
    data = _geni(["matches", "for-profile", guid], cache, f"matches::{guid}")
    matches = data.get("matches") if isinstance(data, dict) else None
    if not matches:
        return []
    out = []
    for m in matches[:8]:
        fam = m.get("immediate_family") or []
        fam_names = []
        if isinstance(fam, list):
            for f in fam:
                if isinstance(f, dict):
                    fam_names.append(f.get("name") or f.get("relation"))
                elif isinstance(f, str):
                    fam_names.append(f)
        out.append({
            "guid": m.get("profile_guid") or m.get("guid"),
            "name": m.get("name") or m.get("display_name"),
            "lifespan": m.get("lifespan_text"),
            "place": m.get("place_text"),
            "manager": m.get("manager_name"),
            "family": [f for f in fam_names if f][:8],
            "compare_url": m.get("compare_url"),
        })
    return out


# --------------------------------------------------------------------------- #
# Reporting / draft config
# --------------------------------------------------------------------------- #

def preliminary_report(targets: list[dict[str, Any]]) -> str:
    lines = [f"Consolidation candidates: {len(targets)} target persons examined", ""]
    flagged = [t for t in targets if t["local"] or t["geni"]]
    lines.append(f"{len(flagged)} have at least one candidate.\n")
    for t in flagged:
        occ = t["target"]
        lines.append(f"■ {occ['name']}  [{occ['rec_type']} {occ['record_num']} "
                     f"{occ['role']} · {occ['year']}]  stub={occ['stub']}")
        for s in t["local"]:
            c = s["cand"]
            lines.append(f"    └ LOCAL [{s['confidence'].upper()} {s['score']}] "
                         f"{c['name']} [{c['rec_type']} {c['record_num']} {c['role']} "
                         f"· {c['year']}] stub={c['stub']}")
            for e in s["evidence"]:
                lines.append(f"         · {e}")
        for h in t["geni"]:
            fam = ("; fam: " + ", ".join(h["family"])) if h.get("family") else ""
            mgr = f" [{h['manager']}]" if h.get("manager") else ""
            lines.append(f"    └ GENI-MATCH {h.get('guid')} {h.get('name')} "
                         f"({h.get('lifespan') or ''}){mgr}{fam}")
            if h.get("compare_url"):
                lines.append(f"         compare: {h['compare_url']}")
        lines.append("")
    return "\n".join(lines)


def _high_edges(targets: list[dict[str, Any]]
                ) -> tuple[set[tuple[str, str]], dict[str, dict[str, Any]]]:
    """Undirected HIGH-confidence edges between stub-resolved occurrences, plus
    the stub -> occurrence map. `--sweep` makes every occurrence a target, so
    the same pair arrives twice (once from each side); the ordered tuple
    collapses that."""
    edges: set[tuple[str, str]] = set()
    occs: dict[str, dict[str, Any]] = {}
    for t in targets:
        tgt = t["target"]
        if not tgt.get("stub"):
            continue
        occs[tgt["stub"]] = tgt
        for s in t["local"]:
            if s["confidence"] != "high":
                continue
            cand = s["cand"]
            if not cand.get("stub"):
                continue
            occs[cand["stub"]] = cand
            a, b = tgt["stub"], cand["stub"]
            edges.add((min(a, b), max(a, b)))
    return edges, occs


def _components(edges: set[tuple[str, str]]) -> list[list[str]]:
    """Connected components (union-find). Each is returned lexicographically
    sorted — res_names are date-prefixed, so that is chronological order and is
    what CCN009 requires of `profile_names`."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for node in {n for e in edges for n in e}:
        groups[find(node)].append(node)
    return sorted((sorted(v) for v in groups.values()), key=lambda m: m[0])


def _stub_year(stub: str, occ_by_stub: dict[str, Occurrence] | None) -> int | None:
    """The year of the record a stub was minted for — asked of the occurrence,
    not read off the res_name's date prefix."""
    occ = (occ_by_stub or {}).get(stub)
    return occ.year if occ is not None else None


def _is_clique(members: list[str], edges: set[tuple[str, str]]) -> bool:
    """True when every member pair carries its own HIGH edge. A component that
    is merely chained (A~B, B~C, no A~C) is how two same-named men fuse into
    one impossible life — flag it, never silently merge."""
    return all((min(a, b), max(a, b)) in edges
               for a, b in itertools.combinations(members, 2))


def append_conflict(prior: list[str], members: list[str],
                    occ_by_stub: dict[str, Occurrence] | None) -> str | None:
    """Why these records must NOT be appended to that existing cluster, or None.

    The scorer's timeline gates only see pairs it actually scores, and a stub
    already folded into a cluster is skipped as a candidate — so an append
    reaches the draft without either gate ever running on it. That is how a
    woman listed as married out to Брехаловка acquired a later bride and a
    later census wife. Re-run the same predicates across the merge boundary."""
    if not occ_by_stub:
        return None
    for p in prior:
        a = occ_by_stub.get(p)
        if a is None:
            continue
        for m in members:
            b = occ_by_stub.get(m)
            if b is None or a is b:
                continue
            if post_death_conflict(a, b):
                return f"{p} is a death record; {m} post-dates it"
            if left_village_conflict(a, b):
                gone = a if a.destination else b
                return (f"{gone.stub or gone.name} left for {gone.destination}; "
                        f"{(b if gone is a else a).stub} post-dates that")
    return None


def existing_canonical_for(members: list[str],
                           existing_clusters: dict[str, list[str]],
                           occ_by_stub: dict[str, Occurrence] | None) -> str | None:
    """The existing cluster that is ALREADY this person, or None.

    A stub already folded into a cluster is skipped as a sweep candidate, so
    the scorer never proposes linking a fresh cluster to an existing canonical;
    and the append check compares generated key strings, where
    `ilarion_platonovich_tjulkin` never collides with `ilarion_platonovich` —
    keys are surname-qualified precisely to avoid colliding with the bare
    given+patronymic ones. Match on the PERSON instead.

    Requires a shared identity key AND a shared spouse, both carrying a
    patronymic: («Иван», None) with a spouse («Марфа», None) describes half the
    village, and a shared spouse is the scorer's own near-decisive signal."""
    if not occ_by_stub:
        return None
    mine = [occ_by_stub[m] for m in members if m in occ_by_stub]
    if not mine:
        return None
    my_keys = {o.key for o in mine if o.key[1]}
    my_spouses = {s for o in mine for s in o.spouses if s[1]}
    if not my_keys or not my_spouses:
        return None
    for canonical, names in sorted(existing_clusters.items()):
        if set(names) & set(members):
            continue  # already this cluster's own records
        theirs = [occ_by_stub[n] for n in names if n in occ_by_stub]
        if not theirs:
            continue
        if ({o.key for o in theirs} & my_keys
                and {s for o in theirs for s in o.spouses} & my_spouses):
            return canonical
    return None


def draft_config(targets: list[dict[str, Any]],
                 existing_clusters: dict[str, list[str]] | None = None,
                 union_by_child: dict[str, str] | None = None,
                 occ_by_stub: dict[str, Occurrence] | None = None) -> str:
    """Survivor-first profiles_to_consolidate stubs for HIGH-confidence local
    matches. Survivor (profile_names[0]) = the earliest-year occurrence.

    Canonical keys are surname-qualified (using any member's surname) to avoid
    colliding with the many bare given+patronymic keys; a key that already
    exists in generate_config_names renders as a merged APPEND block (existing
    + new members) plus the removed{destroy=false} skeletons that append needs,
    rather than a redefinition (which CCN001 would reject)."""
    existing = existing_clusters or {}
    edges, occs = _high_edges(targets)
    clusters: list[dict[str, Any]] = []
    for members in _components(edges):
        # Key and display name come from the earliest-year member; the LIST
        # stays in lexicographic order for CCN009.
        survivor = min((occs[m] for m in members),
                       key=lambda o: (o.get("year") or 9999, o["stub"]))
        surname = next((occs[m]["surname"] for m in members if occs[m].get("surname")), "")
        canonical = generate_res_name(
            f"_{survivor['given']}_{survivor['patr'] or ''}_{surname}_"
        ).strip("_")
        # A key with neither patronymic nor surname (an infant, typically) is
        # just a given name and collides with ANY cluster of that name — an
        # 1807 infant onto the adult Феофилакт Филиппович. Too weak to assume
        # same-person: qualify it instead of appending.
        # This person may already HAVE a canonical under a different key — the
        # sweep cannot see it through the candidate pool, so ask directly.
        same_person = existing_canonical_for(members, existing, occ_by_stub)
        if same_person:
            canonical = same_person
        if canonical in existing and not survivor.get("patr") and not surname:
            canonical = f"{canonical}_{survivor.get('year') or 'x'}"
        # Same treatment when the existing cluster's own records rule the
        # append out on the timeline (died, or married out of the parish).
        why = append_conflict(existing.get(canonical, []), members, occ_by_stub)
        split_from = canonical if why else None
        if why:
            canonical = f"{canonical}_{survivor.get('year') or 'x'}"
        clusters.append({"members": members, "survivor": survivor,
                         "key": canonical, "split_reason": why,
                         "split_from": split_from})

    # Two components can generate one key (same name, no HIGH edge linking
    # them — usually one man the graph failed to connect). A duplicate key in
    # the pasted dict literal silently drops a cluster, so qualify BOTH with
    # the survivor's year and cross-reference them.
    by_key: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for cl in clusters:
        by_key[cl["key"]].append(cl)
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        for cl in group:
            cl["key"] = f"{key}_{cl['survivor'].get('year') or 'x'}"
        siblings = ", ".join(cl["key"] for cl in group)
        for cl in group:
            cl["collision_note"] = (
                f"    #   ⚠ same generated key as {siblings} — no HIGH edge links "
                f"them; verify whether these are one person and merge the clusters\n"
            )

    blocks = []
    removed_blocks: list[str] = []
    union_removed: list[str] = []
    for cl in clusters:
        members, survivor, canonical = cl["members"], cl["survivor"], cl["key"]
        # profile_names[0] survives; every folded member's parent union needs
        # its own state-continuity block.
        for folded in members[1:]:
            union = (union_by_child or {}).get(folded)
            if union:
                union_removed.append(
                    f"removed {{\n  from = geni_union.{union}\n"
                    f"  lifecycle {{ destroy = false }}\n}}")
        # An existing key means these records fold into a cluster that is
        # already (partly) applied: emit the MERGED list plus the
        # removed{destroy=false} blocks that append needs,
        # never a redefinition.
        prior = existing.get(canonical, [])
        new_stubs = [m for m in members if m not in prior]
        # Span over the MERGED list: an append can reach decades further back
        # than the component itself (an 1773 bride + an 1855 mother is one
        # 102-year-old woman), and the component alone would look innocent.
        years = sorted(y for y in (_stub_year(s, occ_by_stub)
                                   for s in set(prior) | set(members))
                       if y is not None)
        span_note = ""
        if years and years[-1] - years[0] > 60:
            span_note = (f"    #   ⚠ span {years[0]}–{years[-1]} — implausible "
                         f"for one person, verify before appending\n")
        if prior:
            note = (f"  # APPEND to existing cluster "
                    f"({len(prior)} existing + {len(new_stubs)} new)")
            names = "\n".join(
                f'            "{s}",  # {"existing" if s in prior else "NEW"}'
                for s in sorted(set(prior) | set(members)))
            removed_blocks.extend(
                f"removed {{\n  from = geni_profile.{s}\n"
                f"  lifecycle {{ destroy = false }}\n}}" for s in new_stubs)
        else:
            note = ""
            names = "\n".join(f'            "{stub}",' for stub in members)
        is_infant = {"child", "deceased"} <= {occs[m].get("role") for m in members}
        header = "auto-drafted (infant born-and-died)" if is_infant else \
            "auto-drafted (HIGH confidence)"
        union_note = (
            "    #   ⚠ the death-record parent→child union re-keys on apply — after\n"
            "    #   `terraform -chdir=terraform/geni show -json .plan > _plan.json`, paste the moved{}/removed{destroy=false}\n"
            "    #   block that detector.suggest_union_blocks prints into\n"
            "    #   terraform/geni/_moved_consolidated_unions.tf\n"
        ) if is_infant else ""
        chain_note = (
            "    #   ⚠ chain-linked (A~B, B~C, no A~C edge) — verify this is one "
            "person, not two\n"
        ) if len(members) > 2 and not _is_clique(members, edges) else ""
        split_note = (
            f'    #   ⚠ NOT appended to the existing "{cl["split_from"]}" '
            f'cluster: {cl["split_reason"]}\n'
        ) if cl.get("split_reason") else ""
        blocks.append(
            f'    # {survivor["name"]} — {header}{note}\n'
            f'{union_note}{chain_note}{span_note}{split_note}'
            f'{cl.get("collision_note", "")}'
            f'    "{canonical}": {{\n'
            f'        "profile_names": [\n{names}\n        ],\n'
            f'        "generate_moved_block": True,\n'
            f'    }},'
        )
    if not blocks:
        return "# No high-confidence local matches to draft.\n"
    out = ("# Draft profiles_to_consolidate entries (review before pasting):\n"
           f"# {len(blocks)} high-confidence cluster(s).\n"
           "profiles_to_consolidate = {\n" + "\n".join(blocks) + "\n}\n")
    if removed_blocks:
        out += ("\n# → terraform/geni/_moved_manual_profiles.tf — appending a record to a\n"
                "#   cluster whose earlier folds already applied plans a DESTROY for it\n"
                "#   unless these are present.\n"
                + "\n".join(removed_blocks) + "\n")
    if union_removed:
        out += ("\n# → terraform/geni/_moved_consolidated_unions.tf — UNVERIFIED, confirm\n"
                "#   with `terraform -chdir=terraform/geni plan -refresh=false -out=.plan-fast`. A union that\n"
                "#   survives under a new canonical name needs moved{}, not removed{}. Plan-accurate\n"
                "#   classification:\n"
                "#   `terraform -chdir=terraform/geni show -json .plan > _plan.json` + detector.suggest_union_blocks.\n"
                "#   COVERAGE: only folds that appear as a union CHILD (born-and-died\n"
                "#   infants and the like). A folded father/mother/groom/bride sits under\n"
                "#   `partners`, whose union re-keys rather than collapses — those blocks\n"
                "#   come from suggest_union_blocks against a saved plan, not from here.\n"
                + "\n".join(dict.fromkeys(union_removed)) + "\n")
    return out


# --------------------------------------------------------------------------- #
# Target selection
# --------------------------------------------------------------------------- #

_FILE_RE = re.compile(r"mk_(\d{4})_(birth|marriage|death)")
_RS_FILE_RE = re.compile(r"(?:rs|ir)_(\d{4})")
_TYPE_FROM_FILE = {"birth": "birth", "marriage": "marriage", "death": "death"}


def parse_tf_file(tf_file: str) -> tuple[int, str]:
    name = Path(tf_file).name
    m = _FILE_RE.search(name)
    if m:
        return int(m.group(1)), _TYPE_FROM_FILE[m.group(2)]
    m = _RS_FILE_RE.search(name)
    if m:
        return int(m.group(1)), "census"
    raise SystemExit(f"error: cannot parse year/type from {tf_file!r} "
                     "(expected mk_YYYY_{birth,marriage,death}.tf, rs_YYYY_*.tf "
                     "or ir_YYYY_*.tf)")


def occ_sig(pub: dict[str, Any]) -> str:
    """Stable signature for an occurrence (its stub, or a record coordinate when
    the stub is unresolved). Used to join AI verdicts back to candidates."""
    return pub.get("stub") or f"{pub['rec_type']}/{pub['record_num']}/{pub['role']}/{pub['year']}"


# --------------------------------------------------------------------------- #
# AI adjudication: fold verdicts.json back into the results
# --------------------------------------------------------------------------- #

def apply_verdicts(results: list[dict[str, Any]], verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay AI verdicts onto local candidates. A verdict is
    {"target": <sig>, "cand": <sig>, "same_person": bool,
     "confidence": "high|medium|low", "rationale": str}.
    The AI confidence overrides the heuristic one; same_person=False demotes the
    pair to "rejected" so it is dropped from the draft."""
    by_pair = {(v["target"], v["cand"]): v for v in verdicts}
    for t in results:
        tsig = occ_sig(t["target"])
        for s in t["local"]:
            v = by_pair.get((tsig, occ_sig(s["cand"])))
            if not v:
                continue
            s["heuristic_confidence"] = s["confidence"]
            if not v.get("same_person", True):
                s["confidence"] = "rejected"
            elif v.get("confidence"):
                s["confidence"] = v["confidence"]
            if v.get("rationale"):
                s["evidence"] = list(s["evidence"]) + [f"AI: {v['rationale']}"]
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tf-file", help="terraform/mk_YYYY_{birth,marriage,death}.tf "
                                      "or terraform/rs_YYYY_*.tf (census)")
    ap.add_argument("--year", type=int, help="alternative to --tf-file")
    ap.add_argument("--type", choices=["birth", "marriage", "death", "census"],
                    help="alternative to --tf-file")
    ap.add_argument("--geni-matches", action="store_true",
                    help="also fetch Geni tree-match candidates (matches for-profile) "
                         "for targets resolvable to an in-state guid (default: local-only)")
    ap.add_argument("--no-infants", action="store_true",
                    help="disable the infant born-and-died matcher (birth-child ↔ "
                         "death-deceased pairing)")
    ap.add_argument("--sweep", action="store_true",
                    help="whole-village sweep: every occurrence is a target (not just "
                         "one year × record type), and a shared relative lets a "
                         "patronymic variant pair (Прасковья Сергеевна ~ Егоровна)")  # i18n: content — names, as an example
    ap.add_argument("--synthesize", metavar="VERDICTS.json",
                    help="fold AI verdicts into the report + draft (re-reads candidates.json)")
    ap.add_argument("--out", help="candidates.json path, the report beside it (default: both in the village directory)")
    ap.add_argument("--village", default=None,
                    help="village directory (default: current directory)")
    args = ap.parse_args(argv)

    village_dir = Path(args.village).resolve() if args.village else Path.cwd()
    tf_dir = village_dir / "terraform" / "geni"
    geni_cache_path = village_dir / ".geni_search_cache.json"

    year = rtype = None
    if args.tf_file:
        year, rtype = parse_tf_file(args.tf_file)
        out_base = Path(args.tf_file).name
    elif args.year and args.type:
        year, rtype = args.year, args.type
        out_base = f"rs_{year}" if rtype == "census" else f"mk_{year}_{rtype}"
    elif args.sweep:
        out_base = "sweep"
    else:
        ap.error("provide --sweep OR --tf-file OR (--year and --type)")

    out_path = Path(args.out) if args.out else (village_dir / f"{out_base}.candidates.json")

    from verso.ru.pipeline.translate import translate_village

    print(f"Translating {village_dir.name} …", file=sys.stderr)
    gen, _ = translate_village(village_dir)
    union_by_child = union_child_index(gen.canonical_unions())
    all_occs = load_occurrences(gen)
    occ_by_stub = by_stub(all_occs, gen.consolidation)
    if args.synthesize:
        results = json.loads(out_path.read_text())
        verdicts = json.loads(Path(args.synthesize).read_text())
        results = apply_verdicts(results, verdicts)
        _emit_report(results, out_base, village_dir, union_by_child, occ_by_stub,
                     report_dir=out_path.parent if args.out else None)
        return 0

    # Folded is the translator's answer — the config spelling a stub was
    # folded under may be one a rename has left behind.
    consolidated = load_consolidated_stubs(village_dir) | {
        o.stub for o in all_occs
        if o.stub and gen.consolidation.config_name_for(o.stub)}
    # Surname pairs the rules cannot derive, read back out of the clusters the
    # curator already confirmed (two family names of one household). Corroboration only.
    surname_aliases = learn_surname_variants(
        load_consolidated_clusters(village_dir), occ_by_stub)
    if surname_aliases:
        print(f"learned {len(surname_aliases)} surname variant pair(s) from "
              f"the existing clusters", file=sys.stderr)
    pool_by_key: dict[Any, list[Occurrence]] = collections.defaultdict(list)
    for o in all_occs:
        pool_by_key[o.key].append(o)
    infant_pool: dict[tuple[str, str], list[Occurrence]] = collections.defaultdict(list)
    if not args.no_infants:
        for o in all_occs:
            for k in infant_keys(o) + infant_variant_keys(o):
                infant_pool[k].append(o)

    # Whole-village sweep blocks on the family graph, scoped per given-name
    # bucket so the pairwise comparison stays bounded.
    rel_index_by_given: dict[str, dict[PersonKey, list[Occurrence]]] = {}
    fanout_skipped: collections.Counter[PersonKey] = collections.Counter()
    if args.sweep:
        by_given: dict[str, list[Occurrence]] = collections.defaultdict(list)
        for o in all_occs:
            by_given[o.key[0]].append(o)
        for given, bucket in by_given.items():
            idx: dict[PersonKey, list[Occurrence]] = collections.defaultdict(list)
            for o in bucket:
                for r in relative_keys(o):
                    idx[r].append(o)
            rel_index_by_given[given] = idx

    if args.sweep:
        targets = all_occs
    else:
        targets = [o for o in all_occs if o.rec_type == rtype and o.year == year]
    print(f"{len(targets)} target persons in {out_base} "
          f"(pool: {len(all_occs)} occurrences)", file=sys.stderr)

    geni_cache = _load_geni_cache(geni_cache_path) if args.geni_matches else {}
    state_guid_idx = build_state_guid_index(tf_dir) if args.geni_matches else {}
    results = []
    for t in targets:
        if t.stub and (t.stub in consolidated or t.stub.lstrip("_") in consolidated):
            continue
        local = find_local_candidates(
            t, pool_by_key, consolidated,
            rel_index=rel_index_by_given.get(t.key[0]) if args.sweep else None,
            fanout_skipped=fanout_skipped if args.sweep else None,
            surname_aliases=surname_aliases)
        if args.sweep:
            # Whole-village, a bare name+patronymic match is noise (~59k pairs
            # on Горюхино) and is never drafted anyway. Corroborated pairs only.
            local = [s for s in local if s.confidence != "low"]
        if not args.no_infants:
            seen_stubs = {s.cand.stub for s in local if s.cand.stub}
            for s in find_infant_candidates(t, infant_pool, consolidated):
                if s.cand.stub and s.cand.stub in seen_stubs:
                    continue
                local.append(s)
            local.sort(key=lambda s: (-s.score, _cand_order(s.cand)))
        geni = []
        if args.geni_matches and t.stub:
            guid = state_guid_idx.get(t.stub) or state_guid_idx.get(t.stub.lstrip("_"))
            if guid:
                geni = geni_matches(guid, geni_cache)
        if not local and not geni:
            continue
        results.append({
            "target": t.public(),
            "local": [{"confidence": s.confidence, "score": s.score,
                       "evidence": s.evidence, "cand": s.cand.public()} for s in local],
            "geni": geni,
        })
    if args.geni_matches:
        _save_geni_cache(geni_cache, geni_cache_path)

    if fanout_skipped:
        print(f"\n{len(fanout_skipped)} relative(s) too common to block on "
              f"(>{REL_FANOUT_MAX} occurrences) — NOT used as a family-graph key:",
              file=sys.stderr)
        for (g, p), n in fanout_skipped.most_common(10):
            print(f"    {g} {p or ''}".rstrip() + f" — {n} occurrences", file=sys.stderr)

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nwrote {out_path} ({len(results)} targets with candidates)", file=sys.stderr)
    # Includes the ALREADY-consolidated people: they are excluded as candidates
    # but an append has to be checked against their records (append_conflict).
    _emit_report(results, out_base, village_dir, union_by_child, occ_by_stub,
                 report_dir=out_path.parent if args.out else None)
    return 0


def _emit_report(results: list[dict[str, Any]], out_base: str, village_dir: Path,
                 union_by_child: dict[str, str],
                 occ_by_stub: dict[str, Occurrence] | None = None, *,
                 report_dir: Path | None = None) -> None:
    """Print the report and write it to `report_dir` (with `--out`, the directory the
    candidates went to; else the village's): a corpus's output check runs the sweep on the checkout under
    test and must write nothing into it."""
    existing_clusters = load_consolidated_clusters(village_dir)
    report = preliminary_report(results)
    draft = draft_config(results, existing_clusters, union_by_child, occ_by_stub)
    report_path = (report_dir or village_dir) / f"{out_base}_consolidation_report.md"
    report_path.write_text(report + "\n\n" + "=" * 70 + "\n\n" + draft)
    print(f"wrote {report_path}", file=sys.stderr)
    print(report)
    print("\n" + "=" * 70 + "\n")
    print(draft)


if __name__ == "__main__":
    sys.exit(main())
