"""What a source ASSERTS, about whom, and on whose authority.

The vocabulary is GENTECH's (NGS Genealogical Data Model, 1998–2000) and
GEDCOM X's, because this problem has been solved in the domain twice and the
names are worth more than ours would be:

* a **Persona** is what one record says about one person — GEDCOM X: "an
  instance of a Person that has been identified as an extracted conclusion";
* an **Assertion** links a subject to a value or another persona;
* a **Surety** is how far we stand behind a derived one;
* and, the part both models insist on, *an assertion rests on a source **or on
  lower-level assertions*** — which is what `Derived.because` carries.

Folding personas into one person is a separate step (`identity.py`), which is
GEDCOM X's evidence→conclusion boundary and the whole point of the layer.

Stdlib only, save `verso.ru.gender`: nothing here may import the DSL, the
translator or the CLI.
"""
from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import TypeVar

from verso.ru.gender import Gender
from verso.ru.messages import t

# --------------------------------------------------------------------------- #
# Who, and from where
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True, order=True)
class Persona:
    """One APPEARANCE of a person in one document entry, by its id.

    The id is the persona's in the records JSON (rule `r1`, `verso.core.records.ids`):
    the entry as it is cited, then where in it the person stands —
    `r1:Заманиловка/48-1-930/1853/birth/f23/godparent2`. So `facts.jsonl`, the
    records export and a Verso link name one appearance alike, and the id moves
    only when the entry's citation does: never when a record is inserted or
    held elsewhere. An entry read without its village's ids (a test, a one-off
    reading) is numbered by its place in that reading instead, which is unique
    there and nowhere else.

    The id is opaque, and there is no slot field: a rule that could read
    `persona.slot == "god_parent1"` would reconstruct the per-record-kind
    ladder this layer exists to remove — and a rule names no role in any
    language (tests/test_facts_layering.py).
    """
    id: str

    def __str__(self) -> str:
        return self.id


class Bound(StrEnum):
    """The shape of a dated claim that is not a point.

    Mirrors `GeniDate.date_range` and `FamilioDate.date_range` so a date can
    round-trip through either without loss.
    """
    BEFORE = "before"
    AFTER = "after"
    BETWEEN = "between"


def _month_end(year: int, month: int) -> int:
    """The last day of that month in the JULIAN calendar the books were kept in.

    `monthrange` follows the proleptic Gregorian rule, which differs from the
    Julian one only for a February in a century year — 1700, 1800 and 1900 are
    Julian leap years and Gregorian common ones. This used to accept that one
    day on the bet that the corpus held no month-only February of those years.
    It does: a `death_month` block hands its month to a burial the book never
    dated, so every Горюхино 1800 burial reads «??.02», and once смерть № 3 was
    re-read as 29 February, a burial ending on the 28th came out BEFORE the
    death. The Julian rule needs no calendar module — it is the line below.
    """
    if not 1 <= month <= 12:
        return 31
    if month == 2 and year % 4 == 0:
        return 29
    return monthrange(year, month)[1]


@dataclass(frozen=True, slots=True)
class FactDate:
    """A date as the source gives it: a point, an approximation, or an interval.

    Rules may ask this three things and nothing else — `earliest`, `latest`,
    `overlaps`. That is deliberate: every date comparison in the consolidation
    checks is charitable-interval arithmetic, and letting a rule read `.year`
    off a `BETWEEN 1848 and 1883` is how a bound gets mistaken for a birthday.

    `BEFORE` has no earliest and `AFTER` has no latest — an open end is a real
    answer, not a missing one. The day conventions match `GeniDate`: a
    year-only start is 1 January and a year-only end is 31 December, a
    month-only end is the 28th (correct for every month).

    `GeniDate.synthetic` is deliberately NOT mirrored. It exists because a
    GeniDate cannot otherwise say whether a bound was read or computed — which
    is `Basis`, under another name and in the wrong place.
    """
    year: int | None = None
    month: int | None = None
    day: int | None = None
    circa: bool = False
    bound: Bound | None = None
    end_year: int | None = None
    end_month: int | None = None
    end_day: int | None = None
    end_circa: bool = False

    def __bool__(self) -> bool:
        return self.year is not None or self.month is not None or self.day is not None

    @property
    def earliest(self) -> tuple[int, int, int] | None:
        """The first day this date can mean, or None when unbounded below."""
        if self.bound is Bound.BEFORE or self.year is None:
            return None
        return (self.year, self.month or 1, self.day or 1)

    @property
    def latest(self) -> tuple[int, int, int] | None:
        """The last day this date can mean, or None when unbounded above.

        A month with no day ends on that month's LAST day, which needs the
        calendar: it was the 28th here until 2026-09-22, on the reasoning that
        the 28th exists in every month. That is true and it is not the
        question — the 28th is the last day GUARANTEED to exist, not the latest
        day an April date can mean, and reading it as the latest makes a burial
        dated only to «апрель 1794» fall entirely before a death on the 29th.
        It produced 127 such findings on Горюхино and 55 on Заманиловка the
        first time an ordering rule ran on assertions, all of them that one
        shape and none of them real. The check being reproduced never had the
        bug: `date_order._latest` reads a dayless month as the 31st, which
        overshoots and therefore never orders anything falsely.

        **The `end_*` branch keeps the 28th, and the asymmetry is deliberate.**
        There it is pinned to `GeniDate.to_end_datetime`, which chose 28 on
        purpose as a conservative end for range-width arithmetic, and
        `tests/test_facts_projection.py` holds the two to each other date for
        date — an interval that silently disagrees with the one the oracle
        computes is the risk the whole bridge is pinned against. A plain
        month-only date has no counterpart there to agree with: `GeniDate`
        offers no upper bound for one at all.
        """
        if self.bound is Bound.AFTER:
            return None
        if self.end_year is not None:
            if self.end_month is None:
                return (self.end_year, 12, 31)
            if self.end_day is None:
                return (self.end_year, self.end_month, 28)
            return (self.end_year, self.end_month, self.end_day)
        if self.year is None:
            return None
        if self.month is None:
            return (self.year, 12, 31)
        if self.day is None:
            return (self.year, self.month, _month_end(self.year, self.month))
        return (self.year, self.month, self.day)

    @property
    def midpoint(self) -> tuple[int, int, int] | None:
        """The day to compare AT when only part of the date is known.

        Unknown components are filled with mid-period values — a record dated
        only to the year is still worth comparing, because it pins an age to
        within a year, which is far tighter than the errors a stated-age check
        hunts. A stated day is capped at 28 so no month can overflow.

        A fourth accessor rather than a rule reaching for `.year`: the choice
        between an edge and a midpoint is a real one, and it should be made by
        name.
        """
        if self.year is None:
            return None
        return (self.year, self.month or 7, min(self.day or 15, 28))

    def overlaps(self, other: FactDate) -> bool:
        """Whether the two dates can name the same day."""
        a_lo, a_hi = self.earliest, self.latest
        b_lo, b_hi = other.earliest, other.latest
        if a_hi is not None and b_lo is not None and a_hi < b_lo:
            return False
        if b_hi is not None and a_lo is not None and b_hi < a_lo:
            return False
        return True

    def definitely_before(self, other: FactDate) -> bool:
        """Whether every day this date can mean precedes every day `other` can."""
        a_hi, b_lo = self.latest, other.earliest
        return a_hi is not None and b_lo is not None and a_hi < b_lo

    def __str__(self) -> str:
        if not self:
            return "?"
        d = f"{self.day:02d}" if self.day else "??"
        m = f"{self.month:02d}" if self.month else "??"
        body = f"{d}.{m}.{self.year or '????'}"
        if self.circa:
            body = f"ок. {body}"
        if self.bound is Bound.BEFORE:
            return f"до {body}"
        if self.bound is Bound.AFTER:
            return f"после {body}"
        if self.bound is Bound.BETWEEN and self.end_year:
            return f"{body}–{self.end_year}"
        return body

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        return (self.year or 0, self.month or 0, self.day or 0,
                self.bound.value if self.bound else "")


#: The `record_num` of an entry its book left unnumbered (`verso.ru.facts.extract.common`).
UNNUMBERED = "none"


@dataclass(frozen=True, slots=True)
class Citation:
    """Where an assertion was read. The only carrier of record-kind vocabulary.

    `record_kind`, `locator` and `stated_role` are for HUMANS and for rebuilding
    a res_name. A rule may read none of them; a RENDERER may read all three —
    that asymmetry is what `tests/test_facts_layering.py` enforces.
    """
    village: str
    source_file: str
    record_kind: str
    record_num: str
    #: Position of the entry within its source file. Provenance, not kind: a
    #: record number is NOT unique — a book may carry two entries numbered
    #: alike (one entry written for two infants), and keying on the number
    #: alone fused them into one.
    entry: int
    year: int | None = None
    page: str | None = None
    locator: str = ""
    #: The document's own wording for a role, when it differs from the typed
    #: one («роль в оригинале: дядя родной»). A claim about the text, so it
    #: belongs in provenance rather than in a predicate.
    stated_role: str | None = None

    @property
    def record_id(self) -> tuple[str, str, int, str, int]:
        """The provenance unit: one entry of one document. Carries no KIND."""
        return (self.village, self.source_file, self.year or 0,
                self.record_num, self.entry)

    @property
    def sort_key(self) -> tuple[str, str, int, int, str, str]:
        return (self.village, self.source_file, self.year or 0, self.entry,
                self.record_num, self.locator)

    def number(self, *, sign: bool = True) -> str:
        """How a report names the record by its number: «№7» («7» without the `sign`, where the line says «рек.»
        before it), or «без номера» for an entry its book left unnumbered (`record_num` "none")."""
        if self.record_num == UNNUMBERED:
            return str(t("cli.facts.unnumbered"))
        return ("№" if sign else "") + self.record_num

    def __str__(self) -> str:
        page = f", л. {self.page}" if self.page else ""
        return (f"{self.year} {self.record_kind} рек. {self.number(sign=False)}"
                f"{page}, слот {self.locator}")


# --------------------------------------------------------------------------- #
# On whose authority
# --------------------------------------------------------------------------- #


class Surety(IntEnum):
    """How far we stand behind a derived assertion. Ordinal, never a float:
    a probability would invite arithmetic the evidence does not support."""
    ASSUMED = 1   # a convention usually but not always true
    INFERRED = 2  # mechanical, no judgement


@dataclass(frozen=True, slots=True)
class Stated:
    """The source says so.

    `basis_unknown` is the honest third answer: the DSL derived this value in
    place and left no breadcrumb, so we cannot tell stated from derived.
    """
    basis_unknown: bool = False


@dataclass(frozen=True)
class Derived:
    """We concluded it — from these assertions, by this rule."""
    rationale: str
    surety: Surety
    because: tuple[Assertion, ...] = ()


@dataclass(frozen=True)
class Retracted:
    """The author has re-read the source and declares the claim unusable —
    without denying that the source makes it.

    This is what `source_date_error`, `source_age_error` and `source_kin_error`
    are, and why a flag on a FINDING cannot express them: `sibling_spacing`
    does not suppress a finding, it withdraws a DERIVED BIRTH YEAR. Wrapping
    the basis it replaces means everything standing on that assertion inherits
    the retraction, and `why()` can still print what the source said.

    A rule never tests for one: `AssertionSet.believed()` filters them out
    before a rule sees them.
    """
    reason: str
    retracts: Basis


Basis = Stated | Derived | Retracted


# --------------------------------------------------------------------------- #
# The predicates
# --------------------------------------------------------------------------- #
#
# The bar for admitting one: it must name a relation a contemporary would
# recognise WITHOUT mentioning a document — «восприемник», «супруг», «отец».
# «Участник слота 2 крещения» does not qualify.


@dataclass(frozen=True, kw_only=True)
class Assertion:
    subject: Persona
    cite: Citation
    basis: Basis

    @property
    def payload(self) -> object:
        return None

    @property
    def sort_key(self) -> tuple[object, ...]:
        """In the order of the reading — kind of claim, then where it was read — and
        the persona only to break a tie: an id's spelling is no order."""
        return (type(self).__name__, self.cite.sort_key, self.subject.id,
                str(self.payload))


@dataclass(frozen=True, kw_only=True)
class Relational(Assertion):
    """An assertion connecting two personas.

    One shared field name — `other` — is what lets a rule join ANY two
    relational predicates without naming either of them.
    """
    other: Persona

    @property
    def payload(self) -> object:
        return self.other


@dataclass(frozen=True, kw_only=True)
class NameClaim(Assertion):
    given: str | None
    patronymic: str | None
    surname: str | None
    gender: Gender | None
    #: Geni's `maiden_name`. Kept apart from `surname` because the DSL routes a
    #: girl's INHERITED surname here rather than to `last_name` — so a rule
    #: comparing identity must consider both, while a report showing what the
    #: book wrote must not.
    birth_surname: str | None = None
    #: The author's note that a newborn's name is RIGHT although no saint of
    #: it is kept near the birth or the christening (`birth(calendar_note=)`).
    #: Not a retraction — the name stays believed; only the check asking that
    #: question reads it (`verso.ru.facts.checks.name_days`), as only
    #: `verso death-age` reads `AgedYears.namesake`. Outside the payload, so no
    #: report or dump changes by carrying it.
    calendar_note: str | None = None

    @property
    def payload(self) -> object:
        return (self.given, self.patronymic, self.surname, self.birth_surname,
                self.gender)


@dataclass(frozen=True, kw_only=True)
class Dated(Assertion):
    date: FactDate

    @property
    def payload(self) -> object:
        return str(self.date)


@dataclass(frozen=True, kw_only=True)
class BornOn(Dated):
    pass


@dataclass(frozen=True, kw_only=True)
class BaptizedOn(Dated):
    #: The author's note that this date is RIGHTLY so long after the one it
    #: follows — the birth, the death (`birth(lag_note=)`, `death(lag_note=)`).
    #: Not a retraction: the date stays believed; only
    #: `verso.ru.facts.checks.lags` reads it. Outside the payload, like
    #: `MarriedOn.calendar_note`.
    lag_note: str | None = None


@dataclass(frozen=True, kw_only=True)
class MarriedOn(Dated):
    #: The author's note that the day is RIGHT although the Church did not
    #: marry on it (`marriage(calendar_note=)`). Not a retraction — the date
    #: stays believed; only `verso.ru.facts.checks.wedding_calendar` reads it.
    #: Outside the payload, like `NameClaim.calendar_note`.
    calendar_note: str | None = None


@dataclass(frozen=True, kw_only=True)
class DivorcedOn(Dated):
    """«разведён(а)» — the day the record dates the end of a marriage by: the
    court's decree where the act names one, the day of the act otherwise.

    Stated of each of the two, as `MarriedOn` is; the couple is the `SpouseOf`
    of the same entry, which has no term of its own — an act of divorce says
    these two WERE spouses, and this is the day they ceased to be. A rule that
    needs how long a marriage lasted takes the pair's `MarriedOn` and this.
    """


@dataclass(frozen=True, kw_only=True)
class DiedOn(Dated):
    pass


@dataclass(frozen=True, kw_only=True)
class BuriedOn(Dated):
    """«погребенъ». A burial is not a death and neither is a birth — the DSL
    spells all three with fields named `b_day`/`b_month` depending on the
    record kind, which is how 3198 burials came to be filed as birth dates."""
    #: The author's note that this date is RIGHTLY so long after the one it
    #: follows — the birth, the death (`birth(lag_note=)`, `death(lag_note=)`).
    #: Not a retraction: the date stays believed; only
    #: `verso.ru.facts.checks.lags` reads it. Outside the payload, like
    #: `MarriedOn.calendar_note`.
    lag_note: str | None = None


@dataclass(frozen=True, kw_only=True)
class Quantified(Assertion):
    """A magnitude the source states about someone, as of a date.

    A base so a rule can ask for «a stated quantity» without naming the one
    predicate it has in mind — the same reason `Dated` and `Relational` exist.
    """
    age: float | int | str | None
    as_of: FactDate

    @property
    def payload(self) -> object:
        return self.age


@dataclass(frozen=True, kw_only=True)
class AgedYears(Quantified):
    """«сколько лет по записи» — a показание, kept VERBATIM.

    The scribe's own string survives («полгода», «недѣль 6», «году»), because
    an age is evidence and the interval it implies is arithmetic. Turning one
    into a date produces a `Derived` assertion with this one among its
    premises — never a value quietly stored here.
    """
    #: The author's note that the age is RIGHT and belongs to a namesake — a
    #: second child given the name of one who died, whose christening the
    #: corpus does not hold (`death(namesake=)`). Not a retraction: the age
    #: stays believed and still dates the birth. It answers one question only
    #: — which christening this age may be measured from — so only the check
    #: asking it reads the note (`verso.ru.facts.checks.stated_age.stated_age_findings`).
    namesake: str | None = None
    #: The author's note that the ages at a wedding are RIGHT although one is
    #: under the age of marriage or the two are far apart
    #: (`marriage(age_note=)`). Not a retraction: the age stays believed and
    #: still dates the birth; only `verso.ru.facts.checks.wedding_ages` reads it.
    age_note: str | None = None


@dataclass(frozen=True, kw_only=True)
class ResidedIn(Assertion):
    place: str

    @property
    def payload(self) -> object:
        return self.place


@dataclass(frozen=True, kw_only=True)
class Titled(Assertion):
    """«Титул/звание» — how the record styles someone, kept VERBATIM.

    «крестьянинъ помѣщика Ивана Васильевича Пеночкина», «ясачная крестьянка»,
    «солдатка»: the wording is the evidence. Which сословие, which owner, and
    whether two wordings name one owner under a maiden and a married surname are
    CLASSIFICATION, and belong to whoever asks — the same division `AgedYears`
    keeps between a scribe's age and the interval it implies.
    """
    status: str

    @property
    def payload(self) -> object:
        return self.status


@dataclass(frozen=True, kw_only=True)
class Grouped(Assertion):
    """Counted as one of a named group the source enumerates as a unit.

    A base for the same reason `Dated` and `Relational` are ones: a rule asks
    for «a group the source counted these people into» and never learns which
    kind of group it got. What the rule may do with it is narrow and strong —
    a source that enumerates two people SEPARATELY has said they are two
    people, which is evidence no amount of name similarity outweighs.
    """
    group: str
    as_of: FactDate
    #: The roll this group belongs to. Deliberately part of the PAYLOAD and
    #: not left to the citation: a group's identity includes which document it
    #: is in, two rolls of one year each number a group 4, and a rule keyed on
    #: the payload must separate them while still being forbidden to read
    #: provenance. The corpus pins archive, fund, inventory, case AND the part
    #: of a case at the level of one source file, so that is the unit — the
    #: case alone is not enough, since its two landlords' sections each start
    #: their numbering at 1.
    within: str = ""

    @property
    def payload(self) -> object:
        return (self.within, self.group, str(self.as_of))


@dataclass(frozen=True, kw_only=True)
class EnumeratedIn(Grouped):
    """«числился во дворѣ N» — one of the people a household is counted as."""


@dataclass(frozen=True, kw_only=True)
class Relocated(Assertion):
    """A move the source records, named by the place at the far end of it.

    `reason` is the source's own word («рекрутъ», «выдана замужъ»), kept for a
    reader on the same terms as `KinOf.term`: a rule may see that somebody
    moved and may not branch on why.
    """
    place: str
    when: FactDate
    reason: str = ""

    @property
    def payload(self) -> object:
        return (self.place, str(self.when))


@dataclass(frozen=True, kw_only=True)
class MovedTo(Relocated):
    """«убылъ въ …» — `place` is where they went."""


@dataclass(frozen=True, kw_only=True)
class ArrivedFrom(Relocated):
    """«прибылъ изъ …» — `place` is where they came from."""


@dataclass(frozen=True, kw_only=True)
class SurvivedUntil(Dated):
    """«былъ живъ въ N» — a lower bound on a life, not an event in it.

    The translator has no such slot, so it dresses the bound as a death with
    `date_range="after"`: 5111 of Горюхино's 6666 «deaths» (77 %) and 963 of
    Нижняя Яичница's 1025 (94 %) are that. While the two share a field, a check
    reading «the death date» is mostly reading bounds. Here they are two
    predicates and a rule has to choose.
    """


@dataclass(frozen=True, kw_only=True)
class ParentOf(Relational):
    """`other` is the child."""


@dataclass(frozen=True, kw_only=True)
class SpouseOf(Relational):
    """`other` is the spouse."""


@dataclass(frozen=True, kw_only=True)
class GodparentOf(Relational):
    """`other` is the person baptized."""


@dataclass(frozen=True, kw_only=True)
class WitnessedAt(Relational):
    """«поручитель» — vouched for this person at their wedding."""


@dataclass(frozen=True, kw_only=True)
class FosterParentOf(Relational):
    """«приёмный отец / приёмная мать» — Geni's `foster` parent modifier;
    `other` is the fostered person.

    Separate from `ParentOf` on purpose: a rule asking for parents must not be
    handed someone the record explicitly says is not one.
    """


@dataclass(frozen=True, kw_only=True)
class KinOf(Relational):
    """Kin the model cannot place: свекор, зять, мачеха, and anything else the
    record names by a word we have no predicate for.

    `term` is the source's word, kept so a reader can see what was said. **A
    rule may not read it** — that is enforced in `tests/test_facts_layering.py`,
    because the moment a rule branches on «свекор» the per-record-kind ladder
    is back. A rule can only observe that these two are related somehow, which
    is exactly as much as we know.
    """
    term: str

    @property
    def payload(self) -> object:
        return f"{self.term} → {self.other}"


@dataclass(frozen=True, kw_only=True)
class OfficiatedAt(Relational):
    """`other` is the person the office was performed for."""


A = TypeVar("A", bound=Assertion)


# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Record:
    """Every assertion read from ONE document entry.

    A provenance unit, not a record kind: `Record` cannot tell you whether it
    came from a birth, a wedding or a revision tale, and nothing may ask.
    """
    assertions: tuple[Assertion, ...]

    def of(self, kind: type[A]) -> tuple[A, ...]:
        return tuple(a for a in self.assertions if isinstance(a, kind))

    def links(self, a: Persona, b: Persona) -> bool:
        """Whether this entry states a relation directly between two personas."""
        pair = {a, b}
        return any(isinstance(x, Relational) and {x.subject, x.other} == pair
                   for x in self.assertions)

    def about(self, persona: Persona) -> tuple[Assertion, ...]:
        return tuple(a for a in self.assertions if a.subject == persona)


class AssertionSet:
    """Assertions in extraction order, groupable by the entry they came from."""

    def __init__(self, assertions: Iterable[Assertion]) -> None:
        self._items: tuple[Assertion, ...] = tuple(assertions)

    def __iter__(self) -> Iterator[Assertion]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def of(self, kind: type[A]) -> tuple[A, ...]:
        return tuple(a for a in self._items if isinstance(a, kind))

    def believed(self) -> AssertionSet:
        """Everything not withdrawn by its author. What a rule reads."""
        return AssertionSet(a for a in self._items
                            if not isinstance(a.basis, Retracted))

    def records(self) -> tuple[Record, ...]:
        """One `Record` per document entry, in first-seen order.

        First-seen and not sorted: a report's tie-break follows insertion
        order, and shuffling it would diff against the oracle as noise.
        """
        grouped: dict[tuple[str, str, int, str, int], list[Assertion]] = {}
        for a in self._items:
            grouped.setdefault(a.cite.record_id, []).append(a)
        return tuple(Record(tuple(v)) for v in grouped.values())

    def sorted(self) -> tuple[Assertion, ...]:
        """Total order — the one a dump is written in."""
        return tuple(sorted(self._items, key=lambda a: a.sort_key))


# --------------------------------------------------------------------------- #
# «Показание»: why do we hold this?
# --------------------------------------------------------------------------- #


def why(assertion: Assertion, *, depth: int = 0, render=None) -> str:
    """The evidence chain behind one assertion, as a human would read it out."""
    name = (render(assertion) if render else
            f"{type(assertion).__name__}({assertion.subject} → {assertion.payload})")
    pad = "  " * depth
    arrow = "← " if depth else ""
    basis = assertion.basis
    if isinstance(basis, Retracted):
        head = f"{pad}{arrow}{name} — ОТОЗВАНО: {basis.reason}"
        inner = _basis_line(basis.retracts, assertion, depth + 1)
        return f"{head}\n{inner}" if inner else head
    if isinstance(basis, Derived):
        head = (f"{pad}{arrow}{name} — ВЫВЕДЕНО "
                f"({basis.rationale}, {basis.surety.name})")
        return "\n".join([head] + [why(b, depth=depth + 1, render=render)
                                   for b in basis.because])
    mark = "ЗАПИСАНО" if not basis.basis_unknown else "ЗАПИСАНО?, основание неизвестно"
    return f"{pad}{arrow}{name} — {mark}  [{assertion.cite}]"


def _basis_line(basis: Basis, assertion: Assertion, depth: int) -> str:
    """Render what a retraction withdrew, so the source's own claim survives."""
    pad = "  " * depth
    if isinstance(basis, Derived):
        return (f"{pad}← было ВЫВЕДЕНО ({basis.rationale}, {basis.surety.name})")
    if isinstance(basis, Stated):
        return f"{pad}← было ЗАПИСАНО  [{assertion.cite}]"
    return ""
