"""Codemod: delete ROV001 dead `override` fields from a village config.

Removing a no-op override is output-neutral by definition, so this rewrite is
verified mechanically rather than reviewed per cluster: regenerate afterwards
and assert the generated `.tf` tree is byte-identical.

Edits by AST LINE NUMBERS, not byte offsets. These configs are predominantly
Cyrillic, and line-based editing sidesteps the whole class of UTF-8 offset
bugs. Of 289 `override` calls in Горюхино, 285 put one kwarg per line; the
4 single-line calls are refused and reported for manual editing rather than
risked.

Scope is the `profiles_to_consolidate` assignment ONLY. `unions_to_consolidate`
carries its own `override` hint with different semantics, and a key name can
collide between the two.
"""
import argparse
import ast
import sys
from pathlib import Path

#: The only top-level assignment this codemod is allowed to rewrite.
TARGET_ASSIGNMENT = "profiles_to_consolidate"


def _profiles_dict(tree: ast.Module) -> ast.Dict | None:
    """The `profiles_to_consolidate = {...}` literal, or None."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Name)
                    and target.id == TARGET_ASSIGNMENT
                    and isinstance(node.value, ast.Dict)):
                return node.value
    return None


def _override_calls(tree: ast.Module) -> dict[str, ast.Call]:
    """Map canonical key -> its `override` GeniProfile call node.

    Walks only `profiles_to_consolidate`'s own entries, never the whole
    module, so a same-named `unions_to_consolidate` entry is out of reach.
    """
    found: dict[str, ast.Call] = {}
    profiles = _profiles_dict(tree)
    if profiles is None:
        return found
    # `keys`/`values` are always parallel; a `**unpack` entry yields a None
    # key, which the isinstance guard below filters out.
    for key, value in zip(profiles.keys, profiles.values, strict=True):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)
                and isinstance(value, ast.Dict)):
            continue
        for inner_key, inner_value in zip(value.keys, value.values,
                                          strict=True):
            if (isinstance(inner_key, ast.Constant)
                    and inner_key.value == "override"
                    and isinstance(inner_value, ast.Call)):
                found[key.value] = inner_value
    return found


def strip_dead_overrides(
        source: str, dead: dict[str, set[str]]) -> tuple[str, list[str]]:
    """Return `(rewritten_source, skipped)`.

    `dead` maps canonical key -> the override field names to delete. Lines are
    collected first and deleted in one pass so earlier deletions cannot shift
    later line numbers.
    """
    tree = ast.parse(source)
    calls = _override_calls(tree)
    lines = source.splitlines(keepends=True)
    drop: set[int] = set()          # 0-based line indices
    skipped: list[str] = []

    for canonical, fields in dead.items():
        call = calls.get(canonical)
        if call is None:
            continue
        if call.lineno == call.end_lineno:
            skipped.append(
                f"{canonical}: single-line `override` call at line "
                f"{call.lineno} — edit by hand")
            continue
        targeted = [kw for kw in call.keywords if kw.arg in fields]
        if not targeted:
            continue
        for kw in targeted:
            # `end_lineno` is Optional on ast nodes but always set for parsed
            # source; fall back to the start line for a single-line kwarg.
            drop.update(range(kw.lineno - 1, kw.end_lineno or kw.lineno))
        # Whole call empties -> drop the `"override": GeniProfile(` header,
        # the closing `),` and any lines the kwargs did not already cover.
        if len(targeted) == len(call.keywords):
            entry_start = _override_entry_lineno(lines, call.lineno)
            drop.update(
                range(entry_start - 1, call.end_lineno or call.lineno))

    if not drop:
        return source, skipped
    kept = [line for i, line in enumerate(lines) if i not in drop]
    return "".join(kept), skipped


def _override_entry_lineno(lines: list[str], call_lineno: int) -> int:
    """1-based line of the `"override":` key introducing the call.

    The call node starts at `GeniProfile(`, which sits on the same line as the
    key in this codebase's formatting; walk back only if it does not.
    """
    index = call_lineno - 1
    while index >= 0 and '"override"' not in lines[index]:
        index -= 1
    return index + 1 if index >= 0 else call_lineno


def _dead_fields_for_village(village: str) -> dict[str, set[str]]:
    from verso.ru.pipeline.translate import translate_village
    gen, _ = translate_village(village, strict=False)
    dead: dict[str, set[str]] = {}
    for finding in gen.redundant_overrides:
        dead.setdefault(finding.canonical, set()).add(finding.field)
    return dead


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delete ROV001 dead override fields from a village config.")
    parser.add_argument("--village", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    config_path = Path(args.village) / "generate_config_names.py"
    if not config_path.exists():
        print(f"no config at {config_path}", file=sys.stderr)
        return 2

    dead = _dead_fields_for_village(args.village)
    total = sum(len(v) for v in dead.values())
    if not total:
        print(f"{args.village}: no dead override fields")
        return 0

    source = config_path.read_text()
    rewritten, skipped = strip_dead_overrides(source, dead)

    for line in skipped:
        print(f"  skipped: {line}", file=sys.stderr)
    print(f"{args.village}: {total} dead override field(s) across "
          f"{len(dead)} cluster(s); {len(skipped)} skipped")
    if args.dry_run:
        return 0
    config_path.write_text(rewritten)
    print(f"rewrote {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
