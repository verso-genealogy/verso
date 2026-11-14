"""The linters that spoke Russian prose speak English too: PSA, RTV, ULC and IMP — every
finding of every sample — and the names table's NCSV, each in English with no Cyrillic but what
the DSL or the table wrote (its params, its token, the table's column names)."""
from __future__ import annotations

import re
from typing import Any

from tests.test_linter_issue import _before, _issues
from verso.core import i18n
from verso.ru.linters import names_csv

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_PROSE = ("PSA", "RTV", "ULC", "IMP")
_COLUMNS = ("«Имя-основа»", "«Имя»", "«Пол»", "М or Ж")


def _leaves(params: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for value in params.values():
        out += _leaves(value["params"]) if isinstance(value, dict) else [str(value)]
    return out


def _bare(text: str, values: list[str]) -> str:
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, "")
    return text


def test_every_variant_has_english():
    seen: set[str] = set()
    found: list[tuple[str, str]] = []
    with i18n.use("en"):
        for rel in sorted(_before()):
            for issue in _issues(rel):
                message = issue["message"]
                if not getattr(message, "code", "").startswith(_PROSE):
                    continue
                seen.add(f"{message.code}.{message.variant}")
                values = [*_leaves(message.params), *([message.token] if message.token else [])]
                if _CYRILLIC.search(_bare(str(message), values)):
                    found.append((rel, str(message)))
    assert found == []
    assert {k.split(".")[0] for k in seen} >= {"PSA001", "PSA002", "PSA003", "PSA004", "RTV001", "ULC001", "IMP001"}


def test_names_table_findings_in_english():
    rows = [{"Пол": "М", "Имя": "Иван", "Имя-основа": ""}, {"Пол": "Х", "Имя": "Петр", "Имя-основа": "Петр"},
            {"Пол": "М", "Имя": "Ян", "Имя-основа": "Иоанн"}, {"Пол": "М", "Имя": "", "Имя-основа": ""},
            {"Пол": "М", "Иван": "", "Имя": "Иван", "Имя-основа": ""}]
    with i18n.use("en"):
        english = names_csv.check_rows(rows)
    with i18n.use("ru"):
        russian = names_csv.check_rows(rows)
    assert [f.code for f in english] == [f.code for f in russian]
    for f in english:
        assert not _CYRILLIC.search(_bare(f.message, [*_COLUMNS, "'Х'", "'Иоанн'", "'Петр'"])), f.message
    assert any(_CYRILLIC.search(f.message) for f in russian if f.code in ("NCSV002", "NCSV004"))
