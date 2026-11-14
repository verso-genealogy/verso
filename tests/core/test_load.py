"""A village loaded through the toy plugin's record kinds and order: the core knows no
record kind of its own."""
from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.core.toy import TOY, Notes
from verso.core import plugins, workspace
from verso.core.pipeline import load
from verso.core.plugins import Plugin, PluginError

HEAD = "from tests.core.toy import note, notes, who\n\n"


def _village(root: Path) -> Path:
    village = root / "V"
    (village / "1850").mkdir(parents=True)
    (village / "1851").mkdir()
    (village / "1851" / "v_notes_1851.py").write_text(
        HEAD + 'n1851 = notes("V", "1", "2", "3", 1851, note(1, who("Анна")))\n', encoding="utf-8")
    # One file, two books — written out of their order — and one of them bound twice.
    (village / "1850" / "v_notes_1850.py").write_text(
        HEAD + 'late = notes("V", "1", "2", "4", 1850, note(2, who("Пётр")))\n'
               'early = notes("V", "1", "2", "3", 1849, note(1, who("Иван")))\n'
               "again = early\n", encoding="utf-8")
    (village / "1850" / "readme.py").write_text("x = 1\n", encoding="utf-8")
    return village


def test_a_village_is_discovered_by_the_plugins_kinds_and_order(toy_workspace: Path):
    found = [(path.name, name, cast(Notes, s).year)
             for path, name, s in load.discover_records(str(_village(toy_workspace)))]
    assert found == [("v_notes_1850.py", "early", 1849), ("v_notes_1850.py", "late", 1850),
                     ("v_notes_1851.py", "n1851", 1851)]


def test_a_record_set_bound_twice_comes_once(toy_workspace: Path):
    names = [name for _, name, _ in load.discover_records(str(_village(toy_workspace)))]
    assert "again" not in names and names.count("early") == 1


@pytest.mark.usefixtures("toy_workspace")
def test_the_record_types_are_the_plugins():
    assert load.record_types() == (Notes,) == load.record_types(translated=True)
    assert plugins.kind_of(Notes("V", "1", "2", "3", 1850)) is plugins.dsl().kinds[0]
    assert plugins.kind_of(object()) is None


def test_book_order_follows_the_plugins_globs(toy_workspace: Path):
    village = _village(toy_workspace)
    assert load.book_order(village / "1850" / "v_notes_1850.py") == ("1850", 0, "v_notes_1850.py")
    assert load.book_order(village / "1850" / "readme.py") == ("1850", 1, "readme.py")
    assert [p.name for p in load.dsl_files(village)] == ["v_notes_1850.py", "readme.py", "v_notes_1851.py"]


def test_no_dsl_and_two_dsls_are_refused(tmp_path: Path):
    bare = Plugin(name="bare", package="tests.core")
    twin = Plugin(name="twin", package="tests.core", dsl=TOY.dsl)
    for listed, message in (('["bare"]', "no plugin of the workspace gives a DSL — plugins in verso.toml"),
                            ('["toy", "twin"]', "two plugins give a DSL: toy, twin — a workspace has one")):
        root = tmp_path / listed.count(",").__str__()
        root.mkdir()
        (root / "verso.toml").write_text(f"schema = 4\nplugins = {listed}\n", encoding="utf-8")
        with plugins.adding(TOY, bare, twin, entry_points=False), workspace.use(root):
            with pytest.raises(PluginError) as caught:
                plugins.dsl()
        assert str(caught.value) == f"{root.resolve() / 'verso.toml'}: {message}"


def test_a_village_of_a_workspace_without_its_plugin_is_refused(tmp_path: Path):
    """Loading a village asks the plugin first: a workspace naming one nobody installed says
    so once, rather than a warning per file and an empty village."""
    village = _village(tmp_path)
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n', encoding="utf-8")
    with plugins.adding(TOY, entry_points=False), workspace.use(tmp_path):
        with pytest.raises(PluginError, match=r"the plugin «ru» is not installed — installed: toy; .* reinstall the environment's packages$"):
            list(load.village_modules(village))


def test_a_module_the_dsl_no_longer_has_is_named_by_the_plugin(toy_workspace: Path):
    path = toy_workspace / "v_notes_1850.py"
    path.write_text("import toy_v0.notes\n", encoding="utf-8")
    with pytest.raises(ImportError) as refused:
        load.load_module(path)
    assert str(refused.value) == f"{path}: toy v0 — перепишите {path}"
    path.write_text("import no_such_module_anywhere\n", encoding="utf-8")
    with pytest.raises(ModuleNotFoundError):
        load.load_module(path)
