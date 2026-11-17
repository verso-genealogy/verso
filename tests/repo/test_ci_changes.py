"""CI's «What changed»: a pull request of prose alone skips the suite, anything a test reads does not."""
from __future__ import annotations

import pytest

from tools.ci_changes import touches_code


@pytest.mark.parametrize("paths", [
    ["README.md", "README.ru.md"],
    ["CHANGELOG.md"],
    ["AGENTS.md", "CONTRIBUTING.ru.md"],
    ["docs/dsl.md", "docs/dsl.ru.md"],
    ["ide/vscode-dsllint/README.md"],
])
def test_prose_alone_is_no_code(paths):
    assert not touches_code(paths)


@pytest.mark.parametrize("paths", [
    ["README.md", "packages/verso-ru/src/verso/ru/dsl/__init__.py"],
    ["plugins/verso-reading/agents/scan-reader.md"],
    ["plugins/verso-reading/README.md"],
    ["packages/verso-ru/src/verso/ru/reading/prompts/births.md"],
    ["packages/verso-core/README.md"],
    ["examples/README.md"],
    ["docs/reference/commands.md"],
    ["docs/scans.md"],
    ["docs/scans.ru.md"],
    ["tests/fixtures/notes.md"],
    [".github/workflows/ci.yml"],
    ["LICENSE"],
    [],
])
def test_anything_a_test_reads_is_code(paths):
    assert touches_code(paths)


def test_blank_lines_of_the_diff_are_ignored():
    assert not touches_code(["README.md\n", "\n"])
