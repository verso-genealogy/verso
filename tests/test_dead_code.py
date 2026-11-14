"""DEAD001 must find rot without ever naming live code.

The asymmetry is the whole design: a lint that deletes something live once is
never trusted again, so this one under-reports by construction — it compares
NAMES, and a name that is also an ordinary word is shielded by every unrelated
use of it. These tests pin both halves: what it catches, and what it must not.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from verso.ru.linters import dead_code
from verso.ru.linters.dead_code import find_dead_functions, find_dead_schema_keys
from verso.core.workspace import use

# The toy trees' own package: the scan takes its roots as a parameter, so a toy tree
# reads the same whatever the checkout's layout.
TOY = ("geni",)


class _Tree:
    def __init__(self, case: unittest.TestCase, under: str = "") -> None:
        """`under` puts the repository root below that relative path — e.g.
        ".claude/worktrees/x", which is where every Claude Code worktree lives."""
        tmp = TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / under
        (self.root / "geni").mkdir(parents=True)
        # The packages are found by import: the toy's root goes on sys.path.
        sys.path.insert(0, str(self.root))
        case.addCleanup(sys.path.remove, str(self.root))

    def package(self, name: str, body: str) -> None:
        (self.root / "geni" / name).write_text(body, encoding="utf-8")

    def elsewhere(self, name: str, body: str) -> None:
        (self.root / name).write_text(body, encoding="utf-8")

    def dead(self) -> list[str]:
        return [n for n, _ in find_dead_functions(self.root, TOY)]


class Catches(unittest.TestCase):
    def test_a_function_nothing_calls(self):
        t = _Tree(self)
        t.package("a.py", "def used():\n    pass\n\n\ndef orphan():\n    pass\n")
        t.package("b.py", "from geni.a import used\n\nused()\n")
        self.assertEqual(["orphan"], t.dead())

    def test_a_property_nothing_reads(self):
        t = _Tree(self)
        t.package("a.py", "class P:\n    @property\n    def unread(self):\n        return 1\n")
        self.assertEqual(["unread"], t.dead())


class Spares(unittest.TestCase):
    def test_a_caller_outside_the_package_counts(self):
        """tests/, tools/ and the village DSL files are callers too."""
        t = _Tree(self)
        t.package("a.py", "def only_tested():\n    pass\n")
        t.elsewhere("test_a.py", "from geni.a import only_tested\n\nonly_tested()\n")
        self.assertEqual([], t.dead())

    def test_a_name_reached_by_string_counts(self):
        """getattr, a registry keyed by name, `__all__` — none of them is a call."""
        t = _Tree(self)
        t.package("a.py", "def by_name():\n    pass\n")
        t.package("b.py", 'HANDLERS = {"x": "by_name"}\n')
        self.assertEqual([], t.dead())

    def test_a_cli_entry_point_is_exempt(self):
        """Every CLI is reached as `python -m verso.ru.cli.X`; no module names it."""
        t = _Tree(self)
        t.package("a.py", "def main():\n    return 0\n")
        self.assertEqual([], t.dead())

    def test_a_visitor_method_is_exempt(self):
        """`ast.NodeVisitor` dispatches on the node class name at runtime."""
        t = _Tree(self)
        t.package("a.py", "import ast\n\n\nclass V(ast.NodeVisitor):\n"
                          "    def visit_Call(self, node):\n        pass\n")
        self.assertEqual([], t.dead())

    def test_a_dispatched_handler_is_exempt(self):
        """libcst calls `leave_Call`, http.server calls `do_GET` and
        `log_message` — each by a name built from a string."""
        t = _Tree(self)
        t.package("a.py", "class H:\n"
                          "    def leave_Call(self, original, updated):\n        return updated\n\n"
                          "    def do_GET(self):\n        pass\n\n"
                          "    def log_message(self, format, *args):\n        pass\n")
        self.assertEqual([], t.dead())

    def test_a_dunder_is_exempt(self):
        t = _Tree(self)
        t.package("a.py", "class P:\n    def __repr__(self):\n        return 'p'\n")
        self.assertEqual([], t.dead())

    def test_a_shared_name_shields_its_twin(self):
        """Two functions of one name shield each other, and that is ACCEPTED:
        the check under-reports rather than risk naming live code."""
        t = _Tree(self)
        t.package("a.py", "def helper():\n    pass\n")
        t.package("b.py", "def helper():\n    pass\n")
        t.package("c.py", "from geni.a import helper\n\nhelper()\n")
        self.assertEqual([], t.dead())


class SchemaKeys(unittest.TestCase):
    """DEAD002 — a key the config linter accepts and no code ever reads.

    Worse than dead code: the config looks like it says something, a curator
    writes it in good faith, and nothing happens. Fourteen such lines sat in
    Горюхино's config.
    """

    def _dead(self, tree: _Tree, *keys: str) -> list[str]:
        return [k for k, _ in find_dead_schema_keys(
            tree.root, {"profiles_to_consolidate": set(keys)}, library=TOY)]

    def test_a_key_the_code_reads_is_alive(self):
        t = _Tree(self)
        t.package("a.py", 'def f(entry):\n    return entry.get("keeper")\n')
        self.assertEqual([], self._dead(t, "keeper"))

    def test_a_key_nobody_reads_is_dead(self):
        t = _Tree(self)
        t.package("a.py", 'def f(entry):\n    return entry.get("keeper")\n')
        self.assertEqual(["legacy"], self._dead(t, "keeper", "legacy"))

    def test_writing_a_key_is_not_reading_it(self):
        """The village config STATING a key is the data whose liveness is in
        question — counting it would make every key alive by being written."""
        t = _Tree(self)
        (t.root / "Село").mkdir()
        (t.root / "Село" / "generate_config_names.py").write_text(
            'profiles_to_consolidate = {"x": {"legacy": "value"}}\n', encoding="utf-8")
        self.assertEqual(["legacy"], self._dead(t, "legacy"))

    def test_a_village_config_that_reads_a_key_keeps_it_alive(self):
        """One village's config builds its own move list from `union_names`,
        and the first draft of this check called that key dead."""
        t = _Tree(self)
        (t.root / "Село").mkdir()
        (t.root / "Село" / "generate_config_names.py").write_text(
            'data = {}\nnames = data.get("union_names", [])\n', encoding="utf-8")
        self.assertEqual([], self._dead(t, "union_names"))


class ARepositoryInsideAWorktree(unittest.TestCase):
    """Every Claude Code worktree lives at `<repo>/.claude/worktrees/<name>/`.

    `.claude` is skipped so that a scan of the MAIN checkout does not read the
    whole-repo copies in its worktrees. Matched against the ABSOLUTE path, it
    also skipped every file of a repository that is itself a worktree: nothing
    was scanned, every schema key came out dead, and the dead-function check
    passed there vacuously — it had collected no definitions to judge.
    """
    UNDER = ".claude/worktrees/x"

    def test_a_key_read_by_the_package_is_alive(self):
        t = _Tree(self, under=self.UNDER)
        t.package("a.py", 'def f(entry):\n    return entry.get("keeper")\n')
        self.assertEqual([], [k for k, _ in find_dead_schema_keys(
            t.root, {"profiles_to_consolidate": {"keeper"}}, library=TOY)])

    def test_a_key_nobody_reads_is_still_dead(self):
        """The same fixture reports the unread key — the check is not merely
        silent here, it actually scanned."""
        t = _Tree(self, under=self.UNDER)
        t.package("a.py", 'def f(entry):\n    return entry.get("keeper")\n')
        self.assertEqual(["legacy"], [k for k, _ in find_dead_schema_keys(
            t.root, {"profiles_to_consolidate": {"keeper", "legacy"}}, library=TOY)])

    def test_dead_functions_are_found_not_vacuously_absent(self):
        t = _Tree(self, under=self.UNDER)
        t.package("a.py", "def used():\n    pass\n\n\ndef orphan():\n    pass\n")
        t.package("b.py", "from geni.a import used\n\nused()\n")
        self.assertEqual(["orphan"], t.dead())

    def test_the_verso_packages_are_checked_like_geni(self):
        """Verso moved out of geni/ before 0.1.0; its functions are the repo's as much as the library's."""
        t = _Tree(self)
        for top in ("verso_app", "verso_app_dsl"):  # verso-rename: keep — the toy's own directories
            (t.root / top).mkdir()
            (t.root / top / "a.py").write_text(f"def {top}_orphan():\n    pass\n", encoding="utf-8")
        found = find_dead_functions(t.root, (*TOY, "verso_app", "verso_app_dsl"))  # verso-rename: keep
        self.assertEqual(["verso_app_orphan", "verso_app_dsl_orphan"], [n for n, _ in found])

    def test_a_claude_directory_inside_the_repo_is_still_skipped(self):
        """From the main checkout, `.claude/worktrees/*` are whole copies of the
        repo; counting them as callers would shield every dead function."""
        t = _Tree(self)
        t.package("a.py", "def orphan():\n    pass\n")
        copy = t.root / ".claude" / "worktrees" / "y"
        copy.mkdir(parents=True)
        (copy / "caller.py").write_text("from geni.a import orphan\n\norphan()\n",
                                        encoding="utf-8")
        self.assertEqual(["orphan"], t.dead())


class TheDefaultRoot(unittest.TestCase):
    def test_the_default_root_is_the_workspace(self):
        """With no root given, the scan reads the workspace's tree — not the
        checkout this module happens to be imported from."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "verso.toml").write_text("schema = 1\n", encoding="utf-8")
            (root / "geni").mkdir()
            (root / "geni" / "lonely.py").write_text("def lonely_helper():\n    pass\n", encoding="utf-8")
            sys.path.insert(0, str(root))
            try:
                with use(root):
                    self.assertEqual(["lonely_helper"], [n for n, _ in find_dead_functions(packages=TOY)])
            finally:
                sys.path.remove(str(root))


def test_the_scan_reads_the_packages_by_name():
    """The roots are packages, found where they are imported from, not directories."""
    assert dead_code.PACKAGES == ("verso.core", "verso.ru", "verso.app", "verso.app_dsl")
    assert dead_code.LIBRARY == dead_code.PACKAGES[:2]


def test_dead_code_finds_the_packages_by_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A package outside the root — a wheel's, another checkout's — is read where it is imported from;
    its sites are named from its import root."""
    site = tmp_path / "site"
    (site / "deadtoy").mkdir(parents=True)
    (site / "deadtoy" / "__init__.py").write_text("", encoding="utf-8")
    (site / "deadtoy" / "a.py").write_text("def orphan():\n    pass\n\n\ndef used():\n    pass\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "caller.py").write_text("from deadtoy.a import used\n\nused()\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(site))
    assert find_dead_functions(root, ("deadtoy",)) == [("orphan", "deadtoy/a.py:1")]


def test_a_clean_report_names_the_places_it_read():
    assert dead_code.format_report([]) == ("DEAD001: OK — every function in verso.core, verso.ru, "
                                           "verso.app, verso.app_dsl is referenced somewhere.")
