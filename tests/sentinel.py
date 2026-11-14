"""The sentinel: in a standalone run (`make standalone`, tools/standalone.py) the project's
tests run from a copy outside any parent repository, and any read of the checkout is refused — a test that
reads `../corpus`, a corpus's names table or the Makefile fails with the path it read.

`install(*forbidden)` adds an audit hook (`sys.addaudithook`, PEP 578) on the events `open`,
`os.listdir` and `os.scandir`: a path (str, bytes or PathLike; a relative one from the working
directory) that resolves inside one of `forbidden` raises PermissionError «читает вне проекта:
<путь>»; a file descriptor passes. A refusal is an OSError, which code that reads may catch: each
is also appended to the file VERSO_SENTINEL_LOG names, and `make standalone` fails a run whose log
is not empty. `install_from_env()` takes the checkouts from VERSO_SENTINEL (a path list) — the
conftest calls it first thing, and so does a `.pth` standalone puts into its venv, for every
Python a test starts. An audit hook cannot be removed: a test of it runs in a child process. One
hook a process, whichever copy of this module installs it first.

What it does not see: `os.stat`, `os.path.exists`, `Path.exists`/`is_file` raise no audit event,
so a test may still ask whether a file of the checkout EXISTS — it cannot read or list one.

lib/tests/sentinel.py and app/tests/sentinel.py are one file (`make fixture-copies`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENV, LOG_ENV = "VERSO_SENTINEL", "VERSO_SENTINEL_LOG"
_EVENTS = frozenset({"open", "os.listdir", "os.scandir"})
_MARK = "_verso_sentinel"            # on sys: the process's hook, whichever module copy installed it


def _checked(forbidden: tuple[Path, ...], path: object) -> None:
    if isinstance(path, int):
        return                                            # a descriptor: its path was checked when opened
    try:
        raw = "." if path is None else os.fsdecode(os.fspath(path))  # type: ignore[arg-type]
    except TypeError:
        return
    resolved = Path(os.getcwd(), raw).resolve()
    if any(resolved == root or root in resolved.parents for root in forbidden):
        log = os.environ.get(LOG_ENV)
        if log:
            with open(log, "a", encoding="utf-8") as out:
                out.write(f"{resolved}\n")
        raise PermissionError(f"читает вне проекта: {resolved}")


def install(*forbidden: Path) -> None:
    """Refuse every open or listing inside `forbidden` from now on, in this process."""
    if getattr(sys, _MARK, None) is not None or not forbidden:
        return
    roots = tuple(root.resolve() for root in forbidden)
    setattr(sys, _MARK, roots)

    def hook(event: str, args: tuple[object, ...]) -> None:
        if event in _EVENTS and args:
            _checked(roots, args[0])

    sys.addaudithook(hook)


def install_from_env() -> None:
    """`install` the checkouts VERSO_SENTINEL names (a path list); nothing when it is not set."""
    named = os.environ.get(ENV)
    if named:
        install(*(Path(p) for p in named.split(os.pathsep) if p))
