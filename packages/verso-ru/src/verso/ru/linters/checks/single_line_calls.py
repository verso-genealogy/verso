#!/usr/bin/env python3
"""Lint script to check that person() calls are on a single line,
and that known status string constants are used instead of inline literals."""

import ast
import sys
from pathlib import Path

from verso.ru.domain import statuses
from verso.ru.linters.checks.file_bindings import module_bindings, record_defaults_call
from verso.ru.linters.checks.newborn_status import derives_status, load_bearing_parent
from verso.ru.naming import modernize_orthography
from verso.ru.linters.issue import issue, line_text, says
from verso.ru.linters.checks import shared_ast

SINGLE_LINE_FUNCTIONS = {'person'}
STATUS_KEYWORDS = {'status', 'status_male', 'status_female', 'status_bride', 'status_groom', 'status_mother'}
CAUSE_OF_DEATH_KEYWORDS = {'cause_of_death'}
MARITAL_STATUS_KEYWORDS = {'marital_status'}
RECORDS_FUNCTIONS = {'birth_records', 'marriage_records', 'death_records'}
# Keywords in person() / death() that can be redundant with RecordDefaults
REDUNDANT_PERSON_KEYWORDS = {'residence', 'status'}
REDUNDANT_RECORD_KEYWORDS = {'cause_of_death'}


@statuses.kept
def known_statuses() -> dict[str, str]:
    """{text: constant name} of the workspace's status catalog, its names in alphabetical
    order (a text two constants spell is the later name's), kept for the workspace."""
    return {str(val): name for name, val in sorted(statuses.catalog().items())}


def _load_known_causes() -> dict[str, str]:
    """Return {string_value: constant_name} from causes_of_death if available.
    Includes aliases (variant forms mapped to the same constant)."""
    try:
        import verso.ru.domain.causes_of_death as mod
    except Exception:
        return {}
    # Build value → constant_name mapping
    value_to_name: dict[str, str] = {}
    for name in dir(mod):
        if name.startswith('_'):
            continue
        val = getattr(mod, name)
        if isinstance(val, str):
            value_to_name[str(val)] = name
    # Build result: direct values + aliases
    result: dict[str, str] = dict(value_to_name)
    aliases = getattr(mod, '_ALIASES', {})
    for alias_str, base_str in aliases.items():
        if base_str in value_to_name:
            result[alias_str] = value_to_name[base_str]
    return result


KNOWN_CAUSES: dict[str, str] = _load_known_causes()


def known_cause(literal: str) -> str | None:
    """The constant name for a cause written as `literal`, or None.

    The table holds modern spellings only; the books write «отъ чахотки»,
    «слабосилія», «кашлемъ». A literal is therefore tried as written, then in
    modern orthography with its first letter lowered, so one «от чахотки» row
    covers every spelling and none has to be listed twice."""
    if literal in KNOWN_CAUSES:
        return KNOWN_CAUSES[literal]
    modern = modernize_orthography(literal)
    if modern and modern != literal:
        modern = modern[0].lower() + modern[1:]
        return KNOWN_CAUSES.get(modern)
    if literal and literal[0].isupper():
        return KNOWN_CAUSES.get(literal[0].lower() + literal[1:])
    return None


def _load_known_marital() -> dict[str, str]:
    """Return {string_value: constant_name} from marital_status if available."""
    try:
        import verso.ru.domain.marital_status as mod
    except Exception:
        return {}
    result: dict[str, str] = {}
    for name in dir(mod):
        if name.startswith('_'):
            continue
        val = getattr(mod, name)
        if isinstance(val, str):  # the MARITAL_STATUSES frozenset is excluded here
            result[str(val)] = name
    return result


KNOWN_MARITAL: dict[str, str] = _load_known_marital()


class Checker(shared_ast.Visitor):
    def __init__(self, source: str = ""):
        # list of (start_line, end_line, func_name)
        self.violations: list[tuple[int, int, str]] = []
        # list of (line, kw_arg, literal, const_name, col)
        self.const_violations: list[tuple[int, str, str, str, int]] = []
        # list of (line, func_name, message, col)
        self.redundant_violations: list[tuple[int, str, str, int]] = []
        # Each redundant violation's finding as a structure — its message, code and params,
        # and the kwarg its fix removes — in step with `redundant_violations`.
        self.redundant_said: list[tuple[dict[str, object], str]] = []
        # Source lines, kept for converting AST byte offsets to char columns.
        self._lines: list[str] = source.splitlines()
        self._bindings: dict[str, ast.expr] = {}

    def _char_col(self, lineno: int, byte_col: int) -> int:
        """Convert a 0-based AST col_offset (a UTF-8 byte offset) to a 0-based
        character column. Required because DSL lines contain Cyrillic (multi-byte
        in UTF-8) before kwargs, so the byte offset overshoots the char index."""
        idx = lineno - 1
        if 0 <= idx < len(self._lines):
            return len(self._lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
        return byte_col

    def visit_Module(self, node):
        self._bindings = module_bindings(node)
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)
        if func_name in SINGLE_LINE_FUNCTIONS and node.end_lineno and node.lineno != node.end_lineno:
            self.violations.append((node.lineno, node.end_lineno, func_name))
        known = known_statuses()
        if known:
            for kw in node.keywords:
                if kw.arg in STATUS_KEYWORDS and isinstance(kw.value, ast.Constant):
                    literal = kw.value.value
                    if isinstance(literal, str) and literal in known:
                        self.const_violations.append(
                            (kw.lineno, kw.arg, literal, known[literal],
                             self._char_col(kw.lineno, kw.col_offset)))
        if KNOWN_CAUSES:
            for kw in node.keywords:
                if kw.arg in CAUSE_OF_DEATH_KEYWORDS and isinstance(kw.value, ast.Constant):
                    literal = kw.value.value
                    const = known_cause(literal) if isinstance(literal, str) else None
                    if const:
                        self.const_violations.append(
                            (kw.lineno, kw.arg, literal, const,
                             self._char_col(kw.lineno, kw.col_offset)))
        if KNOWN_MARITAL:
            for kw in node.keywords:
                if kw.arg in MARITAL_STATUS_KEYWORDS and isinstance(kw.value, ast.Constant):
                    literal = kw.value.value
                    if isinstance(literal, str) and literal in KNOWN_MARITAL:
                        self.const_violations.append(
                            (kw.lineno, kw.arg, literal, KNOWN_MARITAL[literal],
                             self._char_col(kw.lineno, kw.col_offset)))
        if func_name in RECORDS_FUNCTIONS:
            self._check_redundant_defaults(node)
        self.generic_visit(node)

    def _check_redundant_defaults(self, records_node):
        """Check for person()/death() fields that duplicate RecordDefaults values."""
        defaults = self._extract_defaults(records_node)
        if not defaults:
            return
        # Walk all nested calls looking for record calls (birth/marriage/death)
        for node in shared_ast.walk(records_node):
            if not isinstance(node, ast.Call):
                continue
            fn = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)
            if fn in ('death', 'birth', 'marriage'):
                # Check cause_of_death on the record call itself
                for kw in node.keywords:
                    if kw.arg == 'cause_of_death' and 'cause_of_death' in defaults:
                        val = _ast_value(kw.value)
                        if val is not None and val == defaults['cause_of_death']:
                            self._redundant(kw, fn, "SLC003", "cause_of_death", val)
                # Check person() calls inside the record, with role awareness
                slots = []
                for kw in node.keywords:
                    if not isinstance(kw.value, ast.Call):
                        continue
                    pfn = getattr(kw.value.func, 'id', None) or getattr(kw.value.func, 'attr', None)
                    if pfn != 'person':
                        continue
                    role = kw.arg  # e.g. 'groom', 'bride', 'witness1', 'father', etc.
                    slots.append((kw.value, role, effective_default_status(role, defaults)))
                # The parent whose written status the newborn's is derived from
                # keeps it, and so does a dead child whose own a parent's would
                # replace: see newborn_status.
                repeated = [person_node for person_node, role, effective_status in slots
                            if _status_repeats_default(person_node, role, effective_status, defaults)]
                kept = load_bearing_parent(node, repeated, self._bindings)
                for person_node, role, effective_status in slots:
                    keep_status = person_node is kept or (
                        role == 'deceased' and derives_status(node, self._bindings))
                    self._check_person_redundancy(person_node, role, effective_status, defaults,
                                                  keep_status=keep_status)
                # Check person() inside relatives=[relative(person(...), ...)] lists.
                # Only residence is checked here — status redundancy needs role-aware
                # gender resolution from the Relationship arg, which is left to
                # check_genders.py's domain.
                for kw in node.keywords:
                    if kw.arg != 'relatives' or not isinstance(kw.value, ast.List):
                        continue
                    for elt in kw.value.elts:
                        if not isinstance(elt, ast.Call):
                            continue
                        rfn = getattr(elt.func, 'id', None) or getattr(elt.func, 'attr', None)
                        if rfn != 'relative' or not elt.args:
                            continue
                        person_arg = elt.args[0]
                        if not isinstance(person_arg, ast.Call):
                            continue
                        pfn = getattr(person_arg.func, 'id', None) or getattr(person_arg.func, 'attr', None)
                        if pfn != 'person':
                            continue
                        self._check_person_redundancy(
                            person_arg, 'relative',
                            effective_status=None, defaults=defaults,
                        )

    def _check_person_redundancy(self, person_node, role, effective_status, defaults, keep_status=False):
        """Check a single person() call for redundant residence/status."""
        effective_status = _role_default_status(person_node, role, effective_status, defaults)

        for kw in person_node.keywords:
            if kw.arg == 'residence' and 'residence' in defaults:
                val = _ast_value(kw.value)
                if val is not None and val == defaults['residence']:
                    self._redundant(kw, 'person', "SLC004", "residence", val)
            if kw.arg == 'status' and effective_status is not None and not keep_status:
                val = _ast_value(kw.value)
                if val is not None and val == effective_status:
                    self._redundant(kw, 'person', "SLC005", "status", val)

    def _redundant(self, kw: ast.keyword, func: str, code: str, kwarg: str, value: object) -> None:
        said = says(code, "default", value=str(value))
        self.redundant_violations.append((kw.lineno, func, str(said["message"]), self._char_col(kw.lineno, kw.col_offset)))
        self.redundant_said.append((said, kwarg))

    def _extract_defaults(self, records_node) -> dict[str, str]:
        """Extract default values from a defaults=RecordDefaults(...) keyword,
        written in the call or bound by name at the top of the file."""
        defaults = record_defaults_call(records_node, self._bindings)
        if defaults is None:
            return {}
        result = {}
        for dkw in defaults.keywords:
            val = _ast_value(dkw.value)
            if val is not None:
                result[dkw.arg] = val
        return result


# Role → which RecordDefaults field provides the effective status default.
# Roles not listed here use status_male (for male-gendered roles) or status_female.
GENDER_AMBIGUOUS_ROLES = {'witness1', 'witness2', 'witness3', 'witness4',
                           'witness5', 'witness6',
                           'god_parent1', 'god_parent2',
                           # The deceased's status default depends on their gender;
                           # detect it from the name so a female deceased is compared
                           # against status_female (not the status_male fallback).
                           'deceased'}


def _role_default_status(person_node, role, effective_status, defaults):
    """The default status a person of `role` would get: for gender-ambiguous
    roles, by the gender of the person's first name."""
    if role in GENDER_AMBIGUOUS_ROLES:
        return _gender_aware_default_status(person_node, defaults, effective_status)
    return effective_status


def _status_repeats_default(person_node, role, effective_status, defaults):
    """Whether the person's written `status=` is the one the defaults give."""
    effective_status = _role_default_status(person_node, role, effective_status, defaults)
    return effective_status is not None and any(
        kw.arg == 'status' and _ast_value(kw.value) == effective_status for kw in person_node.keywords)


def _gender_aware_default_status(person_node, defaults, fallback):
    """For gender-ambiguous roles, detect gender from name and return appropriate default."""
    # Extract first positional arg (name) from person() call
    if not person_node.args:
        return fallback
    name_node = person_node.args[0]
    if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
        return fallback
    name = name_node.value
    # Detect gender from name using the names table
    try:
        from verso.ru.naming import get_gender_from_name, modernize_orthography
        gender = get_gender_from_name(modernize_orthography(name))
    except (ImportError, Exception):
        return fallback
    if gender is None:
        return fallback
    from verso.ru.gender import Gender
    if gender == Gender.FEMALE:
        return defaults.get('status_female')
    return defaults.get('status_male')


_ROLE_STATUS_KEY = {
    'groom': 'status_groom',    # falls back to status_male if status_groom absent
    'bride': 'status_bride',    # falls back to status_female if status_bride absent
    'father': 'status_male',
    'mother': 'status_mother',    # falls back to status_female if status_mother absent
    'god_parent1': 'status_male',   # gender unknown at AST level; use male as safe default
    'god_parent2': 'status_female',
    'witness1': 'status_male',
    'witness2': 'status_male',
    'witness3': 'status_male',
    'witness4': 'status_male',
    'witness5': 'status_male',
    'witness6': 'status_male',
    'deceased': 'status_male',
}


def effective_default_status(role: str, defaults: dict[str, str]) -> str | None:
    """Return the effective default status for a given person role."""
    key = _ROLE_STATUS_KEY.get(role)
    if key is None:
        return None
    # For groom/bride, try the specific key first, fall back to status_male/female
    if role == 'groom':
        return defaults.get('status_groom') or defaults.get('status_male')
    if role == 'bride':
        return defaults.get('status_bride') or defaults.get('status_female')
    if role == 'mother':
        return defaults.get('status_mother') or defaults.get('status_female')
    return defaults.get(key)


def _ast_value(node):
    """Extract a comparable value from an AST node (string literal or Name reference)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        # For Name nodes (constants like ECON_PEASANT_MALE), use the identifier as value
        return node.id
    return None


def spans(name: str, start: int, end: int) -> dict[str, object]:
    return says("SLC001", "spans", func=name, start=start, end=end)


def use_constant(kwarg: str, literal: str, constant: str) -> dict[str, object]:
    return says("SLC002", "constant", constant=constant, kwarg=kwarg, literal=literal)


def check_file(path):
    errors = []
    try:
        source = path.read_text()
        tree = shared_ast.parse(source)
        checker = Checker(source)
        checker.visit(tree)
        for start, end, name in checker.violations:
            errors.append(f"{path}:{start}: {spans(name, start, end)['message']}")
        for line, kw_arg, literal, const_name, _col in checker.const_violations:
            errors.append(f"{path}:{line}: {use_constant(kw_arg, literal, const_name)['message']}")
        for line, _func_name, message, _col in checker.redundant_violations:
            errors.append(f"{path}:{line}: {message}")
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
