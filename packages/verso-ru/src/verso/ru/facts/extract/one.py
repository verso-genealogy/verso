"""Which extractor reads ONE record, by what the record is.

A village is read set by set, each kind handed to its own extractor
(`verso.ru.pipeline.facts.assertions_of`). A record read alone — on its card —
has no set to say its kind, so the kind is asked of the record itself, here:
the only layer that may know a DSL class.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

from verso.ru.dsl.records.births import Birth
from verso.ru.dsl.records.census import CensusHousehold
from verso.ru.dsl.records.deaths import Death
from verso.ru.dsl.records.divorces import Divorce
from verso.ru.dsl.records.marriages import Marriage
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.divorces import facts_from_divorces
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import Assertion

type Extract = Callable[..., Iterator[Assertion]]

#: The class of a record read one by one — a metric record, an act of divorce — → what reads its assertions.
_EXTRACTORS: tuple[tuple[type, Extract], ...] = (
    (Birth, facts_from_births), (Marriage, facts_from_marriages), (Death, facts_from_deaths),
    (Divorce, facts_from_divorces))


def is_household(record: object) -> bool:
    """Whether the record is a двор of a revision tale or a confession list."""
    return isinstance(record, CensusHousehold)


def extractor_of(record: object, *, record_set: object | None = None) -> Extract | None:
    """The extractor of a record read alone — a birth, a wedding, a death, a divorce — or None: a card and a line
    of a list are read with their book around them, never alone. A household is read as a roll of one household
    (the roll its `record_set` is): the facts are those the whole roll yields for it, its number and its entry
    in the roll's order included, so a citation reads the same either way. Without its roll a household has none."""
    if is_household(record):
        if record_set is None:
            return None

        def of_household(_items: object, **kwargs: object) -> Iterator[Assertion]:
            return facts_from_census([(record_set, "")], only=record, **kwargs)  # type: ignore[arg-type]
        return of_household
    return next((extract for cls, extract in _EXTRACTORS if isinstance(record, cls)), None)
