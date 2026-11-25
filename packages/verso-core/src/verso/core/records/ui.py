"""ui-v1.json — the review page's schema, built from the vocabulary and a plugin's hints.

The vocabulary says what a record holds: its fields, their types, their JSON keys, its people's
slots and its lists of entities. What it does not say is how a page draws them: in which order,
under which label, which slot a record's field belongs beside, which fields are a date. That is
the plugin's hints (`Plugin.ui`, a TOML file of its package; the Russian books' is
`verso/ru/records/ui-hints.toml`), and this module joins the two into one schema, `ui-v1`:

    {"schema": "ui-v1", "records": "records-v1", "package": <the catalog the labels are keys of>,
     "kinds":  {<record kind>: {"label", "fields", "slots", "groups", "events", "draft", "rules"}},
     "persona": {"fields"},  # a person's fields, wherever a person stands
     "enums":  {<enum>: [{"code", "label", "gender"}]},
     "books":  {<record set>: {"label", "fields", "fills", "flags", "queue"}}}

A field's `type` is the vocabulary's, never the hints': `str` → `text`, `int` → `integer`, `bool`
→ `boolean`, `age` and `intstr` → `age` (a number or a scribe's «17 л 2 мес»), an enum class →
`enum`, a scalar of the vocabulary → `catalog`; a field the hints give a `ref` is a `ref`. Its
`path` is its JSON key (records v1). A label is a key of the plugin's catalog, checked against its
English one. The hints place every field of every kind they name — in `fields`, or `hidden` — and
the build refuses rather than guesses: a path the vocabulary lacks, a field left unplaced, a label
the catalog lacks, a path placed twice, a rule of no known kind or a key its kind does not read
(`UiError`, `records.ui.*`).

The schema is generated, not written, and committed beside `records-v1.json`
(`Vocabulary.schema_package`):

    python -m verso.core.records.ui --write    # regenerate ui-v1.json
    python -m verso.core.records.ui --check    # exit 1 if the committed file is stale

The core names no record kind here: every word of a kind comes from the vocabulary or the hints.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import Enum
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from verso.core import i18n
from verso.core.i18n import Message
from verso.core.messages import t
from verso.core.records import SCHEMA_ID
from verso.core.records.fields import PERSON, ListOf, TypeSpec, Vocabulary, code, enum_code, role_of

UI_FILE = "ui-v1.json"
UI_ID = "ui-v1"

#: The kinds of rule a page may run on a record's own fields, and the keys each reads: any other kind, and any other key
#: (a typo the page would never read), is refused.
RULE_KEYS: dict[str, frozenset[str]] = {
    "follows": frozenset({"rule", "from", "to", "advance"}),
    "shown_when": frozenset({"rule", "group", "path", "when"}),
    "renumber": frozenset({"rule", "group", "number", "refs"}),
    "ref_choices": frozenset({"rule", "group", "path", "party"}),
    "late": frozenset({"rule", "after", "event", "days", "stand_down", "stand_down_before"}),
}
RULES = frozenset(RULE_KEYS)
#: The two days a `follows` rule's `advance` compares.
ADVANCE_KEYS = frozenset({"day_from", "day_to"})
GENDERS = frozenset({"male", "female", "of_record"})
WIDGETS = frozenset({"wide", "checkbox"})
REF_TO = frozenset({"item", "slot"})   # another item of the field's own group, or a slot
#: Where a page draws a person's field, and whether it suggests as it is typed: a column of the
#: people's table (`column`), the line every person shows (`line`), suggested (`suggest`). And a
#: field that only answers the corpus's checks — «так в подлиннике», «имя не по святцам — верно»
#: (`checks`): a page offers it in no «+ поле» and shows it where it is written. And a field the plugin
#: sets itself where it can — «фамилия в книге» unticked for a surname it derived (`auto`): the same.
FLAGS = ("column", "line", "suggest", "checks", "auto")
#: Whom a page's «+» offers a person's field (`offer`): a person of this sex (`gender`), and not one
#: standing in these roles (`not_in`, a slot's or an item's role) — shown, all the same, where written.
OFFER_KEYS = frozenset({"gender", "not_in"})
OFFER_GENDERS = frozenset({"male", "female"})

#: The ui-v1 format's own words. Some are words a plugin's vocabulary uses too (a person, a role,
#: a day): here they are the format's keys and types, never a kind's fields.
FORMAT = (
    "schema", "records", "kinds", "person", "persona", "enums", "books", "label", "fields", "slots", "groups",
    "events", "draft", "rules", "rule", "path", "type", "enum", "catalog", "widget", "hidden", "ref",
    "to", "choices", "role", "gender", "party", "row", "quick", "name", "item", "persons", "layout",
    "orderable", "day", "month", "year", "late_days", "follows", "creatable", "code", "forms",
    "fills", "flags", "field", "fallback", "package", "of", "queue",
    "from", "advance", "after", "event", "number", "refs",          # the rules' keys
    "offer", "not_in",                                               # whom a «+» offers a field
    "text", "integer", "boolean", "age", *FLAGS,
)

_SCALAR = {"str": "text", "strs": "text", "int": "integer", "bool": "boolean", "age": "age", "intstr": "age"}


class UiError(ValueError):
    """The hints and the vocabulary do not make a schema: `key` is the message's (`records.ui.*`),
    `params` what it names."""

    def __init__(self, message: Message) -> None:
        self.message = message
        self.key = message.key
        self.params: Mapping[str, object] = message.params
        super().__init__(message.key)

    def __str__(self) -> str:
        return str(self.message)


def _is_entity(voc: Vocabulary, spec: TypeSpec) -> bool:
    return isinstance(spec, type) and spec in voc.specs and spec not in voc.value_classes


def _entity_list(voc: Vocabulary, spec: TypeSpec) -> type | None:
    if isinstance(spec, ListOf) and _is_entity(voc, spec.item):
        assert isinstance(spec.item, type)
        return spec.item
    return None


class _Build:
    """One build: the labels it checks and the enums its fields name, in the order they are met."""

    def __init__(self, voc: Vocabulary, hints: Mapping[str, Any]) -> None:
        self.voc = voc
        self.hints = hints
        self.package = hints.get("package")
        self.labels = set(i18n.catalog(self.package, i18n.SOURCE)) if isinstance(self.package, str) else set()
        self.enums: dict[str, tuple[type[Enum], ...]] = {}

    def label(self, key: object) -> str:
        if not isinstance(key, str) or key not in self.labels:
            raise UiError(t("records.ui.unknown_label", key=key, package=self.package))
        return key

    def labelled(self, base: object, forms: Sequence[str]) -> dict[str, Any]:
        """A label, or a label of several forms (`forms`): `{label: <first form>, forms: {form: key}}`."""
        if not forms:
            return {"label": self.label(base)}
        keys = {form: self.label(f"{base}.{form}") for form in forms}
        return {"label": keys[forms[0]], "forms": keys}

    def typed(self, spec: TypeSpec) -> dict[str, Any] | None:
        """A field's type and what it names, or None for a value no page edits field by field."""
        if isinstance(spec, str):
            if spec in _SCALAR:
                return {"type": _SCALAR[spec]}
            if spec in self.voc.scalars:
                return {"type": "catalog", "catalog": spec}
            return None
        if isinstance(spec, tuple):
            name = "|".join(enum_code(e) for e in spec)
            self.enums.setdefault(name, spec)
            return {"type": "enum", "enum": name}
        if isinstance(spec, type) and issubclass(spec, Enum):
            name = enum_code(spec)
            self.enums.setdefault(name, (spec,))
            return {"type": "enum", "enum": name}
        return None

    def offer(self, where: str, path: str, offer: object) -> dict[str, Any]:
        """Whom a «+» offers the field: `{gender?, not_in?}`, a sex of `OFFER_GENDERS` and a list of roles."""
        if not isinstance(offer, Mapping) or not offer or set(offer) - OFFER_KEYS:
            raise UiError(t("records.ui.bad_offer", kind=where, path=path))
        out: dict[str, Any] = {}
        if "gender" in offer:
            if offer["gender"] not in OFFER_GENDERS:
                raise UiError(t("records.ui.bad_offer", kind=where, path=path))
            out["gender"] = offer["gender"]
        if "not_in" in offer:
            roles = offer["not_in"]
            if not isinstance(roles, list) or not roles or not all(isinstance(r, str) and r for r in roles):
                raise UiError(t("records.ui.bad_offer", kind=where, path=path))
            out["not_in"] = list(roles)
        return out

    def placed(self, cls: type, where: str, hint: Mapping[str, Any], *,
               skip: Iterable[str] = (), taken: set[str] | None = None,
               quick: bool = False) -> list[dict[str, Any]]:
        """The fields of `cls` as `hint` places them, in its order, then its hidden ones; every data
        field of `cls` but those of `skip` must be placed once. `quick`: a field may name its one-click
        adder — a record's own field alone, never a person's, an item's or a book's."""
        spec = self.voc.specs[cls]
        keys = self.voc.json_keys[cls]
        data = {keys[f.name]: f for f in spec.fields
                if f.type != PERSON and _entity_list(self.voc, f.type) is None}
        taken = set() if taken is None else taken
        out: list[dict[str, Any]] = []

        def take(path: object) -> str:
            if not isinstance(path, str) or path not in data:
                raise UiError(t("records.ui.unknown_path", kind=where, path=path))
            if path in taken:
                raise UiError(t("records.ui.repeated", kind=where, path=path))
            taken.add(path)
            return path

        for item in hint.get("fields", ()):
            path = take(item.get("path"))
            typed = self.typed(data[path].type)
            if typed is None:
                raise UiError(t("records.ui.no_type", kind=where, path=path))
            field: dict[str, Any] = {"path": path, "type": typed["type"], "label": self.label(item.get("label"))}
            field.update({k: v for k, v in typed.items() if k != "type"})
            catalog = item.get("catalog")
            if catalog is not None:
                # A plain string the source writes as a constant of a catalog the plugin keeps.
                if typed["type"] != "text" or not isinstance(catalog, str):
                    raise UiError(t("records.ui.not_a_catalog", kind=where, path=path))
                field["type"] = "catalog"
                field["catalog"] = catalog
            widget = item.get("widget")
            if widget is not None:
                if widget not in WIDGETS:
                    raise UiError(t("records.ui.unknown_widget", kind=where, path=path, widget=widget))
                field["widget"] = widget
            if "quick" in item:
                if not quick:
                    raise UiError(t("records.ui.quick_not_here", kind=where, path=path))
                field["quick"] = self.label(item["quick"])   # the adder's words: «+ <field>»
            for flag in FLAGS:
                if flag in item:
                    if item[flag] is not True:
                        raise UiError(t("records.ui.not_a_flag", kind=where, path=path, flag=flag))
                    field[flag] = True
            if "offer" in item:
                field["offer"] = self.offer(where, path, item["offer"])
            ref = item.get("ref")
            if ref is not None:
                field["type"] = "ref"
                field["ref"] = self.ref(where, path, ref)
            out.append(field)
        for path in hint.get("hidden", ()):
            path = take(path)
            typed = self.typed(data[path].type)
            hidden: dict[str, Any] = {"path": path}
            if typed is not None:
                hidden["type"] = typed["type"]
            hidden["hidden"] = True
            out.append(hidden)
        for path in data:
            if path not in taken and path not in skip:
                raise UiError(t("records.ui.unplaced", kind=where, path=path))
        return out

    def ref(self, where: str, path: str, ref: Mapping[str, Any]) -> dict[str, Any]:
        to = ref.get("to")
        if to not in REF_TO:
            raise UiError(t("records.ui.unknown_ref", kind=where, path=path, to=to))
        out: dict[str, Any] = {"to": to}
        if "choices" in ref:
            out["choices"] = [{**{k: v for k, v in choice.items() if k != "label"},
                               "label": self.label(choice.get("label"))} for choice in ref["choices"]]
        return out

    def kind(self, code_: str, cls: type, hint: Mapping[str, Any]) -> dict[str, Any]:
        spec = self.voc.specs[cls]
        fields = self.placed(cls, code_, hint, quick=True)
        paths = {f["path"] for f in fields}

        def known(path: object) -> str:
            if not isinstance(path, str) or path not in paths:
                raise UiError(t("records.ui.unknown_path", kind=code_, path=path))
            return path

        # The people: one slot per role, numbered where the vocabulary numbers it.
        roles: dict[str, list[int]] = {}
        for f in spec.fields:
            if f.type == PERSON:
                role, number = role_of(f.name)
                roles.setdefault(role, [])
                if number is not None:
                    roles[role].append(number)
        slots: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in hint.get("slots", ()):
            role = item.get("role")
            if role not in roles:
                raise UiError(t("records.ui.unknown_path", kind=code_, path=role))
            if role in seen:
                raise UiError(t("records.ui.repeated", kind=code_, path=role))
            seen.add(role)
            slot: dict[str, Any] = {"role": role, "label": self.label(item.get("label"))}
            if roles[role]:
                slot["slots"] = [min(roles[role]), max(roles[role])]
            gender = item.get("gender")
            if gender is not None and gender not in GENDERS:
                raise UiError(t("records.ui.unknown_gender", kind=code_, path=role, gender=gender))
            slot["gender"] = gender
            # The person's field that says whose party (side) the person stood for: the persona's own.
            side = item.get("party")
            if side is not None:
                person = self.voc.json_keys[self.voc.person].values()
                if not isinstance(side, str) or side not in person:
                    raise UiError(t("records.ui.unknown_path", kind=code_, path=side))
                slot["party"] = side
            if "row" in item:
                slot["row"] = [known(p) for p in item["row"]]
            if "quick" in item:
                slot["quick"] = self.label(item["quick"])   # the adder's words: «+ <slot>»
            slots.append(slot)
        for role in roles:
            if role not in seen:
                raise UiError(t("records.ui.unplaced", kind=code_, path=role))

        # The lists of entities: a group each, its items' fields placed as a class's are.
        lists = {f.name: item for f in spec.fields if (item := _entity_list(self.voc, f.type)) is not None}
        groups: list[dict[str, Any]] = []
        done: set[str] = set()
        for item in hint.get("groups", ()):
            name = item.get("name")
            if name not in lists:
                raise UiError(t("records.ui.unknown_path", kind=code_, path=name))
            if name in done:
                raise UiError(t("records.ui.repeated", kind=code_, path=name))
            done.add(name)
            item_cls = lists[name]
            where = f"{code_}/{name}"
            item_fields = self.placed(item_cls, where, item)
            persons = [f.name for f in self.voc.specs[item_cls].fields if f.type == PERSON]
            group: dict[str, Any] = {"name": name, "label": self.label(item.get("label")),
                                     # its items' persons' role in the records JSON (`item_roles`)
                                     "item": {"role": self.voc.item_roles.get(name), "fields": item_fields,
                                              "persons": persons},
                                     "orderable": bool(item.get("orderable", False))}
            if "layout" in item:
                item_paths = {f["path"] for f in item_fields}
                for line in item["layout"]:
                    for p in line:
                        if p not in item_paths:
                            raise UiError(t("records.ui.unknown_path", kind=where, path=p))
                group["layout"] = [list(line) for line in item["layout"]]
            groups.append(group)
        for name in lists:
            if name not in done:
                raise UiError(t("records.ui.unplaced", kind=code_, path=name))

        events: list[dict[str, Any]] = []
        for item in hint.get("events", ()):
            event: dict[str, Any] = {"label": self.label(item.get("label")),
                                     "day": known(item.get("day")), "month": known(item.get("month"))}
            if "year" in item:
                event["year"] = known(item["year"])
            if "of" in item:
                event["of"] = self.label(item["of"])     # the event in the genitive: «… after the birth»
            for extra in ("late_days", "follows"):
                if extra in item:
                    event[extra] = item[extra]
            events.append(event)

        draft_hint = hint.get("draft", {})
        for role in draft_hint.get("slots", ()):
            if role not in roles:
                raise UiError(t("records.ui.unknown_path", kind=code_, path=role))
        draft = {"creatable": bool(draft_hint.get("creatable", False)), "slots": list(draft_hint.get("slots", ()))}

        rules: list[dict[str, Any]] = []
        for rule in hint.get("rules", ()):
            if rule.get("rule") not in RULES:
                raise UiError(t("records.ui.unknown_rule", kind=code_, rule=rule.get("rule")))
            self.check_rule(code_, rule, known, groups, events)
            rules.append(dict(rule))
        return {"label": self.label(hint.get("label")), "fields": fields, "slots": slots, "groups": groups,
                "events": events, "draft": draft, "rules": rules}

    def check_rule(self, code_: str, rule: Mapping[str, Any], known: Callable[[object], str],
                   groups: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]) -> None:
        """Every path, group and event a rule names is the kind's: the page writes by them (a renumbering
        takes references along), so the build refuses rather than ships a rule pointing at nothing."""
        def unknown(path: object) -> UiError:
            return UiError(t("records.ui.unknown_path", kind=code_, path=path))

        name = rule["rule"]
        unread = [key for key in rule if key not in RULE_KEYS[name]]
        if name == "follows":
            unread += [f"advance.{key}" for key in dict(rule.get("advance", {})) if key not in ADVANCE_KEYS]
        if unread:
            raise UiError(t("records.ui.unknown_rule_key", kind=code_, rule=name, key=unread[0]))
        if name == "follows":
            known(rule.get("from"))
            known(rule.get("to"))
            for path in dict(rule.get("advance", {})).values():
                known(path)
        elif name == "late":
            for key in ("after", "event"):
                at = rule.get(key)
                if not isinstance(at, int) or isinstance(at, bool) or not 0 <= at < len(events):
                    raise unknown(at)
            # The field the source's own word for it is written in («так в подлиннике»): the page says no warning
            # where the record writes it — `stand_down` for a late event, `stand_down_before` for one before the first.
            for key in ("stand_down", "stand_down_before"):
                if key in rule:
                    known(rule[key])
        else:   # a group's: ref_choices, shown_when, renumber
            group = next((g for g in groups if g["name"] == rule.get("group")), None)
            if group is None:
                raise unknown(rule.get("group"))
            item = {f["path"] for f in group["item"]["fields"]}
            named = [rule.get("path")] if name in ("ref_choices", "shown_when") else [rule.get("number"),
                                                                                    *rule.get("refs", ())]
            for path in named:
                if path not in item:
                    raise unknown(path)

    def book(self, code_: str, cls: type, hint: Mapping[str, Any]) -> dict[str, Any]:
        spec = self.voc.specs[cls]
        keys = self.voc.json_keys[cls]
        taken: set[str] = set()
        flags: list[dict[str, Any]] = []
        for item in hint.get("flags", ()):
            path = item.get("field")
            f = next((f for f in spec.fields if keys[f.name] == path), None)
            if f is None or f.type != "bool":
                raise UiError(t("records.ui.unknown_path", kind=code_, path=path))
            if path in taken:
                raise UiError(t("records.ui.repeated", kind=code_, path=path))
            taken.add(path)
            flags.append({"field": path, "label": self.label(item.get("label"))})
        fields = self.placed(cls, code_, hint, taken=taken)
        known = {f.name: f for value in self._value_classes(cls) for f in self.voc.specs[value].fields}
        defaults: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in hint.get("fills", ()):
            name = item.get("field")
            if name not in known:
                raise UiError(t("records.ui.unknown_path", kind=code_, path=name))
            if name in seen:
                raise UiError(t("records.ui.repeated", kind=code_, path=name))
            seen.add(name)
            gender = item.get("gender")
            if gender is not None and gender not in GENDERS:
                raise UiError(t("records.ui.unknown_gender", kind=code_, path=name, gender=gender))
            default: dict[str, Any] = {"field": name, "label": self.label(item.get("label")), "gender": gender}
            # Typed as a record's field is: a page edits a default with the field's own widget.
            default.update(self.typed(known[name].type) or {})
            if "fallback" in item:
                default["fallback"] = item["fallback"]
            defaults.append(default)
        return {**self.labelled(hint.get("label"), hint.get("forms", ())), "fields": fields, "fills": defaults,
                "flags": flags, "queue": bool(hint.get("queue", False))}

    def _value_classes(self, cls: type) -> list[type]:
        return [value for (owner, _), value in self.voc.written_only.items()
                if owner is cls and isinstance(value, type) and value in self.voc.value_classes]

    def enum_table(self) -> dict[str, list[dict[str, Any]]]:
        hints: Mapping[str, Any] = self.hints.get("enums", {})
        out: dict[str, list[dict[str, Any]]] = {}
        for name, classes in self.enums.items():
            hint = hints.get(name)
            if hint is None:
                raise UiError(t("records.ui.unplaced_enum", enum=name))
            prefix = hint.get("label")
            forms: Sequence[str] = hint.get("forms", ())
            genders: Mapping[str, str] = hint.get("gender", {})
            members: list[dict[str, Any]] = []
            for cls in classes:
                for m in cls:
                    member_code = code(m) if len(classes) == 1 else f"{enum_code(cls)}.{code(m)}"
                    base = f"{prefix}.{member_code}"
                    gender = genders.get(member_code)
                    if gender is not None and gender not in GENDERS:
                        raise UiError(t("records.ui.unknown_gender", kind=name, path=member_code, gender=gender))
                    member: dict[str, Any] = {"code": member_code, **self.labelled(base, forms), "gender": gender}
                    members.append(member)
            out[name] = members
        return out


def build_ui(vocabulary: Vocabulary, hints: Mapping[str, Any]) -> dict[str, Any]:
    """The `ui-v1` schema of `vocabulary` as `hints` place it."""
    build = _Build(vocabulary, hints)
    records = {c for codes in vocabulary.holds.values() for c in codes}
    kinds: dict[str, Any] = {}
    for code_, hint in hints.get("kinds", {}).items():
        cls = vocabulary.by_code.get(code_)
        if cls is None or code_ not in records:
            raise UiError(t("records.ui.unknown_kind", kind=code_))
        kinds[code_] = build.kind(code_, cls, hint)
    person_hint = hints.get("person")
    person = vocabulary.specs[vocabulary.person].code
    fields = build.placed(vocabulary.person, person, person_hint) if person_hint is not None else []
    books: dict[str, Any] = {}
    for code_, hint in hints.get("books", {}).items():
        cls = vocabulary.by_code.get(code_)
        if cls is None or vocabulary.specs[cls].records_attr is None:
            raise UiError(t("records.ui.unknown_kind", kind=code_))
        books[code_] = build.book(code_, cls, hint)
    # The catalog the labels are keys of: a page names a label `<package>:<key>`.
    return {"schema": UI_ID, "records": SCHEMA_ID, "package": hints.get("package"), "kinds": kinds,
            "persona": {"fields": fields}, "enums": build.enum_table(), "books": books}


def dumps(schema: Mapping[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=1) + "\n"


def load_ui() -> dict[str, Any]:
    """The committed ui-v1.json: beside the workspace's DSL's vocabulary — read once per package, so a
    workspace of another plugin reads its own. Shared: read it, never write it."""
    from verso.core.records.fields import vocabulary
    return _committed(vocabulary().schema_package)


@cache
def _committed(package: str) -> dict[str, Any]:
    return json.loads(files(package).joinpath(UI_FILE).read_text(encoding="utf-8"))


def schema() -> dict[str, Any]:
    """The workspace's interface schema, built now from its plugin's vocabulary and hints."""
    from verso.core import plugins
    return build_ui(plugins.dsl().vocabulary, plugins.ui())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ui-v1.json: build, check")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the committed schema")
    group.add_argument("--check", action="store_true", help="exit 1 if the committed schema is stale")
    args = ap.parse_args(argv)
    from verso.core import plugins
    from verso.core.records.fields import vocabulary
    built = schema()
    if args.write:
        target = Path(str(files(vocabulary().schema_package).joinpath(UI_FILE)))
        target.write_text(dumps(built), encoding="utf-8")
        print(t("records.ui.written", target=target))
        return 0
    try:
        committed = load_ui()
    except FileNotFoundError:
        if not plugins.ui():
            return 0  # a plugin that gives no hints has no schema to commit
        committed = None
    if committed != built:
        print(t("records.ui.stale", file=UI_FILE))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
