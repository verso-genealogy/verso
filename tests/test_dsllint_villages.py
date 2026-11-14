"""`verso dsllint --villages`: the files are every DSL file of every village of the workspace,
in its order — the list the Makefile and CI spelled village by village until then."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.linters import dsllint

WRAPPED = 'from verso.ru.dsl import person\n\np = person(\n    "Иван",\n)\n'


def _workspace(root: Path) -> Path:
    (root / "verso.toml").write_text('schema = 4\nvillages = ["Б", "А"]\nplugins = ["ru"]\n', encoding="utf-8")
    for village, name in (("А", "a_births_1850.py"), ("Б", "b_census_1858.py")):
        (root / village / "1850").mkdir(parents=True)
        (root / village / "1850" / name).write_text(WRAPPED, encoding="utf-8")
        (root / village / "1850" / "notes.txt").write_text("", encoding="utf-8")
    return root


def test_villages_lints_every_dsl_file_of_the_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    monkeypatch.setattr(sys, "argv", ["dsllint", "--json", "--villages"])
    with workspace.use(root):
        dsllint.main()
    files = list(dict.fromkeys(r["file"] for r in json.loads(capsys.readouterr().out)))
    assert [Path(f).relative_to(root).as_posix() for f in files] == ["Б/1850/b_census_1858.py",
                                                                     "А/1850/a_births_1850.py"]


def test_villages_with_paths_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _workspace(tmp_path)
    monkeypatch.setattr(sys, "argv", ["dsllint", "--villages", str(root / "А" / "1850" / "a_births_1850.py")])
    with workspace.use(root), pytest.raises(SystemExit, match="--villages: пути не нужны"):
        dsllint.main()
