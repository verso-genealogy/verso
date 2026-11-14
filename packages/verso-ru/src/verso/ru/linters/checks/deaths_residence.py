#!/usr/bin/env python3
"""AST-based linter that checks residence alignment between the deceased and the
relative(s) named in a `death()` record.

Everyone named in a death entry belongs to ONE household: the deceased and the
kin recorded as their отец / муж / мать / свекор / … A relative is named in a
death record precisely because the deceased belongs to that household, so all
relationship types imply a shared residence village.

`Death.__init__` (dsl/records/deaths.py) therefore derives a *household
residence* — the first relative's residence, else the deceased's own — and fills
it in for whoever lacks one, before `RecordDefaults` can substitute the parish
village. This linter covers the two cases that derivation cannot decide:

  [DRA001] Two explicit residences in one record that DISAGREE. Inheritance
           never overwrites an explicit value, so the record ships a household
           living in two villages — one of the two literals is wrong.

  [DRA002] A RELATIVE's explicit `residence=` REPEATS the deceased's. The
           deceased is the record's subject and the preferred carrier of the
           household residence in the DSL; the relative's copy is redundant —
           the generator derives it for free (mirroring birth_redundancy.py).
           A relative-ONLY residence is fine: it is then the anchor the
           deceased inherits from.
           Silent in a record DRA001 fires on: the generator's anchor is the
           FIRST relative stating a residence, so a removed copy could take
           the contradicting village instead of the deceased's.

DRA002's message starts with `redundant residence=` so dsllint.py turns it into a
`remove_kwarg` quick-fix. A `person()` written with positional args is flagged
without a fix (a kwarg fix would corrupt the call), same as birth_redundancy.

Scope is the deceased + relatives only. Witnesses and clergy are exempt: they
routinely come from other villages. A relative's residence merely repeating the
record-level `RecordDefaults(residence=...)` is a different concern and is not
flagged here.

Run:
    python3 -m verso.ru.linters.checks.deaths_residence FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from verso.ru.linters.issue import issue as finding, line_text, says
from verso.ru.linters.checks import shared_ast

# `death(record_num, gender, d_day, b_day, d_month, b_month, deceased, age, relatives, …)`:
# the places of the arguments read here when written positionally
# (tests/test_check_deaths_residence.py holds them to the factory's signature).
DECEASED_AT, RELATIVES_AT = 6, 8


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


def _residence_value(person_node: ast.Call) -> str | None:
    """`residence=` kwarg literal, else positional index 6 of person()."""
    pkw = _kwargs(person_node)
    if "residence" in pkw:
        return _string_literal(pkw["residence"].value)
    if len(person_node.args) >= 7:
        return _string_literal(person_node.args[6])
    return None


def _person_kwarg(kwargs: dict[str, ast.keyword], role: str) -> ast.Call | None:
    kw = kwargs.get(role)
    if kw is None or not isinstance(kw.value, ast.Call):
        return None
    if _call_func_name(kw.value) != "person":
        return None
    return kw.value


def _relative_persons(node: ast.Call) -> list[ast.Call]:
    """Every relative's person() in a death() call's
    `relatives=[relative(person(...), Relationship.X), ...]` (or the list in its
    positional place), in DSL order."""
    listed: list[ast.Call] = []
    rels = _arg(node, RELATIVES_AT, "relatives")
    if isinstance(rels, ast.List):
        for elt in rels.elts:
            if not isinstance(elt, ast.Call):
                continue
            if _call_func_name(elt) in ("relative", "Relative"):
                person = _person_kwarg(_kwargs(elt), "person")
                if person is None and elt.args and isinstance(elt.args[0], ast.Call):
                    cand = elt.args[0]
                    if _call_func_name(cand) == "person":
                        person = cand
                if person is not None:
                    listed.append(person)
    return listed


def _residence_line(person_node: ast.Call) -> int:
    """Line to anchor a message on: the `residence=` kwarg if written as one,
    else the person() call itself (positional form)."""
    res_kw = _kwargs(person_node).get("residence")
    return res_kw.value.lineno if res_kw is not None else person_node.lineno


def _char_col(lines: list[str], lineno: int, byte_col: int) -> int:
    """Convert a 0-based AST col_offset (UTF-8 byte offset) to a char column.
    DSL lines contain Cyrillic (multi-byte), so the byte offset overshoots."""
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


def _check_death(node: ast.Call, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    value = _arg(node, DECEASED_AT, "deceased")
    deceased = value if isinstance(value, ast.Call) and _call_func_name(value) == "person" else None
    relatives = _relative_persons(node)
    if not relatives:
        return issues

    deceased_res = _residence_value(deceased) if deceased is not None else None

    # Household anchor: the record's SUBJECT is the deceased, so their explicit
    # residence is the preferred carrier; a record stating it only against a
    # relative anchors there instead (Death.__init__ derives the same household
    # value either way).
    anchor = deceased_res
    if anchor is None:
        anchor = next(
            (v for rel in relatives if (v := _residence_value(rel))), None)
    if anchor is None:
        return issues  # nothing to align against

    # A record DRA001 fires on says nothing redundant: `Death.__init__` gives a relative without a residence the
    # FIRST relative's that states one, so a residence removed under DRA002 could take the contradicting village.
    contradicted = any((v := _residence_value(rel)) and v != anchor for rel in relatives)
    for rel in relatives:
        val = _residence_value(rel)
        if not val:
            continue
        # --- DRA001: an explicit residence contradicting the anchor ---
        if val != anchor:
            issues.append({
                "level": "error",
                "line": _residence_line(rel),
                **says("DRA001", "contradicts", val=repr(val), anchor=repr(anchor)),
            })
            continue
        # --- DRA002: relative repeats the deceased's residence ---
        # Only against the DECEASED's explicit value: the deceased keeps the
        # residence in the DSL; a relative restating it is the redundant copy
        # (Death.__init__ derives it). A relative-only residence is the anchor
        # itself and stays.
        if deceased_res is None or val != deceased_res or contradicted:
            continue
        res_kw = _kwargs(rel).get("residence")
        if res_kw is not None:  # kwarg form → remove fix, col-pinned: the
            # deceased's own residence kwarg may sit earlier on the same line.
            issues.append({
                "line": res_kw.value.lineno,
                **says("DRA002", "redundant", val=val),
                "fix": {"type": "remove_kwarg", "kwarg": "residence",
                        "col": _char_col(lines, res_kw.lineno, res_kw.col_offset)},
            })
        else:  # positional form → flag without a (broken) kwarg fix
            issues.append({
                "line": rel.lineno,
                **says("DRA002", "redundant_positional", val=repr(val)),
            })

    return issues


def _collect(tree: ast.AST, lines: list[str] | None = None) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if isinstance(node, ast.Call) and _call_func_name(node) == "death":
            issues.extend(_check_death(node, lines or []))
    return issues


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, finding("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}"
            for i in _collect(tree, src.splitlines())]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    out: list[dict[str, object]] = []
    for i in _collect(tree, src.splitlines()):
        # Split severities: DRA001 (contradictory villages — a true data error)
        # carries "error" from its emission site and shows red in the IDE;
        # DRA002 (redundant kwarg) defaults to "warn" and shows yellow, like
        # ULC001. Text mode / CI stays advisory for both.
        issue: dict[str, object] = {
            "level": i.get("level", "warn"), "line": i["line"], "message": i["message"],
        }
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
