#!/usr/bin/env python3
"""AST-based linter (MRA001) for residence alignment inside a marriage record.

Before the wedding a party lives in their parent's household, so a `marriage()`
naming a party's FATHER/MOTHER via `relatives=[relative(person, Relationship.X,
"жених"/"невеста")]` implies one village for that pair. When BOTH carry an
explicit residence literal and they differ, one of the two is wrong — the shape
that produced the Ротозеево/Ухабовка split-household errors.

Only the explicit-vs-explicit case is checked. Unlike deaths, `Marriage.__init__`
deliberately has NO residence inheritance: clergy genuinely live across parishes
(a пономарь groom whose father is a former deacon of Захолустье), so an implicit
side stays on the record default and is never compared — that keeps the clergy
case silent and makes this check pure drift protection (0 corpus findings).

Groom↔bride are never compared (different households by definition), nor are
witnesses/godparents or non-parent relatives.

Run:
    python3 -m verso.ru.linters.checks.marriage_residence FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from verso.ru.linters.issue import issue, line_text, says
from verso.ru.linters.checks import shared_ast

# `marriage(record_num, w_day, w_month, groom, bride, …, relatives, …)`: the places of
# the arguments read here when written positionally (tests/test_check_marriage_residence.py
# holds them to the factory's signature).
GROOM_AT, BRIDE_AT, RELATIVES_AT = 3, 4, 24


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def _arg(node: ast.Call, index: int, name: str) -> ast.expr | None:
    kw = _kwargs(node).get(name)
    if kw is not None:
        return kw.value
    return node.args[index] if len(node.args) > index else None


def _string_literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _name_id(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _person_kwarg(kwargs: dict[str, ast.keyword], role: str) -> ast.Call | None:
    kw = kwargs.get(role)
    if kw is None or not isinstance(kw.value, ast.Call):
        return None
    if _call_func_name(kw.value) != "person":
        return None
    return kw.value


def _party(node: ast.Call, index: int, role: str) -> ast.Call | None:
    """The `person(...)` a marriage() passes as `role=`, or in `role`'s place."""
    value = _arg(node, index, role)
    if isinstance(value, ast.Call) and _call_func_name(value) == "person":
        return value
    return None


def _residence_value(person_node: ast.Call) -> str | None:
    """`residence=` kwarg literal, else positional index 6 of person()."""
    pkw = _kwargs(person_node)
    if "residence" in pkw:
        return _string_literal(pkw["residence"].value)
    if len(person_node.args) >= 7:
        return _string_literal(person_node.args[6])
    return None


def _residence_line(person_node: ast.Call) -> int:
    res_kw = _kwargs(person_node).get("residence")
    return res_kw.value.lineno if res_kw is not None else person_node.lineno


def _marriage_relatives(node: ast.Call) -> list[tuple[ast.Call, str | None, str | None]]:
    """(person, relationship, relationship_ref) from a marriage()'s relatives."""
    out: list[tuple[ast.Call, str | None, str | None]] = []
    rels = _arg(node, RELATIVES_AT, "relatives")
    if not isinstance(rels, ast.List):
        return out
    for elt in rels.elts:
        if not isinstance(elt, ast.Call):
            continue
        if _call_func_name(elt) not in ("relative", "Relative"):
            continue
        ekw = _kwargs(elt)
        person = _person_kwarg(ekw, "person")
        if person is None and elt.args and isinstance(elt.args[0], ast.Call):
            cand = elt.args[0]
            person = cand if _call_func_name(cand) == "person" else None
        if person is None:
            continue
        rel = (_name_id(ekw["relationship"].value) if "relationship" in ekw
               else (_name_id(elt.args[1]) if len(elt.args) >= 2 else None))
        ref = (_string_literal(ekw["relationship_ref"].value)
               if "relationship_ref" in ekw
               else (_string_literal(elt.args[2]) if len(elt.args) >= 3 else None))
        out.append((person, rel, ref))
    return out


def _check_marriage(node: ast.Call) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for person, relationship, ref in _marriage_relatives(node):
        if relationship not in ("FATHER", "MOTHER"):
            continue
        if ref and "жених" in ref:  # i18n: content — the reference words the DSL writes
            party, party_label = _party(node, GROOM_AT, "groom"), "groom"
        elif ref and "невест" in ref:  # i18n: content — the reference words the DSL writes
            party, party_label = _party(node, BRIDE_AT, "bride"), "bride"
        else:
            continue
        if party is None:
            continue
        party_res = _residence_value(party)
        parent_res = _residence_value(person)
        if not party_res or not parent_res or party_res == parent_res:
            continue
        parent_label = "father" if relationship == "FATHER" else "mother"
        issues.append({
            "line": _residence_line(person),
            **says("MRA001", f"{parent_label}_{party_label}", parent=repr(parent_res), party=repr(party_res)),
        })
    return issues


def _collect(tree: ast.AST) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if isinstance(node, ast.Call) and _call_func_name(node) == "marriage":
            issues.extend(_check_marriage(node))
    return issues


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
    return [{"level": "error", "line": i["line"], "message": i["message"]}
            for i in _collect(tree)]


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
