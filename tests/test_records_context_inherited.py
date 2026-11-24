"""A wrapper's value equal to its field's default, which the record set would have given otherwise: a name-list
entry's `reviewed`, whose field defaults to `True` (`reviewed:bool=True`), under `page(…, reviewed=True)` in a
`name_list_records(…, reviewed=False)`. The default alone would leave it out of the export, and the set's factory
would rebuild the entry held; the encoder writes it under `written.context` when it differs from the set's own
value of the field, so `replay_file(…, context=False)` and `replay_record` rebuild it released. Everything else
an entry wrote before is written as it was."""
from __future__ import annotations

import json
from typing import Any

import pytest

from verso.core.records.decode import decode_file
from verso.core.records.encode import encode_namespace, encode_record
from verso.core.records.fields import CONTEXT_KEY, vocabulary
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids, walk
from verso.core.records.replay import Position, replay_file, replay_record
from verso.core.records.schema import build_schema
from verso.ru.domain import Gender, page, person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.name_lists import ListedPerson, listed_person, name_list_records
from tests.test_linters_on_json_redundancy import _agree


def _list(*entries: ListedPerson, reviewed: bool) -> dict[str, Any]:
    return {"names": name_list_records("ЦГА", "7", "3", "41", "Примерово", 1917, *entries, document_type="Список",
                                       reviewed=reviewed)}


def _encode(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="Примерово", file="1917/names.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for run in data["documents"][0]["pages"] for r in run["records"]]


def _released_leaf() -> dict[str, Any]:
    """Лист 5 released in a held list: one entry under the page's flag, one that writes its own, one off the page."""
    return _list(*page("5", listed_person(1, person("Иванъ")), listed_person(2, person("Петръ"), reviewed=False),
                       reviewed=True),
                 listed_person(3, person("Сидоръ")), reviewed=False)


def test_the_pages_flag_is_written_when_the_set_says_otherwise() -> None:
    first, second, third = _entries(_encode(_released_leaf()))
    assert first["written"]["reviewed"] is True and first["written"][CONTEXT_KEY] == ["reviewed"]
    assert "reviewed" not in first["derived"]
    assert first["review"] == "reviewed"
    assert second["written"]["reviewed"] is False and CONTEXT_KEY not in second["written"]     # the call's own
    assert third["written"][CONTEXT_KEY] == ["reviewed"] and third["written"]["reviewed"] is False  # as before


def test_the_released_leaf_replays_from_written_alone() -> None:
    ns = _released_leaf()
    data = _encode(ns)
    assert first_difference(ns, replay_file(data, context=False)) is None
    assert first_difference(ns, replay_file(data)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_the_released_entry_replays_alone() -> None:
    data = _encode(_released_leaf())
    header = {k: v for k, v in data["documents"][0].items() if k != "pages"}
    run = data["documents"][0]["pages"][0]
    built = replay_record(run["records"][0], header=header, page=run["page"], position=Position(0))
    assert isinstance(built, ListedPerson) and built.reviewed is True


def test_the_view_of_one_entry_is_the_export_s_given_its_set() -> None:
    ns = _released_leaf()
    exported = _entries(_encode(ns))
    for (record_set, entry), node in zip(walk(ns), exported, strict=True):
        assert encode_record(entry, node["id"], record_set=record_set) == node


def test_a_flag_the_set_gives_writes_nothing_new() -> None:
    """The export as it was wherever the entry's value is the set's: a released leaf of a released list, a held
    leaf of a held list, an entry the set alone gave its flag."""
    for reviewed in (True, False):
        flag_on_page = _entries(_encode(_list(*page("5", listed_person(1, person("Иванъ")), reviewed=reviewed),
                                               reviewed=reviewed)))[0]
        bare = _entries(_encode(_list(*page("5", listed_person(1, person("Иванъ"))), reviewed=reviewed)))[0]
        assert flag_on_page == bare
        assert ("reviewed" in bare["written"]) is (not reviewed)       # a held entry has said so since v1.x


def test_a_held_leaf_of_a_released_list_is_as_before() -> None:
    entry = _entries(_encode(_list(*page("5", listed_person(1, person("Иванъ")), reviewed=False), reviewed=True)))[0]
    assert entry["written"]["reviewed"] is False and entry["written"][CONTEXT_KEY] == ["reviewed"]


def test_the_schema_takes_the_flag() -> None:
    import jsonschema
    jsonschema.validate(_encode(_released_leaf()), build_schema())


def test_rvr001_on_json_sees_the_pages_flag() -> None:
    """A page with no leaf releasing entries of a held list, one of them holding itself: the entry's flag is not the
    one it would inherit (the page's), and the walk, which reads the page's flag off the unflagged entry, says
    nothing — as the check on the source. Before, the unflagged entry replayed held and the walk took its run for
    the set's."""
    text = ('n = name_list_records("ЦГА", "7", "3", "41", "Примерово", 1917, *page(None, '
            'listed_person(1, person("Иванъ")), listed_person(2, person("Петръ"), reviewed=False), reviewed=True), '
            'document_type="Список", reviewed=False)')
    assert _agree(text, "RVR001") == 0


def test_a_field_the_set_does_not_give_stays_out() -> None:
    """A birth's `case` is the set's too, but the set gives no record its case, and its default is `None`: a birth
    that holds `None` under a set that names a case writes no `null` (byte neutrality of every other kind)."""
    births = birth_records("ЦГА", "7", "3", "755", "Примерово", "Церковь", 1850,
                           *page("2", birth(1, Gender.MALE, 3, 4, child=person("Иванъ")), reviewed=True), reviewed=False)
    assert births.records[0].case is None and births.case == "755"
    written = _encode({"births": births})["documents"][0]["pages"][0]["records"][0]["written"]
    assert "case" not in written and "case" not in written.get(CONTEXT_KEY, ())


def test_what_a_set_gives_is_declared() -> None:
    """The fields a set gives its records are the vocabulary's table, not every field of one name."""
    inherited = {cls.__name__: names for cls, names in vocabulary().inherited.items()}
    assert inherited["ListedPerson"] == {"reviewed"} and inherited["Divorce"] == {"reviewed"}
    assert all(names == {"reviewed"} for names in inherited.values())


def test_one_record_is_written_with_its_set_or_says_it_has_none() -> None:
    ns = _released_leaf()
    record_set, entry = next(iter(walk(ns)))
    with pytest.raises(TypeError):
        encode_record(entry, "r1:test/0")       # type: ignore[call-arg]
    bare = encode_record(entry, "r1:test/0", record_set=None)
    assert "reviewed" not in bare["written"]
    assert encode_record(entry, "r1:test/0", record_set=record_set)["written"]["reviewed"] is True
