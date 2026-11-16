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


def test_strips_takes_every_suffix_the_scan_tools_open(tmp_path):
    """`strips` cuts from the frames `IMAGE_SUFFIXES` names — a `.heif` too, not a list of its own."""
    from verso.core.scans.cli import strips
    from verso.core.scans.image import IMAGE_SUFFIXES
    for index, suffix in enumerate(IMAGE_SUFFIXES):
        (tmp_path / f"{index:04d}{suffix}").write_bytes(b"")
    (tmp_path / "scans.toml").write_text("", encoding="utf-8")
    assert [p.suffix for p in strips.frames(tmp_path, None)] == list(IMAGE_SUFFIXES)


def test_quadrants_and_descreen_stand_a_tagged_frame_up(tmp_path):
    """A phone's frame lies on its side and says so by its EXIF tag: `quadrants` and `descreen` cut it as it stands,
    as every subcommand does (`open_upright`), not as it lies on disk."""
    Image = pytest.importorskip("PIL.Image")
    from verso.core.scans.cli import quadrants
    lying = Image.new("RGB", (300, 200), (230, 220, 200))                 # 300 wide as it lies, 200 wide standing
    exif = Image.Exif()
    exif[0x0112] = 6
    frame = tmp_path / "frame.jpg"
    lying.save(frame, exif=exif.tobytes())
    out = tmp_path / "q"
    out.mkdir()
    [tl, *_] = quadrants.quadrants(str(frame), str(out))
    assert Image.open(tl).size == ((100 + quadrants.OVERLAP_X) * quadrants.SCALE,
                                   (150 + quadrants.OVERLAP_Y) * quadrants.SCALE)
    with plugins.adding(entry_points=False):
        assert verso(["scans", "descreen", str(frame), "-", "1.0", "raw"]) == 0
    [written] = (tmp_path / "crops").iterdir()
    assert Image.open(written).size == (200, 300)
