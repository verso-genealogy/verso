#!/usr/bin/env python3
"""CRD001 — AST linter that flags redundant surname / patronymic arguments on a
census `member()`'s `person()` when `CensusHousehold.__init__` would auto-derive
the identical value from the household head / husband / father.

`CensusHousehold.__init__` (verso/ru/dsl/records/census.py) fills in a missing name:
  - WIFE / DAUGHTER_IN_LAW → feminize_surname(husband.last_name_modern),
                             last_name_in_book=False  (married surname)
  - SON / GRANDSON         → father.last_name_modern  (un-feminized)
  - DAUGHTER / GRANDDAUGHTER→ feminize_surname(father.last_name_modern), stored as
                             birth_last_name_modern  (Geni maiden_name)
  - child roles            → patronymic derived from the father's first name
                             (derive_patronymic / derive_old_patronymic)

So when a DSL author writes that same value explicitly, it may be redundant. Two
classes, treated very differently because only one is safe to drop:

PATRONYMICS (child roles) — two tiers, by how neutral removal is:
  Tier 1, EXACT old-form match (e.g. "Степанов" == derived): re-derivation
    reproduces `patr_orig`/`patr_old`/`patr_modern` byte-for-byte — a true no-op
    (doc text, middle_name, res_name all unchanged). AUTO-FIXABLE (level=error +
    remove fix).
  Tier 2, MODERNIZE-only match (e.g. "Степановъ": modernize→"Степанов" == derived
    but not equal as written): the patronymic is redundant (same patr_old,
    patr_modern, middle_name, res_name), but re-derivation yields the derived form
    WITHOUT the pre-reform orthography, so removal drops the ъ/ѣ/і from the "ИО в
    документе" doc line. ADVISORY (level=warn) + an OPT-IN remove fix — symmetric
    with the surname findings below.
  BOTH tiers still require canonicalize(modernize(explicit)) == derive_patronymic,
  so the "Нуштанзов" false match (canonicalize="Нуштанзович" != derive="Нуштанзич",
  which would change middle_name AND the res_name) is rejected in either tier —
  widening to modernize-tolerance does not reopen that hole.

SURNAMES (wife/son/daughter…) — ADVISORY (level=warn) but carry a `remove` fix.
Removing a census surname is NOT byte-neutral: the surname disappears from the
"ФИО в документе" doc line (ФИО→ИО), and for daughters/granddaughters it also
reslots to `birth_last_name` (maiden), emptying `last_name_modern` — which RENAMES
the res_name (Geni profile recreate). Because of that these stay **warnings**, not
auto-applied errors, so the author reviews the doc-text / res_name consequence
before applying — but a one-click removal fix is offered so a genuinely redundant
surname is quick to drop in the IDE. (The daughter *maiden*-name finding,
`birth_last_name_modern_orth`, is the one surname case whose removal is fully
byte-neutral — the generator re-derives the identical maiden and it never appears
in the doc text — but it is kept a warning for symmetry.)

To stay in lockstep with the generator — and never flag load-bearing data — this
check imports the generator's own role-classification sets and naming helpers
rather than re-listing them. `tests/test_check_census_redundancy.py` adds a parity
test asserting the linter flags exactly what the generator would derive.

Patronymic auto-fix: census names are usually positional (`person("Имя",
"Отчество", …)`), which the kwarg quick-fix can't target, so a positional
patronymic yields a range-based `remove_arg` fix — but only when it is the *last*
positional argument, so removing it can't shift a later positional into its slot.
(A patronymic in front of a surname gets its fix on the second pass, after the
surname is gone and the buffer re-lints.) A kwarg patronymic yields `remove_kwarg`.

Run:
    python3 -m verso.ru.linters.checks.census_redundancy FILE [FILE...]
"""

import ast
import sys
from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.naming import (
    canonicalize_patronymic, derive_old_patronymic, derive_patronymic, feminize_surname, get_gender_from_name, modernize_orthography)
# Single source of truth: reuse the generator's role classification + gender map
# so the linter can never drift from what CensusHousehold.__init__ actually does.
from verso.ru.dsl.records.census import (
    CensusRole, _CHILD_ROLES, _DAUGHTER_ROLES, _MARRIED_WOMEN_ROLES, _REQUIRE_REF_MEMBER, ROLE_GENDER, _SON_ROLES)
from verso.ru.linters.issue import as_dict, issue as finding, line_text, says
from verso.core.i18n import Message
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast

# Role classification as plain strings (CensusRole member names, e.g. "WIFE").
_MARRIED_WOMEN = {r.name for r in _MARRIED_WOMEN_ROLES}
SONS = {r.name for r in _SON_ROLES}
DAUGHTERS = {r.name for r in _DAUGHTER_ROLES}
CHILDREN = {r.name for r in _CHILD_ROLES}
REQUIRE_REF = {r.name for r in _REQUIRE_REF_MEMBER}
SURNAME_ROLES = _MARRIED_WOMEN | SONS | DAUGHTERS
ROLE_GENDER_BY_NAME = {r.name: g for r, g in ROLE_GENDER.items()}


# --------------------------------------------------------------------------- #
# Generic AST helpers (mirrors birth_redundancy.py)                            #
# --------------------------------------------------------------------------- #
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
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _attr_name(node: ast.expr | None) -> str | None:
    """`CensusRole.WIFE` / `Gender.MALE` → "WIFE" / "MALE"."""
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _char_col(lines: list[str], lineno: int, byte_col: int) -> int:
    """Convert a 0-based AST col_offset (UTF-8 byte offset) to a char column.
    DSL lines contain Cyrillic (multi-byte), so the byte offset overshoots."""
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


# --------------------------------------------------------------------------- #
# person() / member() field extraction                                         #
# --------------------------------------------------------------------------- #
# person(name_orig, patr_orig, last_name_orig, name_modern_orth, patr_old,
#        last_name_modern_orth, residence, status, gender, ...)
def _person_arg(person_node: ast.Call, index: int, kwarg: str) -> ast.expr | None:
    pkw = _kwargs(person_node)
    if kwarg in pkw:
        return pkw[kwarg].value
    if len(person_node.args) > index:
        return person_node.args[index]
    return None


def _name_modern(person_node: ast.Call) -> str | None:
    modern = _kwargs(person_node).get("name_modern_orth")
    if modern is not None:
        return _string_literal(modern.value)
    orig = _string_literal(_person_arg(person_node, 0, "name_orig"))
    return modernize_orthography(orig) if orig else None


def _current_surname_modern(person_node: ast.Call) -> str | None:
    """The modern *current* surname a person carries: last_name_modern_orth if
    given, else modernize(last_name_orig). Maiden (birth_last_name) is separate."""
    modern = _kwargs(person_node).get("last_name_modern_orth")
    if modern is not None:
        return _string_literal(modern.value)
    orig = _string_literal(_person_arg(person_node, 2, "last_name_orig"))
    return modernize_orthography(orig) if orig else None


class _Member:
    """Lightweight view of a `member(...)` Call node."""

    def __init__(self, node: ast.Call):
        self.node = node
        self.number = _int_literal(_member_arg(node, 0, "number"))
        person = _member_arg(node, 1, "person")
        self.person: ast.Call | None = (
            person if isinstance(person, ast.Call) and _call_func_name(person) == "person"
            else None
        )
        self.role = _attr_name(_member_arg(node, 2, "role"))
        self.ref_member = _int_literal(_member_arg(node, 3, "ref_member"))
        mkw = _kwargs(node)
        comment_kw = mkw.get("comment")
        self.comment = _string_literal(comment_kw.value) if comment_kw is not None else None
        hidden_kw = mkw.get("hidden")
        self.hidden = _is_true(hidden_kw.value) if hidden_kw is not None else False


# member(number, person, role, ref_member, age, ...)
def _member_arg(member_node: ast.Call, index: int, kwarg: str) -> ast.expr | None:
    mkw = _kwargs(member_node)
    if kwarg in mkw:
        return mkw[kwarg].value
    if len(member_node.args) > index:
        return member_node.args[index]
    return None


def _gender(m: _Member) -> str | None:
    """Infer a member's gender the way Person does: explicit gender kwarg →
    role-implied → first-name lookup. Returns "MALE"/"FEMALE"/None."""
    if m.person is not None:
        gender_kw = _kwargs(m.person).get("gender")
        g = _attr_name(gender_kw.value) if gender_kw is not None else None
        if g:
            return g
    if m.role and m.role in ROLE_GENDER_BY_NAME:
        return ROLE_GENDER_BY_NAME[m.role].name
    if m.person is not None:
        name = _name_modern(m.person)
        if name:
            inferred = get_gender_from_name(name)
            if inferred is not None:
                return inferred.name
    return None


def _resolve_source(m: _Member, head: _Member | None,
                    by_num: dict[int | None, _Member]) -> _Member | None:
    """Mirror census._resolve_relative_source: ref_member → else HEAD, except
    roles in _REQUIRE_REF_MEMBER (no HEAD fallback)."""
    if m.ref_member is not None:
        return by_num.get(m.ref_member)
    if m.role in REQUIRE_REF:
        return None
    return head


def _is_adopted(m: _Member) -> bool:
    return bool(m.comment and "приемн" in m.comment.lower())  # i18n: content — the comment words the DSL writes


# --------------------------------------------------------------------------- #
# Fix builders                                                                 #
# --------------------------------------------------------------------------- #
def _remove_kwarg_fix(person_node: ast.Call, kwarg: str,
                      lines: list[str]) -> dict[str, object]:
    kw = _kwargs(person_node)[kwarg]
    return {"type": "remove_kwarg", "kwarg": kwarg,
            "col": _char_col(lines, kw.lineno, kw.col_offset)}


def _remove_arg_fix(person_node: ast.Call, index: int, label: str,
                    lines: list[str]) -> dict[str, object] | None:
    """Range-based removal of a positional arg — only safe when it is the LAST
    positional (otherwise a later positional would shift into its slot)."""
    if index != len(person_node.args) - 1:
        return None
    arg = person_node.args[index]
    if arg.end_lineno != arg.lineno or arg.end_col_offset is None:
        return None
    return {
        "type": "remove_arg",
        "kwarg": label,
        "col": _char_col(lines, arg.lineno, arg.col_offset),
        "end_col": _char_col(lines, arg.lineno, arg.end_col_offset),
    }


# --------------------------------------------------------------------------- #
# Core                                                                         #
# --------------------------------------------------------------------------- #
def _household_members(hh_node: ast.Call) -> list[_Member]:
    out: list[_Member] = []
    for arg in hh_node.args:
        if isinstance(arg, ast.Call) and _call_func_name(arg) == "member":
            out.append(_Member(arg))
    return out


def _writes_current_surname(person_node: ast.Call) -> bool:
    """Whether a person's call writes a current surname (`CensusHousehold.__init__`: `p.last_name or
    p.last_name_modern`). An expression the check cannot read counts as one, so the check stays silent there."""
    for value in (_person_arg(person_node, 2, "last_name_orig"), _kwargs(person_node).get("last_name_modern_orth")):
        if isinstance(value, ast.keyword):
            value = value.value
        if value is None or (isinstance(value, ast.Constant) and value.value in (None, "")):
            continue
        return True
    return False


def _effective_surnames(members: list[_Member], head: _Member | None,
                        by_num: dict[int | None, _Member]) -> dict[int | None, str]:
    """Replicate the generator's surname pass, recording each member's effective *current* modern surname (explicit,
    else derived). A written surname is there from the start, as on the generator's `Person`; a derived one is made
    in member order, from the source's surname as it stands when the member is reached. Used so a chained source
    (e.g. a son who himself inherits HEAD's surname) resolves."""
    eff: dict[int | None, str] = {}
    for m in members:
        if m.person is not None and (cur := _current_surname_modern(m.person)):
            eff[m.number] = cur
    for m in members:
        if m.person is None or m.number in eff:
            continue
        if m.role not in SURNAME_ROLES or m.hidden or _is_adopted(m):
            continue
        source = _resolve_source(m, head, by_num)
        if source is None:
            continue
        src = eff.get(source.number)
        if not src or _gender(source) == Gender.FEMALE.name:
            continue
        if m.role in SONS:
            eff[m.number] = src            # sons carry a current surname
        # married women / daughters do not become a surname source for others
    return eff


def _family_surname(m: _Member, source: _Member, head: _Member | None, by_num: dict[int | None, _Member],
                    position: dict[int, int], eff: dict[int | None, str]) -> str | None:
    """The surname `source` had when `CensusHousehold.__init__` reached `m`, which is what `m` would be given were its
    own not written. The generator makes ONE pass in member order: a source that wrote a surname has it at once; one
    that derived its own has it only if listed BEFORE `m`; and if its derivation rests on `m` (it names `m`, or a
    member that does), `m`'s surname is what it derived from, so the value is circular and `m`'s is load-bearing.
    A member naming itself has no source but its own surname. (`on_json.redundancy._family_surname` is the walk's.)"""
    def writes(node: _Member) -> bool:
        return node.person is not None and _writes_current_surname(node.person)

    if source is m or (not writes(source) and position[id(source)] > position[id(m)]):
        return None
    node: _Member | None = source
    seen: set[int] = set()
    while node is not None and not writes(node):
        if id(node) in seen:
            return None
        seen.add(id(node))
        node = _resolve_source(node, head, by_num)
        if node is m:
            return None
    return eff.get(source.number)


def _surname_issues(m: _Member, derived: str,
                    lines: list[str]) -> list[dict[str, object]]:
    """Flag an explicit current surname that matches the head's family surname.

    ADVISORY (level=warn) but carries a `remove` fix: removing a census surname is
    NOT byte-neutral — the surname disappears from the "ФИО в документе" doc line
    (ФИО→ИО), and for daughters/granddaughters it reslots to `birth_last_name`
    (maiden), emptying `last_name_modern` and thus RENAMING the res_name. So the
    finding stays a warning (author reviews before applying), but a one-click
    removal fix is offered. A positional surname only gets the range-based fix when
    it is the LAST positional (else `_remove_arg_fix` returns None → no fix).
    """
    assert m.person is not None
    role = (m.role or "").lower()
    pkw = _kwargs(m.person)
    suffix = t("census.surname_matches_head", role=role)
    # kwarg form: last_name_modern_orth
    modern_kw = pkw.get("last_name_modern_orth")
    if modern_kw is not None and _string_literal(modern_kw.value) == derived:
        return [{"line": modern_kw.value.lineno, "level": "warn",
                 **says("CRD001", "modern_surname", derived=derived, suffix=suffix),
                 "fix": _remove_kwarg_fix(m.person, "last_name_modern_orth", lines)}]
    # last_name_orig: kwarg or positional index 2
    orig_kw = pkw.get("last_name_orig")
    if orig_kw is not None:
        orig_val = _string_literal(orig_kw.value)
        if orig_val is not None:
            if modernize_orthography(orig_val) == derived:
                return [{"line": orig_kw.value.lineno, "level": "warn",
                         **says("CRD002", "surname_orig", orig_val=orig_val, suffix=suffix),
                         "fix": _remove_kwarg_fix(m.person, "last_name_orig", lines)}]
            return []
    if len(m.person.args) > 2:
        val = _string_literal(m.person.args[2])
        if val is not None and modernize_orthography(val) == derived:
            return [{"line": m.person.args[2].lineno, "level": "warn",
                     **says("CRD003", "surname", val=val, suffix=suffix),
                     "fix": _remove_arg_fix(m.person, 2, "last_name_orig", lines)}]
    return []


def _daughter_maiden_issue(m: _Member, derived: str,
                           lines: list[str]) -> list[dict[str, object]]:
    """A daughter's explicit maiden name (birth_last_name_modern_orth) matching the
    derived value. Level=warn with a `remove` fix, for symmetry with the other
    surname findings — though this removal is actually fully byte-neutral (the
    generator re-derives the identical maiden and it never appears in the doc text
    or res_name)."""
    assert m.person is not None
    kw = _kwargs(m.person).get("birth_last_name_modern_orth")
    if kw is not None and _string_literal(kw.value) == derived:
        return [{"line": kw.value.lineno, "level": "warn",
                 **says("CRD004", "modern_birth_surname", derived=derived),
                 "fix": _remove_kwarg_fix(m.person, "birth_last_name_modern_orth", lines)}]
    return []


# Suffix appended to a Tier-2 (modernize-only) patronymic message.
def _patr_advisory() -> Message:
    return t("census.patronymic_advisory")


def patronymic_tier(explicit: str, gen_orig: str, gen_modern: str) -> str | None:
    """Classify an explicit patronymic: "exact" (Tier 1, byte-neutral),
    "modernize" (Tier 2, redundant but drops orthography), or None.

    BOTH tiers require the modern form to canonicalize to gen_modern (so
    middle_name AND the res_name are unchanged). This rejects the false match
    "Нуштанзов" == derive_old_patronymic whose canonicalize("Нуштанзов")=
    "Нуштанзович" != derive_patronymic="Нуштанзич" — in either tier, so
    widening to modernize-tolerance does NOT reopen that hole.
    """
    try:
        if canonicalize_patronymic(modernize_orthography(explicit)) != gen_modern:
            return None
    except ValueError:
        return None
    if explicit == gen_orig:
        return "exact"                              # doc text re-derives identically
    if modernize_orthography(explicit) == gen_orig:
        return "modernize"                          # re-derivation drops pre-reform orth.
    return None


def _patronymic_issue(m: _Member, source: _Member,
                      lines: list[str]) -> list[dict[str, object]]:
    """Flag an explicit child patronymic that equals what the generator derives
    from the (male) parent's first name. Two tiers, by how neutral removal is:

    Tier 1 — EXACT old-form match (explicit == gen_orig, e.g. "Степанов"):
      re-derivation reproduces `patr_orig` byte-for-byte, so removal is a true
      no-op. Emitted with the default level (error) + a remove fix.
    Tier 2 — MODERNIZE-only match (explicit != gen_orig but
      modernize(explicit) == gen_orig, e.g. "Степановъ"): the patronymic is
      redundant (same patr_old / patr_modern / middle_name / res_name), but
      re-derivation yields gen_orig WITHOUT the pre-reform orthography, so removal
      drops the ъ/ѣ/і from the "ИО в документе" doc line. Emitted level=warn with
      an OPT-IN remove fix — advisory, the author reviews the doc-text change
      before applying (symmetric with the surname findings).
    """
    assert m.person is not None and source.person is not None
    role = (m.role or "").lower()
    parent_name = _name_modern(source.person)
    if not parent_name or m.role not in ROLE_GENDER_BY_NAME:
        return []
    child_gender = ROLE_GENDER_BY_NAME[m.role]
    gen_modern = derive_patronymic(parent_name, child_gender)
    gen_orig = derive_old_patronymic(parent_name, child_gender) or gen_modern
    if not gen_orig or gen_orig == "?" or not gen_modern or gen_modern == "?":
        return []
    pkw = _kwargs(m.person)

    # kwarg form: patr_orig
    orig_kw = pkw.get("patr_orig")
    if orig_kw is not None:
        val = _string_literal(orig_kw.value)
        if val is not None:
            tier = patronymic_tier(val, gen_orig, gen_modern)
            if tier is not None:
                adv = _patr_advisory() if tier == "modernize" else ""
                issue: dict[str, object] = {
                    "line": orig_kw.value.lineno,
                    **says("CRD005", "patronymic_orig", val=val, role=role, adv=adv),
                    "level": "warn",
                    "fix": _remove_kwarg_fix(m.person, "patr_orig", lines)}
                return [issue]
        return []
    # positional index 1
    if len(m.person.args) > 1:
        val = _string_literal(m.person.args[1])
        if val is not None:
            tier = patronymic_tier(val, gen_orig, gen_modern)
            if tier is not None:
                adv = _patr_advisory() if tier == "modernize" else ""
                issue = {
                    "line": m.person.args[1].lineno,
                    **says("CRD006", "patronymic", val=val, role=role, adv=adv),
                    "level": "warn",
                    "fix": _remove_arg_fix(m.person, 1, "patr_orig", lines)}
                return [issue]
    return []


def _collect(tree: ast.AST, lines: list[str]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_func_name(node) != "household":
            continue
        members = _household_members(node)
        if not members:
            continue
        by_num: dict[int | None, _Member] = {m.number: m for m in members}
        head = next((m for m in members if m.role == CensusRole.HEAD.name), None)
        eff = _effective_surnames(members, head, by_num)
        position = {id(m): i for i, m in enumerate(members)}

        for m in members:
            if m.person is None or m.hidden or _is_adopted(m):
                continue

            # --- surname redundancy ---
            if m.role in SURNAME_ROLES:
                source = _resolve_source(m, head, by_num)
                if source is not None and _gender(source) != Gender.FEMALE.name:
                    src = _family_surname(m, source, head, by_num, position, eff)
                    if src:
                        derived = src if m.role in SONS else feminize_surname(src)
                        issues += _surname_issues(m, derived, lines)
                        # A daughter who writes a current surname is given no maiden name: hers is load-bearing.
                        if m.role in DAUGHTERS and not _writes_current_surname(m.person):
                            issues += _daughter_maiden_issue(m, derived, lines)

            # --- patronymic redundancy (child roles only) ---
            if m.role in CHILDREN:
                source = _resolve_source(m, head, by_num)
                if source is not None and _gender(source) == Gender.MALE.name:
                    issues += _patronymic_issue(m, source, lines)

    issues.sort(key=lambda i: (i["line"], str(i["message"])))
    return issues


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [as_dict(finding("SYN001", "detail", e.lineno or 1, level="error", detail=e.msg))]
    out: list[dict[str, object]] = []
    for i in _collect(tree, src.splitlines()):
        issue = {"level": i.get("level", "error"), "line": i["line"], "message": i["message"]}
        if i.get("fix"):
            issue["fix"] = i["fix"]
        out.append(issue)
    return out


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, finding("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree, src.splitlines())]


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
