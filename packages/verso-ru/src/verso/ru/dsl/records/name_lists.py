"""Generic archival name-list («Именной список») DSL record family.

A flat roster of residents from a single dated archival document (e.g. the 1917
«Списки избирателей на выборах в Учредительное собрание»). Each `listed_person`
mints a deliberate-duplicate `geni_profile` (circa birth = list year − age) and
all entries share one proof `geni_document`. The specific source is named only
via `document_type` — there is no source-specific vocabulary here.

`age` is the only demographic and is **optional**; when present the birth year is
computed (`year − age`), when absent the profile carries no birth event.
"""
from __future__ import annotations

from verso.ru.domain import Person
from verso.ru.naming import get_gender_from_name
from verso.core.written import captures_written


def _age_to_int(age) -> int | None:
    """Return a positive int age, or None for unknown/non-numeric ('?')."""
    if isinstance(age, bool):  # guard: bool is an int subclass
        return None
    if isinstance(age, int):
        return age if age > 0 else None
    try:
        v = int(str(age).strip())
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


class ListedPerson:
    def __init__(self, number: int, person: Person, *, age=None,
                 comment: str | None = None, reviewed: bool | None = None,
                 page: str | None = None):
        self.number = number
        self.person = person
        self.age = age
        self.comment = comment
        # `None` means "not stated here" — `NameListRecords` resolves it to the
        # file-level `name_list_records(reviewed=…)` default, mirroring the
        # census `household()` / `census_records()` pair.
        self.reviewed = reviewed
        # Archival лист this entry was read from. Set by the `page()` wrapper
        # (`verso.ru.domain.factories.page`), or explicitly for a one-off.
        self.page = page
        # 1-based positional index, assigned by name_list_records().
        self.index: int | None = None

    def age_years(self) -> int | None:
        return _age_to_int(self.age)

    def birth_year(self, list_year: int) -> int | None:
        years = self.age_years()
        return list_year - years if years is not None else None


@captures_written
def listed_person(number: int, person: Person, *, age=None,
                  comment: str | None = None,
                  reviewed: bool | None = None,
                  page: str | None = None) -> ListedPerson:
    """One entry in a name list: its № (`number`) and the `person`. `age`
    (optional — the only demographic) drives the computed birth year (list year
    − age); when absent the profile carries no birth event. `comment` carries
    annotations (e.g. an age/год discrepancy or a maiden-name note). `reviewed`
    left unset defers to `name_list_records(reviewed=…)`. `page` is normally set
    by wrapping entries in `page("11", …)` rather than passed here."""
    return ListedPerson(number, person, age=age, comment=comment,
                        reviewed=reviewed, page=page)


class NameListRecords:
    def __init__(self, archive: str, fund: str, inventory: str, case: str,
                 village: str, year: int, document_type: str,
                 entries: list[ListedPerson], *,
                 document_type_genitive: str | None = None,
                 district: str | None = None, volost: str | None = None,
                 record_day: int | None = None, record_month: int | None = None,
                 scan_file: str | None = None, source_url: str | None = None,
                 labels: list[str] | None = None, reviewed: bool = True,
                 household_order: bool = False):
        self.archive = archive
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.village = village
        self.year = year
        self.document_type = document_type
        self.document_type_genitive = document_type_genitive
        self.district = district
        self.volost = volost
        self.record_day = record_day
        self.record_month = record_month
        self.scan_file = scan_file
        self.source_url = source_url
        self.labels = labels if labels is not None else ["Other"]
        # File-level default for the per-entry `reviewed` flag. An unreviewed
        # entry emits no profile and no roster line, so a half-read лист cannot
        # reach Geni — same contract as `census_records(reviewed=…)`.
        self.reviewed = reviewed
        # The list runs household by household — a family written together
        # (husband, wife, the sons and their wives), as the 1917 lists of
        # Горюхино and Заманиловка are; Маниловка's is sorted by given name within
        # each surname. Only then is the entry beside another one evidence of
        # their kinship, which is what `verso reconcile` reads it for. A fact
        # about the source, stated by whoever read it; the translator ignores it.
        self.household_order = household_order
        self.entries = list(entries)
        for i, e in enumerate(self.entries, start=1):
            e.index = i
            if e.reviewed is None:
                e.reviewed = reviewed
            if not e.person.residence:
                e.person.residence = village
            if e.person.gender is None:
                e.person.gender = get_gender_from_name(e.person.name_modern)


@captures_written
def name_list_records(archive: str, fund: str, inventory: str, case: str,
                      village: str, year: int, *entries: ListedPerson,
                      document_type: str,
                      document_type_genitive: str | None = None,
                      district: str | None = None, volost: str | None = None,
                      record_day: int | None = None,
                      record_month: int | None = None,
                      scan_file: str | None = None,
                      source_url: str | None = None,
                      labels: list[str] | None = None,
                      reviewed: bool = True,
                      household_order: bool = False) -> NameListRecords:
    """Collect a village's name-list entries (one DSL file = one archival list).

    `document_type` (required) names the specific source verbatim, e.g.
    «Список избирателей на выборах в Учредительное собрание». Provenance fields
    (`archive`/`fund`/`inventory`/`case`, `district`/`volost`) mirror
    `census_records`. `scan_file` optionally re-hosts the list page image.
    `reviewed` is the file-level default for entries that do not state their
    own; hold a whole list (or, via `page(…, reviewed=False)`, a whole лист)
    back while any reading is still open. `household_order=True` states that
    the list runs household by household (see `NameListRecords`); leave it
    unset for a list in any other order — alphabetical, by street — or one
    whose order nobody has looked at."""
    return NameListRecords(
        archive, fund, inventory, case, village, year, document_type,
        list(entries),
        document_type_genitive=document_type_genitive,
        district=district, volost=volost,
        record_day=record_day, record_month=record_month,
        scan_file=scan_file, source_url=source_url, labels=labels,
        reviewed=reviewed, household_order=household_order,
    )
