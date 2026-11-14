"""One record linted alone (`on_json.lint_record`, `lint_header`, 0.1.21).

A hosted store holds one record per row and lints ONE record per edit. The checks are the file's own rules over a
view of that record and its set's header, so the findings of `lint_record` over a file's records and of `lint_header`
over its sets must be those of `lint_records` over the file, by code, variant, params, token, level and the id they
are addressed to. The library's samples (`tests/data/`, invented DSL texts that fire the codes) are the file here;
a corpus holds the same of every record it has.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from records_alone import located
from test_linters_on_json_samples import Sample, samples
from thin_dictionary import thin_workspace
from verso.core.records import FormatError
from verso.core.records.replay import Position, replay_file
from verso.ru.linters import hosted, on_json
from verso.ru.linters.on_json import places

Key = tuple[str, str, str, str | None, str, str]

# The codes whose findings the invented samples are held to fire in the union (a floor, not the whole list).
KNOWN_FINDINGS = {
    "CPL002_grandson": "CPL002", "CSR_census_default_status": "CSR001",
    "ULC001_unknown_places": "ULC001", "ZGS_civil_books": "ZGS003", "RVR001_reviewed_flags": "RVR001"}


def _key(f: on_json.Finding) -> Key:
    return f.code, f.variant, json.dumps(f.params, ensure_ascii=False, sort_keys=True), f.token, f.record, f.level


def _documents(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [doc for doc in data["documents"] if "alias_of" not in doc]


def whole_file(data: dict[str, Any], codes: list[str], workspace: Path | None = None) -> Counter[Key]:
    return Counter(_key(f) for f in on_json.lint_records(copy.deepcopy(data), codes=codes, workspace=workspace))


def alone(data: dict[str, Any], codes: list[str], workspace: Path | None = None) -> Counter[Key]:
    """What a store gets: `lint_record` of each record, `lint_header` of each set, the one file fact computed once."""
    table = hosted.readiness()
    scope = places.file_in_scope(_documents(data), workspace=workspace)
    found: list[on_json.Finding] = []
    for item in located(data):
        found += on_json.lint_record(
            item.node, header=item.header, page=item.page, position=item.position, file_in_scope=scope,
            run_levels=item.run_levels, codes=[c for c in codes if table[c].scope != "set"], workspace=workspace)
    for doc in _documents(data):
        found += on_json.lint_header(doc, codes=codes, file_in_scope=scope, workspace=workspace)
    return Counter(_key(f) for f in found)


def _loaded() -> dict[str, Sample]:
    return {s.name.removeprefix("on_json_samples/").removesuffix(".py"): s for s in samples()[0]}


def test_the_union_of_records_and_headers_is_the_file_on_every_sample() -> None:
    compared = skipped = findings = 0
    differing: list[str] = []
    for sample in samples()[0]:
        try:
            replay_file(copy.deepcopy(sample.data), context=False)
            expected = whole_file(sample.data, list(on_json.SUPPORTED))
        except (FormatError, on_json.Unsupported):
            skipped += 1                    # a file the library itself cannot replay: lint_records refuses it too
            continue
        compared += 1
        got = alone(sample.data, list(on_json.SUPPORTED))
        findings += sum(expected.values())
        if got != expected:
            differing.append(f"{sample.name}: missing {dict(expected - got)} extra {dict(got - expected)}")
    print(f"\n{compared} samples compared ({skipped} not replayable), {findings} findings")
    assert not differing, "\n".join(differing[:6])
    assert compared > 100 and findings > 300


def test_a_name_the_workspace_lacks_is_found_in_its_record(tmp_path: Path) -> None:
    """The workspace is an argument: a name the writer's table held and the linting one lacks (NAM001, NAM002) is found
    by the record alone as by the file, and the one fact of the file ULC001 reads comes from the same workspace."""
    thin = thin_workspace(tmp_path / "ws", drop=frozenset({"Лука", "Фома", "Анфиса"}))
    codes = ["NAM001", "NAM002", "ULC001"]
    found = 0
    for sample in samples()[0]:
        expected = whole_file(sample.data, codes, thin)
        assert alone(sample.data, codes, thin) == expected, sample.name
        found += sum(c for key, c in expected.items() if key[0] == "NAM001")
    assert found


@pytest.mark.parametrize("sample, code", sorted(KNOWN_FINDINGS.items()))
def test_a_known_finding_is_made_by_its_record_alone(sample: str, code: str) -> None:
    """The invented samples that fire NAM001, CPL002, CSR001, ULC001, ZGS003 and RVR001: the union holds them."""
    data = _loaded()[sample].data
    got = alone(data, [code])
    assert got, f"{sample}: {code} does not fire"
    assert got == whole_file(data, [code])


def test_set_scope_is_refused_on_a_record() -> None:
    data = _loaded()["ZGS_civil_books"].data
    item = next(iter(located(data)))
    with pytest.raises(on_json.Unsupported) as refused:
        on_json.lint_record(item.node, header=item.header, page=item.page, position=item.position, codes=["ZGS003"])
    assert refused.value.message.key == "on_json.set_scope"
    assert hosted.readiness()["ZGS003"].scope == "set"


def test_a_file_scope_code_needs_the_flag_and_a_source_code_is_refused() -> None:
    data = _loaded()["ULC001_unknown_places"].data
    item = next(iter(located(data)))
    where: dict[str, Any] = {"header": item.header, "page": item.page, "position": item.position}
    with pytest.raises(on_json.Unsupported) as refused:
        on_json.lint_record(item.node, codes=["ULC001"], **where)
    assert refused.value.message.key == "on_json.needs_file_scope"
    with pytest.raises(on_json.Unsupported) as refused:
        on_json.lint_header(item.header, codes=["ULC001"])
    assert refused.value.message.key == "on_json.needs_file_scope"
    assert on_json.lint_record(item.node, codes=["ULC001"], file_in_scope=False, **where) == []
    for code in ("SLC001", "XXX999"):
        with pytest.raises(on_json.Unsupported):
            on_json.lint_record(item.node, codes=[code], **where)
    with pytest.raises(TypeError):
        on_json.lint_record(item.node, codes="NAM001", **where)


def test_header_codes_fire_once() -> None:
    """ZGS003 is a finding about a book: the header gives it once, no record of the book repeats it."""
    data = _loaded()["ZGS_civil_books"].data
    table = hosted.readiness()
    scope = places.file_in_scope(_documents(data))
    from_header = [f for doc in _documents(data) for f in on_json.lint_header(doc, codes=["ZGS003"], file_in_scope=scope)]
    assert from_header and all(f.code == "ZGS003" for f in from_header)
    assert len({f.record for f in from_header}) == len(from_header)
    from_records = [f for item in located(data)
                    for f in on_json.lint_record(item.node, header=item.header, page=item.page, position=item.position,
                                                 codes=[c for c in table if table[c].scope == "record"
                                                        and table[c].cls != "source"], run_levels=item.run_levels)]
    assert not [f for f in from_records if f.code == "ZGS003"]
    whole = [f for f in on_json.lint_records(copy.deepcopy(data), codes=["ZGS003"])]
    assert sorted(f.record for f in whole) == sorted(f.record for f in from_header)


def test_a_flagged_record_needs_its_run_to_be_redundant() -> None:
    """RVR001 compares a record's own `reviewed=` with what its page run shows: alone, a flagged record has no run to
    show it, and the caller that knows the run says it (`run_levels`); asked without, RVR001 is refused."""
    data = _loaded()["RVR001_reviewed_flags"].data
    runs = [item for item in located(data) if item.run_levels and "reviewed" in item.node.get("written", {})]
    assert runs, "the sample holds no flagged record beside an unflagged one"
    lone = Counter()
    told = Counter()
    for item in runs:
        where: dict[str, Any] = {"header": item.header, "page": item.page, "position": item.position,
                                 "codes": ["RVR001"]}
        with pytest.raises(on_json.Unsupported) as refused:       # not answered from a run it cannot see
            on_json.lint_record(item.node, **where)
        assert refused.value.message.key == "on_json.needs_run_levels"
        lone.update(f.record for f in on_json.lint_record(item.node, run_levels=(), **where))
        told.update(f.record for f in on_json.lint_record(item.node, run_levels=item.run_levels, **where))
    expected = Counter(f.record for f in on_json.lint_records(copy.deepcopy(data), codes=["RVR001"])
                       if f.record in {item.node["id"] for item in runs})
    assert told == expected and sum(told.values()) > sum(lone.values())


def test_position_is_the_one_thing_a_record_reads_of_its_neighbours() -> None:
    """A lint that reads a roll's running number gives the same findings wherever the `Position` puts the record,
    as long as it is told: here a twin of the sample's first record at another place."""
    data = _loaded()["CPL002_grandson"].data
    item = next(i for i in located(data) if i.node["kind"] == "household")
    codes = ["CPL002"]
    first = on_json.lint_record(item.node, header=item.header, page=item.page, position=item.position, codes=codes)
    moved = on_json.lint_record(item.node, header=item.header, page=item.page, codes=codes,
                                position=Position(item.position.ordinal + 5, item.position.members_before + 11))
    assert [(f.code, f.variant, f.params) for f in first] == [(f.code, f.variant, f.params) for f in moved]
