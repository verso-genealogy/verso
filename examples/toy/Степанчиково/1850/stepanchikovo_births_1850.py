from corpus.statuses import ROSTANEV_EI_PEASANT_FEMALE, ROSTANEV_EI_PEASANT_MALE
from verso.ru.dsl import Gender, Month, RecordDefaults, birth, birth_month, birth_records, person

# A toy book: the people, the days and the shelfmark are invented.
stepanchikovo_births_1850 = birth_records(
    "ГА", "1", "2", "3", "Степанчиково", "Троицкая", 1850,
    *birth_month(Month.JANUARY,
                 birth(1, Gender.MALE, 3, 4,
                       child=person("Иван"),
                       father=person("Петр", "Степанов", "Видоплясов"),
                       mother=person("Анна", "Фомина"),
                       god_parent1=person("Николай", "Ильин", "Фалалеев"),
                       god_parent2=person("Мария", "Егорова", "Ежевикина"))),
    *birth_month(Month.APRIL,
                 birth(1, Gender.FEMALE, 14, 16,
                       child=person("Прасковья"),
                       father=person("Николай", "Ильин", "Фалалеев"),
                       mother=person("Татьяна", "Сергеева"),
                       god_parent1=person("Петр", "Степанов", "Видоплясов"),
                       god_parent2=person("Евдокия", "Васильева", "Ежевикина", residence="Капустино"))),
    defaults=RecordDefaults(residence="Степанчиково", status_male=ROSTANEV_EI_PEASANT_MALE,
                            status_female=ROSTANEV_EI_PEASANT_FEMALE),
)
