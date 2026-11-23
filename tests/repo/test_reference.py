"""The library's reference (docs/reference) is what the code says — written by
tools/reference.py, checked here and in CI (`make reference check=1`)."""
from __future__ import annotations

import ast
import re

from tools import reference
from verso.core import cli

CHECKS = reference.CHECKS


def test_reference_is_current():
    assert reference.check() == []


def test_every_command_and_linter_code_is_in_the_reference():
    commands = (reference.OUT / "commands.md").read_text(encoding="utf-8")
    assert [c for c in cli.commands() if f"`verso {c}`" not in commands] == []
    linters = (reference.OUT / "linters.md").read_text(encoding="utf-8")
    codes = {node.value for path in CHECKS.glob("*.py")
             for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and re.fullmatch(r"[A-Z]{3}\d{3}", node.value)}
    assert codes and sorted(c for c in codes if c not in linters) == []


def test_a_summary_is_a_sentence_not_a_lead_in():
    """A summary cut at a colon («The святцы:», «Fix:») says nothing about the command."""
    rows = [line for page in ("commands.md", "linters.md")
            for line in (reference.OUT / page).read_text(encoding="utf-8").splitlines() if line.startswith("| `")]
    assert rows and [row for row in rows if row.rstrip(" |").endswith(":")] == []


def test_a_summary_ends_at_a_full_stop_not_at_a_colon():
    source = '"""The tool: what it does. More."""'
    assert reference._docline(source) == "The tool: what it does."  # pyright: ignore[reportPrivateUsage]
