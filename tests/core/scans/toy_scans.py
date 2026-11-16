"""The toy plugin's subcommand of `verso scans`: counts the frames of a directory."""
from __future__ import annotations

import argparse
from pathlib import Path

HELP = "count the frames"


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", type=Path)


def run(args: argparse.Namespace) -> int:
    from verso.core.scans.image import image_names
    print(len(image_names(args.directory)))
    return 0
