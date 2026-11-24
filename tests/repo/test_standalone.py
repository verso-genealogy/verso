"""tools/standalone.py: the tests from the repository's archive,
outside the checkout."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tools import standalone

# The tests of a git checkout: a standalone copy is an archive, no repository.
IN_GIT = subprocess.run(["git", "-C", str(standalone.ROOT), "rev-parse", "--show-toplevel"],
                        capture_output=True, text=True, check=False).returncode == 0 \
    and not os.environ.get("VERSO_SENTINEL")
needs_git = pytest.mark.skipif(not IN_GIT, reason="a standalone copy is no git checkout")


@needs_git
def test_standalone_extracts_outside_the_checkout(tmp_path: Path):
    copy = standalone.extract(tmp_path / "verso")
    assert (copy / "packages" / "verso-core" / "pyproject.toml").is_file()
    assert (copy / "tests" / "conftest.py").is_file()
    assert standalone.ROOT not in copy.parents
    with pytest.raises(standalone.StandaloneError, match="внутри checkout"):
        standalone.extract(standalone.ROOT / "standalone-copy")
    assert not (standalone.ROOT / "standalone-copy").exists()


def test_standalone_pins_come_from_requirements_dev():
    pins = standalone.pins()
    assert [p.split("==")[0] for p in pins] == ["pytest", "pytest-xdist", "jsonschema", "pyyaml"]
    assert all(re.fullmatch(r"[a-z-]+==[\w.]+", pin) for pin in pins), pins


def test_the_distributions_are_the_repositorys():
    for directory in standalone.DISTS:
        assert (standalone.ROOT / directory / "pyproject.toml").is_file(), directory


def test_a_logged_refusal_fails_the_run(tmp_path: Path):
    log = tmp_path / "sentinel.log"
    standalone.check_log(log)                       # no log: nothing was refused
    log.write_text("/repo/corpus/places.toml\n/repo/corpus/places.toml\n", encoding="utf-8")
    with pytest.raises(standalone.StandaloneError, match=r"сторож: читали вне проекта — /repo/corpus/places\.toml$"):
        standalone.check_log(log)


def test_the_children_are_guarded_too(tmp_path: Path):
    """The venv's site-packages gets a .pth that installs the sentinel in every Python it starts —
    a test's child as well as pytest."""
    site, repo = tmp_path / "site", tmp_path / "repo"
    site.mkdir()
    repo.mkdir()
    (repo / "x").write_text("x", encoding="utf-8")
    standalone.guard_children(site, standalone.ROOT / "tests" / "sentinel.py")
    code = f"import site\nsite.addsitedir({str(site)!r})\nopen({str(repo / 'x')!r})"
    env = {k: v for k, v in os.environ.items() if k != "VERSO_SENTINEL_LOG"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False,
                          env={**env, "VERSO_SENTINEL": str(repo)})
    assert f"читает вне проекта: {repo.resolve() / 'x'}" in done.stderr


@needs_git
def test_the_whole_repository_and_the_main_checkout_are_forbidden():
    """In a parent repository the library is lib/: the sentinel refuses the whole repository holding it."""
    top = subprocess.run(["git", "-C", str(standalone.ROOT), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True).stdout.strip()
    common = subprocess.run(["git", "-C", str(standalone.ROOT), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
    forbidden = standalone.forbidden()
    assert forbidden[0] == Path(top).resolve() and Path(common).parent.resolve() in forbidden


def test_a_kept_directory_must_be_empty(tmp_path: Path):
    (tmp_path / "left").write_text("", encoding="utf-8")
    with pytest.raises(standalone.StandaloneError, match="не пуст"):
        standalone.run(keep=tmp_path)


def test_without_uv_it_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def nowhere(_name: str) -> None:
        return None
    monkeypatch.setattr(standalone.shutil, "which", nowhere)
    with pytest.raises(standalone.StandaloneError, match="нет uv"):
        standalone.run(keep=tmp_path / "new")


def test_the_tools_run_without_the_checkouts_code(monkeypatch: pytest.MonkeyPatch):
    """`make` exports the checkout's source roots on PYTHONPATH: uv and the venv's Python get none of it."""
    monkeypatch.setenv("PYTHONPATH", "/the/checkout/packages/verso-core/src")
    seen: list[dict[str, object]] = []

    def fake(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(standalone.subprocess, "run", fake)
    standalone._run(["uv", "--version"])  # pyright: ignore[reportPrivateUsage]
    env = seen[0]["env"]
    assert isinstance(env, dict) and "PYTHONPATH" not in env
