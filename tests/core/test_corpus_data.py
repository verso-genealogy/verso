"""verso.core.corpus_data on the toy plugin: the core reads `schema` and `[geni]` of a
village.toml; every other table is a plugin's, parsed by its `village_tables` hook."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import corpus_data, plugins, workspace
from verso.core.corpus_data import CorpusDataError


def _village(directory: Path, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "village.toml").write_text(text, encoding="utf-8")
    return directory


@pytest.mark.usefixtures("toy_workspace")
def test_core_reads_only_geni(tmp_path: Path):
    v = corpus_data.village(_village(tmp_path / "v", 'schema = 1\n[geni]\nprojects = ["p"]\n[toy]\nshelf = "x"\n'))
    assert v.projects == ("p",)
    assert v.table("toy") == ("toy", "x")
    assert v.table("census") is None


@pytest.mark.usefixtures("toy_workspace")
def test_a_plugin_table_must_be_a_table(tmp_path: Path):
    with pytest.raises(CorpusDataError, match=r"village\.toml: «toy» — "):
        corpus_data.village(_village(tmp_path / "v", 'schema = 1\ntoy = 1\n'))


def test_a_table_no_enabled_plugin_reads_is_unknown(tmp_path: Path):
    (tmp_path / "verso.toml").write_text("schema = 4\n", encoding="utf-8")     # the core alone
    v = _village(tmp_path / "v", 'schema = 1\n[census]\norder = []\n')
    with plugins.adding(entry_points=False), workspace.use(tmp_path), \
            pytest.raises(CorpusDataError, match=r"village\.toml: .*«census»"):
        corpus_data.village(v)


def test_a_plugins_table_outside_a_workspace_says_there_is_none(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch):
    """With no workspace no plugin is enabled: a table only a plugin reads is refused for that,
    not as a key nobody knows."""
    def nowhere() -> object:
        raise workspace.WorkspaceError("no workspace here")
    monkeypatch.setattr(corpus_data.plugins, "enabled", nowhere)
    v = _village(tmp_path / "v", 'schema = 1\n[census]\norder = []\n')
    with pytest.raises(CorpusDataError, match=r"village\.toml: «census».*no workspace here"):
        corpus_data.village(v)
    assert corpus_data.village(_village(tmp_path / "w", 'schema = 1\n[geni]\nprojects = ["p"]\n')).projects == ("p",)


def test_estates_and_events_are_the_plugins():
    assert not hasattr(corpus_data, "estates")
    assert not hasattr(corpus_data, "timeline_events")
    assert not hasattr(corpus_data, "Era")


def test_wrong_speaks_the_language_of_the_print(tmp_path: Path):
    """A CorpusDataError raised in one language reads in the language it is printed in."""
    from verso.core import i18n
    from verso.core.messages import t
    with i18n.use("en"):
        error = corpus_data.wrong(tmp_path / "x.toml", "k", t("corpus_data.expected_table"))
    with i18n.use("ru"):
        assert str(error) == f"{tmp_path / 'x.toml'}: «k» — ожидалась таблица"
    with i18n.use("en"):
        assert str(error) == f"{tmp_path / 'x.toml'}: «k» — expected a table"
