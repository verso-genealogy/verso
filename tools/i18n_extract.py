"""Move a package's messages into its catalog: a message moves verbatim or not at all.

    python -m tools.i18n_extract propose --package P [--helper NAME …] [--any] FILE…
    python -m tools.i18n_extract apply --package P [--lang ru]
    python -m tools.i18n_extract list --package P [--lang en]

`propose` reads FILEs and writes a draft spec, `tools/i18n/<P>.toml`: a `[[site]]` for each
message found at a sink — `file`, `line`, `col`, `key` (`<module>.<n>`) and `params`, a name for
each expression of an f-string (by its simple name, else `p1`…) — and `manual`, the places it will
not move. A person edits the keys and the names; `apply` then replaces each message with
`t("key", name=expression)`, imports `t` from `<P>.messages`, and writes the template into
`locales/<lang>.toml` in the files' order (`--lang en`: into English, the key marked untranslated
in every other catalog).

A sink is what a message is said through: the argument of `raise X(…)`, of `print(…)`, of
`sys.stderr.write(…)` and of `warnings.warn(…)`, `help=`/`description=`/`epilog=`/`metavar=` of any call (argparse), the
value of `"message"` in a dict, and a string argument of a helper the spec names (`--helper`).
By default a message is one that holds Cyrillic; `--any` takes every non-empty one.

Verbatim by construction: a literal becomes its template with `{` and `}` doubled; an f-string its
literal parts and `{name}`, `!r` the parameter `repr(expression)`, `!s` `str(expression)`; an
implicit concatenation is one message. A format spec, `!a`, `+`, `%` and `.format` are left to be
moved by hand (`manual`). After the edit each parameter's AST is the expression's it replaced.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "tools" / "i18n"
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_ARGPARSE = frozenset({"help", "description", "epilog", "metavar"})
# Exceptions whose text is read at once — caught by type and printed, or (KeyError) repr'd: they
# take `str(t(…))`; an exception of the code's own keeps the Message, rendered when it is read.
_BUILTIN_ERRORS = frozenset({"KeyError", "ValueError", "TypeError", "RuntimeError", "LookupError", "OSError",
                             "FileNotFoundError", "ImportError", "ModuleNotFoundError", "AssertionError",
                             "IndexError", "NotImplementedError", "AttributeError", "Exception"})
_CATEGORIES = ("zero", "one", "two", "few", "many", "other")


class ExtractError(Exception):
    """A spec or a file the codemod will not touch; the message names where."""


@dataclass(frozen=True)
class Site:
    file: str                                   # relative to the root, posix
    line: int
    col: int
    key: str
    params: Mapping[str, str] = field(default_factory=dict[str, str])   # name → expression, as written
    text: str = ""                              # the template, for the person reading the spec


@dataclass(frozen=True)
class Spec:
    package: str
    helpers: tuple[str, ...] = ()
    sites: tuple[Site, ...] = ()
    manual: tuple[str, ...] = ()


# ---------------------------------------------------------------- reading a message

@dataclass(frozen=True)
class _Found:
    node: cst.BaseExpression
    line: int
    col: int
    template: str
    exprs: tuple[tuple[str, str], ...]          # (expression as written, its simple name) in order
    eager: bool = False                         # the sink takes a str: `str(t(…))`


def _simple_name(expr: ast.expr) -> str | None:
    match expr:
        case ast.Name(id=name):
            return name
        case ast.Attribute(attr=name):
            return name
        case ast.Call(func=func) if isinstance(func, ast.Name) and func.id in ("repr", "str") and expr.args:
            return _simple_name(expr.args[0])
        case ast.Call(func=func):
            return _simple_name(func)
        case ast.Subscript(value=value):
            return _simple_name(value)
        case _:
            return None


def _escape(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def _strings_in(node: cst.CSTNode) -> Iterable[cst.CSTNode]:
    if isinstance(node, (cst.SimpleString, cst.FormattedString, cst.ConcatenatedString)):
        yield node
    for child in node.children:
        yield from _strings_in(child)


def _is_message(node: cst.CSTNode, any_text: bool, module: cst.Module) -> bool:
    code = module.code_for_node(node)
    return bool(_CYRILLIC.search(code)) if not any_text else any(True for _ in _strings_in(node))


def _read(node: cst.BaseExpression, module: cst.Module) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    """The template and the expressions of a string expression; a reason when it is not one."""
    if isinstance(node, (cst.BinaryOperation,)):
        return "сообщение собрано через + или %"
    if isinstance(node, cst.Call) and isinstance(node.func, cst.Attribute) and node.func.attr.value == "format":
        return "сообщение собрано через .format"
    if not isinstance(node, (cst.SimpleString, cst.FormattedString, cst.ConcatenatedString)):
        return "не строка"
    code = module.code_for_node(node)
    tree = ast.parse(code.strip() if "\n" not in code else f"({code})", mode="eval").body
    if isinstance(tree, ast.Constant) and isinstance(tree.value, str):
        return _escape(tree.value), ()
    if isinstance(tree, ast.Constant):
        return "байтовая строка"
    assert isinstance(tree, ast.JoinedStr)
    written = [module.code_for_node(e.expression) for e in _expressions(node)]
    values = [v for v in tree.values if isinstance(v, ast.FormattedValue)]
    if len(written) != len(values):
        return "вложенная f-строка"
    parts: list[str] = []
    exprs: list[tuple[str, str]] = []
    names: dict[str, str] = {}
    taken: set[str] = set()
    pending = iter(zip(values, written, strict=True))
    for value in tree.values:
        if isinstance(value, ast.Constant):
            parts.append(_escape(str(value.value)))
            continue
        assert isinstance(value, ast.FormattedValue)
        formatted, source = next(pending)
        if formatted.format_spec is not None:
            return "спецификация формата"
        if formatted.conversion == ord("a"):
            return "преобразование !a"
        source = source.strip()
        if formatted.conversion == ord("r"):
            source = f"repr({source})"
        elif formatted.conversion == ord("s"):
            source = f"str({source})"
        if source not in names:
            base = _simple_name(ast.parse(source, mode="eval").body) or f"p{len(names) + 1}"
            name, k = base, 2
            while name in taken:
                name, k = f"{base}{k}", k + 1
            names[source] = name
            taken.add(name)
            exprs.append((source, name))
        parts.append("{" + names[source] + "}")
    return "".join(parts), tuple(exprs)


def _expressions(node: cst.CSTNode) -> list[cst.FormattedStringExpression]:
    found: list[cst.FormattedStringExpression] = []

    def walk(n: cst.CSTNode) -> None:
        if isinstance(n, cst.FormattedStringExpression):
            found.append(n)
            return                         # a nested f-string is refused by the count
        for child in n.children:
            walk(child)
    walk(node)
    return found


class _Sinks(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, helpers: Sequence[str]) -> None:
        self.helpers = frozenset(helpers)
        self.sinks: list[cst.BaseExpression] = []
        self.eager: set[int] = set()            # the ids of the sinks that take a str

    def _first(self, call: cst.Call, *, eager: bool = False) -> None:
        if call.args and call.args[0].keyword is None and call.args[0].star == "":
            self.sinks.append(call.args[0].value)
            if eager:
                self.eager.add(id(call.args[0].value))

    def visit_Raise(self, node: cst.Raise) -> None:
        if isinstance(node.exc, cst.Call):
            self._first(node.exc, eager=isinstance(node.exc.func, cst.Name) and node.exc.func.value in _BUILTIN_ERRORS)

    def visit_Call(self, node: cst.Call) -> None:
        func = node.func
        name = func.value if isinstance(func, cst.Name) else func.attr.value if isinstance(func, cst.Attribute) else None
        if name == "print" and isinstance(func, cst.Name):
            self._first(node)
        if (isinstance(func, cst.Attribute) and name == "write" and isinstance(func.value, cst.Attribute)
                and func.value.attr.value == "stderr"):
            self._first(node, eager=True)
        if name == "warn" and (isinstance(func, cst.Name) or (isinstance(func, cst.Attribute)
                                                              and isinstance(func.value, cst.Name)
                                                              and func.value.value == "warnings")):
            self._first(node, eager=True)
        if name in self.helpers:
            self.sinks.extend(a.value for a in node.args if a.keyword is None and a.star == "")
        for a in node.args:
            if a.keyword is not None and a.keyword.value in _ARGPARSE:
                self.sinks.append(a.value)
                self.eager.add(id(a.value))

    def visit_Dict(self, node: cst.Dict) -> None:
        for element in node.elements:
            if isinstance(element, cst.DictElement) and isinstance(element.key, cst.SimpleString) \
                    and element.key.evaluated_value == "message":
                self.sinks.append(element.value)


def _found(path: Path, helpers: Sequence[str], any_text: bool) -> tuple[list[_Found], list[tuple[int, str]]]:
    module = cst.parse_module(path.read_text(encoding="utf-8"))
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    sinks = _Sinks(helpers)
    wrapper.visit(sinks)
    positions = wrapper.resolve(PositionProvider)
    found: list[_Found] = []
    manual: list[tuple[int, str]] = []
    seen: set[int] = set()
    for node in sinks.sinks:
        if id(node) in seen or not _is_message(node, any_text, module):
            continue
        seen.add(id(node))
        where = positions[node].start
        read = _read(node, module)
        if isinstance(read, str):
            manual.append((where.line, read))
        elif read[0] or read[1]:
            found.append(_Found(node, where.line, where.column, read[0], read[1], id(node) in sinks.eager))
    found.sort(key=lambda f: (f.line, f.col))
    return found, sorted(manual)


# ---------------------------------------------------------------- propose

def _module_key(package: str, path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    head = package.split(".")
    for i in range(len(parts) - len(head) + 1):
        if parts[i:i + len(head)] == head:
            rest = parts[i + len(head):]
            return ".".join(rest) if rest else path.stem
    return path.stem


def propose(package: str, files: Iterable[Path], *, helpers: Sequence[str] = (), any_text: bool = False,
            root: Path = ROOT) -> Spec:
    sites: list[Site] = []
    manual: list[str] = []
    for path in files:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        found, refused = _found(path, helpers, any_text)
        stem = _module_key(package, Path(rel))
        for n, f in enumerate(found, start=1):
            sites.append(Site(rel, f.line, f.col, f"{stem}.{n}", {name: expr for expr, name in f.exprs}, f.template))
        manual += [f"{rel}:{line}: {why} — перенести руками" for line, why in refused]
    return Spec(package, tuple(helpers), tuple(sites), tuple(manual))


def format_spec(spec: Spec) -> str:
    def s(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)
    out = [f"# The codemod's spec of {spec.package} (tools/i18n_extract.py): edit the keys and the names,",
           "# then `python -m tools.i18n_extract apply`. `text` is for reading; apply recomputes it.",
           f"package = {s(spec.package)}",
           f"helpers = [{', '.join(s(h) for h in spec.helpers)}]",
           "manual = [" + "".join(f"\n    {s(m)}," for m in spec.manual) + ("\n]" if spec.manual else "]")]
    for site in spec.sites:
        params = ", ".join(f"{name} = {s(expr)}" for name, expr in site.params.items())
        out += ["", "[[site]]", f"file = {s(site.file)}", f"line = {site.line}", f"col = {site.col}",
                f"key = {s(site.key)}", f"params = {{ {params} }}" if params else "params = {}",
                f"text = {s(site.text)}"]
    return "\n".join(out) + "\n"


def read_spec(text: str) -> Spec:
    data = tomllib.loads(text)
    return Spec(data["package"], tuple(data.get("helpers", ())),
                tuple(Site(s["file"], s["line"], s["col"], s["key"], dict(s.get("params", {})), s.get("text", ""))
                      for s in data.get("site", [])),
                tuple(data.get("manual", ())))


# ---------------------------------------------------------------- the catalog

def _flatten(table: Mapping[str, object], prefix: str, out: dict[str, object]) -> None:
    for name, value in table.items():
        key = f"{prefix}{name}"
        if isinstance(value, dict) and not (set(value) <= set(_CATEGORIES) and "other" in value):
            _flatten(value, f"{key}.", out)  # pyright: ignore[reportUnknownArgumentType]
        else:
            out[key] = value


def _dump(head: str, untranslated: list[str] | None, entries: Mapping[str, object]) -> str:
    def s(value: object) -> str:
        return json.dumps(value, ensure_ascii=False)
    lines = [head.rstrip("\n"), "schema = 1"] if head else ["schema = 1"]
    if untranslated is not None:
        lines.append("untranslated = [" + "".join(f"\n    {s(k)}," for k in untranslated) + ("\n]" if untranslated else "]"))
    tables: dict[str, list[str]] = {}
    for key, value in entries.items():
        table, _, name = key.rpartition(".")
        if isinstance(value, dict):
            tables.setdefault(key, []).extend(f"{c} = {s(v)}" for c, v in value.items())  # pyright: ignore[reportUnknownVariableType]
        else:
            tables.setdefault(table, []).append(f"{_bare(name)} = {s(value)}")
    for table, body in tables.items():
        lines += ["", f"[{'.'.join(_bare(p) for p in table.split('.'))}]", *body]
    return "\n".join(lines) + "\n"


def _bare(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name, ensure_ascii=False)


def _write_catalog(path: Path, add: Mapping[str, str], mark: Iterable[str] = ()) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else "schema = 1\n"
    head = "".join(line for line in text.splitlines(keepends=True)[:_head_length(text)])
    data = tomllib.loads(text)
    data.pop("schema", None)
    untranslated = data.pop("untranslated", None)
    entries: dict[str, object] = {}
    _flatten(data, "", entries)
    for key, template in add.items():
        if key in entries and entries[key] != template:
            raise ExtractError(f"{path}: «{key}» уже есть с другим текстом")
        entries[key] = template
    marks = list(untranslated) if isinstance(untranslated, list) else None  # pyright: ignore[reportUnknownArgumentType]
    for key in mark:
        if marks is None:
            marks = []
        if key not in marks:
            marks.append(key)
    path.write_text(_dump(head, marks, entries), encoding="utf-8")


def _head_length(text: str) -> int:
    n = 0
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        n += 1
    return n


# ---------------------------------------------------------------- apply

class _Replace(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, calls: Mapping[int, str]) -> None:
        self.calls = calls                       # id of an original node → its replacement's code

    def on_leave(self, original_node: cst.CSTNode, updated_node: cst.CSTNode) -> cst.CSTNode:  # type: ignore[override]
        code = self.calls.get(id(original_node))
        return cst.parse_expression(code) if code is not None else updated_node


def _same(a: str, b: str) -> bool:
    return ast.dump(ast.parse(a, mode="eval")) == ast.dump(ast.parse(b, mode="eval"))


def _call(key: str, template_exprs: tuple[tuple[str, str], ...], site: Site) -> tuple[str, dict[str, str]]:
    """`t("key", name=expression)` with the spec's names, each matched to its expression by AST."""
    names: dict[str, str] = {}
    for expr, _ in template_exprs:
        name = next((n for n, e in site.params.items() if _same(e, expr)), None)
        if name is None:
            raise ExtractError(f"{site.file}:{site.line}: выражения {expr} нет в params спеки")
        names[expr] = name
    if len(set(names.values())) != len(names) or set(names.values()) != set(site.params):
        raise ExtractError(f"{site.file}:{site.line}: params спеки не те, что в f-строке")
    args = "".join(f", {name}={expr}" for expr, name in names.items())
    return f"t({json.dumps(key, ensure_ascii=False)}{args})", names


def _renamed(template: str, names: Mapping[str, str], exprs: tuple[tuple[str, str], ...]) -> str:
    by_proposed = {proposed: names[expr] for expr, proposed in exprs}
    return re.sub(r"(?<!\{)\{([A-Za-z_][A-Za-z_0-9]*)\}(?!\})", lambda m: "{" + by_proposed.get(m[1], m[1]) + "}",
                  template)


def _with_import(text: str, package: str) -> str:
    line = f"from {package}.messages import t"
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == f"{package}.messages" \
                and any(a.name == "t" and a.asname is None for a in node.names):
            return text
    bound = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    bound |= {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in (*n.args, *n.kwonlyargs)}
    if "t" in bound:
        raise ExtractError(f"имя t уже занято в модуле — {line} перенести руками")
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    lines = text.splitlines(keepends=True)
    if imports:
        last = max(imports, key=lambda n: n.end_lineno or n.lineno)
        at = last.end_lineno or last.lineno
        top = package.split(".")[0]
        names = [a.name for a in last.names] if isinstance(last, ast.Import) else [last.module or ""]
        if not any(n.split(".")[0] == top for n in names):
            line = "\n" + line                    # a group of its own after the standard library's
    else:
        doc = tree.body[0] if tree.body and isinstance(tree.body[0], ast.Expr) \
            and isinstance(getattr(tree.body[0], "value", None), ast.Constant) else None
        at = doc.end_lineno or doc.lineno if doc is not None else 0
    return "".join([*lines[:at], line + "\n", *lines[at:]])


def apply(spec: Spec, locales: Path, lang: str = "ru", *, root: Path = ROOT) -> list[str]:
    """Replace each message the spec names and write its template; the files changed."""
    by_file: dict[str, list[Site]] = {}
    for site in spec.sites:
        by_file.setdefault(site.file, []).append(site)
    templates: dict[str, str] = {}
    changed: list[str] = []
    for rel, sites in by_file.items():
        path = root / rel
        text = path.read_text(encoding="utf-8")
        found, _ = _found(path, spec.helpers, any_text=True)
        at = {(f.line, f.col): f for f in found}
        calls: dict[int, str] = {}
        for site in sites:
            if re.search(r"\bt\(" + re.escape(json.dumps(site.key, ensure_ascii=False)) + r"[,)]", text):
                continue                                   # moved already
            f = at.get((site.line, site.col))
            if f is None:
                raise ExtractError(f"{rel}:{site.line}: на месте сообщения нет строки — спека устарела")
            code, names = _call(site.key, f.exprs, site)
            calls[id(f.node)] = f"str({code})" if f.eager else code
            templates[site.key] = _renamed(f.template, names, f.exprs)
        if calls:
            module = cst.parse_module(text)
            wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
            nodes = {id(n): n for n in _all_nodes(wrapper.module)}
            remap = _remap(wrapper, nodes, {(f.line, f.col): f for f in found}, calls)
            new = wrapper.visit(_Replace(remap)).code
            new = _with_import(new, spec.package)
            _check(text, new, rel)
            path.write_text(new, encoding="utf-8")
            changed.append(rel)
    if templates:
        _write_catalog(locales / f"{lang}.toml", templates)
        if lang == "en":
            for other in sorted(locales.glob("*.toml")):
                if other.stem != "en":
                    _write_catalog(other, {}, templates)
    return changed


def _all_nodes(node: cst.CSTNode) -> Iterable[cst.CSTNode]:
    yield node
    for child in node.children:
        yield from _all_nodes(child)


def _remap(wrapper: MetadataWrapper, nodes: Mapping[int, cst.CSTNode], found: Mapping[tuple[int, int], _Found],
           calls: Mapping[int, str]) -> dict[int, str]:
    """The ids `_found` gave belong to its own parse: find the same positions in this one."""
    positions = wrapper.resolve(PositionProvider)
    wanted = {(f.line, f.col): calls[id(f.node)] for f in found.values() if id(f.node) in calls}
    out: dict[int, str] = {}
    for node_id, node in nodes.items():
        if isinstance(node, cst.BaseExpression) and node in positions:
            where = positions[node].start
            if isinstance(node, (cst.SimpleString, cst.FormattedString, cst.ConcatenatedString)):
                code = wanted.pop((where.line, where.column), None)     # the outermost string there (pre-order)
                if code is not None:
                    out[node_id] = code
    return out


def _check(before: str, after: str, rel: str) -> None:
    """Every argument of a new `t(…)` call is an expression the old source held, by AST."""
    old = {ast.dump(n) for n in ast.walk(ast.parse(before)) if isinstance(n, ast.expr)}
    for node in ast.walk(ast.parse(after)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t" and node.keywords:
            for keyword in node.keywords:
                value = keyword.value
                inner = value.args[0] if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                                          and value.func.id in ("repr", "str") and value.args) else value
                if ast.dump(inner) not in old:
                    raise ExtractError(f"{rel}:{node.lineno}: параметр {keyword.arg} — выражения не было в исходнике")


# ---------------------------------------------------------------- list

def listing(package: str, lang: str = "en") -> str:
    """Each key of `package`'s catalogs with its text in `lang` and the Russian beside it."""
    spec = importlib.util.find_spec(package)
    assert spec is not None and spec.submodule_search_locations is not None
    locales = Path(next(iter(spec.submodule_search_locations))) / "locales"
    def read(name: str) -> dict[str, object]:
        out: dict[str, object] = {}
        path = locales / f"{name}.toml"
        if path.exists():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            data.pop("schema", None)
            data.pop("untranslated", None)
            _flatten(data, "", out)
        return out
    main, ru = read(lang), read("ru")
    return "".join(f"{key}\n  {lang}: {main[key]}\n  ru: {ru.get(key, '—')}\n" for key in main)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.i18n_extract", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--package", required=True)
    p.add_argument("--helper", action="append", default=[])
    p.add_argument("--any", action="store_true")
    p.add_argument("files", nargs="+", type=Path)
    a = sub.add_parser("apply")
    a.add_argument("--package", required=True)
    a.add_argument("--lang", default="ru")
    li = sub.add_parser("list")
    li.add_argument("--package", required=True)
    li.add_argument("--lang", default="en")
    args = ap.parse_args(argv)
    path = SPECS / f"{args.package}.toml"
    try:
        if args.cmd == "propose":
            spec = propose(args.package, args.files, helpers=args.helper, any_text=args.any)
            SPECS.mkdir(parents=True, exist_ok=True)
            path.write_text(format_spec(spec), encoding="utf-8")
            print(f"{path.relative_to(ROOT)}: сообщений {len(spec.sites)}, руками {len(spec.manual)}")
            for line in spec.manual:
                print(f"  {line}")
        elif args.cmd == "apply":
            spec = read_spec(path.read_text(encoding="utf-8"))
            found = importlib.util.find_spec(spec.package)
            assert found is not None and found.submodule_search_locations is not None
            locales = Path(next(iter(found.submodule_search_locations))) / "locales"
            for rel in apply(spec, locales, args.lang):
                print(rel)
        else:
            print(listing(args.package, args.lang), end="")
    except ExtractError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
