"""A hint that tells a person to make or export a terraform plan runs as printed: terraform runs in the
village's module (`-chdir`), a plan is saved where the tools look for it (`-out`), and the JSON lands
where they read it (`<village>/_plan.json`) — `terraform show -json .plan > _plan.json` works from no
folder, since `.plan` lies in `<village>/terraform/geni/` and `_plan.json` is read from `<village>/`."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.codepaths import code_files, module_name
from verso.ru.consolidation import detector, merge_plan
from verso.ru.consolidation.plan import export_command, plan_command

BARE_EXPORT = re.compile(r"terraform show -json \.plan > _plan\.json")
PLAN_WITHOUT_OUT = re.compile(r"plan -refresh=false(?! -out)")


def test_the_export_runs_in_the_module_and_writes_where_the_tools_read():
    assert export_command("Две Тестовки") == (
        "terraform -chdir='Две Тестовки/terraform/geni' show -json .plan > 'Две Тестовки/_plan.json'")
    assert export_command(".") == "terraform -chdir=terraform/geni show -json .plan > _plan.json"


def test_a_plan_is_saved_where_the_tools_look():
    assert plan_command("Две Тестовки") == "terraform -chdir='Две Тестовки/terraform/geni' plan -out=.plan"
    assert plan_command("Две Тестовки", fast=True) == (
        "terraform -chdir='Две Тестовки/terraform/geni' plan -refresh=false -out=.plan-fast")


def test_the_detector_s_refusal_of_a_text_plan_names_the_export(tmp_path: Path):
    text = tmp_path / "_plan_full.txt"
    text.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        detector._load_plan(text)
    assert export_command(tmp_path) in str(refused.value.code)


def test_merge_plan_without_a_plan_says_how_to_save_one(tmp_path: Path):
    village = tmp_path / "Две Тестовки"
    village.mkdir()
    with pytest.raises(SystemExit) as refused:
        merge_plan.main(["--village", str(village)])
    said = str(refused.value.code)
    assert plan_command(str(village), fast=True) in said
    assert plan_command(str(village)) in said


def _strings() -> list[tuple[str, int, str]]:
    found = []
    for path in code_files("verso.core", "verso.ru"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.append((module_name(path), node.lineno, node.value))
    return found


def test_no_code_tells_a_person_to_export_a_plan_from_nowhere():
    assert [f"{rel}:{line}" for rel, line, text in _strings() if BARE_EXPORT.search(text)] == []


def test_no_code_tells_a_person_to_plan_without_saving_it():
    assert [f"{rel}:{line}" for rel, line, text in _strings() if PLAN_WITHOUT_OUT.search(text)] == []
