"""The library's tests' corpus: tests/fixtures/mini/.

A copy of Verso's fixture records (tests/fixtures/verso/root — invented people under the synthetic
corpus's places, Маниловка 1858–1900), which the App's `tools/fixture_copies.py` keeps byte for byte
equal: the library's tests read it without the App, so they pass here alone. Its names are the base the library
ships under a layer of its own (`names/`). Every test works on a copy, as Verso's do (`tests/verso_fixture.py`,
whose functions these are).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from verso.core import workspace as _workspace
from verso.core.pipeline.load import village_dirs

MINI = Path(__file__).resolve().parent / "fixtures" / "mini"

# An interpreter's cache is not part of the corpus: a fixture module imported in
# place (`--doctest-modules`, an editor) must not reach a test's copy.
_NOT_FIXTURE = shutil.ignore_patterns("__pycache__", "*.pyc")


def root(tmp: Path, *files: str) -> Path:
    """`tmp/root` holding `files` of the mini corpus (paths under its root, such as
    "Маниловка/1900/manilovka_births_1900.py") and every village's scans.toml; with no file
    named, the whole corpus."""
    target = tmp / "root"
    if not files:
        shutil.copytree(MINI / "root", target, ignore=_NOT_FIXTURE)
        return target
    target.mkdir(parents=True)
    for toml in (MINI / "root").glob("*/scans.toml"):
        add(target, toml.relative_to(MINI / "root").as_posix())
    for rel in files:
        add(target, rel)
    return target


def add(root_: Path, rel: str) -> Path:
    """One more file of the mini corpus into a scratch root; the copy's path."""
    copy = root_ / rel
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(MINI / "root" / rel, copy)
    return copy


def workspace(tmp: Path, root_: Path) -> Path:
    """`root_` made a workspace: its verso.toml names the villages in it, a copy of the mini
    corpus's names layer in `tmp` (`tmp/names`) over the base and the corpus data the tests' workspace reads."""
    names = tmp / "names"
    shutil.copytree(MINI / "names", names, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    villages = [d.name for d in village_dirs(root_)]
    corpus = _workspace.current().corpus_dir
    lines = ["# The library tests' workspace (tests/village_fixture.py).", "schema = 6",
             f"villages = {json.dumps(villages, ensure_ascii=False)}", 'plugins = ["ru"]', "", "[names]",
             f"layers = [{json.dumps(str(names.resolve()), ensure_ascii=False)}]"]
    if corpus is not None:
        lines += ["", "[corpus]", f"dir = {json.dumps(str(corpus), ensure_ascii=False)}"]
    (root_ / _workspace.CONFIG).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root_
