"""verso-ru's subcommands of `verso scans` (`verso.ru.plugin.SCANS`): each a module with `HELP`,
`add_arguments(parser)` and `run(args)`. The flags two of them share are here."""
from __future__ import annotations

import argparse

from verso.ru.messages import t

__all__ = ["add_enhance_flag", "add_frames_flag"]


def add_frames_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--frames", action="store_true", help=str(t("scans.help.frames")))


def add_enhance_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--enhance", type=float, default=None, metavar="N",
                   help="push a faded hand: 1 = plain autocontrast (default; `zoom` "
                        "takes the album's `enhance` from scans.toml), "
                        "1.6–1.8 for a pale iron-gall ink")
