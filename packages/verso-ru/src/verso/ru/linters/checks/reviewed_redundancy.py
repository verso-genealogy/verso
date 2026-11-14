#!/usr/bin/env python3
"""RVR001 — a ``reviewed=`` that restates the value it would already inherit.

``reviewed`` is declared at three nesting levels and resolved innermost-first:

    name_list_records(..., reviewed=False)   # file default, `bool` (True)
      └ page("21 об.", ..., reviewed=True)   # a whole лист, `bool | None`
          └ listed_person(823, ..., reviewed=True)   # one entry, `bool | None`

``page()`` fills a record's flag only where the record left it ``None``
(`verso/ru/domain/factories.py`), and ``NameListRecords.__init__`` /
``CensusRecords.__init__`` then fill whatever is still ``None`` from the
file-level default. So an inner ``reviewed=X`` is **redundant** exactly when the
value it would otherwise inherit is also ``X`` — and deleting it is a true no-op:
same flag, same profiles, same document text.

Both directions are flagged, because both happen for the same reason. Holding a
лист with ``page(reviewed=False)`` and then repeating ``reviewed=False`` on its
entries is as redundant as releasing one with ``reviewed=True`` and repeating
that. The second is what the 1917 Горюхино sweep produced: entries carried over
from an older verified extract kept their own ``reviewed=True`` and then the лист
around them was closed with ``page(..., reviewed=True)``.

**Every record type participates** whose own ``reviewed`` defaults to ``None``
— all of them since 2026-10-03 (`verso/ru/dsl/records/reviewed.py`). Until then
``birth``/``marriage``/``death`` defaulted to ``True``, ``page(reviewed=…)``
never reached them, and removing an explicit flag there would silently have
flipped ``False`` to ``True`` — so the check refused to look at them.

Advisory, with a ``remove_kwarg`` fix: the removal is mechanical and provably
byte-neutral, so the editors can offer it as a quick fix.

Run:
    python3 -m verso.ru.linters.checks.reviewed_redundancy FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from typing import Any

from verso.ru.linters.checks.census_redundancy import _call_func_name, _char_col, _kwargs
from verso.ru.linters.issue import as_dict, issue
from verso.ru.linters.checks import shared_ast

# Record-set calls carrying the file-level default, and the `reviewed=` default
# their signature declares when the kwarg is absent.
RECORD_SETS = {"name_list_records": True, "census_records": True,
               "birth_records": True, "marriage_records": True, "death_records": True}

# The record types whose own `reviewed` defaults to None, i.e. the ones a
# page() or a record set can actually fill. See the module docstring.
INNER_CALLS = {"listed_person", "household", "birth", "christening", "marriage", "death"}

PAGE_CALL = "page"


def _bool_literal(node: ast.expr | None) -> bool | None:
    """`True`/`False` as written, else None — a name or expression is not ours
    to resolve, and a flag we cannot read is a flag we must not delete."""
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def _reviewed(node: ast.Call) -> tuple[ast.keyword | None, bool | None]:
    kw = _kwargs(node).get("reviewed")
    return kw, _bool_literal(kw.value) if kw is not None else None


def _first_string_arg(node: ast.Call) -> str | None:
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _remove_fix(kw: ast.keyword, lines: list[str]) -> dict[str, object]:
    return {"type": "remove_kwarg", "kwarg": "reviewed",
            "col": _char_col(lines, kw.lineno, kw.col_offset)}


def _calls(node: ast.AST, names: set[str] | str) -> list[ast.Call]:
    wanted = {names} if isinstance(names, str) else names
    return [n for n in shared_ast.walk(node)
            if isinstance(n, ast.Call) and _call_func_name(n) in wanted]


def _collect(tree: ast.AST, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []

    for records in _calls(tree, set(RECORD_SETS)):
        records_name = _call_func_name(records) or ""
        _, stated = _reviewed(records)
        if stated is None and _kwargs(records).get("reviewed") is not None:
            # `reviewed=SOME_CONSTANT` — unreadable, so nothing below it can be
            # proven redundant.
            continue
        file_level = RECORD_SETS[records_name] if stated is None else stated
        how = "default" if stated is None else "set"

        pages = _calls(records, PAGE_CALL)
        inside_pages = {id(n) for p in pages for n in shared_ast.walk(p)}

        for page in pages:
            page_kw, page_value = _reviewed(page)
            label = _first_string_arg(page)
            named = "page_labelled" if label else "page_bare"

            if page_kw is not None and page_value == file_level:
                issues.append(as_dict(issue("RVR001", f"{named}_{how}", page_kw.lineno, level="warn",
                                            fix=_remove_fix(page_kw, lines), value=str(page_value),
                                            records=records_name, level_set=str(file_level),
                                            **({"label": label} if label else {}))))

            effective = file_level if page_value is None else page_value
            source: tuple[str, dict[str, Any]] = (
                (f"records_{how}", {"records": records_name}) if page_value is None
                else (named, {"label": label} if label else {}))
            for inner in _calls(page, INNER_CALLS):
                issues.extend(_inner_issue(inner, effective, source, lines))

        for inner in _calls(records, INNER_CALLS):
            if id(inner) in inside_pages:
                continue
            issues.extend(
                _inner_issue(inner, file_level, (f"records_{how}", {"records": records_name}), lines))

    issues.sort(key=lambda i: (i["line"], str(i["message"])))
    return issues


def _inner_issue(inner: ast.Call, effective: bool, source: tuple[str, dict[str, Any]],
                 lines: list[str]) -> list[dict[str, object]]:
    """`source` is what already says the value: the record set (its name, defaulting or setting it),
    or the `page()` around the call (its leaf, if it names one)."""
    kw, value = _reviewed(inner)
    if kw is None or value is None or value != effective:
        return []
    variant, params = source
    return [as_dict(issue("RVR001", f"inner_{variant}", kw.lineno, level="warn", fix=_remove_fix(kw, lines),
                          value=str(value), func=_call_func_name(inner) or "", effective=str(effective),
                          **params))]


def check_file_structured(path: Path) -> list[dict[str, Any]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []
    return _collect(tree, src.splitlines())


def check_file(path: Path) -> list[str]:
    return [f"{path}:{d['line']}: {d['message']}"
            for d in check_file_structured(Path(path))]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    findings = [m for a in args for m in check_file(Path(a))]
    for m in findings:
        print(m)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
