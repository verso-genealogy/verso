"""`terraform fmt` over a generated tree, the files split among a few processes at once.

`terraform fmt` formats one file after another in a single thread: a village's tree of 30 MB took it ten seconds, two
thirds of the whole translation, and `verso stale` paid it twice. It takes files as well as a directory, and the result of
a file does not depend on the others, so the files are dealt into groups of about equal bytes and each group is one
`terraform fmt` — the same bytes, in a fifth of the time.

What it formats is what `terraform fmt DIR` would: the files of the extensions it reads, skipping the names it ignores
(a leading `.` or `~`, a trailing `~`, `#…#`, as `configs.IsIgnoredFile`) — in subdirectories too with `recursive`.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from verso.core.tools import find_tool, tool

__all__ = ["SUFFIXES", "groups", "targets", "terraform_fmt"]

#: The files `terraform fmt` reads in a directory.
SUFFIXES: tuple[str, ...] = (".tf", ".tfvars", ".tftest.hcl", ".tfmock.hcl")

_MAX_JOBS = 8
#: At most this many files on one command line: a village's tree has a few hundred.
_MAX_FILES = 200


def _ignored(name: str) -> bool:
    return name.startswith((".", "~")) or name.endswith("~") or (len(name) > 1 and name[0] == name[-1] == "#")


def targets(directory: Path, *, recursive: bool = False) -> list[Path]:
    """The files `terraform fmt directory` (with `-recursive`: and its subdirectories) formats, in name order."""
    found: list[Path] = []
    for entry in sorted(directory.iterdir()):
        if _ignored(entry.name):
            continue
        if entry.is_dir():
            if recursive:
                found.extend(targets(entry, recursive=True))
        elif entry.name.endswith(SUFFIXES):
            found.append(entry)
    return found


def groups(files: Sequence[Path], jobs: int) -> list[list[Path]]:
    """`files` dealt into at most `jobs` groups of about equal bytes (the biggest first, each to the lightest group), none
    longer than `_MAX_FILES`; no group empty."""
    sized = sorted(((f.stat().st_size, f) for f in files), key=lambda pair: (-pair[0], str(pair[1])))
    count = max(1, min(jobs, len(sized)), -(-len(sized) // _MAX_FILES))
    out: list[list[Path]] = [[] for _ in range(count)]
    weight = [0] * count
    for size, f in sized:
        open_ = [i for i in range(count) if len(out[i]) < _MAX_FILES]
        i = min(open_, key=lambda k: (weight[k], k))
        out[i].append(f)
        weight[i] += size
    return [g for g in out if g]


def terraform_fmt(directory: Path, *, recursive: bool = False, check: bool = False, jobs: int | None = None) -> None:
    """`terraform fmt` on what `directory` holds, the files in parallel groups.

    `check` is the caller who needs it done: terraform must be found (`ToolNotFound`) and a failing group raises
    `CalledProcessError`. Without it the format is best-effort: no terraform, or one that fails, leaves the files as written.
    """
    tf = tool("terraform") if check else find_tool("terraform")
    if tf is None:
        return
    files = targets(directory, recursive=recursive)
    if not files:
        return
    dealt = groups(files, jobs or min(os.cpu_count() or 1, _MAX_JOBS))

    def run(group: list[Path]) -> None:
        try:
            subprocess.run([tf, "fmt", "-list=false", *map(str, group)], check=check, capture_output=True, text=True)
        except OSError:
            if check:
                raise

    with ThreadPoolExecutor(len(dealt)) as pool:
        for done in [pool.submit(run, g) for g in dealt]:
            done.result()
