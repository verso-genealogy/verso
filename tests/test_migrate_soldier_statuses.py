"""`verso migrate-soldier-statuses`: a soldier's free-text status becomes its catalog constant, the
scribe's wording goes into `comment=` (bare, in modern spelling)."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.cli import migrate_soldier_statuses as mig
from verso.ru.domain.military_status import unplaced

HEAD = "from verso.ru.dsl import birth, birth_records, person\n\n"


def _call(src: str) -> str:
    """The migrated text without its import lines."""
    return mig.migrate_source(src)[0].split("\n\n", 1)[1]


def test_status_moves_to_comment():
    new, changes, left = mig.migrate_source(HEAD + 'x = person("Иванъ", status="запасный солдат")\n')
    assert new == ("from verso.ru.dsl import birth, birth_records, person\n"
                   "from verso.ru.dsl.statuses import SOLDIER\n\n"
                   'x = person("Иванъ", status=SOLDIER, comment="запасный солдат")\n')
    assert changes == [(3, "запасный солдат", "SOLDIER", None, "запасный солдат")]
    assert left == []


def test_the_wording_goes_in_modern_spelling():
    assert _call(HEAD + 'x = person("Иванъ", status="запасный рядовой")\n') == \
        'x = person("Иванъ", status=SOLDIER, comment="запасный рядовой")\n'
    assert _call(HEAD + 'x = person("Иванъ", status="отставной рядовой")\n') == \
        'x = person("Иванъ", status=RETIRED_SOLDIER, comment="отставной рядовой")\n'


def test_existing_comment_is_kept_and_prefixed():
    new, changes, _ = mig.migrate_source(
        HEAD + 'x = person("Иванъ", status="запасный солдат", comment="тож Ноздревъ")\n')
    assert new.endswith('x = person("Иванъ", status=SOLDIER, comment="запасный солдат; тож Ноздревъ")\n')
    assert changes[0].comment_before == "тож Ноздревъ"
    assert changes[0].comment_after == "запасный солдат; тож Ноздревъ"


def test_wording_already_in_comment_is_not_copied():
    src = HEAD + ('x = person("Иванъ", status="уволенный в запас армии",'
                  ' comment="«уволенный въ запасъ арміи деревни Заманиловки»")\n')
    new, changes, _ = mig.migrate_source(src)
    assert new.endswith('x = person("Иванъ", status=SOLDIER,'
                        ' comment="«уволенный въ запасъ арміи деревни Заманиловки»")\n')
    assert changes[0].comment_before == changes[0].comment_after


def test_a_quoted_military_wording_in_the_comment_holds_it():
    # The comment quotes the scribe's own words for the rank: the free-text status was the reader's
    # paraphrase, so only the status changes.
    src = HEAD + ('x = person("Иванъ", status="рядовой в бессрочном отпуске",'
                  ' comment="«уволенный во временный отпускъ рядовой»; Ноздревъ")\n')
    new, changes, _ = mig.migrate_source(src)
    assert new.endswith('x = person("Иванъ", status=SOLDIER,'
                        ' comment="«уволенный во временный отпускъ рядовой»; Ноздревъ")\n')
    assert changes[0].comment_before == changes[0].comment_after


def test_a_quoted_civil_wording_does_not_hold_it():
    src = HEAD + 'x = person("Иванъ", status="запасный солдат", comment="«деревни Маниловки»")\n'
    assert _call(src) == 'x = person("Иванъ", status=SOLDIER, comment="запасный солдат; «деревни Маниловки»")\n'


def test_the_comparison_folds_case():
    src = HEAD + 'x = person("Иванъ", status="запасный солдат", comment="Запасный солдатъ, крестник")\n'
    assert _call(src) == 'x = person("Иванъ", status=SOLDIER, comment="Запасный солдатъ, крестник")\n'


def test_statusless_reservist_gets_soldier():
    src = HEAD + 'x = person("Петръ", comment="«запасный рядовой деревни Маниловки»")\n'
    new, changes, _ = mig.migrate_source(src)
    assert new.endswith('x = person("Петръ", status=SOLDIER, comment="«запасный рядовой деревни Маниловки»")\n')
    assert "from verso.ru.dsl.statuses import SOLDIER\n" in new
    assert changes == [(3, "", "SOLDIER", "«запасный рядовой деревни Маниловки»",
                        "«запасный рядовой деревни Маниловки»")]


@pytest.mark.parametrize("comment", [
    "«солдатки Марѳы дочь»",  # a soldier's wife's daughter: not a reservist
    "«поступившій въ военную службу»",  # military, but no reserve
    "«изъ крестьянъ деревни Заманиловки»",
    "отчество читается неуверенно",
])
def test_a_statusless_comment_without_a_reserve_wording_is_left(comment: str):
    src = HEAD + f'x = person("Петръ", comment="{comment}")\n'
    assert mig.migrate_source(src) == (src, [], [])


def test_unplaced_is_reported_not_rewritten():
    src = HEAD + 'x = person("Марья", status="солдатская девица")\n'
    new, changes, left = mig.migrate_source(src)
    assert new == src
    assert changes == []
    assert left == [(3, "солдатская девица")]


@pytest.mark.parametrize("text, expected", [
    ("солдатская девица", True), ("кантонист", True), ("вахмистр Глуповского конного полка", True),
    ("военный писарь в бессрочном отпуску", True),
    ("крестьянская девица помещика Собакевича", False), ("сельский писарь", False), ("запасный солдат", False),
])
def test_unplaced_is_a_military_wording_classify_refuses(text: str, expected: bool):
    assert unplaced(text) is expected


def test_catalog_and_civil_texts_are_untouched():
    src = HEAD + ('x = person("Иванъ", status=SOLDIER)\ny = person("Иванъ", status="солдат")\n'
                  'z = person("Иванъ", status="крестьянин поручика Ноздрева")\n')
    assert mig.migrate_source(src) == (src, [], [])


def test_existing_import_is_extended_once():
    src = ("from verso.ru.dsl import person\nfrom verso.ru.dsl.statuses import SOLDIER_SPOUSE\n\n"
           'x = person("Иванъ", status="запасный солдат")\ny = person("Анна", status=SOLDIER_SPOUSE)\n')
    once = mig.migrate_source(src)[0]
    assert once.startswith("from verso.ru.dsl import person\n"
                           "from verso.ru.dsl.statuses import SOLDIER, SOLDIER_SPOUSE\n\n")
    assert once.count("import SOLDIER") == 1
    assert mig.migrate_source(once) == (once, [], [])


LAID_OUT = '''\
from verso.ru.dsl import birth, birth_records, person

records = birth_records(
    # лист 3, правая сторона
    birth(1, father=person("Иванъ",   "Петровъ", residence="Маниловка",
                           status="запасный рядовой"),
          mother=person("Анна", status="солдатская жена из крестьян помещика Собакевича" ,
                        comment="тож Ноздрева")),  # хвост
)
'''


def test_layout_and_comments_survive():
    new = mig.migrate_source(LAID_OUT)[0]
    assert new == '''\
from verso.ru.dsl import birth, birth_records, person
from verso.ru.dsl.statuses import SOLDIER, SOLDIER_SPOUSE

records = birth_records(
    # лист 3, правая сторона
    birth(1, father=person("Иванъ",   "Петровъ", residence="Маниловка",
                           status=SOLDIER, comment="запасный рядовой"),
          mother=person("Анна", status=SOLDIER_SPOUSE ,
                        comment="солдатская жена из крестьян помещика Собакевича; тож Ноздрева")),  # хвост
)
'''


def test_bound_constants_and_defaults_are_reported_not_rewritten():
    src = (HEAD + 'from verso.ru.dsl import RecordDefaults\n\nZ = "запасный солдат"\n'
           'DEFAULTS = RecordDefaults(status_male="уволенный в запас армии")\nx = person("Иванъ", status=Z)\n')
    new, changes, _ = mig.migrate_source(src)
    assert (new, changes) == (src, [])
    assert mig.left_as_is(src) == [(5, "status", "запасный солдат", "SOLDIER", "Z"),
                                   (6, "status_male", "уволенный в запас армии", "SOLDIER", None)]


VILLAGE_FILE = HEAD + 'x = person("Иванъ", status="запасный солдат")\ny = person("Марья", status="солдатская девица")\n'


def _village(tmp_path: Path) -> Path:
    (tmp_path / "verso.toml").write_text('schema = 6\nvillages = ["Маниловка"]\nplugins = ["ru"]\n', encoding="utf-8")
    year = tmp_path / "Маниловка" / "1850"
    year.mkdir(parents=True)
    path = year / "manilovka_births_1850.py"
    path.write_text(VILLAGE_FILE, encoding="utf-8")
    return path


def test_the_cli_dry_run_writes_the_report_and_no_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _village(tmp_path)
    report = tmp_path / "report.tsv"
    with workspace.use(tmp_path):
        mig.main(["--village", "Маниловка", "--dry-run", "--report", str(report)])
    assert path.read_text(encoding="utf-8") == VILLAGE_FILE
    assert '+x = person("Иванъ", status=SOLDIER, comment="запасный солдат")' in capsys.readouterr().out
    rows = [line.split("\t") for line in report.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        ["kind", "file", "line", "old", "constant", "comment_after"],
        ["rewrite", "Маниловка/1850/manilovka_births_1850.py", "3", "запасный солдат", "SOLDIER", "запасный солдат"],
        ["unplaced", "Маниловка/1850/manilovka_births_1850.py", "4", "солдатская девица", "", ""],
    ]


def test_the_cli_writes_the_file(tmp_path: Path):
    path = _village(tmp_path)
    with workspace.use(tmp_path):
        mig.main(["--village", "Маниловка"])
    assert 'x = person("Иванъ", status=SOLDIER, comment="запасный солдат")\n' in path.read_text(encoding="utf-8")
