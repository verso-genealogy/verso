"""The landlords' statuses are the corpus's (corpus/statuses.py). Since 0.1.0 the library
reads them through the workspace — `statuses.catalog()` — in the very place they stood, so
every reader sees the catalog it saw; the module itself holds the library's own alone."""
from __future__ import annotations

import corpus.statuses
from verso.ru.domain import statuses
from verso.ru.domain.status import Status
from verso.ru.linters.checks import parent_status
from verso.ru.dsl import describe


def _catalog() -> list[str]:
    return list(statuses.catalog())


def test_the_corpus_block_stands_where_it_stood() -> None:
    names = _catalog()
    start = names.index(corpus.statuses.__all__[0])
    assert names[start - 1] == "BUDNY_PEASANT"
    assert names[start:start + len(corpus.statuses.__all__)] == list(corpus.statuses.__all__)
    assert names[start + len(corpus.statuses.__all__)] == "LANDLORD"
    assert (len(names), len(corpus.statuses.__all__)) == (162, 53)   # the synthetic corpus


def test_a_corpus_constant_is_the_corpus_s_object_and_not_the_library_s() -> None:
    assert statuses.catalog()["GOLOVLEV_PEASANT"] is corpus.statuses.GOLOVLEV_PEASANT
    assert not hasattr(statuses, "GOLOVLEV_PEASANT")
    own = [n for n, v in vars(statuses).items() if n.isupper() and isinstance(v, Status)]
    assert len(own) == 109 and not set(own) & set(corpus.statuses.__all__)


def test_the_corpus_aliases_reach_both_readers() -> None:
    assert statuses.child_status_for("приказчик вотчины гг. Головлевых", None) is None
    assert parent_status.estate_aliases()["GOLOVLEV_STEWARD"] == "GOLOVLEV_PEASANT"
    assert parent_status.estate_aliases()["POPADIA"] == "PRIEST"


def test_verso_writes_a_corpus_status_from_the_corpus() -> None:
    # DSL v1: `from corpus.statuses import …`.
    golovlev = next(c for c in describe.catalogs()["status"] if c.code == "GOLOVLEV_PEASANT")
    assert golovlev.module == "corpus.statuses"
