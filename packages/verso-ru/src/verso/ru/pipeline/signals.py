"""The signals of one record of a records-v1 file: the record built alone, then asked.

A hosted store holds one record per row and no DSL. Its card asks the checks of
`verso.ru.facts.signals` of one node: the record is rebuilt from what the node
wrote, as its set's own factory builds it (`replay_alone` — the book's
defaults, its year, its section's month), and the rebuilt record is asked. The
way `verso.ru.linters.on_json.lint_record` reads one record, for the checks of
the facts layer.
"""
from __future__ import annotations

import contextlib
from collections.abc import Collection, Mapping
from functools import cache
from pathlib import Path
from typing import Any

from verso.core import workspace as workspaces
from verso.core.records import FormatError
from verso.core.records.replay import Position, replay_alone
from verso.core.workspace import WorkspaceError
from verso.ru.church_calendar.svyatcy import Svyatcy, load_svyatcy
from verso.ru.domain import statuses
from verso.ru.facts.signals import CHECKS, Signals, asked, signals_of
from verso.ru.linters.on_json.walk import names_table_present

__all__ = ["signals_on_json", "svyatcy_cached"]

#: The check that reads a name through the workspace's names table.
_NEEDS_NAMES = "name-days"


@cache
def svyatcy_cached() -> Svyatcy:
    """The package's святцы, read once for the process: the table is data of the package and does not change,
    and a card cannot afford the read (a thousand names) on every record."""
    return load_svyatcy()


def signals_on_json(node: Mapping[str, Any], *, header: Mapping[str, Any], page: str | None, position: Position,
                    checks: Collection[str] = CHECKS, workspace: Path | None = None) -> Signals:
    """The signals of one record of a records-v1 file, as `signals_of` gives them of the record its node builds.

    `node` is the record's node, `header` its record set's node (with or without its `pages`), `page` the leaf it
    stands on and `position` its place in the set — what `lint_record` takes. Every signal is addressed to the node's
    id. The record is read whether it is reviewed or not.

    A card must open whatever its record holds, so nothing here refuses: a record the factories cannot build, or a
    workspace with no names table to build its people from, leaves every check asked `unanswered`; a workspace whose
    table is absent while the record still builds leaves `name-days` so. A name `checks` does not know is the
    caller's mistake (`ValueError`; a text given for the collection, `TypeError`).

    `workspace` is the one whose tables are read (`None`: the current one). Not thread-safe, as `lint_record` is
    not: the workspace is a process-global stack."""
    wanted = asked(checks)
    with workspaces.use(workspace) if workspace is not None else contextlib.nullcontext(), statuses.held():
        try:
            built, record = replay_alone(node, header=header, page=page, position=position, context=False)
        except FormatError:
            return Signals((), tuple(wanted))
        except WorkspaceError:
            if names_table_present():
                raise
            return Signals((), tuple(wanted))
        named = names_table_present()
        got = signals_of(record, record_id=str(node["id"]), book_year=getattr(built, "year", None),
                         checks=[c for c in wanted if named or c != _NEEDS_NAMES], svyatcy=svyatcy_cached())
        unanswered = {*got.unanswered, *(() if named else {_NEEDS_NAMES} & set(wanted))}
        return Signals(got.found, tuple(c for c in wanted if c in unanswered))
