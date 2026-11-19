"""Birth record → assertions. One of two files that may name a slot.

Everything downstream — the rule, the identity fold, a report's join — sees
predicates and citations. If any of that needs to come back here to ask "which
slot was this?", the design has failed.

On `Basis`: `Birth.__init__` derives residence, surname, сословие and gender
IN PLACE, so a reader of a constructed `Birth` usually cannot tell a stated
value from a derived one. Rather than guess, this extractor labels the one
case that left a breadcrumb (`last_name_in_book=False` ⇒ ASSUMED) and marks
the rest `Stated(basis_unknown=True)` so the gap can be priced separately.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from verso.ru.facts.extract.common import (
    Entry, RecordId, SlotIndex, claim_clergy, fact_date, kinship, reviewed, stated_unless)
from verso.ru.facts.model import (
    AgedYears, Assertion, BaptizedOn, BornOn, Derived, GodparentOf, ParentOf, Persona, SpouseOf, Stated, Surety)

__all__ = ["RECORD_KIND", "facts_from_births"]

RECORD_KIND = "birth"

_GODPARENT_SLOTS = ("god_parent1", "god_parent2", "god_parent3", "god_parent4")

# «восприемника №2» → godparent slot 2. The DSL writes this as prose and the
# translator reads it back with a regex (generator.py:2827); this extractor
# reads it HERE, once, and everything downstream sees a Persona.
_GP_REF = re.compile(r"восприемни[кц]\w*\s*№\s*(\d+)")  # i18n: content — the reference words the DSL writes


def facts_from_births(items: Iterable[tuple[Any, str]], *, village: str,
                      slots: SlotIndex | None = None, drafts: bool = False,
                      ids: RecordId | None = None) -> Iterator[Assertion]:
    """`items`: (Birth, source_filename) pairs, as the oracle's loader yields.
    `ids`: each record's id (`Entry`)."""
    for entry, (birth, source_file) in enumerate(items):
        if not (drafts or reviewed(birth)):
            continue
        yield from _facts_from_birth(birth, village, source_file, entry, slots, ids)


def _facts_from_birth(birth: Any, village: str, source_file: str, entry: int,
                      slots: SlotIndex | None = None,
                      ids: RecordId | None = None) -> list[Assertion]:
    e = Entry(birth, village=village, source_file=source_file,
              record_kind=RECORD_KIND, entry=entry, slots=slots, ids=ids)

    # The child: named, born, christened, resident.
    child_ref: Persona | None = None
    if birth.child is not None:
        # A child's residence and surname are filled in from the father by
        # `Birth.__init__`, in place and without a breadcrumb.
        #
        # So is the newborn's status, and it asserts nothing at all: the record
        # styles the PARENTS, and `Birth.__init__` derives the child's сословие
        # from the father's (the mother's when he has none) or takes the book's
        # default — two of 8051 newborns carry a status the author wrote, and
        # both restate a parent's. The translator never publishes it either.
        # Counting it would add 145 estate findings in Горюхино and 2 in
        # Заманиловка, every one resting on our inheritance rule; whether it
        # should is a separate question, asked after parity (2026-09-23).
        child_ref = e.claim(birth.child, "child",
                            residence_basis=Stated(basis_unknown=True),
                            own_status=False,
                            calendar_note=getattr(birth, "calendar_note", None))
        # A christening entry (`christening()`: a late or adult baptism) states
        # no birth at all. Its `b_month` is the section month `birth_month()`
        # fills in, and its year the book's — the day of the BAPTISM, not of
        # the birth — so reading them as a birth dated an eleven-year-old boy
        # to the month he was christened. What it may state is the age at
        # christening, and that is an age: evidence of a birth, not one.
        is_christening = bool(getattr(birth, "is_christening", False))
        born = (None if is_christening
                else fact_date(birth.b_day, birth.b_month, birth.year))
        if born:
            e.facts.append(BornOn(subject=child_ref, cite=e.cite("child"),
                                  date=born, basis=Stated()))
        # A book of the civil registry (`civil=True`) registers the birth: its
        # second date christens no one, so it asserts no baptism.
        christened = (None if getattr(birth, "civil", False)
                      else fact_date(birth.k_day, birth.k_month,
                                     getattr(birth, "k_year", None) or birth.year))
        age = getattr(birth, "christening_age", None)
        if is_christening and age is not None and christened:
            e.facts.append(AgedYears(subject=child_ref, cite=e.cite("child"),
                                     age=age, as_of=christened, basis=Stated()))
        if christened:
            # An author who has re-read the scan and found the SOURCE's two
            # dates inconsistent withdraws the christening: «крещение 11
            # октября записано раньше рождения 18 октября — так в подлиннике».
            # The transcription is faithful and there is nothing to fix, so the
            # date cannot order anything — but the source still says it, which
            # is why this wraps the basis instead of dropping the assertion.
            #
            # Narrower than the check it replaces on purpose: the oracle skips
            # the WHOLE profile, so a genuine death-before-birth on the same
            # person would go unreported too. Retracting the one claim the
            # author pointed at leaves every other assertion of the record
            # believed, which is the argument `Retracted` exists for.
            reason = getattr(birth, "source_date_error", None)
            e.facts.append(BaptizedOn(
                subject=child_ref, cite=e.cite("child"), date=christened,
                basis=stated_unless(reason),
                lag_note=getattr(birth, "lag_note", None) or None))

    # The parents. ORDER MATTERS: the report's tie-break follows insertion
    # order, and the oracle walks father before mother.
    parent_facts: list[ParentOf] = []
    for locator, person, place_basis in (
            ("father", birth.father, None),
            ("mother", birth.mother, Stated(basis_unknown=True))):
        if person is None:
            continue
        ref = e.claim(person, locator, residence_basis=place_basis)
        if child_ref is not None:
            f = ParentOf(subject=ref, cite=e.cite(locator), other=child_ref,
                         basis=Stated())
            e.facts.append(f)
            parent_facts.append(f)

    # Two people who are parents of one child were married — the inference the
    # translator makes by MINTING A RES_NAME (generator.py:2026) and then reads
    # back out of that string to re-classify незаконнорождённые (:1017). Here
    # it is an assertion with a reason, and its absence IS the illegitimacy.
    if len(parent_facts) == 2:
        basis = Derived("birth.co-parents-are-spouses", Surety.INFERRED,
                        tuple(parent_facts))
        a, b = parent_facts[0].subject, parent_facts[1].subject
        e.facts.append(SpouseOf(subject=a, cite=e.cite("father"), other=b, basis=basis))
        e.facts.append(SpouseOf(subject=b, cite=e.cite("mother"), other=a, basis=basis))

    # The godparents (восприемники), in slot order.
    for locator in _GODPARENT_SLOTS:
        gp = getattr(birth, locator, None)
        if gp is None:
            continue
        ref = e.claim(gp, locator)
        if child_ref is not None:
            e.facts.append(GodparentOf(subject=ref, cite=e.cite(locator),
                                       other=child_ref, basis=Stated()))

    # Named relatives. `relationship_ref` says WHICH appearance they hang off;
    # the prose is parsed here, once, and never again downstream.
    for i, rel in enumerate(getattr(birth, "relatives", None) or []):
        locator = f"relative{i + 1}"
        ref = e.claim(rel.person, locator)
        anchor = _anchor_ref(e, rel.relationship_ref, child_ref)
        if anchor is not None:
            e.facts.extend(kinship(ref, anchor, rel.relationship, e.cite(locator)))

    claim_clergy(e, birth, child_ref)
    return e.facts


def _anchor_ref(e: Entry, ref_text: str | None, child_ref: Persona | None) -> Persona | None:
    """Which appearance a relative attaches to. None ⇒ emit no relation."""
    if not ref_text:
        return None
    m = _GP_REF.search(ref_text)
    if m:
        return e.refs.get(f"god_parent{m.group(1)}")
    text = ref_text.strip().lower()
    if text.startswith("мат"):  # i18n: content — the reference words the DSL writes
        return e.refs.get("mother")
    if text.startswith("от"):  # i18n: content — the reference words the DSL writes
        return e.refs.get("father")
    if text.startswith("реб") or text.startswith("млад"):  # i18n: content — the reference words the DSL writes
        return child_ref
    return None
