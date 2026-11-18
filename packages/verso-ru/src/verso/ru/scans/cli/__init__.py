"""verso-ru's subcommands of `verso scans` (`verso.ru.plugin.SCANS`): each a module with `HELP`,
`add_arguments(parser)` and `run(args)`. The flags two of them share are here."""
from __future__ import annotations

import argparse

from verso.core.scans.level import MAX_ANGLE
from verso.ru.messages import t

__all__ = ["add_angle_flag", "add_enhance_flag", "add_frames_flag"]


def add_frames_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--frames", action="store_true", help=str(t("scans.help.frames")))


def add_enhance_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--enhance", type=float, default=None, metavar="N",
                   help="push a faded hand: 1 = plain autocontrast (default; `zoom` "
                        "takes the album's `enhance` from scans.toml), "
                        "1.6–1.8 for a pale iron-gall ink")


def _angle(text: str) -> float | str:
    """`--angle`: degrees counter-clockwise within ±`MAX_ANGLE`, or `auto` — measured on the page."""
    if text == "auto":
        return text
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(str(t("scans.angle.bad", angle=text, limit=f"{MAX_ANGLE:g}"))) from None
    if not abs(value) <= MAX_ANGLE:
        raise argparse.ArgumentTypeError(str(t("scans.angle.bad", angle=text, limit=f"{MAX_ANGLE:g}")))
    return round(value, 2) + 0.0


def add_angle_flag(p: argparse.ArgumentParser, help_text: str) -> None:
    """`--angle DEG|auto`: the page turned level before a window is cut from it. Unset, nothing turns."""
    p.add_argument("--angle", type=_angle, metavar="DEG|auto", help=help_text)
