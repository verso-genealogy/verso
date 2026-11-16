"""verso.core.scans.look — how an album's frames are shown: grey, a faded hand pushed, a coloured ink, a negative.

The rendering needs Pillow, the extra `[scans]` (it is imported where it is used);
those tests skip without it, as `test_level.py` does. The value
itself — its query parameters, its range — is tested everywhere."""
from __future__ import annotations

import importlib.util

import pytest

from verso.core.scans.look import FADED, INKS, MAX_ENHANCE, PLAIN, Look

needs_pil = pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="Pillow not installed")


def _row(im):
    """The pixels of a one-row image, left to right."""
    return [im.getpixel((x, 0)) for x in range(im.width)]


def test_the_default_is_the_frame_as_shot():
    assert PLAIN.plain and not PLAIN.greyed and PLAIN.params() == {}


def test_a_push_implies_grey():
    # As `verso scans crops --enhance` does: a pushed hand is a grey rendering.
    look = Look(enhance=FADED)
    assert look.greyed and not look.plain
    assert look.params() == {"enhance": "1.7"}


def test_query_round_trip():
    for look in (PLAIN, Look(grey=True), Look(enhance=1.6), Look(invert=True), Look(grey=True, enhance=2, invert=True),
                 Look(ink="tone"), Look(ink="binary", invert=True)):
        assert Look.from_query(look.params()) == look


def test_an_enhance_out_of_range_is_refused():
    with pytest.raises(ValueError):
        Look(enhance=0.5)
    with pytest.raises(ValueError):
        Look.from_query({"enhance": str(MAX_ENHANCE + 1)})


@needs_pil
def test_plain_leaves_the_image_alone():
    from PIL import Image
    im = Image.new("RGB", (8, 8), (200, 180, 150))
    assert PLAIN.apply(im) is im


@needs_pil
def test_grey_is_autocontrast_on_one_channel():
    from PIL import Image
    im = Image.new("RGB", (4, 1))
    im.putdata([(120, 110, 100), (140, 130, 120), (160, 150, 140), (180, 170, 160)])
    out = Look(grey=True).apply(im)
    assert out.mode == "L"
    assert (min(_row(out)), max(_row(out))) == (0, 255)


@needs_pil
def test_the_negative_turns_paper_dark():
    from PIL import Image
    im = Image.new("RGB", (2, 1))
    im.putdata([(250, 250, 250), (20, 20, 20)])
    assert _row(Look(invert=True).apply(im)) == [(5, 5, 5), (235, 235, 235)]
    grey = Look(grey=True, invert=True).apply(im)
    assert grey.mode == "L" and _row(grey) == [0, 255]


def test_an_ink_is_grey_and_asks_for_itself():
    look = Look(ink="tone")
    assert look.greyed and not look.plain
    assert look.params() == {"ink": "tone"}
    assert INKS == ("tone", "binary")


def test_an_unknown_ink_or_an_ink_with_a_push_is_refused():
    # Two answers to one pale hand: the page writes one or the other.
    with pytest.raises(ValueError):
        Look(ink="sepia")
    with pytest.raises(ValueError):
        Look(ink="tone", enhance=FADED)
    with pytest.raises(ValueError):
        Look.from_query({"ink": "sepia"})


def _faded_leaf():
    """A yellowed leaf shaded toward its gutter, a pale blue stroke on it, a dark
    signature: (image, the stroke's column, a paper column lit, a paper column shaded)."""
    from PIL import Image
    width, height = 120, 60
    im = Image.new("RGB", (width, height))
    for x in range(width):
        shade = 1 - 0.35 * x / width        # the gutter on the right
        paper = (round(225 * shade), round(205 * shade), round(160 * shade))
        for y in range(height):
            im.putpixel((x, y), paper)
    for y in range(10, 50):
        for x in (30, 31):                  # violet-blue aniline, faded: dark only in red
            px = im.getpixel((x, y))
            assert isinstance(px, tuple)
            r, g, b = px[:3]
            im.putpixel((x, y), (r - 45, g - 20, b + 10))
        for x in (60, 61):                  # an iron-gall signature, dark everywhere
            im.putpixel((x, y), (40, 35, 30))
    return im, 30, 10, 110


@needs_pil
def test_a_coloured_ink_is_drawn_out_of_its_shaded_paper():
    im, stroke, lit, shaded = _faded_leaf()
    out = Look(ink="tone").apply(im)
    assert out.mode == "L" and out.size == im.size
    # The paper is white wherever it lies, the gutter's shade with it …
    assert out.getpixel((lit, 30)) == 255 and out.getpixel((shaded, 30)) == 255
    # … the faded stroke stands out of it, and the signature beside it is black.
    assert out.getpixel((stroke, 30)) < 192
    assert out.getpixel((60, 30)) == 0


@needs_pil
def test_autocontrast_leaves_the_same_stroke_pale():
    # Why the look exists: the grey push reads the shading, not the ink.
    im, stroke, _, shaded = _faded_leaf()
    out = Look(enhance=FADED).apply(im)
    assert out.getpixel((stroke, 30)) > out.getpixel((shaded, 30))


@needs_pil
def test_binary_is_ink_or_paper():
    im, stroke, lit, shaded = _faded_leaf()
    out = Look(ink="binary").apply(im)
    assert set(out.histogram()[1:255]) == {0}
    assert out.getpixel((stroke, 30)) == 0 and out.getpixel((lit, 30)) == 255 and out.getpixel((shaded, 30)) == 255


@needs_pil
def test_an_ink_takes_the_negative():
    im, stroke, lit, _ = _faded_leaf()
    tone, out = Look(ink="tone").apply(im), Look(ink="tone", invert=True).apply(im)
    assert out.getpixel((lit, 30)) == 0
    assert out.getpixel((stroke, 30)) == 255 - tone.getpixel((stroke, 30))
