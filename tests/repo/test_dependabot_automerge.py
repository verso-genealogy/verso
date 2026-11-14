"""dependabot-automerge.yml merges a green Dependabot PR once a day — but never a bump of a dependency
whose bytes reach a corpus's output: dependabot.yml keeps those in PRs of their own so that a corpus
compares its output across each, and no CI here sees a corpus."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

GITHUB = Path(__file__).resolve().parent.parent.parent / ".github"


def _yaml(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _output_pins() -> set[str]:
    pip = [u for u in _yaml(GITHUB / "dependabot.yml")["updates"] if u["package-ecosystem"] == "pip"]
    return {name for u in pip for group in u.get("groups", {}).values()
            for name in group.get("exclude-patterns", [])}


def test_the_output_pins_are_left_for_the_corpus_check():
    job = _yaml(GITHUB / "workflows" / "dependabot-automerge.yml")["jobs"]["merge"]
    step = next(s for s in job["steps"] if "pulls?state=open" in str(s.get("run", "")))
    held = set(step["env"]["HELD_FOR_CORPUS_CHECK"].split())
    assert _output_pins() == {"python-dateutil", "openpyxl", "libcst"}
    assert held == _output_pins()
    assert 'for pin in $HELD_FOR_CORPUS_CHECK; do' in step["run"]
    assert '"$ref" == *"/$pin-"*' in step["run"]
