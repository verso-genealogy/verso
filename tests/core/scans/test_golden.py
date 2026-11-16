"""`verso scans strips|quadrants|descreen` write what they wrote when a test still held them byte for byte to the
reading plugin's scripts they replaced (`tests/golden/scans-library`, captured by `python -m tests.scans_album
golden-library` at that verso commit): the same files under the same names, the same bytes, the same stdout and
stderr (`<DIR>` for the albums' root), the same exit code — in English and in Russian. verso-ru's `cards` is held
so in `tests/ru/scans/test_golden.py`.

The bytes were captured on macOS; elsewhere a file of other bytes matches by its decoded pixels. `strips` labels
its strips in a system font (Arial on macOS, DejaVu Sans on Linux, else Pillow's own), so its sheets match by name
and size only — the names, the output and the exit code stay exact."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PIL")

from tests.scans_album import LIBRARY_GOLDEN, argv_for, draw_album, draw_cards, matches_golden, tree
from verso.core import plugins
from verso.core.cli import main
from verso.core.scans.cli import CORE

CASES = sorted(p for p in LIBRARY_GOLDEN.glob("*.json")
               if json.loads(p.read_text(encoding="utf-8"))["argv"][0] in CORE)


def test_every_core_subcommand_that_replaced_a_script_has_its_goldens():
    held = {json.loads(p.read_text(encoding="utf-8"))["argv"][0] for p in CASES}
    assert held == {"strips", "quadrants", "descreen"}
    assert len(CASES) >= 22


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_verso_scans_writes_its_golden(path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       capfd: pytest.CaptureFixture[str]):
    golden: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    root = tmp_path / "root"
    draw_album(root)
    draw_cards(root)
    before = tree(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("VERSO_LANG", golden["lang"])
    with plugins.adding(entry_points=False):  # the core's own subcommands: `make test-core` blocks verso.ru
        code = main(["scans", *argv_for(golden["argv"], root)])
    out, err = capfd.readouterr()
    assert matches_golden(golden, root, before, code, out, err) == []
