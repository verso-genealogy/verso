"""A workspace whose one plugin is the toy, found with the entry points hidden."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.core.toy import TOY
from verso.core import plugins, workspace


@pytest.fixture(autouse=True)
def _english(monkeypatch: pytest.MonkeyPatch) -> None:
    """The core's tests speak English: a toy workspace of schema 4 reads as Russian, and the
    library's conftest names Russian for every other test."""
    monkeypatch.setenv("VERSO_LANG", "en")


@pytest.fixture
def toy_workspace(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["toy"]\n', encoding="utf-8")
    with plugins.adding(TOY, entry_points=False), workspace.use(tmp_path):
        yield tmp_path
