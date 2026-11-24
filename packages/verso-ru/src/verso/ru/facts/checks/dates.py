"""Records of one person dated out of order — `verso facts --check date-order`.

The SOURCE half of `verso date-order`: that check reads the tree Geni shows
(one birth per canonical, after the fold and the config's overrides); this one
reads every claim each record makes, so two records of one canonical that
disagree are visible. The orderings are a table — the four `verso date-order`
asks, five from Gramps Verify around the wedding and the christening, and a
roll counting someone a record has buried; the comparison is
`FactDate.definitely_before` with a circa year read at its measured slack;
the rule that decides a pair cannot stand is `rules.disagreement`, which
names none of this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from verso.ru.facts.identity import Identity, self_identity
from verso.ru.facts.model import (
    AssertionSet, BaptizedOn, BornOn, Bound, BuriedOn, Dated, DiedOn, DivorcedOn, FactDate, MarriedOn, SurvivedUntil)
from verso.ru.facts.projection import canonical_name
from verso.ru.facts.rules.disagreement import contradictions, held
from verso.ru.messages import t


#: The orderings, as (left, right, kind, event word, reference word): the
#: four `verso date-order` asks about, then five Gramps Verify asks around the
#: wedding and the christening, then a roll that counts the dead alive. Named HERE and nowhere else: the rule takes its
#: two predicates as type parameters, so an ordering costs a line in this table.
def orderings() -> list[tuple[Any, Any, str, str, str]]:
    return [
        (BaptizedOn, BornOn, "baptism_before_birth", str(t("facts.event.baptism")), str(t("facts.event.birth"))),
        (DiedOn, BornOn, "death_before_birth", str(t("facts.event.death")), str(t("facts.event.birth"))),
        (BuriedOn, DiedOn, "burial_before_death", str(t("facts.event.burial")), str(t("facts.event.death"))),
        (BuriedOn, BornOn, "burial_before_birth", str(t("facts.event.burial")), str(t("facts.event.birth"))),
        # From Gramps Verify (MarriageBeforeBirth, MarriageAfterDeath,
        # DeathBeforeBapt, BaptAfterBury), 2026-09-30.
        (MarriedOn, BornOn, "marriage_before_birth", str(t("facts.event.marriage")), str(t("facts.event.birth"))),
        (DiedOn, MarriedOn, "death_before_marriage", str(t("facts.event.death")), str(t("facts.event.marriage"))),
        (BuriedOn, MarriedOn, "burial_before_marriage", str(t("facts.event.burial")), str(t("facts.event.marriage"))),
        (DiedOn, BaptizedOn, "death_before_baptism", str(t("facts.event.death")), str(t("facts.event.baptism"))),
        (BuriedOn, BaptizedOn, "burial_before_baptism", str(t("facts.event.burial")), str(t("facts.event.baptism"))),
        # A roll counting someone a record has buried: measured 2026-09-30,
        # three people, all Горюхино, each a later roll against an earlier
        # metric death — the shape of a father and a son of one name folded.
        (DiedOn, SurvivedUntil, "death_before_alive", str(t("facts.event.death")), str(t("facts.event.counted_alive"))),
        (BuriedOn, SurvivedUntil, "burial_before_alive", str(t("facts.event.burial")), str(t("facts.event.counted_alive"))),
    ]


#: The orderings that hold inside ONE entry and nowhere else, in the shape of
#: `orderings()`. An act of divorce names the marriage it ends, and dating that
#: marriage after the divorce is the act contradicting itself; between two
#: records it is the order of a life — a man divorced marries again — so the
#: class «two entries disagree» never asks it.
def within_orderings() -> list[tuple[Any, Any, str, str, str]]:
    return [
        (DivorcedOn, MarriedOn, "divorce_before_marriage",
         str(t("facts.event.divorce")), str(t("facts.event.named_marriage"))),
    ]


#: A burial measured against an event only when no dated death exists — with
#: one, the death row already asks the question, and the burial would repeat it.
_BURIAL_DEFERS_TO_DEATH = frozenset({
    "burial_before_birth", "burial_before_marriage", "burial_before_baptism",
    "burial_before_alive"})


#: How far a circa year may sit from the truth, in years. Measured, not
#: chosen: on the 140 Горюхино people whose death both a сказка and a metric
#: book give, the сказка's told year is later than the burial by 1 year 14
#: times, by 2 five times, by 3 never, and then by 4–8 — seven, each the shape
#: of two namesakes folded into one. Within the slack a circa year orders
#: nothing; beyond it, it may.
CIRCA_SLACK_YEARS = 2


def as_read(date: FactDate) -> FactDate:
    """A circa year as the interval it can mean. Every other date as is.

    Here and not in `FactDate`: `circa` is carried by the model and interpreted
    by nobody, and how wide «около» is depends on who said it. This is the one
    caller that needs an answer, and the answer is a measurement of one kind of
    record — the сказка's told death year, the only circa date the extractors
    emit.
    """
    if not date.circa or date.year is None or date.bound is not None:
        return date
    return FactDate(year=date.year - CIRCA_SLACK_YEARS, bound=Bound.BETWEEN,
                    end_year=date.year + CIRCA_SLACK_YEARS, circa=True,
                    end_circa=True)


def definitely_before(a: FactDate, b: FactDate) -> bool:
    """Whether every day `a` can mean precedes every day `b` can — reading a
    circa year with its slack. The incompatibility `date-order` hands the rule."""
    return as_read(a).definitely_before(as_read(b))


#: Per-ordering advice. The oracle prints one hint for all four, and it is the
#: birth one («не задан k_year=»), which is wrong for a burial — the corpus has
#: no burial hint because the oracle can barely reach a burial at all.
HINTS = {
    "baptism_before_birth": t("facts.date_order.hint.baptism_before_birth"),
    "death_before_birth": t("facts.date_order.hint.death_before_birth"),
    "burial_before_death": t("facts.date_order.hint.burial_before_death"),
    "burial_before_birth": t("facts.date_order.hint.burial_before_birth"),
    "marriage_before_birth": t("facts.date_order.hint.marriage_before_birth"),
    "death_before_marriage": t("facts.date_order.hint.death_before_marriage"),
    "burial_before_marriage": t("facts.date_order.hint.burial_before_marriage"),
    "death_before_baptism": t("facts.date_order.hint.death_before_baptism"),
    "burial_before_baptism": t("facts.date_order.hint.burial_before_baptism"),
    "death_before_alive": t("facts.date_order.hint.death_before_alive"),
    "burial_before_alive": t("facts.date_order.hint.burial_before_alive"),
    "divorce_before_marriage": t("facts.date_order.hint.divorce_before_marriage"),
}


#: Per canonical res_name, the (kind, event, reference, left, right) of each
#: ordering its records break.
OrderFindings = dict[str, list[tuple[str, str, str, Any, Any]]]


def date_order_findings(facts: AssertionSet,
                        identity: Identity) -> tuple[OrderFindings, OrderFindings]:
    """Events dated before an earlier event of the same life, on assertions:
    (inside one entry, across entries).

    The SOURCE half of `verso date-order` (`verso.ru.consolidation.date_order`),
    not a replacement for it. That check reads the tree Geni shows — one birth
    per canonical, after `_pick_best_date`, config overrides and derived
    estimates — which is exactly what Geni will flag, so it stays on the tree
    as `age-conflicts` does. This one reads what the records say: eleven
    orderings and one charitable comparison, the comparison
    `FactDate.definitely_before` and the orderings a table the rule
    (`verso.ru.facts.rules.disagreement`) never sees.

    It reports TWO classes, and keeping them apart is the point.

    **Inside one entry** is the oracle's own question. Both implementations
    find nothing for the two orderings the oracle can actually reach — and nine
    findings appear for the one it cannot: until 2026-09-25 `add_death_records`
    did not populate `p.burial` (3 of the corpus's 3466 burials reached a
    profile), so a book that dates a burial before the death it records was
    unreadable to the check written for exactly that. It now emits the burial
    day except where `source_date_error` withdraws it — which is exactly these
    records. One such record is `d_day=9, b_day=8`.

    **Two entries disagreeing** is a question the oracle cannot ask at all.
    Folding keeps one value per field, so a canonical shows one birth; the
    assertions keep every claim each record made, and 69 canonicals hold a
    christening that precedes a birth year asserted by a DIFFERENT record.
    That is not a misdated christening — it is a consolidation signal, two
    records that may not be one person, and it is labelled as one rather than
    being printed under the oracle's birth-date advice.
    """
    believed = facts.believed()
    dated_death = held(believed, kind=DiedOn, identity=identity)

    def order(a: Any, b: Any) -> str | None:
        return "before" if definitely_before(a.date, b.date) else None

    within: OrderFindings = {}
    across: OrderFindings = {}
    for left, right, kind, event, reference in orderings():
        for c in contradictions(believed, left=left, right=right,
                                identity=identity, incompatible=order):
            # «погребение раньше рождения» only when no dated death exists —
            # with one, the burial is measured against the death instead. The
            # condition is about the person, which is why the rule hands out
            # `held` rather than deciding it.
            if kind in _BURIAL_DEFERS_TO_DEATH and c.who in dated_death:
                continue
            bucket = (within if c.left.cite.record_id == c.right.cite.record_id
                      else across)
            bucket.setdefault(canonical_name(c.who) or "", []).append(
                (kind, event, reference, c.left, c.right))
    for left, right, kind, event, reference in within_orderings():
        for c in contradictions(believed, left=left, right=right,
                                identity=identity, incompatible=order):
            if c.left.cite.record_id == c.right.cite.record_id:
                within.setdefault(canonical_name(c.who) or "", []).append(
                    (kind, event, reference, c.left, c.right))
    return within, across


@dataclass(frozen=True)
class WithinFinding:
    """One appearance holding two dates its own entry orders wrongly: `left`
    is dated before `right`, which `kind` (an ordering of `orderings()`) says
    cannot be."""
    kind: str
    left: Dated
    right: Dated


def _before(a: Any, b: Any) -> str | None:
    return "before" if definitely_before(a.date, b.date) else None


def within_entry(facts: AssertionSet) -> list[WithinFinding]:
    """The class «inside one entry» of `date_order_findings`, asked without a
    consolidation: every appearance is its own person (`self_identity`), so
    what is compared is what ONE persona of ONE entry is said to have lived.

    The same table and the same comparison; the burial rows defer to a dated
    death of the same appearance, as there. It is what an entry read alone — a
    record on its card — can be asked. Two appearances of one entry that a
    consolidation folds into one person are not compared here, and are there.
    """
    believed = facts.believed()
    identity = self_identity()
    dated_death = held(believed, kind=DiedOn, identity=identity)
    found: list[WithinFinding] = []
    for left, right, kind, _event, _reference in (*orderings(), *within_orderings()):
        for c in contradictions(believed, left=left, right=right,
                                identity=identity, incompatible=_before):
            if kind in _BURIAL_DEFERS_TO_DEATH and c.who in dated_death:
                continue
            found.append(WithinFinding(kind=kind, left=c.left, right=c.right))
    found.sort(key=lambda f: (f.left.sort_key, f.right.sort_key, f.kind))
    # An ordering of `within_orderings()` is a couple's: both of them carry the
    # two dates, and the entry is said once — by the first of them it names —
    # as a wedding is asked once of the calendar.
    of_a_couple = {kind for _left, _right, kind, _event, _reference in within_orderings()}
    said: set[tuple[str, tuple[str, str, int, str, int]]] = set()
    once: list[WithinFinding] = []
    for f in found:
        if f.kind in of_a_couple:
            if (f.kind, f.left.cite.record_id) in said:
                continue
            said.add((f.kind, f.left.cite.record_id))
        once.append(f)
    return once


def unplaced_within(facts: AssertionSet, identity: Identity) -> list[WithinFinding]:
    """`within_entry` for the appearances `identity` places on nobody.

    A village is read through its consolidation, and a rule drops an
    appearance the bridge refuses — the people of a record the tree does not
    publish (an act of divorce) are all such. What their entry says of itself
    needs no one to say who they are, so it is asked of them alone, and the
    report of the village holds it beside the class «inside one entry».
    """
    unplaced = []
    for record in facts.believed().records():
        key_of = identity(record)
        unplaced += [a for a in record.assertions if key_of(a.subject) is None]
    return within_entry(AssertionSet(unplaced))
