"""The Russian books replayed from `written` alone (`verso.core.records.replay`, 0.1.11, L10 part 1).

Every file of the mini corpus and the codec's fixture: encoded, stripped of every derived value
(what a wrapper set — the vocabulary's `context`, a section's month, a лист's provenance — stands
in `written` since records v1.x), replayed by the DSL's factories, and compared with the graph the
DSL built.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import records_fixture as fixture
import village_fixture
from verso.core import workspace
from verso.core.pipeline.load import load_module, record_namespace
from verso.core.records.encode import encode_namespace
from verso.core.records.fields import group, ungroup, vocabulary
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import ReplayGap, replay_file

MINI_FILES = sorted(p.relative_to(village_fixture.MINI / "root").as_posix()
                    for p in (village_fixture.MINI / "root").glob("*/*/*.py"))


def _encode(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="Маниловка", file="1900/f.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _without_derived(node: Any) -> Any:
    """`node` with every `derived` cut: what replay may read is `written` alone."""
    if isinstance(node, list):
        return [_without_derived(x) for x in node]
    if not isinstance(node, dict):
        return node
    return {k: _without_derived(v) for k, v in node.items() if k != "derived"}


def as_before_v1x(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """`data` as an export of before records v1.x wrote it: each wrapper's value back in
    `derived`, no `written.context`; how many values moved."""
    voc = vocabulary()
    old = json.loads(json.dumps(data))
    moved = 0
    for doc in old["documents"]:
        for run in doc.get("pages", ()):
            for record in run["records"]:
                marked = record.get("written", {}).pop("context", None)
                if not marked:
                    continue
                cls = voc.by_code[record["kind"]]
                written = ungroup(cls, record["written"])
                derived = ungroup(cls, record.get("derived", {}))
                for key in marked:
                    derived[key] = written.pop(key)
                    moved += 1
                record["written"], record["derived"] = group(written), group(derived)
    return old, moved


@pytest.fixture
def mini(tmp_path: Path):
    root = village_fixture.root(tmp_path)
    village_fixture.workspace(tmp_path, root)
    with workspace.use(root):
        yield root


@pytest.mark.parametrize("rel", MINI_FILES)
def test_derived_values_come_from_the_calls_not_from_derived(mini: Path, rel: str) -> None:
    ns = record_namespace(load_module(mini / rel))
    data = _encode(ns)
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    old, moved = as_before_v1x(data)
    assert first_difference(ns, replay_file(old)) is None       # an export of before: from `derived`
    if "births" in rel or "deaths" in rel:
        assert moved, "a section's month is the context the test is about"


def _without_verbs(data: dict[str, Any]) -> dict[str, Any]:
    """An export of before the verb was written: the cards' `written` without `verb`."""
    old = json.loads(json.dumps(data))
    for doc in old["documents"]:
        for run in doc.get("pages", ()):
            for record in run["records"]:
                record.get("written", {}).pop("verb", None)
    return old


def test_the_codecs_fixture_replays_whole_cards_included() -> None:
    ns = fixture.namespace()
    assert first_difference(ns, replay_file(_without_derived(_encode(ns)), context=False)) is None


def test_a_card_carries_the_verb_that_built_it() -> None:
    cards = fixture.namespace()["cards"]
    verbs = [r["written"]["verb"] for r in _encode({"cards": cards})["documents"][0]["pages"][0]["records"]]
    assert verbs == ["wwi_record", "wwii_record", "criminal_record"]


def test_an_export_without_verbs_leaves_a_wwi_and_a_wwii_card_a_gap() -> None:
    """Both take the same keys and either enum of document types: an export of before `verb`
    cannot say which was called, so replay says so rather than guess."""
    with pytest.raises(ReplayGap) as gap:
        replay_file(_without_verbs(_encode({"cards": fixture.namespace()["cards"]})))
    assert gap.value.message.key == "records.replay.ambiguous_factory"
    assert gap.value.message.params["cls"] == "ExternalSourceRecord"
    assert gap.value.message.params["factories"] == ["wwi_record", "wwii_record"]


def test_an_old_export_without_context_misses_a_sections_month(mini: Path) -> None:
    ns = record_namespace(load_module(mini / "Маниловка/1900/manilovka_births_1900.py"))
    found = first_difference(ns, replay_file(as_before_v1x(_encode(ns))[0], context=False))
    assert found is not None and "_month" in found


def test_a_card_without_a_verb_that_only_one_factory_takes_still_replays() -> None:
    from verso.ru.dsl import criminal_record, external_source_records, person
    cards = external_source_records("Маниловка", criminal_record(
        person("Василій"), original_text="судим", source_url="https://viewer.rsl.ru/ru/rsl01001234567?page=12",
        bibliography="Ведомости, вып. 1"))
    data = _without_verbs(_encode({"cards": cards}))
    with pytest.raises(ReplayGap) as gap:      # `original_text` and `source_url` fit all three verbs
        replay_file(data)
    assert gap.value.message.params["factories"] == ["criminal_record", "wwi_record", "wwii_record"]
    data["documents"][0]["pages"][0]["records"][0]["written"]["draft_board"] = "Маниловский"
    found: Any = replay_file(data)["cards"]       # `draft_board` is the WWII verb's alone
    assert found.records[0].draft_board == "Маниловский"
