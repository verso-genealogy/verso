"""Turning a frame so a slanted record lies level, and finding the angle that does.

A phone held over a bound дело photographs its lines at a slant, and the binding
bends them further towards the spine. An axis-aligned window around a slanted
line has to be taller than the line, and the height it gains is the next
record's rows — which is how a godparent gets read off the wrong row. So the
reader turns the IMAGE until the lines lie level and draws an ordinary window on
it; the window keeps that angle (`RecordBox.angle`), and its crop is cut from the
frame turned the same way.

The turn is `Image.rotate(angle, BICUBIC, expand=True, fillcolor=white)`: degrees
counter-clockwise, the sign of `rotate`/`rotate_frames`; `expand`, so that no
corner of the leaf is cut off; white, because that is the paper. The page turns
the frame the same way on a canvas (the review page's `turn.js`) and sizes it by
the same arithmetic, so a window drawn there is the window cut here.

Pillow is imported where it is used: the window's arithmetic runs without it.
"""
from __future__ import annotations

from itertools import pairwise
from typing import Any

from verso.core.scans.window import Box

__all__ = ["level_crop", "line_angle", "turn", "turned_size"]

# A window's slant is searched this far either side of where it stands.
SPAN = 10.0
_COARSE = 0.25
_FINE = 0.05
# The width the profile is measured at: a 600-px line moves 2.6 px over its
# length at 0.25°, which is what the coarse step needs to see.
_WIDTH = 600


def _paper(im: Any) -> tuple[Any, int | tuple[int, int, int]]:
    if im.mode == "L":
        return im, 255
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im, (255, 255, 255)


def turn(im: Any, angle: float) -> Any:
    """The frame turned `angle` degrees counter-clockwise, its corners kept on
    paper white; the frame itself at 0."""
    if not angle:
        return im
    from PIL import Image
    im, fill = _paper(im)
    return im.rotate(angle, Image.Resampling.BICUBIC, expand=True, fillcolor=fill)


def _turn_matrix(w: int, h: int, angle: float) -> tuple[list[float], int, int]:
    """The matrix and size of `Image.rotate(angle, expand=True)` on a w×h frame —
    Pillow's own arithmetic, step for step, so a window cut through it is the
    window `turn` would give. The matrix maps a pixel of the turned frame back
    to the frame (`Image.transform` samples that way)."""
    import math
    rad = -math.radians(angle % 360.0)
    m = [round(math.cos(rad), 15), round(math.sin(rad), 15), 0.0,
         round(-math.sin(rad), 15), round(math.cos(rad), 15), 0.0]

    def apply(x: float, y: float) -> tuple[float, float]:
        return m[0] * x + m[1] * y + m[2], m[3] * x + m[4] * y + m[5]

    cx, cy = w / 2, h / 2
    m[2], m[5] = apply(-cx, -cy)
    m[2] += cx
    m[5] += cy
    xs, ys = zip(*(apply(x, y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))), strict=True)
    nw = math.ceil(max(xs)) - math.floor(min(xs))
    nh = math.ceil(max(ys)) - math.floor(min(ys))
    m[2], m[5] = apply(-(nw - w) / 2.0, -(nh - h) / 2.0)
    return m, nw, nh


def turned_size(w: int, h: int, angle: float) -> tuple[int, int]:
    """The size of a w×h frame turned `angle` degrees counter-clockwise with
    `expand=True` — what `turn` gives, and what a window drawn at that turn is a
    fraction of — without turning anything."""
    if not angle % 360:
        return w, h
    _, nw, nh = _turn_matrix(w, h, angle)
    return nw, nh


def level_crop(im: Any, box: tuple[float, float, float, float], angle: float) -> Any:
    """The window `box` — fractions of the frame turned by `angle` — cut out.

    The same pixels as `turn(im, angle).crop(…)` up to rounding (±1 in a rare
    byte: the shifted offset rounds differently by platform), without turning
    the whole frame: only the window is resampled, through the matrix `turn` would use
    shifted to the window's corner. A 9248×6936 phone frame takes 2.8 s to turn
    and its window 0.1 s to cut, which is what lets the review page fetch the
    part of a frame in view at full resolution as the reader zooms and pans.
    """
    if not angle:
        return im.crop(Box(*box).pixels(*im.size))
    from PIL import Image
    im, fill = _paper(im)
    w, h = im.size
    m, nw, nh = _turn_matrix(w, h, angle)
    x0, y0, x1, y1 = Box(*box).pixels(nw, nh)
    shifted = (m[0], m[1], m[0] * x0 + m[1] * y0 + m[2],
               m[3], m[4], m[3] * x0 + m[4] * y0 + m[5])
    return im.transform((x1 - x0, y1 - y0), Image.Transform.AFFINE, shifted,
                        Image.Resampling.BICUBIC, fillcolor=fill)


def _sharpness(region: Any, delta: float) -> float:
    """How cleanly the rows of `region`, turned `delta` degrees, separate into
    lines and gaps: the energy of the row profile's steps. Level lines put all
    of a line's ink into a few rows and none into the gap below; a slant smears
    it across both, and the steps flatten."""
    from PIL import Image
    turned = region.rotate(delta, Image.Resampling.BILINEAR, expand=False, fillcolor=255)
    column = turned.resize((1, turned.height), Image.Resampling.BOX)
    profile = list(column.tobytes())          # one byte a row: "L", one column
    return float(sum((b - a) ** 2 for a, b in pairwise(profile)))


def _steps(start: float, stop: float, step: float) -> list[float]:
    n = round((stop - start) / step)
    return [round(start + i * step, 4) for i in range(n + 1)]


def line_angle(im: Any, box: tuple[float, float, float, float] | None = None,
               angle: float = 0.0, span: float = SPAN) -> float:
    """The angle, absolute and in `turn`'s sense, at which the lines inside
    `box` — fractions of the frame turned by `angle`, or the whole frame — lie
    level, searched within `span` degrees of `angle`.

    The projection profile: the region in grey, at `_WIDTH` px, turned through
    the span a quarter-degree at a time, then a twentieth around the best. A
    region with nothing to level (blank paper) leaves `angle` as it was.
    """
    from PIL import Image, ImageOps
    turned = turn(im, angle)
    region = turned.crop(Box(*box).pixels(*turned.size)) if box is not None else turned
    region = ImageOps.autocontrast(region.convert("L"))
    if region.width > _WIDTH:
        height = max(1, round(region.height * _WIDTH / region.width))
        region = region.resize((_WIDTH, height), Image.Resampling.BOX)
    if region.width < 8 or region.height < 8:
        return angle

    def best(deltas: list[float]) -> tuple[float, float, float]:
        scored = [(_sharpness(region, d), d) for d in deltas]
        top = max(s for s, _ in scored)
        low = min(s for s, _ in scored)
        # Ties go to the smallest turn: a flat profile must not drift to −span.
        return top, low, min((d for s, d in scored if s >= top * 0.9999), key=abs)

    top, low, coarse = best(_steps(-span, span, _COARSE))
    if top <= 0 or top - low <= top * 1e-3:
        return angle
    _, _, fine = best(_steps(coarse - _COARSE, coarse + _COARSE, _FINE))
    return round(angle + fine, 2)
