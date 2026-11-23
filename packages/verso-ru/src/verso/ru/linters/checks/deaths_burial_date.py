#!/usr/bin/env python3
"""AST-based linter for the two dates of a `death()` record: death and burial.

  [DBD001] The burial precedes the death. Found after generation until
           2026-09-22, by `verso facts --check date-order` (eight records
           across the corpus); this is the same question asked while the record
           is still being typed.

  [DBD002] A day its month does not have — 31 November, 30 February. Usually a
           record filed under the wrong `death_month()` block (a day «31.» after
           a November record, with no month heading in the book — December).

The eight came in three shapes, and all three are DSL shapes rather than
arithmetic slips, which is why they want a linter and not a careful eye:

  * a swapped or misread day pair — `death(1, M, 9, 8)`;
  * a month override on the wrong side — `death(6, F, 30, 1,
    d_month=Month.SEPTEMBER)` inside an AUGUST block: the override was meant
    for the burial, and `b_month` silently inherits AUGUST;
  * a burial in the next month the record never states — `death(57, F, 31, 1)`
    in an AUGUST block means buried 1 September, spelled `b_month=`.

**Effective months are resolved the way the DSL resolves them.**
`death_month_year()` (dsl/records/deaths.py) fills `d_month` and `b_month`
from the enclosing block only when they are None — so an explicit `None` is
the same as leaving the kwarg out, and an override on one side leaves the other
on the block. A month this check cannot read as a `Month.X` literal (or a
`death_month(None, …)` block) is unknown, and an unknown month orders nothing:
«9 | 8» with no month may be a burial in the next one.

**The comparison is `FactDate.definitely_before`, on one shared year.** A
burial with no day means its whole month, so it precedes the death only when
the month's LAST day does; a zero day is the corpus's spelling of an empty
column (Заманиловка 1840 смерть 12, `b_day=0`), not day nought. Asking it the
same way as `verso facts --check` is the point: a check that disagrees with the one it
runs ahead of gets ignored.

**The year boundary is flagged, not forgiven.** A `death()` has ONE `year` for
both dates — there is no burial year, as `birth(k_year=)` is for a christening.
A man who died 31 December and was buried 2 January is therefore unstatable:
`b_month=Month.JANUARY` dates the burial to January of the SAME year, eleven
months before the death, and that is what the CSV, the facts layer and every
consumer downstream would read. Silence here would only move the finding to
`verso facts --check`. The honest spelling is to leave the date that falls outside the
record's year undated and state it in `comment=`; a `b_year=` kwarg is the
real fix, worth building when the first such record is read (the corpus holds
none — no death record anywhere carries `b_month=Month.JANUARY`). For the same
reason a December block never advises `b_month=Month.JANUARY` for a small
burial day.

**February follows the Julian calendar.** The books are Old Style until 1918,
where every fourth year is a leap year — 1800 included (a book of 1800 heads an
entry «29 го» February). A record whose year cannot be read allows the 29th.

`source_date_error="…"` stands both codes down: the dates were re-read on the
scan and the book contradicts itself («померъ 9 | погребенъ 8»), which is a
faithful transcription with nothing to fix. As in
`Death` and the facts layer, an empty reason is no reason.

Run:
    python3 -m verso.ru.linters.checks.deaths_burial_date FILE [FILE...]
"""

import ast
import sys
from calendar import Month
from dataclasses import dataclass
from pathlib import Path

from verso.ru.linters.checks.deaths_residence import _call_func_name, _kwargs
from verso.core.i18n import Message
from verso.ru.linters.issue import issue, line_text, says
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast

#: Month-block helpers → index of their first record argument.
_BLOCKS = {"death_month": 1, "death_month_year": 2}

#: Russia kept Old Style dates until February 1918.
_GREGORIAN_FROM = 1918

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)



@dataclass(frozen=True)
class _Block:
    month: int | None = None   # None: no month, or one this check cannot read
    year: int | None = None


@dataclass(frozen=True)
class Side:
    """One of the record's two dates, as the DSL will resolve it."""
    day: int | None
    month: int | None
    explicit: bool   # month written on the death() itself, not inherited


def _int_literal(node: ast.expr | None) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    return None


def _month_literal(node: ast.expr | None) -> tuple[bool, int | None]:
    """(written, month): `written` is False for an absent or `None` month —
    the DSL's «inherit from the block». A written month this check cannot
    read (anything but `Month.X`) resolves to None, i.e. unknown."""
    if node is None or (isinstance(node, ast.Constant) and node.value is None):
        return False, None
    if isinstance(node, ast.Attribute) and node.attr in Month.__members__:
        return True, Month[node.attr].value
    return True, None


def _arg(node: ast.Call, index: int, name: str) -> ast.expr | None:
    kw = _kwargs(node).get(name)
    if kw is not None:
        return kw.value
    return node.args[index] if len(node.args) > index else None


def _day(node: ast.Call, index: int, name: str) -> int | None:
    """A written day, or None. Zero is the corpus's «column left empty»."""
    day = _int_literal(_arg(node, index, name))
    return day or None


def _side(node: ast.Call, block: _Block, day_at: tuple[int, str],
          month_at: tuple[int, str]) -> Side:
    written, month = _month_literal(_arg(node, *month_at))
    if not written:
        month = block.month
    return Side(_day(node, *day_at), month, written)


def _month_length(month: int, year: int | None) -> int:
    if month != 2:
        return _DAYS_IN_MONTH[month - 1]
    if year is None:
        return 29
    if year < _GREGORIAN_FROM:
        return 29 if year % 4 == 0 else 28
    return 29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28


def _name(month: int) -> str:
    return Month(month).name


def _show(side: Side) -> str:
    assert side.month is not None
    return f"{side.day} {_name(side.month)}" if side.day else _name(side.month)


def impossible_days(death: Side, burial: Side,
                     year: int | None) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for word, side in (("death", death), ("burial", burial)):
        if side.day is None:
            continue
        if side.month is None:
            if side.day > 31:
                out.append(says("DBD002", f"{word}_no_month", day=side.day))
            continue
        if side.day > _month_length(side.month, year):
            where = _name(side.month)
            if side.month == 2 and year is not None:
                where += f" {year}"
            out.append(says("DBD002", f"{word}_month", day=side.day, month=where))
    return out


def _order_hint(death: Side, burial: Side) -> Message:
    assert death.month is not None and burial.month is not None
    if death.month == 12 and burial.month == 1:
        return t("DBD001.hint_new_year")
    if death.month == burial.month:
        if death.month == 12:
            return t("DBD001.hint_swapped_december")
        return t("DBD001.hint_swapped", month=_name(death.month + 1))
    if death.explicit and not burial.explicit:
        return t("DBD001.hint_override", death_month=_name(death.month), burial_month=_name(burial.month))
    return t("DBD001.hint_before", month=_name(burial.month))


def burial_before_death(death: Side, burial: Side,
                         year: int | None, civil: bool = False) -> dict[str, object] | None:
    if death.month is None or burial.month is None:
        return None
    burial_last = (burial.month,
                   burial.day or _month_length(burial.month, year))
    death_first = (death.month, death.day or 1)
    if not burial_last < death_first:
        return None
    if civil:
        # A civil registry book's second date is the registration: no burial to advise on.
        return says("DBD001", "registration_precedes", registration=_show(burial), death=_show(death))
    return says("DBD001", "precedes", burial=_show(burial), death=_show(death), hint=_order_hint(death, burial))


def _declares_source_error(node: ast.Call) -> bool:
    kw = _kwargs(node).get("source_date_error")
    if kw is None:
        return False
    value = kw.value
    return not (isinstance(value, ast.Constant) and not value.value)


def _check_death(node: ast.Call, block: _Block,
                 book_year: int | None, civil: bool = False) -> list[dict[str, object]]:
    if _declares_source_error(node):
        return []
    # Innermost first, as the DSL fills it: the record's own year=, then
    # death_month_year's, then the book's.
    year = _int_literal(_arg(node, 20, "year")) or block.year or book_year
    death = _side(node, block, (2, "d_day"), (4, "d_month"))
    burial = _side(node, block, (3, "b_day"), (5, "b_month"))

    # An impossible day makes the order meaningless — 31 November follows
    # every November burial — so it is the one finding reported.
    messages = impossible_days(death, burial, year)
    if not messages:
        order = burial_before_death(death, burial, year, civil)
        messages = [order] if order else []
    return [{"level": "error", "line": node.lineno, **m} for m in messages]


def _collect(tree: ast.AST) -> list[dict[str, object]]:
    book_year: dict[ast.Call, int | None] = {}
    civil: set[ast.Call] = set()
    blocks: dict[ast.Call, _Block] = {}
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_func_name(node)
        if name == "death_records":
            year = _int_literal(_arg(node, 6, "year"))
            flag = _kwargs(node).get("civil")
            is_civil = flag is not None and isinstance(flag.value, ast.Constant) and flag.value.value is True
            for inner in shared_ast.walk(node):
                if isinstance(inner, ast.Call) and _call_func_name(inner) == "death":
                    book_year[inner] = year
                    if is_civil:
                        civil.add(inner)
        elif name in _BLOCKS and node.args:
            _written, month = _month_literal(node.args[0])
            year = (_int_literal(node.args[1])
                    if name == "death_month_year" and len(node.args) > 1 else None)
            for rec in node.args[_BLOCKS[name]:]:
                if isinstance(rec, ast.Call) and _call_func_name(rec) == "death":
                    blocks[rec] = _Block(month, year)

    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if isinstance(node, ast.Call) and _call_func_name(node) == "death":
            issues.extend(_check_death(node, blocks.get(node, _Block()),
                                       book_year.get(node), node in civil))
    return issues


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, issue("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree)]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    return [
        {"level": i.get("level", "error"), "line": i["line"], "message": i["message"]}
        for i in _collect(tree)
    ]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    all_errors: list[str] = []
    for arg in sys.argv[1:]:
        all_errors.extend(check_file(Path(arg)))
    for e in all_errors:
        print(e)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
