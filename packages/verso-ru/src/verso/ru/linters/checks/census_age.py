#!/usr/bin/env python3
"""AST-based linters (CAI001–CAI005) that WARN on internally inconsistent
census `member(...)` age data.

CAI001 flags a lone `birth_day`/`birth_month` (no `birth_year`) that
contradicts the member's `age`.

When a member gives `birth_day` and/or `birth_month` but **no** `birth_year`, the
Terraform generator defaults the birth year to the **census year** — correct only
for an infant actually born around the census. On a grown adult it silently pins
the birth to the wrong year. The classic trap:

    member(7, person("Савватей", "Никитинъ"), CensusRole.BROTHER,
           "43 года 11 мес", birth_day=6, ...)

`birth_day=6` with no `birth_year` makes the birth the census year, but the age
says he was born ~43 years earlier. The fix is to add `birth_year=` or drop the
stray `birth_day`/`birth_month`. The check flags exactly this shape: a member
with `birth_day`/`birth_month`, no `birth_year`, and an age of ≥ 2 years.

It is a WARNING, not an error. It deliberately does NOT cross-check an explicit
`birth_year` against the age: in multi-revision сказки a deceased member is aged
at whichever revision they last appeared in (not the census year), so that
comparison can't be done reliably from the call alone. The check reads its inputs
from the record content (NOT the file path), so it behaves identically when an
IDE plugin lints an unsaved buffer via a temp file.

CAI002 cross-checks `age` against `previous_age` (the age at the previous
revision): with `gap = census_year - prev_revision_year`, it flags a member
when `|(age - previous_age) - gap|` exceeds ±1 whole year. The ±1 tolerance is
required — revisions were surveyed mid-year, and roughly half the real 1850
records drift +1. The previous-revision year comes from
`verso.ru.census_revisions.PREVIOUS_AGE_REVISION_YEAR` — the revision chain, shared
with the facts layer and the translator (whose villages may keep a frozen exception
in village.toml, which CAI002 does not read); the `census_records(prev_revision_year=)` kwarg is
deliberately ignored — real files contradict each other on it (the 1795 file
declares 1762 while its data matches 1782), and its engine role is only
birth-location gating. Members are skipped when: the scribe wrote the prior
age into both columns (source-literal `str(previous_age) == str(age)`, the
generator's `prev_age_compresses_current` convention); the member departed or
died (`departure_year`/`departure_reason` — such members are aged at the
revision they last appeared in); the member is `hidden=True`; either age is
missing or unparseable; or the census year is unknown. Arrived members are NOT
skipped: revisions were synchronized empire-wide, so their prior-RS age uses
the same reference year. When the typed `previous_age` kwarg is absent, a
`прошлая РС: N лет` comment marker is used instead (mirroring the translator's
`_resolve_previous_age` precedence), parsed fractional-aware.

Run:
    python3 -m verso.ru.linters.checks.census_age FILE [FILE...]
"""

import ast
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from verso.ru.ages import age_number, has_fraction, split_age
from verso.ru.census_revisions import PREVIOUS_AGE_REVISION_YEAR
from verso.ru.linters.checks.census_redundancy import _char_col
from verso.core.i18n import Message
from verso.ru.linters.issue import as_dict, issue, Issue, line_text, Param
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast

# Year-unit tokens (mirror verso/ru/linters/checks/ages.py `_VALID_UNITS`).
_YEAR_UNITS = frozenset({"г", "л", "лет", "год", "года", "годов"})  # i18n: content — the age units and comment words the DSL writes
_AGE_TOKEN_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([а-яё]+)\.?", re.IGNORECASE)  # i18n: content — the age units and comment words the DSL writes
# A bare numeric age string, e.g. "34.5" (a real Маниловка 1858 form).
_BARE_NUMBER_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")

# CAI004/CAI005: departures that leave the member OUTSIDE the revision, so the
# «лета по нынешней ревизии» column is blank for them.
#   * death — they are gone for good;
#   * «выдана замуж» — she left the HOUSEHOLD, and it is her natal row whose
#     current-age column stays blank. A `destination` is NOT the discriminator:
#     ALL 26 brides married off within the village carry age == previous_age and
#     a birth_year, without one exception, while the single bride whose ages DO
#     differ is one WITH a destination — the opposite of what a «stayed local,
#     so her age is real» rule would predict.
# Other living departures (в острог, отдан в рекруты, уволен…) are not matched:
# the remaining corpus cases of age != previous_age are exactly those.
DEATH_REASON_RE = re.compile(r"умер", re.IGNORECASE)  # i18n: content — the age units and comment words the DSL writes
MARRIED_OUT_RE = re.compile(r"замуж", re.IGNORECASE)  # i18n: content — the age units and comment words the DSL writes


def _departed_from_parish(m: ast.Call) -> str | None:
    """"died" / "married out" when the revision records no current age for them."""
    dep_kw = _kwargs(m).get("departure_reason")
    dep = dep_kw.value if dep_kw is not None else None
    if not (isinstance(dep, ast.Constant) and isinstance(dep.value, str)):
        return None
    if DEATH_REASON_RE.search(dep.value):
        return "died"
    if MARRIED_OUT_RE.search(dep.value):
        return "married out"
    return None

# Birth fields that, set together without birth_year, pin the birth to the
# census year (only valid for an actual census-year infant).
BIRTH_DATE_KWARGS = ("birth_day", "birth_month")

# A member of at least this age (years) is not a census-year infant, so a lone
# birth_day/birth_month (defaulting birth_year to the census year) is wrong.
MIN_ADULT_YEARS = 2

# CAI002: deviation of |(age - previous_age) - gap| up to this many whole years
# passes; flag from tolerance + 1 up. Mid-year survey dates make ±1 routine
# (roughly half the real 1850 records sit at +1).
CAI002_TOLERANCE = 1

# CAI002's previous-revision-year table. It lives in `verso.ru.census_revisions`
# as `PREVIOUS_AGE_REVISION_YEAR`, where the facts layer dates the same
# column with it: two readers of one column must not hold two tables.
_PREV_REVISION_YEAR: dict[int, int] = PREVIOUS_AGE_REVISION_YEAR

# Comment-marker fallback for the prior-revision age (mirrors the translator's
# `_resolve_previous_age`, but fractional-aware: "0.5 лет" is 0 whole years,
# not 5).
PREV_AGE_COMMENT_RE = re.compile(r"прошлая РС:\s*([^,;]+)")  # i18n: content — the age units and comment words the DSL writes


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


def _int_literal(node: ast.expr | None) -> int | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _int_literal(node.operand)  # a hidden member's -1, -2…
        return -operand if operand is not None else None
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _member_arg(node: ast.Call, index: int, kwarg: str) -> ast.expr | None:
    """A member() argument by kwarg name, else positional index.
    member(number, person, role, ref_member, age, previous_age, ...)."""
    mkw = _kwargs(node)
    if kwarg in mkw:
        return mkw[kwarg].value
    if len(node.args) > index:
        return node.args[index]
    return None


def _person_first_name(person_node: ast.expr | None) -> str:
    """The member's given name for a friendly message (person()'s first
    positional arg / first_name= kwarg), or "" when unavailable."""
    if not isinstance(person_node, ast.Call):
        return ""
    fn = _kwargs(person_node).get("first_name")
    if fn is not None:
        return _string_literal(fn.value) or ""
    if person_node.args:
        return _string_literal(person_node.args[0]) or ""
    return ""


def _age_years(node: ast.expr | None) -> int | None:
    """The whole-years component of an `age` literal, or None when it can't be
    parsed. `22` → 22; `"43 года 11 мес"` → 43; `"6 мес"` → 0 (an infant)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return int(node.value)
    s = _string_literal(node)
    if s is None:
        return None
    return age_years_str(s)


def age_years_str(s: str) -> int | None:
    """`_age_years` for a raw string: `"34.5"` → 34; `"43 года 11 мес"` → 43;
    `"6 мес"` → 0 (an infant); unparseable → None."""
    if has_fraction(s):
        # A fraction is read whole or not at all: "20½" is 20, "2½" before a year unit 2, a "½" apart from its number nothing.
        years = split_age(s)[0]
        number = age_number(years) if years else 0.0
        if number is None or (years == s.strip() and age_number(s) is None):
            return None
        return int(number)
    bare = _BARE_NUMBER_RE.match(s)
    if bare:
        return int(float(bare.group(1).replace(",", ".")))
    tokens = _AGE_TOKEN_RE.findall(s)
    if not tokens:
        return None
    years = 0
    for num, unit in tokens:
        if unit.lower() in _YEAR_UNITS:
            years += int(float(num.replace(",", ".")))
    return years


def _census_year(node: ast.Call) -> int | None:
    """The census year of a census_records(...) call: `year=` kwarg, else
    positional index 5 — census_records(archive, fond, opis, delo, place, year, …)."""
    return _int_literal(_member_arg(node, 5, "year"))


def _member_calls(census_node: ast.Call) -> list[ast.Call]:
    return [n for n in shared_ast.walk(census_node)
            if isinstance(n, ast.Call) and _call_func_name(n) == "member"]


def _kwarg_range(m: ast.Call, name: str,
                 lines: list[str] | None) -> dict[str, object]:
    """`{line, col, end_col}` spanning a kwarg's ``name=value`` token.

    Without this the IntelliJ annotator has no range to narrow to and
    highlights the WHOLE member() line (DslLintAnnotator.narrowRange). Returns
    {} when the source is unavailable, the arg was passed positionally, or the
    value spans lines — the caller then falls back to a line-only issue.
    """
    if lines is None:
        return {}
    kw = _kwargs(m).get(name)
    if kw is None:
        return {}
    end = kw.value
    if end.end_lineno != kw.lineno or end.end_col_offset is None:
        return {}
    return {"line": kw.lineno,
            "col": _char_col(lines, kw.lineno, kw.col_offset),
            "end_col": _char_col(lines, kw.lineno, end.end_col_offset)}


def _collect(tree: ast.AST, lines: list[str] | None = None) -> list[dict[str, object]]:
    return [as_dict(i) for i in _issues(tree, lines)]


def _issues(tree: ast.AST, lines: list[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    for census in shared_ast.walk(tree):
        if not (isinstance(census, ast.Call)
                and _call_func_name(census) == "census_records"):
            continue
        census_year = _census_year(census)
        for m in _member_calls(census):
            issues.extend(_check_member(m, census_year, lines))
    issues.sort(key=lambda i: i.line)
    return issues


def _member_who(m: ast.Call) -> Message:
    num = _int_literal(_member_arg(m, 0, "number"))
    name = _person_first_name(_member_arg(m, 1, "person"))
    number = num if isinstance(num, int) else str(num)
    return t("census.member_named", number=number, name=name) if name else t("census.member", number=number)


def why_departed(why: str) -> Message:
    return t("census.died") if why == "died" else t("census.married_out")


def _found(code: str, variant: str, line: int, pin: Mapping[str, Any], **params: Param) -> list[Issue]:
    """One finding at `line` — or where `pin` (a kwarg's range) puts it, its columns with it."""
    return [issue(code, variant, pin.get("line", line), level="warn", col=pin.get("col"), end_col=pin.get("end_col"),
                  **params)]


def _check_member(m: ast.Call, census_year: int | None,
                  lines: list[str] | None = None) -> list[Issue]:
    return (_check_member_cai001(m, census_year, lines)
            + _check_member_cai002(m, census_year, lines)
            + _check_member_cai003(m, lines)
            + _check_member_cai004(m, lines)
            + _check_member_cai005(m, lines))


def _check_member_cai003(m: ast.Call,
                         lines: list[str] | None = None) -> list[Issue]:
    """CAI003: `age=0` used as an "age not stated" sentinel.

    The translator reads age literally: 0 puts the birth in the census year, so
    a head whose age the source omitted becomes a newborn — and any child
    referencing him ends up OLDER than his father (`verso age-conflicts` reported
    exactly that for three 1719 households).
    A missing `age=` is understood as unknown and emits no birth event at all,
    which is what "not stated" means.

    Every `age=0` in the repo (5 of them, all Заманиловка 1719) carried a comment
    saying the age was absent or illegible — none was a real newborn. A genuine
    age-0 infant would be flagged too, hence advisory: drop the kwarg or, if the
    source really says the child is under a year, spell it out (`age="полгода"`).
    """
    age_node = _member_arg(m, 4, "age")
    if not (isinstance(age_node, ast.Constant) and age_node.value == 0
            and not isinstance(age_node.value, bool)):
        return []
    pin = _kwarg_range(m, "age", lines)
    return _found("CAI003", "zero", age_node.lineno, pin, who=_member_who(m))


def _check_member_cai004(m: ast.Call,
                         lines: list[str] | None = None) -> list[Issue]:
    """CAI004: a member who DIED before the revision carries no current age.

    The «лета по нынешней ревизии» column is blank for someone already dead, so
    `age=` asserts a figure the source does not give. The importer used to
    compress the prior age into BOTH columns — the convention the generator
    documents as `prev_age_compresses_current` — which is where 405 such
    occurrences came from; `previous_age` is the field that holds the value.

    Keyed on DEATH, not on `age == previous_age`. Two reasons: an alive
    departure («в острог», «выдана замуж», «уволен с должности») leaves a person
    the revision really did age, so equality is the wrong trigger there; and a
    deceased member carrying an age with NO `previous_age` — the case that
    actually loses a column — would slip past an equality rule entirely.

    Advisory: dropping `age` is a no-op for the generated tree (birth estimation
    consults `previous_age` first, and the death-stub branch treats a missing age
    exactly like the compressed one), so the fix is safe but is a transcription
    edit, not a mechanical one when `previous_age` is absent.
    """
    why = _departed_from_parish(m)
    if why is None:
        return []
    age_node = _member_arg(m, 4, "age")
    if age_node is None:
        return []
    if isinstance(age_node, ast.Constant) and age_node.value is None:
        return []  # explicitly "not stated" — already correct
    pin = _kwarg_range(m, "age", lines)
    return _found("CAI004", "departed", age_node.lineno, pin, who=_member_who(m), why=why_departed(why))


def _check_member_cai005(m: ast.Call,
                         lines: list[str] | None = None) -> list[Issue]:
    """CAI005: an explicit `birth_year=` on a member who died before the revision.

    The сказка records a prior-revision age and a year of death, never a birth
    year, so an explicit one is somebody's arithmetic presented as source data.
    It also outranks `previous_age` in the generator's birth estimate (step 2 vs
    step 3) and so suppresses the honest uncertainty: an age of N at a revision
    means a two-year window, and dropping these turned `circa 1735` into
    `between circa 1735 and circa 1736` across the corpus.

    A member carrying `birth_day`/`birth_month` is exempt — a recorded birth DATE
    is source data, and there the year is part of it rather than a derivation.

    Sibling of CAI004, kept as its own code so the two pin different kwarg ranges
    and an editor can offer the right fix for each.
    """
    why = _departed_from_parish(m)
    if why is None:
        return []
    mkw = _kwargs(m)
    if any(k in mkw for k in BIRTH_DATE_KWARGS):
        return []                      # a real recorded date, not arithmetic
    by_kw = mkw.get("birth_year")
    if by_kw is None:
        return []
    by = by_kw.value
    if not isinstance(by, ast.Constant) or by.value is None:
        return []
    pin = _kwarg_range(m, "birth_year", lines)
    return _found("CAI005", "departed", by.lineno, pin, who=_member_who(m), why=why_departed(why))


def _check_member_cai001(m: ast.Call, census_year: int | None,
                         lines: list[str] | None = None) -> list[Issue]:
    age_node = _member_arg(m, 4, "age")
    age_years = _age_years(age_node)
    if age_years is None:
        return []  # ages.py flags unparseable ages; nothing to cross-check here

    mkw = _kwargs(m)
    birth_year_set = "birth_year" in mkw
    has_birth_date = any(k in mkw for k in BIRTH_DATE_KWARGS)
    if not (has_birth_date and not birth_year_set and age_years >= MIN_ADULT_YEARS):
        return []

    who = _member_who(m)
    age_txt = _string_literal(age_node)
    age_repr = repr(age_txt) if age_txt is not None else f"{age_years}"
    pin = _kwarg_range(m, "birth_day", lines) or _kwarg_range(m, "birth_month", lines)
    if census_year:
        return _found("CAI001", "with_year", m.lineno, pin, who=who, age=age_repr, years=age_years,
                      year=census_year, born=census_year - age_years)
    return _found("CAI001", "without_year", m.lineno, pin, who=who, age=age_repr, years=age_years)


def _literal_source_str(node: ast.expr | None) -> str | None:
    """The str() of an int/float/str literal (bools excluded), else None.
    Powers the repeat-convention skip, mirroring the generator's
    `prev_age_compresses_current` `str(prev) == str(age)` comparison."""
    if isinstance(node, ast.Constant) and not isinstance(node.value, bool) \
            and isinstance(node.value, (int, float, str)):
        return str(node.value)
    return None


def _source_repr(node: ast.expr) -> str:
    s = _string_literal(node)
    if s is not None:
        return repr(s)
    return str(_literal_source_str(node))


def _comment_prev_age_payload(m: ast.Call) -> str | None:
    """The `прошлая РС: …` payload of the member's comment, or None."""
    kw = _kwargs(m).get("comment")
    s = _string_literal(kw.value) if kw is not None else None
    if s is None:
        return None
    mm = PREV_AGE_COMMENT_RE.search(s)
    return mm.group(1).strip() if mm else None


def _check_member_cai002(m: ast.Call, census_year: int | None,
                         lines: list[str] | None = None) -> list[Issue]:
    if census_year is None:
        return []
    prev_year = _PREV_REVISION_YEAR.get(census_year)
    if prev_year is None:
        return []

    mkw = _kwargs(m)
    # Departed/deceased members are aged at the revision they last appeared
    # in, so their two columns don't straddle the full inter-revision gap.
    if "departure_year" in mkw or "departure_reason" in mkw:
        return []
    hidden = mkw.get("hidden")
    if hidden is not None and isinstance(hidden.value, ast.Constant) \
            and hidden.value.value is True:
        return []

    age_node = _member_arg(m, 4, "age")
    if age_node is None:
        return []

    pa_node = _member_arg(m, 5, "previous_age")
    if pa_node is not None:
        # Repeat convention: the scribe wrote the prior age into both columns
        # (usually a deceased/absent member) — nothing to cross-check.
        age_src = _literal_source_str(age_node)
        if age_src is not None and age_src == _literal_source_str(pa_node):
            return []
        pa_years = _age_years(pa_node)
        pa_repr = _source_repr(pa_node)
    else:
        payload = _comment_prev_age_payload(m)
        if payload is None:
            return []
        pa_years = age_years_str(payload)
        pa_repr = f"{payload!r} (from comment)"

    age_years = _age_years(age_node)
    if age_years is None or pa_years is None:
        return []  # ages.py owns malformed ages; "?" etc. stay silent here

    gap = census_year - prev_year
    diff = age_years - pa_years
    if abs(diff - gap) <= CAI002_TOLERANCE:
        return []

    return _found("CAI002", "gap", m.lineno, _kwarg_range(m, "age", lines), who=_member_who(m),
                  age=_source_repr(age_node), previous=pa_repr, diff=diff, year=census_year, gap=gap,
                  previous_year=prev_year)


class AgePair(NamedTuple):
    """What CAI002 compares on a member written as JSON: the two ages in whole years, the revision the previous one
    counts from, and the previous age as the finding shows it."""
    age: int
    previous: int
    previous_year: int
    shown: str


def json_age_years(value: object) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return age_years_str(value) if isinstance(value, str) else None


def link_age_pair(link: Mapping[str, Any], year: int) -> AgePair | None:
    """The pair CAI002 checks for a member whose `written` link is `link` (keys by the factory's parameters) in a roll
    of `year` — or None where it skips the member: no revision before `year`, a departed or hidden member, no age,
    a copied-forward pair (both columns written the same), no previous age (nor the «прошлая РС» marker in the
    comment), or an age that does not parse. The linter on the JSON and the page's `age_gap` both read it here."""
    previous_year = _PREV_REVISION_YEAR.get(year)
    if previous_year is None:
        return None
    if "departure_year" in link or "departure_reason" in link or link.get("hidden") is True:
        return None
    age = link.get("age")
    if age is None:
        return None
    if "previous_age" in link:
        previous = link["previous_age"]
        age_text = _literal_source_str_of(age)
        if age_text is not None and age_text == _literal_source_str_of(previous):
            return None
        previous_years, shown = json_age_years(previous), _json_source_repr(previous)
    else:
        comment = link.get("comment")
        found = PREV_AGE_COMMENT_RE.search(comment) if isinstance(comment, str) and comment else None
        if found is None:
            return None
        payload = found.group(1).strip()
        previous_years, shown = age_years_str(payload), f"{payload!r} (from comment)"
    years = json_age_years(age)
    if years is None or previous_years is None:
        return None
    return AgePair(years, previous_years, previous_year, shown)


def _literal_source_str_of(value: object) -> str | None:
    """`_literal_source_str` for a value, not a node: the text of a number or a string as the source wrote it."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    return str(value)


def _json_source_repr(value: object) -> str:
    return repr(value) if isinstance(value, str) else str(_literal_source_str_of(value))


def check_file(path: Path) -> list[str]:
    path = Path(path)
    try:
        src = path.read_text(encoding="utf-8")
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, issue("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [line_text(path, i) for i in _issues(tree, src.splitlines())]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    path = Path(path)
    try:
        src = path.read_text(encoding="utf-8")
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    return _collect(tree, src.splitlines())


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    warnings: list[str] = []
    for arg in sys.argv[1:]:
        warnings.extend(check_file(Path(arg)))
    for w in warnings:
        print(w)
    # CAI001 is advisory — never fail the build on warnings.
    return 0


if __name__ == "__main__":
    sys.exit(main())
