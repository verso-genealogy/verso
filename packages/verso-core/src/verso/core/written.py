"""What a DSL call wrote, kept on the object it built (records v1).

A built record cannot tell a value its call wrote from one a wrapper, the book's
defaults or a constructor derived — `Birth.__init__` fills a child's surname in
place, `birth_month()` the month. The records JSON keeps the two apart
(`written` / `derived`), so each DSL factory remembers the arguments it was
given: `captures_written` sets `_written` on what it returns, parameter → value,
the explicit ones only (an explicit `None` too). `copy.deepcopy` in the wrappers
carries it along.

Only values are kept — a person, a relative or a record is its own object with
its own `_written`, and a factory's `*records` are structure. A class whose
instances are values (`EventDate`, `RecordDefaults`) says so with
`_record_value = True`; this module imports nothing of the package, because
`verso.ru.relationship`, below the domain, decorates `relative()` with it.
"""
from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from enum import Enum
from typing import Any

WRITTEN_ATTR = "_written"
RECORD_VALUE_ATTR = "_record_value"
VERB_ATTR = "_verb"        # which of a class's verbs built an object (`Vocabulary.verbs`)
# What a wrapper around a record (a `page()`, a month section) would have set on a field the record's
# own call wrote — the call's value stands, the wrapper's is kept here (`shadow`): attribute → value.
WRAPPER_ATTR = "_wrapper"


def is_value(value: object) -> bool:
    """A scalar, an enum member, an instance of a `_record_value` class, or a
    list or tuple of those — what `_written` keeps."""
    if value is None or isinstance(value, (str, int, float, Enum)):
        return True
    if isinstance(value, (list, tuple)):
        return all(is_value(item) for item in value)
    return bool(getattr(type(value), RECORD_VALUE_ATTR, False))


def captures_written[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """`fn` that also records, on what it returns, the value arguments it was
    called with: positional ones by their parameter's name, `*args` left out."""
    positional = [p.name for p in inspect.signature(fn).parameters.values()
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD)]

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        result = fn(*args, **kwargs)
        given: dict[str, Any] = dict(zip(positional, args, strict=False))  # beyond them: *records
        given.update(kwargs)
        setattr(result, WRITTEN_ATTR, {k: v for k, v in given.items() if is_value(v)})
        return result

    return wrapper


def verb_of(obj: object) -> str | None:
    """The name of the verb (factory) that built `obj`, when its factory said so."""
    return getattr(obj, VERB_ATTR, None)


def written_of(obj: object) -> dict[str, object] | None:
    """What the call that built `obj` wrote, or None when no factory built it."""
    return getattr(obj, WRITTEN_ATTR, None)


def shadow(record: object, attr: str, value: object) -> None:
    """Keep `value`, what a wrapper around `record` gives `attr`, where the record's own call wrote
    `attr` and the wrapper therefore leaves it as written: a `page("11", …)` around a record that writes
    `page="12"`, a month section around one that writes its months. The innermost wrapper's value is the
    one kept (it runs first); nothing is kept for a value the wrapper does not give (None) or a field the
    call did not write — a wrapper that sets the field leaves its value on the record itself."""
    written = written_of(record)
    if value is None or written is None or attr not in written:
        return
    kept: dict[str, object] = vars(record).setdefault(WRAPPER_ATTR, {})
    kept.setdefault(attr, value)


def wrapper_of(obj: object) -> dict[str, object]:
    """What the wrappers around `obj` would have set on fields its call wrote (`shadow`), by attribute."""
    return getattr(obj, WRAPPER_ATTR, {})
