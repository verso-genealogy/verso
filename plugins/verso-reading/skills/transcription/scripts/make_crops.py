#!/usr/bin/env python3
"""Generate upscaled, sharpened quadrant crops of document scans for transcription.

Low-resolution scans (e.g. a 1024px-wide two-page spread) are unreadable when
viewed whole: the cursive handwriting is only a few pixels tall. Cropping each
page into overlapping quadrants and upscaling them 3x with an unsharp mask makes
the script legible to a vision model without inventing detail.

Usage:
    python3 make_crops.py IMAGE [IMAGE ...] --out OUT_DIR    # needs Pillow

For each input image N.png four crops are written to OUT_DIR:
    N_tl.png  left page, top       N_tr.png  right page, top
    N_bl.png  left page, bottom    N_br.png  right page, bottom
Crops overlap by ~50-60 source pixels along the centre lines so no text is lost
at the seams.
"""

import argparse
import os

from PIL import Image, ImageFilter

OVERLAP_X = 60
OVERLAP_Y = 50
SCALE = 3


def make_crops(image_path: str, out_dir: str) -> list[str]:
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
        crop = crop.resize((crop.width * SCALE, crop.height * SCALE), Image.LANCZOS)
        crop = crop.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2))
        out_path = os.path.join(out_dir, f"{stem}_{name}.png")
        crop.save(out_path)
        written.append(out_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="Source scan image(s)")
    parser.add_argument("--out", required=True, help="Output directory for crops")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for image in args.images:
        for path in make_crops(image, args.out):
            print(path)


if __name__ == "__main__":
    main()
