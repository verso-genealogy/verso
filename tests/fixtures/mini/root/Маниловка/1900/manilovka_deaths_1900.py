from verso.ru.dsl import (Gender, Month, RecordDefaults, Relationship, death, death_month,
                          death_records, person, relative)
from verso.ru.dsl.statuses import PEASANT_FEMALE, PEASANT_MALE

# A synthetic book for the Verso tests (tests/verso_fixture.py): the people, the
# days, the parish, the record numbers, the sections and the album's windows are
# all invented; nothing in it is a real book's, and none of its villages or its
# archive is a real one.
manilovka_deaths_1900 = death_records(
    "ГАРО", "755", "473", "169", "Хлестаковка", "Вознесенская", 1900,
    *death_month(Month.FEBRUARY,
                 death(3, Gender.FEMALE, 9, 11, reviewed=False,
                       deceased=person("Ульяна", "Петрова"), age=None,
                       relatives=[relative(person("Ѳедоръ", "Ивановъ", "Заметкинъ"), Relationship.HUSBAND)],
                       comment="возраст не записан"),
                 ),
    *death_month(Month.APRIL,
                 death(7, Gender.MALE, 14, 16, reviewed=False,
                       deceased=person("Лука", "Савельевъ", "Опискинъ"), age=64),
                 ),
    *death_month(Month.DECEMBER,
                 death(21, Gender.MALE, 5, 7, reviewed=False,
                       deceased=person("Іосифъ"), age="1 мес",
                       relatives=[relative(person("Ѳедоръ", "Кузьминъ", "Справкинъ"), Relationship.FATHER)]),
                 ),
    defaults=RecordDefaults(
        residence="Маниловка",
        status_male=PEASANT_MALE,
        status_female=PEASANT_FEMALE,
    ),
)
