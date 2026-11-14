#!/usr/bin/env python3
"""CSR001 — AST linter that flags a redundant explicit ``status=`` on a census
``member()``'s ``person()`` when the enclosing ``census_records(...,
defaults=RecordDefaults(...))`` would apply the identical status by default.

``census_records()`` (verso/ru/dsl/records/census.py) applies its ``defaults`` to
every member's person via ``RecordDefaults.apply_to_person`` — which, for a
person with no explicit status, fills:

  - gender == FEMALE and ``status_female`` is set → ``status_female``
  - otherwise (male, or female with no ``status_female``) → ``status_male``

So when a DSL author writes that same status explicitly on a member, it is
redundant: removing it re-applies the *identical* constant by default, a true
no-op (same document text, same profile). This makes CSR001 **AUTO-FIXABLE**
(level=error + remove fix), mirroring CRD001's patronymic rule.

Byte-neutrality guards (why removal is always safe when we flag):

  * We compare by the argument's *source form* (``ast.unparse``), so a match
    means the member would inherit the very same token — never a look-alike
    alias we can't resolve statically. Divergent tokens are left alone.
  * We resolve the member's gender the way the pipeline does *without* the
    status (explicit ``gender=`` → role-implied → first-name), via CRD001's
    shared ``_gender``. If that is ambiguous (``None``) the status may be
    load-bearing for gender inference (the hidden-ancestor case,
    Person.__init__), so we skip — removal could flip the default.
  * ``hidden=True`` members and members whose status token diverges from the
    default are never flagged.

Only a ``census_records(...)`` that carries a ``defaults=RecordDefaults(...)``
with ``status_male``/``status_female`` can produce findings; files that set
every member's status explicitly with no defaults block produce none.

To stay in lockstep with the generator this check reuses CRD001's member/
gender helpers rather than re-listing role→gender rules.

Run:
    python3 -m verso.ru.linters.checks.census_status_redundancy FILE [FILE...]
"""

import ast
import sys
from collections.abc import Mapping
from pathlib import Path

from verso.ru.gender import Gender
# Reuse CRD001's helpers so gender/role resolution can never drift from the
# generator (single source of truth, mirrors census_redundancy's own imports).
from verso.ru.linters.checks.census_redundancy import (
    _Member, _call_func_name, _char_col, _gender, _kwargs, _person_arg)
from verso.ru.linters.checks.file_bindings import module_bindings, record_defaults_call
from verso.ru.linters.issue import as_dict, issue as finding, line_text
from verso.ru.linters.checks import shared_ast

# person(name_orig, patr_orig, last_name_orig, name_modern_orth, patr_old,
#        last_name_modern_orth, residence, status, gender, ...) — status is
# positional index 7.
_STATUS_INDEX = 7
# RecordDefaults(residence, status_male, status_female, status_bride,
# status_groom, status_mother, cause_of_death) — positional order. CSR001 reads
# only the two gendered fields; the slot-specific ones are here because
# status_redundancy (VSR001) shares `_default_arg`.
_DEFAULT_INDEX = {
    "residence": 0,
    "status_male": 1,
    "status_female": 2,
    "status_bride": 3,
    "status_groom": 4,
    "status_mother": 5,
    "cause_of_death": 6,
}


def _default_arg(defaults_node: ast.Call, name: str) -> ast.expr | None:
    """A ``RecordDefaults(...)`` field value node by kwarg, else positional."""
    dkw = _kwargs(defaults_node)
    if name in dkw:
        return dkw[name].value
    idx = _DEFAULT_INDEX.get(name)
    if idx is not None and len(defaults_node.args) > idx:
        return defaults_node.args[idx]
    return None


def _extract_defaults(records_node: ast.Call, bindings: Mapping[str, ast.expr]
                      ) -> tuple[ast.expr | None, ast.expr | None]:
    """(status_male_node, status_female_node) from ``defaults=RecordDefaults(...)``,
    written in the call or bound by name at the top of the file."""
    defaults = record_defaults_call(records_node, bindings)
    if defaults is None:
        return None, None
    return _default_arg(defaults, "status_male"), _default_arg(defaults, "status_female")


def _census_members(records_node: ast.Call) -> list[_Member]:
    return [
        _Member(node)
        for node in shared_ast.walk(records_node)
        if isinstance(node, ast.Call) and _call_func_name(node) == "member"
    ]


def _status_node(person_node: ast.Call) -> ast.expr | None:
    return _person_arg(person_node, _STATUS_INDEX, "status")


def _status_fix(person_node: ast.Call, lines: list[str]) -> dict[str, object] | None:
    """Removal fix for the person's ``status``. kwarg → remove_kwarg; a positional
    status → remove_arg only when it is the LAST positional (else a later
    positional would shift into its slot)."""
    kw = _kwargs(person_node).get("status")
    if kw is not None:
        return {"type": "remove_kwarg", "kwarg": "status",
                "col": _char_col(lines, kw.lineno, kw.col_offset)}
    if len(person_node.args) > _STATUS_INDEX and _STATUS_INDEX == len(person_node.args) - 1:
        arg = person_node.args[_STATUS_INDEX]
        if arg.end_lineno == arg.lineno and arg.end_col_offset is not None:
            return {"type": "remove_arg", "kwarg": "status",
                    "col": _char_col(lines, arg.lineno, arg.col_offset),
                    "end_col": _char_col(lines, arg.lineno, arg.end_col_offset)}
    return None


def _collect(tree: ast.AST, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    bindings = module_bindings(tree)
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_func_name(node) != "census_records":
            continue
        status_male, status_female = _extract_defaults(node, bindings)
        if status_male is None and status_female is None:
            continue

        for m in _census_members(node):
            if m.person is None or m.hidden:
                continue
            explicit = _status_node(m.person)
            if explicit is None:
                continue
            gender = _gender(m)
            if gender is None:
                # Ambiguous gender — the status may be load-bearing for gender
                # inference; removal could flip which default applies. Skip.
                continue
            # Mirror RecordDefaults.apply_to_person's status selection exactly.
            if gender == Gender.FEMALE.name and status_female is not None:
                effective, field = status_female, "status_female"
            elif status_male is not None:
                effective, field = status_male, "status_male"
            else:
                continue
            if ast.unparse(explicit) != ast.unparse(effective):
                continue
            role = (m.role or "").lower()
            fix = _status_fix(m.person, lines)
            issues.append(as_dict(finding("CSR001", "redundant", explicit.lineno, level="error", fix=fix or None,
                                        status=ast.unparse(explicit), role=role or "member", field=field)))

    issues.sort(key=lambda i: (i["line"], str(i["message"])))
    return issues


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [as_dict(finding("SYN001", "detail", e.lineno or 1, level="error", detail=e.msg))]
    out: list[dict[str, object]] = []
    for i in _collect(tree, src.splitlines()):
        issue = {"level": i.get("level", "error"), "line": i["line"], "message": i["message"]}
        if i.get("fix"):
            issue["fix"] = i["fix"]
        out.append(issue)
    return out


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, finding("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree, src.splitlines())]


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
