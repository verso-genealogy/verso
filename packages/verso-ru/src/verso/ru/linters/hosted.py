"""Each linter code's readiness for records JSON — what it needs once there is no DSL source.

The table is `hosted.toml`, one row per code of `codes.LINTER_CODES`:

* `class` — `written` (what one record's calls wrote, and the library's own tables),
  `derived` (values the factories or the wrappers derive — after `replay`), `context` (data
  outside the record: the names tables, the corpus's places, its estates, the book, the file),
  `source` (the form of the source text — no meaning without a file);
* `severity` — `refuse` for a hard check of `dsllint`, `warn` for an advisory one;
* `scope` — where the code is answered, when there is one record to read and not the file: `record` (one
  record — a двор for a roll — with its set's header, `on_json.lint_record`; a finding the same rule addresses
  to the set itself, like ZGS004's on a book's defaults, is `on_json.lint_header`'s), `set` (the set's header
  alone, `lint_header`: ZGS003), `file` (a record needs one fact of the whole file, `file_in_scope`: ULC001) and
  `source` (the form of the source text, which no JSON answers; the class `source` says it too) and `layer` (a
  names layer's files, read in the sum of the layers under it — no record is read: the LEX codes);
* `needs` — which of `names`, `places`, `estates`, `book`, `file` the code reads: every `context` code names one, and a code of
  another class that asks the names table all the same (it reads a name, or replays the file, which builds its persons
  from it) says `names` — the workspace without one is what `lint_records` gives a warning for (H7);
* `as` — for a positional code, the keyword code it folds into: one rule answers both;
* `forms` — the variants of a code that say the form of an argument and nothing else: each is `said`
  (the variant `dsllint` gives), `read` (the variant the JSON speaks, the keyword code's), `rename` (params
  renamed, old to new) and `unquote` (params the check wrote as Python writes a text, `'Ротозеево'`).
  `fold` applies them, with `as`, to a finding of the source: the one place the positional and the
  keyword form are one;
* `redundant` — true where the finding is a redundant argument: a written value equal to the one the record
  inherits (the book's default, a derivation of the factory), which the fix removes. Every such code is
  `derived`, and a positional code folding into one (`as`) says it too; absent, false. Read it as
  `readiness()[code].redundant`;
* `note` — one line: what it checks and what it reads.

`verso.ru.linters.on_json` walks the JSON for the codes it supports; the table says how far the
rest is.
"""
from __future__ import annotations

import ast
import tomllib
from functools import cache
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from verso.ru.messages import t

__all__ = ["CLASSES", "NEEDS", "SCOPES", "Form", "Readiness", "fold", "readiness"]

CLASSES = ("written", "derived", "context", "source")
NEEDS = ("names", "places", "estates", "book", "file")
SCOPES = ("record", "set", "file", "source", "layer")


@dataclass(frozen=True)
class Form:
    """A variant of the source that the JSON speaks as another (`forms` of `hosted.toml`)."""
    said: str
    read: str
    rename: tuple[tuple[str, str], ...] = ()
    unquote: tuple[str, ...] = ()


@dataclass(frozen=True)
class Readiness:
    cls: str
    severity: str
    needs: tuple[str, ...]
    note: str
    as_code: str | None = None
    forms: tuple[Form, ...] = ()
    redundant: bool = False         # the finding is a redundant argument (`redundant` of `hosted.toml`)
    scope: str = "record"           # where the code is answered (`scope` of `hosted.toml`)


def readiness() -> dict[str, Readiness]:
    """Every code's row of `hosted.toml`, in its order; a row it cannot read is refused. The file is the package's own
    and read once; each call gets a table of its own."""
    return dict(_read_table())


@cache
def _read_table() -> dict[str, Readiness]:
    table = tomllib.loads(files("verso.ru.linters").joinpath("hosted.toml").read_text(encoding="utf-8"))
    out: dict[str, Readiness] = {}
    for code, row in table.items():
        cls, severity, needs = row["class"], row["severity"], tuple(row.get("needs", ()))
        redundant = row.get("redundant", False)
        scope = row.get("scope")
        if (cls not in CLASSES or severity not in ("refuse", "warn") or not set(needs) <= set(NEEDS)
                or not isinstance(redundant, bool) or (redundant and cls != "derived")
                or scope not in SCOPES or (scope == "source") != (cls == "source")):
            raise ValueError(t("hosted.bad_row", code=code, row=repr(row)))
        forms = tuple(Form(f["said"], f["read"], tuple(f.get("rename", {}).items()), tuple(f.get("unquote", ())))
                      for f in row.get("forms", ()))
        out[code] = Readiness(cls, severity, needs, row["note"], row.get("as"), forms, redundant, scope)
    return out


def fold(code: str, variant: str, params: Mapping[str, Any],
         table: Mapping[str, Readiness] | None = None) -> tuple[str, str, dict[str, Any]]:
    """A finding of the source as the JSON speaks it: the keyword code for a positional one (`as`), the variant
    and params its `forms` name. A finding no row folds is returned as it is. `table` is `readiness()` when
    the caller holds it."""
    row = (table if table is not None else readiness()).get(code)
    if row is None:
        return code, variant, dict(params)
    out = dict(params)
    for form in row.forms:
        if form.said == variant:
            renamed = dict(form.rename)
            out = {renamed.get(k, k): ast.literal_eval(v) if k in form.unquote else v for k, v in params.items()}
            variant = form.read
            break
    return row.as_code or code, variant, out
