"""How far the appearance→canonical bridge reaches — `facts-check check=identity`.

The bridge composes two statements the corpus already makes, so there is
nothing for it to disagree with; what is worth measuring is its REACH, and the
invariants a sound bridge keeps: no refusal beyond the причт, no canonical
holding more appearances than its fold explains, no appearance minted twice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from verso.ru.facts.extract.common import CLERGY_SLOTS
from verso.ru.facts.model import AssertionSet, Citation, Persona, Record
from verso.ru.facts.projection import canonical_name, consolidated_identity


@dataclass(frozen=True)
class IdentityReach:
    """What `identity_report` prints, as numbers."""
    total: int
    refused: dict[tuple[str, str], int]
    placed: dict[str, list[Citation]]
    repeated_number: int
    surplus: int
    minted_twice: int

    @property
    def refused_beyond_clergy(self) -> int:
        """Refusals the причт does not explain — each one a bridge defect or a
        new class of appearance nobody mints a profile for."""
        return sum(n for (_kind, slot), n in self.refused.items()
                   if slot not in CLERGY_SLOTS)


def identity_reach(facts: AssertionSet, gen: Any, slots: Any) -> IdentityReach:
    """How far the appearance→canonical bridge reaches, and where it refuses.

    The bridge composes two statements the corpus already makes — the res_name
    the translator minted for an appearance, and the canonical that res_name
    folds into — so there is nothing for it to disagree with. What is worth
    measuring is its REACH, and the reach has a floor that is not a defect:
    the причт gets no profile at all (`_emit_clergy` had no caller and three
    tests pin that clergy profiles are not emitted), so every priest, deacon,
    dyachok and sexton the books name is an appearance nobody minted. The
    refusals are printed BY SLOT for that reason — the reader should be able to
    see what is being declined, not just how much.

    Two independent cross-checks come with it. Every appearance placed on a
    canonical must be one that canonical absorbed, so a canonical holding more
    appearances than the move list explains is either a bridge error or a
    repeated record number, and the report distinguishes them. And an
    appearance that received two profiles would make the key ambiguous — that
    is `minted_twice`, and it is empty everywhere today.
    """
    # The bridge reads only the appearance, so one call site is enough; the
    # per-record shape of `Identity` is for folds that read a record's names.
    key_of = consolidated_identity(gen, slots.object_of)(Record(()))

    placed: dict[str, list[Citation]] = {}
    refused: dict[tuple[str, str], int] = {}
    seen: set[Persona] = set()
    for a in facts:
        if a.subject in seen:
            continue
        seen.add(a.subject)
        canon = canonical_name(key_of(a.subject))
        if canon is None:
            slot = (a.cite.record_kind, a.cite.locator)
            refused[slot] = refused.get(slot, 0) + 1
            continue
        placed.setdefault(canon, []).append(a.cite)

    total = len(seen)
    move_list = dict(getattr(gen.consolidation, "profile_move_list", {}))
    absorbed: dict[str, int] = {}
    for canonical in move_list.values():
        absorbed[canonical] = absorbed.get(canonical, 0) + 1

    # A canonical holding more appearances than the move list folded into it.
    # Not a bridge error when the extra appearances share a record NUMBER: the
    # res_name is built from the number, so two entries numbered alike mint one
    # profile and legitimately collapse. Anything else would be a bridge error.
    repeated_number = surplus = 0
    for canonical, cites in placed.items():
        if len(cites) <= max(absorbed.get(canonical, 0) + 1, 1):
            continue
        keys = {(c.source_file, c.record_num, c.locator) for c in cites}
        if len(keys) < len(cites):
            repeated_number += 1
        else:
            surplus += 1
    return IdentityReach(total=total, refused=refused, placed=placed,
                         repeated_number=repeated_number, surplus=surplus,
                         minted_twice=len(gen.minted_twice()))
