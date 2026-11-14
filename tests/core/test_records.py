"""The records codec on the toy plugin's vocabulary: the core's mechanism — the field
table's reading, the decoder, the schema — the plugin's table."""
from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.core.toy import Note, Notes, Sex, TOY_VOCABULARY, Who
from verso.core.records import SCHEMA_ID, FormatError
from verso.core.records.decode import decode_file
from verso.core.records.fields import (
    Vocabulary, attr_of, carries_persons, flatten, json_key, nest, param_spec, vocabulary)
from verso.core.records.schema import SCHEMA_FILE, build_schema, load_schema, main

pytestmark = pytest.mark.usefixtures("toy_workspace")


def _file(**document: Any) -> dict[str, Any]:
    note = {"id": "r1:V/1-2-3/1850/note/3", "kind": "note", "review": "reviewed",
            "written": {"number": 3}, "derived": {},
            "persons": [{"id": "r1:V/1-2-3/1850/note/3/who", "role": "who",
                         "written": {"full_name": "Анна", "gender": "female"}, "derived": {}}]}
    node = {"id": "r1:V/1-2-3/1850/note", "variable": "book", "kind": "notes",
            "written": {"village": "V", "shelfmark": {"fund": "1", "case": "3"}, "inventory": "2", "year": 1850},
            "derived": {}, "pages": [{"page": "5", "records": [note]}], **document}
    return {"schema": SCHEMA_ID, "village": "V", "file": "1850/v_notes_1850.py", "sha256": "0" * 64,
            "documents": [node, {"variable": "again", "alias_of": "book"}]}


def test_the_vocabulary_is_the_plugins():
    assert vocabulary() is TOY_VOCABULARY
    assert param_spec(Note, "person") == "person" and carries_persons(Note, "person")
    assert not carries_persons(Note, "number")
    assert attr_of(TOY_VOCABULARY.specs[Note], "who", None) == "who"


def test_a_toy_file_is_decoded_through_its_vocabulary():
    decoded = decode_file(_file())
    book = decoded["book"]
    assert decoded["again"] is book and type(book) is Notes
    assert list(vars(book)) == ["village", "fund", "inventory", "case", "year", "records", "reviewed", "_written"]
    (note,) = book.records
    assert type(note) is Note and (note.number, note.page, note.reviewed) == (3, "5", None)
    assert type(note.who) is Who and (note.who.name, note.who.gender) == ("Анна", Sex.FEMALE)


def test_a_toy_field_the_vocabulary_lacks_is_refused():
    with pytest.raises(FormatError, match=r"^book: Notes has no derived field 'shelf'$"):
        decode_file(_file(derived={"shelf": "x"}))
    with pytest.raises(FormatError, match="unknown kind of set 'births'"):
        decode_file(_file(kind="births"))


def test_the_toy_schema_is_written_from_its_vocabulary_and_validates_its_files():
    committed = json.loads(files("tests.core").joinpath(SCHEMA_FILE).read_text(encoding="utf-8"))
    assert committed == build_schema() == load_schema()
    assert main(["--check"]) == 0
    Draft202012Validator.check_schema(committed)
    Draft202012Validator(committed).validate(_file())
    assert set(committed["$defs"]) >= {"derived_who", "written_note", "record_note", "document_notes"}
    assert "status" not in committed["$defs"]


def test_a_toy_namespace_comes_back_as_the_same_graph():
    from tests.core.toy import note, notes, who
    from verso.core.records.encode import encode_namespace
    from verso.core.records.graph import first_difference
    from verso.core.records.ids import Ids

    book = notes("V", "1", "2", "3", 1850, note(3, who("Анна", Sex.FEMALE), page="5"),
                 note(4, who("Пётр"), page="5", reviewed=False))
    namespace = {"book": book, "again": book}
    doc = encode_namespace(namespace, village="V", file="1850/v_notes_1850.py", sha256="0" * 64, ids=Ids())
    Draft202012Validator(load_schema()).validate(doc)
    documents: Any = doc["documents"]
    first = documents[0]
    assert [r["id"] for r in first["pages"][0]["records"]] == [
        "r1:V/1-2-3/1850/note/3", "r1:V/1-2-3/1850/note/4"]
    assert first_difference(namespace, decode_file(json.loads(json.dumps(doc)))) is None


def _vocabulary(json_names: Any) -> Vocabulary:
    return Vocabulary(specs=TOY_VOCABULARY.specs, value_classes=(), param_to_attr=TOY_VOCABULARY.param_to_attr,
                      written_only={}, item_roles={}, person=Who, scalars={}, schema_package="tests.core",
                      json_names=json_names)


def test_json_names_are_injective():
    with pytest.raises(FormatError, match=r"Who: .*'name'.*'gender'|Who: .*'gender'.*'name'"):
        _vocabulary({Who: {"name": "gender"}})


def test_a_group_key_never_shadows_a_field():
    with pytest.raises(FormatError, match=r"Notes: .*'village'"):
        _vocabulary({Notes: {"fund": "village.fund"}})


def test_a_json_name_is_snake_case_and_one_level_deep():
    for bad in ("Fund", "a.b.c", "shelf mark", ".fund"):
        with pytest.raises(FormatError, match=r"Notes: "):
            _vocabulary({Notes: {"fund": bad}})


def test_a_person_slot_takes_no_json_name():
    with pytest.raises(FormatError, match=r"Note: .*'who'"):
        _vocabulary({Note: {"who": "writer"}})


def test_a_json_name_of_no_attribute_is_refused():
    with pytest.raises(FormatError, match=r"Notes: .*'shelf'"):
        _vocabulary({Notes: {"shelf": "shelfmark.shelf"}})


def test_a_group_nests_and_flattens():
    values = {"village": "V", "fund": "1", "inventory": "2", "case": "3"}
    nested = nest(Notes, values)
    assert nested == {"village": "V", "shelfmark": {"fund": "1", "case": "3"}, "inventory": "2"}
    assert list(nested) == ["village", "shelfmark", "inventory"]
    assert json_key(Notes, "fund") == "shelfmark.fund" and json_key(Notes, "year") == "year"
    flat = flatten(Notes, nested)
    assert flat == values and list(flat) == ["village", "fund", "case", "inventory"]
    with pytest.raises(KeyError):
        flatten(Notes, {"shelf": 1})


def test_a_partial_group_round_trips():
    from verso.core.records.encode import encode_namespace
    from verso.core.records.ids import Ids

    doc = _file()
    doc["documents"][0]["written"] = {"village": "V", "shelfmark": {"fund": "1"}, "year": 1850}
    doc["documents"][0]["derived"] = {"inventory": "2", "shelfmark": {"case": "3"}}
    again: Any = encode_namespace(decode_file(json.loads(json.dumps(doc))), village="V", file=doc["file"],
                                  sha256=doc["sha256"], ids=Ids())
    assert again["documents"][0]["written"] == doc["documents"][0]["written"]
    assert again["documents"][0]["derived"] == doc["documents"][0]["derived"]


def test_toy_ids_do_not_follow_json_names():
    from tests.core.toy import note, notes, who
    from verso.core.records.encode import encode_namespace
    from verso.core.records.ids import Ids

    doc = encode_namespace({"book": notes("V", "1", "2", "3", 1850, note(3, who("Анна"), page="5"))},
                           village="V", file="1850/v_notes_1850.py", sha256="0" * 64, ids=Ids())
    persona = doc["documents"][0]["pages"][0]["records"][0]["persons"][0]  # type: ignore[index]
    assert persona["id"] == "r1:V/1-2-3/1850/note/3/who" and persona["role"] == "who"
    assert persona["written"] == {"full_name": "Анна"}


def test_written_is_compared_without_its_order():
    from verso.core.records.graph import first_difference
    from verso.core.written import WRITTEN_ATTR

    a, b = Who("Анна"), Who("Анна")
    vars(a)[WRITTEN_ATTR] = {"name": "Анна", "gender": None}
    vars(b)[WRITTEN_ATTR] = {"gender": None, "name": "Анна"}
    assert first_difference(a, b) is None
    vars(b)[WRITTEN_ATTR] = {"gender": None, "name": "Пётр"}
    assert first_difference(a, b) == "_written.name: 'Анна' ≠ 'Пётр'"
