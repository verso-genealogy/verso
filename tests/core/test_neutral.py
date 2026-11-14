"""The core is neutral: no string of its code holds Cyrillic — its messages are its
catalogs' (`verso/core/locales/`), the Russian domain the plugin's. Docstrings and comments may
name the books."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import verso.core

_CYRILLIC = re.compile(r"[\u0400-\u04FF]")   # the whole block: і ѣ ѳ ѵ too


def _docstrings(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                out.add(id(first.value))
    return out


def test_core_code_has_no_cyrillic():
    root = Path(verso.core.__file__).parent
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                    and _CYRILLIC.search(node.value):
                found.append(f"{path.relative_to(root)}:{node.lineno}: {node.value[:60]!r}")
    assert found == [], "\n" + "\n".join(found)
