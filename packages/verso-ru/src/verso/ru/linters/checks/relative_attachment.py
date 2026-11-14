#!/usr/bin/env python3
"""RLA001–RLA003 — AST linter for how a ``relative()`` attaches to its subject
inside a birth / marriage / death record.

`relationship_ref` names the person a relative hangs off ("жених", "невеста",
"восприемника №N", …). Two things can go wrong, and both are invisible today:

* the ref does not attach at all — it names a slot the record lacks, or one the
  translator never resolves, so the relative is emitted as an edge-less profile
  (**RLA001**);
* the ref attaches, but the two people disagree about the kinship they claim —
  a patronymic or surname that cannot both be right (**RLA002–RLA003**).

Run:
    python3 -m verso.ru.linters.checks.relative_attachment FILE [FILE...]
"""

import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

from verso.ru.gender import Gender
from verso.ru.naming import (
    canonicalize_patronymic, derive_patronymic, feminize_surname, get_gender_from_name, modernize_orthography)
# Reuse the census checks' node readers so the way a person() is read can never
# drift between the linters (same reason CSR001 and VSR001 import from here).
from verso.ru.linters.checks.census_redundancy import (
    _attr_name, _char_col, _current_surname_modern, _call_func_name, _kwargs, _name_modern, _person_arg, _string_literal)
from verso.ru.linters.issue import as_dict, issue, line_text, says
from verso.ru.linters.checks import shared_ast

_RECORD_VERB = {
    "birth_records": "birth",
    "marriage_records": "marriage",
    "death_records": "death",
}

_M, _F = Gender.MALE.name, Gender.FEMALE.name
GODPARENT_REF = re.compile(r"^восприемника №(\d+)$")  # i18n: content — the reference words and endings the DSL writes
WITNESS_REF = re.compile(r"^поручитель №(\d+)$")  # i18n: content — the reference words and endings the DSL writes

# Two suffix conventions can serve one father's name — Иона yields both
# «Ионична» (what derive_patronymic picks) and the «Ионовна» the books write.
# Comparing stems keeps that from reading as a contradiction, and makes the
# Матфей/Матвей spelling pair agree for free.
_PATRONYMIC_SUFFIX = re.compile(r"(ович|евич|ьич|инична|ична|овна|евна|ич|на)$")  # i18n: content — the reference words and endings the DSL writes


def patronymic_stem(patronymic: str) -> str:
    return _PATRONYMIC_SUFFIX.sub("", patronymic)


class Subject(NamedTuple):
    """The person a relative attaches to.

    ``wired`` records whether the TRANSLATOR builds a relationship edge for this
    ref — deliberately stricter than `relationship_ref`'s spelling allowlist,
    which blesses refs the generator silently ignores.
    """

    kwarg: str
    gender_fallback: str | None
    wired: bool


def _anchor(issue: dict[str, object], node: ast.expr | None,
            lines: list[str], fallback: ast.AST) -> dict[str, object]:
    """Pin the finding to the offending literal so an IDE underlines the field
    rather than painting the whole line. Falls back to the enclosing call when
    the node straddles lines (char columns: ast offsets are UTF-8 BYTES)."""
    if (node is not None and node.end_lineno == node.lineno
            and node.end_col_offset is not None):
        issue["line"] = node.lineno
        issue["col"] = _char_col(lines, node.lineno, node.col_offset)
        issue["end_col"] = _char_col(lines, node.lineno, node.end_col_offset)
    else:
        issue["line"] = getattr(fallback, "lineno", issue.get("line", 1))
    return issue


def _slot_person(record_node: ast.Call, kwarg: str) -> ast.Call | None:
    value = _kwargs(record_node).get(kwarg)
    if value is None or not isinstance(value.value, ast.Call):
        return None
    return value.value if _call_func_name(value.value) == "person" else None


def _person_gender(person_node: ast.Call, fallback: str | None = None) -> str | None:
    explicit = _attr_name(_person_arg(person_node, 8, "gender"))
    if explicit:
        return explicit
    name = _name_modern(person_node)
    if name:
        inferred = get_gender_from_name(name)
        if inferred is not None:
            return inferred.name
    return fallback


def _sole_female_godparent(record_node: ast.Call) -> int | None:
    """The single female godparent slot of a birth, if there is exactly one —
    what an unnumbered «восприемница» must have meant."""
    female = [
        i for i in (1, 2, 3, 4)
        if (gp := _slot_person(record_node, f"god_parent{i}")) is not None
        and _person_gender(gp, {1: _M, 2: _F}.get(i)) == _F
    ]
    return female[0] if len(female) == 1 else None


def _subject_of(record_node: ast.Call, verb: str, ref: str | None) -> Subject | None:
    """Mirror the translator: which person does this ref attach the relative to,
    and does the translator actually wire the two together?"""
    ref = ref or ""
    if verb == "marriage":
        if ref == "жених":  # i18n: content — the reference words and endings the DSL writes
            return Subject("groom", _M, True)
        if ref == "невеста":  # i18n: content — the reference words and endings the DSL writes
            return Subject("bride", _F, True)
        witness = WITNESS_REF.match(ref)
        if witness:
            slot = f"witness{witness.group(1)}"
            if _slot_person(record_node, slot) is None:
                return None
            return Subject(slot, None, True)
        return None
    if verb == "birth":
        numbered = GODPARENT_REF.match(ref)
        if numbered:
            slot = f"god_parent{numbered.group(1)}"
            if _slot_person(record_node, slot) is None:
                return None
            return Subject(slot, {"god_parent1": _M, "god_parent2": _F}.get(slot), True)
        if ref == "восприемница":  # i18n: content — the reference words and endings the DSL writes
            sole = _sole_female_godparent(record_node)
            return Subject(f"god_parent{sole}", _F, False) if sole else None
        if ref == "мать":  # i18n: content — the reference words and endings the DSL writes
            return Subject("mother", _F, True) if _slot_person(record_node, "mother") else None
        return None
    if verb == "death" and not ref:
        return Subject("deceased", None, True)
    return None


def _patronymic_written(person_node: ast.Call) -> tuple[str, str] | None:
    """(as the DSL spells it, canonicalized to the form the profile carries).

    The raw spelling is kept so the message names something greppable in the
    file; the canonical form is what the comparison runs on.
    """
    raw = _string_literal(_person_arg(person_node, 1, "patr_orig"))
    if not raw:
        return None
    try:
        return raw, canonicalize_patronymic(modernize_orthography(raw))
    except ValueError:
        return None


def _patronymic_issue(relative_node: ast.Call, relative_person: ast.Call,
                      subject: ast.Call, subject_gender: str | None,
                      lines: list[str]) -> dict[str, object] | None:
    """A subject whose stated patronymic cannot come from this father's name."""
    father_name = _name_modern(relative_person)
    stated = _patronymic_written(subject)
    if not father_name or stated is None or subject_gender not in (_M, _F):
        return None
    raw, written = stated
    derived = derive_patronymic(father_name, Gender[subject_gender])
    if not derived or derived == "?":
        return None
    if written == derived or patronymic_stem(written) == patronymic_stem(derived):
        return None
    return _anchor({
        "level": "warn",
        **says("RLA002", "patronymic", raw=raw, written=written, father_name=father_name, derived=derived),
    }, _person_arg(relative_person, 0, "name_orig"), lines, relative_node)


def _surname_node(person_node: ast.Call) -> ast.expr | None:
    """The surname literal the message quotes: the modern spelling when given,
    else the as-written one."""
    modern = _kwargs(person_node).get("last_name_modern_orth")
    if modern is not None:
        return modern.value
    return _person_arg(person_node, 2, "last_name_orig")


def _surname_issue(relative_node: ast.Call, relative_person: ast.Call,
                   subject: ast.Call, subject_gender: str | None,
                   lines: list[str]) -> dict[str, object] | None:
    """A father and child whose stated surnames cannot both be right.

    A missing surname on either side is silent: that is the generator's
    derivation territory (Death.__init__ already fills one from the other),
    not a contradiction between two stated readings.
    """
    father_surname = _current_surname_modern(relative_person)
    child_surname = _current_surname_modern(subject)
    if not father_surname or not child_surname:
        return None
    expected = (feminize_surname(father_surname) if subject_gender == _F
                else father_surname)
    if expected == child_surname:
        return None
    return _anchor({
        "level": "warn",
        **says("RLA003", "surname", child_surname=repr(child_surname), father_surname=repr(father_surname), expected=repr(expected)),
    }, _surname_node(relative_person), lines, relative_node)


def _relatives_of(record_node: ast.Call) -> list[ast.Call]:
    value = _kwargs(record_node).get("relatives")
    if value is None or not isinstance(value.value, (ast.List, ast.Tuple)):
        return []
    return [e for e in value.value.elts
            if isinstance(e, ast.Call) and _call_func_name(e) == "relative"]


def _unattached_issue(relative_node: ast.Call, record_node: ast.Call,
                      verb: str, ref: str | None,
                      lines: list[str]) -> dict[str, object] | None:
    subject = _subject_of(record_node, verb, ref)
    shown = ref or "<none>"
    ref_node = _person_arg(relative_node, 2, "relationship_ref")
    if subject is None:
        return _anchor({
            "level": "error",
            **says("RLA001", "no_subject", ref=shown, verb=verb),
        }, ref_node, lines, relative_node)
    if not subject.wired:
        sole = _sole_female_godparent(record_node) if ref == "восприемница" else None  # i18n: content — the reference words and endings the DSL writes
        unwired = says("RLA001", "unwired_godmother", ref=shown, kwarg=subject.kwarg, godparent=sole) if sole \
            else says("RLA001", "unwired", ref=shown, kwarg=subject.kwarg)
        return _anchor({
            "level": "error",
            **unwired,
        }, ref_node, lines, relative_node)
    return None


def _collect(tree: ast.AST, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        verb = _RECORD_VERB.get(_call_func_name(node) or "")
        if verb is None:
            continue
        for record in shared_ast.walk(node):
            if not (isinstance(record, ast.Call) and _call_func_name(record) == verb):
                continue
            for rel in _relatives_of(record):
                ref = _string_literal(_person_arg(rel, 2, "relationship_ref"))
                unattached = _unattached_issue(rel, record, verb, ref, lines)
                if unattached is not None:
                    issues.append(unattached)

                subject = _subject_of(record, verb, ref)
                relative_person = _person_arg(rel, 0, "person")
                if subject is None or not isinstance(relative_person, ast.Call):
                    continue
                if _call_func_name(relative_person) != "person":
                    continue
                subject_person = _slot_person(record, subject.kwarg)
                if subject_person is None:
                    continue
                kinship = _attr_name(_person_arg(rel, 1, "relationship"))
                subject_gender = _person_gender(subject_person, subject.gender_fallback)

                # STEP_/FOSTER_FATHER are never compared: a stepdaughter's
                # patronymic legitimately names a different man.
                # The record declares the SOURCE's own kin names inconsistent —
                # a patronymic or surname that cannot come from the relative the
                # same entry names. The transcription is faithful, so the two
                # NAME checks stand down; RLA001 does not, because whether a ref
                # resolves is our modelling, not the scribe's.
                if _string_literal(_kwargs(record).get("source_kin_error")
                                   and _kwargs(record)["source_kin_error"].value):
                    continue

                if kinship == "FATHER":
                    patronymic = _patronymic_issue(
                        rel, relative_person, subject_person, subject_gender, lines)
                    if patronymic is not None:
                        issues.append(patronymic)
                    surname = _surname_issue(
                        rel, relative_person, subject_person, subject_gender, lines)
                    if surname is not None:
                        issues.append(surname)
                # HUSBAND/WIFE surnames are deliberately NOT compared: these
                # books routinely record a married woman under her MAIDEN
                # surname (a widow named with her father's surname beside her
                # late husband; two sisters of one family in one birth, one of
                # them married), and no rule distinguishes that convention from
                # a real error.
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
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree, src.splitlines())]


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
