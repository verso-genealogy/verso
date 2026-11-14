"""The interface's schema on the toy plugin: `verso.core.records.ui` builds `ui-v1` from a
vocabulary and a plugin's hints, and knows no record kind of its own."""
from __future__ import annotations

import copy
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from tests.core.toy import TOY, TOY_VOCABULARY
from verso.core import plugins
from verso.core.records import ui
from verso.core.records.ui import UI_FILE, UiError, build_ui

pytestmark = pytest.mark.usefixtures("toy_workspace")


def _hints() -> dict[str, Any]:
    return copy.deepcopy(dict(plugins.ui()))


def _field(where: list[dict[str, Any]], path: str) -> dict[str, Any]:
    return next(f for f in where if f["path"] == path)


def test_the_toy_plugin_builds_its_ui_schema():
    committed = json.loads(files("tests.core").joinpath(UI_FILE).read_text(encoding="utf-8"))
    built = build_ui(TOY_VOCABULARY, plugins.ui())
    assert built == committed
    assert ui.main(["--check"]) == 0


def test_a_field_type_is_the_vocabulary_s():
    schema = build_ui(TOY_VOCABULARY, plugins.ui())
    note = schema["kinds"]["note"]
    assert _field(note["fields"], "number")["type"] == "age"          # intstr
    assert _field(note["fields"], "page")["type"] == "text"
    assert _field(note["fields"], "reviewed") == {"path": "reviewed", "type": "boolean", "hidden": True}
    gender = _field(schema["persona"]["fields"], "gender")
    assert gender["type"] == "enum" and gender["enum"] == "sex"
    assert [m["code"] for m in schema["enums"]["sex"]] == ["male", "female"]
    assert schema["enums"]["sex"][1] == {"code": "female", "label": "ui.enum.sex.female", "gender": "female"}
    book = schema["books"]["notes"]
    assert _field(book["fields"], "year")["type"] == "integer"
    assert _field(book["fields"], "shelfmark.fund")["label"] == "ui.book.fund"
    assert note["slots"] == [{"role": "who", "label": "ui.slot.who", "gender": "of_record"}]


def test_a_catalog_field_is_typed_by_its_scalar():
    from verso.core.records.fields import Field, Scalar, Vocabulary

    spec = TOY_VOCABULARY.specs
    who = next(c for c in spec if c.__name__ == "Who")
    fields = (*spec[who].fields, Field("title", "title"))
    voc = Vocabulary(
        specs={**spec, who: type(spec[who])(who, "who", fields, spec[who].factories)},
        value_classes=(), param_to_attr=TOY_VOCABULARY.param_to_attr, written_only={},
        item_roles={}, person=who, schema_package="tests.core", json_names=TOY_VOCABULARY.json_names,
        scalars={"title": Scalar("title", str, encode=dict, decode=str, same=str.__eq__,
                                 schema=({}, []))})
    hints = _hints()
    hints["person"]["fields"].append({"path": "title", "label": "ui.person.name"})
    title = _field(build_ui(voc, hints)["persona"]["fields"], "title")
    assert title == {"path": "title", "type": "catalog", "label": "ui.person.name", "catalog": "title"}


def test_a_field_s_place_in_a_person_s_row_is_the_hints():
    hints = _hints()
    person = hints["person"]["fields"]
    person[0] = {**person[0], "column": True, "suggest": True}
    person[1] = {**person[1], "line": True}
    fields = build_ui(TOY_VOCABULARY, hints)["persona"]["fields"]
    assert fields[0]["column"] is True and fields[0]["suggest"] is True and "line" not in fields[0]
    assert fields[1]["line"] is True and "column" not in fields[1]
    person[1] = {**person[1], "line": "yes"}
    assert _refused(hints, "not_a_flag")["flag"] == "line"


def test_a_field_that_only_answers_the_checks_is_marked_so():
    hints = _hints()
    person = hints["person"]["fields"]
    person[0] = {**person[0], "checks": True}
    fields = build_ui(TOY_VOCABULARY, hints)["persona"]["fields"]
    assert fields[0]["checks"] is True and "checks" not in fields[1]
    person[0] = {**person[0], "checks": 1}
    assert _refused(hints, "not_a_flag")["flag"] == "checks"


def test_a_person_s_field_may_say_whom_a_plus_offers_it():
    hints = _hints()
    person = hints["person"]["fields"]
    person[0] = {**person[0], "offer": {"gender": "female", "not_in": ["child"]}}
    fields = build_ui(TOY_VOCABULARY, hints)["persona"]["fields"]
    assert fields[0]["offer"] == {"gender": "female", "not_in": ["child"]} and "offer" not in fields[1]
    for wrong in ({}, {"gender": "of_record"}, {"not_in": []}, {"not_in": "child"}, {"sex": "female"}, "female"):
        person[0] = {**person[0], "offer": wrong}
        assert _refused(hints, "bad_offer")["path"] == person[0]["path"]


def test_a_record_s_field_may_name_its_one_click_adder():
    hints = _hints()
    page = _field(hints["kinds"]["note"]["fields"], "page")
    page["quick"] = "ui.note.page"
    fields = build_ui(TOY_VOCABULARY, hints)["kinds"]["note"]["fields"]
    assert _field(fields, "page")["quick"] == "ui.note.page"
    assert "quick" not in _field(fields, "number")
    page["quick"] = "ui.nowhere"
    assert _refused(hints, "unknown_label")["key"] == "ui.nowhere"


def test_an_adder_on_a_person_s_or_a_book_s_field_is_refused():
    hints = _hints()
    hints["person"]["fields"][0]["quick"] = "ui.person.name"
    assert _refused(hints, "quick_not_here") == {"kind": "who", "path": "full_name"}
    hints = _hints()
    _field(hints["books"]["notes"]["fields"], "year")["quick"] = "ui.book.year"
    assert _refused(hints, "quick_not_here")["path"] == "year"


def _refused(hints: dict[str, Any], key: str) -> dict[str, object]:
    with pytest.raises(UiError) as caught:
        build_ui(TOY_VOCABULARY, hints)
    assert caught.value.key == f"records.ui.{key}"
    return dict(caught.value.params)


def test_a_hint_path_the_vocabulary_lacks_is_refused():
    hints = _hints()
    hints["kinds"]["note"]["fields"].append({"path": "folio", "label": "ui.note.page"})
    assert _refused(hints, "unknown_path") == {"kind": "note", "path": "folio"}
    hints = _hints()
    hints["kinds"]["leaf"] = {"label": "ui.kind.note"}
    assert _refused(hints, "unknown_kind") == {"kind": "leaf"}


def test_an_unplaced_field_is_refused():
    hints = _hints()
    hints["kinds"]["note"]["fields"] = [f for f in hints["kinds"]["note"]["fields"] if f["path"] != "page"]
    assert _refused(hints, "unplaced") == {"kind": "note", "path": "page"}
    hints = _hints()
    hints["kinds"]["note"]["slots"] = []
    assert _refused(hints, "unplaced") == {"kind": "note", "path": "who"}


def test_an_unknown_label_key_is_refused():
    hints = _hints()
    hints["kinds"]["note"]["fields"][0]["label"] = "ui.nowhere"
    assert _refused(hints, "unknown_label") == {"key": "ui.nowhere", "package": "tests.core"}


def test_a_repeated_path_is_refused():
    hints = _hints()
    hints["kinds"]["note"]["fields"].append(dict(hints["kinds"]["note"]["fields"][0]))
    assert _refused(hints, "repeated") == {"kind": "note", "path": "number"}
    hints = _hints()
    hints["kinds"]["note"]["hidden"].append("page")
    assert _refused(hints, "repeated") == {"kind": "note", "path": "page"}


def test_an_unknown_rule_is_refused():
    hints = _hints()
    hints["kinds"]["note"]["rules"] = [{"rule": "guess"}]
    assert _refused(hints, "unknown_rule") == {"kind": "note", "rule": "guess"}


def test_a_rule_naming_an_unknown_path_is_refused():
    """A rule is what the page trusts for writes (a renumbering takes references along): every path,
    group and event it names is the kind's, or the build refuses rather than ships it."""
    for rule, path in (({"rule": "follows", "from": "nowhere", "to": "number"}, "nowhere"),
                       ({"rule": "renumber", "group": "nobody", "number": "number", "refs": []}, "nobody"),
                       ({"rule": "late", "after": 7, "event": 0, "days": 3}, 7)):
        hints = _hints()
        hints["kinds"]["note"]["rules"] = [rule]
        assert _refused(hints, "unknown_path") == {"kind": "note", "path": path}, rule


def test_the_message_says_what_is_wrong():
    hints = _hints()
    hints["kinds"]["note"]["fields"].append({"path": "folio", "label": "ui.note.page"})
    with pytest.raises(UiError, match="note: folio — no such field"):
        build_ui(TOY_VOCABULARY, hints)


def test_no_plugin_declares_ui():
    bare = plugins.Plugin(name="bare", package="tests.core", dsl=TOY.dsl)
    with plugins.adding(bare, entry_points=False):
        from verso.core import workspace
        root = workspace.current().root
        (root / "verso.toml").write_text('schema = 4\nplugins = ["bare"]\n', encoding="utf-8")
        with workspace.use(root):
            assert plugins.ui() == {}
            assert build_ui(TOY_VOCABULARY, plugins.ui()) == {
                "schema": "ui-v1", "records": "records-v1", "package": None, "kinds": {}, "persona": {"fields": []},
                "enums": {}, "books": {}}


def test_the_hints_cannot_rename_the_plugin_s_package(tmp_path: Path):
    """The labels are keys of the package the plugin declares: a `package` written in its hints is not
    the catalog they are read from."""
    hints = tmp_path / "ui-hints.toml"
    hints.write_text('package = "elsewhere"\n', encoding="utf-8")
    hinted = plugins.Plugin(name="hinted", package="tests.core", dsl=TOY.dsl, ui=lambda: hints)
    with plugins.adding(hinted, entry_points=False):
        from verso.core import workspace
        root = workspace.current().root
        (root / "verso.toml").write_text('schema = 4\nplugins = ["hinted"]\n', encoding="utf-8")
        with workspace.use(root):
            assert plugins.ui()["package"] == "tests.core"
