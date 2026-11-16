"""`zoom` in two steps (`verso.ru.scans.cli.zoom.locate`, `cut`): what a caller with a window of its own — the review
page's `verso-scans zoom --record` — hands `cut` is cut, written and said as `--box` is, and at the turn it gives."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from tests.scans_album import draw_album
from verso.core.scans.level import turn
from verso.ru.scans.album import open_page
from verso.ru.scans.cli import zoom

BOX = [0.1, 0.2, 0.6, 0.5]


def _args(directory: Path, *flags: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    zoom.add_arguments(parser)
    return parser.parse_args([str(directory), "--scale", "2", *flags])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    draw_album(tmp_path)
    monkeypatch.chdir(tmp_path)          # the faded album's stanza names its village relative, as an export writes it
    return tmp_path


def test_a_window_handed_to_cut_is_cut_as_box_is(root: Path, capsys: pytest.CaptureFixture[str]):
    album = root / "faded"
    assert zoom.run(_args(album, "--folio", "1об", "--box", *map(str, BOX), "--out", str(root / "box.jpg"))) == 0
    said_box = capsys.readouterr().out
    args = _args(album, "--folio", "1об", "--out", str(root / "cut.jpg"))
    target = zoom.locate(args)
    assert (target.page.label, target.title, target.enhance, target.from_stanza) == ("1об", "Собакевичи 1901", 1.7, True)
    window = zoom.cut(args, target, box=BOX)
    assert (window.x0, window.y0, window.x1, window.y1) == tuple(BOX)
    assert _sha(root / "cut.jpg") == _sha(root / "box.jpg")
    assert capsys.readouterr().out == said_box.replace(str(root / "box.jpg"), str(root / "cut.jpg"))


def test_a_window_handed_to_cut_wins_over_box_and_is_cut_at_its_turn(root: Path):
    from PIL import Image
    album = root / "album"
    args = _args(album, "--folio", "1", "--box", "0.0", "0.0", "1.0", "1.0", "--colour", "--out", str(root / "t.jpg"))
    target = zoom.locate(args)
    zoom.cut(args, target, box=BOX, angle=3.0)
    page = turn(open_page(album, target.page, 180), 3.0)            # the album's stanza turns its leaf 1 by 180
    w, h = page.size
    with Image.open(root / "t.jpg") as cut:
        expected = (round((int(w * 0.6) - int(w * 0.1)) * 2), round((int(h * 0.5) - int(h * 0.2)) * 2))
        assert abs(cut.width - expected[0]) <= 2 and abs(cut.height - expected[1]) <= 2


def test_locate_says_how_a_page_is_written(root: Path):
    with pytest.raises(SystemExit, match="An об page is written"):
        zoom.locate(_args(root / "album", "--folio", "9"))
