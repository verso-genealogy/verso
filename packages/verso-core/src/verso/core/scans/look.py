"""How the frames of one album are shown: colour, grey, a faded hand pushed, coloured ink drawn
out of its paper, a negative.

A faded iron-gall ink is a property of the дело, not of one crop: a faded
book is pale on every leaf, and the reader who found that `--enhance
1.7` makes it plain should not have to find it again for the next record. So
the look lives in the album's stanza of `scans.toml` and every rendering of the
album follows it — the review page's frame, its detail at full resolution, the
crops on the cards, the crop zoomed.

`enhance` is the INK's: how hard a grey rendering of this album pushes, and
`verso scans zoom` reads it too (`verso.core.scans.stanza`). `grey` and `invert`
are how the review page shows the album; `verso scans` keeps its own tiers
(`crops` in colour, to tell ink from paper damage; `zoom` grey).

`ink` is the other answer to a pale hand, for one that a push cannot reach: a
faded COLOURED ink — the violet and blue aniline of the 1910s — on yellowed
paper (`coloured_ink`). A push stretches the grey the camera made, and that grey
mixes the channel in which the ink is dark with the one in which the paper is;
`ink` reads the ink where it is darkest and measures it against its own paper.
`"tone"` gives the ink's darkness as grey, `"binary"` decides ink or paper by
Sauvola's local threshold for the faintest lines (it breaks a thin stroke, so it
is the second view, not the first). The two answers exclude each other.

Pillow is imported where it is used, as in `level.py`: a stanza is read
without it.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from verso.core.messages import t

__all__ = ["INKS", "MAX_ENHANCE", "PLAIN", "Look", "coloured_ink", "legible"]

# Beyond this the push only crushes the hand; the dial that read a faded
# book was 1.7.
MAX_ENHANCE = 3.0
# «Бледные чернила» on the page.
FADED = 1.7
# `ink`: the coloured ink's darkness as grey, or ink and paper by a local threshold.
INKS = ("tone", "binary")


@dataclass(frozen=True)
class Look:
    """How an album's frames are rendered. The default is the frame as shot."""
    grey: bool = False
    # 1 is plain autocontrast; above it the faded-hand push (`legible`).
    enhance: float = 1.0
    invert: bool = False
    # "" none; "tone" or "binary" — a coloured ink drawn out of its paper (`coloured_ink`).
    ink: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.enhance <= MAX_ENHANCE:
            raise ValueError(str(t("scans.look.enhance_out_of_range", enhance=f"{self.enhance:g}", limit=f"{MAX_ENHANCE:g}")))
        if self.ink and self.ink not in INKS:
            raise ValueError(str(t("scans.look.ink_unknown", ink=self.ink, inks=", ".join(INKS))))
        if self.ink and self.enhance > 1:
            raise ValueError(str(t("scans.look.ink_and_enhance", ink=self.ink, enhance=f"{self.enhance:g}")))

    @property
    def greyed(self) -> bool:
        """Grey at all: a push implies grey, as the `--enhance` of `verso scans crops` does, and so does an ink."""
        return self.grey or self.enhance > 1 or bool(self.ink)

    @property
    def plain(self) -> bool:
        return not self.greyed and not self.invert

    def apply(self, image: Any) -> Any:
        """`image` rendered this way; the image itself when the look is plain."""
        if self.plain:
            return image
        if self.ink:
            out = coloured_ink(image, binary=self.ink == "binary")
        else:
            out = legible(image, grey=self.greyed, enhance=self.enhance)
        if self.invert:
            from PIL import ImageOps
            out = ImageOps.invert(out if out.mode in ("L", "RGB") else out.convert("RGB"))
        return out

    def params(self) -> dict[str, str]:
        """The query parameters of `/img` that ask for this look; none for plain.
        The review page builds the same ones."""
        out: dict[str, str] = {}
        if self.grey:
            out["grey"] = "1"
        if self.enhance > 1:
            out["enhance"] = f"{self.enhance:g}"
        if self.invert:
            out["invert"] = "1"
        if self.ink:
            out["ink"] = self.ink
        return out

    @classmethod
    def from_query(cls, query: Mapping[str, str]) -> Look:
        """The look a query asks for; `ValueError` on an enhance out of range or an ink unknown."""
        return cls(grey=query.get("grey") == "1", enhance=float(query.get("enhance") or 1),
                   invert=query.get("invert") == "1", ink=query.get("ink") or "")


PLAIN = Look()


def legible(image: Any, *, grey: bool, enhance: float = 1.0) -> Any:
    """Greyscale + autocontrast, and for a pale hand a firmer push.

    `enhance=1` is plain autocontrast — what every crop cut before this flag
    existed, so the default changes no output. Above 1 the histogram is clipped
    at both ends before the stretch and contrast and edges are pushed after it:
    a faded book is written in an iron-gall ink so pale that
    plain autocontrast leaves the surnames guessable but not readable, and 1.7
    makes them plain. Pushing a hand that is already dark only crushes it, so
    this is a dial and not a default.
    """
    from PIL import ImageEnhance, ImageOps
    if not grey:
        return image
    cutoff = (1, 12) if enhance > 1 else 0
    out = ImageOps.autocontrast(image.convert("L"), cutoff=cutoff)
    if enhance > 1:
        out = ImageEnhance.Contrast(out).enhance(enhance)
        out = ImageEnhance.Sharpness(out).enhance(1.5)
    return out


# The paper is measured where the background is lit: a gutter's shadow, darker
# than this share of the median paper, would pass for ink.
_LIT = 0.75
# The white point stands this many robust σ of the paper below its median, and
# no fewer levels than `_FLOOR`, so the paper's own grain — and what is left of
# its shading once divided — stays white.
_KNEE = 1.0
_FLOOR = 3
# The share of the lit pixels at full black: the ink's darker strokes, not the
# darkest one — a priest's signature in iron-gall ink would otherwise make the
# pale record beside it lighter.
_BLACK = 0.01
# At least this many levels between the two: a window of bare paper has no ink
# to set its black, and its grain would be stretched into strokes.
_SPAN = 80
# Below 1 the faint strokes are lifted toward black.
_GAMMA = 0.7
# Sauvola's k and dynamic range; the spread is the mean absolute deviation
# ×1.25, its estimate of σ, since Pillow blurs no float image.
_SAUVOLA_K = 0.05
_SAUVOLA_R = 128


def coloured_ink(image: Any, *, binary: bool = False) -> Any:
    """A faded coloured ink drawn out of its paper, as grey (`"L"`).

    Two channels are read — red, in which a violet or blue ink is darkest
    against a yellowed paper, and the luminance, which keeps a brown or black
    hand (a signature beside the record) — each divided by its own paper, so a
    gutter's shading and the paper's yellowing fall away. Of the two the darker
    is the ink. Its darkness is then ramped from the paper's white to the ink's
    black, both measured on this image, so it reads its own window's paper as
    `legible`'s autocontrast does. Every dark pixel comes from ink in the photo:
    nothing is drawn in.

    `binary` decides ink or paper by Sauvola's local threshold instead, for the
    faintest lines; it breaks a thin stroke, so it is the second view.
    """
    from PIL import ImageChops, ImageFilter
    rgb = image.convert("RGB").filter(ImageFilter.GaussianBlur(0.7))
    size = max(15, int(min(rgb.size) * 0.08))
    red, lum = rgb.getchannel("R"), rgb.convert("L")
    paper = _paper(lum, size)
    ink = ImageChops.darker(_flattened(red, _paper(red, size)), _flattened(lum, paper))
    at = _LIT * _percentile(paper.histogram(), 0.5)
    lit = paper.point([255 if v > at else 0 for v in range(256)])
    shown = ink.point(_ramp(ink.histogram(mask=lit)))
    return _sauvola(shown) if binary else shown


def _paper(channel: Any, size: int) -> Any:
    """The paper under `channel`: every dark stroke narrower than `size` px closed
    away, on a copy reduced to a few px of it (a rank filter that wide is slow).
    The copy's edges are carried outward first: at an edge the filters see a
    window cut short, and the paper they found there was not the paper's."""
    from PIL import Image, ImageFilter
    step = max(1, size // 5)
    small = channel.reduce(step) if step > 1 else channel
    width = 5 if step > 1 else size | 1
    pad = 2 * width
    closed = _extended(small, pad).filter(ImageFilter.MaxFilter(width)).filter(ImageFilter.MinFilter(width))
    closed = closed.filter(ImageFilter.GaussianBlur(width / 2)).crop((pad, pad, pad + small.width, pad + small.height))
    return closed.resize(channel.size, Image.Resampling.BILINEAR)


def _extended(image: Any, pad: int) -> Any:
    """`image` with `pad` px on every side, each its nearest edge's pixels repeated."""
    from PIL import Image
    w, h = image.size
    out = Image.new(image.mode, (w + 2 * pad, h + 2 * pad))
    out.paste(image, (pad, pad))
    for box, at, size in (((0, 0, 1, h), (0, pad), (pad, h)), ((w - 1, 0, w, h), (pad + w, pad), (pad, h))):
        out.paste(image.crop(box).resize(size), at)
    row = out.crop((0, pad, w + 2 * pad, pad + 1))
    out.paste(row.resize((w + 2 * pad, pad)), (0, 0))
    out.paste(out.crop((0, pad + h - 1, w + 2 * pad, pad + h)).resize((w + 2 * pad, pad)), (0, pad + h))
    return out


def _flattened(channel: Any, paper: Any) -> Any:
    """`channel` divided by its paper: the paper near white wherever it lies."""
    from PIL import ImageMath
    return ImageMath.lambda_eval(lambda a: a["min"](a["c"] * 255 / a["max"](a["p"], 1), 255), c=channel, p=paper).convert("L")


def _percentile(histogram: list[int], share: float) -> int:
    """The level below which `share` of the counted pixels lie."""
    total = sum(histogram)
    seen = 0
    for level, count in enumerate(histogram):
        seen += count
        if seen >= share * total:
            return level
    return len(histogram) - 1


def _ramp(histogram: list[int]) -> list[int]:
    """The table taking the ink's levels to the grey shown: paper white, ink black."""
    median = _percentile(histogram, 0.5)
    spread = [0] * 256
    for level, count in enumerate(histogram):
        spread[abs(level - median)] += count
    white = median - max(_KNEE * 1.4826 * _percentile(spread, 0.5), _FLOOR)
    black = min(_percentile(histogram, _BLACK), white - _SPAN)
    span = white - black
    return [round(255 * (1 - min(max((white - v) / span, 0), 1) ** _GAMMA)) for v in range(256)]


def _sauvola(grey: Any) -> Any:
    """Ink (0) or paper (255) by Sauvola's threshold over a window a few lines high."""
    from PIL import ImageChops, ImageFilter, ImageMath
    radius = max(12, min(40, int(min(grey.size) * 0.05)))
    mean = grey.filter(ImageFilter.BoxBlur(radius))
    spread = ImageChops.difference(grey, mean).filter(ImageFilter.BoxBlur(radius))
    out = ImageMath.lambda_eval(
        lambda a: (a["g"] > a["m"] * (1 + _SAUVOLA_K * (a["s"] * 1.25 / _SAUVOLA_R - 1))) * 255,
        g=grey, m=mean, s=spread).convert("L")
    return out.filter(ImageFilter.MedianFilter(3))
