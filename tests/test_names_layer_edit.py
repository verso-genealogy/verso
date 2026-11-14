"""`names add --replace`: a key the writable layer holds is replaced whole, the layers under it untouched."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.cli.names import main
from verso.ru.gender import Gender
from verso.ru.linters import names_layer as edit

NAMES = "sex\tname\tbases\tcanonical\tsource\tnote\n"
FORMS = "sex\tname\tgenitive\tpatronymic_m\tpatronymic_f\told_patronymic_m\told_patronymic_f\tsource\n"
PINS = "sex\tform\tfather\tmodern\told\tsource\n"


def _layer(root: Path, name: str, names: str = "", forms: str = "") -> None:
    (root / name).mkdir(parents=True)
    (root / name / "names.tsv").write_text(NAMES + names, encoding="utf-8")
    (root / name / "forms.tsv").write_text(FORMS + forms, encoding="utf-8")
    (root / name / "patronymics.tsv").write_text(PINS, encoding="utf-8")


@pytest.fixture
def ws(tmp_path: Path):
    (tmp_path / "verso.toml").write_text(
        'schema = 6\nvillages = []\nplugins = ["ru"]\n[names]\nbase = false\nlayers = ["low", "top"]\n'
        'writable = "top"\n', encoding="utf-8")
    _layer(tmp_path, "low", "F\tЕвфемия\t\tЕвфемия\tlow\t\n", "F\tЕвфемия\tЕвфемии\t\t\t\t\tlow\n")
    _layer(tmp_path, "top", "F\tМавра\t\tМавра\tmine\t\n", "F\tМавра\tМавры\t\t\t\t\tmine\n")
    with workspace.use(tmp_path):
        yield workspace.current()


def _top(root: Path, table: str) -> str:
    return (root / "top" / f"{table}.tsv").read_text(encoding="utf-8")


def test_add_existing_refused_without_replace(ws) -> None:
    at = edit.target(ws, None)
    with pytest.raises(edit.EditError) as refused:
        edit.new_entries(at, Gender.FEMALE, "Мавра", None, {}, "x")
    assert "уже есть" in str(refused.value) or "already" in str(refused.value)


def test_add_replace_overwrites_the_entry(ws) -> None:
    at = edit.target(ws, None)
    entries = edit.new_entries(at, Gender.FEMALE, "Мавра", "Евфемия", {"genitive": "Маврушки"}, "new", replace=True)
    assert len(entries) == 2
    at.layer.put_all(entries)
    assert "Мавра\tЕвфемия" in _top(ws.root, "names") and "\tmine" not in _top(ws.root, "names")
    assert "Маврушки" in _top(ws.root, "forms") and "Мавры" not in _top(ws.root, "forms")
    assert "Евфемии" in (ws.root / "low" / "forms.tsv").read_text(encoding="utf-8")
    assert "\tlow" in (ws.root / "low" / "names.tsv").read_text(encoding="utf-8")


def test_cli_replace_flag(ws, capsys) -> None:
    args = ["add", "--gender", "Ж", "--name", "Мавра", "--base", "Евфемия", "--source", "new"]
    assert main(args) == 1
    assert main([*args, "--replace"]) == 0
    assert "Мавра\tЕвфемия" in _top(ws.root, "names")


def test_replace_forms_only_keeps_the_names_row(ws, capsys) -> None:
    args = ["add", "--gender", "Ж", "--name", "Мавра", "--genitive", "Маврушки", "--source", "new", "--replace"]
    assert main(args) == 0
    assert "Маврушки" in _top(ws.root, "forms") and "Мавры" not in _top(ws.root, "forms")
    assert "\tmine" in _top(ws.root, "names")
    out = capsys.readouterr().out
    assert "forms.tsv" in out and ("заменена" in out or "replaced" in out) and "names.tsv" not in out


def test_replace_base_alone_keeps_the_forms_row(ws) -> None:
    at = edit.target(ws, None)
    entries = edit.new_entries(at, Gender.FEMALE, "Мавра", "Евфемия", {}, "new", replace=True)
    assert len(entries) == 1
    at.layer.put_all(entries)
    assert "Мавры" in _top(ws.root, "forms") and "Мавра\tЕвфемия" in _top(ws.root, "names")


def test_replace_a_removal_row(ws) -> None:
    (ws.root / "top" / "names.tsv").write_text(NAMES + "F\tЕвфемия\t-\t\tmine\t\n", encoding="utf-8")
    at = edit.target(ws, None)
    entries = edit.new_entries(at, Gender.FEMALE, "Евфемия", "Евфемия", {}, "new", replace=True)
    at.layer.put_all(entries)
    assert "Евфемия\tЕвфемия" in _top(ws.root, "names") and "\t-\t" not in _top(ws.root, "names")


def test_replace_is_linted_against_the_layers_below(ws) -> None:
    (ws.root / "low" / "names.tsv").write_text(NAMES + "F\tЕвфемия\t\t\tlow\t\n", encoding="utf-8")
    (ws.root / "top" / "names.tsv").write_text(NAMES + "F\tЕвфемия\tМавра\t\tmine\t\n", encoding="utf-8")
    at = edit.target(ws, None)
    entries = edit.new_entries(at, Gender.FEMALE, "Евфемия", None, {}, "new", replace=True)
    assert any(f.issue.code == "LEX005" for f in edit.findings_of(at, entries, replace=True))
    assert not any(f.issue.code == "LEX005" for f in edit.findings_of(at, entries))


def test_cli_prints_replaced(ws, capsys) -> None:
    args = ["add", "--gender", "Ж", "--name", "Мавра", "--base", "Евфемия", "--source", "new"]
    assert main([*args, "--replace"]) == 0
    out = capsys.readouterr().out
    assert "(заменена)" in out or "(replaced)" in out


def test_replace_refused_on_schema_5(tmp_path: Path, capsys) -> None:
    (tmp_path / "verso.toml").write_text('schema = 5\nvillages = []\nplugins = ["ru"]\n', encoding="utf-8")
    with workspace.use(tmp_path):
        code = main(["add", "--gender", "Ж", "--name", "Мавра", "--source", "x", "--replace"])
    assert code == 1
    assert "--replace" in capsys.readouterr().err
    assert not (tmp_path / "names.csv").exists()
