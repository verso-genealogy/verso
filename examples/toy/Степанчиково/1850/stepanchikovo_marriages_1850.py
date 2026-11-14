from corpus.statuses import ROSTANEV_EI_PEASANT_FEMALE, ROSTANEV_EI_PEASANT_MALE
from verso.ru.dsl import Month, RecordDefaults, marriage, marriage_month, marriage_records, person

# A toy book: the people, the days and the shelfmark are invented.
stepanchikovo_marriages_1850 = marriage_records(
    "ГА", "1", "2", "3", "Степанчиково", "Троицкая", 1850,
    *marriage_month(Month.JANUARY,
                    marriage(1, 21,
                             groom=person("Григорий", "Андреев", "Ежевикин"), groom_age=20, groom_marriage_num=1,
                             bride=person("Ольга", "Павлова", "Коровкина", residence="Капустино"), bride_age=18,
                             witness1=person("Алексей", "Семенов", "Фалалеев"),
                             witness2=person("Михаил", "Яковлев", "Видоплясов"))),
    *marriage_month(Month.OCTOBER,
                    marriage(2, 29,
                             groom=person("Тимофей", "Кузмин", "Коровкин"), groom_age=24, groom_marriage_num=1,
                             bride=person("Дарья", "Максимова", "Видоплясова"), bride_age=19,
                             witness1=person("Федор", "Тимофеев", "Ежевикин"),
                             witness2=person("Василий", "Григорьев", "Фалалеев"))),
    defaults=RecordDefaults(residence="Степанчиково", status_male=ROSTANEV_EI_PEASANT_MALE,
                            status_female=ROSTANEV_EI_PEASANT_FEMALE),
)
