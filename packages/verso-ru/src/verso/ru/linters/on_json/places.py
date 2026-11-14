"""The rules that read the corpus's places (class `context`, needs `places`)."""
from __future__ import annotations

import contextlib
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from verso.core import places as corpus_places
from verso.core import workspace as workspaces
from verso.ru.linters.on_json.walk import FileView, Finding, Rule, finding

__all__ = ["RULES", "file_in_scope"]

# The record sets whose parish and default residence ULC001 reads (its `_RECORD_CALLS`).
_PARISH_SETS = frozenset({"births", "deaths", "marriages", "census"})


def file_in_scope(headers: Sequence[Mapping[str, Any]], *, workspace: Path | None = None) -> bool:
    """Whether a file is in ULC001's scope: some record set of it names a parish the corpus's places know
    (`unmapped_location._file_in_scope`). `headers` are the file's set nodes, with or without their pages; `workspace`
    is the one whose places are read (`None`: the current one)."""
    with workspaces.use(workspace) if workspace is not None else contextlib.nullcontext():
        known = corpus_places.current().bodies
        return any(doc.get("kind") in _PARISH_SETS and doc.get("written", {}).get("village") in known
                   for doc in headers)


def ulc001(view: FileView) -> Iterator[Finding]:
    """A place the corpus's places do not hold (`unmapped_location`), where the file's parish is one
    they hold."""
    known = corpus_places.current().bodies
    books = [doc for doc in view.documents() if doc.get("kind") in _PARISH_SETS]
    if not (view.file_scope if view.file_scope is not None else file_in_scope(books)):
        return

    def unknown(value: object) -> bool:
        return isinstance(value, str) and bool(value) and value not in known

    for doc in books:
        village = doc["written"].get("village")
        if unknown(village):
            yield finding("ULC001", "parish_village", doc["id"], token=village, place=village)
        residence = (doc["written"].get("defaults") or {}).get("residence")
        if unknown(residence):
            yield finding("ULC001", "default_residence", doc["id"], token=residence, place=residence)
    for _, record in view.records():
        for persona in record["persons"]:
            residence = view.written("person", persona).get("residence")
            if unknown(residence):
                yield finding("ULC001", "residence", record["id"], token=residence, place=residence)
            link = view.written("member", persona["link"]) if "link" in persona and persona.get("role") == "member" else {}
            for kwarg in ("origin", "destination"):
                if unknown(link.get(kwarg)):
                    yield finding("ULC001", kwarg, record["id"], token=link[kwarg], place=link[kwarg])


RULES: dict[str, Rule] = {"ULC001": ulc001}
