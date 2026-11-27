from __future__ import annotations

import copy
from calendar import Month
from typing import TYPE_CHECKING

from verso.ru.domain import Person, Gender, RecordDefaults, _set_clergy_status
from verso.ru.domain.record_defaults import apply_parish_to_clergy
from verso.ru.domain.statuses import child_status_for
from verso.ru.dsl.records.reviewed import resolve_reviewed
from verso.ru.naming import derive_old_patronymic, derive_patronymic, feminize_surname, get_gender_from_name
from verso.ru.relationship import Relative, relative  # noqa: F401 (re-exported for backward compat)
from verso.core.written import written_of
from verso.ru.relationship import Relationship, gender_from_relationship
from verso.core.written import captures_written, shadow

if TYPE_CHECKING:
    from verso.ru.exporters.base import RecordsExporter



def as_written(child: Person | None) -> Person | None:
    """A copy of a newborn without the patronymic `Birth.__init__` derived from the father (both forms
    empty, as the record left them); the record's own child is not touched."""
    if child is None:
        return None
    bare = copy.copy(child)
    bare.patr_old = ""
    bare.patr_modern = ""
    return bare

class Birth:
    # Overridden to True by the Christening subclass so the translator can
    # label the record (about-text + geni_document) as крещение rather than
    # рождение, independent of whether christening_age is known.
    is_christening = False

    def __init__(self,
                 # Matches the `birth()` verb below: a scribal-suffixed number
                 # ("12а") or an unnumbered record are both real. Consumers
                 # stringify it; the one int() call guards with try/except.
                 record_num: int | str | None,
                 gender: Gender,
                 b_day: int | None = None,
                 k_day: int | None = None,
                 b_month: Month | None = None,
                 k_month: Month | None = None,
                 child: Person | None = None,
                 father: Person | None = None,
                 mother: Person | None = None,
                 god_parent1: Person | None = None,
                 god_parent2: Person | None = None,
                 god_parent3: Person | None = None,
                 god_parent4: Person | None = None,
                 priest: Person | None = None,
                 deacon: Person | None = None,
                 dyachok: Person | None = None,
                 sexton: Person | None = None,
                 page: str | None = None,
                 inventory: str | None = None,
                 case: str | None = None,
                 book: str | None = None,
                 comment: str | None = None,
                 relatives: list[Relative] | None = None,
                 year: int | None = None,
                 k_year: int | None = None,
                 christening_age: int | None = None,
                 source_date_error: str | None = None,
                 reviewed: bool | None = None,
                 calendar_note: str | None = None,
                 lag_note: str | None = None,
                 father_age: int | str | None = None,
                 mother_age: int | str | None = None,
                 source_age_error: str | None = None):
        self.record_num = record_num
        # `None` is «not stated»: `page()` and then the record set fill it,
        # so a whole лист can be held (`verso.ru.dsl.records.reviewed`).
        self.reviewed = reviewed
        # The author's note that the child's name is RIGHT although no saint
        # of it is kept near the birth or the christening — re-read on the
        # scan and given out of season. Stands `verso facts --check name-days`
        # down for this record and nothing else; never emitted to terraform.
        # Not a retraction: the name and both dates stay believed.
        self.calendar_note = calendar_note or None
        # Free-text reason why this record's OWN dates are internally
        # inconsistent IN THE SOURCE — e.g. a christening the scribe dated
        # before the birth. Truthy means `verso date-order` acknowledges the
        # record instead of reporting it forever: the transcription is faithful
        # and there is nothing to fix on our side. Never use it to silence a
        # conflict caused by consolidation — that is a real error about two
        # people, not about one scribe's slip.
        self.source_date_error = source_date_error
        # The author's note that the christening is RIGHTLY this long after the
        # birth — both dates re-read on the scan. Stands `verso facts
        # --check baptism-lag` down for this record and nothing else; never
        # emitted to terraform. Not a retraction (cf. `source_date_error`):
        # both dates stay believed. An empty string is no note.
        self.lag_note = lag_note or None
        # The parents' ages the entry states (a civil register's act gives them; a church book seldom
        # does), as written — a number or a string, never normalised (`verso.ru.ages.age_bounds` reads
        # the interval). The same type as a marriage's `groom_age`.
        self.father_age = father_age
        self.mother_age = mother_age
        # The author's note that the parents' ages are so IN THE SOURCE and cannot be right (a scribe's
        # slip, re-read on the scan): retracts both ages of this record and stands the checks on them
        # down. As `source_age_error` of a death. An empty string is no note.
        self.source_age_error = source_age_error or None
        self.gender = gender
        self.b_day = b_day
        self.b_month = b_month
        self.k_day = k_day
        self.k_month = k_month
        self.year = year
        # Christening year, if different from birth year. Used for
        # mk_{year}_birth.tf file assignment (mirrors legacy's
        # `year_of_christening`); `year` is used for res_name, about,
        # etc. (mirrors legacy's `year_of_birth`). When unset, file
        # assignment falls back to `year`.
        self.k_year = k_year
        # Age (in full years) at christening, for late/adult baptism
        # records where no exact birth date is known. When set, the
        # translator emits a circa birth year (`year - christening_age`)
        # and labels the about-text as крещение rather than рождение.
        self.christening_age = christening_age
        self.child = child
        self.father = father
        self.mother = mother
        self.god_parent1 = god_parent1
        self.god_parent2 = god_parent2
        self.god_parent3 = god_parent3
        self.god_parent4 = god_parent4
        self.priest = _set_clergy_status(priest, "священник")
        self.deacon = _set_clergy_status(deacon, "диакон")
        self.dyachok = _set_clergy_status(dyachok, "дьячок")
        self.sexton = _set_clergy_status(sexton, "пономарь")
        self.page = page
        self.inventory = inventory
        self.case = case
        self.book = book
        self.comment = comment
        # A book of the civil registry (ЗАГС) — `civil=True` on the record set —
        # registers rather than christens: its second date is the
        # registration's. Stamped onto each record by its record set.
        self.civil = False
        self.relatives: list[Relative] = relatives if relatives is not None else []

        # Validate dates: if both day and month are present, they must be valid
        if self.b_day is not None:
            if not (1 <= self.b_day <= 31):
                raise ValueError(f"Invalid birth day: {self.b_day}")

        if self.b_month is not None:
            if self.b_month not in Month:
                raise ValueError(f"Invalid birth month: {self.b_month}")

        if self.k_day is not None:
            if not (1 <= self.k_day <= 31):
                raise ValueError(f"Invalid christening day: {self.k_day}")

        if self.k_month is not None:
            if self.k_month not in Month:
                raise ValueError(f"Invalid christening month: {self.k_month}")

        if self.christening_age is not None and self.christening_age < 0:
            raise ValueError(f"Invalid christening age: {self.christening_age}")

        # Auto-assign genders if not yet set
        if self.child and not self.child.gender:
            self.child.gender = get_gender_from_name(self.child.name_modern) or self.gender
        if self.father and not self.father.gender:
            self.father.gender = get_gender_from_name(self.father.name_modern) or Gender.MALE
        if self.mother and not self.mother.gender:
            self.mother.gender = get_gender_from_name(self.mother.name_modern) or Gender.FEMALE

        # Residence inheritance: mother lives at father's residence
        # unless the DSL explicitly sets a different one. Matches
        # legacy's per-record residence-propagation behavior.
        if (self.father and self.father.residence
                and self.mother and not self.mother.residence):
            self.mother.residence = self.father.residence

        # Child residence: a newborn lives where the family lives. Mirror the
        # mother-from-father rule — prefer the father's residence, else the
        # mother's. RecordDefaults.apply_to_person back-fills any remaining None.
        if self.child is not None and not self.child.residence:
            if self.father is not None and self.father.residence:
                self.child.residence = self.father.residence
            elif self.mother is not None and self.mother.residence:
                self.child.residence = self.mother.residence
        if self.god_parent1 and not self.god_parent1.gender:
            self.god_parent1.gender = get_gender_from_name(self.god_parent1.name_modern) or Gender.MALE
        if self.god_parent2 and not self.god_parent2.gender:
            self.god_parent2.gender = get_gender_from_name(self.god_parent2.name_modern) or Gender.FEMALE
        for rel in self.relatives:
            if rel.person and not rel.person.gender:
                name_gender = get_gender_from_name(rel.person.name_modern)
                rel_gender = gender_from_relationship(rel.relationship)
                rel.person.gender = name_gender or rel_gender

        # Mother last_name inheritance: 18th-19th century metric books
        # routinely omit the wife's surname from the ФИО column even when
        # the husband's is recorded. When the mother has no surname of
        # her own but the father does, derive the feminized form and mark
        # `last_name_in_book=False` so document-text rendering keeps the
        # original "no surname in book" appearance while the profile still
        # consolidates with other appearances of the same person.
        if (self.mother is not None
                and not self.mother.last_name
                and not self.mother.last_name_modern
                and self.father is not None
                and self.father.last_name_modern):
            self.mother.last_name_modern = feminize_surname(self.father.last_name_modern)
            self.mother.last_name_in_book = False

        # Child last_name inheritance: same rule the legacy CSV pipeline
        # applied. When `child` has no explicit surname but a parent does,
        # inherit it — gender-adjusted for daughters. Mirrors the
        # auto-patronymic logic in `CensusHousehold.__init__` for child
        # roles.
        #
        # Only `last_name_modern` (sons) or `birth_last_name_modern`
        # (daughters) is populated: that's what the translator uses to
        # build res_names and displayed profile fields. `last_name`
        # (the as-written-in-the-book form) stays empty — the metric book
        # didn't record a surname for the child, and the "Имена в МК"
        # transcription downstream must reflect that absence.
        #
        # Daughters route to `birth_last_name_modern` so Geni renders the
        # inherited surname as `maiden_name` rather than `last_name` (a
        # newborn girl has no current/married surname).
        if (self.child and not self.child.last_name and not self.child.last_name_modern
                and not self.child.birth_last_name_modern):
            inherited_modern: str | None = None
            if self.child.gender == Gender.FEMALE:
                if self.mother and self.mother.last_name_modern:
                    inherited_modern = self.mother.last_name_modern
                elif self.father and self.father.last_name_modern:
                    inherited_modern = feminize_surname(self.father.last_name_modern)
                if inherited_modern:
                    self.child.birth_last_name_modern = inherited_modern
            elif self.father and self.father.last_name_modern:
                self.child.last_name_modern = self.father.last_name_modern

        # Child patronymic from the father, in both forms — the rule Death.__init__
        # applies to a deceased child (deaths.py). A birth record writes the
        # newborn's given name alone; the father's name is the patronymic every
        # output already gives the child (`derive_child_patronymic`: the Geni
        # translator, the CSV), and now the records JSON and the facts as well (В10).
        # The breadcrumb is the deaths' one, negative: `patr_orig` stays empty
        # while `patr_old` and `patr_modern` fill in — the facts layer reads that
        # as derived, never as the record's word.
        if (self.child is not None and self.father is not None
                and not self.child.patr_orig and not self.child.patr_old and not self.child.patr_modern):
            patr = self.derive_child_patronymic()
            if patr:
                self.child.patr_modern = patr
                self.child.patr_old = derive_old_patronymic(self.father.name_modern, self.gender) or ""

        # Godparent surname from the relative named for them — the rule
        # Death.__init__ applies to the deceased (deaths.py) and Marriage
        # applies to its partners. «восприемника №N» attaches a father or a
        # husband to godparent N, and that is often the only place the
        # godparent's family name appears in the record.
        for position, godparent in enumerate(
                (self.god_parent1, self.god_parent2,
                 self.god_parent3, self.god_parent4), start=1):
            self._derive_godparent_surname(godparent, f"восприемника №{position}")

        # Child status inheritance: сословие is inherited within the household —
        # the newborn of «крестьянин помещицы Ульяны Корнеевны Собакевич» is her
        # крестьянский сын/крестьянская дочь, never the parish default that
        # RecordDefaults would otherwise substitute (apply_to_birth runs AFTER
        # __init__, and apply_to_person fills only a None status, so the derived
        # value wins — same ordering as the residence rule above).
        #
        # A father WITH any status is consulted exclusively: when his estate is
        # out of derivation scope (clergy, merchant, дворовый — see
        # statuses.child_status_for), the child must NOT fall through to the
        # mother, whose estate would be the wrong one for that household. The
        # mother is the fallback only when the father is absent or statusless
        # (typically незаконнорожденные). A parent left to the book's default has
        # no status yet; `RecordDefaults.apply_to_birth` gives the parents theirs
        # first and derives the child from them the same way (2026-10-09).
        if self.child is not None and self.child.status is None:
            parent = (self.father
                      if self.father is not None and self.father.status
                      else self.mother)
            if parent is not None and parent.status:
                derived = child_status_for(str(parent.status), self.child.gender)
                if derived is not None:
                    self.child.status = derived

        # Validate role-based gender constraints
        if self.child and self.child.gender and self.child.gender != self.gender:
            raise ValueError(
                f"Birth record #{record_num}: record gender '{self.gender}' does not match "
                f"child gender '{self.child.gender}' for '{self.child.name_orig}'"
            )
        if self.father and self.father.gender and self.father.gender != Gender.MALE:
            raise ValueError(
                f"Birth record #{record_num}: father gender must be MALE, "
                f"got '{self.father.gender}' for '{self.father.name_orig}'"
            )
        if self.mother and self.mother.gender and self.mother.gender != Gender.FEMALE:
            raise ValueError(
                f"Birth record #{record_num}: mother gender must be FEMALE, "
                f"got '{self.mother.gender}' for '{self.mother.name_orig}'"
            )
        for rel in self.relatives:
            if rel.person and rel.person.gender:
                expected = gender_from_relationship(rel.relationship)
                if expected is not None and rel.person.gender != expected:
                    raise ValueError(
                        f"Birth record #{record_num}: relative gender must be {expected.name} "
                        f"for relationship '{rel.relationship}', "
                        f"got '{rel.person.gender}' for '{rel.person.name_orig}'"
                    )

    def derive_child_patronymic(self) -> str | None:
        father_name = self.father.name_modern if self.father else None
        patr = derive_patronymic(father_name, self.gender)
        # Suppress placeholder when the father's name was "?" — emitting
        # `middle_name = "?"` on the child profile loses parity with the
        # legacy generator, which left middle_name unset in that case.
        return None if not patr or "?" in patr else patr

    def child_patronymic_derived(self) -> bool:
        """Whether the newborn's patronymic is the one `__init__` derived from the father rather than the
        record's: none written — by what the `person()` call wrote (`written_of`) where it kept it, else by
        `patr_orig` — and the derived one in place. The Geni translator keeps it out of «Имена в МК», as it keeps
        a deceased child's (`_shallow_person_without_patr`); the facts layer states it as derived; the
        consolidation channels read the child without it (`written_child`)."""
        child = self.child
        if child is None or self.father is None or not child.patr_modern:
            return False
        written = written_of(child)
        wrote = (any(written.get(k) for k in ("patr_orig", "patr_old")) if written is not None
                 else bool(child.patr_orig))
        return not wrote and child.patr_modern == self.derive_child_patronymic()

    def written_child(self) -> Person | None:
        """The newborn as the record writes him: `child` without the patronymic `__init__` derived from the
        father. The channels that weigh who may be whom read this one — a patronymic made of the father is no
        evidence of the child (В10), and two spellings of the father's name would part the child from his own
        burial."""
        return as_written(self.child) if self.child_patronymic_derived() else self.child

    def get_birth_location(self, default: str | None = None) -> str | None:
        """Return the village where the birth actually happened.

        Priority: father.residence → mother.residence → `default`. Parents'
        `residence` is populated by explicit DSL input or back-filled from
        RecordDefaults (see genealogy.py). Callers typically pass the
        enclosing book's parish as `default` for the fallback case where
        the DSL carries no residence on either parent.
        """
        for parent in (self.father, self.mother):
            if parent is not None and parent.residence:
                return parent.residence
        return default


    def _derive_godparent_surname(self, godparent: Person | None, ref: str) -> None:
        """Fill a godparent's surname from the FATHER or HUSBAND refd to them.

        A husband's surname is the godmother's MARRIED name (feminized, and
        `last_name_in_book=False` like the mother's in a birth); a father's
        passes down as-is for a son and feminized for a daughter.
        """
        if godparent is None:
            return
        if (godparent.last_name or godparent.last_name_modern
                or godparent.birth_last_name_modern):
            return
        for rel in self.relatives:
            if rel.relationship_ref != ref:
                continue
            if not (rel.person and rel.person.last_name_modern):
                continue
            inherited = rel.person.last_name_modern
            if rel.relationship == Relationship.HUSBAND:
                godparent.last_name_modern = feminize_surname(inherited)
            elif rel.relationship == Relationship.FATHER:
                godparent.last_name_modern = (
                    feminize_surname(inherited) if godparent.gender == Gender.FEMALE
                    else inherited)
            else:
                continue
            godparent.last_name_in_book = False
            return

class Christening(Birth):
    """A late/adult christening recorded in the birth register.

    Behaves like a `Birth` (so it flows through `birth_month`, `page`,
    `birth_records` and the translator/exporter unchanged) but carries no
    recorded birth date — only the christening date and the person's age at
    christening. The translator derives a circa birth year from the age.
    """

    is_christening = True


class BirthRecords:
    def __init__(
            self,
            archive: str,
            fund: str,
            inventory: str,
            case: str,
            village: str,
            church: str,
            year: int,
            records: list[Birth],
            reviewed: bool = True,
            civil: bool = False,
    ):
        self.archive = archive
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.village = village
        self.church = church
        self.year = year
        self.records = records
        # File-level default for the per-record `reviewed` flag, resolved here
        # so a record leaves its record set True or False.
        self.reviewed = reviewed
        resolve_reviewed(self.records, reviewed)
        # A book of the civil registry (ЗАГС): the second date of each entry is
        # its registration, not a christening or a burial. Each record carries
        # it too, so a reader given the record alone (the facts layer) knows.
        self.civil = civil
        for record in records:
            record.civil = civil

    def export(self, exporter: RecordsExporter) -> str:
        return exporter.export(self)


@captures_written
def birth(
        record_num: int | str | None,
        gender: Gender,
        b_day: int | None = None,
        k_day: int | None = None,
        b_month: Month | None = None,
        k_month: Month | None = None,
        child: Person | None = None,
        father: Person | None = None,
        mother: Person | None = None,
        god_parent1: Person | None = None,
        god_parent2: Person | None = None,
        god_parent3: Person | None = None,
        god_parent4: Person | None = None,
        priest: Person | None = None,
        deacon: Person | None = None,
        dyachok: Person | None = None,
        sexton: Person | None = None,
        page: str | None = None,
        case: str | None = None,
        comment: str | None = None,
        relatives: list[Relative] | None = None,
        year: int | None = None,
        k_year: int | None = None,
        source_date_error: str | None = None,
        reviewed: bool | None = None,
        calendar_note: str | None = None,
        lag_note: str | None = None,
        father_age: int | str | None = None,
        mother_age: int | str | None = None,
        source_age_error: str | None = None,
) -> Birth:
    return Birth(record_num,
                 gender,
                 b_day,
                 k_day,
                 b_month,
                 k_month,
                 child,
                 father,
                 mother,
                 god_parent1,
                 god_parent2,
                 god_parent3=god_parent3,
                 god_parent4=god_parent4,
                 priest=priest,
                 deacon=deacon,
                 dyachok=dyachok,
                 sexton=sexton,
                 page=page,
                 case=case,
                 comment=comment,
                 relatives=relatives,
                 year=year,
                 k_year=k_year,
                 source_date_error=source_date_error,
                 reviewed=reviewed,
                 calendar_note=calendar_note,
                 lag_note=lag_note,
                 father_age=father_age,
                 mother_age=mother_age,
                 source_age_error=source_age_error)


@captures_written
def christening(
        record_num: int | str | None,
        gender: Gender,
        k_day: int | None = None,
        k_month: Month | None = None,
        *,
        age: int | None = None,
        child: Person | None = None,
        father: Person | None = None,
        mother: Person | None = None,
        god_parent1: Person | None = None,
        god_parent2: Person | None = None,
        god_parent3: Person | None = None,
        god_parent4: Person | None = None,
        priest: Person | None = None,
        deacon: Person | None = None,
        dyachok: Person | None = None,
        sexton: Person | None = None,
        page: str | None = None,
        case: str | None = None,
        comment: str | None = None,
        relatives: list[Relative] | None = None,
        year: int | None = None,
        reviewed: bool | None = None,
        calendar_note: str | None = None,
) -> Christening:
    """A late/adult christening in the birth register.

    Unlike `birth()`, there is no recorded birth date — only the christening
    date (`k_day`/`k_month`, with `k_month` injected by `birth_month()` when
    omitted) and the person's `age` at christening. The translator emits a
    circa birth year (`year - age`) and a baptism event with the christening
    date.
    """
    return Christening(record_num,
                       gender,
                       b_day=None,
                       k_day=k_day,
                       b_month=None,
                       k_month=k_month,
                       child=child,
                       father=father,
                       mother=mother,
                       god_parent1=god_parent1,
                       god_parent2=god_parent2,
                       god_parent3=god_parent3,
                       god_parent4=god_parent4,
                       priest=priest,
                       deacon=deacon,
                       dyachok=dyachok,
                       sexton=sexton,
                       page=page,
                       case=case,
                       comment=comment,
                       relatives=relatives,
                       year=year,
                       christening_age=age,
                       reviewed=reviewed,
                       calendar_note=calendar_note)


@captures_written
def birth_records(
        archive: str,
        fund: str,
        inventory: str,
        case: str,
        village: str,
        church: str,
        year: int,
        *records: Birth,
        defaults: RecordDefaults | None = None,
        reviewed: bool = True,
        civil: bool = False,
) -> BirthRecords:
    records_copy = copy.deepcopy(records)
    for record in records_copy:
        if defaults is not None:
            defaults.apply_to_birth(record)
        apply_parish_to_clergy(record, village)
    return BirthRecords(archive, fund, inventory, case, village, church, year, list(records_copy),
                        reviewed=reviewed, civil=civil)


def birth_month(month: Month | None, *records: Birth) -> list[Birth]:
    """Helper to group births by month. Pass None for unknown month."""

    return birth_month_year(month, None, *records)


def birth_month_year(month: Month | None, year: int | None, *records: Birth) -> list[Birth]:
    """Helper to group births by month."""

    def copy_with_month(record) -> Birth:
        r = copy.deepcopy(record)
        if r.b_month is None and month is not None:
            r.b_month = month
        else:
            shadow(r, "b_month", month)        # the record writes its own: the section's is kept beside it
        # Cross-month auto-detection: when christening day < birth day
        # within the same birth_month grouping, the christening
        # spilled into the next month (e.g. born 25 Jan, baptized 1
        # Feb). Advance k_month — and k_year if December rolls over.
        spilled = (month is not None and r.b_day is not None and r.k_day is not None
                   and r.k_day < r.b_day)
        k_month = Month((month.value % 12) + 1) if spilled and month is not None else month
        if r.k_month is None and month is not None:
            r.k_month = k_month
            if spilled and month == Month.DECEMBER and r.k_year is None and year is not None:
                r.k_year = year + 1
        else:
            shadow(r, "k_month", k_month)
        if year is not None and r.year is None:
            r.year = year
        else:
            shadow(r, "year", year)
        return r

    return [copy_with_month(record) for record in records]
