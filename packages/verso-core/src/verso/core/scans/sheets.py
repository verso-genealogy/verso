"""Many cuts of an album on one image, so one look answers for 20–40 frames at once.

`contact_sheet` stacks strips of equal width top to bottom — the running headers of a run of leaves, to find where
each part begins. `strips_sheet` lays the same region of every frame side by side (a column, left to right) or one
above another (a line, top to bottom), each labelled with the name it is given — «which frame holds двор 45».
A sheet is for FINDING, not reading: the frame it names is read at full size.

Pillow is imported where it is used.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["GAP", "LABEL", "contact_sheet", "fit_width", "label_font", "strips_sheet"]

# px reserved for a strip's label, and between two strips.
LABEL = 28
GAP = 6
# Fonts with Cyrillic, where a system keeps them; Pillow's own when none is there.
_FONTS = ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def fit_width(im: Any, width: int) -> Any:
    """`im` scaled to `width`, its proportions kept (LANCZOS)."""
    from PIL import Image
    return im.resize((width, int(im.height * width / im.width)), Image.Resampling.LANCZOS)


def contact_sheet(strips: list[Any], width: int, gap: int = 4) -> Any:
    """`strips` (each `width` wide) one under another on white, `gap` px apart, the last followed by one too."""
    from PIL import Image
    sheet = Image.new("RGB", (width, sum(s.height + gap for s in strips)), "white")
    y = 0
    for strip in strips:
        sheet.paste(strip, (0, y))
        y += strip.height + gap
    return sheet


def label_font() -> Any:
    """A font for the labels: Arial or DejaVu Sans where the system has one, else Pillow's own."""
    from PIL import ImageFont
    for name in _FONTS:
        if Path(name).exists():
            return ImageFont.truetype(name, 20)
    return ImageFont.load_default()


def strips_sheet(strips: list[tuple[str, Any]], column: bool, size: int) -> Any:
    """The labelled strips on one image: a `column` scaled to `size` px high and laid left to right, else each
    scaled to `size` px wide and stacked top to bottom; each label in red above its strip."""
    from PIL import Image, ImageDraw
    f = label_font()
    scaled = []
    for label, im in strips:
        if column:  # equal height, laid left to right
            im = im.resize((max(1, round(im.width * size / im.height)), size))
        else:  # equal width, stacked top to bottom
            im = im.resize((size, max(1, round(im.height * size / im.width))))
        scaled.append((label, im))
    if column:
        width = sum(max(im.width, 60) for _, im in scaled) + GAP * (len(scaled) - 1)
        out = Image.new("RGB", (width, size + LABEL), "white")
        x = 0
        for label, im in scaled:
            ImageDraw.Draw(out).text((x + 2, 2), label, fill="red", font=f)
            out.paste(im, (x, LABEL))
            x += max(im.width, 60) + GAP
    else:
        height = sum(im.height + LABEL for _, im in scaled) + GAP * (len(scaled) - 1)
        out = Image.new("RGB", (size, height), "white")
        y = 0
        for label, im in scaled:
            ImageDraw.Draw(out).text((2, y + 2), label, fill="red", font=f)
            out.paste(im, (0, y + LABEL))
            y += im.height + LABEL + GAP
    return out
