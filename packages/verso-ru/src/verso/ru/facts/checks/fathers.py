"""One person's records naming two different fathers — `check=father-claims`.

An over-merge channel, beside `birth-claims`: every other discovery channel
looks for a fold not yet made, these two look for one that went too far. A man
fathered by Мартин in one record and by Мирон in another; a man who is
Сергеевич in one book and Терентьевич in a later one.

A record says who someone's father is in one of two ways: a patronymic on the
person, or a man it makes their parent (a newborn in a birth record has no
patronymic; the record names the father). Each is a FATHER CLAIM. Two claims
AGREE when they share a comparison key, and there are several kinds of key, so
that one gap in the names table cannot manufacture a finding:

- the patronymic, canonical and in the child's gender — for a named father,
  the patronymic his name derives (`derive_patronymic`): «Изот» and
  «Изотович» agree here though the table's base for «Изотович» is «Зотей»;
- the father's given name by its base form — for a patronymic, the father the
  names table reads out of it: «Егорович» and «Георгиевич» agree here;
- for a name the table does not know at all — the pre-Christian names of the
  1717–1721 rolls — the patronymic beginning with the father's name less its
  final vowel: «Шумила» and «Шумилович», «Пичкинза» and «Пичкинзин»;
- and a NAMED father is known by every name his own records give him. The
  later rolls write «Павел Тимофеевъ» for the man the metric books
  call «Петр Тимофеевъ Ежевикинъ»; the corpus has folded the two into one
  canonical, so a son's «Павловъ» and his christening's «отец Петр»
  name one father. Two named fathers folded into one canonical agree however
  they are spelled.

Agreement is not transitive — «Бурмяевич» and «Бурмящевич» each agree with a
named «Бурмяй» and not with each other — so a person is a finding only when
their claims fall into two or more GROUPS that no chain of agreement joins.
From two records, that is a signal the records are of two people — the
channel's finding. From ONE record, the record contradicts itself (a death
whose father is «Михей» and whose deceased is «Михайловна»): the DSL or the
scan, not a fold — unless the entry already says so with
`source_kin_error=`, which the caller passes in as `acknowledged`. A
disagreement resting only on a father we reconstructed (a `Derived` census
parent) is LOW.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from verso.ru.facts.identity import Identity
from verso.ru.facts.model import AssertionSet, Citation, Derived, NameClaim, ParentOf
from verso.ru.facts.projection import canonical_name
from verso.ru.gender import Gender
from verso.ru.naming.fathers import father_keys, fold, name_stem, patronymic_keys
from verso.ru.messages import t


@dataclass(frozen=True)
class FatherClaim:
    """What one record says about someone's father, and on whose authority.
    `stems` is set on a named father, `raw` on a patronymic."""
    said: str
    keys: frozenset[str]
    cite: Citation
    derived: bool
    stems: frozenset[str] = frozenset()
    raw: str = ""


def agree(a: FatherClaim, b: FatherClaim) -> bool:
    """Whether two claims can name one father."""
    if a.keys & b.keys:
        return True
    for named, patronymic in ((a, b), (b, a)):
        if patronymic.raw and any(len(stem) >= 3 and patronymic.raw.startswith(stem)
                                  for stem in named.stems):
            return True
    return False


def groups(claims: tuple[FatherClaim, ...]) -> list[tuple[FatherClaim, ...]]:
    """The claims joined by chains of agreement, the group with the most
    records first — so the smaller groups name the records that stand apart."""
    parent = list(range(len(claims)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(claims):
        for j in range(i + 1, len(claims)):
            if agree(a, claims[j]):
                parent[root(j)] = root(i)
    joined: dict[int, list[FatherClaim]] = {}
    for i, c in enumerate(claims):
        joined.setdefault(root(i), []).append(c)
    return sorted((tuple(g) for g in joined.values()),
                  key=lambda g: (-len({c.cite.record_id for c in g}), g[0].cite.sort_key))


@dataclass(frozen=True)
class FatherFinding:
    """A person whose father claims fall into groups no agreement joins.
    `across` are the pairs from two records (a fold signal), `within` the
    pairs one record states, `acknowledged` those of a record that already
    says its kin names disagree."""
    canonical: str
    groups: tuple[tuple[FatherClaim, ...], ...]
    across: tuple[tuple[FatherClaim, FatherClaim], ...]
    within: tuple[tuple[FatherClaim, FatherClaim], ...]
    acknowledged: tuple[tuple[FatherClaim, FatherClaim, str], ...] = ()

    @property
    def confidence(self) -> str:
        if not self.across:
            return ""
        weak = all(a.derived or b.derived for a, b in self.across)
        return "LOW" if weak else "HIGH"

    @property
    def apart(self) -> int:
        """How many records stand outside the largest group. One record
        against twelve is as often a scribe's slip on one line as a stranger
        folded in; three against eight is rarely a slip."""
        records = {c.cite.record_id for g in self.groups for c in g}
        return len(records - {c.cite.record_id for c in self.groups[0]})


def _given_names(facts: AssertionSet, identity: Identity) -> dict[str, set[str]]:
    """Every given name each canonical's records call him by."""
    out: dict[str, set[str]] = {}
    for record in facts.records():
        key_of = identity(record)
        for a in record.of(NameClaim):
            if not a.given or "?" in a.given:
                continue
            who = canonical_name(key_of(a.subject))
            if who is not None:
                out.setdefault(who, set()).add(a.given)
    return out


def father_claims(facts: AssertionSet, identity: Identity) -> dict[str, list[FatherClaim]]:
    """Every father claim of every placed person, by canonical, record order."""
    names_of = _given_names(facts, identity)
    out: dict[str, list[FatherClaim]] = {}
    for record in facts.records():
        key_of = identity(record)
        for a in record.of(NameClaim):
            patronymic = a.patronymic
            if not patronymic or "?" in patronymic:
                continue
            who = canonical_name(key_of(a.subject))
            if who is None:
                continue
            out.setdefault(who, []).append(FatherClaim(
                said=f"«{patronymic}»", keys=patronymic_keys(patronymic, a.gender),
                cite=a.cite, derived=isinstance(a.basis, Derived),
                raw=fold(patronymic)))
        for edge in record.of(ParentOf):
            father = next((c for c in record.about(edge.subject)
                           if isinstance(c, NameClaim) and c.given
                           and c.gender == Gender.MALE and "?" not in c.given), None)
            if father is None or father.given is None:
                continue
            who = canonical_name(key_of(edge.other))
            if who is None:
                continue
            child = next((c.gender for c in record.about(edge.other)
                          if isinstance(c, NameClaim) and c.gender), None)
            his = canonical_name(key_of(edge.subject))
            known_as = {father.given} | (names_of.get(his, set()) if his else set())
            keys = frozenset().union(*(father_keys(g, child) for g in known_as))
            if his is not None:
                keys |= {"c:" + his}
            out.setdefault(who, []).append(FatherClaim(
                said=str(t("facts.fathers.father", name=father.given)), keys=keys, cite=edge.cite,
                derived=isinstance(edge.basis, Derived),
                stems=frozenset(name_stem(g) for g in known_as)))
    return out


def father_findings(facts: AssertionSet, identity: Identity,
                    acknowledged: Callable[[Citation], str | None] | None = None,
                    ) -> list[FatherFinding]:
    """People whose father claims disagree: fold signals first, HIGH first,
    then the most records standing apart.

    `acknowledged` returns the entry's own note that its kin names disagree
    (`source_kin_error=`), which stands a within-record pair down."""
    found: list[FatherFinding] = []
    for canonical, claims in father_claims(facts, identity).items():
        joined = groups(tuple(claims))
        if len(joined) < 2:
            continue
        group_of: Mapping[int, int] = {id(c): n for n, g in enumerate(joined) for c in g}
        across: list[tuple[FatherClaim, FatherClaim]] = []
        within: list[tuple[FatherClaim, FatherClaim]] = []
        noted: list[tuple[FatherClaim, FatherClaim, str]] = []
        for i, a in enumerate(claims):
            for b in claims[i + 1:]:
                if group_of[id(a)] == group_of[id(b)]:
                    continue
                if a.cite.record_id != b.cite.record_id:
                    across.append((a, b))
                elif acknowledged is not None and (note := acknowledged(a.cite)):
                    noted.append((a, b, note))
                else:
                    within.append((a, b))
        found.append(FatherFinding(canonical=canonical, groups=tuple(joined),
                                   across=tuple(across), within=tuple(within),
                                   acknowledged=tuple(noted)))
    found.sort(key=lambda f: (not f.across, f.confidence != "HIGH", -f.apart,
                              f.canonical))
    return found
