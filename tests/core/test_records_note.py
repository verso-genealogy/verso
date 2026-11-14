"""The `#` notes of a DSL file on its records JSON (records v1.x, additive): the plugin reads them
(`Plugin.notes`), the export puts each on the node its anchor names (`verso.core.records.notes`) —
and binds none to a record it cannot hold the plugin's count to. Invisible to decode, replay and
the graph; the core names no plugin.

The toy plugin, with a toy reader of its own; invented people.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.core.test_records_replay import (  # noqa: F401
    _encode, _without_derived, entry, ledger, ledger_workspace, tag)
from tests.core.toy import TOY
from verso.core import plugins, workspace
from verso.core.pipeline.records import export_village
from verso.core.plugins import SourceNotes
from verso.core.records import FormatError
from verso.core.records import ui
from verso.core.records.decode import decode_file
from verso.core.records.graph import first_difference
from verso.core.records.notes import COUNT, NUMBER, UNCOUNTED, place_notes, record_nodes
from verso.core.records.replay import replay_file
from verso.core.records.schema import build_schema

HEAD = "from tests.core.toy import note, notes, who\n\n"
COMMENTED = HEAD + '''\
# A book of the toy village.
book = notes("V", "1", "2", "3", 1850,
    # The first note.
    note(1, who("Анна")),
    note(2, who("Пётр")),
)
'''
PLAIN = HEAD + 'book = notes("V", "1", "2", "3", 1850, note(1, who("Анна")), note(2, who("Пётр")))\n'


def toy_notes(source: str) -> SourceNotes:
    """The toy's reader: a block right above `note(` is that record's, any other the file's."""
    lines = source.splitlines()
    numbers: list[int | None] = []
    found: list[dict[str, object]] = []
    block: list[str] = []
    for line in lines:
        text = line.strip()
        if text.startswith("#"):
            block.append(text.removeprefix("#").strip())
            continue
        called = re.match(r"note\((\d+)", text)
        if block:
            anchor = {"to": "record", "record": len(numbers)} if called else {"to": "file"}
            found.append({"text": "\n".join(block), "anchor": anchor})
            block = []
        if called:
            numbers.append(int(called.group(1)))
    return SourceNotes(notes=found, numbers=numbers)


def _village(root: Path, source: str) -> Path:
    village = root / "V"
    (village / "1850").mkdir(parents=True)
    (village / "1850" / "v_notes_1850.py").write_text(source, encoding="utf-8")
    return village


@pytest.fixture
def reader(tmp_path: Path) -> Iterator[Callable[[Callable[[str], SourceNotes] | None], None]]:
    """A toy workspace whose plugin reads notes with the reader given (None: reads none)."""
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["toy"]\n', encoding="utf-8")
    stack: list[Any] = []

    def use(read: Callable[[str], SourceNotes] | None) -> None:
        block = plugins.adding(dataclasses.replace(TOY, notes=read), entry_points=False)
        block.__enter__()
        stack.append(block)

    with workspace.use(tmp_path):
        yield use
        for block in reversed(stack):
            block.__exit__(None, None, None)


def _export(tmp_path: Path, source: str) -> tuple[dict[str, Any], Any]:
    village = _village(tmp_path / "data", source)
    exported = export_village(village, tmp_path / "rec")
    doc = json.loads((tmp_path / "rec" / "V" / "1850" / "v_notes_1850.json").read_text(encoding="utf-8"))
    return doc, exported


def _keys(node: object) -> set[str]:
    if isinstance(node, dict):
        return {k for k, v in node.items() for k in (k, *_keys(v))}
    if isinstance(node, list):
        return {k for item in node for k in _keys(item)}
    return set()


def test_the_export_puts_each_note_on_the_node_it_is_about(reader: Any, tmp_path: Path) -> None:
    reader(toy_notes)
    doc, exported = _export(tmp_path, COMMENTED)
    assert doc["note"] == [{"text": "A book of the toy village.", "anchor": {"to": "file"}}]
    first, second = record_nodes(doc)
    assert first["note"] == [{"text": "The first note.", "anchor": {"to": "record", "record": 0}}]
    assert "note" not in second and "note" not in doc["documents"][0]
    assert (exported.notes, exported.manual_notes, exported.unbound) == (2, 0, {})


def test_export_without_comments_has_no_note_keys(reader: Any, tmp_path: Path) -> None:
    reader(toy_notes)
    doc, exported = _export(tmp_path, PLAIN)
    assert "note" not in _keys(doc)
    assert (exported.notes, exported.manual_notes) == (0, 0)


def test_core_without_plugin_notes_exports_no_notes(reader: Any, tmp_path: Path) -> None:
    reader(None)                                         # the toy as it is: no reader
    doc, exported = _export(tmp_path, COMMENTED)
    assert "note" not in _keys(doc)
    assert (exported.notes, exported.manual_notes) == (0, 0)
    assert plugins.source_notes(COMMENTED) is None


@pytest.mark.usefixtures("ledger_workspace")
def test_note_roundtrip_is_invisible_to_graph() -> None:
    ns = {"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")), entry(2, tag("Мария")))}
    bare = _encode(ns)
    noted = copy.deepcopy(bare)
    placed = place_notes(noted, SourceNotes(notes=[
        {"text": "**Книга**", "anchor": {"to": "file"}},
        {"text": "Анна", "anchor": {"to": "record", "record": 0}},
        {"text": "both", "anchor": {"to": "range", "record": 0, "end": 1}},
        {"text": "her name", "anchor": {"to": "argument", "record": 1, "arg": "who"}},
    ], numbers=[1, 2]), ["1", "2"])
    assert (placed.bound, placed.manual) == (4, 0)
    assert noted != bare
    for data in (bare, noted):
        assert first_difference(ns, decode_file(data)) is None
        assert first_difference(ns, replay_file(_without_derived(data))) is None
    assert _encode(decode_file(noted)) == bare            # a node rebuilt from objects carries none


@pytest.mark.usefixtures("ledger_workspace")
def test_an_argument_is_named_as_the_json_names_it() -> None:
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")), entry(2, tag("Мария")))})
    node = record_nodes(data)[1]
    keys, slots = set(node["written"]), {p["id"].rpartition("/")[2] for p in node["persons"]}
    placed = place_notes(data, SourceNotes(notes=[
        {"text": "a person", "anchor": {"to": "argument", "record": 1, "arg": "who"}},
        {"text": "a slot already", "anchor": {"to": "field", "record": 1, "arg": "who"}},
        {"text": "a value", "anchor": {"to": "field", "record": 1, "arg": "number"}},
        {"text": "no such name", "anchor": {"to": "argument", "record": 1, "arg": "nowhere"}},
        {"text": "a wrapper", "anchor": {"to": "range", "record": 0, "end": 1, "arg": "page"}},
    ], numbers=[1, 2]), ["1", "2"])
    by_text = {n["text"]: n["anchor"] for n in node["note"]}
    assert "number" in keys and "who" in slots
    assert by_text["a person"] == {"to": "argument", "record": 1, "arg": "who"}
    assert by_text["a slot already"] == {"to": "field", "record": 1, "arg": "who"}
    assert by_text["a value"] == {"to": "field", "record": 1, "arg": "number"}
    assert by_text["no such name"] == {"to": "record", "record": 1}      # no name in the JSON: the record's
    assert record_nodes(data)[0]["note"][0]["anchor"] == {"to": "range", "record": 0, "end": 1, "arg": "page"}
    assert (placed.bound, placed.manual) == (5, 0)


@pytest.mark.usefixtures("ledger_workspace")
@pytest.mark.parametrize("anchor", [
    {"to": "record", "record": 2},                       # past the last record
    {"to": "record", "record": -1},
    {"to": "record", "record": None},
    {"to": "record", "record": True},
    {"to": "range", "record": 1, "end": 0},              # ends before it begins
    {"to": "range", "record": 0, "end": 2},              # ends past the last
    {"to": "range", "record": 0},                        # no end
    {"to": "field", "record": 0, "end": 1, "arg": "page"},  # an end where none belongs
    {"to": "elsewhere", "record": 0},                    # no anchor of the format's
])
def test_note_anchor_points_at_existing_record(anchor: dict[str, Any]) -> None:
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")), entry(2, tag("Мария")))})
    placed = place_notes(data, SourceNotes(notes=[{"text": "?", "anchor": anchor}], numbers=[1, 2]), ["1", "2"])
    assert data["note"] == [{"text": "?", "anchor": {"to": "manual"}}]
    assert all("note" not in r for r in record_nodes(data))
    assert (placed.bound, placed.manual, placed.refused) == (0, 1, None)


@pytest.mark.usefixtures("ledger_workspace")
@pytest.mark.parametrize(("numbers", "why"), [
    (None, UNCOUNTED),                                   # the plugin could not count the records
    ([1], COUNT),                                        # it counted one, the export holds two
    ([1, 2, 3], COUNT),
    ([1, 3], NUMBER),                                    # its second record is not the export's second
])
def test_a_count_the_export_does_not_hold_binds_no_note_to_a_record(numbers: list[int] | None, why: str) -> None:
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")), entry(2, tag("Мария")))})
    placed = place_notes(data, SourceNotes(notes=[
        {"text": "a", "anchor": {"to": "record", "record": 1}},
        {"text": "b", "anchor": {"to": "file"}},
    ], numbers=numbers), ["1", "2"])
    assert placed.refused == why
    assert [n["anchor"] for n in data["note"]] == [{"to": "manual"}, {"to": "file"}]
    assert all("note" not in r for r in record_nodes(data))


@pytest.mark.usefixtures("ledger_workspace")
def test_a_number_the_plugin_could_not_read_is_not_held_against_it() -> None:
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")), entry(2, tag("Мария")))})
    placed = place_notes(data, SourceNotes(notes=[{"text": "a", "anchor": {"to": "record", "record": 1}}],
                                           numbers=[None, 2]), ["1", "2"])
    assert placed.refused is None and record_nodes(data)[1]["note"][0]["text"] == "a"


@pytest.mark.usefixtures("ledger_workspace")
def test_the_plugins_manual_note_goes_on_the_file_marked() -> None:
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))})
    placed = place_notes(data, SourceNotes(notes=[{"text": "?", "anchor": {
        "to": "manual", "record": None, "end": None, "arg": None}}], numbers=None), ["1"])
    assert data["note"] == [{"text": "?", "anchor": {"to": "manual"}}]
    assert (placed.bound, placed.manual) == (0, 1)


@pytest.mark.usefixtures("ledger_workspace")
def test_the_schema_allows_notes_optionally_and_decode_refuses_a_malformed_one() -> None:
    from jsonschema import Draft202012Validator
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))})
    place_notes(data, SourceNotes(notes=[{"text": "f", "anchor": {"to": "file"}},
                                         {"text": "r", "anchor": {"to": "field", "record": 0, "arg": "page"}}],
                                  numbers=[1]), ["1"])
    schema = build_schema()
    Draft202012Validator(schema).validate(data)
    defs = schema["$defs"]
    assert "note" not in defs["file"]["required"]
    assert all("note" not in v["required"] for k, v in defs.items() if k.startswith("record_"))
    for bad in ([], "text", [{"text": 1, "anchor": {"to": "file"}}], [{"text": "x", "anchor": {"to": "x"}}]):
        for where in (data, record_nodes(data)[0]):
            broken = copy.deepcopy(data)
            target = broken if where is data else record_nodes(broken)[0]
            target["note"] = bad
            with pytest.raises(FormatError):
                decode_file(broken)
            assert not Draft202012Validator(schema).is_valid(broken)


@pytest.mark.usefixtures("toy_workspace")
def test_the_review_pages_schema_shows_no_note() -> None:
    assert ui.main(["--check"]) == 0                    # ui-v1.json as committed: notes are no field
