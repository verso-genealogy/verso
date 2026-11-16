"""`verso scans check|headers|crops|spread|zoom|rows` write what the App's `verso-scans` wrote on the same album
(`tests/golden/scans`, captured by `python -m tests.scans_album golden`): the same files under the same names, the same
bytes, the same stdout and stderr (`<DIR>` for the album's root), the same exit code — in English and in Russian.

The golden bytes were captured on macOS. A platform whose JPEG coder writes other bytes for the same pixels still
matches by the decoded image (`pixels`, the SHA-256 of `Image.tobytes()`); the names, the output and the exit code
stay exact."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PIL")

from tests.scans_album import GOLDEN, argv_for, blank, draw_album, pixels, tree, written
from verso.core.cli import main

CASES = sorted(GOLDEN.glob("*.json"))


def test_the_golden_outputs_are_there():
    assert len(CASES) >= 80


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_verso_scans_writes_what_the_app_wrote(path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capfd: pytest.CaptureFixture[str]):
    golden: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    root = tmp_path / "root"
    root.mkdir()
    draw_album(root)
    before = tree(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("VERSO_LANG", golden["lang"])
    code = main(["scans", *argv_for(golden["argv"], root)])
    out, err = capfd.readouterr()
    assert (code, blank(out, root), blank(err, root)) == (golden["exit"], golden["stdout"], golden["stderr"])
    files = written(root, before)
    assert sorted(files) == sorted(golden["files"])
    for name, sha in files.items():
        if sha != golden["files"][name]:
            assert pixels(root / name) == golden["pixels"][name], f"{name}: other pixels than the App's"
            assert os.uname().sysname != "Darwin", f"{name}: other bytes than the App's, on the platform it was captured on"
