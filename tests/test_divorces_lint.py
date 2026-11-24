"""DVC001: an act of divorce names its marriage as text, where the library reads a date as an `EventDate`.

Advisory: DSL v1 still takes the text (`DeprecationWarning`), and it goes in 0.2. Where the text is a date in a form
the library knows, the finding offers its replacement — `EventDate(1927, Month.FEBRUARY, 24)` in the text's place;
an `EventDate` (and `Month`) imported from `verso.ru.dsl` is the author's to add.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from verso.ru.linters import dsllint
from verso.ru.linters.checks.divorces import _collect


def _found(src: str) -> list[dict[str, object]]:
    return _collect(ast.parse(src), src)


def test_a_text_date_offers_its_event_date():
    src = 'divorce(49, 14, Month.JULY, husband=h, wife=w, marriage_date="24 февраля 1927")\n'
    [f] = _found(src)
    assert str(f["message"]).startswith("[DVC001] ")
    assert f["level"] == "warn" and f["line"] == 1
    fix = f["fix"]
    assert fix == {"type": "replace_kwarg", "old": '"24 февраля 1927"', "new": "EventDate(1927, Month.FEBRUARY, 24)",
                   "col": src.index('"24')}
    assert (f["col"], f["end_col"]) == (src.index('"24'), src.index('"24') + len('"24 февраля 1927"'))


@pytest.mark.parametrize("text, new", [
    ("февраль 1927", "EventDate(1927, Month.FEBRUARY)"),
    ("1915", "EventDate(1915)"),
    ("07.11.1915", "EventDate(1915, Month.NOVEMBER, 7)"),
])
def test_each_form_is_offered_as_written(text: str, new: str):
    [f] = _found(f'divorce(1, 3, Month.JULY, marriage_date="{text}")')
    assert f["fix"]["new"] == new  # type: ignore[index]


def test_a_text_that_is_no_known_date_is_said_and_offers_nothing():
    [f] = _found('divorce(1, 3, Month.JULY, marriage_date="в феврале 1927 г.")')
    assert "fix" not in f and "DVC001" in str(f["message"])


def test_a_text_written_in_its_place_is_found_too():
    src = 'divorce(1, 3, Month.JULY, h, w, 30, 27, "24 февраля 1927")'
    [f] = _found(src)
    assert "DVC001" in str(f["message"]) and "fix" not in f


@pytest.mark.parametrize("src", [
    "divorce(1, 3, Month.JULY, marriage_date=EventDate(1927, Month.FEBRUARY, 24))",
    "divorce(1, 3, Month.JULY, marriage_date=None)",
    "divorce(1, 3, Month.JULY)",
    'marriage(1, 3, Month.JULY, comment="24 февраля 1927")',
    'other(marriage_date="24 февраля 1927")',
])
def test_a_date_and_anything_else_are_quiet(src: str):
    assert _found(src) == []


def test_dsllint_runs_it_as_advisory(tmp_path: Path):
    assert next(lt for lt in dsllint.LINTERS if lt.name == "divorces").advisory
    path = tmp_path / "x_divorces_1927.py"
    path.write_text('from verso.ru.dsl import Month, divorce, divorce_records, person\n'
                    'd = divorce_records("ГА", "1", "2", "3", "Маниловка", "", 1927,\n'
                    '    divorce(1, 3, Month.JULY, husband=person("Иванъ"), wife=person("Анна"), '
                    'marriage_date="24 февраля 1927"))\n', encoding="utf-8")
    found = [i for r in dsllint.check_file_json(path) for i in r["issues"] if i["code"] == "DVC001"]
    assert len(found) == 1 and found[0]["level"] == "warn" and found[0]["fix"]["type"] == "replace_kwarg"
    assert json.dumps(found, ensure_ascii=False)
