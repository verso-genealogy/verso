#!/usr/bin/env python3
"""AST-based linter to check gender-role constraints in genealogy DSL records."""

import ast
import sys
from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.naming import get_gender_from_name, modernize_orthography
from verso.ru.linters.issue import issue as finding, line_text, says
from verso.ru.linters.checks import shared_ast

RELATIONSHIP_GENDER: dict[str, Gender] = {
    'FATHER': Gender.MALE, 'HUSBAND': Gender.MALE, 'SON': Gender.MALE,
    'FATHER_IN_LAW': Gender.MALE, 'SON_IN_LAW': Gender.MALE,
    'MOTHER': Gender.FEMALE, 'WIFE': Gender.FEMALE, 'DAUGHTER': Gender.FEMALE,
    'MOTHER_IN_LAW': Gender.FEMALE, 'DAUGHTER_IN_LAW': Gender.FEMALE,
}


def _person_gender(person_node: ast.Call) -> Gender | None:
    """Extract gender from a person() call node."""
    # Check for explicit gender= kwarg
    for kw in person_node.keywords:
        if kw.arg == 'gender':
            if (
                isinstance(kw.value, ast.Attribute)
                and isinstance(kw.value.value, ast.Name)
                and kw.value.value.id == 'Gender'
            ):
                if kw.value.attr == 'MALE':
                    return Gender.MALE
                elif kw.value.attr == 'FEMALE':
                    return Gender.FEMALE
            return None

    # Try name_modern_orth= kwarg first, then args[0]
    name = None
    for kw in person_node.keywords:
        if kw.arg == 'name_modern_orth':
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                name = kw.value.value
            break

    if name is None and person_node.args:
        first = person_node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            name = first.value

    if not name or '?' in name:
        return None

    return get_gender_from_name(modernize_orthography(name))


def _record_gender(call_node: ast.Call) -> Gender | None:
    """Extract record gender from birth()/death() call node."""
    # Check gender= kwarg first
    for kw in call_node.keywords:
        if kw.arg == 'gender':
            if (
                isinstance(kw.value, ast.Attribute)
                and isinstance(kw.value.value, ast.Name)
                and kw.value.value.id == 'Gender'
            ):
                if kw.value.attr == 'MALE':
                    return Gender.MALE
                elif kw.value.attr == 'FEMALE':
                    return Gender.FEMALE
            return None

    # Fall back to positional args[1]
    if len(call_node.args) > 1:
        node = call_node.args[1]
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == 'Gender'
        ):
            if node.attr == 'MALE':
                return Gender.MALE
            elif node.attr == 'FEMALE':
                return Gender.FEMALE

    return None


def _get_kwarg_person(call_node: ast.Call, kwarg_name: str) -> ast.keyword | None:
    """Return the `kwarg_name=person(...)` keyword node, or None.

    The whole keyword (not just its person() value) is returned so a finding can
    pin the entire `mother=person(...)` argument for IDE highlighting; the
    person() Call itself is `kw.value`.
    """
    for kw in call_node.keywords:
        if kw.arg == kwarg_name:
            if isinstance(kw.value, ast.Call):
                func = kw.value.func
                func_name = getattr(func, 'id', None) or getattr(func, 'attr', None)
                if func_name == 'person':
                    return kw
            return None
    return None


def _has_kwarg(call_node: ast.Call, kwarg_name: str) -> bool:
    """True when the call passes `kwarg_name=` at all (person() or not)."""
    return any(kw.arg == kwarg_name for kw in call_node.keywords)


def _char_col(lines: list[str], lineno: int, byte_col: int) -> int:
    """Convert a 0-based AST col_offset (UTF-8 byte offset) to a char column.
    DSL lines contain Cyrillic (multi-byte), so the byte offset overshoots."""
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode('utf-8')[:byte_col].decode('utf-8', 'ignore'))
    return byte_col


def _relationship_kwarg_gender(call_node: ast.Call) -> Gender | None:
    """Return implied gender from relationship= kwarg or args[1] of a call."""
    for kw in call_node.keywords:
        if kw.arg == 'relationship':
            if (isinstance(kw.value, ast.Attribute)
                    and isinstance(kw.value.value, ast.Name)
                    and kw.value.value.id == 'Relationship'):
                return RELATIONSHIP_GENDER.get(kw.value.attr)
    if len(call_node.args) > 1:
        node = call_node.args[1]
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == 'Relationship'):
            return RELATIONSHIP_GENDER.get(node.attr)
    return None


class GenderChecker(shared_ast.Visitor):
    def __init__(self, filepath: Path, lines: list[str] | None = None):
        self.filepath = filepath
        self.errors: list[str] = []
        self.issues: list[dict[str, object]] = []
        self._lines = lines or []

    def _check_role(self, node: ast.keyword | ast.Call, expected: Gender, role: str,
                    swap_to: str | None = None) -> None:
        """Flag `node` when its person's gender contradicts `role`.

        `node` is the whole `role=person(...)` keyword where there is one, so the
        finding pins that entire argument; for a positional person() (a
        relative() inside relatives=[…]) it is the person() Call itself.

        `swap_to` names the opposite role when the finding is fixable by moving
        the person to it (`mother=` ↔ `father=`), and the caller has checked that
        role is free.
        """
        person_node = node.value if isinstance(node, ast.keyword) else node
        if not isinstance(person_node, ast.Call):
            return
        actual = _person_gender(person_node)
        if actual is None or actual == expected:
            return
        said = says("GND001", "mismatch", expected=expected.name, role=role, actual=actual.name)
        self.errors.append(f"{self.filepath}:{person_node.lineno}: {said['message']}")

        issue: dict[str, object] = {"line": person_node.lineno, **said}
        # Pin the offending argument (char columns) so IDE plugins highlight it
        # instead of the whole line. An argument wrapped over several lines has
        # no single-line range — those stay full-line.
        if node.end_lineno == node.lineno and node.end_col_offset is not None:
            issue["col"] = _char_col(self._lines, node.lineno, node.col_offset)
            issue["end_col"] = _char_col(self._lines, node.lineno, node.end_col_offset)
        # Offer the role swap. Applied by line + column, so the kwarg has to sit
        # on the reported line (a person() opening on a later line does not).
        if (swap_to is not None and isinstance(node, ast.keyword)
                and node.lineno == person_node.lineno):
            issue["fix"] = {
                "type": "replace_kwarg",
                "old": f"{role}=",
                "new": f"{swap_to}=",
                "col": _char_col(self._lines, node.lineno, node.col_offset),
            }
        self.issues.append(issue)

    def _check_relatives(self, node: ast.Call) -> None:
        """Each `relatives=[relative(person(…), Relationship.X), …]` entry
        against the sex its relationship implies."""
        for kw in node.keywords:
            if kw.arg == 'relatives' and isinstance(kw.value, ast.List):
                for elt in kw.value.elts:
                    if not isinstance(elt, ast.Call):
                        continue
                    elt_name = getattr(elt.func, 'id', None) or getattr(elt.func, 'attr', None)
                    if elt_name != 'relative':
                        continue
                    if not elt.args or not isinstance(elt.args[0], ast.Call):
                        continue
                    p_name = getattr(elt.args[0].func, 'id', None) or getattr(elt.args[0].func, 'attr', None)
                    if p_name != 'person':
                        continue
                    rel_gender = _relationship_kwarg_gender(elt)
                    if rel_gender is not None:
                        self._check_role(elt.args[0], rel_gender, 'relative')

    def visit_Call(self, node: ast.Call) -> None:
        func_name = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)

        if func_name == 'marriage':
            groom_arg = _get_kwarg_person(node, 'groom')
            if groom_arg is not None:
                self._check_role(groom_arg, Gender.MALE, 'groom')

            bride_arg = _get_kwarg_person(node, 'bride')
            if bride_arg is not None:
                self._check_role(bride_arg, Gender.FEMALE, 'bride')

        elif func_name == 'birth':
            record_gender = _record_gender(node)

            child_arg = _get_kwarg_person(node, 'child')
            if child_arg is not None and record_gender is not None:
                self._check_role(child_arg, record_gender, 'child')

            # A parent in the wrong slot can be swapped to the other one — but
            # only while that slot is free, or the swap would emit the same
            # kwarg twice.
            father_arg = _get_kwarg_person(node, 'father')
            if father_arg is not None:
                self._check_role(father_arg, Gender.MALE, 'father',
                                 swap_to=None if _has_kwarg(node, 'mother') else 'mother')

            mother_arg = _get_kwarg_person(node, 'mother')
            if mother_arg is not None:
                self._check_role(mother_arg, Gender.FEMALE, 'mother',
                                 swap_to=None if _has_kwarg(node, 'father') else 'father')

            self._check_relatives(node)

        elif func_name == 'death':
            record_gender = _record_gender(node)

            deceased_arg = _get_kwarg_person(node, 'deceased')
            if deceased_arg is not None and record_gender is not None:
                self._check_role(deceased_arg, record_gender, 'deceased')

            self._check_relatives(node)

        self.generic_visit(node)


def _run(filepath: Path) -> GenderChecker:
    src = Path(filepath).read_text(encoding='utf-8')
    checker = GenderChecker(filepath, src.splitlines())
    checker.visit(shared_ast.parse(src))
    return checker


def check_file(filepath: Path) -> list[str]:
    try:
        return _run(filepath).errors
    except SyntaxError as e:
        return [line_text(filepath, finding("SYN001", "detail", e.lineno, level="error", detail=e.msg))]


def check_file_structured(filepath: Path) -> list[dict[str, object]]:
    """Structured issues carrying `col`/`end_col` for the offending argument."""
    try:
        checker = _run(filepath)
    except SyntaxError:
        return []  # single_line_calls reports the file's syntax error once
    return [{"level": "error", **issue} for issue in checker.issues]


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.py> ...")
        return 1

    errors = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_file() and p.suffix == '.py':
            errors.extend(check_file(p))

    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
