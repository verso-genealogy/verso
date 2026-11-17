"""The reading task: prompts present, schemas closed, the prompts' hash, stdlib-only imports."""
from __future__ import annotations

import ast
import hashlib
import json
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
PROMPT_HASH = "efd0eac9d3b130d4282b9a3c45937aaf4b072339fb755c2dbb17c089df01ffb7"


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
    """The nullable fields of the record and of a person: the API's limit (16) is on their sum."""
    schema = task.output_schema(group)
    n = 0
    for obj in (schema["properties"]["record"], schema["properties"]["persons"]["items"]):
        for sub in obj["properties"].values():
            n += "anyOf" in sub or (isinstance(sub.get("type"), list) and "null" in sub["type"])
    return n


def _records_dir():
    return resources.files("verso.ru.records")


def test_relationships_are_records_v1s():
    schema = json.loads(_records_dir().joinpath("records-v1.json").read_text(encoding="utf-8"))
    enum = schema["$defs"]["written_relative"]["properties"]["relationship"]["enum"]
    assert enum == [*task.RELATIONSHIPS, None]


def _ref_roles(kind):
    hints = tomllib.loads(_records_dir().joinpath("ui-hints.toml").read_text(encoding="utf-8"))
    refs = [f["ref"] for node in _walk(hints["kinds"][kind]) if isinstance(node, dict)
            if node.get("path") == "relationship_ref" and (f := node) and "ref" in f]
    assert len(refs) == 1
    return tuple(c["role"] for c in refs[0]["choices"])


@pytest.mark.parametrize("group,kind", (("births", "birth"), ("marriages", "marriage")))
def test_relationship_of_is_the_ui_hints_choices(group, kind):
    assert task.RELATIONSHIP_OF[group] == _ref_roles(kind)
    persons = _persons(group)
    assert persons["relationship_of"]["anyOf"][0]["enum"] == list(task.RELATIONSHIP_OF[group])
    assert set(task.NUMBERED_PARTIES) & set(task.RELATIONSHIP_OF[group])
    assert persons["relationship_of_number"] == {"type": ["string", "null"]}


@pytest.mark.parametrize("group", ("births", "marriages", "deaths"))
def test_relationship_in_person(group):
    persons = _persons(group)
    assert persons["relationship"]["anyOf"][0]["enum"] == list(task.RELATIONSHIPS)
    assert ("relationship_of" in persons) == (group != "deaths")
    assert ("relationship_of_number" in persons) == (group != "deaths")


def test_census_person_has_no_relationship():
    assert not {"relationship", "relationship_of", "relationship_of_number"} & set(_persons("census"))


def test_nullable_count_per_group():
    """Gemini takes 16 nullable fields at most (record + person). The relationship fields lift births and
    marriages to 18 and deaths to 17: recorded here, the report names the smallest way back."""
    assert {g: _nullable_count(g) for g in GROUPS} == {"births": 18, "marriages": 18, "deaths": 17, "census": 10}


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
