"""`verso scans rows|zoom --angle DEG|auto` — a slanted leaf turned level before it is read.

The phone was held crooked: the drawn leaf of `test_rows` is turned 2° clockwise, and its lines fall to the right.
As it lies, the slanted rules break into a mark of their own and `rows` finds one record too many; turned 2° back,
the marks are the records again. `zoom` cuts a window of the same leaf level. Needs Pillow (the module skips without
it)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from PIL import Image

from tests.ru.scans.test_rows import HEIGHT, STARTS, TOTAL, WIDTH, _page
from verso.core.scans.level import carry, line_angle, turned_size
from verso.ru.messages import t

SLANT = -2.0
ALBUM = "Маниловка 1900 (999-1-3)"
# A record's lines, named on the slanted frame as it lies: the second record, across the writing.
BOX = ("0.2", "0.31", "0.97", "0.45")


def _album(tmp_path: Path, angle: float = SLANT) -> Path:
    from verso.core.scans.level import turn
    directory = tmp_path / "album"
    directory.mkdir()
    turn(_page(), angle).save(directory / "IMG_0001.jpg", quality=92)
    (directory / "scans.toml").write_text(f'[album."{ALBUM}"]\ntop = 0.17\n', encoding="utf-8")
    return directory


def _run(*argv: str) -> int:
    from verso.core.cli import main
    return main(["scans", *argv])


def _marks(printed: str) -> list[float]:
    """Where each mark `rows` printed begins."""
    return [float(line.split()[1].split("–")[0]) for line in printed.splitlines()
            if line.startswith("  ") and "–" in line and line.split()[0].isdigit()]


def _starts_on_the_level_page(angle: float) -> list[float]:
    """Where each record's number (and the total) stands on the slanted frame turned `angle`, as fractions."""
    slanted = turned_size(WIDTH, HEIGHT, SLANT)
    return [carry(carry((0.03, y, 0.03, y), WIDTH, HEIGHT, 0.0, SLANT), *slanted, 0.0, angle)[1]
            for y in (*STARTS, TOTAL)]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- rows

def test_a_slanted_leaf_gives_the_wrong_marks_until_it_is_turned_level(tmp_path: Path, capsys):
    directory = _album(tmp_path)
    before = (directory / "scans.toml").read_bytes()
    argv = ("rows", str(directory), "--frames", "--folio", "1", "--part", "1")
    assert _run(*argv, "--out", str(tmp_path / "lies.jpg")) == 0
    as_it_lies = _marks(capsys.readouterr().out)
    # A record and its total each give a mark — six; the slanted rules break into a seventh.
    assert len(as_it_lies) != len(STARTS) + 1

    out = tmp_path / "level.jpg"
    assert _run(*argv, "--angle", "auto", "--out", str(out)) == 0
    printed = capsys.readouterr().out
    assert str(t("scans.angle.level", angle="2")) in printed
    assert str(t("scans.rows.found", where="кадр1", part=1, marks=6, top="0.178")) in printed
    marks = _marks(printed)
    assert len(marks) == len(STARTS) + 1
    for mark, start in zip(marks, _starts_on_the_level_page(2.0), strict=True):
        assert abs(mark - start) < 0.012
    with Image.open(out) as ruler:
        assert ruler.width > 0
    assert (directory / "scans.toml").read_bytes() == before            # it writes no window


def test_a_given_angle_reads_as_the_measured_one(tmp_path: Path, capsys):
    directory = _album(tmp_path)
    argv = ("rows", str(directory), "--frames", "--folio", "1", "--part", "1")
    _run(*argv, "--angle", "auto", "--out", str(tmp_path / "auto.jpg"))
    measured = capsys.readouterr().out
    _run(*argv, "--angle", "2", "--out", str(tmp_path / "given.jpg"))
    given = capsys.readouterr().out
    assert _marks(given) == _marks(measured)
    assert _sha(tmp_path / "auto.jpg") == _sha(tmp_path / "given.jpg")


def test_a_straight_leaf_is_read_as_it_always_was(tmp_path: Path, capsys):
    directory = _album(tmp_path, 0.0)
    argv = ("rows", str(directory), "--frames", "--folio", "1", "--part", "1")
    _run(*argv, "--out", str(tmp_path / "plain.jpg"))
    plain = capsys.readouterr().out.replace(str(tmp_path / "plain.jpg"), "OUT")
    _run(*argv, "--angle", "auto", "--out", str(tmp_path / "auto.jpg"))
    auto = capsys.readouterr().out.replace(str(tmp_path / "auto.jpg"), "OUT")
    assert auto == plain
    assert _sha(tmp_path / "auto.jpg") == _sha(tmp_path / "plain.jpg")


def test_the_leaf_and_the_count_column_are_carried_to_the_turned_page(tmp_path: Path, capsys):
    directory = _album(tmp_path)
    assert _run("rows", str(directory), "--frames", "--folio", "1", "--part", "1", "--x0", "0.02", "--x1", "0.98",
                "--count", "0.02", "0.2", "--angle", "2", "--out", str(tmp_path / "r.jpg")) == 0
    marks = _marks(capsys.readouterr().out)
    assert len(marks) == len(STARTS) + 1


# --------------------------------------------------------------------------- zoom

def _zoom(directory: Path, out: Path, *extra: str) -> int:
    return _run("zoom", str(directory), "--frames", "--folio", "1", "--scale", "1", "--colour",
                "--out", str(out), *extra)


def test_zoom_cuts_a_slanted_record_level(tmp_path: Path, capsys):
    directory = _album(tmp_path)
    assert _zoom(directory, tmp_path / "lies.jpg", "--box", *BOX) == 0
    capsys.readouterr()
    assert _zoom(directory, tmp_path / "level.jpg", "--box", *BOX, "--angle", "auto") == 0
    printed = capsys.readouterr().out
    assert str(t("scans.angle.turned", angle="2")) in printed
    with Image.open(tmp_path / "lies.jpg") as lies, Image.open(tmp_path / "level.jpg") as level:
        # As many pixels wide and high: the window is carried, not grown.
        assert abs(level.width - lies.width) <= 2 and abs(level.height - lies.height) <= 2
        # The lines inside the window as it lies fall 2°; inside the window cut level they lie straight.
        assert abs(line_angle(lies.convert("RGB")) - 2.0) <= 0.3
        assert abs(line_angle(level.convert("RGB"))) <= 0.3


def test_zoom_says_the_window_on_the_turned_page(tmp_path: Path, capsys):
    directory = _album(tmp_path)
    assert _zoom(directory, tmp_path / "z.jpg", "--box", *BOX, "--angle", "2") == 0
    printed = capsys.readouterr().out
    slanted = turned_size(WIDTH, HEIGHT, SLANT)
    x0, y0, x1, y1 = carry(tuple(float(v) for v in BOX), *slanted, 0.0, 2.0)  # type: ignore[arg-type]
    assert f"x {x0:g}–{x1:g}, y {y0:g}–{y1:g}{t('scans.angle.turned', angle='2')}" in printed


def test_zoom_carries_a_window_named_by_its_column_and_row(tmp_path: Path, capsys):
    directory = _album(tmp_path)
    flags = ("--part", "1", "--col", "godparents", "--row", "2", "5")
    assert _zoom(directory, tmp_path / "lies.jpg", *flags) == 0
    lies = capsys.readouterr().out
    assert _zoom(directory, tmp_path / "level.jpg", *flags, "--angle", "2") == 0
    level = capsys.readouterr().out
    assert str(t("scans.angle.turned", angle="2")) in level and "row 2/5" in level
    assert lies.split(" — ")[1].split(",")[0] != level.split(" — ")[1].split(",")[0]


def test_zoom_on_a_straight_leaf_is_cut_as_it_always_was(tmp_path: Path, capsys):
    directory = _album(tmp_path, 0.0)
    _zoom(directory, tmp_path / "plain.jpg", "--box", *BOX)
    plain = capsys.readouterr().out.replace(str(tmp_path / "plain.jpg"), "OUT")
    _zoom(directory, tmp_path / "auto.jpg", "--box", *BOX, "--angle", "auto")
    auto = capsys.readouterr().out.replace(str(tmp_path / "auto.jpg"), "OUT")
    assert auto == plain
    assert _sha(tmp_path / "auto.jpg") == _sha(tmp_path / "plain.jpg")


# --------------------------------------------------------------------------- the limit

@pytest.mark.parametrize("command", ["rows", "zoom"])
@pytest.mark.parametrize("angle", ["46", "-90", "steep", "nan"])
def test_an_angle_past_a_crooked_frame_is_refused(tmp_path: Path, capsys, command: str, angle: str):
    directory = _album(tmp_path)
    flags = ("--part", "1") if command == "rows" else ("--box", *BOX)
    assert _run(command, str(directory), "--frames", "--folio", "1", *flags, "--angle", angle) == 2
    assert str(t("scans.angle.bad", angle=angle, limit="45")) in capsys.readouterr().err
