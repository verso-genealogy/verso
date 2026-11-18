"""The people of the neighbouring years: the window, the clergy and the unproofread left out, the ceiling, the lines.

Every record here is invented (the village Маниловка); no name is a corpus's.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

import verso.ru.reading.people as people_module
from verso.ru.notes.stale_notes import reading_key
from verso.ru.reading.people import (CLERGY, MAX_PEOPLE_CHARS, PEOPLE_HEAD, WINDOW, Entry, Mention, PeopleList,
                                     mentions, people_list, people_text, render)

VILLAGE = "Маниловка"


def _person(given: str, patronymic: str | None = None, surname: str | None = None, *, role: str = "father",
            residence: str | None = None, status: str | None = None) -> dict[str, Any]:
    written = {"given": given, "patronymic": patronymic, "surname": surname, "residence": residence, "status": status}
    return {"role": role, "written": {k: v for k, v in written.items() if v}}


def _doc(year: int, *persons: dict[str, Any], review: str = "reviewed", residence: str = VILLAGE) -> tuple[str, dict[str, Any]]:
    return VILLAGE, {"written": {"year": year, "defaults": {"residence": residence, "status_male": "крестьянин"}},
                     "pages": [{"records": [{"review": review, "persons": list(persons)}]}]}


def _m(name: str, patronymic: str | None, surname: str | None, year: int, status: str | None = None) -> Mention:
    return Mention(name, patronymic, surname, status, year)


def test_window_skips_own_year() -> None:
    by_year = {y: [_m("Афанасій", None, "Тихонинъ", y)] for y in (1848, 1849, 1850, 1851, 1862)}
    pl = people_list(by_year, VILLAGE, 1850, 5)
    assert [e.years for e in pl.entries] == [(1848, 1849, 1851)]      # not 1850, not 1862 (outside ±5)
    assert pl.reach == 5 and all(1850 not in e.years for e in pl.entries)


def test_window_is_the_one_asked() -> None:
    by_year = {y: [_m("Афанасій", None, "Тихонинъ", y)] for y in range(1830, 1871)}
    assert people_list(by_year, VILLAGE, 1850, 2).entries[0].years == (1848, 1849, 1851, 1852)
    assert WINDOW == 10 and people_list(by_year, VILLAGE, 1850, WINDOW).entries[0].years[0] == 1840


def test_clergy_left_out() -> None:
    docs = [_doc(1849, _person("Афанасій", None, "Тихонинъ"), *[_person("Корнилій", role=r) for r in CLERGY])]
    found = mentions(docs)[VILLAGE][1849]
    assert [m.name for m in found] == ["Афанасій"]


def test_unreviewed_left_out() -> None:
    docs = [_doc(1849, _person("Афанасій"), review="reviewed"), _doc(1849, _person("Корнилій"), review="pending"),
            _doc(1849, _person("Лукіянъ"), review="")]
    assert [m.name for m in mentions(docs)[VILLAGE][1849]] == ["Афанасій"]


def test_residence_is_the_village_or_its_canonical() -> None:
    docs = [_doc(1849, _person("Афанасій", residence="Маниловка, село"), _person("Корнилій", residence="Заречье"))]
    places = {"Маниловка, село": VILLAGE}
    assert [m.name for m in mentions(docs, places)[VILLAGE][1849]] == ["Афанасій"]
    assert [m.name for m in mentions(docs, places, scope="parish")[VILLAGE][1849]] == ["Афанасій", "Корнилій"]


def test_status_only_when_written_and_not_the_default() -> None:
    father = {**_person("Афанасій", status="крестьянинъ"), "derived": {"gender": "male"}}
    docs = [_doc(1849, father,
                 {"role": "mother", "written": {"given": "Агафья", "status": "солдатка"}, "derived": {"gender": "female"}})]
    found = mentions(docs)[VILLAGE][1849]
    assert [(m.name, m.status) for m in found] == [("Афанасій", None), ("Агафья", "солдатка")]


def _crowd(year: int, n: int, tag: str) -> list[Mention]:
    return [_m(f"Имя{chr(0x430 + i % 26)}{i}{tag}", None, f"Фамилия{i}{tag}", year) for i in range(n)]


def test_ceiling_takes_year_pairs_whole() -> None:
    by_year = {y: _crowd(y, 40, str(y)) for y in (1849, 1851, 1848, 1852, 1847, 1853)}
    ceiling = len(render(people_list(by_year, VILLAGE, 1850, 2, max_chars=10**9))) + 1
    pl = people_list(by_year, VILLAGE, 1850, 5, max_chars=ceiling)
    assert pl.reach == 2                      # ±3 would not fit, so neither 1847 nor 1853 came in alone
    assert {y for e in pl.entries for y in e.years} == {1848, 1849, 1851, 1852}
    tiny = people_list(by_year, VILLAGE, 1850, 5, max_chars=1)
    assert tiny.reach == 1 and {y for e in tiny.entries for y in e.years} == {1849, 1851}   # ±1 is in, however long
    assert MAX_PEOPLE_CHARS == 34_000


def test_render_lines() -> None:
    by_year = {1848: [_m("Флоръ", "Григорьевъ", "Мечтаевъ", 1848), _m("Марья", "Иванова", "Мечтаева", 1848),
                      _m("Агафья", "Васильева", None, 1848, "солдатка")],
               1852: [_m("Флоръ", "Григорьевъ", "Мечтаевъ", 1852), _m("Антонъ", None, "Азбукинъ", 1852)]}
    assert render(people_list(by_year, VILLAGE, 1850, 5)) == (
        "Азбукинъ: Антонъ 52\n"
        "Мечтаевъ: Марья Иванова 48; Флоръ Григорьевъ 48,52\n"
        "—: Агафья Васильева 48 (солдатка)")


def test_text_is_the_head_and_the_list() -> None:
    pl = PeopleList(VILLAGE, 1850, 5, 3, (Entry("Флоръ", None, "Мечтаевъ", None, (1848,)),))
    assert people_text(pl) == PEOPLE_HEAD.format(span="3 из ±5") + "\nМечтаевъ: Флоръ 48"
    assert people_text(PeopleList(VILLAGE, 1850, 5, 5, pl.entries)).startswith(PEOPLE_HEAD.format(span="5"))


@pytest.mark.parametrize("word", ["Ѳедоръ", "Іосифъ", "Мечтаевъ", "Мечтаевъ Иванъ", "ѵжица", "Ёлкинъ", "Ѯеновъ", "Ъ", "", "Ө"])
def test_key_agrees_with_the_notes(word: str) -> None:
    assert people_module._key(word) == reading_key(word)


def test_only_the_standard_library() -> None:
    tree = ast.parse(Path(people_module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and not getattr(node, "level", 0):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            assert all(m.split(".")[0] in sys.stdlib_module_names for m in mods), mods
