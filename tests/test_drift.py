from verso.ru.consolidation.drift import classify


def _names(last):
    return {"ru": {"last_name": last}}


def test_merge_detected_by_id_change():
    cat, _ = classify({"id": "profile-1", "guid": "g1"}, {"id": "profile-2", "guid": "g1"})
    assert cat == "MERGE"


def test_merge_detected_by_guid_change():
    cat, _ = classify({"id": "p", "guid": "g1"}, {"id": "p", "guid": "g2"})
    assert cat == "MERGE"


def test_project_replace():
    cat, _ = classify(
        {"id": "p", "guid": "g", "projects": ["a", "b"]},
        {"id": "p", "guid": "g", "projects": ["a"]},
    )
    assert cat == "PROJECT-REPLACE"


def test_content_surname_change():
    cat, detail = classify(
        {"id": "p", "guid": "g", "names": _names("Стужева")},
        {"id": "p", "guid": "g", "names": _names("")},
    )
    assert cat == "CONTENT"
    assert "last_name" in detail


def test_content_death_date_change():
    cat, detail = classify(
        {"id": "p", "guid": "g", "death": {"date": {"year": 1850, "range": "after"}}},
        {"id": "p", "guid": "g", "death": {"date": {"year": 1834, "range": "after"}}},
    )
    assert cat == "CONTENT"
    assert "death" in detail


def test_derived_name_only_is_cosmetic():
    # Same birth date, only the event .name differs → derived-name churn.
    birth = {"date": {"year": 1827, "day": 28, "month": 1, "range": None}}
    cat, _ = classify(
        {"id": "p", "guid": "g", "birth": {**birth, "name": "Birth of Anna Holodtsova"}},
        {"id": "p", "guid": "g", "birth": {**birth, "name": "Birth of Anna"}},
    )
    assert cat == "DERIVED-NAME"


def test_identical_is_no_change():
    profile = {"id": "p", "guid": "g", "names": _names("Стужева"), "birth": {"date": {"year": 1827}}}
    assert classify(profile, dict(profile)) is None


def test_content_birth_last_name_change():
    # Only last_name was compared once: a maiden name changed on Geni read as derived churn (В18).
    cat, detail = classify(
        {"id": "p", "guid": "g", "names": {"ru": {"last_name": "Стужева", "birth_last_name": "Холодцова"}}},
        {"id": "p", "guid": "g", "names": {"ru": {"last_name": "Стужева", "birth_last_name": "Морозцова"}}},
    )
    assert (cat, detail) == ("CONTENT", "ru.birth_last_name")


def test_content_event_place_change():
    cat, detail = classify(
        {"id": "p", "guid": "g", "birth": {"date": {"year": 1827}, "location": {"city": "Заманиловка"}}},
        {"id": "p", "guid": "g", "birth": {"date": {"year": 1827}, "location": {"city": "Горюхино"}}},
    )
    assert (cat, detail) == ("CONTENT", "birth")


def test_content_unions_change():
    cat, detail = classify({"id": "p", "guid": "g", "unions": ["union-1"]},
                           {"id": "p", "guid": "g", "unions": ["union-1", "union-2"]})
    assert (cat, detail) == ("CONTENT", "unions")


def test_unknown_after_is_no_difference():
    # A planned update leaves the event names and the unions to be computed: null in `after`.
    birth = {"date": {"year": 1827}}
    before = {"id": "p", "guid": "g", "unions": ["union-1"], "birth": {**birth, "name": "Birth of Anna"}}
    after = {"id": "p", "guid": "g", "unions": None, "birth": dict(birth)}
    assert classify(before, after, {"unions": True, "birth": {"date": {}, "name": True}}) is None


def test_main_skips_no_ops(monkeypatch, capsys):
    from verso.ru.consolidation import drift
    same = {"id": "p", "guid": "g", "names": _names("Стужева")}
    plan = {"resource_changes": [
        {"address": f"geni_profile.p{i}", "change": {"actions": ["no-op"], "before": same, "after": same}}
        for i in range(3)
    ] + [{"address": "geni_profile.q", "change": {
        "actions": ["update"], "before": same, "after": {**same, "names": _names("Холодцова")}}}]}
    monkeypatch.setattr(drift, "_load_plan", lambda arg, plan_file: plan)
    assert drift.main(["x"]) == 0
    out = capsys.readouterr().out
    assert "planned changes: 1 resource(s)" in out
    assert "── CONTENT (1)" in out and "DERIVED-NAME" not in out


def test_a_computed_list_element_is_no_difference():
    before = {"id": "p", "guid": "g", "unions": ["union-1"]}
    after = {"id": "p", "guid": "g", "unions": [None]}
    assert classify(before, after, {"unions": [True]}) is None


def test_the_providers_empties_are_one():
    before = {"id": "p", "guid": "g", "about": "", "unions": [], "birth": {"date": {"year": 1827}, "location": None}}
    after = {"id": "p", "guid": "g", "unions": None, "birth": {"date": {"year": 1827}}}
    assert classify(before, after) is None


def test_main_lists_planned_creates_and_deletes_apart(monkeypatch, capsys):
    from verso.ru.consolidation import drift
    new = {"id": None, "guid": None, "names": _names("Стужева"), "projects": ["a"]}
    plan = {"resource_changes": [
        {"address": "geni_profile.new", "change": {"actions": ["create"], "before": None, "after": new}},
        {"address": "geni_profile.old", "change": {"actions": ["delete"], "before": new, "after": None}},
    ]}
    monkeypatch.setattr(drift, "_load_plan", lambda arg, plan_file: plan)
    assert drift.main(["x"]) == 0
    out = capsys.readouterr().out
    assert "planned changes: 0 resource(s)" in out
    assert "── PLANNED-CREATE (1)\n  geni_profile.new" in out and "── PLANNED-DELETE (1)\n  geni_profile.old" in out
    assert "MERGE" not in out and "PROJECT-REPLACE" not in out
