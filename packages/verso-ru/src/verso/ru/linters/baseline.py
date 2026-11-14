#!/usr/bin/env python3
"""A ratchet for the advisory DSL checks.

Advisory linters print and exit 0 (see `dsllint.LINTERS`), which is right for
findings the corpus cannot reach zero on today — census heuristics, unmapped
places, estate mismatches. The cost is that CI is equally green at 171 findings
and at 500: a newly introduced CPL002 is indistinguishable from one that has
been sitting in Заманиловка since 1719 was transcribed.

This module parks the existing findings in a baseline file so the debt stops
blocking CI while still being counted, and anything NOT in it fails — the same
bargain `verso.ru.consolidation.stale_stubs` already makes for CST001/CST002.

**Identity.** A finding is its file, its code and its params — what the DSL wrote, in no
language (v2) — never the line number: an edit anywhere above a finding shifts its line,
and a baseline keyed on lines would go stale on every unrelated commit. Nor its text: a message
reworded, or read in another language, keeps its row.
`KEY = sha256(file, code, params as JSON with sorted keys, nth)[:16]`.

Each row carries a truncated excerpt of the message beside the hash — informational only, never
matched — so the file can still be read by a human triaging it.

A file opens with `# baseline v2`. One without it is v1 (keyed by the message, until 0.1.0): no
row of it would match, so it is refused — «базлайн v1 — verso dsllint --baseline FILE --update-baseline --villages» — rather than
read as an empty baseline. A finding its linter gave no code has no key: it is always new, and
never written.

Run (via dsllint):
    python3 -m verso.ru.linters.dsllint --baseline dsllint_baseline.tsv <files>
    python3 -m verso.ru.linters.dsllint --baseline dsllint_baseline.tsv --update-baseline <files>
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from verso.ru.messages import t

DEFAULT_NAME = "dsllint_baseline.tsv"
KEY_LEN = 16
_EXCERPT_LEN = 120

_WARNING_RE = re.compile(r'^(?:warning:\s*)?(.+?):(\d+):\s*(.*)$')
_CODE_RE = re.compile(r'^\[([A-Z]{3}\d{3})\]\s*(.*)$')

_MARKER = "# baseline v2"
_HEADER = _MARKER + """
# Advisory DSL-linter findings that already existed when the ratchet was
# introduced (see verso/ru/linters/baseline.py). Every line is real debt — an
# unmapped place silently dropped from the generated TF, a census member
# attached to no union, an age that contradicts the revision gap.
#
# This is a BASELINE, not an allowlist: nothing here is "fine", it is merely
# known. Anything NOT listed fails the check. Fix some, then shrink it with:
#   verso dsllint --baseline <this file> --update-baseline --villages
#
# Columns: CODE <tab> KEY <tab> FILE <tab> excerpt (informational, truncated —
# only CODE+KEY are matched). KEY is the finding's code and params (v2), in no language.
"""


@dataclass(frozen=True)
class Finding:
    file: str
    code: str
    message: str
    line: int = 0
    nth: int = 0
    """Which occurrence of an IDENTICAL (file, code, params) this is.

    Without it the ratchet leaks: one file carries the same
    `redundant patronymic "Ivanov"` finding on several lines, and keying on
    what it says alone folds them into a single baseline row — after which
    fixing one and introducing another elsewhere in that file nets out to no
    change. Numbering makes the count itself part of the identity: a fourth
    occurrence is a key nobody baselined, while dropping to two simply retires
    the last ordinal. Set by `number()`; do not assign by hand.
    """
    params_json: str | None = None
    """The finding's params as JSON with sorted keys (`structured()`); None for a finding read
    from its text alone, which has no key."""
    printed: str = ""
    """The message as its linter printed it, prefix and all (`structured()`)."""

    def key(self) -> str | None:
        if self.code == "-" or self.params_json is None:
            return None
        raw = f"{self.file}\n{self.code}\n{self.params_json}\n{self.nth}".encode()
        return hashlib.sha256(raw).hexdigest()[:KEY_LEN]

    def excerpt(self) -> str:
        m = self.message
        return m if len(m) <= _EXCERPT_LEN else m[:_EXCERPT_LEN - 1] + "…"

    def row(self) -> str | None:
        if (key := self.key()) is None:
            return None
        return f"{self.code}\t{key}\t{self.file}\t{self.excerpt()}"

    def line_text(self) -> str:
        if self.printed:
            return f"{self.file}:{self.line}: {self.printed}"
        return f"{self.file}:{self.line}: [{self.code}] {self.message}"


def _normalise(text: str) -> str:
    """Collapse whitespace so re-wrapping a message does not move its key."""
    return " ".join(text.split())


def parse_warning(text: str) -> Finding | None:
    """`[warning: ]path:line: [CODE] message` → `Finding`, or None if unparseable."""
    m = _WARNING_RE.match(text.strip())
    if not m:
        return None
    path, line, rest = m.group(1).strip(), int(m.group(2)), m.group(3)
    code = "-"
    if (c := _CODE_RE.match(rest.strip())):
        code, rest = c.group(1), c.group(2)
    return Finding(file=path, code=code, message=_normalise(rest), line=line)


def structured(found: Finding, *, code: str, params: dict[str, Any], printed: str = "") -> Finding:
    """`found` (read from its text) with what it is: its code (its text's, where `code` is empty)
    and params, and the message as printed."""
    return replace(found, code=code or found.code, printed=printed,
                   params_json=json.dumps(params, sort_keys=True, ensure_ascii=False))


def number(findings: list[Finding]) -> list[Finding]:
    """Stamp each finding with its occurrence index among identical siblings.

    Order follows the linters' own emission order (per file, per check), which
    is line order — so retiring the first of three identical findings renumbers
    the survivors onto the first two keys rather than inventing new ones.
    """
    counts: dict[tuple[str, str, str | None], int] = {}
    out: list[Finding] = []
    for f in findings:
        ident = (f.file, f.code, f.params_json)
        n = counts.get(ident, 0)
        counts[ident] = n + 1
        out.append(replace(f, nth=n))
    return out


def load(path: Path) -> set[str]:
    """The set of baselined keys. A missing file is an empty baseline; a v1 file is refused."""
    if not path.is_file():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    keys: set[str] = set()
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        cols = ln.split("\t")
        if len(cols) >= 2:
            keys.add(cols[1])
    if keys and (not lines or lines[0].strip() != _MARKER):
        raise SystemExit(f"{path}: {t('baseline.v1')}")
    return keys


def write(path: Path, findings: list[Finding]) -> Path:
    """Rewrite the baseline. Rows are sorted so diffs stay readable."""
    rows = sorted({row for f in number(findings) if (row := f.row()) is not None})
    path.write_text(_HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return path


def classify(findings: list[Finding], baselined: set[str]) -> tuple[list[Finding], int]:
    """`(findings absent from the baseline, count of baselined ones now gone)`.

    The second number is what keeps the ratchet turning: it is the prompt to
    re-run `--update-baseline` so fixed debt cannot be silently re-spent.
    """
    numbered = number(findings)
    seen = {k for f in numbered if (k := f.key()) is not None}
    new = [f for f in numbered if f.key() is None or f.key() not in baselined]
    return new, len(baselined - seen)
