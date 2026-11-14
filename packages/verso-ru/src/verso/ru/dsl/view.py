"""One record as the review page reads it (`/api/v2`): the records JSON's record, as the export
writes it, and two things the JSON does not say — which paths the source writes as a constant of a
catalog (`consts`: L9, the constants' names in `written`), and which no schema can edit (`opaque`) —
with the record's version, the hash of its call. `record_view` reads them off the source;
`node_view` is its twin for a record that has no source, only its JSON node (a folder of records
JSON): `consts` are read off `written` by the catalogs, `opaque` is empty and there is no version.

    {"record": <a records-v1 record: kind, review, written, derived, persons — a wrapper's value
                in `derived`, as v1.0 wrote it (`context_in_derived`)>,
     "consts": {<path>: <the constant's code>},
     "opaque": [<path>],
     "version": <the call's sha>}

`value_at` reads one path of a record: `written` where the source writes it, else `derived`. The page
reads a path by the same rule (its parity is `tests/golden/ui/value-at.json`).
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from verso.core.records.encode import context_in_derived, encode_record
from verso.core.records.ui import load_ui
from verso.ru.dsl import describe, paths
from verso.ru.domain import statuses as domain_statuses
from verso.ru.dsl.source import CallView, Record


def _consts(func: str, call: CallView, prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, str]]:
    """(path, code) of every argument written as a constant, items and persons included."""
    for a in call.args:
        here = (*prefix, a.param)
        value = a.value
        if value.kind == "const":
            yield paths.path_of(func, here), str(value.value)
        elif value.kind == "call" and value.call is not None:
            yield from _consts(func, value.call, here)
        elif value.kind == "list" and value.items is not None:
            for k, item in enumerate(value.items):
                if item.kind == "call" and item.call is not None:
                    yield from _consts(func, item.call, (*here, f"#{k}"))


def record_view(record: Record, built: object, record_id: str) -> dict[str, Any]:
    """`record` — the call as the source writes it — and `built`, the object a load of its file
    built of it, as the page's v2 reads one record."""
    opaque = paths.opaque(record.func, record.call)
    consts: dict[str, str] = {}
    for path, code in _consts(record.func, record.call):
        if not any(path == o or path.startswith(o + "/") for o in opaque):
            consts[path] = code
    # The page reads `written` as what the call alone wrote: a wrapper's value (a section's month, a
    # лист's flag) stands in `derived` for it, as records v1.0 wrote it.
    return {"record": context_in_derived(encode_record(built, record_id)), "consts": consts, "opaque": opaque,
            "version": record.sha}


def _group_value(node: Mapping[str, Any], key: str) -> Any:
    head, dot, tail = key.partition(".")
    if dot:
        group = node.get(head)
        return group.get(tail) if isinstance(group, Mapping) else None
    return node.get(key)


def _field(node: Mapping[str, Any], key: str) -> Any:
    """A field of a node: what `written` holds, else `derived`."""
    for part in ("written", "derived"):
        holder = node.get(part, {})
        value = _group_value(holder, key)
        if value is not None:
            return value
    return None


def value_at(record: Mapping[str, Any], path: str) -> object:
    """The value of `path` in a records-v1 `record` — None where it has none."""
    kind = load_ui()["kinds"][record["kind"]]
    segs = path.split("/")
    persons: list[Mapping[str, Any]] = record.get("persons", [])
    slots = {s["role"]: s for s in kind["slots"]}
    groups = {g["name"]: g for g in kind["groups"]}
    head, rest = segs[0], segs[1:]
    if head in slots:
        slot = None
        if "slots" in slots[head]:
            if not rest or not rest[0].isdigit():
                return None
            slot, rest = int(rest[0]), rest[1:]
        persona = next((p for p in persons if p["role"] == head and p.get("slot") == slot), None)
        if persona is None:
            return None
        return _field(persona, "/".join(rest)) if rest else persona
    if head in groups:
        group = groups[head]
        items = [p for p in persons if p["role"] == group["item"]["role"]]
        if not rest or not rest[0].isdigit():
            return None
        n = int(rest[0])
        if not 1 <= n <= len(items):
            return None
        item, rest = items[n - 1], rest[1:]
        if not rest:
            return item
        if rest[0] in group["item"]["persons"]:
            return _field(item, "/".join(rest[1:]))
        return _field(item.get("link", {}), "/".join(rest))
    return _field(record, path)


# --- the view of a record that has no source: its JSON node ------------------------------------------------

# The interface schema's name of an enumeration -> the catalog of `describe.catalogs()` that holds its
# constants (`Gender.MALE`, `Month.MAY`, `CensusRole.HEAD`). The document types of a card have none.
_ENUM_CATALOG = {"gender": "gender", "month": "month", "relationship": "relationship", "census_role": "role",
                 "side": "side"}


@domain_statuses.kept
def _status_codes() -> dict[tuple[str, str | None], str]:
    """{(text, gender): the constant's name} of the workspace's statuses. Of the constants that spell one text the
    one that sorts last: the rule the checks on JSON apply (`on_json.walk.status_name`), so a view names the
    constant a linter's fix would."""
    out: dict[tuple[str, str | None], str] = {}
    for name, value in sorted(domain_statuses.catalog().items()):
        out[(str(value), None if value.gender is None else value.gender.name.lower())] = name
    return out


@domain_statuses.kept
def _codes(catalog: str) -> dict[str, str]:
    """{the text the JSON holds: the code} of a catalog, the last of the codes that sort alike. An enumeration is
    written by the lower-cased name of its member (`male`, `january`), a marital status or a cause by its text."""
    out: dict[str, str] = {}
    for constant in sorted(describe.catalogs()[catalog], key=lambda c: c.code):
        text = constant.code.split(".")[1].lower() if catalog in _ENUM_CATALOG.values() else constant.text
        out[text] = constant.code
    return out


def _code_of(kind: str, name: str, value: object) -> str | None:
    """The constant a JSON value is, or None where it is no constant. `kind` is the field's type in the
    interface's schema: a status or a cause of death is a constant when the JSON holds it as an object (a literal
    is the bare text), an enumeration or a marital status is read by its text."""
    if kind == "enum":
        catalog = _ENUM_CATALOG.get(name)
        return _codes(catalog).get(value) if catalog is not None and isinstance(value, str) else None
    if name == "status":
        if not isinstance(value, Mapping) or not isinstance(text := value.get("text"), str):
            return None
        gender = value.get("gender")
        return _status_codes().get((text, gender if isinstance(gender, str) else None))
    if name == "cause":
        return _codes("cause").get(str(value["text"])) if isinstance(value, Mapping) and "text" in value else None
    if name == "marital":
        return _codes("marital").get(value) if isinstance(value, str) else None
    return None


def _field_consts(fields: list[Mapping[str, Any]], prefix: str, at: Mapping[str, Any],
                  skip: frozenset[str] = frozenset()) -> Iterator[tuple[str, str]]:
    """(path, code) of each constant among `fields`' values, read where `value_at` reads a path."""
    for field in fields:
        kind = field.get("type")
        name = field.get("enum") or field.get("catalog")
        if kind not in ("enum", "catalog") or not isinstance(name, str) or field["path"] in skip:
            continue
        path = f"{prefix}{field['path']}"
        code = _code_of(kind, name, value_at(at, path))
        if code is not None:
            yield path, code


def _node_consts(node: Mapping[str, Any]) -> dict[str, str]:
    ui = load_ui()
    kind = ui["kinds"][node["kind"]]
    persons: list[Mapping[str, Any]] = node.get("persons", [])
    skip = frozenset(node.get("written", {}).get("context", ()))
    out = dict(_field_consts(kind["fields"], "", node, skip))
    for slot in kind["slots"]:
        for persona in (p for p in persons if p["role"] == slot["role"]):
            prefix = slot["role"] if "slots" not in slot else f"{slot['role']}/{persona['slot']}"
            out.update(_field_consts(ui["persona"]["fields"], prefix + "/", node))
    for group in kind["groups"]:
        item = group["item"]
        for n, _ in enumerate((p for p in persons if p["role"] == item["role"]), 1):
            out.update(_field_consts(item["fields"], f"{group['name']}/{n}/", node))
            for person in item["persons"]:
                out.update(_field_consts(ui["persona"]["fields"], f"{group['name']}/{n}/{person}/", node))
    return out


def node_view(built: object, node: Mapping[str, Any], record_id: str) -> dict[str, Any]:
    """`record_view`'s twin for a record that has only its JSON node: `node` is a records-v1 record node
    holding `written` alone (the shape a folder keeps), `built` the object `replay_file` made of it. `consts`
    are the paths whose value in `written` is a constant of a catalog, by the catalog: of several constants
    that spell one text the one that sorts last (the rule of the linters on JSON, «Aliases of one constant»),
    which is not always the one an author wrote. There is no expression in JSON, so `opaque` is empty; there is
    no version either, a store keeps its own."""
    return {"record": context_in_derived(encode_record(built, record_id)), "consts": _node_consts(node),
            "opaque": []}
