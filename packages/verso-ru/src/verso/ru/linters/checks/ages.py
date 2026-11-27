#!/usr/bin/env python3
"""AST-based linter to validate `age`, `groom_age`, and `bride_age` literals
on `death(...)` and `marriage(...)` DSL calls (and a card's `age=`), written as
keywords or in their positional places.

Accepted shapes:
  - `None` (or omitted)
  - integer / float literal — interpreted as years
  - string literal made of `<number><unit>` tokens separated by whitespace,
    where `<unit>` is one of the recognized Russian abbreviations for years,
    months, weeks, or days. Examples: "19 лет 6 мес", "6 м", "1 нед", "3 дн".

Anything else (negative numbers, Latin units, junk text, repeated unit) is
flagged. The downstream `split_age()` in `verso/ru/ages.py` falls
back to dumping unparseable strings into the *Лет* column, so flagging here
is the only signal authors get that the data won't be properly tabulated.

AGE001 covers the opposite failure: an age that *parses* but spells a WHOLE
number of years as a string — `age="1 год"`, `age="5 лет"`, `age="70"` — where
the integer form is meant. It is not cosmetic. The generator appends `" лет"` to
the death document's *Умерший* line unless the age ends in a recognised SUB-year
unit (мес/нед/дн), so a whole-year string emits the unit twice:
«Умерший: … Феодора Николаевна 1 год лет». `split_age()` returns the identical
(Лет, Месяцев, Недель, Дней) tuple for `1` and `"1 год"`, so writing the integer
costs nothing and reads correctly. Idioms (`"полгода"`, `"полтора года"`),
sub-year units and compound ages are deliberately NOT flagged — the integer
cannot express them.
"""

import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

from verso.ru.ages import AGE_CALLS, AGE_KWARGS, AGE_NUMBER, whole_years
from verso.ru.linters.checks.census_redundancy import _char_col
from verso.ru.linters.issue import as_dict, issue as finding, line_text, says
from verso.ru.linters.checks import shared_ast

# Mirrors _AGE_UNIT_TO_SLOT in csv_familio_exporters.py — keep in sync.
_VALID_UNITS = frozenset({
    "г", "л", "лет", "год", "года", "годов",  # i18n: content — the age units the sources write
    "м", "мес", "месяц", "месяца", "месяцев",  # i18n: content — the age units the sources write
    "н", "нед", "неделя", "недели", "недель",  # i18n: content — the age units the sources write
    "д", "дн", "день", "дня", "дней",  # i18n: content — the age units the sources write
})

_TOKEN_RE = re.compile(rf'({AGE_NUMBER})\s*([а-яё]+)\.?', re.IGNORECASE)  # i18n: content — the age units the sources write
_AGE_KWARGS = AGE_KWARGS
_RECORD_FUNCS = AGE_CALLS
# The ages a call may pass positionally: `death(record_num, gender, d_day, b_day,
# d_month, b_month, deceased, age, …)`, `marriage(record_num, w_day, w_month, groom,
# bride, groom_marriage_num, bride_marriage_num, groom_age, bride_age, …)`. A card's
# age is keyword-only. tests/test_check_ages.py holds them to the factories' signatures.
AGE_POSITIONS: dict[str, dict[int, str]] = {
    "death": {7: "age"},
    "marriage": {7: "groom_age", 8: "bride_age"},
}

_BARE_DIGITS_RE = re.compile(r'^\s*(\d+)\s*$')

# Mirrors _AGE_IDIOMS in csv_familio_exporters.py — keep in sync.
_VALID_IDIOMS = frozenset({
    "полгода", "пол года", "полу года", "полтора года",  # i18n: content — the age units the sources write
})


def is_valid_age_string(s: str) -> bool:
    """Return True iff `s` parses cleanly as a sequence of <num><unit> tokens
    using only recognized Cyrillic units, with no leftover junk and no
    repeated unit slot."""
    s = s.strip()
    if not s:
        return False
    if s.isdigit() or re.fullmatch(AGE_NUMBER, s):   # «2», «2½», «½»
        return True
    if s.lower() in _VALID_IDIOMS:
        return True
    seen_slots: set[str] = set()
    pos = 0
    matched_any = False
    for m in _TOKEN_RE.finditer(s):
        if s[pos:m.start()].strip():
            return False
        unit = m.group(2).lower().rstrip(".")
        if unit not in _VALID_UNITS:
            return False
        # Reject duplicate units (e.g. "19 лет 19 лет").
        if unit in seen_slots:
            return False
        seen_slots.add(unit)
        pos = m.end()
        matched_any = True
    if not matched_any:
        return False
    return not s[pos:].strip()


def said_unknown(kwarg: str, literal: str) -> dict[str, object]:
    return says("AGE002", "unrecognized", kwarg=kwarg, literal=repr(literal))


def _format_message(kwarg: str, literal: str) -> str:
    return str(said_unknown(kwarg, literal)["message"])


def _integer_age_for(s: str) -> str | None:
    """The digit form of `s` when it spells a WHOLE number of years, else None
    (`verso.ru.ages.whole_years`, the rule a page's edit writes by too)."""
    return whole_years(s)


def said_age001(kwarg: str, literal: str, digits: str, func: str) -> dict[str, object]:
    if _BARE_DIGITS_RE.match(literal):
        return says("AGE001", "quoted_number", kwarg=kwarg, literal=literal, digits=digits)
    # The doubled-unit rendering is specific to the death document's
    # `Умерший:` line, so only claim it where it actually happens.
    return says("AGE001", "unit_death" if func == "death" else "unit", kwarg=kwarg, literal=literal, digits=digits)


def _format_age001(kwarg: str, literal: str, digits: str, func: str) -> str:
    return str(said_age001(kwarg, literal, digits, func)["message"])


class _Age001(NamedTuple):
    """One AGE001 finding. `src`/`col` are None when the literal's source text
    could not be located (multi-line literal, or source unavailable), which
    costs only the quick fix — the diagnostic is still reported."""
    line: int
    kwarg: str
    literal: str
    digits: str
    func: str
    src: str | None
    col: int | None


class AgeChecker(shared_ast.Visitor):
    """Walk a DSL file and validate the ages on every death()/marriage()
    call, by keyword or in their positional place. Violations stored as (line, kwarg, literal_repr); AGE001 findings —
    parseable ages that should be integers — stored separately in
    `normalizable` as `_Age001` records."""

    def __init__(self, filepath: Path, lines: list[str] | None = None):
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []
        self.normalizable: list[_Age001] = []

    def visit_Call(self, node: ast.Call) -> None:
        func_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if func_name in _RECORD_FUNCS:
            for index, arg in AGE_POSITIONS.get(str(func_name), {}).items():
                if index < len(node.args):
                    self._check_age(node.args[index], arg, str(func_name))
            for kw in node.keywords:
                # `arg` is None only for **kwargs unpacking, never for a named
                # age kwarg — binding it narrows the Optional for the checker.
                arg = kw.arg
                if arg is not None and arg in _AGE_KWARGS:
                    self._check_age(kw.value, arg, str(func_name))
        self.generic_visit(node)

    def _check_age(self, v: ast.expr, arg: str, func: str) -> None:
        """Validate one age, written as `arg=v` or in `arg`'s place."""
        # Literal None or numeric → ok.
        if isinstance(v, ast.Constant):
            value = v.value
            if value is None:
                return
            if isinstance(value, bool):
                # bool is an int subclass — disallow explicitly.
                self.violations.append((v.lineno, arg, repr(value)))
                return
            if isinstance(value, (int, float)):
                if value < 0:
                    self.violations.append((v.lineno, arg, repr(value)))
                return
            if isinstance(value, str):
                if not is_valid_age_string(value):
                    self.violations.append((v.lineno, arg, value))
                    return
                digits = _integer_age_for(value)
                if digits is not None:
                    src, col = self._literal_source(v)
                    self.normalizable.append(
                        _Age001(v.lineno, arg, value, digits, func, src, col))
                return
            self.violations.append((v.lineno, arg, repr(value)))
            return
        # Unary minus on a numeric literal → negative age, reject.
        if (isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub)
                and isinstance(v.operand, ast.Constant)
                and isinstance(v.operand.value, (int, float))):
            self.violations.append((v.lineno, arg, f"-{v.operand.value}"))
            return
        # Anything non-literal (variables, expressions) — leave alone.

    def _literal_source(self, v: ast.Constant) -> tuple[str | None, int | None]:
        """The verbatim source text of a string literal and its char column.

        The quick fix matches `old` as literal text in the line, so the slice is
        taken from the source rather than re-quoting the value — an assumed
        quote style would silently fail to match. Columns are converted from
        AST byte offsets, which overshoot on Cyrillic lines. Returns (None,
        None) when the source is unavailable or the literal spans lines.
        """
        if self.lines is None or v.end_lineno != v.lineno \
                or v.end_col_offset is None:
            return None, None
        idx = v.lineno - 1
        if not (0 <= idx < len(self.lines)):
            return None, None
        col = _char_col(self.lines, v.lineno, v.col_offset)
        end_col = _char_col(self.lines, v.lineno, v.end_col_offset)
        return self.lines[idx][col:end_col], col


def _run(filepath: Path) -> AgeChecker:
    src = Path(filepath).read_text(encoding="utf-8")
    checker = AgeChecker(Path(filepath), src.splitlines())
    checker.visit(shared_ast.parse(src))
    return checker


def check_file(filepath: Path) -> list[str]:
    """Return list of `path:line: message` errors."""
    try:
        checker = _run(Path(filepath))
    except SyntaxError as e:
        return [line_text(filepath, finding("SYN001", "detail", e.lineno, level="error", detail=e.msg))]
    out = [
        (line, f"{filepath}:{line}: {_format_message(kwarg, literal)}")
        for line, kwarg, literal in checker.violations
    ] + [
        (n.line, f"{filepath}:{n.line}: "
                 f"{_format_age001(n.kwarg, n.literal, n.digits, n.func)}")
        for n in checker.normalizable
    ]
    out.sort(key=lambda t: t[0])
    return [msg for _, msg in out]


def check_file_structured(filepath: Path) -> list[dict[str, object]]:
    """Return list of structured issue dicts."""
    try:
        checker = _run(Path(filepath))
    except SyntaxError as e:
        return [as_dict(finding("SYN001", "detail", e.lineno or 1, level="error", detail=e.msg))]

    issues: list[dict[str, object]] = [
        {
            "level": "error",
            "line": line,
            **said_unknown(kwarg, literal),
        }
        for line, kwarg, literal in checker.violations
    ]
    for n in checker.normalizable:
        issue: dict[str, object] = {
            "level": "error",
            "line": n.line,
            **said_age001(n.kwarg, n.literal, n.digits, n.func),
        }
        # No source slice (multi-line literal / source unavailable) → a
        # line-only issue: the IDEs fall back to highlighting the whole line
        # and simply offer no quick fix.
        if n.src is not None and n.col is not None:
            issue["col"] = n.col
            issue["end_col"] = n.col + len(n.src)
            issue["fix"] = {
                "type": "replace_kwarg",
                "old": n.src,
                "new": n.digits,
                "col": n.col,
            }
        issues.append(issue)
    def _line_of(issue: dict[str, object]) -> int:
        line = issue["line"]
        return line if isinstance(line, int) else 0

    issues.sort(key=_line_of)
    return issues


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.py> ...", file=sys.stderr)
        return 1

    errors: list[str] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_file() and p.suffix == ".py":
            errors.extend(check_file(p))

    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
