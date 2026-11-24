from __future__ import annotations

import copy
from calendar import Month
from typing import TYPE_CHECKING

import warnings

from verso.ru.domain import EventDate, Person, Gender, RecordDefaults
from verso.ru.dsl.records.reviewed import resolve_reviewed
from verso.ru.naming import get_gender_from_name
from verso.core.written import captures_written, shadow

if TYPE_CHECKING:
    from verso.ru.exporters.base import RecordsExporter


class Divorce:
    def __init__(
            self,
            record_num: int,
            d_day: int | None = None,
            d_month: Month | None = None,
            husband: Person | None = None,
            wife: Person | None = None,
            husband_age: int | None = None,
            wife_age: int | None = None,
            marriage_date: EventDate | str | None = None,
            children: str | None = None,
            initiator: str | None = None,
            page: str | None = None,
            case: str | None = None,
            comment: str | None = None,
            year: int | None = None,
            reviewed: bool | None = None,
            source_date_error: str | None = None,
            calendar_note: str | None = None,
    ):
        self.record_num = record_num
        # `None` is «not stated»: `page()` and then the record set fill it,
        # so a whole лист can be held (`verso.ru.dsl.records.reviewed`).
        self.reviewed = reviewed
        self.d_day = d_day
        self.d_month = d_month
        self.husband = husband
        self.wife = wife
        self.husband_age = husband_age
        self.wife_age = wife_age
        self.marriage_date = marriage_date
        self.children = children
        self.initiator = initiator
        self.page = page
        self.case = case
        self.comment = comment
        self.year = year
        # «Так в акте»: the marriage the act names is dated after the divorce itself — the author
        # has re-read the scan and withdraws that date (`verso.ru.facts.extract.divorces`).
        self.source_date_error = source_date_error
        # The day of the marriage the act names is RIGHT although the Church did not marry on it:
        # a note, not a retraction — `marriage(calendar_note=)`'s word for a wedding a later act names.
        self.calendar_note = calendar_note

        if self.husband and not self.husband.gender:
            self.husband.gender = get_gender_from_name(self.husband.name_modern) or Gender.MALE
        if self.wife and not self.wife.gender:
            self.wife.gender = get_gender_from_name(self.wife.name_modern) or Gender.FEMALE


class DivorceRecords:
    def __init__(
            self,
            archive: str,
            fund: str,
            inventory: str,
            case: str,
            village: str,
            church: str,
            year: int,
            records: list[Divorce],
            reviewed: bool = True,
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

    def export(self, exporter: RecordsExporter) -> str:
        return exporter.export(self)


@captures_written
def divorce(
        record_num: int,
        d_day: int | None = None,
        d_month: Month | None = None,
        husband: Person | None = None,
        wife: Person | None = None,
        husband_age: int | None = None,
        wife_age: int | None = None,
        marriage_date: EventDate | str | None = None,
        children: str | None = None,
        initiator: str | None = None,
        page: str | None = None,
        case: str | None = None,
        comment: str | None = None,
        year: int | None = None,
        reviewed: bool | None = None,
        source_date_error: str | None = None,
        calendar_note: str | None = None,
) -> Divorce:
    if isinstance(marriage_date, str):
        # DSL v1 wrote the marriage as the act's text; the library reads a date as an `EventDate` only. The text is
        # kept and exported as written, no reader parses it, and it goes in 0.2. `stacklevel` reaches past
        # `captures_written` to the line of the DSL file.
        from verso.ru.messages import t
        warnings.warn(str(t("dsl.divorce.marriage_date_text", text=marriage_date)), DeprecationWarning, stacklevel=3)
    return Divorce(
        record_num,
        d_day,
        d_month,
        husband,
        wife,
        husband_age,
        wife_age,
        marriage_date,
        children,
        initiator,
        page=page,
        case=case,
        comment=comment,
        year=year,
        reviewed=reviewed,
        source_date_error=source_date_error,
        calendar_note=calendar_note,
    )


@captures_written
def divorce_records(
        archive: str,
        fund: str,
        inventory: str,
        case: str,
        village: str,
        church: str,
        year: int,
        *records: Divorce,
        defaults: RecordDefaults | None = None,
        reviewed: bool = True,
) -> DivorceRecords:
    if defaults is not None:
        for record in records:
            if record.husband and not record.husband.residence and defaults.residence:
                record.husband.residence = defaults.residence
            if record.wife and not record.wife.residence and defaults.residence:
                record.wife.residence = defaults.residence
    return DivorceRecords(archive, fund, inventory, case, village, church, year, list(records),
                          reviewed=reviewed)


def divorce_month(month: Month, *records: Divorce) -> list[Divorce]:
    def copy_with_month(record: Divorce) -> Divorce:
        r = copy.deepcopy(record)
        if r.d_month is None:
            r.d_month = month
        else:
            shadow(r, "d_month", month)        # the record writes its own: the section's is kept beside it
        return r

    return [copy_with_month(record) for record in records]
