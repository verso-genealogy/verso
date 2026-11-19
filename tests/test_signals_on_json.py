"""The signals of one record of a records-v1 file — `verso.ru.pipeline.signals.signals_on_json`.

A hosted store holds one record per row. Its card asks the six single-record checks of that row alone: the
record is built from what its node wrote (`replay_alone`: its set's header, its leaf, its place) and handed to
`verso.ru.facts.signals.signals_of`. What it proves: the record read alone says what its book says of it — the
same checks over the whole book's assertions, drafts read, give the same signals record by record.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from records_alone import located
from test_linters_on_json_samples import _try_load, samples
from thin_dictionary import thin_workspace
from verso.core.pipeline.load import record_namespace
from verso.core.records import FormatError
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.core.records.replay import Position, replay_file
from verso.ru.dsl.records.births import BirthRecords
from verso.ru.dsl.records.deaths import DeathRecords
from verso.ru.dsl.records.marriages import MarriageRecords
from verso.ru.facts.extract.common import SlotIndex
from verso.ru.facts.model import AssertionSet
from verso.ru.facts.signals import CHECKS, Signals, findings_of, signal_of
from verso.ru.pipeline.facts import assertions_of
from verso.ru.pipeline.signals import signals_on_json, svyatcy_cached

SAMPLE = Path(__file__).resolve().parent / "data" / "signal_samples" / "SIG_six_checks.py.sample"
METRIC = (BirthRecords, MarriageRecords, DeathRecords)

type Key = tuple[str, str, str, str]


def _book() -> dict[str, Any]:
    """The invented book of the six checks, as an export holds it."""
    module, error = _try_load(SAMPLE.read_text(encoding="utf-8"))
    assert module is not None, error
    doc = encode_namespace(record_namespace(module), village="Маниловка", file="SIG_six_checks.py", sha256="-", ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _key(signal: Any) -> Key:
    return signal.check, signal.variant, signal.record, signal.confidence


def alone(data: dict[str, Any], workspace: Path | None = None) -> tuple[Counter[Key], int]:
    """What a store gets: `signals_on_json` of each record; and how many records it asked."""
    found: Counter[Key] = Counter()
    asked = 0
    for item in located(data):
        got = signals_on_json(item.node, header=item.header, page=item.page, position=item.position, workspace=workspace)
        assert got.unanswered == (), item.node["id"]
        found.update(_key(s) for s in got.found)
        asked += 1
    return found, asked


def whole(data: dict[str, Any]) -> Counter[Key]:
    """What the book says: the six checks over the assertions of all its metric sets, drafts read, each finding
    addressed to the record its claims were read in."""
    built = replay_file(copy.deepcopy(data), context=False)
    ids = {id(item.built): item.node["id"] for item in located(data, built)}
    sources = [(name, records) for name, records in built.items() if isinstance(records, METRIC)]
    facts = AssertionSet(assertions_of(sources, village="Маниловка", slots=SlotIndex(), drafts=True,
                                       ids=lambda record: ids[id(record)]))
    record_of = {a.cite.record_id: a.subject.id.rsplit("/", 1)[0] for a in facts}
    believed = facts.believed()
    out: Counter[Key] = Counter()
    for check in CHECKS:
        for finding in findings_of(believed, check, svyatcy=svyatcy_cached()):
            signal = signal_of(finding)
            out[(signal.check, signal.variant, record_of[signal.cite.record_id], signal.confidence)] += 1
    return out


def test_the_record_alone_gives_what_the_whole_book_gives() -> None:
    data = _book()
    by_record, asked = alone(data)
    assert by_record == whole(data)
    assert asked == 24
    # every variant of the plan's table fires in the invented book, so the equality compares something
    assert {(check, variant) for check, variant, _id, _c in by_record} == {
        ("wedding-calendar", "strict"), ("wedding-calendar", "loose"), ("name-days", "far"), ("name-days", "lookalike"),
        ("baptism-lag", "late"), ("baptism-lag", "month_carried"), ("burial-lag", "late"), ("burial-lag", "very_late"),
        ("wedding-ages", "under_age"), ("wedding-ages", "age_gap"),
        ("date-order", "baptism_before_birth"), ("date-order", "burial_before_death")}


def test_the_notes_of_the_invented_book_stand_their_records_down() -> None:
    """Births 3, 5, 8; weddings 4 (the fast) and 7 (the ages); deaths 3, 5: each has a noisy twin and says nothing
    of its own check."""
    data = _book()
    said = {(item.node["id"].rsplit("/", 2)[-2], item.node["written"]["number"]): {
        s.check for s in signals_on_json(item.node, header=item.header, page=item.page, position=item.position).found}
        for item in located(data)}
    assert "baptism-lag" in said["birth", 1] and "baptism-lag" not in said["birth", 3]
    assert "date-order" in said["birth", 4] and "date-order" not in said["birth", 5]
    assert "name-days" in said["birth", 6] and "name-days" not in said["birth", 8]
    assert "wedding-calendar" in said["marriage", 1] and "wedding-calendar" not in said["marriage", 4]
    assert "wedding-ages" in said["marriage", 5] and "wedding-ages" not in said["marriage", 7]
    assert "burial-lag" in said["death", 2] and "burial-lag" not in said["death", 3]
    assert "date-order" in said["death", 4] and "date-order" not in said["death", 5]
    assert said["birth", 10] == said["marriage", 8] == said["death", 6] == set()


def test_a_held_record_is_read_and_a_signal_names_its_node() -> None:
    held = next(item for item in located(_book()) if item.node["written"].get("reviewed") is False)
    got = signals_on_json(held.node, header=held.header, page=held.page, position=held.position)
    assert [(s.check, s.record) for s in got.found] == [("baptism-lag", held.node["id"])]


def test_the_book_s_year_dates_its_records() -> None:
    """No record of the invented book writes a year: the wedding of 1 December is in the Nativity fast of 1850."""
    wedding = next(item for item in located(_book()) if item.node["id"].endswith("/marriage/1"))
    [signal] = signals_on_json(wedding.node, header=wedding.header, page=wedding.page, position=wedding.position).found
    assert signal.params["date"] == "01.12.1850"


def test_only_the_checks_asked() -> None:
    item = next(i for i in located(_book()) if i.node["id"].endswith("/marriage/5"))
    got = signals_on_json(item.node, header=item.header, page=item.page, position=item.position, checks=["wedding-calendar"])
    assert got == Signals((), ())


def test_every_sample_of_the_linters_agrees_too() -> None:
    """The linters' invented books hold records these checks were never written for — households, cards, days no
    month has: none may break a card, and each record alone still says what its book says of it."""
    compared = signals = 0
    for sample in samples()[0]:
        try:
            replay_file(copy.deepcopy(sample.data), context=False)
        except FormatError:
            continue                    # a file the library itself cannot replay
        found: Counter[Key] = Counter()
        for item in located(sample.data):
            found.update(_key(s) for s in signals_on_json(
                item.node, header=item.header, page=item.page, position=item.position).found)
        assert found == whole(sample.data), sample.name
        compared += 1
        signals += sum(found.values())
    assert compared > 30 and signals > 0


def test_a_record_the_factories_cannot_build_is_unanswered() -> None:
    item = next(iter(located(_book())))
    broken = copy.deepcopy(item.node)
    broken["written"]["gender"] = "neither"
    got = signals_on_json(broken, header=item.header, page=item.page, position=item.position)
    assert got == Signals((), CHECKS)
    assert signals_on_json({"id": "x", "kind": "birth"}, header={}, page=None, position=Position(0, 0)) == Signals((), CHECKS)


def test_a_workspace_without_a_names_table_leaves_name_days_unanswered(tmp_path: Path) -> None:
    bare = thin_workspace(tmp_path / "bare", names=False)
    item = next(i for i in located(_book()) if i.node["id"].endswith("/birth/m6") or i.node["id"].endswith("/birth/f6"))
    got = signals_on_json(item.node, header=item.header, page=item.page, position=item.position, workspace=bare)
    assert "name-days" in got.unanswered
    assert all(s.check != "name-days" for s in got.found)


def test_the_svyatcy_are_read_once() -> None:
    assert svyatcy_cached() is svyatcy_cached()
    assert len(svyatcy_cached()) > 1000


def test_checks_as_a_text_are_refused() -> None:
    item = next(iter(located(_book())))
    with pytest.raises(TypeError):
        signals_on_json(item.node, header=item.header, page=item.page, position=item.position, checks="name-days")
