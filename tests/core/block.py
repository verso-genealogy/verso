"""The core alone: a pytest plugin — and a module a child may import — that blocks the
plugin, the App and the corpus's package, so tests/core proves the core works
without them, at work as well as at import (`make test-core`: `python -m pytest -p
tests.core.block tests/core`; `-m` puts the checkout on sys.path, so `tests.core` imports
before any conftest).

`install()` puts a finder first in `sys.meta_path` that refuses the names below; as a pytest
plugin (`-p`) it installs at configure. Importing the module installs nothing: the whole
suite imports every file of tests/ (`--doctest-modules`).
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from types import ModuleType

BLOCKED = ("verso.ru", "verso.app", "verso.app_dsl", "corpus")


class _Blocker:
    def find_spec(self, name: str, path: Sequence[str] | None = None,  # noqa: ARG002 — a finder's signature
                  target: ModuleType | None = None) -> ModuleSpec | None:  # noqa: ARG002
        for blocked in BLOCKED:
            if name == blocked or name.startswith(blocked + "."):
                raise ImportError(f"ядро без плагина: {blocked} заблокирован (tests/core/block.py)")
        return None


def install() -> None:
    """Block the names below — refused when one is imported already (a conftest's import):
    a finder never sees a module `sys.modules` holds, so it would block nothing."""
    early = sorted(name for name in sys.modules for blocked in BLOCKED
                   if name == blocked or name.startswith(blocked + "."))
    if early:
        raise RuntimeError(f"ядро без плагина: {early[0]} уже импортирован — блокировщик опоздал (tests/core/block.py)")
    if not any(isinstance(finder, _Blocker) for finder in sys.meta_path):
        sys.meta_path.insert(0, _Blocker())


def pytest_configure() -> None:
    install()
