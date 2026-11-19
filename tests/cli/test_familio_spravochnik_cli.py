"""`verso familio-spravochnik`: the справочник from the village's records — no CSV read, the unreviewed left
out, a workbook the library builds where no template is named.

The village is the mini corpus's (tests/village_fixture.py): the directory Маниловка holds the books of the
parish Хлестаковка, 1899–1900, some of their records unreviewed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl
import pytest

import village_fixture
from verso.core.pipeline import records
from verso.core.pipeline.load import record_namespace, village_modules
from verso.core.pipeline.records import export_village as export_records
from verso.core.ratchet import unreviewed
from verso.ru.cli.familio_spravochnik import main
from verso.ru.exporters.familio_layout import build_workbook
from verso.ru.exporters.familio_template import TEMPLATE_DATA_START_ROW

PARISH = "Хлестаковка"
BIRTHS = "1900/manilovka_births_1900.py"
TABS = {"BirthRecords": "РОЖДЕНИЕ", "MarriageRecords": "БРАК", "DeathRecords": "СМЕРТЬ"}
NUMBER_COLUMN = 11          # «№ записи» of every record tab


def _village(tmp_path: Path) -> Path:
    village = village_fixture.root(tmp_path) / "Маниловка"
    for csv in village.rglob("*.csv"):
        csv.unlink()
    return village


def _records(village: Path) -> dict[str, list[tuple[str, bool]]]:
    """Tab → (number, unreviewed) of every record of the parish's metric books, as the DSL builds them."""
    found: dict[str, list[tuple[str, bool]]] = {tab: [] for tab in TABS.values()}
    for _, module in village_modules(village):
        books: dict[int, Any] = {id(v): v for v in record_namespace(module).values()}
        for record_set in books.values():
            tab = TABS.get(type(record_set).__name__)
            if tab is not None and record_set.village == PARISH:
                found[tab] += [(str(r.record_num), unreviewed(r)) for r in record_set.records]
    return found


def _numbers(path: Path) -> dict[str, list[str]]:
    wb = openpyxl.load_workbook(path)
    return {tab: [str(row[NUMBER_COLUMN - 1].value) for row in wb[tab].iter_rows(min_row=TEMPLATE_DATA_START_ROW)
                  if row[0].value is not None] for tab in TABS.values()}


def _cells(path: Path) -> dict[str, dict[str, object]]:
    wb = openpyxl.load_workbook(path)
    return {ws.title: {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}
            for ws in wb.worksheets}


def _run(village: Path, out: Path, *flags: str) -> int:
    return main([PARISH, "1899", "1900", "--village-dir", str(village), "--out", str(out), *flags])


def test_cli_reads_records_not_csv(tmp_path, capsys):
    village, out = _village(tmp_path), tmp_path / "mk.xlsx"
    assert not list(village.rglob("*_familio.csv"))
    assert _run(village, out) == 0
    assert out.is_file() and not list(village.rglob("*_familio.csv"))
    assert f"Wrote {out}" in capsys.readouterr().out


def test_cli_leaves_unreviewed_out_by_default(tmp_path, capsys):
    village, out = _village(tmp_path), tmp_path / "mk.xlsx"
    wanted = _records(village)
    held = sum(1 for rows in wanted.values() for _, is_held in rows if is_held)
    assert held >= 5, "the mini corpus holds unreviewed records"
    assert _run(village, out) == 0
    assert _numbers(out) == {tab: [n for n, is_held in rows if not is_held] for tab, rows in wanted.items()}
    assert f"пропущено невычитанных: {held}" in capsys.readouterr().out.splitlines()


def test_cli_with_unreviewed(tmp_path, capsys):
    village, out = _village(tmp_path), tmp_path / "mk.xlsx"
    assert _run(village, out, "--with-unreviewed") == 0
    assert {tab: sorted(n) for tab, n in _numbers(out).items()} == {
        tab: sorted(n for n, _ in rows) for tab, rows in _records(village).items()}
    assert "пропущено невычитанных" not in capsys.readouterr().out


def test_cli_parish_is_the_set_village(tmp_path, capsys):
    village = _village(tmp_path)
    with pytest.raises(SystemExit) as refused:                 # the directory's name is no parish of its books
        main(["Маниловка", "1899", "1900", "--village-dir", str(village), "--out", str(tmp_path / "mk.xlsx")])
    assert refused.value.code == 2 and "no records found" in capsys.readouterr().err


def test_cli_skips_csv_skip_files(tmp_path):
    village, out = _village(tmp_path), tmp_path / "mk.xlsx"
    (village / "village.toml").write_text(f'schema = 1\n[csv]\nskip = ["{BIRTHS}"]\n', encoding="utf-8")
    assert _run(village, out, "--with-unreviewed") == 0
    numbers = _numbers(out)
    assert numbers["РОЖДЕНИЕ"] == [] and numbers["СМЕРТЬ"]


def test_cli_builds_without_template(tmp_path):
    village, out = _village(tmp_path), tmp_path / "mk.xlsx"
    assert _run(village, out) == 0
    assert openpyxl.load_workbook(out).sheetnames == ["about", "location", "РОЖДЕНИЕ", "БРАК", "СМЕРТЬ"]


def test_cli_template_flag_fills_the_file(tmp_path):
    village = _village(tmp_path)
    template = build_workbook()
    template.create_sheet("spiski").cell(1, 1, "список")
    template.save(tmp_path / "template.xlsx")
    assert _run(village, tmp_path / "a.xlsx", "--template", str(tmp_path / "template.xlsx")) == 0
    assert _run(village, tmp_path / "b.xlsx") == 0
    filled, built = _cells(tmp_path / "a.xlsx"), _cells(tmp_path / "b.xlsx")
    assert filled.pop("spiski") == {"A1": "список"}
    # With no about.json a template's `about` is left as it came; the built workbook says its years.
    about_filled, about_built = filled.pop("about"), built.pop("about")
    assert {k: v for k, v in about_built.items() if k not in about_filled} == {"B5": "1899-1900", "B6": 1899}
    assert filled == built


def test_cli_under_records_export(tmp_path):
    a, b = _village(tmp_path / "a"), _village(tmp_path / "b")
    export_records(b, tmp_path / "rec")
    assert _run(a, tmp_path / "a.xlsx") == 0
    with records.use(tmp_path / "rec"):
        assert _run(b, tmp_path / "b.xlsx") == 0
    assert _cells(tmp_path / "a.xlsx") == _cells(tmp_path / "b.xlsx")


def test_no_regenerate_is_accepted(tmp_path):
    village = _village(tmp_path)
    assert _run(village, tmp_path / "a.xlsx", "--no-regenerate") == 0
    assert _run(village, tmp_path / "b.xlsx") == 0
    assert _cells(tmp_path / "a.xlsx") == _cells(tmp_path / "b.xlsx")


def test_cli_location_is_the_csv_then_the_places(tmp_path, capsys):
    village, out = _village(tmp_path), tmp_path / "mk.xlsx"
    submissions = village / "familio_submissions"
    submissions.mkdir()
    (submissions / "location.csv").write_text(
        "place,type,region,district,volost,link\nСвоя,д.,Энская,Свой,,\n", encoding="utf-8")
    assert _run(village, out) == 0
    ws = openpyxl.load_workbook(out)["location"]
    listed = [str(ws.cell(r, 1).value) for r in range(3, ws.max_row + 1)]
    assert listed[0] == "Своя" and len(listed) > 1 and len(set(listed)) == len(listed)
    printed = capsys.readouterr().out
    assert f"  location: {len(listed)} places" in printed
    blank = sum(1 for r in range(3, ws.max_row + 1)
                if not any(ws.cell(r, c).value for c in (2, 3, 4, 5, 8)))
    assert (f"мест без данных: {blank}" in printed) == (blank > 0)


def test_cli_refuses_a_file_that_does_not_import(tmp_path, capsys):
    village = _village(tmp_path)
    (village / "1900" / "manilovka_broken_1900.py").write_text("raise RuntimeError('сломан')\n", encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        _run(village, tmp_path / "mk.xlsx")
    assert refused.value.code == 2
    assert "manilovka_broken_1900.py" in capsys.readouterr().err
    assert not (tmp_path / "mk.xlsx").exists()


def test_default_out_path_is_under_the_village(tmp_path, monkeypatch):
    village = _village(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main([PARISH, "1899", "1900", "--village-dir", str(village)]) == 0
    assert (village / "familio_submissions" / "mk_hlestakovka_1899-1900.xlsx").is_file()


def test_cli_says_when_everything_is_unreviewed(tmp_path, capsys):
    village = tmp_path / "V"
    (village / "1900").mkdir(parents=True)
    (village / "1900" / "v_births_1900.py").write_text(
        "from verso.ru.dsl import Gender, Month, birth, birth_month, birth_records, person\n\n"
        'v_births_1900 = birth_records("ГАРО", "1", "2", "3", "V", "Церковь", 1900,\n'
        "    *birth_month(Month.JANUARY,\n"
        '                 birth(1, Gender.MALE, 3, 4, reviewed=False, child=person("Тимоѳей"), father=person("Іоаннъ")),\n'
        '                 birth(2, Gender.MALE, 5, 6, reviewed=False, child=person("Іоаннъ"), father=person("Іоаннъ"))))\n',
        encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        main(["V", "1900", "1900", "--village-dir", str(village), "--out", str(tmp_path / "mk.xlsx")])
    assert refused.value.code == 2
    assert "no records found for V 1900 — пропущено невычитанных: 2; --with-unreviewed положит и их" in capsys.readouterr().err
    assert main(["V", "1900", "1900", "--village-dir", str(village), "--out", str(tmp_path / "mk.xlsx"),
                 "--with-unreviewed"]) == 0
