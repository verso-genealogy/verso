#!/usr/bin/env python3
"""Static linter for a village's ``familio_kin.py`` KIN registry.

Consolidation folds per-record ``geni_profile`` stubs into canonical
res_names (recorded in ``generate_config_names.py``'s ``profile_move_list``).
When that happens, any ``familio_kin.py`` KIN key that named a *folded* stub
becomes stale — ``verso.ru.familio.projection.project_kin`` then raises
``KinResolutionError`` at ``tf-familio-generate`` time (which needs a full
translate). This linter shifts that check left: it parses both files with
``ast`` (never imports them) and flags every KIN key that is a folded stub,
suggesting its canonical target.

FKN001: a KIN key equals a ``profile_move_list`` *source* key (a folded
per-record stub) — replace it with the canonical it maps to.

Exit status: 1 if any error-severity finding is reported, else 0.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict
from pathlib import Path
from collections.abc import Iterable

from verso.ru.consolidation.lint_config import Finding, _const_str

KIN_VAR = "KIN"
MOVE_LIST_VAR = "profile_move_list"


def _find_dict(tree: ast.Module, var_name: str) -> ast.Dict | None:
    """Return the dict literal assigned to *var_name* (plain or annotated)."""
    for node in tree.body:
        target = None
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            target = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        if target == var_name and isinstance(getattr(node, "value", None), ast.Dict):
            return node.value  # type: ignore[union-attr]
    return None


def _move_list_map(gcn_path: Path) -> dict[str, str]:
    """Parse ``profile_move_list`` from a generate_config_names.py into a
    ``{source_stub: canonical}`` map. Empty if the file or var is absent."""
    if not gcn_path.exists():
        return {}
    tree = ast.parse(gcn_path.read_text(encoding="utf-8"), filename=str(gcn_path))
    node = _find_dict(tree, MOVE_LIST_VAR)
    if node is None:
        return {}
    out: dict[str, str] = {}
    for k, v in zip(node.keys, node.values, strict=False):
        if k is None:  # dict `**spread` has a None key
            continue
        ks, vs = _const_str(k), _const_str(v)
        if ks is not None and vs is not None:
            out[ks] = vs
    return out


def lint_file(kin_path: str | Path, gcn_path: str | Path | None = None) -> list[Finding]:
    kin_path = Path(kin_path)
    if gcn_path is None:
        gcn_path = kin_path.parent / "generate_config_names.py"
    gcn_path = Path(gcn_path)

    src = kin_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(kin_path))
    kin = _find_dict(tree, KIN_VAR)
    if kin is None:
        return [Finding(
            code="FKN000", severity="error", path=str(kin_path), line=1, col=0,
            message=f"could not find top-level `{KIN_VAR} = {{...}}` assignment",
        )]

    folded = _move_list_map(gcn_path)  # source_stub -> canonical
    findings: list[Finding] = []
    for key_node in kin.keys:
        if key_node is None:  # dict `**spread` has a None key
            continue
        name = _const_str(key_node)
        if name is None:
            continue
        canonical = folded.get(name)
        if canonical is not None:
            findings.append(Finding(
                code="FKN001", severity="error", path=str(kin_path),
                line=key_node.lineno, col=key_node.col_offset,
                message=(
                    f"KIN key {name!r} is a folded per-record stub "
                    f"(consolidated into {canonical!r}); replace it with the "
                    f"canonical key {canonical!r}"
                ),
            ))
    return findings


def _format(findings: Iterable[Finding], *, as_json: bool) -> str:
    if as_json:
        return json.dumps({"findings": [asdict(f) for f in findings]}, ensure_ascii=False, indent=2)
    return "\n".join(f.format_text() for f in findings)


def main(argv: list[str]) -> int:
    args = list(argv)
    as_json = "--json" in args
    if as_json:
        args.remove("--json")

    if len(args) == 1:
        target = Path.cwd() / "familio_kin.py"
    elif len(args) == 2:
        target = Path(args[1])
    else:
        print("usage: verso lint-kin [--json] [PATH]", file=sys.stderr)
        return 2

    findings = lint_file(target)
    out = _format(findings, as_json=as_json)
    if out:
        print(out)
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
