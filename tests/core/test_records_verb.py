"""A class with several factories `written` cannot tell apart names the one that built each object
(`Vocabulary.verbs`, `written.verb`; records v1.x, additive).

A toy DSL of its own: a note comes from `plain_tag` or `loud_tag`, which take the same keys.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tests.core.test_records_replay import (
    Tag, _encode, _plugin, _vocabulary, _without_derived, entry, ledger, ledger_workspace)  # noqa: F401
from verso.core import plugins, workspace
from verso.core.records import FormatError
from verso.core.records.fields import Vocabulary
from verso.core.records.graph import first_difference
from verso.core.records.replay import ReplayGap, replay_file
from verso.core.records.schema import build_schema
from verso.core.written import VERB_ATTR, captures_written


@captures_written
def plain_tag(name: str) -> Tag:
    made = Tag(name)
    setattr(made, VERB_ATTR, "plain_tag")
    return made


@captures_written
def loud_tag(name: str) -> Tag:
    made = Tag(name.upper())
    setattr(made, VERB_ATTR, "loud_tag")
    return made


def _verb_vocabulary() -> Vocabulary:
    base = _vocabulary((plain_tag, loud_tag))
    return dataclasses.replace(base, verbs={Tag: {"plain_tag": plain_tag, "loud_tag": loud_tag}})


@pytest.fixture
def verb_workspace(tmp_path: Path):
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["toy"]\n', encoding="utf-8")
    with plugins.adding(_plugin(_verb_vocabulary()), entry_points=False), workspace.use(tmp_path):
        yield


def _tags(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for r in data["documents"][0]["pages"][0]["records"] for p in r["persons"]]


@pytest.mark.usefixtures("verb_workspace")
def test_card_verb_roundtrip() -> None:
    ns = {"book": ledger("V", "1", "2", "3", 1850, entry(1, plain_tag("Анна")), entry(2, loud_tag("Мария")))}
    data = _encode(ns)
    assert [p["written"]["verb"] for p in _tags(data)] == ["plain_tag", "loud_tag"]
    replayed: Any = replay_file(_without_derived(data))
    assert first_difference(ns, replayed) is None
    assert [e.who.name for e in replayed["book"].records] == ["Анна", "МАРИЯ"]


@pytest.mark.usefixtures("verb_workspace")
def test_the_verb_is_in_the_schema_and_a_foreign_one_is_refused() -> None:
    written = build_schema()["$defs"]["written_who"]
    assert written["properties"]["verb"] == {"enum": ["plain_tag", "loud_tag"]}
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, plain_tag("Анна")))})
    _tags(data)[0]["written"]["verb"] = "quiet_tag"
    with pytest.raises(FormatError):
        replay_file(data)


def test_old_export_without_verb_still_replays_when_unambiguous(tmp_path: Path) -> None:
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["toy"]\n', encoding="utf-8")
    ns = {"book": ledger("V", "1", "2", "3", 1850, entry(1, plain_tag("Анна")))}
    with plugins.adding(_plugin(_verb_vocabulary()), entry_points=False), workspace.use(tmp_path):
        data = json.loads(json.dumps(_encode(ns)))
    for persona in _tags(data):
        del persona["written"]["verb"]
    with plugins.adding(_plugin(_vocabulary((plain_tag,))), entry_points=False), workspace.use(tmp_path):
        book: Any = replay_file(_without_derived(data))["book"]
        assert book.records[0].who.name == "Анна"   # one factory
    with plugins.adding(_plugin(_verb_vocabulary()), entry_points=False), workspace.use(tmp_path):
        with pytest.raises(ReplayGap) as gap:                                              # two: a gap
            replay_file(_without_derived(data))
    assert gap.value.message.key == "records.replay.ambiguous_factory"
    assert gap.value.message.params["factories"] == ["plain_tag", "loud_tag"]


@pytest.mark.usefixtures("ledger_workspace")
def test_a_class_without_verbs_writes_none() -> None:
    from tests.core.test_records_replay import tag
    data = _encode({"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))})
    assert "verb" not in _tags(data)[0]["written"]

