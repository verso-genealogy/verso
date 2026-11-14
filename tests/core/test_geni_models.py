"""The Geni models of the core on the toy plugin: they spell names through the enabled
transliterator and know the about's section marker themselves."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import plugins, workspace
from verso.core.plugins import PluginError
from verso.core.targets.geni import about
from verso.core.targets.geni.profile import GeniProfile


@pytest.mark.usefixtures("toy_workspace")
def test_a_profile_spells_its_latin_names_with_the_enabled_transliterator():
    p = GeniProfile(res_name="x", gender="male", first_name="Анна", nicknames=["Аннушка"])
    p.last_name = "Петрова"
    assert (p.first_name_en, p.last_name_en, p.nicknames_en) == ("АННА", "ПЕТРОВА", ["АННУШКА"])


@pytest.mark.usefixtures("toy_workspace")
def test_the_section_marker_is_stripped_when_the_about_is_rendered():
    marker = about.marker(1850, 4, 7)
    assert marker == "<!--sd:1850-04-07-->"
    assert about.marker(1850, None, 7) is None
    p = GeniProfile(res_name="x", gender="female", first_name="Анна", about=f"<strong>Рождение</strong>{marker}\nтекст")
    assert "<!--sd:" not in p.to_terraform()
    assert about.strip_section_date_markers(f"a{marker}b") == "ab"
    found = about.SECTION_DATE_MARKER.search(f"x{marker}")
    assert found is not None and found.group(1) == "1850"


def test_a_profile_without_names_asks_no_transliterator(tmp_path: Path):
    """An empty name has nothing to spell: a profile built without names needs no plugin."""
    (tmp_path / "verso.toml").write_text("schema = 4\n", encoding="utf-8")     # the core alone
    with plugins.adding(entry_points=False), workspace.use(tmp_path):
        p = GeniProfile(res_name="x", gender="male")
        assert (p.first_name_en, p.last_name_en, p.nicknames_en) == ("", "", [])
        with pytest.raises(PluginError, match="gives a transliteration"):
            p.first_name = "Анна"


@pytest.mark.usefixtures("toy_workspace")
def test_profile_locales_are_the_plugins():
    """The names' and the about's locale keys are the plugin's content profile: the core
    names no language of the records."""
    p = GeniProfile(res_name="x", gender="female", first_name="Анна", about="текст")
    text = p.to_terraform()
    assert '"xx" = {' in text and '"en-US" = {' in text
    assert '"ru" = ' not in text
    assert plugins.content() == plugins.ContentProfile(native="xx", latin="en-US")


def test_a_profile_without_names_asks_no_plugin(tmp_path: Path):
    """No names and no about: nothing to key by a locale, so no plugin is asked."""
    (tmp_path / "verso.toml").write_text("schema = 4\n", encoding="utf-8")     # the core alone
    with plugins.adding(entry_points=False), workspace.use(tmp_path):
        text = GeniProfile(res_name="x", gender="male").to_terraform()
    assert "names" not in text and "about" not in text


def test_content_without_a_profile_is_refused(tmp_path: Path):
    (tmp_path / "verso.toml").write_text("schema = 4\n", encoding="utf-8")
    with plugins.adding(entry_points=False), workspace.use(tmp_path), pytest.raises(PluginError):
        plugins.content()
