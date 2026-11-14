"""Edits addressed by the records' own names (`verso.ru.dsl.paths`): a v2 operation writes what
the same v1 edit wrote, character for character, and an edit refused says its key and params. The
books below are invented: people, villages, numbers and the archive alike."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from verso.core.records.ui import load_ui
from verso.ru.dsl import paths, source
from verso.ru.dsl.paths import PathError, path_of, translate

BIRTHS = '''from verso.ru.dsl import Gender, Month, Relationship, birth, birth_month, birth_records, person, relative
from verso.ru.dsl.statuses import PEASANT_WIFE

book = birth_records(
    "ГАРО", "11", "22", "33", "Окуровка", "Никольская", 1890,
    *birth_month(Month.MAY,
                 birth(4, Gender.MALE, 3, 4,
                       child=person("Пахомъ"),
                       father=person("Кузьма", "Лукинъ", "Пересыпкинъ"),
                       mother=person("Ѳекла", "Петрова", status=PEASANT_WIFE),
                       god_parent1=person("Лука", "Ильинъ", "Пересыпкинъ"),
                       god_parent2=person("Агнія", "Лукина")),
                 birth(5, Gender.FEMALE, 7, 8,
                       child=person("Васса"),
                       father=person("Савва", "Ѳомичъ", "Перекатовъ"),
                       mother=person("Марѳа", "Саввина"),
                       relatives=[relative(person("Ѳома", "Ильинъ", "Перекатовъ"), Relationship.FATHER, "мать"),
                                  # her mother's brother, as the book says
                                  relative(person("Ипатъ", "Ильинъ"), Relationship.SON, "мать"),
                                  relative(person("Аѳанасій"), Relationship.SON, "мать")]),
                 ),
)
'''
MARRIAGES = '''from verso.ru.dsl import Month, Side, marriage, marriage_month, marriage_records, person

book = marriage_records(
    "ГАРО", "11", "22", "34", "Окуровка", "Никольская", 1890,
    *marriage_month(Month.MAY,
                    marriage(1, 12,
                             groom=person("Кузьма", "Лукинъ", "Пересыпкинъ"),
                             bride=person("Ѳекла", "Петрова"),
                             groom_age=24, bride_age=19,
                             witness1=person("Лука", "Ильинъ", side=Side.GROOM)),
                    ),
)
'''
DEATHS = '''from verso.ru.dsl import Gender, Month, death, death_month, death_records, person

book = death_records(
    "ГАРО", "11", "22", "35", "Окуровка", "Никольская", 1890,
    *death_month(Month.MAY,
                 death(1, Gender.MALE, 3, 5,
                       deceased=person("Пахомъ"), age=2),
                 death(2, Gender.FEMALE, 4, 6,
                       deceased=person("Марѳа"), age=2 + 3, comment=f"{'см.'} л. 4"),
                 ),
)
'''
CENSUS = '''from verso.ru.dsl import CensusRole, census_records, household, member, page, person

ROWS = [member(9, person("Мина"), CensusRole.SON, ref_member=1, age=3)]

census = census_records(
    "ГАРО", "11", "22", "36", "Окуровка",
    1858,
    *page("4",
          household("1",
                    member(1, person("Кузьма", "Лукинъ", "Пересыпкинъ"), CensusRole.HEAD, age=40),
                    member(2, person("Ѳекла", "Петрова"), CensusRole.WIFE, ref_member=1, age=35),
                    member(3, person("Пахомъ"), CensusRole.SON, ref_member=1, age=6)),
          household("2",
                    member(1, person("Савва", "Ѳомичъ"), CensusRole.HEAD, age=50),
                    *ROWS)),
)
'''


def _record(text: str, ordinal: int) -> source.Record:
    return source.find_records(text)[ordinal]


def _v1(text: str, ordinal: int, ops: list[dict[str, Any]]) -> str:
    rec = _record(text, ordinal)
    return source.apply(text, ordinal, rec.sha, ops)


def _v2(text: str, ordinal: int, ops: list[dict[str, Any]]) -> str:
    rec = _record(text, ordinal)
    return source.apply(text, ordinal, rec.sha, translate(rec.func, ops, call=rec.call))


def _s(v: str) -> dict[str, Any]:
    return {"kind": "str", "value": v}


PAIRS: list[tuple[str, str, int, list[dict[str, Any]], list[dict[str, Any]]]] = [
    ("a day", BIRTHS, 0, [{"op": "set", "path": ["b_day"], "value": {"kind": "int", "value": 2}}],
     [{"op": "set", "path": "birth.day", "value": 2}]),
    ("a slot's name", BIRTHS, 0, [{"op": "set", "path": ["god_parent2", "name_orig"], "value": _s("Агриппина")}],
     [{"op": "set", "path": "godparent/2/given.original", "value": "Агриппина"}]),
    ("a constant", BIRTHS, 0, [{"op": "set", "path": ["father", "status"], "value": {"kind": "const", "value": "PEASANT_WIFE"}}],
     [{"op": "set", "path": "father/status", "value": {"const": "PEASANT_WIFE"}}]),
    ("a status as text", BIRTHS, 0, [{"op": "set", "path": ["father", "status"], "value": _s("однодворецъ")}],
     [{"op": "set", "path": "father/status", "value": {"text": "однодворецъ"}}]),
    ("an enum", BIRTHS, 0, [{"op": "set", "path": ["b_month"], "value": {"kind": "const", "value": "Month.APRIL"}}],
     [{"op": "set", "path": "birth.month", "value": "april"}]),
    ("unset", BIRTHS, 0, [{"op": "delete", "path": ["mother", "status"]}],
     [{"op": "unset", "path": "mother/status"}]),
    ("a new slot", BIRTHS, 0, [{"op": "set", "path": ["god_parent3"], "value": {
        "kind": "call", "func": "person", "args": [{"param": "name_orig", "value": _s("Ия")}]}}],
     [{"op": "add", "path": "godparent/3", "value": {"given.original": "Ия"}}]),
    ("the lowest free slot", BIRTHS, 0, [{"op": "set", "path": ["god_parent3"], "value": {
        "kind": "call", "func": "person", "args": [{"param": "name_orig", "value": _s("Ия")}]}}],
     [{"op": "add", "path": "godparent", "value": {"given.original": "Ия"}}]),
    ("a person removed", BIRTHS, 0, [{"op": "delete", "path": ["god_parent2"]}],
     [{"op": "remove", "path": "godparent/2"}]),
    ("a relative's word", BIRTHS, 1, [{"op": "set", "path": ["relatives", "#0", "relationship_ref"], "value": _s("восприемника №1")}],
     [{"op": "set", "path": "relatives/1/relationship_ref", "value": "восприемника №1"}]),
    ("a relative's person", BIRTHS, 1, [{"op": "set", "path": ["relatives", "#1", "person", "patr_orig"], "value": _s("Ѳомичъ")}],
     [{"op": "set", "path": "relatives/2/person/patronymic.original", "value": "Ѳомичъ"}]),
    ("a relative added", BIRTHS, 1, [{"op": "set", "path": ["relatives", "#+"], "value": {
        "kind": "call", "func": "relative", "args": [
            {"param": "person", "value": {"kind": "call", "func": "person", "args": [{"param": "name_orig", "value": _s("Минай")}]}},
            {"param": "relationship", "value": {"kind": "const", "value": "Relationship.SON"}}]}}],
     [{"op": "add", "path": "relatives", "value": {"relationship": "son", "person/given.original": "Минай"}}]),
    ("relatives written anew", BIRTHS, 0, [{"op": "set", "path": ["relatives"], "value": {
        "kind": "raw", "code": '[relative(person("Минай"), Relationship.SON)]'}}],
     [{"op": "add", "path": "relatives", "value": {"person/given.original": "Минай", "relationship": "son"}}]),
    ("a relative removed", BIRTHS, 1, [{"op": "delete", "path": ["relatives", "#0"]}],
     [{"op": "remove", "path": "relatives/1"}]),
    ("a witness's side", MARRIAGES, 0, [{"op": "set", "path": ["witness1", "side"], "value": {"kind": "const", "value": "Side.BRIDE"}}],
     [{"op": "set", "path": "witness/1/side", "value": "bride"}]),
    ("a row's age", MARRIAGES, 0, [{"op": "set", "path": ["groom_age"], "value": {"kind": "str", "value": "24 л 2 мес"}}],
     [{"op": "set", "path": "groom_age", "value": "24 л 2 мес"}]),
    ("a member's age", CENSUS, 0, [{"op": "set", "path": ["@2", "age"], "value": {"kind": "int", "value": 7}}],
     [{"op": "set", "path": "members/3/age", "value": 7}]),
    ("a member's name", CENSUS, 0, [{"op": "set", "path": ["@1", "person", "name_orig"], "value": _s("Ѳеодосія")}],
     [{"op": "set", "path": "members/2/person/given.original", "value": "Ѳеодосія"}]),
    ("a member added", CENSUS, 0, [{"op": "set", "path": ["@+"], "value": {"kind": "call", "func": "member", "args": [
        {"param": "number", "value": {"kind": "int", "value": 4}},
        {"param": "person", "value": {"kind": "call", "func": "person", "args": [{"param": "name_orig", "value": _s("Мина")}]}},
        {"param": "role", "value": {"kind": "const", "value": "CensusRole.SON"}},
        {"param": "ref_member", "value": {"kind": "int", "value": 1}}]}}],
     [{"op": "add", "path": "members", "value": {"number": 4, "person/given.original": "Мина", "role": "son",
                                                 "ref_member": 1}}]),
    ("a member moved", CENSUS, 0, [{"op": "move", "path": ["@2"], "to": 0}],
     [{"op": "move", "path": "members/3", "to": 1}]),
    ("a member removed", CENSUS, 0, [{"op": "delete", "path": ["@1"]}],
     [{"op": "remove", "path": "members/2"}]),
    ("a member inserted", CENSUS, 0, [
        {"op": "set", "path": ["@+"], "value": {"kind": "call", "func": "member", "args": [
            {"param": "number", "value": {"kind": "int", "value": 4}},
            {"param": "person", "value": {"kind": "call", "func": "person", "args": [{"param": "name_orig", "value": _s("Мина")}]}}]}},
        {"op": "move", "path": ["@3"], "to": 1}],
     [{"op": "insert", "path": "members/2", "value": {"number": 4, "person/given.original": "Мина"}}]),
]


@pytest.mark.parametrize(("name", "text", "ordinal", "v1", "v2"), PAIRS, ids=[p[0] for p in PAIRS])
def test_v2_writes_what_v1_wrote(name: str, text: str, ordinal: int, v1: list[dict[str, Any]],
                                 v2: list[dict[str, Any]]):
    del name
    before = _v1(text, ordinal, v1)
    assert before != text
    assert _v2(text, ordinal, v2) == before


WHOLE_YEARS = [
    ("a bare number", DEATHS, "age", "4", "age=4"),
    ("years by their unit", DEATHS, "age", "5 лет", "age=5"),
    ("months stay text", DEATHS, "age", "4 мес", 'age="4 мес"'),
    ("an idiom stays text", DEATHS, "age", "полгода", 'age="полгода"'),
    ("a groom's age", MARRIAGES, "groom_age", "25", "groom_age=25"),
    ("a compound age stays text", MARRIAGES, "bride_age", "19 лет 6 мес", 'bride_age="19 лет 6 мес"'),
    ("a record's number is no age", DEATHS, "number", "12", 'death("12"'),
    ("a roll's age is not AGE001's", CENSUS, "members/3/age", "4", 'age="4"'),
]


@pytest.mark.parametrize(("name", "text", "path", "typed", "written"), WHOLE_YEARS, ids=[w[0] for w in WHOLE_YEARS])
def test_whole_years_are_written_as_an_integer(name: str, text: str, path: str, typed: str, written: str):
    """An age typed as a whole number of years is written as the integer AGE001 asks for, so the
    page's edit gains no finding; what the integer cannot say stays text."""
    del name
    assert written in _v2(text, 0, [{"op": "set", "path": path, "value": typed}])


def test_relatives_move():
    """The elements of `relatives=[…]` change places; the comment over one goes with it."""
    moved = _v2(BIRTHS, 1, [{"op": "move", "path": "relatives/3", "to": 2}])

    def names(text: str) -> list[str]:
        rel = _record(text, 1).call.arg("relatives")
        assert rel is not None and rel.value.items is not None
        return [i.call.arg("person").value.call.args[0].value.value for i in rel.value.items]  # type: ignore[union-attr]

    assert names(moved) == ["Ѳома", "Аѳанасій", "Ипатъ"]
    assert moved.index("# her mother's brother") < moved.index('person("Ипатъ"')
    assert moved.index('person("Аѳанасій"') < moved.index("# her mother's brother")
    assert _v2(moved, 1, [{"op": "move", "path": "relatives/2", "to": 3}]) == BIRTHS
    # A comment cannot ride to the line `relatives=[` opens: that is the editor's.
    with pytest.raises(source.EditError) as refused:
        _v2(BIRTHS, 1, [{"op": "move", "path": "relatives/2", "to": 1}])
    assert refused.value.key == "source.member_comment"
    moved = _v2(BIRTHS, 1, [{"op": "move", "path": "relatives/3", "to": 1}])
    assert names(moved) == ["Аѳанасій", "Ѳома", "Ипатъ"]


def test_path_of_inverts_translate():
    """For every field the schema lets a page set, the DSL path `translate` writes reads back as it."""
    schema = load_ui()
    cases = {"birth": (BIRTHS, 1), "marriage": (MARRIAGES, 0), "household": (CENSUS, 0), "death": (DEATHS, 0)}
    seen = 0
    for kind, (text, ordinal) in cases.items():
        rec = _record(text, ordinal)
        k = schema["kinds"][kind]
        wanted = [f["path"] for f in k["fields"] if not f.get("hidden")]
        for slot in k["slots"]:
            prefix = slot["role"] if "slots" not in slot else f"{slot['role']}/{slot['slots'][0]}"
            wanted += [f"{prefix}/{f['path']}" for f in schema["persona"]["fields"] if not f.get("hidden")]
        for g in k["groups"]:
            wanted += [f"{g['name']}/1/{f['path']}" for f in g["item"]["fields"] if not f.get("hidden")]
            wanted += [f"{g['name']}/1/{p}/{f['path']}" for p in g["item"]["persons"]
                       for f in schema["persona"]["fields"] if not f.get("hidden")]
        for path in wanted:
            dsl = paths._resolve(rec.func, path).dsl  # pyright: ignore[reportPrivateUsage]
            assert path_of(rec.func, dsl) == path, (kind, path, dsl)
            seen += 1
    assert seen > 200


def _refused(text: str, ordinal: int, ops: list[dict[str, Any]]) -> PathError:
    rec = _record(text, ordinal)
    with pytest.raises(PathError) as caught:
        translate(rec.func, ops, call=rec.call)
    return caught.value


def test_a_wrong_type_is_refused():
    e = _refused(BIRTHS, 0, [{"op": "set", "path": "birth.day", "value": "пятое"}])
    assert (e.key, e.params) == ("paths.type", {"path": "birth.day", "expected": "integer"})
    e = _refused(BIRTHS, 0, [{"op": "set", "path": "birth.month", "value": "brumaire"}])
    assert (e.key, e.params["expected"]) == ("paths.type", "enum")
    e = _refused(BIRTHS, 0, [{"op": "set", "path": "father/status", "value": "крестьянинъ"}])
    assert (e.key, e.params["expected"]) == ("paths.type", "catalog")
    e = _refused(BIRTHS, 1, [{"op": "set", "path": "relatives/2/relationship", "value": "brother"}])
    assert e.key == "paths.type"


def test_an_unknown_path_and_position_are_refused():
    assert _refused(BIRTHS, 0, [{"op": "set", "path": "b_day", "value": 2}]).key == "paths.unknown"
    assert _refused(BIRTHS, 0, [{"op": "set", "path": "godparent/9/given.original", "value": "x"}]).key == "paths.unknown"
    assert _refused(BIRTHS, 0, [{"op": "set", "path": "reviewed", "value": True}]).key == "paths.unknown"
    e = _refused(CENSUS, 0, [{"op": "remove", "path": "members/4"}])
    assert (e.key, e.params) == ("paths.position", {"path": "members/4", "size": 3})
    assert _refused(BIRTHS, 0, [{"op": "add", "path": "godparent/1", "value": {}}]).key == "paths.slot_taken"
    assert _refused(BIRTHS, 0, [{"op": "move", "path": "birth.day", "to": 1}]).key == "paths.not_a_group"
    assert _refused(BIRTHS, 0, [{"op": "set", "path": "godparent/1", "value": {}}]).key == "paths.not_a_value"
    assert _refused(BIRTHS, 0, [{"op": "rename", "path": "birth.day"}]).key == "paths.op"


def test_an_op_on_an_opaque_path_is_refused():
    assert _refused(DEATHS, 1, [{"op": "set", "path": "age", "value": 4}]).key == "paths.opaque"
    assert _refused(DEATHS, 1, [{"op": "unset", "path": "comment"}]).key == "paths.opaque"
    e = _refused(CENSUS, 1, [{"op": "add", "path": "members", "value": {"number": 2}}])
    assert (e.key, e.params) == ("paths.opaque", {"path": "members"})
    assert paths.opaque("death", _record(DEATHS, 1).call) == ["age", "comment"]
    assert paths.opaque("household", _record(CENSUS, 1).call) == ["members"]
    assert paths.opaque("birth", _record(BIRTHS, 1).call) == []


# The phrases `source` said before its refusals took keys, frozen: `str()` under ru says them still.
PHRASES: list[tuple[str, dict[str, object], str]] = [
    ("source.unknown_value_kind", {"kind": "blob"}, "неизвестный вид значения 'blob'"),
    ("source.no_parameter", {"func": "birth", "param": "b_dya"}, "birth() has no parameter 'b_dya'"),
    ("source.cannot_create", {"func": "page"}, "нельзя создать вызов page()"),
    ("source.no_parameters", {"func": "member", "params": "['x']"}, "member() has no parameter(s) ['x']"),
    ("source.splat", {}, "распакованный список (*…) правится только в редакторе"),
    ("source.unknown_op", {"op": "rename"}, "неизвестная операция 'rename'"),
    ("source.no_member", {"func": "household", "head": "@7"}, "в household() нет члена @7"),
    ("source.no_place", {"func": "household", "to": 7}, "в household() нет места @7"),
    ("source.member_comment", {}, "комментарий в конце строки члена — переставьте в редакторе"),
    ("source.not_a_list", {"param": "relatives"}, "relatives= здесь не список — он правится только как выражение"),
    ("source.no_element", {"param": "relatives", "key": "#3"}, "в relatives= нет элемента #3"),
    ("source.gone", {"ordinal": 7}, "в файле нет записи #7"),
    ("source.stale", {}, "запись изменилась на диске с момента загрузки"),
    ("source.listed_needs_review", {}, "запись уже на Geni и не вычитана: правка проходит только вместе с "
                                       "«Вычитано» — иначе храповик её задержит, и план удалит её профили с Geni"),
    ("source.unknown_where_new", {"where": "aside"}, "неизвестное место новой записи 'aside'"),
    ("source.new_only_in_a_metric_book", {}, "новую запись можно добавить только в метрическую книгу"),
    ("source.not_in_its_group_new", {}, "запись стоит не прямо в своей группе — новую рядом с ней пишут в редакторе"),
    ("source.new_not_a_call", {"func": "birth"}, "начало новой записи — не вызов birth()"),
    ("source.new_no_number", {}, "у новой записи нет номера"),
    ("source.unknown_where", {"where": "aside"}, "неизвестное место 'aside'"),
    ("source.already_here", {}, "запись уже здесь"),
    ("source.listed_move", {}, "запись уже на Geni и не вычитана: сначала «Вычитано», потом на место — "
                               "иначе храповик её задержит, и план удалит её профили с Geni"),
    ("source.not_in_its_group_move", {}, "запись стоит не прямо в своей группе — переносят в редакторе"),
    ("source.not_in_its_group_remove", {}, "запись стоит не прямо в своей группе — убирают в редакторе"),
    ("source.unknown_constant", {"code": "NOBODY"}, "неизвестная константа 'NOBODY': её нет в файле и в каталоге"),
    ("source.looks_like_a_constant", {"code": "NOBODY"}, "«NOBODY» — похоже на имя константы, но её нет ни в файле, ни в каталоге"),
    ("source.not_python", {"value": "{'kind': 'raw'}", "error": "KeyError('code')"},
     "не выражение Python: {'kind': 'raw'} (KeyError('code'))"),
    ("source.not_a_number", {"value": "x"}, "не число: 'x'"),
    ("source.no_call", {"func": "birth", "head": "child"}, "в birth() нет вызова 'child'"),
    ("source.household_end_only_adds", {}, "в конец двора можно только добавить"),
    ("source.by_its_fields", {"head": "@2"}, "@2 правится по полям, а не целиком"),
    ("source.list_end_only_adds", {"param": "relatives"}, "в конец relatives= можно только добавить"),
    ("source.not_an_element_number", {"key": "#x"}, "не номер элемента: '#x'"),
    ("source.element_not_a_call", {"param": "relatives", "key": "#0"}, "relatives=#0 — не вызов"),
    ("source.empty_path", {}, "пустой путь правки"),
    ("source.reviewed_already", {}, "запись уже вычитана"),
    ("source.not_a_constant_name", {"code": "a-b"}, "'a-b' — не имя константы"),
    ("source.dsl_v0", {}, "DSL v0: verso upgrade-dsl <файл>"),
]


def test_edit_errors_have_keys(monkeypatch: pytest.MonkeyPatch):
    """Every refusal of `source` passes a key of the catalog (AST), and says in Russian what it said."""
    from verso.core import i18n
    from verso.ru.messages import t

    tree = ast.parse(Path(source.__file__).read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name) and node.exc.func.id in ("EditError", "Stale")):
            (arg,) = node.exc.args
            assert isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "t", node.lineno
            first = arg.args[0]
            assert isinstance(first, ast.Constant) and isinstance(first.value, str), node.lineno
            keys.add(first.value)
    assert keys == {key for key, _, _ in PHRASES}
    monkeypatch.setenv("VERSO_LANG", "ru")
    for key, params, phrase in PHRASES:
        assert str(source.EditError(t(key, **params))) == phrase, key
    assert set(i18n.catalog("verso.ru", "en")) >= keys
    e = source.Stale(t("source.gone", ordinal=3))
    assert (e.package, e.key, e.params) == ("verso.ru", "source.gone", {"ordinal": 3})
    assert source.EditError("свой текст").key is None and str(source.EditError("свой текст")) == "свой текст"


def test_a_refusal_takes_any_catalog_s_message():
    """An App raises `EditError` with a message of its own copy of the mechanism: its key still shows."""
    from dataclasses import dataclass, field

    @dataclass(frozen=True)
    class Other:
        package: str
        key: str
        params: dict[str, object] = field(default_factory=dict)

        def __str__(self) -> str:
            return "text"

    e = source.EditError(Other("verso.app_dsl", "bookdefaults.gone", {"n": 1}))  # type: ignore[arg-type]
    assert (e.package, e.key, e.params, str(e)) == ("verso.app_dsl", "bookdefaults.gone", {"n": 1}, "text")


def test_field_of_names_a_field_s_schema():
    """What the page types a path's value by: the field's schema at a path — none for a slot, a
    group or an item, a PathError for a path of nothing."""
    types = {p: (paths.field_of("birth", p) or {}).get("type") for p in ("birth.day", "father/status", "gender")}
    assert types == {"birth.day": "integer", "father/status": "catalog", "gender": "enum"}
    assert paths.field_of("birth", "godparent/2") is None
    with pytest.raises(paths.PathError):
        paths.field_of("birth", "nobody/here")


# The last relative written with a trailing comma, a note in that comma's line: the note is hers.
NOTED_LAST = BIRTHS.replace('''relative(person("Аѳанасій"), Relationship.SON, "мать")]),''',
                            '''relative(person("Аѳанасій"), Relationship.SON, "мать"),  # the last, noted
                                  ]),''')


def test_a_move_never_hands_the_last_relatives_note_to_another():
    """A move keeps every separator in place, so the note in the last element's comma would end beside
    whoever comes last: the move is refused, as a member's is."""
    assert "# the last, noted" in NOTED_LAST
    with pytest.raises(source.EditError) as refused:
        _v2(NOTED_LAST, 1, [{"op": "move", "path": "relatives/3", "to": 1}])
    assert refused.value.key == "source.member_comment"


def test_a_relative_added_after_a_noted_one_leaves_the_note_where_it_was():
    added = _v2(NOTED_LAST, 1, [{"op": "add", "path": "relatives",
                                 "value": {"person/given.original": "Новый", "relationship": "son"}}])
    line = next(ln for ln in added.splitlines() if "# the last, noted" in ln)
    assert 'person("Аѳанасій")' in line
    assert "Новый" not in line
    assert 'person("Новый")' in added
    source.find_records(added)  # it still parses


def test_a_relative_added_copies_no_one_s_note():
    """The new element's separator is the list's own, not the comment line that stands in it: a note
    over one relative is written once."""
    for text in (BIRTHS, NOTED_LAST):
        added = _v2(text, 1, [{"op": "add", "path": "relatives",
                               "value": {"person/given.original": "Новый", "relationship": "son"}}])
        assert added.count("# her mother's brother") == 1


def test_the_schema_is_the_current_vocabulary_s(monkeypatch: pytest.MonkeyPatch):
    """The paths ask the schema of the workspace's vocabulary each time — never the first one a process
    met: a second workspace with another plugin reads its own."""
    from types import SimpleNamespace

    from verso.core.records import fields
    assert "birth" in paths._ui()["kinds"]
    monkeypatch.setattr(fields, "vocabulary", lambda: SimpleNamespace(schema_package="tests.core"))
    assert list(paths._ui()["kinds"]) == ["note"]


def test_two_calls_apart_in_their_splat_are_not_equal():
    """`splat` is no field (the card's `asdict` stays as it was), but two calls that differ in it differ."""
    plain, unpacked = source.CallView("birth", []), source.CallView("birth", [])
    unpacked.splat = True
    assert plain != unpacked
    assert plain == source.CallView("birth", [])


# The same book with its surnames named, as many of a corpus's files write them.
NAMED_SURNAMES = BIRTHS.replace('person("Кузьма", "Лукинъ", "Пересыпкинъ")',
                                'person("Кузьма", "Лукинъ", last_name_orig="Пересыпкинъ")') \
    .replace('person("Лука", "Ильинъ", "Пересыпкинъ")', 'person("Лука", "Ильинъ", last_name_orig="Пересыпкинъ")') \
    .replace('person("Савва", "Ѳомичъ", "Перекатовъ")', 'person("Савва", "Ѳомичъ", last_name_orig="Перекатовъ")')


def _surname(text: str) -> str:
    return _v1(text, 0, [{"op": "set", "path": ["mother", "last_name_orig"], "value": _s("Пересыпкина")}])


def test_a_surname_added_is_written_as_the_file_writes_surnames():
    """2026-10-26: a surname added to `person("Ѳекла", "Петрова")` took the next positional place in a file
    whose every other surname is named — and named, in a file that names them."""
    assert 'mother=person("Ѳекла", "Петрова", last_name_orig="Пересыпкина", status=PEASANT_WIFE)' \
        in _surname(NAMED_SURNAMES)
    assert 'mother=person("Ѳекла", "Петрова", "Пересыпкина", status=PEASANT_WIFE)' in _surname(BIRTHS)


def test_a_person_added_names_its_surname_as_the_file_does():
    value = {"person/given.original": "Новый", "person/patronymic.original": "Саввинъ",
             "person/surname.original": "Перекатовъ", "relationship": "son"}
    named = _v2(NAMED_SURNAMES, 1, [{"op": "add", "path": "relatives", "value": value}])
    assert 'person("Новый", "Саввинъ", last_name_orig="Перекатовъ")' in named
    positional = _v2(BIRTHS, 1, [{"op": "add", "path": "relatives", "value": value}])
    assert 'person("Новый", "Саввинъ", "Перекатовъ")' in positional
