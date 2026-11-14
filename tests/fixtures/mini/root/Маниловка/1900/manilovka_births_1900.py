from verso.ru.dsl import Gender, Month, RecordDefaults, birth, birth_month, birth_records, person
from verso.ru.dsl.statuses import MAIDEN, PEASANT_FEMALE, PEASANT_MALE, PEASANT_WIFE

# A synthetic book for the Verso tests (tests/verso_fixture.py): the people, the
# days, the parish, the record numbers, the sections and the album's windows are
# all invented; nothing in it is a real book's, and none of its villages or its
# archive is a real one.
manilovka_births_1900 = birth_records(
    "ГАРО", "755", "473", "169", "Хлестаковка", "Вознесенская", 1900,
    *birth_month(Month.JANUARY,
                 birth(2, Gender.MALE, 12, 13, reviewed=False,
                       child=person("Тимоѳей"),
                       father=person("Іоаннъ", "Семеновъ", "Примеровъ", residence="Хлестаково"),
                       mother=person("Пелагія", "Ѳедорова"),
                       god_parent1=person("Никифоръ", "Андреевъ", "Образцовъ"),
                       god_parent2=person("Ѳекла", "Семенова", "Опытова", residence="Спесивая")),
                 ),
    *birth_month(Month.FEBRUARY,
                 birth(5, Gender.FEMALE, 5, 6,
                       child=person("Агафья"),
                       father=person("Павел", "Николаев", "Пробин"),
                       mother=person("Анна", "Петрова"),
                       god_parent1=person("Николай", "Николаев", "Пробин"),
                       god_parent2=person("Марія", "Павлова", "Пробина")),
                 birth(5, Gender.MALE, 10, 11, reviewed=False,
                       child=person("Ѳеодоръ"),
                       father=person("Димитрій", "Лукинъ", "Черновиковъ"),
                       mother=person("Евдокія", "Павлова"),
                       god_parent1=person("Семенъ", "Лукинъ", "Списковъ"),
                       god_parent2=person("Ирина", "Димитріева", "Черновикова")),
                 birth(9, Gender.FEMALE, 20, 21, reviewed=False,
                       child=person("Агафія"),
                       father=person("Андрей", "Никитинъ", "Выпискинъ"),
                       mother=person("Марѳа", "Яковлева"),
                       god_parent1=person("Петръ", "Никитинъ", "Выпискинъ"),
                       god_parent2=person("Ксенія", "Яковлева", "Пробникова", residence="Нежданная", status=MAIDEN)),
                 ),
    *birth_month(Month.MARCH,
                 birth(8, Gender.MALE, 3, 5, reviewed=False,
                       child=person("Стефанъ"),
                       father=person("Михаилъ", "Ильинъ", "Опискинъ"),
                       mother=person("Анна", "Сергѣева"),
                       god_parent1=person("Сергій", "Ильинъ", "Опискинъ"),
                       god_parent2=person("Марія", "Сергѣева", "Заметкина", residence="Скупка")),
                 ),
    defaults=RecordDefaults(
        residence="Маниловка",
        status_male=PEASANT_MALE,
        status_female=PEASANT_FEMALE,
        status_mother=PEASANT_WIFE,
    ),
)
