"""`verso.ru.records.blank`: an empty metric book built from a record set's factory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import village_fixture
from verso.core import workspace
from verso.core.pipeline.load import load_module, record_namespace
from verso.core.records import schema
from verso.core.records.encode import encode_namespace
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import replay_file
from verso.ru.dsl import birth_records
from verso.ru.dsl.statuses import PEASANT_FEMALE, PEASANT_MALE, PEASANT_WIFE
from verso.ru.records.blank import BlankError, BookSpec, blank_book, book_path


def _spec(**over: Any) -> BookSpec:
    base: dict[str, Any] = dict(kind="births", locality="Маниловка", year=1901, archive="ГАРО", fund="755",
                                inventory="473", case="170", part=None, church="Сретенская",
                                parish="Хлестаковка", defaults=None)
    base.update(over)
    return BookSpec(**base)


def test_blank_book_is_valid(tmp_path: Path) -> None:
    data = blank_book(_spec())
    (tmp_path / "Маниловка" / "1901").mkdir(parents=True)
    (tmp_path / "Маниловка" / "1901" / "x.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert schema.validate(tmp_path / "Маниловка" / "1901") == []
    doc = data["documents"][0]
    assert doc["pages"] == []
    assert "reviewed" not in doc["written"]
    assert data["sha256"] == "" and data["file"] == "1901/births_755-473-170.py"
    assert doc["id"] == "r1:Хлестаковка/755-473-170/1901/birth"
    assert doc["variable"] == "births_755_473_170"


def test_blank_book_replays() -> None:
    spec = _spec()
    sets: dict[str, Any] = replay_file(blank_book(spec))
    built = birth_records("ГАРО", "755", "473", "170", "Хлестаковка", "Сретенская", 1901)
    assert first_difference(built, sets["births_755_473_170"]) is None
    assert sets["births_755_473_170"].records == []


def test_blank_book_then_record_equals_dsl(tmp_path: Path) -> None:
    root = village_fixture.root(tmp_path)
    village_fixture.workspace(tmp_path, root)
    with workspace.use(root):
        ns = record_namespace(load_module(root / "Маниловка/1900/manilovka_births_1900.py"))
        full = json.loads(json.dumps(encode_namespace(ns, village="Маниловка", file="1900/f.py", sha256="0" * 64,
                                                      ids=Ids()), ensure_ascii=False))
    document = full["documents"][0]
    written = document["written"]
    spec = _spec(year=written["year"], fund=written["fund"], inventory=written["inventory"], case=written["case"],
                 archive=written["archive"], church=written["church"], parish=written["village"],
                 defaults={"residence": "Маниловка", "status_male": PEASANT_MALE, "status_female": PEASANT_FEMALE,
                           "status_mother": PEASANT_WIFE})
    blank = blank_book(spec)
    blank["documents"][0]["pages"] = [{"page": p["page"], "records": [r for r in p["records"]]}
                                      for p in document["pages"]]
    whole = replay_file(blank)
    assert first_difference(ns[document["variable"]], whole[blank["documents"][0]["variable"]]) is None


@pytest.mark.parametrize("over, key", [
    ({"year": 1699}, "records.blank.year"), ({"year": 1931}, "records.blank.year"),
    ({"fund": " "}, "records.blank.shelfmark"), ({"case": ""}, "records.blank.shelfmark"),
    ({"inventory": ""}, "records.blank.shelfmark"),
    ({"locality": "а/б"}, "records.blank.path"), ({"case": "..\\x"}, "records.blank.path"),
    ({"part": "a..b"}, "records.blank.path"), ({"kind": "census"}, "records.blank.kind"),
    ({"fund": " 755"}, "records.blank.path"), ({"case": "170 "}, "records.blank.path"),
    ({"locality": " Маниловка"}, "records.blank.path"), ({"part": "2 "}, "records.blank.path"),
    ({"fund": "75\n5"}, "records.blank.path"), ({"inventory": "47\x003"}, "records.blank.path"),
    ({"case": "17\t0"}, "records.blank.path"), ({"part": "2\x1b"}, "records.blank.path"),
    ({"locality": "Мани\x7fловка"}, "records.blank.path"), ({"parish": "Хлеста\nковка"}, "records.blank.path"),
    ({"locality": ""}, "records.blank.path"), ({"locality": "."}, "records.blank.path"),
    ({"locality": ".."}, "records.blank.path"), ({"parish": ""}, "records.blank.parish"),
    ({"parish": "  "}, "records.blank.parish"),
    ({"defaults": {"no_such_default": 1}}, "records.blank.defaults"),
])
def test_blank_refuses(over: dict[str, Any], key: str) -> None:
    with pytest.raises(BlankError) as refused:
        blank_book(_spec(**over))
    assert refused.value.key == key


def test_path_keeps_cyrillic() -> None:
    path = book_path(_spec(locality="Нижняя Ѳедоровка", part="2"))
    assert path.startswith("Нижняя Ѳедоровка/1901/") and path.endswith("births_755-473-170_2.json")


def test_blank_error_carries_key_and_params() -> None:
    with pytest.raises(BlankError) as refused:
        blank_book(_spec(year=1699))
    assert refused.value.key == "records.blank.year" and refused.value.params == {"year": 1699}
    assert "1699" in str(refused.value)
    with pytest.raises(BlankError) as path:
        blank_book(_spec(fund="a/b"))
    assert path.value.params == {"value": "a/b"}
    with pytest.raises(BlankError) as parish:
        blank_book(_spec(parish=""))
    assert parish.value.params == {}
    with pytest.raises(BlankError) as defaults:
        blank_book(_spec(defaults={"no_such_default": 1}))
    assert set(defaults.value.params) == {"error"}


def test_blank_error_old_form_still_works() -> None:
    error = BlankError("some.key", "a ready message")
    assert str(error) == "a ready message" and error.key == "some.key" and error.params == {}


@pytest.mark.parametrize("kind", ["births", "marriages", "deaths"])
def test_blank_kinds_are_valid_and_replay(tmp_path: Path, kind: str) -> None:
    data = blank_book(_spec(kind=kind))
    folder = tmp_path / "Маниловка" / "1901"
    folder.mkdir(parents=True)
    (folder / "x.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert schema.validate(folder) == []
    sets: dict[str, Any] = replay_file(data)
    assert list(sets) == [f"{kind}_755_473_170"] and sets[f"{kind}_755_473_170"].records == []


def test_part_is_in_the_file_variable_and_path_not_the_id() -> None:
    plain, parted = _spec(), _spec(part="2")
    data = blank_book(parted)
    doc = data["documents"][0]
    assert data["file"] == "1901/births_755-473-170_2.py"
    assert doc["variable"] == "births_755_473_170_2"
    assert doc["id"] == blank_book(plain)["documents"][0]["id"]
    assert book_path(parted) == "Маниловка/1901/births_755-473-170_2.json" != book_path(plain)
