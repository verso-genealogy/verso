#!/usr/bin/env python3
"""Rewrite a soldier's free-text status into its catalog constant (DSL v1).

For each `person(...)` of the villages' year files (`<village>/YYYY/*.py`) whose `status=` is a string
literal that `verso.ru.domain.military_status.classify` places («запасный рядовой» → SOLDIER):
  - the status becomes the constant, imported in the file's own form (`verso.ru.dsl.statuses`);
  - the scribe's wording goes into `comment=`, bare and in modern spelling — what MIL001 asks for. A
    comment the person has is kept and the wording put before it with «; », unless that comment already
    holds it (compared in modern spelling, case-folded, «» stripped).
A person with no status whose comment holds a reserve wording («запасный рядовой …», the comment or one
of its «quoted» parts, which `classify` places on SOLDIER) gets `status=SOLDIER`, the comment untouched.

Reported, never rewritten: a military wording `classify` will not place (`military_status.unplaced`: a
soldier's maiden, a cantonist, a vakhmistr, a military clerk), and whatever MIL001 would still flag after
the rewrite — a constant the file defines for itself, a `RecordDefaults` status form.

Usage:
    python3 -m verso.ru.cli.migrate_soldier_statuses --village <village> [--village …] [--dry-run]
        [--report FILE.tsv]
"""

import argparse
import ast
import difflib
import re
import sys
from pathlib import Path
from typing import NamedTuple

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from verso.core import workspace
from verso.ru.cli.migrate_statuses import add_import
from verso.ru.domain.military_status import classify, unplaced
from verso.ru.domain.orthography import modern_spelling
from verso.ru.dsl.source import EditError, find_arg, insert_arg
from verso.ru.linters.checks.file_bindings import module_bindings, string_constants
from verso.ru.linters.checks.military_status import STATUS_FIELDS


class Change(NamedTuple):
    """A person's status rewritten; `old` is "" for a statusless reservist given SOLDIER."""
    line: int
    old: str
    constant: str
    comment_before: str | None
    comment_after: str | None


class Unplaced(NamedTuple):
    """A military wording `classify` will not place: left as it is, for a person to decide."""
    line: int
    text: str


class Left(NamedTuple):
    """What MIL001 still flags after the rewrite: a file's own constant (`name`) or a defaults form."""
    line: int
    kwarg: str
    text: str
    constant: str
    name: str | None


# A reserve wording: «запасный рядовой», «уволенный в запас армии», «состоящий в запасе».
_RESERVE = re.compile(r"запас")  # i18n: content — status words: vocabulary
_QUOTED = re.compile(r"«([^»]*)»")  # i18n: content — the source's quotation marks
_QUOTES = str.maketrans("", "", "«»")  # i18n: content — the source's quotation marks
_SPACE = cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))


def _folded(text: str) -> str:
    return modern_spelling(text).casefold().translate(_QUOTES)


def comment_with(wording: str, before: str | None) -> str:
    """The comment that holds `wording`: `before` itself when it holds it already, else the
    wording before it with «; »."""
    if before is None or not before.strip():
        return wording
    if _folded(wording) in _folded(before):
        return before
    return f"{wording}; {before}"


def reservist(comment: str) -> bool:
    """A comment that names a reservist: the comment, or one of its «quoted» parts, holds a reserve
    word and `classify` places it on SOLDIER."""
    parts = _QUOTED.findall(comment) or [comment]
    return any(_RESERVE.search(modern_spelling(p).lower()) is not None and classify(p) == "SOLDIER"
               for p in parts)


def _text(node: cst.BaseExpression) -> str | None:
    if isinstance(node, cst.SimpleString):
        value = node.evaluated_value
        return value if isinstance(value, str) else None
    return None


def _literal(text: str, like: cst.BaseExpression | None) -> cst.SimpleString:
    """`text` as a string literal in the quote of the literal it replaces (double by default)."""
    quote = '"'
    if isinstance(like, cst.SimpleString) and like.prefix == "" and like.quote in ('"', "'"):
        quote = like.quote
    escaped = text.replace("\\", "\\\\").replace(quote, "\\" + quote).replace("\n", "\\n")
    return cst.SimpleString(f"{quote}{escaped}{quote}")


def _keyword(name: str, value: cst.BaseExpression) -> cst.Arg:
    return cst.Arg(value=value, keyword=cst.Name(name),
                   equal=cst.AssignEqual(whitespace_before=cst.SimpleWhitespace(""),
                                         whitespace_after=cst.SimpleWhitespace("")), comma=_SPACE)


def _with_value(call: cst.Call, i: int, value: cst.BaseExpression) -> cst.Call:
    args = list(call.args)
    args[i] = args[i].with_changes(value=value)
    return call.with_changes(args=args)


class _Migrator(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        super().__init__()
        self.changes: list[Change] = []
        self.unplaced: list[Unplaced] = []
        self.used: set[str] = set()

    def _line(self, node: cst.CSTNode) -> int:
        position = self.get_metadata(PositionProvider, node)
        assert isinstance(position, CodeRange)
        return position.start.line

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
        if not (isinstance(updated_node.func, cst.Name) and updated_node.func.value == "person"):
            return updated_node
        si, status = find_arg(original_node, "status")
        ci, comment = find_arg(original_node, "comment")
        before = _text(comment.value) if comment is not None else None
        if comment is not None and before is None:
            return updated_node  # a comment that is no literal: MIL001 still names the status (left_as_is)
        if status is not None and si is not None:
            text = _text(status.value)
            if text is None:
                return updated_node
            constant = classify(text)
            if constant is None:
                if unplaced(text):
                    self.unplaced.append(Unplaced(self._line(status.value), text))
                return updated_node
            after = comment_with(modern_spelling(text), before)
            call = _with_value(updated_node, si, cst.Name(constant))
            if comment is not None and ci is not None:
                if after != before:
                    call = _with_value(call, ci, _literal(after, comment.value))
            else:
                call = call.with_changes(args=insert_arg(call.args, si + 1, _keyword("comment", _literal(after, None)),
                                                         inline=True))
            self.used.add(constant)
            self.changes.append(Change(self._line(status.value), text, constant, before, after))
            return call
        if comment is not None and ci is not None and before is not None and reservist(before):
            call = updated_node.with_changes(
                args=insert_arg(updated_node.args, ci, _keyword("status", cst.Name("SOLDIER")), inline=True))
            self.used.add("SOLDIER")
            self.changes.append(Change(self._line(comment.value), "", "SOLDIER", before, before))
            return call
        return updated_node


def migrate_source(src: str) -> tuple[str, list[Change], list[Unplaced]]:
    """The file's text with each soldier's status rewritten (see the module's docstring), the changes
    and the wordings left unplaced. Raises EditError on a DSL v0 file that needs a new import."""
    migrator = _Migrator()
    new = MetadataWrapper(cst.parse_module(src)).visit(migrator).code
    if migrator.used:
        new = add_import(new, migrator.used)
    return new, migrator.changes, migrator.unplaced


def left_as_is(src: str) -> list[Left]:
    """What MIL001 flags in `src`: a status (or a `RecordDefaults` form) written as a literal or as a
    constant the file defines, which `classify` places. Run on a migrated text, the rows it was not
    allowed to rewrite."""
    tree = ast.parse(src)
    bindings = module_bindings(tree)
    texts = string_constants(bindings)
    out: list[Left] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg not in STATUS_FIELDS:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text, name, line = value.value, None, value.lineno
        elif isinstance(value, ast.Name) and value.id in texts:
            text, name, line = texts[value.id], value.id, bindings[value.id].lineno
        else:
            continue
        constant = classify(text)
        if constant is not None:
            out.append(Left(line, node.arg, text, constant, name))
    return sorted(out)


def _cell(value: object) -> str:
    return "" if value is None else str(value).replace("\t", " ").replace("\n", " ")


def _left_kind(left: Left) -> str:
    if left.name is not None:
        return "bound"
    return "defaults" if left.kwarg != "status" else "left"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--village", action="append", required=True,
                        help="a village of the workspace whose year files to migrate (repeat for more)")
    parser.add_argument("--dry-run", action="store_true", help="print a unified diff instead of writing")
    parser.add_argument("--report", type=Path, help="write every change and every row left as is to this TSV")
    args = parser.parse_args(argv)

    ws = workspace.current()
    files: list[Path] = []
    for village in args.village:
        files.extend(sorted(ws.village_dir(village).glob("[0-9][0-9][0-9][0-9]/*.py")))

    rows: list[list[object]] = []
    counts = {"rewrite": 0, "statusless": 0, "unplaced": 0, "left": 0}
    changed = 0
    for path in files:
        rel = path.relative_to(ws.root).as_posix()
        original = path.read_text(encoding="utf-8")
        try:
            new, changes, unplaced_rows = migrate_source(original)
        except EditError as err:
            print(f"{rel}: {err}", file=sys.stderr)
            continue
        for c in changes:
            kind = "rewrite" if c.old else "statusless"
            counts[kind] += 1
            rows.append([kind, rel, c.line, c.old, c.constant, c.comment_after])
        for u in unplaced_rows:
            counts["unplaced"] += 1
            rows.append(["unplaced", rel, u.line, u.text, "", ""])
        for left in left_as_is(new):
            counts["left"] += 1
            rows.append([_left_kind(left), rel, left.line, left.text, left.constant, left.name])
        if new == original:
            continue
        changed += 1
        if args.dry_run:
            sys.stdout.writelines(difflib.unified_diff(
                original.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=rel, tofile=f"{rel} (migrated)"))
        else:
            path.write_text(new, encoding="utf-8")
            print(f"  migrated: {rel}")

    if args.report is not None:
        lines = ["\t".join(["kind", "file", "line", "old", "constant", "comment_after"])]
        lines += ["\t".join(_cell(v) for v in row) for row in rows]
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    action = "would change" if args.dry_run else "changed"
    print(f"\n{action} {changed} / {len(files)} files: {counts['rewrite']} statuses rewritten, "
          f"{counts['statusless']} statusless reservists, {counts['unplaced']} unplaced, "
          f"{counts['left']} left as is", file=sys.stderr if args.dry_run else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
