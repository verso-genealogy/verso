"""Edits addressed by the records' own names: an operation of the review page's `/api/v2` — a
path of the interface's schema (ui-v1.json) and a typed value — turned into the edits `source.apply`
writes, by the vocabulary read backwards.

A path is the records JSON's (v1): a record's field is its key (`birth.day`), a person's field
`<role>/<field>` or, in a numbered slot, `<role>/<slot>/<field>` (`godparent/2/given.original`), an
item of a group `<group>/<n>/<field>`, `n` its place in the source from 1 (`members/3/age`), and its
person's fields `<group>/<n>/person/<field>`. The operations:

* `set` a field to a value, `unset` it;
* `add` a person into an empty slot, or an item at the end of a group — its value an object of the
  item's own paths (`{"number": 4, "person/given.original": "Иванъ"}`);
* `insert` an item at a place, `remove` an item or a person, `move` an item to a place (`to`, from 1).

A value is typed as its field is: `text` a string, `integer` a number, `boolean`, `age` a number or a
string, `enum` a code of the records JSON (`january`), `catalog` `{"const": CODE}` or `{"text": …}`, a
`ref` to another item its number and to a slot the source's word. «Empty» is `unset`; there is no
expression. What the source writes as one — `relatives=ROWS`, `*members` from a variable, an f-string,
arithmetic — is opaque (`opaque`), and no operation reaches it.

The knowledge that `birth.day` is `b_day` lives here and in the vocabulary only; nothing of the page
knows a parameter of the DSL. `path_of` reads a DSL path back as the page's.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from verso.core.records.fields import PERSON, ListOf, attr_of, member_of, param_of_key, param_spec, role_of, written_key
from verso.core.records.fields import vocabulary as _vocabulary
from verso.core.records.ui import load_ui
from verso.ru.ages import AGE_CALLS, AGE_KWARGS, whole_years
from verso.ru.dsl import signatures as sig
from verso.ru.dsl.source import ArgView, CallView, EditError, Value
from verso.ru.messages import t

OPS = frozenset({"set", "unset", "add", "insert", "remove", "move"})
_PLAIN = {"str", "int", "float", "bool"}


class PathError(EditError):
    """An operation the schema cannot address: `paths.*` (unknown, type, opaque, not_a_group,
    not_a_value, slot_taken, position, op)."""


def _ui() -> dict[str, Any]:
    return load_ui()


def _class_of(func: str) -> type:
    voc = _vocabulary()
    for cls, spec in voc.specs.items():
        if any(getattr(f, "__name__", None) == func for f in spec.factories):
            return cls
    raise PathError(t("paths.unknown", path=func))


def _factory(cls: type) -> str:
    return _vocabulary().specs[cls].factories[0].__name__


@dataclass(frozen=True)
class _At:
    """What a path names."""
    what: str                          # field | slot | role | item | group
    dsl: tuple[str, ...]               # the v1 path to it
    field: Mapping[str, Any] | None    # a field's schema
    owner: type                        # the class the last parameter is of
    role: str | None = None            # a slot's role
    group: Mapping[str, Any] | None = None
    item: type | None = None           # a group's item class
    vararg: bool = False               # a group of the call's own *items
    index: int | None = None           # an item's place, from 0


def _kind(func: str) -> tuple[type, Mapping[str, Any]]:
    cls = _class_of(func)
    code = _vocabulary().specs[cls].code
    kind = _ui()["kinds"].get(code)
    if kind is None:
        raise PathError(t("paths.unknown", path=func))
    return cls, kind


def _visible(fields: Sequence[Mapping[str, Any]], key: str) -> Mapping[str, Any] | None:
    return next((f for f in fields if f["path"] == key and not f.get("hidden")), None)


def _int(seg: str) -> int | None:
    return int(seg) if seg.isdigit() else None


def _person_field(path: str, key: str) -> Mapping[str, Any]:
    field = _visible(_ui()["persona"]["fields"], key)
    if field is None:
        raise PathError(t("paths.unknown", path=path))
    return field


def _resolve(func: str, path: str) -> _At:
    cls, kind = _kind(func)
    voc = _vocabulary()
    spec = voc.specs[cls]
    segs = path.split("/") if path else []
    if not segs:
        raise PathError(t("paths.unknown", path=path))
    head, rest = segs[0], segs[1:]
    slots = {s["role"]: s for s in kind["slots"]}
    groups = {g["name"]: g for g in kind["groups"]}
    if head in slots:
        slot = slots[head]
        number = None
        if "slots" in slot:
            if not rest:
                return _At("role", (), None, voc.person, role=head)
            number = _int(rest[0])
            lo, hi = slot["slots"]
            if number is None or not lo <= number <= hi:
                raise PathError(t("paths.unknown", path=path))
            rest = rest[1:]
        attr = attr_of(spec, head, number)
        if not rest:
            return _At("slot", (attr,), None, voc.person, role=head)
        key = "/".join(rest)
        field = _person_field(path, key)
        return _At("field", (attr, param_of_key(voc.person, key)), field, voc.person)
    if head in groups:
        group = groups[head]
        attr = voc.json_attrs[cls].get(head, head)
        item_type = spec.field(attr).type
        assert isinstance(item_type, ListOf) and isinstance(item_type.item, type)
        item = item_type.item
        signature = sig.signature(func)
        vararg = signature is not None and signature.varargs == attr
        if not rest:
            return _At("group", (attr,), None, cls, group=group, item=item, vararg=vararg)
        n = _int(rest[0])
        if n is None or n < 1:
            raise PathError(t("paths.unknown", path=path))
        k = n - 1
        base = (f"@{k}",) if vararg else (attr, f"#{k}")
        rest = rest[1:]
        if not rest:
            return _At("item", base, None, item, group=group, item=item, vararg=vararg, index=k)
        if rest[0] in group["item"]["persons"]:
            person_attr = rest[0]
            key = "/".join(rest[1:])
            if not key:
                raise PathError(t("paths.unknown", path=path))
            field = _person_field(path, key)
            return _At("field", (*base, person_attr, param_of_key(voc.person, key)), field, voc.person,
                       group=group, item=item, vararg=vararg, index=k)
        key = "/".join(rest)
        field = _visible(group["item"]["fields"], key)
        if field is None:
            raise PathError(t("paths.unknown", path=path))
        return _At("field", (*base, param_of_key(item, key)), field, item, group=group, item=item,
                   vararg=vararg, index=k)
    if rest:
        raise PathError(t("paths.unknown", path=path))
    field = _visible(kind["fields"], head)
    if field is None:
        raise PathError(t("paths.unknown", path=path))
    return _At("field", (param_of_key(cls, head),), field, cls)


# ---------------------------------------------------------------- values

def _enum_const(owner: type, param: str, code: str, path: str) -> dict[str, Any]:
    spec = param_spec(owner, param)
    if not isinstance(spec, (type, tuple)):
        raise PathError(t("paths.type", path=path, expected="enum"))
    try:
        m = member_of(spec, code)  # type: ignore[arg-type]
    except ValueError:
        raise PathError(t("paths.type", path=path, expected="enum")) from None
    assert isinstance(m, Enum)
    return {"kind": "const", "value": f"{type(m).__name__}.{m.name}"}


def _v1_value(at_field: Mapping[str, Any], owner: type, param: str, value: Any, path: str) -> dict[str, Any]:
    """A v2 value of a field as the v1 edit writes it."""
    kind = at_field["type"]
    if kind == "ref":
        kind = "integer" if at_field["ref"]["to"] == "item" else "text"
    ok: dict[str, Any] | None = None
    if kind == "text" and isinstance(value, str):
        ok = {"kind": "str", "value": value}
    elif kind == "integer" and isinstance(value, int) and not isinstance(value, bool):
        ok = {"kind": "int", "value": value}
    elif kind == "boolean" and isinstance(value, bool):
        ok = {"kind": "bool", "value": value}
    elif kind == "age" and isinstance(value, (int, float, str)) and not isinstance(value, bool):
        ok = {"kind": "int" if isinstance(value, int) else "float" if isinstance(value, float) else "str",
              "value": value}
    elif kind == "enum" and isinstance(value, str):
        return _enum_const(owner, param, value, path)
    elif kind == "catalog" and isinstance(value, Mapping):
        if set(value) == {"const"} and isinstance(value["const"], str):
            ok = {"kind": "const", "value": value["const"]}
        elif set(value) == {"text"} and isinstance(value["text"], str):
            ok = {"kind": "str", "value": value["text"]}
    if ok is None:
        raise PathError(t("paths.type", path=path, expected=at_field["type"]))
    return ok


def _whole_years(func: str, param: str, value: dict[str, Any]) -> dict[str, Any]:
    """An age typed as a whole number of years, written as the integer AGE001 asks for: «4» and
    «5 лет» are `age=4` and `age=5`, so the edit gains no finding; «4 мес» stays text."""
    if func in AGE_CALLS and param in AGE_KWARGS and value["kind"] == "str":
        digits = whole_years(value["value"])
        if digits is not None:
            return {"kind": "int", "value": int(digits)}
    return value


def _person_call(values: Mapping[str, Any], path: str) -> dict[str, Any]:
    voc = _vocabulary()
    args = []
    for key, value in values.items():
        sub = f"{path}/{key}"
        field = _person_field(sub, key)
        param = param_of_key(voc.person, key)
        args.append({"param": param, "value": _v1_value(field, voc.person, param, value, sub)})
    return {"kind": "call", "func": _factory(voc.person), "args": args}


def _item_call(at: _At, values: Mapping[str, Any], path: str) -> dict[str, Any]:
    assert at.group is not None and at.item is not None
    persons: dict[str, dict[str, Any]] = {}
    args = []
    for key, value in values.items():
        head, _, tail = key.partition("/")
        if head in at.group["item"]["persons"] and tail:
            persons.setdefault(head, {})[tail] = value
            continue
        sub = f"{path}/{key}"
        field = _visible(at.group["item"]["fields"], key)
        if field is None:
            raise PathError(t("paths.unknown", path=sub))
        param = param_of_key(at.item, key)
        args.append({"param": param, "value": _v1_value(field, at.item, param, value, sub)})
    for name, person in persons.items():
        args.append({"param": name, "value": _person_call(person, f"{path}/{name}")})
    return {"kind": "call", "func": _factory(at.item), "args": args}


# ---------------------------------------------------------------- what the source writes

def _arg(view: CallView | None, param: str) -> ArgView | None:
    return view.arg(param) if view is not None else None


def _items(view: CallView, at: _At) -> list[Value]:
    """The items of a group as the call writes them."""
    if at.vararg:
        return [a.value for a in view.args if a.param.startswith("@")]
    arg = view.arg(at.dsl[0])
    if arg is None:
        return []
    return list(arg.value.items or []) if arg.value.kind == "list" else []


def _scalar_opaque(field: Mapping[str, Any] | None, value: Value) -> bool:
    if field is None:
        return False
    if value.kind in _PLAIN or value.kind == "none":
        return False
    return not (value.kind == "const" and field["type"] in ("enum", "catalog"))


def _call_opaque(view: CallView, prefix: str, fields: Sequence[Mapping[str, Any]], owner: type,
                 persons: Sequence[str]) -> Iterator[str]:
    """The opaque paths of a person's or an item's call."""
    for a in view.args:
        if a.param in persons:
            sub = f"{prefix}/{a.param}"
            if a.value.kind == "call" and a.value.call is not None:
                yield from _call_opaque(a.value.call, sub, _ui()["persona"]["fields"], _vocabulary().person, ())
            elif a.value.kind != "none":
                yield sub
            continue
        key = written_key(owner, a.param)
        field = next((f for f in fields if f["path"] == key), None)
        if _scalar_opaque(field, a.value):
            yield f"{prefix}/{key}"


def opaque(func: str, call: CallView) -> list[str]:
    """The paths of `call` the schema cannot edit: written as an expression, not a value."""
    cls, kind = _kind(func)
    voc = _vocabulary()
    spec = voc.specs[cls]
    out: list[str] = []
    signature = sig.signature(func)
    for group in kind["groups"]:
        attr = voc.json_attrs[cls].get(group["name"], group["name"])
        item_type = spec.field(attr).type
        assert isinstance(item_type, ListOf) and isinstance(item_type.item, type)
        item = item_type.item
        persons = group["item"]["persons"]
        if signature is not None and signature.varargs == attr:
            if call.splat:
                out.append(group["name"])
                continue
            values = [a.value for a in call.args if a.param.startswith("@")]
        else:
            arg = call.arg(attr)
            if arg is None or arg.value.kind == "none":
                continue
            if arg.value.kind != "list":
                out.append(group["name"])
                continue
            values = list(arg.value.items or [])
        for n, value in enumerate(values, 1):
            prefix = f"{group['name']}/{n}"
            if value.kind == "call" and value.call is not None:
                out.extend(_call_opaque(value.call, prefix, group["item"]["fields"], item, persons))
            else:
                out.append(prefix)
    for a in call.args:
        if a.param.startswith("@"):
            continue
        try:
            kind_of_param = param_spec(cls, a.param)
        except KeyError:
            continue
        if kind_of_param == PERSON:
            role, number = role_of(voc.param_to_attr.get(cls, {}).get(a.param, a.param))
            prefix = role if number is None else f"{role}/{number}"
            if a.value.kind == "call" and a.value.call is not None:
                out.extend(_call_opaque(a.value.call, prefix, _ui()["persona"]["fields"], voc.person, ()))
            elif a.value.kind != "none":
                out.append(prefix)
            continue
        if isinstance(kind_of_param, ListOf):
            continue
        key = written_key(cls, a.param)
        field = next((f for f in kind["fields"] if f["path"] == key), None)
        if _scalar_opaque(field, a.value):
            out.append(key)
    return out


def _under(path: str, opaque_paths: Sequence[str]) -> bool:
    return any(path == o or path.startswith(o + "/") for o in opaque_paths)


# ---------------------------------------------------------------- the operations

def translate(func: str, ops: Sequence[Mapping[str, Any]], *, call: CallView) -> list[dict[str, Any]]:
    """The v2 operations of a record of `func`, written as `call` reads now, as `source.apply`'s ops."""
    out: list[dict[str, Any]] = []
    shut = opaque(func, call)
    sizes: dict[str, int] = {}            # a group's items, as the operations before have left it
    taken: set[str] = set()               # the slots the operations before have filled
    for op in ops:
        name = op.get("op")
        if name not in OPS:
            raise PathError(t("paths.op", op=name))
        path = op.get("path")
        if not isinstance(path, str):
            raise PathError(t("paths.unknown", path=path))
        at = _resolve(func, path)
        if _under(path, shut) or (at.what in ("item", "group") and _under(at.group["name"] if at.group else path, shut)):
            raise PathError(t("paths.opaque", path=path))
        if at.what in ("item", "group", "field") and at.group is not None:
            size = sizes.setdefault(at.group["name"], len(_items(call, at)))
        else:
            size = 0
        if name in ("set", "unset"):
            if at.what != "field":
                raise PathError(t("paths.not_a_value", path=path))
            assert at.field is not None
            if at.index is not None and at.index >= size:
                raise PathError(t("paths.position", path=path, size=size))
            if name == "unset":
                out.append({"op": "delete", "path": list(at.dsl)})
            else:
                param = at.dsl[-1]
                value = _v1_value(at.field, at.owner, param, op.get("value"), path)
                out.append({"op": "set", "path": list(at.dsl), "value": _whole_years(func, param, value)})
            continue
        if name == "add":
            values = op.get("value", {})
            if not isinstance(values, Mapping):
                raise PathError(t("paths.type", path=path, expected="object"))
            if at.what in ("slot", "role"):
                attr = at.dsl[0] if at.what == "slot" else _free_slot(func, call, at, taken, path)
                existing = _arg(call, attr)
                if attr in taken or (existing is not None and existing.value.kind != "none"):
                    raise PathError(t("paths.slot_taken", path=path))
                taken.add(attr)
                out.append({"op": "set", "path": [attr], "value": _person_call(values, path)})
                continue
            if at.what != "group":
                raise PathError(t("paths.not_a_group", path=path))
            out.append(_append(at, _item_call(at, values, f"{path}/{size + 1}")))
            sizes[at.group["name"]] = size + 1  # type: ignore[index]
            continue
        if at.what != "item":
            if name == "remove" and at.what == "slot":
                out.append({"op": "delete", "path": list(at.dsl)})
                continue
            raise PathError(t("paths.not_a_group", path=path))
        assert at.index is not None and at.group is not None
        k = at.index
        if name == "insert":
            values = op.get("value", {})
            if not isinstance(values, Mapping):
                raise PathError(t("paths.type", path=path, expected="object"))
            if k > size:
                raise PathError(t("paths.position", path=path, size=size))
            out.append(_append(at, _item_call(at, values, path)))
            if k < size:
                out.append(_move(at, size, k))
            sizes[at.group["name"]] = size + 1
        elif name == "remove":
            if k >= size:
                raise PathError(t("paths.position", path=path, size=size))
            out.append({"op": "delete", "path": list(at.dsl)})
            sizes[at.group["name"]] = size - 1
        else:  # move
            to = op.get("to")
            if not isinstance(to, int) or isinstance(to, bool) or not 1 <= to <= size or k >= size:
                raise PathError(t("paths.position", path=path, size=size))
            out.append(_move(at, k, to - 1))
    return out


def _append(at: _At, value: dict[str, Any]) -> dict[str, Any]:
    head = ["@+"] if at.vararg else [at.dsl[0], "#+"]
    return {"op": "set", "path": head, "value": value}


def _move(at: _At, k: int, to: int) -> dict[str, Any]:
    head = [f"@{k}"] if at.vararg else [at.dsl[0], f"#{k}"]
    return {"op": "move", "path": head, "to": to}


def _free_slot(func: str, call: CallView, at: _At, taken: set[str], path: str) -> str:
    """The lowest numbered slot of a role no person stands in."""
    cls, kind = _kind(func)
    spec = _vocabulary().specs[cls]
    slot = next(s for s in kind["slots"] if s["role"] == at.role)
    lo, hi = slot["slots"]
    for n in range(lo, hi + 1):
        attr = attr_of(spec, slot["role"], n)
        arg = call.arg(attr)
        if attr not in taken and (arg is None or arg.value.kind == "none"):
            return attr
    raise PathError(t("paths.slot_taken", path=path))


def field_of(func: str, path: str) -> Mapping[str, Any] | None:
    """The schema's field at `path` of a record of `func` (`ui-v1`: its type, its catalog …), what a
    path's value is typed by — None where the path names a slot, a group or an item; a PathError where
    it names nothing."""
    at = _resolve(func, path)
    return at.field if at.what == "field" else None


def path_of(func: str, dsl_path: Sequence[str]) -> str:
    """A v1 path of a record of `func` — its parameters, `@k`, `#k` — as the page's path."""
    cls, kind = _kind(func)
    voc = _vocabulary()
    if not dsl_path:
        raise PathError(t("paths.unknown", path=""))
    head, rest = dsl_path[0], list(dsl_path[1:])
    signature = sig.signature(func)
    if head.startswith("@") and head[1:].isdigit():
        assert signature is not None and signature.varargs is not None
        group = voc.json_keys[cls].get(signature.varargs, signature.varargs)
        return _item_path(cls, kind, group, int(head[1:]), rest)
    try:
        spec_type = param_spec(cls, head)
    except KeyError:
        raise PathError(t("paths.unknown", path="/".join(dsl_path))) from None
    if spec_type == PERSON:
        role, number = role_of(voc.param_to_attr.get(cls, {}).get(head, head))
        prefix = role if number is None else f"{role}/{number}"
        return "/".join([prefix, *(written_key(voc.person, p) for p in rest)])
    if isinstance(spec_type, ListOf) and rest and rest[0].startswith("#"):
        return _item_path(cls, kind, voc.json_keys[cls].get(head, head), int(rest[0][1:]), rest[1:])
    if rest:
        raise PathError(t("paths.unknown", path="/".join(dsl_path)))
    return written_key(cls, head)


def _item_path(cls: type, kind: Mapping[str, Any], group: str, k: int, rest: list[str]) -> str:
    voc = _vocabulary()
    spec = voc.specs[cls]
    attr = voc.json_attrs[cls].get(group, group)
    item_type = spec.field(attr).type
    assert isinstance(item_type, ListOf) and isinstance(item_type.item, type)
    item = item_type.item
    persons = next(g["item"]["persons"] for g in kind["groups"] if g["name"] == group)
    base = f"{group}/{k + 1}"
    if not rest:
        return base
    if rest[0] in persons:
        return "/".join([base, rest[0], *(written_key(voc.person, p) for p in rest[1:])])
    if len(rest) != 1:
        raise PathError(t("paths.unknown", path="/".join([base, *rest])))
    return f"{base}/{written_key(item, rest[0])}"
