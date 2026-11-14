"""`verso.ru.dsl.notes`: the `#` blocks of a DSL file, each bound to the file, a record, an
argument, a field or a run of records — read off the text, the file never run."""
from __future__ import annotations

import textwrap

from verso.ru.dsl.notes import Anchor, AnchorKind, Note, extract_notes, is_code

HEAD = '''\
from verso.ru.dsl import Gender, Month, birth, birth_month, birth_records, page, person
'''


def notes(body: str) -> list[Note]:
    return extract_notes(HEAD + textwrap.dedent(body))


def anchors(body: str) -> dict[str, Anchor]:
    """Each note's anchor by its first line of text."""
    return {n["text"].splitlines()[0]: n["anchor"] for n in notes(body)}


def at(to: AnchorKind, record: int | None = None, end: int | None = None, arg: str | None = None) -> Anchor:
    return {"to": to, "record": record, "end": end, "arg": arg}


BOOK = '''\
# Метрическая книга села Заречье за 1871 г.
# Читано целиком.

zarechye_births_1871 = birth_records(
    "ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
    *page("10",
          *birth_month(Month.MAY,
                       # Первый ребёнок Кузьмы Прохорова.
                       birth(1, Gender.MALE, 3, 4,
                             child=person("Аверкий"),
                             # Отец — отставной солдат.
                             father=person("Кузьма", "Прохоров"),
                             mother=person("Ульяна", "Савельева")),  # в девичестве Лыкова
                       birth(2, Gender.FEMALE, 5, 6,
                             child=person("Фекла"),
                             father=person("Тит", "Ермилов")),
                       ),
          ),
)
'''


def test_header_is_file() -> None:
    first = notes(BOOK)[0]
    assert first["anchor"] == at("file")
    assert first["text"] == "Метрическая книга села Заречье за 1871 г.\nЧитано целиком."
    assert first["lines"] == (2, 3)


def test_block_above_record_anchors_record() -> None:
    assert anchors(BOOK)["Первый ребёнок Кузьмы Прохорова."] == at("record", 0)


def test_inline_comment_is_field() -> None:
    assert anchors(BOOK)["в девичестве Лыкова"] == at("field", 0, arg="mother")


def test_inline_comment_on_the_line_a_call_opens_is_the_record() -> None:
    a = anchors('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(7, Gender.MALE, 1, 2,  # близнецы
                  child=person("Лука")),
        )
        ''')
    assert a["близнецы"] == at("record", 0)


def test_trailing_comment_on_a_line_of_two_records_is_manual() -> None:
    found = notes('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(1, Gender.MALE, 1, 2, child=person("Лука")), birth(2, Gender.MALE, 3, 4, child=person("Ерема")),  # twins: second
            # про третью
            birth(3, Gender.MALE, 5, 6, child=person("Пров")),  # один на строке
        )
        ''')
    by_text = {n["text"]: n["anchor"] for n in found}
    assert by_text["twins: second"] == at("manual")
    assert by_text["про третью"] == at("record", 2)
    assert by_text["один на строке"] == at("record", 2)


def test_comment_inside_call_is_argument() -> None:
    assert anchors(BOOK)["Отец — отставной солдат."] == at("argument", 0, arg="father")


def test_comment_inside_a_household_is_the_members_role() -> None:
    a = anchors('''\
        from verso.ru.dsl import CensusRole, census_records, household, member
        roll = census_records("ГАХО", "4", "5", "6", "Заречье", 1858,
            household("12",
                      member(1, person("Агафон"), CensusRole.HEAD, age=40),
                      # Вторая жена; первая умерла до 1850 г.
                      member(2, person("Агния"), CensusRole.WIFE, ref_member=1, age=31),
                      member(-1, person("Сидор"), CensusRole.FATHER, hidden=True),  # восстановлен
                      ),
        )
        ''')
    assert a["Вторая жена; первая умерла до 1850 г."] == at("argument", 0, arg="member2")
    assert a["восстановлен"] == at("field", 0, arg="member-1")


def test_comment_inside_a_list_of_relatives_is_the_relatives_place() -> None:
    a = anchors('''\
        from verso.ru.dsl import Relationship, death, death_records, relative
        d = death_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            death(4, Gender.MALE, 2, 3, deceased=person("Авдей"),
                  relatives=[relative(person("Ирина"), Relationship.WIFE),
                             # сын от первого брака
                             relative(person("Ефрем"), Relationship.SON)]),
        )
        ''')
    assert a["сын от первого брака"] == at("argument", 0, arg="relative2")


def test_comment_after_the_last_argument_is_the_record() -> None:
    a = anchors('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(7, Gender.MALE, 1, 2,
                  child=person("Лука"),
                  # запись приписана позже
                  ),
        )
        ''')
    assert a["запись приписана позже"] == at("record", 0)


GROUPS = '''\
from verso.ru.dsl import listed_person, name_list_records
voters = name_list_records("ГАХО", "7", "8", "9", "Заречье", 1917,
    listed_person(1, person("Агей", "Карпов", "Дятлов")),
    # Дятловы (№ 2–4)
    listed_person(2, person("Савва", "Агеев", "Дятлов")),
    listed_person(3, person("Марфа", "Ильина", "Дятлова")),
    listed_person(4, person("Фома", "Саввин", "Дятлов")),
    # Жмуркины 5-6
    listed_person(5, person("Герасим", "Жмуркин")),
    listed_person(6, person("Анна", "Жмуркина")),
    listed_person(7, person("Елена", "Пчелина")),
    # Пчелины (№ 40–41): номер не тот, это не заголовок записи ниже
    listed_person(8, person("Ефим", "Пчелин")),
)
'''


def test_group_heading_range() -> None:
    a = anchors(GROUPS)
    assert a["Дятловы (№ 2–4)"] == at("range", 1, 3)
    assert a["Жмуркины 5-6"] == at("range", 4, 5)
    # A range that does not hold the next record's number is no heading of it.
    assert a["Пчелины (№ 40–41): номер не тот, это не заголовок записи ниже"] == at("record", 7)


def test_commented_out_code_is_not_a_note() -> None:
    texts = [n["text"] for n in notes('''\
        # birth(9, Gender.MALE, 1, 2, child=person("Лука")),
        # if __name__ == "__main__":
        #     main()

        # Фроловы (Ивановы)
        # - Петров
        # TODO

        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(1, Gender.MALE, 1, 2, child=person("Лука")),  # type: ignore[reportUnknownArgumentType]
        )
        ''')]
    assert texts == ["Фроловы (Ивановы)\n- Петров\nTODO"]


def test_prose_that_parses_is_a_note_not_code() -> None:
    for prose in ("Восприемник: Петровъ", "TODO: recheck", "Итого: 12", "Иван = Пётр"):
        assert not is_code(prose)
        [note] = notes(f'''\
            b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
                # {prose}
                birth(1, Gender.MALE, 1, 2, child=person("Лука")),
            )
            ''')
        assert note["text"] == prose
        assert note["anchor"] == at("record", 0)


def test_code_stays_code() -> None:
    assert is_code('birth(1, person("Тест"))')
    assert is_code('from verso.ru.dsl import birth')
    assert is_code('def f():\n    pass')
    assert is_code('rows.append(1)')


def test_is_code_tells_code_from_prose() -> None:
    assert is_code('x = birth(1, Gender.MALE, 1, 2)')
    assert is_code('import os')
    assert not is_code('Фроловы (Ивановы)')
    assert not is_code('- Петров')
    assert not is_code('см. л. 12 об.')


def test_trailing_block_after_last_record_is_file_not_record() -> None:
    a = anchors(BOOK + '''
# Конец книги: часть вторая не сохранилась.
''')
    assert a["Конец книги: часть вторая не сохранилась."] == at("file")
    inside = anchors('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(1, Gender.MALE, 1, 2, child=person("Лука")),
            # дальше листы утрачены
            reviewed=False,
        )
        ''')
    assert inside["дальше листы утрачены"] == at("file")


def test_block_between_pages_is_not_bound_to_previous_record() -> None:
    a = anchors('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            *page("10",
                  birth(1, Gender.MALE, 1, 2, child=person("Лука")),
                  # низ листа оборван
                  ),
            # Лист 11 подклеен из другого дела.
            *page("11",
                  birth(2, Gender.FEMALE, 3, 4, child=person("Дарья")),
                  birth(3, Gender.MALE, 3, 4, child=person("Савва")),
                  ),
        )
        ''')
    assert a["Лист 11 подклеен из другого дела."] == at("range", 1, 2, arg="page")
    # At the end of a leaf, with more to come: neither the record above nor the one below.
    assert a["низ листа оборван"] == at("file")


def test_blank_line_breaks_a_block() -> None:
    found = notes('''\
        # шапка

        # вторая заметка шапки
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            # про запись, но через пустую строку

            birth(1, Gender.MALE, 1, 2, child=person("Лука")),
        )
        ''')
    assert [n["text"] for n in found] == ["шапка", "вторая заметка шапки", "про запись, но через пустую строку"]
    assert found[2]["anchor"] == at("file")


def test_no_comments_gives_no_notes() -> None:
    assert notes('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(1, Gender.MALE, 1, 2, child=person("Лука")),
        )
        ''') == []
    assert extract_notes("") == []


def test_note_text_keeps_markdown() -> None:
    [note] = notes('''\
        # **Главное:** два рода.
        #
        # - Дятловы:
        #   - Савва
        #
        #Без пробела.
        x = 1
        ''')
    assert note["text"] == "**Главное:** два рода.\n\n- Дятловы:\n  - Савва\n\nБез пробела."


def test_ordinals_count_every_record_call_in_source_order() -> None:
    """The records of every set, in the file's order — a christening, a divorce and a card
    are records too — as the records export counts them."""
    a = anchors('''\
        from verso.ru.dsl import christening, marriage, marriage_records
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(1, Gender.MALE, 1, 2, child=person("Лука")),
            christening(2, Gender.FEMALE, 3, child=person("Дарья")),
        )
        m = marriage_records("ГАХО", "1", "2", "4", "Заречье", "Троицкая", 1871,
            # венчание вдовца
            marriage(1, 5, groom=person("Тит"), bride=person("Анна")),
        )
        ''')
    assert a["венчание вдовца"] == at("record", 2)


def test_a_file_that_does_not_parse_has_no_notes() -> None:
    assert extract_notes("# заметка\nb = birth_records(\n") == []


def test_block_not_in_the_records_column_or_not_adjacent_is_file() -> None:
    a = anchors('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            *page("10",
                  birth(1, Gender.MALE, 1, 2, child=person("Лука")),
            # о листе вообще, не о записи
                  birth(2, Gender.MALE, 1, 2, child=person("Ерема")),
                  # через пустую строку

                  birth(3, Gender.MALE, 1, 2, child=person("Пров")),
                  # в колонке записи
                  birth(4, Gender.MALE, 1, 2, child=person("Нифонт")),
                  ),
        )
        ''')
    assert a["о листе вообще, не о записи"] == at("file")
    assert a["через пустую строку"] == at("file")
    assert a["в колонке записи"] == at("record", 3)


def test_block_above_the_first_wrapper_is_file_above_a_later_one_or_a_book_range() -> None:
    a = anchors('''\
        from verso.ru.dsl import book, marriage, marriage_month, marriage_records
        m = marriage_records("ГАХО", "1", "2", "4", "Заречье", "Троицкая", 1871,
            # книга целиком
            *page("3",
                  # январь
                  *marriage_month(Month.JANUARY,
                                  marriage(1, 5, groom=person("Тит"), bride=person("Анна"))),
                  # февраль
                  *marriage_month(Month.FEBRUARY,
                                  marriage(2, 6, groom=person("Пров"), bride=person("Олимпиада")),
                                  marriage(3, 8, groom=person("Ерема"), bride=person("Фекла"))),
                  ),
            # вторая книга
            *book("7", person("Нифонт", "Агеев"),
                  marriage(4, 9, groom=person("Савва"), bride=person("Дарья"))),
        )
        ''')
    assert a["книга целиком"] == at("file")
    assert a["январь"] == at("file")
    assert a["февраль"] == at("range", 1, 2, arg="marriage_month")
    assert a["вторая книга"] == at("range", 3, 3, arg="book")


def test_a_heading_range_stops_at_the_last_record_of_its_set() -> None:
    a = anchors('''\
        from verso.ru.dsl import marriage, marriage_records
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            # № 1–3: первая семья
            birth(1, Gender.MALE, 1, 2, child=person("Лука")),
            birth(2, Gender.MALE, 1, 2, child=person("Ерема")),
            birth(3, Gender.MALE, 1, 2, child=person("Пров")),
        )
        m = marriage_records("ГАХО", "1", "2", "4", "Заречье", "Троицкая", 1871,
            marriage(1, 5, groom=person("Тит"), bride=person("Анна")),
            marriage(2, 6, groom=person("Савва"), bride=person("Дарья")),
        )
        ''')
    assert a["№ 1–3: первая семья"] == at("range", 0, 2)


def test_a_range_of_leaves_or_years_is_no_heading() -> None:
    a = anchors('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            # писано на лл. 12–13
            birth(12, Gender.MALE, 1, 2, child=person("Лука")),
            birth(13, Gender.MALE, 1, 2, child=person("Ерема")),
            # жил тут 14-20, потом ушёл
            birth(14, Gender.MALE, 1, 2, child=person("Пров")),
            birth(15, Gender.MALE, 1, 2, child=person("Савва")),
            # Агеевы (14-20)
            birth(16, Gender.MALE, 1, 2, child=person("Тит")),
        )
        ''')
    assert a["писано на лл. 12–13"] == at("record", 0)
    # Unmarked, and not ending on a record's number: no heading.
    assert a["жил тут 14-20, потом ушёл"] == at("record", 2)
    # In brackets it is one, however far it runs.
    assert a["Агеевы (14-20)"] == at("range", 4, 4)


def test_records_that_cannot_be_counted_make_every_note_manual() -> None:
    spliced = notes('''\
        # шапка
        x = birth(9, Gender.MALE, 1, 2, child=person("Лука"))
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            birth(1, Gender.MALE, 1, 2, child=person("Ерема")),
            # о записи ниже
            x,
        )
        ''')
    assert [n["anchor"] for n in spliced] == [at("manual"), at("manual")]
    for body in ('''\
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            # о записях
            *[birth(n, Gender.MALE, 1, 2, child=person("Лука")) for n in (1, 2)],
        )
        ''', '''\
        from verso.ru.dsl import birth as rodilsya
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            # о записи
            rodilsya(1, Gender.MALE, 1, 2, child=person("Лука")),
        )
        ''', '''\
        def make(n):
            return birth(n, Gender.MALE, 1, 2, child=person("Лука"))
        b = birth_records("ГАХО", "1", "2", "3", "Заречье", "Троицкая", 1871,
            # о записи
            make(1),
        )
        '''):
        assert [n["anchor"]["to"] for n in notes(body)] == ["manual"]


def test_bom_shebang_and_coding_cookie_are_no_notes() -> None:
    found = extract_notes("\ufeff#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n# шапка\nx = 1\n")
    assert [(n["text"], n["lines"]) for n in found] == [("шапка", (3, 3))]


def test_a_directive_does_not_split_a_block() -> None:
    [note] = notes('''\
        # первая строка
        # fmt: off
        # вторая строка
        x = 1
        ''')
    assert note["text"] == "первая строка\nвторая строка"
    assert note["lines"] == (2, 4)


def test_item_roles_agree_with_the_records_vocabulary() -> None:
    from verso.ru.dsl.notes import _ITEM_ROLES  # pyright: ignore[reportPrivateUsage]
    from verso.ru.records.vocabulary import ITEM_ROLES
    assert _ITEM_ROLES.items() <= ITEM_ROLES.items()
