"""The places of a records-v1 file's records, for the tests of one record rebuilt or linted alone.

`located(data)` walks the export as a store would hold it: each record node with its set's header, its leaf, its
`Position`, the record the book built for it and what the rest of its page run shows RVR001. The running number
before a двор is what the book's own members end on.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, NamedTuple

from verso.core.records.fields import vocabulary
from verso.core.records.replay import Position, replay_file
from verso.ru.linters.on_json import FileView, review_level


class Located(NamedTuple):
    header: dict[str, Any]
    page: str | None
    node: dict[str, Any]
    position: Position
    built: Any
    run_levels: frozenset[bool]


def located(data: Mapping[str, Any], whole: Mapping[str, object] | None = None) -> Iterator[Located]:
    """Every record of the file, in the order of the export. An aliased set holds the records of another."""
    voc = vocabulary()
    whole = replay_file(data, context=False) if whole is None else whole
    for doc in data["documents"]:
        if "alias_of" in doc:
            continue
        built = whole[doc["variable"]]
        attr = voc.specs[type(built)].records_attr
        assert attr is not None
        in_book = list(getattr(built, attr))
        header = {k: v for k, v in doc.items() if k != "pages"}
        k = counter = 0
        for run in doc["pages"]:
            first = k
            for record in run["records"]:
                position = Position(k, counter)
                for m in getattr(in_book[k], "members", ()):
                    if not m.is_hidden() and isinstance(m.record_number, int):
                        counter = m.record_number
                k += 1
                yield Located(header, run["page"], record, position, in_book[k - 1],
                              frozenset(review_level(other, in_book[first + i]) for i, other in enumerate(run["records"])
                                        if other is not record and "reviewed" not in FileView.written(other["kind"], other)))
