from corpus.statuses import ROSTANEV_EI_PEASANT_FEMALE, ROSTANEV_EI_PEASANT_MALE
from verso.ru.dsl import CensusRole, RecordDefaults, census_records, household, member, person

# A toy roll: one двор of the 10th revision; the people and their ages are invented.
census = census_records(
    "ГА", "1", "5", "8", "Степанчиково", 1858,
    household("1",
              member(1, person("Петр", "Степанов", "Видоплясов"), CensusRole.HEAD, age=33, previous_age=26),
              member(2, person("Анна", "Фомина"), CensusRole.WIFE, ref_member=1, age=30),
              member(3, person("Иван"), CensusRole.SON, ref_member=1, age=8),
              member(4, person("Ирина"), CensusRole.DAUGHTER, ref_member=1, age=5)),
    defaults=RecordDefaults(status_male=ROSTANEV_EI_PEASANT_MALE, status_female=ROSTANEV_EI_PEASANT_FEMALE),
)
