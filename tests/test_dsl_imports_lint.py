"""IMP001 — a DSL file imports the facade, its catalogs and corpus.statuses, nothing else."""
from __future__ import annotations

from pathlib import Path
from typing import Any


from verso.ru.linters import dsllint
from verso.ru.linters.checks import dsl_imports



def _findings(tmp_path: Path, text: str) -> list[dict[str, Any]]:
    path = tmp_path / "v_births_1850.py"
    path.write_text(text, encoding="utf-8")
    return dsl_imports.check_file_structured(path)


def test_imp001_flags_an_old_import(tmp_path: Path):
    path = tmp_path / "v_births_1850.py"
    assert _findings(tmp_path, "from geni.domain import person\n\nx = 1\n") == [
        {"level": "error", "line": 1,
         "message": f"[IMP001] импорт не из фасада DSL: geni.domain — verso upgrade-dsl {path}"}]


def test_imp001_flags_calendar_and_os(tmp_path: Path):
    found = _findings(tmp_path, "import os\nfrom calendar import Month\n\nx = 1\n")
    assert [(f["line"], f["message"].split(" — ")[0]) for f in found] == [
        (1, "[IMP001] импорт не из фасада DSL: os"), (2, "[IMP001] импорт не из фасада DSL: calendar")]


def test_imp001_sends_to_upgrade_dsl_only_what_it_rewrites(tmp_path: Path):
    # `verso upgrade-dsl` rewrites geni.* and calendar.Month; it refuses __future__ or a module of
    # the library, and keeps an `os` the file uses — so those are told no command.
    path = tmp_path / "v_births_1850.py"
    found = _findings(tmp_path, "from __future__ import annotations\nimport os\n"
                                "from verso.ru.domain.person import person\nfrom calendar import Month\n\nx = 1\n")
    assert [f["message"] for f in found] == [
        "[IMP001] импорт не из фасада DSL: __future__", "[IMP001] импорт не из фасада DSL: os",
        "[IMP001] импорт не из фасада DSL: verso.ru.domain.person",
        f"[IMP001] импорт не из фасада DSL: calendar — verso upgrade-dsl {path}"]


def test_imp001_accepts_the_facade_and_the_corpus(tmp_path: Path):
    text = ("from corpus.statuses import MANILOV_LK_PEASANT_MALE\n"
            "from verso.ru.dsl import Gender, person\n"
            "from verso.ru.dsl.causes_of_death import FEVER\n"
            "from verso.ru.dsl.marital_status import WIDOW\n"
            "from verso.ru.dsl.statuses import PEASANT_MALE\n\nx = 1\n")
    assert _findings(tmp_path, text) == []


def test_imp001_is_registered_and_hard():
    [linter] = [lt for lt in dsllint.LINTERS if lt.name == "dsl_imports"]
    assert not linter.advisory
