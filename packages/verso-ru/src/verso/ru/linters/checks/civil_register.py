"""AST-based linter (ZGS001–ZGS006) for a book of the civil registry — `civil=True`.

A ZAGS book records births, deaths and marriages as acts: the same kinds and the same
people as a parish book, its second date a registration. What a parish book writes and an
act never does, or what a civil book of 1918 on could not have written, is a contradiction
— most often a parish book's template copied into the civil one, or a flag left off.

Hard (`check_file` / `check_file_structured`):

- ZGS001 — a civil book holds what only a church writes: a godparent, a wedding's surety,
  the clergy (`priest=`, `deacon=`, `dyachok=`, `sexton=`), or a `christening()` entry.
- ZGS002 — a civil birth registered before it was born: an explicit `k_month=` (or
  `k_year=`) puts the registration before the birth. Inside a `birth_month()` block a
  smaller registration day is read as the next month, as the DSL reads it, and is no
  finding.

Advisory (`check_file_advisory` / `check_file_advisory_structured`):

- ZGS003 — a book of 1918 on that names no church and is not `civil=True`: a ZAGS book
  read as a parish one, whose registrations become christenings and burials. The year
  only guards it — a book of before with its church unknown is no finding. Nothing asks
  the reverse: `civil=True` before 1917 is a civil registration too — the police books of
  the Old Believers (1874) and the sectarians (1879), the Kingdom of Poland's acts.
- ZGS004 — a civil book styles someone by an estate of the old order: an owner, a
  ministry, an одноворец, a дворянин («крестьянин помѣщика …», «казенный крестьянин»).
  Estates were abolished in November 1917; the acts write «гражданин» or an occupation.
  Plain «крестьянин» is no finding: the acts kept it as a social position.
- ZGS005 — a name in a civil book written with the letters the 1918 reform removed (ѣ, і,
  ѳ, ѵ, a final ъ). The DSL keeps the book's spelling, so this asks whether the act wrote it
  so or the hand typed the old books' habit.

- ZGS006 — a civil birth's `comment=` says a parent's age («отцу 26, матери 22») while that role's
  field (`father_age=`, `mother_age=`) is empty. It fires only on a fragment `verso fix-parent-ages` would
  move — `verso.ru.parent_age_text` is the one reader of both; a doubtful or cut one stays no finding.

Two of ZAGS's questions are not here. One deed's books of one year — births, deaths —
stand in separate files, and a check reads one file: a flag set on one and not the other is
out of its reach (ZGS003 flags each unflagged one). And a death registered before it
happened is DBD001's, worded for a registration when the book is civil.

Run:
    python3 -m verso.ru.linters.checks.civil_register FILE [FILE...]
"""

import ast
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from verso.ru.linters.checks.file_bindings import module_bindings, record_defaults_call, string_constants
from verso.ru.linters.checks.status_words import words_of
from verso.ru.parent_age_text import FIELDS, ROLES, read_comment
from verso.ru.parent_age_text import Reading as ParentAgeReading
from verso.ru.linters.issue import issue, line_text, says
from verso.ru.linters.checks import shared_ast

Issue = dict[str, object]

#: A record set and the record calls it holds.
_SETS: dict[str, tuple[str, ...]] = {
    "birth_records": ("birth", "christening"),
    "death_records": ("death",),
    "marriage_records": ("marriage",),
}

#: What only a church writes, per record kind: keyword slots, and positional ones by index.
_CLERGY = ("priest", "deacon", "dyachok", "sexton")
CHURCH_SLOTS: dict[str, tuple[str, ...]] = {
    "birth": ("god_parent1", "god_parent2", "god_parent3", "god_parent4", *_CLERGY),
    "christening": ("god_parent1", "god_parent2", "god_parent3", "god_parent4", *_CLERGY),
    "marriage": tuple(f"witness{n}" for n in range(1, 7)) + _CLERGY,
    "death": _CLERGY,
}
_CHURCH_POSITIONS: dict[str, dict[int, str]] = {
    "birth": {9: "god_parent1", 10: "god_parent2"},
    "marriage": {9 + i: f"witness{i + 1}" for i in range(6)},
}

#: A book of this year on with no church is likely a civil one.
CIVIL_LIKELY_FROM = 1918

#: Words of an estate of the old order — an owner, a ministry, a lost estate — never the
#: plain «крестьянин» the acts kept as a social position.
OLD_ESTATE = re.compile(
    r"пом[еѣ]щи|вотчин|отчин|казен|казён|государствен|экономическ|удельн|ясачн|однодвор|дворян"  # i18n: content
    r"|временнообязан|собственник|мещан|купе[цч]|купчих|почетн|почётн",  # i18n: content
    re.IGNORECASE)

#: The letters the 1918 reform removed, and a hard sign closing a word.
OLD_LETTERS = re.compile(r"[ѣіѳѵѢІѲѴ]|ъ\b")  # i18n: content
NAME_KWARGS = ("name_orig", "patr_orig", "last_name_orig")


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def _arg(node: ast.Call, index: int, name: str) -> ast.expr | None:
    kw = _kwargs(node).get(name)
    if kw is not None:
        return kw.value
    return node.args[index] if len(node.args) > index else None


def _int(node: ast.expr | None) -> int | None:
    return node.value if isinstance(node, ast.Constant) and type(node.value) is int else None


def _str(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _month(node: ast.expr | None) -> int | None:
    """`Month.MARCH` → 3; anything else (None, a name it cannot read) → None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Month":
        months = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                  "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER")
        return months.index(node.attr) + 1 if node.attr in months else None
    return None


def _civil(book: ast.Call) -> bool:
    kw = _kwargs(book).get("civil")
    return kw is not None and isinstance(kw.value, ast.Constant) and kw.value.value is True


def _books(tree: ast.AST) -> Iterator[ast.Call]:
    for node in shared_ast.walk(tree):
        if _call_name(node) in _SETS:
            assert isinstance(node, ast.Call)
            yield node


def _records(book: ast.Call) -> Iterator[ast.Call]:
    kinds = _SETS[_call_name(book) or ""]
    for node in shared_ast.walk(book):
        if _call_name(node) in kinds:
            assert isinstance(node, ast.Call)
            yield node


def civil_births(tree: ast.AST) -> Iterator[ast.Call]:
    """Each `birth()` of a book flagged `civil=True` — the births ZGS006 reads and `verso fix-parent-ages` edits."""
    for book in _books(tree):
        if _civil(book):
            for record in _records(book):
                if _call_name(record) == "birth":
                    yield record


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def parent_age_moves(birth: ast.Call) -> tuple[ast.keyword, ParentAgeReading, dict[str, ast.keyword]] | None:
    """(the birth's `comment=` keyword, what it says of the parents' ages, the `father_age=None`-like keywords the
    figures replace) when a field of an empty role could take it — the one question the linter and the codemod ask.
    A role is empty when its keyword is missing or written `None`."""
    kwargs = _kwargs(birth)
    comment = _str(kwargs["comment"].value) if "comment" in kwargs else None
    nones = {role: kwargs[FIELDS[role]] for role in ROLES
             if FIELDS[role] in kwargs and _is_none(kwargs[FIELDS[role]].value)}
    empty = tuple(role for role in ROLES if FIELDS[role] not in kwargs or role in nones)
    reading = read_comment(comment, empty) if comment and empty else None
    return (kwargs["comment"], reading, nones) if reading is not None else None


def _persons(node: ast.AST) -> Iterator[ast.Call]:
    for inner in shared_ast.walk(node):
        if _call_name(inner) == "person":
            assert isinstance(inner, ast.Call)
            yield inner


# --- hard ---------------------------------------------------------------------------------

def _church_slots(record: ast.Call) -> Iterator[Issue]:
    kind = _call_name(record) or ""
    if kind == "christening":
        yield {"line": record.lineno, **says("ZGS001", "christening", token="christening")}
    kwargs = _kwargs(record)
    for slot in CHURCH_SLOTS.get(kind, ()):
        kw = kwargs.get(slot)
        if kw is not None and not (isinstance(kw.value, ast.Constant) and kw.value.value is None):
            yield {"line": kw.value.lineno, **says("ZGS001", "slot", slot=slot, token=slot)}
    for index, slot in _CHURCH_POSITIONS.get(kind, {}).items():
        if index < len(record.args) and _call_name(record.args[index]) == "person":
            yield {"line": record.args[index].lineno, **says("ZGS001", "slot", slot=slot, token=slot)}


def _block_months(book: ast.Call) -> dict[int, tuple[int | None, int | None]]:
    """id(birth call) → (its block's month, its block's year), as `birth_month[_year]` sets them."""
    out: dict[int, tuple[int | None, int | None]] = {}
    for node in shared_ast.walk(book):
        name = _call_name(node)
        if name not in ("birth_month", "birth_month_year"):
            continue
        assert isinstance(node, ast.Call)
        if not node.args:
            continue
        month = _month(node.args[0])
        year = _int(node.args[1]) if name == "birth_month_year" and len(node.args) > 1 else None
        first = 2 if name == "birth_month_year" else 1
        for rec in node.args[first:]:
            if _call_name(rec) == "birth":
                out[id(rec)] = (month, year)
    return out


def _registered_before_birth(book: ast.Call) -> Iterator[Issue]:
    blocks = _block_months(book)
    book_year = _int(_arg(book, 6, "year"))
    for record in _records(book):
        if _call_name(record) != "birth":
            continue
        block_month, block_year = blocks.get(id(record), (None, None))
        b_day, k_day = _int(_arg(record, 2, "b_day")), _int(_arg(record, 3, "k_day"))
        b_month = _month(_arg(record, 4, "b_month")) or block_month
        k_written = _month(_arg(record, 5, "k_month"))
        year = _int(_arg(record, 21, "year")) or block_year or book_year
        k_year = _int(_arg(record, 22, "k_year"))
        if k_written is None and k_year is None:
            continue    # the block's month, advanced past a smaller day as the DSL advances it
        k_month = k_written or block_month
        if b_month is None or k_month is None:
            continue
        birth = (year or 0, b_month, b_day or 1)
        registration = (k_year or year or 0, k_month, k_day or 31)
        if registration < birth:
            yield {"line": record.lineno,
                   **says("ZGS002", "precedes", registration=f"{k_day or '?'}.{k_month}",
                          birth=f"{b_day or '?'}.{b_month}")}


def _hard(tree: ast.AST) -> list[Issue]:
    issues: list[Issue] = []
    for book in _books(tree):
        if not _civil(book):
            continue
        for record in _records(book):
            issues.extend(_church_slots(record))
        issues.extend(_registered_before_birth(book))
    return issues


# --- advisory -----------------------------------------------------------------------------

def _unflagged(book: ast.Call) -> Iterator[Issue]:
    year = _int(_arg(book, 6, "year"))
    if (not _civil(book) and year is not None and year >= CIVIL_LIKELY_FROM
            and _str(_arg(book, 5, "church")) == ""):
        yield {"line": book.lineno, **says("ZGS003", "unflagged", year=year)}


def _old_estates(book: ast.Call, bindings: dict[str, ast.expr], texts: dict[str, str]) -> Iterator[Issue]:
    defaults = record_defaults_call(book, bindings)
    sources: list[tuple[ast.expr, str]] = []
    if defaults is not None:
        sources += [(kw.value, kw.arg) for kw in defaults.keywords
                    if kw.arg is not None and kw.arg.startswith("status_")]
    for person in _persons(book):
        kw = _kwargs(person).get("status")
        if kw is not None:
            sources.append((kw.value, "status"))
    for node, _where in sources:
        words = words_of(node, texts)
        if words and OLD_ESTATE.search(words):
            token = node.id if isinstance(node, ast.Name) else words
            yield {"line": node.lineno, **says("ZGS004", "estate", status=words, token=token)}


def _old_letters(book: ast.Call) -> Iterator[Issue]:
    for person in _persons(book):
        written = [*person.args[:3], *(kw.value for kw in person.keywords if kw.arg in NAME_KWARGS)]
        for node in written:
            name = _str(node)
            if name and OLD_LETTERS.search(name):
                yield {"line": node.lineno, **says("ZGS005", "old_letters", name=name, token=name)}
                break    # one finding a person: the habit, not every word of it


def _parent_ages_in_comment(tree: ast.AST) -> Iterator[Issue]:
    for record in civil_births(tree):
        if (move := parent_age_moves(record)) is not None:
            comment, reading, _ = move
            for role in reading.ages:
                yield {"line": comment.value.lineno, **says("ZGS006", role, token="comment")}


def _advisory(tree: ast.AST) -> list[Issue]:
    bindings = module_bindings(tree)
    texts = string_constants(bindings)
    issues: list[Issue] = []
    for book in _books(tree):
        issues.extend(_unflagged(book))
        if _civil(book):
            issues.extend(_old_estates(book, bindings, texts))
            issues.extend(_old_letters(book))
    issues.extend(_parent_ages_in_comment(tree))
    return issues


# --- plumbing, as witness_side's ------------------------------------------------------------

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
    found = False
    for arg in sys.argv[1:]:
        for line in [*check_file(Path(arg)), *check_file_advisory(Path(arg))]:
            print(line)
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
