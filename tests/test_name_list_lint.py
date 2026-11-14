from verso.ru.linters.checks.name_lists import check_file, check_file_structured

GOOD = '''
from verso.ru.dsl import listed_person, name_list_records, person
x = name_list_records(
    "ГАРО", "F", "I", "C", "Маниловка", 1917,
    listed_person(512, person("Домна", "Лукинична", "Телятникова"), age=66),
    document_type="Список избирателей",
)
'''

BAD_AGE = '''
from verso.ru.dsl import listed_person, name_list_records, person
x = name_list_records(
    "ГАРО", "F", "I", "C", "Маниловка", 1917,
    listed_person(1, person("Савва", "Фомич", "Телятников"), age=0),
    document_type="Список избирателей",
)
'''

BAD_DOCTYPE = '''
from verso.ru.dsl import listed_person, name_list_records, person
x = name_list_records(
    "ГАРО", "F", "I", "C", "Маниловка", 1917,
    listed_person(1, person("Савва", "Фомич", "Телятников"), age=44),
    document_type="",
)
'''

BAD_NEGATIVE_AGE = '''
from verso.ru.dsl import listed_person, name_list_records, person
x = name_list_records(
    "ГАРО", "F", "I", "C", "Маниловка", 1917,
    listed_person(1, person("Савва", "Фомич", "Телятников"), age=-5),
    document_type="Список избирателей",
)
'''


def _write(tmp_path, src):
    p = tmp_path / "manilovka_name_lists_1917.py"
    p.write_text(src, encoding="utf-8")
    return p


def test_good_has_no_findings(tmp_path):
    assert check_file(_write(tmp_path, GOOD)) == []


def test_nonpositive_age_flagged(tmp_path):
    out = check_file(_write(tmp_path, BAD_AGE))
    assert any("NLC001" in m for m in out)


def test_empty_document_type_flagged(tmp_path):
    out = check_file(_write(tmp_path, BAD_DOCTYPE))
    assert any("NLC001" in m for m in out)


def test_negative_age_flagged(tmp_path):
    out = check_file(_write(tmp_path, BAD_NEGATIVE_AGE))
    assert any("NLC001" in m for m in out)


def test_structured_output_shape(tmp_path):
    out = check_file_structured(_write(tmp_path, BAD_NEGATIVE_AGE))
    assert out
    for d in out:
        assert d["level"] == "error"
        assert "NLC001" in d["message"]
