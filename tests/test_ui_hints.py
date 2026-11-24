"""The Russian books' interface schema: ui-v1.json is built from verso-ru's hints, places every
field of the vocabulary, labels each in both languages, and names in its references only the words
the translator reads."""
from __future__ import annotations

from typing import Any

from verso.core import i18n, plugins
from verso.core.records.fields import PERSON, ListOf, role_of
from verso.core.records.ui import build_ui, load_ui, main
from verso.ru.linters.checks.relationship_ref import is_allowed
from verso.ru.records.vocabulary import VOCABULARY as V
from verso.ru.facts.signals import DATE_ORDER_STOOD_DOWN, STAND_DOWN


def _schema() -> dict[str, Any]:
    return build_ui(V, plugins.ui())


def _labels(node: object) -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("label", "quick", "of") and isinstance(value, str):
                out.add(value)
            else:
                out |= _labels(value)
    elif isinstance(node, list):
        for item in node:
            out |= _labels(item)
    return out


def test_ui_v1_is_built_from_the_hints():
    assert load_ui() == _schema()
    assert main(["--check"]) == 0


def _entity_list(t: object) -> bool:
    return isinstance(t, ListOf) and isinstance(t.item, type) and t.item in V.specs and t.item not in V.value_classes


def test_every_record_field_is_placed():
    """Each of the vocabulary's 276 data fields stands in the schema or is hidden: a value class's
    fields by the field holding it, hidden, or (a book's defaults) by `books.*.defaults`."""
    schema = _schema()
    placed: dict[str, set[str]] = {"person": {f["path"] for f in schema["persona"]["fields"]}}
    for code, kind in schema["kinds"].items():
        placed[code] = {f["path"] for f in kind["fields"]}
        for group in kind["groups"]:
            item = V.specs[V.by_code[code]].field(group["name"]).type
            assert isinstance(item, ListOf) and isinstance(item.item, type)
            placed.setdefault(V.specs[item.item].code, set()).update(f["path"] for f in group["item"]["fields"])
    for code, book in schema["books"].items():
        placed[code] = {f["path"] for f in book["fields"]} | {f["field"] for f in book["flags"]}
    defaults = {d["field"] for book in schema["books"].values() for d in book["fills"]}
    count = 0
    for cls, spec in V.specs.items():
        keys = V.json_keys[cls]
        for f in spec.fields:
            if f.type == PERSON or _entity_list(f.type):
                continue
            count += 1
            if cls in V.value_classes:
                if spec.code == "record_defaults":
                    assert f.name in defaults, f"{spec.code}.{f.name}"
                continue
            assert keys[f.name] in placed.get(spec.code, set()), f"{spec.code}: {keys[f.name]}"
    assert count == 284


def test_every_label_has_both_languages():
    labels = _labels(_schema())
    assert labels
    for lang in ("en", "ru"):
        catalog = i18n.catalog("verso.ru", lang)
        missing = sorted(key for key in labels if key not in catalog)
        assert not missing, (lang, missing)
        assert not labels & i18n.untranslated("verso.ru", lang)


def test_the_ref_words_are_the_sources():
    """Every word a reference offers is one the translator reads (`relationship_ref`'s allowlist)."""
    words: list[str] = []
    for kind in _schema()["kinds"].values():
        for group in kind["groups"]:
            for field in group["item"]["fields"]:
                for choice in field.get("ref", {}).get("choices", ()):
                    words.append(choice["word"])
                    slot = next(s for s in kind["slots"] if s["role"] == choice["role"])
                    if "{n}" in choice["word"]:
                        lo, hi = slot["slots"]
                        for n in range(lo, hi + 1):
                            assert is_allowed(choice["word"].replace("{n}", str(n))), choice
                    else:
                        assert is_allowed(choice["word"]), choice
    assert {"жених", "невеста", "мать"} <= set(words)


def test_the_slots_are_the_vocabulary_s():
    schema = _schema()

    def slots(kind: str) -> dict[str, list[int] | None]:
        return {s["role"]: s.get("slots") for s in schema["kinds"][kind]["slots"]}

    assert slots("birth")["godparent"] == [1, 4]
    assert slots("marriage")["witness"] == [1, 6]
    assert slots("death")["witness"] == [1, 2]
    for code, kind in schema["kinds"].items():
        spec = V.specs[V.by_code[code]]
        roles = {role_of(f.name)[0] for f in spec.fields if f.type == PERSON}
        assert {s["role"] for s in kind["slots"]} == roles, code
    sides = [(code, s["role"], s["party"]) for code, kind in schema["kinds"].items() for s in kind["slots"]
             if s.get("party")]
    assert sides == [("marriage", "witness", "side")]
    # …the person's field that says the side, an enum of the persona.
    side = next(f for f in schema["persona"]["fields"] if f["path"] == "side")
    assert side["type"] == "enum"


def test_the_page_s_tables_are_in_the_hints():
    """What app.js keeps today, spot-checked: a burial's day is labelled as a burial's, the dates and
    their lateness, the drafts, a roll member's layout and references, the books' defaults."""
    schema = _schema()
    ru = i18n.catalog("verso.ru", "ru")

    def label(kind: str, path: str) -> str:
        return str(ru[next(f for f in schema["kinds"][kind]["fields"] if f["path"] == path)["label"]])

    assert label("death", "burial.day") == "день погреб." and label("birth", "birth.day") == "день рожд."
    assert label("birth", "calendar_note") == "имя не по святцам — верно"
    assert label("birth", "lag_note") == "позднее крещение — верно"
    assert label("death", "lag_note") == "позднее погребение — верно"
    assert label("marriage", "age_note") == "возраст при венчании — верно"
    assert label("divorce", "calendar_note") == "брак в запретный день — верно"
    assert label("divorce", "source_date_error") == "ошибка даты в подлиннике"
    late = {k: [r["days"] for r in v["rules"] if r["rule"] == "late"] for k, v in schema["kinds"].items()}
    assert (late["birth"], late["death"], late["marriage"]) == ([12], [4], [])
    # The field that stands each late rule down is the one the signal of its check names (STAND_DOWN).
    for kind, check in (("birth", "baptism-lag"), ("death", "burial-lag")):
        (rule,) = [r for r in schema["kinds"][kind]["rules"] if r["rule"] == "late"]
        assert (rule["stand_down"], rule["stand_down_before"]) == (STAND_DOWN[check], STAND_DOWN["date-order"])
    assert DATE_ORDER_STOOD_DOWN == {"baptism_before_birth", "burial_before_death"}
    follows = [r for r in schema["kinds"]["birth"]["rules"] if r["rule"] == "follows"]
    assert follows == [{"rule": "follows", "from": "birth.month", "to": "baptism.month",
                        "advance": {"day_from": "birth.day", "day_to": "baptism.day"}}]
    assert {r["rule"] for r in schema["kinds"]["household"]["rules"]} == {"shown_when", "renumber"}
    assert {k: v["draft"]["slots"] for k, v in schema["kinds"].items() if v["draft"]["creatable"]} == {
        "birth": ["child", "father", "mother"], "marriage": ["groom", "bride"], "death": ["deceased"]}
    (members,) = schema["kinds"]["household"]["groups"]
    assert members["layout"][0] == ["number", "role", "ref_member"]
    refs = {f["path"]: f["ref"]["to"] for f in members["item"]["fields"] if "ref" in f}
    assert refs == dict.fromkeys(("ref_member", "parent_member", "spouse_member", "secondary_ref_member"), "item")
    groom = next(s for s in schema["kinds"]["marriage"]["slots"] if s["role"] == "groom")
    assert groom["row"] == ["groom_age", "groom_marriage_number"] and groom["gender"] == "male"
    births = schema["books"]["births"]
    assert [d["field"] for d in births["fills"]] == ["residence", "status_male", "status_female", "status_mother"]
    assert births["fills"][3]["fallback"] == "status_female"
    # …each typed as a field is: a place is text, a status a constant of its catalog.
    assert {d["field"]: (d["type"], d.get("catalog")) for d in births["fills"]} == {
        "residence": ("text", None), "status_male": ("catalog", "status"), "status_female": ("catalog", "status"),
        "status_mother": ("catalog", "status")}
    deaths = schema["books"]["deaths"]
    assert next(d for d in deaths["fills"] if d["field"] == "cause_of_death")["catalog"] == "cause"
    assert schema["books"]["census"]["flags"] == [{"field": "female_previous_age", "label": "ui.book.female_previous_age"}]
    assert [str(ru[m["forms"]["gen"]]) for m in schema["enums"]["month"]][:2] == ["января", "февраля"]
    assert schema["enums"]["census_role"][0] == {"code": "head", "label": "ui.enum.census_role.head", "gender": None}


def _fields(node: object) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "path" in node and "type" in node and "label" in node:
            out.append(node)
        for value in node.values():
            out += _fields(value)
    elif isinstance(node, list):
        for item in node:
            out += _fields(item)
    return out


def test_the_notes_to_the_checks_are_marked_and_nothing_else():
    """«Так в подлиннике», «не по святцам — верно», «тёзка»: what only stands a check down is offered in no «+ поле»
    (`checks`) — on every kind that has it, a roll member's two age notes too; a field of the record is never so marked."""
    notes = {"source_date_error", "calendar_note", "source_kin_error", "source_age_error", "namesake", "previous_age_error",
             "lag_note", "age_note"}
    shown = [f for kind in _schema()["kinds"].values() for f in _fields(kind) if not f.get("hidden")]
    assert {f["path"] for f in shown if f.get("checks")} == notes
    assert all(f.get("checks") for f in shown if f["path"] in notes)


def test_the_birth_surname_is_offered_to_women_who_are_not_a_newborn():
    """«фамилия при рождении» (Geni's and Familio's birth surname): a newborn girl's is derived from her parents, a man's is his
    surname — so a «+» offers it to a woman alone, and not to the child of a birth or a christening."""
    field = next(f for f in _schema()["persona"]["fields"] if f["path"] == "maiden_surname.modern")
    assert field["offer"] == {"gender": "female", "not_in": ["child"]}
    assert i18n.render(i18n.Message("verso.ru", "ui.field.maiden_surname_modern", {}), "ru") == "фамилия при рождении"


def test_what_the_plugin_sets_itself_is_marked_auto():
    """«фамилия в книге»: unticked by the plugin wherever it derives a surname (a mother's, a wife's) — offered in no «+»."""
    marked = [f["path"] for f in _fields(_schema()) if f.get("auto")]
    assert marked == ["surname.in_book"]

