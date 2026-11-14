#!/usr/bin/env python3
"""AST-based linter for `parent_member` misuse on census
`member()` / `CensusMember(...)` calls. Two rules:

PM001 — redundant `parent_member`.
`parent_member` is the explicit upward parent link. For child roles the
translator already derives the parent from `ref_member` (see
`_resolve_parent_ref` in tf_translator.py — for SON/DAUGHTER, `ref_member`
IS the parent). So when `parent_member` is given AND equals `ref_member`
ON A CHILD ROLE it carries no extra information: `ref_member` alone suffices.
For every other role the translator does NOT treat `ref_member` as the
parent — on a GRANDSON/NEPHEW whose ref happens to BE the father (the 1897
посемейные списки shape, see census_parent_link CPL001), `parent_member`
equal to `ref_member` is load-bearing: it is the only thing that emits the
parent union. PM001 therefore fires only on SON/DAUGHTER/STEPSON/
STEPDAUGHTER. `parent_member` pointing at a DIFFERENT member than
`ref_member` is always meaningful (e.g. a step-child whose `ref_member` is
the step-parent, or a member whose parent is a hidden ancestor).

PM002 — married-in spouse sharing their partner's parent.
A WIFE/HUSBAND who married into the household has parents living in ANOTHER
household, so their `parent_member` must not point at an in-household parent.
The specific bug this catches: a spouse given the SAME parent as their partner
(`ref_member`) — e.g. a wife whose `parent_member` equals her husband's parent,
making her a child of her own father-in-law (two pairs of parents on Geni).
This is household-aware: it does NOT flag legitimate uxorilocal cases (a
`SON_IN_LAW` who married in, whose wife correctly points at her own father, the
head) because there the partner has no in-household parent. Use `father_ref`
when a married-in spouse's parent genuinely needs linking across households.

Run:
    python3 check_parent_member.py FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from verso.ru.linters.issue import as_dict, Issue, issue, line_text
from verso.ru.linters.checks import shared_ast


_TARGETS = {"member", "CensusMember"}
SPOUSE_ROLES = {"WIFE", "HUSBAND"}
# Roles where `ref_member` itself encodes the parent (mirrors the
# SON/DAUGHTER branch of `_resolve_parent_ref` in tf_translator.py). Used to
# resolve a partner's parent when they carry no explicit `parent_member`.
REF_IS_PARENT_ROLES = {"SON", "DAUGHTER", "STEPSON", "STEPDAUGHTER"}
# `member(number, person, role, ref_member, …, parent_member=…)`: the places of the
# arguments read here when written positionally (tests/test_check_parent_member.py
# holds them to the factory's signature).
ROLE_AT, REF_MEMBER_AT, PARENT_MEMBER_AT = 2, 3, 18


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


def _arg(node: ast.Call, index: int, name: str) -> ast.expr | None:
    kw = _kwargs(node).get(name)
    if kw is not None:
        return kw.value
    return node.args[index] if len(node.args) > index else None


def _int_literal(node: ast.expr) -> int | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _int_literal(node.operand)  # a hidden member's -1, -2…
        return -operand if operand is not None else None
    # `bool` is a subclass of `int` — exclude it.
    if (isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)):
        return node.value
    return None


def _role_name(node: ast.Call) -> str | None:
    # role is the 3rd positional arg in member()/CensusMember(), or a kwarg.
    role_expr = _arg(node, ROLE_AT, "role")
    if isinstance(role_expr, ast.Attribute):
        return role_expr.attr
    return None


def _member_number(node: ast.Call) -> int | None:
    if node.args:
        return _int_literal(node.args[0])
    return None


def _resolved_parent(node: ast.Call) -> int | None:
    """Member number this member descends from, or None — explicit
    `parent_member` wins, else `ref_member` for roles where it IS the parent."""
    pm = _arg(node, PARENT_MEMBER_AT, "parent_member")
    if pm is not None:
        pm_v = _int_literal(pm)
        if pm_v is not None:
            return pm_v
    rm = _arg(node, REF_MEMBER_AT, "ref_member")
    if _role_name(node) in REF_IS_PARENT_ROLES and rm is not None:
        return _int_literal(rm)
    return None


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

    # PM001: redundant parent_member == ref_member (per-call, no context).
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_func_name(node) not in _TARGETS:
            continue

        pm = _arg(node, PARENT_MEMBER_AT, "parent_member")
        rm = _arg(node, REF_MEMBER_AT, "ref_member")
        if pm is None or rm is None:
            continue
        if _role_name(node) not in REF_IS_PARENT_ROLES:
            # ref_member is NOT the parent for these roles, so an equal
            # parent_member is load-bearing (it alone emits the union).
            continue
        pm_v = _int_literal(pm)
        rm_v = _int_literal(rm)
        if pm_v is not None and rm_v is not None and pm_v == rm_v:
            errors.append(issue("PM001", "redundant", pm.lineno, level="error", member=pm_v))

    # PM002: a married-in spouse sharing their partner's parent — needs the
    # whole household to resolve the partner (ref_member) and its parent.
    for hh in shared_ast.walk(tree):
        if not (isinstance(hh, ast.Call) and _call_func_name(hh) == "household"):
            continue
        members: dict[int, ast.Call] = {}
        for arg in hh.args:
            if isinstance(arg, ast.Call) and _call_func_name(arg) in _TARGETS:
                num = _member_number(arg)
                if num is not None:
                    members[num] = arg
        for member_node in members.values():
            if _role_name(member_node) not in SPOUSE_ROLES:
                continue
            pm = _arg(member_node, PARENT_MEMBER_AT, "parent_member")
            rm = _arg(member_node, REF_MEMBER_AT, "ref_member")
            if pm is None or rm is None:
                continue
            pm_v = _int_literal(pm)
            rm_v = _int_literal(rm)
            partner = members.get(rm_v) if rm_v is not None else None
            if pm_v is None or partner is None:
                continue
            if _resolved_parent(partner) == pm_v:
                errors.append(issue("PM002", "partners_parent", pm.lineno, level="error", member=pm_v,
                                    role=str(_role_name(member_node)), partner=rm_v))

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
