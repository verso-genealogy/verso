"""One record as the review page reads it (`verso.ru.dsl.view`): the export's record, the
constants the source names, the paths no schema can edit, and `value_at`, whose cases the page's JS
reads too (tests/golden/ui/value-at.json). The books are invented."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import records_fixture as fixture
from verso.core.records.encode import context_in_derived, encode_namespace, encode_record
from verso.core.records.ids import Ids
from verso.ru.dsl import source
from verso.ru.dsl.view import record_view, value_at

from tests.test_dsl_paths import BIRTHS, CENSUS, DEATHS, MARRIAGES

VALUE_AT = Path(__file__).parent / "golden" / "ui" / "value-at.json"


def _built(text: str) -> list[Any]:
    """The records a DSL text builds, in the order its record calls stand."""
    namespace: dict[str, Any] = {}
    exec(compile(text, "<dsl>", "exec"), namespace)  # the tests' own invented text
    from verso.core.records.ids import records_of
    sets = [v for k, v in namespace.items() if k in ("book", "census")]
    return [r for s in sets for r in records_of(s)]


def _view(text: str, ordinal: int) -> dict[str, Any]:
    rec = source.find_records(text)[ordinal]
    return record_view(rec, _built(text)[ordinal], f"r1:test/{ordinal}")


def _records(doc: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    return [(r, d["variable"]) for d in doc["documents"] if "pages" in d for p in d["pages"] for r in p["records"]]


def test_the_view_is_the_export_s_record():
    ns = fixture.namespace()
    doc = encode_namespace(ns, village="Маниловка", file="1900/fixture.py", sha256="0" * 64, ids=Ids())
    exported = _records(doc)
    from verso.core.records.ids import walk
    built = list(walk(ns))
    assert len(built) == len(exported) > 10
    for (_, obj), (record, _) in zip(built, exported, strict=True):
        assert encode_record(obj, record["id"]) == record
    view = _view(BIRTHS, 0)
    # the page's record is the export's, a wrapper's value back in `derived` (records v1.0's shape)
    assert view["record"] == context_in_derived(encode_record(_built(BIRTHS)[0], "r1:test/0"))
    assert view["version"] == source.find_records(BIRTHS)[0].sha


def test_a_constant_is_named():
    view = _view(BIRTHS, 0)
    assert view["consts"]["mother/status"] == "PEASANT_WIFE"
    assert view["consts"]["gender"] == "Gender.MALE"
    mother = next(p for p in view["record"]["persons"] if p["role"] == "mother")
    assert mother["written"]["status"]["text"] == "законная жена крестьянина"
    assert _view(MARRIAGES, 0)["consts"]["witness/1/side"] == "Side.GROOM"
    assert _view(CENSUS, 0)["consts"]["members/2/role"] == "CensusRole.WIFE"
    assert _view(BIRTHS, 1)["consts"]["relatives/2/relationship"] == "Relationship.SON"


def test_an_expression_is_opaque_and_keeps_its_value():
    death = _view(DEATHS, 1)
    assert death["opaque"] == ["age", "comment"]
    assert value_at(death["record"], "age") == 5
    assert value_at(death["record"], "comment") == "см. л. 4"
    roll = _view(CENSUS, 1)
    assert roll["opaque"] == ["members"]
    assert "members/2/role" not in roll["consts"]
    assert value_at(roll["record"], "members/2/age") == 3
    assert value_at(roll["record"], "members/2/person/given.original") == "Мина"



def test_a_path_that_names_no_item_has_no_value():
    """A slot or a group asked without its number, or by a word where the number goes, holds nothing:
    None, as for a slot nobody fills — not an IndexError or a ValueError."""
    birth, roll = _view(BIRTHS, 0)["record"], _view(CENSUS, 1)["record"]
    for record, path in ((birth, "godparent"), (birth, "godparent/x/given.original"),
                         (roll, "members"), (roll, "members/x/age")):
        assert value_at(record, path) is None, path

CASES = [
    (BIRTHS, 0, ["number", "birth.day", "baptism.day", "birth.month", "gender", "father/given.original",
                 "father/surname.original", "mother/status", "godparent/2/given.original",
                 "godparent/2/patronymic.modern", "godparent/3/given.original", "child/surname.original"]),
    (BIRTHS, 1, ["relatives/1/relationship", "relatives/2/relationship_ref", "relatives/2/person/given.original",
                 "relatives/4/relationship"]),
    (MARRIAGES, 0, ["groom_age", "witness/1/side", "bride/given.original"]),
    (CENSUS, 0, ["members/1/number", "members/2/role", "members/3/ref_member", "members/3/person/given.original",
                 "members/3/person/patronymic.original"]),
]


def test_value_at_cases():
    expected = {"birth.day": 3, "baptism.day": 4, "birth.month": "may", "gender": "male",
                "father/surname.original": "Пересыпкинъ", "godparent/2/given.original": "Агнія",
                "godparent/3/given.original": None, "relatives/1/relationship": "father",
                "relatives/4/relationship": None, "witness/1/side": "groom", "members/2/role": "wife",
                "members/3/ref_member": 1, "members/3/person/patronymic.original": "Кузьмин"}
    out: list[dict[str, Any]] = []
    for text, ordinal, cases in CASES:
        record = _view(text, ordinal)["record"]
        values = {path: value_at(record, path) for path in cases}
        for path, want in expected.items():
            if path in values:
                assert values[path] == want, path
        out.append({"record": record, "cases": [[p, v] for p, v in values.items()]})
    text = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    if os.environ.get("VERSO_GOLDEN") == "update":
        VALUE_AT.parent.mkdir(parents=True, exist_ok=True)
        VALUE_AT.write_text(text, encoding="utf-8")
    assert VALUE_AT.read_text(encoding="utf-8") == text


SECTION = '''from verso.ru.dsl import Gender, Month, birth, birth_month_year, birth_records, page, person

book = birth_records(
    "ГАРО", "11", "22", "33", "Окуровка", "Никольская", 1890,
    *page("9", *birth_month_year(Month.JUNE, 1890,
                                 birth(6, Gender.MALE, 2, 3, child=person("Пахомъ"))),
          reviewed=False))
'''


def test_a_wrappers_values_reach_the_page_in_derived():
    """The page reads `written` as what the call alone wrote. A section's month and year and a
    лист's flag stand in `derived` for it, as records v1.0 wrote them — the shape below is that
    encoder's: the call's keys in `written`, every other value in `derived` in the field table's
    order (reviewed, birth.month, baptism.month, year) — and no `written.context`."""
    record = _view(SECTION, 0)["record"]
    assert record["review"] == "held"
    assert json.dumps(record["written"]) == json.dumps(
        {"number": 6, "gender": "male", "birth": {"day": 2}, "baptism": {"day": 3}})
    assert json.dumps(record["derived"]) == json.dumps(
        {"reviewed": False, "birth": {"month": "june"}, "baptism": {"month": "june"}, "year": 1890})
    assert list(record) == ["id", "label", "kind", "review", "written", "derived", "persons"]
    exported: dict[str, Any] = encode_record(_built(SECTION)[0], "r1:test/0")    # the export keeps v1.x's form
    assert exported["written"]["context"] == ["reviewed", "birth.month", "baptism.month", "year"]
    assert value_at(record, "birth.month") == value_at(exported, "birth.month") == "june"
