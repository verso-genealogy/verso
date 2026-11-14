"""What a DSL file binds at its top level, for the checks that follow a name.

A book's `RecordDefaults` and its own status constants are often written once
at the head of the file and passed by name:

    GORELOVO_PEASANT = "крестьянин Экономического ведомства деревни Гореловой"
    DEFAULTS = RecordDefaults(residence="Глуповы Горы", status_male=PEASANT_MALE, …)
    …
    birth_records(…, defaults=DEFAULTS)

Every Глуповы Горы file does (220 of them), and no other village. A check
that read only `defaults=RecordDefaults(...)` written inside the call ran on
those files without knowing the book's defaults at all: until 2026-10-01 PSA
and VSR001 did, and hid 18 findings between them (two priests' wives on the
«крестьянка» default, sixteen redundant `status=`).

Not a module check — nothing here reports anything.
"""

import ast
from collections.abc import Mapping


def module_bindings(tree: ast.AST) -> dict[str, ast.expr]:
    """`NAME = <expr>` (or `NAME: T = <expr>`) at the top level of a module.

    A name bound more than once is left out: which value a call sees depends on
    where it stands, and guessing would make a check fire on the wrong one.
    """
    if not isinstance(tree, ast.Module):
        return {}
    seen: dict[str, ast.expr] = {}
    rebound: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets, value = [stmt.target], stmt.value
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in seen:
                rebound.add(target.id)
            seen[target.id] = value
    return {name: value for name, value in seen.items() if name not in rebound}


def string_constants(bindings: Mapping[str, ast.expr]) -> dict[str, str]:
    """The file's own string constants: `GORELOVO_PEASANT = "…"`."""
    return {name: value.value for name, value in bindings.items()
            if isinstance(value, ast.Constant) and isinstance(value.value, str)}


def _func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def record_defaults_call(records_node: ast.Call,
                         bindings: Mapping[str, ast.expr]) -> ast.Call | None:
    """The `RecordDefaults(...)` a records call's `defaults=` stands for —
    written in the call, or bound by name at the top of the file."""
    value = next((kw.value for kw in records_node.keywords if kw.arg == "defaults"), None)
    if isinstance(value, ast.Name):
        value = bindings.get(value.id)
    if isinstance(value, ast.Call) and _func_name(value) == "RecordDefaults":
        return value
    return None
