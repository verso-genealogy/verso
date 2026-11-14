"""verso.ru.persons.corpus — the people of a corpus's DSL files, kept by the files' stamps
— what Verso's whole-person suggestions are drawn from."""
from __future__ import annotations

from pathlib import Path

from verso.ru.persons.corpus import PeopleCorpus
from verso.ru.persons.people import RecordContext
from tests import village_fixture as fixture

BIRTHS = "Маниловка/1900/manilovka_births_1900.py"
# The godfather of № 2.
GODFATHER = 'person("Никифоръ", "Андреевъ", "Образцовъ")'


def test_a_file_changed_on_disk_is_read_again(tmp_path: Path) -> None:
    root = fixture.root(tmp_path, BIRTHS)
    corpus = PeopleCorpus(root, recheck=0.0)
    assert not corpus.index().suggest_for("зос", "", "", RecordContext("Маниловка"))
    path = root / BIRTHS
    text = path.read_text(encoding="utf-8")
    assert GODFATHER in text
    path.write_text(text.replace(GODFATHER, 'person("Зосима", "Петровъ")', 1), encoding="utf-8")
    corpus.touched()
    assert [s.name for s in corpus.index().suggest_for("зос", "", "", RecordContext("Маниловка"))] == ["Зосима"]


def test_a_file_that_does_not_import_names_nobody(tmp_path: Path) -> None:
    root = fixture.root(tmp_path, BIRTHS)
    (root / BIRTHS).write_text("raise ValueError\n", encoding="utf-8")
    assert len(PeopleCorpus(root, recheck=0.0).index()) == 0


def test_the_index_is_kept_between_two_questions(tmp_path: Path) -> None:
    corpus = PeopleCorpus(fixture.root(tmp_path, BIRTHS), recheck=3600.0)
    assert corpus.index() is corpus.index()
