"""verso.core.workspace: where the data is, found one way.

Hermetic: every workspace here is written into tmp_path. The process's own
workspace is forgotten before each test and after it, so a test that finds one
by the cwd or the environment never leaves it behind for the next.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from verso.core import workspace
from verso.core.workspace import (
    ENV, SCHEMA, LexiconNotConfigured, NamesLayers, WorkspaceError, child_env, current, find, load, main, on_change,
    pin, use)


def write(root: Path, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "verso.toml").write_text(text, encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def forgotten() -> Iterator[None]:
    pin(None)
    yield
    pin(None)


def test_load_reads_the_four_keys(tmp_path: Path) -> None:
    write(tmp_path, 'schema = 1\nvillages = ["А", "Б"]\n[names]\ndir = "t"\n[notes]\nglobs = ["{village}/*.md"]\n')
    ws = load(tmp_path)
    assert ws.root == tmp_path.resolve()
    assert ws.villages == ("А", "Б")
    assert ws.names_dir == tmp_path.resolve() / "t"
    assert ws.notes == ("{village}/*.md",)


def test_a_bare_schema_is_a_workspace_with_nothing_in_it(tmp_path: Path) -> None:
    ws = load(write(tmp_path, "schema = 1\n"))
    assert (ws.villages, ws.names_dir, ws.notes) == ((), None, ())


@pytest.mark.parametrize("text, key", [
    ('schema = 1\n[names]\ntable = "names.csv"\n', "names.table"),
    ('schema = 2\n[tools]\nterraform = "tf"\n', "tools.terraform"),
    ('schema = 2\n[corpus]\npath = "c"\n', "corpus.path"),
    ('schema = 1\nvilage = []\n', "vilage"),
])
def test_an_unknown_key_is_refused(tmp_path: Path, text: str, key: str) -> None:
    write(tmp_path, text)
    with pytest.raises(WorkspaceError, match=f"неизвестный ключ «{key}»"):
        load(tmp_path)


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    write(tmp_path, f"schema = {SCHEMA + 1}\n")
    with pytest.raises(WorkspaceError, match=f"schema {SCHEMA + 1} новее кода \\({SCHEMA}\\)"):
        load(tmp_path)


def test_a_missing_schema_is_refused(tmp_path: Path) -> None:
    write(tmp_path, 'villages = ["А"]\n')
    with pytest.raises(WorkspaceError, match="«schema»"):
        load(tmp_path)


def test_schema_2_reads_corpus_and_tools(tmp_path: Path) -> None:
    ws = load(write(tmp_path, 'schema = 2\nvillages = []\n[corpus]\ndir = "c"\n[tools]\npath = ["~/bin", "bin"]\n'))
    assert ws.corpus_dir == (tmp_path / "c").resolve()
    assert ws.tool_path == (Path.home() / "bin", (tmp_path / "bin").resolve())


def test_schema_1_still_loads(tmp_path: Path) -> None:
    ws = load(write(tmp_path, "schema = 1\nvillages = []\n"))
    assert (ws.corpus_dir, ws.tool_path) == (None, ())


@pytest.mark.parametrize("text, key", [
    ('schema = 1\nvillages = "А"\n', "villages"),
    ('schema = 2\n[corpus]\ndir = 1\n', "corpus.dir"),
    ('schema = 2\n[tools]\npath = "bin"\n', "tools.path"),
    ('schema = 1\nvillages = ["А", 2]\n', "villages"),
    ('schema = 1\n[names]\ndir = 1\n', "names.dir"),
    ('schema = "1"\n', "schema"),
])
def test_a_wrong_type_is_refused(tmp_path: Path, text: str, key: str) -> None:
    write(tmp_path, text)
    with pytest.raises(WorkspaceError, match=f"«{key}» — ожидал"):
        load(tmp_path)


def test_find_walks_up_from_a_subdirectory(tmp_path: Path) -> None:
    root = write(tmp_path / "data", "schema = 1\n")
    (root / "a" / "b").mkdir(parents=True)
    assert find(root / "a" / "b") == root.resolve()


def test_a_git_boundary_without_config_stops_the_search(tmp_path: Path) -> None:
    write(tmp_path, "schema = 1\n")                      # main, with its verso.toml
    wt = tmp_path / ".claude" / "worktrees" / "x"
    wt.mkdir(parents=True)
    (wt / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")   # a worktree without one
    (wt / "sub").mkdir()
    # A worktree of a branch older than verso.toml is the usual one: the message says how.
    with pytest.raises(WorkspaceError, match=r"граница git.*обновите рабочую копию"):
        find(wt / "sub")


def test_a_repository_holding_its_config_is_found_at_its_root(tmp_path: Path) -> None:
    root = write(tmp_path, "schema = 1\n")
    (root / ".git").mkdir()
    assert find(root) == root.resolve()


def test_nothing_up_to_the_top_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError, match="рабочая область не найдена"):
        find(tmp_path)


def test_the_environment_wins_over_the_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = write(tmp_path / "here", "schema = 1\n")
    there = write(tmp_path / "there", "schema = 1\n")
    monkeypatch.chdir(here)
    monkeypatch.setenv(ENV, str(there))
    assert current().root == there.resolve()


def test_without_the_environment_the_cwd_decides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = write(tmp_path / "here", "schema = 1\n")
    monkeypatch.chdir(here)
    monkeypatch.delenv(ENV, raising=False)
    assert current().root == here.resolve()


def test_an_environment_naming_no_workspace_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV, str(tmp_path))
    with pytest.raises(WorkspaceError, match=f"{ENV}=.*: нет verso.toml"):
        current()


def test_the_first_answer_is_kept_after_chdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = write(tmp_path / "here", "schema = 1\n")
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.chdir(here)
    assert current().root == here.resolve()
    monkeypatch.chdir(tmp_path / "elsewhere")
    assert current().root == here.resolve()


def test_use_stacks_and_restores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b, c = (write(tmp_path / n, "schema = 1\n") for n in "abc")
    monkeypatch.setenv(ENV, str(a))
    with use(b) as ws:
        assert ws.root == current().root == b.resolve()
        with use(c):
            assert current().root == c.resolve()
        assert current().root == b.resolve()
    assert current().root == a.resolve()


def test_listeners_hear_every_change_and_only_a_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = (write(tmp_path / n, "schema = 1\n") for n in "ab")
    monkeypatch.setenv(ENV, str(b))
    current()
    heard: list[Path] = []
    # The process's own listeners (names_registry's reload) must outlive this test.
    kept = list(workspace._listeners)  # pyright: ignore[reportPrivateUsage]
    on_change(lambda: heard.append(current().root))
    try:
        with use(a):                     # b → a
            with use(a):                 # a → a: no change
                pass
        assert heard == [a.resolve(), b.resolve()]      # entered a, back to b
        pin(a)                           # b → a
        pin(a)                           # a → a
        assert heard == [a.resolve(), b.resolve(), a.resolve()]
    finally:
        workspace._listeners[:] = kept   # pyright: ignore[reportPrivateUsage]


def test_child_env_names_the_current_root(tmp_path: Path) -> None:
    root = write(tmp_path, "schema = 1\n")
    with use(root):
        env = child_env({"PATH": "/bin"})
        assert env == {"PATH": "/bin", ENV: str(root.resolve())}
        assert child_env()[ENV] == str(root.resolve())
        assert child_env()["PATH"] == os.environ["PATH"]


def test_names_file_without_names_section_is_lexicon_not_configured(tmp_path: Path) -> None:
    ws = load(write(tmp_path, "schema = 1\n"))
    with pytest.raises(LexiconNotConfigured, match=r"лексикон не настроен: в .*verso.toml нет \[names\]"):
        ws.names_file("names.csv")


def test_names_file_is_under_the_names_dir(tmp_path: Path) -> None:
    ws = load(write(tmp_path, 'schema = 1\n[names]\ndir = "."\n'))
    assert ws.names_file("names_ignore.csv") == tmp_path.resolve() / "names_ignore.csv"
    # Which tables there are is the plugins': the core refuses only a path out of the directory.
    with pytest.raises(ValueError):
        ws.names_file("../other.csv")


def test_village_dir_refuses_an_unlisted_village(tmp_path: Path) -> None:
    ws = load(write(tmp_path, 'schema = 1\nvillages = ["Маниловка"]\n'))
    assert ws.village_dir("Маниловка") == tmp_path.resolve() / "Маниловка"
    with pytest.raises(WorkspaceError, match="деревни «Заманиловка» нет в"):
        ws.village_dir("Заманиловка")


def test_the_command_prints_root_and_villages(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write(tmp_path, 'schema = 1\nvillages = ["Нижняя Яичница", "Маниловка"]\n')
    with use(root):
        assert main(["root"]) == 0
        assert main(["villages"]) == 0
    assert capsys.readouterr().out == f"{root.resolve()}\nНижняя Яичница\nМаниловка\n"


def test_the_command_says_why_there_is_no_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv(ENV, str(tmp_path))
    assert main(["root"]) == 2
    assert "нет verso.toml" in capsys.readouterr().err


def test_schema_3_takes_an_app_table_it_does_not_read(tmp_path: Path) -> None:
    """[app] is the App's (verso.app.settings): the library takes it and reads nothing in it."""
    (tmp_path / "verso.toml").write_text('schema = 3\nvillages = []\n[app]\nport = 1\nwhatever = "x"\n',
                                         encoding="utf-8")
    assert workspace.load(tmp_path).root == tmp_path.resolve()


def test_plugins_must_be_a_list_of_strings(tmp_path: Path) -> None:
    write(tmp_path, 'schema = 4\nplugins = "ru"\n')
    with pytest.raises(WorkspaceError, match="«plugins» — ожидался список строк"):
        load(tmp_path)


def test_schema_4_names_its_plugins_and_an_older_one_reads_as_ru(tmp_path: Path) -> None:
    """A file of schema 1–3 reads as it always did — the library was the Russian books'."""
    assert load(write(tmp_path / "a", 'schema = 4\nplugins = ["ru", "toy"]\n')).plugins == ("ru", "toy")
    assert load(write(tmp_path / "b", "schema = 4\n")).plugins == ()
    assert load(write(tmp_path / "c", "schema = 3\n")).plugins == ("ru",)
    assert load(write(tmp_path / "d", "schema = 1\n")).plugins == ("ru",)


# --- schema 6: the names lexicon as layers over a base ---------------------------------------------------------

def test_schema_5_reads_names_dir_and_no_layers(tmp_path: Path) -> None:
    ws = load(write(tmp_path, 'schema = 5\n[names]\ndir = "t"\n'))
    assert (ws.names_dir, ws.names_layers) == (tmp_path.resolve() / "t", None)


def test_schema_6_without_names_is_the_base_alone(tmp_path: Path) -> None:
    ws = load(write(tmp_path, "schema = 6\n"))
    assert ws.names_dir is None
    assert ws.names_layers == NamesLayers(base="ru", layers=(), writable=None)


def test_schema_6_reads_base_layers_and_writable(tmp_path: Path) -> None:
    ws = load(write(tmp_path, 'schema = 6\n[names]\nbase = false\nlayers = ["low", "top"]\nwritable = "low"\n'))
    root = tmp_path.resolve()
    assert ws.names_layers == NamesLayers(base=None, layers=(root / "low", root / "top"), writable=root / "low")


def test_schema_6_writes_to_the_top_layer_by_default(tmp_path: Path) -> None:
    ws = load(write(tmp_path, 'schema = 6\n[names]\nlayers = ["low", "top"]\n'))
    assert ws.names_layers is not None and ws.names_layers.writable == tmp_path.resolve() / "top"


def test_schema_6_names_file_says_there_are_no_tables(tmp_path: Path) -> None:
    ws = load(write(tmp_path, "schema = 6\n"))
    with pytest.raises(LexiconNotConfigured, match="в схеме 6 нет таблиц имён"):
        ws.names_file("names.csv")


@pytest.mark.parametrize("text, message", [
    ('schema = 6\n[names]\ndir = "."\n', "«\\[names\\] dir» — схема ≤ 5; в схеме 6 — «layers»"),
    ('schema = 6\n[names]\nlayers = ["a"]\nwritable = "b"\n', "«names.writable» — b нет среди «names.layers»"),
    ('schema = 6\n[names]\nwritable = "b"\n', "«names.writable» — b нет среди «names.layers»"),
    ('schema = 6\n[names]\nlayers = ["a", "./a"]\n', "«names.layers» — .* дважды"),
    ('schema = 6\n[names]\nbase = true\n', "«names.base» — ожидалось имя базы или false"),
    ('schema = 6\n[names]\nbase = ""\n', "«names.base» — ожидалось имя базы или false"),
    ('schema = 6\n[names]\nlayers = "a"\n', "«names.layers» — ожидался список строк"),
    ('schema = 6\n[names]\nlayers = ["a"]\nwritable = 1\n', "«names.writable» — ожидалась строка"),
    ('schema = 5\n[names]\nlayers = ["a"]\n', "«names.layers» — с schema 6"),
    ('schema = 5\n[names]\nbase = "ru"\n', "«names.base» — с schema 6"),
])
def test_schema_6_names_keys_are_checked(tmp_path: Path, text: str, message: str) -> None:
    write(tmp_path, text)
    with pytest.raises(WorkspaceError, match=message):
        load(tmp_path)
