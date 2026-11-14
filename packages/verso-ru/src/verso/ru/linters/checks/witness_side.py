#!/usr/bin/env python3
"""AST-based linter (WSD001–WSD006) for the side a wedding's поручитель stood for.

Часть 2 of a metric book lists the sureties «по женихѣ» and «по невѣстѣ». The
DSL declares that on the person — `witness3=person(…, side=Side.BRIDE)` — and
never by renumbering the slots: `witnessN` is part of the res_name on Geni.

Hard (`check_file` / `check_file_structured`):

- WSD001 — `side=` on a person that is not a marriage's `witness1..6`: a groom,
  a bride, the clergy, a relative, anyone in a birth or a death. A side means
  nothing there, and nothing reads it.
- WSD002 — `side=` contradicts the words of the same witness's `comment=`
  («поручитель по невесте» on a `Side.GROOM`): one of the two is a misreading.

Advisory (`check_file_advisory` / `check_file_advisory_structured`):

- WSD003 — the side is written in words. Either a witness's `comment=` names it
  and `side=` is missing (declare it), or names it and `side=` already says the
  same (drop the words: the Familio export writes them from `side=`); or the
  record's own `comment=` names sides while some witness has no `side=`.
- WSD004 — in one record some witnesses carry a side and some do not.
- WSD005 — a groom's surety sits in a later slot than a bride's. The books write
  the groom's first, so the reading wants a second look — but an applied slot is
  never renumbered.
- WSD006 — more than three sureties for one side: the Familio справочник has
  three columns per side, and the rest would be dropped.

Run:
    python3 -m verso.ru.linters.checks.witness_side FILE [FILE...]
"""

import ast
import re
import sys
from collections.abc import Callable
from pathlib import Path
from verso.ru.linters.issue import issue, line_text, says
from verso.ru.linters.checks import shared_ast

Issue = dict[str, object]

_WITNESS_SLOTS = tuple(f"witness{n}" for n in range(1, 7))
# marriage(record_num, w_day, w_month, groom, bride, groom_marriage_num,
#          bride_marriage_num, groom_age, bride_age, witness1..witness6, …)
_POSITIONAL_WITNESS = {9 + i: slot for i, slot in enumerate(_WITNESS_SLOTS)}

_GROOM_WORDS = re.compile(r"по\s+жених[уеѣ]|со\s+стороны\s+жениха", re.IGNORECASE)  # i18n: content — the side words the sources write
_BRIDE_WORDS = re.compile(r"по\s+нев[еѣ]ст[еѣ]|со\s+стороны\s+нев[еѣ]сты", re.IGNORECASE)  # i18n: content — the side words the sources write

SIDE_WORD = {"GROOM": "по жениху", "BRIDE": "по невесте"}  # i18n: content — the side words the sources write
PER_SIDE_COLUMNS = 3


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def _string_literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _side_of(person: ast.Call) -> tuple[str | None, ast.keyword | None]:
    """("GROOM"/"BRIDE"/other attribute name, the keyword) or (None, None)."""
    kw = _kwargs(person).get("side")
    if kw is None:
        return None, None
    value = kw.value
    if isinstance(value, ast.Attribute):
        return value.attr, kw
    if isinstance(value, ast.Name):
        return value.id, kw
    return "?", kw


def words_side(text: str | None) -> str | None:
    """The side the words name: "GROOM", "BRIDE", "BOTH" or None."""
    if not text:
        return None
    groom, bride = bool(_GROOM_WORDS.search(text)), bool(_BRIDE_WORDS.search(text))
    if groom and bride:
        return "BOTH"
    return "GROOM" if groom else "BRIDE" if bride else None


def _comment_of(node: ast.Call) -> str | None:
    kw = _kwargs(node).get("comment")
    return _string_literal(kw.value) if kw is not None else None


def _is_person(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _call_func_name(node) == "person"


def _marriage_witnesses(node: ast.Call) -> list[tuple[int, ast.Call]]:
    """(slot number, person call) of a marriage()'s filled witness slots."""
    out: list[tuple[int, ast.Call]] = []
    kwargs = _kwargs(node)
    for n, slot in enumerate(_WITNESS_SLOTS, start=1):
        kw = kwargs.get(slot)
        if kw is not None and _is_person(kw.value):
            assert isinstance(kw.value, ast.Call)
            out.append((n, kw.value))
    for index, slot in _POSITIONAL_WITNESS.items():
        if index < len(node.args) and _is_person(node.args[index]):
            person = node.args[index]
            assert isinstance(person, ast.Call)
            out.append((int(slot.removeprefix("witness")), person))
    return sorted(out, key=lambda t: t[0])


def _marriages(tree: ast.AST) -> list[ast.Call]:
    return [n for n in shared_ast.walk(tree)
            if isinstance(n, ast.Call) and _call_func_name(n) == "marriage"]


def _hard(tree: ast.AST) -> list[Issue]:
    issues: list[Issue] = []
    witness_ids: set[int] = set()
    for m in _marriages(tree):
        for n, person in _marriage_witnesses(m):
            witness_ids.add(id(person))
            side, kw = _side_of(person)
            if side not in SIDE_WORD or kw is None:
                continue
            words = words_side(_comment_of(person))
            if words in SIDE_WORD and words != side:
                issues.append({"line": kw.value.lineno,
                               **says("WSD002", f"says_{words.lower()}", n=n, side=side)})
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_person(node) or id(node) in witness_ids:
            continue
        _, kw = _side_of(node)
        if kw is not None:
            issues.append({"line": kw.value.lineno, **says("WSD001", "outside")})
    return issues


def _advisory(tree: ast.AST) -> list[Issue]:
    issues: list[Issue] = []
    for m in _marriages(tree):
        witnesses = _marriage_witnesses(m)
        if not witnesses:
            continue
        sides: dict[int, str | None] = {}
        for n, person in witnesses:
            side, _ = _side_of(person)
            sides[n] = side if side in SIDE_WORD else None
            comment_kw = _kwargs(person).get("comment")
            words = words_side(_string_literal(comment_kw.value) if comment_kw else None)
            if words not in SIDE_WORD or comment_kw is None:
                continue
            if side is None:
                issues.append({"line": comment_kw.value.lineno,
                               **says("WSD003", f"undeclared_{words.lower()}", n=n)})
            elif side == words:
                issues.append({"line": comment_kw.value.lineno,
                               **says("WSD003", f"repeated_{words.lower()}", n=n)})
        record_comment = _kwargs(m).get("comment")
        if (record_comment is not None
                and words_side(_string_literal(record_comment.value)) is not None
                and any(s is None for s in sides.values())):
            issues.append({"line": record_comment.value.lineno, **says("WSD003", "record_comment")})
        declared = {n: s for n, s in sides.items() if s is not None}
        if declared and len(declared) < len(sides):
            missing = ", ".join(f"witness{n}" for n, s in sides.items() if s is None)
            issues.append({"line": m.lineno, **says("WSD004", "half_declared", missing=missing)})
        grooms = [n for n, s in declared.items() if s == "GROOM"]
        brides = [n for n, s in declared.items() if s == "BRIDE"]
        if grooms and brides and max(grooms) > min(brides):
            issues.append({"line": m.lineno, **says("WSD005", "order", groom=max(grooms), bride=min(brides))})
        for side, slots in (("GROOM", grooms), ("BRIDE", brides)):
            if len(slots) > PER_SIDE_COLUMNS:
                issues.append({"line": m.lineno, **says("WSD006", f"too_many_{side.lower()}", count=len(slots),
                                                        columns=PER_SIDE_COLUMNS)})
    return issues


def _parse(path: Path) -> ast.AST | SyntaxError:
    try:
        return shared_ast.parse(Path(path).read_text(encoding="utf-8"))
    except SyntaxError as e:
        return e


def _sorted(issues: list[Issue]) -> list[Issue]:
    return sorted(issues, key=lambda i: (int(str(i["line"])), str(i["message"])))


def _plain(path: Path, collect: Callable[[ast.AST], list[Issue]]) -> list[str]:
    tree = _parse(path)
    if isinstance(tree, SyntaxError):
        return [line_text(path, issue("SYN002", "detail", tree.lineno or 1, level="error", detail=tree.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _sorted(collect(tree))]


def _structured(path: Path, collect: Callable[[ast.AST], list[Issue]], level: str) -> list[Issue]:
    tree = _parse(path)
    if isinstance(tree, SyntaxError):
        return []  # other linters report the syntax error as an error
    return [{"level": level, "line": i["line"], "message": i["message"]}
            for i in _sorted(collect(tree))]


def check_file(path: Path) -> list[str]:
    return _plain(path, _hard)


def check_file_structured(path: Path) -> list[Issue]:
    return _structured(path, _hard, "error")


def check_file_advisory(path: Path) -> list[str]:
    return _plain(path, _advisory)


def check_file_advisory_structured(path: Path) -> list[Issue]:
    return _structured(path, _advisory, "warn")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    hard: list[str] = []
    for arg in sys.argv[1:]:
        hard.extend(check_file(Path(arg)))
        for warning in check_file_advisory(Path(arg)):
            print(f"warning: {warning}")
    for e in hard:
        print(e)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
