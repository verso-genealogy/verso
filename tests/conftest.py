"""The library's tests: `cd lib && python -m pytest tests`.

They run in a workspace of their own — tests/fixtures/workspace: the names base the library ships under
a layer of invented names (`names-layer`), no villages, and the synthetic corpus (
tests/fixtures/workspace/corpus, invented places, owners, statuses and events) — set before any test module is
imported (several build a Person at module level) and inherited by every child a test starts.
`VERSO_TEST_WORKSPACE` swaps it. Nothing here
reads a parent repository: `make standalone` runs these tests from `git archive HEAD:lib`.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

_PROJECT = Path(__file__).resolve().parent.parent
FIXTURE_WORKSPACE = _PROJECT / "tests" / "fixtures" / "workspace"
# `import corpus` is the synthetic corpus (the DSL texts import corpus.statuses), and `tests.*` this
# project's: both before whatever the venv holds.
for _path in (FIXTURE_WORKSPACE, _PROJECT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# The sentinel (`make standalone`: VERSO_SENTINEL names the checkout): from here on no test reads
# a parent repository — installed before the library is imported.
from tests import sentinel  # noqa: E402 — after the paths above

sentinel.install_from_env()

from verso.core import workspace  # noqa: E402 — after the sentinel

_TESTS = Path(os.environ.get("VERSO_TEST_WORKSPACE") or FIXTURE_WORKSPACE).resolve()
os.environ[workspace.ENV] = str(_TESTS)
# The tests speak Russian, whatever a test's own workspace says (tests/core: English).
os.environ["VERSO_LANG"] = "ru"


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:  # noqa: ARG001 — the hook's signature
    """Each test starts in the tests' workspace, whatever the test before it left behind (a variable
    pointing nowhere, a workspace pinned)."""
    os.environ[workspace.ENV] = str(_TESTS)
    os.environ["VERSO_LANG"] = "ru"
    if workspace.current().root != _TESTS:
        workspace.pin(_TESTS)


@pytest.fixture
def tests_workspace() -> Path:
    """The workspace the tests run in: the fixture, or VERSO_TEST_WORKSPACE."""
    return _TESTS


@pytest.fixture
def base_workspace(tmp_path: Path) -> Path:
    """A workspace of schema 6 with no layer: the names base the library ships, alone."""
    root = tmp_path / "base-only"
    root.mkdir()
    (root / "verso.toml").write_text('schema = 6\nvillages = []\nplugins = ["ru"]\n', encoding="utf-8")
    return root


#: A workspace of schema 4 whose names are the old tables (names.csv and its ignore lists) — invented names, for the
#: tests of the old format; the tests' own workspace has the base and a layer.
LEGACY_NAMES = _PROJECT / "tests" / "fixtures" / "legacy-names"


@pytest.fixture
def legacy_workspace(tmp_path: Path) -> Path:
    """A copy of `LEGACY_NAMES` in `tmp_path`, which a test may write."""
    root = tmp_path / "legacy"
    shutil.copytree(LEGACY_NAMES, root)
    return root


# tests/fixtures/ holds data, not tests (the mini corpus's DSL, the copy of the corpus):
# `--doctest-modules` would import it, and write its __pycache__ into the fixture.
collect_ignore = ["fixtures"]
