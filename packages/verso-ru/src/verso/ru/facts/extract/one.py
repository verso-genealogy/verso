"""Which extractor reads ONE record, by what the record is.

A village is read set by set, each kind handed to its own extractor
(`verso.ru.pipeline.facts.assertions_of`). A record read alone — on its card —
has no set to say its kind, so the kind is asked of the record itself, here:
the only layer that may know a DSL class.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

from verso.ru.dsl.records.births import Birth
from verso.ru.dsl.records.deaths import Death
from verso.ru.dsl.records.divorces import Divorce
from verso.ru.dsl.records.marriages import Marriage
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.divorces import facts_from_divorces
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import Assertion

type Extract = Callable[..., Iterator[Assertion]]

#: The class of a record read one by one — a metric record, an act of divorce — → what reads its assertions.
_EXTRACTORS: tuple[tuple[type, Extract], ...] = (
    (Birth, facts_from_births), (Marriage, facts_from_marriages), (Death, facts_from_deaths),
    (Divorce, facts_from_divorces))


def extractor_of(record: object) -> Extract | None:
    """The extractor of a record read alone — a birth, a wedding, a death, a divorce — or None: a household, a card
    and a line of a list are read with their book around them, never alone."""
    return next((extract for cls, extract in _EXTRACTORS if isinstance(record, cls)), None)
