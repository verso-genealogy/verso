"""The scan tools on frames already on disk, a directory of an album's images (`verso scans <subcommand>`).

The core's subcommands know no numbering of a book: `strips` lays one region of every frame side by side,
`quadrants` cuts a scan into four overlapping quarters, `descreen` takes the moiré off a photograph of a screen,
`jpeg` writes a directory's HEIC frames as JPEG. Each installed plugin adds those that read its books' numbering
(`Plugin.scans`: a name → the module), found as the commands of `verso` are: a module is imported only when the
parser is built, and a name two declare is refused.

A subcommand's module gives `HELP` (its one line), `add_arguments(parser)` and `run(args) -> int`, the exit code.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Mapping

from verso.core.messages import t

__all__ = ["CORE", "build_parser", "main", "subcommands"]

# The core's own subcommands; each installed plugin brings its own (`Plugin.scans`).
CORE: dict[str, str] = {
    "descreen":  "verso.core.scans.cli.descreen",
    "jpeg":      "verso.core.scans.cli.jpeg",
    "quadrants": "verso.core.scans.cli.quadrants",
    "strips":    "verso.core.scans.cli.strips",
}


def _plugins() -> list[tuple[str, Mapping[str, str]]]:
    from verso.core import plugins
    return [(name, plugin.scans) for name, plugin in plugins.installed().items()]


def subcommands() -> dict[str, str]:
    """Every subcommand: the core's, then each installed plugin's — refused when two name one."""
    from verso.core.plugins import PluginError
    out, owner = dict(CORE), dict.fromkeys(CORE, "")
    for name, given in _plugins():
        for sub, module in given.items():
            if sub in owner:
                where = t("cli.where_plugins", first=owner[sub], second=name) if owner[sub] \
                    else t("cli.where_core", plugin=name)
                raise PluginError(t("scans.cli.sub_twice", sub=sub, where=where))
            out[sub], owner[sub] = module, name
    return out


def build_parser() -> argparse.ArgumentParser:
    """The parser of `verso scans`: a subparser for each subcommand, its module imported here."""
    parser = argparse.ArgumentParser(description=str(t("scans.cli.description")))
    sub = parser.add_subparsers(dest="subcommand", required=True, metavar=str(t("scans.cli.sub_metavar")))
    for name, module_name in subcommands().items():
        module = importlib.import_module(module_name)
        help_text = str(module.HELP)
        p = sub.add_parser(name, help=help_text, description=help_text)
        module.add_arguments(p)
        p.set_defaults(run=module.run)
    return parser


def main(argv: list[str] | None = None) -> int:
    import verso.core.workspace  # noqa: F401 — it tells verso.core.i18n where the language comes from
    from verso.core.plugins import PluginError
    try:
        parser = build_parser()
    except PluginError as error:
        print(f"verso scans: {error}", file=sys.stderr)
        return 2
    args = parser.parse_args(argv)
    return args.run(args)
