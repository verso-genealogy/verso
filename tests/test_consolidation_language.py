"""The consolidation reports speak the interface's language, and the sweep's draft — a file the
owner pastes into a village's config — does not (rule 9)."""
from __future__ import annotations

import ast
from pathlib import Path

from tests.test_cli_language import english_but
from verso.core import i18n
from verso.ru.consolidation import candidates
from verso.ru.consolidation.union_duplicates import (
    VERDICT_CANDIDATE, VERDICT_REUSED_NAME, Member, UnionDuplicate, format_report)


def _group(verdict: str, reason: str) -> UnionDuplicate:
    return UnionDuplicate(union="ivan_and_anna", given_name="Петр", partners=("Иван Петров", "Анна Ильина"),
                          members=(Member("petr_1", "Петр Иванович", 1850, 1851),
                                   Member("petr_2", "Петр Иванович", 1853, None)),
                          verdict=verdict, reason=reason)


def test_union_dups_reports_in_english():
    with i18n.use("en"):
        text = format_report([_group(VERDICT_CANDIDATE, "x"), _group(VERDICT_REUSED_NAME, "y")], all_groups=True)
    assert "union-dups: 2 group(s)" in text
    assert english_but(text, "Петр Иванович", "Петр", "Иван Петров", "Анна Ильина") == ""


def test_the_sweep_draft_never_goes_through_a_catalog():
    """The sweep writes a draft the user pastes into a village's config: it is content, so its module
    asks no catalog — the draft is the same bytes whatever the interface speaks."""
    tree = ast.parse(Path(candidates.__file__).read_text(encoding="utf-8"))
    asked = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "t"]
    assert asked == []
