"""verso-ru's subcommands of `verso scans` (`Plugin.scans`): listed with the core's, each answering `--help` in both
languages, and `cards` writing what the reading plugin's `card_crops.py` it replaces writes."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from verso.core.cli import main
from verso.core.scans.cli import CORE, subcommands
from verso.ru.plugin import PLUGIN, SCANS

ROOT = Path(__file__).resolve().parents[3]
CARDS = ROOT / "plugins" / "verso-reading" / "skills" / "agri-census-1917" / "scripts" / "card_crops.py"


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


def _cards(root: Path) -> Path:
    """Three invented card frames: a table over a header on a wide spread, one tagged to stand on its side."""
    from PIL import Image, ImageDraw
    album = root / "cards"
    album.mkdir()
    for index in range(3):
        im = Image.new("RGB", (880, 670), (230, 222, 200))
        draw = ImageDraw.Draw(im)
        for row in range(8):
            draw.line((20, 40 + 25 * row, 560, 40 + 25 * row), fill=(60, 50, 40), width=2)
        draw.rectangle((680, 250, 780, 285), outline=(60, 50, 40), width=3)
        draw.text((690, 255), f"{index + 7}", fill=(20, 20, 20))
        draw.text((820, 8), f"{index + 41}", fill=(80, 80, 80))
        im.save(album / f"card_{index:02d}.jpg", quality=90)
    return album


def _run(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    done = subprocess.run([sys.executable, *argv], cwd=cwd, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                          capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    return done.returncode, done.stdout, done.stderr


def _files(directory: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir())}


@pytest.mark.parametrize("flags", [[], ["--zoom", "1:0.2:0.1:0.6:0.4"], ["--table", "0:0:0.7:0.4"]])
def test_cards_writes_what_the_script_writes(tmp_path: Path, flags: list[str]):
    pytest.importorskip("PIL")
    album = _cards(tmp_path)
    script = _run([str(CARDS), str(album), str(tmp_path / "a"), *flags], tmp_path)
    ours = _run(["-m", "verso.core.cli", "scans", "cards", str(album), str(tmp_path / "b"), *flags], tmp_path)
    assert script[0] == ours[0] == 0, (script, ours)
    assert script[1].replace(str(tmp_path / "a"), "OUT") == ours[1].replace(str(tmp_path / "b"), "OUT")
    assert _files(tmp_path / "a") == _files(tmp_path / "b") != {}


def test_cards_of_an_empty_album_is_refused_as_the_script_does(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    script = _run([str(CARDS), str(tmp_path / "empty"), str(tmp_path / "a")], tmp_path)
    ours = _run(["-m", "verso.core.cli", "scans", "cards", str(tmp_path / "empty"), str(tmp_path / "a")], tmp_path)
    assert script == ours and script[0] == 1
