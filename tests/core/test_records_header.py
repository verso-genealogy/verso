"""A records file's optional header keys (records v1.x, additive): `vocabulary` (the plugin that wrote the
records and the version of its vocabulary) and `lang` (the book's language by default, BCP 47). Both come
from the plugin registry; the core names neither. The graph reads neither; a file of a newer
vocabulary than its plugin knows is refused by name, by decode and by replay alike.

A toy DSL of its own, invented people.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from tests.core.test_records_replay import (  # noqa: F401
    _encode, _plugin, _vocabulary, _without_derived, entry, ledger, ledger_workspace, tag)
from verso.core import plugins, workspace
from verso.core.records import FormatError
from verso.core.records.decode import decode_file
from verso.core.records.graph import first_difference
from verso.core.records.replay import replay_file
from verso.core.records.schema import build_schema


def _ns() -> dict[str, Any]:
    return {"book": ledger("V", "1", "2", "3", 1850, entry(1, tag("Анна")))}


def _versioned(version: int = 3) -> plugins.Plugin:
    return dataclasses.replace(_plugin(_vocabulary()), vocabulary=("toy", version), default_lang="tt-Latn")


@pytest.fixture
def versioned_workspace(tmp_path: Any) -> Any:
    (tmp_path / "verso.toml").write_text('schema = 4\nplugins = ["toy"]\n', encoding="utf-8")
    with plugins.adding(_versioned(), entry_points=False), workspace.use(tmp_path):
        yield


@pytest.mark.usefixtures("versioned_workspace")
def test_header_names_plugin_and_version() -> None:
    data = _encode(_ns())
    assert data["vocabulary"] == {"plugin": "toy", "version": 3}
    assert data["lang"] == "tt-Latn"


@pytest.mark.usefixtures("versioned_workspace")
def test_header_roundtrip_is_invisible_to_graph() -> None:
    ns = _ns()
    data = _encode(ns)
    assert first_difference(ns, decode_file(data)) is None
    assert first_difference(ns, replay_file(_without_derived(data))) is None


@pytest.mark.usefixtures("versioned_workspace")
def test_old_export_without_header_keys_reads() -> None:
    ns = _ns()
    data = _encode(ns)
    del data["vocabulary"], data["lang"]
    assert first_difference(ns, decode_file(data)) is None
    assert first_difference(ns, replay_file(_without_derived(data))) is None


@pytest.mark.usefixtures("versioned_workspace")
def test_unknown_vocabulary_version_is_refused_by_name() -> None:
    data = _encode(_ns())
    data["vocabulary"]["version"] = 4
    with pytest.raises(FormatError) as refused:
        decode_file(data)
    assert "«toy»" in str(refused.value) and "version 4" in str(refused.value)
    data["vocabulary"]["version"] = 3
    decode_file(data)                                   # the plugin's own version reads


@pytest.mark.usefixtures("versioned_workspace")
def test_replay_refuses_a_newer_vocabulary_as_decode_does() -> None:
    data = _encode(_ns())
    data["vocabulary"]["version"] = 99
    with pytest.raises(FormatError) as by_decode:
        decode_file(data)
    with pytest.raises(FormatError) as by_replay:
        replay_file(_without_derived(data))
    assert str(by_replay.value) == str(by_decode.value)
    assert "«toy»" in str(by_replay.value) and "version 99" in str(by_replay.value)
    data["vocabulary"]["version"] = 3
    replay_file(_without_derived(data))                 # the plugin's own version reads


@pytest.mark.usefixtures("versioned_workspace")
def test_a_malformed_vocabulary_is_refused() -> None:
    for bad in ("toy", {"plugin": "toy"}, {"plugin": "toy", "version": "1"}, {"plugin": 1, "version": 1}):
        data = _encode(_ns())
        data["vocabulary"] = bad
        with pytest.raises(FormatError):
            decode_file(data)


@pytest.mark.usefixtures("ledger_workspace")
def test_core_without_plugin_writes_no_vocabulary() -> None:
    data = _encode(_ns())                               # a plugin that declares neither
    assert "vocabulary" not in data and "lang" not in data


@pytest.mark.usefixtures("versioned_workspace")
def test_the_schema_allows_both_keys_optionally() -> None:
    file = build_schema()["$defs"]["file"]
    assert {"vocabulary", "lang"} <= set(file["properties"])
    assert not {"vocabulary", "lang"} & set(file["required"])
