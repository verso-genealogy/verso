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
from verso.ru.church_calendar.svyatcy import Commemorated, Svyatcy, read_rows
from verso.ru.domain import statuses
from verso.ru.facts.signals import CHECKS, Signals, asked, signals_of
from verso.ru.linters.on_json.walk import names_table_present
from verso.ru.naming.names_registry import current_lexicon

__all__ = ["signals_on_json", "svyatcy_cached"]

#: The check that reads a name through the workspace's names table.
_NEEDS_NAMES = "name-days"


@cache
def _rows() -> tuple[Commemorated, ...]:
    """The package's святцы as rows, read once for the process: data of the package, the same for every workspace."""
    return tuple(read_rows())


#: The tables built lately, by the lexicon each was indexed through (held, so its identity is not reused).
_tables: dict[int, tuple[object, Svyatcy]] = {}
#: How many are kept: a server holds a project a workspace, and each has a lexicon of its own.
_KEPT = 16


def svyatcy_cached() -> Svyatcy:
    """The святцы for the CURRENT workspace, built once per names lexicon. The rows are the package's and never
    change, but the table's index is read through the workspace's lexicon (a people's form is kept under its saint
    only where the lexicon ties them), so a table built for one project answers wrongly for another, and a card
    cannot afford the build (a thousand names) on every record. A workspace with no names table has no lexicon
    (`LexiconNotConfigured`): ask only where there is one."""
    lexicon = current_lexicon()
    kept = _tables.get(id(lexicon))
    if kept is None or kept[0] is not lexicon:
        while len(_tables) >= _KEPT:
            del _tables[next(iter(_tables))]
        kept = _tables[id(lexicon)] = (lexicon, Svyatcy(_rows()))
    return kept[1]


def signals_on_json(node: Mapping[str, Any], *, header: Mapping[str, Any], page: str | None, position: Position,
                    checks: Collection[str] = CHECKS, workspace: Path | None = None) -> Signals:
    """The signals of one record of a records-v1 file, as `signals_of` gives them of the record its node builds.

    `node` is the record's node, `header` its record set's node (with or without its `pages`), `page` the leaf it
    stands on and `position` its place in the set — what `lint_record` takes. Every signal is addressed to the node's
    id. The record is read whether it is reviewed or not.

    A card must open whatever its record holds, so nothing here refuses: a record the factories cannot build, or a
    workspace with no names table to build its people from, leaves every check asked `unanswered`; a workspace whose
    table is absent while the record still builds leaves `name-days` so (and the святцы are not asked for). A node
    with no `id` is answered, its signals addressed to "". A name `checks` does not know is the
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
        ask = [c for c in wanted if c != _NEEDS_NAMES or names_table_present()]
        got = signals_of(record, record_id=str(node.get("id", "")), book_year=getattr(built, "year", None), checks=ask,
                         svyatcy=svyatcy_cached() if _NEEDS_NAMES in ask else None)
        unanswered = {*got.unanswered, *(set(wanted) - set(ask))}
        return Signals(got.found, tuple(c for c in wanted if c in unanswered))
