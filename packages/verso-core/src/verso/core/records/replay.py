"""A records-v1 file rebuilt by the DSL's own factories from `written` (L10 part 1).

`decode_file` rebuilds the objects without their constructors and takes every derived value
from the JSON. `replay_file` calls the factories instead, bottom up as the DSL computes:
a record's persons, then its link items (a relative, a member), then the record, then its
set — so what a constructor or a set's factory derives (a child's surname, a book's default
status, a running number) is derived again, and `_written` is the factory's own. No source
is read and nothing is `exec`'d.

What a wrapper set — a section's month, a sheet's provenance — no call wrote: the vocabulary
names those attributes (`Vocabulary.context`). Records v1.x writes them into `written`, the
marker `written.context` naming their keys; they are taken out before the factory is called
and set on the built record after it (`split_context`). An export of before keeps them in
`derived` alone: `context=True` (the default) reads those — the only derived values read —
and `context=False` reads none. What a wrapper would have set on a field the call wrote itself
(`written.wrapper`) changes no value — the call's stands, as in the DSL — and is kept on the record as
the wrapper kept it (`verso.core.written.shadow`). A node whose `written` fits no factory of its class,
or more than one, is a `ReplayGap`.

`replay_record` builds ONE record, given its set's header, its лист and its `Position` in the set: a record
is a function of its `written`, its set's header and two counters its place in the set gives (the 1-based
`index` of a list's entry, the roll's running number over a household's members) — the neighbours play no
part. `position_values` names those counters without building anything.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from verso.core.i18n import Message
from verso.core.messages import t
from verso.core.records import SCHEMA_ID, FormatError
from verso.core.records.decode import check_vocabulary, decode_value
from verso.core.records.fields import (
    CONTEXT_KEY, WRAPPER_KEY, ClassSpec, ListOf, Vocabulary, attr_of, param_names, param_spec_in, role_of,
    split_context_in, split_wrapper, takes_records, ungroup_in, vocabulary)
from verso.core.targets.geni.held import ON_GENI
from verso.core.written import VERB_ATTR, WRAPPER_ATTR

__all__ = ["Position", "ReplayGap", "position_values", "replay_alone", "replay_file", "replay_record"]


class ReplayGap(FormatError):
    """A node no factory of its class can be told to build from what it wrote."""

    def __init__(self, message: Message) -> None:
        super().__init__(message)
        self.message = message


# The vocabulary is asked once a book (`_document`) and handed down: a book replays every field of every record.

def _param_of_attr(voc: Vocabulary, cls: type, attr: str) -> str:
    for param, target in voc.param_to_attr.get(cls, {}).items():
        if target == attr:
            return param
    return attr


def _written(voc: Vocabulary, cls: type, node: Mapping[str, Any],
             path: str) -> tuple[dict[str, object], dict[str, object]]:
    """What the call wrote, by parameter, and what a wrapper set, by attribute (`split_context`)."""
    call, wrapped = split_context_in(voc, cls, node.get("written", {}), path)
    renamed = voc.params_of_keys.get(cls, {})
    params = {renamed.get(k, k): v for k, v in call.items()}
    spec = voc.specs[cls]
    return ({p: decode_value(v, param_spec_in(voc, cls, p), f"{path}.{p}") for p, v in params.items()},
            {a: decode_value(v, spec.field(a).type, f"{path}.{a}") for a, v in wrapped.items()})


def _shadowed(voc: Vocabulary, cls: type, node: Mapping[str, Any], path: str) -> dict[str, object]:
    """`written.wrapper`, decoded by attribute (`split_wrapper`)."""
    if WRAPPER_KEY not in node.get("written", {}):      # `split_wrapper`'s {}, without asking the vocabulary
        return {}
    spec = voc.specs[cls]
    return {a: decode_value(v, spec.field(a).type, f"{path}.{WRAPPER_KEY}.{a}")
            for a, v in split_wrapper(cls, node.get("written", {}), path).items()}


def _derived_context(voc: Vocabulary, cls: type, node: Mapping[str, Any], path: str) -> dict[str, object]:
    """What a wrapper set that only `derived` holds — an export of before v1.x, or a value the call
    wrote and a wrapper changed: the attributes `written.context` does not name."""
    wanted = voc.context.get(cls, frozenset())
    if not wanted:
        return {}
    marked = {voc.json_attrs[cls].get(k) for k in node.get("written", {}).get(CONTEXT_KEY) or ()}
    spec = voc.specs[cls]
    out: dict[str, object] = {}
    for key, value in ungroup_in(voc, cls, node.get("derived", {})).items():
        attr = voc.json_attrs[cls].get(key)
        if attr in wanted and attr not in marked:
            out[attr] = decode_value(value, spec.field(attr).type, f"{path}.{attr}")
    return out


def _verb(voc: Vocabulary, spec: ClassSpec, node: Mapping[str, Any], path: str) -> str | None:
    """The verb the node names, or None: a class with none, or an export that does not say."""
    verbs = voc.verbs.get(spec.cls)
    verb = node.get("written", {}).get("verb") if verbs else None
    if verb is not None and (not isinstance(verb, str) or verb not in (verbs or {})):
        raise FormatError(t("records.replay.unknown_verb", path=path, cls=spec.cls.__name__, verb=repr(verb)))
    return verb


def _factory(voc: Vocabulary, spec: ClassSpec, keys: frozenset[str], path: str,
             verb: str | None = None) -> Callable[..., object]:
    if verb is not None:
        return voc.verbs[spec.cls][verb]
    fn = spec.factory_for(keys)
    if fn is not None:
        return fn
    found = spec.factories_for(keys)
    if not found:
        raise ReplayGap(t("records.replay.no_factory", path=path, cls=spec.cls.__name__, keys=sorted(keys)))
    raise ReplayGap(t("records.replay.ambiguous_factory", path=path, cls=spec.cls.__name__, keys=sorted(keys),
                      factories=[fn.__name__ for fn in found]))


def _call(voc: Vocabulary, cls: type, node: Mapping[str, Any], given: Mapping[str, object],
          lists: Mapping[str, list[object]], path: str) -> Any:
    """`cls` built by its factory: what `node` wrote, the persons `given` by parameter, and its
    entity lists — by keyword where the factory names them, else as its `*records`."""
    spec = voc.specs[cls]
    written, wrapped = _written(voc, cls, node, path)
    kwargs = {**written, **given}
    verb = _verb(voc, spec, node, path)
    fn = _factory(voc, spec, frozenset(kwargs), path, verb)
    names = param_names(fn)
    varargs: list[object] = []
    takes_varargs = takes_records(fn)
    for param, items in lists.items():
        if param in names:
            if items:
                kwargs[param] = items
        elif takes_varargs and not varargs:
            varargs = items
        elif items:          # a list the factory has no place for: never dropped quietly
            raise ReplayGap(t("records.replay.no_list", path=path, cls=spec.cls.__name__, param=param))
    if takes_varargs:
        args: list[object] = []
        for p in inspect.signature(fn).parameters.values():
            if p.kind is inspect.Parameter.VAR_POSITIONAL:
                break
            args.append(kwargs.pop(p.name) if p.name in kwargs else p.default)
        built = fn(*args, *varargs, **kwargs)
    else:
        built = fn(**kwargs)
    if verb is not None:
        vars(built)[VERB_ATTR] = verb
    vars(built).update(wrapped)      # what a wrapper set: on the record, after its call
    shadowed = _shadowed(voc, cls, node, path)
    if shadowed:                     # what a wrapper would have set on a field the call wrote (`shadow`)
        vars(built)[WRAPPER_ATTR] = shadowed
    return built


def _is_entity_list(voc: Vocabulary, kind: object) -> bool:
    return (isinstance(kind, ListOf) and isinstance(kind.item, type) and kind.item in voc.specs
            and kind.item not in voc.value_classes)


def _record(voc: Vocabulary, node: Mapping[str, Any], sheet: object, context: bool, path: str) -> Any:
    cls = voc.by_code.get(node["kind"])
    if cls is None or voc.specs[cls].records_attr is not None:
        raise FormatError(t("records.decode.unknown_record", path=path, node=repr(node["kind"])))
    spec = voc.specs[cls]
    persons: dict[str, object] = {}
    lists: dict[str, list[object]] = {}
    entity_lists = [f for f in spec.fields if _is_entity_list(voc, f.type)]
    for f in entity_lists:
        lists[_param_of_attr(voc, cls, f.name)] = []
    for i, persona in enumerate(node["persons"]):
        where = f"{path}.persons[{i}]"
        person = _call(voc, voc.person, persona, {}, {}, where)
        role, slot = persona["role"], persona.get("slot")
        item = next((f for f in entity_lists if role_of(f.name, item=True)[0] == role), None)
        if item is None:
            try:
                attr = attr_of(spec, role, slot)
            except KeyError:
                raise FormatError(t("records.decode.no_role", where=where, cls=cls.__name__, role=role,
                                    detail=slot or "")) from None
            persons[_param_of_attr(voc, cls, attr)] = person
            continue
        assert isinstance(item.type, ListOf) and isinstance(item.type.item, type)
        link_cls = item.type.item
        lists[_param_of_attr(voc, cls, item.name)].append(
            _call(voc, link_cls, persona["link"], {_param_of_attr(voc, link_cls, "person"): person}, {},
                  f"{where}.link"))
    record = _call(voc, cls, node, persons, lists, path)
    if "page" in vars(record):
        vars(record)["page"] = sheet
    if context:
        vars(record).update(_derived_context(voc, cls, node, path))
    return record


def _document(node: Mapping[str, Any], context: bool, path: str) -> Any:
    voc = vocabulary()
    cls = voc.by_code.get(node["kind"])
    if cls is None or voc.specs[cls].records_attr is None:
        raise FormatError(t("records.decode.unknown_set", path=path, node=repr(node["kind"])))
    spec = voc.specs[cls]
    records: list[Any] = []
    nodes: list[Mapping[str, Any]] = []
    for i, run in enumerate(node["pages"]):
        sheet = decode_value(run["page"], "str", f"{path}.pages[{i}].page")
        for j, r in enumerate(run["records"]):
            records.append(_record(voc, r, sheet, context, f"{path}.pages[{i}].records[{j}]"))
            nodes.append(r)
    assert spec.records_attr is not None
    built = _call(voc, cls, node, {}, {_param_of_attr(voc, cls, spec.records_attr): records}, path)
    for record, r in zip(getattr(built, spec.records_attr), nodes, strict=True):
        if r.get("review") == "on_geni":
            vars(record)[ON_GENI] = True
    return built


def replay_file(data: Mapping[str, Any], *, context: bool = True) -> dict[str, object]:
    """The record sets of a records-v1 file node, by variable, built by their factories: what
    `decode_file` gives, an alias the very object it names, every derived value made again but
    the wrappers' values, which `written` names (`written.context`) — and, with `context=True`, a
    wrapper's value only `derived` holds (an export of before v1.x). A node the schema
    would refuse, or a value a constructor refuses, is a `FormatError`: validate a node from outside
    (`verso.core.records.schema`) before trusting its message."""
    if data.get("schema") != SCHEMA_ID:
        raise FormatError(t("records.decode.other_schema", wanted=SCHEMA_ID, found=repr(data.get("schema"))))
    check_vocabulary(data)
    out: dict[str, object] = {}
    for i, node in enumerate(data["documents"]):
        try:
            variable = node["variable"]
            out[variable] = out[node["alias_of"]] if "alias_of" in node else _document(node, context, variable)
        except FormatError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            # A node the schema would refuse (a key of no field, a slot without its role), or a value a
            # constructor refuses: what the caller handed is malformed, said as such — never a bare error.
            raise FormatError(t("records.replay.malformed", path=f"documents[{i}]",
                                error=f"{type(exc).__name__}: {exc}")) from exc
    return out



# --- one record alone -------------------------------------------------------------------------------

@dataclass(frozen=True)
class Position:
    """A record's place in its record set, in the order of the export: `ordinal` is 0-based, and
    `members_before` the running number a roll has reached before this record's members (the number its
    first member takes is the next one; 0 for every record that has no running number). Only a structural
    act — an insertion, a removal, a move — changes it for the records after the one acted on."""
    ordinal: int
    members_before: int = 0


def _members(cls: type, node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The link nodes of the record's numbered list, in persona order (the order the factory takes them in)."""
    voc = vocabulary()
    numbering = voc.positional[cls].numbering
    assert numbering is not None
    role = voc.item_roles[numbering.items]
    return [p["link"] for p in node.get("persons", ()) if p.get("role") == role and "link" in p]


def _numbered(cls: type, node: Mapping[str, Any], start: int) -> dict[int, int]:
    """{place of a member in its list: the running number the book gives it}, for the members the count
    reaches: as a roll's autonumbering goes — a skipped member takes none, an integer written whole is kept and
    the count continues from it, anything else written leaves the count where it stood."""
    voc = vocabulary()
    numbering = voc.positional[cls].numbering
    assert numbering is not None
    item = voc.item_class(cls, numbering.items)
    keys = voc.json_keys[item]
    counter = start
    out: dict[int, int] = {}
    for place, link in enumerate(_members(cls, node)):
        written = link.get("written", {})
        if written.get(keys[numbering.skipped]):
            continue
        own = written.get(keys[numbering.attr])
        if own is None:
            counter += 1
            out[place] = counter
        elif isinstance(own, int):
            counter = own
    return out


def position_values(node: Mapping[str, Any], *, position: Position) -> dict[str, int]:
    """The values a record's place in its set gives it, by path in its `derived` (`"index"`,
    `"members[3].record_number"`, a member's place counted from 0), without building the record: what a store
    writes into the rows of the records after a structural act. A record that has no place-given value
    gives `{}`; a member that wrote its own number gives nothing for it."""
    voc = vocabulary()
    cls = voc.by_code.get(node["kind"])
    held = voc.positional.get(cls) if cls is not None else None
    out: dict[str, int] = {}
    if held is None or cls is None:
        return out
    if held.index is not None:
        out[voc.json_keys[cls][held.index]] = position.ordinal + 1
    if held.numbering is not None:
        item = voc.item_class(cls, held.numbering.items)
        key = voc.json_keys[item][held.numbering.attr]
        out.update({f"{voc.json_keys[cls][held.numbering.items]}[{place}].{key}": number
                    for place, number in _numbered(cls, node, position.members_before).items()})
    return out


def _place(record: Any, node: Mapping[str, Any], position: Position) -> None:
    """Set on a record built alone what its place in the set gives (`Positional`)."""
    voc = vocabulary()
    held = voc.positional.get(type(record))
    if held is None:
        return
    if held.index is not None:
        vars(record)[held.index] = position.ordinal + 1
    if held.numbering is not None:
        built = getattr(record, held.numbering.items)
        links = _members(type(record), node)
        if len(built) != len(links):
            raise ReplayGap(t("records.replay.members_differ", path=node.get("id", "?"), nodes=len(links),
                              built=len(built)))
        for place, number in _numbered(type(record), node, position.members_before).items():
            vars(built[place])[held.numbering.attr] = number


def replay_alone(node: Mapping[str, Any], *, header: Mapping[str, Any], page: str | None, position: Position,
                 context: bool = False) -> tuple[Any, Any]:
    """The record set built around one record, and the record: `header` is the set's node without its
    `pages`, `page` the leaf the record stands on, `position` its place. The record is what the set's own
    factory makes of it — the book's defaults, the parish's clergy, the `on_geni` mark — with the counters of
    its place set (`replay_record` is its second half)."""
    where = str(node.get("id", "record"))
    try:
        one: dict[str, Any] = {key: value for key, value in header.items() if key not in ("pages", "alias_of")}
        one["pages"] = [{"page": page, "records": [node]}]
        built = _document(one, context, where)
        spec = vocabulary().specs[type(built)]
        assert spec.records_attr is not None
        record = getattr(built, spec.records_attr)[0]
        _place(record, node, position)
    except FormatError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise FormatError(t("records.replay.malformed", path=where, error=f"{type(exc).__name__}: {exc}")) from exc
    return built, record


def replay_record(node: Mapping[str, Any], *, header: Mapping[str, Any], page: str | None, position: Position,
                  context: bool = False) -> object:
    """One record of a records-v1 file, built alone as its set's factory builds it in the book.

    `header` is the record set's node without its `pages` — its `written` holds the book's defaults, its
    parish, `civil`, `reviewed` — `page` the leaf the record stands on and `position` its place in the set.
    Equal to the record `replay_file` makes of the same node in its book (`first_difference` finds nothing):
    a record is a function of its `written` and its header, and of nothing else but the two counters
    `position` gives. A `FormatError` as `replay_file` raises it."""
    return replay_alone(node, header=header, page=page, position=position, context=context)[1]
