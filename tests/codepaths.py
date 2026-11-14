"""Where the code is, for the tests of the library and the App — by importing it, never by
the repo's paths.

The same test passes in a parent repository's lib/, at this repository's root, and from an installed
wheel: it asks where the package it walks was imported from, and starts a child that imports
the same one. A walk that finds nothing fails — a guard over an empty set guards nothing.
Standard library only (the App alone imports this too); nothing is looked up at import but
where this file is.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path

#: The tests' project: the directory above tests/ — the repo's root before 0.1.0, lib/ or app/ after it.
PROJECT = Path(__file__).resolve().parent.parent
#: Every package of verso, the library's first.
VERSO = ("verso.core", "verso.ru", "verso.app", "verso.app_dsl")


def package_dir(name: str) -> Path:
    """The directory of a package, where it is imported from."""
    try:
        spec = importlib.util.find_spec(name)
    except ImportError:                                     # a parent missing, or blocked (tests/core/block.py)
        spec = None
    if spec is None or not spec.submodule_search_locations:
        raise LookupError(f"{name}: пакет не найден")
    return Path(next(iter(spec.submodule_search_locations))).resolve()


def code_files(*packages: str) -> list[Path]:
    """Every .py of the packages, sorted; a package with none is refused."""
    found: list[Path] = []
    for package in packages:
        try:
            files = [path for path in package_dir(package).rglob("*.py")
                     if not {"__pycache__", "node_modules"} & set(path.parts)]
        except LookupError:
            files = []
        if not files:
            raise LookupError(f"{package}: ни одного модуля — код не там, где его ищут")
        found.extend(files)
    return sorted(found)


def import_roots(*packages: str) -> tuple[Path, ...]:
    """The directories the packages are imported from (each package's directory, climbed by its
    dotted depth), in order, each once; a package not found is left out."""
    roots: list[Path] = []
    for package in packages:
        try:
            directory = package_dir(package)
        except LookupError:
            continue
        root = directory.parents[len(package.split(".")) - 1]
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def module_name(path: Path) -> str:
    """The dotted name of a file under one of the import roots (the deepest that holds it), or of the
    tests' project."""
    path = path.resolve()
    holding = [root for root in (*import_roots(*VERSO), PROJECT) if path.is_relative_to(root)]
    if not holding:
        raise LookupError(f"{path}: не под корнем импорта")
    parts = path.relative_to(max(holding, key=lambda root: len(root.parts))).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def pythonpath() -> str:
    """`PYTHONPATH` for a child importing what this process does: the roots of verso, then the
    tests' project (for `tests.*`)."""
    return os.pathsep.join(str(root) for root in (*import_roots(*VERSO), PROJECT))


def child_env(**extra: str) -> dict[str, str]:
    """The environment of a Python child of a test: this one's, the workspace named
    (`verso.core.workspace.child_env`, where the library is installed), `pythonpath()`, `extra`."""
    try:
        from verso.core import workspace
    except ImportError:                                     # the App alone: no library, no workspace
        base = dict(os.environ)
    else:
        base = workspace.child_env()
    return {**base, "PYTHONPATH": pythonpath(), **extra}


def imported(path: Path) -> set[str]:
    """Every module a file imports, at any depth, relative imports aside: `from a import b` is a
    and a.b — a guard «this module imports nothing of X» reads it."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.update({node.module, *(f"{node.module}.{alias.name}" for alias in node.names)})
    return found
