"""tests/codepaths.py — the tests of the library and the App find the code by importing it,
never by the repo's paths: the same test passes in a parent repository's lib/, at this repository's root, after
0.1.0's run, and from an installed wheel. A walk of the code that finds nothing fails."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import verso.core
from tests import codepaths
from tests.codepaths import PROJECT, child_env, code_files, import_roots, module_name, package_dir


def test_project_holds_these_tests():
    assert (PROJECT / "tests" / Path(__file__).name).is_file()


def test_package_dir_is_where_verso_core_was_imported_from():
    assert package_dir("verso.core") == Path(verso.core.__file__).resolve().parent


def test_package_dir_of_nothing_is_refused():
    with pytest.raises(LookupError, match=r"verso\.nonexistent: пакет не найден"):
        package_dir("verso.nonexistent")


def test_code_files_refuses_an_empty_walk():
    with pytest.raises(LookupError, match="ни одного модуля — код не там, где его ищут"):
        code_files("verso.nonexistent")


def test_code_files_walks_the_package():
    files = code_files("verso.core")
    assert Path(verso.core.__file__).resolve() in files
    assert files == sorted(files)
    assert not any("__pycache__" in path.parts for path in files)


def test_module_name_of_a_core_file():
    assert module_name(package_dir("verso.core") / "workspace.py") == "verso.core.workspace"
    assert module_name(package_dir("verso.core") / "__init__.py") == "verso.core"


def test_import_roots_hold_the_packages():
    roots = import_roots("verso.core", "verso.ru")
    assert any((root / "verso" / "core").is_dir() for root in roots)
    assert any((root / "verso" / "ru").is_dir() for root in roots)
    assert len(roots) == len(set(roots))


def test_a_child_imports_the_same_verso_as_the_parent(tmp_path):
    code = "import verso.core, tests.codepaths; print(verso.core.__file__); print(tests.codepaths.__file__)"
    done = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=child_env(), capture_output=True,
                          text=True, check=True)
    core, helper = done.stdout.splitlines()
    assert Path(core).resolve() == Path(verso.core.__file__).resolve()
    assert Path(helper).resolve() == Path(codepaths.__file__).resolve()


def test_child_env_names_the_workspace_and_takes_extras():
    env = child_env(PYTHONHASHSEED="1")
    assert env["PYTHONHASHSEED"] == "1"
    assert env["VERSO_WORKSPACE"]
    assert env["PYTHONPATH"].split(os.pathsep)[-1] == str(PROJECT)


def test_imported_names_what_a_file_imports_at_any_depth(tmp_path):
    from tests.codepaths import imported
    path = tmp_path / "m.py"
    path.write_text("import os.path\nfrom verso import app_dsl\nfrom .x import y\n\ndef f():\n"
                    "    from verso.ru.dsl import source as s\n", encoding="utf-8")
    assert imported(path) == {"os.path", "verso", "verso.app_dsl", "verso.ru.dsl", "verso.ru.dsl.source"}
