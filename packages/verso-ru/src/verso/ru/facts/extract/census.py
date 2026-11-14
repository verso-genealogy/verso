"""Household roll → assertions: revision tales and confession lists alike.

A ревизская сказка and an исповедная роспись are one shape — двор, people,
relations stated against the head — and the DSL already spells the difference
as a handful of strings (`CONFESSION_LIST`). So does this: nothing below reads
`file_prefix` or `record_type` except to put them in the citation, and the
`EnumeratedIn` of a двор is the `EnumeratedIn` of a семья. That matters,
because both regexes that recover a household from a res_name hardcode `_rs_`
and are blind to a confession list by construction.

Four things this extractor states that its consumers reconstruct today:

**Being counted into a household is a fact.** «Оба — члены двора N одной
ревизии» is the strongest evidence the corpus has that two same-named people
are two people: the scribe enumerated them on adjacent lines. It used to be
recovered by running a regex over a res_name the translator minted, which
needed the consolidation move list to see past a fold and could not see a
confession list at all; `union-dups` has read `EnumeratedIn` instead since
2026-09-23 (the regex was removed on 2026-09-25). `EnumeratedIn` is the same
claim before it was ever spelled as a string.

**Being enumerated is not being born, and it is not dying either.** A member
listed in 1834 was alive in 1834 — a lower bound, which the translator has no
slot for and therefore dresses as a death event with `date_range="after"`.
`SurvivedUntil` says the bound, derived from the enumeration that supports it —
except for a member the roll lists as dead since the last revision, who is
counted on the page and was not alive at the count.

**Two ages are two statements, not one column.** A revision copies the previous
tale's age forward, so a member carries two readings taken years apart; the DSL
holds them in `age` and `previous_age`, and 40 more sit in prose as «прошлая
РС: 4.5 лет». Each becomes an `AgedYears` dated to the roll that took it, which
is what makes `single_age_column` a rendering question rather than a modelling
one. Except where both columns carry ONE figure: that is the importer's copy
into an empty current column, and it is one age, not two (`_copied_forward`).

**What the roll says and what we reconstructed are the same predicate on
different authority.** `ref_member` is the relation the SOURCE states, measured
against the role; `parent_member` is our upward reconstruction; a `hidden=True`
member is not in the book at all. All three produce `ParentOf`/`SpouseOf` — and
`Stated`, `Derived` and `Derived` respectively, which is the distinction CPL006
polices by hand and CPL007 now makes writable.

On `Basis`, the same gap as births and deaths and a wider one: `CensusHousehold`
derives patronymics and surnames from the resolved parent IN PLACE, writing
`patr_orig` as well as `patr_modern` — so the negative breadcrumb the death
extractor reads is not available here. A member whose role makes derivation
possible gets `Stated(basis_unknown=True)`; `verso facts --basis-census` prices it.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.ages import age_recorded
from verso.ru.census_revisions import PREVIOUS_AGE_REVISION_YEAR
from verso.ru.dsl.records.census import (
    CensusRole, _CHILD_ROLES, _DAUGHTER_ROLES, _MARRIED_WOMEN_ROLES, _SON_ROLES)

from verso.ru.facts.extract.common import Entry, RecordId, SlotIndex, fact_date, reviewed
from verso.ru.facts.model import (
    AgedYears, ArrivedFrom, Assertion, BornOn, Bound, Derived, DiedOn, EnumeratedIn, FactDate, FosterParentOf, KinOf, MovedTo, ParentOf, Persona, Retracted, SpouseOf, Stated, SurvivedUntil, Surety)

__all__ = ["RECORD_KIND", "facts_from_census"]

RECORD_KIND = "census"

#: What the role says about the edge between a member and the member their
#: reference names — the HEAD when no `ref_member` is given, exactly as the
#: document's own «N. роль (ref)» line resolves it.
#:
#: «Внукъ» is deliberately NOT a parent edge: the word is measured against the
#: head, so the reference is the GRANDfather. The real father arrives, when we
#: have reconstructed him, as `parent_member`.
_EDGE: dict[CensusRole, str] = {
    CensusRole.SON: "child",
    CensusRole.DAUGHTER: "child",
    CensusRole.WIFE: "spouse",
    CensusRole.HUSBAND: "spouse",
    CensusRole.MOTHER: "parent-of-ref",
    CensusRole.FATHER: "parent-of-ref",
    CensusRole.FOSTER_SON: "foster",
    CensusRole.FOSTER_DAUGHTER: "foster",
}

#: The head's other parent — a FATHER referenced at the MOTHER is her husband.
_OTHER_PARENT: dict[CensusRole, CensusRole] = {
    CensusRole.FATHER: CensusRole.MOTHER,
    CensusRole.MOTHER: CensusRole.FATHER,
}

#: Roles whose patronymic or surname `CensusHousehold.__init__` may have
#: written itself, overwriting `patr_orig` as well as `patr_modern` — so a
#: reader of the constructed record cannot tell the book's word from ours.
_DERIVATION_MAY_HAVE_RUN = (
    set(_CHILD_ROLES) | set(_MARRIED_WOMEN_ROLES) | set(_SON_ROLES)
    | set(_DAUGHTER_ROLES)
)

#: «прошлая РС: 4.5 лет» — an age from the previous revision that did not make
#: it into the `previous_age` column. The translator reads this same prose
#: (census_resolvers); here it becomes a second dated statement of an age.
_PRIOR_AGE = "прошлая РС:"  # i18n: content — the comment words and age unit the DSL writes
#: «роль в оригинале: дядя родной» — the book's own qualifier, which for a
#: `role=None` member is the only role word there is. Provenance, not a
#: predicate: a rule may not read it.
_STATED_ROLE = "роль в оригинале:"  # i18n: content — the comment words and age unit the DSL writes


def facts_from_census(items: Iterable[tuple[Any, str]], *, village: str,
                      slots: SlotIndex | None = None, drafts: bool = False,
                      ids: RecordId | None = None) -> Iterator[Assertion]:
    """`items` are whole `CensusRecords`, not single records: a household takes
    its year, its dates and its previous revision from the roll around it.

    A held двор is skipped and does not count in a citation's `entry`; its id
    (`ids`, the household's in the records JSON) is its own and moves nobody's."""
    entry = 0
    for records, source_file in items:
        for display_id, household in _households(records):
            if not (drafts or reviewed(household)):
                # Transcribed, not yet checked against the scan. The rest of
                # the pipeline emits nothing for such a двор; asserting from
                # one here would put claims into the layer that the author has
                # not yet stood behind.
                continue
            yield from _facts_from_household(records, household, display_id,
                                             village, source_file, entry, slots, ids)
            entry += 1


def _households(records: Any) -> list[tuple[str, Any]]:
    """(display number, household) — the household's own number as the roll
    gives it, falling back to a running count over the unnumbered ones.

    The same rule the generator applies, and for the same reason: the number is
    what the document calls this двор, so it is provenance. Unlike the
    generator's, it is read here from the roll rather than back out of a string.
    """
    out: list[tuple[str, Any]] = []
    numeric = 0
    for h in records.households:
        if h.family_id:
            out.append((str(h.family_id), h))
        else:
            numeric += 1
            out.append((str(numeric), h))
    return out


def _facts_from_household(records: Any, h: Any, display_id: str, village: str,
                          source_file: str, entry: int,
                          slots: SlotIndex | None = None,
                          ids: RecordId | None = None) -> list[Assertion]:
    e = Entry(h, village=village, source_file=source_file,
              record_kind=RECORD_KIND, entry=entry, record_num=display_id,
              year=records.year, page=getattr(h, "page", None), slots=slots, ids=ids)
    taken = fact_date(getattr(h, "record_day", None),
                      getattr(h, "record_month", None), records.year)
    prior = fact_date(None, None, _previous_revision(records))

    head = next((m for m in h.members if m.role == CensusRole.HEAD), None)
    refs: dict[int, Persona] = {}

    for m in h.members:
        refs[m.number] = _claim_member(e, m, display_id, taken, prior)

    members = {m.number: m for m in h.members}
    for m in h.members:
        _relate(e, m, refs, head, members)

    return e.facts


def _previous_revision(records: Any) -> int | None:
    """The revision a roll's previous-age column counts from.

    NOT `prev_revision_year=`, though the name invites it. That kwarg is a gate
    — «this roll has a known prior revision», which the translator reads only
    for whether it is set — and its value is whatever the author typed. Four
    books contradict their own ages with it: a book of 1795 declares 1762
    while its 242 comparable members are 13 years older than their previous
    age, which is 1782; three books of 1816 declare 1815 while
    theirs are 4 years older, which is 1811. Read as a date, it put 433 ages
    twenty years early and 90 four years late.

    The table is the one CAI002 checks the same two columns with, so the linter
    and this extractor cannot date one column two ways. Where the table has no
    entry the book's own word is all there is — one book of 1782, whose
    five comparable members agree with it.
    """
    return PREVIOUS_AGE_REVISION_YEAR.get(
        records.year, getattr(records, "prev_revision_year", None))


def _claim_member(e: Entry, m: Any, display_id: str, taken: Any,
                  prior: Any) -> Persona:
    reconstructed = bool(m.is_hidden())
    locator = f"member{m.number}"
    # A hidden member is nowhere in the roll: the household does not name them,
    # so nothing about them is stated. Everything else is stated by the roll,
    # except where `CensusHousehold` may have written the name itself.
    name_basis: Stated | Derived
    if reconstructed:
        name_basis = Derived("census.reconstructed-member", Surety.ASSUMED, ())
    elif m.role in _DERIVATION_MAY_HAVE_RUN:
        name_basis = Stated(basis_unknown=True)
    else:
        name_basis = Stated()
    ref = e.claim(m.person, locator, slot=("member", m.number),
                  name_basis=name_basis,
                  # `CensusRecords.__init__` fills an empty residence with the
                  # village, in place, for every member.
                  residence_basis=Stated(basis_unknown=True),
                  stated_role=_phrase(m, _STATED_ROLE),
                  # Nor is a reconstructed member's status the roll's: we gave
                  # it to someone the roll does not name.
                  status_basis=(Derived("census.reconstructed-member",
                                        Surety.ASSUMED, ())
                                if reconstructed else None))
    cite = e.cite(locator)
    base: Stated | Derived = (
        Derived("census.reconstructed-member", Surety.ASSUMED, ())
        if reconstructed else Stated())

    if not reconstructed:
        listed = EnumeratedIn(subject=ref, cite=cite, group=display_id,
                              within=e.source_file, as_of=taken, basis=Stated())
        e.facts.append(listed)
        # Being counted is the evidence; being alive is the conclusion. The
        # translator has no slot for the second and mints a death event with
        # `date_range="after"` instead. Not for the roll's own dead, and not
        # for anyone it records as gone: those were alive when they LEFT,
        # which `_movements` bounds from the departure itself.
        if not _died_before_roll(m) and not _departed_alive(m):
            e.facts.append(SurvivedUntil(
                subject=ref, cite=cite, date=taken,
                basis=Derived("census.listed-alive", Surety.INFERRED, (listed,))))

    # An author who re-read the scan and still cannot reconcile the line's
    # figure withdraws its ages — and the birth year computed from them, which
    # restates the same figure. Everything else the line says stands.
    reason = getattr(m, "source_age_error", None)
    age_basis: Stated | Derived | Retracted = (
        Retracted(reason, base) if reason else base)
    # The previous revision's figure alone, when the roll carried a slip
    # forward faithfully and its own age is sound (`previous_age_error=`).
    prior_reason = getattr(m, "previous_age_error", None)
    prior_basis: Stated | Derived | Retracted = (
        Retracted(prior_reason, base) if prior_reason else age_basis)

    stated_prior = m.previous_age if m.previous_age is not None \
        else _prior_age(m)
    # `"?"`, `"-"` and `""` are the transcriber's «не записано», not a figure
    # the book gives: 198 of them were asserted as ages.
    if not age_recorded(stated_prior):
        stated_prior = None
    if age_recorded(m.age) and not _copied_forward(m.age, stated_prior):
        # Someone gone before the roll has a blank current-age column (CAI004),
        # so a figure standing there is an age the roll does not date.
        e.facts.append(AgedYears(subject=ref, cite=cite, age=m.age,
                                 as_of=FactDate() if _left_before_roll(m) else taken,
                                 basis=age_basis))
    if stated_prior is not None:
        # The roll's own cross-check: the previous tale's age, copied forward.
        # Two readings taken years apart are two statements — which is why
        # `single_age_column` is a question about rendering and not about this.
        e.facts.append(AgedYears(subject=ref, cite=cite, age=stated_prior,
                                 as_of=prior, basis=prior_basis))
    if m.birth_year is not None:
        e.facts.append(BornOn(
            subject=ref, cite=cite,
            date=fact_date(m.birth_day, m.birth_month, m.birth_year),
            basis=age_basis))
    moved = _movements(e, m, ref, cite, base, taken)
    if not reconstructed and moved is not None and moved.when:
        # Sold, recruited, transferred, married off: alive to be sent, and
        # nothing more the roll can vouch for. 367 members were asserted alive
        # at a count that lists them as gone; those with a year are bounded
        # by it, the rest by nothing.
        e.facts.append(SurvivedUntil(
            subject=ref, cite=cite, date=moved.when,
            basis=Derived("census.departed-alive", Surety.INFERRED, (moved,))))
    return ref


def _movements(e: Entry, m: Any, ref: Persona, cite: Any,
               base: Stated | Derived, taken: FactDate) -> MovedTo | None:
    """Arrivals, departures and deaths; returns the departure, if one."""
    if m.origin:
        e.facts.append(ArrivedFrom(
            subject=ref, cite=cite, place=m.origin,
            when=fact_date(None, None, m.arrival_year),
            reason=m.arrival_reason or "", basis=base))
    elif m.arrival_year is not None:
        e.facts.append(ArrivedFrom(
            subject=ref, cite=cite, place="",
            when=fact_date(None, None, m.arrival_year),
            reason=m.arrival_reason or "", basis=base))
    if _died_before_roll(m):
        # A death, not a move to nowhere. It was a `MovedTo` with an empty
        # place and the reason «умер» — which no rule may read — so the roll's
        # 497 recorded deaths reached nothing that asks about a death.
        #
        # The year is CIRCA: it was told to the counter years after the fact,
        # and on the 140 Горюхино people a metric book also buries it sits
        # within two years of the burial either way 121 times. The translator
        # writes it circa for the same reason. With no year the death lies
        # somewhere before the roll — a bound, and an exact one.
        died = (FactDate(year=m.departure_year, circa=True)
                if m.departure_year is not None else
                FactDate(year=taken.year, month=taken.month, day=taken.day,
                         bound=Bound.BEFORE))
        e.facts.append(DiedOn(subject=ref, cite=cite, date=died, basis=base))
    elif _departed_alive(m):
        # A reason alone is a departure too: «в бегах», «отдан в рекруты»
        # with neither a year nor a place left no trace at all when a move
        # needed one of the two — 43 members.
        moved = MovedTo(
            subject=ref, cite=cite, place=m.destination or "",
            when=fact_date(None, None, m.departure_year),
            reason=m.departure_reason or "", basis=base)
        e.facts.append(moved)
        return moved
    return None


def _relate(e: Entry, m: Any, refs: dict[int, Persona], head: Any,
            members: dict[int, Any]) -> None:
    me = refs[m.number]
    cite = e.cite(f"member{m.number}")
    reconstructed = bool(m.is_hidden())
    stated: Stated | Derived = (
        Derived("census.reconstructed-member", Surety.ASSUMED, ())
        if reconstructed else Stated())

    # (1) The axis the ROLE measures: `ref_member` when given, else the head,
    # which is what the document's own role line resolves to.
    anchor_num = m.ref_member
    if anchor_num is None and m.role is not None and m.role != CensusRole.HEAD \
            and head is not None:
        anchor_num = head.number
    anchor = refs.get(anchor_num) if anchor_num is not None else None
    if anchor is not None and anchor is not me:
        edge = _EDGE.get(m.role) if m.role is not None else None
        partner = members.get(anchor_num) if anchor_num is not None else None
        if edge == "parent-of-ref" and m.role is not None and partner is not None \
                and partner.role == _OTHER_PARENT.get(m.role):
            # «отецъ» referenced at the member who is «мать»: the reference
            # names his WIFE — the convention the translator's hidden-ancestor
            # pass reads (`ref_member` of a hidden parent is the partner) — and
            # the role word is the head's, as it is with no reference at all.
            # She need not be the head's mother: a household can list her as
            # the mother of a son by her first husband.
            _spouses(e, cite, me, anchor, stated)
            child = refs.get(head.number) if head is not None else None
            if child is not None and child is not me and child is not anchor:
                e.facts.append(ParentOf(subject=me, cite=cite, other=child,
                                        basis=stated))
        elif edge == "child":
            e.facts.append(ParentOf(subject=anchor, cite=cite, other=me, basis=stated))
        elif edge == "parent-of-ref":
            e.facts.append(ParentOf(subject=me, cite=cite, other=anchor, basis=stated))
        elif edge == "spouse":
            _spouses(e, cite, me, anchor, stated)
        elif edge == "foster":
            e.facts.append(FosterParentOf(subject=anchor, cite=cite, other=me,
                                          basis=stated))
        elif m.role is not None:
            # «внукъ», «племянникъ», «невѣстка», «зять», «пасынокъ»: related,
            # and to a person the word does not place as parent or spouse. The
            # word is kept for a reader; no rule may read it.
            e.facts.append(KinOf(subject=me, cite=cite, other=anchor,
                                 term=str(m.role.value), basis=stated))

    # (2) The axis WE reconstructed. Same predicates, different authority —
    # which is the whole of the distinction CPL006 polices in prose.
    if m.parent_member is not None and m.parent_member in refs:
        e.facts.append(ParentOf(
            subject=refs[m.parent_member], cite=cite, other=me,
            basis=Derived("census.reconstructed-parent", Surety.ASSUMED, ())))
    spouse_num = getattr(m, "spouse_member", None)
    if spouse_num is not None and spouse_num in refs:
        _spouses(e, cite, me, refs[spouse_num], stated)
    if m.secondary_role is not None and m.secondary_ref_member in refs:
        other = refs[m.secondary_ref_member]
        secondary = Derived("census.reconstructed-secondary-role",
                            Surety.ASSUMED, ())
        edge = _EDGE.get(m.secondary_role)
        if edge == "child":
            e.facts.append(ParentOf(subject=other, cite=cite, other=me,
                                    basis=secondary))
        elif edge == "spouse":
            _spouses(e, cite, me, other, secondary)


def _spouses(e: Entry, cite: Any, a: Persona, b: Persona,
             basis: Stated | Derived) -> None:
    if a is b:
        return
    e.facts.append(SpouseOf(subject=a, cite=cite, other=b, basis=basis))
    e.facts.append(SpouseOf(subject=b, cite=cite, other=a, basis=basis))


def _phrase(m: Any, key: str) -> str | None:
    """The value of a `key: …` phrase inside a member's comment, else None.

    Comments are semicolon-separated and mostly free text — 1744 of the
    corpus's 1900 carry no key at all — so this is deliberately the whole of
    the comment parsing: two keys, both of which state something the record
    says rather than something we concluded.
    """
    comment = getattr(m, "comment", None)
    if not comment or key not in comment:
        return None
    tail = comment.split(key, 1)[1]
    value = tail.split(";", 1)[0].strip()
    return value or None


#: «умер», «умерла». Searched, not compared: the translator's exact `== "умер"`
#: misses the one «умерла» in the corpus, and CAI004 — the other reader of this
#: column — searches the same way.
_DIED = re.compile(r"умер", re.IGNORECASE)  # i18n: content — the comment words and age unit the DSL writes


#: «выдана замуж», «выдана в замужество». The other departure CAI004 knows to
#: leave the current-age column blank: it is her natal row the roll keeps.
_MARRIED_OUT = re.compile(r"замуж", re.IGNORECASE)  # i18n: content — the comment words and age unit the DSL writes


def _left_before_roll(m: Any) -> bool:
    """Whether the roll keeps this member's row without aging them.

    CAI004's two departures, read the way CAI004 reads them: a death, and a
    daughter married off — whose natal row stays while her current-age column
    goes blank. A figure in that column is an age the roll does not date: in
    the corpus, ten brides of 1762, the first revision to count women at all
    and so with no previous column either, and one child of the 1850 roll
    buried in 1835 at «2 недели».
    """
    reason = getattr(m, "departure_reason", None) or ""
    return bool(_DIED.search(reason) or _MARRIED_OUT.search(reason))


def _died_before_roll(m: Any) -> bool:
    """Whether the roll records this member's death.

    A сказка lists who died since the last revision on the household's own page,
    so being counted there is not being alive at the count. «Listed, therefore
    alive» held for everyone else and was asserted for these too: 497 members
    of the corpus were said to have survived until a roll that records their
    death. They are still enumerated — the household's page names them, which is
    what `EnumeratedIn` claims and what the same-household guard relies on.
    """
    return bool(_DIED.search(getattr(m, "departure_reason", None) or ""))


def _departed_alive(m: Any) -> bool:
    """Whether the roll records this member as gone, and not by dying."""
    if _died_before_roll(m):
        return False
    return bool(getattr(m, "departure_reason", None)
                or getattr(m, "departure_year", None) is not None
                or getattr(m, "destination", None))


def _copied_forward(age: object, prior: object) -> bool:
    """Whether the current-age column holds the previous one's figure.

    The importer's compression: where the сказка left the current-age column
    EMPTY — usually because the member had gone before the revision: сдан в
    рекруты, продан, переведён, умер — it copied the previous age into both
    columns so the document body had something to render. 136 of the 154 in
    the corpus had gone; the 18 who had not all carry a `birth_year` that
    agrees with the previous revision to within a year and with the current
    one in no case, so the figure is the previous reading there too. The
    translator reads the same
    equality as `prev_age_compresses_current` and takes one birth estimate from
    the previous revision; CAI002 skips it for the same reason. One figure in
    two columns is one age, taken at the previous revision, and asserting it a
    second time under the current roll's date puts it a whole revision late.

    Wider than the translator's test in one place, deliberately: it also
    compares the prose form, «прошлая РС: 0.5 лет» beside `age="0.5"`. That is
    the same copy spelled differently — 21 members, nearly all infants who died
    between revisions — and the translator can afford to miss it only because
    its death branch drops the alive-bound for them anyway. The unit the
    transcriber appended to the prose («лет») is not part of the figure.
    """
    if prior is None:
        return False
    return _figure(age) == _figure(prior)


def _figure(age: object) -> str:
    text = str(age).strip()
    return text[:-len("лет")].rstrip() if text.endswith("лет") else text  # i18n: content — the comment words and age unit the DSL writes


def _prior_age(m: Any) -> str | None:
    """«прошлая РС: 4.5 лет» — the previous revision's age, written in prose
    because the column it belongs in was already spoken for."""
    value = _phrase(m, _PRIOR_AGE)
    if value is None:
        return None
    # The phrase carries the unit the transcriber wrote, «лет» included, and
    # sometimes doubled («3 мес лет»). Kept VERBATIM, like every other stated
    # age: what it implies about a birth year is arithmetic, and arithmetic
    # belongs in a `Derived` assertion with this one among its premises.
    return value
