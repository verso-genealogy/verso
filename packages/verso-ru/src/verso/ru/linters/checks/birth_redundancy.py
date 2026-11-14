#!/usr/bin/env python3
"""AST-based linter that flags redundant surname *and* residence kwargs on a
`birth()` record's `mother` / `child` when the generator would auto-derive the
identical value.

`Birth.__init__` (births.py) fills in a missing family surname:
  - mother  → feminize_surname(father.last_name_modern), last_name_in_book=False
  - son     → father.last_name_modern  (un-feminized)
  - daughter→ mother's surname else feminize_surname(father.last_name_modern),
              stored as birth_last_name_modern (Geni maiden_name)

So when a DSL author writes that same surname together with
`last_name_in_book=False`, the explicit surname is redundant — the generator
derives it for free. With `last_name_in_book=False` the book-form surname never
reaches generated output, so dropping it is safe (for daughters it normalizes the
surname into the maiden-name slot, which is the correct shape for a newborn girl).

Each flagged surname yields one of three coupled, single-kwarg removals that
converge to a bare `person("Имя", "Отчество", ...)`:
  redundant last_name_orig=…  →  (after removal) redundant last_name_modern_orth=…
                              →  (after removal) redundant last_name_in_book=False

`Birth.__init__` likewise propagates residence (a newborn lives where the family
lives):
  - mother → father.residence (when she has none of her own)
  - child  → father.residence else mother.residence

So an explicit `residence=X` on the mother (== father's) or on the child
(== the derived family residence) is redundant. Residence redundancy is pure
value equality — independent of `last_name_in_book`.

Messages start with `redundant <kwarg>=` so dsllint.py turns them into
`remove_kwarg` quick-fixes.

Run:
    python3 check_birth_redundancy.py FILE [FILE...]
"""

import ast
import sys
from pathlib import Path

from verso.ru.linters.checks.census_redundancy import _char_col
from verso.ru.naming import feminize_surname, modernize_orthography
from verso.ru.linters.issue import as_dict, issue as finding, line_text, says
from verso.core.i18n import Message
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def _string_literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_false(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _record_gender(birth_node: ast.Call) -> str | None:
    """Second positional arg of birth() is the record gender Gender.MALE/FEMALE."""
    if len(birth_node.args) < 2:
        return None
    g = birth_node.args[1]
    if (isinstance(g, ast.Attribute)
            and isinstance(g.value, ast.Name)
            and g.value.id == "Gender"):
        return g.attr
    return None


def _person_node(kwargs: dict[str, ast.keyword], role: str) -> ast.Call | None:
    kw = kwargs.get(role)
    if kw is None or not isinstance(kw.value, ast.Call):
        return None
    if _call_func_name(kw.value) != "person":
        return None
    return kw.value


def _effective_modern(person_node: ast.Call) -> str | None:
    """Modern surname a person would carry: last_name_modern_orth if given,
    else modernize(last_name_orig). None when the person has no surname."""
    pkw = _kwargs(person_node)
    modern = pkw.get("last_name_modern_orth")
    if modern is not None:
        return _string_literal(modern.value)
    orig = _orig_value(person_node)
    if orig is not None:
        return modernize_orthography(orig)
    return None


def _orig_value(person_node: ast.Call) -> str | None:
    """last_name_orig from kwarg, else positional index 2."""
    pkw = _kwargs(person_node)
    if "last_name_orig" in pkw:
        return _string_literal(pkw["last_name_orig"].value)
    if len(person_node.args) >= 3:
        return _string_literal(person_node.args[2])
    return None


def _residence_value(person_node: ast.Call) -> str | None:
    """residence from kwarg, else positional index 6 (person() signature)."""
    pkw = _kwargs(person_node)
    if "residence" in pkw:
        return _string_literal(pkw["residence"].value)
    if len(person_node.args) >= 7:
        return _string_literal(person_node.args[6])
    return None


def _kwarg_fix(kwarg: ast.keyword, lines: list[str]) -> dict[str, object]:
    """A removal of `kwarg`, with the CHARACTER column of `name=` that pins the
    occurrence — the review page finds the argument by it."""
    return {"type": "remove_kwarg", "kwarg": kwarg.arg,
            "col": _char_col(lines, kwarg.lineno, kwarg.col_offset)}


def _residence_issues(person_node: ast.Call, derived: str | None,
                      reason: Message, lines: list[str]) -> list[dict[str, object]]:
    """Flag an explicit `residence` that equals the value `Birth.__init__`
    would derive (`derived`). Pure value equality — no last_name_in_book gate.
    kwarg form → remove_kwarg fix; positional form → flag without a fix."""
    if not derived:
        return []
    val = _residence_value(person_node)
    if val is None or val != derived:
        return []
    res_kw = _kwargs(person_node).get("residence")
    if res_kw is not None:  # kwarg form → remove_kwarg fix
        return [{
            "line": res_kw.value.lineno,
            **says("BRD001", "residence", val=val, reason=reason),
            "fix": _kwarg_fix(res_kw, lines),
        }]
    # positional form → flag without a (broken) kwarg fix
    return [{
        "line": person_node.lineno,
        **says("BRD002", "residence_positional", val=val, reason=reason),
        "fix": None,
    }]


def _redundancy_issues(person_node: ast.Call, derived: str | None,
                       role: str, lines: list[str]) -> list[dict[str, object]]:
    """Apply the three condition-gated rules to one person against the surname
    `derived` the generator would auto-assign. Returns issue dicts."""
    if not derived:
        return []
    pkw = _kwargs(person_node)
    in_book = pkw.get("last_name_in_book")
    if in_book is None or not _is_false(in_book.value):
        return []  # gate: only when last_name_in_book=False is explicit

    orig_kw = pkw.get("last_name_orig")
    orig_val = _orig_value(person_node)
    modern_kw = pkw.get("last_name_modern_orth")
    has_surname = orig_val is not None or modern_kw is not None
    eff = _effective_modern(person_node)

    # Rule 1 — last_name_orig present and the effective surname matches.
    if orig_val is not None and eff == derived:
        if orig_kw is not None:  # kwarg form → remove_kwarg fix
            return [{
                "line": orig_kw.value.lineno,
                **says("BRD003", "surname", orig_val=orig_val, role=role),
                "fix": _kwarg_fix(orig_kw, lines),
            }]
        # positional form → flag without a (broken) kwarg fix
        return [{
            "line": person_node.lineno,
            **says("BRD004", "surname_positional", role=role, orig_val=orig_val),
            "fix": None,
        }]

    # Rule 2 — last_name_modern_orth only, matches.
    if orig_val is None and modern_kw is not None and eff == derived:
        return [{
            "line": modern_kw.value.lineno,
            **says("BRD005", "modern_surname", eff=eff, role=role),
            "fix": _kwarg_fix(modern_kw, lines),
        }]

    # Rule 3 — no surname at all; the generator will set last_name_in_book=False.
    if not has_surname:
        return [{
            "line": in_book.value.lineno,
            **says("BRD006", "in_book", role=role),
            "fix": _kwarg_fix(in_book, lines),
        }]

    return []


def _collect(tree: ast.AST, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_func_name(node) != "birth":
            continue
        kwargs = _kwargs(node)
        father = _person_node(kwargs, "father")
        mother = _person_node(kwargs, "mother")
        child = _person_node(kwargs, "child")

        # --- surname rules: need a father surname to derive from ---
        f = _effective_modern(father) if father is not None else None
        if f:
            if mother is not None:
                issues += _redundancy_issues(mother, feminize_surname(f), "mother", lines)
            if child is not None:
                gender = _record_gender(node)
                if gender == "MALE":
                    issues += _redundancy_issues(child, f, "son", lines)
                elif gender == "FEMALE":
                    mother_surname = _effective_modern(mother) if mother else None
                    derived = mother_surname or feminize_surname(f)
                    issues += _redundancy_issues(child, derived, "daughter", lines)

        # --- residence rules: pure value equality, independent of surnames ---
        father_res = _residence_value(father) if father is not None else None
        mother_res = _residence_value(mother) if mother is not None else None
        if mother is not None and father_res:
            issues += _residence_issues(
                mother, father_res, t("birth.mother_at_father"), lines)
        if child is not None:
            issues += _residence_issues(
                child, father_res or mother_res, t("birth.child_at_family"), lines)
    return issues


def check_file(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, finding("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree, src.splitlines())]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [as_dict(finding("SYN001", "detail", e.lineno or 1, level="error", detail=e.msg))]
    out: list[dict[str, object]] = []
    for i in _collect(tree, src.splitlines()):
        issue = {"level": "error", "line": i["line"], "message": i["message"]}
        if i.get("fix"):
            issue["fix"] = i["fix"]
        out.append(issue)
    return out


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
