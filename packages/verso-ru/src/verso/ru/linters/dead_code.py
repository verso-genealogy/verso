#!/usr/bin/env python3
"""Things declared and never read.

DEAD001 — a function in `verso/` (the library, the App, the adapter) that nothing anywhere references.
DEAD002 — a key the consolidation-config schema accepts and no code reads.

The repo checks its DATA for rot thoroughly: `stale_stubs` (CST001),
`stale_moved` (SMB001), `strip_dead_overrides` (ROV001), `stale_claims` and
RIG001 each hunt a config entry that no longer addresses anything. Its Python
had almost nothing — ruff catches unused imports and locals, and pyright's
`reportUnusedFunction` is off on purpose (`pyrightconfig.json`: it counts
same-file use only, so every cross-module helper would false-positive).

So this is the same idea one level up, and it is deliberately NAME-based rather
than resolution-based. Every definition in the library (`verso/core/`, `verso/ru/`)
and in Verso's two packages is collected; every name loaded, attribute accessed or
string literal written ANYWHERE in the repo — `verso/`, `tests/`, `tools/`, the
per-village DSL and config files — goes into one flat set of used names. A
definition whose name never appears there is reported.

**That under-reports, and it must.** Two functions sharing a name shield each
other, and a short name that is also an ordinary word (`at`, `child`, `key`)
is shielded by every unrelated use of it. The alternative — resolving each call
to its definition — would report a function as dead because an import was
spelled differently, and a lint that deletes live code once is never trusted
again. Missing some rot is the cheap failure; naming live code is not.

Like VSR001, this gates at zero rather than carrying a baseline: the seven
findings it had on its first run were removed in the commit that added it.

Run:
    python3 -m verso.ru.linters.dead_code
    verso dead-code
"""
from __future__ import annotations

import argparse
import ast
import collections
import importlib
import importlib.util
import sys
from pathlib import Path

from verso.core import workspace
from verso.ru.messages import t

# The code: the library, and Verso since 0.1.0 moved it out of geni/ — packages, found where they
# are imported from (a src/ of lib/ or app/, a site-packages), never a directory of the
# root. The scan takes them as a parameter, so a toy tree names its own.
PACKAGES = ("verso.core", "verso.ru", "verso.app", "verso.app_dsl")
LIBRARY = PACKAGES[:2]

#: Directories with no source of ours in them. NOT plain `terraform`: the
#: village `terraform/` trees hold `.tf` and no Python, while `verso/core/targets/geni/`
#: is a package — skipping the name outright hid `generator.py` and
#: `profile.py`, which is 7000 lines of the very code this check is for.
SKIP_PARTS = {".venv", "__pycache__", ".git", "node_modules", ".claude",
              ".terraform"}

#: Names whose caller is not a Python reference at all.
#:
#: `main` — every CLI is reached as `python -m verso.ru.cli.X`, from a Makefile
#: target or by hand, and no module names it.
#: `visit_*` / `generic_visit` — `ast.NodeVisitor` dispatches on the node class
#: name at runtime, so a visitor method is called by a string this scan cannot
#: see. The same is true of any dispatcher keyed on a method name: libcst's
#: `leave_*` (the other half of its visitor), and `http.server`'s `do_<METHOD>`
#: and `log_message`, which `BaseHTTPRequestHandler` calls by name.
EXEMPT_NAMES = {"main", "generic_visit", "log_message"}
EXEMPT_PREFIXES = ("visit_", "leave_", "do_", "test_", "__")


def _python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        # RELATIVE to the directory being scanned. Every Claude Code worktree
        # lives at `<repo>/.claude/worktrees/<name>/`, so matched against the
        # absolute path `.claude` skipped every file of such a checkout: DEAD002
        # reported all twelve schema keys dead and DEAD001 passed vacuously,
        # with no definitions collected. Relative, `.claude` is still skipped
        # where it matters — the main checkout's own worktree copies.
        if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        yield path


def collect_definitions(package: Path, root: Path | None = None) -> dict[str, list[str]]:
    """{name: [file:line, ...]} for every function defined under `package`.

    `root` is what the reported paths are relative to — the repository when run
    for real, the fixture's own directory in a test.
    """
    root = root or workspace.current().root
    found: dict[str, list[str]] = collections.defaultdict(list)
    for path in _python_files(package):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rel = path.relative_to(root)
                found[node.name].append(f"{rel}:{node.lineno}")
    return found


def collect_references(root: Path) -> set[str]:
    """Every name the repo could be calling something by.

    Attribute access covers methods and properties; a string constant covers
    `getattr`, a registry keyed by name, and `__all__`.
    """
    used: set[str] = set()
    for path in _python_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                used.add(node.value)
            elif isinstance(node, ast.ImportFrom):
                used.update(a.name for a in node.names)
    return used


def _located(package: str) -> tuple[Path, Path] | None:
    """A package's directory and the directory it is imported from, or None if it is not there."""
    try:
        spec = importlib.util.find_spec(package)
    except ImportError:
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    directory = Path(next(iter(spec.submodule_search_locations))).resolve()
    return directory, directory.parents[package.count(".")]


def _exempt(name: str) -> bool:
    return name in EXEMPT_NAMES or name.startswith(EXEMPT_PREFIXES)


def find_dead_functions(root: Path | None = None,
                        packages: tuple[str, ...] = PACKAGES) -> list[tuple[str, str]]:
    """[(name, first definition site)] for every unreferenced function of `packages` (dotted,
    found by import; a site is named from the package's import root), the references read
    under `root` — by default the workspace's tree."""
    root = root or workspace.current().root
    importlib.invalidate_caches()           # a tree written since this process last looked
    definitions: dict[str, list[str]] = collections.defaultdict(list)
    for package in packages:
        located = _located(package)
        if located is not None:
            for name, sites in collect_definitions(*located).items():
                definitions[name] += sites
    used = collect_references(root)
    dead = [(name, sites[0]) for name, sites in definitions.items()
            if not _exempt(name) and name not in used]
    dead.sort(key=lambda pair: pair[1])
    return dead


#: The two set literals that DECLARE the schema. Everything else in that module
#: — including `names_field = "profile_names" if ... else "union_names"` — is a
#: use like any other.
SCHEMA_DECLARATIONS = {"PROFILE_SCHEMA_KEYS", "UNION_SCHEMA_KEYS"}


def _read_strings(node: ast.AST) -> set[str]:
    """String literals that READ a name, not ones that write it.

    A key inside a dict literal is the config STATING something — it is the
    data whose liveness is in question, so counting it as a use would make
    every key alive by virtue of being written. `entry.get("keeper")` and
    `d["keeper"]` are reads and do count.
    """
    found: set[str] = set()
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            if key is not None and not isinstance(key, ast.Constant):
                found |= _read_strings(key)
            found |= _read_strings(value)
        return found
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    for child in ast.iter_child_nodes(node):
        found |= _read_strings(child)
    return found


def _is_schema_declaration(node: ast.AST) -> bool:
    return (isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in SCHEMA_DECLARATIONS
                    for target in node.targets))


def find_dead_schema_keys(root: Path | None = None,
                          schema: dict[str, set[str]] | None = None,
                          library: tuple[str, ...] = LIBRARY,
                          ) -> list[tuple[str, str]]:
    """[(key, where it is declared)] for schema keys nothing in the library reads.

    `profiles_to_consolidate` entries are consumed key by key — `entry.get(
    "keeper")`, `cfg_entry.get("preference")` — so a key name absent from the
    package is a key the linter ACCEPTS and the generator ignores. That is
    worse than dead code: the config looks like it says something, a curator
    writes it in good faith, and nothing happens.

    References from `tests/` deliberately do NOT count: a test asserting that
    the schema accepts a key is not a consumer of it, and that was exactly the
    shape the two legacy keys had. The per-village `generate_config_names.py`
    files DO count — they are code, and one of them reads `union_names` to
    build its own move list. The first draft of this check missed that and
    called a live key dead, which is why only the two schema set-literals are
    hidden from the scan rather than the whole module that declares them.
    """
    if schema is None:
        from verso.ru.consolidation.lint_config import (
            PROFILE_SCHEMA_KEYS, UNION_SCHEMA_KEYS)
        schema = {"profiles_to_consolidate": PROFILE_SCHEMA_KEYS,
                  "unions_to_consolidate": UNION_SCHEMA_KEYS}
    declared = schema
    root = root or workspace.current().root
    importlib.invalidate_caches()
    sources = [path for top in library if (located := _located(top)) for path in _python_files(located[0])]
    sources += sorted(root.glob("*/generate_config_names.py"))
    used: set[str] = set()
    for path in sources:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.iter_child_nodes(tree):
            if _is_schema_declaration(node):
                continue      # the allow-list is a declaration, not a use
            used |= _read_strings(node)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                used.add(node.attr)
    dead = [(key, var) for var, keys in sorted(declared.items())
            for key in sorted(keys) if key not in used]
    return dead


def format_report(dead: list[tuple[str, str]]) -> str:
    if not dead:
        return f"DEAD001: OK — every function in {', '.join(PACKAGES)} is referenced somewhere."
    lines = [str(t("linters.dead_code.functions", count=len(dead))), ""]
    lines += [f"  {name:38} {site}" for name, site in dead]
    lines.append("")
    lines.append(str(t("linters.dead_code.functions_hint")))
    return "\n".join(lines)


def format_key_report(dead: list[tuple[str, str]]) -> str:
    if not dead:
        return "DEAD002: OK — every schema key the config accepts is read by code."
    lines = [str(t("linters.dead_code.keys", count=len(dead))), ""]
    lines += [str(t("linters.dead_code.key", key=key, schema=var)) for key, var in dead]
    lines.append("")
    lines.append(str(t("linters.dead_code.keys_hint")))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", help="the tree to scan (default: the workspace's)")
    args = ap.parse_args(argv)
    root = Path(args.root) if args.root else workspace.current().root
    dead_fns = find_dead_functions(root)
    dead_keys = find_dead_schema_keys(root)
    print(format_report(dead_fns))
    print(format_key_report(dead_keys))
    return 1 if (dead_fns or dead_keys) else 0


if __name__ == "__main__":
    sys.exit(main())
