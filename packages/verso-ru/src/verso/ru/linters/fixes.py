#!/usr/bin/env python3
"""In-place fixes for the mechanical DSL findings.

Today this is one rule, and it is the one that costs a session every time a new
year is written: `single_line_calls` requires every `person(...)` to sit on one
line, an editor's auto-wrap breaks a dozen of them at once, and the repair is a
pure whitespace edit with no judgement in it at all. It has been done by hand
and by throwaway scripts more than once; here it is, in the linter that reports
it.

**Safety.** A join is applied only when the file re-parses to an IDENTICAL AST.
That is the whole guarantee: whitespace inside a call has no meaning, so if the
tree is unchanged the edit cannot have changed the records — and if anything
about the join is wrong, the comparison catches it and the file is left alone.
Calls carrying a `#` comment between their parentheses are skipped outright: a
comment would swallow the rest of the line, and no AST comparison would notice
because comments are not in the tree.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import verso.ru.linters.checks.single_line_calls as single_line_calls

# Whitespace that a join leaves behind on either side of a bracket or comma.
_AFTER_OPEN = re.compile(r"\(\s+")
_BEFORE_CLOSE = re.compile(r"\s+\)")
_BEFORE_COMMA = re.compile(r"\s+,")
# A wrap usually leaves a magic trailing comma behind; on one line it is noise.
# Removing it from a one-element TUPLE would change meaning, which is exactly
# what the AST comparison in fix_source() refuses to let through.
_TRAILING_COMMA = re.compile(r",\s*\)")
_RUNS = re.compile(r"[ \t]{2,}")


@dataclass(frozen=True)
class FixResult:
    path: Path
    joined: int
    skipped: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return self.joined > 0


def _multiline_calls(source: str) -> list[tuple[int, int, str]]:
    """(start, end, name) of every wrapped single-line-only call, 1-based."""
    checker = single_line_calls.Checker(source)
    checker.visit(ast.parse(source))
    return sorted(checker.violations, key=lambda v: v[0])


def join_lines(chunk: list[str]) -> str:
    """Collapse the lines of one wrapped call into a single line.

    Indentation of the first line is kept — it positions the call inside the
    record — and everything after it becomes single spaces, tightened around
    the brackets and commas the wrap introduced.
    """
    indent = chunk[0][: len(chunk[0]) - len(chunk[0].lstrip())]
    body = " ".join(part.strip() for part in chunk if part.strip())
    body = _AFTER_OPEN.sub("(", body)
    body = _BEFORE_CLOSE.sub(")", body)
    body = _BEFORE_COMMA.sub(",", body)
    body = _TRAILING_COMMA.sub(")", body)
    return indent + _RUNS.sub(" ", body)


def fix_source(source: str) -> tuple[str, int, list[str]]:
    """Join every wrapped call in `source`. Returns (new source, joined, skipped)."""
    try:
        original_tree = ast.dump(ast.parse(source))
    except SyntaxError:
        return source, 0, ["SyntaxError — nothing rewritten"]

    lines = source.splitlines(keepends=True)
    skipped: list[str] = []
    joined = 0

    # Bottom-up: an earlier join would shift every line number after it.
    for start, end, name in reversed(_multiline_calls(source)):
        chunk = lines[start - 1:end]
        if any("#" in part for part in chunk):
            skipped.append(f"{name}() at line {start}: carries a comment")
            continue
        newline = "\n" if chunk[-1].endswith("\n") else ""
        lines[start - 1:end] = [join_lines([c.rstrip("\n") for c in chunk]) + newline]
        joined += 1

    if not joined:
        return source, 0, skipped

    candidate = "".join(lines)
    try:
        if ast.dump(ast.parse(candidate)) != original_tree:
            return source, 0, skipped + ["join changed the parse tree — nothing rewritten"]
    except SyntaxError:
        return source, 0, skipped + ["join produced invalid Python — nothing rewritten"]
    return candidate, joined, skipped


def fix_file(path: Path, *, dry_run: bool = False) -> FixResult:
    source = path.read_text(encoding="utf-8")
    new_source, joined, skipped = fix_source(source)
    if joined and not dry_run:
        path.write_text(new_source, encoding="utf-8")
    return FixResult(path=path, joined=joined, skipped=tuple(skipped))


def run(paths: list[Path], *, dry_run: bool = False) -> tuple[list[FixResult], int]:
    """Fix each path. Returns (results, exit code) — non-zero only on a skip."""
    results = [fix_file(p, dry_run=dry_run) for p in paths if p.is_file()]
    skipped = sum(len(r.skipped) for r in results)
    return results, (1 if skipped else 0)


def format_report(results: list[FixResult], *, dry_run: bool = False) -> str:
    verb = "would join" if dry_run else "joined"
    changed = [r for r in results if r.changed]
    lines = []
    for r in changed:
        lines.append(f"{r.path}: {verb} {r.joined} wrapped call(s)")
    for r in results:
        for reason in r.skipped:
            lines.append(f"{r.path}: SKIPPED {reason}")
    if not lines:
        return "dsllint --fix: nothing to join."
    total = sum(r.joined for r in changed)
    lines.append(f"\ndsllint --fix: {verb} {total} call(s) in {len(changed)} file(s).")
    return "\n".join(lines)
