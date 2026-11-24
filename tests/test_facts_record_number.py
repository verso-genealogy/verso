"""An entry its book left unnumbered is said «без номера» in every report — never «№none», never a bare «none».

The extractors write such an entry's `record_num` as "none" (`verso.ru.facts.extract.common`); a report names a
record by `verso.ru.facts.labels.record_number`, and no line of the library writes the number itself.
"""
from __future__ import annotations

import re
from pathlib import Path

import tomllib

from verso.core import i18n
from verso.ru.facts.labels import record_number
from verso.ru.facts.model import Citation
from verso.ru.messages import t

SOURCE = Path(__file__).resolve().parent.parent / "packages" / "verso-ru" / "src" / "verso" / "ru"


def _cite(number: str) -> Citation:
    return Citation(village="Горюхино", source_file="births_1850.py", record_kind="birth", record_num=number, entry=0)


def test_a_number_is_said_with_its_sign_and_none_as_unnumbered():
    assert record_number(_cite("7")) == "№7" and record_number(_cite("7"), sign=False) == "7"
    assert record_number(_cite("none")) == record_number(_cite("none"), sign=False) == str(t("cli.facts.unnumbered"))
    assert i18n.render(t("cli.facts.unnumbered"), "ru") == "без номера"
    assert i18n.render(t("cli.facts.unnumbered"), "en") == "unnumbered"


def test_no_line_of_the_library_writes_a_record_s_number_itself():
    """Each report once wrote «№{…record_num}» on its own and printed «№none» for an unnumbered entry."""
    written = re.compile(r"№\{[^}]*record_num")
    found = [f"{path.relative_to(SOURCE)}:{n}" for path in SOURCE.rglob("*.py")
             for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if written.search(line)]
    assert found == []


#: The templates that may write «№{number}», each with its reason.
SIGNED = {
    "cli.facts.lags.finding": "called by nothing since 0.1.45, kept until 0.2 (tests/test_catalog_ru.py)",
    "consolidation.reconcile.backing": "a list neighbour's number, an int: an unnumbered entry has no neighbours",
    "consolidation.reconcile.backing_by_name": "the same",
}


def _templates(tree: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict) and not ({"one", "other"} & set(value)):
            out |= _templates(value, f"{prefix}{key}.")
        else:
            out[prefix + key] = str(value)
    return out


def test_no_message_writes_the_sign_before_a_number_it_is_handed():
    """A template that writes «№{number}» prints «№none» when handed an unnumbered entry's number."""
    for path in (SOURCE / "locales").glob("*.toml"):
        signed = {key for key, text in _templates(tomllib.loads(path.read_text(encoding="utf-8"))).items()
                  if "№{number}" in text}
        assert signed == set(SIGNED), path.name
