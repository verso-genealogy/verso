"""The reading task: prompts present, schemas closed, the prompts' hash, stdlib-only imports."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
import tomllib
from importlib import resources
from pathlib import Path

import pytest

import verso.ru.reading as reading
from verso.ru.dsl import CensusRole
from verso.ru.reading import marking, task

GROUPS = ("births", "marriages", "deaths", "census")
#: sha256 of the cleaned prompts and schemas. A change of a prompt or a schema changes what a model
#: answers: change it on purpose, re-measure it, then update this.
PROMPT_HASH = "b7d6e0a7172ac901ef0957d097692524380241bf8acfd1d2db2129678c67cbee"


def test_prompts_present():
    for group in GROUPS:
        text = task.system_prompt(group)
        assert task.prompt_text("common.md").strip() in text
        assert task.prompt_text(f"{group}.md").strip() in text
    assert marking.system_prompt().strip()


def _walk(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _assert_closed(schema):
    for node in _walk(schema):
        if isinstance(node, dict) and node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert node["required"] == list(node["properties"])


@pytest.mark.parametrize("group", GROUPS)
def test_schema_closed(group):
    schema = task.output_schema(group)
    _assert_closed(schema)
    persons = schema["properties"]["persons"]["items"]["properties"]
    assert persons["slot"]["enum"] == list(task.FAMILIES[group])
    assert tuple(schema["properties"]["record"]["properties"]) == task.RECORD_FIELDS[group]
    assert ("previous_age" in persons) == (group == "census")
    assert ("role" in persons) == (group == "census")



@pytest.mark.parametrize("group", GROUPS)
def test_alternatives_schema(group):
    """A name read two or three ways: the likelier in the field, the others by the field's path (П15)."""
    schema = task.output_schema(group)
    alternatives = schema["properties"]["alternatives"]
    assert alternatives["type"] == "array"
    item = alternatives["items"]
    assert item["properties"] == {"path": {"type": "string"}, "readings": {"type": "array", "items": {"type": "string"}}}
    assert list(schema["properties"]) == ["record", "persons", "doubtful", "alternatives"]


def test_prompt_asks_for_alternatives():
    text = task.prompt_text("common.md")
    assert "`alternatives`" in text
    assert "persons[2].name" in text

def test_marking_schema_converts():
    schema = marking.output_schema()
    _assert_closed(schema)
    assert json.loads(json.dumps(schema)) == schema
    rec = schema["properties"]["records"]["items"]["properties"]
    assert set(rec) == {"number", "kind", "gender", "box_2d", "continues", "continued"}
    assert rec["kind"]["enum"] == ["birth", "marriage", "death"]
    assert rec["box_2d"] == {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}
    assert schema["properties"]["doubtful"]["items"] == {"type": "string"}


@pytest.mark.parametrize("group", (*GROUPS, "marking"))
def test_schemas_in_geminis_subset(group):
    """The converter's contract, stdlib-only: a nullable is `anyOf` of one type and null, or a type array
    of one type and "null"; no oneOf/allOf/$ref/patternProperties or other keyword outside the subset."""
    schema = marking.output_schema() if group == "marking" else task.output_schema(group)
    keywords = {"type", "properties", "required", "additionalProperties", "items", "enum", "anyOf",
                "minItems", "maxItems"}

    def check(node):
        assert isinstance(node, dict)
        assert set(node) <= keywords, set(node) - keywords
        if "anyOf" in node:
            assert set(node) == {"anyOf"}
            a, b = node["anyOf"]
            assert b == {"type": "null"} and a.get("type") != "null" and "anyOf" not in a
            check(a)
        t = node.get("type")
        if isinstance(t, list):
            assert len(t) == 2 and "null" in t and t.count("null") == 1
        if t == "object":
            for sub in node["properties"].values():
                check(sub)
        if t == "array":
            check(node["items"])

    check(schema)


def _persons(group):
    return task.output_schema(group)["properties"]["persons"]["items"]["properties"]


def _nullable_count(group):
    """What Gemini counts over the whole schema: an `anyOf` with a null branch, a `type` list holding "null"."""
    n = 0
    for node in _walk(task.output_schema(group)):
        if not isinstance(node, dict):
            continue
        n += any(b == {"type": "null"} for b in node.get("anyOf", ())) or (
            isinstance(node.get("type"), list) and "null" in node["type"])
    return n


def _records_dir():
    return resources.files("verso.ru.records")


def test_relationships_are_records_v1s():
    schema = json.loads(_records_dir().joinpath("records-v1.json").read_text(encoding="utf-8"))
    enum = schema["$defs"]["written_relative"]["properties"]["relationship"]["enum"]
    assert enum == [*task.RELATIONSHIPS, None]


def _ref_choices(kind):
    hints = tomllib.loads(_records_dir().joinpath("ui-hints.toml").read_text(encoding="utf-8"))
    refs = [node["ref"] for node in _walk(hints["kinds"][kind]) if isinstance(node, dict)
            if node.get("path") == "relationship_ref" and "ref" in node]
    assert len(refs) == 1
    return refs[0]["choices"]


@pytest.mark.parametrize("group,kind", (("births", "birth"), ("marriages", "marriage")))
def test_relationship_of_is_the_ui_hints_choices(group, kind):
    """The role part of a choice is a `relationship_ref` choice; a numbered role is one whose word has `{n}`."""
    choices = _ref_choices(kind)
    assert task.RELATIONSHIP_OF[group] == tuple(c["role"] for c in choices)
    numbered = {c["role"] for c in choices if "{n}" in c["word"]}
    assert numbered == set(task.NUMBERED_PARTIES) & set(task.RELATIONSHIP_OF[group])
    enum = _persons(group)["relationship_of"]["anyOf"][0]["enum"]
    assert enum == task.relationship_of_choices(group)
    assert {c.split(" ")[0] for c in enum} == set(task.RELATIONSHIP_OF[group])
    assert all((" " in c) == (c.split(" ")[0] in numbered) for c in enum)
    assert "relationship_of_number" not in _persons(group)


@pytest.mark.parametrize("group", ("births", "marriages", "deaths"))
def test_relationship_in_person(group):
    persons = _persons(group)
    assert persons["relationship"]["anyOf"][0]["enum"] == list(task.RELATIONSHIPS)
    assert ("relationship_of" in persons) == (group != "deaths")
    assert "role" not in persons


def test_party_counts_are_records_v1s():
    """How many godparents and witnesses a record can hold: the `god_parentN` and `witnessN` properties."""
    defs = json.loads(_records_dir().joinpath("records-v1.json").read_text(encoding="utf-8"))["$defs"]

    def numbered(kind, stem):
        return sum(bool(re.fullmatch(stem + r"\d+", p)) for p in defs[kind]["properties"])
    assert task.NUMBERED_PARTIES == {"godparent": numbered("written_birth", "god_parent"),
                                     "witness": numbered("written_marriage", "witness")}


def test_relationship_of_choices():
    assert task.relationship_of_choices("births") == ["mother", "godparent 1", "godparent 2", "godparent 3",
                                                      "godparent 4"]
    assert task.relationship_of_choices("marriages") == ["groom", "bride", *(f"witness {n}" for n in range(1, 7))]


def test_census_person_has_no_relationship():
    assert not {"relationship", "relationship_of"} & set(_persons("census"))


def test_nullable_count_per_group():
    """Gemini takes 16 nullable fields at most (record + person): every group stays within it."""
    counts = {g: _nullable_count(g) for g in GROUPS}
    assert counts == {"births": 16, "marriages": 16, "deaths": 16, "census": 10}
    assert max(counts.values()) <= 16


def test_census_roles_are_the_dsls():
    assert dict(task.CENSUS_ROLES) == {m.name.lower(): m.value for m in CensusRole}


def test_lines_and_card():
    assert marking.MARK_LINE == "Найди на листе все записи и верни их рамки в JSON по схеме."
    assert task.TASK_LINE == "Прочитай запись на снимке и верни её поля в JSON по схеме."
    assert task.card({"village": "Маниловка", "year": 1850, "folio": ""}) == "Село: Маниловка\nГод: 1850"


def _digest() -> str:
    h = hashlib.sha256()
    for group in GROUPS:
        h.update(task.system_prompt(group).encode())
        h.update(json.dumps(task.output_schema(group), sort_keys=True).encode())
    h.update(marking.system_prompt().encode())
    h.update(json.dumps(marking.output_schema(), sort_keys=True).encode())
    return h.hexdigest()


def test_prompt_hash():
    assert _digest() == PROMPT_HASH, "a prompt or a schema changed: re-measure, then update PROMPT_HASH"


def test_no_imports():
    allowed = set(sys.stdlib_module_names) | {"verso"}
    for path in Path(reading.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else [])
            for mod in mods:
                assert mod.split(".")[0] in allowed, f"{path.name} imports {mod}"
                if mod.startswith("verso"):
                    assert mod.startswith("verso.ru.reading"), f"{path.name} imports {mod}"
