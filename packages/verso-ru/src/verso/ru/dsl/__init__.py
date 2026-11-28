"""DSL v1: what a DSL file imports — the records' functions, their types and enums.

    from verso.ru.dsl import birth, birth_records, page, person, Gender, Month
    from verso.ru.dsl.statuses import PEASANT_MALE
    from corpus.statuses import MANILOV_LK_PEASANT_MALE

The constants are catalogs of their own, submodules of the facade: `verso.ru.dsl.statuses`
(the library's), `verso.ru.dsl.causes_of_death`, `verso.ru.dsl.marital_status` — `WIDOW` is a
status and a marital status, two constants that one namespace could not hold. A corpus's own
statuses are its `corpus.statuses`.

`DSL_API` versions this surface: `api-v1.json` holds it, `verso.ru.dsl.surface` writes it and
checks that it only grows (`verso dsl-surface --check`). A name, a parameter with a default added, or a parameter that gains a default keeps
DSL v1; one removed or renamed, a default, a kind, the order of the positionals or a constant's
value changed is DSL v2.

The facade is a corpus's: the library takes a name from the module that defines it, and
imports a submodule of this package as any other (`import verso.ru.dsl.kinds`).
"""

from calendar import Month

from verso.ru.domain import NOT_IN_DOCUMENT, EventDate, Gender, RecordDefaults, Side, Status, book, page, person
from verso.ru.dsl.records.births import birth, birth_month, birth_month_year, birth_records, christening
from verso.ru.dsl.records.census import CONFESSION_LIST, CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_month, death_month_year, death_records
from verso.ru.dsl.records.divorces import divorce, divorce_month, divorce_records
from verso.ru.dsl.records.external_sources import (WwiDocumentType, WwiiDocumentType, criminal_record,
                                                   external_source_records, wwi_record, wwii_record)
from verso.ru.dsl.records.marriages import marriage, marriage_month, marriage_month_year, marriage_records
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.relationship import Relationship, relative

DSL_API = 1

__all__ = [
    "CONFESSION_LIST", "NOT_IN_DOCUMENT", "CensusRole", "EventDate", "Gender", "Month", "RecordDefaults",
    "Relationship", "Side", "Status", "WwiDocumentType", "WwiiDocumentType", "birth", "birth_month",
    "birth_month_year", "birth_records", "book", "census_records", "christening", "criminal_record",
    "death", "death_month", "death_month_year", "death_records", "divorce", "divorce_month",
    "divorce_records", "external_source_records", "household", "listed_person", "marriage",
    "marriage_month", "marriage_month_year", "marriage_records", "member", "name_list_records", "page",
    "person", "relative", "wwi_record", "wwii_record",
]
