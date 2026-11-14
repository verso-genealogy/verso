"""The `#` notes of a DSL file, each bound to what it is about: the file, a record, an
argument of a record's call, a field on a line, or a run of records.

Pure and read-only: the file's text in, its notes out. It reads the text with `tokenize`
and `ast` alone — it never runs the file and builds no record — so a file that would not
load still gives its notes.

**A record is counted as the records export counts it.** `record` and `end` are a record's
place among the file's records, from nought: the record calls of the file in source order,
each call of a record factory — `birth`, `christening`, `marriage`, `death`, `divorce`,
`household`, `listed_person` and the three card verbs — counted once. The export walks the
record sets the module binds, in the order it binds them, and each set's records in its
book's order (`verso.core.records.ids.walk`); a set's factory and the wrappers around its
records (`page`, `book`, the `*_month` sections) keep the order their arguments are written
in, so the two counts agree on every file whose records are written inside the sets that
hold them. Where that cannot be told from the text — a record call outside every set's
call, in a loop, a comprehension or a definition, a factory imported or bound under
another name (`countable`) — no ordinal is guessed: every note of the file is `manual`.

**A block** is a run of whole `#` lines with no blank line in it (a tool's directive among
them, `# fmt: off`, neither breaks it nor is part of it); a `#` at the end of a line of
code is a note of its own. Each is bound by the first rule that holds:

0. a block that parses, its `#` taken off, as Python and calls a function by an ASCII name
   (`birth(…)`, `x.append(…)`) or imports or defines (`import`, `def`, `class`) is
   commented-out code — prose that happens to parse («Восприемник: Петровъ», «Иван = Пётр»)
   is a note; a tool's directive (`# type: ignore`, `# noqa`)
   and the first lines' `#!` and coding cookie are no notes either — none is returned;
1. a block outside every record set's call — the file's header, between two sets, after
   the last — is the file's (`file`);
2. a `#` at the end of a line inside a record's call is that line's argument (`field`) —
   on the line the call opens, the record's (`record`); at the end of a wrapper's line it
   is about the wrapper's records (`range`, `arg` the wrapper's name), elsewhere the
   file's (`file`); when two records' calls share the line, it is `manual`;
3. a block inside a record's call is the argument written below it, or the person's role
   for a census member (`member3`) or a relative (`relative2`) (`argument`); a block after
   the call's last argument is the record's (`record`);
4. a block whose next line opens a record's call (or a wrapper whose first record it is),
   and whose text names a range of numbers holding that record's number, is a group
   heading — the run of records from it whose numbers lie in the range, within the record
   set (the same `*_records(…)` call) of its first record (`range`, `record` to `end`). The range must be marked as numbers («№ 970–971», «(970–971)») or end on
   the number of the run's last record («970-971»); a range of leaves («лл. 12–13») is none;
5. a block whose next line opens a record's call, written in the call's column and in
   the same wrapper, is that record's (`record`);
6. a block whose next line opens a `book(…)`, or a wrapper (`*page(…)`, `*birth_month(…)`)
   after a record of its set, is about the wrapper's records (`range`, `arg` the wrapper's
   name: `"page"`, `"birth_month"`);
7. any other block in a set's call — above its first wrapper, beside the book's own
   arguments, not right above a record — is the file's (`file`);
8. `manual` is left for a file whose records cannot be counted: exported as a note on the
   file, marked, and not counted as bound.

An anchor's `arg` is the DSL's name — a factory parameter (`b_day`, `god_parent1`) — or, for a
census member or a relative, the person's slot (`member3`); the export names it as the JSON does
(`birth.day`, `godparent1`: `verso.core.records.notes`), which this module, below the records'
vocabulary, cannot.

The note's text is the block with `# ` (or a bare `#`) taken off each line and nothing
else: a Markdown list keeps its indents.
"""
from __future__ import annotations

import ast
import inspect
import io
import re
import tokenize
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, TypedDict

from verso.ru.dsl.calls import RECORD_FUNCS
from verso.ru.dsl.describe import CONTAINER_FUNCS, FUNCS
from verso.ru.dsl.records.divorces import divorce, divorce_month, divorce_records
from verso.ru.dsl.records.external_sources import (
    criminal_record, external_source_records, wwi_record, wwii_record)

AnchorKind = Literal["file", "record", "argument", "field", "range", "manual"]


class Anchor(TypedDict):
    to: AnchorKind
    record: int | None      # the record's place among the file's records, from nought
    end: int | None         # the last record of a range
    arg: str | None         # the DSL's name of the argument, or the person's slot (`member3`)


class Note(TypedDict):
    text: str
    anchor: Anchor
    lines: tuple[int, int]  # first and last line, from one


# The factories whose calls are records, beyond Verso's rows (`RECORD_FUNCS`): a divorce
# and the cards, which the export counts as records too.
_EXTRA_RECORDS: dict[str, Callable[..., Any]] = {
    f.__name__: f for f in (divorce, criminal_record, wwi_record, wwii_record)}
RECORD_CALLS = RECORD_FUNCS | frozenset(_EXTRA_RECORDS)
SET_CALLS = CONTAINER_FUNCS | frozenset({divorce_records.__name__, external_source_records.__name__})
WRAPPER_CALLS = frozenset(
    {"page", "book", divorce_month.__name__}
    | {name for name in FUNCS if name.endswith(("_month", "_month_year"))})
# The list arguments whose items are persons, and the role an item's persona takes.
_ITEM_ROLES = {"relatives": "relative"}
_MEMBER = "member"

# A tool's directive, not a note: `type: ignore[…]`, `noqa`, `pyright: …`, `fmt: off` after the `#`.
_PRAGMA = re.compile(r"#\s*(type:|noqa\b|pyright:|fmt:)")
# The first two lines' `#!…` and coding cookie (PEP 263) are the interpreter's, not notes.
_SHEBANG = re.compile(r"#!|#.*?coding[:=]")
# «№ 970–971», «970-971», «970 — 971».
_RANGE = re.compile(r"(\d+)\s*[-‐‑‒–—]\s*(\d+)")
_NUMERO = re.compile(r"№+\s*$")
# «лл. 12–13», «л. 4–5»: leaves, not records.
_LEAVES = re.compile(r"(?<!\w)лл?\.\s*$")  # i18n: content — the books' word for a leaf
# What a record call may not stand in for its place to be its order: the order would not
# be the source's.
_NOT_IN_ORDER = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp,
                 ast.GeneratorExp, ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _anchor(to: AnchorKind, record: int | None = None, end: int | None = None,
            arg: str | None = None) -> Anchor:
    return {"to": to, "record": record, "end": end, "arg": arg}


@cache
def _params(func: str) -> tuple[tuple[str, ...], str | None]:
    """A factory's positional parameters, and its `*varargs`."""
    fn = FUNCS.get(func) or _EXTRA_RECORDS.get(func)
    if fn is None:
        return (), None
    positional: list[str] = []
    for name, p in inspect.signature(fn).parameters.items():
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            return tuple(positional), name
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            positional.append(name)
    return tuple(positional), None


def _name(call: ast.Call) -> str | None:
    return call.func.id if isinstance(call.func, ast.Name) else None


@dataclass(frozen=True)
class _Call:
    node: ast.Call
    name: str
    start: tuple[int, int]      # where it opens — a wrapper at its `*` — line and character
    first: int                  # its first and last line
    last: int


@dataclass(frozen=True)
class _Record(_Call):
    ordinal: int


@dataclass(frozen=True)
class _Wrapper(_Call):
    records: tuple[int, ...]    # the ordinals it holds


class _Reader:
    def __init__(self, source: str, tree: ast.Module) -> None:
        self.lines = source.splitlines()
        self.records: list[_Record] = []
        self.sets: list[_Call] = []
        self.wrappers: list[_Wrapper] = []
        for node, star in _in_order(tree):
            self._take(node, star)

    def _col(self, line: int, byte_col: int) -> int:
        """A character column from `ast`'s byte offset."""
        text = self.lines[line - 1] if 0 < line <= len(self.lines) else ""
        return len(text.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore"))

    def _call(self, node: ast.Call, star: ast.Starred | None) -> tuple[tuple[int, int], int, int]:
        at = star or node
        assert node.end_lineno is not None
        return (at.lineno, self._col(at.lineno, at.col_offset)), at.lineno, node.end_lineno

    def _take(self, node: ast.AST, star: ast.Starred | None) -> None:
        if not isinstance(node, ast.Call):
            return
        name = _name(node)
        if name is None:
            return
        start, first, last = self._call(node, star)
        if name in RECORD_CALLS:
            self.records.append(_Record(node, name, start, first, last, len(self.records)))
        elif name in SET_CALLS:
            self.sets.append(_Call(node, name, start, first, last))
        elif name in WRAPPER_CALLS:
            self.wrappers.append(_Wrapper(node, name, start, first, last, ()))

    def finish(self) -> None:
        self.wrappers = [
            _Wrapper(w.node, w.name, w.start, w.first, w.last,
                     tuple(r.ordinal for r in self.records if _inside(r.node, w.node)))
            for w in self.wrappers]


def _inside(inner: ast.AST, outer: ast.AST) -> bool:
    return _pos(outer) <= _pos(inner) and _end(inner) <= _end(outer)


def _pos(node: ast.AST) -> tuple[int, int]:
    return node.lineno, node.col_offset  # type: ignore[attr-defined]


def _end(node: ast.AST) -> tuple[int, int]:
    return node.end_lineno or 0, node.end_col_offset or 0  # type: ignore[attr-defined]


def _in_order(node: ast.AST) -> Iterator[tuple[ast.AST, ast.Starred | None]]:
    """Every node under `node`, in the order the source writes it (a call's positional
    and keyword arguments interleaved as written); a call under `*` with its star."""
    children = [c for c in ast.iter_child_nodes(node) if hasattr(c, "lineno")]
    children.sort(key=_pos)
    for child in children:
        if isinstance(child, ast.Starred) and isinstance(child.value, ast.Call):
            yield child.value, child
            yield from _in_order(child.value)
        else:
            yield child, None
            yield from _in_order(child)


@dataclass(frozen=True)
class _Comment:
    line: int
    col: int            # its character column
    text: str           # the token, `#` included
    trailing: bool      # written after code on its line


def _comments(source: str) -> tuple[list[_Comment], list[tuple[int, int]]]:
    """The file's comments, and where each token of code starts (line, character)."""
    comments: list[_Comment] = []
    code: list[tuple[int, int]] = []
    last_code_line = 0
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
            tokenize.ENCODING}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            comments.append(_Comment(tok.start[0], tok.start[1], tok.string.rstrip(),
                                     last_code_line == tok.start[0]))
        elif tok.type not in skip:
            code.append(tok.start)
            last_code_line = tok.end[0]
    return comments, code


def _strip(comment: str) -> str:
    text = comment.removeprefix("#")
    return text.removeprefix(" ")


def _blocks(comments: Sequence[_Comment]) -> Iterator[list[_Comment]]:
    """Runs of whole-line comments on consecutive lines, and each trailing comment alone.
    A tool's directive is left out and does not break the run it stands in; the
    interpreter's first lines are left out."""
    run: list[_Comment] = []
    tail = 0                    # the run's last line, a directive's included
    for c in comments:
        if c.line <= 2 and not c.trailing and _SHEBANG.match(c.text):
            continue
        if _PRAGMA.match(c.text):
            if run and not c.trailing and c.line == tail + 1:
                tail = c.line
            continue
        if c.trailing:
            if run:
                yield run
                run = []
            yield [c]
            continue
        if run and c.line != tail + 1:
            yield run
            run = []
        run.append(c)
        tail = c.line
    if run:
        yield run


def is_code(text: str) -> bool:
    """Whether a block's text, its `#` taken off, is commented-out Python rather than prose:
    it parses, and either some call in it names its function in ASCII (`birth(…)`, `x.append(…)`)
    or a top-level statement imports or defines (`import`, `def`, `class`). A statement that merely
    parses — an annotation («Восприемник: Петровъ», «TODO: recheck»), an assignment of names
    («Иван = Пётр»), a bare expression («- Петров») — is prose."""
    lines = text.splitlines()
    indent = min((len(s) - len(s.lstrip()) for s in lines if s.strip()), default=0)
    try:
        tree = ast.parse("\n".join(s[indent:] for s in lines))
    except (SyntaxError, ValueError):
        return False
    if any(isinstance(stmt, _CODE_STATEMENTS) for stmt in tree.body):
        return True
    return any(isinstance(n, ast.Call) and _ascii_callee(n.func) for n in ast.walk(tree))


_CODE_STATEMENTS = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _ascii_callee(func: ast.expr) -> bool:
    if isinstance(func, ast.Attribute):
        return bool(func.attr) and func.attr.isascii()
    return isinstance(func, ast.Name) and bool(func.id) and func.id.isascii()


def _int(node: ast.expr) -> int | None:
    """A whole number written as a literal: `3`, `-1`."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        n = _int(node.operand)
        return None if n is None else -n
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    return None


def _number(record: _Record) -> int | None:
    """The record's number as written — its first positional argument, or its number's
    keyword — when it is a whole number."""
    node = record.node
    value: ast.expr | None = node.args[0] if node.args and not isinstance(node.args[0], ast.Starred) else None
    if value is None:
        for kw in node.keywords:
            if kw.arg in ("record_num", "number", "family_id"):
                value = kw.value
    if isinstance(value, ast.Constant):
        raw: object = value.value
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().isdigit():
            return int(raw.strip())
    return None


def countable(tree: ast.Module) -> bool:
    """Whether the record calls in source order are the records export's order: each
    stands inside the call of a record set, in no loop, comprehension or definition; no
    factory is imported or bound under another name, nor named but to be called."""
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    named = RECORD_CALLS | SET_CALLS | WRAPPER_CALLS
    for node in ast.walk(tree):
        if isinstance(node, ast.alias) and node.name in named and node.asname not in (None, node.name):
            return False
        if isinstance(node, ast.Name) and node.id in RECORD_CALLS:
            call = parent.get(node)
            if not (isinstance(call, ast.Call) and call.func is node):
                return False
            in_set = False
            up: ast.AST | None = parent.get(call)
            while up is not None:
                if isinstance(up, _NOT_IN_ORDER):
                    return False
                if isinstance(up, ast.Call) and _name(up) in SET_CALLS:
                    in_set = True
                up = parent.get(up)
            if not in_set:
                return False
    return True


class _Binder:
    def __init__(self, source: str) -> None:
        tree = ast.parse(source)
        self.countable = countable(tree)
        self.reader = _Reader(source, tree)
        self.reader.finish()
        self.comments, self.code = _comments(source)

    # --------------------------------------------------------------- where

    def _innermost(self, calls: Sequence[_Call], first: int, last: int,
                   *, strict: bool = True) -> _Call | None:
        """The innermost call whose lines hold `first`..`last` — strictly inside its first
        and last line for a whole-line block, or on them too for a trailing comment."""
        found: _Call | None = None
        for c in calls:
            holds = (c.first < first and last < c.last) if strict else (c.first <= first and last <= c.last)
            if holds and (found is None or _inside(c.node, found.node)):
                found = c
        return found

    def _next_code(self, line: int) -> tuple[int, int] | None:
        for at in self.code:
            if at[0] > line:
                return at
        return None

    # --------------------------------------------------------------- binding

    def bind(self, block: list[_Comment]) -> Note | None:
        first, last = block[0].line, block[-1].line
        text = "\n".join(_strip(c.text) for c in block)
        if not block[0].trailing and is_code(text):
            return None
        anchor = (self._anchor(block[0], first, last, text) if self.countable
                  else _anchor("manual"))
        return {"text": text, "anchor": anchor, "lines": (first, last)}

    def _container(self, first: int, last: int) -> _Call | None:
        """The innermost set or wrapper whose lines hold the block."""
        return self._innermost([*self.reader.sets, *self.reader.wrappers], first, last)

    def _container_of(self, node: ast.AST) -> _Call | None:
        found: _Call | None = None
        for c in (*self.reader.sets, *self.reader.wrappers):
            if c.node is not node and _inside(node, c.node) and (found is None or _inside(c.node, found.node)):
                found = c
        return found

    def _set_of(self, record: _Record) -> _Call | None:
        """The innermost record set whose call holds the record."""
        found: _Call | None = None
        for c in self.reader.sets:
            if _inside(record.node, c.node) and (found is None or _inside(c.node, found.node)):
                found = c
        return found

    def _anchor(self, head: _Comment, first: int, last: int, text: str) -> Anchor:
        records = self.reader.records
        if head.trailing:
            return self._trailing(first)
        record = self._innermost(records, first, last)
        if isinstance(record, _Record):
            return self._argument(record, first, last)
        set_ = self._innermost(self.reader.sets, first, last)
        if set_ is None:
            return _anchor("file")
        below = self._next_code(last)
        if below is None or below[0] != last + 1:
            return _anchor("file")
        for r in records:
            if r.start == below:
                heading = self._heading(text, r)
                if heading is not None:
                    return heading
                if head.col == r.start[1] and self._container(first, last) is self._container_of(r.node):
                    return _anchor("record", r.ordinal)
                return _anchor("file")
        for w in self.reader.wrappers:
            if w.start == below and w.records:
                heading = self._heading(text, records[w.records[0]])
                if heading is not None:
                    return heading
                earlier = any(_inside(r.node, set_.node) and _pos(r.node) < _pos(w.node) for r in records)
                if w.name == "book" or earlier:
                    return _anchor("range", w.records[0], w.records[-1], arg=w.name)
                return _anchor("file")
        return _anchor("file")

    def _heading(self, text: str, record: _Record) -> Anchor | None:
        """A group heading: a range of numbers holding the record's, marked as numbers
        («№», brackets) or ending on the number of the last record of its run — never a
        range of leaves («лл. 12–13»)."""
        number = _number(record)
        if number is None:
            return None
        for m in _RANGE.finditer(text):
            lo, hi = int(m.group(1)), int(m.group(2))
            before = text[:m.start()]
            if not lo <= number <= hi < lo + 10_000 or _LEAVES.search(before):
                continue
            end, end_number = record.ordinal, number
            own_set = self._set_of(record)
            for nxt in self.reader.records[record.ordinal + 1:]:
                if self._set_of(nxt) is not own_set:
                    break                  # a run stops at the last record of its set
                n = _number(nxt)
                if n is None or not lo <= n <= hi:
                    break
                end, end_number = nxt.ordinal, n
            bracketed = before.count("(") > before.count(")") or before.count("[") > before.count("]")
            if _NUMERO.search(before) or bracketed or end_number == hi:
                return _anchor("range", record.ordinal, end)
        return None

    def _trailing(self, line: int) -> Anchor:
        if sum(r.first <= line <= r.last for r in self.reader.records) > 1:
            return _anchor("manual")        # two records share the line: which one it is about is a guess
        record = self._innermost(self.reader.records, line, line, strict=False)
        if isinstance(record, _Record):
            # On the line the call opens it is about the record: `birth(93, …, 1, 3,  # twins`.
            arg = None if line == record.first else self._arg_on(record, line)
            return _anchor("field", record.ordinal, arg=arg) if arg else _anchor("record", record.ordinal)
        wrapper = self._innermost(self.reader.wrappers, line, line, strict=False)
        if isinstance(wrapper, _Wrapper) and wrapper.records:
            return _anchor("range", wrapper.records[0], wrapper.records[-1], arg=wrapper.name)
        return _anchor("file")

    # --------------------------------------------------------------- arguments

    def _arguments(self, record: _Record) -> list[tuple[str | None, ast.expr]]:
        """The call's arguments as written, each with the name it binds to."""
        positional, varargs = _params(record.name)
        out: list[tuple[str | None, ast.expr]] = []
        for i, arg in enumerate(record.node.args):
            if isinstance(arg, ast.Starred):
                out.append((None, arg))
            else:
                out.append((positional[i] if i < len(positional) else varargs, arg))
        out.extend((kw.arg, kw.value) for kw in record.node.keywords)
        out.sort(key=lambda a: _pos(a[1]))
        return out

    def _arg_on(self, record: _Record, line: int) -> str | None:
        """The argument a trailing comment on `line` closes: the last one ending on it,
        else the one whose lines hold it."""
        args = self._arguments(record)
        ending = [a for a in args if _end(a[1])[0] == line]
        if ending:
            return self._role(*ending[-1], line)
        for name, value in args:
            if value.lineno <= line <= _end(value)[0]:
                return self._role(name, value, line)
        return None

    def _argument(self, record: _Record, first: int, last: int) -> Anchor:
        for name, value in self._arguments(record):
            if value.lineno > last or (value.lineno < first and _end(value)[0] > last):
                arg = self._role(name, value, last)
                return (_anchor("argument", record.ordinal, arg=arg) if arg
                        else _anchor("record", record.ordinal))
        return _anchor("record", record.ordinal)

    def _role(self, name: str | None, value: ast.expr, line: int) -> str | None:
        """The argument's name — or the person's role for a census member or a relative:
        `member3` (its number), `relative2` (its place in the list)."""
        if isinstance(value, ast.Call) and _name(value) == _MEMBER and value.args:
            number = _int(value.args[0])
            if number is not None:
                return f"{_MEMBER}{number}"
        if name in _ITEM_ROLES and isinstance(value, ast.List | ast.Tuple):
            for i, item in enumerate(value.elts):      # the item holding the line, or below it
                if _end(item)[0] >= line:
                    return f"{_ITEM_ROLES[name]}{i + 1}"
            return name
        return name


def read_notes(source: str) -> tuple[list[Note], list[int | None] | None]:
    """Every `#` note of a DSL file (`extract_notes`) and the records it counted: each record
    call's number as written (`None` where it is no whole number), in source order — what
    the export holds the ordinals to. `None` for records it could not count (`countable`),
    or for a file that does not parse."""
    source = source.removeprefix("\ufeff")
    try:
        binder = _Binder(source)
    except (SyntaxError, ValueError, tokenize.TokenError):
        return [], None
    notes: list[Note] = []
    for block in _blocks(binder.comments):
        note = binder.bind(block)
        if note is not None:
            notes.append(note)
    numbers = [_number(r) for r in binder.reader.records] if binder.countable else None
    return notes, numbers


def extract_notes(source: str) -> list[Note]:
    """Every `#` note of a DSL file, in the file's order, each with its anchor.
    Commented-out code is left out. A file that does not parse has none."""
    return read_notes(source)[0]
