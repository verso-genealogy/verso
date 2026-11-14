"""The sentinel (tests/sentinel.py): an audit hook refusing any open or listing inside the checkout
in a standalone run. A hook cannot be removed, so each test installs it in a child process."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
# A child starts clean of the run's own sentinel: under `make standalone` the venv's .pth would
# install it first (one hook a process), and its refusals would land in the run's log.
_CLEAN = {k: v for k, v in os.environ.items() if k not in ("VERSO_SENTINEL", "VERSO_SENTINEL_LOG")}


def _child(tmp_path: Path, body: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """`body` run after the sentinel guards tmp_path/repo; the child imports this project's tests.sentinel."""
    head = textwrap.dedent(f"""\
        import os, sys, sysconfig
        from pathlib import Path
        from tests import sentinel
        repo = Path({str(tmp_path / "repo")!r})
        sentinel.install(repo)
        sentinel.install(repo.parent)
    """)
    return subprocess.run([sys.executable, "-c", head + textwrap.dedent(body)], cwd=PROJECT, capture_output=True,
                          text=True, check=False, env={**_CLEAN, **(env or {})})


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "x").write_text("x", encoding="utf-8")
    return (tmp_path / "repo").resolve()


def test_the_sentinel_refuses_a_read_in_the_checkout(tmp_path: Path):
    repo = _repo(tmp_path)
    done = _child(tmp_path, "open(repo / 'x').read()")
    assert done.returncode == 1
    assert f"PermissionError: читает вне проекта: {repo / 'x'}" in done.stderr


def test_the_sentinel_lets_tmp_and_site_packages_through(tmp_path: Path):
    """Outside the checkout — beside it, the venv's site-packages, the stdlib — and a second install
    (here of repo's parent) changes nothing."""
    _repo(tmp_path)
    (tmp_path / "beside").write_text("y", encoding="utf-8")
    done = _child(tmp_path, """\
        print(open(repo.parent / 'beside').read())
        print(bool(os.listdir(sysconfig.get_paths()['purelib'])))
        import json, email.mime.text
        print('ok')
    """)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["y", "True", "ok"]


def test_the_sentinel_resolves_a_relative_path(tmp_path: Path):
    repo = _repo(tmp_path)
    done = _child(tmp_path, "os.chdir(repo)\nopen('x')")
    assert f"PermissionError: читает вне проекта: {repo / 'x'}" in done.stderr


def test_the_sentinel_refuses_listing_the_checkout(tmp_path: Path):
    repo = _repo(tmp_path)
    for listing in ("os.listdir(repo)", "list(os.scandir(repo))", "os.listdir(str(repo).encode())"):
        done = _child(tmp_path, listing)
        assert f"PermissionError: читает вне проекта: {repo}" in done.stderr, listing


def test_a_swallowed_refusal_is_still_logged(tmp_path: Path):
    """A refusal is an OSError, and code that reads may catch one: every refusal is written to
    VERSO_SENTINEL_LOG as well, which `make standalone` reads after the run."""
    repo = _repo(tmp_path)
    log = tmp_path / "sentinel.log"
    done = _child(tmp_path, """\
        try:
            open(repo / 'x')
        except OSError:
            print('swallowed')
    """, env={"VERSO_SENTINEL_LOG": str(log)})
    assert done.stdout.strip() == "swallowed", done.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [str(repo / "x")]


def test_the_variable_may_name_several_checkouts(tmp_path: Path):
    """`VERSO_SENTINEL` is a path list: a worktree and the main checkout that holds it."""
    one, two = _repo(tmp_path), tmp_path / "two"
    two.mkdir()
    (two / "y").write_text("y", encoding="utf-8")
    code = ("from tests import sentinel\nsentinel.install_from_env()\n"
            "import sys\nfor p in sys.argv[1:]:\n    try:\n        open(p)\n    except PermissionError as e:\n"
            "        print(e)\n")
    done = subprocess.run([sys.executable, "-c", code, str(one / "x"), str(two.resolve() / "y")], cwd=PROJECT,
                          capture_output=True, text=True, check=False,
                          env={**_CLEAN, "VERSO_SENTINEL": os.pathsep.join(map(str, (one, two)))})
    assert done.stdout.splitlines() == [f"читает вне проекта: {one / 'x'}", f"читает вне проекта: {two.resolve() / 'y'}"]
