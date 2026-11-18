"""A corpus's own statuses are read from the workspace, at work time — not re-exported."""
from __future__ import annotations

import re
import sys
import textwrap
import types
from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.gender import Gender
from verso.core.workspace import WorkspaceError
from verso.ru.domain import statuses
from verso.ru.domain.status import Status
from verso.ru.domain.statuses import catalog, child_status_for, corpus_aliases, corpus_statuses
from verso.ru.linters.checks import parent_status, status_words

TOY = '''\
from verso.ru.gender import Gender
from verso.ru.domain.status import Status

__all__ = ["TOY_PEASANT_MALE", "TOY_PEASANT_SON", "TOY_PEASANT_DAUGHTER"]

TOY_PEASANT_MALE = Status("тойский крестьянин", Gender.MALE)
TOY_PEASANT_SON = Status("тойский крестьянский сын", Gender.MALE)
TOY_PEASANT_DAUGHTER = Status("тойская крестьянская дочь", Gender.FEMALE)

CHILD_ESTATE_ALIASES = {"TOY_STEWARD": "TOY_PEASANT"}
ESTATE_ALIASES = {"TOY_STEWARD": "TOY_PEASANT"}
'''


def _workspace(tmp_path: Path, statuses_py: str | None = TOY) -> Path:
    """A workspace whose corpus holds `statuses_py`; its directory is named after the test,
    since a corpus's statuses module is registered by the directory's name."""
    corpus = "toy_" + re.sub(r"\W", "_", tmp_path.name)
    root = tmp_path / "ws"
    root.mkdir()
    table = f'[corpus]\ndir = "{corpus}"\n' if statuses_py is not None else ""
    (root / "verso.toml").write_text(f'schema = 4\nplugins = ["ru"]\n{table}', encoding="utf-8")
    if statuses_py is not None:
        (root / corpus).mkdir()
        (root / corpus / "statuses.py").write_text(textwrap.dedent(statuses_py), encoding="utf-8")
    return root


def test_the_statuses_follow_the_workspace(tmp_path: Path):
    root = _workspace(tmp_path)
    with workspace.use(root):
        assert "TOY_PEASANT_MALE" in catalog() and "MANILOV_LK_PEASANT_MALE" not in catalog()
        assert child_status_for("тойский крестьянин", Gender.MALE) == "тойский крестьянский сын"
        assert "TOY_PEASANT_MALE" in status_words.tables().texts
        assert Status.gender_of("тойская крестьянская дочь") is Gender.FEMALE
        module = corpus_statuses()
        assert module is not None and module.__name__.endswith(".statuses")
        assert sys.modules[module.__name__] is module
    assert "TOY_PEASANT_MALE" not in catalog()          # the tests' workspace again
    assert child_status_for("тойский крестьянин", Gender.MALE) is None


def test_the_corpus_statuses_stand_before_the_landlord(tmp_path: Path):
    with workspace.use(_workspace(tmp_path)):
        names = list(catalog())
    toy = names.index("TOY_PEASANT_MALE")
    assert names[toy:toy + 3] == ["TOY_PEASANT_MALE", "TOY_PEASANT_SON", "TOY_PEASANT_DAUGHTER"]
    assert names[toy + 3] == "LANDLORD" and names[toy - 1] == "BUDNY_PEASANT"


def test_a_workspace_without_corpus_statuses_has_the_library_s_alone(tmp_path: Path):
    with workspace.use(_workspace(tmp_path, statuses_py=None)):
        assert corpus_statuses() is None
        assert len(catalog()) == 111
        assert corpus_aliases() == statuses.CorpusAliases({}, {})
        assert child_status_for("крестьянин", Gender.MALE) == "крестьянский сын"


def test_corpus_statuses_from_another_file_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # A worktree's child that took `corpus` from main's editable install: the DSL would get
    # one set of statuses and the library another.
    root = _workspace(tmp_path)
    corpus = next(p for p in root.iterdir() if p.is_dir())
    stranger = types.ModuleType(f"{corpus.name}.statuses")
    stranger.__file__ = str(tmp_path / "elsewhere" / "statuses.py")
    monkeypatch.setitem(sys.modules, stranger.__name__, stranger)
    with workspace.use(root), pytest.raises(WorkspaceError) as refused:
        corpus_statuses()
    assert str(tmp_path / "elsewhere" / "statuses.py") in str(refused.value)
    assert str(corpus / "statuses.py") in str(refused.value)
    assert "PYTHONPATH" in str(refused.value)


def test_statuses_loaded_through_a_link_outlive_the_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Two workspaces whose corpora each link one statuses file (Verso's tests copy a corpus per
    # test and link its Python): the first is loaded, its directory goes, the second is the same
    # file and is no stranger.
    real = tmp_path / "real" / "statuses.py"
    real.parent.mkdir()
    real.write_text(textwrap.dedent(TOY), encoding="utf-8")
    corpus = "toy_" + re.sub(r"\W", "_", tmp_path.name)
    roots = []
    for side in ("a", "b"):
        root = tmp_path / side
        (root / corpus).mkdir(parents=True)
        (root / corpus / "statuses.py").symlink_to(real)
        (root / "verso.toml").write_text(f'schema = 4\nplugins = ["ru"]\n[corpus]\ndir = "{corpus}"\n',
                                         encoding="utf-8")
        roots.append(root)
    monkeypatch.delitem(sys.modules, f"{corpus}.statuses", raising=False)
    with workspace.use(roots[0]):
        first = corpus_statuses()
    (roots[0] / corpus / "statuses.py").unlink()
    with workspace.use(roots[1]):
        assert corpus_statuses() is first
    monkeypatch.delitem(sys.modules, f"{corpus}.statuses", raising=False)


def test_the_corpus_aliases_reach_psa(tmp_path: Path):
    with workspace.use(_workspace(tmp_path)):
        aliases = parent_status.estate_aliases()
        assert aliases["TOY_STEWARD"] == "TOY_PEASANT"
        assert aliases["POPADIA"] == "PRIEST"
        assert corpus_aliases().child == {"TOY_STEWARD": "TOY_PEASANT"}
    assert "TOY_STEWARD" not in parent_status.estate_aliases()


def test_the_dsl_names_the_corpus_by_its_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    # One name for the corpus's statuses everywhere: `<the corpus directory>.statuses` — what
    # Verso writes (describe), what IMP001 allows and what `verso upgrade-dsl` writes.
    from verso.ru.cli import upgrade_dsl
    from verso.ru.dsl import describe
    from verso.ru.linters.checks import dsl_imports
    root = _workspace(tmp_path)
    name = next(p.name for p in root.iterdir() if p.is_dir()) + ".statuses"
    path = root / "V" / "1850" / "v_births_1850.py"
    path.parent.mkdir(parents=True)
    with workspace.use(root):
        assert statuses.corpus_module_name() == name
        assert describe.constant_by_code()["TOY_PEASANT_MALE"].module == name
        path.write_text(f"from {name} import TOY_PEASANT_MALE\nfrom verso.ru.dsl import person\n\nx = 1\n", encoding="utf-8")
        assert dsl_imports.check_file_structured(path) == []
        path.write_text("from corpus.statuses import A\n\nx = 1\n", encoding="utf-8")
        assert [f["message"].split(" — ")[0] for f in dsl_imports.check_file_structured(path)] == [
            "[IMP001] импорт не из фасада DSL: corpus.statuses"]
        path.write_text("from geni.domain.statuses import PEASANT_MALE, TOY_PEASANT_MALE\n\nx = 1\n", encoding="utf-8")
        assert upgrade_dsl.main([str(path)]) == 0
        assert path.read_text(encoding="utf-8") == (
            f"from {name} import TOY_PEASANT_MALE\nfrom verso.ru.dsl.statuses import PEASANT_MALE\n\nx = 1\n")
    capsys.readouterr()
