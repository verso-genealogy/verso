"""What the code tells a person to type names a `verso` command — never an old module."""
from __future__ import annotations

import ast
import re
from pathlib import Path


from verso.core.cli import commands
from tests.codepaths import code_files, module_name, package_dir

OLD = re.compile(r"-m geni\b|python3? -m geni\.")
COMMAND = re.compile(r"(?<![\w.-])verso ([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\b")
# «verso» in prose is also a leaf's back side: «two, verso and recto», «its verso is present».
PROSE = frozenset({"and", "is", "was", "only"})


def _strings() -> list[tuple[str, int, str]]:
    found = []
    for path in code_files("verso.core", "verso.ru"):
        rel = module_name(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.append((rel, node.lineno, node.value))
    return found


def test_no_printed_command_names_an_old_module():
    assert [f"{rel}:{line}" for rel, line, text in _strings() if OLD.search(text)] == []


def test_every_printed_verso_command_exists():
    known = set(commands())
    named = {(rel, line, m[1]) for rel, line, text in _strings() for m in COMMAND.finditer(text)
             if m[1] not in PROSE}
    assert {name for _, _, name in named} >= {"dsl-surface", "upgrade-dsl", "moved-blocks", "document-sync"}
    assert sorted(f"{rel}:{line} verso {name}" for rel, line, name in named if name not in known) == []


def _headed(path: Path) -> None:
    assert not OLD.search(path.read_text(encoding="utf-8")), path


def test_the_package_data_the_tools_headed_names_the_command():
    # The headers the tools wrote into committed files say what the tools say now.
    _headed(package_dir("verso.ru.church_calendar") / "data" / "svyatcy_1906.tsv")
