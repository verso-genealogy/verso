"""verso.core.scans.sheets — many cuts of an album on one image."""
from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from verso.core.scans.sheets import GAP, LABEL, contact_sheet, fit_width, strips_sheet


def test_a_contact_sheet_stacks_its_strips_a_gap_apart():
    strips = [Image.new("RGB", (100, 10), "black"), Image.new("RGB", (100, 20), "black")]
    sheet = contact_sheet(strips, 100)
    assert sheet.size == (100, 38)
    assert sheet.getpixel((5, 12)) == (255, 255, 255)         # the gap
    assert sheet.getpixel((5, 15)) == (0, 0, 0)


def test_fit_width_keeps_the_proportions():
    assert fit_width(Image.new("RGB", (200, 50)), 760).size == (760, 190)


def test_columns_lie_side_by_side_and_lines_stack():
    tall, wide = Image.new("RGB", (20, 100)), Image.new("RGB", (100, 20))
    assert strips_sheet([("a", tall), ("b", tall)], True, 200).size == (60 * 2 + GAP, 200 + LABEL)
    assert strips_sheet([("a", wide), ("b", wide)], False, 300).size == (300, 2 * (60 + LABEL) + GAP)
