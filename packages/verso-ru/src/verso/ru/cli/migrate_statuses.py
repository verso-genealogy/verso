#!/usr/bin/env python3
"""Migrate DSL files to use statuses constants.

For each .py file of the villages named with --village:
  - Replaces string literals in status=/status_male=/status_female=/status_bride=/status_groom=
    positions that match a known constant with the constant name.
  - Imports each constant in the file's own form (DSL v1: verso.ru.dsl.statuses, corpus.statuses).

Usage:
    python3 -m verso.ru.cli.migrate_statuses --village <village> [--village …] [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path

from verso.core import workspace

STATUS_KEYWORDS = {'status', 'status_male', 'status_female', 'status_bride', 'status_groom', 'status_mother'}


def load_known_statuses() -> dict[str, str]:
    """Return {string_value: constant_name} of the workspace's status catalog — its corpus's
    included —, its names in alphabetical order."""
    from verso.ru.domain import statuses
    return {str(val): name for name, val in sorted(statuses.catalog().items())}


def build_pattern(known: dict[str, str]) -> re.Pattern[str]:
    """Build a regex that matches keyword="known_value" for any STATUS_KEYWORD."""
    kw_group = '|'.join(re.escape(k) for k in STATUS_KEYWORDS)
    # Sort by length descending to match longest string first (avoids partial matches)
    values = sorted(known.keys(), key=len, reverse=True)
    val_group = '|'.join(re.escape(v) for v in values)
    return re.compile(
        r'(?P<kw>' + kw_group + r')=(?P<q>["\'])(?P<val>' + val_group + r')(?P=q)'
    )


def migrate_content(content: str, known: dict[str, str], pattern: re.Pattern[str]) -> tuple[str, set[str]]:
    """Return (new_content, set_of_constant_names_used)."""
    used: set[str] = set()

    def replace(m: re.Match[str]) -> str:
        val = m.group('val')
        const = known[val]
        used.add(const)
        return f"{m.group('kw')}={const}"

    new_content = pattern.sub(replace, content)
    return new_content, used


def add_import(content: str, constants: set[str]) -> str:
    """Import each constant into `content` (DSL v1): from `verso.ru.dsl.statuses` — a
    corpus's from `corpus.statuses` —, into the file's import of that module when it has one."""
    import libcst as cst

    from verso.ru.dsl.describe import constant_by_code
    from verso.ru.dsl.source import add_import as add_one, bound_names
    module = cst.parse_module(content)
    bound = bound_names(module)
    for name in sorted(constants - bound):
        module = add_one(module, constant_by_code()[name].module, name)
    return module.code


def migrate_file(path: Path, known: dict[str, str], pattern: re.Pattern[str], dry_run: bool) -> bool:
    """Migrate a single file. Returns True if the file was (or would be) changed."""
    original = path.read_text(encoding='utf-8')
    new_content, used = migrate_content(original, known, pattern)
    if not used:
        return False
    new_content = add_import(new_content, used)
    if new_content == original:
        return False
    if dry_run:
        import difflib
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path) + ' (migrated)',
        )
        sys.stdout.writelines(diff)
    else:
        path.write_text(new_content, encoding='utf-8')
    return True


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print diffs without writing files')
    parser.add_argument('--village', action='append', required=True,
                        help="a village of the workspace whose DSL files to migrate (repeat for more)")
    args = parser.parse_args(argv)

    known = load_known_statuses()
    pattern = build_pattern(known)

    # The villages named on the command line
    ws = workspace.current()
    py_files = []
    for village in args.village:
        d = ws.village_dir(village)
        if d.exists():
            py_files.extend(d.rglob('*.py'))
    py_files = sorted(set(py_files))
    # Exclude this script itself
    py_files = [f for f in py_files if f.name != 'migrate_statuses.py']

    changed = 0
    for path in py_files:
        if migrate_file(path, known, pattern, dry_run=args.dry_run):
            changed += 1
            if not args.dry_run:
                print(f"  migrated: {path.relative_to(ws.root)}")

    action = "would change" if args.dry_run else "changed"
    print(f"\n{action} {changed} / {len(py_files)} files")


if __name__ == '__main__':
    main()
