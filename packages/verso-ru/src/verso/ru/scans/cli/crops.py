"""Half-page crops, upscaled — the unit that reads in a sweep: each page cut into an upper and a lower half that
overlap, `<кадр:04d>_<лист>_{a,b}.jpg`.

A reading-room frame is about 950 px across a leaf, which is legible at roughly 1.8× on half a page and not legible
on a whole one. Reading whole pages costs several times the tokens and gets the surnames wrong; the half-page crop is
the unit that works, and `--verso-only` halves the count again because in ч.3 the recto carries only «Отъ чего
умеръ» and no names at all. `--part` crops only the columns of a part that carry names, at the zoom that affords.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from verso.core.scans.image import pil
from verso.core.scans.look import legible
from verso.ru.messages import t
from verso.ru.scans.album import album_of, load_pages, note_frame_mode, open_page
from verso.ru.scans.cli import add_enhance_flag, add_frames_flag
from verso.ru.scans.folio import Page

__all__ = ["HELP", "add_arguments", "run"]

HELP = "half-page upscaled crops, the unit that reads"

# Defaults measured on one дело's leaves (~950 px across): 1.8× on a half page is comfortably readable, and the
# halves overlap by three points so a record straddling the cut is whole in one of them.
DEFAULT_SCALE = 1.8
HALF_OVERLAP = 0.03

# Per-part crop windows, as fractions of the leaf width, with the zoom each affords. **This is the same output size
# as a full-width crop, and a third bigger glyphs** — the left columns (счётъ, мѣсяцъ и день) carry no names, so
# spending pixels on them is what made one given name read as another on a 1.8× full-width sweep.
#
# ч. 1 keeps «Имена родившихся» beside the parents; ч. 3 keeps the age column, because a burial is unusable without
# it; ч. 2 spans nearly the whole leaf.
#
# What every preset drops is the счётъ column — and that is the one thing that says WHICH record a row is. For
# READING a record that costs nothing (the row is already located), but for CHECKING a DSL attribution against the
# book it is the whole question, and re-deriving the number by counting rows is exactly how a record lands on its
# neighbour. `--with-count` puts the left edge back at 0.
PART_WINDOWS = {
    1: (0.24, 1.00, 2.4),
    2: (0.06, 1.00, 2.0),
    3: (0.15, 1.00, 2.4),
}


def crop_window(args: argparse.Namespace) -> tuple[float, float, float]:
    """(x0, x1, scale) — the part preset, with any explicit flag overriding it."""
    x0, x1, scale = PART_WINDOWS.get(args.part, (0.0, 1.0, DEFAULT_SCALE))
    if getattr(args, "with_count", False):
        x0 = 0.0
    if args.x0 is not None:
        x0 = args.x0
    if args.x1 is not None:
        x1 = args.x1
    if args.scale is not None:
        scale = args.scale
    return x0, x1, scale


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", metavar="DIR")
    p.add_argument("--out", required=True)
    p.add_argument("--verso-only", action="store_true", help=str(t("scans.help.verso_only")))
    p.add_argument("--part", type=int, choices=sorted(PART_WINDOWS), help=str(t("scans.help.part")))
    p.add_argument("--from", dest="from_folio", type=int, metavar="N",
                   help="first folio to crop (a part covers a range)")
    p.add_argument("--to", dest="to_folio", type=int, metavar="N",
                   help="last folio to crop")
    p.add_argument("--with-count", action="store_true", help=str(t("scans.help.with_count")))
    p.add_argument("--x0", type=float, help="override the left edge (fraction)")
    p.add_argument("--x1", type=float, help="override the right edge (fraction)")
    p.add_argument("--scale", type=float, help=f"override the zoom (default {DEFAULT_SCALE:g})")
    p.add_argument("--top", type=float, default=0.07,
                   help="skip the printed header (default 0.07)")
    p.add_argument("--grey", action="store_true", help="greyscale + autocontrast")
    add_enhance_flag(p)
    add_frames_flag(p)
    p.set_defaults(part=None)


def run(args: argparse.Namespace) -> int:
    Image, _, _ = pil()
    directory = Path(args.directory)
    album = album_of(directory)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pages, by_frame = load_pages(directory, force_frames=args.frames,
                                 expand=bool(album and album.frames == "spread"),
                                 turn=album.rotate if album else 0)
    if by_frame:
        note_frame_mode(directory, len(pages))
    if args.verso_only:
        if by_frame:
            raise SystemExit("--verso-only needs folio names: with frame numbering "
                             "nothing says which side of a leaf a frame holds.")
        pages = [p for p in pages if p.verso]
    # A part occupies a folio RANGE, so cropping one part means cropping a range — the presets are per-part and a
    # year holds all three. Under frame numbering the same two flags select frames, which is the only sequence there
    # is.
    def ordinal(page: Page) -> int:
        return page.frame if by_frame else page.number

    if args.from_folio is not None:
        pages = [p for p in pages if ordinal(p) >= args.from_folio]
    if args.to_folio is not None:
        pages = [p for p in pages if ordinal(p) <= args.to_folio]

    x0, x1, scale = crop_window(args)
    enhance = args.enhance or 1.0
    grey = args.grey or enhance > 1
    count = 0
    for page in pages:
        im = open_page(directory, page, album.rotation_for(page.label) if album else 0)
        left, right = int(im.width * x0), int(im.width * x1)
        bands = ((args.top, 0.5 + HALF_OVERLAP), (0.5 - HALF_OVERLAP, 1.0))
        for tag, (y0, y1) in zip("ab", bands, strict=True):
            crop = im.crop((left, int(im.height * y0), right, int(im.height * y1)))
            crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.Resampling.LANCZOS)
            crop = legible(crop, grey=grey, enhance=enhance)
            crop.save(out / f"{page.frame:04d}_{page.label}_{tag}.jpg", quality=90)
            count += 1
    window = f"x {x0:g}–{x1:g} at {scale:g}×"
    part = f" (ч. {args.part} preset)" if args.part else ""  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
    if getattr(args, "with_count", False):
        part += " +счётъ"  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
    print(f"{count} crop(s) from {len(pages)} page(s), {window}{part} → {out}")
    if args.verso_only:
        print(t("scans.crops.verso_only"))
    return 0
