"""How many records of the workspace's corpus write a given name — what `verso names remove` tells before a name goes.

A record is one call of the DSL's record verbs (`RECORD_VERBS`: a birth, a roll's member, a card …) with a `person(...)`
among its arguments that writes the name as its given name — `name_orig`, read modernized as the lexicon's keys are
(«Тимоѳей» is «Тимофей»), or `name_modern_orth` where written; a `person(...)` outside any such call counts as one. The
files are read as syntax, never run: the count is advisory and costs the parse of each file of each village.
"""
from __future__ import annotations

import ast
from collections.abc import Iterator

from verso.core import workspace
from verso.core.pipeline.load import dsl_files
from verso.ru.naming.orthography import modernize_orthography

#: The calls that make one record of the corpus (`verso.ru.dsl`).
RECORD_VERBS = frozenset({"birth", "christening", "criminal_record", "death", "divorce", "listed_person", "marriage",
                          "member", "wwi_record", "wwii_record"})


def _callee(node: ast.Call) -> str | None:
    func = node.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def _text(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _given_name(call: ast.Call) -> str | None:
    """The given name a `person(...)` call writes, in the lexicon's orthography; None when it writes none as text."""
    keywords = {k.arg: k.value for k in call.keywords if k.arg}
    modern = _text(keywords.get("name_modern_orth"))
    if modern:
        return modern
    written = _text(call.args[0]) if call.args else _text(keywords.get("name_orig"))
    return modernize_orthography(written) if written else None


def _records_writing(tree: ast.AST, name: str) -> Iterator[ast.AST]:
    """The record nodes of `tree` holding a `person(...)` that writes `name` (each once, however many persons do)."""
    stack: list[tuple[ast.AST, ast.AST | None]] = [(tree, None)]
    seen: set[int] = set()
    while stack:
        node, record = stack.pop()
        if isinstance(node, ast.Call):
            callee = _callee(node)
            if callee in RECORD_VERBS:
                record = node
            elif callee == "person" and _given_name(node) == name:
                holder = record or node
                if id(holder) not in seen:
                    seen.add(id(holder))
                    yield holder
        stack.extend((child, record) for child in ast.iter_child_nodes(node))


def written_count(ws: workspace.Workspace, name: str) -> int:
    """The records of the workspace's villages that write `name` as a given name."""
    total = 0
    for village in ws.villages:
        directory = ws.village_dir(village)
        for path in dsl_files(directory) if directory.is_dir() else ():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, ValueError):
                continue
            total += sum(1 for _ in _records_writing(tree, name))
    return total
