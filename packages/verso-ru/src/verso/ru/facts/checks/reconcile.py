"""A list entry or catalog card standing alone, and the canonicals it may be.

The sixth discovery channel (`verso reconcile`). A name list and an external
card each mint a deliberate duplicate of somebody the metric books and rolls
already hold, for the corpus's consolidation to join; until 2026-09-28 finding that somebody was done by
hand, by a rule written down in a per-village note — the same
given name by its base form, the same father by the patronymic, the surname
within a scribe's variant, and the birth year where the source gives one. This
is that rule, over the assertions.

A TARGET is a person whose every record is a list or a card — a single
appearance, or cards already joined to each other and to nothing else. The
POOL is every person with at least one record of the corpus proper (a birth,
a marriage, a death, a roll). A pool person is a MATCH when:

- the given name agrees by its base form (`matching_base`);
- the father agrees by the patronymic (`father_name_for_patronymic`) — or
  either side's patronymic is not written, which is not a reason against;
- a surname of the target is within one letter of a surname the person's
  own records carry (`within_one_letter` on `normalise_surname` roots), or is
  a spelling of that family the corpus has already learned: two roots at most
  two letters apart that the records of ONE man both carry (a man does not
  change his surname, so his records spelling it two ways — Бикешеев in a card,
  Бекешев in the metric books — say the two are one family). A person with no
  surname in any record is never a match: the revision-only canonical is the
  case that needs a human.

The father is read from the patronymic and, where a record names the father
outright — a newborn in a birth record carries no patronymic — from that
record's father.

A match is RETIRED, with its reason, when:

- `SAME_LIST` — the person already holds an entry of the same list: two
  entries of one list are two people;
- `SAME_HOUSEHOLD` — both are counted into one household of one roll: the
  scribe listed them apart (`EnumeratedIn`, the guard `union-dups` stands on);
- `BIRTH_APART` — the target states a birth (a year, a date, an age on a
  day) that no birth claim of the person can share (`checks.births.birth_gap`,
  the measured slack, an old age made older forgiven);
- `TWO_BAPTISMS` — each has an entry christening them, on births that cannot
  be one day (`checks.lives.two_baptisms`, the guard `union-dups` stands on):
  one entry christens one child, so the parents reused the name. The slack of
  `BIRTH_APART` is for an age someone told; two christenings are written on the
  day, and a boy born in October 1915 and one born in June 1916 are two boys;
- `SEEN_BEFORE_BIRTH` — one of the two is named in an entry written before the
  other's earliest dated birth (`BornOn`) less the birth slack: whoever a
  record names was born by the day it was written. An age is `BIRTH_APART`'s;
- `LIFE_APART` — one of the two is dead before the other is seen alive
  (`checks.lives.outlived`, a circa year read at its slack) — or before the
  other stands at a font, a wedding or a child's cradle (`PRESENT_SLOTS`: a
  godparent, a witness, a groom, a bride, a mother, a child; never a father or
  a named relative, who may be named after their death).

One match surviving is a CANDIDATE — HIGH when the target stated a birth
and the person holds one to check it against, MEDIUM otherwise, and MEDIUM
too when a namesake was retired for `TWO_BAPTISMS`: he was born inside the
window that check allows, so the survivor may be him grown up. More than one
is AMBIGUOUS: namesakes, and a human reads the households. None is NONE.

The households are on the list itself, where the list runs household by
household (`name_list_records(household_order=True)` — Горюхино's and
Заманиловка's 1917 lists; Маниловка's is sorted by given name, and its neighbours
say nothing). A match is BACKED when the canonical a NEIGHBOUR of the entry is
— its own, if that entry is already folded, else each survivor of its own
matching — is the match's spouse, parent or child by the records of the corpus
(`checks.neighbours`). A backed single survivor is HIGH; among several
survivors, the one backed alone is the CANDIDATE, HIGH, and the namesakes stay
in the report unbacked. Measured on 2026-09-29, before the list order was
declared: Горюхино 81 of 193 candidates backed and 10 of 26 ambiguous entries
resolved; the same targets asked of the entries 97 numbers on back none, and of
their own surname's entries more than 20 numbers away, 6. The span (4) and the
kin (one step: spouse, parent, child) are where that measure was flat — 2 and
8 numbers, or a sibling and an in-law as well, move a handful either way.
Absent backing is no reason against: a household split over two pages, a wife
the books hold under her maiden name.

The matcher serves more than this channel. A `Channel` says who is looked for
(`is_target`), among whom (`in_pool`), which folded appearance its oracle may
take back out (`auditable`) and whether the father must be written on both
sides; `LISTS_AND_CARDS` is this one, and `name-variants` is the second
(`verso.ru.consolidation.name_variants`): a loose record of the corpus proper
against the canonicals, the father required, as that channel always did.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from verso.ru.facts.checks.births import BIRTH_SLACK_YEARS, birth_gap, birth_span
from verso.ru.facts.checks.dates import as_read
from verso.ru.facts.checks.lives import (
    Day, LifeMark, Lives, lives_of_canonicals, outlived, two_baptisms)
from verso.ru.facts.checks.neighbours import (
    INVERSE, Kin, ListEntry, Neighbourhood, fits_ages, kin_of_canonicals, list_entries)
from verso.ru.facts.identity import Identity, IdentityKey, conclusions
from verso.ru.facts.model import (
    AgedYears, Assertion, AssertionSet, BornOn, Citation, Dated, EnumeratedIn, NameClaim, ParentOf, Persona, Record)
from verso.ru.facts.projection import canonical_name
from verso.ru.gender import Gender
from verso.ru.naming import father_name_for_patronymic, matching_base
from verso.ru.naming.surnames import normalise_surname, within_one_letter
from verso.ru.messages import t

#: The record kinds a target is made of: the deliberate duplicates.
TARGET_KINDS = frozenset({"list", "external"})

VERDICT_CANDIDATE = "CANDIDATE"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_NONE = "NONE"

RETIRED_BIRTH_APART = "BIRTH_APART"
RETIRED_LIFE_APART = "LIFE_APART"
RETIRED_SAME_LIST = "SAME_LIST"
RETIRED_SAME_HOUSEHOLD = "SAME_HOUSEHOLD"
RETIRED_SEEN_BEFORE_BIRTH = "SEEN_BEFORE_BIRTH"
RETIRED_TWO_BAPTISMS = "TWO_BAPTISMS"

#: The slots whose person was alive on the day of the entry: at the font, the
#: wedding, the cradle. A father may be named after his death, and so may any
#: relative a record names — they are not here.
PRESENT_SLOTS = ("child", "mother", "god_parent", "groom", "bride", "witness")

#: Each entry as the days it can have been written on: (the earliest day any
#: dated claim of it can mean, the latest).
EntryDays = dict[tuple[object, ...], tuple[Day, Day]]

#: Letters the corpus spells two ways, folded so a pre-reform spelling cannot
#: split a key — the same fold `split-couples` compares partners with.
_FOLD = str.maketrans({"ѳ": "ф", "і": "и", "ѣ": "е", "ѵ": "и", "ё": "е",  # i18n: content — the old letters folded
                       "й": "и", "ъ": None})  # i18n: content — the old letters folded


def _fold(text: str | None) -> str:
    return (text or "").strip().lower().translate(_FOLD)


@dataclass(frozen=True)
class NameKeys:
    """What a person's records call them, as comparison keys: given-name
    bases, fathers by the patronymic, surname roots. Never written anywhere."""
    given: frozenset[str]
    fathers: frozenset[str]
    roots: frozenset[str]


def name_keys(claims: Iterable[Assertion],
              stated_fathers: dict[Persona, frozenset[str]] | None = None) -> NameKeys:
    held = tuple(claims)
    given: set[str] = set()
    fathers: set[str] = set()
    roots: set[str] = set()
    for who in {c.subject for c in held}:
        fathers |= (stated_fathers or {}).get(who, frozenset())
    for c in held:
        if not isinstance(c, NameClaim):
            continue
        if c.given and "?" not in c.given:
            base = _fold(matching_base(c.given, c.gender))
            if base:
                given.add(base)
        if c.patronymic and "?" not in c.patronymic:
            father = father_name_for_patronymic(c.patronymic)
            fathers.add(_fold(matching_base(father, Gender.MALE)) if father
                        else _fold(c.patronymic))
        for surname in (c.surname, c.birth_surname):
            if surname and surname.strip() and "?" not in surname:
                roots.add(normalise_surname(surname))
    return NameKeys(frozenset(given), frozenset(fathers), frozenset(roots))


@dataclass(frozen=True)
class Side:
    """One person as the channel reads them: the key, the claims, and what
    their records call them."""
    key: IdentityKey
    claims: tuple[Assertion, ...]
    names: NameKeys

    @staticmethod
    def of(key: IdentityKey, claims: Iterable[Assertion],
           stated_fathers: dict[Persona, frozenset[str]] | None = None) -> Side:
        held = tuple(claims)
        return Side(key=key, claims=held, names=name_keys(held, stated_fathers))

    @property
    def records(self) -> int:
        return len({c.cite.record_id for c in self.claims})

    @property
    def male(self) -> bool:
        return any(isinstance(c, NameClaim) and c.gender == Gender.MALE
                   for c in self.claims)

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(c.cite.record_kind for c in self.claims)

    @property
    def births(self) -> tuple[Assertion, ...]:
        return tuple(c for c in self.claims if isinstance(c, (BornOn, AgedYears)))

    @property
    def lists(self) -> frozenset[str]:
        return frozenset(c.cite.source_file for c in self.claims
                         if c.cite.record_kind == "list")

    @property
    def households(self) -> frozenset[object]:
        """The households of rolls this person is counted into."""
        return frozenset(c.payload for c in self.claims if isinstance(c, EnumeratedIn))

    @property
    def entries(self) -> dict[tuple[object, ...], Citation]:
        """Each entry naming this person, by its first citation."""
        out: dict[tuple[object, ...], Citation] = {}
        for c in self.claims:
            out.setdefault(c.cite.record_id, c.cite)
        return out

    def born_by(self) -> LifeMark | None:
        """The earliest day a dated birth of this person can be, less the
        slack two birth claims are compared with (`BIRTH_SLACK_YEARS`: a card's
        year of birth is a year someone wrote down, not a baptism), and how it
        is said — the most charitable of two, where a fold holds two."""
        best: LifeMark | None = None
        for c in self.claims:
            if isinstance(c, BornOn) and (first := as_read(c.date).earliest) is not None:
                slack = (first[0] - int(BIRTH_SLACK_YEARS), first[1], first[2])
                if best is None or slack < best[0]:
                    best = (slack, str(t("facts.reconcile.born", date=c.date, cite=_label(c.cite))))
        return best

    def present(self, entries: EntryDays) -> frozenset[LifeMark]:
        """The first day of each entry that places this person alive at it."""
        marks: set[LifeMark] = set()
        for c in self.claims:
            if c.cite.locator.startswith(PRESENT_SLOTS) and c.cite.record_id in entries:
                first = entries[c.cite.record_id][0]
                marks.add((first, f"{c.cite.locator} [{_label(c.cite)}]"))
        return frozenset(marks)

    def lives(self) -> Lives:
        """This person's baptisms, deaths and signs of life, from these claims
        alone — so an audit that takes a card out of a canonical reads the
        canonical without it."""
        name = canonical_name(self.key) or ""

        def everyone(_who: Persona) -> IdentityKey:
            return (name,)

        def one(_record: Record) -> Callable[[Persona], IdentityKey | None]:
            return everyone
        found = lives_of_canonicals(AssertionSet(self.claims), one)
        return found.get(name, Lives())


@dataclass(frozen=True)
class Backing:
    """A neighbour on the list, the canonical it is (or may be), and what that
    canonical is to the match: «супруг(а)», «родитель», «ребёнок». `by_name`:
    the canonical is the match's kin named like the neighbour — given name and
    father, the surname left out — rather than one the neighbour's own
    matching found."""
    neighbour: ListEntry
    canonical: IdentityKey
    relation: str
    by_name: bool = False


@dataclass(frozen=True)
class Match:
    """A pool person the target's name matches, and whether a guard retired
    them. `father` is True when both patronymics name one father, None when
    either is not written. `backed` is the list neighbours who vouch for them."""
    person: Side
    retired: str | None
    reason: str
    father: bool | None
    birth_checked: bool
    backed: tuple[Backing, ...] = ()


@dataclass(frozen=True)
class Reconciliation:
    target: Side
    verdict: str
    confidence: str
    matches: tuple[Match, ...]
    #: The candidate was chosen among namesakes by the list's neighbours alone.
    by_neighbours: bool = False
    #: Other entries of the same list the channel proposed the same person for:
    #: two entries of one list are two people, so none of them is a candidate.
    contested: tuple[str, ...] = ()
    #: No name of the corpus matched the entry; its match was found as the kin
    #: of a neighbour's canonical, named like it with the surname left out.
    through_neighbour: bool = False

    @property
    def survivors(self) -> tuple[Match, ...]:
        return tuple(m for m in self.matches if m.retired is None)

    @property
    def proposed(self) -> tuple[Match, ...]:
        """Whom the channel proposes: the candidate, or every survivor."""
        survivors = self.survivors
        return survivors[:1] if self.is_candidate else survivors

    @property
    def is_candidate(self) -> bool:
        return self.verdict == VERDICT_CANDIDATE


Aliases = dict[str, frozenset[str]]


def _one_family(a: str, b: str, aliases: Aliases) -> bool:
    """Two surname roots one family writes: one letter apart, a spelling the
    corpus has learned, or one letter away from a learned spelling — «Бокешеев»
    is a letter from «Бикешеев», which the records of one man already join to
    «Бекешев»."""
    if within_one_letter(a, b) or b in aliases.get(a, frozenset()):
        return True
    return any(b in others and within_one_letter(a, known)
               for known, others in aliases.items())


def _names_match(tk: NameKeys, p: NameKeys, aliases: Aliases,
                 require_father: bool = False) -> tuple[bool, bool | None]:
    """(match, father agreement) — see the module docstring for the rule."""
    if not (tk.given & p.given):
        return False, None
    if not tk.roots or not p.roots:
        return False, None
    if not any(_one_family(a, b, aliases) for a in tk.roots for b in p.roots):
        return False, None
    if tk.fathers and p.fathers:
        if not tk.fathers & p.fathers:
            return False, None
        return True, True
    if require_father:
        return False, None
    return True, None


def _named_alike(a: NameKeys, b: NameKeys) -> bool:
    """One given name by its base, and one father where both give one — the
    surname left out. Evidence only beside a neighbour on the list: alone it is
    the given-name-and-patronymic prior the channel refuses."""
    if not (a.given & b.given):
        return False
    return not (a.fathers and b.fathers) or bool(a.fathers & b.fathers)


def _label(c: Citation) -> str:
    page = str(t("facts.leaf", page=c.page)) if c.page else ""
    return f"{c.source_file} №{c.record_num}{page}"


def entry_days(facts: AssertionSet) -> EntryDays:
    """Each entry as the days it can have been written on — from the earliest
    to the latest day any dated claim of it can mean, a told year at its slack."""
    out: EntryDays = {}
    for record in facts.records():
        firsts: list[Day] = []
        lasts: list[Day] = []
        for a in record.of(Dated):
            read = as_read(a.date)
            if read.earliest is not None:
                firsts.append(read.earliest)
            if read.latest is not None:
                lasts.append(read.latest)
        if firsts and lasts and record.assertions:
            out[record.assertions[0].cite.record_id] = (min(firsts), max(lasts))
    return out


def _guard(target: Side, person: Side, lives: tuple[Lives, Lives],
           entries: EntryDays) -> tuple[str | None, str, bool]:
    """(retired code or None, reason, whether a birth was checked)."""
    if target.lists & person.lists:
        return (RETIRED_SAME_LIST,
                str(t("facts.reconcile.same_list")), False)
    if target.households & person.households:
        return (RETIRED_SAME_HOUSEHOLD,
                str(t("facts.reconcile.same_household")), False)
    checked = False
    for tb in target.births:
        for p in person.births:
            # Checked means both sides place a birth; a gap of None from an
            # age the parser declines is no check at all.
            checked = checked or (birth_span(tb) is not None
                                  and birth_span(p) is not None)
            gap = birth_gap(tb, p)
            if gap is not None and not gap.weak:
                return (RETIRED_BIRTH_APART,
                        str(t("facts.reconcile.birth_apart", years=gap.years, allowed=gap.allowed)), True)
    target_life, person_life = lives
    both = two_baptisms(target_life, person_life)
    if both is not None:
        return (RETIRED_TWO_BAPTISMS,
                str(t("facts.reconcile.two_baptisms", first=both[0], second=both[1])), checked)
    for named, born, who in ((target, person, str(t("facts.reconcile.target"))),
                             (person, target, str(t("facts.reconcile.canonical")))):
        birth = born.born_by()
        if birth is None:
            continue
        for record_id, cite in named.entries.items():
            span = entries.get(record_id)
            if span is not None and span[1] < birth[0]:
                return (RETIRED_SEEN_BEFORE_BIRTH,
                        str(t("facts.reconcile.seen_before_birth", who=who, cite=_label(cite), birth=birth[1])),
                        checked)
    for dead, alive, who in ((target_life, person_life, str(t("facts.reconcile.target"))),
                             (person_life, target_life, str(t("facts.reconcile.canonical")))):
        apart = outlived(dead, alive)
        if apart is not None:
            return (RETIRED_LIFE_APART,
                    str(t("facts.reconcile.life_apart", who=who, first=apart[0], second=apart[1])),
                    checked)
    return None, "", checked


def _life(side: Side, entries: EntryDays) -> Lives:
    """A side's life, with every entry that places it alive counted as a sign
    of life."""
    life = side.lives()
    present = side.present(entries)
    if not present:
        return life
    return Lives(baptisms=life.baptisms, died_by=life.died_by,
                 alive_at=life.alive_at | present)


def _reconcile(target: Side, pool: Sequence[Side], aliases: Aliases,
               entries: EntryDays, life_of: Callable[[Side], Lives],
               require_father: bool = False) -> Reconciliation:
    matches: list[Match] = []
    target_life = _life(target, entries)
    for person in pool:
        agree, father = _names_match(target.names, person.names, aliases,
                                     require_father)
        if not agree:
            continue
        retired, reason, checked = _guard(target, person,
                                          (target_life, life_of(person)), entries)
        matches.append(Match(person=person, retired=retired, reason=reason,
                             father=father, birth_checked=checked))
    return _verdict(target, matches)


def _verdict(target: Side, matches: Iterable[Match]) -> Reconciliation:
    """The verdict on a target's matches — see the module docstring."""
    # Survivors first, and among them the most telling: backed by the list's
    # neighbours, a birth checked, then the person held by the most records.
    ranked = sorted(matches, key=lambda m: (m.retired is not None, not m.backed,
                                            not m.birth_checked, -m.person.records,
                                            m.person.key))
    survivors = [m for m in ranked if m.retired is None]
    if len(survivors) == 1:
        only = survivors[0]
        high = (bool(target.births) and only.birth_checked) or bool(only.backed)
        # A namesake retired for a christening of his own was born inside the
        # window the birth check allows: the survivor's birth fits him as well,
        # so the survivor may be that child grown up, not the target (two
        # namesakes christened two months apart, and a later groom the age
        # of both).
        if high and not only.backed and any(m.retired == RETIRED_TWO_BAPTISMS
                                            for m in ranked):
            high = False
        return Reconciliation(target, VERDICT_CANDIDATE, "HIGH" if high else "MEDIUM",
                              tuple(ranked))
    backed = [m for m in survivors if m.backed]
    if len(backed) == 1:
        return Reconciliation(target, VERDICT_CANDIDATE, "HIGH", tuple(ranked),
                              by_neighbours=True)
    verdict = VERDICT_AMBIGUOUS if survivors else VERDICT_NONE
    return Reconciliation(target, verdict, "", tuple(ranked))


class _Neighbours:
    """Who stands beside an entry on a list in household order, whom they may
    be — their own canonical once folded into the corpus proper, else every
    survivor of their own matching — and whom those are kin to."""

    def __init__(self, facts: AssertionSet, identity: Identity,
                 ordered_lists: frozenset[str], pool: Iterable[Side],
                 first_pass: Iterable[Reconciliation], aliases: Aliases,
                 entries: EntryDays, life_of: Callable[[Side], Lives]) -> None:
        def same_family(a: frozenset[str], b: frozenset[str]) -> bool:
            return any(_one_family(x, y, aliases) for x in a for y in b)
        self._hood = Neighbourhood(
            list_entries(facts, identity, lambda c: c.source_file in ordered_lists
                         and c.record_kind in TARGET_KINDS),
            same_family)
        self._kin: Kin = kin_of_canonicals(facts, identity)
        found = list(first_pass)
        self._people: dict[IdentityKey, Side] = {s.key: s for s in pool}
        self._pool = frozenset(self._people)
        # A neighbour's names: its own side, whether it is a target or a person
        # of the pool.
        self._named: dict[IdentityKey, NameKeys] = {
            **{k: s.names for k, s in self._people.items()},
            **{r.target.key: r.target.names for r in found}}
        self._survivors = {r.target.key: tuple(m.person.key for m in r.survivors)
                           for r in found}
        self._entries = entries
        self._life_of = life_of

    def _may_be(self, entry: ListEntry) -> tuple[IdentityKey, ...]:
        if entry.key is None:
            return ()
        if entry.key in self._pool:
            return (entry.key,)
        return self._survivors.get(entry.key, ())

    def back(self, result: Reconciliation, target: Side) -> Reconciliation:
        """`result` again, each surviving match with the neighbours of
        `target`'s list entries who vouch for it — or, where no name matched,
        the match a neighbour's kin gives (`_through`)."""
        pairs = [(own, n) for rid in target.entries
                 if (own := self._hood.entry(rid)) is not None
                 for n in self._hood.beside(own, target.key)]
        if not pairs:
            return result
        if not result.matches:
            return self._through(target, pairs)
        if not result.survivors:
            return result
        matches: list[Match] = []
        for m in result.matches:
            backed = self._backing(m.person.key, pairs) if m.retired is None else ()
            matches.append(Match(m.person, m.retired, m.reason, m.father,
                                 m.birth_checked, backed))
        return _verdict(target, matches)

    def _backing(self, person: IdentityKey,
                 pairs: Sequence[tuple[ListEntry, ListEntry]]) -> tuple[Backing, ...]:
        """The neighbours who vouch for `person`: by the canonical their own
        matching gave them, or by name — a kin of `person` named like the
        neighbour, the surname left out, since a bride is written in her
        wedding record without the name she bears on the list."""
        kin = self._kin.get(person, {})
        found: dict[tuple[object, ...], Backing] = {}
        for own, n in pairs:
            for d in self._may_be(n):
                if d in kin and fits_ages(own.age, n.age, kin[d]):
                    found.setdefault((n.record_id, d), Backing(n, d, kin[d]))
            named = self._named.get(n.key) if n.key is not None else None
            if named is None:
                continue
            for d, relation in kin.items():
                other = self._people.get(d)
                if (other is not None and (n.record_id, d) not in found
                        and _named_alike(named, other.names)
                        and fits_ages(own.age, n.age, relation)):
                    found[(n.record_id, d)] = Backing(n, d, relation, by_name=True)
        return tuple(found.values())

    def _through(self, target: Side,
                 pairs: Sequence[tuple[ListEntry, ListEntry]]) -> Reconciliation:
        """No name of the corpus matched the entry. Its neighbour's canonical
        may still have kin named like it — given name and father, the surname
        left out: the wife of the man beside her, whose wedding record gives
        her maiden name or none. Each such kin is matched as any match is, the
        guards included, and the neighbour is its backing."""
        target_life = _life(target, self._entries)
        seen: dict[IdentityKey, list[Backing]] = {}
        for own, n in pairs:
            for c in self._may_be(n):
                for k, relation in self._kin.get(c, {}).items():
                    person = self._people.get(k)
                    back = INVERSE[relation]
                    if (person is None or k == target.key
                            or not _named_alike(target.names, person.names)
                            or not fits_ages(own.age, n.age, back)):
                        continue
                    seen.setdefault(k, []).append(Backing(n, c, back))
        if not seen:
            return Reconciliation(target, VERDICT_NONE, "", ())
        matches: list[Match] = []
        for k, backed in seen.items():
            person = self._people[k]
            retired, reason, checked = _guard(
                target, person, (target_life, self._life_of(person)), self._entries)
            father = True if target.names.fathers and person.names.fathers else None
            matches.append(Match(person, retired, reason, father, checked,
                                 tuple(backed) if retired is None else ()))
        result = _verdict(target, matches)
        return replace(result, through_neighbour=True) if result.survivors else result


def _contest(found: list[Reconciliation]) -> list[Reconciliation]:
    """Two entries of one list are two people (`SAME_LIST`), so a person the
    channel proposes for two of them is proposed for neither: each becomes
    AMBIGUOUS, naming the other entry. Two women of one name can stand in one
    household — a grandmother and her grandson's wife — and the names alone
    cannot tell them apart."""
    claims: dict[tuple[str, IdentityKey], list[Reconciliation]] = {}
    for r in found:
        if r.is_candidate:
            for source in sorted(r.target.lists):
                claims.setdefault((source, r.proposed[0].person.key), []).append(r)
    rivals: dict[IdentityKey, list[str]] = {}
    for group in claims.values():
        if len(group) > 1:
            for r in group:
                rivals.setdefault(r.target.key, []).extend(
                    _entry_label(o.target) for o in group if o is not r)
    if not rivals:
        return found
    return [Reconciliation(r.target, VERDICT_AMBIGUOUS, "", r.matches,
                           contested=tuple(sorted(set(rivals[r.target.key]))))
            if r.target.key in rivals else r for r in found]


def _entry_label(side: Side) -> str:
    return ", ".join(sorted(f"№{c.record_num}" for c in side.entries.values()
                            if c.record_kind == "list"))


def _index(pool: Iterable[Side]) -> dict[str, list[Side]]:
    by_given: dict[str, list[Side]] = {}
    for side in pool:
        for given in side.names.given:
            by_given.setdefault(given, []).append(side)
    return by_given


def _candidates(target: Side, index: dict[str, list[Side]]) -> list[Side]:
    seen: dict[IdentityKey, Side] = {}
    for given in sorted(target.names.given):
        for side in index.get(given, ()):
            seen.setdefault(side.key, side)
    return [seen[k] for k in sorted(seen)]


def stated_fathers(facts: AssertionSet) -> dict[Persona, frozenset[str]]:
    """Each appearance's father as the record names him — the given name of a
    man the record makes its parent, as a comparison key."""
    out: dict[Persona, set[str]] = {}
    for record in facts.records():
        for edge in record.of(ParentOf):
            for c in record.about(edge.subject):
                if isinstance(c, NameClaim) and c.given and c.gender == Gender.MALE \
                        and "?" not in c.given:
                    out.setdefault(edge.other, set()).add(
                        _fold(matching_base(c.given, Gender.MALE)))
                    break
    return {who: frozenset(names) for who, names in out.items()}


def _distance_at_most_two(a: str, b: str) -> bool:
    """Edit distance between two roots is at most two."""
    if abs(len(a) - len(b)) > 2:
        return False
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        if min(current) > 2:
            return False
        previous = current
    return previous[-1] <= 2


def _alias_pairs(side: Side) -> frozenset[tuple[str, str]]:
    """The spellings one man's records join: two roots at most two letters
    apart (one letter apart is a variant already, and needs no lesson)."""
    if not side.male or side.records < 2:
        return frozenset()
    roots = sorted(side.names.roots)
    return frozenset((a, b) for i, a in enumerate(roots) for b in roots[i + 1:]
                     if not within_one_letter(a, b) and _distance_at_most_two(a, b))


class AliasBook:
    """The spellings the corpus has learned, and who taught each — so the
    oracle can leave one person's lesson out without relearning the corpus."""

    def __init__(self, sides: Iterable[Side]) -> None:
        self._taught: dict[IdentityKey, frozenset[tuple[str, str]]] = {}
        for side in sides:
            if pairs := _alias_pairs(side):
                self._taught[side.key] = pairs
        self._count: dict[tuple[str, str], int] = {}
        for pairs in self._taught.values():
            for pair in pairs:
                self._count[pair] = self._count.get(pair, 0) + 1
        self._all = self._build(frozenset())

    def _build(self, own: frozenset[tuple[str, str]]) -> Aliases:
        out: dict[str, set[str]] = {}
        for (a, b), n in self._count.items():
            if n - ((a, b) in own) > 0:
                out.setdefault(a, set()).add(b)
                out.setdefault(b, set()).add(a)
        return {root: frozenset(others) for root, others in out.items()}

    def aliases(self, excluding: IdentityKey | None = None) -> Aliases:
        """Every lesson, or every lesson but one person's own."""
        own = self._taught.get(excluding) if excluding is not None else None
        return self._build(own) if own else self._all


def learned_aliases(sides: Iterable[Side],
                    excluding: IdentityKey | None = None) -> Aliases:
    """Spellings of one family the corpus has already joined: two roots at most
    two letters apart that the records of one MAN both carry. `excluding`
    leaves one person's records out — the audit's own fold must not teach it."""
    return AliasBook(sides).aliases(excluding)


def _sides(facts: AssertionSet, identity: Identity) -> list[Side]:
    fathers = stated_fathers(facts)
    return [Side.of(key, c.claims, fathers)
            for key, c in sorted(conclusions(facts, identity).items())]


def lists_and_cards(side: Side) -> bool:
    """A person made only of list entries and catalog cards."""
    return bool(side.kinds) and side.kinds <= TARGET_KINDS


def corpus_proper(side: Side) -> bool:
    """A person holding at least one record of the corpus proper."""
    return bool(side.kinds - TARGET_KINDS)


@dataclass(frozen=True)
class Channel:
    """Who is looked for, among whom, which folded appearance the oracle may
    take back out, whether the father must be written on both sides, and
    whether a list's neighbours may back a match."""
    is_target: Callable[[Side], bool]
    in_pool: Callable[[Side], bool]
    auditable: Callable[[Side], bool]
    require_father: bool = False
    by_neighbours: bool = False


#: `verso reconcile`: the deliberate duplicates against the corpus proper.
LISTS_AND_CARDS = Channel(is_target=lists_and_cards, in_pool=corpus_proper,
                          auditable=lists_and_cards, by_neighbours=True)


def _life_of(entries: EntryDays) -> Callable[[Side], Lives]:
    cache: dict[IdentityKey, Lives] = {}

    def life_of(side: Side) -> Lives:
        if side.key not in cache:
            cache[side.key] = _life(side, entries)
        return cache[side.key]
    return life_of


def _first_pass(facts: AssertionSet, channel: Channel,
                sides: list[Side]) -> tuple[list[Reconciliation], list[Side], Aliases]:
    entries = entry_days(facts)
    targets = [s for s in sides if channel.is_target(s)]
    pool = [s for s in sides if channel.in_pool(s)]
    index = _index(pool)
    aliases = AliasBook(pool).aliases()
    life_of = _life_of(entries)
    found = [_reconcile(target, _candidates(target, index), aliases, entries, life_of,
                        channel.require_father)
             for target in targets]
    return found, pool, aliases


def match(facts: AssertionSet, identity: Identity, channel: Channel,
          ordered_lists: frozenset[str] = frozenset()) -> list[Reconciliation]:
    """Every target of the channel, matched against its pool; candidates first.
    `ordered_lists` names the list files that run household by household."""
    sides = _sides(facts, identity)
    found, pool, aliases = _first_pass(facts, channel, sides)
    if channel.by_neighbours and ordered_lists:
        entries = entry_days(facts)
        hood = _Neighbours(facts, identity, ordered_lists, pool, found, aliases,
                           entries, _life_of(entries))
        found = [hood.back(r, r.target) for r in found]
    found = _contest(found)
    order = {VERDICT_CANDIDATE: 0, VERDICT_AMBIGUOUS: 1, VERDICT_NONE: 2}
    found.sort(key=lambda r: (order[r.verdict], r.confidence != "HIGH", r.target.key))
    return found


def reconcile(facts: AssertionSet, identity: Identity,
              ordered_lists: frozenset[str] = frozenset()) -> list[Reconciliation]:
    """Every list entry and card standing alone, reconciled against the corpus
    proper; candidates first."""
    return match(facts, identity, LISTS_AND_CARDS, ordered_lists)


@dataclass(frozen=True)
class Audit:
    """One list entry or card already folded by hand, read as if it were not:
    `outcome` is FOUND (the channel proposes exactly its canonical), AMONG
    (its canonical is one of several), OTHER (the channel proposes someone
    else) or MISSED (its canonical is not proposed — `reason` says why)."""
    target: Side
    canonical: IdentityKey
    outcome: str
    reason: str
    result: Reconciliation


def audit_folded(facts: AssertionSet, identity: Identity,
                 channel: Channel = LISTS_AND_CARDS,
                 ordered_lists: frozenset[str] = frozenset()) -> list[Audit]:
    """The hand-made folds as the channel's oracle.

    Each appearance the channel could have proposed (`channel.auditable`)
    inside a person of its pool is taken OUT of that person and matched against
    the pool — the person included, without it — as if the fold had never been
    made, and nothing the fold itself taught (its surname spellings) is used.
    A channel that cannot find the folds a human made is not one.

    The list's neighbours back it as they would in a live run: a neighbour
    already folded by hand is its canonical — the state a reader of the report
    is in, having folded the husband and asking about the wife."""
    fathers = stated_fathers(facts)
    sides = _sides(facts, identity)
    entries = entry_days(facts)
    homes = [s for s in sides if channel.in_pool(s)]
    index = _index(homes)
    book = AliasBook(homes)
    cached = _life_of(entries)
    hood: _Neighbours | None = None
    if channel.by_neighbours and ordered_lists:
        first, _, aliases = _first_pass(facts, channel, sides)
        hood = _Neighbours(facts, identity, ordered_lists, homes, first, aliases,
                           entries, cached)
    audits: list[Audit] = []
    for home in homes:
        personas: dict[Persona, list[Assertion]] = {}
        for c in home.claims:
            personas.setdefault(c.subject, []).append(c)
        if len(personas) < 2:
            continue
        aliases = book.aliases(excluding=home.key)
        for persona, claims in personas.items():
            target = Side.of(("audit",) + (canonical_name(home.key) or "",)
                             + (str(persona),), claims, fathers)
            if not channel.auditable(target):
                continue
            rest = Side.of(home.key, (c for c in home.claims if c.subject != persona),
                           fathers)
            pool = [rest if s.key == home.key else s for s in _candidates(target, index)]

            def life_of(side: Side, rest: Side = rest) -> Lives:
                return _life(side, entries) if side is rest else cached(side)
            result = _reconcile(target, pool, aliases, entries, life_of,
                                channel.require_father)
            if hood is not None:
                result = hood.back(result, target)
            audits.append(_judge(target, home.key, result))
    return audits


def _judge(target: Side, home: IdentityKey, result: Reconciliation) -> Audit:
    keys = [m.person.key for m in result.proposed]
    if keys == [home]:
        return Audit(target, home, "FOUND", "", result)
    if home in keys:
        first = (str(t("facts.reconcile.audit.first")) if keys[0] == home
                 else str(t("facts.reconcile.audit.at", place=keys.index(home) + 1)))
        return Audit(target, home, "AMONG", str(t("facts.reconcile.audit.among", count=len(keys), first=first)),
                     result)
    mine = next((m for m in result.matches if m.person.key == home), None)
    if keys:
        why = mine.reason if mine is not None and mine.retired else str(t("facts.reconcile.audit.no_name"))
        return Audit(target, home, "OTHER", why, result)
    why = (f"{mine.retired}: {mine.reason}" if mine is not None
           else str(t("facts.reconcile.audit.no_name_father_surname")))
    return Audit(target, home, "MISSED", why, result)
