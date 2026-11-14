#!/usr/bin/env python3
"""Lint script to check first names and patronymics in person() calls."""

import ast
import re
import sys
from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.naming import modernize_orthography, validate_first_name, validate_old_patronymic, get_gender_from_name, get_gender_from_old_patronymic
from verso.ru.linters.issue import as_dict, Issue, issue, line_text
from verso.ru.linters.checks import shared_ast


# Status constant name patterns that imply gender
_FEMALE_STATUS_SUFFIXES = ("_FEMALE", "_GIRL", "_MAIDEN", "_WIFE", "_ZHONKA", "_WIDOW", "_DAUGHTER")
_MALE_STATUS_SUFFIXES = ("_MALE", "_BOY", "_SON", "_WIDOWER")
# Known status constant names → gender (covers clergy and other special cases)
_STATUS_NAME_GENDER = {
    "HIEREUS": Gender.MALE, "PRIEST": Gender.MALE, "DEACON": Gender.MALE,
    "DYACHOK": Gender.MALE, "SEXTON": Gender.MALE, "DYACHOK_SON": Gender.MALE,
}


def gender_from_status_name(name: str) -> Gender | None:
    """Infer gender from a status constant name (e.g. ECON_PEASANT_FEMALE → FEMALE)."""
    if name in _STATUS_NAME_GENDER:
        return _STATUS_NAME_GENDER[name]
    for suffix in _FEMALE_STATUS_SUFFIXES:
        if name.endswith(suffix):
            return Gender.FEMALE
    for suffix in _MALE_STATUS_SUFFIXES:
        if name.endswith(suffix):
            return Gender.MALE
    return None


CYRILLIC_NAME_RE = re.compile(r'^[А-Яа-яЁёѣѢіІѳѲѵѴѯѮөӨъЪ?\-\s]+$')  # i18n: content — the letters a name may hold


class NameChecker(shared_ast.Visitor):
    def __init__(self, filepath):
        self.filepath = filepath
        self.errors = []
        self.issues: list[Issue] = []

    def _get_str(self, node):
        """Extract string literal from AST node, or None if not a string constant."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _get_arg(self, node, pos, keyword):
        """Get argument value by keyword name or positional index."""
        for kw in node.keywords:
            if kw.arg == keyword:
                return self._get_str(kw.value)
        if pos < len(node.args):
            return self._get_str(node.args[pos])
        return None

    def _get_status_gender(self, node):
        """Try to determine gender from the status argument of a person() call."""
        for kw in node.keywords:
            if kw.arg == "status":
                # Status is a Name reference (constant like ECON_PEASANT_FEMALE)
                if isinstance(kw.value, ast.Name):
                    return gender_from_status_name(kw.value.id)
                # Status is an Attribute reference (e.g. module.CONSTANT)
                if isinstance(kw.value, ast.Attribute):
                    return gender_from_status_name(kw.value.attr)
                # Status is a plain string literal (e.g. "ясачный
                # крестьянин") — look up in the Status registry, which
                # is populated by `statuses` module at import time.
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    from verso.ru.domain import Status
                    return Status.gender_of(kw.value.value)
        return None

    def _check_person(self, node):
        name_orig = self._get_arg(node, 0, 'name_orig')
        patr_orig = self._get_arg(node, 1, 'patr_orig')
        name_modern_orth = self._get_arg(node, 3, 'name_modern_orth')
        patr_old = self._get_arg(node, 4, 'patr_old')

        # Validate first name
        if name_modern_orth is not None:
            name_to_check = name_modern_orth
            name_orig_display = name_modern_orth
        elif name_orig is not None:
            name_to_check = modernize_orthography(name_orig)
            name_orig_display = name_orig
        else:
            name_to_check = None
            name_orig_display = None

        if not validate_first_name(name_to_check):
            self._found(issue("NAM001", "unknown", node.lineno, level="error", token=str(name_to_check),
                              name=str(name_to_check), written=str(name_orig_display)))

        # Always bind patr_to_check (used in the gender messages below); only run
        # the patronymic validation when patr_old isn't explicitly provided.
        patr_to_check = modernize_orthography(patr_orig) if patr_orig is not None else None
        if patr_old is None:
            if not validate_old_patronymic(patr_to_check, accept_full=True):
                self._found(issue("NAM002", "unknown", node.lineno, level="error", token=str(patr_to_check),
                                  patronymic=str(patr_to_check), written=str(patr_orig)))

        # Validate gender vs status consistency
        name_gender = get_gender_from_name(name_to_check) if name_to_check else None
        patr_gender = get_gender_from_old_patronymic(
            modernize_orthography(patr_orig) if patr_orig else None
        ) if patr_orig else None
        # Cross-check: name gender vs patronymic gender
        if name_gender and patr_gender and name_gender != patr_gender:
            self._found(issue("NAM003", "mismatch", node.lineno, level="error", token=str(name_to_check),
                              name=str(name_to_check),
                              name_gender=name_gender.value, patronymic=str(patr_to_check),
                              patronymic_gender=patr_gender.value))

        person_gender = name_gender or patr_gender
        status_gender = self._get_status_gender(node)
        if person_gender and status_gender and person_gender != status_gender:
            status_arg = ""
            for kw in node.keywords:
                if kw.arg == "status":
                    if isinstance(kw.value, ast.Name):
                        status_arg = kw.value.id
                    elif isinstance(kw.value, ast.Attribute):
                        status_arg = kw.value.attr
                    elif isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        status_arg = repr(kw.value.value)
                    break
            self._found(issue("NAM004", "mismatch", node.lineno, level="error",
                              token=str(name_to_check or patr_to_check), name=str(name_to_check or patr_to_check),
                              name_gender=person_gender.value, status=status_arg, status_gender=status_gender.value))

        # Validate Cyrillic-only characters in name fields
        last_name_orig = self._get_arg(node, 2, 'last_name_orig')
        last_name_modern_orth = self._get_arg(node, 5, 'last_name_modern_orth')
        for field_name, value in [
            ('name_orig', name_orig),
            ('patr_orig', patr_orig),
            ('last_name_orig', last_name_orig),
            ('name_modern_orth', name_modern_orth),
            ('last_name_modern_orth', last_name_modern_orth),
        ]:
            if value and value != '?' and not CYRILLIC_NAME_RE.match(value):
                self._found(issue("NAM005", "latin", node.lineno, level="error", token=value, field=field_name,
                                  value=value))

    def _found(self, found: Issue) -> None:
        self.issues.append(found)
        self.errors.append(line_text(self.filepath, found))

    def visit_Call(self, node):
        func_name = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)
        if func_name == 'person':
            self._check_person(node)
        self.generic_visit(node)


def check_file_structured(path) -> list[dict[str, object]]:
    """The findings as structures; a file that does not parse is one finding where its
    error has a line (as the text mode's «path:line: SyntaxError» read)."""
    try:
        tree = shared_ast.parse(path.read_text())
    except SyntaxError as e:
        return [as_dict(issue("SYN001", "bare", e.lineno, level="error"))] if e.lineno is not None else []
    checker = NameChecker(path)
    checker.visit(tree)
    return [as_dict(i) for i in checker.issues]


def check_file(path):
    errors = []
    try:
        tree = shared_ast.parse(path.read_text())
        checker = NameChecker(path)
        checker.visit(tree)
        errors.extend(checker.errors)
    except SyntaxError as e:
        errors.append(line_text(path, issue("SYN001", "bare", e.lineno, level="error")))
    return errors


def main():
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
