"""A record's view from its records-JSON node (`verso.ru.dsl.view.node_view`) is the view `record_view` gives of
its call: the same `record`, the same `consts` but for the aliases of one constant, and no `opaque`.

Run over the library's linter samples (`tests/data/linter_samples/`, as `test_linters_on_json_samples` loads them),
the four invented books of `test_dsl_paths` and the fixture book of `records_fixture`. Each DSL record is built by
its file's code; the JSON node is that file's export with every `derived` dropped — what a folder of records JSON
keeps — and the record it is viewed with is `replay_file`'s (`context=False`), made of `written` alone."""
from __future__ import annotations

import copy
import json
from collections import Counter
from collections.abc import Iterator, Mapping
from typing import Any

import records_fixture as fixture
from test_dsl_paths import BIRTHS, CENSUS, DEATHS, MARRIAGES
from test_linters_on_json_samples import load_sample, samples

from verso.core.pipeline.load import record_namespace
from verso.core.records.encode import context_in_derived, encode_namespace, encode_record
from verso.core.records.ids import Ids, walk
from verso.core.records.replay import replay_file
from verso.ru.dsl import describe, source
from verso.ru.dsl.view import node_view, record_view

# Where the DSL names a constant the JSON names differently: two constants of the catalog spell one text, and the
# JSON, which holds the text alone, names the one that sorts last (the rule of the linters on JSON, «Aliases of one
# constant»). {the source's constant: the JSON's}; the test prints what it compared and holds each entry to a use.
ALIASES: dict[str, str] = {"GOSUDARSTVENNYJ_PEASANT_MALE": "STATE_PEASANT_MALE"}


def _written_only(data: Any) -> Any:
    """`data` less every `derived`: the shape a folder keeps."""
    if isinstance(data, dict):
        return {k: _written_only(v) for k, v in data.items() if k != "derived"}
    if isinstance(data, list):
        return [_written_only(v) for v in data]
    return data


def _nodes(data: Any) -> Iterator[Mapping[str, Any]]:
    """The record nodes of a records-v1 file, in the export's order."""
    if isinstance(data, dict):
        if "review" in data and "kind" in data and "written" in data:
            yield data
            return
        for value in data.values():
            yield from _nodes(value)
    elif isinstance(data, list):
        for value in data:
            yield from _nodes(value)


def _pairs() -> Iterator[tuple[str, str, Any]]:
    """(name, DSL text, its records-v1 file) of every text that loads: see `_compare`."""
    for sample in samples()[0]:
        yield sample.name, sample.text, sample.data
    for name, text in (("births", BIRTHS), ("marriages", MARRIAGES), ("deaths", DEATHS), ("census", CENSUS)):
        module = load_sample(text)
        assert module is not None, name
        yield f"test_dsl_paths/{name}", text, encode_namespace(
            record_namespace(module), village="Примерово", file=f"{name}.py", sha256="-", ids=Ids())


def _kind_of_difference(text: str, path: str, dsl: str | None, js: str | None, opaque: list[str]) -> str:
    """Why the two views name `path` differently — one of the few forms the JSON (or the source) cannot show —
    or "" where nothing explains it."""
    if dsl is None and any(path.startswith(o + "/") for o in opaque):
        return "under an expression"            # the source cannot be read through `*ROWS`; the JSON holds the rows
    if dsl is not None and js is None and dsl in source.file_constants(text):
        return "a constant of the file"          # TENTETNIKOV_PEASANT = «…»: the JSON holds its text, not its name
    if dsl is None and js is not None and path.endswith("marital_status"):
        return "a marital status written as text"  # a marital status is text either way
    if dsl is not None and js is not None and ALIASES.get(dsl) == js:
        constants = describe.constant_by_code()
        assert constants[dsl].text == constants[js].text and dsl < js, (dsl, js)
        return "alias"
    return ""


def _compare() -> tuple[int, int, list[str], Counter[str], dict[str, str]]:
    compared, record_only, skipped = 0, 0, []
    kinds: Counter[str] = Counter()
    aliases: dict[str, str] = {}
    for name, text, data in _pairs():
        module = load_sample(text)
        assert module is not None
        built = [record for _, record in walk(record_namespace(module))]
        found = source.find_records(text)
        nodes = list(_nodes(data))
        if len(built) != len(nodes):
            skipped.append(f"{name} ({len(built)}/{len(found)}/{len(nodes)})")  # a set the source builds in a loop …
            continue
        stripped = _written_only(copy.deepcopy(data))
        replayed = replay_file(json.loads(json.dumps(stripped)), context=False)
        again = [record for _, record in walk(replayed)]
        assert len(again) == len(nodes), name
        views = list(zip(built, nodes, again, _nodes(stripped), strict=True))
        for k, (record, node, rebuilt, bare) in enumerate(views):
            js = node_view(rebuilt, bare, node["id"])
            assert js["opaque"] == [] and set(js) == {"record", "consts", "opaque"}
            if len(found) != len(nodes):       # cards have no call in the source: their record alone
                assert js["record"] == context_in_derived(encode_record(record, node["id"], record_set=None)), (name, node["id"])
                record_only += 1
                continue
            dsl = record_view(found[k], record, node["id"])
            assert js["record"] == dsl["record"], (name, node["id"])
            for path in dsl["opaque"]:
                assert path not in js["consts"], (name, path)
            for path in set(dsl["consts"]) | set(js["consts"]):
                before, after = dsl["consts"].get(path), js["consts"].get(path)
                if before == after:
                    continue
                kind = _kind_of_difference(text, path, before, after, dsl["opaque"])
                assert kind, (name, node["id"], path, before, after)
                kinds[kind] += 1
                if kind == "alias":
                    aliases[str(before)] = str(after)
            compared += 1
    return compared, record_only, skipped, kinds, aliases


# The forms of `_kind_of_difference`: each is met, so none is an escape hatch nothing uses.
KINDS = {"a constant of the file", "alias", "a marital status written as text", "under an expression"}


def test_node_view_matches_record_view():
    compared, record_only, skipped, kinds, aliases = _compare()
    assert skipped == [], skipped                # every text's records are compared, none set aside
    assert compared >= 300 and record_only >= 10, (compared, record_only)
    assert set(kinds) == KINDS, dict(kinds)
    assert aliases == ALIASES                    # every alias the test keeps is met, and no other


def test_the_view_and_the_linters_name_a_cause_alike():
    """`view._codes("cause")` (a record's view, from `describe.catalogs()`) and `KNOWN_CAUSES` (the linters, from
    the domain's module and its aliases) are two readings of one catalog: every text a constant spells names the
    same constant in both. The linters know aliases besides (`от чахотки`), which no constant spells."""
    from verso.ru.dsl import view
    from verso.ru.linters.checks.single_line_calls import KNOWN_CAUSES
    codes = view._codes("cause")                 # pyright: ignore[reportPrivateUsage]
    texts = {c.text for c in describe.catalogs()["cause"]}
    assert set(codes) == texts and len(codes) > 50
    assert {text: KNOWN_CAUSES.get(text) for text in codes} == codes
    assert {text: code for text, code in KNOWN_CAUSES.items() if text in texts} == codes


def test_node_view_opaque_is_empty():
    ns = fixture.namespace()
    doc = _written_only(encode_namespace(ns, village="Маниловка", file="1900/fixture.py", sha256="0" * 64,
                                         ids=Ids()))
    replayed = replay_file(json.loads(json.dumps(doc)), context=False)
    nodes = list(_nodes(doc))
    records = [record for _, record in walk(replayed)]
    assert len(nodes) == len(records) > 10
    for node, record in zip(nodes, records, strict=True):
        view = node_view(record, node, node["id"])
        assert view["opaque"] == []
        assert view["record"]["id"] == node["id"]
