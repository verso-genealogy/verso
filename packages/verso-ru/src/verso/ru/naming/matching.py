"""How the review page matches names: orthography aside (`match_key`), the sex a
field's value gives (`field_sex`) and a given name (`name_sex`), a given name's base
form (`name_base`). Verso's App takes them as its `Spelling` port.

Split out of `geni.review.names` before 0.1.0: the people index (`verso.ru.persons`) and the
stale-notes finder (`verso.ru.notes`) match by it, and the library imports nothing of the
App.
"""
from __future__ import annotations

import re

from verso.ru.gender import Gender
from verso.ru.naming.gender_inference import get_gender_from_name, get_gender_from_old_patronymic
from verso.ru.naming.names_registry import matching_base
from verso.ru.naming.orthography import modernize_orthography


_SEX = {Gender.MALE: "м", Gender.FEMALE: "ж"}


def match_key(text: str) -> str:
    return modernize_orthography(text).lower().replace("ё", "е")


def field_sex(field_name: str, modern: str) -> str:
    """«м»/«ж» a value of `field_name` in modern spelling gives — a given name or a
    patronymic by the names table, a surname by its ending — or «»."""
    if field_name == "name_orig":
        return _SEX.get(get_gender_from_name(modern), "")  # type: ignore[arg-type]
    if field_name == "patr_orig":
        return _SEX.get(get_gender_from_old_patronymic(modern), "")  # type: ignore[arg-type]
    low = modern.lower()
    if low.endswith("а") or low.endswith("ая"):
        return "ж"
    if re.search(r"[бвгджзклмнпрстфхцчшщ]$|[иыо]й$", low):
        return "м"
    return ""


def name_sex(name: str) -> str:
    """«м»/«ж» when the names table holds this given name in one sex only; «»
    for a name it holds in both («Фома»), does not know, or a blank one."""
    return field_sex("name_orig", modernize_orthography(name.strip()))


def name_base(modern: str) -> str:
    """The base form a given name in modern spelling is matched by («Иван» for
    «Иоанн»), by the names table — the name itself where it has none."""
    return matching_base(modern, get_gender_from_name(modern))
