"""The linters on a file's records JSON, without its source.

`dsllint` reads the AST of a DSL file; a hosted Verso has records-v1 JSON and no file. This walk
answers a code as its check answers the source — the same code, variant and params — and
addresses the finding by the id (rule r1) of its record, or of its book for what the book writes,
instead of a line. A held record (`reviewed=False`) is linted like any other, as `dsllint` lints it.

The package is a registry: each family's module (`census`, `places`, …) holds the rules of its codes
in `RULES`, `lint_records` runs the ones asked for and gives each finding the level its code has in
`hosted.toml` (`refuse` is an error, `warn` a warning). A code that is the form of the source text
(class `source`) is refused as such, and a code no rule answers is refused by name, not skipped.

A hosted store holds one record per row, so a record is linted alone too: `lint_record` runs the same rules
over a view of one record and its set's header, `lint_header` over a set's header. Every finding of a file is
addressed to a record or to a set, so the findings of `lint_record` over its records and of `lint_header` over its
sets are those of `lint_records` — the corpus holds it (`tests/test_lint_record_corpus.py`).

The same codes and params, not always the same count: dsllint reads a call, the walk a persona. A
`person()` bound once and used in two records (a module-level name, a `book()`'s priest copied into
every record) is one finding there and one per record here; a residence written through a name, which
dsllint does not read, the walk sees evaluated. Neither occurs in the corpus today
(`tests/test_linters_on_json_corpus.py` holds the counts equal), and the walk does not dedupe: two
people of one unknown place are two findings.
"""
from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any

from verso.core import workspace as workspaces
from verso.core.records import SCHEMA_ID
from verso.core.records.replay import Position
from verso.ru.domain import statuses
from verso.ru.linters import hosted
from verso.ru.linters.on_json import census, common, estates, events, names, places, redundancy
from verso.ru.linters.on_json.places import file_in_scope
from verso.ru.linters.on_json.redundancy import review_level
from verso.ru.linters.on_json.walk import (
    FileView, Finding, NoReplay, RecordView, ReplayRefused, Rule, Unsupported, check_input, estates_present,
    keeping_written, names_table_present)
from verso.ru.messages import t

__all__ = ["RULES", "SUPPORTED", "FileView", "Finding", "Position", "Rule", "Unsupported", "estates_present",
           "file_in_scope", "lint_header", "lint_record", "lint_records", "names_table_present", "review_level"]

RULES: dict[str, Rule] = {
    **census.RULES, **common.RULES, **estates.RULES, **events.RULES, **names.RULES, **places.RULES, **redundancy.RULES}
SUPPORTED = tuple(sorted(RULES))


# The codes whose finding on a record reads the record's page run: a store passes `run_levels` (`lint_record`).
NEEDS_RUN = frozenset({"RVR001"})


def _validated(codes: Collection[str], *, not_a_set_code: bool = False,
               file_scope: bool | None = None, flag_needed: bool = False, run_needed: bool = False) -> tuple[dict[str, hosted.Readiness], set[str]]:
    """The table and the codes asked, each one a code a rule answers: `Unsupported` by name for the rest.
    `not_a_set_code` refuses a code of scope `set`; `flag_needed` a code of scope `file` asked without its flag
    (`file_scope` None); `run_needed` a code of `NEEDS_RUN`, asked without `run_levels`."""
    if isinstance(codes, str):
        raise TypeError(t("on_json.codes_is_str", codes=codes))
    table = hosted.readiness()
    wanted = set(codes)
    for code in sorted(wanted):
        row = table.get(code)
        if row is None:
            raise Unsupported(t("on_json.unsupported", code=code))
        if row.cls == "source":
            raise Unsupported(t("on_json.source_code", code=code))
        if not_a_set_code and row.scope == "set":
            raise Unsupported(t("on_json.set_scope", code=code))
        if flag_needed and row.scope == "file" and file_scope is None:
            raise Unsupported(t("on_json.needs_file_scope", code=code))
        if run_needed and (row.as_code or code) in NEEDS_RUN:
            raise Unsupported(t("on_json.needs_run_levels", code=code))
        if (row.as_code or code) not in RULES:
            raise Unsupported(t("on_json.unsupported", code=code))
    return table, wanted


def _answer(view: FileView, table: Mapping[str, hosted.Readiness], wanted: set[str], keep: Callable[[Finding], bool],
            check: Callable[[], None] | None = None) -> list[Finding]:
    """The findings of the codes `wanted` that the rules make on `view` and `keep` keeps, leveled: the part of
    `lint_records` the three entries share. A positional code asks its keyword code's findings; a rule that reads the
    replay of a view that cannot be replayed leaves its codes unanswered (`Unsupported.unanswered`).

    The call is one request: the corpus's `statuses.toml` is looked at once, as it starts (`statuses.held`), and what
    each node wrote is read once for all the rules (`keeping_written`)."""
    with statuses.held(), keeping_written():
        return _answer_held(view, table, wanted, keep, check)


def _answer_held(view: FileView, table: Mapping[str, hosted.Readiness], wanted: set[str],
                 keep: Callable[[Finding], bool], check: Callable[[], None] | None) -> list[Finding]:
    folded = {table[c].as_code or c for c in wanted}      # a positional code asks its keyword code's findings
    found: list[Finding] = []
    unanswered: set[str] = set()
    refusal: ReplayRefused | None = None
    if wanted and check is not None:
        check()
    lacking = not names_table_present()
    no_estates = not estates_present()
    for rule_code in sorted(folded):
        made: list[Finding] = []
        try:
            for item in RULES[rule_code](view):
                if item.code in folded and keep(item):
                    made.append(dataclasses.replace(item, level=_level(table[item.code], lacking, no_estates)))
        except ReplayRefused as error:
            # the rule reads the replay and the file cannot be replayed: its part is unanswered, not partly found
            refusal = refusal or error
            unanswered.update(c for c in wanted if (table[c].as_code or c) == rule_code)
            continue
        except NoReplay:
            # the file is replayed through the names table; with none, a rule that needs the replay finds nothing
            # more. Every other workspace error is the rule's bug or the caller's, and raises.
            pass
        found.extend(made)
    if refusal is not None:
        raise Unsupported(refusal.message, findings=found, unanswered=unanswered) from refusal
    return found


def lint_records(data: Mapping[str, Any], *, codes: Collection[str],
                 workspace: Path | None = None) -> list[Finding]:
    """The findings of `codes` in a records-v1 file node, as `dsllint` gives them of its source.

    `workspace` is the workspace whose tables (places, names, …) the rules read; `None` is the
    current one. A positional code (`hosted.toml`'s `as`) asks for its keyword code's findings, which are
    spoken as that code: the export does not hold the form of an argument.

    `codes` is a collection of codes, not a `str` (`TypeError`). When it asks for any, the input is checked first,
    as `replay_file` checks it: anything but a mapping of schema `records-v1` with a list of documents, or with a
    vocabulary newer than the plugin's, is a `FormatError`.

    A code the walk cannot answer is `Unsupported` by name (no such code, or one about the form of the source text). A
    file that cannot be replayed (an export without wrapper context, a record no factory rebuilds, a names table that
    lacks a name the file writes) leaves unanswered the codes that read the replay, and the call refuses with
    `Unsupported` — which carries `findings`, those of every requested rule that reads no replay, leveled as usual,
    and `unanswered`, the sorted requested codes whose rules asked for the replay and were refused: a code is
    unanswered exactly when it is refused when asked alone (a derived code whose file holds no record of its kind
    never asks, and is answered with nothing). The refusal is the only report of the
    codes left out: a returned list is whole.

    Calls are not thread-safe: the workspace is a process-global stack and the status tables are cleared through a
    process-global hook. Serialise the calls, or run one per process."""
    table, wanted = _validated(codes)
    view = FileView(data)
    with workspaces.use(workspace) if workspace is not None else contextlib.nullcontext():
        # the input is checked in the workspace of the call: the vocabulary header asks the plugins enabled there
        return _answer(view, table, wanted, lambda item: True, lambda: check_input(data))


def lint_record(node: Mapping[str, Any], *, header: Mapping[str, Any], page: str | None, position: Position,
                codes: Collection[str], workspace: Path | None = None, file_in_scope: bool | None = None,
                run_levels: Collection[bool] | None = None) -> list[Finding]:
    """The findings of `codes` on one record of a records-v1 file, as `lint_records` gives them in the file.

    `node` is the record's node, `header` its record set's node (with or without its `pages`), `page` the leaf it
    stands on and `position` its place in the set (`verso.core.records.replay`): the rules read the record and its set's
    header and nothing else, and the objects they read are built alone, as the set's factory builds them in the book.
    The findings are those addressed to the record; a finding addressed to the set is `lint_header`'s.

    A code of scope `set` (`hosted.readiness()[code].scope`) is answered of the header alone and refused here
    (`Unsupported`, `on_json.set_scope`), as a source code is. A code of scope `file` — ULC001 — reads one fact of the
    whole file: `file_in_scope` (`places.file_in_scope(headers)`), refused without it (`on_json.needs_file_scope`).
    `run_levels` is what RVR001 cannot see of a record alone: a record's own `reviewed=` is redundant only if its page
    run holds an unflagged record built with the set's level, so the caller that knows the run gives the `reviewed` the
    run's other unflagged records show — `review_level(node, built)` of each (an empty collection: the run holds no
    other). RVR001 asked without
    it is refused (`Unsupported`, `on_json.needs_run_levels`), never answered from a run it cannot see.

    A record the factories cannot build, or a names table that lacks a name it writes, leaves unanswered the codes that
    read the replay, as in `lint_records` (`Unsupported.findings`, `Unsupported.unanswered`). `workspace` is the one
    whose tables the rules read (`None`: the current one). Calls are not thread-safe, as `lint_records`' are not."""
    table, wanted = _validated(codes, not_a_set_code=True, file_scope=file_in_scope, flag_needed=True,
                               run_needed=run_levels is None)
    view = RecordView(node, header=header, page=page, position=position, file_scope=file_in_scope,
                      run_levels=run_levels)
    with workspaces.use(workspace) if workspace is not None else contextlib.nullcontext():
        return _answer(view, table, wanted, lambda item: item.record == node["id"])


def lint_header(header: Mapping[str, Any], *, codes: Collection[str], workspace: Path | None = None,
                file_in_scope: bool | None = None) -> list[Finding]:
    """The findings of `codes` addressed to a record set itself — what its header writes: the codes of scope `set`,
    and the part of any other code that a book's defaults or its parish make (SOR001 on a default status, ZGS004, ULC001
    on a parish). `header` is the set's node with or without its `pages`, which are not read. A code of scope `file` is
    refused without `file_in_scope`, as in `lint_record`. The findings of `lint_header` over a file's sets and those of
    `lint_record` over its records are those of `lint_records`."""
    table, wanted = _validated(codes, file_scope=file_in_scope, flag_needed=True)
    view = FileView({"schema": SCHEMA_ID, "documents": [{**{k: v for k, v in header.items() if k != "pages"}, "pages": []}]})
    view.file_scope = file_in_scope
    with workspaces.use(workspace) if workspace is not None else contextlib.nullcontext():
        return _answer(view, table, wanted, lambda item: True)


def _level(row: hosted.Readiness, lacking_names: bool, lacking_estates: bool) -> str:
    """A finding's level: `refuse` is an error, `warn` a warning (H5); a code that reads the names table, in a
    workspace without one, only warns (H7), and so does one that reads the corpus's estates in a workspace with
    none: what it finds there rests on a partial reading."""
    if (lacking_names and "names" in row.needs) or (lacking_estates and "estates" in row.needs):
        return "warn"
    return "error" if row.severity == "refuse" else "warn"
