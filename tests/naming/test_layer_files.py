"""A names layer kept as three TSV files (`FilesLayer`): what it reads, what it writes, in what order."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.ru.gender import Gender
from verso.ru.naming.layer_files import FILES, FilesLayer, LayerFileError, is_base_source, read_rows
from verso.ru.naming.lexicon import FormsEntry, Layer, NameEntry, PatronymicEntry

M, F = Gender.MALE, Gender.FEMALE

NAMES = [NameEntry(M, "Зюзей", source="editor"),
         NameEntry(M, "Зюзя", ("Зюзей",), source="mk"),
         NameEntry(None, "Зюзя", ("Зюзей",), "Зюзя", source="mk"),
         NameEntry(F, "Зюзея", ("Зюзеия", "Зюзения"), source="wikidata:Q7")]
FORMS = [FormsEntry(M, "Зюзей", "Зюзья", "Зюзьевич", None, "Зюзьев", "Зюзьева", "editor"),
         FormsEntry(F, "Зюзея", genitive="Зюзеи", source="editor")]
PATRONYMICS = [PatronymicEntry(M, "Зюзьев", "Зюзей", "Зюзьевич", "editor"),
               PatronymicEntry(F, "Зюзьевна", source="editor", old="Зюзьева"),
               PatronymicEntry(None, "Зюзекова", source="editor")]


def _write(layer: FilesLayer) -> None:
    for entry in (*NAMES, *FORMS, *PATRONYMICS):
        layer.put(entry)


def test_every_entry_type_round_trips(tmp_path: Path) -> None:
    layer = FilesLayer(tmp_path, name="corpus", writable=True)
    _write(layer)
    loaded = FilesLayer(tmp_path, name="corpus", writable=False).load()
    assert isinstance(loaded, Layer) and loaded.name == "corpus" and not loaded.writable
    assert sorted(loaded.names.values(), key=repr) == sorted(NAMES, key=repr)
    assert sorted(loaded.forms.values(), key=repr) == sorted(FORMS, key=repr)
    assert sorted(loaded.patronymics.values(), key=repr) == sorted(PATRONYMICS, key=repr)
    for table in (loaded.names, loaded.forms, loaded.patronymics):
        assert all(entry.key == key for key, entry in table.items())


def test_files_are_sorted_by_key_whatever_the_order_of_put(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _write(FilesLayer(one, name="a", writable=True))
    other = FilesLayer(two, name="a", writable=True)
    for entry in reversed((*NAMES, *FORMS, *PATRONYMICS)):
        other.put(entry)
    for file in FILES.values():
        assert (one / file).read_bytes() == (two / file).read_bytes()
    lines = (one / "names.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "sex\tname\tbases\tcanonical\tsource\tnote"
    assert [line.split("\t")[:2] for line in lines[1:]] == [["", "Зюзя"], ["F", "Зюзея"], ["M", "Зюзей"], ["M", "Зюзя"]]


def test_put_replaces_its_key_and_keeps_the_note(tmp_path: Path) -> None:
    layer = FilesLayer(tmp_path, name="a", writable=True)
    _write(layer)
    path = tmp_path / "names.tsv"
    path.write_text(path.read_text(encoding="utf-8").replace("\tmk\t\n", "\tmk\tпочему так\n", 1), encoding="utf-8")
    layer.put(NameEntry(None, "Зюзя", ("Зюзей",), source="editor"))
    rows = read_rows(tmp_path)["names"]
    assert [(r["name"], r["source"], r["note"]) for _, r in rows if r["sex"] == ""] == [("Зюзя", "editor", "почему так")]
    assert len(rows) == len(NAMES)


def test_remove_drops_one_key_of_one_table(tmp_path: Path) -> None:
    layer = FilesLayer(tmp_path, name="a", writable=True)
    _write(layer)
    layer.remove("names", (M, "Зюзя"))
    layer.remove("patronymics", (None, "Зюзекова"))
    loaded = layer.load()
    assert (M, "Зюзя") not in loaded.names and (None, "Зюзя") in loaded.names
    assert (None, "Зюзекова") not in loaded.patronymics and len(loaded.forms) == 2
    with pytest.raises(KeyError):
        layer.remove("forms", (M, "Зюзя"))


def test_a_read_only_layer_refuses_to_write(tmp_path: Path) -> None:
    layer = FilesLayer(tmp_path, name="base", writable=False)
    with pytest.raises(TypeError, match="base"):
        layer.put(NAMES[0])
    with pytest.raises(TypeError, match="base"):
        layer.remove("names", NAMES[0].key)


def test_a_missing_table_is_empty_and_the_stamp_follows_the_files(tmp_path: Path) -> None:
    layer = FilesLayer(tmp_path, name="a", writable=True)
    empty = layer.stamp()
    assert layer.load().names == {}
    layer.put(NAMES[0])
    assert layer.stamp() != empty


def test_a_duplicate_key_is_refused_on_load(tmp_path: Path) -> None:
    layer = FilesLayer(tmp_path, name="a", writable=True)
    layer.put(NAMES[0])
    path = tmp_path / "names.tsv"
    path.write_text(path.read_text(encoding="utf-8") + "M\tЗюзей\t\t\tmk\t\n", encoding="utf-8")
    with pytest.raises(LayerFileError, match="Зюзей"):
        layer.load()


def test_a_value_the_file_cannot_hold_is_refused(tmp_path: Path) -> None:
    layer = FilesLayer(tmp_path, name="a", writable=True)
    with pytest.raises(ValueError, match="Зюз"):
        layer.put(NameEntry(M, "Зюз\tей", source="mk"))
    with pytest.raises(ValueError, match="Зюз"):
        layer.put(NameEntry(M, "Зюзей", ("Зюз|ей",), source="mk"))


def test_the_base_sources() -> None:
    for good in ("trebnik1906:5", "wikidata:Q42", "mk", "rule", "editor"):
        assert is_base_source(good)
    for bad in ("", "names.csv", "trebnik1906:", "trebnik1906:x", "wikidata:42", "wikidata:Q", "Петровский", "mk:1"):
        assert not is_base_source(bad)
