"""Strips of one column: the same region cut from every frame of an album and laid side by side, each strip
labelled with its frame, so one image answers «which frame holds двор 45» or «where does the parents' column name
Маниловъ» for 20–40 frames at once.

The region is given in FRACTIONS of the frame (x0,y0,x1,y1), because the scans of one дело drift by a few pixels
in size (an archive's reading-room scans: 1500×1176…1184). A tall, narrow region (a column: «№ семьи», «Имена
родившихся») is laid out left to right; a wide, low one (a header line, the «домохозяин» line of a 1917 card) is
stacked top to bottom.

It works on scans with a steady layout — an archive's own scanning. Phone photographs of a book shift and rotate
from frame to frame, and a fixed region misses.

A strip is for FINDING, not reading: open the frame it names and read it at full size. Each sheet's path is
printed once to stdout; frames that cannot be opened go to stderr with the frame to resume from. Sheets are named
`strips_<first>-<last>.jpg`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from verso.core.messages import t
from verso.core.scans.image import IMAGE_SUFFIXES, pil
from verso.core.scans.sheets import strips_sheet

__all__ = ["HELP", "add_arguments", "run"]

HELP = t("scans.cli.help_strips")


def parse_box(text: str) -> tuple[float, float, float, float]:
    """`x0,y0,x1,y1` as four fractions of the frame, x0 < x1 and y0 < y1."""
    try:
        x0, y0, x1, y1 = (float(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(str(t("scans.strips.bad_box"))) from None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise argparse.ArgumentTypeError(str(t("scans.strips.box_range")))
    return x0, y0, x1, y1


def frames(album: Path, span: str | None) -> list[Path]:
    """The frames of `album`, in name order; `span` FIRST-LAST keeps those whose stem falls between (string order)."""
    files = sorted(p for p in album.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if span:
        first, _, last = span.partition("-")
        last = last or first
        files = [p for p in files if first <= p.stem[: len(first)] and p.stem[: len(last)] <= last]
    return files


def cut(path: Path, box: tuple[float, float, float, float]) -> Any:
    """The region `box` of the frame at `path`, upright by its EXIF tag."""
    Image, ImageOps, _ = pil()
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    x0, y0, x1, y1 = box
    return im.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("album", type=Path, metavar="ALBUM", help=str(t("scans.cli.help_album")))
    p.add_argument("--box", type=parse_box, required=True, metavar="X0,Y0,X1,Y1", help=str(t("scans.cli.help_box")))
    p.add_argument("--frames", metavar="FIRST-LAST", help=str(t("scans.cli.help_strips_frames")))
    p.add_argument("--per", type=int, default=20, help=str(t("scans.cli.help_per")))
    p.add_argument("--size", type=int, default=900, help=str(t("scans.cli.help_size")))
    p.add_argument("--out", type=Path, required=True, help=str(t("scans.cli.help_strips_out")))


def run(args: argparse.Namespace) -> int:
    if not args.album.is_dir():
        print(t("scans.strips.no_album", album=args.album), file=sys.stderr)
        return 2
    todo = frames(args.album, args.frames)
    if not todo:
        print(t("scans.strips.no_frames"), file=sys.stderr)
        return 2
    x0, y0, x1, y1 = args.box
    column = (y1 - y0) >= (x1 - x0)  # by fractions; a spread is wider than tall, a page taller
    args.out.mkdir(parents=True, exist_ok=True)
    batch: list[tuple[str, Any]] = []
    for i, path in enumerate(todo):
        try:
            batch.append((path.stem, cut(path, args.box)))
        except Exception as exc:
            print(t("scans.strips.skipped", name=path.name, error=exc), file=sys.stderr)
        last = i == len(todo) - 1
        if batch and (len(batch) == args.per or last):
            name = args.out / f"strips_{batch[0][0]}-{batch[-1][0]}.jpg"
            strips_sheet(batch, column, args.size).save(name, quality=85)
            print(name)
            batch = []
    return 0
