from verso.ru.dsl import Month, RecordDefaults, marriage, marriage_month, marriage_records, person
from verso.ru.dsl.statuses import PEASANT_DAUGHTER_MAIDEN, PEASANT_FEMALE, PEASANT_MALE

# A synthetic book for the Verso tests (tests/verso_fixture.py): the people, the
# days, the parish, the record numbers, the sections and the album's windows are
# all invented; nothing in it is a real book's, and none of its villages or its
# archive is a real one.
manilovka_marriages_1900 = marriage_records(
    "ГАРО", "755", "473", "169", "Хлестаковка", "Вознесенская", 1900,
    *marriage_month(Month.FEBRUARY,
                    marriage(2, 9,
                             groom=person("Григорий", "Петров", "Справкин"), groom_age=20, groom_marriage_num=1,
                             bride=person("Евдокия", "Андреева", "Опытова", residence="Спесивая"), bride_age=18,
                             witness1=person("Николай", "Петров", "Черновиков"),
                             witness2=person("Иван", "Сергеев", "Пробин"),
                             witness3=person("Василий", "Егоров", "Списков"),
                             witness4=person("Петр", "Ильин", "Заметкин")),
                    ),
    *marriage_month(Month.APRIL,
                    marriage(8, 23, reviewed=False,
                             groom=person("Косма", "Ѳедоровъ", "Выпискинъ", residence="Лентяевка"), groom_age=21, groom_marriage_num=1,
                             bride=person("Марія", "Лукина", "Опискина"), bride_age=19,
                             witness1=person("Алексѣй", "Петровъ", "Образцовъ"),
                             witness2=person("Иларіонъ", "Лукинъ", "Опискинъ"),
                             witness3=person("Семенъ", last_name_orig="Справкинъ"),
                             witness4=person("Ѳедоръ", "Ивановъ", "Пробинъ")),
                    ),
    defaults=RecordDefaults(
        residence="Маниловка",
        status_male=PEASANT_MALE,
        status_female=PEASANT_FEMALE,
        status_bride=PEASANT_DAUGHTER_MAIDEN,
        status_groom=PEASANT_MALE
    ),
)
