"""The review queue of one DSL file, and the rewrite of one of its calls.

Pure: source text in, source text out. Everything is read off the CST, so a
record is exactly what the file writes — `person("Василій")` has one argument,
not the three a `Person` object ends up holding once the book's defaults and
the father's surname are in.

**A record is addressed by its ordinal** — its position among the record calls
of the file, in source order — plus a hash of the call's text. The record
number cannot do it (932 in-file repeats of number+gender across the corpus),
and the ordinal alone would silently edit the wrong call if the file changed
under the page; the hash turns that into a refusal (`Stale`).

**A pending record is held or on Geni**, and the ratchet says which
(`verso.core.ratchet`): one unreviewed and listed in the village's
`unreviewed_on_geni.tsv` is on Geni already — Глуповы Горы's лист markers,
uploaded while `page(reviewed=False)` did nothing around vital records — and
every other one is held (`effective`): the Маниловка sweep, the census rolls. The
caller passes the file's listed fingerprints (`on_geni`); this module reads no
file. A listed record may be edited only together with «Вычитано» — edited and
still unreviewed it would no longer match its line, leave Geni, and the next
plan would destroy its profiles — and «Вычитано» strikes its line (`struck`).

**Where the flag is written** decides how it is dropped:

* `own` — `birth(…, reviewed=False)`: dropping the kwarg reviews the record.
* `page` — `page("341об", reviewed=False, …)`: reviewing one record of the leaf
  writes an explicit `reviewed=True` on it, and the last one takes the page's
  flag and every explicit `True` away with it.
* `file` — `census_records(…, reviewed=False)` (or a `birth_records(…)`), dropped
  the same way per record.
"""
from __future__ import annotations

import ast
import calendar
import hashlib
import io
import re
import tokenize
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast, override

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from verso.core.i18n import Message
from verso.core.ratchet import record_prints
from verso.ru.dsl import signatures as sig
from verso.ru.messages import t


class _Keyed:
    """A refusal that says which: its message's `key` and `params` (`source.*` of verso.ru's
    catalogs) — what a page shows in its own language —, and `str()` the text in the workspace's.
    A caller's own text (a str) has no key."""

    def __init__(self, message: Message | str) -> None:
        self.message = message
        # A message of any catalog's mechanism — the library's, or an App's copy of it — by its shape.
        keyed = not isinstance(message, str) and all(hasattr(message, a) for a in ("package", "key", "params"))
        self.package: str | None = getattr(message, "package", None) if keyed else None
        self.key: str | None = getattr(message, "key", None) if keyed else None
        self.params: dict[str, object] = dict(getattr(message, "params", {})) if keyed else {}

    def __str__(self) -> str:
        return str(self.message)


class Stale(_Keyed, Exception):
    """The record changed on disk since the page was loaded (`source.stale`), or is gone
    (`source.gone`)."""

    def __init__(self, message: Message | str) -> None:
        _Keyed.__init__(self, message)
        Exception.__init__(self, self.key or message)


class EditError(_Keyed, ValueError):
    """An edit that cannot be expressed in this call."""

    def __init__(self, message: Message | str) -> None:
        _Keyed.__init__(self, message)
        ValueError.__init__(self, self.key or message)


# ---------------------------------------------------------------- model

@dataclass
class Value:
    """One argument's value, as the source writes it."""
    kind: str                     # str int float bool none const raw call list
    value: Any = None             # the literal; a constant's code («PEASANT_WIDOW»)
    code: str = ""                # the source text
    call: CallView | None = None  # kind == "call": person(…), member(…), relative(…)
    items: list[Value] | None = None   # kind == "list": relatives=[relative(…), …]


@dataclass
class ArgView:
    param: str                    # the parameter it binds to; «@3» for the 4th `*members`
    value: Value
    positional: bool


@dataclass
class CallView:
    func: str
    args: list[ArgView]
    # Whether an unpacked list (`*rows`) stands among its arguments (`_call_view` says it): items no
    # path names one by one (`verso.ru.dsl.paths`). Not a field, so the v1 card
    # (`dataclasses.asdict`) is as it was; `__eq__` counts it all the same.
    splat = False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CallView):
            return NotImplemented
        return (self.func, self.args, self.splat) == (other.func, other.args, other.splat)

    __hash__ = None  # type: ignore[assignment]  # mutable, as the dataclass made it

    def arg(self, param: str) -> ArgView | None:
        for a in self.args:
            if a.param == param:
                return a
        return None


@dataclass
class Record:
    ordinal: int
    func: str
    kind: str                     # births / marriages / deaths / census / name_lists
    sha: str
    start_line: int
    end_line: int
    pending: bool
    flag: str | None              # own / page / file — where the pending flag is written
    effective: bool               # held: pending, and not on the ratchet's list
    year: int | None
    month: int | None
    day: int | None
    page: str | None
    record_num: int | str | None
    gender: str                   # «м» / «ж» / ""
    case_ref: str | None          # «436-13-458»: фонд-опись-дело, as album titles carry it
    call: CallView
    comments: list[str] = field(default_factory=list)
    # The month of the `birth_month(…)` section around it, whatever the record
    # writes of its own: what a month field reverts to when cleared.
    section_month: int | None = None
    # The лист of the `page(…)` around it, whatever the record writes of its
    # own: what its `page` reverts to when the record's own `page=` is taken off.
    wrapper_page: str | None = None
    # The ratchet's fingerprint of the call as it reads now (`verso.core.ratchet`).
    fingerprint: str = ""
    # Where the call the record stands in starts («12:17»): two records with
    # one container are neighbours a record added between them joins.
    container: str = ""
    # The year of the book it is written in — its record set's — where `year`
    # is the record's own date: a child born 30 Dec 1870 is № 1 of the 1871
    # book (Маниловка), and the Nov–Dec 1797 sections open Заманиловка's 1798 one.
    # The book decides the album, and the series a window's number is of.
    book_year: int | None = None


# ---------------------------------------------------------------- reading

def _func_name(call: cst.Call) -> str | None:
    return call.func.value if isinstance(call.func, cst.Name) else None


@dataclass(frozen=True)
class _Found:
    node: cst.Call
    func: str
    ancestors: tuple[cst.Call, ...]   # known-function calls around it, innermost first


class _Collector(cst.CSTVisitor):
    def __init__(self) -> None:
        self.stack: list[cst.Call] = []
        self.found: list[_Found] = []

    def visit_Call(self, node: cst.Call) -> bool:
        name = _func_name(node)
        if name in sig.RECORD_FUNCS:
            self.found.append(_Found(node, name, tuple(reversed(self.stack))))
        if name in sig.KNOWN_FUNCS:
            self.stack.append(node)
        return True

    def leave_Call(self, original_node: cst.Call) -> None:
        if self.stack and self.stack[-1] is original_node:
            self.stack.pop()


def _collect(module: cst.Module) -> list[_Found]:
    collector = _Collector()
    module.visit(collector)
    return collector.found


def _bind(call: cst.Call) -> list[tuple[str, int, cst.Arg]]:
    """(parameter, index in `call.args`, arg) for every argument. A splat binds
    to «*»; a positional past the fixed parameters to «@N» of `*varargs`."""
    s = sig.signature(_func_name(call) or "")
    out: list[tuple[str, int, cst.Arg]] = []
    positional = varargs = 0
    for i, arg in enumerate(call.args):
        if arg.keyword is not None:
            out.append((arg.keyword.value, i, arg))
        elif arg.star:
            out.append(("*", i, arg))
        else:
            p = s.positional_param(positional) if s else None
            if p is not None:
                out.append((p.name, i, arg))
                positional += 1
            else:
                out.append((f"@{varargs}", i, arg))
                varargs += 1
    return out


def find_arg(call: cst.Call, param: str) -> tuple[int, cst.Arg] | tuple[None, None]:
    for name, i, arg in _bind(call):
        if name == param:
            return i, arg
    return None, None


_DOTTED = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)?$")
_CONSTANT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*(\.[A-Z][A-Z0-9_]*)?$")


def value_of(node: cst.BaseExpression, module: cst.Module) -> Value:
    code = module.code_for_node(node)
    if isinstance(node, (cst.SimpleString, cst.ConcatenatedString)):
        try:
            text = ast.literal_eval(f"({code})")
        except (ValueError, SyntaxError):
            return Value("raw", code=code)
        return Value("str", text, code) if isinstance(text, str) else Value("raw", code=code)
    if isinstance(node, cst.Integer):
        return Value("int", ast.literal_eval(code), code)
    if isinstance(node, cst.Float):
        return Value("float", ast.literal_eval(code), code)
    if isinstance(node, cst.Name):
        if node.value in ("True", "False"):
            return Value("bool", node.value == "True", code)
        if node.value == "None":
            return Value("none", None, code)
        return Value("const", code, code)
    if isinstance(node, cst.Attribute) and _DOTTED.match(code):
        return Value("const", code, code)
    if isinstance(node, cst.Call) and _func_name(node) in _EDITABLE_CALLS:
        return Value("call", code=code, call=_call_view(node, module))
    if isinstance(node, cst.List) and all(_is_relative(e) for e in node.elements):
        # `relatives=[relative(…), …]`, element by element; any other list —
        # a comprehension, a name — stays code.
        return Value("list", code=code, items=[value_of(e.value, module) for e in node.elements])
    return Value("raw", code=code)


# The calls the page edits argument by argument and may create.
_EDITABLE_CALLS = ("person", "member", "relative")


def _is_relative(element: cst.BaseElement) -> bool:
    return (isinstance(element, cst.Element) and isinstance(element.value, cst.Call)
            and _func_name(element.value) == "relative")


def _call_view(call: cst.Call, module: cst.Module) -> CallView:
    bound = _bind(call)
    view = CallView(_func_name(call) or "", [
        ArgView(name, value_of(arg.value, module), arg.keyword is None)
        for name, _, arg in bound if name != "*"])
    view.splat = any(name == "*" for name, _, _ in bound)
    return view


def _kw_bool(call: cst.Call, name: str) -> bool | None:
    _, arg = find_arg(call, name)
    if arg is not None and isinstance(arg.value, cst.Name) and arg.value.value in ("True", "False"):
        return arg.value.value == "True"
    return None


def _literal(call: cst.Call, param: str, module: cst.Module) -> Any:
    _, arg = find_arg(call, param)
    if arg is None:
        return None
    v = value_of(arg.value, module)
    return v.value if v.kind in ("str", "int", "float", "const") else None


def _holders(found: _Found) -> list[cst.Call]:
    """The calls around a record that may write its review flag, innermost first."""
    out = []
    for call in found.ancestors:
        name = _func_name(call)
        if name == "page":
            out.append(call)
        elif name in sig.CONTAINER_FUNCS:
            s = sig.signature(name)
            if s is not None and s.param("reviewed") is not None:
                out.append(call)
    return out


def _state(found: _Found) -> tuple[bool, str | None]:
    own = _kw_bool(found.node, "reviewed")
    if own is not None:
        return (not own, None if own else "own")
    for holder in _holders(found):
        value = _kw_bool(holder, "reviewed")
        if value is not None:
            return (not value, None if value else
                    ("page" if _func_name(holder) == "page" else "file"))
    return (False, None)


_GENDER = {"Gender.MALE": "м", "Gender.FEMALE": "ж"}  # i18n: content — the sex as the DSL writes it
_MONTH_PARAM = {"birth": "b_month", "christening": "k_month", "death": "d_month",
                "marriage": "w_month", "household": "record_month"}
_DAY_PARAM = {"birth": "b_day", "christening": "k_day", "death": "d_day", "marriage": "w_day"}
_NUMBER_PARAM = {"household": "family_id", "listed_person": "number"}


def _month(code: Any) -> int | None:
    if isinstance(code, str) and code.startswith("Month."):
        try:
            return int(calendar.Month[code.removeprefix("Month.")])
        except KeyError:
            return None
    return None


def _context(found: _Found, module: cst.Module) -> dict[str, Any]:
    node, func = found.node, found.func
    year = _literal(node, "year", module)
    month = _month(_literal(node, _MONTH_PARAM.get(func, ""), module))
    page = _literal(node, "page", module)
    case = _literal(node, "case", module)
    fund = inventory = section = wrapper = book = None
    for call in found.ancestors:
        name = _func_name(call) or ""
        if case is None and (name == "page" or name in sig.CONTAINER_FUNCS):
            case = _literal(call, "case", module)
        if name in sig.CONTAINER_FUNCS:
            fund, inventory = _literal(call, "fund", module), _literal(call, "inventory", module)
            book = _literal(call, "year", module)
        if section is None and name.endswith(("_month", "_month_year")):
            section = _month(_literal(call, "month", module))
        if year is None and (name.endswith("_month_year") or name == "page"
                             or name in sig.CONTAINER_FUNCS):
            year = _literal(call, "year", module)
        if wrapper is None and name == "page":
            wrapper = _literal(call, "num", module)
    page = wrapper if page is None else page
    month = section if month is None else month
    day = _literal(node, _DAY_PARAM.get(func, ""), module)
    return {
        "year": year if isinstance(year, int) else None,
        "book_year": book if isinstance(book, int) else year if isinstance(year, int) else None,
        "month": month,
        "section_month": section,
        "day": day if isinstance(day, int) else None,
        "page": str(page) if page is not None else None,
        "wrapper_page": str(wrapper) if wrapper is not None else None,
        "record_num": _literal(node, _NUMBER_PARAM.get(func, "record_num"), module),
        "gender": _GENDER.get(str(_literal(node, "gender", module)), ""),
        "case_ref": f"{fund}-{inventory}-{case}" if fund and inventory and case else None,
    }


def sha(code: str) -> str:
    return hashlib.sha1(code.encode("utf-8")).hexdigest()[:12]


def _comment_lines(source: str) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                out[tok.start[0]] = tok.string.removeprefix("#").strip()
    except (tokenize.TokenError, SyntaxError):
        pass
    return out


def _comments_for(lines: Sequence[str], comments: Mapping[int, str],
                  start: int, end: int) -> list[str]:
    """The comment block directly above the call, then those inside it."""
    above: list[str] = []
    n = start - 1
    while n >= 1 and lines[n - 1].lstrip().startswith("#"):
        above.append(comments.get(n, lines[n - 1].strip().lstrip("#").strip()))
        n -= 1
    inside = [comments[n] for n in range(start, end + 1) if n in comments]
    return list(reversed(above)) + inside


def find_records(source: str, on_geni: Iterable[str] = ()) -> list[Record]:
    """Every record call of the file — pending or not — in source order.

    `on_geni`: the fingerprints the village's ratchet lists for this file. A
    pending record whose fingerprint is among them (one line each) is on Geni;
    every other pending record is held."""
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    lines = source.splitlines()
    comments = _comment_lines(source)
    found_all = _collect(module)
    prints = record_prints(source)
    if [f.func for f in found_all] != [p.func for p in prints]:
        raise ValueError("the record calls read by libcst and by ast disagree")
    listed = Counter(on_geni)
    out = []
    for ordinal, (found, p) in enumerate(zip(found_all, prints, strict=True)):
        where: CodeRange = positions[found.node]
        pending, flag = _state(found)
        held = pending
        if pending and listed[p.fingerprint] > 0:
            listed[p.fingerprint] -= 1
            held = False
        out.append(Record(
            ordinal=ordinal, func=found.func, kind=sig.KIND[found.func],
            sha=sha(module.code_for_node(found.node)),
            start_line=where.start.line, end_line=where.end.line,
            pending=pending, flag=flag, effective=held,
            call=_call_view(found.node, module),
            comments=_comments_for(lines, comments, where.start.line, where.end.line),
            fingerprint=p.fingerprint,
            container=_where(positions, found.ancestors[0]) if found.ancestors else "",
            **_context(found, module)))
    return out


def _where(positions: Mapping[cst.CSTNode, CodeRange], node: cst.CSTNode) -> str:
    start = positions[node].start
    return f"{start.line}:{start.column}"


def struck(source: str, ordinal: int, on_geni: Iterable[str]) -> str | None:
    """The ratchet line «Вычитано» strikes for the record at `ordinal`: its
    fingerprint as the file reads now, when the record is pending and listed."""
    record = find_records(source, on_geni)[ordinal]
    return record.fingerprint if record.pending and not record.effective else None


def file_constants(source: str) -> dict[str, str]:
    """The string constants the file defines for itself — `TENTETNIKOV_M =
    "крестьянин вотчины Г. Тентетникова"` — which no catalog knows, so the page
    can show and read them by their words like the catalog's own."""
    out: dict[str, str] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and _CONSTANT_NAME.match(node.targets[0].id)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            out[node.targets[0].id] = node.value.value
    return out


def file_notes(source: str) -> list[str]:
    """The comment lines above the file's records container: the file's own
    account of how it was read («reviewed=False: имена сверены кропом при 5–8×…»)."""
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    lines = source.splitlines()
    stop = len(lines) + 1
    for node, where in positions.items():
        if isinstance(node, cst.Call) and _func_name(node) in sig.CONTAINER_FUNCS:
            stop = min(stop, where.start.line)
    return [line.strip().lstrip("#").strip() for line in lines[:stop - 1]
            if line.strip().startswith("#")]


# ---------------------------------------------------------------- writing

_SPACE = cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))


def insert_arg[T: (cst.Arg, cst.ImportAlias, cst.Element)](args: Sequence[T], k: int, new: T, *,
                                                inline: bool = False) -> list[T]:
    """Insert `new` at position `k`, keeping the call's own layout: it takes the
    separator of the argument before it, so a one-per-line call stays one per
    line. `inline` puts it on the previous argument's line instead — how the
    corpus writes `birth(2, Gender.MALE, 26, 27, reviewed=False,` .

    A separator is copied bare: the comments in it stay above the argument
    they were written over, and are not repeated above the new one."""
    out = list(args)
    if not out:
        return [new.with_changes(comma=cst.MaybeSentinel.DEFAULT)]
    if k == 0:
        return [new.with_changes(comma=_SPACE), *out]
    prev = out[k - 1]
    if k < len(out):
        out[k - 1] = prev.with_changes(comma=_SPACE if inline else _bare(prev.comma))
        out.insert(k, new.with_changes(comma=prev.comma))
        return out
    sep = (out[-2].comma if len(out) >= 2 and isinstance(out[-2].comma, cst.Comma)
           else _SPACE)
    out[-1] = prev.with_changes(comma=_SPACE if inline else _bare(sep))
    out.append(new.with_changes(comma=prev.comma))
    return out


def _bare(comma: cst.Comma | cst.MaybeSentinel) -> cst.Comma | cst.MaybeSentinel:
    """The separator's line break and indent, without the comments it carries."""
    if isinstance(comma, cst.Comma) and isinstance(ws := comma.whitespace_after, cst.ParenthesizedWhitespace):
        return comma.with_changes(whitespace_after=ws.with_changes(
            first_line=cst.TrailingWhitespace(), empty_lines=[]))
    return comma


def _remove_arg[T: (cst.Arg, cst.ImportAlias, cst.Element)](args: Sequence[T], k: int) -> list[T]:
    """Drop the argument at `k`; the one before takes its separator, so the
    line break (or the trailing comma) that followed it survives."""
    out = list(args)
    removed = out.pop(k)
    if k > 0:
        out[k - 1] = out[k - 1].with_changes(comma=removed.comma)
    return out


def _positional_count(call: cst.Call) -> int:
    n = 0
    for arg in call.args:
        if arg.keyword is not None or arg.star:
            break
        n += 1
    return n


def _is_none(node: cst.BaseExpression) -> bool:
    return isinstance(node, cst.Name) and node.value == "None"


# The keywords that date a vital record, written beside its days.
_DATE_PARAMS = frozenset({"b_month", "k_month", "d_month", "w_month", "k_year", "year"})


def set_param(call: cst.Call, param: str, node: cst.BaseExpression, *,
               keyword: bool = False) -> cst.Call:
    """`param` set to `node`: replaced where the call writes it, else added. A
    `keyword` value is always named — a book's defaults, and a value written
    onto a person for them, where the next positional place would be legal
    Python that nobody writes (`RecordDefaults("Маниловка")`)."""
    i, arg = find_arg(call, param)
    if arg is not None and i is not None:
        args = list(call.args)
        args[i] = arg.with_changes(value=node)
        return call.with_changes(args=args)
    s = sig.signature(_func_name(call) or "")
    p = s.param(param) if s else None
    if s is None or p is None:
        raise EditError(t("source.no_parameter", func=_func_name(call), param=param))
    count = _positional_count(call)
    positional_index = [q.name for q in s.params if q.positional].index(param) \
        if p.positional else None
    # A literal takes the next positional place (person("Иванъ", "Петровъ")); a
    # constant is named, as the corpus writes a month: birth(14, …, 27, 1,
    # b_month=Month.FEBRUARY, k_month=Month.MARCH).
    constant = isinstance(node, (cst.Name, cst.Attribute)) and not _is_none(node)
    if positional_index is not None and positional_index == count and not constant and not keyword:
        return call.with_changes(args=insert_arg(call.args, count, cst.Arg(value=node)))
    new = cst.Arg(value=node, keyword=cst.Name(param),
                  equal=cst.AssignEqual(whitespace_before=cst.SimpleWhitespace(""),
                                        whitespace_after=cst.SimpleWhitespace("")))
    if param == "reviewed" and _func_name(call) in sig.VITAL_FUNCS:
        return call.with_changes(args=insert_arg(call.args, count, new, inline=True))
    # After the last keyword that precedes it in the signature — ignoring
    # `reviewed`, which the corpus writes right after the positionals whatever
    # its place in the signature — else right after the positionals.
    at = count
    for name, k, _ in _bind(call):
        q = s.param(name)
        if k >= count and q is not None and q.order < p.order and name != "reviewed":
            at = k + 1
    # A record's date stays on its head line with the days it completes:
    # birth(14, Gender.MALE, 27, 1, b_month=Month.FEBRUARY, k_month=Month.MARCH,
    head = all(k < count or name in _DATE_PARAMS or name == "reviewed"
               for name, k, _ in _bind(call) if k < at)
    inline = _func_name(call) in sig.VITAL_FUNCS and param in _DATE_PARAMS and head
    return call.with_changes(args=insert_arg(call.args, at, new, inline=inline))


def delete_param(call: cst.Call, param: str) -> cst.Call:
    i, arg = find_arg(call, param)
    if arg is None or i is None:
        return call
    count = _positional_count(call)
    if arg.keyword is None and i < count - 1:
        # A positional with positionals after it: hold its place.
        args = list(call.args)
        args[i] = arg.with_changes(value=cst.Name("None"))
        return call.with_changes(args=args)
    call = call.with_changes(args=_remove_arg(call.args, i))
    if arg.keyword is None:
        # …and the `None`s that held places for it go too: person("Иванъ", None).
        while (count := _positional_count(call)) > 1 and _is_none(call.args[count - 1].value):
            call = call.with_changes(args=_remove_arg(call.args, count - 1))
    return call


def _quote(text: str, quote: str = '"') -> str:
    escaped = (text.replace("\\", "\\\\").replace(quote, "\\" + quote)
               .replace("\n", "\\n").replace("\t", "\\t"))
    return f"{quote}{escaped}{quote}"


@dataclass
class Imports:
    """What an edit needs of the file it writes: the names it binds, the imports it will need, and
    how it writes a surname (`surnames_named`)."""
    bound: frozenset[str]
    needed: set[tuple[str, str]] = field(default_factory=set)
    surnames_named: bool = False

    def need_function(self, func: str) -> None:
        """A function the page wrote a call to, when the file does not bind it."""
        module = sig.IMPORT_OF.get(func)
        if module is not None and func not in self.bound:
            self.needed.add((module, func))

    def need(self, code: str) -> None:
        head = code.split(".")[0]
        if head in self.bound:
            return
        constant = sig.constant_by_code().get(code)
        if constant is None:
            raise EditError(t("source.unknown_constant", code=code))
        self.needed.add((constant.module, constant.import_name))


def surnames_named(module: cst.Module) -> bool:
    """Whether the file names a person's surname (`last_name_orig=`) more often than it writes it third
    in place: a corpus writes both, a file mostly one, and a surname added follows its file."""
    named = placed = 0
    for node in _calls(module):
        if _func_name(node) != "person":
            continue
        if any(a.keyword is not None and a.keyword.value == "last_name_orig" for a in node.args):
            named += 1
        elif _positional_count(node) >= 3:
            placed += 1
    return named > placed


def _calls(module: cst.Module) -> list[cst.Call]:
    found: list[cst.Call] = []

    class Visitor(cst.CSTVisitor):
        def visit_Call(self, node: cst.Call) -> None:
            found.append(node)

    module.visit(Visitor())
    return found


def bound_names(module: cst.Module) -> frozenset[str]:
    names: set[str] = set()
    for stmt in module.body:
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        for small in stmt.body:
            if isinstance(small, cst.ImportFrom) and not isinstance(small.names, cst.ImportStar):
                for alias in small.names:
                    target = alias.asname.name if alias.asname else alias.name
                    if isinstance(target, cst.Name):
                        names.add(target.value)
            elif isinstance(small, cst.Import):
                for alias in small.names:
                    target = alias.asname.name if alias.asname else alias.name
                    names.add(module.code_for_node(target).split(".")[0])
            elif isinstance(small, cst.Assign):
                for t in small.targets:
                    if isinstance(t.target, cst.Name):
                        names.add(t.target.value)
    return frozenset(names)


def value_node(value: Mapping[str, Any], imports: Imports,
                like: cst.BaseExpression | None = None) -> cst.BaseExpression:
    kind = value.get("kind")
    if kind == "str" and _CONSTANT_NAME.match(str(value.get("value", ""))):
        # «TENTETNIKOV_M» typed or sent as text is the constant, never the string
        # "TENTETNIKOV_M": no status is written in capital Latin. A page that lost
        # track of a file's own constant once wrote exactly that string.
        code = str(value["value"])
        if code.split(".")[0] not in imports.bound and code not in sig.constant_by_code():
            raise EditError(t("source.looks_like_a_constant", code=code))
        value = {"kind": "const", "value": code}
        kind = "const"
    try:
        if kind == "str":
            # Keep the call's own quote style: a single-quoted string stays one.
            written = like.value if like is not None and isinstance(like, cst.SimpleString) else ""
            quote = "'" if written.endswith("'") and not written.endswith("'" * 3) else '"'
            return cst.SimpleString(_quote(str(value["value"]), quote))
        if kind == "int":
            return cst.parse_expression(str(int(value["value"])))
        if kind == "float":
            return cst.parse_expression(repr(float(value["value"])))
        if kind == "bool":
            return cst.Name("True" if value["value"] else "False")
        if kind == "none":
            return cst.Name("None")
        if kind == "const":
            code = str(value["value"])
            if not _DOTTED.match(code):
                raise EditError(t("source.not_a_constant_name", code=code))
            imports.need(code)
            return cst.parse_expression(code)
        if kind == "raw":
            return cst.parse_expression(str(value["code"]))
        if kind == "call":
            return _call_node(value, imports)
    except (cst.ParserSyntaxError, TypeError, KeyError) as exc:
        raise EditError(t("source.not_python", value=repr(value), error=str(exc))) from exc
    except ValueError as exc:
        if isinstance(exc, EditError):
            raise
        raise EditError(t("source.not_a_number", value=value.get("value"))) from exc
    raise EditError(t("source.unknown_value_kind", kind=kind))


def _call_node(value: Mapping[str, Any], imports: Imports) -> cst.Call:
    func = str(value.get("func"))
    s = sig.signature(func)
    if s is None or func not in _EDITABLE_CALLS:
        raise EditError(t("source.cannot_create", func=func))
    imports.need_function(func)
    given = {str(a["param"]): a["value"] for a in value.get("args", ())}
    unknown = set(given) - {p.name for p in s.params}
    if unknown:
        raise EditError(t("source.no_parameters", func=func, params=str(sorted(unknown))))
    args: list[cst.Arg] = []
    positional = [p.name for p in s.params if p.positional]
    leading = 0
    while leading < len(positional) and positional[leading] in given:
        leading += 1
    # member(18, person(…), CensusRole.SON, ref_member=9): the corpus names
    # what follows the first few, though the signature would take it in place.
    leading = min(leading, sig.WRITTEN_POSITIONALLY.get(func, leading))
    if func == "person" and imports.surnames_named:
        leading = min(leading, 2)
    for p in s.params:
        if p.name not in given:
            continue
        node = value_node(given[p.name], imports)
        if p.positional and positional.index(p.name) < leading:
            args.append(cst.Arg(value=node, comma=_SPACE))
        else:
            args.append(cst.Arg(value=node, keyword=cst.Name(p.name), comma=_SPACE,
                                equal=cst.AssignEqual(
                                    whitespace_before=cst.SimpleWhitespace(""),
                                    whitespace_after=cst.SimpleWhitespace(""))))
    if args:
        args[-1] = args[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
    return cst.Call(func=cst.Name(func), args=args)


def _apply_op(call: cst.Call, path: Sequence[str], op: Mapping[str, Any],
              imports: Imports) -> cst.Call:
    head, rest = path[0], path[1:]
    if rest and rest[0].startswith("#"):
        return _apply_list_op(call, head, rest, op, imports)
    if rest:
        i, arg = find_arg(call, head)
        if arg is None or i is None or not isinstance(arg.value, cst.Call):
            raise EditError(t("source.no_call", func=_func_name(call), head=head))
        args = list(call.args)
        args[i] = arg.with_changes(value=_apply_op(arg.value, rest, op, imports))
        return call.with_changes(args=args)
    if head == "*":
        raise EditError(t("source.splat"))
    if head == "@+":
        # A household's new member, after its last one.
        if op.get("op") != "set":
            raise EditError(t("source.household_end_only_adds"))
        return _append_vararg(call, value_node(op["value"], imports))
    if head.startswith("@"):
        if op.get("op") == "move":
            return _move_vararg(call, head, int(op["to"]))
        if op.get("op") != "delete":
            raise EditError(t("source.by_its_fields", head=head))
        i, arg = find_arg(call, head)
        if arg is None or i is None:
            raise EditError(t("source.no_member", func=_func_name(call), head=head))
        # The comment above it goes with it: the argument before takes its separator.
        return call.with_changes(args=_remove_arg(call.args, i))
    if op.get("op") == "delete":
        return delete_param(call, head)
    if op.get("op") != "set":
        raise EditError(t("source.unknown_op", op=op.get("op")))
    _, existing = find_arg(call, head)
    node = value_node(op["value"], imports, like=existing.value if existing else None)
    named = head == "last_name_orig" and _func_name(call) == "person" and imports.surnames_named
    return set_param(call, head, node, keyword=bool(op.get("keyword")) or named)


def _append_vararg(call: cst.Call, node: cst.BaseExpression) -> cst.Call:
    """`node` as the last of the call's `*varargs`, on a line of its own when
    the others are."""
    bound = _bind(call)
    last = max((k for name, k, _ in bound if name.startswith("@")), default=None)
    at = last + 1 if last is not None else _positional_count(call)
    return call.with_changes(args=insert_arg(call.args, at, cst.Arg(value=node)))


def _move_vararg(call: cst.Call, head: str, to: int) -> cst.Call:
    """The member `head` moved to be the `to`-th, as `move` moves a record
    within its group: the comment written above it goes with it, the one above
    the member after it stays there."""
    i, arg = find_arg(call, head)
    j, _ = find_arg(call, f"@{to}")
    if i is None or arg is None:
        raise EditError(t("source.no_member", func=_func_name(call), head=head))
    if j is None:
        raise EditError(t("source.no_place", func=_func_name(call), to=to))
    if i == j:
        return call
    # A comment at the end of a line rides on the separator, which stays at its
    # place: it would end up beside another member.
    members = [k for name, k, _ in _bind(call) if name.startswith("@")]
    if any(_trailing_comment(call.args[k]) for k in range(min(members) - 1, max(members) + 1)):
        raise EditError(t("source.member_comment"))
    return call.with_changes(args=_moved(call.args, i, j))


def _moved[T: (cst.Arg, cst.Element)](args: Sequence[T], i: int, j: int) -> list[T]:
    """`args` with the one at `i` moved to `j`: the comment written above it goes with it, the one
    above the argument after it stays there."""
    if i == j:
        return list(args)
    lead = _leading_lines(args, i) if i > 0 else []
    column = 0
    if i > 0:
        comma = args[i - 1].comma
        if isinstance(comma, cst.Comma) and isinstance(ws := comma.whitespace_after, cst.ParenthesizedWhitespace):
            column = len(ws.last_line.value)
    moved = insert_arg(_remove_arg(args, i), j, args[i])
    return _with_leading(moved, j, lead, column)


def _moved_in_list(lst: cst.List, k: int, to: int) -> cst.List:
    """`lst` with its element at `k` moved to `to`. Each place keeps its separator — the line
    breaks and the indent — and the values move through them, each with the comment lines written
    above it (in the separator before it, or after `[` for the first)."""
    elements = list(lst.elements)
    if k == to:
        return lst

    def lead(p: int) -> Sequence[cst.EmptyLine]:
        if p == 0:
            ws: cst.BaseParenthesizableWhitespace | None = lst.lbracket.whitespace_after
        else:
            comma = elements[p - 1].comma
            ws = comma.whitespace_after if isinstance(comma, cst.Comma) else None
        return ws.empty_lines if isinstance(ws, cst.ParenthesizedWhitespace) else ()

    order = list(range(len(elements)))
    order.insert(to, order.pop(k))
    leads = [lead(o) for o in order]
    out = [e.with_changes(value=elements[o].value) for e, o in zip(elements, order, strict=True)]

    def with_lead(ws: cst.BaseParenthesizableWhitespace, lines: Sequence[cst.EmptyLine]) -> cst.BaseParenthesizableWhitespace:
        if isinstance(ws, cst.ParenthesizedWhitespace):
            return ws.with_changes(empty_lines=list(lines))
        if lines:
            raise EditError(t("source.member_comment"))
        return ws

    for p, lines in enumerate(leads):
        if p == 0:
            lst = lst.with_changes(lbracket=lst.lbracket.with_changes(
                whitespace_after=with_lead(lst.lbracket.whitespace_after, lines)))
        else:
            comma = out[p - 1].comma
            if isinstance(comma, cst.Comma):
                out[p - 1] = out[p - 1].with_changes(comma=comma.with_changes(
                    whitespace_after=with_lead(comma.whitespace_after, lines)))
            elif lines:
                raise EditError(t("source.member_comment"))
    return lst.with_changes(elements=out)


def _trailing_comment(arg: cst.Arg | cst.Element) -> bool:
    comma = arg.comma
    return (isinstance(comma, cst.Comma) and isinstance(ws := comma.whitespace_after, cst.ParenthesizedWhitespace)
            and ws.first_line.comment is not None)


def _closing_comment(lst: cst.List) -> bool:
    """Whether a note stands after the last element's trailing comma — libcst keeps it before `]`."""
    ws = lst.rbracket.whitespace_before
    return isinstance(ws, cst.ParenthesizedWhitespace) and ws.first_line.comment is not None


def _apply_list_op(call: cst.Call, param: str, rest: Sequence[str], op: Mapping[str, Any],
                   imports: Imports) -> cst.Call:
    """An edit of one element of a list argument: «#2» the third, «#+» a new one
    at the end — which writes `relatives=[…]` when the call has none. Removing
    the last element removes the argument."""
    i, arg = find_arg(call, param)
    lst = arg.value if arg is not None and isinstance(arg.value, cst.List) else None
    if arg is not None and lst is None:
        raise EditError(t("source.not_a_list", param=param))
    key = rest[0]
    if key == "#+":
        if len(rest) != 1 or op.get("op") != "set":
            raise EditError(t("source.list_end_only_adds", param=param))
        node = value_node(op["value"], imports)
        if lst is None or arg is None or i is None:
            return set_param(call, param, cst.List([cst.Element(value=node)]))
        elements = list(lst.elements)
        last = elements[-1] if elements else None
        if last is None:
            elements = [cst.Element(value=node)]
        else:
            sep = (elements[0].comma if len(elements) >= 2 and isinstance(elements[0].comma, cst.Comma)
                   else _element_separator(call, i, param))
            if isinstance(sep.whitespace_after, cst.ParenthesizedWhitespace):
                # The list's separator, not a note that stands in it: a comment is written once.
                sep = sep.with_changes(whitespace_after=sep.whitespace_after.with_changes(
                    first_line=cst.TrailingWhitespace(), empty_lines=[]))
            closing = lst.rbracket.whitespace_before
            if _closing_comment(lst) and isinstance(sep.whitespace_after, cst.ParenthesizedWhitespace):
                # The note after the last element's trailing comma (libcst keeps it before `]`) is that
                # element's: it stays on its line, and the new element closes the list without it.
                assert isinstance(closing, cst.ParenthesizedWhitespace)
                sep = sep.with_changes(whitespace_after=sep.whitespace_after.with_changes(first_line=closing.first_line))
                lst = lst.with_changes(rbracket=lst.rbracket.with_changes(
                    whitespace_before=closing.with_changes(first_line=cst.TrailingWhitespace())))
            elements[-1] = last.with_changes(comma=sep)
            elements.append(cst.Element(value=node, comma=last.comma))
        return with_arg(call, i, arg.with_changes(value=lst.with_changes(elements=elements)))
    try:
        k = int(key[1:])
    except ValueError:
        raise EditError(t("source.not_an_element_number", key=key)) from None
    if lst is None or arg is None or i is None or not 0 <= k < len(lst.elements):
        raise EditError(t("source.no_element", param=param, key=key))
    elements = list(lst.elements)
    element = elements[k]
    if len(rest) == 1 and op.get("op") == "move":
        to = int(op["to"])
        if not 0 <= to < len(elements):
            raise EditError(t("source.no_element", param=param, key=f"#{to}"))
        # A move keeps every separator in place: a note in an element's comma — or after the last one's
        # trailing comma, before `]` — would end beside another person.
        if any(_trailing_comment(e) for e in elements[:-1]) or _closing_comment(lst):
            raise EditError(t("source.member_comment"))
        return with_arg(call, i, arg.with_changes(value=_moved_in_list(lst, k, to)))
    if len(rest) > 1:
        if not isinstance(element, cst.Element) or not isinstance(element.value, cst.Call):
            raise EditError(t("source.element_not_a_call", param=param, key=key))
        elements[k] = element.with_changes(value=_apply_op(element.value, rest[1:], op, imports))
    elif op.get("op") == "delete":
        elements = _remove_arg(elements, k)
        if not elements:
            return delete_param(call, param)
    elif op.get("op") == "set" and isinstance(element, cst.Element):
        elements[k] = element.with_changes(value=value_node(op["value"], imports))
    else:
        raise EditError(t("source.unknown_op", op=op.get("op")))
    return with_arg(call, i, arg.with_changes(value=lst.with_changes(elements=elements)))


def with_arg(call: cst.Call, i: int, arg: cst.Arg) -> cst.Call:
    args = list(call.args)
    args[i] = arg
    return call.with_changes(args=args)


def _element_separator(call: cst.Call, i: int, param: str) -> cst.Comma:
    """Between a list's first element and a second: on the next line under the
    first, when `param=` stands on a line of its own — else a space."""
    if i == 0:
        return _SPACE
    before = call.args[i - 1].comma
    if not isinstance(before, cst.Comma):
        return _SPACE
    ws = before.whitespace_after
    if not isinstance(ws, cst.ParenthesizedWhitespace):
        return _SPACE
    column = ws.last_line.value + " " * (len(param) + 2)     # past «relatives=[»
    return cst.Comma(whitespace_after=cst.ParenthesizedWhitespace(
        first_line=cst.TrailingWhitespace(), empty_lines=[], indent=ws.indent,
        last_line=cst.SimpleWhitespace(column)))


def apply_ops(call: cst.Call, ops: Iterable[Mapping[str, Any]], imports: Imports) -> cst.Call:
    for op in ops:
        path = [str(p) for p in op.get("path", ())]
        if not path:
            raise EditError(t("source.empty_path"))
        call = _apply_op(call, path, op, imports)
    return call


def _review_edits(found: Sequence[_Found], target: _Found
                  ) -> list[tuple[cst.Call, Callable[[cst.Call], cst.Call]]]:
    """The flag changes that mark `target` reviewed, as (original node, rewrite).

    Modelled before it is written: own flags and holder flags are set in a small
    table, the holders the change completes are cleared, and every explicit
    `True` the result has made redundant is dropped — so the file ends as it
    would have been written had the whole leaf been read in one sitting.
    """
    holders = {id(f.node): _holders(f) for f in found}
    own0 = {id(f.node): _kw_bool(f.node, "reviewed") for f in found}
    hold0 = {id(h): _kw_bool(h, "reviewed") for hs in holders.values() for h in hs}
    own, hold = dict(own0), dict(hold0)

    def resolve(f: _Found) -> bool:
        if own[id(f.node)] is not None:
            return bool(own[id(f.node)])
        for h in holders[id(f.node)]:
            if hold[id(h)] is not None:
                return bool(hold[id(h)])
        return True

    own[id(target.node)] = True
    touched = [target]
    for h in holders[id(target.node)]:
        if hold[id(h)] is not False:
            continue
        members = [f for f in found if any(x is h for x in holders[id(f.node)])]
        if not all(resolve(m) for m in members):
            break
        hold[id(h)] = None
        touched.extend(members)
    for f in touched:
        if own[id(f.node)] is True:
            own[id(f.node)] = None
            if not resolve(f):
                own[id(f.node)] = True

    edits: list[tuple[cst.Call, Callable[[cst.Call], cst.Call]]] = []
    seen: set[int] = set()
    for f in touched:
        key = id(f.node)
        if key in seen or own[key] == own0[key]:
            continue
        seen.add(key)
        edits.append((f.node, _drop_reviewed if own[key] is None else _set_reviewed))
    for h in {id(x): x for f in found for x in holders[id(f.node)]}.values():
        if hold[id(h)] != hold0[id(h)]:
            edits.append((h, _drop_reviewed))
    return edits


def _drop_reviewed(call: cst.Call) -> cst.Call:
    return delete_param(call, "reviewed")


def _set_reviewed(call: cst.Call) -> cst.Call:
    return set_param(call, "reviewed", cst.Name("True"))


def _unreviewed(target: _Found) -> Callable[[cst.Call], cst.Call]:
    """The rewrite that holds `target` unreviewed: its own flag dropped where a page or a file around it holds
    `reviewed=False` already (an explicit `True` under it was what read it), else its own `reviewed=False`."""
    inherited = next((v for h in _holders(target) if (v := _kw_bool(h, "reviewed")) is not None), None)

    def rewrite(call: cst.Call) -> cst.Call:
        if inherited is False:
            return delete_param(call, "reviewed")
        return set_param(call, "reviewed", cst.Name("False"))
    return rewrite


class _Rewriter(cst.CSTTransformer):
    def __init__(self, edits: Mapping[int, list[Callable[[cst.Call], cst.Call]]]) -> None:
        self.edits = edits

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.BaseExpression:
        for fn in self.edits.get(id(original_node), ()):
            updated_node = fn(updated_node)
        return updated_node


def apply(source: str, ordinal: int, expected_sha: str,
          ops: Sequence[Mapping[str, Any]] = (), mark_reviewed: bool = False,
          on_geni: Iterable[str] | None = None, *, unreview: bool = False) -> str:
    """`source` with the record at `ordinal` edited by `ops` and, when asked,
    marked reviewed — or, with `unreview`, marked unreviewed again: the record's
    own call writes `reviewed=False`, or drops its `reviewed=True` where a page or
    a file around it holds `reviewed=False` (an edit someone other than the owner
    made is the owner's to read again; `ops` may not touch the flag then). `unreview` leaves a record that is unreviewed
    already as it is, and touches no ratchet line: the caller decides where an
    unreviewed record may stand. Raises `Stale` when the record is not the one
    the caller saw, `EditError` when an edit cannot be written (both flags at
    once among them).

    With `on_geni` (the file's ratchet fingerprints) an edit of a record that is
    on Geni and still unreviewed is refused unless it is marked reviewed with
    it: the ratchet would hold the edited record, and its live profiles would
    leave the tree. A preview passes no `on_geni` — nothing is written."""
    module = cst.parse_module(source)
    found = _collect(module)
    if not 0 <= ordinal < len(found):
        raise Stale(t("source.gone", ordinal=ordinal))
    target = found[ordinal]
    if sha(module.code_for_node(target.node)) != expected_sha:
        raise Stale(t("source.stale"))
    if mark_reviewed and unreview:
        raise EditError(t("source.review_and_unreview"))
    if unreview and any([str(p) for p in op.get("path", ())][:1] == ["reviewed"] for op in ops):
        raise EditError(t("source.review_and_unreview"))      # the flag is `unreview`'s alone
    if on_geni is not None and ops and not mark_reviewed and struck(source, ordinal, on_geni):
        raise EditError(t("source.listed_needs_review"))

    imports = Imports(bound_names(module), surnames_named=surnames_named(module))
    edits: dict[int, list[Callable[[cst.Call], cst.Call]]] = {}
    if ops:
        def edit(call: cst.Call) -> cst.Call:
            return apply_ops(call, ops, imports)
        edits.setdefault(id(target.node), []).append(edit)
    if mark_reviewed:
        if not _state(target)[0]:
            raise EditError(t("source.reviewed_already"))
        for node, fn in _review_edits(found, target):
            edits.setdefault(id(node), []).append(fn)
    if unreview and not _state(target)[0]:
        edits.setdefault(id(target.node), []).append(_unreviewed(target))
    if not edits:
        return source
    new = module.visit(_Rewriter(edits))
    for mod, name in sorted(imports.needed):
        new = add_import(new, mod, name)
    still = _used_names(new)
    return drop_imports(new, {n for n in _used_names(module) if n not in still}).code


def apply_batch(source: str, ops: Mapping[int, Sequence[Mapping[str, Any]]]) -> str:
    """`source` with each record at an ordinal of `ops` edited by its ops — the
    many records a book's defaults change reaches, in one pass, with one edit of
    the imports. No hash, no flag, no ratchet: the caller holds the file as it
    read it, and decides what may be written."""
    if not any(ops.values()):
        return source
    module = cst.parse_module(source)
    found = _collect(module)
    imports = Imports(bound_names(module), surnames_named=surnames_named(module))
    edits: dict[int, list[Callable[[cst.Call], cst.Call]]] = {}

    def editor(record_ops: Sequence[Mapping[str, Any]]) -> Callable[[cst.Call], cst.Call]:
        def edit(call: cst.Call) -> cst.Call:
            return apply_ops(call, record_ops, imports)
        return edit

    for ordinal, record_ops in ops.items():
        if not 0 <= ordinal < len(found):
            raise EditError(t("source.gone", ordinal=ordinal))
        if record_ops:
            edits.setdefault(id(found[ordinal].node), []).append(editor(record_ops))
    new = module.visit(_Rewriter(edits))
    for mod, name in sorted(imports.needed):
        new = add_import(new, mod, name)
    still = _used_names(new)
    return drop_imports(new, {n for n in _used_names(module) if n not in still}).code


# ---------------------------------------------------------------- a new record

# The record a metric book's record set takes: a new entry of the book.
_NEW_RECORD = {"birth_records": "birth", "marriage_records": "marriage", "death_records": "death"}


def insert(source: str, anchor: int, anchor_sha: str, where: str,
           ops: Sequence[Mapping[str, Any]] = (), mark_reviewed: bool = False,
           on_geni: Iterable[str] | None = None, draft: bool = False,
           base: str | None = None) -> tuple[str, int]:
    """`source` with a new record written next to the one at `anchor` — right
    `after` it or right `before` it, in the same container — and the new
    record's ordinal. Every later record's ordinal moves up by one.

    The record starts as its neighbour suggests: the next number (the previous
    one before it), the neighbour's sex and its own лист; `ops` are the page's
    edits of that start, applied as on any record. It is laid out as its
    neighbour is. «Сохранить» holds it — by the flag of a held leaf around it,
    else by its own `reviewed=False` —, «Вычитано» (`mark_reviewed`) writes it
    read. A `draft` (what the page shows before anything is written) may have
    no number yet; a record written must. `base` — a draft sent to its place
    (`draft_code`) — starts from that call instead of the neighbour's
    suggestion: what was typed into it at its old place."""
    if where not in ("after", "before"):
        raise EditError(t("source.unknown_where_new", where=where))
    module = cst.parse_module(source)
    found = _collect(module)
    if not 0 <= anchor < len(found):
        raise Stale(t("source.gone", ordinal=anchor))
    near = found[anchor]
    if sha(module.code_for_node(near.node)) != anchor_sha:
        raise Stale(t("source.stale"))
    func = _NEW_RECORD.get(next((_func_name(c) or "" for c in near.ancestors
                                 if _func_name(c) in sig.CONTAINER_FUNCS), ""))
    if func is None:
        raise EditError(t("source.new_only_in_a_metric_book"))
    container = near.ancestors[0]
    k = next((i for i, a in enumerate(container.args) if a.value is near.node), None)
    if k is None:
        raise EditError(t("source.not_in_its_group_new"))
    at = k + 1 if where == "after" else k

    imports = Imports(bound_names(module), surnames_named=surnames_named(module))
    s = sig.signature(func)
    assert s is not None
    order = {p.name: p.order for p in s.params}
    # In the order of the signature, whatever order the page sent them in: the
    # days take their places after the number and sex, the people follow.
    start = _skeleton(near, func, where, module) if base is None else cst.parse_expression(base)
    if not isinstance(start, cst.Call) or _func_name(start) != func:
        raise EditError(t("source.new_not_a_call", func=func))
    record = apply_ops(start,
                       sorted(ops, key=lambda op: order.get(str(op.get("path", [""])[0]), len(order))),
                       imports)
    _, number = find_arg(record, "record_num")
    if not draft and (number is None or _is_none(number.value)):
        raise EditError(t("source.new_no_number"))

    def place(call: cst.Call) -> cst.Call:
        return call.with_changes(args=insert_arg(call.args, at, cst.Arg(value=record)))

    new = module.visit(_Rewriter({id(container): [place]}))
    for mod, name in sorted(imports.needed):
        new = add_import(new, mod, name)
    still = _used_names(new)
    text = drop_imports(new, {n for n in _used_names(module) if n not in still}).code

    ordinal = anchor + (1 if where == "after" else 0)
    held = next((not v for h in _holders(near) if (v := _kw_bool(h, "reviewed")) is not None), False)
    written = _collect(cst.parse_module(text))[ordinal].node
    if mark_reviewed and held:
        text = apply(text, ordinal, sha(cst.Module([]).code_for_node(written)), (), True, on_geni)
    elif not mark_reviewed and not held:
        text = apply(text, ordinal, sha(cst.Module([]).code_for_node(written)),
                     [{"op": "set", "path": ["reviewed"], "value": {"kind": "bool", "value": False}}])
    return _lay_out_new(text, ordinal, anchor + (0 if where == "after" else 1)), ordinal


def move(source: str, ordinal: int, expected_sha: str, anchor: int, anchor_sha: str, where: str,
         on_geni: Iterable[str] | None = None, *, keep: bool = True) -> tuple[str, int]:
    """`source` with the record at `ordinal` moved right `after` or right
    `before` the one at `anchor`, into its group — and its new ordinal.

    Its own comments go with it, shifted to its new column. What it says does
    not move: a month or a year its old section gave it, and a лист its old
    `page(…)` gave it, are written on it when its new group would give
    another; a month or a лист it writes that its new group gives anyway is
    taken off. Its review state stays too: held by its old leaf's flag, it
    takes its own `reviewed=False` where nothing holds it; read, it takes an
    explicit `True` inside a held leaf; a flag of its own its new place makes
    redundant goes.

    A record on Geni and unreviewed (`on_geni`) does not move: its fingerprint
    takes in the calls around it, and the ratchet would hold it.

    Without `keep` — a record the page is adding, sent to its place — nothing
    its old place gave it goes with it: its month and лист were only where the
    reader opened it, and its new place gives them; what was typed into it
    stays."""
    if where not in ("after", "before"):
        raise EditError(t("source.unknown_where", where=where))
    if anchor == ordinal:
        raise EditError(t("source.already_here"))
    wrapper = MetadataWrapper(cst.parse_module(source), unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    module = wrapper.module
    found = _collect(module)
    for i, expected in ((ordinal, expected_sha), (anchor, anchor_sha)):
        if not 0 <= i < len(found):
            raise Stale(t("source.gone", ordinal=i))
        if sha(module.code_for_node(found[i].node)) != expected:
            raise Stale(t("source.stale"))
    if on_geni is not None and struck(source, ordinal, on_geni):
        raise EditError(t("source.listed_move"))
    rec, near = found[ordinal], found[anchor]
    home, there = rec.ancestors[0], near.ancestors[0]
    k, ka = _arg_index(home, rec.node), _arg_index(there, near.node)
    if k is None or ka is None or k == 0:
        raise EditError(t("source.not_in_its_group_move"))

    imports = Imports(bound_names(module), surnames_named=surnames_named(module))
    call = _keep_review(rec, near, _keep_dates(rec, near, module, imports)) if keep else rec.node
    delta = positions[near.node].start.column - positions[rec.node].start.column
    call = cast(cst.Call, call.visit(_Shift(delta)))
    lead = [_shift_line(line, delta) for line in _leading_lines(home.args, k)]
    moved = home.args[k].with_changes(value=call)
    at = ka + 1 if where == "after" else ka
    column = positions[near.node].start.column

    def put(args: Sequence[cst.Arg], at: int) -> list[cst.Arg]:
        return _with_leading(insert_arg(args, at, moved), at, lead, column)

    def cut(c: cst.Call) -> cst.Call:
        return c.with_changes(args=_remove_arg(c.args, k))

    def cut_and_put(c: cst.Call) -> cst.Call:
        return c.with_changes(args=put(_remove_arg(c.args, k), at - (1 if at > k else 0)))

    def place(c: cst.Call) -> cst.Call:
        return c.with_changes(args=put(c.args, at))

    edits: dict[int, list[Callable[[cst.Call], cst.Call]]] = (
        {id(home): [cut_and_put]} if home is there else {id(home): [cut], id(there): [place]})
    new = module.visit(_Rewriter(edits))
    for mod, name in sorted(imports.needed):
        new = add_import(new, mod, name)
    return new.code, anchor - (1 if anchor > ordinal else 0) + (1 if where == "after" else 0)


def draft_code(source: str, ordinal: int) -> str:
    """The call of the record at `ordinal` as a draft's `base`: without its
    review flag, which the place it is written at decides."""
    found = _collect(cst.parse_module(source))
    return cst.Module([]).code_for_node(delete_param(found[ordinal].node, "reviewed"))


def remove(source: str, ordinal: int, expected_sha: str) -> str:
    """`source` without the record at `ordinal` and the comments above it.
    A `page(…)` or a `*_month(…)` section it leaves empty goes with it, flag
    and all — an empty group is legal Python and a trap for the next reader —
    up to the record set, which stays. The names only it used go from the
    imports."""
    module = cst.parse_module(source)
    found = _collect(module)
    if not 0 <= ordinal < len(found):
        raise Stale(t("source.gone", ordinal=ordinal))
    rec = found[ordinal]
    if sha(module.code_for_node(rec.node)) != expected_sha:
        raise Stale(t("source.stale"))
    node: cst.Call = rec.node
    home = rec.ancestors[0]
    if _arg_index(home, node) is None:
        raise EditError(t("source.not_in_its_group_remove"))
    for parent in rec.ancestors[1:]:
        if _func_name(home) in sig.CONTAINER_FUNCS or _contents(home) != [node]:
            break
        node, home = home, parent
    k = _arg_index(home, node)
    if k is None or k == 0:
        raise EditError(t("source.not_in_its_group_remove"))

    def cut(c: cst.Call) -> cst.Call:
        return c.with_changes(args=_remove_arg(c.args, k))

    new = module.visit(_Rewriter({id(home): [cut]}))
    still = _used_names(new)
    return drop_imports(new, {n for n in _used_names(module) if n not in still}).code


def _contents(group: cst.Call) -> list[cst.BaseExpression]:
    """What a group holds: its records and the groups splatted into it — not
    its own лист, month or flag."""
    return [a.value for a in group.args
            if a.star or (isinstance(a.value, cst.Call) and _func_name(a.value) in sig.RECORD_FUNCS)]


def _arg_index(container: cst.Call, node: cst.Call) -> int | None:
    return next((i for i, a in enumerate(container.args) if a.value is node), None)


def _section(found: _Found, module: cst.Module) -> tuple[int | None, int | None]:
    """The month and year the `*_month(…)` / `*_month_year(…)` section around a
    record gives it."""
    for call in found.ancestors:
        name = _func_name(call) or ""
        if name.endswith(("_month", "_month_year")):
            year = _literal(call, "year", module) if name.endswith("_month_year") else None
            return _month(_literal(call, "month", module)), year if isinstance(year, int) else None
    return None, None


def _wrapper_page(found: _Found, module: cst.Module) -> str | None:
    for call in found.ancestors:
        if _func_name(call) == "page":
            num = _literal(call, "num", module)
            return None if num is None else str(num)
    return None


def _section_gives(func: str, call: cst.Call, month: int | None, year: int | None,
                   module: cst.Module) -> dict[str, str]:
    """What a section of `month` and `year` gives a record — parameter → code —
    as `birth_month_year` and its kin copy it onto the records they hold: a
    christening day before the birth day spills into the next month (and a
    December one into the next year)."""
    gives: dict[str, str] = {}
    if month is not None:
        name = f"Month.{calendar.Month(month).name}"
        if func in ("birth", "christening"):
            gives["b_month"] = name
            b_day, k_day = _literal(call, "b_day", module), _literal(call, "k_day", module)
            if isinstance(b_day, int) and isinstance(k_day, int) and k_day < b_day:
                gives["k_month"] = f"Month.{calendar.Month(month % 12 + 1).name}"
                if month == 12 and year is not None:
                    gives["k_year"] = str(year + 1)
            else:
                gives["k_month"] = name
        elif func == "death":
            gives["d_month"] = gives["b_month"] = name
        elif func == "marriage":
            gives["w_month"] = name
    if year is not None:
        gives["year"] = str(year)
    s = sig.signature(func)
    return {p: v for p, v in gives.items() if s is not None and s.param(p) is not None}


def _keep_dates(rec: _Found, near: _Found, module: cst.Module, imports: Imports) -> cst.Call:
    """The record's call with what its old section and leaf gave it written on
    it, where its new group gives other — and what its new group gives anyway
    taken off."""
    call = rec.node
    old = _section_gives(rec.func, call, *_section(rec, module), module)
    new = _section_gives(rec.func, call, *_section(near, module), module)
    for param, code in old.items():
        if find_arg(call, param)[1] is None and new.get(param) != code:
            if code.startswith("Month."):
                imports.need(code)
            call = set_param(call, param, cst.parse_expression(code))
    for param, code in new.items():
        arg = find_arg(call, param)[1]
        if arg is not None and cst.Module([]).code_for_node(arg.value).strip() == code:
            call = delete_param(call, param)
    old_leaf, new_leaf = _wrapper_page(rec, module), _wrapper_page(near, module)
    own = find_arg(call, "page")[1]
    if own is None and old_leaf is not None and old_leaf != new_leaf:
        call = set_param(call, "page", cst.SimpleString(_quote(old_leaf)), keyword=True)
    elif (own is not None and new_leaf is not None and isinstance(own.value, cst.SimpleString)
          and own.value.evaluated_value == new_leaf):
        call = delete_param(call, "page")
    return call


def _keep_review(rec: _Found, near: _Found, call: cst.Call) -> cst.Call:
    """The call with the flag its new place needs to keep it held or read."""
    pending = _state(rec)[0]
    inherited = next((v for h in _holders(near) if (v := _kw_bool(h, "reviewed")) is not None), None)
    want = (None if inherited is False else False) if pending else (True if inherited is False else None)
    own = _kw_bool(call, "reviewed")
    if want is None:
        return call if own is None else delete_param(call, "reviewed")
    return call if own is want else set_param(call, "reviewed", cst.Name(str(want)))


class _Shift(cst.CSTTransformer):
    """Every line break inside a call moved `delta` columns: a record taken to
    a group indented otherwise keeps its own layout."""

    def __init__(self, delta: int) -> None:
        self.delta = delta

    @override
    def leave_ParenthesizedWhitespace(self, original_node: cst.ParenthesizedWhitespace,
                                      updated_node: cst.ParenthesizedWhitespace) -> cst.ParenthesizedWhitespace:
        return updated_node.with_changes(last_line=_widen(updated_node.last_line, self.delta))

    @override
    def leave_EmptyLine(self, original_node: cst.EmptyLine, updated_node: cst.EmptyLine) -> cst.EmptyLine:
        return _shift_line(updated_node, self.delta)


def _widen(ws: cst.SimpleWhitespace, delta: int) -> cst.SimpleWhitespace:
    if not ws.value or ws.value.strip(" "):
        return ws
    return cst.SimpleWhitespace(" " * max(1, len(ws.value) + delta))


def _shift_line(line: cst.EmptyLine, delta: int) -> cst.EmptyLine:
    return line if line.comment is None else line.with_changes(whitespace=_widen(line.whitespace, delta))


def _leading_lines(args: Sequence[cst.Arg] | Sequence[cst.Element], k: int) -> list[cst.EmptyLine]:
    """The comment (and blank) lines written above the argument at `k`: they
    sit in the separator after the one before it."""
    comma = args[k - 1].comma
    if isinstance(comma, cst.Comma) and isinstance(ws := comma.whitespace_after, cst.ParenthesizedWhitespace):
        return list(ws.empty_lines)
    return []


def _with_leading[T: (cst.Arg, cst.Element)](args: list[T], at: int, lead: Sequence[cst.EmptyLine], column: int) -> list[T]:
    """`args` with `lead` written above the argument at `at`."""
    if not lead or at == 0:
        return args
    prev = args[at - 1]
    comma = prev.comma if isinstance(prev.comma, cst.Comma) else cst.Comma()
    ws = comma.whitespace_after
    if isinstance(ws, cst.ParenthesizedWhitespace):
        ws = ws.with_changes(empty_lines=[*lead, *ws.empty_lines])
    else:
        ws = cst.ParenthesizedWhitespace(first_line=cst.TrailingWhitespace(), empty_lines=list(lead),
                                         indent=True, last_line=cst.SimpleWhitespace(" " * column))
    args[at - 1] = prev.with_changes(comma=comma.with_changes(whitespace_after=ws))
    return args


def _skeleton(near: _Found, func: str, where: str, module: cst.Module) -> cst.Call:
    """The record a new entry starts as: the number after the neighbour's (or
    before it), the neighbour's sex, and the лист it writes of its own."""
    _, num = find_arg(near.node, "record_num")
    number = None
    if num is not None and isinstance(num.value, cst.Integer):
        n = int(num.value.value) + (1 if where == "after" else -1)
        number = n if n >= 1 else None
    args = [str(number)]
    s = sig.signature(func)
    if s is not None and s.param("gender") is not None:
        _, gender = find_arg(near.node, "gender")
        args.append(module.code_for_node(gender.value) if gender is not None else "Gender.MALE")
    _, page = find_arg(near.node, "page")
    if page is not None:
        args.append(f"page={module.code_for_node(page.value)}")
    call = cst.parse_expression(f"{func}({', '.join(args)})")
    assert isinstance(call, cst.Call)
    return call


def _lay_out_new(source: str, ordinal: int, like: int) -> str:
    """`source` with the record at `ordinal` laid out as the one at `like` is."""
    wrapper = MetadataWrapper(cst.parse_module(source), unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    found = _collect(wrapper.module)
    record, model = found[ordinal].node, found[like].node
    column = positions[record].start.column

    def lay_out(call: cst.Call) -> cst.Call:
        return _lay_out(call, model, column)

    return wrapper.module.visit(_Rewriter({id(record): [lay_out]})).code


def _lay_out(call: cst.Call, like: cst.Call, column: int) -> cst.Call:
    """`call` written as `like` is. One argument per line when `like` opens its
    parenthesis on a line of its own (the importer's books, Заманиловка 1850);
    else as the corpus writes a record by hand — the number, sex, days, months
    and flag on the head line, every other argument on a line of its own under
    the first, the parenthesis closed on the last."""
    args = list(call.args)
    if not args:
        return call
    blank = cst.SimpleWhitespace("")
    if isinstance(opening := like.whitespace_before_args, cst.ParenthesizedWhitespace):
        line = opening.with_changes(first_line=cst.TrailingWhitespace(), empty_lines=[])
        last = like.args[-1] if like.args else None
        out = [a.with_changes(comma=cst.Comma(whitespace_after=line), whitespace_after_arg=blank)
               for a in args[:-1]]
        out.append(args[-1].with_changes(
            comma=_bare(last.comma) if last is not None else cst.MaybeSentinel.DEFAULT,
            whitespace_after_arg=last.whitespace_after_arg if last is not None else blank))
        return call.with_changes(whitespace_before_args=line, args=out)
    under = cst.Comma(whitespace_after=cst.ParenthesizedWhitespace(
        first_line=cst.TrailingWhitespace(), empty_lines=[], indent=True,
        last_line=cst.SimpleWhitespace(" " * (column + len(_func_name(call) or "") + 1))))
    names = [name for name, _, _ in _bind(call)]
    head = 0
    while head < len(args) and (args[head].keyword is None or names[head] in _DATE_PARAMS
                                or names[head] == "reviewed"):
        head += 1
    out = []
    for i, a in enumerate(args):
        comma: cst.Comma | cst.MaybeSentinel = (cst.MaybeSentinel.DEFAULT if i == len(args) - 1
                                                else _SPACE if i + 1 < head else under)
        out.append(a.with_changes(comma=comma, whitespace_after_arg=blank))
    return call.with_changes(whitespace_before_args=blank, args=out)


def locate(source: str, line: int, col: int) -> tuple[int, list[str]] | None:
    """The record and the editor's path of the argument that starts at (1-based
    `line`, 0-based character `col`) — where a linter's fix points — or None.

    The path is the one `apply` takes: «father», «@3», «relatives», «#0», then
    the parameter. An argument is found by its own start (the keyword of a
    keyword argument) or its value's (a positional one)."""
    wrapper = MetadataWrapper(cst.parse_module(source), unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)

    def at(node: cst.CSTNode) -> bool:
        start = positions[node].start
        return (start.line, start.column) == (line, col)

    def walk(call: cst.Call, path: list[str]) -> list[str] | None:
        for name, _, arg in _bind(call):
            if name == "*":
                continue
            if at(arg) or at(arg.value):
                return [*path, name]
            value = arg.value
            if isinstance(value, cst.Call) and _func_name(value) in _EDITABLE_CALLS:
                if (found := walk(value, [*path, name])) is not None:
                    return found
            elif isinstance(value, cst.List):
                for k, element in enumerate(value.elements):
                    if isinstance(element, cst.Element) and isinstance(element.value, cst.Call):
                        if (found := walk(element.value, [*path, name, f"#{k}"])) is not None:
                            return found
        return None

    for ordinal, found_record in enumerate(_collect(wrapper.module)):
        where = positions[found_record.node]
        if not where.start.line <= line <= where.end.line:
            continue
        if (path := walk(found_record.node, [])) is not None:
            return ordinal, path
    return None


class _Uses(cst.CSTVisitor):
    def __init__(self) -> None:
        self.names: Counter[str] = Counter()

    def visit_Name(self, node: cst.Name) -> None:
        self.names[node.value] += 1


def _used_names(module: cst.Module) -> Counter[str]:
    """Every name the module mentions outside its top-level imports."""
    uses = _Uses()
    for stmt in module.body:
        if not (isinstance(stmt, cst.SimpleStatementLine)
                and all(isinstance(small, (cst.Import, cst.ImportFrom)) for small in stmt.body)):
            stmt.visit(uses)
    return uses.names


def drop_imports(module: cst.Module, gone: Collection[str]) -> cst.Module:
    """The `from … import` names in `gone` removed — the constants an edit
    replaced and nothing else uses (`status=WIDOW` rewritten as its words). Only
    those: an import unused before the edit is the file's business, not ours."""
    if not gone:
        return module
    body: list[cst.BaseStatement | cst.BaseCompoundStatement] = []
    carry: list[cst.EmptyLine] = []     # the blank lines and comments above a dropped line
    for stmt in module.body:
        if isinstance(stmt, cst.SimpleStatementLine) and len(stmt.body) == 1 \
                and isinstance(small := stmt.body[0], cst.ImportFrom) \
                and not isinstance(small.names, cst.ImportStar):
            names = list(small.names)
            for k in reversed(range(len(names))):
                alias = names[k]
                bound = alias.asname.name if alias.asname is not None else alias.name
                if isinstance(bound, cst.Name) and bound.value in gone:
                    names = _remove_arg(names, k)
            if not names:
                carry.extend(stmt.leading_lines)
                continue
            if len(names) != len(small.names):
                rewrapped = _rewrapped(module, stmt, small, [module.code_for_node(a.name) for a in names])
                if rewrapped is not None:
                    stmt = rewrapped
                else:
                    # The last name keeps no trailing comma a one-line import never had.
                    if small.lpar is None:
                        names[-1] = names[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
                    stmt = stmt.with_changes(body=[small.with_changes(names=names)])
        if carry:
            stmt = stmt.with_changes(leading_lines=[*carry, *stmt.leading_lines])
            carry = []
        body.append(stmt)
    return module.with_changes(body=body)


def _rewrapped(module: cst.Module, stmt: cst.SimpleStatementLine, small: cst.ImportFrom,
               names: list[str]) -> cst.SimpleStatementLine | None:
    """`stmt`, a sorted `from … import` with no comment in it and no `as`, written again with
    `names` as `format_import` writes it (its leading lines, comments above it too, kept); None
    for any other import."""
    if isinstance(small.names, cst.ImportStar):
        return None
    keys = [module.code_for_node(a.name) for a in small.names]
    if (not keys or keys != sorted(keys) or small.module is None or small.relative or len(stmt.body) != 1
            or "#" in module.code_for_node(stmt.with_changes(leading_lines=[]))
            or any(a.asname is not None for a in small.names)):
        return None
    line = cst.parse_statement(format_import(module.code_for_node(small.module), names) + "\n")
    assert isinstance(line, cst.SimpleStatementLine)
    return line.with_changes(leading_lines=stmt.leading_lines)


_IMPORT_WIDTH = 100


def format_import(module: str, names: Iterable[str]) -> str:
    """`from module import a, b`, the names sorted — on one line up to 100 characters, else
    in parentheses, filled greedily, each line ending in a comma up to 100 characters and
    going on under the first name: as the corpus's imports are wrapped."""
    ordered = sorted(names)
    line = f"from {module} import {', '.join(ordered)}"
    if len(line) <= _IMPORT_WIDTH:
        return line
    head = f"from {module} import ("
    lines, current = [], head
    for k, name in enumerate(ordered):
        piece = name + (")" if k == len(ordered) - 1 else ",")
        candidate = current + ("" if current == head else " ") + piece
        if len(candidate) > _IMPORT_WIDTH and current != head and current.strip():
            lines.append(current)
            current = " " * len(head) + piece
        else:
            current = candidate
    lines.append(current)
    return "\n".join(lines)


def dsl_form(module: cst.Module) -> Literal["v1"]:
    """The form a DSL file imports the DSL in — v1, the facade `verso.ru.dsl`, its catalogs and
    `corpus.statuses`; a file importing `geni.*`, DSL v0, is refused: its writer would
    leave the file half in each form."""
    for stmt in module.body:
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        for small in stmt.body:
            if isinstance(small, cst.ImportFrom) and small.module is not None and not small.relative:
                names = [module.code_for_node(small.module)]
            elif isinstance(small, cst.Import):
                names = [module.code_for_node(a.name) for a in small.names]
            else:
                continue
            if any(name == "geni" or name.startswith("geni.") for name in names):
                raise EditError(t("source.dsl_v0"))
    return "v1"


def add_import(module: cst.Module, mod: str, name: str) -> cst.Module:
    """`from mod import name`, added to the file's own import from that module when it has
    one — in alphabetical place when that import is sorted, and then wrapped again as
    `format_import` wraps it unless a comment stands in it — else as a new line in its place
    among the imports (`import_rank`), under the module's docstring in a file with none. A DSL
    v0 file is refused (`dsl_form`)."""
    dsl_form(module)
    body = list(module.body)
    last_import = -1
    for i, stmt in enumerate(body):
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        for j, small in enumerate(stmt.body):
            if isinstance(small, (cst.Import, cst.ImportFrom)):
                last_import = i
            if (isinstance(small, cst.ImportFrom) and small.module is not None
                    and not isinstance(small.names, cst.ImportStar)
                    and module.code_for_node(small.module) == mod and not small.relative):
                names = list(small.names)
                keys = [module.code_for_node(a.name) for a in names]
                at = len(names)
                if keys == sorted(keys):
                    at = next((k for k, key in enumerate(keys) if key > name), len(names))
                rewrapped = _rewrapped(module, stmt, small, [*keys, name])
                if rewrapped is not None:
                    body[i] = rewrapped
                    return module.with_changes(body=body)
                names = insert_arg(names, at, cst.ImportAlias(name=cst.Name(name)))
                smalls = list(stmt.body)
                smalls[j] = small.with_changes(names=names)
                body[i] = stmt.with_changes(body=smalls)
                return module.with_changes(body=body)
    line = cst.parse_statement(f"from {mod} import {name}\n")
    if last_import < 0 and body and is_docstring(body[0]):     # the first import: under the docstring
        last_import = 0
    at = next((i for i, stmt in enumerate(body[:last_import + 1]) if _import_rank(stmt, module) > import_rank(mod)),
              last_import + 1)
    if at <= last_import:       # before an import: the lines above it stay above the head
        line = line.with_changes(leading_lines=body[at].leading_lines)
        body[at] = body[at].with_changes(leading_lines=[])
    body.insert(at, line)
    return module.with_changes(body=body)


# The modules of DSL v1 in the order a file imports them, as `verso upgrade-dsl` writes them:
# the corpus's statuses (`<corpus>.statuses`, a module outside the library) first, then the
# facade and its catalogs.
DSL_IMPORT_ORDER = ("verso.ru.dsl", "verso.ru.dsl.causes_of_death", "verso.ru.dsl.marital_status",
                    "verso.ru.dsl.statuses")


def import_rank(mod: str) -> int:
    """Where a `from mod import …` line stands among a DSL file's imports."""
    if mod in DSL_IMPORT_ORDER:
        return DSL_IMPORT_ORDER.index(mod) + 1
    return len(DSL_IMPORT_ORDER) + 1 if mod.startswith("verso.") or not mod.endswith(".statuses") else 0


def is_docstring(stmt: cst.CSTNode) -> bool:
    """A module's docstring: a string standing alone on its line."""
    return (isinstance(stmt, cst.SimpleStatementLine) and len(stmt.body) == 1
            and isinstance(stmt.body[0], cst.Expr) and isinstance(stmt.body[0].value, cst.SimpleString))


def _import_rank(stmt: cst.CSTNode, module: cst.Module) -> int:
    if (isinstance(stmt, cst.SimpleStatementLine) and len(stmt.body) == 1
            and isinstance(small := stmt.body[0], cst.ImportFrom) and small.module is not None and not small.relative):
        return import_rank(module.code_for_node(small.module))
    return -1
