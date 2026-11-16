"""A directory's HEIC frames written as JPEG: each of the same name with the suffix `.jpg`, at its own pixel size,
quality 92, its orientation turned into the pixels (`verso.core.scans.image.heic_to_jpeg`); the HEIC is taken away.
JPEGs, PNGs and TIFFs are left as they are, and a HEIC beside a `.jpg` of its stem is kept (one JPEG cannot be both).
Exits 1 when any frame was not written. Needs pillow-heif (`pip install 'verso-core[heic]'`).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from verso.core.messages import t
from verso.core.scans.image import convert_heic_frames, pil

__all__ = ["HELP", "add_arguments", "run"]

HELP = t("scans.cli.help_jpeg")


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", type=Path, metavar="DIR", help=str(t("scans.cli.help_jpeg_dir")))


def run(args: argparse.Namespace) -> int:
    pil()
    return 1 if convert_heic_frames(args.directory, None) else 0
