"""Upscaled, sharpened quadrant crops of a document scan, for reading it.

A low-resolution scan (a 1024-px-wide two-page spread) is unreadable whole: the cursive handwriting is only a few
pixels tall. Cut into four overlapping quadrants, each upscaled 3× with an unsharp mask, the script is legible to a
vision model without anything invented. For each IMAGE `N.png` four crops are written to OUT:

    N_tl.png  left page, top       N_tr.png  right page, top
    N_bl.png  left page, bottom    N_br.png  right page, bottom

They overlap by ~50–60 source pixels along the centre lines, so no text is lost at the seams. Each crop's path is
printed.
"""
from __future__ import annotations

import argparse
import os

from verso.core.messages import t
from verso.core.scans.image import pil

__all__ = ["HELP", "add_arguments", "run"]

HELP = t("scans.cli.help_quadrants")
OVERLAP_X = 60
OVERLAP_Y = 50
SCALE = 3


def quadrants(image_path: str, out_dir: str) -> list[str]:
    """The four crops of `image_path`, written to `out_dir`: their paths."""
    Image, _, _ = pil()
    from PIL import ImageFilter
    stem = os.path.splitext(os.path.basename(image_path))[0]
    img = Image.open(image_path).convert("L")
    w, h = img.size
    mid_x, mid_y = w // 2, h // 2
    boxes = {
        "tl": (0, 0, mid_x + OVERLAP_X, mid_y + OVERLAP_Y),
        "tr": (mid_x - OVERLAP_X, 0, w, mid_y + OVERLAP_Y),
        "bl": (0, mid_y - OVERLAP_Y, mid_x + OVERLAP_X, h),
        "br": (mid_x - OVERLAP_X, mid_y - OVERLAP_Y, w, h),
    }
    written = []
    for name, box in boxes.items():
        crop = img.crop(box)
        crop = crop.resize((crop.width * SCALE, crop.height * SCALE), Image.Resampling.LANCZOS)
        crop = crop.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2))
        out_path = os.path.join(out_dir, f"{stem}_{name}.png")
        crop.save(out_path)
        written.append(out_path)
    return written


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("images", nargs="+", metavar="IMAGE", help=str(t("scans.cli.help_images")))
    p.add_argument("--out", required=True, help=str(t("scans.cli.help_quadrants_out")))


def run(args: argparse.Namespace) -> int:
    os.makedirs(args.out, exist_ok=True)
    for image in args.images:
        for path in quadrants(image, args.out):
            print(path)
    return 0
