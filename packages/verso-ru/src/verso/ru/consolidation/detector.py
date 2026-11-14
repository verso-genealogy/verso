#!/usr/bin/env python3
"""Detect duplicate Geni profiles in a terraform plan and suggest
consolidation entries for `generate_config_names.py`.

Reads the structured JSON plan (`_plan.json`, produced by
`terraform -chdir=terraform/geni show -json .plan > _plan.json`, from the village's directory). The legacy text-regex parser is gone; everything
now walks `resource_changes` directly.
"""

import argparse
import json
import re
from collections import defaultdict
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from verso.ru.consolidation.plan import export_command, plan_paths


_TRACKED_TYPES = ("geni_profile", "geni_union", "geni_document")


# The annotation is optional. Глуповы Горы declares the dict as
# `profiles_to_consolidate: dict[str, object] = {`, and matching only the bare
# form is why every writer here — delete, --write, --normalize-sort — silently
# refused to touch that village and worked nowhere but Горюхино.
_PROFILES_DICT_RE = re.compile(r"profiles_to_consolidate\s*(?::[^=\n]+)?=\s*{")

def _resource_name(address: str) -> str:
    """Extract the bare resource name from a TF address like
    `geni_profile.foo` → `foo`. Module-prefixed addresses are not used in
    this project, so a single split is enough."""
    return address.split(".", 1)[1] if "." in address else address


def _effective_id(change: dict[str, Any]) -> str | None:
    """Return the resource's effective id for grouping. Prefer the
    post-apply id (`after.id`) so id remappings (`~ id = "A" -> "B"`)
    group under the destination; fall back to `before.id` for destroys
    and no-ops."""
    after = change.get("after") or {}
    before = change.get("before") or {}
    return after.get("id") or before.get("id")


def collect_profile_ids(plan: dict[str, Any]) -> dict[str, list[str]]:
    """Map each Geni profile-id to the list of TF resource names that
    reference it. Names listed more than once flag a duplicate the
    consolidator should fold."""
    id_to_names: dict[str, list[str]] = defaultdict(list)
    for rc in plan.get("resource_changes") or []:
        if rc.get("type") != "geni_profile":
            continue
        pid = _effective_id(rc.get("change") or {})
        if not pid:
            continue
        name = _resource_name(rc["address"])
        if name not in id_to_names[pid]:
            id_to_names[pid].append(name)
    return id_to_names


def collect_destroy_and_update_addresses(
    plan: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Per-resource-id maps split by action. The destroy map holds the
    `before` id (the live resource being removed); the update map holds
    the `after` id (which captures any remapping)."""
    removed: dict[str, list[str]] = defaultdict(list)
    changed: dict[str, list[str]] = defaultdict(list)
    for rc in plan.get("resource_changes") or []:
        rtype = rc.get("type")
        if rtype not in _TRACKED_TYPES:
            continue
        change = rc.get("change") or {}
        actions = change.get("actions") or []
        addr = f"{rtype}.{_resource_name(rc['address'])}"
        if actions == ["delete"]:
            rid = (change.get("before") or {}).get("id")
            if rid and addr not in removed[rid]:
                removed[rid].append(addr)
        elif "update" in actions:
            rid = _effective_id(change)
            if rid and addr not in changed[rid]:
                changed[rid].append(addr)
    return removed, changed


def collect_creates_and_destroys(
    plan: dict[str, Any],
) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
    """Lists of `(address, change_payload)` for creates and destroys.
    The payload is the resource-change dict's `before`/`after` body,
    used for fuzzy rename matching downstream."""
    added: list[tuple[str, dict[str, Any]]] = []
    removed: list[tuple[str, dict[str, Any]]] = []
    for rc in plan.get("resource_changes") or []:
        rtype = rc.get("type")
        if rtype not in _TRACKED_TYPES:
            continue
        change = rc.get("change") or {}
        actions = change.get("actions") or []
        addr = rc["address"]
        if actions == ["create"]:
            added.append((addr, change.get("after") or {}))
        elif actions == ["delete"]:
            removed.append((addr, change.get("before") or {}))
    return added, removed


def find_duplicate_profiles(profile_id_to_names):
    duplicates = {}

    for profile_id, names in profile_id_to_names.items():
        if len(names) > 1:
            # Sort names to ensure consistent output
            names.sort()
            duplicates[profile_id] = names

    return duplicates


def create_consolidated_structure(duplicates, profiles):
    """Build new profiles_to_consolidate entries from shared-id groups.

    Returns `(new_profiles, folded_canonicals)`. `folded_canonicals` maps a
    SOURCE canonical key → its TARGET when a shared-id group merges two
    already-consolidated canonicals (a canonical→canonical merge): the source's
    own raw stubs are expanded INTO the target's profile_names (a canonical key
    in profile_names would violate CCN008), and the source entry must be dropped
    (done by `--write`, or manually) + its orphan profile forgotten.
    """
    new_profiles = {}
    folded_canonicals: dict[str, str] = {}

    for _profile_id, names in duplicates.items():
        # Extract the base name (without date/version suffixes)
        base_name = find_base_name(names, profiles)

        # Expand any OTHER canonical member into its raw source stubs so the
        # emitted profile_names contain only stubs (CCN008), and record the
        # canonical→canonical fold.
        profile_names: set[str] = set()
        for n in names:
            if n != base_name and n in profiles:
                folded_canonicals[n] = base_name
                profile_names.update(profiles[n].get('profile_names', []))
            else:
                profile_names.add(n)

        check_if_name_already_exists_in(base_name, None, profile_names, profiles, new_profiles)

    return new_profiles, folded_canonicals


def delete_canonical_entries(file_name, source_keys):
    """Remove the given top-level `profiles_to_consolidate` entries in place.

    Used by `--write` to drop a canonical that was folded into another canonical
    (its stubs already moved to the target). Returns the number deleted.
    """
    source_keys = [k for k in source_keys]
    if not source_keys:
        return 0
    with open(file_name, 'r', encoding='utf-8') as f:
        content = f.read()
    m = _PROFILES_DICT_RE.search(content)
    if not m:
        return 0
    brace_start = content.find('{', m.start())
    dict_end = find_matching_brace(content, brace_start)
    deleted = 0
    for key in source_keys:
        dict_body = content[brace_start:dict_end + 1]
        span = find_key_block(content, dict_body, key, brace_start)
        if span is None:
            continue
        abs_open, abs_close = span
        # widen to the line start (indent) and swallow the trailing `,\n`.
        line_start = content.rfind('\n', 0, abs_open) + 1
        end = abs_close + 1
        while end < len(content) and content[end] in ', \t':
            end += 1
        if end < len(content) and content[end] == '\n':
            end += 1
        content = content[:line_start] + content[end:]
        dict_end = find_matching_brace(content, brace_start)
        deleted += 1
    with open(file_name, 'w', encoding='utf-8') as f:
        f.write(content)
    return deleted


def format_canonical_merge_notice(folded_canonicals):
    """Suggest `removed{destroy=false}` blocks + the delete step for each
    canonical→canonical fold (the orphan profile now shares the target's id)."""
    if not folded_canonicals:
        return ""
    out = ["# ── Canonical→canonical cluster merges ──",
           "# These canonicals were merged INTO another on Geni; their stubs are",
           "# folded into the target above. `--write` deletes the source entries;",
           "# paste the orphan-profile removed{} blocks into",
           "# terraform/geni/_moved_consolidated_unions.tf (id now shared with target):",
           ""]
    for source, target in sorted(folded_canonicals.items()):
        out.append(f"#   {source} → {target}")
        out.append("removed {")
        out.append(f"  from = geni_profile.{source}")
        out.append("  lifecycle {")
        out.append("    destroy = false")
        out.append("  }")
        out.append("}")
    return "\n".join(out)


def check_if_name_already_exists_in(base_name, name_suffix, profile_names, profiles, new_profiles):
    # Check if this base name already exists in profiles
    profile_name = f"{base_name}{f'_{name_suffix}' if name_suffix else ''}"

    if profile_name in profiles:
        # Check if all profile names are already included
        existing_names = set(profiles[profile_name].get('profile_names', []))
        existing_names.add(profile_name)

        # Overlap means some names are already present
        if existing_names & profile_names:
            # If there are new names not in the existing entry, create a new entry
            missing_names = profile_names - existing_names
            if missing_names:
                # Include only missing names
                new_profiles[profile_name] = {
                    'profile_names': missing_names
                }
        else:
            # No overlap, so we need to update the key and add the new entry
            i = name_suffix + 1 if name_suffix else 2
            check_if_name_already_exists_in(base_name, i, profile_names, profiles, new_profiles)
    else:
        # Check if this base name already exists in consolidated
        if profile_name in new_profiles:
            # Append a number to make it unique
            i = name_suffix + 1 if name_suffix else 2
            check_if_name_already_exists_in(base_name, i, profile_names, profiles, new_profiles)
        else:
            # This is a completely new entry
            new_profiles[profile_name] = {
                'profile_names': profile_names
            }


def find_base_name(names, profiles):
    # If any name is already in profiles, return it directly
    for name in names:
        if name in profiles:
            return name

    # Common patterns in profile names
    patterns = [
        r'_\d{4}_\d{2}_\d{2}_', # _1838_10_14_
        r'_(mk_births|mk_marriages|mk_deaths|rs)_\w+$', # _mk_births_31_god_parent_2
    ]

    # Find the shortest name after removing all patterns
    shortest_name = None
    shortest_length = float('inf')

    for name in names:
        # Try to remove all patterns
        base = name
        for pattern in patterns:
            base = re.sub(pattern, '', base)

        # If this is the shortest base name so far, remember it
        if len(base) < shortest_length:
            shortest_name = base
            shortest_length = len(base)

    # If we couldn't find a base name, use the first name in the list
    if shortest_name is None and names:
        return names[0]

    return shortest_name


def format_output(new_entries):
    """
    Format the new entries as Python code to be added to profiles_to_consolidate.

    Args:
        new_entries (dict): Dictionary of new entries to be added

    Returns:
        str: Formatted string of Python code
    """
    if not new_entries:
        return "No new entries to add to profiles_to_consolidate."

    output = "# New entries to add to profiles_to_consolidate:\n\n"

    for base_name, entry in sorted(new_entries.items()):
        output += f'"{base_name}": {{\n'
        output += '    "generate_moved_block": True,\n'
        output += '    "profile_names": [\n'

        for name in sorted(entry["profile_names"]):
            output += f'        "{name}",\n'

        output += "    ],\n"
        output += "},\n"

    return output


def check_profiles_to_consolidate_for_duplicates(profiles):
    seen = set()
    duplicates = set()

    for _profile_name, profile_data in profiles.items():
        profile_names = profile_data.get('profile_names', [])
        for name in profile_names:
            if name in seen:
                duplicates.add(name)
            else:
                seen.add(name)

    if duplicates:
        print("Duplicate entries found in profiles_to_consolidate:")
        for dup in sorted(duplicates):
            print(f"  - {dup}")
    else:
        print("No duplicate entries found in profiles_to_consolidate.")


def _payload_signature(payload: dict[str, Any]) -> str:
    """Stable string form of a resource-change payload, for fuzzy
    similarity matching between added and removed resources. JSON dump
    with sorted keys gives a deterministic ordering across runs."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def tf_move_commands(added_resources, removed_resources, union_moves=None):
    """Authoritative `(removed_addr, added_addr)` state-mv rename pairs.

    `geni_union` renames use the partner-id-matched pairs from
    `suggest_union_blocks` (`union_moves` = list of `(delete_name, create_name)`)
    rather than difflib payload similarity — the signature match paired two
    siblings whose surname/patronymic tokens overlapped but whose Geni partners
    were disjoint (pointing a move at the wrong family). Non-union types keep
    signature matching (their declarative moves are auto-generated, lower-risk),
    and unions never fall through to it."""
    pairs: list[tuple[str, str]] = []
    added_union = {
        _resource_name(a): a for a, _ in added_resources if a.startswith("geni_union.")
    }
    removed_union = {
        _resource_name(a): a for a, _ in removed_resources if a.startswith("geni_union.")
    }
    matched_added: set[str] = set()
    for frm, to in (union_moves or []):
        if frm in removed_union and to in added_union:
            pairs.append((removed_union[frm], added_union[to]))
            matched_added.add(added_union[to])

    sig_by_addr = {
        addr: _payload_signature(payload)
        for addr, payload in removed_resources
        if not addr.startswith("geni_union.")
    }
    for added_addr, added_payload in added_resources:
        if added_addr.startswith("geni_union.") or added_addr in matched_added:
            continue
        added_type = added_addr.split('.', 1)[0]
        candidates = {addr: sig for addr, sig in sig_by_addr.items()
                      if addr.startswith(added_type + '.')}
        if not candidates:
            continue
        matches = get_close_matches(
            _payload_signature(added_payload), list(candidates.values()), n=1, cutoff=0.3)
        if not matches:
            continue
        removed_addr = next(addr for addr, sig in candidates.items() if sig == matches[0])
        pairs.append((removed_addr, added_addr))
    return pairs


def print_tf_move_commands(added_resources, removed_resources, union_moves=None):
    """Suggest `terraform state mv` for renames (see `tf_move_commands`)."""
    for removed_addr, added_addr in tf_move_commands(
            added_resources, removed_resources, union_moves):
        print(f'terraform -chdir=terraform/geni state mv {removed_addr} {added_addr}')


def find_matching_brace(s, start_pos):
    # Find a matching closing brace for the opening brace at start_pos.
    i = start_pos
    n = len(s)
    depth = 0
    in_string = None  # None, "'", '"', "'''", '"""'
    escape = False
    while i < n:
        ch = s[i]
        # Handle escaping
        if escape:
            escape = False
            i += 1
            continue

        if in_string:
            # handle end of string
            if in_string in ("'", '"'):
                if ch == in_string:
                    in_string = None
            else:
                # triple quotes
                if s.startswith(in_string, i):
                    i += len(in_string)
                    in_string = None
                    continue
            if ch == "\\":
                escape = True
            i += 1
            continue

        # not in string
        if ch == '#':
            # skip a `#` comment to end of line — its braces/quotes are not code
            nl = s.find('\n', i)
            if nl == -1:
                return -1
            i = nl + 1
            continue
        if s.startswith("'''", i) or s.startswith('"""', i):
            in_string = s[i:i + 3]
            i += 3
            continue
        if ch == "'" or ch == '"':
            in_string = ch
            i += 1
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        elif ch == "\\":
            escape = True

        i += 1
    return -1


def find_key_block(content, dict_body, key, brace_start):
    # pattern to find the key occurrence inside the dict literal
    key_pattern = re.compile(r'(?m)^(\s*)"' + re.escape(key) + r'"\s*:\s*{', re.MULTILINE)
    m = key_pattern.search(dict_body)
    if not m:
        return None
    # compute position of the opening brace for this key in the full content
    # m.start() is relative to dict_body start
    rel_open = dict_body.find('{', m.end() - 1)
    if rel_open == -1:
        return None
    abs_open = brace_start + rel_open
    abs_close = find_matching_brace(content, abs_open)
    if abs_close == -1:
        return None
    return (abs_open, abs_close)


def write_new_entries_to_file(new_entries, file_name):
    if not new_entries:
        print("No new entries to write.")
        return

    # Read the target file
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File {file_name} not found")
        raise

    # Find the start of profiles_to_consolidate assignment
    m = _PROFILES_DICT_RE.search(content)
    if not m:
        print("Could not find 'profiles_to_consolidate = {' in file")
        return

    dict_start = m.start()
    brace_start = content.find('{', dict_start)
    if brace_start == -1:
        print("Could not find opening brace for profiles_to_consolidate")
        return

    dict_end = find_matching_brace(content, brace_start)
    if dict_end == -1:
        print("Could not find matching closing brace for profiles_to_consolidate")
        return

    # Extract the dict body (including outer braces)
    dict_body = content[brace_start:dict_end + 1]

    # We'll prepare a list of in-place edits (tuples of (start,end,new_text))
    edits: list[tuple[int, int, str]] = []

    # For existing keys, update their profile_names list and ensure generate_moved_block
    for base_name, entry in sorted(new_entries.items()):
        new_names = set(entry.get('profile_names', []))

        key_block = find_key_block(content, dict_body, base_name, brace_start)
        if key_block:
            open_idx, close_idx = key_block
            block_text = content[open_idx:close_idx + 1]

            # Find the profile_names list inside block_text
            pn_pattern = re.compile(r'("profile_names"\s*:\s*\[)(.*?)(\])', re.DOTALL)
            pn_m = pn_pattern.search(block_text)
            if pn_m:
                existing_list_text = pn_m.group(2)
                # extract existing names (simple regex for quoted strings)
                existing_names = re.findall(r'"([^\"]+)"', existing_list_text)
                combined = []
                seen = set()
                # Preserve existing order, then add new names
                for n in existing_names:
                    combined.append(n)
                    seen.add(n)
                for n in new_names:
                    if n not in seen:
                        combined.append(n)
                        seen.add(n)

                # guess indentation as 4 spaces
                indent = ' ' * 12  # matches file formatting (4 for dict + 8 for nested)
                rebuilt_list = "\n"
                for name in sorted(combined):
                    rebuilt_list += f'{indent}"{name}",\n'

                close_indent = ' ' * 8  # matches file formatting (4 for dict + 4 for nested)
                rebuilt_list += f"{close_indent}"  # close indentation aligned with original

                new_block_text = block_text[:pn_m.start(2)] + rebuilt_list + block_text[pn_m.end(2):]
            else:
                # No profile_names found; we'll append one before the closing brace
                insert_pos = len(block_text) - 1
                indent = ' ' * 12  # matches file formatting (4 for dict + 8 for nested)
                rebuilt_list = '\n            "profile_names": [\n'

                for n in sorted(new_names):
                    rebuilt_list += f'{indent}"{n}",\n'

                close_indent = ' ' * 8  # matches file formatting (4 for dict + 4 for nested)
                rebuilt_list += f"{close_indent}],\n"
                new_block_text = block_text[:insert_pos] + rebuilt_list + block_text[insert_pos:]

            # Ensure 'generate_moved_block': True is present
            if "generate_moved_block" not in new_block_text:
                # insert it right after opening brace
                # find position after the first newline in block_text
                open_line_end = new_block_text.find('\n')
                insert_at = open_line_end + 1 if open_line_end != -1 else 1
                # compose insertion with indentation matching file
                gen_text = '        "generate_moved_block": True,\n'
                new_block_text = new_block_text[:insert_at] + gen_text + new_block_text[insert_at:]

            # Schedule replacement in full content
            edits.append((open_idx, close_idx + 1, new_block_text))
        else:
            # Key does not exist in the dict; we'll append a new block at insertion index
            pass

    # Apply scheduled edits from end to start to not disturb indices
    new_content = content
    if edits:
        for start, end, txt in sorted(edits, key=lambda e: e[0], reverse=True):
            new_content = new_content[:start] + txt + new_content[end:]

    # Build appended entries for keys that do not exist yet (or that we prefer to append as new)
    appended = ""
    for base_name, entry in sorted(new_entries.items()):
        # If the key already exists in the original content, skip appending (we updated it in-place)
        if re.search(r'(?m)^\s*"' + re.escape(base_name) + r'"\s*:', dict_body):
            continue

        names = sorted(entry.get('profile_names', []))
        appended += f'    "{base_name}": {{\n'
        appended += '        "generate_moved_block": True,\n'
        appended += '        "profile_names": [\n'
        for n in names:
            appended += f'            "{n}",\n'
        appended += "        ],\n"
        appended += "    },\n"

    if appended:
        dict_end = find_matching_brace(new_content, brace_start)
        if dict_end == -1:
            print("Could not find matching closing brace for profiles_to_consolidate")
            return

        # We'll build textual entries to insert before the final closing brace of the dict.
        insertion_index = dict_end  # position of closing '}' in original content

        # Insert appended text before the closing brace of the dict
        new_content = new_content[:insertion_index] + appended + new_content[insertion_index:]

    # Write back to the file only if content changed
    if new_content != content:
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {file_name} with {len(new_entries)} entries.")
    else:
        print("No changes made to the file.")


def _strip_py_comments(text: str) -> str:
    """Drop `#…` comments from each line (comments may contain quoted strings
    we must NOT mistake for list entries)."""
    return re.sub(r"#[^\n]*", "", text)


def _name_in_line(line: str) -> str | None:
    """The first quoted-string entry on a list line (before any `#` comment),
    or None for comment-only / blank / structural lines."""
    code = _strip_py_comments(line)
    m = re.match(r'\s*"([^"]+)"\s*,?\s*$', code)
    return m.group(1) if m else None


def _sort_profile_names_body(body: str) -> str | None:
    """Return a re-sorted version of a `profile_names` list body (the text
    between `[` and `]`), or None if it's already sorted.

    `#` comment lines that precede an entry travel WITH that entry through the
    sort, so per-entry annotations stay attached. Blank-line noise is dropped
    and a clean 8-space close-indent is always emitted, which incidentally
    repairs the occasional malformed entry (`]` glued to the last element).
    The exact multiset of names is preserved (only the order changes).
    """
    names_in_order = re.findall(r'"([^"]+)"', _strip_py_comments(body))
    if not names_in_order or names_in_order == sorted(names_in_order):
        return None  # nothing to do (covers every single-element list)

    indent = " " * 12  # list items: 4 (dict) + 8 (nested)
    close_indent = " " * 8  # closing bracket: 4 (dict) + 4 (nested)

    if "\n" not in body:
        # Single-line list. Comments here are vanishingly rare; bail rather
        # than risk dropping one.
        if "#" in body:
            return None
        return "\n" + "".join(f'{indent}"{n}",\n' for n in sorted(names_in_order)) + close_indent

    lines = body.split("\n")
    lead = ""
    if lines and lines[0].strip() == "":
        lead, lines = lines[0], lines[1:]

    items: list[tuple[list[str], str, str]] = []  # (preceding comments, name line, name)
    pending: list[str] = []
    for ln in lines:
        if ln.strip() == "":
            continue  # drop blank-line noise
        name = _name_in_line(ln)
        if name is None:  # `#` comment — anchors to the next entry
            pending.append(ln)
            continue
        items.append((pending, ln, name))
        pending = []

    items.sort(key=lambda it: it[2])  # stable sort by entry name

    out = [lead]
    for comments, name_line, _ in items:
        out.extend(comments)
        out.append(name_line)
    out.extend(pending)  # trailing comments (after the last entry), if any
    if out[-1].strip() != "":  # guarantee a clean close-indent before `]`
        out.append(close_indent)
    rebuilt = "\n".join(out)

    assert sorted(re.findall(r'"([^"]+)"', _strip_py_comments(rebuilt))) == sorted(
        names_in_order
    ), "normalize_sort would change list membership"
    return rebuilt


def normalize_sort_profile_names(file_name: str) -> bool:
    """One-off: sort every `profile_names` list in `profiles_to_consolidate`
    into the canonical order that `--write` emits (and CCN009 enforces).

    Sorted lists keep diffs minimal — once every list is pre-sorted, a real
    fold inserts the new name in place (a one-line diff) instead of
    re-alphabetizing the whole list. Only lists that are actually out of order
    are rewritten (so single-element / already-sorted lists stay byte-identical),
    and per-entry comments are preserved.

    Returns True if the file changed.
    """
    with open(file_name, "r", encoding="utf-8") as f:
        content = f.read()

    m = _PROFILES_DICT_RE.search(content)
    if not m:
        print("Could not find 'profiles_to_consolidate = {' in file")
        return False
    brace_start = content.find("{", m.start())
    if brace_start == -1:
        print("Could not find opening brace for profiles_to_consolidate")
        return False
    dict_end = find_matching_brace(content, brace_start)
    if dict_end == -1:
        print("Could not find matching closing brace for profiles_to_consolidate")
        return False

    region = content[brace_start : dict_end + 1]
    pn_pattern = re.compile(r'("profile_names"\s*:\s*\[)(.*?)(\])', re.DOTALL)
    changed = 0

    def _resort(match: re.Match[str]) -> str:
        nonlocal changed
        rebuilt = _sort_profile_names_body(match.group(2))
        if rebuilt is None:
            return match.group(0)
        changed += 1
        return match.group(1) + rebuilt + match.group(3)

    new_region = pn_pattern.sub(_resort, region)
    if changed == 0:
        print("profile_names already sorted; no changes.")
        return False

    new_content = content[:brace_start] + new_region + content[dict_end + 1 :]
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Sorted {changed} profile_names list(s) in {file_name}.")
    return True


def print_tf_remove_commands(removed_profile_id_to_names, changed_profile_id_to_names):
    # Iterate over removed resources and find if it matches changed resources
    command = ""
    for removed_id, removed_names in removed_profile_id_to_names.items():
        if removed_id in changed_profile_id_to_names:
            for removed_name in removed_names:
                command += f' {removed_name}'

    if command:
        print(f'terraform -chdir=terraform/geni state rm{command}')


# Tokens in a union resource name that describe the RECORD, not the partners.
# Stripped before computing partner-name overlap between a delete and its rename.
_UNION_NOISE_TOKENS = {
    "and", "mk", "rs", "births", "marriages", "deaths", "divorces", "bf",
    "family", "member", "father", "mother", "groom", "bride", "child",
    "relative", "witness", "god", "parent", "deceased", "rel",
}


def _union_name_tokens(name: str) -> set[str]:
    """Partner-name tokens of a union resource name (record-type / number /
    year noise removed), used to match a per-record union to its rename."""
    return {
        t
        for t in name.strip("_").split("_")
        if t and not t.isdigit() and t not in _UNION_NOISE_TOKENS
    }


def _best_name_match(target: str, candidates: list[str], min_overlap: int = 1) -> str | None:
    """The candidate sharing the most partner-name tokens with *target*
    (≥ min_overlap), or None. Used to pair a renamed union (delete) with the
    create that adopts it when the plan can't link them by Geni id."""
    tt = _union_name_tokens(target)
    best, best_score = None, 0
    for c in candidates:
        score = len(tt & _union_name_tokens(c))
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= min_overlap else None


def _union_meta(payload: dict[str, Any]) -> dict[str, Any]:
    """Partner/children profile-id sets from a union change payload — the
    authoritative identity of a union (immune to the surname/patronymic name
    coincidence that fools resource-name token matching between siblings)."""
    partners = payload.get("partners")
    children = payload.get("children")
    return {
        "partners": frozenset(partners) if isinstance(partners, list) else frozenset(),
        "children": tuple(children) if isinstance(children, list) else (),
    }


def collect_union_id_groups(plan: dict[str, Any]):
    """Group geni_union changes by effective Geni id, plus the creates whose
    id is still 'known after apply' (id-less). Also returns `meta`: a map of
    union resource name -> {"partners": frozenset(profile ids), "children":
    tuple(profile ids)} used to match renames by partner identity."""
    by_id: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"delete": [], "create": [], "survive": []}
    )
    creates_no_id: list[str] = []
    meta: dict[str, dict[str, Any]] = {}
    for rc in plan.get("resource_changes") or []:
        if rc.get("type") != "geni_union":
            continue
        change = rc.get("change") or {}
        actions = change.get("actions") or []
        name = _resource_name(rc["address"])
        if actions == ["create"]:
            after = change.get("after") or {}
            meta[name] = _union_meta(after)
            pid = after.get("id")
            if pid:
                by_id[pid]["create"].append(name)
            else:
                creates_no_id.append(name)
        elif actions == ["delete"]:
            before = change.get("before") or {}
            meta[name] = _union_meta(before)
            rid = before.get("id")
            if rid:
                by_id[rid]["delete"].append(name)
        elif actions == ["no-op"] or "update" in actions:
            pid = _effective_id(change)
            meta[name] = _union_meta(change.get("after") or change.get("before") or {})
            if pid:
                by_id[pid]["survive"].append(name)
    return by_id, creates_no_id, meta


def _union_partners(name: str, meta: dict[str, dict[str, Any]]) -> frozenset[str]:
    return meta.get(name, {}).get("partners") or frozenset()


def _partner_overlap(a: str, b: str, meta: dict[str, dict[str, Any]]) -> int:
    return len(_union_partners(a, meta) & _union_partners(b, meta))


def _union_children_count(name: str, meta: dict[str, dict[str, Any]]) -> int:
    return len(meta.get(name, {}).get("children") or ())


def _best_create_match(delete: str, candidates: list[str], meta: dict[str, dict[str, Any]]):
    """Best create matching `delete`, as (create, score, by_partner).

    Partner-id overlap is authoritative; resource-name token overlap is only a
    fallback used when the plan exposes no partner ids for the pair. When the
    delete HAS partner ids but every candidate's partner set is disjoint, this
    returns no match (rather than falling back to name tokens) — that disjoint
    case is exactly the sibling false-match that detached a child before."""
    if _union_partners(delete, meta):
        scored = [
            (c, _partner_overlap(delete, c, meta))
            for c in candidates
            if _union_partners(c, meta)
        ]
        scored = [(c, s) for c, s in scored if s > 0]
        if scored:
            c, s = max(scored, key=lambda t: t[1])
            return c, s, True
        if any(_union_partners(c, meta) for c in candidates):
            return None, 0, False  # partner ids known and disjoint → not a rename
    m = _best_name_match(delete, candidates, min_overlap=2)
    if m:
        return m, len(_union_name_tokens(delete) & _union_name_tokens(m)), False
    return None, 0, False


def _keeper_for_create(create: str, deletes: list[str], meta: dict[str, dict[str, Any]]) -> str | None:
    """Which delete (same resolved id) the create adopts — prefer the one
    sharing partners with the create, else the best name match."""
    if _union_partners(create, meta):
        scored = [(d, _partner_overlap(create, d, meta)) for d in deletes]
        scored = [(d, s) for d, s in scored if s > 0]
        if scored:
            return max(scored, key=lambda t: t[1])[0]
    return _best_name_match(create, deletes)


def suggest_union_blocks(plan: dict[str, Any]):
    """Classify shared-id union churn into `_moved_consolidated_unions.tf`
    suggestions: a per-record union that collapsed onto a surviving canonical
    couple union (shared Geni id) becomes `removed{destroy=false}`; a union
    renamed to a new canonical name becomes `moved`. Returns (moved, removed,
    notes)."""
    by_id, creates_no_id, meta = collect_union_id_groups(plan)
    moved: list[tuple[str, str]] = []
    removed: list[str] = []
    notes: list[str] = []
    used_creates: set[str] = set()

    def _flag_unmatched(d: str) -> None:
        """A delete with no valid rename match: REVIEW (never plain-destroy a
        union that still holds children on Geni)."""
        kids = _union_children_count(d, meta)
        if kids:
            notes.append(
                f"union delete {d} still has {kids} child(ren) on Geni and no "
                "partner-id rename match — do NOT plain-destroy; verify (moved to "
                "its canonical, or removed{destroy=false})"
            )
        else:
            notes.append(
                f"standalone union delete (no shared id / partner-id match): {d} "
                "— usually a safe within-tree destroy+create, verify"
            )

    for _pid, g in by_id.items():
        deletes = g["delete"]
        if not deletes:
            continue
        if g["create"]:
            # Rename: the create adopts this id. moved the delete that best
            # matches it (same couple); removed any other delete on this id.
            create = g["create"][0]
            keeper = _keeper_for_create(create, deletes, meta) or deletes[0]
            moved.append((keeper, create))
            removed.extend(d for d in deletes if d != keeper)
        elif g["survive"]:
            # Lone collapse onto a surviving canonical couple union — forget,
            # never destroy (would detach the canonical's children).
            removed.extend(deletes)
        else:
            # No survivor and no same-id create — the surviving union is an
            # id-less create (Geni hasn't resolved the new id yet). Match by
            # shared partner ids (authoritative — a sibling's union with a
            # disjoint partner set is NOT a rename, however much the surname
            # tokens overlap), and pick the single best (delete, create) pair:
            # that delete is the rename (moved), the rest collapsed (removed).
            cand = [c for c in creates_no_id if c not in used_creates]
            best_pair, best_score, best_is_id = None, 0, False
            for d in deletes:
                m, score, by_partner = _best_create_match(d, cand, meta)
                if m is None:
                    continue
                if by_partner and not best_is_id:
                    best_pair, best_score, best_is_id = (d, m), score, True
                elif by_partner == best_is_id and score > best_score:
                    best_pair, best_score = (d, m), score
            if best_pair:
                kd, create = best_pair
                moved.append((kd, create))
                used_creates.add(create)
                for d in deletes:
                    if d == kd:
                        continue
                    # A collapse must share partners with the renamed canonical;
                    # a delete whose partner set is disjoint is a different
                    # family caught in the same id group → flag, never forget.
                    if _union_partners(d, meta) and _partner_overlap(d, create, meta) == 0:
                        _flag_unmatched(d)
                    else:
                        removed.append(d)
            else:
                for d in deletes:
                    _flag_unmatched(d)
    moved.sort()
    removed.sort()
    notes.sort()
    return moved, removed, notes


def format_union_blocks(moved, removed, notes) -> str:
    """Render ready-to-paste blocks for `terraform/geni/_moved_consolidated_unions.tf`."""
    if not (moved or removed or notes):
        return ""
    out = [
        "",
        "# ── Suggested terraform/geni/_moved_consolidated_unions.tf blocks ──",
        "# Review, then paste into that hand-maintained file (generate does not emit it).",
        "",
    ]
    for frm, to in moved:
        out.append(f"moved {{\n  from = geni_union.{frm}\n  to   = geni_union.{to}\n}}")
    for frm in removed:
        out.append(
            f"removed {{\n  from = geni_union.{frm}\n  lifecycle {{\n    destroy = false\n  }}\n}}"
        )
    for note in notes:
        out.append(f"# REVIEW: {note}")
    return "\n".join(out) + "\n"


def collect_document_changes(plan: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """geni_document resources the plan would force-replace or update (text /
    projects delta). A terraform replace deletes+recreates the Geni document,
    losing its id/created_at — these must be pushed via update_documents.py
    instead. Returns (resource_name, changed_fields)."""
    out: list[tuple[str, list[str]]] = []
    for rc in plan.get("resource_changes") or []:
        if rc.get("type") != "geni_document":
            continue
        change = rc.get("change") or {}
        actions = change.get("actions") or []
        replace = "delete" in actions and "create" in actions
        if not (replace or actions == ["update"]):
            continue
        before = change.get("before") or {}
        after = change.get("after") or {}
        fields = [f for f in ("text", "projects") if before.get(f) != after.get(f)]
        if fields:
            out.append((_resource_name(rc["address"]), fields))
    return out


def format_document_warning(docs: list[tuple[str, list[str]]]) -> str:
    """Warn about documents that need document_sync before apply."""
    if not docs:
        return ""
    out = [
        "",
        f"WARNING: {len(docs)} geni_document(s) would be force-replaced (losing the "
        "Geni doc id). Push the text via document_sync BEFORE `terraform apply`:",
        "    verso document-sync --plan _plan.json",
    ]
    for name, fields in docs:
        out.append(f"  - {name} ({', '.join(fields)})")
    return "\n".join(out)


def _load_plan(plan_path: Path) -> dict[str, Any]:
    """Load a JSON plan. Rejects legacy text plans with a clear message
    so users land on the JSON plan (`export_command`)."""
    if plan_path.suffix == ".txt":
        raise SystemExit(
            f"detector.py no longer reads text plans ({plan_path}).\n"
            f"Run `{export_command(plan_path.parent)}` to produce `_plan.json`, then re-run."
        )
    with open(plan_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_consolidate_config(config_path: str):
    """The village-local generate_config_names module at a path (`verso.core.pipeline.config`)."""
    from verso.core.pipeline.config import load_config
    return load_config(Path(config_path))


def main():
    parser = argparse.ArgumentParser(description="Analyze terraform plan and consolidate duplicate Geni profiles.")
    parser.add_argument(
        "--plan",
        default=str(plan_paths().plan_json),
        help=f"Path to terraform plan JSON file (default: {plan_paths().plan_json.name})",
    )
    parser.add_argument(
        "--config",
        default="generate_config_names.py",
        help="Path to generate_config_names.py (default: generate_config_names.py)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="When set, write new consolidation entries into generate_config_names.py",
    )
    parser.add_argument(
        "--normalize-sort",
        action="store_true",
        help=(
            "One-off: sort every profile_names list in the config into canonical "
            "order (matches --write / CCN009), then exit. Does not read the plan."
        ),
    )

    args = parser.parse_args()

    if args.normalize_sort:
        normalize_sort_profile_names(args.config)
        return

    try:
        profiles_to_consolidate = _load_consolidate_config(args.config).profiles_to_consolidate
        # Parse the plan file
        plan = _load_plan(Path(args.plan))
        updated_profile_id_to_names = collect_profile_ids(plan)
        added_resources, removed_resources = collect_creates_and_destroys(plan)
        removed_resource_id_to_names, changed_resource_id_to_names = collect_destroy_and_update_addresses(plan)

        # Find duplicate profiles
        duplicates = find_duplicate_profiles(updated_profile_id_to_names)

        if not duplicates:
            print(f"No duplicate profiles found in {args.plan}")
        else:
            # Create consolidated structure
            new_entries, folded_canonicals = create_consolidated_structure(
                duplicates, profiles_to_consolidate)

            # Optionally write to generate_config_names.py
            if args.write:
                write_new_entries_to_file(new_entries, args.config)
                # Canonical→canonical merges: the source's stubs were folded into
                # the target (above); drop the now-redundant source entries.
                if folded_canonicals:
                    n = delete_canonical_entries(args.config, folded_canonicals.keys())
                    print(f"Deleted {n} folded canonical entry(ies) from profiles_to_consolidate.")

            # Format and print the output
            print(format_output(new_entries))
            notice = format_canonical_merge_notice(folded_canonicals)
            if notice:
                print(notice)

        check_profiles_to_consolidate_for_duplicates(profiles_to_consolidate)

        # Union side: suggest _moved_consolidated_unions.tf blocks for per-record
        # unions that collapsed onto canonical couple unions (shared Geni id).
        moved_u, removed_u, notes_u = suggest_union_blocks(plan)
        union_out = format_union_blocks(moved_u, removed_u, notes_u)
        if union_out:
            print(union_out)

        # Documents that would be force-replaced (losing the Geni id) — must be
        # pushed via update_documents.py before apply.
        doc_warn = format_document_warning(collect_document_changes(plan))
        if doc_warn:
            print(doc_warn)

        print_tf_move_commands(added_resources, removed_resources, union_moves=moved_u)
        print_tf_remove_commands(removed_resource_id_to_names, changed_resource_id_to_names)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
