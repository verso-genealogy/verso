"""Two object graphs compared: the first place they differ, or None.

The test of the round trip DSL → JSON → objects. Strict where a consumer could tell
the difference: the type exactly (`5` is not `5.0`, `Status` not `str`), an object's
attributes and their ORDER (Verso's people index walks `__dict__` in order), a
`Status`'s gender, an enum member by identity. An entity — a record, a person, a set —
is matched one to one: the object reached twice on the left must be one object on the
right, so an aliased record set stays one set. A value object (`EventDate`) and a list
are compared by value.
"""
from __future__ import annotations

from enum import Enum

from verso.core.records.fields import vocabulary
from verso.core.written import WRAPPER_ATTR, WRITTEN_ATTR
from verso.core.messages import t


class _Walk:
    def __init__(self) -> None:
        self.voc = vocabulary()
        self.left: dict[int, int] = {}
        self.right: dict[int, int] = {}
        self.keep: list[object] = []          # ids stay valid while the walk lasts

    def walk(self, a: object, b: object, path: str) -> str | None:
        if type(a) is not type(b):
            return f"{path}: {type(a).__name__} ≠ {type(b).__name__}"
        if isinstance(a, Enum):
            return None if a is b else f"{path}: {a!r} ≠ {b!r}"
        scalar = next((s for s in self.voc.scalars.values() if isinstance(a, s.type)), None)
        if scalar is not None:     # a `Status` keeps its gender
            if not scalar.same(a, b):
                return f"{path}: {str(a)!r}/{getattr(a, '__dict__', {})} ≠ {str(b)!r}/{getattr(b, '__dict__', {})}"
            return None
        if a is None or isinstance(a, (str, int, float)):
            return None if a == b else f"{path}: {a!r} ≠ {b!r}"
        if isinstance(a, dict):
            return self.mapping(a, b, path)  # type: ignore[arg-type]
        if isinstance(a, (list, tuple)):
            if len(a) != len(b):  # type: ignore[arg-type]
                return str(t("records.graph.length", path=path, left=len(a), right=len(b)))  # type: ignore[arg-type]
            for i, (x, y) in enumerate(zip(a, b, strict=True)):  # type: ignore[arg-type]
                found = self.walk(x, y, f"{path}[{i}]")
                if found:
                    return found
            return None
        if not hasattr(a, "__dict__"):
            return None if a == b else f"{path}: {a!r} ≠ {b!r}"
        if type(a) not in self.voc.value_classes:
            seen_a, seen_b = self.left.get(id(a)), self.right.get(id(b))
            if seen_a is not None or seen_b is not None:
                return None if seen_a == id(b) and seen_b == id(a) else str(t("records.graph.other_object", path=path))
            self.left[id(a)], self.right[id(b)] = id(b), id(a)
            self.keep += [a, b]
        return self.mapping(vars(a), vars(b), path)

    def mapping(self, a: dict[str, object], b: dict[str, object], path: str) -> str | None:
        # What a call wrote is a set of arguments: records v1 groups them by event and name,
        # so their order comes back grouped — and no reader of `_written` reads its order; nor of
        # what the wrappers kept beside it (`_wrapper`), grouped alike.
        unordered = path.rpartition(".")[2] in (WRITTEN_ATTR, WRAPPER_ATTR)
        if (sorted(a) != sorted(b)) if unordered else (list(a) != list(b)):
            return str(t("records.graph.fields", path=path, left=list(a), right=list(b)))
        for key, value in a.items():
            found = self.walk(value, b[key], f"{path}.{key}" if path else key)
            if found:
                return found
        return None


def first_difference(a: object, b: object, path: str = "") -> str | None:
    """Where two graphs first differ — `births.records[0].child.name_orig: 'Иванъ' ≠ 'Петръ'`."""
    return _Walk().walk(a, b, path)
