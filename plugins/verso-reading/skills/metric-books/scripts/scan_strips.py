#!/usr/bin/env python3
"""Ленты по одной графе: the same region cut from every frame of an album and laid
side by side, each strip labelled with its frame, so one image answers «which frame
holds двор 45» or «where does the parents column name Маниловъ» for 20–40 frames at once.

The region is given in FRACTIONS of the frame (x0,y0,x1,y1), because archive scans of one
дело drift by a few pixels in size (an archive's reading-room scans: 1500×1176…1184). A tall, narrow region (a
column: «№ семьи», «Имена родившихся») is laid out left to right; a wide, low one (a header
line, the «домохозяин» line of a 1917 card) is stacked top to bottom.

It works on scans with a steady layout — an archive's own scanning. Phone photographs of a
book shift and rotate from frame to frame, and a fixed region misses.

A strip is for FINDING, not reading: open the frame it names and read it at full size
(the two-tier rule of the `metric-books` skill). Each sheet's path is printed once to
stdout; frames that cannot be opened go to stderr with the frame to resume from.

Usage (any Python with Pillow):
    python3 scan_strips.py ALBUM_DIR \
        --box 0.07,0.26,0.20,0.93 [--frames 0671-0776] [--per 20] [--size 900] \
        --out DIR

    ALBUM_DIR   a directory of frames (an exported album)
    --box       x0,y0,x1,y1 as fractions of the frame (0..1)
    --frames    first-last by file stem (string order), default every image
    --per       strips per sheet (default 20)
    --size      strip height for columns / strip width for rows, px (default 900)
    --out       output directory (created); sheets are named strips_<first>-<last>.jpg
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic"}
LABEL = 28  # px reserved for the frame label
GAP = 6


def parse_box(text: str) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = (float(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("--box: четыре доли через запятую, x0,y0,x1,y1") from None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise argparse.ArgumentTypeError("--box: нужно 0 ≤ x0 < x1 ≤ 1 и 0 ≤ y0 < y1 ≤ 1")
    return x0, y0, x1, y1


def frames(album: Path, span: str | None) -> list[Path]:
    files = sorted(p for p in album.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if span:
        first, _, last = span.partition("-")
        last = last or first
        files = [p for p in files if first <= p.stem[: len(first)] and p.stem[: len(last)] <= last]
    return files


def cut(path: Path, box: tuple[float, float, float, float]) -> Image.Image:
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    x0, y0, x1, y1 = box
    return im.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))


def font() -> ImageFont.ImageFont:
    for name in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(name).exists():
            return ImageFont.truetype(name, 20)
    return ImageFont.load_default()


def sheet(strips: list[tuple[str, Image.Image]], column: bool, size: int) -> Image.Image:
    f = font()
    scaled = []
    for label, im in strips:
        if column:  # equal height, laid left to right
            im = im.resize((max(1, round(im.width * size / im.height)), size))
        else:  # equal width, stacked top to bottom
            im = im.resize((size, max(1, round(im.height * size / im.width))))
        scaled.append((label, im))
    if column:
        width = sum(max(im.width, 60) for _, im in scaled) + GAP * (len(scaled) - 1)
        out = Image.new("RGB", (width, size + LABEL), "white")
        x = 0
        for label, im in scaled:
            ImageDraw.Draw(out).text((x + 2, 2), label, fill="red", font=f)
            out.paste(im, (x, LABEL))
            x += max(im.width, 60) + GAP
    else:
        height = sum(im.height + LABEL for _, im in scaled) + GAP * (len(scaled) - 1)
        out = Image.new("RGB", (size, height), "white")
        y = 0
        for label, im in scaled:
            ImageDraw.Draw(out).text((2, y + 2), label, fill="red", font=f)
            out.paste(im, (0, y + LABEL))
            y += im.height + LABEL + GAP
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("album", type=Path)
    ap.add_argument("--box", type=parse_box, required=True)
    ap.add_argument("--frames")
    ap.add_argument("--per", type=int, default=20)
    ap.add_argument("--size", type=int, default=900)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if not args.album.is_dir():
        print(f"нет такого альбома: {args.album}", file=sys.stderr)
        return 2
    todo = frames(args.album, args.frames)
    if not todo:
        print("ни одного кадра в этом диапазоне", file=sys.stderr)
        return 2
    x0, y0, x1, y1 = args.box
    column = (y1 - y0) >= (x1 - x0)  # by fractions; a spread is wider than tall, a page taller
    args.out.mkdir(parents=True, exist_ok=True)
    batch: list[tuple[str, Image.Image]] = []
    for i, path in enumerate(todo):
        try:
            batch.append((path.stem, cut(path, args.box)))
        except Exception as exc:  # a broken frame must not lose the sheets already made
            print(f"пропущен {path.name}: {exc}", file=sys.stderr)
        last = i == len(todo) - 1
        if batch and (len(batch) == args.per or last):
            name = args.out / f"strips_{batch[0][0]}-{batch[-1][0]}.jpg"
            sheet(batch, column, args.size).save(name, quality=85)
            print(name)
            batch = []
    return 0


if __name__ == "__main__":
    sys.exit(main())
