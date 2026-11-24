"""The Russian books' DSL as the core reads a village through it: the record kinds, the
globs of the files and the order of the books (the plugin, `verso.ru.plugin`, assembles them
with the calls and the records' vocabulary into its `Dsl`).

`SOURCE_PATTERNS`, `_CATEGORY_ORDER`, `_categorize` and `_within_category_key` moved here
verbatim from `verso.core.pipeline.load`: the order of the walk is the contract of the
generated terraform tree (`discover_records` feeds the translator in it).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from verso.core.plugins import RecordKind
from verso.ru.dsl.records.births import Birth, BirthRecords, Christening
from verso.ru.dsl.records.census import CensusHousehold, CensusRecords
from verso.ru.dsl.records.deaths import Death, DeathRecords
from verso.ru.dsl.records.divorces import Divorce, DivorceRecords
from verso.ru.dsl.records.external_sources import ExternalSourceRecord, ExternalSourceRecords
from verso.ru.dsl.records.marriages import Marriage, MarriageRecords
from verso.ru.dsl.records.name_lists import ListedPerson, NameListRecords

if TYPE_CHECKING:
    from verso.core.corpus_data import Village
    from verso.ru.corpus_data import Census

# Globs of the DSL files that feed village.db (`verso.ru.cli.all_persons`), in insertion order. Shared with
# `verso.ru.cli.find_person`, which uses them to detect a STALE index: deriving the
# staleness check from a second, hand-copied list is exactly how the two drift
# apart the next time a record family is added (external_sources and name_lists
# were both once missing from lists like this).
SOURCE_PATTERNS: tuple[str, ...] = (
    "*/*_births_*.py",
    "*/*_marriages_*.py",
    "*/*_deaths_*.py",
    "*/*_divorces_*.py",
    "*/*_census_*.py",
    # An исповедная роспись IS a census (`CONFESSION_LIST`); the separate glob
    # exists because the filename is the only place the source kind is stated.
    "*/*_confessions_*.py",
    "*/*_external_*.py",
    "*/*_name_lists_*.py",
)


# The kinds, in the order the translator read them (0.1.0's RECORD_TYPES), then the divorce,
# which the translator does not read: it reaches its CSV, the records JSON and the facts layer.
KINDS: tuple[RecordKind, ...] = (
    RecordKind("birth", BirthRecords, (Birth, Christening), "records"),
    RecordKind("marriage", MarriageRecords, (Marriage,), "records"),
    RecordKind("death", DeathRecords, (Death,), "records"),
    RecordKind("household", CensusRecords, (CensusHousehold,), "households"),
    RecordKind("card", ExternalSourceRecords, (ExternalSourceRecord,), "records", ratcheted=False),
    RecordKind("listed", NameListRecords, (ListedPerson,), "entries"),
    RecordKind("divorce", DivorceRecords, (Divorce,), "records", translated=False, ratcheted=False),
)


# Legacy iteration order: village MK → other-parish MK → census, with the
# census files in the order the village's village.toml lists (`[census] order`,
# the exact non-chronological order the legacy generator hardcoded). Used by `discover_records` so
# the translator's `add_to_consolidated_unions` calls happen in the same
# sequence — that determines the position of each consolidated union in
# `consolidated_unions.tf` and matches legacy byte-for-byte.
_CATEGORY_ORDER: tuple[tuple[str, bool], ...] = (
    ("births", False),
    ("marriages", False),
    ("deaths", False),
    ("births", True),
    ("marriages", True),
    ("deaths", True),
    ("census", False),
    ("external", False),
    ("name_list", False),
)

def _categorize(dsl_path: Path, records: object) -> tuple[str, bool]:
    """Return `(category, is_other_parish)` tuple matching `_CATEGORY_ORDER`.

    `is_other_parish` is True when the DSL filename starts with `other_`,
    which is how secondary-parish records (Неелово / Ябедные Пепелищи)
    are flagged in the DSL layout.
    """
    is_other = dsl_path.name.startswith("other_")
    if isinstance(records, BirthRecords):
        return ("births", is_other)
    if isinstance(records, MarriageRecords):
        return ("marriages", is_other)
    if isinstance(records, DeathRecords):
        return ("deaths", is_other)
    # Covers исповедные росписи too — an ИР is a CensusRecords carrying
    # `CONFESSION_LIST`, not a separate type.
    if isinstance(records, CensusRecords):
        return ("census", False)
    if isinstance(records, ExternalSourceRecords):
        return ("external", False)
    if isinstance(records, NameListRecords):
        return ("name_list", False)
    return ("other", is_other)


def _within_category_key(
    cat: tuple[str, bool], dsl_path: Path, records: object,
    census_order: tuple[tuple[int, str | None], ...] = (),
) -> tuple[int, ...] | tuple[int, str]:
    """Sort key inside a single category bucket.

    - Census records follow the village's `[census] order` (village.toml): a
      (year, archive_suffix) it lists sorts by its place there, any other after
      the list, by year — so a newly-added roll lands at the end.
    - All other categories sort chronologically by year, with filename as
      tie-breaker (matches legacy CSV row order, since the source CSVs were
      year-sorted).
    """
    if cat == ("census", False):
        year = getattr(records, "year", None)
        suffix = getattr(records, "archive_suffix", None)
        try:
            idx = census_order.index((year, suffix))
        except ValueError:
            idx = len(census_order) + (year or 0)
        return (idx,)
    year = getattr(records, "year", None) or int(dsl_path.parent.name)
    return (year, dsl_path.name)


def order(path: Path, records: Any, village: Village) -> tuple[Any, ...]:
    """A record set's place among its village's: its category's, then its place inside it."""
    cat = _categorize(path, records)
    cat_order = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    census: Census | None = village.table("census")         # the plugin's [census]
    census_order = census.order if census is not None else ()
    return (cat_order.get(cat, len(cat_order)), _within_category_key(cat, path, records, census_order))

