"""docs/writing-records.md is a guide a reader copies from: every example in it lints with no error and
builds, as its own section «When a file is done» asks of a file."""
from __future__ import annotations

import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
GUIDE = ROOT / "docs" / "writing-records.md"
_BLOCK = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _examples() -> list[str]:
    return _BLOCK.findall(GUIDE.read_text(encoding="utf-8"))


def test_the_guide_has_examples():
    assert len(_examples()) >= 2


@pytest.mark.parametrize("n", range(len(_examples())))
def test_an_example_lints_with_no_error_and_builds(n: int, tmp_path: Path):
    from verso.ru.linters.dsllint import check_file_json

    path = tmp_path / f"example_{n}.py"
    path.write_text(_examples()[n], encoding="utf-8")
    errors = [issue for linter in check_file_json(path) for issue in linter["issues"] if issue.get("level") == "error"]
    assert errors == []
    built = runpy.run_path(str(path))
    assert any(name.startswith("stepanchikovo_") for name in built)


def test_the_two_examples_are_the_translations_examples():
    russian = GUIDE.with_name("writing-records.ru.md").read_text(encoding="utf-8")
    assert _BLOCK.findall(russian) == _examples()


def test_the_field_table_names_the_calls_that_take_each_field():
    """«What the source contradicts» says on which call each field goes: a field on the wrong call does not build."""
    import json

    api = json.loads((ROOT / "packages" / "verso-ru" / "src" / "verso" / "ru" / "dsl" / "api-v1.json").read_text(encoding="utf-8"))
    takes = {name: {p[0] for p in entry["params"]} for name, entry in api["modules"]["verso.ru.dsl"].items()
             if entry["kind"] == "function"}
    rows = re.findall(r"^\| `(\w+)=` \| ([^|]+) \|", GUIDE.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(rows) >= 8
    for field, calls in rows:
        named = set(re.findall(r"`(\w+)\(\)`", calls))
        assert named == {call for call, params in takes.items() if field in params}, field
