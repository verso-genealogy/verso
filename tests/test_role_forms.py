"""The roles a finding names: a table of forms per language in the catalog — `forms.role.<id>`
— never Russian words in the checks' code. Russian keeps three cases (who, whose, to whom) and
their capitals; English one form."""
from __future__ import annotations

import tomllib
from pathlib import Path

from verso.core import i18n
from verso.ru.linters.checks import status_words
from verso.ru.linters.checks.status_words import DAT, GEN, role_word, who

LOCALES = Path(status_words.__file__).parents[2] / "locales"
ROLES = ("father", "mother", "husband", "wife", "son", "daughter", "brother", "sister", "child",
         "newborn_male", "newborn_female", "deceased_male", "deceased_female", "groom", "bride",
         "godfather", "godmother", "surety", "witness", "relative", "household_member")


def _roles(lang: str) -> dict[str, dict[str, str]]:
    with (LOCALES / f"{lang}.toml").open("rb") as f:
        return tomllib.load(f)["forms"]["role"]


def test_role_forms_cover_every_role():
    table = _roles("ru")
    assert sorted(table) == sorted(ROLES)
    for role in ROLES:
        assert {"nom", "gen", "dat", "nom_capital", "gen_capital", "dat_capital"} <= set(table[role]), role


def test_english_has_no_cases():
    table = _roles("en")
    assert sorted(table) == sorted(ROLES)
    assert all(set(forms) == {"nom", "nom_capital"} for forms in table.values())
    with i18n.use("en"):
        assert (str(role_word("husband", GEN)), str(role_word("husband", DAT, capital=True))) == ("husband", "Husband")


def test_a_role_is_named_by_its_id():
    with i18n.use("ru"):
        assert (str(role_word("husband", GEN)), str(role_word("wife", DAT, capital=True))) == ("мужа", "Жене")
        assert str(who("household_member", None)) == "член двора"


def test_the_checks_hold_no_role_words():
    assert not hasattr(status_words, "ROLE_IDS")
