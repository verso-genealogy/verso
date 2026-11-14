"""The DSL v1 surface is written down (api-v1.json) and may only grow."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from verso.ru.dsl import surface


def _fn(*params: tuple[str, str, str | None]) -> dict[str, object]:
    return {"kind": "function", "params": [list(p) for p in params]}


OLD = {"api": 1, "modules": {
    "verso.ru.dsl": {
        "birth": _fn(("number", "POSITIONAL_OR_KEYWORD", None), ("gender", "POSITIONAL_OR_KEYWORD", None),
                     ("k_year", "KEYWORD_ONLY", "None")),
        "Month": {"kind": "enum", "members": {"JANUARY": "1", "FEBRUARY": "2"}},
    },
    "verso.ru.dsl.statuses": {"WIDOW": {"kind": "constant", "value": "вдова", "gender": "FEMALE"}},
}}


def _new() -> dict[str, Any]:
    return copy.deepcopy(OLD)


def test_the_surface_is_written():
    assert surface.surface() == json.loads(surface.API_FILE.read_text(encoding="utf-8"))
    assert surface.API_FILE.name == "api-v1.json"


def test_the_surface_names_the_facade_and_its_catalogs():
    modules = surface.surface()["modules"]
    assert set(modules) == {"verso.ru.dsl", "verso.ru.dsl.statuses", "verso.ru.dsl.causes_of_death",
                            "verso.ru.dsl.marital_status"}
    assert modules["verso.ru.dsl"]["Month"]["kind"] == "enum"
    assert modules["verso.ru.dsl"]["birth"]["kind"] == "function"
    assert modules["verso.ru.dsl.statuses"]["WIDOW"] == {"kind": "constant", "value": "вдова", "gender": "FEMALE"}


def test_a_new_keyword_is_compatible():
    new = _new()
    new["modules"]["verso.ru.dsl"]["birth"]["params"].append(["note", "KEYWORD_ONLY", "None"])
    new["modules"]["verso.ru.dsl"]["christening"] = _fn()
    new["modules"]["verso.ru.dsl"]["Month"]["members"]["MARCH"] = "3"
    assert surface.incompatible(OLD, new) == []


def test_a_new_parameter_without_a_default_is_not():
    new = _new()
    new["modules"]["verso.ru.dsl"]["birth"]["params"].append(["note", "KEYWORD_ONLY", None])
    assert surface.incompatible(OLD, new) == ["verso.ru.dsl.birth: новый параметр note без умолчания"]


def test_a_removed_parameter_is_not():
    new = _new()
    del new["modules"]["verso.ru.dsl"]["birth"]["params"][2]
    assert surface.incompatible(OLD, new) == ["verso.ru.dsl.birth: нет параметра k_year"]


def test_a_removed_name_is_not():
    new = _new()
    del new["modules"]["verso.ru.dsl"]["Month"]["members"]["FEBRUARY"]
    del new["modules"]["verso.ru.dsl.statuses"]["WIDOW"]
    assert surface.incompatible(OLD, new) == ["verso.ru.dsl.Month.FEBRUARY: нет имени",
                                             "verso.ru.dsl.statuses.WIDOW: нет имени"]


def test_a_changed_default_is_not():
    new = _new()
    new["modules"]["verso.ru.dsl"]["birth"]["params"][2][2] = "0"
    assert surface.incompatible(OLD, new) == ["verso.ru.dsl.birth: умолчание k_year None → 0"]


def test_a_reordered_positional_is_not():
    new = _new()
    params = new["modules"]["verso.ru.dsl"]["birth"]["params"]
    params[0], params[1] = params[1], params[0]
    assert surface.incompatible(OLD, new) == ["verso.ru.dsl.birth: порядок позиционных"]


def test_a_changed_kind_is_not():
    new = _new()
    new["modules"]["verso.ru.dsl"]["Month"] = _fn()
    assert surface.incompatible(OLD, new) == ["verso.ru.dsl.Month: другой вид"]


def test_a_changed_constant_is_not():
    new = _new()
    new["modules"]["verso.ru.dsl.statuses"]["WIDOW"]["value"] = "вдовица"
    new["modules"]["verso.ru.dsl"]["Month"]["members"]["JANUARY"] = "13"
    assert surface.incompatible(OLD, new) == ["verso.ru.dsl.Month.JANUARY: значение «1» → «13»",
                                             "verso.ru.dsl.statuses.WIDOW: значение «вдова» → «вдовица»"]


def test_write_refuses_an_incompatible_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]):
    written = surface.surface()
    written["modules"]["verso.ru.dsl"]["gone"] = _fn()
    api = tmp_path / "api-v1.json"
    api.write_text(json.dumps(written, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(surface, "API_FILE", api)
    assert surface.main(["--write"]) == 1
    assert capsys.readouterr().out.strip() == ("несовместимое изменение DSL v1: verso.ru.dsl.gone: нет имени — "
                                               "это DSL v2 (DSL_API = 2, api-v2.json)")
    assert json.loads(api.read_text(encoding="utf-8")) == written      # not written


def test_check_says_how_to_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                 capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(surface, "API_FILE", tmp_path / "api-v1.json")
    assert surface.main(["--check"]) == 1
    assert capsys.readouterr().out.strip() == "поверхность DSL не записана: verso dsl-surface --write"
    assert surface.main(["--write"]) == 0
    assert surface.main(["--check"]) == 0


def test_surface_at_reads_a_commit_of_either_layout(tmp_path: Path):
    """`--base REV` reads the surface file wherever that commit kept it: verso/ru/dsl/ before
    0.1.0's run, lib/packages/verso-ru/src/verso/ru/dsl/ after it."""
    import subprocess

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    flat = tmp_path / "verso" / "ru" / "dsl" / "api-v1.json"
    flat.parent.mkdir(parents=True)
    flat.write_text('{"a": 1}', encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "flat")
    before = git("rev-parse", "HEAD")
    split = tmp_path / "lib" / "packages" / "verso-ru" / "src" / "verso" / "ru" / "dsl" / "api-v1.json"
    split.parent.mkdir(parents=True)
    git("mv", str(flat), str(split))
    split.write_text('{"a": 2}', encoding="utf-8")
    git("commit", "-qam", "split")
    assert surface._at(before, tmp_path) == {"a": 1}  # pyright: ignore[reportPrivateUsage]
    assert surface._at("HEAD", tmp_path) == {"a": 2}  # pyright: ignore[reportPrivateUsage]
    # From a subdirectory too: a base read relative to it would be «no surface», a silent pass.
    assert surface._at("HEAD", tmp_path / "lib") == {"a": 2}  # pyright: ignore[reportPrivateUsage]
    flat.parent.mkdir(parents=True, exist_ok=True)
    flat.write_text('{"a": 3}', encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "both")
    with pytest.raises(SystemExit, match="два файла поверхности"):
        surface._at("HEAD", tmp_path)  # pyright: ignore[reportPrivateUsage]
    (tmp_path / "x").write_text("", encoding="utf-8")
    git("rm", "-q", str(flat), str(split))
    git("add", "x")
    git("commit", "-qm", "none")
    assert surface._at("HEAD", tmp_path) is None  # pyright: ignore[reportPrivateUsage]
