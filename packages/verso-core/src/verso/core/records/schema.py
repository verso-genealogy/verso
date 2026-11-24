"""records-v1.json — the JSON Schema of the records JSON, built from the field table.

The schema is generated, not written: `build_schema()` reads the workspace's DSL's vocabulary
(`verso.core.records.fields.vocabulary()`), the same table the encoder and the decoder read,
so the three cannot drift. The committed file lies beside the vocabulary
(`Vocabulary.schema_package`: the Russian books' in verso/ru/records/) and is checked
against it (`--check`, and a test). Validating a file needs `jsonschema` — a dev dependency,
imported only by `--validate`.

    python -m verso.core.records.schema --write          # regenerate records-v1.json
    python -m verso.core.records.schema --check          # exit 1 if the committed file is stale
    python -m verso.core.records.schema --validate DIR   # every *.json under DIR
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from enum import Enum
from importlib.resources import files
from pathlib import Path
from typing import Any

from verso.core.records import SCHEMA_ID
from verso.core.records.notes import ANCHORS, NOTE
from verso.core.records.fields import (
    CONTEXT_KEY, PERSON, WRAPPER_KEY, ClassSpec, ListOf, OneOf, TypeSpec, Vocabulary, code, enum_code, factory_params,
    param_spec, vocabulary, written_key)
from verso.core.messages import t

SCHEMA_FILE = "records-v1.json"
ID_PATTERN = r"^r1:[^/]+(?:/[^/]+)+$"
REVIEW = ["reviewed", "held", "on_geni"]

_SCALAR: dict[str, list[str]] = {
    "str": ["string"], "int": ["integer"], "bool": ["boolean"], "age": ["integer", "number", "string"],
    "intstr": ["integer", "string"],
}


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [{"type": "null"}, schema]}


def _is_entity(spec: TypeSpec) -> bool:
    voc = vocabulary()
    return isinstance(spec, type) and spec in voc.specs and spec not in voc.value_classes


def type_schema(spec: TypeSpec) -> dict[str, Any]:
    """What a field of `spec` may hold in the JSON."""
    if isinstance(spec, OneOf):
        return {"anyOf": [type_schema(one) for one in spec.types]}
    if isinstance(spec, str):
        if spec in _SCALAR:
            return {"type": [*_SCALAR[spec], "null"]}
        if spec == "strs":
            return _nullable({"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]})
        if spec in vocabulary().scalars:
            return {"anyOf": [{"type": ["string", "null"]}, {"$ref": f"#/$defs/{spec}"}]}
        if spec == PERSON:
            return {"type": "null"}
    if isinstance(spec, tuple):
        return {"enum": [*(f"{enum_code(e)}.{code(m)}" for e in spec for m in e), None]}
    if isinstance(spec, type) and issubclass(spec, Enum):
        return {"enum": [*(code(m) for m in spec), None]}
    if isinstance(spec, type) and spec in vocabulary().value_classes:
        return _nullable({"$ref": f"#/$defs/{vocabulary().specs[spec].code}"})
    if isinstance(spec, ListOf):
        if _is_entity(spec.item):
            return _nullable({"type": "array", "maxItems": 0})
        return _nullable({"type": "array", "items": type_schema(spec.item)})
    raise ValueError(str(t("records.schema.no_schema", spec=repr(spec))))


def _non_null(schema: dict[str, Any]) -> dict[str, Any]:
    """`schema` without its null: a scalar's `type` or an enumeration's `enum`."""
    if isinstance(schema.get("type"), list):
        return {**schema, "type": [k for k in schema["type"] if k != "null"]}
    if "enum" in schema:
        return {**schema, "enum": [v for v in schema["enum"] if v is not None]}
    return schema


def _structural(spec: ClassSpec) -> set[str]:
    return {f.name for f in spec.fields
            if f.type == PERSON or (isinstance(f.type, ListOf) and _is_entity(f.type.item))}


def _closed(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def _grouped(properties: dict[str, Any]) -> dict[str, Any]:
    """Properties by JSON key; a dotted key's group is a closed object of its own (records v1)."""
    out: dict[str, Any] = {}
    for key, schema in properties.items():
        head, dot, tail = key.partition(".")
        if dot:
            out.setdefault(head, _closed({}))["properties"][tail] = schema
        else:
            out[key] = schema
    return _closed(out)


def _written(spec: ClassSpec) -> dict[str, Any]:
    params = dict.fromkeys(p for fn in spec.factories for p in factory_params(fn))
    props = {written_key(spec.cls, p): type_schema(param_spec(spec.cls, p)) for p in params}
    voc = vocabulary()
    verbs = voc.verbs.get(spec.cls)
    for reserved in (CONTEXT_KEY, WRAPPER_KEY, *(("verb",) if verbs else ())):
        if reserved in props:   # a parameter written under a key the format keeps for itself
            raise ValueError(str(t("records.schema.reserved_key", cls=spec.cls.__name__, key=reserved)))
    if verbs:
        props = {"verb": {"enum": list(verbs)}, **props}
    # A wrapper's value stands under its attribute's key, and the marker names it (records v1.x).
    keys = voc.json_keys[spec.cls]
    context = [keys[f.name] for f in spec.fields if f.name in voc.context.get(spec.cls, frozenset())
               and f.name != "page"]
    if context:
        for f in spec.fields:
            if keys[f.name] in context and keys[f.name] not in props:
                props[keys[f.name]] = type_schema(f.type)
    grouped = _grouped(props)
    if context:
        grouped["properties"][CONTEXT_KEY] = {"type": "array", "items": {"enum": context}, "uniqueItems": True}
    # What a wrapper would have set on a field the call wrote (records v1.x): the fields a wrapper keeps so.
    # Never null: a wrapper that gives no value keeps none (`verso.core.written.shadow`).
    shadowed = {keys[f.name]: _non_null(type_schema(f.type)) for f in spec.fields
                if f.name in voc.shadowed.get(spec.cls, frozenset())}
    if shadowed:
        grouped["properties"][WRAPPER_KEY] = {**_grouped(shadowed), "minProperties": 1}
    return grouped


def _derived(spec: ClassSpec, skip: set[str]) -> dict[str, Any]:
    keys = vocabulary().json_keys[spec.cls]
    return _grouped({keys[f.name]: type_schema(f.type) for f in spec.fields if f.name not in skip})


def _records(voc: Vocabulary) -> tuple[type, ...]:
    """The classes of records: what a record set holds."""
    held = {code_ for codes in voc.holds.values() for code_ in codes}
    return tuple(cls for cls, spec in voc.specs.items() if spec.code in held)


def _defs() -> Iterator[tuple[str, dict[str, Any]]]:
    voc = vocabulary()
    records = _records(voc)
    yield "id", {"type": "string", "pattern": ID_PATTERN}
    for name, scalar in voc.scalars.items():
        yield name, _closed(*scalar.schema)
    for cls in voc.value_classes:
        spec = voc.specs[cls]
        yield spec.code, _grouped({voc.json_keys[cls][f.name]: type_schema(f.type) for f in spec.fields})
    for cls, spec in voc.specs.items():
        if cls in voc.value_classes:
            continue
        skip = _structural(spec) | ({"page"} if spec.records_attr is None and cls in records else set())
        if spec.records_attr is not None:
            skip.add(spec.records_attr)
        if spec.factories:
            yield f"written_{spec.code}", _written(spec)
        yield f"derived_{spec.code}", _derived(spec, skip)
    # A persona's link: its item of a list of persons (a relative, a household's member); a
    # vocabulary with no such list has none — no persona may hold one.
    yield "link", {"anyOf": [_closed({"written": {"$ref": f"#/$defs/written_{c}"},
                                      "derived": {"$ref": f"#/$defs/derived_{c}"}}, ["derived"])
                             for c in voc.links]} if voc.links else {"not": {}}
    person = voc.specs[voc.person].code
    yield "persona", _closed({
        "id": {"$ref": "#/$defs/id"}, "label": {"type": "string"}, "role": {"type": "string"},
        "slot": {"type": "integer"}, "link": {"$ref": "#/$defs/link"},
        "written": {"$ref": f"#/$defs/written_{person}"}, "derived": {"$ref": f"#/$defs/derived_{person}"},
    }, ["id", "role", "derived"])
    # The `#` notes of the DSL file, on the file's and the records' nodes (records v1.x).
    yield "source_notes", {"type": "array", "minItems": 1, "items": _closed({
        "text": {"type": "string"},
        "anchor": _closed({"to": {"enum": list(ANCHORS)}, "record": {"type": "integer", "minimum": 0},
                           "end": {"type": "integer", "minimum": 0}, "arg": {"type": "string"}}, ["to"]),
    }, ["text", "anchor"])}
    for cls in records:
        c = voc.specs[cls].code
        yield f"record_{c}", _closed({
            "id": {"$ref": "#/$defs/id"}, "label": {"type": "string"}, "kind": {"const": c},
            "key": {"type": "string", "minLength": 1, "pattern": "^[^/]+$"},
            "review": {"enum": REVIEW}, "written": {"$ref": f"#/$defs/written_{c}"},
            "derived": {"$ref": f"#/$defs/derived_{c}"},
            "persons": {"type": "array", "items": {"$ref": "#/$defs/persona"}},
            NOTE: {"$ref": "#/$defs/source_notes"},
        }, ["id", "kind", "review", "derived", "persons"])
    for spec in voc.specs.values():
        if spec.records_attr is None:
            continue
        c = spec.code
        run = _closed({"page": {"type": ["string", "null"]}, "records": {
            "type": "array", "items": {"anyOf": [{"$ref": f"#/$defs/record_{r}"} for r in voc.holds[c]]}}},
            ["page", "records"])
        yield f"document_{c}", _closed({
            "id": {"$ref": "#/$defs/id"}, "variable": {"type": "string"}, "kind": {"const": c},
            "written": {"$ref": f"#/$defs/written_{c}"}, "derived": {"$ref": f"#/$defs/derived_{c}"},
            "pages": {"type": "array", "items": run},
        }, ["id", "variable", "kind", "derived", "pages"])
    yield "alias", _closed({"variable": {"type": "string"}, "alias_of": {"type": "string"}},
                           ["variable", "alias_of"])
    documents = [{"$ref": f"#/$defs/document_{s.code}"} for s in voc.specs.values() if s.records_attr]
    yield "file", _closed({
        "schema": {"const": SCHEMA_ID}, "village": {"type": "string"}, "file": {"type": "string"},
        "sha256": {"type": "string"},
        "vocabulary": _closed({"plugin": {"type": "string"}, "version": {"type": "integer", "minimum": 1}},
                              ["plugin", "version"]),
        "lang": {"type": "string"},
        "documents": {"type": "array", "items": {"anyOf": [*documents, {"$ref": "#/$defs/alias"}]}},
        NOTE: {"$ref": "#/$defs/source_notes"},
    }, ["schema", "village", "file", "sha256", "documents"])
    yield "index", _closed({
        "schema": {"const": SCHEMA_ID}, "village": {"type": "string"},
        "files": {"type": "object", "additionalProperties": {"type": "string"}},
        "skipped": {"type": "object", "additionalProperties": {"type": "string"}},
        "inputs": {"type": "object", "additionalProperties": {"type": "string"}},
    }, ["schema", "village", "files", "skipped", "inputs"])


def build_schema() -> dict[str, Any]:
    """records-v1.json, from the field table."""
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SCHEMA_ID,
            "title": "Verso records v1",
            "description": "The built DSL records as JSON: documents, page runs, records, personas; "
                           "`written` is what a DSL call wrote, `derived` what the objects hold besides.",
            "oneOf": [{"$ref": "#/$defs/file"}, {"$ref": "#/$defs/index"}],
            "$defs": dict(_defs())}


def dumps(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=1) + "\n"


def load_schema() -> dict[str, Any]:
    """The committed records-v1.json: beside the workspace's DSL's vocabulary."""
    return json.loads(files(vocabulary().schema_package).joinpath(SCHEMA_FILE).read_text(encoding="utf-8"))


def check_keys(doc: dict[str, Any]) -> list[str]:
    """One message per record whose `key` another record of the export already holds, naming both
    paths. `key` is the record's immutable key (optional, a property of the stored node: the DSL never writes one, decode and
    replay ignore it; a folder backend sets it on first load and must copy it when it rebuilds a node), so two records sharing one are a defect of the export."""
    seen: dict[str, str] = {}
    problems: list[str] = []
    for d, document in enumerate(doc.get("documents", [])):
        for p, run in enumerate(document.get("pages", [])):
            for r, record in enumerate(run.get("records", [])):
                key = record.get("key")
                if key is None:
                    continue
                path = f"documents[{d}].pages[{p}].records[{r}]"
                if key in seen:
                    problems.append(str(t("records.schema.duplicate_key", key=repr(key), first=seen[key], second=path)))
                else:
                    seen[key] = path
    return problems


def validate(directory: Path) -> list[str]:
    """«file: path: error» for every invalid *.json under `directory`."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema())
    problems = []
    for path in sorted(directory.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.path))[:3]:
            where = "/".join(str(p) for p in error.path)
            problems.append(f"{path.relative_to(directory)}: {where}: {error.message}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="records-v1.json: build, check, validate")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the committed schema")
    group.add_argument("--check", action="store_true", help="exit 1 if the committed schema is stale")
    group.add_argument("--validate", metavar="DIR", help="validate every *.json under DIR")
    args = ap.parse_args(argv)
    if args.write:
        target = Path(str(files(vocabulary().schema_package).joinpath(SCHEMA_FILE)))
        target.write_text(dumps(build_schema()), encoding="utf-8")
        print(t("records.schema.written", target=target))
        return 0
    if args.check:
        if load_schema() != build_schema():
            print(t("records.schema.stale", file=SCHEMA_FILE))
            return 1
        return 0
    try:
        problems = validate(Path(args.validate))
    except ImportError:
        print(t("records.schema.needs_jsonschema"))
        return 2
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
