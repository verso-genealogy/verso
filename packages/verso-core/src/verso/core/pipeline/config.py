"""A village's consolidation config — `generate_config_names.py` — read once, by one loader.

Until 0.1.0 seven places imported it, five of them by putting the village on `sys.path`
and importing `generate_config_names`: the module cache then answered every later
village of the process with the first one's config. `load_config` gives each file a
module of its own name, registers it nowhere and compiles it from the source, as
`verso.core.pipeline.load.load_module` does a DSL file.

`consolidation_state_blocks` and `ConsolidationBlock` moved here verbatim from
`verso.ru.cli.generate_tf`: the state-continuity blocks the config generates are read
by the generator and by the consolidation checks alike. What the config folds —
`make_consolidation`, the translator's `Consolidation` — is the plugin's since 0.1.0
(`verso.ru.pipeline.translate`).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

from verso.core.messages import t

CONFIG_FILE = "generate_config_names.py"


def load_config(path: Path) -> ModuleType:
    """The config at `path` as a module named after its village's directory, compiled
    from the source and registered nowhere: `sys.modules` and `sys.path` stay as they were."""
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(str(t("consolidation_config.missing", path=path)))
    spec = importlib.util.spec_from_file_location(f"generate_config_names__{resolved.parent.name}", str(resolved))
    if spec is None or spec.loader is None:
        raise ImportError(str(t("consolidation_config.not_py", path=path)))
    module = importlib.util.module_from_spec(spec)
    exec(compile(resolved.read_bytes(), str(resolved), "exec"), vars(module))
    return module


def village_config(village_dir: str | Path) -> ModuleType | None:
    """The village's config (`load_config`), None when it has none."""
    path = Path(village_dir) / CONFIG_FILE
    return load_config(path) if path.is_file() else None


class ConsolidationBlock(NamedTuple):
    """One state-continuity block `profiles_to_consolidate` generates.

    `frm` is the address the block acts on; `canonical` is the entry that
    emitted it. Both matter to `verso.ru.consolidation.stale_moved`, which asks
    whether any address an entry still names survives in terraform state.
    """

    kind: str        # "moved" | "removed"
    frm: str
    canonical: str


def consolidation_state_blocks(gcn) -> list[ConsolidationBlock]:
    """Every `moved` / `removed{destroy=false}` block the config generates, in
    emission order (per entry: the `moved` first, then its `removed`s).

    Split out of `build_moved_consolidated_profiles` so the staleness check
    reads the SAME derivation the generator does rather than re-deriving it —
    the `keeper` fallback and the `adopt_external` removed-only branch are
    exactly the parts that would drift.
    """
    blocks: list[ConsolidationBlock] = []
    for key, entry in getattr(gcn, "profiles_to_consolidate", {}).items():
        if not isinstance(entry, dict) or not entry.get("generate_moved_block"):
            continue
        names = entry.get("profile_names") or []
        if not names:
            continue
        if entry.get("adopt_external"):
            blocks.extend(ConsolidationBlock("removed", n, key) for n in names)
            continue
        keeper = entry.get("keeper") or names[0]
        blocks.append(ConsolidationBlock("moved", keeper, key))
        blocks.extend(ConsolidationBlock("removed", n, key) for n in names if n != keeper)
    return blocks
