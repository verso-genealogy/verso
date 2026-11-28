"""A household member's role may be left out: the same as `None`, in the objects, the records JSON and the replay."""
from __future__ import annotations

import json
from typing import Any

from verso.core.records.encode import encode_namespace
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import replay_file
from verso.ru.domain import person
from verso.ru.dsl.records.census import CensusRole, census_records, household, member


def _ns(*members: Any) -> dict[str, Any]:
    return {"census": census_records("ГАРО", "735", "265", "53", "Заманиловка", 1858,
                                     household("1", *members))}


def _encode(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="Заманиловка", file="1858/f.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _head() -> Any:
    return member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=40)


def _member2(ns: dict[str, Any]) -> Any:
    return ns["census"].households[0].members[1]


def test_a_member_without_a_role_is_the_one_with_none() -> None:
    left_out = _ns(_head(), member(2, person("Петръ"), age=10))
    written = _ns(_head(), member(2, person("Петръ"), None, age=10))
    assert _member2(left_out).role is None and _member2(written).role is None
    assert _member2(left_out).age == _member2(written).age == 10
    # The records JSON keeps what was written: an explicit None is a written null, a left-out role is no field.
    # The null is the only difference between the two.
    plain, nulled = json.dumps(_encode(left_out)), json.dumps(_encode(written))
    assert plain == nulled.replace('"number": 2, "role": null, ', '"number": 2, ')


def test_a_member_without_a_role_replays() -> None:
    for role_args in ((), (None,)):
        ns = _ns(_head(), member(2, person("Петръ"), *role_args, age=10), member(3, person("Марья"), hidden=True))
        back = replay_file(_encode(ns))
        assert first_difference(ns, back) is None
        assert _member2(back).role is None
