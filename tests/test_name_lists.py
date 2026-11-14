from verso.ru.domain import person
from verso.ru.gender import Gender
from verso.ru.dsl.records.name_lists import name_list_records, listed_person


def _sample():
    return name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(214, person("Фекла", "Тимоновна", "Телятникова"), age=58),
        listed_person(219, person("Нил", "Пахомович", "Телятников"), age=44),
        listed_person(251, person("Харитон", "Сидорович", "Телятников"), age=37,
                      comment="в списке 73 — ошибка"),
        document_type="Список избирателей на выборах в Учредительное собрание",
    )


def test_collection_fields():
    r = _sample()
    assert r.village == "Маниловка"
    assert r.year == 1917
    assert r.document_type.startswith("Список избирателей")
    assert len(r.entries) == 3
    assert r.labels == ["Other"]  # default


def test_entry_index_is_positional():
    r = _sample()
    assert [e.index for e in r.entries] == [1, 2, 3]


def test_entry_number_is_source_number():
    r = _sample()
    assert [e.number for e in r.entries] == [214, 219, 251]


def test_residence_defaults_to_village():
    r = _sample()
    assert all(e.person.residence == "Маниловка" for e in r.entries)


def test_gender_inferred_from_name():
    r = _sample()
    assert r.entries[0].person.gender == Gender.FEMALE  # Телятникова
    assert r.entries[1].person.gender == Gender.MALE     # Телятников


def test_birth_year_computed_from_age():
    r = _sample()
    assert r.entries[0].birth_year(r.year) == 1917 - 58   # 1859
    assert r.entries[2].birth_year(r.year) == 1917 - 37   # 1880 (corrected age)


def test_birth_year_none_for_nonnumeric_age():
    e = listed_person(1, person("Иван", "Иванович", "Телятников"), age="?")
    assert e.birth_year(1917) is None


def test_age_optional_defaults_to_none():
    e = listed_person(1, person("Иван", "Иванович", "Телятников"))
    assert e.age is None
    assert e.birth_year(1917) is None


def test_comment_preserved():
    r = _sample()
    assert r.entries[2].comment == "в списке 73 — ошибка"


# --- Лист locator: `page()` wraps entries exactly as it does census households ---

def test_page_sets_the_sheet_on_each_entry():
    from verso.ru.domain import page
    r = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        *page("7",
              listed_person(41, person("Нил", "Пахомов", "Бечков")),
              listed_person(42, person("Фекла", "Сидорова", "Бечкова"))),
        *page("8",
              listed_person(88, person("Анисья", "Игнатьева", "Гуйдышанова"))),
        document_type="Список избирателей",
    )
    assert [e.page for e in r.entries] == ["7", "7", "8"]


def test_page_does_not_overwrite_an_explicit_sheet():
    from verso.ru.domain import page
    wrapped = page("7", listed_person(41, person("Нил", "Пахомов", "Бечков"),
                                       page="6об"))
    assert wrapped[0].page == "6об"


def test_page_defaults_to_none_without_a_wrapper():
    e = listed_person(1, person("Иван", "Иванович", "Телятников"))
    assert e.page is None


# --- File-level `reviewed=`, mirroring `census_records(reviewed=...)` ---

def test_reviewed_defaults_to_true():
    r = _sample()
    assert all(e.reviewed for e in r.entries)


def test_file_level_reviewed_false_applies_to_every_entry():
    r = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        listed_person(41, person("Нил", "Пахомов", "Бечков")),
        listed_person(42, person("Фекла", "Сидорова", "Бечкова")),
        document_type="Список избирателей",
        reviewed=False,
    )
    assert [e.reviewed for e in r.entries] == [False, False]


def test_entry_reviewed_overrides_the_file_default():
    r = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        listed_person(41, person("Нил", "Пахомов", "Бечков"), reviewed=True),
        listed_person(42, person("Фекла", "Сидорова", "Бечкова")),
        document_type="Список избирателей",
        reviewed=False,
    )
    assert [e.reviewed for e in r.entries] == [True, False]


def test_page_reviewed_holds_back_a_whole_sheet():
    from verso.ru.domain import page
    r = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        *page("7",
              listed_person(41, person("Нил", "Пахомов", "Бечков")),
              listed_person(42, person("Фекла", "Сидорова", "Бечкова")),
              reviewed=False),
        listed_person(88, person("Анисья", "Игнатьева", "Гуйдышанова")),
        document_type="Список избирателей",
    )
    assert [e.reviewed for e in r.entries] == [False, False, True]
