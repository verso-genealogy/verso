"""`verso upgrade-dsl` — a DSL v0 file's imports through the facade, its `__main__` gone,
nothing else touched: no record's ratchet print moves."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.ru.cli import upgrade_dsl
from verso.ru.dsl.upgrade import UpgradeError, check_unchanged, upgrade


V0 = '''import os
from calendar import Month

from geni.domain import Gender, RecordDefaults, page, person
from geni.domain.statuses import (PEASANT_FEMALE, PEASANT_MALE,
                                  MANILOV_LK_PEASANT_MALE)
from geni.dsl.records.births import birth, birth_month, birth_records
from geni.exporters.csv_familio import BirthRecordsCsvFamilioExporter

# комментарий
x_births_1850 = birth_records(...)

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    x_births_1850.export(BirthRecordsCsvFamilioExporter())
'''
CORPUS = {"MANILOV_LK_PEASANT_MALE"}
RECORDS = '''x_births_1850 = birth_records(
    "ГАРО", "1", "2", "3", "Маниловка", "Покровская", 1850,
    *birth_month(Month.JANUARY,
                 birth(1, Gender.MALE, 3, 4, child=person("Іоаннъ"),
                       father=person("Петръ", status=PEASANT_MALE))),  # запись
)
'''


def test_v0_header_becomes_the_facade():
    assert upgrade(V0, CORPUS) == (
        "from corpus.statuses import MANILOV_LK_PEASANT_MALE\n"
        "from verso.ru.dsl import (Gender, Month, RecordDefaults, birth, birth_month, birth_records, page,\n"
        "                          person)\n"
        "from verso.ru.dsl.statuses import PEASANT_FEMALE, PEASANT_MALE\n"
        "\n# комментарий\nx_births_1850 = birth_records(...)\n")


def test_a_short_facade_import_stays_on_one_line():
    text = "from geni.domain import person\nfrom geni.dsl.records.deaths import death, death_records\n\nx = 1\n"
    assert upgrade(text, set()) == "from verso.ru.dsl import death, death_records, person\n\nx = 1\n"


def test_upgrade_is_idempotent():
    once = upgrade(V0, CORPUS)
    assert upgrade(once, CORPUS) == once


def test_comments_and_records_are_untouched():
    text = V0.replace("# комментарий\nx_births_1850 = birth_records(...)\n", "# комментарий\n" + RECORDS)
    after = upgrade(text, CORPUS)
    assert after.endswith("\n# комментарий\n" + RECORDS)


def test_the_catalogs_keep_their_constants_apart():
    text = ("from geni.domain.causes_of_death import FEVER, NOT_IN_DOCUMENT\n"
            "from geni.domain.marital_status import WIDOW\nfrom geni.domain import NOT_IN_DOCUMENT\n\nx = 1\n")
    assert upgrade(text, set()) == ("from verso.ru.dsl import NOT_IN_DOCUMENT\n"
                                    "from verso.ru.dsl.causes_of_death import FEVER, NOT_IN_DOCUMENT\n"
                                    "from verso.ru.dsl.marital_status import WIDOW\n\nx = 1\n")


@pytest.mark.parametrize("text, reason", [
    ("from geni.domain import person  # мой\n\nx = 1\n", "комментарий в шапке импортов"),
    ("from geni.domain import (person,  # мой\n                         page)\n\nx = 1\n",
     "комментарий в шапке импортов"),
    ("x = 1\nfrom geni.domain import person\n", "импорт после кода"),
    ("from geni.terraform.date import GeniDate\n\nx = 1\n", "geni.terraform.date — не модуль DSL"),
    ("import geni.domain\n\nx = 1\n", "import geni.domain — не форма DSL"),
    ("from geni.domain import person as p\n\nx = 1\n", "импорт с as"),
    ("from geni.domain import nobody\n\nx = 1\n", "nobody: этого имени нет в фасаде DSL"),
    ("from geni.domain.statuses import NOBODY_PEASANT\n\nx = 1\n", "NOBODY_PEASANT: этого имени нет в каталоге"),
    ('import os\n\nx = 1\n\nif __name__ == "__main__":\n    print(x)\n', "в __main__ не только экспорт CSV"),
])
def test_an_unusual_header_is_refused(text: str, reason: str):
    with pytest.raises(UpgradeError) as refused:
        upgrade(text, set())
    assert reason in str(refused.value)


def test_an_import_line_with_a_comment_is_refused():
    with pytest.raises(UpgradeError, match="комментарий в шапке импортов"):
        upgrade(V0.replace("from geni.domain import Gender, RecordDefaults, page, person",
                           "from geni.domain import Gender, RecordDefaults, page, person  # нужен"), CORPUS)


def test_os_stays_when_the_file_uses_it():
    text = V0.replace("x_births_1850 = birth_records(...)\n", "x_births_1850 = birth_records(...)\nHERE = os.sep\n")
    after = upgrade(text, CORPUS)
    assert after.startswith("import os\nfrom corpus.statuses import MANILOV_LK_PEASANT_MALE\n")
    assert "__main__" not in after
    assert "import os" not in upgrade(V0, CORPUS)


def test_check_unchanged_refuses_a_changed_record():
    before = V0.replace("x_births_1850 = birth_records(...)\n", RECORDS)
    after = upgrade(before, CORPUS)
    check_unchanged(before, after)
    with pytest.raises(UpgradeError, match="отпечатки храповика изменились бы"):
        check_unchanged(before, after.replace("birth(1, ", "birth(2, "))
    with pytest.raises(UpgradeError, match="изменилось что-то кроме шапки"):
        check_unchanged(before, after + "print(1)\n")      # no assignment: out of every print


def test_check_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    village = tmp_path / "V"
    (village / "1850").mkdir(parents=True)
    path = village / "1850" / "v_births_1850.py"
    path.write_text(V0.replace("MANILOV_LK_PEASANT_MALE", "MESHCHANIN").replace(
        "x_births_1850 = birth_records(...)\n", RECORDS), encoding="utf-8")
    before = path.read_bytes()
    assert upgrade_dsl.main(["--village", str(village), "--check"]) == 1
    assert path.read_bytes() == before
    assert capsys.readouterr().out.strip() == f"{village}: файлов 1, переписано 1, без изменений 0"
    assert upgrade_dsl.main(["--village", str(village)]) == 0
    assert path.read_bytes() != before
    assert upgrade_dsl.main(["--village", str(village), "--check"]) == 0
    assert capsys.readouterr().out.strip().endswith(f"{village}: файлов 1, переписано 0, без изменений 1")


def test_a_refused_file_stops_the_village(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    village = tmp_path / "V"
    (village / "1850").mkdir(parents=True)
    good, bad = village / "1850" / "a_births_1850.py", village / "1850" / "b_births_1850.py"
    good.write_text("from geni.domain import person\n\nx = 1\n", encoding="utf-8")
    bad.write_text("from geni.domain import person  # мой\n\nx = 1\n", encoding="utf-8")
    assert upgrade_dsl.main(["--village", str(village)]) == 2
    assert good.read_text(encoding="utf-8") == "from geni.domain import person\n\nx = 1\n"
    assert capsys.readouterr().err.strip() == f"{bad}: комментарий в шапке импортов: from geni.domain import person  # мой"


def test_the_hint_s_command_works_on_a_file_alone(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    # «verso upgrade-dsl <файл>» — what every DSL v0 message says to run.
    path = tmp_path / "V" / "1850" / "v_births_1850.py"
    path.parent.mkdir(parents=True)
    path.write_text("from geni.domain import person\n\nx = 1\n", encoding="utf-8")
    assert upgrade_dsl.main([str(path)]) == 0
    assert path.read_text(encoding="utf-8") == "from verso.ru.dsl import person\n\nx = 1\n"
    assert capsys.readouterr().out.strip() == "файлов 1, переписано 1, без изменений 0"


def test_a_main_with_an_else_is_refused():
    text = ('from geni.domain import person\n\nx = 1\n\nif __name__ == "__main__":\n'
            '    x.export(E())\nelse:\n    y = 2\n')
    with pytest.raises(UpgradeError, match="в __main__ не только экспорт CSV"):
        upgrade(text, set())


def test_check_unchanged_sees_an_if_that_only_names_main():
    before = 'x = 1\n\nif __name__ != "__main__":\n    y = 2\n'
    with pytest.raises(UpgradeError, match="изменилось что-то кроме шапки"):
        check_unchanged(before, "x = 1\n")


def test_a_docstring_stays_above_the_imports():
    text = '"""Док."""\nfrom geni.domain import person\n\nx = 1\n'
    assert upgrade(text, set()) == '"""Док."""\nfrom verso.ru.dsl import person\n\nx = 1\n'
