#!/usr/bin/env python3
"""AST-based advisory linter (PAF001) for the *form* of a patronymic vs. the
person's social status.

The full «-ович/-евич» patronymic (and feminine «-овна/-евна/-ична») was, before
the revolution, a status marker — a privilege of the nobility, officer ranks,
clergy, merchants and honoured citizens (codified by Catherine II: classes 1–5
written «с -вичем», the rest with a полуотчество or by name only). Peasants were
recorded with the short полуотчество («Абрамовъ», not «Абрамовичъ»).

So a full form on a peasant/low-rank person is historically unusual and worth a
look. PAF001 is therefore **advisory** (a warning, never fails CI): it flags a
full patronymic on a person whose status is NOT high-rank (or is unstated).
High-rank statuses get no warning — the full form is expected there.

Records transcribed from a modern printed catalog — the WWI/WWII participant
cards, the судимость gazette, flat name lists (`VERBATIM_SOURCE_VERBS`) — are
exempt entirely. The полуотчество rule is an estate marker of the parish-book
era; those sources write the full form for everyone, and we keep their text
verbatim, so a warning there says something about the source, never about our
data. Before the exemption they produced 58 of the corpus's 60 hits, i.e. the
signal was 3%.

A record set dated 1918 or later (`SOVIET_ERA_FROM`) is exempt for the same
reason: a civil-registry (ЗАГС) book is written with the parish-era verbs but
after the estates were abolished, and it writes «Иван Иванович» for everyone.

Path-independent: scopes purely on the `person()` call's args, so it behaves the
same on disk or on a temp-file copy of an unsaved editor buffer.

Run:
    python3 -m verso.ru.linters.checks.patronymic_form FILE [FILE...]
"""

import ast
import sys
from pathlib import Path

from verso.ru.naming import modernize_orthography
from verso.ru.linters.issue import says
from verso.ru.linters.checks import shared_ast

# Suffixes of a FULL patronymic (after orthography is modernised). Short
# полуотчества end in -ов/-ев/-ин/-ын (М) or -ова/-ева/-ина (Ж) and are excluded.
FULL_SUFFIXES = ("ович", "евич", "ич", "овна", "евна", "ична", "ишна")  # i18n: content — patronymic endings and status words: vocabulary

# Tokens in a status CONSTANT name that mark a high-rank person for whom the full
# form is expected. Matched case-sensitively as substrings of the identifier.
HIGH_RANK_NAME_TOKENS = (
    "LANDLORD", "NOBLE", "DVORYAN", "KNYAZ", "GRAF", "BARON",
    "MERCHANT", "KUPETS", "PRIEST", "DEACON", "DIAKON", "DYACHOK", "DYAK",
    "HIEREUS", "IEREUS", "SEXTON", "PONOMAR", "PRICHET", "PSALOM",
    "OFFICER", "PORUCHIK", "PRAPORSHCHIK", "KORNET", "ROTMISTR", "KAPITAN",
    "POLKOVNIK", "GENERAL", "PODPORUCHIK", "SHTABS",
    "CHINOVNIK", "TITULYAR", "KOLLEZH", "HONORARY", "POCHET",
)
# Tokens that mark a LOW-rank person even when the constant carries a noble
# surname (e.g. MANILOV_PS_PEASANT_MALE is a peasant OF landlord Манилов).
LOW_RANK_NAME_TOKENS = ("PEASANT", "DVOROVY", "SERF", "SOLDIER")

# Substrings of a freeform-string status marking high rank (lowercased match).
HIGH_RANK_TEXT = (
    "помещик", "помещиц", "дворян", "княз", "граф", "барон",  # i18n: content — patronymic endings and status words: vocabulary
    "купец", "купч", "почётн", "почетн", "потомственн",  # i18n: content — patronymic endings and status words: vocabulary
    "свящ", "протоиере", "иере", "диакон", "дьякон", "дьячок",  # i18n: content — patronymic endings and status words: vocabulary
    "пономар", "причетник", "псаломщик",  # i18n: content — patronymic endings and status words: vocabulary
    "офицер", "поручик", "прапорщик", "корнет", "ротмистр", "капитан",  # i18n: content — patronymic endings and status words: vocabulary
    "полковник", "генерал", "подпоручик", "штабс",  # i18n: content — patronymic endings and status words: vocabulary
    "чиновник", "титулярн", "коллежск",  # i18n: content — patronymic endings and status words: vocabulary
)
LOW_RANK_TEXT = ("крестьян", "дворов", "солдат")  # i18n: content — patronymic endings and status words: vocabulary

# Record verbs whose names are transcribed VERBATIM from a modern printed
# catalog rather than from a pre-revolutionary parish/revision book: the WWI
# (gwar.mil.ru) and WWII (Память народа) participant cards, the судимость
# gazette, and flat archival name lists. The полуотчество rule these warnings
# encode is an *estate* marker of the parish-register era; by the 1910s-1940s
# the full «-ович» form is simply how these sources write every name, peasant
# or not, so PAF001 there is noise about the source, not about our data —
# and the transcription is required to stay verbatim regardless.
# Scoping on the enclosing record verb keeps the check path-independent (an
# IDE lints an unsaved buffer via a temp file whose name means nothing).
VERBATIM_SOURCE_VERBS = frozenset({
    "criminal_record", "wwi_record", "wwii_record", "external_source_records",
    "listed_person", "name_list_records",
})

# The same argument by date rather than by source: a civil-registry (ЗАГС) book
# is a parish-era verb carrying a Soviet year, and it writes «Иван Иванович» for
# every peasant, because the estates the полуотчество marked were abolished by
# the decree of 11 (24) November 1917. A record set whose year is on or after
# this one is exempt; 1917 itself is not (the Обломовка farm census of summer
# 1917 still mixes the two forms on one sheet — a finding there is worth a look).
SOVIET_ERA_FROM = 1918
_RECORD_SET_SUFFIX = "_records"


def _record_set_year(node: ast.Call) -> int | None:
    """The year literal of a `*_records(archive, fund, …, year, …)` call.

    `birth_records` carries it in slot 6 (after `church`), `census_records` in
    slot 5, so the slot is not fixed: the first int literal among the leading
    positional args is the year — the archive references before it are strings.
    """
    for arg in node.args[:8]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, int) \
                and not isinstance(arg.value, bool):
            return arg.value
    return None


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


def _name_id(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _person_patronymic(person_node: ast.Call) -> str | None:
    """The as-written patronymic of a `person()` call: `patr_orig` (kwarg or
    positional index 1), else the explicit `patr_old` (kwarg or index 4)."""
    pkw = _kwargs(person_node)
    if "patr_orig" in pkw:
        return _string_literal(pkw["patr_orig"].value)
    if len(person_node.args) >= 2:
        lit = _string_literal(person_node.args[1])
        if lit is not None:
            return lit
    if "patr_old" in pkw:
        return _string_literal(pkw["patr_old"].value)
    if len(person_node.args) >= 5:
        return _string_literal(person_node.args[4])
    return None


def _status_node(person_node: ast.Call) -> ast.expr | None:
    """`status=` kwarg, else positional index 7 of person()."""
    pkw = _kwargs(person_node)
    if "status" in pkw:
        return pkw["status"].value
    if len(person_node.args) >= 8:
        return person_node.args[7]
    return None


def _is_high_rank(status_node: ast.expr | None) -> bool:
    """True only when the status clearly denotes a high-rank person (nobility,
    officers, clergy, merchants, honoured citizens). Peasants/serfs/soldiers and
    an absent/unclassifiable status are NOT high-rank."""
    ident = _name_id(status_node)
    if ident is not None:
        if any(t in ident for t in LOW_RANK_NAME_TOKENS):
            return False
        return any(t in ident for t in HIGH_RANK_NAME_TOKENS)
    text = _string_literal(status_node)
    if text is None:
        return False
    low = text.lower()
    if any(t in low for t in LOW_RANK_TEXT):
        return False
    return any(t in low for t in HIGH_RANK_TEXT)


def is_full_form(patronymic: str) -> bool:
    p = modernize_orthography(patronymic)
    if not p or "?" in p:
        return False
    return p.endswith(FULL_SUFFIXES)


class PatronymicFormChecker(shared_ast.Visitor):
    def __init__(self) -> None:
        self.issues: list[dict[str, object]] = []
        self._verbatim_depth = 0

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_func_name(node) or ""
        year = _record_set_year(node) if name.endswith(_RECORD_SET_SUFFIX) else None
        verbatim = (name in VERBATIM_SOURCE_VERBS
                    or (year is not None and year >= SOVIET_ERA_FROM))
        if verbatim:
            self._verbatim_depth += 1
        if _call_func_name(node) == "person" and not self._verbatim_depth:
            self._check_person(node)
        self.generic_visit(node)
        if verbatim:
            self._verbatim_depth -= 1

    def _check_person(self, node: ast.Call) -> None:
        patr = _person_patronymic(node)
        if patr is None or not is_full_form(patr):
            return
        if _is_high_rank(_status_node(node)):
            return
        self.issues.append({
            "level": "warning",
            "line": node.lineno,
            **says("PAF001", "full_form", patr=patr),
        })


def _collect(tree: ast.AST) -> list[dict[str, object]]:
    checker = PatronymicFormChecker()
    checker.visit(tree)
    return checker.issues


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []
    return _collect(tree)


def check_file(path: Path) -> list[str]:
    return [f"{path}:{i['line']}: {i['message']}" for i in check_file_structured(path)]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    all_warnings: list[str] = []
    for arg in sys.argv[1:]:
        all_warnings.extend(check_file(Path(arg)))
    for w in all_warnings:
        print(w)
    return 0  # advisory: never fail the exit code


if __name__ == "__main__":
    sys.exit(main())
