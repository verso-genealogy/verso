"""The core alone: every module of verso/core imports with the plugin's — and the App's,
the alias's, the corpus's — import blocked (tests/core/block.py). `make test-core` runs all
of tests/core so; these tests check the blocker and the imports from a child of their own."""
from __future__ import annotations

import subprocess
import sys

from tests.codepaths import PROJECT, code_files, module_name, pythonpath


def _child(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True,
                          timeout=120, check=False, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()})


def _core_modules() -> list[str]:
    return [module_name(path) for path in code_files("verso.core")]


def test_every_core_module_imports_with_the_plugin_blocked():
    modules = _core_modules()
    assert len(modules) >= 33
    done = _child("import importlib, sys\nimport tests.core.block\ntests.core.block.install()\n"
                  f"for name in {modules!r}:\n    importlib.import_module(name)\n"
                  "print(sorted(m for m in sys.modules if m.split('.')[0] == 'corpus' "
                  "or m.startswith(('verso.ru', 'verso.app'))))")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_the_blocker_blocks():
    done = _child("import tests.core.block\ntests.core.block.install()\nimport verso.core.plugins\n"
                  "for name in ('verso.ru.naming', 'verso.app.server', 'verso.app_dsl.cli', 'corpus'):\n"
                  "    try:\n        __import__(name)\n    except ImportError as e:\n        print(e)\n"
                  "    else:\n        print('imported', name)\n")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        f"ядро без плагина: {name} заблокирован (tests/core/block.py)"
        for name in ("verso.ru", "verso.app", "verso.app_dsl", "corpus")]


def test_importing_the_blocker_blocks_nothing():
    """The suite imports every file of tests/ (`--doctest-modules`): the module alone installs nothing."""
    done = _child("import sys, tests.core.block\nimport verso.ru.plugin\nprint('ok')")
    assert (done.returncode, done.stdout) == (0, "ok\n"), done.stderr


def test_the_blocker_refuses_to_install_too_late():
    """A module of the plugin already imported (a conftest's import) is out of a finder's
    reach: installing then would block nothing, so it is refused."""
    done = _child("import verso.ru.plugin\nimport tests.core.block\ntests.core.block.install()\n")
    assert done.returncode == 1
    assert "ядро без плагина: verso.ru уже импортирован — блокировщик опоздал (tests/core/block.py)" in done.stderr


def test_the_core_has_no_gender():
    """Sex is the Russian books': the core never asked for it, and the toy has its own."""
    import importlib.util
    assert importlib.util.find_spec("verso.core.gender") is None
