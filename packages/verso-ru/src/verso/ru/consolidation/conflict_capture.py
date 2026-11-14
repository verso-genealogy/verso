#!/usr/bin/env python3
"""Inspect Geni merge data-conflicts and preserve external contributors' data.

After two Geni profiles are merged, Geni records a *data conflict* for every
field the two profiles disagreed on. Resolving it with the bare
`geni conflicts resolve` keeps the surviving (primary) profile's value for
every field, **silently discarding** anything the merged-in profile carried —
which is exactly the data an external contributor added from a source outside
this repo (a death date, a residence, an alternative name spelling).

Because the surviving/canonical profile is Terraform-managed, preserving that
value only on Geni is not durable: the next `terraform apply` overwrites it
back to the DSL value. So this tool does two complementary things:

  1. **Capture into the repo** — record the external value in
     `generate_config_names.py` as an `additional_info` note on the canonical,
     so Terraform writes it onto the profile (durable). Name-variant and
     event values also get a paste-ready structured suggestion
     (`preference.nicknames` / `override`) for an optional manual upgrade;
     it pins the survivor's name only where RPF001 would not call the pin
     dead (the village is translated to ask it).
  2. **Keep on Geni** — print (and with `--resolve`, run) the matching
     `geni conflicts resolve -prefer-nonempty` so the external value survives
     on Geni until the next apply converges.

Default output is a read-only report. `--write` appends the additional_info
notes; `--resolve` performs the Geni-side resolution. Pure helpers
(`translate_field`, `classify_field`, `build_captures`,
`ensure_additional_info_note`) are unit-tested in `tests/test_conflict_capture.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verso.ru.consolidation.detector import (
    _load_consolidate_config, find_key_block, find_matching_brace)
from verso.core.targets.geni.redundant_preferences import PinIsDead
from verso.core.tools import tool



# --------------------------------------------------------------------------- #
# Field taxonomy (pure)
# --------------------------------------------------------------------------- #

# Geni conflict-field id (last path component) → GeniProfile attribute. Name
# fields arrive as `names/<locale>/<part>`; everything else is a flat id.
_NAME_PART_TO_ATTR = {
    "first_name": "first_name",
    "middle_name": "middle_name",
    "last_name": "last_name",
    "maiden_name": "birth_last_name",
}
_FLAT_FIELD_TO_ATTR = {
    "birth_date": ("birth", "event"),
    "death_date": ("death", "event"),
    "baptism_date": ("baptism", "event"),
    "burial_date": ("burial", "event"),
    "current_residence": ("current_residence", "residence"),
    "about_me": ("about", "about"),
}


@dataclass(frozen=True)
class TranslatedField:
    attr: str | None   # GeniProfile attribute, or None when unmapped
    kind: str          # "name" | "event" | "residence" | "about" | "other"
    locale: str        # name locale ("ru"/"en-US"), else ""


def translate_field(geni_field: str) -> TranslatedField:
    """Map a Geni conflict field id to the repo's GeniProfile attribute."""
    if geni_field.startswith("names/"):
        parts = geni_field.split("/")
        locale = parts[1] if len(parts) >= 3 else ""
        attr = _NAME_PART_TO_ATTR.get(parts[-1])
        return TranslatedField(attr=attr, kind="name", locale=locale)
    if geni_field in _FLAT_FIELD_TO_ATTR:
        attr, kind = _FLAT_FIELD_TO_ATTR[geni_field]
        return TranslatedField(attr=attr, kind=kind, locale="")
    return TranslatedField(attr=None, kind="other", locale="")


def classify_field(primary: str, others: list[str]) -> tuple[str, str | None]:
    """Classify a field's data-loss risk and pick the value worth preserving.

    Returns (classification, external_value):
      - "external_added": survivor blank, a merged-in profile filled it in.
      - "disagreement":   both sides have a value and they differ.
      - "no_loss":        the others only echo the primary (or are empty).
    """
    distinct = [o for o in others if o and o != primary]
    if not distinct:
        return "no_loss", None
    if not primary:
        return "external_added", distinct[0]
    return "disagreement", distinct[0]


# --------------------------------------------------------------------------- #
# Capture model (pure)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Capture:
    """One field whose external value would be lost on a keep-primary resolve."""

    canonical: str
    guid: str
    manager: str
    geni_field: str
    attr: str | None
    kind: str
    classification: str   # "external_added" | "disagreement"
    primary: str
    external: str


def build_captures(detail: dict[str, Any], *, canonical: str, guid: str,
                   manager: str) -> list[Capture]:
    """Turn a parsed `geni conflicts show` payload into the data-loss captures
    for one profile. Skips no-loss fields and non-`ru` name locales (the en-US
    columns are transliterations, not independent data)."""
    captures: list[Capture] = []
    for f in detail.get("fields") or []:
        geni_field = f.get("field") or ""
        tf = translate_field(geni_field)
        if tf.kind == "name" and tf.locale not in ("ru", ""):
            continue  # keep the canonical Russian variant only
        classification, external = classify_field(
            f.get("primary_value") or "", f.get("other_values") or [])
        if classification == "no_loss" or external is None:
            continue
        captures.append(Capture(
            canonical=canonical, guid=guid, manager=manager,
            geni_field=geni_field, attr=tf.attr, kind=tf.kind,
            classification=classification,
            primary=f.get("primary_value") or "", external=external,
        ))
    return captures


def _escape(text: str) -> str:
    """Escape a value for embedding in a double-quoted Python string."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def additional_info_note(captures: list[Capture]) -> str:
    """Render the GeniProfile(about=...) note that preserves every external
    value for one canonical. This is the always-valid, append-only capture
    Terraform folds into the profile's About."""
    mgr = captures[0].manager or "внешний участник"  # i18n: content — written into the village's config
    parts = []
    for c in captures:
        label = c.attr or c.geni_field
        if c.primary:
            parts.append(f"{label}: {c.external} (выживший: {c.primary})")  # i18n: content — written into the village's config
        else:
            parts.append(f"{label}: {c.external}")
    body = "; ".join(parts)
    note = f"[слияние Geni] данные из профиля {mgr}, сохранённые при слиянии — {body}"  # i18n: content — written into the village's config
    return f'GeniProfile(about="{_escape(note)}")'


def structured_suggestion(canonical: str, captures: list[Capture], *,
                          pin_is_dead: PinIsDead | None = None) -> str:
    """Optional manual upgrade: pin name variants as `preference.nicknames`
    and surface event/residence values as an `override`. Returns "" when no
    structured upgrade applies.

    The survivor's name is pinned beside the nicknames only where
    `pin_is_dead` says RPF001 would not reject it: for a canonical we manage,
    Geni's survivor reads what our seeding record already says, and a pin of
    it writes nothing. Without `pin_is_dead` every survivor name is pinned."""
    name_caps = [c for c in captures if c.kind == "name"]
    struct_caps = [c for c in captures if c.kind in ("event", "residence", "about")]
    lines: list[str] = []
    if name_caps:
        pins: dict[str, str] = {}
        for c in name_caps:
            if (c.attr and c.primary and c.attr not in pins
                    and not (pin_is_dead
                             and pin_is_dead(canonical, c.attr, c.primary))):
                pins[c.attr] = c.primary
        parts = [f'{attr}="{_escape(value)}"' for attr, value in pins.items()]
        nicks = ", ".join(
            f'"{_escape(c.external)}"' for c in name_caps
        )
        parts.append(f"nicknames=[{nicks}]")
        lines.append(f'    "preference": GeniProfile({", ".join(parts)}),')
    for c in struct_caps:
        if c.kind == "event":
            lines.append(
                f'    # "override": GeniProfile({c.attr}=GeniEvent(...))  '
                f'# external {c.attr} = {c.external!r}')
        else:
            lines.append(
                f'    # "override": GeniProfile({c.attr}=...)  '
                f'# external = {c.external!r}')
    if not lines:
        return ""
    return f"  {canonical}:\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Config write (pure on text)
# --------------------------------------------------------------------------- #

def ensure_additional_info_note(content: str, canonical: str,
                                note: str) -> tuple[str, str]:
    """Append `note` (a GeniProfile(...) literal) to the canonical's
    `additional_info` list, creating the key if absent. Returns
    (new_content, status); status is one of:
      - "appended": added to an existing additional_info list
      - "created":  added a new additional_info key to the entry
      - "no-entry": canonical has no profiles_to_consolidate entry (skipped)
      - "duplicate": the exact note is already present (skipped)
    """
    m = re.search(r"profiles_to_consolidate\s*=\s*{", content)
    if not m:
        return content, "no-entry"
    brace_start = content.find("{", m.start())
    dict_end = find_matching_brace(content, brace_start)
    if brace_start == -1 or dict_end == -1:
        return content, "no-entry"
    dict_body = content[brace_start:dict_end + 1]

    block = find_key_block(content, dict_body, canonical, brace_start)
    if not block:
        return content, "no-entry"
    open_idx, close_idx = block
    block_text = content[open_idx:close_idx + 1]

    if note in block_text:
        return content, "duplicate"

    ai = re.search(r'"additional_info"\s*:\s*\[', block_text)
    if ai:
        # Insert before the list's closing ']'.
        list_open = open_idx + ai.end() - 1
        list_close = find_matching_brace_bracket(content, list_open)
        if list_close == -1:
            return content, "no-entry"
        indent = " " * 12
        insertion = f"{indent}{note},\n        "
        new_content = content[:list_close] + insertion + content[list_close:]
        return new_content, "appended"

    # No additional_info key — inject one right after the opening brace.
    insert_at = open_idx + 1
    block_indent = " " * 8
    insertion = (
        f'\n{block_indent}"additional_info": [\n'
        f'            {note},\n'
        f'{block_indent}],'
    )
    new_content = content[:insert_at] + insertion + content[insert_at:]
    return new_content, "created"


def find_matching_brace_bracket(s: str, start_pos: int) -> int:
    """Like detector.find_matching_brace but for `[` … `]`, string-aware."""
    i = start_pos
    n = len(s)
    depth = 0
    in_string: str | None = None
    escape = False
    while i < n:
        ch = s[i]
        if escape:
            escape = False
            i += 1
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# --------------------------------------------------------------------------- #
# Reporting (pure)
# --------------------------------------------------------------------------- #

def resolve_command(guid: str, has_external_added: bool, *, run: bool) -> str:
    """The `geni conflicts resolve` invocation that keeps Geni consistent with
    the capture: -prefer-nonempty when the survivor was missing data, plain
    keep-primary otherwise."""
    flag = " -prefer-nonempty" if has_external_added else ""
    yes = " -yes" if run else ""
    return f"geni conflicts resolve{flag}{yes} {guid}"


def format_report(captures: list[Capture], unmapped: list[dict[str, Any]], *,
                  pin_is_dead: PinIsDead | None = None) -> str:
    """Human-readable report grouped by canonical. `pin_is_dead` is handed to
    `structured_suggestion`."""
    if not captures and not unmapped:
        return "No Geni data-conflicts with at-risk external data found."
    by_canon: dict[str, list[Capture]] = {}
    for c in captures:
        by_canon.setdefault(c.canonical, []).append(c)

    lines = [
        f"Geni data-conflicts: {len(by_canon)} profile(s) carry external data "
        "that keep-primary would drop.",
        "",
    ]
    for canon, caps in sorted(by_canon.items()):
        guid = caps[0].guid
        mgr = caps[0].manager or "?"
        lines.append(f"━━ {canon}  (guid {guid}, manager {mgr})")
        for c in caps:
            tag = "external-added" if c.classification == "external_added" else "disagreement"
            kept = c.primary or "∅"
            lines.append(f"   • {c.geni_field} [{tag}]: keep {kept!r}, external {c.external!r}")
        lines.append("   capture (additional_info, --write applies this):")
        lines.append(f"       {additional_info_note(caps)}")
        sugg = structured_suggestion(canon, caps, pin_is_dead=pin_is_dead)
        if sugg:
            lines.append("   optional structured upgrade (paste manually):")
            lines.append(sugg)
        has_ext = any(c.classification == "external_added" for c in caps)
        lines.append("   keep on Geni: " + resolve_command(guid, has_ext, run=False))
        lines.append("")

    if unmapped:
        lines.append("⚠ Unmapped conflicts (could not map guid → canonical; resolve by hand):")
        for u in unmapped:
            lines.append(f"   - guid {u.get('profile_guid')}  {u.get('name', '')}  "
                         f"manager {u.get('manager_name', '')}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def _geni_json(args: list[str]) -> Any:
    env = {**os.environ, "GENI_WEB_CONSENT": "accepted"}
    res = subprocess.run([tool("geni"), *args], capture_output=True, text=True,
                         timeout=120, env=env)
    if res.returncode != 0:
        raise RuntimeError(f"geni {' '.join(args)} failed: {res.stderr.strip()}")
    return json.loads(res.stdout) if res.stdout.strip() else None


def fetch_conflicts(profile: str | None) -> list[dict[str, Any]]:
    """All pending data-conflicts, or just one when `profile` is given."""
    if profile:
        return [{"profile_guid": profile}]
    data = _geni_json(["conflicts", "list", "-all"])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("conflicts") or []
    return []


def fetch_detail(guid: str) -> dict[str, Any]:
    return _geni_json(["conflicts", "show", guid]) or {}


def guid_to_resource(tf_dir: Path) -> dict[str, str]:
    """{guid: resource_name} from `terraform state pull` — the canonical (or
    standalone) profile that holds each live Geni guid."""
    try:
        out = subprocess.run(
            [tool("terraform"), f"-chdir={tf_dir}", "state", "pull"],
            capture_output=True, text=True, timeout=180,
        )
        state = json.loads(out.stdout)
    except Exception:
        return {}
    idx: dict[str, str] = {}
    for res in state.get("resources", []):
        if res.get("type") != "geni_profile":
            continue
        for inst in res.get("instances", []):
            guid = inst.get("attributes", {}).get("guid")
            if guid:
                idx[str(guid)] = res["name"]
    return idx


def resource_to_canonical(profiles_to_consolidate: dict[str, Any]) -> dict[str, str]:
    """{folded_record_name: canonical_key}. A name absent here is its own
    canonical (a standalone, un-consolidated profile)."""
    out: dict[str, str] = {}
    for canon, entry in profiles_to_consolidate.items():
        for name in entry.get("profile_names", []) or []:
            out[name] = canon
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Geni merge conflicts and preserve external data.")
    parser.add_argument("--village", help="village dir (default: cwd)")
    parser.add_argument("--config", default="generate_config_names.py")
    parser.add_argument("--profile", help="inspect a single profile id/guid "
                        "instead of the whole pending list")
    parser.add_argument("--write", action="store_true",
                        help="append additional_info capture notes into the config")
    parser.add_argument("--resolve", action="store_true",
                        help="run `geni conflicts resolve` (destructive) to keep "
                        "Geni consistent with the capture")
    args = parser.parse_args()

    village = Path(args.village).resolve() if args.village else Path.cwd()
    tf_dir = village / "terraform" / "geni"
    config_path = args.config if os.path.isabs(args.config) else str(village / args.config)

    cfg = _load_consolidate_config(config_path)
    ptc = cfg.profiles_to_consolidate
    rec_to_canon = resource_to_canonical(ptc)
    g2r = guid_to_resource(tf_dir)

    captures: list[Capture] = []
    unmapped: list[dict[str, Any]] = []
    for conflict in fetch_conflicts(args.profile):
        guid = str(conflict.get("profile_guid") or "")
        if not guid:
            continue
        resource = g2r.get(guid)
        canonical = rec_to_canon.get(resource or "", resource) if resource else None
        if not canonical:
            unmapped.append(conflict)
            continue
        detail = fetch_detail(guid)
        if not detail.get("has_conflict"):
            continue
        captures.extend(build_captures(
            detail, canonical=canonical, guid=guid,
            manager=conflict.get("manager_name") or ""))

    print(format_report(captures, unmapped,
                        pin_is_dead=_rpf001_verdict(village, captures)))

    if args.write and captures:
        _apply_writes(config_path, captures)
    if args.resolve and captures:
        _apply_resolves(captures)
    return 0


def _rpf001_verdict(village: Path, captures: list[Capture]) -> PinIsDead | None:
    """RPF001's verdict over this village's seeds, so the structured
    suggestion prints no pin `verso generate-tf` would then reject. Translates
    the village, so only when a name capture will print a `preference`."""
    if not any(c.kind == "name" for c in captures):
        return None
    from verso.ru.pipeline.translate import translate_village
    gen, _ = translate_village(village)
    return gen.preference_pin_is_dead


def _apply_writes(config_path: str, captures: list[Capture]) -> None:
    by_canon: dict[str, list[Capture]] = {}
    for c in captures:
        by_canon.setdefault(c.canonical, []).append(c)
    content = Path(config_path).read_text(encoding="utf-8")
    statuses: dict[str, int] = {}
    for canon, caps in sorted(by_canon.items()):
        note = additional_info_note(caps)
        content, status = ensure_additional_info_note(content, canon, note)
        statuses[status] = statuses.get(status, 0) + 1
        if status == "no-entry":
            print(f"  ⚠ {canon}: no consolidation entry — capture by hand "
                  f"(add an entry or run the merge reconciliation first).")
    Path(config_path).write_text(content, encoding="utf-8")
    print("\n--write summary: " + ", ".join(
        f"{k}={v}" for k, v in sorted(statuses.items())))


def _apply_resolves(captures: list[Capture]) -> None:
    by_guid: dict[str, list[Capture]] = {}
    for c in captures:
        by_guid.setdefault(c.guid, []).append(c)
    for guid, caps in sorted(by_guid.items()):
        has_ext = any(c.classification == "external_added" for c in caps)
        cmd = resolve_command(guid, has_ext, run=True).split()
        print(f"  resolving {guid} ({'prefer-nonempty' if has_ext else 'keep-primary'})…")
        res = subprocess.run([tool("geni"), *cmd[1:]], text=True,
                             env={**os.environ, "GENI_WEB_CONSENT": "accepted"})
        if res.returncode != 0:
            print(f"  ⚠ resolve failed for {guid}")


if __name__ == "__main__":
    sys.exit(main())
