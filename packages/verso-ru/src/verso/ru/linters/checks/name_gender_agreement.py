#!/usr/bin/env python3
"""AST-based advisory linter (NGA001, NGA002): a person's surname or patronymic
in the other gender's form.

A Russian surname and patronymic agree with the person's gender — «Степанъ
Васильевъ Ляпкинъ», «Степанида Васильева Ляпкина». A record whose parts
disagree is almost always a transcription slip, and the classic way it arises
is a correction that stopped half-way: an entry first read «Степанида Васильева
Ляпкина» has its name and patronymic corrected to «Степанъ Васильевъ» against
the scan, and the surname stays feminine. `names` checks that a name and a
patronymic EXIST, `genders` that a name fits its ROLE; neither compared the
parts of one name with each other.

- **NGA001** — the surname is in the other gender's form (a man's ending in
  «-ова/-ева/-ина/-ая», a woman's in «-овъ/-евъ/-инъ/-ой/-ій»);
- **NGA002** — the patronymic is: a man's short «-ова/-ева/-ина» or full
  «-овна/-евна/-ична», a woman's «-овъ/-евъ/-инъ» or «-овичъ/-ичъ».

The person's gender is the explicit `gender=`, else the first name's
(`get_gender_from_name`); an unknown or doubtful («?») name is skipped. A
surname or patronymic with no gendered ending (Шевчукъ, Дурново) says nothing
and is skipped. Advisory: the ratchet baseline fails CI only on a NEW finding.

Measured on the whole corpus when it was added (2026-09-29): two more findings,
in records of other villages — a woman written with a masculine surname.

Run:
    python3 -m verso.ru.linters.checks.name_gender_agreement FILE [FILE...]
"""

import ast
import re
import sys
from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.naming import get_gender_from_name, modernize_orthography
from verso.ru.linters.issue import says
from verso.ru.linters.checks import shared_ast

FEMININE_SURNAME = re.compile(r"(ова|ева|ёва|ина|ына|ая|яя)$")  # i18n: content — surname and patronymic endings: vocabulary
MASCULINE_SURNAME = re.compile(r"(ов|ев|ёв|ин|ын|ой|ий|ый)$")  # i18n: content — surname and patronymic endings: vocabulary
FEMININE_PATRONYMIC = re.compile(r"(ова|ева|ёва|ина|вна|чна|шна)$")  # i18n: content — surname and patronymic endings: vocabulary
MASCULINE_PATRONYMIC = re.compile(r"(ов|ев|ёв|ин|ич)$")  # i18n: content — surname and patronymic endings: vocabulary

# person(name_orig, patr_orig, last_name_orig, name_modern_orth, patr_old,
#        last_name_modern_orth, residence, status, gender, ...)
_POSITION = {"name_orig": 0, "patr_orig": 1, "last_name_orig": 2,
             "name_modern_orth": 3, "patr_old": 4, "last_name_modern_orth": 5,
             "gender": 8}


def _arg(node: ast.Call, name: str) -> ast.expr | None:
    for kw in node.keywords:
        if kw.arg == name:
            return kw.value
    pos = _POSITION[name]
    return node.args[pos] if len(node.args) > pos else None


def _text(node: ast.Call, *names: str) -> str | None:
    """The first of `names` given as a string literal."""
    for name in names:
        value = _arg(node, name)
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
            return value.value
    return None


def _gender(node: ast.Call) -> Gender | None:
    value = _arg(node, "gender")
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) \
            and value.value.id == "Gender":
        return {"MALE": Gender.MALE, "FEMALE": Gender.FEMALE}.get(value.attr)
    name = _text(node, "name_orig", "name_modern_orth")
    if not name or "?" in name:
        return None
    return get_gender_from_name(modernize_orthography(name))


def _form(text: str) -> str:
    return modernize_orthography(text).strip()


def disagrees(gender: Gender, text: str, feminine: re.Pattern[str],
              masculine: re.Pattern[str]) -> bool:
    if "?" in text:
        return False
    form = _form(text)
    if gender is Gender.MALE:
        return bool(feminine.search(form))
    return bool(masculine.search(form)) and not feminine.search(form)


class NameGenderAgreementChecker(shared_ast.Visitor):
    def __init__(self) -> None:
        self.issues: list[dict[str, object]] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "person":
            self._check(node)
        self.generic_visit(node)

    def _check(self, node: ast.Call) -> None:
        gender = _gender(node)
        if gender is None:
            return
        who = "man" if gender is Gender.MALE else "woman"            # the variant: whose name it is
        full = " ".join(x for x in (_text(node, "name_orig", "name_modern_orth"),
                                    _text(node, "patr_orig", "patr_old"),
                                    _text(node, "last_name_orig", "last_name_modern_orth")) if x)
        surname = _text(node, "last_name_orig", "last_name_modern_orth")
        if surname and disagrees(gender, surname, FEMININE_SURNAME, MASCULINE_SURNAME):
            self.issues.append({
                "level": "warning",
                "line": node.lineno,
                **says("NGA001", f"surname_{who}", token=surname, full=full, surname=surname),
            })
        patronymic = _text(node, "patr_orig", "patr_old")
        if patronymic and disagrees(gender, patronymic, FEMININE_PATRONYMIC,
                                     MASCULINE_PATRONYMIC):
            self.issues.append({
                "level": "warning",
                "line": node.lineno,
                **says("NGA002", f"patronymic_{who}", token=patronymic, full=full, patronymic=patronymic),
            })


def check_file_structured(path: Path) -> list[dict[str, object]]:
    try:
        tree = shared_ast.parse(Path(path).read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    checker = NameGenderAgreementChecker()
    checker.visit(tree)
    return checker.issues


def check_file(path: Path) -> list[str]:
    return [f"{path}:{i['line']}: {i['message']}" for i in check_file_structured(path)]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    for arg in sys.argv[1:]:
        for line in check_file(Path(arg)):
            print(line)
    return 0  # advisory: never fail the exit code


if __name__ == "__main__":
    sys.exit(main())
