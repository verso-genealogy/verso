"""The tests run in a workspace of their own (a `corpus` test runs in the checkout's:
tests/test_conftest_workspace_corpus.py)."""
from __future__ import annotations

import os
from pathlib import Path

from verso.core.workspace import ENV, current, pin

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "workspace"


def test_the_tests_workspace_is_the_fixture_unless_swapped(tests_workspace: Path) -> None:
    if "VERSO_TEST_WORKSPACE" not in os.environ:
        assert tests_workspace == FIXTURE.resolve()


def test_an_unmarked_test_sees_the_tests_workspace(tests_workspace: Path) -> None:
    assert current().root == tests_workspace
    assert os.environ[ENV] == str(tests_workspace)


def test_back_on_the_tests_workspace_after_a_corpus_test(tests_workspace: Path) -> None:
    """After whatever ran before it, a corpus test too: the switch goes both ways."""
    assert current().root == tests_workspace


def test_a_test_may_leave_a_broken_environment_behind() -> None:
    """Sets the variable to nowhere and forgets the workspace — the next test
    must not be the one to pay for it."""
    os.environ[ENV] = "/nonexistent-workspace"
    pin(None)


def test_the_next_test_still_finds_its_workspace(tests_workspace: Path) -> None:
    assert current().root == tests_workspace
