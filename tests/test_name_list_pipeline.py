from pathlib import Path
from verso.ru.dsl.kinds import _CATEGORY_ORDER, KINDS, _categorize  # pyright: ignore[reportPrivateUsage]
from verso.ru.dsl.records.name_lists import name_list_records, listed_person
from verso.ru.domain import person


def test_name_list_in_record_types():
    from verso.ru.dsl.records.name_lists import NameListRecords
    assert NameListRecords in [kind.set_type for kind in KINDS if kind.translated]


def test_categorize_name_list():
    r = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(1, person("Егор", "Иванович", "Телятников"), age=41),
        document_type="Список",
    )
    cat, is_other = _categorize(Path("manilovka_name_lists_1917.py"), r)
    assert cat == "name_list"
    assert is_other is False


def test_category_order_has_name_list():
    # _CATEGORY_ORDER holds (category, is_other) tuples, not bare names.
    assert ("name_list", False) in _CATEGORY_ORDER
