"""The linters' findings as structures: every finding has a code, and its text is
rendered from the catalog byte for byte as the linters wrote it before.

`tests/data/linter_samples/` holds every DSL file the library's tests handed a check
(tools/i18n/linter_samples.py harvested them before the move; `.py.sample`, so that no tool reads
them as code: each is linted as a copy under its own name), and `linter_messages_before.json`
what the old code said on each, in both modes: the JSON the IDEs read and the text CI prints.
`VERSO_LINTER_SNAPSHOT=write` writes that file — once, from the old code."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from verso.ru.linters.dsllint import LINTERS, check_file_json

DATA = Path(__file__).resolve().parent / "data"
SAMPLES = DATA / "linter_samples"
BEFORE = DATA / "linter_messages_before.json"


def _samples() -> list[Path]:
    return sorted(p.with_suffix("") for p in SAMPLES.rglob("*.py.sample") if p.is_file())


def _rel(path: Path) -> str:
    return path.relative_to(SAMPLES).as_posix()


def _copy(rel: str, into: Path) -> Path:
    """The sample `rel` as a `.py` of its own name under `into`."""
    target = into / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SAMPLES / f"{rel}.sample", target)
    return target


def said(sample: Path) -> dict[str, Any]:
    """What every linter says on the sample: the JSON issues by linter and the text lines by linter,
    the path written `<file>`."""
    with tempfile.TemporaryDirectory(prefix="verso-sample-") as tmp:
        return _said(_copy(_rel(sample), Path(tmp)))


def _said(path: Path) -> dict[str, Any]:
    where = str(path)
    issues = {r["linter"]: [{k: v.replace(where, "<file>") if k == "message" else v for k, v in i.items()}
                            for i in r["issues"]] for r in check_file_json(path)}
    text = {lt.name: [line.replace(where, "<file>") for line in lt.plain(path)] for lt in LINTERS}
    order = {k: [list(i) for i in v] for k, v in issues.items() if v}      # the JSON's key order, as printed
    return {"json": {k: v for k, v in issues.items() if v}, "text": {k: v for k, v in text.items() if v},
            "order": order}


def _write() -> None:
    out: dict[str, Any] = {}
    for path in _samples():
        found = said(path)
        if found["json"] or found["text"]:
            out[_rel(path)] = found
        else:                                  # a sample nothing fires on says nothing of the texts
            path.with_name(path.name + ".sample").unlink()
    for directory in sorted((p for p in SAMPLES.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(directory.iterdir()):
            directory.rmdir()
    BEFORE.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if os.environ.get("VERSO_LINTER_SNAPSHOT") == "write":
    _write()


def _before() -> dict[str, Any]:
    return json.loads(BEFORE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("rel", sorted(_before()) if BEFORE.exists() else [])
def test_message_is_todays_text(rel: str):
    """Each finding of each sample, in both modes, as the old code wrote it — the keys it had."""
    before = _before()[rel]
    now = said(SAMPLES / rel)
    assert now["text"] == before["text"]
    assert {k: [{key: i.get(key) for key in b} for i, b in zip(now["json"].get(k, []), v, strict=False)]
            for k, v in before["json"].items()} == before["json"]
    assert {k: len(v) for k, v in now["json"].items()} == {k: len(v) for k, v in before["json"].items()}
    assert {k: [[key for key in i if key in b] for i, b in zip(v, before["json"][k], strict=False)]
            for k, v in now["order"].items()} == before["order"]


def _issues(rel: str) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="verso-sample-") as tmp:
        return [i for r in check_file_json(_copy(rel, Path(tmp))) for i in r["issues"]]


def test_every_finding_has_a_code():
    """Each finding of every sample carries its code — no linter answers in text alone."""
    from verso.ru.linters.codes import COMMON_CODES, LINTER_CODES
    known = {*COMMON_CODES, *(c for codes in LINTER_CODES.values() for c in codes)}
    missing = [(rel, i["message"]) for rel in sorted(_before()) for i in _issues(rel)
               if getattr(i["message"], "code", "") not in known]
    assert missing == []


def test_params_hold_no_rendered_text():
    """A finding's params are what the DSL wrote, codes and numbers — never text a language
    renders (a part said in words is a nested message, its key and params): so every finding of
    every sample has the same code, params and token in English as in Russian."""
    from verso.core import i18n

    def structures() -> list[str]:
        out = [(rel, getattr(i["message"], "code", ""), getattr(i["message"], "params", {}),
                getattr(i["message"], "token", None)) for rel in sorted(_before()) for i in _issues(rel)]
        # A sample is linted as a copy in a temporary directory of its own: its path is no param's.
        return [re.sub(r"[^\"]*verso-sample-[^/]+/", "", json.dumps(o, ensure_ascii=False)) for o in out]
    with i18n.use("ru"):
        ru = structures()
    with i18n.use("en"):
        en = structures()
    assert en == ru


def test_prefix_styles_reproduce_the_bytes():
    from verso.ru.linters.issue import prefixed
    assert prefixed("ESC001", "x") == "ESC001 x"
    assert prefixed("MST001", "x") == "MST001 x" and prefixed("PM002", "x") == "PM002 x"
    assert prefixed("CRD003", "x") == "x" and prefixed("SLC001", "x") == "x" and prefixed("SYN001", "x") == "x"
    assert prefixed("CPL002", "x") == "[CPL002] x"


def test_a_finding_keeps_its_structure_in_the_findings_api(tmp_path):
    from verso.ru.linters.findings import lint_text
    sample = next(rel for rel in sorted(_before()) if "status_redundancy" in _before()[rel]["json"])
    found = [f for f in lint_text((SAMPLES / f"{sample}.sample").read_text(encoding="utf-8"), SAMPLES / sample)
             if f.linter == "status_redundancy"]
    assert found and all(f.code == "VSR001" and f.variant == "redundant" and "status" in f.params for f in found)
