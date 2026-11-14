"""The record sets a loaded DSL module binds — each one once.

A file may bind one record set to two names: a year file ending with
`village_deaths_1913 = parish_deaths_1913`. That is one book, and a
reader of the module's variables takes it once, under the first name that binds it —
as the records export writes the second name as `alias_of` (`verso.core.records.encode`).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def record_sets(namespace: Mapping[str, object], kinds: type | tuple[type, ...]) -> dict[str, Any]:
    """The values of `kinds` in `namespace`, in its order, each under the first name binding it."""
    out: dict[str, Any] = {}
    seen: set[int] = set()
    for name, value in namespace.items():
        if isinstance(value, kinds) and id(value) not in seen:
            seen.add(id(value))
            out[name] = value
    return out
