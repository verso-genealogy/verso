"""verso-ru's subcommands of `verso scans` (`Plugin.scans`): listed with the core's, each answering `--help` in both
languages, and `cards` writing the cards' windows."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.scans_album import draw_cards
from verso.core.cli import main
from verso.core.scans.cli import CORE, subcommands
from verso.ru.plugin import PLUGIN, SCANS

def test_the_plugin_brings_its_subcommands():
    assert PLUGIN.scans is SCANS
    assert sorted(SCANS) == ["cards", "check", "crops", "headers", "rows", "spread", "zoom"]
    assert subcommands() == {**CORE, **SCANS}


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_every_subcommand_answers_help(lang: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VERSO_LANG", lang)
    assert main(["scans", "--help"]) == 0
    listing = capsys.readouterr().out
    for name in {**CORE, **SCANS}:
        assert f"\n    {name} " in listing
        assert main(["scans", name, "--help"]) == 0
        assert capsys.readouterr().out.startswith(f"usage: verso scans {name} ")


def test_the_windows_are_not_this_commands(capsys: pytest.CaptureFixture[str], tmp_path: Path):
    """`--record`, `--remember` and `--gender` write a window into scans.toml: the App's, not the library's."""
    for flag in ("--record", "--remember", "--gender"):
        assert main(["scans", "zoom", str(tmp_path), "--folio", "1", flag]) == 2
        assert f"unrecognized arguments: {flag}" in capsys.readouterr().err


def _run(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    done = subprocess.run([sys.executable, *argv], cwd=cwd, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                          capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    return done.returncode, done.stdout, done.stderr


@pytest.mark.parametrize(("flags", "written"), [
    ([], {"00.jpg", "01.jpg", "02.jpg", "numbers.jpg", "leaves.jpg"}),
    (["--table", "0:0:0.7:0.4"], {"00.jpg", "01.jpg", "02.jpg", "numbers.jpg", "leaves.jpg"}),
    (["--zoom", "1:0.2:0.1:0.6:0.4"], {"zoom_01.jpg"}),
])
def test_cards_writes_the_cards_windows(tmp_path: Path, flags: list[str], written: set[str]):
    pytest.importorskip("PIL")
    album = draw_cards(tmp_path)
    code, out, err = _run(["-m", "verso.core.cli", "scans", "cards", str(album), str(tmp_path / "out"), *flags], tmp_path)
    assert code == 0, err
    assert {p.name for p in (tmp_path / "out").iterdir()} == written
    if not flags:
        assert out.splitlines() == ["00  card_00", "01  card_01", "02  card_02"]


def test_cards_of_an_empty_album_is_refused(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    code, _, err = _run(["-m", "verso.core.cli", "scans", "cards", str(tmp_path / "empty"), str(tmp_path / "a")], tmp_path)
    assert code == 1
    assert str(tmp_path / "empty") in err
