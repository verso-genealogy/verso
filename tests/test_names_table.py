"""The library writes a row of the workspace's names table, or of an ignore list: the path `python -m verso.ru.cli.names add` takes, which Verso's
«Добавить в справочник…» takes too. Each test in a copy of the old tables of tests/fixtures/legacy-names."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.linters import names_csv
from verso.ru.naming.validation import validate_old_patronymic

# The old tables the tests of the old format read: invented names, a workspace of schema 4.
VERSO_NAMES = Path(__file__).resolve().parent / "fixtures" / "legacy-names"
# What «Добавить в справочник…» proposes for the patronymic «Зафеева» (golden 34).
ZAFEJ_ROW = {"Пол": "М", "Имя": "Зафей", "Имя-основа": "Матвей", "От": "ист. написание", "Склонения, связи": "",
             "Родительный падеж": "Зафея", "Отчество старое М": "Зафеев", "Отчество старое Ж": "Зафеева",
             "Отчество М": "Матвеевич", "Отчество Ж": "Матвеевна", "Источник": "ист. написание (Маниловка МК 1900)"}


def lexicon(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    shutil.copytree(VERSO_NAMES, root)
    (root / "verso.toml").write_text('schema = 2\n[names]\ndir = "."\n', encoding="utf-8")
    return root


def test_a_row_is_added_where_names_add_puts_it_and_the_registry_sees_it(tmp_path: Path) -> None:
    with workspace.use(lexicon(tmp_path)) as ws:
        assert not validate_old_patronymic("Зафеева", accept_full=True)
        where = names_csv.add_row(ZAFEJ_ROW)
        assert where["file"] == "names.csv" and where["line_text"].startswith("М,Зафей,")
        lines = ws.names_file("names.csv").read_text(encoding="utf-8").splitlines()
        assert lines[where["line"] - 1] == where["line_text"]
        assert validate_old_patronymic("Зафеева", accept_full=True)
        assert any(row["Имя"] == "Зафей" for row in names_csv.rows())


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    with workspace.use(lexicon(tmp_path)) as ws:
        before = ws.names_file("names.csv").read_bytes()
        assert names_csv.add_row(ZAFEJ_ROW, dry_run=True)["line_text"].startswith("М,Зафей,")
        assert ws.names_file("names.csv").read_bytes() == before


def test_the_same_row_twice_is_refused(tmp_path: Path) -> None:
    with workspace.use(lexicon(tmp_path)):
        names_csv.add_row(ZAFEJ_ROW)
        with pytest.raises(ValueError, match="уже есть"):
            names_csv.add_row(ZAFEJ_ROW)


def test_an_ignored_patronymic_goes_to_its_list(tmp_path: Path) -> None:
    with workspace.use(lexicon(tmp_path)) as ws:
        where = names_csv.add_ignored("patronymic", "Зафеева", "", dry_run=False)
        assert where == {"file": "patronymics_ignore.csv", "line_text": "Зафеева"}
        assert ws.names_file("patronymics_ignore.csv").read_text(encoding="utf-8").endswith("\nЗафеева\n")
        with pytest.raises(ValueError, match=r"уже есть в patronymics_ignore\.csv"):
            names_csv.add_ignored("patronymic", "Зафеева", "")


def test_a_name_the_table_holds_is_not_ignored(tmp_path: Path) -> None:
    """The ignore list is read before the table: an entry would flip every bearer's sex."""
    with workspace.use(lexicon(tmp_path)):
        with pytest.raises(ValueError, match="уже есть в справочнике"):
            names_csv.add_ignored("name", "Анна", "М", dry_run=True)
