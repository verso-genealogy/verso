from __future__ import annotations

import copy
from calendar import Month
from typing import TYPE_CHECKING

from verso.ru.domain.person import Person
from verso.ru.domain.side import Side
from verso.ru.domain.status import Status
from verso.ru.gender import Gender
from verso.core.written import captures_written, shadow

if TYPE_CHECKING:
    from verso.ru.dsl.records.births import Birth
    from verso.ru.dsl.records.census import CensusHousehold
    from verso.ru.dsl.records.deaths import Death
    from verso.ru.dsl.records.divorces import Divorce
    from verso.ru.dsl.records.marriages import Marriage
    from verso.ru.dsl.records.name_lists import ListedPerson


def _set_clergy_status(p: Person | None, default_status: Status | str) -> Person | None:
    if p is None:
        return None
    p = copy.deepcopy(p)
    if p.status is None:
        p.status = default_status
    return p


@captures_written
def person(
        name_orig: str | None = None,
        patr_orig: str | None = None,
        last_name_orig: str | None = None,
        name_modern_orth: str | None = None,
        patr_old: str | None = None,
        last_name_modern_orth: str | None = None,
        residence: str | None = None,
        status: Status | str | None = None,
        gender: Gender | None = None,
        side: Side | None = None,
        comment: str | None = None,
        last_name_in_book: bool = True,
        birth_last_name_modern_orth: str | None = None,
        occupation: str | None = None,
) -> Person:
    return Person(name_orig,
                  patr_orig,
                  last_name_orig,
                  name_modern_orth,
                  patr_old,
                  last_name_modern_orth,
                  residence,
                  status,
                  gender=gender,
                  comment=comment,
                  last_name_in_book=last_name_in_book,
                  birth_last_name_modern_orth=birth_last_name_modern_orth,
                  occupation=occupation,
                  side=side)


def page[T: (Birth, Divorce, Marriage, Death, CensusHousehold, ListedPerson)](num: str, *records: T, archive: str | None = None, fund: str | None = None, inventory: str | None = None, case: str | None = None, church: str | None = None, year: int | None = None, day: int | None = None, month: Month | None = None, reviewed: bool | None = None) -> list[T]:
    """Cat B1: `day=` and `month=` propagate the per-page "Дата записи"
    onto each wrapped record. For `CensusHousehold` these set the
    `record_day`/`record_month` fields the translator uses in res_name
    date segments (legacy 1816/1834 rs_* files have per-page dates in
    res_names; earlier years use `_00_00_`).

    `reviewed=` holds (or releases) a whole лист at once — the unit you
    actually check against a scan. It fills only a record's unset flag, so a
    per-record flag still wins. Every record type it wraps defaults to `None`
    since 2026-10-03; before that births, marriages and deaths defaulted to
    `True` and a `page(reviewed=False)` around them did nothing
    (`verso.ru.dsl.records.reviewed`). Every record type it wraps has the
    flag, a divorce too; the refusal below guards a record type added to the
    constraint without one, which is REFUSED rather than silently passed over.

    `ListedPerson` (name lists) carries only `page` and `reviewed` of these
    fields; the provenance kwargs live on `name_list_records()` instead, so
    every field access below is guarded rather than assumed."""
    def copy_with_page(record) -> T:
        r = copy.deepcopy(record)
        if r.page is None:
            r.page = num
        else:
            shadow(r, "page", num)       # the record writes its own leaf: the page's is kept beside it
        if case is not None and hasattr(r, 'case') and r.case is None:
            r.case = case
        if year is not None and hasattr(r, 'year') and r.year is None:
            r.year = year
        if archive is not None and hasattr(r, 'archive') and r.archive is None:
            r.archive = archive
        if fund is not None and hasattr(r, 'fund') and r.fund is None:
            r.fund = fund
        if inventory is not None and hasattr(r, 'inventory') and r.inventory is None:
            r.inventory = inventory
        if church is not None and hasattr(r, 'church') and r.church is None:
            r.church = church
        if day is not None and hasattr(r, 'record_day') and r.record_day is None:
            r.record_day = day
        if month is not None and hasattr(r, 'record_month') and r.record_month is None:
            r.record_month = month
        if reviewed is not None:
            if not hasattr(r, 'reviewed'):
                raise TypeError(f"page({num!r}, reviewed=…) cannot reach a "
                                f"{type(r).__name__}: it has no reviewed flag")
            if r.reviewed is None:
                r.reviewed = reviewed
        return r

    return [copy_with_page(record) for record in records]


def book[T: (Birth, Marriage, Death)](name: str, priest_person: Person, *records: T) -> list[T]:
    """Group records by metric book. Sets priest and book name on each record."""
    priest_copy = _set_clergy_status(copy.deepcopy(priest_person), "священник")  # i18n: content — the clergy's status the DSL writes

    def copy_with_book(record) -> T:
        r = copy.deepcopy(record)
        if r.priest is None:
            r.priest = copy.deepcopy(priest_copy)
        if r.book is None:
            r.book = name
        return r

    return [copy_with_book(record) for record in records]
