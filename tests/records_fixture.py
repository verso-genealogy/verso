"""Every record kind of the DSL in one namespace, for the records v1 tests.

Built by the factories, as a DSL file builds them, with invented people under real
names of the tests' lexicon; the shelfmarks are invented too. Each record carries one
of the cases the codec must keep: a held and an on-Geni record, a лист met twice, a
christening, a godparent's father, sureties with sides, ages 5 / 5.0 / "15.5" / 0.5,
a cause "" that `page()` copied from `NOT_IN_DOCUMENT`, a confession list with a hidden
member and a typed status, a list with labels, three cards of three catalogs and an
alias of a record set.
"""
from __future__ import annotations

from calendar import Month
from typing import Any

from verso.ru.domain import Gender, RecordDefaults, page, person
from verso.ru.domain.cause_of_death import NOT_IN_DOCUMENT
from verso.ru.domain.causes_of_death import NATURAL
from verso.ru.domain.event_date import EventDate
from verso.ru.domain.side import Side
from verso.ru.domain.status import Status
from verso.ru.dsl.records.births import birth, birth_month, birth_records, christening
from verso.ru.dsl.records.census import CONFESSION_LIST, CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.dsl.records.divorces import divorce, divorce_records
from verso.ru.dsl.records.external_sources import (
    WwiDocumentType, WwiiDocumentType, criminal_record, external_source_records, wwi_record, wwii_record)
from verso.ru.dsl.records.marriages import marriage, marriage_records
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.relationship import Relationship, relative

PEASANT = Status("крестьянин", Gender.MALE)
PEASANT_WIFE = Status("крестьянская жена", Gender.FEMALE)


def namespace() -> dict[str, Any]:
    births = birth_records(
        "ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1900,
        *page("1", *birth_month(
            Month.JANUARY,
            birth(1, Gender.MALE, 3, 4, child=person("Иванъ"),
                  father=person("Петръ", "Ивановъ", "Сидоровъ", status=PEASANT),
                  mother=person("Марья", "Петрова"),
                  god_parent1=person("Василій", "Петровъ"),
                  relatives=[relative(person("Иванъ", "Петровъ", "Сидоровъ"), Relationship.FATHER,
                                      "восприемника №1")],
                  comment="строка с \r и «\"»"),
            birth(2, Gender.FEMALE, 5, 6, child=person("Анна"), father=person("Петръ"),
                  reviewed=False),
            birth(3, Gender.FEMALE, 7, 8, child=person("Марья"), father=person("Иванъ"),
                  reviewed=False))),
        *page("1об", christening(4, Gender.MALE, 9, Month.JANUARY, age=11, child=person("Петръ"),
                                 father=person("Иванъ"))),
        *page("1", birth("4а", Gender.MALE, 10, 11, b_month=Month.FEBRUARY, k_month=Month.FEBRUARY,
                         child=person("Василій"), father=person("Иванъ"))),
        defaults=RecordDefaults(residence="Маниловка", status_male=PEASANT, status_female="крестьянка",
                                status_mother=PEASANT_WIFE),
    )
    vars(births.records[2])["on_geni"] = True  # as `ratchet.admit` marks a listed record

    marriages = marriage_records(
        "ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1900,
        *page("2", marriage(1, 9, Month.JANUARY, groom=person("Иванъ", "Петровъ"),
                            bride=person("Анна", "Иванова"), groom_age="17 л 2 мес", bride_age=18,
                            witness1=person("Петръ", "Ивановъ", side=Side.GROOM),
                            witness2=person("Василій", "Петровъ", side=Side.BRIDE))),
    )

    deaths = death_records(
        "ЦГА", "47", "9", "755", "Хлестаковка", "Церковь", 1913,
        *page("3",
              death(1, Gender.MALE, 2, 4, Month.MARCH, Month.MARCH, deceased=person("Иванъ"), age=5,
                    cause_of_death=NOT_IN_DOCUMENT),
              death(2, Gender.FEMALE, 3, 5, Month.MARCH, Month.MARCH, deceased=person("Анна"), age=0.5,
                    cause_of_death=NATURAL),
              death(3, Gender.MALE, 4, 6, Month.MARCH, Month.MARCH, deceased=person("Петръ"),
                    age="15.5", relatives=[relative(person("Иванъ"), Relationship.FATHER)]),
              death(4, Gender.MALE, 5, 7, Month.MARCH, Month.MARCH, deceased=person("Василій"),
                    age=5.0, cause_of_death="горячка")),
        defaults=RecordDefaults(cause_of_death=NATURAL),
    )

    divorces = divorce_records(
        "ГАПО", "1605", "59", "59", "Заманиловка", "", 1923,
        divorce(1, 3, Month.JULY, husband=person("Иванъ", "Петровъ"), wife=person("Анна", "Иванова"),
                husband_age=24, wife_age=29, page="?"),
    )

    confessions = census_records(
        "ГАРО", "735", "265", "53", "Заманиловка", 1828,
        *page("80", household(
            "94",
            member(1, person("Иванъ", "Петровъ", status=PEASANT), CensusRole.HEAD, age=40),
            member(2, person("Марья", status=Status("крестьянка", Gender.FEMALE)), CensusRole.WIFE,
                   age=35),
            member(3, person("Петръ"), CensusRole.SON, ref_member=1, age="6 мес"),
            member(-1, person("Петръ"), CensusRole.FATHER, hidden=True))),
        **CONFESSION_LIST, record_month=Month.MARCH, archive_suffix="стр-80",
    )

    voters = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        *page("5", listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"), age=40),
              listed_person(2, person("Петръ", "Ивановъ", "Сидоровъ"))),
        document_type="Список избирателей", labels=["Other"],
    )

    cards = external_source_records(
        "Маниловка",
        wwi_record(person("Иванъ", "Петровъ"), source_url="https://gwar.mil.ru/heroes/chelovek_plen1/",
                   document_type=WwiDocumentType.POW_CARD, date=EventDate(1915, Month.MAY, 3)),
        wwii_record(person("Петръ", "Ивановъ"),
                    source_url="https://pamyat-naroda.ru/heroes/memorial-chelovek_donesenie2/",
                    document_type=WwiiDocumentType.POW_CARD, date=EventDate(1943, date_range="after")),
        criminal_record(person("Василій", "Петровъ"), original_text="судим",
                        source_url="https://viewer.rsl.ru/ru/rsl01001234567?page=12",
                        bibliography="Ведомости, вып. 1"),
    )

    return {"births": births, "marriages": marriages, "hlestakovka_deaths_1913": deaths,
            "divorces": divorces, "confessions": confessions, "voters": voters, "cards": cards,
            "zamanilovka_deaths_1913": deaths}
