from verso.ru.dsl import CensusRole, census_records, household, member, page, person

# A synthetic roll for the Verso tests (tests/verso_fixture.py): everything in it —
# the people, their ages, the village and its archive — is invented.
census = census_records(
    "ГА Глуповской области", "10", "4", "4044", "Маниловка",
    1858,
    *page("16об-17",
          household("1",
                    member(1, person("Петръ", "Ивановъ", "Примеровъ"), CensusRole.HEAD, age=45, previous_age=37),
                    member(2, person("Анна", "Петрова"), CensusRole.WIFE, ref_member=1, age=40),
                    member(3, person("Іоаннъ"), CensusRole.SON, ref_member=1, age=12, previous_age=4)),
          household("2",
                    member(1, person("Сергій", "Косьминъ", "Опискинъ"), CensusRole.HEAD, age=50, previous_age=42),
                    member(2, person("Марія"), CensusRole.DAUGHTER, ref_member=1, age=20))),
    reviewed=False,
)
