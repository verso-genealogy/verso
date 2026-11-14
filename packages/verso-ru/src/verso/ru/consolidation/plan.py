"""Terraform-plan artifact paths and loaders for village consolidation tooling.

Centralizes the locations of the plan artifacts (``export_command``: the saved ``.plan`` of the
village's module shown as JSON into the village's ``_plan.json``) so every tool reads the same files, resolved relative to a
village directory. Tools default the village dir to the current working directory
and accept a ``--village`` override (so they run from a village dir, or from the
repo root with ``--village <name>``).

Artifacts:
- ``plan_bin``  — binary plan from ``terraform plan -out`` (``terraform/.plan``)
- ``plan_text`` — ``terraform show .plan`` color-stripped (``_plan_full.txt``)
- ``plan_json`` — ``terraform show -json .plan`` (``_plan.json``)
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlanPaths:
    village_dir: Path

    @property
    def tf_dir(self) -> Path:
        return self.village_dir / "terraform" / "geni"

    @property
    def plan_bin(self) -> Path:
        return self.tf_dir / ".plan"

    @property
    def plan_text(self) -> Path:
        return self.village_dir / "_plan_full.txt"

    @property
    def plan_json(self) -> Path:
        return self.village_dir / "_plan.json"

    def load_json(self) -> dict[str, Any]:
        return json.loads(self.plan_json.read_text(encoding="utf-8"))

    def load_text(self) -> str:
        return self.plan_text.read_text(encoding="utf-8", errors="replace")


def plan_paths(village_dir: Path | str | None = None) -> PlanPaths:
    """Resolve plan artifact paths for ``village_dir`` (default: current dir)."""
    return PlanPaths(Path(village_dir).resolve() if village_dir else Path.cwd())


def _module(village: str | Path) -> str:
    return shlex.quote(str(Path(village) / "terraform" / "geni"))


def plan_command(village: str | Path, *, fast: bool = False) -> str:
    """The shell line that saves a plan of `village`'s module where the tools look for it (`.plan`, or
    `.plan-fast` without a refresh), runnable from the folder `village` is relative to."""
    if fast:
        return f"terraform -chdir={_module(village)} plan -refresh=false -out=.plan-fast"
    return f"terraform -chdir={_module(village)} plan -out=.plan"


def export_command(village: str | Path) -> str:
    """The shell line that shows `village`'s saved `.plan` as the `_plan.json` the tools read, runnable
    from the folder `village` is relative to (`.` from the village's own)."""
    return f"terraform -chdir={_module(village)} show -json .plan > {shlex.quote(str(Path(village) / '_plan.json'))}"
