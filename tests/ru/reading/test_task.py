"""The reading task: prompts present, schemas closed, the prompts' hash, stdlib-only imports."""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

import verso.ru.reading as reading
from verso.ru.dsl import CensusRole
from verso.ru.reading import marking, task

GROUPS = ("births", "marriages", "deaths", "census")
#: sha256 of the cleaned prompts and schemas. A change of a prompt or a schema changes what a model
#: answers: change it on purpose, re-measure it, then update this.
PROMPT_HASH = "b1738a7c5ed6d6399f080f91ac5c23bf1dc4c63f05c26e088f29420d5a78209d"


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
