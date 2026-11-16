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


def test_cards_reads_every_suffix_the_scan_tools_open(tmp_path: Path):
    """A TIFF card (or a phone's HEIC) is a card: `cards` takes the frames `IMAGE_SUFFIXES` names, as every subcommand."""
    Image = pytest.importorskip("PIL.Image")
    album = tmp_path / "tiffs"
    album.mkdir()
    for index in range(2):
        Image.new("RGB", (880, 670), (230, 222, 200)).save(album / f"card_{index:02d}.tif")
    code, out, err = _run(["-m", "verso.core.cli", "scans", "cards", str(album), str(tmp_path / "out")], tmp_path)
    assert code == 0, err
    assert out.splitlines() == ["00  card_00", "01  card_01"]


@pytest.mark.parametrize("sub", ["check", "headers", "crops", "spread", "zoom", "rows"])
def test_a_broken_scans_toml_is_refused_with_exit_2(sub: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                    monkeypatch: pytest.MonkeyPatch):
    """`check` reads the stanza now, and is a skill's first command: a `scans.toml` that is no TOML is said in a
    line and exits 2, in every subcommand that reads it — no traceback."""
    pytest.importorskip("PIL")
    monkeypatch.setenv("VERSO_LANG", "en")
    (tmp_path / "0001_10об.jpg").write_bytes(b"")
    (tmp_path / "scans.toml").write_text("[album.\"Маниловка 1902\"\nframes = spread\n", encoding="utf-8")
    more = {"headers": ["--out", str(tmp_path / "h")], "crops": ["--out", str(tmp_path / "c")],
            "spread": ["--folio", "10об"], "zoom": ["--folio", "10об"], "rows": ["--part", "1", "--folio", "10об"]}
    assert main(["scans", sub, str(tmp_path), *more.get(sub, [])]) == 2
    err = capsys.readouterr().err
    assert err.startswith("verso scans: ") and "scans.toml is not TOML" in err and "Traceback" not in err
