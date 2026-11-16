"""`verso <команда>` on the toy plugin: the core's five commands and each installed plugin's."""
from __future__ import annotations

from importlib import metadata
from pathlib import Path

import pytest

from tests.core.toy import TOY
from verso.core import plugins, workspace
from verso.core.cli import COMMANDS, commands, main
from verso.core.plugins import Plugin, PluginError


@pytest.mark.usefixtures("toy_workspace")
def test_a_toy_plugins_command_runs_through_verso(capsys: pytest.CaptureFixture[str]):
    assert commands() == {"records-schema": "verso.core.records.schema", "scans": "verso.core.scans.cli",
                          "tools": "verso.core.tools",
                          "ui-schema": "verso.core.records.ui", "workspace": "verso.core.workspace",
                          "toy-hello": "tests.core.hello"}
    assert main(["toy-hello"]) == 0
    assert capsys.readouterr().out == "привет\n"


def test_every_module_of_the_core_run_as_a_program_is_a_command():
    """A module of the core that runs as a program is a command of `verso`: the commands are public."""
    import verso.core
    root = Path(verso.core.__file__).parent
    # A package runs as a program by its `__main__.py`.
    mains = {".".join(("verso", "core", *p.relative_to(root).with_suffix("").parts)).removesuffix(".__main__")
             for p in root.rglob("*.py") if 'if __name__ == "__main__":' in p.read_text(encoding="utf-8")}
    assert mains - {"verso.core.cli"} == set(COMMANDS.values())


def test_two_plugins_with_one_command_are_refused():
    twin = Plugin(name="twin", package="tests.core", commands={"toy-hello": "tests.core.hello"})
    with plugins.adding(TOY, twin, entry_points=False), pytest.raises(PluginError) as caught:
        commands()
    assert str(caught.value) == "the command «toy-hello» is the plugins' toy and twin"


def test_a_plugins_command_named_as_the_cores_is_refused():
    shadow = Plugin(name="shadow", package="tests.core", commands={"tools": "tests.core.hello"})
    with plugins.adding(shadow, entry_points=False), pytest.raises(PluginError) as caught:
        commands()
    assert str(caught.value) == "the command «tools» is the core's and the plugin shadow's"


def test_a_command_of_a_plugin_nobody_installed_says_make_bootstrap(tmp_path: Path,
                                                                    capsys: pytest.CaptureFixture[str]):
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n', encoding="utf-8")
    with plugins.adding(TOY, entry_points=False), workspace.use(tmp_path):
        assert main(["generate-tf"]) == 2
    assert capsys.readouterr().err == (
        "verso: no command «generate-tf» — the list: verso --help\n"
        f"verso: {tmp_path.resolve() / 'verso.toml'}: the plugin «ru» is not installed — installed: toy; "
        "if it is in pyproject.toml — reinstall the environment's packages\n")


def test_help_without_plugins_says_make_bootstrap(capsys: pytest.CaptureFixture[str]):
    with plugins.adding(entry_points=False), pytest.raises(SystemExit):
        main(["--help"])
    assert "no plugin installed — if they are in pyproject.toml, reinstall the environment's packages" in capsys.readouterr().out


def test_a_broken_entry_point_is_one_line(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    broken = metadata.EntryPoint(name="gone", value="verso_no_such_module:PLUGIN", group=plugins.GROUP)

    def entry_points(group: str) -> metadata.EntryPoints:  # noqa: ARG001 — importlib's signature
        return metadata.EntryPoints([broken])
    monkeypatch.setattr(plugins.metadata, "entry_points", entry_points)
    with plugins.adding():
        assert main(["tools"]) == 2
    assert capsys.readouterr().err == ("verso: the entry point «gone» (verso_no_such_module:PLUGIN) does not load: "
                                       "No module named 'verso_no_such_module'\n")
