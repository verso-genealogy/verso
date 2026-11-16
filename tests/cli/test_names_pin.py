"""`verso names pin | unpin`: a row of patronymics.tsv in the writable layer, read by the layers' linter first.

Every workspace here is written into tmp_path over the shipped base, its names invented: a father Зюзей the layer
holds, whose forms give the short patronymic «Зюзеев», and a scribe's spelling «Зюзеин» of it.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.cli import names as cli
from verso.ru.gender import Gender
from verso.ru.linters import names_layer as edit
from verso.ru.naming import names_registry
from verso.ru.naming.lexicon import PatronymicEntry
from verso.ru.naming import (
    canonicalize_patronymic, derive_old_patronymic, father_name_for_patronymic)
from verso.ru.naming.validation import validate_old_patronymic

M, F = Gender.MALE, Gender.FEMALE

NAMES = "sex\tname\tbases\tcanonical\tsource\tnote\nM\tЗюзей\t\t\tinvented\t\n"
FORMS = "sex\tname\tgenitive\tpatronymic_m\tpatronymic_f\told_patronymic_m\told_patronymic_f\tsource\n"
PINS = "sex\tform\tfather\tmodern\told\tsource\n"


@pytest.fixture(autouse=True)
def forgotten() -> Iterator[None]:
    names_registry.reload()
    yield
    names_registry.reload()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "verso.toml").write_text('schema = 6\nvillages = []\nplugins = ["ru"]\n[names]\nlayers = ["names"]\n'
                                         'writable = "names"\n[i18n]\nlocale = "ru"\n', encoding="utf-8")
    layer = tmp_path / "names"
    layer.mkdir()
    (layer / "names.tsv").write_text(NAMES, encoding="utf-8")
    (layer / "forms.tsv").write_text(FORMS, encoding="utf-8")
    (layer / "patronymics.tsv").write_text(PINS, encoding="utf-8")
    return tmp_path


def _run(root: Path, *argv: str) -> int:
    with workspace.use(root):
        return cli.main(list(argv))


def _pins(root: Path) -> list[str]:
    return (root / "names" / "patronymics.tsv").read_text(encoding="utf-8").splitlines()[1:]


def _pin(root: Path, *more: str) -> int:
    return _run(root, "pin", "--gender", "М", "--form", "Зюзеин", "--father", "Зюзей", "--modern", "Зюзеевич",
                "--source", "Маниловка МК 1900", *more)


def test_pin_teaches_the_spelling_and_moves_no_derivation(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with workspace.use(root):
        assert not validate_old_patronymic("Зюзеин")
        assert derive_old_patronymic("Зюзей", M) == "Зюзеев"
    assert _pin(root) == 0
    assert _pins(root) == ["M\tЗюзеин\tЗюзей\tЗюзеевич\t\tМаниловка МК 1900"]
    assert "patronymics.tsv: М Зюзеин: Зюзей, Зюзеевич" in capsys.readouterr().out
    with workspace.use(root):
        assert validate_old_patronymic("Зюзеин")
        assert canonicalize_patronymic("Зюзеин") == "Зюзеевич"
        assert father_name_for_patronymic("Зюзеин") == "Зюзей"
        # The father's own forms are as they were: no record writing «Зюзеев» reads otherwise.
        assert derive_old_patronymic("Зюзей", M) == "Зюзеев"
        assert derive_old_patronymic("Зюзей", F) == "Зюзеева"
        assert canonicalize_patronymic("Зюзеев") == "Зюзеевич"


def test_a_woman_s_pin(root: Path) -> None:
    assert _run(root, "pin", "--gender", "Ж", "--form", "Зюзеина", "--father", "Зюзей", "--modern", "Зюзеевна") == 0
    assert _pins(root) == ["F\tЗюзеина\tЗюзей\tЗюзеевна\t\teditor"]
    with workspace.use(root):
        assert validate_old_patronymic("Зюзеина")
        assert canonicalize_patronymic("Зюзеина") == "Зюзеевна"


def test_dry_run_writes_nothing(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _pin(root, "--dry-run") == 0
    assert _pins(root) == []
    assert "--dry-run" in capsys.readouterr().out


def test_a_key_the_layer_pins_is_refused_unless_replaced(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _pin(root) == 0
    assert _pin(root) == 1
    assert "patronymics.tsv" in capsys.readouterr().err
    assert _run(root, "pin", "--gender", "М", "--form", "Зюзеин", "--father", "Зюзей", "--modern", "Зюзеевич",
                "--source", "второе чтение", "--replace") == 0
    assert _pins(root) == ["M\tЗюзеин\tЗюзей\tЗюзеевич\t\tвторое чтение"]
    assert "(заменена)" in capsys.readouterr().out


def test_a_father_no_layer_holds_is_refused(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """LEX003: a pin's father must be a man's name some layer holds."""
    assert _run(root, "pin", "--gender", "М", "--form", "Брякин", "--father", "Бряка", "--modern", "Брякович") == 1
    err = capsys.readouterr().err
    assert "Бряка" in err and "ничего не записано" in err
    assert _pins(root) == []


def test_a_key_no_lookup_asks_by_is_refused(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """LEX001: not one Cyrillic word, or a pin tied to a father with no sex."""
    assert _run(root, "pin", "--gender", "М", "--form", "Zyuzein", "--father", "Зюзей", "--modern", "Зюзеевич") == 1
    assert _run(root, "pin", "--gender", "-", "--form", "Зюзеин", "--father", "Зюзей", "--modern", "Зюзеевич") == 1
    assert _pins(root) == []
    capsys.readouterr()


def test_a_pin_that_rereads_a_known_form_is_said(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """«Зюзеев» is read by the father's forms already: a pin to another reading is written, and said loud."""
    (root / "names" / "names.tsv").write_text(NAMES + "M\tЗюзий\t\t\tinvented\t\n", encoding="utf-8")
    assert _run(root, "pin", "--gender", "М", "--form", "Зюзеев", "--father", "Зюзий", "--modern", "Зюзиевич") == 0
    err = capsys.readouterr().err
    assert "Зюзей, Зюзеевич" in err and "Зюзий, Зюзиевич" in err


def test_an_unattached_form(root: Path) -> None:
    """No father, no modern, no short form: a form the lexicon knows and ties to nothing."""
    assert _run(root, "pin", "--gender", "-", "--form", "Зюзинкин", "--source", "ignore") == 0
    assert _pins(root) == ["\tЗюзинкин\t\t\t\tignore"]
    with workspace.use(root):
        assert validate_old_patronymic("Зюзинкин")


def test_unpin_deletes_the_layer_s_pin(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _pin(root) == 0
    assert _run(root, "unpin", "--gender", "М", "--form", "Зюзеин", "--dry-run") == 0
    assert len(_pins(root)) == 1
    assert _run(root, "unpin", "--gender", "М", "--form", "Зюзеин") == 0
    assert _pins(root) == []
    with workspace.use(root):
        assert not validate_old_patronymic("Зюзеин")
    assert _run(root, "unpin", "--gender", "М", "--form", "Зюзеин") == 1
    assert "не закрепляет" in capsys.readouterr().err


def test_replace_is_linted_without_the_row_it_replaces(root: Path) -> None:
    """`findings_of(replace=True)` reads a replaced pin against the layers below, not against the row it takes the place of."""
    assert _pin(root) == 0
    with workspace.use(root):
        at = edit.target(workspace.current(), None)
        again = edit.new_pin(at, M, "Зюзеин", "Зюзей", "Зюзеевич", None, "x", replace=True)
        assert isinstance(again, PatronymicEntry)
        assert [f.issue.code for f in edit.findings_of(at, [again], replace=True)] == []
        assert edit.reading_change(at, again) is None
