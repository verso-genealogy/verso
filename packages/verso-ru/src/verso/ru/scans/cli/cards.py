"""The readable parts of the 1917 farm-census cards (Всероссийская с/х перепись 1917), cut out.

A card stitched from an archive's viewer tiles is a ~8800×6700 two-page spread. Read whole it is downscaled to
~1.1 MP and nothing on it resolves; the names and ages live in three small windows. For every card in ALBUM this
writes, into OUT:

    NN.jpg          the «Население» table (top) over the card header (bottom): домохозяин, сословие, «Отс.»,
                    № карточки. The table sits ABOVE its own header on the printed form and fills BOTTOM-UP — the
                    Х row is the one nearest the column numbers 1…21.
    numbers.jpg     the «№ карточки» box of every card, tiled — the card order at a glance
    leaves.jpg      the pencil лист number, top-right, tiled

Windows are fractions of the (EXIF-upright) frame, measured on one дело of these cards. Other дела of the same
census use the same printed form, but check one card by eye first and pass --header/--table/--number/--leaf to move
a window. `--zoom IDX:x0:y0:x1:y1` cuts one window of one card (its index in sorted order), autocontrasted, 1400 px
wide: `zoom_NN.jpg`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from verso.core.scans.image import IMAGE_SUFFIXES, pil

__all__ = ["HELP", "add_arguments", "run"]

HELP = "the readable windows of the 1917 farm-census cards: the table over the header, the card numbers, the leaves"
TABLE = (0.00, 0.03, 0.66, 0.345)
HEADER = (0.19, 0.37, 0.84, 0.625)
NUMBER = (0.76, 0.37, 0.90, 0.43)
LEAF = (0.90, 0.00, 1.00, 0.05)
WIDTH = 1500


def _box(text: str) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in text.split(":"))
    return (x0, y0, x1, y1)


def _open(path: Path) -> Any:
    Image, ImageOps, _ = pil()
    return ImageOps.exif_transpose(Image.open(path))


def _cut(im: Any, box: tuple[float, float, float, float]) -> Any:
    w, h = im.size
    return im.crop((int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))


def _fit(im: Any, width: int) -> Any:
    from PIL import Image
    return im.resize((width, max(1, int(im.height * width / im.width))), Image.Resampling.LANCZOS)


def _tile(cards: list[Path], box: tuple[float, float, float, float], out: Path) -> None:
    from PIL import Image, ImageDraw
    tiles = []
    for i, f in enumerate(cards):
        tile = _fit(_cut(_open(f), box), 360)
        d = ImageDraw.Draw(tile)
        d.rectangle((0, 0, 40, 28), fill="white")
        d.text((3, 3), f"{i:02d}", fill="red")
        tiles.append(tile)
    w = tiles[0].width
    h = max(tile.height for tile in tiles)
    cols = 4
    grid = Image.new("RGB", (w * cols, h * ((len(tiles) + cols - 1) // cols)), "white")
    for i, tile in enumerate(tiles):
        grid.paste(tile, ((i % cols) * w, (i // cols) * h))
    grid.save(out, quality=85)


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("album", type=Path, metavar="ALBUM", help="a directory of the cards' frames")
    p.add_argument("out", type=Path, metavar="OUT", help="where the cuts are written (created)")
    p.add_argument("--header", type=_box, default=HEADER, metavar="X0:Y0:X1:Y1", help="the card header's window")
    p.add_argument("--table", type=_box, default=TABLE, metavar="X0:Y0:X1:Y1", help="the population table's window")
    p.add_argument("--number", type=_box, default=NUMBER, metavar="X0:Y0:X1:Y1", help="the card number's window")
    p.add_argument("--leaf", type=_box, default=LEAF, metavar="X0:Y0:X1:Y1", help="the pencil leaf number's window")
    p.add_argument("--zoom", help="IDX:x0:y0:x1:y1 — one enlarged window of one card")


def run(args: argparse.Namespace) -> int:
    Image, ImageOps, _ = pil()
    cards = sorted(p for p in args.album.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not cards:
        print(f"no images in {args.album}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    if args.zoom:
        idx, rest = args.zoom.split(":", 1)
        crop = ImageOps.autocontrast(_cut(_open(cards[int(idx)]), _box(rest)).convert("L"), cutoff=1)
        target = args.out / f"zoom_{int(idx):02d}.jpg"
        _fit(crop, 1400).save(target, quality=88)
        print(target)
        return 0

    for i, f in enumerate(cards):
        im = _open(f)
        table = _fit(_cut(im, args.table), WIDTH)
        header = _fit(_cut(im, args.header), WIDTH)
        sheet = Image.new("RGB", (WIDTH, table.height + header.height + 10), "white")
        sheet.paste(table, (0, 0))
        sheet.paste(header, (0, table.height + 10))
        sheet.save(args.out / f"{i:02d}.jpg", quality=85)
        print(f"{i:02d}  {f.name.split('.')[0]}")
    _tile(cards, args.number, args.out / "numbers.jpg")
    _tile(cards, args.leaf, args.out / "leaves.jpg")
    return 0
