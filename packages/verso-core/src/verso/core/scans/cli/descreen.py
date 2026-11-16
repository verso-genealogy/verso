"""Crop and zoom a page scan, killing the moiré of screen photographs.

Some дела reach us as phone photos of a monitor. The screen's pixel grid beats against the camera sensor and
leaves fine directional stripes that survive contrast stretching and get WORSE under upscaling. A one-dimensional
box blur ACROSS the stripes, applied before the resize, removes them; a median filter does not, because the noise
is directional.

    verso scans descreen IMAGE [l,t,r,b|-] [SCALE] [MODE] [ROT]

    l,t,r,b  fractions of width/height, e.g. 0.19,0.22,0.66,0.60 ('-' = whole page)
    SCALE    resize factor applied after de-screening (default 1.0). 1.5–2.0 over a band of 6–10 rows beats 4–5×
             over one word — the scan has no more detail to give, and the band gives the neighbouring rows to
             align against.
    MODE     vertical (default) — stripes run vertically, blur horizontally
             horizontal        — stripes run horizontally, blur vertically
             raw               — no de-screening (real scans, not screen photos)
    ROT      extra counter-clockwise rotation in degrees, e.g. 90 / 180 / 270. In some printed forms the column
             headers run PERPENDICULAR to the handwriting: if a printed header reads horizontally, the names do
             not — rotate and look again.

Writes a PNG next to the source, in ./crops/, and prints its path and size.
"""
from __future__ import annotations

import argparse
import os
from typing import Any

from verso.core.messages import t
from verso.core.scans.image import pil

__all__ = ["HELP", "add_arguments", "run"]

HELP = t("scans.cli.help_descreen")
MODES = ("vertical", "horizontal", "raw")
# 5x5 kernels with a single filled row / column: a 1-D box blur, which PIL has no direct spelling for (Kernel
# accepts only 3x3 and 5x5).
_ACROSS_VERTICAL_STRIPES = [0] * 10 + [1] * 5 + [0] * 10
_ACROSS_HORIZONTAL_STRIPES = [0, 0, 1, 0, 0] * 5


def descreen(im: Any, mode: str) -> Any:
    """`im` blurred across its stripes: `mode` says which way they run."""
    from PIL import ImageFilter
    if mode == "horizontal":
        return im.filter(ImageFilter.Kernel((5, 5), _ACROSS_HORIZONTAL_STRIPES, 5))
    return im.filter(ImageFilter.Kernel((5, 5), _ACROSS_VERTICAL_STRIPES, 5))


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("image", metavar="IMAGE", help=str(t("scans.cli.help_descreen_image")))
    p.add_argument("box", nargs="?", default="-", metavar="l,t,r,b|-", help=str(t("scans.cli.help_descreen_box")))
    p.add_argument("scale", nargs="?", type=float, default=1.0, metavar="SCALE",
                   help=str(t("scans.cli.help_descreen_scale")))
    p.add_argument("mode", nargs="?", default="vertical", metavar="MODE", help=str(t("scans.cli.help_descreen_mode")))
    p.add_argument("rot", nargs="?", type=int, default=0, metavar="ROT", help=str(t("scans.cli.help_descreen_rot")))


def run(args: argparse.Namespace) -> int:
    Image, ImageOps, _ = pil()
    from PIL import ImageFilter
    path = args.image
    box = [float(x) for x in args.box.split(",")] if args.box != "-" else None
    scale, mode, rot = args.scale, args.mode, args.rot

    im = Image.open(path).convert("L")
    if rot:
        im = im.rotate(rot, expand=True)
    w, h = im.size
    if box:
        im = im.crop((int(w * box[0]), int(h * box[1]),
                      int(w * box[2]), int(h * box[3])))
    if mode != "raw":
        im = descreen(im, mode)
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.Resampling.LANCZOS)
    if mode != "raw":
        im = im.filter(ImageFilter.UnsharpMask(radius=4, percent=160, threshold=2))
    im = ImageOps.autocontrast(im, cutoff=0.5)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "crops")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    tag = args.box.replace(",", "-") if box else "full"
    out = os.path.join(out_dir, f"{stem}_{tag}_{scale}_{mode}_{rot}.png")
    im.save(out)
    print(out, im.size)
    return 0
