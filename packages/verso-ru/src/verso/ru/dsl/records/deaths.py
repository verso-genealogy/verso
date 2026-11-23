from __future__ import annotations

import copy
from calendar import Month
from typing import TYPE_CHECKING

from verso.ru.domain import Gender, Person, RecordDefaults, _set_clergy_status
from verso.ru.domain.record_defaults import apply_parish_to_clergy
from verso.ru.dsl.records.reviewed import resolve_reviewed
from verso.ru.domain.statuses import child_status_for
from verso.ru.naming import get_gender_from_name, derive_patronymic, derive_old_patronymic, feminize_surname
from verso.ru.relationship import Relationship, Relative, gender_from_relationship
from verso.core.written import captures_written, shadow

if TYPE_CHECKING:
    from verso.ru.exporters.base import RecordsExporter


class Death:
    def __init__(self,
                 # None = the record carries no number in the source (a scribe's
                 # omission, or a row the marginal bracket numbering skips).
                 record_num: int | None,
                 gender: Gender | str,
                 d_day: int | None = None,
                 b_day: int | None = None,
                 d_month: Month | None = None,
                 b_month: Month | None = None,
                 deceased: Person | None = None,
                 age: float | str | None = None,
                 relatives: list[Relative] | None = None,
                 witness1: Person | None = None,
                 witness2: Person | None = None,
                 priest: Person | None = None,
                 deacon: Person | None = None,
                 dyachok: Person | None = None,
                 sexton: Person | None = None,
                 cause_of_death: str | None = None,
                 page: str | None = None,
                 archive: str | None = None,
                 fund: str | None = None,
                 inventory: str | None = None,
                 case: str | None = None,
                 church: str | None = None,
                 book: str | None = None,
                 comment: str | None = None,
                 year: int | None = None,
                 reviewed: bool | None = None,
                 source_age_error: str | None = None,
                 source_date_error: str | None = None,
                 namesake: str | None = None,
                 lag_note: str | None = None):
        self.record_num = record_num
        # `None` is «not stated»: `page()` and then the record set fill it,
        # so a whole лист can be held (`verso.ru.dsl.records.reviewed`).
        self.reviewed = reviewed
        # Free text: the two DATES have been re-read on the scan and the
        # transcription is faithful, but the source contradicts itself —
        # «погребёнъ 8, умеръ 9 — так в подлиннике». The burial is the claim
        # withdrawn (as `source_date_error` withdraws the CHRISTENING on a
        # birth, not the birth), so every other assertion of the record stays
        # believed. `verso date-order` honours it and stops reporting. Never
        # emitted to terraform. Do NOT use it to silence a conflict caused by
        # a wrong merge — that is a real error about two people, not a slip.
        self.source_date_error = source_date_error
        # Free text: the stated age has been re-read on the scan, the
        # transcription is faithful, and the SCRIBE's figure is wrong — «6 мѣс»
        # for a girl who lived a year and two weeks. `verso.ru.facts` withdraws the
        # age, the translator derives no birth from it (nor the parent's bound
        # that rested on it), and `verso death-age` / `sibling-spacing` stop
        # reporting (cf. source_date_error for dates, source_kin_error for
        # kin). The document still prints the age as written.
        self.source_age_error = source_age_error
        # Free text: the age is RIGHT, and the burial is of a namesake — a
        # second child given the name of one who died, whom `verso death-age`
        # pairs with the first child's christening by name and parents. Only
        # that check reads it (as `AgedYears.namesake`, in
        # `verso.ru.facts.checks.stated_age.stated_age_findings`); the age stays believed and
        # dates the birth.
        # (Until 2026-09-25 this case was written as `source_age_error`.)
        self.namesake = namesake
        # The author's note that the burial is RIGHTLY this long after the
        # death — both dates re-read on the scan. Stands `verso facts
        # --check burial-lag` down for this record and nothing else; never
        # emitted to terraform. Not a retraction (cf. `source_date_error`):
        # both dates stay believed. An empty string is no note.
        self.lag_note = lag_note or None
        self.gender = gender
        self.year = year
        self.d_day = d_day
        self.d_month = d_month
        self.b_day = b_day
        self.b_month = b_month
        self.deceased = deceased
        self.relatives: list[Relative] = relatives if relatives is not None else []
        self.witness1 = witness1
        self.witness2 = witness2
        self.priest = _set_clergy_status(priest, "священник")
        self.deacon = _set_clergy_status(deacon, "диакон")
        self.dyachok = _set_clergy_status(dyachok, "дьячок")
        self.sexton = _set_clergy_status(sexton, "пономарь")
        self.cause_of_death = cause_of_death
        self.age = age
        self.page = page
        self.archive = archive
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.church = church
        self.book = book
        self.comment = comment
        # A book of the civil registry (ЗАГС) — `civil=True` on the record set —
        # registers rather than buries: its second date is the registration's.
        # Stamped onto each record by its record set.
        self.civil = False

        # Auto-assign genders: first try to detect from name, then fall back to role-based assignment
        if self.deceased and not self.deceased.gender:
            # self.gender is `Gender | str` (the DSL allows a string gender); Person.gender
            # is `Gender | None`. The str case is a legacy duality handled elsewhere.
            self.deceased.gender = get_gender_from_name(self.deceased.name_modern) or self.gender  # type: ignore[assignment]
        for rel in self.relatives:
            if rel.person and not rel.person.gender:
                name_gender = get_gender_from_name(rel.person.name_modern)
                rel_gender = gender_from_relationship(rel.relationship) if rel.relationship else None
                rel.person.gender = name_gender or rel_gender
        if self.witness1 and not self.witness1.gender:
            self.witness1.gender = get_gender_from_name(self.witness1.name_modern)
        if self.witness2 and not self.witness2.gender:
            self.witness2.gender = get_gender_from_name(self.witness2.name_modern)

        # Validate that record gender matches deceased's gender (if known)
        if self.deceased and self.deceased.gender and self.deceased.gender != self.gender:
            raise ValueError(
                f"Death record #{record_num}: record gender '{self.gender}' does not match "
                f"deceased gender '{self.deceased.gender}' for '{self.deceased.name_orig}'"
            )

        # Validate that relative gender matches the relationship (if known)
        for rel in self.relatives:
            if rel.person and rel.person.gender and rel.relationship:
                expected = gender_from_relationship(rel.relationship)
                if expected is not None and rel.person.gender != expected:
                    raise ValueError(
                        f"Death record #{record_num}: relative gender must be {expected.name} "
                        f"for relationship '{rel.relationship}', "
                        f"got '{rel.person.gender}' for '{rel.person.name_orig}'"
                    )

        # If a father relative is present, set patronymic for deceased if missing
        if self.deceased:
            for rel in self.relatives:
                if (rel.relationship == Relationship.FATHER
                        and rel.person and rel.person.name_modern
                        and not self.deceased.patr_old):
                    canonical = derive_patronymic(rel.person.name_modern, self.deceased.gender)
                    self.deceased.patr_modern = canonical
                    old_form = derive_old_patronymic(rel.person.name_modern, self.deceased.gender)
                    if old_form:
                        self.deceased.patr_old = old_form
                    break  # Only derive from the first father

        # Surname inheritance from a related father/husband: 18th-19th
        # century metric books routinely omit the surname of a deceased
        # child or wife even when the father's/husband's surname is
        # recorded in the same entry. Mirror the birth-record rule
        # (births.py): when the deceased has no surname of their own but a
        # related father (deceased is a child) or husband (deceased is a
        # wife) does, derive it — gender-adjusted.
        #
        # As in births.py, only `last_name_modern` (sons / wives) or
        # `birth_last_name_modern` (daughters) is populated; `last_name`
        # (the as-written form) stays empty so document-text rendering keeps
        # the original "no surname in book" appearance while the profile
        # still consolidates with other appearances of the same person.
        # A wife's inherited surname is her married name, so it routes to
        # `last_name_modern` with `last_name_in_book=False` (like the mother
        # in births.py); a daughter's routes to `birth_last_name_modern`
        # (Geni maiden_name).
        if (self.deceased
                and not self.deceased.last_name
                and not self.deceased.last_name_modern
                and not self.deceased.birth_last_name_modern):
            for rel in self.relatives:
                if not (rel.person and rel.person.last_name_modern):
                    continue
                if rel.relationship == Relationship.FATHER:
                    if self.deceased.gender == Gender.FEMALE:
                        self.deceased.birth_last_name_modern = feminize_surname(
                            rel.person.last_name_modern)
                    else:
                        self.deceased.last_name_modern = rel.person.last_name_modern
                    break
                if rel.relationship == Relationship.HUSBAND:
                    self.deceased.last_name_modern = feminize_surname(
                        rel.person.last_name_modern)
                    self.deceased.last_name_in_book = False
                    break

        # Residence: everyone named in a death entry belongs to ONE household —
        # the deceased and the kin named as their relative. The metric book
        # states the village once (usually against the household head), so
        # propagate it, mirroring the surname rule above and births.py
        # (father.residence → mother/child). Anchor = the first relative with a
        # residence (the head), else the deceased's own. Witnesses and clergy are
        # deliberately excluded: they routinely come from elsewhere.
        #
        # Without this the implicit side silently picked up the parish village
        # from RecordDefaults.apply_to_death — which runs AFTER __init__, so an
        # inherited residence wins over the default — placing e.g. a Шпонькин Бор
        # father's infant in Заманиловка.
        #
        # An author who needs a different village for one party states it
        # explicitly: an explicit value is never overwritten, and DRA001
        # (linters/checks/deaths_residence.py) flags the contradiction when the
        # two disagree.
        household_residence = next(
            (rel.person.residence for rel in self.relatives
             if rel.person and rel.person.residence), None)
        if household_residence is None and self.deceased:
            household_residence = self.deceased.residence
        if household_residence:
            if self.deceased and self.deceased.residence is None:
                self.deceased.residence = household_residence
            for rel in self.relatives:
                if rel.person and rel.person.residence is None:
                    rel.person.residence = household_residence

        # Status: a deceased child inherits the parent's сословие — the dead
        # infant of «крестьянин помещицы А.И. Маниловой» is her крестьянский
        # сын/крестьянская дочь, never the ADULT parish default («ясачный
        # крестьянин») that RecordDefaults would otherwise render into the
        # About/document text. Mirrors the birth rule (births.py) via the same
        # statuses.child_status_for; runs before apply_to_death, so the derived
        # value wins over the default.
        #
        # Like births, the first FATHER with a status is consulted exclusively
        # (a clergy/merchant father's child must not fall through to the
        # mother's estate); the first MOTHER with a status only when no such
        # father exists. HUSBAND is deliberately out of scope: a wife's form
        # (жена / законная жена) is a vocabulary choice the source makes, not
        # a derivation. A parent left to the book's default has no status yet;
        # `RecordDefaults.apply_to_death` styles the relatives first and derives
        # the deceased from them the same way (2026-10-09).
        if self.deceased is not None and self.deceased.status is None:
            parent = next(
                (rel.person for rel in self.relatives
                 if rel.person and rel.person.status
                 and rel.relationship == Relationship.FATHER), None)
            if parent is None:
                parent = next(
                    (rel.person for rel in self.relatives
                     if rel.person and rel.person.status
                     and rel.relationship == Relationship.MOTHER), None)
            if parent is not None and parent.status:
                derived = child_status_for(str(parent.status), self.deceased.gender)
                if derived is not None:
                    self.deceased.status = derived

    # The first relative is the one a burial carries into every output — the
    # translator emits `relatives[0]` alone (DRL001), the CSV columns and
    # village.db read it — so it has a name of its own.
    @property
    def relative(self) -> Person | None:
        """The first relative's person."""
        return self.relatives[0].person if self.relatives else None

    @property
    def relationship(self) -> Relationship | None:
        """What the first relative is to the deceased."""
        return self.relatives[0].relationship if self.relatives else None


class DeathRecords:
    def __init__(
            self,
            archive: str,
            fund: str,
            inventory: str,
            case: str,
            village: str,
            church: str,
            year: int,
            records: list[Death],
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
        # its registration, not a burial. Each record carries it too, so a
        # reader given the record alone (the facts layer) knows.
        self.civil = civil
        for record in records:
            record.civil = civil

    def export(self, exporter: RecordsExporter) -> str:
        return exporter.export(self)


@captures_written
def death(record_num: int | None,
          gender: Gender,
          d_day: int | None = None,
          b_day: int | None = None,
          d_month: Month | None = None,
          b_month: Month | None = None,
          deceased: Person | None = None,
          age: float | str | None = None,
          relatives: list[Relative] | None = None,
          witness1: Person | None = None,
          witness2: Person | None = None,
          priest: Person | None = None,
          deacon: Person | None = None,
          dyachok: Person | None = None,
          sexton: Person | None = None,
          cause_of_death: str | None = None,
          page: str | None = None,
          case: str | None = None,
          comment: str | None = None,
          year: int | None = None,
          reviewed: bool | None = None,
          source_age_error: str | None = None,
          source_date_error: str | None = None,
          namesake: str | None = None,
          lag_note: str | None = None) -> Death:
    return Death(record_num,
                 gender,
                 d_day,
                 b_day,
                 d_month,
                 b_month,
                 deceased,
                 age=age,
                 relatives=relatives,
                 witness1=witness1,
                 witness2=witness2,
                 priest=priest,
                 deacon=deacon,
                 dyachok=dyachok,
                 sexton=sexton,
                 cause_of_death=cause_of_death,
                 page=page,
                 case=case,
                 comment=comment,
                 year=year,
                 reviewed=reviewed,
                 source_age_error=source_age_error,
                 source_date_error=source_date_error,
                 namesake=namesake,
                 lag_note=lag_note)


@captures_written
def death_records(
        archive: str,
        fund: str,
        inventory: str,
        case: str,
        village: str,
        church: str,
        year: int,
        *records: Death,
        defaults: RecordDefaults | None = None,
        reviewed: bool = True,
        civil: bool = False,
) -> DeathRecords:
    for record in records:
        if defaults is not None:
            defaults.apply_to_death(record)
        apply_parish_to_clergy(record, village)
    return DeathRecords(archive, fund, inventory, case, village, church, year, list(records),
                        reviewed=reviewed, civil=civil)


def death_month(month: Month | None, *records: Death) -> list[Death]:
    """Helper to group deaths by month. Pass None for unknown month."""

    return death_month_year(month, None, *records)


def death_month_year(month: Month | None, year: int | None, *records: Death) -> list[Death]:
    """Helper to group deaths by month."""

    def copy_with_month(record: Death) -> Death:
        r = copy.deepcopy(record)
        if r.d_month is None and month is not None:
            r.d_month = month
        else:
            shadow(r, "d_month", month)        # the record writes its own: the section's is kept beside it
        if r.b_month is None and month is not None:
            r.b_month = month
        else:
            shadow(r, "b_month", month)
        if year is not None and r.year is None:
            r.year = year
        else:
            shadow(r, "year", year)
        return r

    return [copy_with_month(record) for record in records]
