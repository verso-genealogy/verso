#!/usr/bin/env python3
"""AST-based linter (CML001) requiring every `member()` in a census record to
start its own line.

Revision lists are read one person per row, and the DSL is easiest to diff,
review and hand-edit when it keeps that shape. Packing a member onto the tail of
the previous one — `... age=44), member(5, ...` — hides a person mid-line, makes
a one-person change touch two members, and turns a `git blame` on a member into
a blame on its neighbour.

  [CML001] A `member(...)` call that does not begin its line.

The rule is deliberately unconditional: the first member after `household("12",`
must move to its own line too. An exception for that one position would need a
special case in both the check and the codemod, and buys nothing — a household's
head is no less a person than the rest.

Note this does NOT ask for the whole call on one line: a member with many kwargs
may wrap freely. Only its FIRST token must start a line. (`single_line_calls`
governs `person()`, which is a different rule and unaffected.)

Run:
    python3 -m verso.ru.linters.checks.census_member_lines FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from verso.ru.linters.issue import as_dict, issue, line_text
from verso.ru.linters.checks import shared_ast


def _char_col(lines: list[str], lineno: int, byte_col: int) -> int:
    """Convert a 0-based AST col_offset (a UTF-8 BYTE offset) to a character
    column. Census DSL lines are full of Cyrillic, so the byte offset overshoots
    and slicing by it would cut mid-name."""
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


def _member_calls(tree: ast.AST):
    for node in shared_ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "member"):
            yield node


def _collect(tree: ast.AST, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in _member_calls(tree):
        idx = node.lineno - 1
        if not (0 <= idx < len(lines)):
            continue
        col = _char_col(lines, node.lineno, node.col_offset)
        before = lines[idx][:col]
        if before.strip() == "":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            found = issue("CML001", "numbered", node.lineno, level="error", number=str(node.args[0].value))
        else:
            found = issue("CML001", "unnumbered", node.lineno, level="error")
        issues.append(as_dict(found))
    return issues


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, issue("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}"
            for i in _collect(tree, src.splitlines())]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    return _collect(tree, src.splitlines())


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    errors: list[str] = []
    for arg in sys.argv[1:]:
        errors.extend(check_file(Path(arg)))
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
