"""The scan tools' public names are what the guide's table lists (docs/scans.md, «In Python»): each module's
`__all__` is exactly its row — a subcommand's module `HELP`, `add_arguments` and `run`, and what its row adds —, so
the surface the compatibility promise holds (docs/compatibility.md) is the one the guide shows, and no wider."""
from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path

import verso.core.scans
import verso.ru.scans

GUIDE = Path(__file__).resolve().parents[3] / "docs" / "scans.md"
PROTOCOL = {"HELP", "add_arguments", "run"}


def _table() -> dict[str, set[str]]:
    """The guide's rows: a module (or the subcommands' row) and the names it gives."""
    text = GUIDE.read_text(encoding="utf-8").split("## In Python", 1)[1]
    rows: dict[str, set[str]] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2 or not cells[0].startswith(("`verso.", "a subcommand")):
            continue
        rows[cells[0]] = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", cells[1]))
    return rows


def _modules() -> list[str]:
    found = []
    for package in (verso.core.scans, verso.ru.scans):
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            if not info.name.endswith("__main__"):
                found.append(info.name)
    return sorted(found)


def test_every_module_s_all_is_its_row():
    rows = _table()
    subcommand = next(names for key, names in rows.items() if key.startswith("a subcommand"))
    seen = []
    for name in _modules():
        public = set(importlib.import_module(name).__all__)
        row = rows.get(f"`{name}`")
        if row is not None:
            assert public == row, (name, sorted(public ^ row))
        else:
            assert ".cli." in name, f"{name}: no row in docs/scans.md"
            extra = {"leaf", "report"} if name == "verso.ru.scans.cli.rows" else set()
            assert public == PROTOCOL | extra, (name, sorted(public))
            assert extra <= subcommand
        seen.append(name)
    assert PROTOCOL <= subcommand and "verso.ru.scans.cli.rows" in seen
    assert {key for key in rows if key.startswith("`")} == {f"`{name}`" for name in seen if f"`{name}`" in rows}
