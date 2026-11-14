#!/usr/bin/env python3
"""VSR001 — AST linter that flags a redundant explicit ``status=`` on a person in
a VITAL record (birth / marriage / death) when the enclosing
``*_records(..., defaults=RecordDefaults(...))`` would apply the identical
status by default — written in the call, or bound by name at the top of the
file (``defaults=DEFAULTS``, as every Глуповы Горы book does).

The census counterpart is CSR001 (``census_status_redundancy``); this is the
same idea for the other three record verbs.

Run:
    python3 -m verso.ru.linters.checks.status_redundancy FILE [FILE...]
"""

import ast
import sys
from pathlib import Path
from typing import NamedTuple

from verso.ru.gender import Gender
from verso.ru.naming import get_gender_from_name
from verso.ru.relationship import Relationship, gender_from_relationship
# Reuse CSR001's helpers so the reading of a person()/RecordDefaults() node can
# never drift between the two status-redundancy checks.
from verso.ru.linters.checks.census_redundancy import (
    _attr_name, _call_func_name, _kwargs, _person_arg, _string_literal)
from verso.ru.linters.checks.census_status_redundancy import (
    _STATUS_INDEX, _default_arg, _status_fix)
from verso.ru.linters.checks.file_bindings import module_bindings, record_defaults_call
from verso.ru.linters.checks.newborn_status import load_bearing_parent
from verso.ru.linters.issue import as_dict, issue, line_text
from verso.ru.linters.checks import shared_ast

# person(name_orig, patr_orig, last_name_orig, name_modern_orth, ...)
_NAME_ORIG_INDEX = 0
_NAME_MODERN_INDEX = 3
_GENDER_INDEX = 8


def _person_gender(person_node: ast.Call) -> str | None:
    """Gender as resolved BEFORE defaults are applied: explicit ``gender=`` then
    the name. Person.__init__'s patronymic and status fallbacks are deliberately
    excluded — status is the very thing we may remove."""
    explicit = _attr_name(_person_arg(person_node, _GENDER_INDEX, "gender"))
    if explicit:
        return explicit
    name = (_string_literal(_person_arg(person_node, _NAME_MODERN_INDEX, "name_modern_orth"))
            or _string_literal(_person_arg(person_node, _NAME_ORIG_INDEX, "name_orig")))
    if name:
        inferred = get_gender_from_name(name)
        if inferred is not None:
            return inferred.name
    return None


def _gendered_default(gender: str | None, status_male: ast.expr | None,
                      status_female: ast.expr | None) -> tuple[ast.expr | None, str]:
    """Mirror RecordDefaults.apply_to_person's status selection exactly."""
    if gender == Gender.FEMALE.name and status_female is not None:
        return status_female, "status_female"
    return status_male, "status_male"


# The three vital-record verbs, keyed by the records wrapper that carries the
# `defaults=` block. Census has its own check (CSR001).
_RECORD_VERB = {
    "birth_records": "birth",
    "marriage_records": "marriage",
    "death_records": "death",
}


class Slot(NamedTuple):
    """A person slot that RecordDefaults actually reaches.

    ``gender_fallback`` is the gender the record's own ``__init__`` assigns when
    the name resolves nothing — it runs BEFORE defaults, so it decides which
    gendered default applies. ``dedicated_default`` is the RecordDefaults field
    that pre-empts the gendered one for this slot (assigned first in
    ``apply_to_*``, after which ``apply_to_person`` sees a non-None status and
    leaves it alone).
    """

    kwarg: str
    gender_fallback: str | None = None
    dedicated_default: str | None = None


_M, _F = Gender.MALE.name, Gender.FEMALE.name

# Mirrors RecordDefaults.apply_to_birth / _marriage / _death slot for slot.
# DELIBERATELY ABSENT: birth `child` and death `deceased`. Birth.__init__ and
# Death.__init__ derive their сословие from the parent via child_status_for
# BEFORE defaults run, and apply_to_person only fills a None status, so the
# derived value wins — removing an explicit status there yields the derived
# status, not the default. Not byte-neutral, so never flagged.
SLOTS: dict[str, tuple[Slot, ...]] = {
    "marriage": (
        # status_groom itself falls back to status_male in RecordDefaults.__init__,
        # which the gendered branch reproduces via the MALE fallback.
        Slot("groom", _M, "status_groom"),
        Slot("bride", _F, "status_bride"),
        *(Slot(f"witness{i}") for i in range(1, 7)),
    ),
    "birth": (
        Slot("father", _M),
        Slot("mother", _F, "status_mother"),
        Slot("god_parent1", _M),
        Slot("god_parent2", _F),
        # gp3/gp4 get the defaults (unlike gp1/gp2 they get no slot-implied
        # gender — a trio has no reliable convention), so the name alone decides.
        Slot("god_parent3"),
        Slot("god_parent4"),
    ),
    "death": (
        Slot("witness1"),
        Slot("witness2"),
    ),
}

# Every person slot of these verbs is passed by keyword across the whole corpus
# (verified: no record passes one positionally), so slots resolve by kwarg only.
RELATIVE_SLOT = Slot("relative")


def _slot_person(record_node: ast.Call, kwarg: str) -> ast.Call | None:
    value = _kwargs(record_node).get(kwarg)
    if value is None or not isinstance(value.value, ast.Call):
        return None
    return value.value if _call_func_name(value.value) == "person" else None


def _relative_gender(relative_node: ast.Call) -> str | None:
    """The gender `<Record>.__init__` derives from the relationship when the
    relative's name resolves nothing."""
    name = _attr_name(_person_arg(relative_node, 1, "relationship"))
    if not name:
        return None
    try:
        implied = gender_from_relationship(Relationship[name])
    except KeyError:
        return None
    return implied.name if implied is not None else None


def _defaulted_persons(record_node: ast.Call, verb: str) -> list[tuple[ast.Call, Slot, str | None]]:
    """Every (person, slot, gender fallback) that RecordDefaults reaches in this
    record — the named slots of `SLOTS` plus each `relatives=` entry."""
    found: list[tuple[ast.Call, Slot, str | None]] = []
    for slot in SLOTS.get(verb, ()):
        person = _slot_person(record_node, slot.kwarg)
        if person is not None:
            found.append((person, slot, slot.gender_fallback))

    relatives = _kwargs(record_node).get("relatives")
    if relatives is None or not isinstance(relatives.value, (ast.List, ast.Tuple)):
        return found
    for element in relatives.value.elts:
        if not (isinstance(element, ast.Call) and _call_func_name(element) == "relative"):
            continue
        person = _person_arg(element, 0, "person")
        if isinstance(person, ast.Call) and _call_func_name(person) == "person":
            found.append((person, RELATIVE_SLOT, _relative_gender(element)))
    return found


def _effective_default(slot: Slot, gender: str | None, defaults: ast.Call,
                       status_male: ast.expr | None,
                       status_female: ast.expr | None) -> tuple[ast.expr | None, str]:
    """The status this person would inherit with no explicit `status=`."""
    if slot.dedicated_default is not None:
        dedicated = _default_arg(defaults, slot.dedicated_default)
        if dedicated is not None:
            return dedicated, slot.dedicated_default
    return _gendered_default(gender, status_male, status_female)


def _collect(tree: ast.AST, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    bindings = module_bindings(tree)
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        verb = _RECORD_VERB.get(_call_func_name(node) or "")
        if verb is None:
            continue
        defaults = record_defaults_call(node, bindings)
        if defaults is None:
            continue
        status_male = _default_arg(defaults, "status_male")
        status_female = _default_arg(defaults, "status_female")

        for record in shared_ast.walk(node):
            if not (isinstance(record, ast.Call) and _call_func_name(record) == verb):
                continue
            repeated: list[tuple[ast.Call, Slot, ast.expr, str]] = []
            for person, slot, fallback in _defaulted_persons(record, verb):
                explicit = _person_arg(person, _STATUS_INDEX, "status")
                if explicit is None:
                    continue
                gender = _person_gender(person) or fallback
                effective, field = _effective_default(
                    slot, gender, defaults, status_male, status_female)
                if effective is None or ast.unparse(explicit) != ast.unparse(effective):
                    continue
                repeated.append((person, slot, explicit, field))
            # The parent whose written status the newborn's is derived from
            # stays, default or not: see newborn_status.
            kept = load_bearing_parent(record, [person for person, *_ in repeated], bindings)
            for person, slot, explicit, field in repeated:
                if person is kept:
                    continue
                fix = _status_fix(person, lines)
                issues.append(as_dict(issue("VSR001", "redundant", explicit.lineno, level="error",
                                            fix=fix or None, status=ast.unparse(explicit), slot=slot.kwarg,
                                            verb=verb, field=field)))
    issues.sort(key=lambda i: (i["line"], str(i["message"])))
    return issues


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [as_dict(issue("SYN001", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return _collect(tree, src.splitlines())


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, issue("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}"
            for i in _collect(tree, src.splitlines())]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    errors: list[str] = []
    for arg in sys.argv[1:]:
        errors.extend(check_file(Path(arg)))
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
