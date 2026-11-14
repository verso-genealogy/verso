#!/usr/bin/env python3
"""AST-based linter (ULC001) that WARNS when a DSL record names a place that is
not among the corpus's places (`corpus/places.toml`, `verso.core.places`).

The Terraform generator resolves every residence / parish village through
`locations.get(name)` (see `verso.ru.targets.geni.translator.res_names._location`,
called for child/father/mother/godparent/relative residences plus the parish
and birth-event locations). An unmapped name silently resolves to `None`, so the
profile or event gets **no location block** in the generated `.tf` — the place is
quietly dropped. This check surfaces those names so they can be added to
the corpus's places or the residence string normalised to a known key.

It is a WARNING, not an error: an unmapped location is lossy but not invalid, and
some one-off foreign residences may legitimately stay unmapped.

Scope: only files whose own parish `village` is itself a known location key —
i.e. villages that are set up for Terraform generation. CSV-only villages (e.g.
a village whose parish is not among the corpus's places) never go through the location
map, so their residence strings are not flagged. The check deliberately reads
this from the record content (NOT the file path) so it works identically when an
IDE plugin lints an unsaved buffer via a temp file.

Checked inputs (all flow to `_location()`):
  * `person(..., residence="X")`            — kwarg or positional index 6
  * `RecordDefaults(residence="X")`         — record-level residence default
  * `<...>_records(..., village, ...)`      — parish village (positional 4 / village=)
  * `member(..., origin="X")`               — kwarg or positional index 8; becomes
    the census member's birth location AND feeds Geni project assignment
  * `member(..., destination="X")`          — kwarg or positional index 9; overrides
    the member's current residence

Run:
    python3 -m verso.ru.linters.checks.unmapped_location FILE [FILE...]
"""

import ast
import sys
from collections.abc import Mapping
from pathlib import Path

from verso.ru.linters.checks.file_bindings import module_bindings, record_defaults_call
from verso.core import places
from verso.ru.linters.issue import issue as finding, line_text, says
from verso.ru.linters.checks import shared_ast


# Record-list factories that carry a parish `village` and (births/deaths/
# marriages) a `defaults=RecordDefaults(residence=...)`.
_RECORD_CALLS = ("birth_records", "death_records", "marriage_records", "census_records")


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def _string_literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _person_residence(node: ast.Call) -> ast.expr | None:
    """`residence=` kwarg, else positional index 6 of person()."""
    pkw = _kwargs(node)
    if "residence" in pkw:
        return pkw["residence"].value
    if len(node.args) >= 7:
        return node.args[6]
    return None


def _member_place(node: ast.Call, kwarg: str, index: int) -> ast.expr | None:
    """A member() place argument by kwarg name, else positional index.
    member(number, person, role, ref_member, age, previous_age,
    marital_status, occupation, origin, destination, ...)."""
    mkw = _kwargs(node)
    if kwarg in mkw:
        return mkw[kwarg].value
    if len(node.args) > index:
        return node.args[index]
    return None


def _record_village(node: ast.Call) -> ast.expr | None:
    """Parish `village`: `village=` kwarg, else positional index 4."""
    vkw = _kwargs(node).get("village")
    if vkw is not None:
        return vkw.value
    if len(node.args) >= 5:
        return node.args[4]
    return None


def _record_defaults_residence(node: ast.Call,
                               bindings: Mapping[str, ast.expr]) -> ast.expr | None:
    """`defaults=RecordDefaults(residence=...)` on a record-list call, written in
    the call or bound by name at the top of the file."""
    defaults = record_defaults_call(node, bindings)
    if defaults is None:
        return None
    res = _kwargs(defaults).get("residence")
    return res.value if res is not None else None


def _char_col(lines: list[str], lineno: int, byte_col: int) -> int:
    """Convert a 0-based AST col_offset (UTF-8 byte offset) to a char column.
    DSL lines contain Cyrillic (multi-byte), so the byte offset overshoots."""
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


class UnmappedLocationChecker(shared_ast.Visitor):
    def __init__(self, lines: list[str] | None = None) -> None:
        self.issues: list[dict[str, object]] = []
        self._lines = lines or []
        self._bindings: dict[str, ast.expr] = {}

    def _flag(self, node: ast.expr | None, kind: str) -> None:
        if node is None:
            return
        value = _string_literal(node)
        if not value:  # "" / non-literal — nothing to check
            return
        if value in places.current().bodies:
            return
        issue: dict[str, object] = {
            "line": node.lineno,
            **says("ULC001", kind.replace(" ", "_"), token=value, place=value),   # the variant: the field it stands in
        }
        # Pin the exact string literal (char columns) so IDE plugins highlight
        # THIS occurrence — the same place name may appear earlier on the line
        # (e.g. inside departure_reason prose).
        if node.end_lineno == node.lineno and node.end_col_offset is not None:
            issue["col"] = _char_col(self._lines, node.lineno, node.col_offset)
            issue["end_col"] = _char_col(self._lines, node.lineno, node.end_col_offset)
        self.issues.append(issue)

    def visit_Module(self, node: ast.Module) -> None:
        self._bindings = module_bindings(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fname = _call_func_name(node)
        if fname == "person":
            self._flag(_person_residence(node), "residence")
        elif fname == "member":
            self._flag(_member_place(node, "origin", 8), "origin")
            self._flag(_member_place(node, "destination", 9), "destination")
        elif fname in _RECORD_CALLS:
            self._flag(_record_village(node), "parish village")
            self._flag(_record_defaults_residence(node, self._bindings), "default residence")
        self.generic_visit(node)


def _file_in_scope(tree: ast.AST) -> bool:
    """True when the file is for a Terraform-generated village, judged from the
    record content (not the path): some record-list call's parish `village` is a
    known place of the corpus. CSV-only villages (parish absent from the places) and
    files without a record-list call are out of scope. Path-independent, so it
    behaves the same whether linting the file on disk or a temp-file copy of an
    unsaved editor buffer (how the IntelliJ plugin invokes the linter)."""
    for node in shared_ast.walk(tree):
        if isinstance(node, ast.Call) and _call_func_name(node) in _RECORD_CALLS:
            village = _string_literal(_record_village(node))
            if village and village in places.current().bodies:
                return True
    return False


def _collect(tree: ast.AST, lines: list[str] | None = None) -> list[dict[str, object]]:
    if not _file_in_scope(tree):
        return []
    checker = UnmappedLocationChecker(lines)
    checker.visit(tree)
    return checker.issues


def check_file(path: Path) -> list[str]:
    path = Path(path)
    try:
        src = path.read_text(encoding="utf-8")
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, finding("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}"
            for i in _collect(tree, src.splitlines())]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    path = Path(path)
    try:
        src = path.read_text(encoding="utf-8")
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    out: list[dict[str, object]] = []
    for i in _collect(tree, src.splitlines()):
        issue: dict[str, object] = {
            "level": "warn", "line": i["line"], "message": i["message"]}
        if "col" in i:
            issue["col"] = i["col"]
            issue["end_col"] = i["end_col"]
        out.append(issue)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    warnings: list[str] = []
    for arg in sys.argv[1:]:
        warnings.extend(check_file(Path(arg)))
    for w in warnings:
        print(w)
    # ULC001 is advisory — never fail the build on warnings.
    return 0


if __name__ == "__main__":
    sys.exit(main())
