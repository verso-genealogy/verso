"""Records rebuilt by their factories from `written` alone (`verso.core.records.replay`, 0.1.11, L10).

A toy DSL of its own, on the toy plugin: a tag derives its initial in its constructor, an entry
takes its month from a section wrapper — the value v1 keeps in `derived` alone.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.core.toy import TOY, TOY_CITE, TOY_DSL, Sex
from verso.core import plugins, workspace
from verso.core.plugins import RecordKind
from verso.core.records.encode import encode_namespace
from verso.core.records.fields import ClassSpec, ListOf, TypeSpec, Vocabulary, parse_fields
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import ReplayGap, replay_file
from verso.core.written import captures_written


class Tag:
    def __init__(self, name: str, gender: Sex | None = None) -> None:
        self.name = name
        self.gender = gender
        self.initial = name[:1]


class Entry:
    def __init__(self, number: int, who: Tag, *, page: str | None = None, reviewed: bool | None = None) -> None:
        self.number = number
        self.who = who
        self.page = page
        self.reviewed = reviewed
        self.month: str | None = None


class Ledger:
    def __init__(self, village: str, fund: str, inventory: str, case: str, year: int, *records: Entry,
                 reviewed: bool = True) -> None:
        self.village = village
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.year = year
        self.records = list(records)
        self.reviewed = reviewed


@captures_written
def tag(name: str, gender: Sex | None = None) -> Tag:
    return Tag(name, gender)


@captures_written
def tag_again(name: str, gender: Sex | None = None) -> Tag:
    return Tag(name, gender)


@captures_written
def entry(number: int, person: Tag, *, page: str | None = None, reviewed: bool | None = None) -> Entry:
    return Entry(number, person, page=page, reviewed=reviewed)


@captures_written
def ledger(village: str, fund: str, inventory: str, case: str, year: int, *records: Entry,
           reviewed: bool = True) -> Ledger:
    return Ledger(village, fund, inventory, case, year, *copy.deepcopy(records), reviewed=reviewed)


def section(month: str, *records: Entry) -> list[Entry]:
    out = []
    for record in records:
        r = copy.deepcopy(record)
        r.month = r.month or month
        out.append(r)
    return out


_TYPES: dict[str, TypeSpec] = {"Sex": Sex, "Entries": ListOf(Entry)}


def _vocabulary(tag_factories: tuple[Any, ...] = (tag,)) -> Vocabulary:
    def f(spec: str) -> tuple[Any, ...]:
        return parse_fields(spec, _TYPES)
    return Vocabulary(
        specs={s.cls: s for s in (
            ClassSpec(Tag, "who", f("name:str gender:Sex initial:str"), tag_factories),
            ClassSpec(Entry, "note", f("number:intstr who:person page:str reviewed:bool month:str"), (entry,)),
            ClassSpec(Ledger, "notes", f("village:str fund:str inventory:str case:str year:int records:Entries "
                                         "reviewed:bool=True"), (ledger,), "records"),
        )},
        value_classes=(), param_to_attr={Entry: {"person": "who"}}, written_only={}, item_roles={},
        person=Tag, scalars={}, schema_package="tests.core", context={Entry: frozenset({"month"})})


def _plugin(voc: Vocabulary) -> plugins.Plugin:
    dsl = dataclasses.replace(TOY_DSL, vocabulary=voc, cite=TOY_CITE,
                              kinds=(RecordKind("note", Ledger, (Entry,), "records"),))
    return dataclasses.replace(TOY, dsl=lambda: dsl)


@pytest.fixture
def ledger_workspace(tmp_path: Path) -> Iterator[None]:
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["toy"]\n', encoding="utf-8")
    with plugins.adding(_plugin(_vocabulary()), entry_points=False), workspace.use(tmp_path):
        yield


def _encode(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="V", file="1850/v_notes_1850.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _without_derived(node: Any, keep: frozenset[str] = frozenset()) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "derived":
                kept = {key: value for key, value in v.items() if key in keep}
                if kept:
                    out[k] = kept
            else:
                out[k] = _without_derived(v, keep)
        return out
    if isinstance(node, list):
        return [_without_derived(v, keep) for v in node]
    return node


@pytest.mark.usefixtures("ledger_workspace")
def test_replay_builds_by_the_factory() -> None:
    ns = {"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна", Sex.FEMALE), page="5"))}
    data = _encode(ns)
    assert data["documents"][0]["pages"][0]["records"][0]["persons"][0]["derived"] == {"initial": "А"}
    replayed = replay_file(_without_derived(data))
    book = replayed["book"]
    assert isinstance(book, Ledger) and book.records[0].who.initial == "А"
    assert first_difference(ns, replayed) is None


@pytest.mark.usefixtures("ledger_workspace")
def test_an_alias_is_the_very_object_it_names() -> None:
    book = ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))
    replayed = replay_file(_without_derived(_encode({"a": book, "b": book})))
    assert replayed["a"] is replayed["b"]


@pytest.mark.usefixtures("ledger_workspace")
def test_a_wrapper_value_comes_from_written_and_an_old_exports_from_derived() -> None:
    ns = {"book": ledger("V", "1", "2", "3", 1850, *section("march", entry(1, tag("Анна"))))}
    data = _encode(ns)
    record = data["documents"][0]["pages"][0]["records"][0]
    assert record["written"]["month"] == "march" and record["written"]["context"] == ["month"]
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    old = json.loads(json.dumps(data))                 # an export of before v1.x: the month in `derived`
    old_record = old["documents"][0]["pages"][0]["records"][0]
    del old_record["written"]["context"]
    old_record["derived"]["month"] = old_record["written"].pop("month")
    assert first_difference(ns, replay_file(_without_derived(old, keep=frozenset({"month"})))) is None
    found = first_difference(ns, replay_file(old, context=False))
    assert found is not None and found.endswith("month: str ≠ NoneType")


def test_two_factories_that_written_cannot_tell_apart_are_a_gap(tmp_path: Path) -> None:
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["toy"]\n', encoding="utf-8")
    with plugins.adding(_plugin(_vocabulary()), entry_points=False), workspace.use(tmp_path):
        data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))})
    with plugins.adding(_plugin(_vocabulary((tag, tag_again))), entry_points=False), workspace.use(tmp_path):
        with pytest.raises(ReplayGap) as gap:
            replay_file(data)
    assert gap.value.message.key == "records.replay.ambiguous_factory"
    assert gap.value.message.params["cls"] == "Tag"


@pytest.mark.usefixtures("ledger_workspace")
def test_a_malformed_node_is_a_format_error() -> None:
    from verso.core.records import FormatError
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))})
    data["documents"][0]["pages"][0]["records"][0]["written"]["no_such_field"] = 1
    with pytest.raises(FormatError):
        replay_file(data)
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))})
    del data["documents"][0]["pages"][0]["records"][0]["persons"][0]["role"]
    with pytest.raises(FormatError):
        replay_file(data)
