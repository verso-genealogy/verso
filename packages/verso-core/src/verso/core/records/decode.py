"""A records-v1 JSON node back into the DSL objects it was written from.

Pure: a dict in, the file's record sets out — variable → set, in the documents'
order, an alias bound to the very object it names. Objects are rebuilt without their
constructors (`cls.__new__`), their `__dict__` in the field table's order, then
`_written`, then `on_geni`: the derivations already ran when the DSL was built, and
the JSON holds their results. Ids and labels are not read; the encoder makes them
again from the objects. A record's `key` and the notes (`note`, `verso.core.records.notes`)
are checked and not read: they are properties of the stored node, no part of the graph.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from verso.core import plugins
from verso.core.records import SCHEMA_ID
from verso.core.records.encode import FormatError, review
from verso.core.records.notes import check_notes
from verso.core.records.fields import (
    PERSON, WRAPPER_KEY, ClassSpec, ListOf, OneOf, TypeSpec, Vocabulary, attr_of, spec_name, member_of, param_of_key_in, param_spec_in,
    split_context, split_wrapper, ungroup, vocabulary)
from verso.core.targets.geni.held import ON_GENI
from verso.core.written import VERB_ATTR, WRAPPER_ATTR, WRITTEN_ATTR
from verso.core.messages import t

__all__ = ["FormatError", "decode_file", "decode_value"]

_SCALARS: dict[str, tuple[type, ...]] = {
    "str": (str,), "int": (int,), "bool": (bool,), "age": (int, float, str), "intstr": (int, str)}


def decode_value(data: object, spec: TypeSpec, path: str = "") -> object:
    """One JSON value back into what its field holds."""
    if data is None:
        return None
    if isinstance(spec, OneOf):
        reasons: list[ValueError] = []
        for one in spec.types:
            try:
                return decode_value(data, one, path)
            except ValueError as refused:            # a FormatError, or an enum's code no member has (`member_of`)
                reasons.append(refused)
        raise FormatError(t("records.decode.none_of", path=path, type=type(data).__name__, spec=spec_name(spec),
                            reasons="; ".join(str(r) for r in reasons))) from reasons[-1]
    kind = type(data)
    voc = None if isinstance(spec, str) and spec in _SCALARS else vocabulary()
    if voc is None:
        if kind in _SCALARS[spec]:  # type: ignore[index]
            return data
    elif spec == "strs":
        if kind is str or (kind is list and all(type(x) is str for x in data)):  # type: ignore[attr-defined]
            return list(data) if kind is list else data  # type: ignore[call-overload]
    elif isinstance(spec, str) and spec in voc.scalars:
        if kind is str:
            return data
        if kind is dict:
            return voc.scalars[spec].decode(data)  # type: ignore[arg-type]
    elif isinstance(spec, (type, tuple)) and not (isinstance(spec, type) and spec in voc.value_classes):
        if kind is str:
            return member_of(spec, data)  # type: ignore[arg-type]
    elif isinstance(spec, type) and spec in voc.value_classes:
        if kind is dict:
            return _value_object(spec, data, path)  # type: ignore[arg-type]
    elif isinstance(spec, ListOf):
        if kind is list:
            return [decode_value(item, spec.item, f"{path}[{i}]") for i, item in enumerate(data)]  # type: ignore[arg-type]
    elif spec == PERSON:
        pass
    raise FormatError(t("records.decode.wrong_type", path=path, type=kind.__name__, spec=spec_name(spec)))


def _value_object(cls: type, data: Mapping[str, Any], path: str) -> object:
    voc = vocabulary()
    spec, attrs = voc.specs[cls], voc.json_attrs[cls]
    values: dict[str, Any] = {}
    for key, value in ungroup(cls, data).items():
        if key not in attrs:
            raise FormatError(t("records.decode.no_field", path=path, cls=cls.__name__, key=repr(key)))
        values[attrs[key]] = value
    obj: Any = object.__new__(cls)
    vars(obj).update({f.name: decode_value(values[f.name], f.type, f"{path}.{f.name}") if f.name in values
                      else copy.copy(f.default) for f in spec.fields})
    return obj


def _build(cls: type, node: Mapping[str, Any], structural: Mapping[str, object], path: str) -> Any:
    """One object from its `written` and `derived`, its structural fields given."""
    voc = vocabulary()
    spec: ClassSpec = voc.specs[cls]
    attrs_of = voc.json_attrs[cls]
    derived: dict[str, Any] = {}
    for key, value in ungroup(cls, node.get("derived", {})).items():
        attr = attrs_of.get(key)
        if attr is None or attr in structural:
            raise FormatError(t("records.decode.no_derived_field", path=path, cls=cls.__name__, key=repr(key)))
        derived[attr] = value
    written: dict[str, object] | None = None
    as_attr: dict[str, object] = {}
    verb: str | None = None
    shadowed: dict[str, object] = {}
    if "written" in node:
        if cls in voc.verbs:
            verb = node["written"].get("verb")
        call, context = split_context(cls, node["written"], path)
        shadowed = {attr: decode_value(value, spec.field(attr).type, f"{path}.{WRAPPER_KEY}.{attr}")
                    for attr, value in split_wrapper(cls, node["written"], path).items()}
        for attr, value in context.items():      # a wrapper's value: on the object, not in `_written`
            if attr in structural or attr in derived:
                raise FormatError(t("records.decode.context_collides", path=path, cls=cls.__name__,
                                    key=repr(voc.json_keys[cls][attr])))
            derived[attr] = value
        params = {param_of_key_in(voc, cls, k): v for k, v in call.items()}
        written = {p: decode_value(v, param_spec_in(voc, cls, p), f"{path}.{p}") for p, v in params.items()}
        rename = voc.param_to_attr.get(cls, {})
        as_attr = {rename.get(p, p): v for p, v in written.items()}
    attrs: dict[str, object] = {}
    for f in spec.fields:
        if f.name in structural:
            attrs[f.name] = structural[f.name]
        elif f.name in derived:
            attrs[f.name] = decode_value(derived[f.name], f.type, f"{path}.{f.name}")
        elif f.name in as_attr:
            attrs[f.name] = as_attr[f.name]
        else:
            attrs[f.name] = copy.copy(f.default)
    obj: Any = object.__new__(cls)
    vars(obj).update(attrs)
    if verb is not None:      # before `_written`: the DSL's factory sets the verb, its decorator then the call
        vars(obj)[VERB_ATTR] = verb
    if written is not None:
        vars(obj)[WRITTEN_ATTR] = written
    if shadowed:              # after `_written`: a wrapper keeps it once the call has built the record
        vars(obj)[WRAPPER_ATTR] = shadowed
    return obj


def _is_entity_list(spec: TypeSpec, voc: Vocabulary) -> bool:
    return isinstance(spec, ListOf) and spec.item in voc.specs and spec.item not in voc.value_classes


def _list_field(spec: ClassSpec, role: str, voc: Vocabulary) -> tuple[str, type]:
    for f in spec.fields:
        if _is_entity_list(f.type, voc):
            if voc.item_roles[f.name] == role:      # `role_of(f.name, item=True)`'s role
                return f.name, f.type.item  # type: ignore[union-attr,return-value]
    raise KeyError(role)


def _record(node: Mapping[str, Any], sheet: object, path: str) -> Any:
    voc = vocabulary()
    cls = voc.by_code.get(node["kind"])
    if cls is None or voc.specs[cls].records_attr is not None:
        raise FormatError(t("records.decode.unknown_record", path=path, node=repr(node['kind'])))
    spec = voc.specs[cls]
    structural: dict[str, object] = {}
    for f in spec.fields:
        if f.type == PERSON:
            structural[f.name] = None
        elif _is_entity_list(f.type, voc):
            structural[f.name] = []
    structural["page"] = sheet
    for i, persona in enumerate(node["persons"]):
        where = f"{path}.persons[{i}]"
        person = _build(voc.person, persona, {}, where)
        role, slot = persona["role"], persona.get("slot")
        try:
            attr, item_cls = _list_field(spec, role, voc)
        except KeyError:
            try:
                structural[attr_of(spec, role, slot)] = person
            except KeyError:
                raise FormatError(t("records.decode.no_role", where=where, cls=cls.__name__, role=role, detail=slot or '')) from None
            continue
        items = structural[attr]
        assert isinstance(items, list)
        items.append(_build(item_cls, persona["link"], {"person": person}, f"{where}.link"))
    key = node.get("key")
    if "key" in node and (not isinstance(key, str) or not key or "/" in key):
        raise FormatError(t("records.decode.bad_key", path=path, key=repr(key)))
    check_notes(node, path)      # a stored node's notes: checked, never read into the objects
    record = _build(cls, node, structural, path)
    if node.get("review") == "on_geni":
        vars(record)[ON_GENI] = True
    if review(record, path) != node.get("review"):
        raise FormatError(t("records.decode.review_mismatch", path=path, review=repr(node.get('review'))))
    return record


def _document(node: Mapping[str, Any], path: str) -> Any:
    voc = vocabulary()
    cls = voc.by_code.get(node["kind"])
    if cls is None or voc.specs[cls].records_attr is None:
        raise FormatError(t("records.decode.unknown_set", path=path, node=repr(node['kind'])))
    spec = voc.specs[cls]
    records: list[Any] = []
    for i, run in enumerate(node["pages"]):
        sheet = decode_value(run["page"], "str", f"{path}.pages[{i}].page")
        records.extend(_record(r, sheet, f"{path}.pages[{i}].records[{j}]") for j, r in enumerate(run["records"]))
    assert spec.records_attr is not None
    return _build(cls, node, {spec.records_attr: records}, path)


def check_vocabulary(doc: Mapping[str, Any]) -> None:
    """Refuse a file written in a newer vocabulary than its plugin reads. A file without the
    header key, or of a plugin not enabled here, is read as before; replay and the graph read nothing of it."""
    found = doc.get("vocabulary")
    if found is None:
        return
    if not (isinstance(found, Mapping) and isinstance(found.get("plugin"), str)
            and isinstance(found.get("version"), int) and not isinstance(found.get("version"), bool)):
        raise FormatError(t("records.decode.bad_vocabulary", found=repr(found)))
    known = plugins.known_vocabulary_version(found["plugin"])
    if known is not None and found["version"] > known:
        raise FormatError(t("records.decode.newer_vocabulary", plugin=found["plugin"],
                            version=found["version"], known=known))


def decode_file(doc: Mapping[str, Any]) -> dict[str, Any]:
    """The record sets of a records-v1 file node, by variable, in its order."""
    if doc.get("schema") != SCHEMA_ID:
        raise FormatError(t("records.decode.other_schema", wanted=SCHEMA_ID, found=repr(doc.get('schema'))))
    check_vocabulary(doc)
    check_notes(doc, "file")
    out: dict[str, Any] = {}
    for node in doc["documents"]:
        variable = node["variable"]
        if "alias_of" in node:
            out[variable] = out[node["alias_of"]]
        else:
            out[variable] = _document(node, variable)
    return out
