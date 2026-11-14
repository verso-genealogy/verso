"""The linters' findings of one DSL file, each with the mechanical repair its linter
offers (what the App requires of the library, from `verso.app_dsl.validate` before 0.1.0): what a Verso save
is checked on, and what it strips a redundant value with.

Measured in the file's own place: dsllint's checks gate on the file name
(`_confessions_`, `_name_lists_`), so a text is linted as a copy under the same
village, year and name, never as a file elsewhere.
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, cast

from verso.ru.linters.dsllint import LINTERS, check_file_json
from verso.ru.messages import t

ADVISORY: frozenset[str] = frozenset(linter.name for linter in LINTERS if linter.advisory)


class Fix(TypedDict):
    """A finding's repair, as the linters write it (`dsllint._check_single_line_calls_structured`,
    `census_status_redundancy._status_fix`, `birth_redundancy._kwarg_fix`,
    `deaths_residence._check_death`): `remove_kwarg` takes `kwarg=` off the call,
    `remove_arg` the positional `kwarg` names between `col` and `end_col`,
    `replace_kwarg` writes `new` for `old`. `col` is the 0-based column, in characters
    on the finding's line, where `kwarg=` (or the value) starts: a line may hold several."""
    type: Literal["remove_kwarg", "remove_arg", "replace_kwarg"]
    col: int
    kwarg: NotRequired[str]
    end_col: NotRequired[int]
    old: NotRequired[str]
    new: NotRequired[str]


@dataclass(frozen=True)
class Finding:
    linter: str
    level: str
    line: int
    message: str
    # The linter's mechanical repair, when it has one: `remove_kwarg` and the
    # character column that pins the occurrence. Not part of what the finding IS.
    fix: Fix | None = field(default=None, compare=False)
    # What the finding is, whatever language its message speaks — its code, the variant of
    # its message, the message's params (a nested message as its key and params) and the token
    # it is about; where it is — the columns its linter pins. None of them is part of equality.
    code: str = field(default="", compare=False)
    variant: str = field(default="", compare=False)
    params: dict[str, Any] = field(default_factory=dict[str, Any], compare=False)
    token: str | None = field(default=None, compare=False)
    col: int | None = field(default=None, compare=False)
    end_col: int | None = field(default=None, compare=False)

    @property
    def advisory(self) -> bool:
        return self.linter in ADVISORY

    def __str__(self) -> str:
        return str(t("linters.finding", linter=self.linter, line=self.line, message=self.message))


def _finding(linter: str, issue: dict[str, Any]) -> Finding:
    message = issue.get("message", "")
    col, end_col = issue.get("col"), issue.get("end_col")
    return Finding(linter, str(issue.get("level", "")), int(issue.get("line") or 0), str(message),
                   cast(Fix, issue.get("fix")) or None, code=getattr(message, "code", ""),
                   variant=getattr(message, "variant", ""), params=dict(getattr(message, "params", {})),
                   token=getattr(message, "token", None), col=col if isinstance(col, int) else None,
                   end_col=end_col if isinstance(end_col, int) else None)


def lint_file(path: Path) -> list[Finding]:
    """Every finding of every linter on the file where it lies."""
    return [_finding(result["linter"], issue) for result in check_file_json(path) for issue in result["issues"]]


def lint_text(text: str, like: Path) -> list[Finding]:
    """`text` linted as the file `like` would be, without writing `like`: a
    copy under the same village, year and name in a directory of its own —
    what a book's defaults change is checked on before anything is written."""
    with tempfile.TemporaryDirectory(prefix="verso-lint-") as tmp:
        copy = Path(tmp, like.parent.parent.name, like.parent.name, like.name)
        copy.parent.mkdir(parents=True)
        copy.write_bytes(text.encode("utf-8"))
        return lint_file(copy)


def _identity(f: Finding) -> tuple[str, ...]:
    if f.code:
        return (f.linter, f.code, f.variant, json.dumps(f.params, sort_keys=True, ensure_ascii=False))
    return (f.linter, f.message)


def new_findings(before: list[Finding], after: list[Finding]) -> list[Finding]:
    """What `after` has that `before` did not — line numbers aside, since an
    edit above a finding moves it without changing it. A finding is its code and params,
    whatever its message says; one without a code (from before the codes) is its message."""
    budget = Counter(_identity(f) for f in before)
    out = []
    for f in after:
        key = _identity(f)
        if budget[key]:
            budget[key] -= 1
        else:
            out.append(f)
    return out
