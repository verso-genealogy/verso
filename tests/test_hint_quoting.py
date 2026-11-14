"""A hint that names a village or a path quotes it for a shell, as `facts-snapshot` does: a village of
two words — and, `shlex` being ASCII, any Cyrillic one — runs as it is printed."""
from __future__ import annotations

import shlex
from pathlib import Path

from verso.core import i18n
from verso.core.pipeline import records
from verso.ru import plugin
from verso.ru.cli.find_person import rebuild_command, stale_warning
from verso.ru.linters.checks import dsl_imports

VILLAGE = "Две Тестовки"


def test_the_records_export_hint_quotes_the_village():
    with i18n.use("en"):
        assert str(records._hint(VILLAGE)) == "export again: verso export-records --village 'Две Тестовки'"


def test_the_v0_refusal_quotes_the_path():
    path = Path(VILLAGE) / "1900" / "v_births_1900.py"
    assert plugin._legacy_import("geni.domain", path) == f"DSL v0 — verso upgrade-dsl {shlex.quote(str(path))}"


def test_imp001_quotes_the_path(tmp_path: Path):
    folder = tmp_path / VILLAGE
    folder.mkdir()
    path = folder / "v_births_1850.py"
    path.write_text("from geni.domain import person\n", encoding="utf-8")
    [found] = dsl_imports.check_file_structured(path)
    assert found["message"].endswith(f"verso upgrade-dsl {shlex.quote(str(path))}")


def test_find_person_s_hints_quote_the_village():
    assert rebuild_command(VILLAGE) == "verso all-persons 'Две Тестовки'"
    assert "Rebuild with: verso all-persons 'Две Тестовки'" in stale_warning([Path("a_births_1818.py")], VILLAGE)
