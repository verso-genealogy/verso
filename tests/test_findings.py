"""verso.ru.linters.findings — the linters' findings of one DSL file, each with its fix
— what a Verso save is checked on."""
from __future__ import annotations

import dataclasses
from pathlib import Path

from verso.ru.linters import dsllint, findings

BIRTHS = Path(__file__).resolve().parent / "fixtures" / "mini" / "root" / "Маниловка" / "1900" / "manilovka_births_1900.py"
# The fixture's book with one godfather's status written as the book's default.
REDUNDANT_STATUS = BIRTHS.read_text(encoding="utf-8").replace(
    'god_parent1=person("Никифоръ", "Андреевъ", "Образцовъ"),',
    'god_parent1=person("Никифоръ", "Андреевъ", "Образцовъ", status=PEASANT_MALE),')


def test_a_finding_carries_its_fix(tmp_path: Path):
    assert "status=PEASANT_MALE" in REDUNDANT_STATUS
    like = tmp_path / "Маниловка" / "1900" / "manilovka_births_1900.py"
    found = findings.lint_text(REDUNDANT_STATUS, like)
    fix = next(f.fix for f in found if f.linter == "status_redundancy" and f.fix)
    assert (fix["type"], fix.get("kwarg")) == ("remove_kwarg", "status") and fix["col"] > 0
    assert not like.exists()


def test_new_findings_ignore_where_the_line_went():
    a = findings.Finding("names", "error", 3, "нет имени «Х»")
    assert findings.new_findings([a], [dataclasses.replace(a, line=9)]) == []
    assert findings.new_findings([a], [a, a]) == [a]


def test_advisory_is_the_registrys_flag():
    assert findings.ADVISORY == {linter.name for linter in dsllint.LINTERS if linter.advisory}
    assert findings.Finding("names", "warning", 1, "x").advisory is ("names" in findings.ADVISORY)
    assert str(findings.Finding("names", "error", 3, "нет имени")) == "names: стр. 3: нет имени"
