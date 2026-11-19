"""verso-ru's commands speak the interface's language: a report of `verso facts` reads in English
under English with no Cyrillic but what the records wrote, and what a command writes into a file the
corpus keeps does not follow the interface (rule 9)."""
from __future__ import annotations

import re
import tempfile
from calendar import Month
from pathlib import Path

from verso.core import i18n, workspace
from verso.ru.cli.facts import format_lags, format_wedding_ages
from verso.ru.cli.names import main as names_main
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.dsl.records.marriages import marriage
from verso.ru.facts.checks.lags import baptism_lags, burial_lags
from verso.ru.facts.checks.wedding_ages import wedding_age_findings
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import AssertionSet
from verso.ru.gender import Gender
from verso.ru.naming.names_table import COLUMNS

LEGACY_NAMES = Path(__file__).resolve().parent / "fixtures" / "legacy-names"

_CYRILLIC = re.compile(r"[А-Яа-яЁёѢѣІіѲѳѴѵ]")
_VILLAGE = "Тестовка"


def english_but(text: str, *values: str) -> str:
    """What of `text` is Cyrillic once the records' own values are taken out."""
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, "")
    return "".join(_CYRILLIC.findall(text))


def test_lags_report_speaks_english():
    births = AssertionSet(facts_from_births(
        [(birth(1, Gender.MALE, 3, 2, Month.MAY, Month.JUNE, year=1850, child=person("Иван"),
               father=person("Петр", "Иванов")), "b.py")], village=_VILLAGE)).believed()
    deaths = AssertionSet(facts_from_deaths(
        [(death(2, Gender.MALE, 3, 20, Month.MARCH, Month.MARCH, year=1850, deceased=person("Иван")),
          "d.py")], village=_VILLAGE)).believed()
    with i18n.use("en"):
        text = format_lags(baptism_lags(births).findings, "baptism-lag") + format_lags(burial_lags(deaths).findings, "burial-lag")
    assert english_but(text, "Иван", "Петр", "Иванов", _VILLAGE) == ""


def test_wedding_ages_report_speaks_english():
    rec = marriage(1, 20, Month.OCTOBER, person("Иван", "Петров"), person("Анна", "Ильина"),
                   groom_age=15, bride_age=40)
    rec.year = 1850
    facts = AssertionSet(facts_from_marriages([(rec, "m.py")], village=_VILLAGE)).believed()
    with i18n.use("en"):
        text = format_wedding_ages(wedding_age_findings(facts).findings)
    assert "groom «15»" in text
    assert english_but(text, "Иван", "Петров", "Анна", "Ильина", _VILLAGE) == ""


def _names_add(lang: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp, workspace.use(LEGACY_NAMES):   # `--path` is the old tables' add
        path = Path(tmp) / "names.csv"
        path.write_text(",".join(COLUMNS) + "\nМ,Абрам,,,,,,,,,\n", encoding="utf-8")
        with i18n.use(lang):
            assert names_main(["add", "--path", str(path), "--gender", "М", "--name", "Ефим"]) == 0
        return path.read_bytes()


def test_names_add_writes_the_same_row_in_either_language():
    assert _names_add("en") == _names_add("ru")
