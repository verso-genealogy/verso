#!/usr/bin/env python3
"""Crop and zoom a page scan, killing the moiré of screen photographs.

Some дела reach us as phone photos of a monitor. The screen's pixel grid beats
against the camera sensor and leaves fine directional stripes that survive
contrast stretching and get WORSE under upscaling. A one-dimensional box blur
ACROSS the stripes, applied before the resize, removes them; a median filter
does not, because the noise is directional.

    descreen_crop.py IMAGE [l,t,r,b|-] [scale] [mode] [rot]

    l,t,r,b  fractions of width/height, e.g. 0.19,0.22,0.66,0.60 ('-' = whole page)
    scale    resize factor applied after de-screening (default 1.0).
             1.5-2.0 over a band of 6-10 rows beats 4-5x over one word — the
             scan has no more detail to give, and the band gives you the
             neighbouring rows to align against.
    mode     vertical (default) — stripes run vertically, blur horizontally
             horizontal        — stripes run horizontally, blur vertically
             raw               — no de-screening (real scans, not screen photos)
    rot      extra counter-clockwise rotation in degrees, e.g. 90 / 180 / 270.
             In this form the printed column headers run PERPENDICULAR to the
             handwriting: if the printed «…дворовъ» header reads horizontally, the names
             do not — rotate and look again.

Writes a PNG next to the source in ./crops/ and prints its path.
"""
import os
import sys

from PIL import Image, ImageFilter, ImageOps

# 5x5 kernels with a single filled row / column: a 1-D box blur, which PIL has
# no direct spelling for (Kernel accepts only 3x3 and 5x5).
_ACROSS_VERTICAL_STRIPES = [0] * 10 + [1] * 5 + [0] * 10
_ACROSS_HORIZONTAL_STRIPES = [0, 0, 1, 0, 0] * 5


def descreen(im: Image.Image, mode: str) -> Image.Image:
    if mode == "horizontal":
        return im.filter(ImageFilter.Kernel((5, 5), _ACROSS_HORIZONTAL_STRIPES, 5))
    return im.filter(ImageFilter.Kernel((5, 5), _ACROSS_VERTICAL_STRIPES, 5))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    path = argv[0]
    box = None
    if len(argv) > 1 and argv[1] != "-":
        box = [float(x) for x in argv[1].split(",")]
    scale = float(argv[2]) if len(argv) > 2 else 1.0
    mode = argv[3] if len(argv) > 3 else "vertical"
    rot = int(argv[4]) if len(argv) > 4 else 0

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
        im = im.resize((int(im.width * scale), int(im.height * scale)),
                       Image.LANCZOS)
    if mode != "raw":
        im = im.filter(ImageFilter.UnsharpMask(radius=4, percent=160, threshold=2))
    im = ImageOps.autocontrast(im, cutoff=0.5)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "crops")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    tag = (argv[1].replace(",", "-") if box else "full")
    out = os.path.join(out_dir, f"{stem}_{tag}_{scale}_{mode}_{rot}.png")
    im.save(out)
    print(out, im.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
