from corpus.statuses import ROSTANEV_EI_PEASANT_FEMALE, ROSTANEV_EI_PEASANT_MALE
from verso.ru.dsl import (Gender, Month, RecordDefaults, Relationship, death, death_month, death_records,
                          person, relative)

# A toy book: the people, the days and the shelfmark are invented.
stepanchikovo_deaths_1850 = death_records(
    "ГА", "1", "2", "3", "Степанчиково", "Троицкая", 1850,
    *death_month(Month.MARCH,
                 death(1, Gender.MALE, 9, 11,
                       deceased=person("Семен", "Яковлев", "Видоплясов"), age=67),
                 death(2, Gender.FEMALE, 20, 22,
                       deceased=person("Агафья"), age=2,
                       relatives=[relative(person("Николай", "Ильин", "Фалалеев"), Relationship.FATHER)])),
    defaults=RecordDefaults(residence="Степанчиково", status_male=ROSTANEV_EI_PEASANT_MALE,
                            status_female=ROSTANEV_EI_PEASANT_FEMALE),
)
