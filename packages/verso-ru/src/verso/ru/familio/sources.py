"""What each canonical's records say about them, as the familio projection cites it.

A familio person carries a comment on each event — the text of the record that
documents it — and until 2026-09-28 the projection found those records by cutting
the canonical's joined Geni `about` apart with a header regex and guessing, from
the role word after each header, which event the section was: «смерт» for a death
(the translator writes «умерший», so no death was ever found), «рожден» for a
birth («крещение» is one too), «жених»/«невест» for a wedding («отец невесты» is
not). The records are known structurally elsewhere:

- the facts layer knows every appearance of a canonical — which record, of what
  kind, in which slot, in what year (`Citation`, placed by `consolidated_identity`);
- the translator knows the about section it minted for that very appearance
  (`TerraformGenerator.section_minted_for`).

An `Appearance` joins the two. Which event it documents is a table over the
record's kind and slot (`Appearance.event`) — a renderer may name those; a facts
rule may not, which is why this lives in `verso.ru.familio` and not in `verso.ru.facts`.

Pure: the caller hands in the assertions, the identity and the section lookup.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from verso.ru.ages import format_age
from verso.ru.facts.identity import Identity
from verso.ru.facts.model import (
    AgedYears, AssertionSet, DiedOn, NameClaim, ParentOf, Persona, Retracted, SpouseOf, Titled)
from verso.ru.facts.projection import canonical_name

#: (record kind, slot) → the event of THIS person the record documents. Slots
#: not listed — a parent, a godparent, a witness, a named relative, a list
#: entry, a catalog card — document no event of the person they name.
_EVENTS: dict[tuple[str, str], str] = {
    ("birth", "child"): "birth",        # a christening() entry is a birth record too
    ("death", "deceased"): "death",
    ("marriage", "groom"): "marriage",
    ("marriage", "bride"): "marriage",
}

#: A marriage slot and the role word its section's header ends with.
MARRIAGE_ROLE = {"groom": "жених", "bride": "невеста"}


@dataclass(frozen=True)
class Appearance:
    """One record naming a canonical: where, and the section minted for it.

    `title` and `age` are what the record states of the person — `Titled`
    verbatim and `AgedYears` rendered by `format_age`, the renderer the
    section's own «Титул/звание» and «Возраст» lines were written with.
    `spouse` and `children` are the canonicals the record marries the person
    to and names them the parent of (`SpouseOf`, `ParentOf`); `record` is the
    entry, so two appearances in one record can be told apart from two records.
    `died` says the record states the person's death (`DiedOn`) — a burial
    does, and so does a roll listing a member dead since the last revision."""
    kind: str
    slot: str
    year: int | None
    text: str
    title: str = ""
    age: str = ""
    record: tuple[object, ...] = ()
    spouse: str | None = None
    children: frozenset[str] = frozenset()
    died: bool = False

    @property
    def event(self) -> str:
        """The event of this person the record documents: birth, death,
        marriage, census (a roll counting them — an age, so an indirect birth
        source), or "" for none."""
        if self.kind == "census" and self.slot.startswith("member"):
            return "census"
        return _EVENTS.get((self.kind, self.slot), "")

    @property
    def weds_children(self) -> frozenset[str]:
        """The children whose wedding this record is, where it names this
        person their parent («отец жениха», «мать невесты»)."""
        return self.children if self.kind == "marriage" else frozenset()


def appearances_by_canonical(
        facts: AssertionSet, identity: Identity,
        section_of: Callable[[Persona], str | None],
) -> dict[str, list[Appearance]]:
    """Every appearance of every placed person that was minted a section, by
    canonical res_name, in extraction order.

    `facts` should be ALL the assertions, retracted ones included: a section
    prints the age its record states even when the author withdrew it from
    dating the birth (`source_age_error=`), and `age` has to read the same."""
    out: dict[str, list[Appearance]] = {}
    for record in facts.records():
        key_of = identity(record)
        seen: set[Persona] = set()
        for name in record.of(NameClaim):
            persona = name.subject
            if persona in seen:
                continue
            seen.add(persona)
            canonical = canonical_name(key_of(persona))
            text = section_of(persona)
            if canonical is None or not text:
                continue
            said = record.about(persona)
            title = next((a.status for a in said if isinstance(a, Titled)), "")
            aged = next((a.age for a in said if isinstance(a, AgedYears)), None)
            believed = [a for a in said if not isinstance(a.basis, Retracted)]
            spouses = [canonical_name(key_of(a.other)) for a in believed
                       if isinstance(a, SpouseOf)]
            kids = [canonical_name(key_of(a.other)) for a in believed
                    if isinstance(a, ParentOf)]
            spouse = next((c for c in spouses if c is not None), None)
            children = frozenset(c for c in kids if c is not None)
            out.setdefault(canonical, []).append(Appearance(
                kind=name.cite.record_kind, slot=name.cite.locator,
                year=name.cite.year, text=text, title=title,
                age=(format_age(aged) or "") if aged is not None else "",
                record=name.cite.record_id, spouse=spouse, children=children,
                died=any(isinstance(a, DiedOn) for a in believed)))
    return out


def in_about_order(appearances: list[Appearance], about: str | None) -> list[Appearance]:
    """The appearances in the order their sections stand in the canonical's
    about, and only those that stand there.

    The about is the translator's fold of these very sections, sorted; where a
    section lies is found by its known text, not by cutting the narrative. A
    section the fold dropped because another one already contains it (the
    translator's substring de-duplication) is dropped here too."""
    if not about:
        return []
    placed: list[tuple[int, int, Appearance]] = []
    for i, a in enumerate(appearances):
        if any(a.text != b.text and a.text in b.text for b in appearances):
            continue
        at = about.find(a.text)
        if at >= 0 and not any(p[2].text == a.text for p in placed):
            placed.append((at, i, a))
    return [a for _, _, a in sorted(placed, key=lambda p: (p[0], p[1]))]
