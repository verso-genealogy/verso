"""verso.core.scans.level — a slanted record turned level, and the angle that does it.

Needs Pillow (the extra `[scans]`; the module skips without it, as the HEIC
tests do)."""
from __future__ import annotations

import random

import pytest

pytest.importorskip("PIL")

from PIL import Image, ImageDraw

from verso.core.scans.level import STRAIGHT, carry, level_crop, line_angle, slant, turn
from verso.core.scans.window import Box


def _lines(width: int = 1200, height: int = 900, seed: int = 1) -> Image.Image:
    """Rows of word-like bars on paper: what a written page looks like to a
    projection profile."""
    rng = random.Random(seed)
    im = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(im)
    for y in range(60, height - 60, 48):
        x = 60
        while x < width - 80:
            word = rng.randint(20, 90)
            draw.rectangle([x, y, x + word, y + 14], fill=(40, 40, 40))
            x += word + rng.randint(10, 25)
    return im


def _dark_rows(im: Image.Image) -> int:
    grey = im.convert("L")
    return sum(1 for y in range(grey.height)
               if any(grey.getpixel((x, y)) < 128 for x in range(0, grey.width, 2)))  # type: ignore[operator]


def test_no_turn_is_the_old_crop_pixel_for_pixel():
    im = _lines()
    box = (0.1, 0.2, 0.7, 0.45)
    old = im.crop(Box(*box).pixels(*im.size))
    assert level_crop(im, box, 0).tobytes() == old.tobytes()
    assert turn(im, 0) is im


def test_a_turned_window_is_the_turned_frames_crop():
    # level_crop resamples only the window, through the matrix `turn` uses;
    # a whole phone frame takes seconds to turn and its window a tenth of one.
    # The two agree up to rounding, not byte for byte: the window's offset is
    # the frame's plus a shift, equal in exact arithmetic and ~1e-13 apart in
    # floating point, and how that rounds depends on the platform (macOS arm64
    # matched to the byte, Linux CI did not at -12°). On noise a window off by
    # even a pixel differs almost everywhere, so ±1 in a few bytes still pins
    # the geometry.
    im = Image.effect_noise((617, 431), 60).convert("RGB")
    for angle in (0.1, -1.5, 3.25, -12.0, 44.9):
        turned = turn(im, angle)
        for box in ((0, 0, 1, 1), (0.1, 0.2, 0.6, 0.9), (0.33, 0.01, 0.34, 0.5)):
            fast = level_crop(im, box, angle)
            slow = turned.crop(Box(*box).pixels(*turned.size))
            assert fast.size == slow.size, (angle, box)
            diffs = [abs(a - b) for a, b in zip(fast.tobytes(), slow.tobytes(), strict=True)]
            off = sum(1 for d in diffs if d)
            assert max(diffs) <= 1 and off <= len(diffs) // 1000, \
                (angle, box, f"max {max(diffs)}, {off} of {len(diffs)} bytes differ")


def test_the_turn_keeps_the_corners_on_paper():
    im = Image.new("RGB", (400, 200), "black")
    turned = turn(im, 10)
    assert turned.size == (430, 268)        # PIL's expand; turn.test.js pins the same
    assert turned.getpixel((0, 0)) == (255, 255, 255)


def test_a_slanted_bar_comes_out_level():
    page = Image.new("RGB", (800, 400), "white")
    ImageDraw.Draw(page).rectangle([100, 200, 700, 205], fill="black")
    slanted = turn(page, 4)
    assert _dark_rows(slanted) > 30
    assert _dark_rows(turn(slanted, -4)) <= 10


@pytest.mark.parametrize("slant", [3, -3, 7, -7])
def test_the_angle_of_the_lines_is_found(slant):
    found = line_angle(turn(_lines(), slant))
    assert abs(found + slant) <= 0.3


def test_the_angle_is_found_inside_a_window_of_a_turned_frame():
    # Lines slanted 5°, looked at already turned 2° and through a window.
    slanted = turn(_lines(), 5)
    found = line_angle(slanted, box=(0.2, 0.2, 0.8, 0.6), angle=-2)
    assert abs(found + 5) <= 0.3


def test_blank_paper_leaves_the_angle_as_it_was():
    assert line_angle(Image.new("RGB", (800, 600), "white"), angle=1.5) == 1.5


def _ink_middle(im: Image.Image) -> tuple[float, float]:
    """The middle of the dark pixels of `im`, as fractions of it."""
    grey = im.convert("L")
    dark = [(x, y) for y in range(grey.height) for x in range(grey.width)
            if grey.getpixel((x, y)) < 100]  # type: ignore[operator]
    return (sum(x for x, _ in dark) / len(dark) / grey.width,
            sum(y for _, y in dark) / len(dark) / grey.height)


@pytest.mark.parametrize("angle", [2.0, -3.5, 12.0])
def test_a_window_carried_to_the_turned_frame_frames_the_same_ink(angle):
    # A blot off the middle of the frame, a window around it as the frame lies: carried to the frame turned
    # `angle`, the window is as many pixels and the blot is still where it was in it.
    im = Image.new("RGB", (900, 600), "white")
    ImageDraw.Draw(im).rectangle([600, 120, 640, 150], fill="black")
    box = (0.6, 0.15, 0.8, 0.3)
    carried = carry(box, *im.size, 0.0, angle)
    turned = turn(im, angle)
    window = turned.crop(Box(*carried).pixels(*turned.size))
    assert abs(window.width - 180) <= 2 and abs(window.height - 90) <= 2
    mx, my = _ink_middle(window)
    assert abs(mx - 0.444) < 0.03 and abs(my - 0.5) < 0.04
    # And back: the window as the frame lies, to a pixel.
    back = carry(carried, *im.size, angle, 0.0)
    assert all(abs(a - b) <= 2 / 600 for a, b in zip(back, box, strict=True))


def test_no_turn_carries_a_window_nowhere():
    assert carry((0.1, 0.2, 0.5, 0.6), 1000, 800, 0.0, 0.0) == (0.1, 0.2, 0.5, 0.6)
    assert carry((0.1, 0.2, 0.5, 0.6), 1000, 800, 3.0, 3.0) == (0.1, 0.2, 0.5, 0.6)


def test_a_window_carried_stays_on_the_frame():
    assert carry((0.0, 0.0, 1.0, 1.0), 900, 600, 0.0, 5.0) == pytest.approx((0.0, 0.0, 1.0, 1.0), abs=0.06)
    assert all(0.0 <= v <= 1.0 for v in carry((0.0, 0.0, 0.02, 1.0), 900, 600, 0.0, -8.0))


def test_a_slant_under_straight_is_none():
    assert slant(_lines()) == 0.0
    assert abs(slant(turn(_lines(), 2)) + 2) <= 0.3
    assert STRAIGHT == 0.1


def test_a_slant_is_found_inside_a_window_too():
    turned = turn(_lines(), -3)
    assert abs(slant(turned, (0.1, 0.1, 0.9, 0.9)) - 3) <= 0.3
