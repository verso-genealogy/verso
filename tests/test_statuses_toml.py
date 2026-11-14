"""A corpus's landlord statuses can be data: `<[corpus] dir>/statuses.toml`, read without executing Python."""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

from verso.core import workspace
from verso.core.workspace import WorkspaceError
from verso.ru.cli import statuses_toml as command
from verso.ru.dsl import describe, view
from verso.ru.domain import Status, statuses
from verso.ru.gender import Gender
from verso.ru.linters.checks import dsl_imports
from verso.ru.linters.checks.single_line_calls import known_statuses
from verso.ru.linters.on_json import walk
from verso.ru.domain.statuses import catalog, corpus_aliases, corpus_module_name, corpus_statuses, statuses_toml

FIXTURE = Path(__file__).parent / "fixtures" / "workspace"


def _copy(tmp_path: Path, *, py: bool, toml: str | None) -> tuple[Path, str]:
    """A copy of the fixture workspace whose corpus holds the statuses as Python (`py`) and/or as
    `toml`; the corpus directory is named after the test, as a statuses module is registered by it."""
    name = "toy_" + re.sub(r"\W", "_", tmp_path.name)
    root = tmp_path / "ws"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "corpus").rename(root / name)
    (root / "verso.toml").write_text((root / "verso.toml").read_text(encoding="utf-8")
                                     .replace('dir = "corpus"', f'dir = "{name}"'), encoding="utf-8")
    if not py:
        (root / name / "statuses.py").unlink()
    if toml is not None:
        (root / name / "statuses.toml").write_text(toml, encoding="utf-8")
    return root, name


def _library_count() -> int:
    """How many statuses the library defines itself: the catalog of a workspace whose corpus has none."""
    return sum(1 for k, v in vars(statuses).items() if k.isupper() and isinstance(v, Status))


def _rows() -> list[tuple[str, str, object]]:
    return [(name, str(status), status.gender) for name, status in catalog().items()]


def _as_python_toml() -> str:
    module = corpus_statuses()
    assert module is not None
    return statuses_toml(module)


def test_toml_round_trip(tmp_path: Path):
    with workspace.use(FIXTURE):
        want, aliases = _rows(), corpus_aliases()
        text = _as_python_toml()
        names = list(vars(corpus_statuses())["__all__"])
    root, _ = _copy(tmp_path, py=False, toml=text)
    with workspace.use(root):
        assert _rows() == want
        assert corpus_aliases() == aliases
        assert len(want) > _library_count() and aliases.child and aliases.estate
        module = corpus_statuses()
        assert module is not None and list(vars(module)["__all__"]) == names


def test_both_forms_refused(tmp_path: Path):
    root, _ = _copy(tmp_path, py=True, toml="[X]\ntext = \"икс\"\n")
    with workspace.use(root), pytest.raises(WorkspaceError) as refused:
        corpus_statuses()
    assert "statuses.toml" in str(refused.value) and "statuses.py" in str(refused.value)


def test_toml_imports_no_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with workspace.use(FIXTURE):
        text = _as_python_toml()
    root, name = _copy(tmp_path, py=False, toml=text)
    monkeypatch.delitem(sys.modules, f"{name}.statuses", raising=False)
    with workspace.use(root):
        assert len(catalog()) > _library_count()
        assert corpus_module_name() is None          # no module to import: the DSL cannot name them
        assert f"{name}.statuses" not in dsl_imports.allowed()      # IMP001 refuses the import
    assert f"{name}.statuses" not in sys.modules


@pytest.mark.parametrize("body, key", [
    ("[X]\ntext = 1\n", "X.text"),
    ("[X]\ntext = \"икс\"\ngender = \"other\"\n", "X.gender"),
    ("[X]\ngender = \"male\"\n", "X.text"),
    ("[X]\ntext = \"икс\"\nsize = 1\n", "X.size"),
    ("X = 1\n", "X"),
    ("[x]\ntext = \"икс\"\n", "x"),
    ("child_estate_aliases = 1\n", "child_estate_aliases"),
    ("[child_estate_aliases]\nABC = 1\n", "child_estate_aliases"),
    ("[estate_aliases]\nABC = [\"PEASANT\"]\n", "estate_aliases"),
])
def test_a_wrong_toml_is_refused_naming_the_key(tmp_path: Path, body: str, key: str):
    root, _ = _copy(tmp_path, py=False, toml=body)
    with workspace.use(root), pytest.raises(WorkspaceError) as refused:
        corpus_statuses()
    assert "statuses.toml" in str(refused.value) and key in str(refused.value)


def test_command_prints_toml(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    root, name = _copy(tmp_path, py=True, toml=None)
    with workspace.use(root):
        module = corpus_statuses()
        assert module is not None
        want = statuses_toml(module)
        assert command.main([]) == 0
        assert capsys.readouterr().out == want
    assert not (root / name / "statuses.toml").exists()


def test_command_has_no_write_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """`--write` always left the module and the data side by side, which the workspace refuses: dropped."""
    root, name = _copy(tmp_path, py=True, toml=None)
    with workspace.use(root), pytest.raises(SystemExit) as refused:
        command.main(["--write"])
    assert refused.value.code == 2
    assert not (root / name / "statuses.toml").exists()
    capsys.readouterr()


def test_command_out_beside_the_module_warns_that_both_stand(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    root, name = _copy(tmp_path, py=True, toml=None)
    with workspace.use(root):
        assert command.main(["--out", str(root / name / "statuses.toml")]) == 0
    assert "statuses.py" in capsys.readouterr().err


def test_command_out_writes_elsewhere(tmp_path: Path):
    root, name = _copy(tmp_path, py=True, toml=None)
    out = tmp_path / "elsewhere.toml"
    with workspace.use(root):
        assert command.main(["--out", str(out)]) == 0
        module = corpus_statuses()
        assert module is not None
        assert out.read_text(encoding="utf-8") == statuses_toml(module)
    assert not (root / name / "statuses.toml").exists()


def test_command_without_python_statuses_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    root, _ = _copy(tmp_path, py=False, toml=None)
    with workspace.use(root):
        assert command.main([]) == 1
    assert capsys.readouterr().err.strip()


def test_the_library_alone_has_no_corpus_statuses_without_either_file(tmp_path: Path):
    root, _ = _copy(tmp_path, py=False, toml=None)
    with workspace.use(root):
        assert corpus_statuses() is None and corpus_module_name() is None
        assert len(statuses.catalog()) == _library_count()


def test_a_status_without_a_gender_and_a_quoted_text_round_trip(tmp_path: Path):
    body = '[ABC_ONE]\ntext = "с \\"кавычкой\\" и \\\\"\n\n[ABC_TWO]\ntext = "ж"\ngender = "female"\n'
    root, _ = _copy(tmp_path, py=False, toml=body)
    with workspace.use(root):
        module = corpus_statuses()
        assert module is not None
        assert catalog()["ABC_ONE"] == 'с "кавычкой" и \\' and catalog()["ABC_ONE"].gender is None
        assert catalog()["ABC_TWO"].gender is not None
        assert statuses_toml(module) == body


def test_del_is_escaped_in_the_written_toml(tmp_path: Path):
    """A TOML basic string may not hold DEL (U+007F) raw; the writer escapes it and the file reads back."""
    body = '[ABC_ONE]\ntext = "до\\u007fпосле"\n\n[child_estate_aliases]\n"к\\u007fл" = "ABC"\n'
    root, _ = _copy(tmp_path, py=False, toml=body)
    with workspace.use(root):
        module = corpus_statuses()
        assert module is not None
        assert catalog()["ABC_ONE"] == "до\x7fпосле"
        written = statuses_toml(module)
        assert "\x7f" not in written and "\\u007f" in written
    root2, _ = _copy(tmp_path / "again", py=False, toml=written)
    with workspace.use(root2):
        assert catalog()["ABC_ONE"] == "до\x7fпосле"
        assert corpus_aliases().child == {"к\x7fл": "ABC"}


def test_statuses_toml_is_read_again_when_its_stamp_changes(tmp_path: Path):
    """Like estates.toml and places.toml: a change of the file (size, mtime) reaches the catalog and what is
    built from it without the workspace changing; an unchanged file is not read again."""
    root, name = _copy(tmp_path, py=False, toml='[ABC_ONE]\ntext = "один"\n')
    path = root / name / "statuses.toml"
    with workspace.use(root):
        first = catalog()
        assert "ABC_ONE" in first and "ABC_TWO" not in first
        assert catalog() is first                                  # kept while the stamp holds
        assert describe.constant_by_code()["ABC_ONE"].text == "один"
        assert known_statuses()["один"] == "ABC_ONE"
        assert "ABC_TWO" not in describe.constant_by_code()
        path.write_text('[ABC_ONE]\ntext = "один"\n\n[ABC_TWO]\ntext = "два"\ngender = "female"\n',
                        encoding="utf-8")
        assert "ABC_TWO" in catalog() and catalog()["ABC_TWO"].gender is not None
        assert "ABC_TWO" in describe.constant_by_code()            # what is built from the catalog follows
        assert known_statuses()["два"] == "ABC_TWO"
        assert corpus_aliases().child == {}
        path.write_text('[ABC_ONE]\ntext = "один"\n\n[child_estate_aliases]\nABC = "PEASANT"\n', encoding="utf-8")
        assert "ABC_TWO" not in catalog() and corpus_aliases().child == {"ABC": "PEASANT"}
        path.unlink()
        assert corpus_statuses() is None and "ABC_ONE" not in catalog() and len(catalog()) == _library_count()
        path.write_text('[ABC_THREE]\ntext = "три"\n', encoding="utf-8")
        assert "ABC_THREE" in catalog()                            # a file that appears is read, too


def test_a_held_block_reads_statuses_toml_as_it_stood_when_it_began(tmp_path: Path):
    """`statuses.held()` is one request: the stamp is asked as it begins and not again inside it, so an edit made
    while it runs is seen by the next request — and by the next question outside any block."""
    root, name = _copy(tmp_path, py=False, toml='[ABC_ONE]\ntext = "один"\n')
    path = root / name / "statuses.toml"
    two = '[ABC_ONE]\ntext = "один"\n\n[ABC_TWO]\ntext = "два"\n'
    with workspace.use(root):
        with statuses.held():
            assert "ABC_ONE" in catalog()
            path.write_text(two, encoding="utf-8")
            assert "ABC_TWO" not in catalog()                      # not asked again inside the request
            with statuses.held():                                  # a block inside it asks nothing either
                assert "ABC_TWO" not in catalog()
            assert "ABC_TWO" not in catalog()
        with statuses.held():
            assert "ABC_TWO" in catalog()                          # the next request sees the edit
        path.write_text('[ABC_THREE]\ntext = "три"\n', encoding="utf-8")
        assert "ABC_THREE" in catalog()                            # outside a block every question asks

def test_the_view_and_the_checks_name_a_status_alike():
    """`view._status_codes` (a record's view) and `walk.status_name_or_none` (the linters on JSON) are one rule —
    of the constants that spell a text, the one that sorts last — written twice: every status of the catalog."""
    with workspace.use(FIXTURE):
        codes = view._status_codes()                               # pyright: ignore[reportPrivateUsage]
        seen: set[tuple[str, str | None]] = set()
        for status in catalog().values():
            key = (str(status), None if status.gender is None else status.gender.name.lower())
            seen.add(key)
            assert codes[key] == walk.status_name_or_none(*key), key
        assert set(codes) == seen and len(seen) > 100


def test_the_expected_constant_message_shows_its_braces(tmp_path: Path):
    """The catalog escapes its braces (`{{ text, gender }}`): the message shows them once."""
    root, _ = _copy(tmp_path, py=False, toml="X = 1\n")
    with workspace.use(root), pytest.raises(WorkspaceError) as refused:
        corpus_statuses()
    assert "{ text, gender }" in str(refused.value) and "{{" not in str(refused.value)


def test_a_status_statuses_toml_drops_loses_its_sex(tmp_path: Path):
    """A constant of statuses.toml gives its sex to a plain-string status of its words while the file holds it, and
    none once the file drops it: the data registers nothing in `Status._gender_registry`."""
    root, name = _copy(tmp_path, py=False, toml='[ABC_ONE]\ntext = "особый чин"\ngender = "female"\n')
    path = root / name / "statuses.toml"
    with workspace.use(root):
        assert Status.gender_of("особый чин") is not None
        assert "особый чин" not in Status._gender_registry       # pyright: ignore[reportPrivateUsage]
        path.write_text('[ABC_TWO]\ntext = "другой чин"\n', encoding="utf-8")
        assert Status.gender_of("особый чин") is None
    with workspace.use(FIXTURE):
        assert Status.gender_of("особый чин") is None


def test_upgrade_dsl_knows_no_name_of_a_toml_only_corpus(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """A v0 file importing a corpus's status is refused where the corpus has `statuses.toml` alone: the
    upgrade would write `from <corpus>.statuses import …`, which no module answers."""
    from verso.ru.cli import upgrade_dsl
    root, _ = _copy(tmp_path, py=False, toml='[ABC_ONE]\ntext = "один"\n')
    path = tmp_path / "V" / "1850" / "v_births_1850.py"
    path.parent.mkdir(parents=True)
    text = "from geni.domain import person\nfrom geni.domain.statuses import ABC_ONE\n\nx = 1\n"
    path.write_text(text, encoding="utf-8")
    with workspace.use(root):
        assert upgrade_dsl.main([str(path)]) == 2
    assert path.read_text(encoding="utf-8") == text
    assert "ABC_ONE" in capsys.readouterr().err


@pytest.mark.parametrize("form", ["toml", "py"])
def test_a_corpus_status_wins_over_the_librarys_of_its_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                             form: str):
    """A corpus's constant spelled like a library's of another sex gives its own sex to those words, whether the
    corpus holds its statuses as data or as a module (whose import overwrites the library's registration)."""
    monkeypatch.setattr(Status, "_gender_registry", dict(Status._gender_registry))   # pyright: ignore[reportPrivateUsage]
    assert Status.gender_of("солдат") is Gender.MALE                                    # the library's SOLDIER
    if form == "toml":
        root, _ = _copy(tmp_path, py=False, toml='[ABC_ONE]\ntext = "солдат"\ngender = "female"\n')
    else:
        root, name = _copy(tmp_path, py=False, toml=None)
        (root / name / "statuses.py").write_text(
            'from verso.ru.dsl import Gender\nfrom verso.ru.domain import Status\n\n__all__ = ["ABC_ONE"]\n'
            'ABC_ONE = Status("солдат", Gender.FEMALE)\n', encoding="utf-8")
        monkeypatch.delitem(sys.modules, f"{name}.statuses", raising=False)
    with workspace.use(root):
        catalog()
        assert Status.gender_of("солдат") is Gender.FEMALE
