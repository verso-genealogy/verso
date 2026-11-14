"""Ids by rule r1 on the toy plugin's citation: the core counts and spells, the plugin
says what a record is cited by."""
from __future__ import annotations

import pytest

from tests.core.toy import note, notes, who
from verso.core.records.ids import Ids, RecordIds, book_key, entry_token, parse, persona_id, person_label, record_label

pytestmark = pytest.mark.usefixtures("toy_workspace")


def _book():
    return notes("Село", "1", "2", "3", 1850, note(3, who("Анна")), note(4, who("Пётр")), note(3, who("Иван")))


def test_toy_records_take_their_ids_and_a_repeat_takes_a_tilde():
    book = _book()
    ids = Ids()
    assert [ids.of(book, r) for r in book.records] == [
        "r1:Село/1-2-3/1850/note/3", "r1:Село/1-2-3/1850/note/4", "r1:Село/1-2-3/1850/note/3~2"]
    assert str(book_key(book)) == "r1:Село/1-2-3/1850/note"
    assert entry_token(book.records[1]) == ("", "4")
    counted = RecordIds()
    counted.walk({"book": book, "again": book, "other": 7})
    assert len(counted) == 3 and counted(book.records[2]) == "r1:Село/1-2-3/1850/note/3~2"


def test_a_toy_persona_id_and_parse_round_trip():
    book = _book()
    record_id = Ids().of(book, book.records[0])
    assert record_label(book.records[0]) == "Анна" == person_label(book.records[0].who)
    found = parse(persona_id(record_id, "who", None))
    assert (found.village, found.shelfmark, found.year, found.kind, found.token, found.repeat, found.persona) == (
        "Село", "1-2-3", 1850, "note", "3", None, "who")
    yearless = parse("r1:Село/1-2-3/note/3~2")
    assert (yearless.year, yearless.kind, yearless.token, yearless.repeat) == (None, "note", "3", 2)
