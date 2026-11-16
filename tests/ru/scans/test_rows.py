"""verso.ru.scans.rows and `verso scans rows` — where every record of a leaf begins, found in one step.

The pages are drawn here: a printed head of column titles, a счётъ column crossed by broken,
slanted rules, a number at the top of each record and lines of word-like bars beside it, a
monthly total under the last one. Needs Pillow for the drawing (the module skips without it, as
the level tests do); the record list and the pairing are pure.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from verso.ru.scans.rows import Key, Mark, Rows, count_window, cuts_from, find_marks, pair, parse_keys

# Where the records of the drawn page begin, as fractions of its height; the total stands at TOTAL.
STARTS = (0.21, 0.32, 0.46, 0.585, 0.70)
TOTAL = 0.83
WIDTH, HEIGHT = 1000, 1400
INK = (70, 50, 35)


def _page(starts: tuple[float, ...] = STARTS, *, total: float | None = TOTAL, seed: int = 3):
    """A leaf of a metric book's form as `detect` sees one."""
    from PIL import Image, ImageDraw, ImageFont
    rng = random.Random(seed)
    im = Image.new("RGB", (WIDTH, HEIGHT), (238, 230, 212))
    draw = ImageDraw.Draw(im)
    # The phone's light falls off towards the gutter.
    for x in range(WIDTH - 120, WIDTH):
        shade = round((x - (WIDTH - 120)) * 0.6)
        draw.line([(x, 0), (x, HEIGHT)], fill=(238 - shade, 230 - shade, 212 - shade))
    # The printed head: two lines of titles over every column, ruled under at 0.155.
    for y in (0.10, 0.125):
        x = 15
        while x < WIDTH - 60:
            word = rng.randint(25, 60)
            draw.rectangle([x, y * HEIGHT, x + word, y * HEIGHT + 12], fill=(30, 30, 30))
            x += word + 14
    draw.line([(0, 0.155 * HEIGHT), (WIDTH, 0.155 * HEIGHT)], fill=(30, 30, 30), width=3)
    # The columns' rules, slanted and broken where the pen skipped.
    for x in (60, 100, 150, 200):
        y = 0.155 * HEIGHT
        while y < HEIGHT - 20:
            dash = rng.randint(40, 140)
            draw.line([(x + y * 0.012, y), (x + (y + dash) * 0.012, y + dash)], fill=(40, 40, 40), width=2)
            y += dash + rng.randint(4, 12)
    font = ImageFont.load_default(size=34)
    for number, start in enumerate(starts, 1):
        top = start * HEIGHT
        if number == 1:
            draw.line([(30, top), (32, top + 30)], fill=INK, width=3)       # a «1» is one stroke
        else:
            draw.text((18, top - 4), str(number), fill=INK, font=font)
        draw.text((112, top - 2), str(number + 10), fill=INK, font=ImageFont.load_default(size=22))
        for line in range(rng.randint(3, 4)):
            x, y = 215, top + 6 + line * 0.024 * HEIGHT
            while x < WIDTH - 40:
                word = rng.randint(20, 80)
                draw.rectangle([x, y, x + word, y + 10], fill=INK)
                x += word + rng.randint(10, 22)
    if total is not None:
        y = total * HEIGHT
        draw.rectangle([20, y, 140, y + 12], fill=INK)
        draw.rectangle([215, y, 600, y + 12], fill=INK)
    return im


@pytest.fixture
def pil():
    return pytest.importorskip("PIL")


# --------------------------------------------------------------------------- the record list

def test_keys_name_the_series_the_number_and_the_marks_that_are_none():
    keys = parse_keys("+ж3, м1 ,-,12,1а,*")
    assert [str(k) for k in keys] == ["+ж3", "м1", "-", "12", "1а", "*"]
    assert keys[0] == Key(3, "ж", carried=True)
    assert keys[1] == Key(1, "м")
    assert keys[2].record is None and not keys[2].rest
    assert keys[3] == Key(12)
    assert keys[4] == Key("1а")
    assert keys[5].rest


@pytest.mark.parametrize("text", ["м1,x2", "м1,+ж2", "м1,*,ж2", "-,*", "м"])
def test_a_list_that_cannot_be_read_is_refused(text: str):
    with pytest.raises(ValueError):
        parse_keys(text)


def test_the_count_column_is_the_left_of_the_leaf():
    assert count_window(1, 0.0, 1.0) == (0.0, 0.18)
    assert count_window(2, 0.1, 0.84) == (0.1, 0.2036)
    assert count_window(None, 0.5, 1.0) == (0.5, 0.59)


# --------------------------------------------------------------------------- pairing

ROWS = Rows(marks=(Mark(0.2, 0.22), Mark(0.3, 0.32), Mark(0.45, 0.47)), cuts=(0.19, 0.29, 0.44, 0.6))


def test_each_record_takes_the_band_from_its_cut_to_the_next():
    bands = pair(parse_keys("м1,ж1,м2"), ROWS, top=0.17)
    assert [(str(k), y0, y1) for k, y0, y1 in bands] == [
        ("м1", 0.19, 0.29), ("ж1", 0.29, 0.44), ("м2", 0.44, 0.6)]


def test_a_mark_that_is_no_record_closes_the_one_above():
    bands = pair(parse_keys("м1,-,м2"), ROWS, top=0.17)
    assert [(str(k), y0, y1) for k, y0, y1 in bands] == [("м1", 0.19, 0.29), ("м2", 0.44, 0.6)]


def test_the_rest_of_the_marks_are_none_after_a_star():
    bands = pair(parse_keys("м1,*"), ROWS, top=0.17)
    assert [(str(k), y0, y1) for k, y0, y1 in bands] == [("м1", 0.19, 0.29)]


def test_a_carried_record_holds_the_writing_above_the_first_mark():
    bands = pair(parse_keys("+ж7,м1,ж1,м2"), ROWS, top=0.17)
    key, y0, y1 = bands[0]
    assert (str(key), y0, y1) == ("+ж7", 0.17, 0.19)


def test_counts_that_differ_are_refused_not_guessed():
    with pytest.raises(ValueError, match="2"):
        pair(parse_keys("м1,ж1"), ROWS, top=0.17)
    with pytest.raises(ValueError, match="4"):
        pair(parse_keys("м1,ж1,м2,ж2"), ROWS, top=0.17)
    with pytest.raises(ValueError):
        pair(parse_keys("м1,ж1,м2,ж2,*"), ROWS, top=0.17)


def test_nothing_above_the_first_mark_carries_nothing():
    with pytest.raises(ValueError):
        pair(parse_keys("+ж7,м1,ж1,м2"), ROWS, top=0.19)


def test_cuts_by_hand_are_rising_fractions():
    assert cuts_from([0.2, 0.3, 0.41]).marks == (Mark(0.2, 0.2), Mark(0.3, 0.3))
    for bad in ([0.2], [0.3, 0.2], [0.2, 1.4], [0.2, 0.2]):
        with pytest.raises(ValueError):
            cuts_from(bad)


# --------------------------------------------------------------------------- marks

def test_a_thin_run_is_a_rule_and_near_pieces_are_one_mark():
    signal = [0.0] * 1000
    for i in range(300, 303):            # a rule across: three rows
        signal[i] = 0.9
    for i in (*range(500, 510), *range(514, 524)):   # one number, its stroke broken
        signal[i] = 0.3
    for i in range(700, 716):
        signal[i] = 0.25
    assert find_marks(signal, 1000) == [(500, 524), (700, 716)]


def test_a_stray_stroke_much_fainter_than_the_page_s_numbers_is_no_mark():
    signal = [0.0] * 1000
    for start in (100, 300, 500):
        for i in range(start, start + 20):
            signal[i] = 0.4
    for i in range(700, 706):
        signal[i] = 0.05
    assert [a for a, _ in find_marks(signal, 1000)] == [100, 300, 500]


# --------------------------------------------------------------------------- detection

@pytest.mark.usefixtures("pil")
def test_every_record_s_number_is_a_mark_and_the_total_one_more():
    from verso.ru.scans.rows import detect
    rows = detect(_page(), top=0.17)
    assert len(rows.marks) == len(STARTS) + 1
    for mark, start in zip(rows.marks, (*STARTS, TOTAL), strict=True):
        assert abs(mark.y0 - start) < 0.012
    assert len(rows.cuts) == len(rows.marks) + 1
    # A cut lies in the white above its number — never inside the record above.
    for cut, start in zip(rows.cuts, (*STARTS, TOTAL), strict=False):
        assert start - 0.03 <= cut <= start + 0.002
    assert not rows.cut


@pytest.mark.usefixtures("pil")
def test_a_mark_the_top_line_cuts_is_left_out():
    from verso.ru.scans.rows import detect
    rows = detect(_page(), top=0.13)      # through the second line of the column titles
    assert rows.cut
    assert abs(rows.marks[0].y0 - STARTS[0]) < 0.012


@pytest.mark.usefixtures("pil")
def test_the_last_record_ends_where_a_record_of_its_page_would():
    from verso.ru.scans.rows import detect
    rows = detect(_page(total=None), top=0.17)
    assert len(rows.marks) == len(STARTS)
    assert rows.cuts[-1] - rows.cuts[-2] < 0.2


@pytest.mark.usefixtures("pil")
def test_a_ruler_is_drawn_and_a_sheet_lays_them_side_by_side():
    from verso.ru.scans.rows import _latin, detect, ruler, sheet
    page = _page()
    rows = detect(page, top=0.17)
    one = ruler(page, rows, x0=0.0, x1=1.0, count=count_window(1, 0.0, 1.0), top=0.17, bottom=1.0,
                title="кадр2 · ч.1")
    two = sheet([one, one])
    assert two.width > 2 * one.width and two.height == one.height
    assert _latin("кадр2 · ч.1") == "frame 2 · part 1"


# --------------------------------------------------------------------------- the commands


ALBUM = "Маниловка 1900 (999-1-3)"


def _album(tmp_path: Path) -> Path:
    directory = tmp_path / "album"
    directory.mkdir()
    _page().save(directory / "IMG_0001.jpg", quality=92)
    _page(STARTS[:3], seed=5).save(directory / "IMG_0002.jpg", quality=92)
    (directory / "scans.toml").write_text(f'[album."{ALBUM}"]\ntop = 0.17\n', encoding="utf-8")
    return directory


def _run(*argv: str) -> int:
    from verso.core.cli import main
    return main(["scans", *argv])


@pytest.mark.usefixtures("pil")
def test_rows_prints_the_marks_and_draws_one_sheet_for_several_leaves(tmp_path: Path, capsys):
    from PIL import Image
    directory = _album(tmp_path)
    before = (directory / "scans.toml").read_bytes()
    out = tmp_path / "sheet.jpg"
    assert _run("rows", str(directory), "--frames", "--folio", "1", "2", "--part", "1",
                "--out", str(out)) == 0
    printed = capsys.readouterr().out
    assert printed.count("кадр") >= 2
    assert "below 0.17" in printed or "ниже 0.17" in printed          # the stanza's top
    with Image.open(out) as sheet:
        assert sheet.width > sheet.height
    assert (directory / "scans.toml").read_bytes() == before            # it writes no window
