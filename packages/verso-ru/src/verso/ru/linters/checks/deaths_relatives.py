#!/usr/bin/env python3
"""AST-based linter guarding the ONE-relative limit of `death()` records.

`add_death_records` (terraform/translator/generator.py) emits a profile for
`d.relatives[0]` only — role `"relative"`, singular, plus the one union tying
that relative to the deceased. A second entry in `relatives=[...]` produces no
profile, no union and no mention in the document body: it vanishes without a
word, and nothing downstream can tell it was ever written.

  [DRL001] A `death()` record naming MORE than one relative. Everything past
           the first is silently dropped by the translator.

No such record exists in any village today (checked 2026-07-28 across
Горюхино / Заманиловка / Нижняя Яичница / Маниловка: 3219 death records, none with
a second relative), so this check costs nothing now and exists to make the
limit impossible to hit unnoticed later. Since 2026-10-09 a death names its
relative only in the list — the single `relative=` / `relationship=` slot is
gone — so a second entry is one «+ Родственник» away on the review page.

Note this is a LIMIT, not a rule about the sources. Should the translator grow
real multi-relative support, delete this check along with the limit. The hard
part there is the union: a second parent has to become `partner_2` of the SAME
union the first relative anchors, not a union of its own — otherwise the
deceased lands in two parent unions, which is the `duplicate_parents` conflict
that `census_parent_link`'s CPL004 and `verify_plan`'s multi-parent gate exist
to prevent.

Births and marriages are unaffected: both route extra kin through
`_emit_relatives`, which emits every entry as `rel_N`.

Run:
    python3 -m verso.ru.linters.checks.deaths_relatives FILE [FILE...]
"""

import ast
import sys
from pathlib import Path

from verso.ru.linters.checks.deaths_residence import (
    RELATIVES_AT, _arg, _call_func_name, _relative_persons)
from verso.ru.linters.issue import as_dict, issue, line_text
from verso.ru.linters.checks import shared_ast


def _relationship_label(node: ast.Call, index: int) -> str:
    """Best-effort name of relative #index for the message: `Relationship.X`
    renders as `X`, anything else as `#<n>`."""
    rels = _arg(node, RELATIVES_AT, "relatives")
    if not isinstance(rels, ast.List):
        return f"#{index + 1}"
    if index >= len(rels.elts):
        return f"#{index + 1}"
    elt = rels.elts[index]
    if not isinstance(elt, ast.Call):
        return f"#{index + 1}"
    args = list(elt.args) + [kw.value for kw in elt.keywords if kw.arg == "relationship"]
    for arg in args:
        if isinstance(arg, ast.Attribute):
            return arg.attr
    return f"#{index + 1}"


def _check_death(node: ast.Call) -> list[dict[str, object]]:
    relatives = _relative_persons(node)
    if len(relatives) < 2:
        return []

    # Anchor on the DROPPED entries, not on the record: the first relative is
    # emitted fine, so pointing at it would be misleading.
    kept = _relationship_label(node, 0)
    return [as_dict(issue("DRL001", "dropped", rel.lineno, level="error", relative=_relationship_label(node, i),
                          kept=kept))
            for i, rel in enumerate(relatives[1:], start=1)]


def _collect(tree: ast.AST) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if isinstance(node, ast.Call) and _call_func_name(node) == "death":
            issues.extend(_check_death(node))
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
    return [
        {"level": i.get("level", "error"), "line": i["line"], "message": i["message"]}
        for i in _collect(tree)
    ]


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
