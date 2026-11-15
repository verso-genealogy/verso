#!/usr/bin/env python3
"""Cut the readable parts out of 1917 farm-census cards (Всероссийская с/х перепись 1917).

A card stitched from an archive's viewer tiles is a ~8800×6700 two-page spread. Read whole it is
downscaled to ~1.1 MP and nothing on it resolves; the names and ages live in three
small windows. For every card in DIR this writes, into OUT:

    NN.jpg          the «Население» table (top) over the card header (bottom): домохозяин,
                    сословие, «Отс.», № карточки. The table sits ABOVE its own header on the
                    printed form and fills BOTTOM-UP — the Х row is the one nearest the
                    column numbers 1…21.
    numbers.jpg     the «№ карточки» box of every card, tiled — the card order at a glance
    leaves.jpg      the pencil лист number, top-right, tiled

Windows are fractions of the (EXIF-upright) frame, measured on one дело of these cards. Other
дела of the same census use the same printed form, but check one card by eye first and
pass --header/--table/--number/--leaf to move a window.

    python3 card_crops.py <album_dir> <out_dir>
    python3 card_crops.py <album_dir> <out_dir> --zoom 7:0.20:0.47:0.52:0.52
        # one card (index in sorted order), one box x0:y0:x1:y1, autocontrast, 1400 px wide
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

TABLE = (0.00, 0.03, 0.66, 0.345)
HEADER = (0.19, 0.37, 0.84, 0.625)
NUMBER = (0.76, 0.37, 0.90, 0.43)
LEAF = (0.90, 0.00, 1.00, 0.05)
WIDTH = 1500


def _box(text: str) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in text.split(":"))
    return (x0, y0, x1, y1)


def _open(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path))


def _cut(im: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = im.size
    return im.crop((int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))


def _fit(im: Image.Image, width: int) -> Image.Image:
    return im.resize((width, max(1, int(im.height * width / im.width))), Image.Resampling.LANCZOS)


def _tile(cards: list[Path], box: tuple[float, float, float, float], out: Path) -> None:
    tiles = []
    for i, f in enumerate(cards):
        t = _fit(_cut(_open(f), box), 360)
        d = ImageDraw.Draw(t)
        d.rectangle((0, 0, 40, 28), fill="white")
        d.text((3, 3), f"{i:02d}", fill="red")
        tiles.append(t)
    w = tiles[0].width
    h = max(t.height for t in tiles)
    cols = 4
    grid = Image.new("RGB", (w * cols, h * ((len(tiles) + cols - 1) // cols)), "white")
    for i, t in enumerate(tiles):
        grid.paste(t, ((i % cols) * w, (i // cols) * h))
    grid.save(out, quality=85)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("album", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--header", type=_box, default=HEADER)
    ap.add_argument("--table", type=_box, default=TABLE)
    ap.add_argument("--number", type=_box, default=NUMBER)
    ap.add_argument("--leaf", type=_box, default=LEAF)
    ap.add_argument("--zoom", help="IDX:x0:y0:x1:y1 — one enlarged window of one card")
    a = ap.parse_args()

    cards = sorted(p for p in a.album.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not cards:
        print(f"no images in {a.album}", file=sys.stderr)
        return 1
    a.out.mkdir(parents=True, exist_ok=True)

    if a.zoom:
        idx, rest = a.zoom.split(":", 1)
        crop = ImageOps.autocontrast(_cut(_open(cards[int(idx)]), _box(rest)).convert("L"), cutoff=1)
        target = a.out / f"zoom_{int(idx):02d}.jpg"
        _fit(crop, 1400).save(target, quality=88)
        print(target)
        return 0

    for i, f in enumerate(cards):
        im = _open(f)
        table = _fit(_cut(im, a.table), WIDTH)
        header = _fit(_cut(im, a.header), WIDTH)
        sheet = Image.new("RGB", (WIDTH, table.height + header.height + 10), "white")
        sheet.paste(table, (0, 0))
        sheet.paste(header, (0, table.height + 10))
        sheet.save(a.out / f"{i:02d}.jpg", quality=85)
        print(f"{i:02d}  {f.name.split('.')[0]}")
    _tile(cards, a.number, a.out / "numbers.jpg")
    _tile(cards, a.leaf, a.out / "leaves.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
