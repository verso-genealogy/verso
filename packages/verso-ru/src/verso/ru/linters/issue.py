"""A linter's finding as a structure: its code, the variant of its message, the message's
parameters and the token it is about — the text is the catalog's (`CODE.variant` of
`verso/ru/locales/<lang>.toml`), put together when it is read.

    issue("CPL002", "no_father", line, level="warn", token="Иван", member=3)

`params` hold what the DSL wrote (a name, a status, a place, a kwarg, a member's number), the codes
of constants and numbers — never a word of a language: what reads in Russian is the catalog's. A
part of the text said in words of its own («member 3 (Иван)», «died») is a message itself, a
parameter rendered with the text; in the JSON it is its key and its params (`neutral`). The
text keeps the code's prefix as each linter wrote it (`codes.PREFIX`: `[CPL002] `, `ESC001 `, none),
so the findings read byte for byte as they did before the catalogs.

A check still answers with dicts (`as_dict`, `says`) — today's keys, `level`, `line`, `message`,
and `col`, `end_col`, `fix` where it has them — and its message is a `Text`: the rendered text,
a `str` to everything that reads it, carrying its `code`, `params` and `token` for `dsllint --json`,
the baseline and the readers that answer by code.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from verso.core.i18n import Message
from verso.ru.linters.codes import PREFIX
from verso.ru.messages import PACKAGE

type Param = str | int | Message | None



class Text(str):
    """A finding's message: its text, and what it is — the code, the params (`neutral`), the token."""
    code: str = ""
    variant: str = ""
    params: dict[str, Any] = {}  # noqa: RUF012 — set on each instance by `text()`
    token: str | None = None


def text(found: Issue) -> Text:
    out = Text(found.message)
    out.code, out.variant, out.params, out.token = found.code, found.variant, neutral(found.params), found.token
    return out


@dataclass(frozen=True)
class Issue:
    code: str
    variant: str
    level: str
    line: int | None              # None: a SyntaxError that names no line
    params: Mapping[str, Param] = field(default_factory=dict[str, Param])
    token: str | None = None
    col: int | None = None
    end_col: int | None = None
    fix: Mapping[str, Any] | None = None

    @property
    def key(self) -> str:
        return f"{self.code}.{self.variant}"

    @property
    def message(self) -> str:
        """The text, in the language of the moment, with the code's prefix as the linter wrote it."""
        return prefixed(self.code, str(Message(PACKAGE, self.key, self.params)))


def prefixed(code: str, text: str) -> str:
    style = PREFIX.get(code, "none")
    return f"[{code}] {text}" if style == "bracket" else f"{code} {text}" if style == "bare" else text


def issue(code: str, variant: str, line: int | None, *, level: str = "warn", token: str | None = None,
          col: int | None = None, end_col: int | None = None, fix: Mapping[str, Any] | None = None,
          **params: Param) -> Issue:
    return Issue(code, variant, level, line, params, token, col, end_col, fix)


def as_dict(found: Issue) -> dict[str, Any]:
    """The finding as the checks answer: today's keys, the message a `Text`."""
    out: dict[str, Any] = {"level": found.level, "line": found.line, "message": text(found)}
    if found.col is not None:
        out["col"] = found.col
    if found.end_col is not None:
        out["end_col"] = found.end_col
    if found.fix is not None:
        out["fix"] = dict(found.fix)
    return out


def neutral(params: Mapping[str, Param]) -> dict[str, Any]:
    """The params as no language writes them: a nested message is its key and its own params."""
    return {k: {"key": v.key, "params": neutral(v.params)} if isinstance(v, Message) else v  # pyright: ignore[reportArgumentType]
            for k, v in params.items()}


def says(code: str, variant: str, *, token: str | None = None, **params: Param) -> dict[str, Any]:
    """The `message` of a finding a check builds as a dict of its own (its keys in their order):
    `{"line": …, **says("CPL002", "no_father", who=…)}`."""
    return {"message": text(Issue(code, variant, "", 0, params, token))}


def line_text(path: object, found: Issue) -> str:
    """The finding as the text mode prints it: `path:line: message`."""
    return f"{path}:{found.line}: {found.message}"
