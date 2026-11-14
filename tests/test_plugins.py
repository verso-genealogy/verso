"""The plugin ru as the registry finds it — by its entry point in the venv's metadata
(`make bootstrap`), outside tests/core."""
from __future__ import annotations

import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

from verso.core import plugins, workspace
from verso.core.plugins import PluginError
from tests.codepaths import pythonpath


def test_an_enabled_plugin_is_found_by_its_entry_point(tmp_path: Path):
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n', encoding="utf-8")
    with workspace.use(tmp_path):
        (ru,) = plugins.enabled()
    from verso.ru.plugin import PLUGIN
    assert ru is PLUGIN and ru.package == "verso.ru"


def test_a_workspace_loaded_again_keeps_the_answers(tmp_path: Path):
    """One verso.toml entered again inside itself is one workspace: a host that enters it once a book, under a request
    that entered it first, does not build the DSL anew each time. A verso.toml that changed is another."""
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n', encoding="utf-8")
    with workspace.use(tmp_path) as first:
        dsl = plugins.dsl()
        with workspace.use(tmp_path) as again:
            assert again is not first and plugins.dsl() is dsl
        (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n[notes]\nglobs = ["*.md"]\n', encoding="utf-8")
        with workspace.use(tmp_path):
            assert plugins.dsl() is not dsl


def test_the_tests_workspace_enables_ru():
    assert [p.name for p in plugins.enabled()] == ["ru"]
    assert plugins.transliterator()("Плотвичкинъ") == "Plotvichkin'"


def test_a_plugin_named_otherwise_than_its_entry_point_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    wrong = metadata.EntryPoint(name="rus", value="verso.ru.plugin:PLUGIN", group=plugins.GROUP)
    not_one = metadata.EntryPoint(name="ru", value="verso.ru:__doc__", group=plugins.GROUP)
    for ep, message in ((wrong, "точка входа «rus» (verso.ru.plugin:PLUGIN) даёт плагин «ru» — имена должны совпадать"),
                        (not_one, "точка входа «ru» (verso.ru:__doc__) — не Plugin")):
        def entry_points(group: str, ep: metadata.EntryPoint = ep) -> metadata.EntryPoints:
            return metadata.EntryPoints([ep])
        monkeypatch.setattr(plugins.metadata, "entry_points", entry_points)
        (tmp_path / "verso.toml").write_text(f'schema = 4\nplugins = ["{ep.name}"]\n', encoding="utf-8")
        with plugins.adding(), workspace.use(tmp_path), pytest.raises(PluginError) as caught:
            plugins.enabled()
        assert str(caught.value) == message


def test_importing_the_registry_reads_no_workspace(tmp_path: Path):
    """No verso.toml above the child: importing the registry and the plugin asks nothing."""
    code = "import verso.core.plugins, verso.ru.plugin; print('ok')"
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()}
    done = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=60, check=False)
    assert (done.returncode, done.stdout) == (0, "ok\n"), done.stderr


def test_the_registry_does_not_import_the_workspace_it_runs(tmp_path: Path):
    """`verso workspace` runs `verso.core.workspace` as __main__ after the registry is imported: a registry that
    imported the module first made runpy warn on every run (0.1.23)."""
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n', encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath(), "VERSO_WORKSPACE": str(tmp_path)}
    done = subprocess.run([sys.executable, "-m", "verso.core.cli", "workspace", "root"], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=60, check=False)
    assert (done.returncode, done.stdout, done.stderr) == (0, f"{tmp_path}\n", "")


def test_two_distributions_naming_one_plugin_say_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A venv left with the old `geni` distribution beside verso-ru declares «ru» twice: the
    registry says so in a line and names the fix, whatever the two entry points point at."""
    dists = []
    for name in ("geni", "verso-ru"):
        info = tmp_path / f"{name.replace('-', '_')}-0.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0\n", encoding="utf-8")
        (info / "entry_points.txt").write_text("[verso.plugins]\nru = verso.ru.plugin:PLUGIN\n", encoding="utf-8")
        dists.append(metadata.PathDistribution(info))

    def entry_points(group: str) -> metadata.EntryPoints:
        return metadata.EntryPoints(ep for dist in dists for ep in dist.entry_points if ep.group == group)

    monkeypatch.setattr(plugins.metadata, "entry_points", entry_points)
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n', encoding="utf-8")
    with plugins.adding(), workspace.use(tmp_path), pytest.raises(PluginError) as caught:
        plugins.enabled()
    assert str(caught.value) == "плагин «ru» объявлен дважды: geni, verso-ru — переустановите пакеты окружения"
