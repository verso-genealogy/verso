from verso.ru.dsl import (Month, RecordDefaults, Side, marriage, marriage_month, marriage_records,
                          person)
from verso.ru.dsl.statuses import PEASANT_DAUGHTER_MAIDEN, PEASANT_FEMALE, PEASANT_MALE

# A synthetic book for the Verso tests (tests/verso_fixture.py): the people, the
# days, the parish, the record numbers, the sections and the album's windows are
# all invented; nothing in it is a real book's, and none of its villages or its
# archive is a real one.
manilovka_marriages_1899 = marriage_records(
    "ГАРО", "384", "961", "387", "Хлестаковка", "Вознесенская", 1899,
    *marriage_month(Month.JANUARY,
                    marriage(4, 19,
                             groom=person("Павел", "Ильин", "Справкин"), groom_age=20, groom_marriage_num=1,
                             bride=person("Ольга", "Петрова", "Пробникова"), bride_age=19,
                             witness1=person("Сергей", "Ильин", "Справкин"),
                             witness2=person("Николай", "Лукин", "Опискин"),
                             witness3=person("Алексей", "Иванов", "Заметкин"),
                             witness4=person("Петр", "Андреев", "Выпискин")),
                    marriage(9, 27, reviewed=False,
                             groom=person("Ѳеодоръ", "Семеновъ", "Списковъ", residence="Спесивая"), groom_age=22, groom_marriage_num=1,
                             bride=person("Анна", "Петрова", "Черновикова"), bride_age=None, bride_marriage_num=1,
                             witness1=person("Иларіонъ", "Петровъ", "Образцовъ", residence="Спесивая"),
                             witness2=person("Семенъ", "", "Примеровъ", residence="Спесивая"),
                             witness3=person("Петръ", "Семеновъ", "Списковъ", residence="Спесивая", side=Side.BRIDE),
                             witness4=person("Андрей", "Ильинъ", "Опытовъ", residence="Спесивая", side=Side.BRIDE)),
                    ),
    defaults=RecordDefaults(
        residence="Маниловка",
        status_male=PEASANT_MALE,
        status_female=PEASANT_FEMALE,
        status_bride=PEASANT_DAUGHTER_MAIDEN,
        status_groom=PEASANT_MALE
    ),
)
