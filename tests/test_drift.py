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
