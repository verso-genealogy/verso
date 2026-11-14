"""Every field the built DSL objects hold, in the order `vars()` shows it — the mechanism.

The table itself is the plugin's: `Vocabulary`, `plugins.dsl().vocabulary` — the Russian
books' is `verso.ru.records.vocabulary`. One row per attribute: its name, its type and the
value it holds when the call wrote nothing and nothing derived it. The encoder writes a
field only where it differs from what its call wrote or, unwritten, from that default; the
decoder rebuilds `__dict__` in this order, because Verso's people index walks it in order.
A class or an attribute the table lacks is refused by the encoder, so a new DSL field fails
a test instead of going missing from the JSON.

The `type` of a field is one of:

* `"str"`, `"int"`, `"bool"`, `"age"` (int, float or str — a scribe's «15.5», «6 мес»),
  `"intstr"` (int or str — `record_num` «12а», `family_id`), `"strs"` (str or a list of
  them — `scan_file`);
* a scalar of the vocabulary (`Scalar`: the Russian books' `"status"`, a `Status`, and
  `"cause"`, a `CauseOfDeath` — each a plain str too);
* an enum class, or a tuple of them where a field takes several (`document_type`);
* a value class (`EventDate`, `SourceCitation`, `RecordDefaults`), written whole;
* `PERSON`, or `ListOf(...)` of a type — a list of entities (`relatives`, `members`)
  or of values (`labels`).

A field is written in the JSON under its key (records v1): its attribute's name unless
the vocabulary's `json_names` names it otherwise. A dotted key — `birth.day` — puts the
field into a group, one object for the fields of one event or one name; groups are one level
deep. A person's slot takes no key of its own: it is a persona, named by its role.

No table is read at import: every lookup asks `vocabulary()` when it runs.
"""
from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from functools import cache, cached_property
from typing import Any

from verso.core import plugins
from verso.core.messages import t
from verso.core.records import FormatError

PERSON = "person"


@dataclass(frozen=True)
class ListOf:
    item: TypeSpec


type TypeSpec = str | type | tuple[type[Enum], ...] | ListOf


@dataclass(frozen=True)
class Field:
    name: str
    type: TypeSpec
    default: object = None


@dataclass(frozen=True)
class ClassSpec:
    cls: type
    code: str
    fields: tuple[Field, ...]
    factories: tuple[Callable[..., object], ...] = ()
    records_attr: str | None = None      # a record set's list of records

    def factories_for(self, keys: frozenset[str]) -> tuple[Callable[..., object], ...]:
        """The factories that take every key as a parameter and need no parameter the keys lack."""
        return tuple(fn for fn in self.factories
                     if keys <= param_names(fn) and required_params(fn) <= keys)

    def factory_for(self, keys: frozenset[str]) -> Callable[..., object] | None:
        """The one factory `factories_for` names, or None when none or several do."""
        found = self.factories_for(keys)
        return found[0] if len(found) == 1 else None

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"{self.cls.__name__}.{name}")


def parse_fields(spec: str, types: Mapping[str, TypeSpec]) -> tuple[Field, ...]:
    """`name:type[=default]` pairs, space-separated: a row per field, in `vars()` order; a
    type named in `types` is that type, any other is its own name (`str`, `person`)."""
    out = []
    for item in spec.split():
        name, _, rest = item.partition(":")
        kind, _, default = rest.partition("=")
        value: object = {"": None, "True": True, "False": False, "''": "", "[]": []}[default]
        out.append(Field(name, types.get(kind, kind), value))
    return tuple(out)


@dataclass(frozen=True)
class Scalar:
    """A field type of the vocabulary's own: a plain str, or an object of `type` written as a
    JSON object (`encode`/`decode`), compared by `same`; `schema` is the object's properties
    and the required ones."""
    name: str
    type: type
    encode: Callable[[Any], dict[str, Any]]
    decode: Callable[[Mapping[str, Any]], Any]
    same: Callable[[Any, Any], bool]
    schema: tuple[dict[str, Any], list[str]]


@dataclass(frozen=True)
class Numbering:
    """A running number a book gives the items of its entries' lists, across the entries (a roll's
    № п/п over its дворы): `items` is the record's list, `attr` the item's attribute holding the number,
    `skipped` the item's boolean attribute that takes no number (a placeholder the book does not hold).
    An item that wrote its own whole number keeps it and the count continues from it."""
    items: str
    attr: str
    skipped: str


@dataclass(frozen=True)
class Positional:
    """What a record holds that is its place in its record set, not what it wrote: `index`, the attribute
    holding its 1-based place in the set, and `numbering`, a running number over its list's items.
    The set's factory gives them; a record built alone is given them by `Position`
    (`verso.core.records.replay`)."""
    index: str | None = None
    numbering: Numbering | None = None


@dataclass(frozen=True, eq=False)
class Vocabulary:
    """A plugin's table of the records JSON: what the core's codec reads."""
    specs: Mapping[type, ClassSpec]
    value_classes: tuple[type, ...]                      # written whole, as a field's value
    param_to_attr: Mapping[type, Mapping[str, str]]      # a factory parameter spelled otherwise
    written_only: Mapping[tuple[type, str], TypeSpec]    # a factory parameter with no attribute of its own
    item_roles: Mapping[str, str]                        # a list of entities → its items' persons' role
    person: type                                         # the class of a `PERSON` field
    scalars: Mapping[str, Scalar]
    schema_package: str                                  # where its records-v1.json lies
    json_names: Mapping[type, Mapping[str, str]] = dataclass_field(default_factory=dict)  # attribute → key
    # Attributes a wrapper sets — a section's month, a sheet's provenance. Records v1.x writes
    # such a value into `written` under the attribute's key, when the call did not write it, and
    # names the key in `written.context` (`CONTEXT_KEY`); replay sets it on the built record. An
    # export of before keeps them in `derived` alone, which replay reads with `context=True`.
    context: Mapping[type, frozenset[str]] = dataclass_field(default_factory=dict)
    # A class whose factories `written` cannot tell apart names the one that built each object:
    # its verbs, by the name `written.verb` carries (records v1.x, additive). Replay takes the
    # factory from here; an export without the key falls back to the keys' own answer.
    verbs: Mapping[type, Mapping[str, Callable[..., object]]] = dataclass_field(default_factory=dict)
    # The wrapper-set attributes a wrapper keeps beside a call's own value of them (`written.wrapper`, records
    # v1.x): a subset of `context` — the Russian books' a page's leaf, a section's months and year.
    shadowed: Mapping[type, frozenset[str]] = dataclass_field(default_factory=dict)
    # The record classes whose objects hold their place in the set (`Positional`): what a record
    # built alone is given by its `Position`.
    positional: Mapping[type, Positional] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        for cls, spec in self.specs.items():
            _check_json_names(self, cls, spec)

    @cached_property
    def json_keys(self) -> dict[type, dict[str, str]]:
        """Each class's attribute → its JSON key, for every field of the table."""
        return {cls: {f.name: self.json_names.get(cls, {}).get(f.name, f.name) for f in spec.fields}
                for cls, spec in self.specs.items()}

    @cached_property
    def json_attrs(self) -> dict[type, dict[str, str]]:
        """Each class's JSON key → its attribute."""
        return {cls: {key: attr for attr, key in keys.items()} for cls, keys in self.json_keys.items()}

    @cached_property
    def params_of_keys(self) -> dict[type, dict[str, str]]:
        """Each class's renamed JSON key → the factory parameter it names (`param_of_key`): a key no
        `json_names` gives is its parameter's own name, and is not listed."""
        out: dict[type, dict[str, str]] = {}
        for cls, names in self.json_names.items():
            params = self.param_to_attr.get(cls, {})
            renamed = {k: attr for attr, k in names.items()}
            out[cls] = {k: next((p for p, target in params.items() if target == attr), attr)
                        for k, attr in renamed.items()}
        return out

    @cached_property
    def groups(self) -> dict[type, frozenset[str]]:
        """Each class's group keys: the heads of its dotted keys."""
        return {cls: frozenset(k.partition(".")[0] for k in keys.values() if "." in k)
                for cls, keys in self.json_keys.items()}

    def item_class(self, cls: type, attr: str) -> type:
        """The class of the items of a record's list of entities (`members` of a household)."""
        kind = self.specs[cls].field(attr).type
        assert isinstance(kind, ListOf) and isinstance(kind.item, type)
        return kind.item

    @cached_property
    def by_code(self) -> dict[str, type]:
        return {spec.code: cls for cls, spec in self.specs.items()}

    @cached_property
    def holds(self) -> dict[str, list[str]]:
        """A record set's code → the codes of the records it holds: its list's item class and
        every class of the table under it (a christening is a birth), in the table's order."""
        out: dict[str, list[str]] = {}
        for spec in self.specs.values():
            if spec.records_attr is None:
                continue
            item = spec.field(spec.records_attr).type
            assert isinstance(item, ListOf) and isinstance(item.item, type)
            out[spec.code] = [s.code for cls, s in self.specs.items() if issubclass(cls, item.item)]
        return out

    @cached_property
    def links(self) -> list[str]:
        """The codes of the items of the lists that hold persons (`item_roles`), as the table
        first names them."""
        out: list[str] = []
        for spec in self.specs.values():
            for f in spec.fields:
                if f.name in self.item_roles and isinstance(f.type, ListOf) and isinstance(f.type.item, type):
                    code_ = self.specs[f.type.item].code
                    if code_ not in out:
                        out.append(code_)
        return out


_KEY = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?")


def _check_json_names(voc: Vocabulary, cls: type, spec: ClassSpec) -> None:
    """Refuse a key the codec could not read back: of no attribute, of a person's slot, not
    snake_case or deeper than one group, two attributes on one key, a group named like a field."""
    names = voc.json_names.get(cls, {})
    fields = {f.name: f for f in spec.fields}
    for attr, key in names.items():
        if attr not in fields:
            raise FormatError(t("records.fields.json_name_no_attribute", cls=cls.__name__, attr=repr(attr)))
        kind = fields[attr].type
        if kind == PERSON or (isinstance(kind, ListOf) and isinstance(kind.item, type)
                              and kind.item in voc.specs and kind.item not in voc.value_classes):
            raise FormatError(t("records.fields.json_name_of_a_slot", cls=cls.__name__, attr=repr(attr)))
        if not _KEY.fullmatch(key):
            raise FormatError(t("records.fields.json_name_bad", cls=cls.__name__, attr=repr(attr), key=repr(key)))
    keys: dict[str, str] = {}
    for attr in fields:
        key = names.get(attr, attr)
        if key in keys:
            raise FormatError(t("records.fields.json_name_twice", cls=cls.__name__, key=repr(key),
                                first=repr(keys[key]), second=repr(attr)))
        keys[key] = attr
    for (owner, param), _ in voc.written_only.items():
        if owner is cls and param in keys and keys[param] != param:
            raise FormatError(t("records.fields.json_name_twice", cls=cls.__name__, key=repr(param),
                                first=repr(keys[param]), second=repr(param)))
    for key in keys:
        head, dot, _ = key.partition(".")
        if dot and head in keys:
            raise FormatError(t("records.fields.json_group_shadows", cls=cls.__name__, group=repr(head),
                                attr=repr(keys[head])))


def json_key(cls: type, attr: str) -> str:
    """The JSON key of an attribute: `Birth.b_day` → `birth.day` (records v1)."""
    return vocabulary().json_keys[cls][attr]


def written_key(cls: type, param: str) -> str:
    """The JSON key of a factory parameter: the key its attribute is renamed to, else the
    parameter's own name (`last_name_orig`, a `written_only` one)."""
    return written_key_in(vocabulary(), cls, param)


def written_key_in(voc: Vocabulary, cls: type, param: str) -> str:
    """`written_key` in a vocabulary the caller holds."""
    attr = voc.param_to_attr.get(cls, {}).get(param, param)
    return voc.json_names.get(cls, {}).get(attr, param)


def param_of_key(cls: type, key: str) -> str:
    """The factory parameter a key of `written` names — `written_key` read backwards."""
    return param_of_key_in(vocabulary(), cls, key)


def param_of_key_in(voc: Vocabulary, cls: type, key: str) -> str:
    """`param_of_key` in a vocabulary the caller holds."""
    return voc.params_of_keys.get(cls, {}).get(key, key)


#: The key of `written` that names the keys a wrapper set rather than the call (records v1.x).
#: No factory parameter may be written under it (the schema refuses one).
CONTEXT_KEY = "context"
#: The key of `written` that holds what a wrapper around the record would have set on a field the call wrote
#: itself — the `page()` around a record writing its own `page=`, the month section around one writing its
#: months (records v1.x): an object of the wrappers' fields, grouped as `written` is. The call's value stands;
#: the wrapper's is kept for a reader that shows where the record stands. No parameter is written under it.
WRAPPER_KEY = "wrapper"


def split_context(cls: type, written: Mapping[str, Any], path: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """A node's `written` as (the call's keys, the wrappers' values): the first a flat
    JSON key → value, its groups opened and `verb` and the marker left out; the second the
    attribute → JSON value of each key `written.context` names (`written.wrapper` left out: `split_wrapper`).
    An export without the marker splits nothing off. A marker naming a key of no context attribute of `cls`, a key twice,
    `page` (a record's лист is its page run's) or a key `written` lacks is a `FormatError`."""
    return split_context_in(vocabulary(), cls, written, path)


def split_context_in(voc: Vocabulary, cls: type, written: Mapping[str, Any],
                     path: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """`split_context` in a vocabulary the caller holds: a caller in a loop asks the workspace's once."""
    flat = dict(written)
    if cls in voc.verbs:
        flat.pop("verb", None)
    flat.pop(WRAPPER_KEY, None)         # `split_wrapper`'s
    marked = flat.pop(CONTEXT_KEY, None)
    call = ungroup_in(voc, cls, flat)
    if marked is None:
        return call, {}
    if not isinstance(marked, list):
        raise FormatError(t("records.fields.context_not_a_list", path=path, cls=cls.__name__))
    wanted = voc.context.get(cls, frozenset())
    attrs = voc.json_attrs.get(cls, {})
    context: dict[str, Any] = {}
    for key in marked:  # type: ignore[union-attr]
        attr = attrs.get(key) if isinstance(key, str) else None
        if attr == "page":      # a record's лист is its page run's, never a key of its own
            raise FormatError(t("records.fields.context_page", path=path, cls=cls.__name__))
        if attr in context:
            raise FormatError(t("records.fields.context_key_twice", path=path, cls=cls.__name__, key=repr(key)))
        if attr is None or attr not in wanted:
            raise FormatError(t("records.fields.context_not_a_wrapper_field", path=path, cls=cls.__name__,
                                key=repr(key)))
        if key not in call:
            raise FormatError(t("records.fields.context_key_missing", path=path, cls=cls.__name__, key=repr(key)))
        context[attr] = call.pop(key)
    return call, context


def split_wrapper(cls: type, written: Mapping[str, Any], path: str = "") -> dict[str, Any]:
    """`written.wrapper` of a node, attribute → JSON value: what a wrapper around the record would have set on a
    field its call wrote (`WRAPPER_KEY`); {} for a node without it. A field no wrapper keeps is a `FormatError`.

    An entry whose key the call no longer writes — an edit took the call's own value away (a `page=` deleted,
    an own month unset), or marked the key as a wrapper's (`written.context`, a record moved into a section) —
    is dropped, not refused: the wrapper's value changes no value of the record, and an editor of the JSON
    need not know of it. The encoder writes no such entry (`records.encode.wrapper_field`), and the schema
    holds the keys a wrapper keeps."""
    found = written.get(WRAPPER_KEY)
    if found is None:
        return {}
    if not isinstance(found, Mapping) or not found:
        raise FormatError(t("records.fields.wrapper_not_an_object", path=path, cls=cls.__name__))
    voc = vocabulary()
    wanted = voc.shadowed.get(cls, frozenset())
    attrs = voc.json_attrs.get(cls, {})
    call, _ = split_context_in(voc, cls, written, path)
    out: dict[str, Any] = {}
    for key, value in ungroup_in(voc, cls, found).items():  # pyright: ignore[reportUnknownArgumentType]
        attr = attrs.get(key)
        if attr is None or attr not in wanted:
            raise FormatError(t("records.fields.wrapper_not_a_wrapper_field", path=path, cls=cls.__name__,
                                key=repr(key)))
        if key in call:         # else stale: the call's own value is gone, or a wrapper's now (see above)
            out[attr] = value
    return out


def group(flat: Mapping[str, Any]) -> dict[str, Any]:
    """Dotted keys into their groups, each group where its first field stands."""
    out: dict[str, Any] = {}
    for key, value in flat.items():
        head, dot, tail = key.partition(".")
        if dot:
            out.setdefault(head, {})[tail] = value
        else:
            out[key] = value
    return out


def ungroup(cls: type, node: Mapping[str, Any]) -> dict[str, Any]:
    """A node's groups back into dotted keys, in the node's order; a group must be an object."""
    return ungroup_in(vocabulary(), cls, node)


def ungroup_in(voc: Vocabulary, cls: type, node: Mapping[str, Any]) -> dict[str, Any]:
    """`ungroup` in a vocabulary the caller holds."""
    groups = voc.groups[cls]
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in groups:
            if not isinstance(value, dict):
                raise FormatError(t("records.fields.group_not_an_object", cls=cls.__name__, group=repr(key)))
            for sub, item in value.items():  # type: ignore[union-attr]
                out[f"{key}.{sub}"] = item
        else:
            out[key] = value
    return out


def nest(cls: type, values: Mapping[str, Any]) -> dict[str, Any]:
    """Attributes → the JSON object: each under its key, grouped."""
    keys = vocabulary().json_keys[cls]
    return group({keys[attr]: value for attr, value in values.items()})


def flatten(cls: type, node: Mapping[str, Any]) -> dict[str, Any]:
    """The JSON object → attributes, in the node's order; `KeyError` for a key of no field."""
    attrs = vocabulary().json_attrs[cls]
    return {attrs[key]: value for key, value in ungroup(cls, node).items()}


def vocabulary() -> Vocabulary:
    """The workspace's DSL's vocabulary."""
    return plugins.dsl().vocabulary


_SLOT = re.compile(r"([a-z_]*?)(\d*)")


def code(member_: Enum) -> str:
    """An enum member's code in the JSON: its name in lower case (`male`, `daughter_in_law`)."""
    return member_.name.lower()


def enum_code(cls: type[Enum]) -> str:
    """An enum class's code, for a field that takes several: `WwiDocumentType` → `wwi_document_type`."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()


def member_of(spec: type[Enum] | tuple[type[Enum], ...], code_: str) -> Enum:
    """The member a code names, in the enum (or enums) of a field."""
    if isinstance(spec, tuple):
        owner, _, name = code_.partition(".")
        for cls in spec:
            if enum_code(cls) == owner:
                return member_of(cls, name)
        raise ValueError(str(t("records.fields.no_enum", code=repr(code_), known=[enum_code(c) for c in spec])))
    try:
        return spec[code_.upper()]
    except KeyError:
        raise ValueError(str(t("records.fields.not_a_code", code=repr(code_), enum_code=enum_code(spec), known=[code(m) for m in spec]))) from None


def role_of(attr: str, *, item: bool = False) -> tuple[str, int | None]:
    """A person slot's role and slot number: `god_parent2` → (`godparent`, 2); an item of
    `relatives` → (`relative`, None) — its slot is its place, given by the caller."""
    if item:
        return vocabulary().item_roles[attr], None
    m = _SLOT.fullmatch(attr)
    assert m is not None
    name, digits = m.groups()
    return name.replace("_", ""), int(digits) if digits else None


def attr_of(spec: ClassSpec, role: str, slot: int | None) -> str:
    """The person attribute of `spec` a role and slot name."""
    for f in spec.fields:
        if f.type == PERSON and role_of(f.name) == (role, slot):
            return f.name
    raise KeyError(str(t("records.fields.no_slot", cls=spec.cls.__name__, role=role, detail=slot or '')))


def carries_persons(cls: type, param: str) -> bool:
    """Whether a factory parameter holds a person or entities rather than a value."""
    voc = vocabulary()
    attr = voc.param_to_attr.get(cls, {}).get(param, param)
    try:
        kind = voc.specs[cls].field(attr).type
    except KeyError:
        return False
    return kind == PERSON or (isinstance(kind, ListOf) and isinstance(kind.item, type)
                              and kind.item in voc.specs and kind.item not in voc.value_classes)


def param_spec(cls: type, param: str) -> TypeSpec:
    """The type of what a factory parameter writes: its attribute's, or `written_only`'s."""
    return param_spec_in(vocabulary(), cls, param)


def param_spec_in(voc: Vocabulary, cls: type, param: str) -> TypeSpec:
    """`param_spec` in a vocabulary the caller holds."""
    if (cls, param) in voc.written_only:
        return voc.written_only[(cls, param)]
    attr = voc.param_to_attr.get(cls, {}).get(param, param)
    try:
        return voc.specs[cls].field(attr).type
    except KeyError:
        raise KeyError(str(t("records.fields.param_undescribed", cls=cls.__name__, param=repr(param), package=voc.schema_package))) from None


# A factory's signature is read once: `factories_for` asks it of every record a book replays.
@cache
def factory_params(fn: Callable[..., object]) -> tuple[str, ...]:
    """A factory's parameters but `*records`."""
    return tuple(n for n, p in inspect.signature(fn).parameters.items()
                 if p.kind is not inspect.Parameter.VAR_POSITIONAL)


@cache
def param_names(fn: Callable[..., object]) -> frozenset[str]:
    """`factory_params` as a set."""
    return frozenset(factory_params(fn))


@cache
def takes_records(fn: Callable[..., object]) -> bool:
    """Whether a factory takes `*records`."""
    return any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in inspect.signature(fn).parameters.values())


@cache
def required_params(fn: Callable[..., object]) -> frozenset[str]:
    """A factory's parameters without a default, `*records` and `**kwargs` aside."""
    return frozenset(n for n, p in inspect.signature(fn).parameters.items()
                     if p.default is inspect.Parameter.empty
                     and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD))
