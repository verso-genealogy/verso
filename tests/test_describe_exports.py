"""What the App reads off verso.ru.dsl.describe beside describe() itself is re-exported explicitly:
with py.typed (0.1.1) a strict type checker refuses a name a module only imports."""
from __future__ import annotations

import ast
from importlib.util import find_spec
from pathlib import Path


def test_record_funcs_is_an_explicit_re_export():
    spec = find_spec("verso.ru.dsl.describe")
    assert spec is not None and spec.origin is not None
    tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
    aliases = [a for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for a in node.names
               if a.name == "RECORD_FUNCS"]
    assert aliases and all(a.asname == "RECORD_FUNCS" for a in aliases)
