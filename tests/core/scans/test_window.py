"""verso.core.scans.window — a crop window in fractions of the leaf."""
from __future__ import annotations

from verso.core.scans.window import FULL_WIDTH, Box


def test_a_box_is_pixels_of_any_frame():
    box = Box(0.1, 0.25, 0.5, 0.75)
    assert box.pixels(1000, 800) == (100, 200, 500, 600)
    assert box.pixels(999, 801) == (99, 200, 499, 600)        # truncated, as every cut has always been


def test_a_box_says_itself_in_fractions():
    assert str(Box(0.0, 0.17, 1.0, 1.0)) == "x 0–1, y 0.17–1"


def test_the_full_width_is_the_leaf():
    assert FULL_WIDTH == (0.0, 1.0)
