"""The names tables are the workspace's: read from it, read again when it changes,
and an error — not an empty index — when it has none."""
from __future__ import annotations

import csv
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from verso.ru.gender import Gender
from verso.ru.linters.names_csv import names_csv_path, read_rows
from verso.ru.naming import names_registry
from verso.ru.naming.gender_inference import get_gender_from_name
from verso.ru.naming.names_registry import (
    _find_name_in_table, ignored_name_gender, is_ignored_name, is_ignored_patronymic)
from verso.ru.naming.lexicon import IGNORE_LIST, Layer, NameEntry
from verso.ru.naming.validation import validate_old_patronymic
from verso.core.workspace import LexiconNotConfigured, WorkspaceError, pin, use

HEADER = ["Пол", "Имя", "Имя-основа", "От", "Склонения, связи", "Родительный падеж",
          "Отчество старое М", "Отчество старое Ж", "Отчество М", "Отчество Ж", "Источник"]


def area(root: Path, names: Sequence[tuple[str, str]] | None, *, ignore: Sequence[tuple[str, str]] = (),
         patronymics: Sequence[str] = (), section: bool = True) -> Path:
    """A workspace whose names.csv holds `names` as (Пол, Имя); None writes no names.csv."""
    root.mkdir(parents=True)
    (root / "verso.toml").write_text('schema = 1\n' + ('[names]\ndir = "."\n' if section else ""), encoding="utf-8")
    if names is not None:
        with (root / "names.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(HEADER)
            for sex, name in names:
                w.writerow([sex, name, "", "", "", name + "а", name + "ов", name + "ова", name + "ович", name + "овна", ""])
    if ignore:
        (root / "names_ignore.csv").write_text("Gender,Name\n" + "".join(f"{g},{n}\n" for g, n in ignore), encoding="utf-8")
    if patronymics:
        (root / "patronymics_ignore.csv").write_text("Patronymic\n" + "".join(f"{p}\n" for p in patronymics),
                                                     encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def forgotten() -> Iterator[None]:
    """The registry follows the workspace; each test leaves the process's alone."""
    pin(None)
    yield
    pin(None)


def test_the_table_is_the_workspaces(tmp_path: Path) -> None:
    with use(area(tmp_path / "a", [("М", "Агап")])):
        assert [e.name for e in _find_name_in_table("Агап")] == ["Агап"]
        assert _find_name_in_table("Иван") == []


def test_a_change_of_workspace_reads_the_other_table(tmp_path: Path) -> None:
    a = area(tmp_path / "a", [("М", "Агап")])
    b = area(tmp_path / "b", [("Ж", "Агапа")])
    with use(a):
        assert get_gender_from_name("Агап") is Gender.MALE
        with use(b):
            assert get_gender_from_name("Агап") is None
            assert get_gender_from_name("Агапа") is Gender.FEMALE
        assert get_gender_from_name("Агап") is Gender.MALE


def test_without_names_section_lookup_is_lexicon_not_configured(tmp_path: Path) -> None:
    with use(area(tmp_path / "a", [("М", "Агап")], section=False)), pytest.raises(LexiconNotConfigured):
        _find_name_in_table("Агап")


def test_a_missing_table_is_an_error_every_time(tmp_path: Path) -> None:
    """The load is not marked done before the file is found: a second lookup
    would otherwise answer «no such name» from an empty index."""
    with use(area(tmp_path / "a", None)):
        for _ in range(2):
            with pytest.raises(WorkspaceError, match=r"нет файла .*names\.csv"):
                _find_name_in_table("Иван")


def test_missing_ignore_lists_are_empty(tmp_path: Path) -> None:
    with use(area(tmp_path / "a", [("М", "Агап")])):
        assert not is_ignored_name("Шумила")
        assert not is_ignored_patronymic("Шумилов")


def test_the_ignore_lists_are_the_workspaces(tmp_path: Path) -> None:
    with use(area(tmp_path / "a", [("М", "Агап")], ignore=[("М", "Шумила"), ("", "Адмак")], patronymics=["Шумилов"])):
        assert is_ignored_name("Шумила") and ignored_name_gender("Шумила") is Gender.MALE
        assert is_ignored_name("Адмак") and ignored_name_gender("Адмак") is None
        assert is_ignored_patronymic("Шумилов")
        assert validate_old_patronymic("Шумилов")


def test_the_ignore_functions_honour_a_substituted_lexicon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with use(area(tmp_path / "a", [("М", "Агап")])):
        lexicon = names_registry.current_lexicon().with_layer(
            Layer("test", {(Gender.MALE, "Шумила"): NameEntry(Gender.MALE, "Шумила", source=IGNORE_LIST)}, {}, {}))
        monkeypatch.setattr(names_registry, "current_lexicon", lambda: lexicon)
        assert is_ignored_name("Шумила")
        assert get_gender_from_name("Шумила") is Gender.MALE


def test_a_changed_table_is_read_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The lexicon follows its files' stamps — looked at again after `RECHECK_SECONDS`, at once
    after `reload()`."""
    root = area(tmp_path / "a", [("М", "Агап")])
    with use(root):
        assert get_gender_from_name("Агапа") is None
        area_rows = (root / "names.csv").read_text(encoding="utf-8")
        (root / "names.csv").write_text(area_rows + "Ж,Агапа,,,,Агапы,,,,,\n", encoding="utf-8")
        monkeypatch.setattr(names_registry, "RECHECK_SECONDS", 3600.0)
        assert get_gender_from_name("Агапа") is None          # not looked at yet
        monkeypatch.setattr(names_registry, "_next_check", 0.0)
        assert get_gender_from_name("Агапа") is Gender.FEMALE  # its stamp moved
        (root / "names.csv").write_text(area_rows, encoding="utf-8")
        names_registry.reload()
        assert get_gender_from_name("Агапа") is None


def test_read_rows_reads_the_workspaces_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with use(area(tmp_path / "a", [("М", "Агап"), ("Ж", "Агапа")])):
        assert names_csv_path() == (tmp_path / "a").resolve() / "names.csv"
        assert [r["Имя"] for r in read_rows()] == ["Агап", "Агапа"]


def test_a_table_gone_answers_nothing_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A names.csv removed under a held lexicon: once its stamp is looked at, every lookup fails —
    none answers from the lexicon built before; a table put back is read afresh."""
    root = area(tmp_path / "a", [("М", "Агап")])
    with use(root):
        assert get_gender_from_name("Агап") is Gender.MALE
        assert names_registry._names_table_loaded
        rows = (root / "names.csv").read_text(encoding="utf-8")
        (root / "names.csv").unlink()
        monkeypatch.setattr(names_registry, "_next_check", 0.0)
        for _ in range(2):
            with pytest.raises(WorkspaceError, match=r"нет файла .*names\.csv"):
                get_gender_from_name("Агап")
            # The lexicon built before is forgotten, not merely passed over until the deadline.
            assert names_registry._held is None
            assert not names_registry._names_table_loaded
        # Back with other content: the next lookup builds the lexicon again and answers by it.
        assert "М,Агап," in rows
        (root / "names.csv").write_text(rows.replace("М,Агап,", "Ж,Агап,"), encoding="utf-8")
        assert get_gender_from_name("Агап") is Gender.FEMALE
        assert names_registry._names_table_loaded
