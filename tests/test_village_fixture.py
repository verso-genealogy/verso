"""tests/village_fixture.py — the library's tests' mini corpus: Verso's fixture, copied
(tools/fixture_copies.py keeps it equal), read without the App."""
from __future__ import annotations

import ast
from pathlib import Path

import village_fixture
from verso.core import workspace


def test_the_mini_corpus_holds_manilovka(tmp_path):
    root = village_fixture.root(tmp_path)
    assert sorted(p.name for p in (root / "Маниловка" / "1900").glob("*.py"))
    assert not list(root.rglob("__pycache__"))


def test_named_files_and_the_scans_toml(tmp_path):
    root = village_fixture.root(tmp_path, "Маниловка/1900/manilovka_births_1900.py")
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == [
        "Маниловка/1900/manilovka_births_1900.py", "Маниловка/scans.toml"]


def test_the_workspace_names_the_mini_corpus_s_layer(tmp_path):
    root = village_fixture.root(tmp_path)
    with workspace.use(village_fixture.workspace(tmp_path / "tables", root)) as ws:
        assert ws.villages == ("Маниловка",)
        names = (tmp_path / "tables" / "names").resolve()
        assert ws.names_dir is None and ws.names_layers is not None
        assert ws.names_layers.base == "ru" and ws.names_layers.layers == (names,)
        for table in ("names.tsv", "forms.tsv", "patronymics.tsv"):
            assert (names / table).read_bytes() == (village_fixture.MINI / "names" / table).read_bytes()


def test_village_fixture_imports_no_app():
    tree = ast.parse(Path(village_fixture.__file__).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in imported if m.startswith(("verso.app", "tests.verso_fixture", "verso_fixture"))}
