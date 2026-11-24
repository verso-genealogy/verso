#!/usr/bin/env python3
"""AST-based linter (DVC001) for an act of divorce that names its marriage as text.

`divorce(marriage_date=)` takes an `EventDate` — the library's one structure of a date, as an external card's
dates are. DSL v1 wrote the act's text there (`marriage_date="24 февраля 1927"`); the text is still taken, with a
`DeprecationWarning`, kept and exported as written, and no reader parses it — so the facts layer does not see the
wedding it names, and from 0.2 the text is refused.

  [DVC001] `marriage_date=` written as text. Where the text is a date in a form the library reads
           (`verso.ru.domain.event_date.read_written_date`: «24 февраля 1927», «февраль 1927», «1927»,
           «24.02.1927»), the finding offers its replacement, `EventDate(1927, Month.FEBRUARY, 24)` — the IDE's
           quick fix; `EventDate` and `Month` are imported from `verso.ru.dsl` by the author. A text the library
           does not read as a date (written in its place, or in another form) is said with no replacement. A
           text bound once to a name at the head of the file (`MARRIED = "…"`, `marriage_date=MARRIED`) is said
           at the act, with no replacement either. A file that defines or binds its own `divorce` has no act.

Advisory: the corpora that wrote the text move to `EventDate` on their own commit.

Run:
    python3 -m verso.ru.linters.checks.divorces FILE [FILE...]
"""

import ast
import sys
from calendar import Month
from pathlib import Path

from verso.ru.domain.event_date import EventDate, read_written_date
from verso.ru.linters.issue import as_dict, issue
from verso.ru.linters.checks import shared_ast
from verso.ru.linters.checks.file_bindings import module_bindings, string_constants

#: Where `divorce()` takes `marriage_date` in its place (record_num, d_day, d_month, husband, wife, husband_age,
#: wife_age, marriage_date).
MARRIAGE_DATE_POSITION = 7


def as_code(date: EventDate) -> str:
    """`date` as the DSL writes it: `EventDate(1927, Month.FEBRUARY, 24)`, `EventDate(1927, Month.FEBRUARY)`,
    `EventDate(1927)`."""
    parts = [str(date.year)]
    if date.month is not None:
        parts.append(f"Month.{Month(date.month).name}")
        if date.day is not None:
            parts.append(str(date.day))
    return f"EventDate({', '.join(parts)})"


def said(text: str) -> dict[str, object]:
    """DVC001's finding of one text, without a place: the replacement it offers where the text reads as a date."""
    date = read_written_date(text)
    if date is None:
        return as_dict(issue("DVC001", "unread", None, token=text, text=text))
    return as_dict(issue("DVC001", "text", None, token=text, text=text, date=as_code(date)))


def _func_name(node: ast.Call) -> str | None:
    return node.func.id if isinstance(node.func, ast.Name) else None


#: Where a DSL file's `divorce` comes from (IMP001).
FACADE = "verso.ru.dsl"


def _binds_divorce(stmt: ast.stmt) -> bool:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return stmt.name == "divorce"
    if isinstance(stmt, ast.ImportFrom):
        return stmt.module != FACADE and any((a.asname or a.name) == "divorce" for a in stmt.names)
    if isinstance(stmt, ast.Import):
        return any((a.asname or a.name) == "divorce" for a in stmt.names)
    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
        return any(isinstance(n, ast.Name) and n.id == "divorce" for t in targets for n in ast.walk(t))
    return False


def _own_divorce(tree: ast.AST) -> bool:
    """The file defines, binds or imports from elsewhere a `divorce` of its own: its calls are no act (a DSL file
    imports the facade's, IMP001)."""
    return isinstance(tree, ast.Module) and any(_binds_divorce(stmt) for stmt in tree.body)


def _collect(tree: ast.AST, src: str | None = None) -> list[dict[str, object]]:
    lines = src.splitlines() if src is not None else []
    found: list[dict[str, object]] = []
    if _own_divorce(tree):
        return found
    # `MARRIED = "24 февраля 1927"` once at the head of the file, `marriage_date=MARRIED` in the act.
    texts = string_constants(module_bindings(tree))
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call) or _func_name(node) != "divorce":
            continue
        keyword = next((kw for kw in node.keywords if kw.arg == "marriage_date"), None)
        value = keyword.value if keyword is not None else (
            node.args[MARRIAGE_DATE_POSITION] if len(node.args) > MARRIAGE_DATE_POSITION else None)
        if isinstance(value, ast.Name) and texts.get(value.id, "").strip():
            # Said at the act, with no fix: the name may stand for other acts too, and its line is the author's.
            found.append({**said(texts[value.id]), "level": "warn", "line": value.lineno})
            continue
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)) or not value.value.strip():
            continue
        finding = {**said(value.value), "level": "warn", "line": value.lineno}
        date = read_written_date(value.value)
        source = ast.get_source_segment(src, value) if src is not None else None
        on_one_line = value.lineno == value.end_lineno and value.lineno <= len(lines)
        if keyword is not None and date is not None and source is not None and on_one_line:
            # `ast` counts UTF-8 bytes; the IDEs place a fix by character.
            col = len(lines[value.lineno - 1].encode("utf-8")[:value.col_offset].decode("utf-8", "ignore"))
            finding.update(col=col, end_col=col + len(source),
                           fix={"type": "replace_kwarg", "old": source, "new": as_code(date), "col": col})
        found.append(finding)
    return sorted(found, key=lambda i: int(str(i["line"])))


def _parsed(path: Path) -> tuple[ast.AST, str] | SyntaxError:
    src = Path(path).read_text(encoding="utf-8")
    try:
        return shared_ast.parse(src), src
    except SyntaxError as e:
        return e


def check_file(path: Path) -> list[str]:
    parsed = _parsed(path)
    if isinstance(parsed, SyntaxError):
        return []  # an advisory check: the hard ones report the syntax error
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(*parsed)]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    parsed = _parsed(path)
    if isinstance(parsed, SyntaxError):
        return []  # other linters report the syntax error as an error
    return _collect(*parsed)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    lines = [line for arg in sys.argv[1:] for line in check_file(Path(arg))]
    for line in lines:
        print(line)
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
