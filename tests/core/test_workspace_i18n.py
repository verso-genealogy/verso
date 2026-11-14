"""verso.toml's language (schema 5): `[i18n] locale` and `packs`; an older file reads as ru."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import workspace
from verso.core.workspace import WorkspaceError


def _load(tmp_path: Path, text: str) -> workspace.Workspace:
    (tmp_path / "verso.toml").write_text(text, encoding="utf-8")
    return workspace.load(tmp_path)


def test_schema_4_reads_as_ru(tmp_path: Path):
    assert _load(tmp_path, "schema = 4\n").locale == "ru"
    assert _load(tmp_path, "schema = 1\n").locale == "ru"


def test_schema_5_without_i18n_is_english(tmp_path: Path):
    ws = _load(tmp_path, "schema = 5\n")
    assert (ws.locale, ws.packs) == ("en", ())


def test_schema_5_says_its_language(tmp_path: Path):
    ws = _load(tmp_path, 'schema = 5\n[i18n]\nlocale = "ru"\npacks = []\n')
    assert (ws.locale, ws.packs) == ("ru", ())


def test_a_pack_not_installed_is_refused_at_load(tmp_path: Path):
    """Said once and loudly where the setting is written — rendering would forgive it in silence."""
    with pytest.raises(WorkspaceError, match=r"verso\.toml: \[i18n\]: language pack «xx» is not installed"):
        _load(tmp_path, 'schema = 5\n[i18n]\nlocale = "ru"\npacks = ["xx"]\n')


def test_a_locale_nobody_speaks_is_refused_at_load(tmp_path: Path):
    with pytest.raises(WorkspaceError, match=r"unknown language «zz» — languages: en, ru"):
        _load(tmp_path, 'schema = 5\n[i18n]\nlocale = "zz"\n')


def test_unknown_i18n_key_is_refused(tmp_path: Path):
    with pytest.raises(WorkspaceError, match=r"i18n\.lang"):
        _load(tmp_path, 'schema = 5\n[i18n]\nlang = "ru"\n')


def test_i18n_in_an_older_schema_is_refused(tmp_path: Path):
    with pytest.raises(WorkspaceError, match="i18n"):
        _load(tmp_path, 'schema = 4\n[i18n]\nlocale = "en"\n')
