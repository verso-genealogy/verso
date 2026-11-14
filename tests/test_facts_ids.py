"""A facts persona is named by its id in the records JSON (rule r1, `verso.core.records.ids`).

One id for `facts.jsonl`, the records export and a Verso link — and, unlike the
positional `<file>#<entry>` it replaced, one that no record inserted or held
elsewhere can move. On a scratch copy of the Verso fixture's village.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import village_fixture
from verso.ru.facts.model import AssertionSet, Relational
from verso.ru.pipeline.facts import consolidated_facts
from verso.core.pipeline.records import export_village

# A reviewed roll and burial (the fixture's are held), a list and a card: every kind
# the facts read.
EXTRA = '''\
from calendar import Month

from verso.ru.dsl import Gender, person
from verso.ru.dsl import CensusRole, census_records, household, member
from verso.ru.dsl import death, death_records
from verso.ru.dsl import Relationship, relative
from verso.ru.dsl import external_source_records, wwi_record
from verso.ru.dsl import listed_person, name_list_records

manilovka_census_1901 = census_records(
    "ГА Глуповской области", "5", "1", "20", "Маниловка", 1901,
    household("1",
              member(1, person("Петръ", "Ивановъ", "Примеровъ"), CensusRole.HEAD, age=45),
              member(2, person("Анна", "Петрова"), CensusRole.WIFE, ref_member=1, age=40)),
    household("2",
              member(1, person("Сергій", "Косьминъ", "Опискинъ"), CensusRole.HEAD, age=50),
              member(2, person("Марія"), CensusRole.DAUGHTER, ref_member=1, age=20)),
    household("3",
              member(1, person("Іоаннъ", "Петровъ", "Примеровъ"), CensusRole.HEAD, age=30)))
manilovka_deaths_1901 = death_records(
    "ГАРО", "1", "2", "3", "Хлестаковка", "Покровская", 1901,
    death(3, Gender.FEMALE, 9, 11, Month.MARCH, Month.MARCH, deceased=person("Ульяна", "Петрова"),
          relatives=[relative(person("Ѳедоръ", "Ивановъ", "Заметкинъ"), Relationship.HUSBAND)]))
manilovka_name_lists_1901 = name_list_records(
    "ГАТО", "1", "1", "1", "Маниловка", 1901, listed_person(1, person("Петръ", "Ивановъ")),
    document_type="Список")
manilovka_external_sources_1901 = external_source_records(
    "Маниловка", wwi_record(person("Василій"), source_url="https://gwar.mil.ru/heroes/chelovek_plen1/"))
'''
ROLL = "manilovka_extra_1901.py"
MARRIAGES_1899 = "1899/manilovka_marriages_1899.py"
# A wedding of 1899 for the fixture's January section, in front of its first.
INSERTED = '''                    marriage(30, 5,
                             groom=person("Павел", "Ильин", "Справкин"), groom_age=20,
                             bride=person("Ольга", "Петрова", "Пробникова"), bride_age=19),
'''


@pytest.fixture
def village(tmp_path: Path) -> Path:
    manilovka = village_fixture.root(tmp_path) / "Маниловка"
    (manilovka / "1901").mkdir()
    (manilovka / "1901" / ROLL).write_text(EXTRA, encoding="utf-8")
    return manilovka


def _facts(village: Path) -> AssertionSet:
    facts, _, _ = consolidated_facts(village)
    return facts


def _personas(facts: AssertionSet, source_file: str | None = None) -> list[str]:
    """Every persona the facts name — subjects and the others of a relation — in order."""
    out: list[str] = []
    for a in facts:
        if source_file is not None and a.cite.source_file != source_file:
            continue
        out.append(a.subject.id)
        if isinstance(a, Relational):
            out.append(a.other.id)
    return out


def _json_personas(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for d in doc.get("documents", ()):
            for run in d.get("pages", ()):
                for record in run["records"]:
                    found.update(p["id"] for p in record["persons"])
    return found


def test_every_persona_is_a_persona_of_the_records_json(village: Path, tmp_path: Path):
    facts = _facts(village)
    export_village(village, tmp_path / "records")
    named = set(_personas(facts))
    assert {a.cite.record_kind for a in facts} == {"birth", "marriage", "death", "census", "list",
                                                   "external"}
    assert named and all(p.startswith("r1:") for p in named)   # the parish is Хлестаковка
    assert named <= _json_personas(tmp_path / "records"), sorted(named - _json_personas(tmp_path / "records"))


def test_a_record_inserted_in_another_file_moves_no_persona(village: Path):
    """A wedding added to 1899 shifts every later wedding's place in the reading —
    the old id was that place — and none of the 1900 personas."""
    before = _facts(village)
    path = village / MARRIAGES_1899
    text = path.read_text(encoding="utf-8")
    anchor = "    *marriage_month(Month.JANUARY,\n"
    assert anchor in text
    path.write_text(text.replace(anchor, anchor + INSERTED), encoding="utf-8")
    after = _facts(village)

    weddings = "manilovka_marriages_1900.py"
    assert _personas(after, weddings) == _personas(before, weddings)
    places = [{a.cite.entry for a in facts if a.cite.source_file == weddings} for facts in (before, after)]
    assert places[1] == {e + 1 for e in places[0]}, "the insert must stand before them in the reading"


def test_a_household_held_back_moves_no_other_household(village: Path):
    """Holding двор 2 back (`reviewed=False`) takes it out of the reading, and двор 3's
    place with it; its persona stays."""
    before = _facts(village)
    path = village / "1901" / ROLL
    text = path.read_text(encoding="utf-8")
    held = 'ref_member=1, age=20)),'
    assert held in text
    path.write_text(text.replace(held, 'ref_member=1, age=20), reviewed=False),'), encoding="utf-8")
    after = _facts(village)

    def third(facts: AssertionSet) -> list[str]:
        return [p for p in _personas(facts, ROLL) if "/household/3/" in p]

    assert third(after) == third(before) == ["r1:Маниловка/5-1-20/1901/household/3/member1"] * len(third(before))
    assert not [p for p in _personas(after, ROLL) if "/household/2/" in p]
    entries = [{a.cite.entry for a in facts if "/household/3/" in a.subject.id} for facts in (before, after)]
    assert entries[1] == {e - 1 for e in entries[0]}, "the held двор must stand before it in the reading"
