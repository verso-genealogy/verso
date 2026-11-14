#!/usr/bin/env python3
"""AST-based linter that flags the legacy implicit `hidden` sentinels on
census `member()` / `CensusMember(...)` calls. After the migration to
the explicit `hidden=True` kwarg, neither sentinel carries semantic
meaning to the translator, so leaving one in place is a hard error.

Two patterns are flagged:
1. `record_number="X-Y"` (any string literal) → use `hidden=True` and
   drop the kwarg. `record_number` is now typed `int | None`.
2. `comment="Отсутствует в РС…"` (the manual-add documentation) without
   an accompanying `hidden=True` kwarg → add `hidden=True`. The comment
   text stays as documentation, but the explicit flag is required.

Run:
    python3 check_hidden_flag.py FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from verso.ru.linters.issue import as_dict, Issue, issue, line_text
from verso.ru.linters.checks import shared_ast


_TARGETS = {"member", "CensusMember"}


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {
        kw.arg: kw for kw in node.keywords
        if kw.arg is not None
    }


def _string_literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_true(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def check_file(path: Path) -> list[str]:
    return [line_text(path, i) for i in _issues(path)]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    return [as_dict(i) for i in _issues(path)]


def _issues(path: Path) -> list[Issue]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [issue("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg)]

    errors: list[Issue] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_func_name(node) not in _TARGETS:
            continue

        kw = _kwargs(node)

        rn = kw.get("record_number")
        if rn is not None and _string_literal(rn.value) is not None:
            errors.append(issue("HID001", "string_number", rn.value.lineno, level="error"))

        comment = kw.get("comment")
        comment_text = (
            _string_literal(comment.value) if comment is not None else None
        )
        if (
            comment_text is not None
            and comment_text.strip().startswith("Отсутствует в РС")  # i18n: content — the comment words the DSL writes
            and not (
                "hidden" in kw and _is_true(kw["hidden"].value)
            )
        ):
            errors.append(issue("HID002", "absent_not_hidden", comment.value.lineno, level="error"))

    return errors


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
