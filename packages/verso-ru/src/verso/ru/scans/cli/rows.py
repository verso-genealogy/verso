"""Where each record of a leaf begins: the marks in the счётъ column and the cuts between records, printed, and
drawn on one sheet for every leaf asked — `rows_<first>[-<last>]_<part>.jpg`, one image to check a run of leaves.
It writes no window: `scans.toml` is the review page's (`verso.ru.scans.rows`)."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from verso.core.scans import stanza
from verso.core.scans.stanza import Stanza
from verso.ru.messages import t
from verso.ru.scans import rows as scan_rows
from verso.ru.scans.album import load_pages, note_frame_mode, open_page, page_named, titled, where
from verso.ru.scans.cli import add_frames_flag
from verso.ru.scans.folio import Page
from verso.ru.scans.zoom import COLUMNS, DEFAULT_TOP

__all__ = ["HELP", "add_arguments", "leaf", "report", "run"]

HELP = t("scans.rows.help_rows")


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", metavar="DIR")
    p.add_argument("--part", type=int, required=True, choices=sorted(COLUMNS), help=str(t("scans.help.zoom_part")))
    p.add_argument("--x0", type=float, default=0.0, help=str(t("scans.rows.help_x0")))
    p.add_argument("--x1", type=float, default=1.0, help=str(t("scans.rows.help_x1")))
    p.add_argument("--count", type=float, nargs=2, metavar=("X0", "X1"), help=str(t("scans.rows.help_count")))
    p.add_argument("--top", type=float, help=str(t("scans.rows.help_top", top=DEFAULT_TOP)))
    p.add_argument("--bottom", type=float, help=str(t("scans.rows.help_bottom")))
    p.add_argument("--layout", help="path to scans.toml (default: the album's, else the village's)")
    p.add_argument("--village", help="village directory holding the durable scans.toml")
    p.add_argument("--album-title", help="which album's section to use, when scans.toml holds several")
    p.add_argument("--out", help=str(t("scans.rows.help_out")))
    add_frames_flag(p)
    p.add_argument("--folio", required=True, nargs="+", help=str(t("scans.rows.help_folios")))


def leaf(args: argparse.Namespace, album: Stanza | None) -> tuple[float, float, float, float]:
    """(x0, x1, top, bottom) of the leaf the rows are read on: the flags, else the album's stanza (its `top` and
    `bottom`, measured once for the дело), else the whole width under `DEFAULT_TOP`."""
    top = args.top if args.top is not None else (
        album.top if album is not None and album.top is not None else DEFAULT_TOP)
    bottom = args.bottom if args.bottom is not None else (
        album.bottom if album is not None and album.bottom is not None else 1.0)
    if not (0.0 <= args.x0 < args.x1 <= 1.0 and 0.0 <= top < bottom <= 1.0):
        raise SystemExit(t("scans.rows.bad_leaf", x0=args.x0, x1=args.x1, top=top, bottom=bottom))
    return args.x0, args.x1, top, bottom


def report(rows: scan_rows.Rows, place: str, part: int, top: float) -> None:
    """What `detect` found on a leaf, printed: its marks and its cuts."""
    print(t("scans.rows.found", where=place, part=part, marks=len(rows.marks), top=f"{top:g}"))
    if rows.cut:
        print(t("scans.rows.cut_at_top"))
    for index, mark in enumerate(rows.marks, 1):
        print(f"  {index:>2}  {mark.y0:.3f}–{mark.y1:.3f}")
    if rows.cuts:
        print(t("scans.rows.cuts", cuts=" ".join(f"{c:g}" for c in rows.cuts)))


def _read(directory: Path, args: argparse.Namespace, album: Stanza | None, page: Page,
          bounds: tuple[float, float, float, float]) -> tuple[Any, scan_rows.Rows, tuple[float, float]]:
    """(the page's image, its rows, the счётъ column) — detected on the page."""
    x0, x1, top, bottom = bounds
    image = open_page(directory, page, album.rotation_for(page.label) if album else 0)
    count = tuple(args.count) if args.count else scan_rows.count_window(args.part, x0, x1)
    return image, scan_rows.detect(image, x0=x0, x1=x1, count=count, top=top, bottom=bottom), count


def run(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    _, title, stanzas = stanza.for_album(directory, layout=args.layout, village=args.village,
                                         album_title=args.album_title)
    album = stanzas.album(title) if title else None
    pages, by_frame = load_pages(directory, force_frames=args.frames,
                                 expand=bool(album and album.frames == "spread"),
                                 turn=album.rotate if album else 0)
    if by_frame:
        note_frame_mode(directory, len(pages))
    bounds = leaf(args, album)
    rulers = []
    labels = []
    for folio in args.folio:
        page = page_named(directory, pages, by_frame, folio)
        image, rows, count = _read(directory, args, album, page, bounds)
        place = where(page, by_frame)
        report(rows, place, args.part, bounds[2])
        rulers.append(scan_rows.ruler(image, rows, x0=bounds[0], x1=bounds[1], count=count, top=bounds[2],
                                      bottom=bounds[3], title=titled(place, args.part)))
        labels.append(page.label)
    out = (Path(args.out) if args.out
           else directory / f"rows_{labels[0]}{'-' + labels[-1] if len(labels) > 1 else ''}_{args.part}.jpg")
    scan_rows.sheet(rulers).save(out, quality=88)
    print(t("scans.rows.sheet", path=out))
    return 0
