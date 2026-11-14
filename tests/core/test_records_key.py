"""A record's optional immutable `key` (records v1.x, additive): a property of the stored node, ignored by
decode and replay (it is no part of the graph), never written by the encoder, and moves no id (rule r1).
Code that rebuilds a node from objects does not carry it (the folder backend must copy it).

A toy DSL of its own, invented people.
"""
from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.core.test_records_replay import (  # noqa: F401
    _encode, _without_derived, entry, ledger, ledger_workspace, tag)
from verso.core.records import FormatError
from verso.core.records.decode import decode_file
from verso.core.records.graph import first_difference
from verso.core.records.replay import replay_file
from verso.core.records.schema import build_schema, check_keys


def _ns() -> dict[str, Any]:
    return {"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")), entry(2, tag("Мария")))}


def _records(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data["documents"][0]["pages"][0]["records"]


@pytest.mark.usefixtures("ledger_workspace")
def test_export_from_dsl_has_no_key() -> None:
    assert all("key" not in r for r in _records(_encode(_ns())))


@pytest.mark.usefixtures("ledger_workspace")
def test_a_node_with_a_key_decodes_and_replays_to_the_same_graph() -> None:
    ns = _ns()
    data = _encode(ns)
    _records(data)[0]["key"] = "k-1"
    assert first_difference(ns, decode_file(data)) is None
    assert first_difference(ns, replay_file(_without_derived(data))) is None


@pytest.mark.usefixtures("ledger_workspace")
def test_rebuilding_a_node_from_objects_does_not_carry_the_key() -> None:
    ns = _ns()
    data = _encode(ns)
    _records(data)[0]["key"] = "k-1"
    assert all("key" not in r for r in _records(_encode(decode_file(data))))   # the limit: copy it by hand


@pytest.mark.usefixtures("ledger_workspace")
def test_a_malformed_key_is_refused_and_the_schema_allows_it_optionally() -> None:
    for bad in ("", "a/b", 7):
        data = _encode(_ns())
        _records(data)[0]["key"] = bad
        with pytest.raises(FormatError):
            decode_file(data)
    props = build_schema()["$defs"]
    record = next(v for k, v in props.items() if k.startswith("record_"))
    assert record["properties"]["key"]["pattern"] == "^[^/]+$"
    assert "key" not in record["required"]


@pytest.mark.usefixtures("ledger_workspace")
def test_duplicate_keys_rejected() -> None:
    data = _encode(_ns())
    assert check_keys(data) == []
    _records(data)[0]["key"] = _records(data)[1]["key"] = "k-1"
    problems = check_keys(data)
    assert len(problems) == 1
    assert "documents[0].pages[0].records[0]" in problems[0] and "documents[0].pages[0].records[1]" in problems[0]


@pytest.mark.usefixtures("ledger_workspace")
def test_r1_unchanged_by_key() -> None:
    data = _encode(_ns())
    ids = [r["id"] for r in _records(data)]
    keyed = copy.deepcopy(data)
    for i, r in enumerate(_records(keyed)):
        r["key"] = f"k-{i}"
    assert [r["id"] for r in _records(keyed)] == ids
    again = replay_file(_without_derived(keyed))
    assert [r["id"] for r in _records(_encode(again))] == ids
