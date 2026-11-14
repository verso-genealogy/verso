"""One parse and one walk of a DSL file for every check (`verso.ru.linters.checks.shared_ast`): the same tree for
the same text, `ast.walk`'s nodes and `NodeVisitor`'s visits in their order."""
from __future__ import annotations

import ast

import pytest

from verso.ru.linters.checks import shared_ast

SOURCE = '''\
from verso.ru.dsl import *

DEFAULTS = RecordDefaults(residence="Маниловка")

births = birth_records(
    "ГА", "1", "2", "3", "Маниловка", "Чичиковская", 1801,
    page("5", birth_month(Month.MAY,
        birth(1, M, 3, 4, father=person("Иван", "Петров"), mother=person("Мария", "Сидорова")),
        birth(2, F, 9, 10, father=person("Петр", "Иванов"), comment="двойня"),
    ), reviewed=True),
    defaults=DEFAULTS,
)
'''


def test_one_text_is_parsed_once_and_reads_as_ast_parse():
    tree = shared_ast.parse(SOURCE)
    assert shared_ast.parse(SOURCE) is tree
    assert shared_ast.parse("".join(SOURCE)) is tree           # the same text, another string
    assert ast.dump(tree, include_attributes=True) == ast.dump(ast.parse(SOURCE), include_attributes=True)
    assert shared_ast.parse(SOURCE + "\n") is not tree


def test_a_text_that_does_not_parse_raises_each_time():
    for _ in range(2):
        with pytest.raises(SyntaxError) as raised:
            shared_ast.parse("birth(1, M,\n")
        assert raised.value.lineno == 1


def test_a_tree_is_kept_while_its_text_is_among_the_last_parsed():
    tree = shared_ast.parse(SOURCE)
    for i in range(shared_ast._KEPT):
        shared_ast.parse(f"x = {i}\n")
    assert shared_ast.parse(SOURCE) is not tree
    assert ast.dump(shared_ast.parse(SOURCE)) == ast.dump(tree)


def test_a_walk_is_ast_walk_in_its_order():
    tree = shared_ast.parse(SOURCE)
    assert shared_ast.walk(tree) == tuple(ast.walk(tree))
    assert shared_ast.walk(tree) is shared_ast.walk(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "page")
    assert shared_ast.walk(call) == tuple(ast.walk(call))
    other = ast.parse(SOURCE)                       # a tree parsed elsewhere is walked as it is
    assert [ast.dump(n) for n in shared_ast.walk(other)] == [ast.dump(n) for n in ast.walk(other)]
    assert shared_ast.children(call) == tuple(ast.iter_child_nodes(call))


class _Trace:
    """What a visitor saw, in its order: every Call, every Name below a Call, and every Constant — through a handler
    that goes on below and one that stops, as the checks' visitors do."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self.calls = 0

    def visit_Call(self, node: ast.Call) -> None:
        self.calls += 1
        self.seen.append(f"call {ast.unparse(node.func)}")
        self.generic_visit(node)  # type: ignore[attr-defined]
        self.calls -= 1

    def visit_Name(self, node: ast.Name) -> None:
        if self.calls:
            self.seen.append(f"name {node.id}")

    def visit_keyword(self, node: ast.keyword) -> None:
        self.seen.append(f"kw {node.arg}")
        if node.arg != "comment":       # a handler that stops: what is below it is not visited
            self.visit(node.value)  # type: ignore[attr-defined]

    def visit_Constant(self, node: ast.Constant) -> None:
        self.seen.append(f"const {node.value!r}")


class _Stdlib(_Trace, ast.NodeVisitor):
    pass


class _Shared(_Trace, shared_ast.Visitor):
    pass


def test_a_visitor_visits_what_node_visitor_visits_in_its_order():
    tree = shared_ast.parse(SOURCE)
    stdlib, shared = _Stdlib(), _Shared()
    stdlib.visit(tree)
    shared.visit(tree)
    assert shared.seen == stdlib.seen
    assert "kw comment" in shared.seen and "const 'двойня'" not in shared.seen
    again = _Shared()                               # a second visitor of the tree, on the kept children
    again.visit(tree)
    assert again.seen == stdlib.seen


def test_a_visitor_that_overrides_visit_is_refused():
    with pytest.raises(TypeError, match="does not override visit"):
        class _Own(shared_ast.Visitor):  # pyright: ignore[reportUnusedClass]
            def visit(self, node: ast.AST) -> None:
                pass
