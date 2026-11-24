"""One translation of a village, read twice: its assertions and the bridge to its canonicals.

Moved verbatim out of `verso.ru.cli.facts` before 0.1.0: the consolidation channels, the familio
generator and Verso's people index read the facts layer through these, and a library
does not import its CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.divorces import facts_from_divorces
from verso.ru.facts.extract.external_sources import facts_from_external_sources
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.extract.name_lists import facts_from_name_lists
from verso.ru.facts.model import Assertion, AssertionSet
from verso.core.records.ids import RecordIds


def consolidated_facts(village_dir: Path, *,
                       strict: bool = False) -> tuple[AssertionSet, Any, Any]:
    """Every assertion of a village, read from the SAME objects the translation
    read, plus the bridge from an appearance to its consolidated profile.

    One discovery, two readers. A second `discover_records` would build a second
    set of `Person` objects — equal to the first and not identical — and the
    join key is identity, so the two readers must share one walk.

    `strict` fails when a DSL file did not import, as the familio generator
    asks — its records, and any kin among them, would otherwise be missing.

    Each persona is named by its records-JSON id (rule r1), counted in the
    same walk: the village's files as the records export reads them.

    The record sets the translator does not read — a divorce — come from that
    walk too, beside the ones it was fed: their people have no profile, so the
    bridge places none of them, and what they assert is read all the same.
    """
    from verso.ru.pipeline.translate import translate_village
    from verso.ru.facts.extract.common import SlotIndex

    ids = RecordIds()
    beside: list[tuple[str, Any]] = []
    gen, _ = translate_village(village_dir, strict=strict, ids=ids, untranslated=beside)
    slots = SlotIndex()
    assertions = assertions_of([*gen.fed_sources, *beside], village=village_dir.name, slots=slots, ids=ids)
    return AssertionSet(assertions), gen, slots


def unpublished_kinds() -> frozenset[str]:
    """The kinds of record the translator does not read, by their code (`RecordKind.code`) — a divorce:
    an appearance in one has no profile, and the bridge to the canonicals counts it apart."""
    from verso.core import plugins

    return frozenset(kind.code for kind in plugins.dsl().kinds if not kind.translated)


def assertions_of(sources: Any, *, village: str, slots: Any,
                  drafts: bool = False, ids: RecordIds | None = None) -> list[Assertion]:
    """What the record sets of `sources` — (source file, record set) pairs —
    assert, each extractor given the sets of its kind: a metric book's records
    one by one, each dated by its book (`_dated`), and a roll, a list or a file
    of cards whole. `drafts` is the extractors' own (`extract.common.reviewed`);
    `ids` names every record (`RecordIds`, walked over the files of `sources`
    beforehand) — without it an entry is numbered by its place in this reading."""
    from verso.ru.dsl.records.births import BirthRecords
    from verso.ru.dsl.records.census import CensusRecords
    from verso.ru.dsl.records.deaths import DeathRecords
    from verso.ru.dsl.records.divorces import DivorceRecords
    from verso.ru.dsl.records.external_sources import ExternalSourceRecords
    from verso.ru.dsl.records.marriages import MarriageRecords
    from verso.ru.dsl.records.name_lists import NameListRecords

    pairs = list(sources)
    assertions: list[Assertion] = []
    for wanted, extract in ((BirthRecords, facts_from_births),
                            (MarriageRecords, facts_from_marriages),
                            (DeathRecords, facts_from_deaths),
                            (DivorceRecords, facts_from_divorces)):
        items = [(r, name) for name, recs in pairs
                 if isinstance(recs, wanted)
                 for r in _dated(cast(Any, recs))]
        assertions += list(extract(items, village=village, slots=slots, drafts=drafts, ids=ids))
    for wanted_book, extract_book in ((CensusRecords, facts_from_census),
                                      (NameListRecords, facts_from_name_lists),
                                      (ExternalSourceRecords, facts_from_external_sources)):
        books = [(recs, name) for name, recs in pairs
                 if isinstance(recs, wanted_book)]
        assertions += list(extract_book(books, village=village, slots=slots, drafts=drafts, ids=ids))
    return assertions


def _dated(records: Any) -> list[Any]:
    """The records of one book, each dated by its container when it omits the
    year — the same contract `_iter_records` applies."""
    out = []
    for r in records.records:
        if r.year is None:
            r.year = records.year
        out.append(r)
    return out
