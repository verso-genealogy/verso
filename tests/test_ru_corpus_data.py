"""verso.ru.corpus_data: what the Russian books read of the corpus's data files (out of
the core, which keeps `[geni]`)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from verso.core.corpus_data import CorpusDataError
from verso.ru import corpus_data
from verso.ru.corpus_data import Era, RuVillage
from verso.core.workspace import use
from verso.ru.dsl.records.census import CensusRecords
from verso.core.pipeline.load import discover_records


def _village_toml(directory: Path, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "village.toml").write_text(textwrap.dedent(text), encoding="utf-8")
    return directory


def test_a_village_without_village_toml_has_no_settings(tmp_path: Path) -> None:
    assert corpus_data.village(tmp_path) == RuVillage()
    assert (RuVillage().projects, dict(RuVillage().project_rules), RuVillage().census_order) == ((), {}, ())


def test_village_toml_is_read_from_the_directory(tmp_path: Path) -> None:
    # The directory is no village of verso.toml: test villages live in temporary directories.
    _village_toml(tmp_path, '''\
        schema = 1
        [geni]
        projects = ["data.geni_project.a.id", "data.geni_project.b.id"]
        [geni.project_rules]
        "Неелов" = "data.geni_project.c.id"
        ''')
    v = corpus_data.village(tmp_path)
    assert v.projects == ("data.geni_project.a.id", "data.geni_project.b.id")
    assert dict(v.project_rules) == {"Неелов": "data.geni_project.c.id"}


def test_a_census_entry_without_suffix_is_none(tmp_path: Path) -> None:
    _village_toml(tmp_path, '''\
        schema = 1
        [census]
        order = [{ year = 1717, suffix = "133-5-847" }, { year = 1850 }]
        ''')
    assert corpus_data.village(tmp_path).census_order == ((1717, "133-5-847"), (1850, None))


@pytest.mark.parametrize("text, key", [
    ('schema = 1\n[geni]\nproject = ["p"]\n', "geni.project"),
    ('schema = 1\nvillage = 1\n', "village"),
    ('schema = 1\n[census]\norder = [{ year = 1850, shelf = "x" }]\n', "census.order.shelf"),
])
def test_unknown_key_is_refused_with_the_file_and_key(tmp_path: Path, text: str, key: str) -> None:
    (tmp_path / "village.toml").write_text(text, encoding="utf-8")
    with pytest.raises(CorpusDataError, match=rf"village\.toml: неизвестный ключ «{key}»"):
        corpus_data.village(tmp_path)


@pytest.mark.parametrize("text, key", [
    ('schema = 1\n[geni]\nprojects = "p"\n', "geni.projects"),
    ('schema = 1\n[census]\norder = [{ suffix = "x" }]\n', "census.order.year"),
    ('schema = "1"\n', "schema"),
])
def test_a_wrong_type_is_refused_with_the_file_and_key(tmp_path: Path, text: str, key: str) -> None:
    (tmp_path / "village.toml").write_text(text, encoding="utf-8")
    with pytest.raises(CorpusDataError, match=rf"village\.toml: «{key}» — ожидал"):
        corpus_data.village(tmp_path)


def test_a_toml_slip_is_said_in_russian_with_the_file(tmp_path: Path) -> None:
    (tmp_path / "village.toml").write_text("schema = 1\n[geni\n", encoding="utf-8")
    with pytest.raises(CorpusDataError, match=r"village\.toml: не читается как TOML: "):
        corpus_data.village(tmp_path)


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    (tmp_path / "village.toml").write_text("schema = 2\n", encoding="utf-8")
    with pytest.raises(CorpusDataError, match=r"schema 2 новее кода \(1\)"):
        corpus_data.village(tmp_path)


def _census_file(village: Path, year: int) -> None:
    (village / str(year)).mkdir(parents=True, exist_ok=True)
    (village / str(year) / f"v_census_{year}.py").write_text(textwrap.dedent(f'''\
        from verso.ru.dsl import census_records
        v_census_{year} = census_records("A", "F", "I", "C", "V", {year})
        '''), encoding="utf-8")


def test_census_sets_follow_the_villages_order(tmp_path: Path) -> None:
    village = tmp_path / "V"
    for year in (1782, 1834, 1850):
        _census_file(village, year)
    def years() -> list[int]:
        return [r.year for _, _, r in discover_records(str(village)) if isinstance(r, CensusRecords)]
    assert years() == [1782, 1834, 1850]
    _village_toml(village, 'schema = 1\n[census]\norder = [{ year = 1850 }]\n')
    assert years() == [1850, 1782, 1834]


def _corpus(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "verso.toml").write_text('schema = 2\n[corpus]\ndir = "corpus"\n', encoding="utf-8")
    for name, text in files.items():
        (tmp_path / "corpus").mkdir(exist_ok=True)
        (tmp_path / "corpus" / name).write_text(textwrap.dedent(text), encoding="utf-8")
    return tmp_path


def test_events_are_read_in_order(tmp_path: Path) -> None:
    _corpus(tmp_path, {"timeline.toml": '''\
        [[event]]
        from = 1812
        to = 1812
        label = "Б"
        detail = "подробно"
        [[event]]
        from = 1773
        to = 1775
        label = "А"
        '''})
    with use(tmp_path):
        assert corpus_data.timeline_events() == (Era(1812, 1812, "Б", "подробно"), Era(1773, 1775, "А", ""))


def test_no_corpus_no_events(tmp_path: Path) -> None:
    (tmp_path / "verso.toml").write_text("schema = 2\n", encoding="utf-8")
    with use(tmp_path):
        assert corpus_data.timeline_events() == ()
    _corpus(tmp_path, {})
    with use(tmp_path):
        assert corpus_data.timeline_events() == ()


def test_eras_and_the_split_note_come_from_village_toml(tmp_path: Path) -> None:
    _village_toml(tmp_path, '''\
        schema = 1
        [timeline]
        split_note = "Линии не соединены."
        [[timeline.era]]
        from = 1700
        to = 1840
        label = "ясачные крестьяне"
        detail = "Мокша"
        ''')
    v = corpus_data.village(tmp_path)
    assert (v.eras, v.split_note) == ((Era(1700, 1840, "ясачные крестьяне", "Мокша"),), "Линии не соединены.")


def test_an_event_without_a_label_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path, {"timeline.toml": "[[event]]\nfrom = 1812\nto = 1812\n"})
    with use(tmp_path), pytest.raises(CorpusDataError, match=r"timeline\.toml: «event\.label» — ожидалась строка"):
        corpus_data.timeline_events()


# --- the corpus's estates (corpus/estates.toml) --------------------

ESTATES = '''\
[owner_aliases]
"Анны Петровны Первой" = "Анны Петровны Второй"

[maiden_families]
"Анны Петровны Второй" = "Первова"

[landlords]
PERVOV_IP = { villages = ["Вязовка"], token = "Ивана Петровича Первова" }
PERVOV_I = { villages = ["Березовка", "Вязовка"], token = "Ивана Первова" }

[[state_peasants]]
books = ["Вязовка", "Березовка"]
village = "Вязовка"
who = "государственные крестьяне прихода"

[[owners_and_state]]
parish = "Ольховка"
owners = { village = "Ольховка", in = "в Ольховке" }
state = { village = "Дубки", in = "в Дубках" }

[village_aliases]
"Вязовка СССР" = "Вязовка"
'''


def test_estates_are_read_from_the_corpus(tmp_path: Path) -> None:
    from verso.ru.corpus_data import Landlord, OwnersAndState, Side, StatePeasants
    _corpus(tmp_path, {"estates.toml": ESTATES})
    with use(tmp_path):
        e = corpus_data.estates()
    assert dict(e.owner_aliases) == {"Анны Петровны Первой": "Анны Петровны Второй"}
    assert dict(e.maiden_families) == {"Анны Петровны Второй": "Первова"}
    assert e.landlords["PERVOV_I"] == Landlord(("Березовка", "Вязовка"), "Ивана Первова")
    assert e.state_peasants == (StatePeasants(frozenset({"Вязовка", "Березовка"}), "Вязовка",
                                              "государственные крестьяне прихода"),)
    assert e.owners_and_state == (OwnersAndState("Ольховка", Side("Ольховка", "в Ольховке"), Side("Дубки", "в Дубках")),)
    assert dict(e.village_aliases) == {"Вязовка СССР": "Вязовка"}


def test_landlords_keep_their_order(tmp_path: Path) -> None:
    # The free-text reading takes the FIRST owner whose token a status holds:
    # «Ивана Петровича Первова» holds no «Ивана Первова», and the order decides the rest.
    _corpus(tmp_path, {"estates.toml": ESTATES})
    with use(tmp_path):
        assert list(corpus_data.estates().landlords) == ["PERVOV_IP", "PERVOV_I"]


def test_estates_without_a_corpus_are_empty(tmp_path: Path) -> None:
    (tmp_path / "verso.toml").write_text("schema = 2\n", encoding="utf-8")
    with use(tmp_path):
        assert corpus_data.estates() == corpus_data.Estates()


def test_estates_follow_the_workspace(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    _corpus(one, {"estates.toml": ESTATES})
    _corpus(two, {"estates.toml": '[owner_aliases]\n"А" = "Б"\n'})
    with use(one):
        assert "Анны Петровны Первой" in corpus_data.estates().owner_aliases
        with use(two):
            assert dict(corpus_data.estates().owner_aliases) == {"А": "Б"}
        assert "Анны Петровны Первой" in corpus_data.estates().owner_aliases


def test_a_landlord_without_token_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path, {"estates.toml": '[landlords]\nX_Y = { villages = ["А"] }\n'})
    with use(tmp_path), pytest.raises(CorpusDataError, match=r"estates\.toml: «landlords\.X_Y\.token» — ожидалась строка"):
        corpus_data.estates()


def test_an_unknown_key_of_estates_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path, {"estates.toml": '[owners]\n"А" = "Б"\n'})
    with use(tmp_path), pytest.raises(CorpusDataError, match=r"estates\.toml: неизвестный ключ «owners»"):
        corpus_data.estates()


def test_the_plugins_tables_are_the_modules_in_order():
    from verso.ru.plugin import PLUGIN
    assert list(PLUGIN.village_tables) == list(corpus_data.TABLES)


def test_a_village_error_speaks_both_languages(tmp_path: Path) -> None:
    """0.1.0's pilot: the messages that came from the core go through the plugin's catalog."""
    from verso.core import i18n
    (tmp_path / "village.toml").write_text('schema = 1\n[census]\norder = 1\n', encoding="utf-8")
    for lang, text in (("ru", "ожидался список"), ("en", "expected a list")):
        with i18n.use(lang):                    # read in the language of the print
            with pytest.raises(CorpusDataError) as caught:
                corpus_data.village(tmp_path)
            assert str(caught.value).endswith(f"village.toml: «census.order» — {text}")
