"""The library's layers: tools/layers.toml, read and held to the tree (the verso repo's since 0.1.0).

The library took what the CLI did for
everyone else into the library (`verso.core.pipeline`), and this keeps it there. The table
puts packages in tiers, bottom first, the core's under the plugin's; a module's package
is the longest package of the table it lies under (`verso.ru.facts.checks.births` →
`verso.ru.facts`), but for a side's root — `geni`, `verso.core`, `verso.ru` — which is its
own `__init__` alone, so a module put straight under it names its tier itself. A module of
the library or the alias under no package is named («нет слоя»). What it refuses:

* LAY001 — `verso.ru.cli` imported, or named in a string of code, outside `verso/ru/cli/`,
  `verso/core/cli.py` (`verso <команда>`) and `verso/ru/plugin.py` (the plugin's commands):
  by the library and by both packages of Verso. A docstring is documentation and is
  not read.
* LAY002 — a package of the library importing one of its own tier or a higher one. A
  module may import its own package and lower tiers only; `[overrides]` puts a module in
  another tier than its package's. An edge of the core into the plugin is LAY006's.
* LAY003 — a cycle of top-level imports, as written (a package is not taken to import
  its parent).
* LAY004 — a name moved out of a CLI module imported through it. The
  re-exports went before 0.1.0, so a CLI module answers only for the names it uses; a
  table still holding `[moved]` is refused.
* LAY005 — the library or the App importing the corpus's package (`[corpus] package`).
  The library reads the corpus's data through the workspace; the corpus may import the
  library. Until 0.1.0 one bridge stood (`verso.ru.domain.statuses` re-exported the landlords'
  statuses for DSL v0); since, none, and `[corpus] bridge` is refused.
* LAY006 — a module of the core (`verso.core.*`) importing one of the plugin
  (`verso.ru.*`), at the top or in a function, or naming one in a string of code — an
  import by name, a command run by its module; a docstring and a comment are documentation.
  The rename before 0.1.0 listed what the packages' sides had, and the list went to none: since, a
  LAY006 is never listed — a line of it in the allowlist is refused. What the core needs of
  the plugin it asks the registry (`verso.core.plugins`).

The tree the check reads is this repository's —
each distribution's `packages/*/src`, its `tests/` and `tools/` — or, in a toy test, the code
at its root. LAY007 stayed behind with the rename map it read: no distribution answers to an
old name, so an import of one fails anyway.

The table speaks in the new names since 0.1.0 (schema 2): 0.1.0's moves (`verso.ru.pipeline`,
`verso.core.plugins`) have no old one. A table of schema 1 is refused.

Imports at the top and inside functions count; one under `if TYPE_CHECKING:` is no
dependency.

LAY001 and LAY002 are listed in tests/layering_allowlist.txt, which only shrinks: pytest
refuses a line that is no longer a violation, `--update` strikes those and never adds one
(it writes a missing list whole), and `--base REV` (CI) refuses a line REV's list lacks —
but for a code REV's tool did not define yet.

    python -m tools.layers                 # check
    python -m tools.layers --update        # strike what no longer holds
    python -m tools.layers --base REV      # … and refuse a line REV lacks
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ROOT = Path(__file__).resolve().parent.parent
TABLE = Path("tools") / "layers.toml"
ALLOWLIST = Path("tests") / "layering_allowlist.txt"
SCHEMA = 2
# A side's root package is its own __init__ alone: a module put straight under it names its tier.
_ROOTS = frozenset({"verso.core", "verso.ru"})
# The code's top-level package: the namespace every distribution of the library shares.
TARGETS = ("verso",)
# What an edge may lead to: the library, the App, and the corpus's package (LAY005).
_IMPORTED = (*TARGETS, "corpus")
LISTED = frozenset({"LAY001", "LAY002"})
# The core imports the plugin nowhere, and a line of LAY006 is no exemption.
NEVER_LISTED = "LAY006"
# The CLI named in a string of code — run in a subprocess, imported by name, invoked with -m.
_CLI_STRING = re.compile(r"(?<![\w.])verso\.(?:core|ru)\.cli(?!\w)(?:\.\w+)*")
# A module of the plugin named in a string of code (LAY006).
_PLUGIN_STRING = re.compile(r"(?<![\w.])verso\.ru(?!\w)(?:\.\w+)*")
# What may name the CLI's modules by a string besides the CLI: the plugin's table of commands.
_NAMES_THE_CLI = frozenset({"verso.ru.plugin"})
HEADER = ("# Рёбра, которые ещё нарушают tools/layers.toml (tools/layers.py). Только убывают:\n"
          "# pytest не терпит устаревшей строки, CI (--base) — новой. «КОД откуда -> куда».\n"
          "# Списываются LAY001 и LAY002; LAY006 — никогда (ядро не импортирует плагин).\n")

Kind = Literal["top", "func", "typecheck", "string"]


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    line: int
    kind: Kind
    names: tuple[str, ...] = ()


@dataclass(frozen=True)
class Violation:
    code: str
    src: str
    dst: str
    message: str

    @property
    def key(self) -> str:
        """The violation's line in the allowlist."""
        return f"{self.code} {self.src} -> {self.dst}"


@dataclass(frozen=True)
class Table:
    tiers: tuple[tuple[str, tuple[str, ...]], ...]
    overrides: Mapping[str, str]
    corpus: str | None = None                       # [corpus] package

    def package_of(self, module: str) -> str | None:
        """The longest package of the table `module` lies under — a side's root only for its
        own __init__; None when there is none."""
        parts = module.split(".")
        for i in range(len(parts), 0, -1):
            head = ".".join(parts[:i])
            if head in self.packages and (i == len(parts) or head not in _ROOTS):
                return head
        return None

    @property
    def packages(self) -> dict[str, int]:
        """Every package of the table → the index of its tier."""
        return {p: i for i, (_, packages) in enumerate(self.tiers) for p in packages}

    def tier_of(self, module: str) -> int | None:
        """The index of the tier `module` sits in; None when no tier lists its package."""
        if module in self.overrides:
            return [name for name, _ in self.tiers].index(self.overrides[module])
        package = self.package_of(module)
        return None if package is None else self.packages[package]

    def tier_name(self, module: str) -> str:
        index = self.tier_of(module)
        return self.tiers[index][0] if index is not None else "?"


class LayersError(Exception):
    """The table cannot be read; the message says why, in Russian."""


def read_table(path: Path) -> Table:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") == 1:
        raise LayersError(f"{TABLE.as_posix()}: schema 1 — старые имена; с 0.1.0 таблица в новых (schema {SCHEMA})")
    if data.get("schema") != SCHEMA:
        raise LayersError(f"{TABLE.as_posix()}: schema {data.get('schema')!r}, ожидалась {SCHEMA}")
    if "moved" in data:
        raise LayersError(f"{TABLE.as_posix()}: [moved] снят до 0.1.0 — CLI-модуль отвечает только за свои имена")
    unknown = set(data) - {"schema", "tier", "overrides", "corpus"}
    if unknown:
        raise LayersError(f"{TABLE.as_posix()}: неизвестный ключ «{sorted(unknown)[0]}»")
    for i, tier in enumerate(data.get("tier", []), 1):
        if not isinstance(tier, dict) or "name" not in tier or "packages" not in tier:
            raise LayersError(f"{TABLE.as_posix()}: слой №{i} без «name» или «packages»")
    tiers = tuple((t["name"], tuple(t["packages"])) for t in data.get("tier", []))
    names = {name for name, _ in tiers}
    overrides = dict(data.get("overrides", {}))
    for module, tier in overrides.items():
        if tier not in names:
            raise LayersError(f"{TABLE.as_posix()}: [overrides] «{module}» — слоя «{tier}» нет")
    corpus = data.get("corpus", {})
    if "bridge" in corpus:
        raise LayersError(f"{TABLE.as_posix()}: [corpus] bridge снят до 0.1.0 — библиотека не импортирует корпус")
    if set(corpus) - {"package"}:
        raise LayersError(f"{TABLE.as_posix()}: неизвестный ключ «corpus.{sorted(set(corpus) - {'package'})[0]}»")
    return Table(tiers, overrides, corpus.get("package"))


def _is_cli(module: str) -> bool:
    """The CLI's modules, and 0.1.0's `verso` command, which names each of them by a string."""
    return module in ("verso.ru.cli", "verso.core.cli") or module.startswith("verso.ru.cli.")


def side(module: str) -> str | None:
    """`core` or `ru` — the distribution a module of the library belongs to; None for any other."""
    for name in ("core", "ru"):
        if module == f"verso.{name}" or module.startswith(f"verso.{name}."):
            return name
    return None


def _layered(module: str) -> bool:
    """A module the tiers must place: the library's."""
    return side(module) in ("core", "ru")


def source_roots(root: Path) -> list[Path]:
    """Where the code is imported from: each distribution's `packages/*/src`, and the root (a toy
    tree keeps its code there)."""
    return [*sorted(p for p in root.glob("packages/*/src") if p.is_dir()), root]


def modules(root: Path) -> dict[str, Path]:
    """Every module of the scanned trees: dotted name → path, the code named from its source root
    (each distribution's src/) and the tests as `tests.*`. Test fixtures are data."""
    tops = [(base, top) for base in source_roots(root) for top in TARGETS]
    tops += [(root, "corpus"), (root, "tools"), (root, "tests")]
    found: dict[str, Path] = {}
    for base, top in tops:
        for path in sorted((base / top).rglob("*.py")):
            rel = path.relative_to(base)
            if {"__pycache__", "node_modules", "fixtures", "golden"} & set(rel.parts[:-1]):
                continue
            parts = rel.with_suffix("").parts
            found[".".join(parts[:-1] if parts[-1] == "__init__" else parts)] = path
    return found


def _deepest(name: str, known: Mapping[str, Path]) -> str | None:
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        if (head := ".".join(parts[:i])) in known:
            return head
    return None


def _docstrings(tree: ast.Module) -> set[int]:
    return {id(s.value) for s in ast.walk(tree)
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str)}


def _type_checking(test: ast.expr) -> bool | None:
    """True for `TYPE_CHECKING` (or `typing.TYPE_CHECKING`), False for `not` it, None else."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _type_checking(test.operand)
        return None if inner is None else not inner
    name = test.id if isinstance(test, ast.Name) else test.attr if isinstance(test, ast.Attribute) else None
    return True if name == "TYPE_CHECKING" else None


def _walk(node: ast.AST, kind: Kind) -> Iterator[tuple[ast.AST, Kind]]:
    for child in ast.iter_child_nodes(node):
        inner = kind
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) and kind == "top":
            inner = "func"
        yield child, inner
        checking = _type_checking(child.test) if isinstance(child, ast.If) else None
        if isinstance(child, ast.If) and checking is not None:
            for branch, typed in ((child.body, checking), (child.orelse, not checking)):
                for stmt in branch:
                    yield stmt, "typecheck" if typed else inner
                    yield from _walk(stmt, "typecheck" if typed else inner)
            continue
        yield from _walk(child, inner)


def edges_of(module: str, path: Path, known: Mapping[str, Path]) -> list[Edge]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstrings(tree)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    out: list[Edge] = []
    for node, kind in _walk(tree, "top"):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _IMPORTED and (dst := _deepest(alias.name, known)):
                    out.append(Edge(module, dst, node.lineno, kind))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = package.split(".")[:len(package.split(".")) - node.level + 1]
                base = ".".join([*up, *([base] if base else [])])
            if base.split(".")[0] not in _IMPORTED:
                continue
            rest = []
            for alias in node.names:
                if f"{base}.{alias.name}" in known:
                    out.append(Edge(module, f"{base}.{alias.name}", node.lineno, kind))
                else:
                    rest.append(alias.name)
            if rest and (dst := _deepest(base, known)):
                out.append(Edge(module, dst, node.lineno, kind, tuple(rest)))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            named = {m.group(0) for m in _CLI_STRING.finditer(node.value)}
            if side(module) == "core":
                named |= {m.group(0) for m in _PLUGIN_STRING.finditer(node.value)}
            out.extend(Edge(module, name, node.lineno, "string") for name in sorted(named))
    return out


def edges(root: Path) -> list[Edge]:
    known = modules(root)
    return [edge for module, path in known.items() for edge in edges_of(module, path, known)]


def violations(root: Path, table: Table) -> list[Violation]:
    known = modules(root)
    found: dict[str, Violation] = {}
    top_level: dict[str, set[str]] = {}

    def add(v: Violation) -> None:
        found.setdefault(v.key if v.code in LISTED else f"{v.key} {v.message}", v)

    for module, path in known.items():
        if module.split(".")[0] not in TARGETS:
            continue
        for edge in edges_of(module, path, known):
            dst = _deepest(edge.dst, known) if edge.kind == "string" else edge.dst
            if dst is None or edge.kind == "typecheck":
                continue
            core_to_ru = side(module) == "core" and side(dst) == "ru"
            if edge.kind in ("top", "func") and core_to_ru:
                add(Violation("LAY006", module, dst, f"{module} → {dst}: ядро импортирует ru — "
                                                     "возьмите это у плагина (verso.core.plugins)"))
            elif edge.kind == "string" and core_to_ru:
                add(Violation("LAY006", module, dst, f"{module} → {dst}: ядро называет ru строкой — "
                                                     "возьмите это у плагина (verso.core.plugins)"))
            if table.corpus and edge.kind != "string" and (dst == table.corpus or dst.startswith(table.corpus + ".")):
                add(Violation("LAY005", module, dst, f"{module} → {dst}: библиотека не импортирует корпус — данные "
                                                     "читаются через рабочую область (verso.core.corpus_data, "
                                                     "verso.core.places)"))
                continue
            if _is_cli(dst) and not _is_cli(module) and module not in _NAMES_THE_CLI:
                add(Violation("LAY001", module, dst, f"{module}: {dst} — CLI не импортируют; "
                                                     "возьмите из verso.core.pipeline или перенесите в библиотеку"))
                continue
            if edge.kind == "top" and dst != module:
                top_level.setdefault(module, set()).add(dst)
            if edge.kind == "string" or core_to_ru or not _layered(module) or not _layered(dst):
                continue
            if table.package_of(module) == table.package_of(dst):
                continue
            src_tier, dst_tier = table.tier_of(module), table.tier_of(dst)
            if src_tier is None or dst_tier is None or dst_tier < src_tier:
                continue
            add(Violation("LAY002", module, dst, f"{module} ({table.tier_name(module)}) → {dst} "
                                                 f"({table.tier_name(dst)}): ребро вверх или вбок — см. tools/layers.toml"))
    for cycle in _cycles(top_level):
        add(Violation("LAY003", cycle[0], cycle[1], "цикл импортов верхнего уровня: " + " → ".join(cycle)))
    return list(found.values())


def _cycles(graph: Mapping[str, set[str]]) -> list[list[str]]:
    """One cycle per strongly connected component of more than one module, starting at
    its smallest name and following the smallest next step back to it."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    components: list[set[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in sorted(graph.get(v, ())):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            component = set()
            while True:
                w = stack.pop()
                on.discard(w)
                component.add(w)
                if w == v:
                    break
            if len(component) > 1:
                components.append(component)

    for v in sorted(graph):
        if v not in index:
            visit(v)
    out = []
    for component in components:
        start = min(component)
        path, seen = [start], {start}
        while True:
            nxt = min(w for w in graph[path[-1]] if w in component and (w == start or w not in seen))
            path.append(nxt)
            if nxt == start:
                break
            seen.add(nxt)
        out.append(path)
    return sorted(out)


def table_problems(root: Path, table: Table) -> list[str]:
    """A module of the library under no package of the table that [overrides]
    does not place; a package of the table that is not there; an override that is no module."""
    known = modules(root)
    out = [f"{m}: нет слоя — впишите пакет в {TABLE.as_posix()}"
           for m in sorted(known) if _layered(m) and table.tier_of(m) is None]
    out += [f"{TABLE.as_posix()}: пакета {p} нет"
            for p in sorted(table.packages) if not any(m == p or m.startswith(p + ".") for m in known)]
    out += [f"{TABLE.as_posix()}: [overrides] — модуля {m} нет" for m in sorted(set(table.overrides) - set(known))]
    return out


def read_allowlist(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def check(root: Path = ROOT) -> list[str]:
    table = read_table(root / TABLE)
    found = violations(root, table)
    path = root / ALLOWLIST
    allowed = read_allowlist(path.read_text(encoding="utf-8")) if path.is_file() else []
    keys = {v.key for v in found}
    out = [v.message for v in found if not (v.code in LISTED and v.key in allowed)]
    out += [f"{ALLOWLIST.as_posix()}: «{line}» — {NEVER_LISTED} не списывается: ядро не импортирует плагин"
            if line.split()[0] == NEVER_LISTED else
            f"{ALLOWLIST.as_posix()}: «{line}» уже не нарушение — вычеркните: make layering update=1"
            for line in allowed if line not in keys or line.split()[0] == NEVER_LISTED]
    return table_problems(root, table) + out


def update(root: Path = ROOT) -> list[str]:
    """Write the allowlist as the tree has it — refusing a line the list lacks, unless
    there is no list yet. Returns the refusals; nothing is written when there are any."""
    path = root / ALLOWLIST
    keys = sorted({v.key for v in violations(root, read_table(root / TABLE)) if v.code in LISTED})
    if path.is_file():
        new = set(keys) - set(read_allowlist(path.read_text(encoding="utf-8")))
        if new:
            return [f"--update только вычёркивает: {len(new)} новых нарушений — исправьте код"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "".join(f"{key}\n" for key in keys), encoding="utf-8")
    return []


def allowlist_at(rev: str, root: Path = ROOT) -> list[str] | None:
    """The allowlist as commit `rev` has it; None when it has none."""
    done = subprocess.run(["git", "-C", str(root), "show", f"{rev}:./{ALLOWLIST.as_posix()}"],
                          capture_output=True, text=True, encoding="utf-8")
    return read_allowlist(done.stdout) if done.returncode == 0 else None


def base_problems(rev: str, root: Path = ROOT) -> list[str]:
    """A line of this tree's allowlist that `rev`'s lacks; nothing when `rev` has none. A
    line of a code `rev` could not have held is the first seed of that code, and passes: a
    code `rev`'s tool did not define. Paths are read from this tree's root (`rev:./…`), so a
    library inside a parent repository (`lib/`) reads its own."""
    base = allowlist_at(rev, root)
    path = root / ALLOWLIST
    if base is None or not path.is_file():
        return []
    shown = subprocess.run(["git", "-C", str(root), "show", f"{rev}:./tools/layers.py"], capture_output=True,
                           text=True, encoding="utf-8")

    def known(code: str) -> bool:      # a base without the tool knows them all
        return shown.returncode != 0 or f'"{code}"' in shown.stdout
    return [f"«{line}» появилась после {rev} — список только убывает"
            for line in read_allowlist(path.read_text(encoding="utf-8"))
            if line not in base and known(line.split()[0])]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.layers", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="strike the allowlist's lines that no longer hold")
    ap.add_argument("--base", metavar="REV", help="refuse an allowlist line REV's list lacks")
    args = ap.parse_args(argv)
    found = update(ROOT) if args.update else []
    found += check(ROOT)
    if args.base:
        if allowlist_at(args.base) is None:
            print(f"в {args.base} списка нет — сверять не с чем")
        found += base_problems(args.base)
    lines = read_allowlist((ROOT / ALLOWLIST).read_text(encoding="utf-8")) if (ROOT / ALLOWLIST).is_file() else []
    print("\n".join(found) if found else f"{TABLE.as_posix()}: в порядке — строк в списке {len(lines)}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
