"""`[translit]` of verso.toml (schema 7): the profile each role of the transliteration spells by, read as data."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core.workspace import TranslitRoles, WorkspaceError, load


def _ws(tmp_path: Path, text: str) -> Path:
    (tmp_path / "verso.toml").write_text(text, encoding="utf-8")
    return tmp_path


def test_schema_6_has_no_roles(tmp_path: Path):
    assert load(_ws(tmp_path, "schema = 6\n")).translit is None


def test_schema_7_without_the_table_leaves_both_roles_to_the_plugin(tmp_path: Path):
    assert load(_ws(tmp_path, "schema = 7\n")).translit == TranslitRoles(None, None)


def test_schema_7_names_each_role(tmp_path: Path):
    ws = load(_ws(tmp_path, 'schema = 7\n[translit]\naddress = "ru-v1"\ndisplay = "ru-v2"\n'))
    assert ws.translit == TranslitRoles(address="ru-v1", display="ru-v2")


def test_translit_key_needs_schema_7(tmp_path: Path):
    with pytest.raises(WorkspaceError, match=r"\[translit\] — с schema 7"):
        load(_ws(tmp_path, 'schema = 6\n[translit]\ndisplay = "ru-v2"\n'))


@pytest.mark.parametrize("value", ['""', "1", "false"])
def test_a_profile_must_be_a_name(tmp_path: Path, value: str):
    with pytest.raises(WorkspaceError, match=r"«translit\.display» — ожидалось имя профиля"):
        load(_ws(tmp_path, f"schema = 7\n[translit]\ndisplay = {value}\n"))


def test_an_unknown_key_is_named(tmp_path: Path):
    with pytest.raises(WorkspaceError, match=r"translit\.res_names"):
        load(_ws(tmp_path, 'schema = 7\n[translit]\nres_names = "ru-v1"\n'))
