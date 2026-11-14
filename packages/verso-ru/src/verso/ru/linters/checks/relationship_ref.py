#!/usr/bin/env python3
"""AST-based linter to validate `relationship_ref` strings on `relative()`
calls inside DSL records (birth/marriage/death) against a fixed allowlist.

The downstream translator (`tf_translator.py`, `csv_familio_exporters.py`)
only recognizes a small set of canonical refs; deviations silently fail to
wire up the relative.
"""

import ast
import re
import sys
from pathlib import Path
from verso.ru.linters.issue import as_dict, issue as finding, line_text, says
from verso.ru.linters.checks import shared_ast

# Exact-match allowlist
_ALLOWED_EXACT = {
    "жених",         # marriage: groom's relative  # i18n: content — the reference words the DSL writes
    "невеста",       # marriage: bride's relative  # i18n: content — the reference words the DSL writes
    "мать",          # birth: child's mother as a separate relative  # i18n: content — the reference words the DSL writes
    # NB spelled correctly but NOT wired: the translator resolves only
    # "восприемника №N", so a relative refd this way gets no relationship
    # edge. RLA001 (relative_attachment) flags that; this allowlist is
    # about spelling alone.
    "восприемница",  # birth: female godparent (witness)  # i18n: content — the reference words the DSL writes
}

# Pattern allowlist (regex)
_ALLOWED_PATTERN = re.compile(
    r"^(восприемника|поручитель) №\d+$",  # birth: godparent #N; marriage: поручитель #N  # i18n: content — the reference words the DSL writes
)


def is_allowed(ref: str) -> bool:
    return ref in _ALLOWED_EXACT or bool(_ALLOWED_PATTERN.match(ref))


def suggest(ref: str) -> str | None:
    """Return a canonical suggestion for known typo classes, else None."""
    # "восприемника N" missing №
    m = re.match(r"^восприемника (\d+)$", ref)  # i18n: content — the reference words the DSL writes
    if m:
        return f"восприемника №{m.group(1)}"  # i18n: content — the reference words the DSL writes
    # "воспреемника …" misspelling (drops 'и')
    if ref.startswith("воспреемника "):  # i18n: content — the reference words the DSL writes
        rest = ref[len("воспреемника "):]  # i18n: content — the reference words the DSL writes
        candidate = f"восприемника {rest}"  # i18n: content — the reference words the DSL writes
        if is_allowed(candidate):
            return candidate
        # try also fixing the № at the same time
        m = re.match(r"^(\d+)$", rest)
        if m:
            return f"восприемника №{m.group(1)}"  # i18n: content — the reference words the DSL writes
    if ref == "невесты":  # i18n: content — the reference words the DSL writes
        return "невеста"  # i18n: content — the reference words the DSL writes
    if ref == "женихa" or ref == "жениха":  # i18n: content — the reference words the DSL writes
        return "жених"  # i18n: content — the reference words the DSL writes
    return None


def said(ref: str) -> dict[str, object]:
    suggestion = suggest(ref)
    if suggestion:
        return says("REL001", "suggest", ref=ref, suggestion=suggestion)
    return says("REL002", "allowed", ref=ref, allowed=", ".join(f'"{s}"' for s in sorted(_ALLOWED_EXACT)))


def _format_message(ref: str) -> str:
    return str(said(ref)["message"])


def _extract_ref(call_node: ast.Call) -> tuple[str, int] | None:
    """Return (ref_value, line) if a string-literal relationship_ref is set
    on this `relative(...)` call. Skip when missing or non-literal."""
    # kwarg form
    for kw in call_node.keywords:
        if kw.arg == "relationship_ref":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value, kw.value.lineno
            return None
    # positional form: relative(person, relationship, ref)
    if len(call_node.args) >= 3:
        node = call_node.args[2]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, node.lineno
    return None


def _is_relative_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
    return name == "relative"


class RelationshipRefChecker(shared_ast.Visitor):
    """Walk a DSL file and validate `relationship_ref` on every `relative(...)`
    call that appears as an element of a `relatives=[...]` list inside a
    `birth(...)`, `marriage(...)`, or `death(...)` record."""

    RECORD_FUNCS = ("birth", "marriage", "death")

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.violations: list[tuple[int, str, str | None]] = []  # (line, ref, suggestion)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if func_name in self.RECORD_FUNCS:
            for kw in node.keywords:
                if kw.arg == "relatives" and isinstance(kw.value, ast.List):
                    for elt in kw.value.elts:
                        if not _is_relative_call(elt):
                            continue
                        extracted = _extract_ref(elt)
                        if extracted is None:
                            continue
                        ref, line = extracted
                        if not is_allowed(ref):
                            self.violations.append((line, ref, suggest(ref)))
        self.generic_visit(node)


def check_file(filepath: Path) -> list[str]:
    """Return list of `path:line: message` errors."""
    try:
        tree = shared_ast.parse(Path(filepath).read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [line_text(filepath, finding("SYN001", "detail", e.lineno, level="error", detail=e.msg))]
    checker = RelationshipRefChecker(Path(filepath))
    checker.visit(tree)
    return [
        f"{filepath}:{line}: {_format_message(ref)}"
        for line, ref, _ in checker.violations
    ]


def check_file_structured(filepath: Path) -> list[dict[str, object]]:
    """Return list of structured issue dicts with optional fix payloads."""
    try:
        tree = shared_ast.parse(Path(filepath).read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [as_dict(finding("SYN001", "detail", e.lineno or 1, level="error", detail=e.msg))]
    checker = RelationshipRefChecker(Path(filepath))
    checker.visit(tree)
    issues: list[dict[str, object]] = []
    for line, ref, suggestion in checker.violations:
        issue: dict[str, object] = {
            "level": "error",
            "line": line,
            **said(ref),
        }
        if suggestion:
            issue["fix"] = {
                "type": "replace_kwarg",
                "old": f'"{ref}"',
                "new": f'"{suggestion}"',
            }
        issues.append(issue)
    return issues


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.py> ...", file=sys.stderr)
        return 1

    errors: list[str] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_file() and p.suffix == ".py":
            errors.extend(check_file(p))

    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
