"""A cleric the book names with no village lives in the parish, not in the book's
default village — what the review page shows as the place it becomes."""
from verso.ru.domain import Gender, Person, RecordDefaults, person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.dsl.records.marriages import marriage, marriage_records

PARISH = ("ГАРО", "424", "187", "149", "Хлестаковка", "Вознесенская", 1866)
DEFAULTS = RecordDefaults(residence="Маниловка")


def place(p: Person | None) -> str | None:
    assert p is not None
    return p.residence


def test_birth_clergy_take_the_parish_parishioners_the_default():
    b = birth_records(*PARISH,
                      birth(1, Gender.MALE, 1, 2, child=person("Иванъ"),
                            father=person("Петръ", "Ивановъ", "Калачниковъ"), mother=person("Анна", "Петрова"),
                            priest=person("Николай", "Ивановъ"), sexton=person("Петръ", "Сидоровъ")),
                      defaults=DEFAULTS).records[0]
    assert place(b.father) == "Маниловка"
    assert place(b.priest) == "Хлестаковка"
    assert place(b.sexton) == "Хлестаковка"


def test_a_written_village_stands():
    b = birth_records(*PARISH,
                      birth(1, Gender.MALE, 1, 2, child=person("Иванъ"),
                            priest=person("Егоръ", "Ѳедоровъ", residence="Маниловка")),
                      defaults=DEFAULTS).records[0]
    assert place(b.priest) == "Маниловка"


def test_marriage_and_death_clergy_without_defaults():
    m = marriage_records(*PARISH,
                         marriage(1, 5, groom=person("Иванъ", "Петровъ"), bride=person("Анна", "Ивановна"),
                                  deacon=person("Николай", "Ивановъ"))).records[0]
    d = death_records(*PARISH,
                      death(1, Gender.MALE, 3, 5, deceased=person("Петръ", "Ивановъ"), age=60,
                            dyachok=person("Николай", "Ивановъ"))).records[0]
    assert place(m.deacon) == "Хлестаковка"
    assert place(d.dyachok) == "Хлестаковка"
