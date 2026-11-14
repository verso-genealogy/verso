"""The names oracle: the questions a corpus asks its naming functions, with the answers it got — and those
questions asked again of a lexicon.

The oracle file is TSV, one row a question:

    function <TAB> args_json <TAB> answer_json

  * a line starting with `#` is a comment (a header); the rows are sorted as lines;
  * `function` is the bare name of one of `FUNCTIONS`;
  * `args_json` is the JSON list of ALL the function's parameters, in order, defaults applied — so `f("x")` and
    `f("x", None)` are one question; a `Gender` is written "M", "F" or null;
  * `answer_json` is the answer in the same notation, or `{"raises": "<the exception's class>"}`;
  * JSON is written `ensure_ascii=False, sort_keys=True, separators=(",", ":")`.

A corpus records its oracle with its own tool, from the code of the day; `answers()` asks every row of it of
a lexicon — `names_registry.answering()`, so the workspace's own lexicon is left alone — and says, for each,
the answer and the lexicon keys the answer was looked up by (`names_registry.asked()`).
"""
from __future__ import annotations

import importlib
import inspect
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from verso.ru.gender import Gender
from verso.ru.messages import t
from verso.ru.naming import names_registry
from verso.ru.naming.lexicon import Lexicon

#: The functions an oracle may ask, by bare name → their module.
FUNCTIONS: dict[str, str] = {
    "canonicalize_name": "verso.ru.naming.orthography",
    "canonicalize_patronymic": "verso.ru.naming.orthography",
    "matching_base": "verso.ru.naming.names_registry",
    "father_name_for_patronymic": "verso.ru.naming.names_registry",
    "find_old_patronymic_by_modern": "verso.ru.naming.names_registry",
    "genitive_from_name": "verso.ru.naming.names_registry",
    "name_from_genitive": "verso.ru.naming.names_registry",
    "is_ignored_name": "verso.ru.naming.names_registry",
    "ignored_name_gender": "verso.ru.naming.names_registry",
    "is_ignored_patronymic": "verso.ru.naming.names_registry",
    "derive_patronymic": "verso.ru.naming.patronymics",
    "derive_old_patronymic": "verso.ru.naming.patronymics",
    "get_gender_from_name": "verso.ru.naming.gender_inference",
    "get_gender_from_old_patronymic": "verso.ru.naming.gender_inference",
    "validate_first_name": "verso.ru.naming.validation",
    "validate_old_patronymic": "verso.ru.naming.validation",
    "genitive_given_name": "verso.ru.naming.genitive",
    "feminine_patronymic": "verso.ru.naming.names_registry",
}
_JSON: dict[str, Any] = {"ensure_ascii": False, "sort_keys": True, "separators": (",", ":")}
_GENDER = {"M": Gender.MALE, "F": Gender.FEMALE}
_CELL = {Gender.MALE: "M", Gender.FEMALE: "F"}


class OracleError(Exception):
    """A question the replay cannot ask, or an answer it cannot write in the file's notation."""


class Row(NamedTuple):
    """One question of the oracle and the answer recorded for it, in the file's notation."""
    function: str
    args: tuple[Any, ...]
    answer: Any


class Asked(NamedTuple):
    """A question asked of a lexicon: the answer (the file's notation) and the keys it was looked up by."""
    answer: Any
    keys: frozenset[tuple[str, str]]


def dumps(value: Any) -> str:
    return json.dumps(value, **_JSON)


def encode(value: Any) -> Any:
    """An argument or an answer in the file's notation."""
    if isinstance(value, Gender):
        return _CELL[value]
    if value is None or type(value) in (str, bool):
        return value
    raise OracleError(str(t("oracle.cannot_write", value=repr(value), type=type(value).__name__)))


def parse(path: Path) -> list[Row]:
    """The rows of an oracle file."""
    out: list[Row] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            function, args, answer = line.split("\t")
            out.append(Row(function, tuple(json.loads(args)), json.loads(answer)))
    return out


def line_of(row: Row) -> str:
    return f"{row.function}\t{dumps(list(row.args))}\t{dumps(row.answer)}"


def write(path: Path, rows: Sequence[Row], header: str = "# names oracle v1: function<TAB>args_json<TAB>answer_json") -> None:
    """Write `rows` as an oracle file, sorted as lines."""
    path.write_text("\n".join([header, *sorted(line_of(r) for r in rows)]) + "\n", encoding="utf-8")


def _functions() -> dict[str, tuple[Callable[..., Any], list[bool]]]:
    """Each function and, for each of its parameters, whether it takes a `Gender`."""
    out: dict[str, tuple[Callable[..., Any], list[bool]]] = {}
    for name, module in FUNCTIONS.items():
        fn = getattr(importlib.import_module(module), name)
        out[name] = (fn, ["Gender" in str(p.annotation) for p in inspect.signature(fn).parameters.values()])
    return out


def ask(function: str, args: Sequence[Any]) -> Any:
    """`function` asked `args` (the file's notation) of the current lexicon; the answer in the file's notation."""
    fns = _functions()
    if function not in fns:
        raise OracleError(str(t("oracle.unknown_function", function=function, known=", ".join(sorted(fns)))))
    fn, gendered = fns[function]
    return _call(fn, gendered, args)


def _call(fn: Callable[..., Any], gendered: list[bool], args: Sequence[Any]) -> Any:
    call = [_GENDER[a] if is_gender and a is not None else a for a, is_gender in zip(args, gendered, strict=True)]
    try:
        answer = fn(*call)
    except Exception as exc:  # the oracle writes any exception the function raises as an answer
        return {"raises": type(exc).__name__}
    return encode(answer)  # an answer the notation cannot hold is the replay's error (OracleError), not an answer


def answers(rows: Sequence[Row], lexicon: Lexicon) -> list[Asked]:
    """Every row's question asked of `lexicon`, in order: the answer and the keys it was looked up by."""
    fns = _functions()
    out: list[Asked] = []
    with names_registry.answering(lexicon):
        for row in rows:
            if row.function not in fns:
                raise OracleError(str(t("oracle.unknown_function", function=row.function,
                                        known=", ".join(sorted(fns)))))
            fn, gendered = fns[row.function]
            with names_registry.asked() as keys:
                answer = _call(fn, gendered, row.args)
            out.append(Asked(answer, frozenset(keys)))
    return out


def same(a: Any, b: Any) -> bool:
    """Whether two answers in the file's notation are one answer (`True` is not `1`)."""
    return a == b and type(a) is type(b)
