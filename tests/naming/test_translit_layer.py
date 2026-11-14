"""The transliteration's rules as rows of the names layers (schema 7): bound to a profile, summed bottom to top, a `-`
taking a lower rule away; a workspace of schema 6 reads its corpus's transliteration.toml as it always did."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import workspace
from verso.core.corpus_data import CorpusDataError
from verso.core.workspace import WorkspaceError
from verso.ru.naming import translit_layers
from verso.ru.naming.layer_files import LayerFileError
from verso.ru.naming.translit_layers import TranslitRule
from verso.ru.naming.transliteration import RU_V1, RU_V2, address, display, profile_of

HEADER = "profile\tword\tlatin\tsource\tnote\n"


def _root(tmp_path: Path, *, schema: int = 7, translit: str = "", corpus_toml: str | None = None,
          low: str = "", top: str = "") -> Path:
    corpus = '[corpus]\ndir = "corpus"\n'
    names = '[names]\nbase = "ru"\nlayers = ["low", "top"]\nwritable = "top"\n' if schema >= 6 else ""
    (tmp_path / "verso.toml").write_text(f'schema = {schema}\nplugins = ["ru"]\n{corpus}{names}{translit}',
                                         encoding="utf-8")
    (tmp_path / "corpus").mkdir()
    if corpus_toml is not None:
        (tmp_path / "corpus" / "transliteration.toml").write_text(corpus_toml, encoding="utf-8")
    for name, rows in (("low", low), ("top", top)):
        (tmp_path / name).mkdir()
        if rows:
            (tmp_path / name / "translit.tsv").write_text(HEADER + rows, encoding="utf-8")
    return tmp_path


def test_schema_6_reads_the_toml(tmp_path: Path):
    root = _root(tmp_path, schema=6, corpus_toml='[names]\n"Плотвичкин" = "Plotvichkine"\n')
    with workspace.use(root):
        assert profile_of("address") is RU_V1 and profile_of("display") is RU_V1
        assert address()("Плотвичкин") == display()("Плотвичкин") == "Plotvichkine"


def test_schema_7_defaults_ru_v2(tmp_path: Path):
    with workspace.use(_root(tmp_path)):
        assert profile_of("address") is RU_V2 and profile_of("display") is RU_V2
        assert address()("Яков") == display()("Яков") == "Yakov"


def test_schema_7_names_a_profile_for_each_role(tmp_path: Path):
    with workspace.use(_root(tmp_path, translit='[translit]\naddress = "ru-v1"\ndisplay = "ru-v2"\n')):
        assert address()("Юрий") == "Jurij"
        assert display()("Юрий") == "Yury"


def test_an_unknown_profile_is_named(tmp_path: Path):
    with workspace.use(_root(tmp_path, translit='[translit]\ndisplay = "ru-v9"\n')), \
            pytest.raises(WorkspaceError, match=r"«translit\.display» = «ru-v9» — такого профиля транслитерации нет"):
        display()("Юрий")


def test_schema_7_refuses_the_old_file(tmp_path: Path):
    with workspace.use(_root(tmp_path, corpus_toml='[names]\n"Плотвичкин" = "Plotvichkine"\n')), \
            pytest.raises(CorpusDataError, match="verso translit migrate"):
        address()("Плотвичкин")


def test_rule_bound_to_profile(tmp_path: Path):
    root = _root(tmp_path, translit='[translit]\naddress = "ru-v1"\ndisplay = "ru-v2"\n',
                 top="ru-v1\tПлотвичкин\tPlotvichkine\teditor\t\n")
    with workspace.use(root):
        assert address()("Плотвичкин") == "Plotvichkine"
        assert display()("Плотвичкин") == "Plotvichkin"


def test_upper_layer_rule_wins(tmp_path: Path):
    root = _root(tmp_path, low="ru-v2\tПлотвичкин\tPlotvichkine\teditor\t\n",
                 top="ru-v2\tПлотвичкин\tPlotwitschkin\teditor\t\n")
    with workspace.use(root):
        assert display()("Плотвичкин") == "Plotwitschkin"


def test_dash_removes_lower_rule(tmp_path: Path):
    root = _root(tmp_path, low="ru-v2\tПлотвичкин\tPlotvichkine\teditor\t\n", top="ru-v2\tПлотвичкин\t-\teditor\t\n")
    with workspace.use(root):
        assert display()("Плотвичкин") == "Plotvichkin"
        assert [name for name, _ in translit_layers.explain(workspace.current(), "ru-v2", "Плотвичкин")] == ["low", "top"]


def test_a_rule_edited_is_read_on_the_next_name(tmp_path: Path):
    root = _root(tmp_path)
    with workspace.use(root):
        assert display()("Плотвичкин") == "Plotvichkin"
        translit_layers.writable(workspace.current()).put(TranslitRule("ru-v2", "Плотвичкин", "Plotvichkine"))
        assert display()("Плотвичкин") == "Plotvichkine"


def test_translit_rows_sorted_and_unique(tmp_path: Path):
    root = _root(tmp_path)
    with workspace.use(root):
        source = translit_layers.writable(workspace.current())
        source.put(TranslitRule("ru-v2", "Щеглов", "Shcheglof"))
        source.put(TranslitRule("ru-v1", "Ащеулов", "Aschcheulov", note="как в адресах"))
        source.put(TranslitRule("ru-v1", "Ащеулов", "Ashcheulov"))
    text = (root / "top" / "translit.tsv").read_text(encoding="utf-8")
    assert text == (HEADER + "ru-v1\tАщеулов\tAshcheulov\teditor\tкак в адресах\n"
                    "ru-v2\tЩеглов\tShcheglof\teditor\t\n")
    (root / "top" / "translit.tsv").write_text(text + "ru-v2\tЩеглов\tShcheglov\teditor\t\n", encoding="utf-8")
    with workspace.use(root), pytest.raises(LayerFileError):
        translit_layers.rules(workspace.current())


def test_the_base_layer_is_read_only(tmp_path: Path):
    with workspace.use(_root(tmp_path)):
        base = translit_layers.sources(workspace.current())[0]
        assert base.name == "base" and not base.writable
        with pytest.raises(TypeError):
            base.put(TranslitRule("ru-v2", "Плотвичкин", "Plotvichkine"))


def test_schema_6_reads_no_rules_from_layers(tmp_path: Path):
    root = _root(tmp_path, schema=6, top="ru-v1\tПлотвичкин\tPlotvichkine\teditor\t\n")
    with workspace.use(root):
        assert translit_layers.sources(workspace.current()) == []
        assert address()("Плотвичкин") == "Plotvichkin"
