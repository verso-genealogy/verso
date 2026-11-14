"""DSL v0 → v1: a file's imports through the facade, its `__main__` gone — nothing else.

`upgrade(source, corpus_names)` rewrites the head of a DSL file — the imports it opens with —
as DSL v1 writes it: `from corpus.statuses import …` (a name of `corpus_names`), the facade
`from verso.ru.dsl import …` and its catalogs, in that order of modules, each import's names
sorted and wrapped at 100 columns (`verso.ru.dsl.source.format_import`). The exporters' imports
and the `if __name__ == "__main__":` block go — `verso export-csv` writes the CSV — and
`import os` with them, unless the file uses it elsewhere. Every other byte stays.

What it cannot be sure of it refuses (`UpgradeError`), and says which line: a comment in the
head, an import after code (a module's docstring stays above the imports), a module of `geni`
that is no DSL, an import with `as`, a name no catalog holds, a `__main__` that does more than
export or has an `else:`. And it checks itself
(`check_unchanged`): the ratchet's prints of every record and the module's AST outside its
head are those of the file it was given.
"""
from __future__ import annotations

import ast
from collections.abc import Collection
from itertools import zip_longest

import libcst as cst

import verso.ru.dsl
from verso.core import ratchet
from verso.ru.dsl import causes_of_death, marital_status, statuses
from verso.ru.dsl.source import DSL_IMPORT_ORDER, format_import, is_docstring
from verso.ru.messages import t

# This corpus's statuses module — `<the corpus directory>.statuses` (`statuses.corpus_module_name`).
CORPUS = "corpus.statuses"
FACADE = "verso.ru.dsl"
# The modules of DSL v1, in the order a file imports them (the writers' order too).
ORDER = (CORPUS, *DSL_IMPORT_ORDER)
_CATALOGS = {"geni.domain.statuses": statuses, "geni.domain.causes_of_death": causes_of_death,
             "geni.domain.marital_status": marital_status}
# The modules of DSL v0 whose names the facade gives.
_FACADE_V0 = frozenset({
    "geni.domain", "geni.relationship", "geni.gender", "calendar",
    *(f"geni.dsl.records.{kind}" for kind in ("births", "census", "deaths", "divorces", "external_sources",
                                              "marriages", "name_lists")),
})
_EXPORTERS = "geni.exporters"


class UpgradeError(ValueError):
    """A file the codemod will not guess about."""


def _is_main(node: cst.CSTNode) -> bool:
    if not isinstance(node, cst.If) or not isinstance(node.test, cst.Comparison):
        return False
    test = node.test
    return (isinstance(test.left, cst.Name) and test.left.value == "__name__" and len(test.comparisons) == 1
            and isinstance(test.comparisons[0].operator, cst.Equal)
            and isinstance(test.comparisons[0].comparator, cst.SimpleString)
            and test.comparisons[0].comparator.evaluated_value == "__main__")


def _only_exports(module: cst.Module, main: cst.If) -> bool:
    """A `__main__` that only exports: `os.chdir(…)` and `<set>.export(<Exporter>())`, its
    result kept in a name or not (Заманиловка 1804: `csv_file = … .export(…)`), and no `else:`."""
    if main.orelse is not None:
        return False
    for stmt in main.body.body:
        code = module.code_for_node(stmt).strip()
        try:
            [expr] = ast.parse(code).body
        except (SyntaxError, ValueError):
            return False
        call = expr.value if isinstance(expr, ast.Expr | ast.Assign) else None
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            return False
        target = call.func.value
        if call.func.attr == "chdir" and isinstance(target, ast.Name) and target.id == "os":
            continue
        if (call.func.attr == "export" and isinstance(target, ast.Name) and len(call.args) == 1
                and isinstance(call.args[0], ast.Call) and not call.args[0].args):
            continue
        return False
    return True


def _is_import(stmt: cst.CSTNode) -> bool:
    return (isinstance(stmt, cst.SimpleStatementLine)
            and all(isinstance(small, cst.Import | cst.ImportFrom) for small in stmt.body))


def _place(module: str, name: str, corpus_names: Collection[str], corpus: str) -> str:
    """The v1 module of `name` imported from `module` (v0 or v1)."""
    if module in _CATALOGS or module in ORDER[2:]:
        catalog = _CATALOGS.get(module) or {m.__name__: m for m in _CATALOGS.values()}[module]
        if catalog is statuses and name in corpus_names:
            return corpus
        if name not in catalog.__all__:
            raise UpgradeError(t("dsl.upgrade.not_in_catalog", name=name, catalog=catalog.__name__))
        return catalog.__name__
    if module == corpus:
        return corpus
    if module in _FACADE_V0 or module == FACADE:
        if name not in verso.ru.dsl.__all__:
            raise UpgradeError(t("dsl.upgrade.not_in_facade", name=name, module=module))
        return FACADE
    raise UpgradeError(t("dsl.upgrade.not_a_dsl_module", module=module))


def upgrade(source: str, corpus_names: Collection[str], corpus: str = CORPUS) -> str:
    """`source` as DSL v1 (see the module's docstring), the corpus's statuses imported from
    `corpus` — the workspace's module name for them; refused with `UpgradeError`."""
    order = (corpus, *DSL_IMPORT_ORDER)
    module = cst.parse_module(source)
    if "#" in "".join(module.code_for_node(line) for line in module.header):
        raise UpgradeError(t("dsl.upgrade.comment_in_head"))
    body = list(module.body)
    lead = 1 if body and is_docstring(body[0]) else 0     # a module's docstring stays above its imports
    head = lead
    while head < len(body) and _is_import(body[head]):
        head += 1
    docstring, imports, rest = body[:lead], body[lead:head], body[head:]
    for stmt in imports:
        if "#" in module.code_for_node(stmt):
            raise UpgradeError(t("dsl.upgrade.comment_in_head_at", code=module.code_for_node(stmt).strip()))
    for stmt in rest:
        if _is_import(stmt):
            raise UpgradeError(t("dsl.upgrade.import_after_code", code=module.code_for_node(stmt).strip()))
    mains = [stmt for stmt in rest if _is_main(stmt)]
    for main in mains:
        assert isinstance(main, cst.If)
        if not _only_exports(module, main):
            raise UpgradeError(t("dsl.upgrade.main_does_more"))
        if "#" in "".join(module.code_for_node(line) for line in main.leading_lines):
            raise UpgradeError(t("dsl.upgrade.comment_before_main"))
    kept = [stmt for stmt in rest if stmt not in mains]

    names: dict[str, set[str]] = {m: set() for m in order}
    want_os = False
    for stmt in imports:
        assert isinstance(stmt, cst.SimpleStatementLine)
        for small in stmt.body:
            if isinstance(small, cst.Import):
                for alias in small.names:
                    dotted = module.code_for_node(alias.name)
                    if dotted.split(".")[0] == "geni":
                        raise UpgradeError(t("dsl.upgrade.not_a_dsl_form", dotted=dotted))
                    if dotted != "os" or alias.asname is not None:
                        raise UpgradeError(t("dsl.upgrade.not_a_dsl_import", dotted=dotted))
                    want_os = True
                continue
            assert isinstance(small, cst.ImportFrom)
            if small.module is None or small.relative or isinstance(small.names, cst.ImportStar):
                raise UpgradeError(t("dsl.upgrade.code_not_a_dsl_import", code=module.code_for_node(small)))
            mod = module.code_for_node(small.module)
            if mod == _EXPORTERS or mod.startswith(_EXPORTERS + "."):
                continue
            for alias in small.names:
                if alias.asname is not None:
                    raise UpgradeError(t("dsl.upgrade.import_as", code=module.code_for_node(small)))
                name = module.code_for_node(alias.name)
                if mod == "calendar" and name != "Month":
                    raise UpgradeError(t("dsl.upgrade.calendar_name", name=name))
                names[_place(mod, name, corpus_names, corpus)].add(name)

    rewritten = module.with_changes(body=kept)
    uses_os = want_os and any(isinstance(n, ast.Name) and n.id == "os" for n in ast.walk(ast.parse(rewritten.code)))
    lines = ["import os"] if uses_os else []
    lines += [format_import(m, names[m]) for m in order if names[m]]
    new_head = list(cst.parse_module("\n".join(lines) + "\n").body) if lines else []
    if new_head and imports:      # the blank lines between a docstring and the imports
        new_head[0] = new_head[0].with_changes(leading_lines=imports[0].leading_lines)
    after = module.with_changes(body=[*docstring, *new_head, *kept]).code
    check_unchanged(source, after)
    return after


def _is_main_block(stmt: ast.stmt) -> bool:
    """`if __name__ == "__main__":` and no `else:` — the block the codemod takes out."""
    if not isinstance(stmt, ast.If) or stmt.orelse or not isinstance(test := stmt.test, ast.Compare):
        return False
    return (isinstance(test.left, ast.Name) and test.left.id == "__name__" and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq) and isinstance(value := test.comparators[0], ast.Constant)
            and value.value == "__main__")


def _outside_the_head(tree: ast.Module) -> str:
    return ast.dump(ast.Module(body=[stmt for stmt in tree.body if not isinstance(stmt, ast.Import | ast.ImportFrom)
                                     and not _is_main_block(stmt)], type_ignores=[]))


def check_unchanged(before: str, after: str) -> None:
    """Refuse `after` unless it compiles, every record prints as in `before` (the ratchet's
    fingerprints and labels, the lines aside) and the module outside its imports and
    `__main__` is the same AST."""
    compile(after, "<upgrade-dsl>", "exec")
    prints = [(p.func, p.fingerprint, p.label) for p in ratchet.record_prints(before)]
    now = [(p.func, p.fingerprint, p.label) for p in ratchet.record_prints(after)]
    if prints != now:
        was, becomes = next((a, b) for a, b in zip_longest(prints, now, fillvalue=("", "", "")) if a != b)
        raise UpgradeError(t("dsl.upgrade.prints_would_move", was=was[2] or was[0], becomes=becomes[2] or becomes[0]))
    if _outside_the_head(ast.parse(before)) != _outside_the_head(ast.parse(after)):
        raise UpgradeError(t("dsl.upgrade.more_than_head"))
