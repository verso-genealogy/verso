"""A frame as the reader sees it: its own EXIF turn applied, a declared turn on top, a spread cut to one half — and a
phone's HEIC frames written as JPEG.

Every window of the scan tools is a FRACTION of the frame, so a frame read as it lies on disk rather than as it
stands puts every window in the wrong place: a phone records its rotation as a tag instead of turning the pixels,
an album shot flat over a book carries a wrong tag, and a frame of an album of spreads holds two leaves. Each of
these is undone here, in this order, before anything is cut.

Pillow is imported where it is used (`pil`): the names, the suffixes and a spread's arithmetic run without it.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from verso.core.messages import t
from verso.core.scans.level import turned_size

__all__ = ["HEIC_SUFFIXES", "IMAGE_SUFFIXES", "convert_heic_frames", "cut_half", "heic_clashes", "heic_to_jpeg",
           "image_names", "open_upright", "pil", "turn_upright", "turned_frame_size", "upright_size"]

# `.heic` is what a phone's photo library exports. While it was missing here `image_names()` returned
# nothing for such an album, and an export reported «11 frame(s)» and «0 file(s)» in consecutive lines.
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif")
HEIC_SUFFIXES = (".heic", ".heif")

# What a HEIC frame is written as: Pillow's quality, at the frame's own pixel size.
JPEG_QUALITY = 92

# A gutter is never exactly at the middle of a photographed spread, so each half is cut slightly past it. The
# overlap costs a sliver of the facing leaf and saves a line that sits right on the fold.
SPREAD_OVERLAP = 0.015


def pil() -> tuple[Any, Any, Any]:
    """Pillow's `Image`, `ImageOps` and `ImageEnhance` — SystemExit naming the extra when it is not installed —
    with the HEIC opener registered when pillow-heif is."""
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError as exc:  # pragma: no cover - depends on the machine
        raise SystemExit(
            "Pillow is not installed in this environment.\n"
            "  pip install 'verso-core[scans]'") from exc
    # Pillow cannot decode HEIC on its own, and a phone's export is all HEIC. Register the opener when it is
    # available; a missing plugin is not fatal here because every other format still works — `open_upright` is
    # where the reader finds out, with a message naming the fix.
    try:  # pragma: no cover - depends on the machine
        # From the module that defines it: the package re-exports it without `__all__`, which a strict pyright
        # reads as a private import.
        from pillow_heif.as_plugin import register_heif_opener
        register_heif_opener()
    except ImportError:  # pragma: no cover - depends on the machine
        pass
    return Image, ImageOps, ImageEnhance


def image_names(directory: Path) -> list[str]:
    """The frames of `directory` by name, sorted: every file of an image suffix."""
    return sorted(p.name for p in directory.iterdir()
                  if p.suffix.lower() in IMAGE_SUFFIXES)


def open_upright(path: Path) -> Any:
    """Open a frame with its EXIF orientation already baked into the pixels.

    A phone photographs a bound дело in whatever orientation the hand held it and records the rotation as an EXIF
    tag instead of rotating the pixels; Pillow does not apply that tag on open. Every window is a FRACTION of width
    and height, so on a frame tagged «rotate 90°» a crop of a column cuts a band across the columns rather than
    along them — the picture comes out unreadable and nothing says why. Albums shot straight by an archive carry
    no tag and are unaffected; the ones exported out of a phone's photo library mix tagged and untagged frames in one album.

    A HEIC arrives here ALREADY turned. libheif applies the container's `irot` box while decoding, and pillow-heif
    then resets the EXIF tag to 1 so that `exif_transpose` cannot turn it a second time, keeping the old value in
    `info["original_orientation"]` purely as a record. Do not apply that record: it turns every frame twice. When a
    decoded HEIC still lies on its side, the tag itself was wrong (a phone flat over a book guesses), and the
    remedy is `rotate` / `rotate_frames` in scans.toml — see `turn_upright`.
    """
    Image, ImageOps, _ = pil()
    try:
        fh = Image.open(path)
    except Exception as exc:  # pragma: no cover - depends on the machine
        if path.suffix.lower() in HEIC_SUFFIXES:
            raise SystemExit(
                f"cannot decode {path.name}: HEIC support is missing.\n"
                "  pip install pillow-heif") from exc
        raise
    with fh as im:
        return ImageOps.exif_transpose(im)


def turn_upright(im: Any, rotate: int) -> Any:
    """Apply a frame's declared turn on top of the orientation its file declares.

    `open_upright` handles the frames that SAY how they are rotated. This handles the ones whose saying is wrong or
    missing: declared in scans.toml, per album (`rotate`) or per frame (`rotate_frames`), because neither the
    pixels nor the tag carry a hint of it.
    """
    return im.rotate(rotate % 360, expand=True) if rotate % 360 else im


def cut_half(im: Any, half: str) -> Any:
    """The half of a spread a page occupies — 'L' or 'R', each cut `SPREAD_OVERLAP` past the middle — or the frame
    itself for '' (a frame that is one page). Cut after any turn: on a sideways frame the gutter runs across."""
    if not half:
        return im
    w, h = im.size
    mid = w / 2
    box = ((0, 0, int(mid * (1 + SPREAD_OVERLAP)), h) if half == "L"
           else (int(mid * (1 - SPREAD_OVERLAP)), 0, w, h))
    return im.crop(box)


def half_size(width: int, height: int, half: str) -> tuple[int, int]:
    """`cut_half(im, half).size` for a `width`×`height` frame, in the same arithmetic."""
    if not half:
        return width, height
    mid = width / 2
    return ((int(mid * (1 + SPREAD_OVERLAP)), height) if half == "L"
            else (width - int(mid * (1 - SPREAD_OVERLAP)), height))


def upright_size(path: Path) -> tuple[int, int]:
    """A frame's size as the reader sees it — after its own orientation tag — from the header alone:
    `open_upright(path).size` without decoding a pixel.

    Two formats need no swap, because they come turned already: a HEIC (pillow-heif reports the size libheif
    turned to and resets the tag to 1 on open — see `open_upright`), and a TIFF (Pillow's TIFF reader reports the
    turned size on open and turns the pixels itself on load, its tag gone by the time `exif_transpose` asks).
    Raises what Pillow raises for a file it cannot read, and SystemExit without Pillow.
    """
    Image, _, _ = pil()
    with Image.open(path) as im:
        width, height = im.size
        # EXIF orientation 5–8: the reader sees the frame turned a quarter.
        if im.format != "TIFF" and im.getexif().get(0x0112, 1) in (5, 6, 7, 8):
            width, height = height, width
    return width, height


def turned_frame_size(path: Path, rotate: int = 0, half: str = "") -> tuple[int, int]:
    """`cut_half(turn_upright(open_upright(path), rotate), half).size` from the frame's header alone: the size a
    window on the page is a fraction of. Raises as `upright_size`."""
    width, height = upright_size(path)
    if rotate % 360:
        width, height = turned_size(width, height, rotate % 360)
    return half_size(width, height, half)


def heic_clashes(names: Iterable[str]) -> set[str]:
    """The stems whose HEIC frames would make a JPEG that is not theirs alone: a HEIC beside a real `.jpg` of the same
    stem (an edit, a duplicate), or two HEIC suffixes of one stem. Such frames are kept as they are."""
    heic: dict[str, int] = {}
    jpeg: set[str] = set()
    for name in names:
        stem, suffix = Path(name).stem, Path(name).suffix.lower()
        if suffix in HEIC_SUFFIXES:
            heic[stem] = heic.get(stem, 0) + 1
        elif suffix == ".jpg":
            jpeg.add(stem)
    return {stem for stem, n in heic.items() if n > 1 or stem in jpeg}


def heic_to_jpeg(path: Path) -> Path:
    """Write the HEIC frame `path` beside itself as a JPEG, and take the HEIC away: same name, suffix `.jpg`.

    The pixels are `open_upright(path)` — the orientation exactly as every crop and window sees it, so a window of
    `scans.toml` (a fraction of the frame, `rotate`/`rotate_frames` on top) lands on the same place — at the frame's
    own size, quality `JPEG_QUALITY`. The JPEG carries no EXIF orientation: it is turned in the pixels, and a tag
    would turn it a second time. The colour profile is kept; the rest of the HEIC's metadata is not. Written whole
    and moved into place, so a crash leaves the HEIC and no half of a JPEG; a JPEG of the same name already there is
    replaced (a rerun converts the same HEIC again).
    """
    destination = path.with_suffix(".jpg")
    im = open_upright(path)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    icc = im.info.get("icc_profile")
    part = destination.with_name(f".{destination.name}.part")
    try:
        im.save(part, format="JPEG", quality=JPEG_QUALITY, **({"icc_profile": icc} if icc else {}))
        part.replace(destination)
    finally:
        part.unlink(missing_ok=True)
    path.unlink()
    return destination


def convert_heic_frames(directory: Path, source_names: Iterable[str] | None) -> int:
    """`heic_to_jpeg` for every HEIC frame of `directory`; JPEGs, PNGs and TIFFs are left as they are.

    `source_names` are the frame names of the SOURCE the frames were fetched from (an album's export names, a
    folder): a HEIC whose stem the source also holds as a real `.jpg` — or as a second HEIC — would be written over a
    frame that is not its own, so it is kept as it is, with that JPEG, and counted as failed. That is told from the
    source and not from `directory`, where the `.jpg` of an earlier run beside a HEIC copied again is the run's own
    and is replaced. `None` — a source that cannot list its frames, or none at all — asks `directory` instead,
    conservatively: a `.jpg` beside a HEIC is a clash, and an earlier run's is then refused too.

    A frame that will not decode stays as it was and is named on stderr. How many did not convert is returned."""
    names = list(source_names) if source_names is not None else image_names(directory)
    clashing = heic_clashes(names)
    failed = 0
    for name in image_names(directory):
        path = directory / name
        if path.suffix.lower() not in HEIC_SUFFIXES:
            continue
        if path.stem in clashing:
            failed += 1
            print(t("scans.jpeg.clash", name=name, stem=path.stem), file=sys.stderr)
            continue
        try:
            jpeg = heic_to_jpeg(path)
        except (Exception, SystemExit) as exc:     # open_upright says «HEIC support is missing» as a SystemExit
            failed += 1
            print(t("scans.jpeg.failed", name=name, reason=str(exc).splitlines()[0] if str(exc) else type(exc).__name__),
                  file=sys.stderr)
            continue
        print(t("scans.jpeg.written", name=name, jpeg=jpeg.name), flush=True)
    return failed
