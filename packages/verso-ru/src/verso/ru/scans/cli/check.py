"""Folio continuity of an album on disk: every side of its run of leaves present, none photographed twice, and —
given the archive's inventory — none outside the year's range. Exits 1 on any defect."""
from __future__ import annotations

import argparse
from pathlib import Path

from verso.core.scans.image import image_names
from verso.ru.scans.folio import check_album, format_report

__all__ = ["HELP", "add_arguments", "run"]

HELP = "folio continuity of an album on disk"


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", metavar="DIR", help="an exported album: a directory of its frames")
    p.add_argument("--first", type=int, help="first folio the year should hold (the archive's inventory)")
    p.add_argument("--last", type=int, help="last folio the year should hold (the archive's inventory)")


def run(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    report = check_album(image_names(directory), expect_first=args.first, expect_last=args.last)
    print(format_report(report, album=directory.name))
    return 0 if report.ok else 1
