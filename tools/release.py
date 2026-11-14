"""A version stamped into both distributions at once: their
`version` and the pin of the sister distribution (`verso-core==…`), which the two keep equal.

    python tools/release.py stamp 0.1.0          # make stamp v=0.1.0 — before a tag, and in publish.yml

A version is X.Y.Z, X.Y.Z.devN or X.Y.ZrcN; anything else is refused before a file is written.
Standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECTS = ("packages/verso-core", "packages/verso-ru")
_VERSION = re.compile(r"\d+\.\d+\.\d+(?:\.dev\d+|rc\d+)?")
_OWN = re.compile(r'^version = "[^"]*"$', re.M)
_SISTER = re.compile(r'("verso-(?:core|ru)(?:\[[^\]]*\])?==)[^"]*(")')


def stamp(version: str, root: Path = REPO) -> list[Path]:
    """Write `version` into both pyproject.toml — their own and their sister's pin; the files."""
    if not _VERSION.fullmatch(version):
        raise SystemExit(f"версия {version}: ждём X.Y.Z[.devN|rcN]")
    paths = [root / project / "pyproject.toml" for project in PROJECTS]
    texts = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        text, own = _OWN.subn(f'version = "{version}"', text, count=1)
        if own != 1:
            raise SystemExit(f"{path}: нет строки version")
        texts.append(_SISTER.sub(lambda m: f"{m.group(1)}{version}{m.group(2)}", text))
    for path, text in zip(paths, texts, strict=True):
        path.write_text(text, encoding="utf-8")
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/release.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    stamped = sub.add_parser("stamp", help="write a version into both distributions")
    stamped.add_argument("version")
    args = parser.parse_args(argv)
    for path in stamp(args.version):
        print(path.relative_to(REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
