#!/usr/bin/env python3
"""AST-based linter (RET001–RET003) for an age retraction that retracts nothing.

`member(source_age_error=)`, `member(previous_age_error=)` and
`death(source_age_error=)` withdraw an age the record states — the facts layer
stops believing it and, since 2026-09-25, the translator derives no birth from
it. `death(namesake=)` says the age is right and stands `verso death-age` down.
Each of them is a statement ABOUT an age, so on a line that states no such age
it says nothing, and is almost certainly a slip of the pen: the wrong line, the
wrong kwarg, or a figure the transcriber left out.

  [RET001] `previous_age_error=` on a roll line with no previous figure — no
           `previous_age=` and no «прошлая РС:» marker in `comment=`.
  [RET002] `source_age_error=` (roll line or burial) or `namesake=` (burial) on
           a record that states no age at all.
  [RET003] `source_age_error=` and `previous_age_error=` on one roll line: the
           whole-line retraction already withdraws the previous figure.

Not-recorded ages (`None`, `""`, `"?"`, `"-"`) count as no age, as they do for
`verso.ru.ages.format_age`. A roll line dated by a typed `birth_year=`/`birth_day=`
is a line `source_age_error=` can withdraw, so it does not trip RET002.

Run:
    python3 -m verso.ru.linters.checks.retractions FILE [FILE...]
"""

import ast
import sys
from pathlib import Path

from verso.ru.linters.checks.census_age import (
    PREV_AGE_COMMENT_RE, _call_func_name, _kwargs, _member_arg, _string_literal)
from verso.ru.linters.issue import as_dict, issue, line_text
from verso.ru.linters.checks import shared_ast

NOT_RECORDED = frozenset({"", "?", "-"})


def _states(node: ast.expr | None) -> bool:
    """Does this argument state an age (or a date)?"""
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        if node.value is None:
            return False
        if isinstance(node.value, str):
            return node.value.strip() not in NOT_RECORDED
    return True


def _has_prev_marker(m: ast.Call) -> bool:
    kw = _kwargs(m).get("comment")
    text = _string_literal(kw.value) if kw is not None else None
    return bool(text and PREV_AGE_COMMENT_RE.search(text))


def _issue(node: ast.keyword, code: str, variant: str) -> dict[str, object]:
    return as_dict(issue(code, variant, node.lineno, level="error"))


def _check_member(m: ast.Call) -> list[dict[str, object]]:
    kw = _kwargs(m)
    issues: list[dict[str, object]] = []
    whole, prev = kw.get("source_age_error"), kw.get("previous_age_error")
    has_prev = _states(_member_arg(m, 5, "previous_age")) or _has_prev_marker(m)
    has_age = _states(_member_arg(m, 4, "age"))
    has_date = any(_states(kw[k].value) for k in ("birth_year", "birth_day", "birth_month")
                   if k in kw)
    if prev is not None and not has_prev:
        issues.append(_issue(prev, "RET001", "no_previous"))
    if whole is not None and not (has_age or has_prev or has_date):
        issues.append(_issue(whole, "RET002", "no_age"))
    if whole is not None and prev is not None:
        issues.append(_issue(prev, "RET003", "both"))
    return issues


def _check_death(d: ast.Call) -> list[dict[str, object]]:
    kw = _kwargs(d)
    age = kw["age"].value if "age" in kw else (d.args[7] if len(d.args) > 7 else None)
    if _states(age):
        return []
    return [_issue(kw[name], "RET002", "burial_" + name) for name in ("source_age_error", "namesake") if name in kw]


def _collect(tree: ast.AST) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_func_name(node)
        if name == "member":
            issues.extend(_check_member(node))
        elif name == "death":
            issues.extend(_check_death(node))
    return sorted(issues, key=lambda i: (int(str(i["line"])), str(i["message"])))


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, issue("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree)]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    return [
        {"level": i.get("level", "error"), "line": i["line"], "message": i["message"]}
        for i in _collect(tree)
    ]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    errors: list[str] = []
    for arg in sys.argv[1:]:
        errors.extend(check_file(Path(arg)))
    for line in errors:
        print(line)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
