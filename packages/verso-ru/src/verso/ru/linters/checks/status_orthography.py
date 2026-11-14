"""AST-based linter (SOR001): a classification field in pre-reform orthography.

The DSL keeps the scribe's spelling where it transcribes him — names
(`person()`) and the source's own words in a member's `comment=` — and writes
CLASSIFICATION fields in modern orthography, so they can be parsed and
standardized (the maintainers' ruling of 2026-10-01):
`status=` and the reason a member left the roll, `departure_reason=`. The
status catalog (`verso.ru.domain.statuses`) is modern for the same reason.

SOR001 flags such a field whose words carry a pre-reform letter — ѣ, і, ѳ, ѵ —
or a hard sign closing a word («умеръ», «унтеръ-офицеръ»), or an abbreviated
honorific the books capitalise and modern spelling does not: «вотчины Г-на
Ноздрева» → «г-на», «Г.Г.»/«Гг. Головлевых» → «гг.», «вотчины Г. Тентетникова» → «г.»
(the maintainers' ruling of 2026-10-02; 0 left in the corpus when it was added). A bare
«Г.» counts only after «вотчины»/«отчины», where it is the honorific and not an
initial («дворянина А. Р. Ноздрева»). It reads a string
literal and a constant the file defines itself (`TENTETNIKOV_M = "…"`, through
`file_bindings`); a catalog constant is modern by construction. The message
proposes the modern spelling, and names the catalog constant when that
spelling is one («священникъ» → PRIEST).

Measured 2026-10-01 over the five villages: 91 uses — Маниловка 77 (15 texts,
«крестьянинъ собственникъ» ×47), Глуповы Горы 13 («умеръ», «отданъ въ
рекруты», «… Г. Тентетникова»), Заманиловка 1 («воинъ») — all rewritten before the
check was registered, so it gates at zero.

Path-independent: scopes on kwargs and module-level bindings only.

Run:
    python3 -m verso.ru.linters.checks.status_orthography FILE [FILE...]
"""

import ast
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from verso.ru.domain import statuses
from verso.ru.linters.checks.file_bindings import module_bindings, string_constants
from verso.ru.linters.issue import as_dict, issue
from verso.ru.linters.checks import shared_ast

# `status=` and its RecordDefaults forms, and the roll's reason for leaving.
FIELDS = frozenset({"status", "status_male", "status_female", "status_mother",
                     "status_bride", "status_groom", "departure_reason"})

_CONSONANTS = "бвгджзклмнпрстфхцчшщБВГДЖЗКЛМНПРСТФХЦЧШЩ"  # i18n: content — the old orthography and status words: vocabulary
# A pre-reform letter, or ъ ending a word after a consonant (before a space,
# hyphen, punctuation or the end).
PRE_REFORM = re.compile(rf"[ѣѢіІѳѲѵѴ]|(?<=[{_CONSONANTS}])ъ(?![а-яёА-ЯЁ])")  # i18n: content — the old orthography and status words: vocabulary
# A capitalised honorific: Г-на/Г-ну/Г-жи…, Г.Г. (господ), Гг., and a bare Г.
# after the estate word, where it cannot be an initial.
HONORIFIC = re.compile(r"(?<![а-яёА-ЯЁ])(?:Г-[нж][а-я]*|Г\.\s?Г\.|Гг\.)|(?<=отчины )Г\.(?=\s)")  # i18n: content — the old orthography and status words: vocabulary


@statuses.kept
def catalog() -> dict[str, str]:
    """{text: constant name} of the workspace's status catalog (`statuses.catalog()`, in its
    order: a text two constants spell is the later one's), kept for the workspace."""
    return {str(v): k for k, v in statuses.catalog().items()}


# The modern word where the 1918 spelling is not the letter-for-letter one:
# a catalog wording the corpus standardizes on.
_WORDS = {"дьячек": "дьячок"}  # i18n: content — the old orthography and status words: vocabulary


def modern_spelling(text: str) -> str:
    """The text in modern orthography: ѣ→е, і→и, ѳ→ф, ѵ→и, a word-final ъ
    dropped, the adjective ending -аго/-яго → -ого/-его, без-/из-/раз-/
    воз-/низ-/чрез- before a voiceless consonant spelled with с, and an
    abbreviated honorific in lowercase (Г-на → г-на, Г.Г./Гг. → гг.)."""
    s = text
    for old, new in (("ѣ", "е"), ("Ѣ", "Е"), ("і", "и"), ("І", "И"),  # i18n: content — the old orthography and status words: vocabulary
                     ("ѳ", "ф"), ("Ѳ", "Ф"), ("ѵ", "и"), ("Ѵ", "И")):  # i18n: content — the old orthography and status words: vocabulary
        s = s.replace(old, new)
    s = re.sub(rf"(?<=[{_CONSONANTS}])ъ(?![а-яёА-ЯЁ])", "", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<=[а-яё])аго\b", "ого", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<=[а-яё])яго\b", "его", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"\b(без|из|раз|воз|низ|чрез)(?=[кпстфхцчшщ])",  # i18n: content — the old orthography and status words: vocabulary
               lambda m: m.group(1)[:-1] + "с", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<![а-яёА-ЯЁ])Г\.\s?Г\.|(?<![а-яёА-ЯЁ])Гг\.", "гг.", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<![а-яёА-ЯЁ])Г-(?=[нж])", "г-", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<=отчины )Г\.(?=\s)", "г.", s)  # i18n: content — the old orthography and status words: vocabulary
    return " ".join(_WORDS.get(w, w) for w in s.split(" "))


def _char_col(lines: Sequence[str], lineno: int, byte_col: int) -> int:
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


def _collect(tree: ast.AST, lines: Sequence[str]) -> list[dict[str, Any]]:
    bindings = module_bindings(tree)
    file_texts = string_constants(bindings)
    issues: list[dict[str, Any]] = []
    for node in shared_ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg not in FIELDS:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text, bound, pin = value.value, None, value
        elif isinstance(value, ast.Name) and value.id in file_texts:
            text = file_texts[value.id]
            bound = value.id
            pin = bindings[value.id]
        else:
            continue
        if not (PRE_REFORM.search(text) or HONORIFIC.search(text)):
            continue
        modern = modern_spelling(text)
        const = catalog().get(modern)
        variant = ("bound" if bound else "literal") + ("_constant" if const else "_words")
        span: dict[str, Any] = {}
        if pin.lineno == pin.end_lineno and pin.end_col_offset is not None:
            span = {"col": _char_col(lines, pin.lineno, pin.col_offset),
                    "end_col": _char_col(lines, pin.lineno, pin.end_col_offset)}
        params: dict[str, Any] = {"kwarg": node.arg, "text": text, "modern": modern, **({"name": bound} if bound else {}),
                  **({"constant": const} if const else {})}
        issues.append(as_dict(issue("SOR001", variant, pin.lineno, level="error", token=text, **span, **params)))
    issues.sort(key=lambda i: i["line"])
    return issues


def check_file_structured(path: Path) -> list[dict[str, Any]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error
    return _collect(tree, src.splitlines())


def check_file(path: Path) -> list[str]:
    return [f"{path}:{i['line']}: {i['message']}" for i in check_file_structured(path)]


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
