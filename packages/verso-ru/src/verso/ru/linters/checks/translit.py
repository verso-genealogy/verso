"""The layers' linter over a layer's transliteration rules (`translit.tsv`, `verso.ru.naming.translit_layers`).

* **LEX008** (hard) — a rule the transliteration cannot use: a profile no profile is (`PROFILES`), a word that is not one
  Cyrillic word, an empty Latin spelling.
* **LEX009** (advice) — a rule that spells as the sum without it does: the profile, or a layer under it, already gives
  that Latin — it is redundant.
* **LEX010** — a Latin spelling with a character outside the Latin letters, the apostrophe, the space and the hyphen:
  hard for any profile but `ru-v1`, whose rules are the res_names' of old and stand as they were spelled (advice).
* **LEX002** (hard) — a key (profile, word) written twice in the file, as in the names tables.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from verso.ru.linters.checks.lexicon import Finding
from verso.ru.linters.issue import issue
from verso.ru.naming.translit_layers import FILE, Key, TranslitRule
from verso.ru.naming.transliteration import PROFILES, RU_V1

_WORD = re.compile("[\u0400-\u04ff]+(?:-[\u0400-\u04ff]+)?")  # one word of the Cyrillic block
_LATIN = re.compile("[A-Za-z' -]+")
_ERROR, _WARN = "error", "warn"


def lint_rules(rows: Sequence[tuple[int, TranslitRule]], *,
               below: Mapping[Key, TranslitRule] | None = None) -> list[Finding]:
    """The findings of one layer's rules (`rows`, as `read_rows` gives them), read over `below` — the rules of the layers
    under it, summed."""
    below = below or {}
    found: list[Finding] = []
    first: dict[Key, int] = {}
    for line, rule in rows:
        key = f"{rule.profile} {rule.word}"
        if rule.key in first:
            found.append(Finding(FILE, issue("LEX002", "duplicate", line, level=_ERROR, token=rule.word, key=key,
                                             first=first[rule.key])))
            continue
        first[rule.key] = line
        profile = PROFILES.get(rule.profile)
        if profile is None:
            found.append(Finding(FILE, issue("LEX008", "profile", line, level=_ERROR, token=rule.word, key=key,
                                             profile=rule.profile, known=", ".join(PROFILES))))
            continue
        if _WORD.fullmatch(rule.word) is None:
            found.append(Finding(FILE, issue("LEX008", "word", line, level=_ERROR, token=rule.word, key=key)))
            continue
        if rule.latin is None:
            if rule.key not in below:
                found.append(Finding(FILE, issue("LEX009", "removal", line, token=rule.word, key=key)))
            continue
        if not rule.latin:
            found.append(Finding(FILE, issue("LEX008", "empty", line, level=_ERROR, token=rule.word, key=key)))
            continue
        if _LATIN.fullmatch(rule.latin) is None:
            found.append(Finding(FILE, issue("LEX010", "latin", line, level=_WARN if profile is RU_V1 else _ERROR,
                                             token=rule.word, key=key, latin=rule.latin)))
        lower = below.get(rule.key)
        gives = lower.latin if lower is not None and lower.latin is not None else profile(rule.word)
        if gives == rule.latin:
            found.append(Finding(FILE, issue("LEX009", "redundant", line, token=rule.word, key=key, latin=rule.latin)))
    return found
