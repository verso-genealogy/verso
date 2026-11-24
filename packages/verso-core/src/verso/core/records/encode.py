"""The built DSL records of one file as a records-v1 JSON node.

Pure: a module's record sets in, a dict out (`verso.core.pipeline.records` writes it). The
layout — documents, page runs, records, personas, `written`/`derived` — and the value
encodings are those of the records-v1 format. It refuses rather than guesses: a class or an
attribute the field table lacks, a value of another type than its field's, and an
entity reached twice, which JSON v0 cannot share.
"""
from __future__ import annotations

import warnings
from collections.abc import Mapping
from enum import Enum
from typing import Any, overload

from verso.core import plugins
from verso.core.records import SCHEMA_ID, FormatError
from verso.core.records.fields import (
    CONTEXT_KEY, PERSON, WRAPPER_KEY, ClassSpec, ListOf, TypeSpec, code, enum_code, flatten, group, nest, param_spec_in,
    role_of, ungroup, vocabulary, written_key_in)
from verso.core.records.ids import (
    Ids, book_key, person_label, persona_id, record_label, records_of)
from verso.core.targets.geni.held import ON_GENI
from verso.core.written import VERB_ATTR, WRAPPER_ATTR, WRITTEN_ATTR, verb_of, wrapper_of, written_of
from verso.core.messages import t

#: Attributes an object may hold beside its table's fields.
CONDITIONAL = (WRITTEN_ATTR, VERB_ATTR, WRAPPER_ATTR, ON_GENI)


class SharedEntity(FormatError):
    """One entity reached at two places."""


_PLAIN = (str, int, float, bool, type(None))


def same(a: object, b: object) -> bool:
    """Equal and of one type — `0` is not `False`, `""` not `None`, a `Status` keeps its gender
    (a scalar of the vocabulary is compared by its own `same`)."""
    if type(a) is not type(b):
        return False
    if type(a) in _PLAIN:
        return a == b
    voc = vocabulary()
    for scalar in voc.scalars.values():
        if isinstance(a, scalar.type):
            return scalar.same(a, b)
    if isinstance(a, Enum):
        return a is b
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))  # type: ignore[arg-type]
    if type(a) in voc.value_classes:
        va, vb = vars(a), vars(b)
        return list(va) == list(vb) and all(same(va[k], vb[k]) for k in va)
    return a == b


_EXACT: dict[str, type] = {"str": str, "int": int, "bool": bool}


def _is_entity_list(spec: TypeSpec) -> bool:
    if not (isinstance(spec, ListOf) and isinstance(spec.item, type)):
        return False
    voc = vocabulary()
    return spec.item in voc.specs and spec.item not in voc.value_classes


def encode_value(value: object, spec: TypeSpec, path: str = "") -> object:
    """One value as JSON, by its field's type."""
    if value is None:
        return None
    kind = type(value)
    if isinstance(spec, str) and spec in _EXACT and kind is _EXACT[spec]:
        return value
    if spec == "age" and kind in (int, float, str):
        return value
    if spec == "intstr" and kind in (int, str):
        return value
    if spec == "strs" and (kind is str or (kind is list and all(type(x) is str for x in value))):  # type: ignore[attr-defined]
        return value
    voc = vocabulary()
    if isinstance(spec, str) and spec in voc.scalars:
        if kind is str:
            return value
        if isinstance(value, voc.scalars[spec].type):
            return voc.scalars[spec].encode(value)
    if isinstance(spec, type) and issubclass(spec, Enum) and isinstance(value, spec):
        return code(value)
    if isinstance(spec, tuple) and kind in spec:
        return f"{enum_code(kind)}.{code(value)}"  # type: ignore[arg-type]
    if isinstance(spec, type) and spec in voc.value_classes and kind is spec:
        return _value_object(value, path)
    if isinstance(spec, ListOf) and kind is list:
        if _is_entity_list(spec) and value:
            raise FormatError(t("records.encode.list_of_entities", path=path))
        return [encode_value(item, spec.item, f"{path}[{i}]") for i, item in enumerate(value)]  # type: ignore[arg-type]
    raise FormatError(t("records.encode.wrong_type", path=path, type=kind.__name__, spec=_spec_name(spec)))


def _spec_name(spec: TypeSpec) -> str:
    if isinstance(spec, tuple):
        return " | ".join(c.__name__ for c in spec)
    if isinstance(spec, type):
        return spec.__name__
    if isinstance(spec, ListOf):
        return f"list[{_spec_name(spec.item)}]"
    return spec


def _value_object(value: object, path: str) -> dict[str, object]:
    spec = vocabulary().specs[type(value)]
    _check_attributes(value, spec, path)
    attrs = vars(value)
    return nest(type(value), {f.name: encode_value(attrs[f.name], f.type, f"{path}.{f.name}")
                              for f in spec.fields if not same(attrs[f.name], f.default)})


def _check_attributes(obj: object, spec: ClassSpec, path: str) -> None:
    names = {f.name for f in spec.fields}
    for attr in vars(obj):
        if attr not in names and attr not in CONDITIONAL:
            raise FormatError(t("records.encode.no_field_in_vocabulary", cls=type(obj).__name__, attr=attr, package=vocabulary().schema_package, path=path))
    for f in spec.fields:
        if f.name not in vars(obj):
            raise FormatError(t("records.encode.no_attribute", cls=type(obj).__name__, name=f.name, path=path))


def _wrapper_field(spec: ClassSpec, shadowed: frozenset[str], written: Mapping[str, object], attr: str,
                   path: str) -> Any:
    """The field a wrapper's kept value (`shadow`) is of: one a wrapper keeps (`Vocabulary.shadowed`), which the
    call wrote."""
    if attr not in shadowed or attr not in written:
        raise FormatError(t("records.encode.wrapper_field", cls=spec.cls.__name__, attr=attr, path=path))
    return spec.field(attr)


def _structural(spec: ClassSpec) -> set[str]:
    return {f.name for f in spec.fields if f.type == PERSON or _is_entity_list(f.type)}


class _Encoder:
    def __init__(self, ids: Ids) -> None:  # `encode_record` passes none: it is given its record's id
        self.ids = ids
        self.entities: dict[int, str] = {}
        self.given: dict[tuple[int, type], dict[str, object]] = {}     # `_inherited`, once per set and class

    def claim(self, obj: object, path: str) -> None:
        if id(obj) in self.entities:
            raise SharedEntity(t("records.encode.shared", entities=self.entities[id(obj)], path=path))
        self.entities[id(obj)] = path

    def node(self, obj: object, path: str, skip: set[str],
             inherited: Mapping[str, object] | None = None) -> dict[str, object]:
        """`written` and `derived` of one object. `inherited` is what its record set holds of the fields it gives the
        object (`_inherited`): a wrapper's value equal to the field's default is still written when it is not the
        set's."""
        cls = type(obj)
        voc = vocabulary()
        if cls not in voc.specs:
            raise FormatError(t("records.encode.no_class", cls=cls.__name__, package=voc.schema_package, path=path))
        spec = voc.specs[cls]
        _check_attributes(obj, spec, path)
        self.claim(obj, path)
        out: dict[str, object] = {}
        written = written_of(obj)
        rename = voc.param_to_attr.get(cls, {})
        as_attr: dict[str, object] = {}
        attrs = vars(obj)
        wrapped: dict[str, object] = {}
        if written is not None:
            flat = {written_key_in(voc, cls, p): encode_value(v, param_spec_in(voc, cls, p), f"{path}.{p}")
                    for p, v in written.items()}
            as_attr = {rename.get(p, p): v for p, v in written.items()}
            # What a wrapper set and the call did not write goes beside the call's keys, under its
            # own key, and the marker names it (records v1.x); `derived` then does not hold it.
            context = voc.context.get(cls, frozenset())
            given = inherited or {}
            for f in spec.fields:
                if f.name not in context or f.name in skip or f.name in as_attr:
                    continue
                value = attrs[f.name]
                # A value equal to its default is left out, but for one the set would not give: a field the set
                # gives (`Vocabulary.inherited`) whose default is a value (a name-list entry's `reviewed:bool=True`)
                # takes the set's when unstated, so `page(…, reviewed=True)` in a held set is written. A default
                # `None` is the unstated mark itself: a record that still holds it was given nothing by its set.
                if (not same(value, f.default)
                        or (f.default is not None and f.name in given and not same(value, given[f.name]))):
                    wrapped[f.name] = encode_value(value, f.type, f"{path}.{f.name}")
            keys = voc.json_keys[cls]
            flat.update({keys[attr]: value for attr, value in wrapped.items()})
            out["written"] = group(flat)
            if wrapped:
                out["written"][CONTEXT_KEY] = [keys[attr] for attr in wrapped]  # type: ignore[index]
            # What a wrapper would have set on a field the call wrote itself (records v1.x), beside the marker.
            shadowed = wrapper_of(obj)
            if shadowed:
                out["written"][WRAPPER_KEY] = group({  # type: ignore[index]
                    keys[attr]: encode_value(value, _wrapper_field(spec, voc.shadowed.get(cls, frozenset()), as_attr,
                                                                   attr, path).type,
                                             f"{path}.{WRAPPER_KEY}.{attr}")
                    for attr, value in shadowed.items()})
            verb = verb_of(obj)
            if verb is not None and cls in voc.verbs:
                if verb not in voc.verbs[cls]:
                    raise FormatError(t("records.encode.unknown_verb", cls=cls.__name__, verb=repr(verb), path=path))
                out["written"] = {"verb": verb, **out["written"]}  # type: ignore[dict-item]
        derived: dict[str, object] = {}
        for f in spec.fields:
            if f.name in skip or f.name in wrapped:
                continue
            value = attrs[f.name]
            if f.name in as_attr:
                if same(value, as_attr[f.name]):
                    continue
            elif same(value, f.default):
                continue
            derived[f.name] = encode_value(value, f.type, f"{path}.{f.name}")
        out["derived"] = nest(cls, derived)
        return out

    def persons(self, record: object, record_id: str, path: str) -> list[dict[str, object]]:
        spec = vocabulary().specs[type(record)]
        out: list[dict[str, object]] = []
        attrs: dict[str, Any] = vars(record)
        for f in spec.fields:
            value = attrs[f.name]
            if f.type == PERSON and value is not None:
                role, slot = role_of(f.name)
                out.append(self.persona(value, record_id, role, slot, f"{path}.{f.name}"))
            elif _is_entity_list(f.type):
                role, _ = role_of(f.name, item=True)
                for i, item in enumerate(value or []):
                    slot = item.number if role == "member" else i + 1
                    item_path = f"{path}.{f.name}[{i}]"
                    link = self.node(item, item_path, {"person"})
                    out.append(self.persona(item.person, record_id, role, slot, f"{item_path}.person",
                                            link))
        return out

    def persona(self, person: Any, record_id: str, role: str, slot: int | None, path: str,
                link: dict[str, object] | None = None) -> dict[str, object]:
        node: dict[str, object] = {"id": persona_id(record_id, role, slot)}
        label = person_label(person)
        if label:
            node["label"] = label
        node["role"] = role
        if slot is not None:
            node["slot"] = slot
        if link is not None:
            node["link"] = link
        node.update(self.node(person, path, set()))
        return node

    def record(self, record_set: object, record: Any, path: str) -> dict[str, object]:
        voc = vocabulary()
        if type(record) not in voc.specs:
            raise FormatError(t("records.encode.no_class", cls=type(record).__name__, package=voc.schema_package, path=path))
        key = (id(record_set), type(record))
        if key not in self.given:
            self.given[key] = _inherited(record_set, record)
        return self.record_node(record, self.ids.of(record_set, record), path, self.given[key])

    def record_node(self, record: Any, record_id: str, path: str,
                    inherited: Mapping[str, object]) -> dict[str, object]:
        voc = vocabulary()
        spec = voc.specs.get(type(record))
        if spec is None:
            raise FormatError(t("records.encode.no_class", cls=type(record).__name__, package=voc.schema_package, path=path))
        node: dict[str, object] = {"id": record_id}
        label = record_label(record)
        if label:
            node["label"] = label
        node["kind"] = spec.code
        node["review"] = review(record, path)
        node.update(self.node(record, path, _structural(spec) | {"page"}, inherited))
        node["persons"] = self.persons(record, record_id, path)
        return node

    def document(self, variable: str, record_set: Any) -> dict[str, object]:
        spec = vocabulary().specs.get(type(record_set))
        if spec is None or spec.records_attr is None:
            raise FormatError(t("records.encode.not_a_set", variable=variable, type=type(record_set).__name__))
        node: dict[str, object] = {"id": self.ids.document_id(book_key(record_set)),
                                   "variable": variable, "kind": spec.code}
        node.update(self.node(record_set, variable, {spec.records_attr}))
        pages: list[dict[str, Any]] = []
        for i, record in enumerate(records_of(record_set)):     # `ids.walk`'s order
            where = f"{variable}.{spec.records_attr}[{i}]"
            encoded = self.record(record_set, record, where)
            sheet = encode_value(record.page, "str", f"{where}.page")
            if pages and same(pages[-1]["page"], sheet):
                pages[-1]["records"].append(encoded)
            else:
                pages.append({"page": sheet, "records": [encoded]})
        node["pages"] = pages
        return node


_UNNAMED: Any = object()     # `encode_record`'s `record_set` left out: a caller written before the keyword


@overload
def encode_record(record: object, record_id: str, path: str = "record", *,
                  record_set: object | None) -> dict[str, object]: ...
@overload
@warnings.deprecated("encode_record without record_set=: pass the record set, or None for a view; required from 0.2")
def encode_record(record: object, record_id: str, path: str = "record") -> dict[str, object]: ...
def encode_record(record: object, record_id: str, path: str = "record", *,
                  record_set: object | None = _UNNAMED) -> dict[str, object]:
    """One record as the export writes it under its record set — `id`, `label`, `kind`, `review`,
    `written`, `derived`, `persons` — given the id its file's walk counts it by (the review
    page's view of one record, `verso.ru.dsl.view`): the node the export writes (`_Encoder.record`), given its
    `record_set`. `record_set=None` says there is none to hand: a wrapper's value equal to its field's default is then
    left out even where the set holds another (`Vocabulary.inherited`), so the node reads as `decode_file` reads it but
    replays with the set's value — a view's node, not one to store. Left out, it is `None` and warns
    (`DeprecationWarning`); from 0.2 it is required."""
    if record_set is _UNNAMED:
        warnings.warn(str(t("records.encode.no_record_set")), DeprecationWarning, stacklevel=2)
        record_set = None
    return _Encoder(_NO_IDS).record_node(record, record_id, path, _inherited(record_set, record))


def _inherited(record_set: object | None, record: object) -> dict[str, object]:
    """What `record_set` holds of the fields it gives `record` when the record leaves them unstated
    (`Vocabulary.inherited`): a list's `reviewed` for its entries. Nothing without a set."""
    voc = vocabulary()
    if record_set is None or type(record_set) not in voc.specs:
        return {}
    held = vars(record_set)
    return {name: held[name] for name in voc.inherited.get(type(record), frozenset()) if name in held}


_NO_IDS: Any = None


def context_in_derived(node: Mapping[str, Any]) -> dict[str, Any]:
    """A record node as records v1.0 wrote it: the values `written.context` names moved back into
    `derived`, in the field table's order, the marker and `written.wrapper` dropped — byte for byte what
    the encoder wrote before v1.x. For a reader that takes `written` as what the call alone wrote (the review
    page, `verso.ru.dsl.view`). A node without the marker comes back as it is."""
    written = node.get("written")
    if not isinstance(written, Mapping) or (CONTEXT_KEY not in written and WRAPPER_KEY not in written):
        return dict(node)
    if CONTEXT_KEY not in written:      # v1.0 kept no wrapper's value of a field the call wrote
        return {**node, "written": {k: v for k, v in written.items() if k != WRAPPER_KEY}}
    voc = vocabulary()
    cls = voc.by_code[node["kind"]]
    flat = ungroup(cls, {k: v for k, v in written.items() if k not in (CONTEXT_KEY, WRAPPER_KEY)})
    moved = {voc.json_attrs[cls][key]: flat.pop(key) for key in written[CONTEXT_KEY]}
    derived = {**flatten(cls, node.get("derived", {})), **moved}
    out = dict(node)
    out["written"] = group(flat)
    out["derived"] = nest(cls, {f.name: derived[f.name] for f in voc.specs[cls].fields if f.name in derived})
    return out


def review(record: object, path: str = "") -> str:
    """`reviewed`, `held` (unreviewed, kept off Geni) or `on_geni` (unreviewed, listed)."""
    reviewed = getattr(record, "reviewed", None)
    if ON_GENI in vars(record):
        if vars(record)[ON_GENI] is not True or reviewed is not False:
            raise FormatError(t("records.encode.on_geni_not_held", path=path))
        return "on_geni"
    return "held" if reviewed is False else "reviewed"


def encode_namespace(namespace: Mapping[str, object], *, village: str, file: str, sha256: str,
                     ids: Ids) -> dict[str, object]:
    """The record sets of one DSL file, in the module's order, as a records-v1 file node."""
    encoder = _Encoder(ids)
    named: dict[int, str] = {}
    documents: list[dict[str, object]] = []
    for variable, record_set in namespace.items():
        if id(record_set) in named:
            documents.append({"variable": variable, "alias_of": named[id(record_set)]})
            continue
        named[id(record_set)] = variable
        documents.append(encoder.document(variable, record_set))
    return {"schema": SCHEMA_ID, "village": village, "file": file, "sha256": sha256,
            **plugins.records_header(), "documents": documents}
