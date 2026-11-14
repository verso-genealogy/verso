"""A command that finds no workspace says so in a line, not in a traceback."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.codepaths import pythonpath


@pytest.mark.parametrize("argv", [
    ["-m", "verso.ru.cli.facts", "--village", "Горюхино"],
    ["-m", "verso.ru.linters.dead_code"],
], ids=["facts", "dead-code"])
def test_no_workspace_is_one_line(argv: list[str], tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "VERSO_WORKSPACE"} | {"PYTHONPATH": pythonpath(),
                                                                            "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, *argv], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=120, check=False)
    assert done.returncode != 0
    assert "Traceback" not in done.stderr
    assert done.stderr.strip().splitlines()[-1].startswith("рабочая область не найдена")
    assert len(done.stderr.strip().splitlines()) == 1
