"""verso.core.places: the corpus's places, read through the workspace."""
from __future__ import annotations

import os
import re
import textwrap
from pathlib import Path

import pytest

from verso.core import places
from verso.core.places import PlacesError, add_place, add_spelling, parse, parse_body, render_body, verify
from verso.ru.linters.checks import unmapped_location
from verso.core.workspace import use

PLACES = """\
["а"]
same_as = "А"

["А"]
city = "село А"
country = "Россия"
familio = "00000000-0000-0000-0000-000000000001"

["Б"]
city = "деревня Б"
country = "Россия"
"""
_MORE = '\n["{key}"]\ncity = "{key}"\n'


def _workspace(root: Path, places_text: str | None = PLACES) -> Path:
    (root / "verso.toml").write_text('schema = 2\n[corpus]\ndir = "corpus"\n', encoding="utf-8")
    (root / "corpus").mkdir(exist_ok=True)
    if places_text is not None:
        (root / "corpus" / places.PLACES_FILE).write_text(places_text, encoding="utf-8")
    return root


def test_a_workspace_without_corpus_has_no_places(tmp_path: Path) -> None:
    (tmp_path / "verso.toml").write_text("schema = 2\n", encoding="utf-8")
    with use(tmp_path):
        current = places.current()
    assert (current.bodies, current.attributes, current.path) == ({}, {}, None)


def test_places_are_the_corpus_files(tmp_path: Path) -> None:
    with use(_workspace(tmp_path)):
        current = places.current()
    assert set(current.bodies) == {"а", "А", "Б"}
    assert current.key_for_body(current.bodies["а"]) == "А"          # a spelling reads back as its canonical
    assert current.key_for_body("") is None and current.key_for_body(None) is None
    assert current.attributes == {"familio": {"А": "00000000-0000-0000-0000-000000000001"}}
    assert current.path == (tmp_path / "corpus" / places.PLACES_FILE).resolve()


def test_reload_refills_the_same_object(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    with use(root):
        held = places.current().bodies
        (root / "corpus" / places.PLACES_FILE).write_text(PLACES + _MORE.format(key="В"), encoding="utf-8")
        assert places.reload() is places.current()
        assert "В" in held


def test_places_follow_the_workspace(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    _workspace(one)
    _workspace(two, _MORE.format(key="Г"))
    with use(one):
        assert "Б" in places.current().bodies
        with use(two):
            assert set(places.current().bodies) == {"Г"}
        assert "Б" in places.current().bodies


def test_ulc001_sees_a_place_added_at_runtime(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    dsl = root / "x.py"
    dsl.write_text(textwrap.dedent('''\
        birth_records("a", "f", "i", "c", "А", "Церковь", 1855,
            birth(1, Gender.MALE, father=person("Иван", residence="Новое")))
        '''), encoding="utf-8")
    with use(root):
        assert [str(i["message"])[:9] for i in unmapped_location.check_file_structured(dsl)] == ["[ULC001] "]
        path = root / "corpus" / places.PLACES_FILE
        path.write_text(PLACES + _MORE.format(key="Новое"), encoding="utf-8")
        places.reload()
        assert unmapped_location.check_file_structured(dsl) == []


TOML = '''\
# Места корпуса.

["а"]
same_as = "А"

# Село А — комментарий канона.
["А"]
city = "село А"
county = "Уезд"
state = "Губерния"
country = "Россия"
familio = "00000000-0000-0000-0000-000000000001"

["Б"]
city = "деревня Б"
country = "Россия"
'''


def test_a_place_renders_as_the_aligned_body() -> None:
    assert parse('["А"]\ncity = "село А"\ncountry = "Россия"\n').bodies["А"] == \
        'city    = "село А"\n' + " " * 18 + 'country = "Россия"'


def test_same_as_names_the_canonical() -> None:
    p = parse(TOML)
    assert p.bodies["а"] == p.bodies["А"]
    assert p.key_for_body(p.bodies["а"]) == "А"
    assert p.attributes == {"familio": {"А": "00000000-0000-0000-0000-000000000001"}}
    assert list(p.bodies) == ["а", "А", "Б"]


def test_the_canonical_wins_wherever_its_spelling_stands() -> None:
    p = parse('["А"]\ncity = "село А"\n["а"]\nsame_as = "А"\n')
    assert p.key_for_body(p.bodies["а"]) == "А"


@pytest.mark.parametrize("text, message", [
    ('["а"]\nsame_as = "Б"\n', "«а»: same_as «Б» — такого места нет"),
    ('["а"]\nsame_as = "б"\n["б"]\nsame_as = "В"\n["В"]\ncity = "В"\n', "«а»: same_as «б» — это само написание"),
    ('["а"]\nsame_as = "А"\ncity = "x"\n["А"]\ncity = "А"\n', "«а»: same_as не пишется вместе с полями"),
    ('["А"]\ncity = "А"\n["Б"]\ncity = "А"\n', "у «А» и «Б» одни поля — напишите same_as"),
    ('["А"]\ncity = "А"\nvillage = "x"\n', "«А»: неизвестный ключ «village»"),
    ('["А"]\nfamilio = "x"\n', "«А»: нет ни одного поля места"),
    ('["А"]\ncity = 1\n', "«А»: «city» — ожидалась строка"),
    # A spelling of a spelling, written after the spelling it names (review I1).
    ('["А"]\ncity = "село А"\n["Аа"]\nsame_as = "А"\n["ааа"]\nsame_as = "Аа"\n',
     "«ааа»: same_as «Аа» — это само написание, напишите same_as = «А»"),
    # What the HCL body cannot carry is refused on reading too, not only by add_place (I2).
    ('["А"]\ncity = "село \\"А\\""\n', "«А»: в поле «city» кавычка"),
    ('["А"]\ncity = "село\\\\А"\n', "«А»: в поле «city» .*обратная косая"),
    ('["А"]\ncity = "село\\nА"\n', "«А»: в поле «city» .*перевод строки"),
    ('["А"]\ncity = "${var.x}"\n', "«А»: в поле «city» .*\\$\\{"),
    ('["А"]\ncity = "%{if x}"\n', "«А»: в поле «city» .*%\\{"),
    # Blank and padded values (M1): a blank field is no field, a padded one the same field.
    ('["А"]\ncity = "  "\n', "«А»: нет ни одного поля места"),
    ('["А"]\ncity = "село"\n["Б"]\ncity = " село"\n', "у «А» и «Б» одни поля — напишите same_as"),
    # A TOML slip is said in Russian, naming what TOML says (M2).
    ('["А"]\ncity = "x"\n["А"]\ncity = "y"\n', "^не читается как TOML: "),
])
def test_a_broken_place_is_refused(text: str, message: str) -> None:
    with pytest.raises(PlacesError, match=message):
        parse(text)


def test_a_refusal_on_reading_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "places.toml"
    path.write_text('["А"]\ncity = "x"\n["А"]\ncity = "y"\n', encoding="utf-8")
    with pytest.raises(PlacesError, match=f"^{re.escape(str(path.resolve()))}: не читается как TOML: "):
        places.load(path)


def test_a_padded_value_reads_as_written_without_its_padding() -> None:
    assert parse('["А"]\ncity = " село А "\n').bodies["А"] == 'city    = "село А"'


def test_a_corpus_still_holding_places_py_is_refused(tmp_path: Path) -> None:
    """A worktree of a branch older than places.toml runs main's code (the editable
    install): its places are corpus/places.py, which main no longer reads — refused,
    rather than a corpus without places that drops every location block (review M3)."""
    root = _workspace(tmp_path, places_text=None)
    (root / "corpus" / "places.py").write_text("locations = {}\n", encoding="utf-8")
    with use(root), pytest.raises(PlacesError, match=r"places\.py.*обновите рабочую копию"):
        places.current()


def test_render_and_parse_are_inverse() -> None:
    for fields in ({"city": "А", "county": "Б", "state": "В", "country": "Г"},
                   {"county": "Б", "state": "В", "country": "Г"}, {"city": "А", "country": "Г"}):
        assert {k: v for k, v in parse_body(render_body(fields)).items() if v} == fields


def test_add_place_appends_and_verifies() -> None:
    new = add_place(TOML, "Новое", {"city": "деревня Новое", "state": "Губерния", "country": "Россия"},
                    "рожд. 1900 № 1")
    assert new.startswith(TOML)
    assert new.endswith('# рожд. 1900 № 1\n["Новое"]\ncity = "деревня Новое"\nstate = "Губерния"\ncountry = "Россия"\n')
    assert parse(new).key_for_body(parse(new).bodies["Новое"]) == "Новое"


def test_add_place_refuses_a_known_key_and_a_known_place() -> None:
    with pytest.raises(PlacesError, match="«Б» уже есть среди мест корпуса"):
        add_place(TOML, "Б", {"city": "x"}, "")
    with pytest.raises(PlacesError, match="это место уже записано под ключом «Б» — добавьте как его написание"):
        add_place(TOML, "Бэ", {"city": "деревня Б", "country": "Россия"}, "")


def test_add_spelling_goes_before_the_canonical_and_its_comment() -> None:
    new = add_spelling(TOML, "А.", "а", "пишут и так")
    assert '# пишут и так\n["А."]\nsame_as = "А"\n\n# Село А — комментарий канона.\n["А"]' in new
    assert parse(new).key_for_body(parse(new).bodies["А."]) == "А"


def test_add_spelling_of_a_place_that_is_not_there_is_refused() -> None:
    with pytest.raises(PlacesError, match="«Нет» нет среди мест корпуса"):
        add_spelling(TOML, "Нэт", "Нет", "")


def test_verify_refuses_an_edit_that_moves_an_old_place() -> None:
    with pytest.raises(PlacesError, match="правка изменила место «Б»"):
        verify(TOML, TOML.replace('city = "деревня Б"', 'city = "деревня Бэ"'), "Б")


def test_a_toml_string_survives_quotes_and_backslashes_in_comments() -> None:
    new = add_place(TOML, "Кавычки", {"city": "село К"}, 'запись «с \\"кавычками\\»')
    assert parse(new).bodies["Кавычки"] == 'city    = "село К"'


def test_a_value_with_a_quote_cannot_reach_the_hcl() -> None:
    with pytest.raises(PlacesError, match="кавычка"):
        add_place(TOML, "Кавычка", {"city": 'село "К"'}, "")


def test_load_reads_toml_by_its_suffix(tmp_path: Path) -> None:
    path = tmp_path / "places.toml"
    path.write_text(TOML, encoding="utf-8")
    assert places.load(path).key_for_body(parse(TOML).bodies["а"]) == "А"


def test_places_are_read_again_when_their_file_changes(tmp_path: Path) -> None:
    """Edited by hand, or by another process, the places are read again on the next
    question — as the estates are — and into the object every reader holds."""
    root = _workspace(tmp_path)
    path = root / "corpus" / places.PLACES_FILE
    with use(root):
        held = places.current()
        path.write_text(PLACES + _MORE.format(key="В"), encoding="utf-8")
        stamp = path.stat().st_mtime_ns + 1_000_000_000
        os.utime(path, ns=(stamp, stamp))
        assert places.current() is held
        assert "В" in held.bodies


def test_every_place_has_a_canonical() -> None:
    assert places.Places().canonicals == {}
    assert places.Places({"а": "x", "б": "y"}).canonicals == {"а": "а", "б": "б"}


def test_verify_refuses_an_edit_that_moves_a_familio_settlement() -> None:
    with pytest.raises(PlacesError, match="правка изменила место «А»"):
        verify(TOML, TOML.replace('familio = "00000000-0000-0000-0000-000000000001"\n', ""), "Б")


def test_verify_asks_what_the_new_key_reads_as() -> None:
    new = TOML + '\n["Бэ"]\nsame_as = "Б"\n'
    with pytest.raises(PlacesError, match="после правки «Бэ» читается как «Б»"):
        verify(TOML, new, "Бэ")
    assert verify(TOML, new, "Бэ", canonical="Б").canonicals["Бэ"] == "Б"


def test_an_edit_of_a_broken_file_names_the_file() -> None:
    broken = '["А"]\ncity = "x"\n["А"]\ncity = "y"\n'
    path = Path("/corpus/places.toml")
    with pytest.raises(PlacesError, match=r"^/corpus/places\.toml: не читается как TOML"):
        add_place(broken, "Б", {"city": "Б"}, "", path=path)
    with pytest.raises(PlacesError, match=r"^/corpus/places\.toml: не читается как TOML"):
        add_spelling(broken, "Б", "А", "", path=path)


def test_the_first_place_starts_the_file() -> None:
    assert add_place("", "А", {"city": "село А"}, "первое место") == '# первое место\n["А"]\ncity = "село А"\n'


def test_ru_reads_familio_as_a_place_attribute():
    from verso.core import plugins
    from verso.ru.plugin import PLUGIN
    assert PLUGIN.place_attributes == ("familio",)
    assert plugins.names_tables() == ("names.csv", "names_ignore.csv", "patronymics_ignore.csv")
    read = places.parse('["Вязовка"]\ncity = "Вязовка"\nfamilio = "u-1"\n')
    assert read.attributes == {"familio": {"Вязовка": "u-1"}}


def test_export_index_inputs_unchanged(tmp_path):
    """The records export's inputs keep their keys and order (the tables are the plugin's): in a workspace of the old
    tables, schema ≤ 5."""
    from verso.core import workspace
    from verso.core.pipeline import records
    with workspace.use(Path(__file__).resolve().parent / "fixtures" / "legacy-names"):
        assert list(records._input_files(tmp_path)) == [  # pyright: ignore[reportPrivateUsage]
            "unreviewed_on_geni.tsv", "names/names.csv", "names/names_ignore.csv", "names/patronymics_ignore.csv"]


def test_export_index_inputs_of_schema_6_are_each_layers_files(tmp_path):
    """Schema 6: each layer's files, keyed by its directory, and the base the layers sum over."""
    from verso.core import workspace
    from verso.core.pipeline import records
    (tmp_path / "verso.toml").write_text('schema = 6\nplugins = ["ru"]\n[names]\nlayers = ["corpus/names"]\n',
                                         encoding="utf-8")
    with workspace.use(tmp_path):
        keys = list(records._input_files(tmp_path))  # pyright: ignore[reportPrivateUsage]
        assert keys == ["unreviewed_on_geni.tsv", *(f"names/corpus/names/{f}" for f in (
            "names.tsv", "forms.tsv", "patronymics.tsv", "names.csv", "names_ignore.csv", "patronymics_ignore.csv"))]
        assert records.inputs(tmp_path)["names/base"].startswith("ru:")


def test_a_changed_base_stales_an_export(tmp_path, monkeypatch):
    """Schema 6: a release that changes the base's rows alone (its TSV files are data, not the code the export's
    `code` fingerprints) changes the export's inputs — an export of before is stale."""
    import shutil
    from verso.core import workspace
    from verso.core.pipeline import records
    from verso.ru.naming import layers
    from verso.ru.naming.layer_files import BASE, FilesLayer
    (tmp_path / "verso.toml").write_text('schema = 6\nplugins = ["ru"]\n', encoding="utf-8")
    copy = tmp_path / "base"
    copy.mkdir()
    for name in ("names.tsv", "forms.tsv", "patronymics.tsv"):
        (copy / name).write_bytes((BASE / name).read_bytes())
    monkeypatch.setitem(layers.BASES, "ru", lambda: FilesLayer(copy, name="base", writable=False))
    with workspace.use(tmp_path):
        before = records.inputs(tmp_path)
        with (copy / "names.tsv").open("a", encoding="utf-8") as f:
            f.write("M\tЗюзей\t\t\teditor\t\n")
        after = records.inputs(tmp_path)
    assert before["code"] == after["code"] and before["names/base"] != after["names/base"]
    shutil.rmtree(copy)
