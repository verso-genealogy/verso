"""verso.core.plugins on toy plugins, the entry points hidden: the registry, the order, the
transliterator, the cache across workspaces."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.core.toy import TOY, TOY_DSL
from verso.core import plugins, workspace
from verso.core.plugins import Plugin, PluginError

TOY2 = Plugin(name="toy2", package="tests.core", transliterate=lambda: str.lower)
BARE = Plugin(name="bare", package="tests.core")


def _root(path: Path, text: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "verso.toml").write_text(text, encoding="utf-8")
    return path


def test_plugins_come_in_the_order_the_workspace_names_them(tmp_path: Path):
    root = _root(tmp_path, 'schema = 4\nplugins = ["toy2", "bare", "toy"]\n')
    with plugins.adding(TOY, TOY2, BARE, entry_points=False), workspace.use(root):
        assert plugins.enabled() == (TOY2, BARE, TOY)


def test_an_enabled_plugin_nobody_installed_says_make_bootstrap(tmp_path: Path):
    root = _root(tmp_path, 'schema = 4\nplugins = ["ru"]\n')
    with plugins.adding(TOY, entry_points=False), workspace.use(root):
        with pytest.raises(PluginError) as caught:
            plugins.enabled()
    assert str(caught.value) == (f"{root.resolve() / 'verso.toml'}: the plugin «ru» is not installed — installed: toy; "
                                 "if it is in pyproject.toml — reinstall the environment's packages")


def test_none_installed_is_said_too(tmp_path: Path):
    root = _root(tmp_path, 'schema = 4\nplugins = ["ru"]\n')
    with plugins.adding(entry_points=False), workspace.use(root):
        with pytest.raises(PluginError, match=r"installed: none; if it is in pyproject\.toml — reinstall the environment's packages$"):
            plugins.enabled()


def test_an_old_schema_reads_as_ru_and_schema_4_without_plugins_as_the_core_alone(tmp_path: Path):
    old = _root(tmp_path / "old", "schema = 3\n")
    bare = _root(tmp_path / "bare", "schema = 4\n")
    with plugins.adding(TOY, entry_points=False):
        with workspace.use(bare):
            assert plugins.enabled() == ()
        with workspace.use(old), pytest.raises(PluginError, match="the plugin «ru» is not installed"):
            plugins.enabled()


def test_one_transliterator_two_or_none_is_refused(tmp_path: Path):
    one = _root(tmp_path / "one", 'schema = 4\nplugins = ["toy", "bare"]\n')
    two = _root(tmp_path / "two", 'schema = 4\nplugins = ["toy", "toy2"]\n')
    none = _root(tmp_path / "none", 'schema = 4\nplugins = ["bare"]\n')
    with plugins.adding(TOY, TOY2, BARE, entry_points=False):
        with workspace.use(one):
            assert plugins.transliterator()("Анна") == "АННА"
        with workspace.use(two), pytest.raises(PluginError, match=r"two plugins give a transliteration: toy, toy2 — keep one$"):
            plugins.transliterator()
        with workspace.use(none), pytest.raises(
                PluginError, match=r"no enabled plugin gives a transliteration — plugins in verso\.toml$"):
            plugins.transliterator()


def test_the_registry_follows_the_workspace(tmp_path: Path):
    a = _root(tmp_path / "a", 'schema = 4\nplugins = ["toy"]\n')
    b = _root(tmp_path / "b", 'schema = 4\nplugins = ["toy2"]\n')
    with plugins.adding(TOY, TOY2, entry_points=False), workspace.use(a):
        assert plugins.transliterator()("Анна") == "АННА"
        with workspace.use(b):
            assert plugins.transliterator()("Анна") == "анна"
            assert plugins.enabled() == (TOY2,)
        assert plugins.transliterator()("Анна") == "АННА"
        assert plugins.enabled() == (TOY,)


def test_the_dsl_follows_the_workspace(tmp_path: Path):
    # The records' encoder and decoder ask `dsl()` of every field: its kept answer is the workspace's, in and out of a block.
    other = dataclasses.replace(TOY_DSL)
    twin = Plugin(name="twin", package="tests.core", dsl=lambda: other)
    a = _root(tmp_path / "a", 'schema = 4\nplugins = ["toy"]\n')
    b = _root(tmp_path / "b", 'schema = 4\nplugins = ["twin"]\n')
    with plugins.adding(TOY, twin, entry_points=False), workspace.use(a):
        assert plugins.dsl() is TOY_DSL
        assert plugins.dsl() is TOY_DSL
        with workspace.use(b):
            assert plugins.dsl() is other
            assert plugins.dsl() is other
        assert plugins.dsl() is TOY_DSL


def test_a_plugin_added_for_a_block_is_gone_after_it(tmp_path: Path):
    root = _root(tmp_path, 'schema = 4\nplugins = ["toy"]\n')
    with workspace.use(root):
        with plugins.adding(TOY, entry_points=False):
            assert plugins.enabled() == (TOY,)
        with plugins.adding(entry_points=False), pytest.raises(PluginError, match="the plugin «toy» is not installed"):
            plugins.enabled()


def test_two_plugins_of_one_name_are_refused(tmp_path: Path):
    root = _root(tmp_path, 'schema = 4\nplugins = ["toy"]\n')
    twin = Plugin(name="toy", package="elsewhere")
    with plugins.adding(TOY, twin, entry_points=False), workspace.use(root):
        with pytest.raises(PluginError, match="two plugins named «toy»"):
            plugins.enabled()


def test_an_uncaught_plugin_error_is_one_line():
    """A PluginError stops the program with its message alone, and a loader's broad
    `except Exception` cannot swallow it (`StaleRecords` does the same)."""
    import subprocess
    import sys
    from tests.codepaths import PROJECT, pythonpath
    code = ("from verso.core.plugins import PluginError\n"
            "try:\n"
            "    raise PluginError('плагин «ru» не установлен — переустановите пакеты окружения')\n"
            "except Exception:\n"
            "    print('swallowed')\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, timeout=60,
                          check=False, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()})
    assert (done.returncode, done.stdout, done.stderr) == (1, "", "плагин «ru» не установлен — переустановите пакеты окружения\n")
