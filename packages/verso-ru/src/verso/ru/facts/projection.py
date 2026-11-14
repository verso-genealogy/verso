"""Bridges between the fact model and the Geni domain objects.

Pure: no I/O, no CLI. The only module in `verso.ru.facts` allowed to know that
`verso.core.targets.geni` exists, and it exists so that nothing else has to.

Three bridges. Dates: every date comparison in the consolidation checks is
charitable-interval arithmetic over `GeniDate`, so a `FactDate` that rounds
badly would not fail loudly; it would quietly produce findings the oracle does
not have (`tests/test_facts_projection.py` pins the round trip against
`GeniDate`'s own `to_datetime`/`to_end_datetime`). Identity: which consolidated
profile an appearance belongs to (`consolidated_identity`). And which
appearances still stand as a profile of their own (`LooseIndex`) — both asked
of the translation, never of a res_name.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from verso.ru.facts.identity import Identity, IdentityKey
from verso.ru.facts.model import Bound, FactDate, Persona, Record
from verso.core.targets.geni.date import GeniDate


def fact_date(date: GeniDate | None) -> FactDate | None:
    """A `GeniDate` as the interval it actually asserts.

    `synthetic` is deliberately dropped. It exists on `GeniDate` because a date
    there cannot otherwise say whether a bound was read off a record or
    computed from a relative's — which is `Basis`, under another name. A caller
    that cares must carry it as `Derived`, not smuggle it inside the date.
    """
    if date is None:
        return None
    raw = getattr(date, "date_range", None)
    return FactDate(
        year=date.year,
        month=date.month,
        day=date.day,
        circa=bool(date.circa),
        bound=Bound(raw) if raw in tuple(b.value for b in Bound) else None,
        end_year=date.end_year,
        end_month=date.end_month,
        end_day=date.end_day,
        end_circa=bool(date.end_circa),
    )


def geni_date(date: FactDate | None) -> GeniDate | None:
    """The inverse. Never sets `synthetic` — see `fact_date`."""
    if date is None:
        return None
    return GeniDate(
        day=date.day,
        month=date.month,
        year=date.year,
        circa=date.circa,
        end_day=date.end_day,
        end_month=date.end_month,
        end_year=date.end_year,
        end_circa=date.end_circa,
        date_range=date.bound.value if date.bound else None,
    )


# --------------------------------------------------------------------------- #
# «Which consolidated person is this appearance?»
# --------------------------------------------------------------------------- #


class MintedProfiles(Protocol):
    """What the bridge needs of a finished translation, and nothing more."""

    def profile_minted_for(self, person: object) -> str | None: ...

    def resolve_canonical(self, res_name: str) -> str: ...


def consolidated_identity(
        minted: MintedProfiles,
        slot_object: Callable[[Persona], object | None],
) -> Identity:
    """Fold appearances the way the consolidation config already folds them.

    The third answer to a question the repository holds three answers to, and
    the only one that asks rather than guesses: the translator recorded which
    res_name it minted for each appearance, the config says which canonical that
    res_name folds into, and this composes the two. `slot_object` is what the
    extractor recorded — the DSL object behind a `Persona` — so the join needs
    no vocabulary and no res_name is ever rebuilt or parsed.

    The two rejected alternatives, both named in the plan: reconstructing a
    res_name duplicates the naming policy in `_profile_from_person`, where the
    choice between `last_name` and `birth_last_name` depends on the role; and
    parsing one back would be the sixth such parser in this repository, and the
    largest corpus (Заманиловка) has no generated tree to parse.

    **It refuses rather than guesses.** An appearance nobody minted a profile
    for — a held двор, a name the DSL skipped — gets `None`, and a rule drops
    it. That is the property the spike measured and the reason this is a
    bridge and not a heuristic: a wrong fold invents a person, where a refusal
    only declines to answer.
    """
    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        def key(who: Persona) -> IdentityKey | None:
            obj = slot_object(who)
            if obj is None:
                return None
            res_name = minted.profile_minted_for(obj)
            if res_name is None:
                return None
            return (minted.resolve_canonical(res_name),)
        return key
    return identity


def canonical_name(key: IdentityKey | None) -> str | None:
    """The canonical res_name a `consolidated_identity` key names, or None.

    The one place that knows the bridge's key is `(res_name,)`. A caller asks
    here rather than unpacking the tuple, so a richer key costs one function —
    and a key some other identity produced (a folded written name) is never
    mistaken for a res_name by a caller that reached into it.
    """
    if not key or not key[0]:
        return None
    return key[0]


def canonical_key(res_name: str) -> IdentityKey:
    """The `consolidated_identity` key of one canonical — `canonical_name`'s
    inverse, for a caller that starts from a res_name (`facts-why person=`)."""
    return (res_name,)


class LooseIndex:
    """Which appearances still stand as a profile of their own, and under what
    res_name — asked of the translation, not of the files it wrote.

    The translator records the res_name it minted for each appearance
    (`profile_minted_for`), and the consolidation config says whether that
    res_name was folded into a cluster (`in_profile_move_list`): a folded one
    moves from `mk_*.tf` to `consolidated_profiles_*.tf`, and one nobody minted
    never had a profile. A standing profile is LOOSE when the config does not
    name it at all, and `folded` when it does without folding it (a keeper, an
    ignore, a preference).

    Until 2026-09-28 this came from `godparent_cooccurrence.ConsolidationIndex`,
    which globbed `mk_*_birth.tf` and matched a res_name regex plus a name
    token rebuilt from the record — the sixth res_name parser. Заманиловка has no
    generated tree, so there it printed every one of its records as
    «already consolidated» and `--loose-only` dropped them all.
    """

    def __init__(self, gen: Any, slots: Any, config_text: str) -> None:
        self._gen = gen
        self._slots = slots
        self.config_text = config_text

    def resolve(self, who: Persona) -> str | None:
        """The res_name `who`'s own profile stands under, or None when it was
        folded into a cluster or never minted."""
        obj = self._slots.object_of(who)
        minted = self._gen.profile_minted_for(obj) if obj is not None else None
        if minted is None or self._gen.consolidation.in_profile_move_list(minted):
            return None
        return minted

    def is_loose(self, who: Persona) -> bool:
        name = self.resolve(who)
        return bool(name) and name not in self.config_text
