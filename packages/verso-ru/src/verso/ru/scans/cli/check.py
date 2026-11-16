"""Folio continuity of an album on disk: every side of its run of leaves present, none photographed twice, and —
given the archive's inventory — none outside the year's range. Exits 1 on any defect.

An album whose stanza of `scans.toml` (the directory's own) says `frames = "spread"` is checked as its frames hold
it: a frame named by its left leaf holds the facing recto too, unless it stands up as one page."""
from __future__ import annotations

import argparse
from pathlib import Path

from verso.core.scans.image import image_names
from verso.ru.messages import t
from verso.ru.scans.album import album_of, spread_frames
from verso.ru.scans.folio import check_album, format_report

__all__ = ["HELP", "add_arguments", "run"]

HELP = "folio continuity of an album on disk"


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", metavar="DIR", help="an exported album: a directory of its frames")
    p.add_argument("--first", type=int, help="first folio the year should hold (the archive's inventory)")
    p.add_argument("--last", type=int, help="last folio the year should hold (the archive's inventory)")


def run(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    spreads = spread_frames(directory, album_of(directory))
    report = check_album(image_names(directory), expect_first=args.first, expect_last=args.last, spreads=spreads)
    print(format_report(report, album=directory.name))
    if spreads is not None:
        print(t("scans.spread_album"))
    return 0 if report.ok else 1
