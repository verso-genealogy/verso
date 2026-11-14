"""Which exporter writes a record set's CSV: the table `verso export-csv` reads.

Until 0.1.0 each DSL file's `__main__` named its exporter; measured over the corpus, every one
named the exporter this table gives its record set's type — a familio CSV for the metric
books, the roll's own for a census, none for an external card or a name list.
"""
from __future__ import annotations

from verso.ru.dsl.records.births import BirthRecords
from verso.ru.dsl.records.census import CensusRecords
from verso.ru.dsl.records.deaths import DeathRecords
from verso.ru.dsl.records.divorces import DivorceRecords
from verso.ru.dsl.records.marriages import MarriageRecords
from verso.ru.exporters.base import RecordsExporter
from verso.ru.exporters.csv import CensusRecordsCsvExporter
from verso.ru.exporters.csv_familio import (BirthRecordsCsvFamilioExporter, DeathRecordsCsvFamilioExporter,
                                            DivorceRecordsCsvFamilioExporter, MarriageRecordsCsvFamilioExporter)

_EXPORTERS: dict[type, type[RecordsExporter]] = {
    BirthRecords: BirthRecordsCsvFamilioExporter,
    MarriageRecords: MarriageRecordsCsvFamilioExporter,
    DeathRecords: DeathRecordsCsvFamilioExporter,
    DivorceRecords: DivorceRecordsCsvFamilioExporter,
    CensusRecords: CensusRecordsCsvExporter,
}


def exporter_for(record_set: object) -> RecordsExporter | None:
    """The exporter of `record_set`'s CSV; None for a kind that writes none (an external
    source's cards, a name list) or for what is no record set."""
    exporter = _EXPORTERS.get(type(record_set))
    return exporter() if exporter is not None else None
