#!/usr/bin/env python3
"""IMP001 — a DSL file imports the DSL's facade and nothing else (DSL v1).

The facade `verso.ru.dsl`, its three catalogs (`verso.ru.dsl.statuses`, `.causes_of_death`,
`.marital_status`) and the corpus's own statuses (`<corpus dir>.statuses`, `corpus.statuses`
here) are all a DSL file
needs; anything else — `geni.*` (DSL v0, whose alias is gone), `calendar`, `os`, a module
of the library — is an import the DSL's contract (`verso dsl-surface`) does not cover.
`verso upgrade-dsl <файл>` rewrites a v0 file's imports, and the finding names it for
`geni.*` and `calendar` alone — the rest is the author's to take out. Hard, no `--fix`.

Run: python3 -m verso.ru.linters.checks.dsl_imports FILE [FILE...]
"""
import ast
import shlex
import sys
from pathlib import Path
from typing import Any
from verso.ru.linters.issue import as_dict, issue
from verso.ru.linters.checks import shared_ast

FACADE = frozenset({"verso.ru.dsl", "verso.ru.dsl.statuses", "verso.ru.dsl.causes_of_death",
                    "verso.ru.dsl.marital_status"})


def allowed() -> frozenset[str]:
    """The facade's modules and the workspace's corpus's statuses (`<corpus dir>.statuses`)."""
    from verso.core.workspace import WorkspaceError
    from verso.ru.domain.statuses import corpus_module_name
    try:
        corpus = corpus_module_name()
    except WorkspaceError:
        corpus = None
    return FACADE | ({corpus} if corpus else set())


def _imported(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return ["." * node.level + (node.module or "")]


def check_file_structured(path: Path) -> list[dict[str, Any]]:
    try:
        tree = shared_ast.parse(Path(path).read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    ok = allowed()
    return [as_dict(issue("IMP001", "upgrade", node.lineno, level="error", token=module, module=module, path=shlex.quote(str(path)))
                    if _upgraded(module) else
                    issue("IMP001", "outside", node.lineno, level="error", token=module, module=module))
            for node in shared_ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)
            for module in _imported(node) if module not in ok]


def _upgraded(module: str) -> bool:
    """A module `verso upgrade-dsl` rewrites to the facade — DSL v0's `geni.*`, `calendar` (its
    `Month`); anything else it refuses or keeps, so the finding names no command."""
    return module in ("geni", "calendar") or module.startswith("geni.")


def check_file(path: Path) -> list[str]:
    return [f"{path}:{d['line']}: {d['message']}" for d in check_file_structured(path)]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    findings = [m for a in args for m in check_file(Path(a))]
    for m in findings:
        print(m)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
