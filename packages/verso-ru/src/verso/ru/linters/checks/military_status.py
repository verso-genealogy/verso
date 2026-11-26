"""AST-based linter (MIL001): a soldier's status written as free text.

A soldier's rank, a soldier's wife or widow, a soldier's son or daughter are catalog constants
(`SOLDIER`, `RETIRED_SOLDIER`, `SOLDIER_SPOUSE`, …): the status says WHO the person is, so it can be
parsed and standardized, and the scribe's own wording — «запасный рядовой», «уволенный в запас армии» —
goes in the member's `comment=`, which keeps the source's words (the maintainers' ruling of 2026-11-26).

MIL001 flags a `status=` (or a `RecordDefaults` form) that is a string literal, or a constant the file
defines itself, which `verso.ru.domain.military_status.classify` places on a catalog constant. The
message names the constant and the wording the comment should hold (the text in modern spelling). It
has no fix: the edit is two keyword arguments, so the bulk fix is the codemod. A catalog text, an
officer, a landlord's peasant and a cantonist are quiet (`classify` answers None).

Path-independent: scopes on kwargs and module-level bindings only.

Run:
    python3 -m verso.ru.linters.checks.military_status FILE [FILE...]
"""

import ast
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from verso.ru.domain.military_status import classify
from verso.ru.domain.orthography import modern_spelling
from verso.ru.linters.checks import shared_ast
from verso.ru.linters.checks.file_bindings import module_bindings, string_constants
from verso.ru.linters.checks.status_orthography import FIELDS
from verso.ru.linters.issue import as_dict, issue

# The classification fields a status of a soldier is written in: `status=` and its RecordDefaults forms.
STATUS_FIELDS = FIELDS - {"departure_reason"}


def _char_col(lines: Sequence[str], lineno: int, byte_col: int) -> int:
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


def _collect(tree: ast.AST, lines: Sequence[str]) -> list[dict[str, Any]]:
    bindings = module_bindings(tree)
    file_texts = string_constants(bindings)
    issues: list[dict[str, Any]] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg not in STATUS_FIELDS:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text, bound, pin = value.value, None, value
        elif isinstance(value, ast.Name) and value.id in file_texts:
            text, bound, pin = file_texts[value.id], value.id, bindings[value.id]
        else:
            continue
        constant = classify(text)
        if constant is None:
            continue
        span: dict[str, Any] = {}
        if pin.lineno == pin.end_lineno and pin.end_col_offset is not None:
            span = {"col": _char_col(lines, pin.lineno, pin.col_offset),
                    "end_col": _char_col(lines, pin.lineno, pin.end_col_offset)}
        params: dict[str, Any] = {"kwarg": node.arg, "text": text, "constant": constant,
                                  "comment": modern_spelling(text), **({"name": bound} if bound else {})}
        issues.append(as_dict(issue("MIL001", "bound" if bound else "literal", pin.lineno, level="error",
                                    token=text, **span, **params)))
    issues.sort(key=lambda i: i["line"])
    return issues


def check_file_structured(path: Path) -> list[dict[str, Any]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error
    return _collect(tree, src.splitlines())


def check_file(path: Path) -> list[str]:
    return [f"{path}:{i['line']}: {i['message']}" for i in check_file_structured(path)]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    errors: list[str] = []
    for arg in sys.argv[1:]:
        errors.extend(check_file(Path(arg)))
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
