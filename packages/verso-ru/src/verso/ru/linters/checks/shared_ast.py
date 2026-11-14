"""One parse and one walk of a DSL file, shared by every check that reads it.

`dsllint` runs some thirty-five checks over a file, and each reads the file and
asks for its tree on its own: a file was parsed once per check, and its tree
walked from the root once per check and again from inside for many. Here a text is
parsed once and a node walked once, for as long as the text is among the last
few parsed; every check is handed the same tree.

The tree is shared, so it is read-only: no check may change a node. Nothing
else changes — `parse` is `ast.parse` and `walk` yields `ast.walk`'s nodes in
`ast.walk`'s order. A text that does not parse is parsed again each time, and
raises the same `SyntaxError` each time.

Not a module check — nothing here reports anything.
"""

import ast
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

# The texts parsed last, newest at the end. A lint run reads one file at a time,
# so a handful is enough for every check of a file to find its tree.
_KEPT = 4
_trees: OrderedDict[str, ast.Module] = OrderedDict()
# A walk of a node of a kept tree: id(node) → (node, its walk). The node is held,
# so its id cannot pass to another while the entry stands; emptied when a tree
# leaves `_trees`.
_walks: dict[int, tuple[ast.AST, tuple[ast.AST, ...]]] = {}
_children: dict[int, tuple[ast.AST, tuple[ast.AST, ...]]] = {}
_WALKS_KEPT = 200_000
_lock = threading.Lock()


def parse(source: str) -> ast.Module:
    """`ast.parse(source)`, parsed once while the text is kept."""
    with _lock:
        tree = _trees.get(source)
        if tree is not None:
            _trees.move_to_end(source)
            return tree
    tree = ast.parse(source)
    with _lock:
        _trees[source] = tree
        if len(_trees) > _KEPT:
            _trees.popitem(last=False)
            _walks.clear()
            _children.clear()
    return tree


def _kept(memo: dict[int, tuple[ast.AST, tuple[ast.AST, ...]]], node: ast.AST,
          make) -> tuple[ast.AST, ...]:
    key = id(node)
    entry = memo.get(key)
    if entry is not None and entry[0] is node:
        return entry[1]
    nodes = tuple(make(node))
    with _lock:
        if len(memo) >= _WALKS_KEPT:        # nodes of trees parsed elsewhere, which no parse here retires
            memo.clear()
        memo[key] = (node, nodes)
    return nodes


def walk(node: ast.AST) -> tuple[ast.AST, ...]:
    """The nodes `ast.walk(node)` yields, in its order, walked once per node."""
    return _kept(_walks, node, ast.walk)


def children(node: ast.AST) -> tuple[ast.AST, ...]:
    """The nodes `ast.iter_child_nodes(node)` yields, in its order, listed once per node."""
    entry = _children.get(id(node))           # `_kept`'s lookup, inline: it runs once per node per visitor
    if entry is not None and entry[0] is node:
        return entry[1]
    return _kept(_children, node, ast.iter_child_nodes)


class Visitor(ast.NodeVisitor):
    """`ast.NodeVisitor`, visiting the same nodes in the same order, faster.

    A node's handler is looked up once per class of visitor and of node, and its
    children are listed once per node (`children`) for every visitor of the tree,
    where `NodeVisitor` looks both up again at every node. A handler is looked up on
    the visitor's class: one set on an instance is not seen.
    """

    _handlers: dict[type, Callable[[Any, ast.AST], Any]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.visit is not Visitor.visit:
            # `generic_visit` dispatches a child itself, past `visit`: an override would be skipped.
            raise TypeError(f"{cls.__name__}: a shared_ast.Visitor does not override visit()")
        cls._handlers = {}

    @classmethod
    def _handler(cls, kind: type) -> Callable[[Any, ast.AST], Any]:
        handler = getattr(cls, "visit_" + kind.__name__, None) or cls.generic_visit
        cls._handlers[kind] = handler
        return handler

    def visit(self, node: ast.AST):
        cls = type(self)
        handler = cls._handlers.get(node.__class__) or cls._handler(node.__class__)
        return handler(self, node)

    def generic_visit(self, node: ast.AST):
        cls = type(self)
        handlers = cls._handlers
        for child in children(node):
            (handlers.get(child.__class__) or cls._handler(child.__class__))(self, child)
