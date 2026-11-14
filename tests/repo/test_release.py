"""tools/release.py — a version stamped into the four distributions at once (TestPyPI trial)."""
from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tools import release

REPO = Path(__file__).resolve().parent.parent.parent    # the library's root


def _tree(tmp_path: Path) -> Path:
    for project in release.PROJECTS:
        (tmp_path / project).mkdir(parents=True)
        shutil.copy(REPO / project / "pyproject.toml", tmp_path / project / "pyproject.toml")
    return tmp_path


def _project(root: Path, project: str) -> dict[str, Any]:
    return tomllib.loads((root / project / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_stamp_moves_every_version_and_sister_pin(tmp_path: Path):
    root = _tree(tmp_path)
    written = release.stamp("0.1.0.dev7", root)
    assert sorted(p.relative_to(root).as_posix() for p in written) == sorted(
        f"{p}/pyproject.toml" for p in release.PROJECTS)
    for project in release.PROJECTS:
        meta = _project(root, project)
        assert meta["version"] == "0.1.0.dev7"
        sisters = [d for d in meta.get("dependencies", []) if d.startswith("verso-")]
        assert all(d.endswith("==0.1.0.dev7") for d in sisters), sisters
    assert "verso-core==0.1.0.dev7" in _project(root, "packages/verso-ru")["dependencies"]
    # Third-party pins stay as they are (which versions they are is Dependabot's).
    third = [d for d in _project(REPO, "packages/verso-ru")["dependencies"] if not d.startswith("verso-")]
    assert third and all(d in _project(root, "packages/verso-ru")["dependencies"] for d in third), third


@pytest.mark.parametrize("version", ["0.1", "v0.1.0", "0.1.0-dev1", "0.1.0.post1", "1.2.3.dev"])
def test_stamp_refuses_a_version_of_another_shape(tmp_path: Path, version: str):
    root = _tree(tmp_path)
    before = {p: (root / p / "pyproject.toml").read_bytes() for p in release.PROJECTS}
    with pytest.raises(SystemExit, match=f"версия {version}: ждём X.Y.Z"):
        release.stamp(version, root)
    assert {p: (root / p / "pyproject.toml").read_bytes() for p in release.PROJECTS} == before


def test_stamp_twice_is_stamp_once(tmp_path: Path):
    root = _tree(tmp_path)
    release.stamp("0.2.0rc1", root)
    once = {p: (root / p / "pyproject.toml").read_bytes() for p in release.PROJECTS}
    release.stamp("0.2.0rc1", root)
    assert {p: (root / p / "pyproject.toml").read_bytes() for p in release.PROJECTS} == once
