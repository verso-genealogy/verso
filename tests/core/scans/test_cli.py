"""`verso scans`: the core's subcommands, without any plugin (`make test-core` runs this with verso.ru blocked)."""
from __future__ import annotations

import pytest

from verso.core import plugins
from verso.core.cli import COMMANDS
from verso.core.cli import main as verso
from verso.core.scans.cli import CORE, subcommands


def test_scans_is_a_command_of_the_core():
    assert COMMANDS["scans"] == "verso.core.scans.cli"


def test_core_scans_without_ru(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VERSO_LANG", "en")
    with plugins.adding(entry_points=False):
        assert subcommands() == CORE
        assert verso(["scans", "--help"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: verso scans [-h] subcommand ...\n")
    for name in ("descreen", "jpeg", "quadrants", "strips"):
        assert f"\n    {name} " in out


def test_a_subcommands_help_speaks_the_language(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VERSO_LANG", "ru")
    with plugins.adding(entry_points=False):
        assert verso(["scans", "strips", "--help"]) == 0
    assert "одна область каждого кадра альбома" in capsys.readouterr().out


def test_a_missing_argument_is_argparses_refusal(capsys: pytest.CaptureFixture[str]):
    with plugins.adding(entry_points=False):
        assert verso(["scans", "strips"]) == 2
    assert "usage: verso scans strips" in capsys.readouterr().err
