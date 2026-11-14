#!/usr/bin/env python3
"""AST-based linter (MST001) for the `marital_status=` (семейное положение) field
on census members and WWI/WWII external-source records.

`marital_status=` is free-text rendered as «Семейное положение: …». MST001 keeps
the vocabulary consistent: a string literal must be a known `verso.ru.domain.marital_status`
value — an **unknown** literal is a typo/mistake and is flagged here. A *recognised*
literal (one that has a constant) is handled by `single_line_calls` instead — its
"use constant X instead of the string literal" rule, with the replace-kwarg
quick-fix, exactly like `status=`/`cause_of_death=`. A constant reference (a
Name/Attribute, not a literal) is always accepted.

Path-independent: scopes on the call func name + the `marital_status=` kwarg, so
it behaves the same on disk or on a temp-file copy of an unsaved editor buffer.

Run:
    python3 -m verso.ru.linters.checks.marital_status FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from typing import Any
from verso.ru.linters.issue import as_dict, issue
from verso.ru.linters.checks import shared_ast

# Records that carry a marital_status= kwarg.
_RECORD_FUNCS = frozenset({"wwi_record", "wwii_record", "member", "CensusMember"})


def _load_known_marital() -> dict[str, str]:
    """Return {string_value: constant_name} from verso.ru.dsl.marital_status."""
    try:
        import verso.ru.domain.marital_status as mod
    except Exception:
        return {}
    result: dict[str, str] = {}
    for name in dir(mod):
        if name.startswith("_") or name == "MARITAL_STATUSES":
            continue
        val = getattr(mod, name)
        if isinstance(val, str):
            result[str(val)] = name
    return result


KNOWN_MARITAL: dict[str, str] = _load_known_marital()


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


class MaritalStatusChecker(shared_ast.Visitor):
    def __init__(self) -> None:
        self.issues: list[dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if _call_func_name(node) in _RECORD_FUNCS and KNOWN_MARITAL:
            for kw in node.keywords:
                if kw.arg != "marital_status" or not isinstance(kw.value, ast.Constant):
                    continue
                literal = kw.value.value
                if not isinstance(literal, str) or literal in KNOWN_MARITAL:
                    # A recognised literal is single_line_calls' job (use-constant
                    # rule + quick-fix); only flag values with no constant.
                    continue
                self.issues.append(as_dict(issue("MST001", "unknown", kw.lineno, level="error", token=literal,
                                                 value=literal)))
        self.generic_visit(node)


def check_file_structured(path: Path) -> list[dict[str, Any]]:
    try:
        tree = shared_ast.parse(Path(path).read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    checker = MaritalStatusChecker()
    checker.visit(tree)
    return checker.issues


def check_file(path: Path) -> list[str]:
    return [f"{path}:{i['line']}: {i['message']}" for i in check_file_structured(path)]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    all_errors: list[str] = []
    for arg in sys.argv[1:]:
        all_errors.extend(check_file(Path(arg)))
    for e in all_errors:
        print(e)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
