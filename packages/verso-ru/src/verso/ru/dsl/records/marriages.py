from __future__ import annotations

import copy
from calendar import Month
from typing import TYPE_CHECKING

from verso.ru.domain import Person, Gender, RecordDefaults, Side, _set_clergy_status
from verso.ru.domain.record_defaults import apply_parish_to_clergy
from verso.ru.dsl.records.reviewed import resolve_reviewed
from verso.ru.naming import derive_patronymic, feminize_surname, get_gender_from_name
from verso.ru.relationship import Relationship, Relative, gender_from_relationship
from verso.core.written import captures_written, shadow

if TYPE_CHECKING:
    from verso.ru.exporters.base import RecordsExporter


class Marriage:
    def __init__(
            self,
            # See Birth.__init__: matches the `marriage()` verb's own type.
            record_num: int | str | None,
            w_day: int | None = None,
            w_month: Month | None = None,
            groom: Person | None = None,
            bride: Person | None = None,
            groom_marriage_num: int | None = None,
            bride_marriage_num: int | None = None,
            groom_age: int | str | None = None,
            bride_age: int | str | None = None,
            witness1: Person | None = None,
            witness2: Person | None = None,
            witness3: Person | None = None,
            witness4: Person | None = None,
            witness5: Person | None = None,
            witness6: Person | None = None,
            page: str | None = None,
            archive: str | None = None,
            fund: str | None = None,
            inventory: str | None = None,
            case: str | None = None,
            village: str | None = None,
            church: str | None = None,
            book: str | None = None,
            comment: str | None = None,
            priest: Person | None = None,
            deacon: Person | None = None,
            dyachok: Person | None = None,
            sexton: Person | None = None,
            relatives: list[Relative] | None = None,
            year: int | None = None,
            bride_takes_groom_surname: bool = True,
            reviewed: bool | None = None,
            source_kin_error: str | None = None,
            calendar_note: str | None = None,
            age_note: str | None = None,
    ):
        self.record_num = record_num
        # `None` is «not stated»: `page()` and then the record set fill it,
        # so a whole лист can be held (`verso.ru.dsl.records.reviewed`).
        self.reviewed = reviewed
        # The author's note that the wedding date is RIGHT although the Church
        # did not marry on that day — re-read on the scan (a dispensation, a
        # parish's own custom). Stands `facts-check check=wedding-calendar`
        # down for this record and nothing else; never emitted to terraform.
        # Not a retraction: the date stays believed.
        self.calendar_note = calendar_note or None
        # Free text: the SOURCE names kin that its own patronymics or surnames
        # cannot support, and the transcription is faithful — RLA002/RLA003 honour
        # it and stop reporting (cf. source_date_error for dates). Never emitted
        # to terraform.
        self.source_kin_error = source_kin_error
        # The author's note that the ages at the wedding are RIGHT although
        # one is under the age of marriage or the two are far apart — re-read
        # on the scan. Stands `facts-check check=wedding-ages` down for this
        # record and nothing else; never emitted to terraform. Not a
        # retraction: both ages stay believed. An empty string is no note.
        self.age_note = age_note or None
        self.w_day = w_day
        self.w_month = w_month
        self.groom = groom
        self.bride = bride
        self.groom_marriage_num = groom_marriage_num
        self.bride_marriage_num = bride_marriage_num
        self.groom_age = groom_age
        self.bride_age = bride_age
        self.witness1 = witness1
        self.witness2 = witness2
        self.witness3 = witness3
        self.witness4 = witness4
        self.witness5 = witness5
        self.witness6 = witness6
        self.page = page
        self.archive = archive
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.village = village
        self.church = church
        self.book = book
        self.comment = comment
        self.priest = _set_clergy_status(priest, "священник")
        self.deacon = _set_clergy_status(deacon, "диакон")
        self.dyachok = _set_clergy_status(dyachok, "дьячок")
        self.sexton = _set_clergy_status(sexton, "пономарь")
        self.relatives: list[Relative] = relatives if relatives is not None else []
        self.year = year
        self.bride_takes_groom_surname = bride_takes_groom_surname
        # A book of the civil registry (ЗАГС) — `civil=True` on the record set —
        # registers rather than weds: its one date is the registration's.
        # Stamped onto each record by its record set.
        self.civil = False

        # Auto-set genders: first try to detect from name, then fall back to role-based assignment
        if self.groom and not self.groom.gender:
            self.groom.gender = get_gender_from_name(self.groom.name_modern) or Gender.MALE
        if self.bride and not self.bride.gender:
            self.bride.gender = get_gender_from_name(self.bride.name_modern) or Gender.FEMALE
        for rel in self.relatives:
            if rel.person and not rel.person.gender:
                name_gender = get_gender_from_name(rel.person.name_modern)
                rel_gender = gender_from_relationship(rel.relationship)
                rel.person.gender = name_gender or rel_gender
        if self.witness1 and not self.witness1.gender:
            self.witness1.gender = get_gender_from_name(self.witness1.name_modern)
        if self.witness2 and not self.witness2.gender:
            self.witness2.gender = get_gender_from_name(self.witness2.name_modern)
        if self.witness3 and not self.witness3.gender:
            self.witness3.gender = get_gender_from_name(self.witness3.name_modern)
        if self.witness4 and not self.witness4.gender:
            self.witness4.gender = get_gender_from_name(self.witness4.name_modern)
        if self.witness5 and not self.witness5.gender:
            self.witness5.gender = get_gender_from_name(self.witness5.name_modern)
        if self.witness6 and not self.witness6.gender:
            self.witness6.gender = get_gender_from_name(self.witness6.name_modern)

        # Surname from the father named as a relative — the rule
        # Death.__init__ has always applied to the deceased (deaths.py), for
        # the partners of a marriage. A partner recorded with only a name and
        # patronymic belongs to the family their father carries; without this
        # the surname sits one line away in the same record and is dropped.
        #
        # As in deaths.py only `last_name_modern` is populated: `last_name`
        # (the as-written form) stays empty and `last_name_in_book` goes False,
        # so the document text keeps the "no surname in book" appearance while
        # the profile still consolidates with the person's other appearances.
        # The bride's value is her MAIDEN surname; the translator moves it to
        # birth_last_name when she takes the groom's (bride_takes_groom_surname).
        self._derive_surname_from_father(self.groom, "жених")
        self._derive_surname_from_father(self.bride, "невеста")

        # Validate role-based genders
        if self.groom and self.groom.gender and self.groom.gender != Gender.MALE:
            raise ValueError(
                f"Marriage record #{record_num}: groom gender must be MALE, "
                f"got '{self.groom.gender}' for '{self.groom.name_orig}'"
            )
        if self.bride and self.bride.gender and self.bride.gender != Gender.FEMALE:
            raise ValueError(
                f"Marriage record #{record_num}: bride gender must be FEMALE, "
                f"got '{self.bride.gender}' for '{self.bride.name_orig}'"
            )
        for rel in self.relatives:
            if rel.person and rel.person.gender:
                expected = gender_from_relationship(rel.relationship)
                if expected is not None and rel.person.gender != expected:
                    raise ValueError(
                        f"Marriage record #{record_num}: relative gender must be {expected.name} "
                        f"for relationship '{rel.relationship}', "
                        f"got '{rel.person.gender}' for '{rel.person.name_orig}'"
                    )

        # Validate groom/bride status vs marriage number
        if (
            self.groom_marriage_num is not None
            and self.groom_marriage_num > 1
            and self.groom
            and self.groom.status
            and "отрок" in self.groom.status
        ):
            raise ValueError(
                f"Marriage record #{record_num}: groom with marriage_num={self.groom_marriage_num} "
                f"cannot have status containing 'отрок' (got '{self.groom.status}')"  # i18n: content — the source's word
            )
        if (
            self.bride_marriage_num is not None
            and self.bride_marriage_num > 1
            and self.bride
            and self.bride.status
            and "отроковиц" in self.bride.status
        ):
            raise ValueError(
                f"Marriage record #{record_num}: bride with marriage_num={self.bride_marriage_num} "
                f"cannot have status containing 'отроковица' (got '{self.bride.status}')"  # i18n: content — the source's word
            )


    def witness_sides(self) -> list[tuple[int, Person, Side | None]]:
        """The filled witness slots in slot order: (slot number, person, side).

        The side is what the person carries (`person(..., side=Side.BRIDE)`),
        None when the record does not say whom they stood surety for. The slot
        number is the one in the res_name and is never renumbered by side.
        """
        slots = (self.witness1, self.witness2, self.witness3,
                 self.witness4, self.witness5, self.witness6)
        return [(n, p, p.side) for n, p in enumerate(slots, start=1) if p is not None]

    def derive_partner_patronymic(self, partner: Person | None) -> str | None:
        """The patronymic `partner` takes from the FATHER relative refd to them.

        None when the partner writes one, or when the first father «жениха» /
        «невесты» has no name. Not stored on the person, like the newborn's
        (`Birth.derive_child_patronymic`): the book wrote no patronymic, so
        the translator puts it on the profile alone, and the review page
        shows it as what the empty field becomes.
        """
        if partner is None or partner.patr_modern:
            return None
        if partner is self.groom:
            ref, gender = "жених", Gender.MALE
        elif partner is self.bride:
            ref, gender = "невеста", Gender.FEMALE
        else:
            return None
        father = next((rel.person for rel in self.relatives
                       if rel.relationship == Relationship.FATHER
                       and rel.relationship_ref == ref), None)
        if father is None or not father.name_modern:
            return None
        return derive_patronymic(father.name_modern, gender) or None

    def _derive_surname_from_father(self, partner: Person | None, ref: str) -> None:
        """Fill `partner`'s surname from the FATHER relative refd to them.

        Silent when the partner already carries any surname, when no father is
        named for THIS partner, or when that father has no surname himself.
        """
        if partner is None:
            return
        if partner.last_name or partner.last_name_modern or partner.birth_last_name_modern:
            return
        for rel in self.relatives:
            if rel.relationship != Relationship.FATHER or rel.relationship_ref != ref:
                continue
            if not (rel.person and rel.person.last_name_modern):
                continue
            inherited = rel.person.last_name_modern
            partner.last_name_modern = (
                feminize_surname(inherited) if partner.gender == Gender.FEMALE
                else inherited)
            partner.last_name_in_book = False
            return


class MarriageRecords:
    def __init__(
            self,
            archive: str,
            fund: str,
            inventory: str,
            case: str,
            village: str,
            church: str,
            year: int,
            records: list[Marriage],
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
        # its registration, not a church wedding. Each record carries it too, so a
        # reader given the record alone (the facts layer) knows.
        self.civil = civil
        for record in records:
            record.civil = civil

    def export(self, exporter: RecordsExporter) -> str:
        return exporter.export(self)


@captures_written
def marriage(
        record_num: int | str | None,
        w_day: int | None = None,
        w_month: Month | None = None,
        groom: Person | None = None,
        bride: Person | None = None,
        groom_marriage_num: int | None = None,
        bride_marriage_num: int | None = None,
        groom_age: int | str | None = None,
        bride_age: int | str | None = None,
        witness1: Person | None = None,
        witness2: Person | None = None,
        witness3: Person | None = None,
        witness4: Person | None = None,
        witness5: Person | None = None,
        witness6: Person | None = None,
        page: str | None = None,
        case: str | None = None,
        village: str | None = None,
        church: str | None = None,
        comment: str | None = None,
        priest: Person | None = None,
        deacon: Person | None = None,
        dyachok: Person | None = None,
        sexton: Person | None = None,
        relatives: list[Relative] | None = None,
        year: int | None = None,
        bride_takes_groom_surname: bool = True,
        reviewed: bool | None = None,
        source_kin_error: str | None = None,
        calendar_note: str | None = None,
        age_note: str | None = None,
) -> Marriage:
    return Marriage(
        record_num,
        w_day,
        w_month,
        groom,
        bride,
        groom_marriage_num,
        bride_marriage_num,
        groom_age,
        bride_age,
        witness1,
        witness2,
        witness3,
        witness4,
        witness5=witness5,
        witness6=witness6,
        page=page,
        case=case,
        village=village,
        church=church,
        comment=comment,
        priest=priest,
        deacon=deacon,
        dyachok=dyachok,
        sexton=sexton,
        relatives=relatives,
        year=year,
        bride_takes_groom_surname=bride_takes_groom_surname,
        reviewed=reviewed,
        source_kin_error=source_kin_error,
        calendar_note=calendar_note,
        age_note=age_note,
    )


@captures_written
def marriage_records(
        archive: str,
        fund: str,
        inventory: str,
        case: str,
        village: str,
        church: str,
        year: int,
        *records: Marriage,
        defaults: RecordDefaults | None = None,
        reviewed: bool = True,
        civil: bool = False,
) -> MarriageRecords:
    for record in records:
        if defaults is not None:
            defaults.apply_to_marriage(record)
        apply_parish_to_clergy(record, village)
    return MarriageRecords(archive, fund, inventory, case, village, church, year, list(records),
                           reviewed=reviewed, civil=civil)


def marriage_month(month: Month | None, *records: Marriage) -> list[Marriage]:
    """Helper to group marriages by month. Pass None for unknown month."""

    def copy_with_month(record: Marriage) -> Marriage:
        r = copy.deepcopy(record)
        if r.w_month is None and month is not None:
            r.w_month = month
        else:
            shadow(r, "w_month", month)        # the record writes its own: the section's is kept beside it
        return r

    return [copy_with_month(record) for record in records]


def marriage_month_year(month: Month | None, year: int | None, *records: Marriage) -> list[Marriage]:
    """Helper to group marriages by month and year."""

    def copy_with_month(record: Marriage) -> Marriage:
        r = copy.deepcopy(record)
        if r.w_month is None and month is not None:
            r.w_month = month
        else:
            shadow(r, "w_month", month)        # the record writes its own: the section's is kept beside it
        if year is not None and r.year is None:
            r.year = year
        else:
            shadow(r, "year", year)
        return r

    return [copy_with_month(record) for record in records]
