"""Who an appearance IS — the one place identity policy lives.

The point of the separation: an assertion is about an appearance, and folding
appearances into people is a single pluggable function instead of a choice
smeared across three modules. The repo held three of them —
`godparent_cooccurrence._person_key` (canonicalize_name; retired with that
check on 2026-09-28), `death_age.person_key` (matching_base) and
`candidates.person_key` — with two incompatible `PersonKey` types between them.

`canonical_fold` reproduces the oracle exactly, so parity is measurable.
`matching_fold` is the deliberately more aggressive one («Егоръ» and «Георгій»
are one man): run it once, report the delta, act on nothing.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from verso.ru.gender import Gender
from verso.ru.naming import canonicalize_name
from verso.ru.naming.names_registry import matching_base

from verso.ru.facts.model import Assertion, AssertionSet, NameClaim, Persona, Record

#: Whatever a fold considers one person. A tuple so a rule can use it as a
#: dict key and put it in a set, and nothing more: its shape is the identity
#: policy's business, and a rule must never take it apart.
IdentityKey = tuple[str | None, ...]
Fold = Callable[[str | None, Gender | None], str]

#: How a rule turns appearances into people. One call per entry, then one call
#: per appearance. `name_identity` folds the written name; a config-backed
#: identity would read the consolidation config instead. The rule knows only
#: this shape — not that name folding exists.
Identity = Callable[["Record"], Callable[["Persona"], "IdentityKey | None"]]

# A name the book did not give. Folding these together would merge every
# anonymous person in the parish into one.
_PLACEHOLDERS = {"?", "[имя]", ""}  # i18n: content — the placeholder the DSL writes, a letter folded


def canonical_fold(given: str | None, gender: Gender | None) -> str:
    """The oracle's fold — `Person.get_canonical_name()`."""
    return canonicalize_name(given, gender)


def matching_fold(given: str | None, gender: Gender | None) -> str:
    """The sweep's fold — folds «Егоръ» onto «Георгій» via names.csv «Имя-основа»."""
    return matching_base(given, gender)


def _norm(s: str | None) -> str:
    """Fold for comparison: case, ё, surrounding space."""
    return (s or "").strip().lower().replace("ё", "е")  # i18n: content — the placeholder the DSL writes, a letter folded


def kin_identity(fold: Fold = matching_fold) -> Identity:
    """Name, patronymic and surname, each folded, none of them required.

    The three-part key the cross-record checks use. Its point is the PARTIAL
    match in `kin_matches`: a child in a birth record carries no patronymic and
    a revision list records no surnames at all, so a component missing on
    either side is not evidence of difference — only two stated components that
    DISAGREE are.
    """
    def make(record: Record) -> Callable[[Persona], IdentityKey | None]:
        cache: dict[Persona, IdentityKey | None] = {}

        def key(ref: Persona) -> IdentityKey | None:
            if ref in cache:
                return cache[ref]
            claims = [a for a in record.about(ref)
                      if isinstance(a, NameClaim) and a.given]
            result: IdentityKey | None = None
            if claims:
                c = claims[0]
                try:
                    folded = _norm(fold(c.given, c.gender))
                except Exception:
                    folded = ""
                if folded and folded not in _PLACEHOLDERS:
                    result = (folded, _norm(c.patronymic),
                              _norm(c.surname or c.birth_surname))
            cache[ref] = result
            return result
        return key
    return make


def kin_matches(a: IdentityKey, b: IdentityKey) -> bool:
    """Two keys that can be one person. Asymmetric evidence, not equality."""
    if not a or not b or not a[0] or a[0] != b[0]:
        return False
    for i in (1, 2):
        left = a[i] if i < len(a) else None
        right = b[i] if i < len(b) else None
        if left and right and left != right:
            return False
    return True


def identity_of(ref: Persona, record: Record, fold: Fold = canonical_fold) -> IdentityKey | None:
    """This appearance's identity key, or None when the record does not name them.

    Built only from the appearance's own `NameClaim` — never from its slot,
    never from the record kind.
    """
    claims = [f for f in record.about(ref) if isinstance(f, NameClaim)]
    if not claims:
        return None
    claim = claims[0]
    try:
        given = fold(claim.given, claim.gender)
    except Exception:
        given = None
    if not given or given in _PLACEHOLDERS:
        return None
    return (given, claim.patronymic)


def name_identity(fold: Fold = canonical_fold) -> Identity:
    """The identity a rule gets by default: the written name, folded."""
    def make(record: Record) -> Callable[[Persona], IdentityKey | None]:
        return IdentityCache(record, fold)
    return make


def self_identity() -> Identity:
    """Every appearance its own person: no fold at all.

    What a rule sees of ONE entry read alone, with no consolidation to say
    which appearances are one man: two claims meet only when one persona holds
    both. A persona's id is its entry's, so nothing is compared across entries.
    """
    return _own_keys


def _own_keys(_record: Record) -> Callable[[Persona], IdentityKey | None]:
    return _own_key


def _own_key(ref: Persona) -> IdentityKey | None:
    return (ref.id,)


class IdentityCache:
    """Identity lookups for ONE entry, memoised.

    A class rather than a closure so the rule stays free of a nested function
    capturing its loop variables (ruff B023) — and so the caching policy sits
    with the identity policy rather than with the rule.
    """

    def __init__(self, record: Record, fold: Fold = canonical_fold) -> None:
        self._record = record
        self._fold = fold
        self._cache: dict[Persona, IdentityKey | None] = {}

    def __call__(self, ref: Persona) -> IdentityKey | None:
        if ref not in self._cache:
            self._cache[ref] = identity_of(ref, self._record, self._fold)
        return self._cache[ref]


def display_name(claim: NameClaim, fold: Fold = canonical_fold) -> str:
    """«Фамилия Имя Отчество» — the oracle's `Person.get_fio()`."""
    try:
        given = fold(claim.given, claim.gender)
    except Exception:
        given = claim.given
    return " ".join(p for p in (claim.surname, given, claim.patronymic) if p) or "?"


@dataclass(frozen=True)
class Conclusion:
    """One person as an identity folds them: the key, and every claim the
    records make about them — GENTECH's conclusion person, GEDCOM X's `Person`
    with its evidence references. Built from assertions, never from a profile:
    what it holds is what the sources say, withdrawn claims included when the
    caller hands them in (`why()` prints the withdrawal).
    """
    key: IdentityKey
    claims: tuple[Assertion, ...]

    def of[A: Assertion](self, kind: type[A]) -> tuple[A, ...]:
        return tuple(a for a in self.claims if isinstance(a, kind))

    @property
    def personas(self) -> tuple[Persona, ...]:
        """Every appearance folded into this person, in the order the records
        give them."""
        return tuple(dict.fromkeys(a.subject for a in self.claims))


def conclusions(facts: AssertionSet, identity: Identity) -> dict[IdentityKey, Conclusion]:
    """Every person `identity` folds the assertions into, with the claims whose
    SUBJECT they are, in record order. An appearance the identity refuses is in
    no conclusion."""
    out: dict[IdentityKey, list[Assertion]] = {}
    for record in facts.records():
        key_of = identity(record)
        for a in record.assertions:
            who = key_of(a.subject)
            if who is not None:
                out.setdefault(who, []).append(a)
    return {who: Conclusion(key=who, claims=tuple(claims)) for who, claims in out.items()}
