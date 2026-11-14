#!/usr/bin/env python3
"""AST linter for name-list DSL records (`name_list_records()` /
`listed_person()` from verso.ru.dsl).

NLC001 — data sanity: a `name_list_records()` must have a non-empty
`document_type`; a `listed_person()` numeric `age` must be > 0 (a non-numeric
age such as "?" is allowed — it just yields no birth event).

Path-independent: scopes purely on the call func name, so it behaves the same
on a file on disk or a temp-file copy of an unsaved editor buffer.

Run: python3 -m verso.ru.linters.checks.name_lists FILE [FILE...]
"""
import ast
import sys
from pathlib import Path
from typing import Any
from verso.ru.linters.issue import as_dict, Issue, issue
from verso.ru.linters.checks import shared_ast


def _resolve_int_literal(node: ast.expr) -> int | None:
    """Resolve a literal (possibly negated) integer, else None.

    Handles both a plain `ast.Constant` int and a negative literal, which
    parses as `ast.UnaryOp(op=ast.USub(), operand=ast.Constant(n))` — e.g.
    `age=-5`. Bools are excluded (bool is an int subclass). Non-numeric
    values (including strings like "?") resolve to None and are left alone.
    """
    if isinstance(node, ast.Constant) \
            and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
            and isinstance(node.operand, ast.Constant) \
            and isinstance(node.operand.value, int) \
            and not isinstance(node.operand.value, bool):
        return -node.operand.value
    return None


def _findings(tree: ast.AST) -> list[Issue]:
    out: list[Issue] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name == "listed_person":
            for kw in node.keywords:
                if kw.arg != "age":
                    continue
                resolved = _resolve_int_literal(kw.value)
                if resolved is not None and resolved <= 0:
                    out.append(issue("NLC001", "age", node.lineno, level="error", age=repr(resolved)))
        elif name == "name_list_records":
            for kw in node.keywords:
                if kw.arg == "document_type" and isinstance(kw.value, ast.Constant) \
                        and (kw.value.value is None or str(kw.value.value).strip() == ""):
                    out.append(issue("NLC001", "document_type", node.lineno, level="error"))
    return out


def check_file_structured(path: Path) -> list[dict[str, Any]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []
    return [as_dict(found) for found in _findings(tree)]


def check_file(path: Path) -> list[str]:
    return [
        f"{path}:{d['line']}: {d['message']}"
        for d in check_file_structured(path)
    ]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    findings = [m for a in args for m in check_file(Path(a))]
    for m in findings:
        print(m)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
