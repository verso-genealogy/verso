"""verso.core.scans.image — a frame as the reader sees it, and a phone's HEIC frames written as JPEG (`verso scans
jpeg`). Pillow is the extra `[scans]`, pillow-heif `[heic]`: a test that needs one skips without it."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from verso.core.scans import image
from verso.core.scans.image import (JPEG_QUALITY, convert_heic_frames, cut_half, heic_clashes, image_names, open_upright,
                                    turn_upright, turned_frame_size, upright_size)

RED, BLUE = (250, 0, 0), (0, 0, 250)


# An Apple Photos export is HEIC. While it was missing from IMAGE_SUFFIXES the tools saw no frame of such an album:
# an export reported «11 frame(s)» and then «0 file(s)».
def test_image_names_sees_heic(tmp_path: Path):
    for name in ("IMG_1.HEIC", "IMG_2.heic", "IMG_3.jpg", "notes.txt"):
        (tmp_path / name).touch()
    assert image_names(tmp_path) == ["IMG_1.HEIC", "IMG_2.heic", "IMG_3.jpg"]


# --- orientation: what the file declares, and what the album declares on top ---
#
# pillow-heif hands back a HEIC ALREADY turned: libheif applies the container's `irot` box while decoding, and
# pillow-heif then resets the EXIF tag to 1 so `exif_transpose` cannot turn it again, keeping the old value in
# `info["original_orientation"]` as a record. Applying that record a second time is the tempting fix for a sideways
# frame and it is wrong: it turns an album's sideways frames upside down and lays its upright ones on their side.
# What is wrong is the phone's guess (it lay flat over the book), and that is declared in scans.toml.

class _Decoded:
    """A decoded frame that refuses to be turned: `open_upright` must not."""
    def __init__(self, size: tuple[int, int], info: dict[str, Any]) -> None:
        self.size, self.info = size, info

    def __enter__(self) -> _Decoded:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def transpose(self, method: object) -> None:
        raise AssertionError(f"open_upright turned the frame again ({method})")

    rotate = transpose


def test_open_upright_does_not_reapply_original_orientation(monkeypatch: pytest.MonkeyPatch):
    frame = _Decoded((3024, 4032), {"original_orientation": 6})
    def decode(path: Path) -> _Decoded:
        del path
        return frame

    def exif_transpose(im: _Decoded) -> _Decoded:
        return im               # the EXIF tag reads 1: pillow-heif reset it

    fake_image = SimpleNamespace(open=decode)
    fake_ops = SimpleNamespace(exif_transpose=exif_transpose)
    monkeypatch.setattr(image, "pil", lambda: (fake_image, fake_ops, None))
    assert open_upright(Path("IMG_0001.HEIC")) is frame


def test_a_heic_decodes_turned_once(tmp_path: Path):
    """The premise of the guard above, on a real file: tagged «rotate 90° CW», a 400×200 frame with a mark in its
    top-left corner decodes as 200×400 with the mark top-RIGHT — turned once. Turned twice it would be 400×200 with
    the mark bottom-right."""
    pytest.importorskip("pillow_heif")
    from PIL import Image, ImageDraw
    image.pil()                       # registers the HEIC codec, as every command does
    raw = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(raw).rectangle((0, 0, 50, 50), fill="red")
    exif = Image.Exif()
    exif[274] = 6
    path = tmp_path / "IMG_0001.HEIC"
    raw.save(path, exif=exif.tobytes())

    frame = open_upright(path)
    assert frame.size == (200, 400)
    red, white = frame.getpixel((190, 10)), frame.getpixel((10, 10))
    assert red[0] > 200 and red[1] < 60, red
    assert white[1] > 200, white


def _page(path: Path, rotate: int, half: str) -> Any:
    return cut_half(turn_upright(open_upright(path), rotate), half)


@pytest.mark.parametrize("half", ["", "L", "R"])
@pytest.mark.parametrize("rotate", [0, 90, 180, 270, 33])
@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_a_pages_size_is_read_off_its_header(tmp_path: Path, orientation: int, rotate: int, half: str):
    # `turned_frame_size` is the page's size without decoding: the file's own orientation, the album's turn (any
    # angle), then a spread's half — on odd sides, where the half's integer arithmetic shows.
    Image = pytest.importorskip("PIL.Image")
    frame = Image.new("RGB", (301, 157), "white")
    exif = frame.getexif()
    exif[0x0112] = orientation
    frame.save(tmp_path / "f.jpg", exif=exif)
    assert turned_frame_size(tmp_path / "f.jpg", rotate, half) == _page(tmp_path / "f.jpg", rotate, half).size


def test_a_tiff_and_a_heic_tell_their_size_as_they_open(tmp_path: Path):
    Image = pytest.importorskip("PIL.Image")
    Image.new("RGB", (301, 157), "white").save(tmp_path / "f.tif", tiffinfo={274: 6})
    assert turned_frame_size(tmp_path / "f.tif") == _page(tmp_path / "f.tif", 0, "").size
    # A HEIC decodes turned once, its tag reset (test_a_heic_decodes_turned_once).
    pytest.importorskip("pillow_heif")
    image.pil()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (400, 200), "white").save(tmp_path / "f.heic", exif=exif.tobytes())
    assert turned_frame_size(tmp_path / "f.heic") == _page(tmp_path / "f.heic", 0, "").size == (200, 400)


def test_an_unreadable_frame_has_no_size(tmp_path: Path):
    pytest.importorskip("PIL.Image")
    (tmp_path / "f.jpg").write_bytes(b"")
    with pytest.raises(Exception):  # noqa: B017 - what Pillow raises is Pillow's
        turned_frame_size(tmp_path / "f.jpg")


def test_a_half_of_a_spread_is_cut_past_the_middle():
    Image = pytest.importorskip("PIL.Image")
    spread = Image.new("RGB", (1000, 10))
    assert cut_half(spread, "L").size == (507, 10)
    assert cut_half(spread, "R").size == (508, 10)
    assert cut_half(spread, "") is spread


# --- HEIC → JPEG: `verso scans jpeg` -------------------------------------------------------------------------

def _heic(path: Path, orientation: int = 1, size: tuple[int, int] = (64, 32)) -> None:
    """A synthetic frame: red on the left half, blue on the right, EXIF orientation as a phone writes it."""
    from PIL import Image
    im = Image.new("RGB", size, RED)
    for x in range(size[0] // 2, size[0]):
        for y in range(size[1]):
            im.putpixel((x, y), BLUE)
    exif = Image.Exif()
    exif[0x0112] = orientation
    im.save(path, quality=95, exif=exif.tobytes())


def _tables(image: Any) -> Any:
    return image.quantization


def _near(pixel: Any, want: tuple[int, int, int]) -> bool:
    return all(abs(a - b) <= 12 for a, b in zip(pixel[:3], want, strict=True))


@pytest.fixture
def album(tmp_path: Path) -> Path:
    pytest.importorskip("pillow_heif")
    from PIL import Image
    image.pil()
    album = tmp_path / "Маниловка 1900"
    album.mkdir()
    _heic(album / "0001_1.heic", orientation=6)
    _heic(album / "0002_1об.heic", orientation=1)
    Image.new("RGB", (20, 10), (1, 2, 3)).save(album / "0003_2.jpg")
    return album


def _jpeg(directory: Path) -> int:
    from verso.core import plugins
    from verso.core.scans.cli import main
    with plugins.adding(entry_points=False):     # the core's subcommand, whatever plugins are installed
        return main(["jpeg", str(directory)])


def test_jpeg_keeps_size_and_orientation(album: Path, capsys: pytest.CaptureFixture[str]):
    from PIL import Image
    assert open_upright(album / "0001_1.heic").size == (32, 64)     # the phone's «turn 90°», applied by the decoder
    assert _jpeg(album) == 0
    assert image_names(album) == ["0001_1.jpg", "0002_1об.jpg", "0003_2.jpg"]    # the same names, `.jpg`; no `.heic`
    assert capsys.readouterr().out == "0001_1.heic → 0001_1.jpg\n0002_1об.heic → 0002_1об.jpg\n"
    for name, size in (("0001_1.jpg", (32, 64)), ("0002_1об.jpg", (64, 32))):
        with Image.open(album / name) as jpeg:
            assert jpeg.format == "JPEG" and jpeg.size == size
            assert jpeg.getexif().get(0x0112, 1) == 1    # turned in the pixels, no tag to turn it a second time
        assert upright_size(album / name) == size
    with Image.open(album / "0001_1.jpg") as jpeg:       # red was the left half; turned a quarter, it is the top
        rgb = jpeg.convert("RGB")
        assert _near(rgb.getpixel((16, 6)), RED) and _near(rgb.getpixel((16, 58)), BLUE)
    with Image.open(album / "0002_1об.jpg") as jpeg:     # untagged: as shot
        rgb = jpeg.convert("RGB")
        assert _near(rgb.getpixel((6, 16)), RED) and _near(rgb.getpixel((58, 16)), BLUE)
    with Image.open(album / "0001_1.jpg") as jpeg:       # quality 92: Pillow's own tables for it
        reference = album.parent / "ref.jpg"
        Image.new("RGB", (8, 8)).save(reference, quality=JPEG_QUALITY)
        with Image.open(reference) as ref:
            assert JPEG_QUALITY == 92 and _tables(jpeg) == _tables(ref)


def test_jpeg_leaves_a_jpeg_as_it_is(album: Path):
    before = (album / "0003_2.jpg").read_bytes()
    assert _jpeg(album) == 0
    assert (album / "0003_2.jpg").read_bytes() == before


def test_jpeg_twice_converts_nothing_new_and_breaks_nothing(album: Path):
    _jpeg(album)
    first = (album / "0001_1.jpg").read_bytes()
    assert _jpeg(album) == 0 and (album / "0001_1.jpg").read_bytes() == first
    assert image_names(album) == ["0001_1.jpg", "0002_1об.jpg", "0003_2.jpg"]


def test_a_frame_that_will_not_decode_is_kept_and_named(album: Path, capsys: pytest.CaptureFixture[str]):
    (album / "0004_2об.heic").write_bytes(b"not an image")
    assert _jpeg(album) == 1                 # said, not swallowed: a short album looks like an unphotographed year
    assert "0004_2об.heic" in capsys.readouterr().err
    assert (album / "0004_2об.heic").exists() and not (album / "0004_2об.jpg").exists()
    assert (album / "0001_1.jpg").exists()   # the rest is done


def test_two_heic_suffixes_of_one_stem_would_be_one_jpeg():
    assert heic_clashes(["0001.heic", "0001.heif", "0002.heic", "0003.jpg", "0003.HEIC", "0004.png"]) == {"0001", "0003"}
    assert heic_clashes(["0002.heic", "0002.jpg"]) == {"0002"} and heic_clashes(["0005.heic"]) == set()


def test_a_directory_with_no_listing_is_asked_conservatively(album: Path):
    """With no listing of the source, a `.jpg` beside a HEIC cannot be told from an earlier run's: refused."""
    (album / "0001_1.jpg").write_bytes(b"x")
    assert convert_heic_frames(album, None) == 1
    assert (album / "0001_1.heic").exists() and (album / "0001_1.jpg").read_bytes() == b"x"
    assert (album / "0002_1об.jpg").exists() and not (album / "0002_1об.heic").exists()


def test_the_source_listing_tells_an_earlier_runs_jpeg_from_a_frame(album: Path):
    """Given the source's names, the `.jpg` beside a HEIC is the earlier run's own: replaced."""
    (album / "0001_1.jpg").write_bytes(b"stale")
    assert convert_heic_frames(album, ["0001_1.heic", "0002_1об.heic", "0003_2.jpg"]) == 0
    assert upright_size(album / "0001_1.jpg") == (32, 64) and not (album / "0001_1.heic").exists()
