"""The DSL calls that ARE a record: a row of Verso's review table each, and the unit
the review ratchet fingerprints (`verso.core.ratchet`).

One list since 0.1.0: the ratchet and Verso's signatures (`verso.ru.dsl.signatures`)
each spelled it, and two copies of a list drift. Since 0.1.0 the ratchet reads them as the
plugin's dialect, `CALLS`, which also says what numbers each, its sex and the roll's words
to Verso alone — the ratchet's `_NUMBER_PARAM`, `_GENDER`, `_KIND_OF` and `_READING_FLAGS`,
verbatim. It imports only the core's ratchet, which is standard library only.
"""
from __future__ import annotations

from verso.core.ratchet import CallDialect, RecordCall

CALLS = CallDialect(
    calls={"birth": RecordCall("Birth", sexed=True), "christening": RecordCall("Christening", sexed=True),
           "marriage": RecordCall("Marriage"), "death": RecordCall("Death", sexed=True),
           "household": RecordCall("CensusHousehold", number="family_id"),
           "listed_person": RecordCall("ListedPerson", number="number")},
    page_label="л.",                          # i18n: content — the citation's own word for a leaf
    sexes={"MALE": "м", "FEMALE": "ж"},       # i18n: content — the citation's sex marks
    # A roll's word on how Verso reads it (`census_records(female_previous_age=)`):
    # the translator does not read it, so setting it changes no record.
    reading_flags=frozenset({"female_previous_age"}),
)

# The calls that are a record, by name: Verso's rows, the describe catalog's record functions.
RECORD_FUNCS = frozenset(CALLS.calls)
