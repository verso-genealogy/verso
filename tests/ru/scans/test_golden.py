"""`verso scans check|headers|crops|spread|zoom|rows` write what the App's `verso-scans` wrote on the same album
(`tests/golden/scans`, captured by `python -m tests.scans_album golden`): the same files under the same names, the same
bytes, the same stdout and stderr (`<DIR>` for the album's root), the same exit code — in English and in Russian.
One line was reworded after the capture, on purpose: the one `rows` ends with named the App's `windows`, which
`verso scans` has not.

The golden bytes were captured on macOS, and on macOS every file matches by its bytes. Elsewhere Pillow's wheel is
another build whose JPEG coder and LANCZOS differ — the decoded pixels of a zoom drift by a few levels — so a file
of other bytes matches by its likeness (`thumbs`: mode, size, a 32×32 greyscale thumbnail) within
`scans_album.TOLERANCE`; the names, the output and the exit code stay exact everywhere. The likenesses were taken
on macOS from outputs byte-equal to the capture. `VERSO_GOLDEN_OFF_MACOS=1` takes the tolerant path on macOS."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PIL")

from tests.scans_album import (GOLDEN, LIBRARY_GOLDEN, SPREAD_CASES, SPREAD_GOLDEN, argv_for, draw_album, draw_cards,
                                draw_spreads, matches_golden, tree, unlike)
from verso.core.cli import main

CASES = sorted(GOLDEN.glob("*.json"))


def test_the_golden_outputs_are_there():
    assert len(CASES) >= 80


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_verso_scans_writes_what_the_app_wrote(path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capfd: pytest.CaptureFixture[str]):
    golden: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    root = tmp_path / "root"
    root.mkdir()
    draw_album(root)
    before = tree(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("VERSO_LANG", golden["lang"])
    code = main(["scans", *argv_for(golden["argv"], root)])
    out, err = capfd.readouterr()
    assert matches_golden(golden, root, before, code, out, err) == []


def test_every_app_golden_holds_the_likeness_of_each_file():
    for path in CASES:
        golden = json.loads(path.read_text(encoding="utf-8"))
        assert sorted(golden["thumbs"]) == sorted(golden["files"]), path.name


ZOOM = GOLDEN / "zoom-en.json"  # л. 1об, ч.1 godparents, row 2 of 3, at 6×, enhance 1.6 from the stanza


def _zoom(root: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], *extra: str) -> Path:
    """`zoom-en`'s run with `extra` arguments after its own; the file it wrote."""
    golden: dict[str, Any] = json.loads(ZOOM.read_text(encoding="utf-8"))
    draw_album(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("VERSO_LANG", "en")
    assert main(["scans", *argv_for(golden["argv"], root), *extra]) == 0
    capfd.readouterr()
    return root / "album" / "zoom_1об_a.jpg"


def _like(path: Path) -> str | None:
    return unlike(path, json.loads(ZOOM.read_text(encoding="utf-8"))["thumbs"]["album/zoom_1об_a.jpg"])


def test_the_tolerance_lets_a_jpeg_coders_drift_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capfd: pytest.CaptureFixture[str]):
    """The App's zoom decoded and encoded again at quality 75 — a coarser drift than another platform's Pillow
    (measured: 1 level in a cell of the thumbnail; this, up to 6) — is still the App's zoom."""
    from PIL import Image
    out = _zoom(tmp_path, monkeypatch, capfd)
    assert _like(out) is None
    with Image.open(out) as im:
        im.load()
    buffer = io.BytesIO()
    im.save(buffer, "JPEG", quality=75)
    out.write_bytes(buffer.getvalue())
    assert _like(out) is None


@pytest.mark.parametrize("extra", [["--row", "1", "3"], ["--enhance", "1"], ["--pad", "0.2"]],
                         ids=["another-row", "no-enhance", "wider-window"])
def test_a_wrong_window_or_enhance_is_caught_off_macos(extra: list[str], tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       capfd: pytest.CaptureFixture[str]):
    """Row 1 is a window of the same size elsewhere on the leaf (its thumbnail is 101 levels off at worst), the
    zoom without its enhance 1.6 is 29 off (26 on the mean), a wider pad is another size."""
    assert _like(_zoom(tmp_path, monkeypatch, capfd, *extra)) is not None


@pytest.mark.parametrize("wrong", ["upside-down", "shifted"])
def test_a_missed_rotation_or_a_shifted_crop_is_caught_off_macos(wrong: str, tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch,
                                                                 capfd: pytest.CaptureFixture[str]):
    """The App's zoom left upside down (its frame's `rotate_frames` missed; 117 levels off), or cut 3% lower on the
    page (101 off)."""
    from PIL import Image, ImageChops
    out = _zoom(tmp_path, monkeypatch, capfd)
    with Image.open(out) as im:
        im.load()
    bad = im.rotate(180) if wrong == "upside-down" else ImageChops.offset(im, 0, -round(im.height * 0.03))
    bad.save(out, quality=93)
    assert _like(out) is not None


def test_off_macos_a_wrong_image_fails_its_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                  capfd: pytest.CaptureFixture[str]):
    """The whole check, on the tolerant path: the App's zoom passes it, the same zoom without its enhance fails it."""
    golden: dict[str, Any] = json.loads(ZOOM.read_text(encoding="utf-8"))
    monkeypatch.setenv("VERSO_GOLDEN_OFF_MACOS", "1")
    for extra, wrong in (([], False), (["--enhance", "1"], True)):
        root = tmp_path / ("wrong" if wrong else "right")
        root.mkdir()
        draw_album(root)
        before = tree(root)
        monkeypatch.chdir(root)
        monkeypatch.setenv("VERSO_LANG", "en")
        code = main(["scans", *argv_for(golden["argv"], root), *extra])
        out, err = capfd.readouterr()
        if not wrong:
            out_file = root / "album" / "zoom_1об_a.jpg"
            out_file.write_bytes(out_file.read_bytes() + b"\0")  # other bytes, the same image
            assert matches_golden(golden, root, before, code, out, err) == []
        else:
            problems = matches_golden(golden, root, before, code, out, err)
            assert any("zoom_1об_a.jpg: not like the golden's" in p for p in problems), problems


CARDS = sorted(p for p in LIBRARY_GOLDEN.glob("cards*.json"))


def test_the_cards_goldens_are_there():
    assert len(CARDS) == 8


@pytest.mark.parametrize("path", CARDS, ids=[p.stem for p in CARDS])
def test_cards_writes_its_golden(path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                 capfd: pytest.CaptureFixture[str]):
    """`cards` writes what it wrote when a test still held it byte for byte to the reading plugin's script it
    replaced (`tests/golden/scans-library`, `python -m tests.scans_album golden-library`)."""
    golden: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    root = tmp_path / "root"
    draw_album(root)
    draw_cards(root)
    before = tree(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("VERSO_LANG", golden["lang"])
    code = main(["scans", *argv_for(golden["argv"], root)])
    out, err = capfd.readouterr()
    assert matches_golden(golden, root, before, code, out, err) == []


SPREADS = sorted(SPREAD_GOLDEN.glob("*.json"))


def test_every_subcommand_that_reads_a_stanza_has_its_spread_goldens():
    held = {json.loads(p.read_text(encoding="utf-8"))["argv"][0] for p in SPREADS}
    assert held == {"check", "headers", "crops", "spread", "zoom", "rows"}
    assert len(SPREADS) == 2 * len(SPREAD_CASES)


@pytest.mark.parametrize("path", SPREADS, ids=[p.stem for p in SPREADS])
def test_an_album_of_spreads_is_read_as_its_stanza_says(path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capfd: pytest.CaptureFixture[str]):
    """`frames = "spread"`: each frame named by its left leaf is two pages, cut to the half each lies on, in every
    subcommand that reads the stanza (`tests/golden/scans-spread`, `python -m tests.scans_album golden-spread`)."""
    golden: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    root = tmp_path / "root"
    draw_album(root)
    draw_cards(root)
    draw_spreads(root)
    before = tree(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("VERSO_LANG", golden["lang"])
    code = main(["scans", *argv_for(golden["argv"], root)])
    out, err = capfd.readouterr()
    assert matches_golden(golden, root, before, code, out, err) == []
