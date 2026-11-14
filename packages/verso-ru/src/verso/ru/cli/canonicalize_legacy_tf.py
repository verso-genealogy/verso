#!/usr/bin/env python3
"""Canonicalize legacy Terraform files to match translator output.

Pairs each legacy profile with the translator-emitted profile by
res_name structure — `_YYYY_MM_DD_<first>_<middle>_<last>_<doc>_<n>_<role>[_suffix]` —
extracting the name tokens from the translator side and renaming the
legacy profile accordingly. Also updates `generate_config_names.py`
move_list keys that reference renamed profiles.

Usage:
    rm -rf /tmp/tf-out && mkdir /tmp/tf-out
    .venv/bin/python generate_tf.py --village Горюхино --output-dir /tmp/tf-out
    terraform fmt -recursive /tmp/tf-out/ >/dev/null 2>&1

    .venv/bin/python canonicalize_legacy_tf.py --village Горюхино \\
        --translator-dir /tmp/tf-out --apply

Rewrites `{village}/terraform/geni/*.tf` and `{village}/generate_config_names.py`
in place. Run with `--apply` to persist; omit for a dry-run preview.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


# _YYYY_MM_DD_{first}_{middle}_{last}_{document}_{record}_{role}[_suffix]
# Suffix is everything after the role (e.g. `_43-6-587-part-2`).
# Use non-greedy matching for tokens since tokens themselves may contain
# nothing more than [a-z0-9]. Date prefix anchors the split.
_PROFILE_NAME_RE = re.compile(
    r'_(?P<date>\d{4}_\d{2}_\d{2})_(?P<middle>.+)'
)

# Identify the SUFFIX structure: everything from `_mk_` / `_rs_` token onward.
# Known document prefixes in res_names.
_DOC_PREFIXES = ("mk_births", "mk_marriages", "mk_deaths", "rs")


# Document-resource naming patterns. The res_name is
#   `birth_of_{name}_{N}_{YYYY}`
#   `death_of_{name}_{N}_{YYYY}`
#   `marriage_of_{groom}_and_{bride}_{N}_{YYYY}`
# where {name} / {groom} / {bride} are underscore-joined name tokens.
_DOC_RES_RE = re.compile(
    r'^(?P<type>birth|death)_of_(?P<name>.+)_(?P<n>\d+)_(?P<year>\d{4})$'
)
_MARRIAGE_RES_RE = re.compile(
    r'^marriage_of_(?P<groom>.+?)_and_(?P<bride>.+?)_(?P<n>\d+)_(?P<year>\d{4})$'
)


def _split_doc_res_name(res_name: str) -> tuple[str, str, int, int, str] | None:
    """Parse a document res_name into (type, name_part, N, year, kind).
    Returns None when the res_name doesn't match a known shape.

    `kind` distinguishes single-name docs (births/deaths) from marriages
    (where `name_part` is `"{groom}|{bride}"` joined by a literal `|`)."""
    m = _MARRIAGE_RES_RE.match(res_name)
    if m:
        return ("marriage",
                f'{m.group("groom")}|{m.group("bride")}',
                int(m.group("n")), int(m.group("year")), "marriage")
    m = _DOC_RES_RE.match(res_name)
    if m:
        return (m.group("type"), m.group("name"),
                int(m.group("n")), int(m.group("year")), "single")
    return None


def _split_res_name(res_name: str) -> tuple[str, str, str] | None:
    """Split `_YYYY_MM_DD_...name_parts..._doc_N_role[_suffix]` into
    (date_prefix, name_part, doc_suffix). Returns None when the
    res_name doesn't match the expected shape (e.g. consolidated
    profile names with no date prefix)."""
    if not res_name.startswith("_"):
        return None
    m = re.match(r'^_(\d{4}_\d{2}_\d{2})_(.*)', res_name)
    if not m:
        return None
    rest = m.group(2)
    # Find the first known document prefix.
    for doc_prefix in _DOC_PREFIXES:
        idx = rest.find(f"_{doc_prefix}_")
        if idx >= 0:
            # Also catch the start-of-rest case: rest = "doc_N_role..." with
            # doc_prefix at position 0. The `_{doc_prefix}_` pattern misses
            # the leading case; check separately.
            name_part = rest[:idx]
            doc_suffix = rest[idx + 1:]
            return (m.group(1), name_part, doc_suffix)
        if rest.startswith(f"{doc_prefix}_"):
            return (m.group(1), "", rest)
    return None


def _build_doc_rename_map(legacy_dir: Path,
                          translator_dir: Path) -> dict[str, str]:
    """Build old→new rename map for DOCUMENT res_names (birth_of_*,
    death_of_*, marriage_of_*_and_*). Pair by (type, year, N) and
    require the first-name token to differ while some other token
    (patronymic/surname for single-person docs, groom-or-bride halves
    for marriages) matches."""
    trans_by_key: dict[tuple[str, int, int], list[tuple[str, str]]] = {}
    for tf in sorted(translator_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'resource "geni_document" "([^"]+)"', text):
            res = m.group(1)
            parts = _split_doc_res_name(res)
            if parts is None:
                continue
            typ, name_part, n, year, _kind = parts
            trans_by_key.setdefault((typ, year, n), []).append((res, name_part))

    def _tokens(np: str) -> set[str]:
        # For marriages, split across the `|` too so groom+bride
        # tokens all participate in overlap.
        return {t for t in re.split(r"[_|]", np) if t}

    renames: dict[str, str] = {}
    skipped = 0
    for tf in sorted(legacy_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'resource "geni_document" "([^"]+)"', text):
            old_res = m.group(1)
            parts = _split_doc_res_name(old_res)
            if parts is None:
                continue
            typ, old_np, n, year, _kind = parts
            candidates = trans_by_key.get((typ, year, n), [])
            matches = [
                (res, np) for res, np in candidates
                if _tokens(old_np) & _tokens(np) and np != old_np
            ]
            if len(matches) != 1:
                if len(matches) > 1:
                    skipped += 1
                continue
            new_res, _new_np = matches[0]
            if new_res != old_res:
                renames[old_res] = new_res
    if skipped:
        print(
            f"  skipped {skipped} ambiguous document pairings",
            file=sys.stderr,
        )
    return renames


def _build_rename_map(legacy_dir: Path, translator_dir: Path) -> dict[str, str]:
    """Build old→new res_name map by pairing profiles across legacy
    and translator outputs. Keyed on (date_prefix, doc_suffix). When
    both sides have a profile with the same key AND the NON-FIRST name
    tokens are identical (patronymic+surname), we treat them as the
    same person and the translator's tokens replace the legacy ones.
    When the non-first tokens differ, the pairing is ambiguous
    (different person in the same slot) and we skip.
    """
    # Collect translator profiles.
    trans_by_key: dict[tuple[str, str], str] = {}
    for tf in sorted(translator_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'^resource "geni_profile" "([^"]+)"', text, re.MULTILINE):
            res = m.group(1)
            parts = _split_res_name(res)
            if parts is None:
                continue
            key = (parts[0], parts[2])
            trans_by_key[key] = parts[1]

    def _token_set(name_part: str) -> set[str]:
        return {t for t in name_part.split("_") if t}

    def _pairable(old_np: str, new_np: str) -> bool:
        """Accept as the same person when token-sets overlap by at
        least one non-empty token. This catches:
          - first-name canonicalization (Лука→Гликерия) with shared
            patronymic+surname.
          - patronymic canonicalization (Ионична→Ионовна,
            Сидоровна→Исидоровна) with shared first_name.
          - surname add/remove when DSL migration differed, with
            shared first+patronymic.
        Completely-different people ("савелий_никифорович" vs
        "феофилакт_васильевич") share no tokens → rejected.
        Single-token name-parts (e.g. "феодосия") match when they
        equal any token in the other side's name-part.
        """
        return bool(_token_set(old_np) & _token_set(new_np))

    renames: dict[str, str] = {}
    skipped_ambiguous = 0
    for tf in sorted(legacy_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'^resource "geni_profile" "([^"]+)"', text, re.MULTILINE):
            old_res = m.group(1)
            parts = _split_res_name(old_res)
            if parts is None:
                continue
            date_prefix, old_name_part, doc_suffix = parts
            key = (date_prefix, doc_suffix)
            new_name_part = trans_by_key.get(key)
            if new_name_part is None or new_name_part == old_name_part:
                continue
            if not _pairable(old_name_part, new_name_part):
                skipped_ambiguous += 1
                continue
            new_res = f"_{date_prefix}_{new_name_part}_{doc_suffix}"
            if new_res != old_res:
                renames[old_res] = new_res
    if skipped_ambiguous:
        print(
            f"  skipped {skipped_ambiguous} ambiguous pairings "
            f"(no shared tokens)",
            file=sys.stderr,
        )
    return renames


def _build_display_name_map(
    renames: dict[str, str],
    legacy_dir: Path,
    translator_dir: Path,
) -> dict[str, list[tuple[str, str]]]:
    """For each rename, also derive (old_display, new_display) pairs
    for Cyrillic+Latin first_name/middle_name/last_name fields.
    Returns map: res_name -> [(old_val, new_val), ...].
    """
    # Parse each translator profile block for its display-name values.
    # We look only at profiles whose res_name is in the `new` side of
    # renames.
    new_res_set = set(renames.values())

    def _name_values(block_text: str) -> dict[str, str]:
        """Extract first_name/middle_name/last_name from a profile
        block. Returns {key_locale: value}, e.g. {'en-US:first_name':
        'Mariya', 'ru:first_name': 'Мария', ...}."""
        result: dict[str, str] = {}
        # Split by locale.
        for loc_match in re.finditer(
            r'"(?P<loc>en-US|ru)" = \{(?P<inner>.*?)\}',
            block_text, re.DOTALL,
        ):
            loc = loc_match.group("loc")
            for nm in re.finditer(
                r'(first_name|middle_name|last_name|birth_last_name)\s*=\s*"([^"]*)"',
                loc_match.group("inner"),
            ):
                result[f"{loc}:{nm.group(1)}"] = nm.group(2)
        return result

    # Index translator name values by new res_name.
    trans_vals: dict[str, dict[str, str]] = {}
    for tf in sorted(translator_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(
            r'^resource "geni_profile" "([^"]+)" \{(.*?)^\}',
            text, re.MULTILINE | re.DOTALL,
        ):
            res = m.group(1)
            if res in new_res_set:
                trans_vals[res] = _name_values(m.group(2))

    # Index legacy name values by old res_name.
    legacy_vals: dict[str, dict[str, str]] = {}
    for tf in sorted(legacy_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(
            r'^resource "geni_profile" "([^"]+)" \{(.*?)^\}',
            text, re.MULTILINE | re.DOTALL,
        ):
            res = m.group(1)
            if res in renames:
                legacy_vals[res] = _name_values(m.group(2))

    # Build the per-profile name substitutions.
    out: dict[str, list[tuple[str, str]]] = {}
    for old_res, new_res in renames.items():
        old_nv = legacy_vals.get(old_res, {})
        new_nv = trans_vals.get(new_res, {})
        subs = []
        for k, old_v in old_nv.items():
            new_v = new_nv.get(k, "")
            if old_v and new_v and old_v != new_v:
                subs.append((old_v, new_v))
        if subs:
            out[old_res] = subs
    return out


_PROFILE_BLOCK_RE = re.compile(
    r'(^resource "geni_profile" "(?P<res>[^"]+)" \{)(?P<body>.*?)(^\})',
    re.MULTILINE | re.DOTALL,
)


def _translator_display_names(translator_dir: Path) -> dict[str, str]:
    """Extract the text after `# geni_profile.RES ` from translator
    output files — this is the canonical display form (e.g. 'Мария
    Ивановна'). Keyed by res_name; returns every profile emitted
    by the translator."""
    result: dict[str, str] = {}
    pat = re.compile(r'^# geni_profile\.([^ \n]+)\s+([^\n]+)$', re.MULTILINE)
    for tf in sorted(translator_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in pat.finditer(text):
            res, display = m.group(1), m.group(2).rstrip()
            result[res] = display
    return result


def _apply_to_legacy(
    legacy_dir: Path,
    renames: dict[str, str],
    display_subs: dict[str, list[tuple[str, str]]],
    translator_display_names: dict[str, str],
) -> dict[Path, str]:
    """Rewrite each legacy .tf file:
      - Inside each profile block whose res_name is in `renames`,
        apply the display-name substitutions from `display_subs`.
      - Everywhere in the file text, rewrite res_name references.
      - For each renamed profile, update the `# geni_profile.NEW_RES
        OLD_DISPLAY` comment line to use translator's display text.
    Returns {path: new_text}.
    """
    out: dict[Path, str] = {}
    for tf in sorted(legacy_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")

        # 1) Rewrite display names inside each matching profile block.
        def _block_sub(m):
            res = m.group("res")
            body = m.group("body")
            subs = display_subs.get(res)
            if subs:
                for old, new in sorted(subs, key=lambda s: -len(s[0])):
                    body = body.replace(f'"{old}"', f'"{new}"')
            header = m.group(1)
            closer = m.group(4)
            return header + body + closer

        text = _PROFILE_BLOCK_RE.sub(_block_sub, text)

        # 2) Rewrite res_name references (resource declarations, .id
        # refs, # comments, # - merge-comment entries).
        for old, new in sorted(renames.items(), key=lambda kv: -len(kv[0])):
            # Use word-boundary-like substitution that doesn't mangle
            # substrings inside other names.
            pat = re.compile(
                r'(?<![A-Za-z0-9_-])' + re.escape(old) +
                r'(?![A-Za-z0-9_-])'
            )
            text = pat.sub(new, text)

        # 3) Update every `# geni_profile.RES DISPLAY` comment to match
        # translator's display string for the same res_name. Covers
        # both renamed profiles AND unrenamed ones whose display text
        # differs (e.g. last_name suppressed/emitted asymmetrically).
        # Use a single regex sub with a callback so the pass is O(N).
        def _comment_sub(m):
            res = m.group(1)
            new_display = translator_display_names.get(res)
            if new_display is None:
                return m.group(0)
            return f"# geni_profile.{res} {new_display}"

        text = re.sub(
            r'^# geni_profile\.([^ \n]+)\s+[^\n]+$',
            _comment_sub,
            text,
            flags=re.MULTILINE,
        )

        out[tf] = text
    return out


def _apply_to_config(
    cfg_path: Path,
    renames: dict[str, str],
) -> str:
    text = cfg_path.read_text(encoding="utf-8")
    for old, new in sorted(renames.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(f'"{old}"', f'"{new}"')
    return text


def _extra_config_renames(
    cfg_path: Path,
    translator_dir: Path,
) -> dict[str, str]:
    """Find move_list entries that point to per-record res_names NOT
    emitted by the translator, and rename them to the translator's
    per-record res_name when a token-overlap pairing exists.

    These catch cases where legacy moved a profile to consolidated
    (so the per-record res_name is absent from legacy's .tf files
    altogether, but lives only as a string literal in move_list)
    but the translator still emits it per-record under a different
    name (e.g. Андриан → Адриан canonicalization on the first name,
    not visible to the file-pairing step).
    """
    # Collect translator per-record res_names indexed by (date, doc_suffix).
    trans_by_key: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for tf in sorted(translator_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'^resource "geni_profile" "([^"]+)"', text, re.MULTILINE):
            res = m.group(1)
            parts = _split_res_name(res)
            if parts is None:
                continue
            trans_by_key[(parts[0], parts[2])].append((res, parts[1]))

    # Extract all string literals in the config that look like per-record
    # res_names.
    text = cfg_path.read_text(encoding="utf-8")
    keys = re.findall(r'"(_\d{4}_\d{2}_\d{2}_[^"]+)"', text)

    def _first_two_match(old_np: str, new_np: str) -> bool:
        """Require first OR second token to match (first_name OR
        patronymic). Shared surname alone is too weak — different
        people can share a surname."""
        old_toks = old_np.split("_")
        new_toks = new_np.split("_")
        if not old_toks or not new_toks:
            return False
        if old_toks[0] and old_toks[0] == new_toks[0]:
            return True
        if len(old_toks) > 1 and len(new_toks) > 1:
            if old_toks[1] and old_toks[1] == new_toks[1]:
                return True
        return False

    renames: dict[str, str] = {}
    skipped = 0
    for key in set(keys):
        parts = _split_res_name(key)
        if parts is None:
            continue
        date_prefix, old_np, doc_suffix = parts
        candidates = trans_by_key.get((date_prefix, doc_suffix), [])
        if not candidates:
            continue
        # Accept a pairing only if exactly one candidate shares either
        # first_name OR patronymic with the legacy key. Surname-alone
        # overlap rejected to avoid swapping different people who
        # happen to share a family name.
        matches = [
            (res, np) for res, np in candidates
            if _first_two_match(old_np, np) and np != old_np
        ]
        if len(matches) != 1:
            if len(matches) > 1:
                skipped += 1
            continue
        new_res, _new_np = matches[0]
        if new_res != key:
            renames[key] = new_res
    if skipped:
        print(
            f"  skipped {skipped} ambiguous move_list keys "
            f"(multiple first/patr-overlap candidates)",
            file=sys.stderr,
        )
    return renames


def run(village: str, translator_dir: Path, apply: bool,
        docs_only: bool = False) -> int:
    legacy_dir = Path(village) / "terraform" / "geni"
    if not legacy_dir.is_dir():
        print(f"no terraform dir for village {village}", file=sys.stderr)
        return 2
    if not translator_dir.is_dir():
        print(f"translator-dir {translator_dir} not found", file=sys.stderr)
        return 2

    if docs_only:
        renames = _build_doc_rename_map(legacy_dir, translator_dir)
        print(f"document renames (docs-only mode): {len(renames)}",
              file=sys.stderr)
    else:
        renames = _build_rename_map(legacy_dir, translator_dir)
        print(f"profile renames discovered: {len(renames)}", file=sys.stderr)
        # Also rename document res_names (birth_of_*, death_of_*,
        # marriage_of_*) that differ from translator's.
        doc_renames = _build_doc_rename_map(legacy_dir, translator_dir)
        print(f"document renames discovered: {len(doc_renames)}", file=sys.stderr)
        renames.update(doc_renames)

    display_subs = _build_display_name_map(renames, legacy_dir, translator_dir) \
        if renames else {}
    if renames:
        print(
            f"profiles with display-name changes: {len(display_subs)}",
            file=sys.stderr,
        )

    # Pass 2: rename move_list keys that point to per-record profiles
    # NOT emitted by the translator (consolidated-source canonicalization).
    cfg_path = Path(village) / "generate_config_names.py"
    extra_cfg_renames: dict[str, str] = {}
    if cfg_path.is_file() and not docs_only:
        extra_cfg_renames = _extra_config_renames(cfg_path, translator_dir)
        print(
            f"extra move_list-key renames: {len(extra_cfg_renames)}",
            file=sys.stderr,
        )

    if not renames and not extra_cfg_renames:
        return 0

    if not apply:
        print("Dry run — sample Pass-1 renames (first 10):", file=sys.stderr)
        for old, new in list(renames.items())[:10]:
            print(f"  {old} -> {new}", file=sys.stderr)
        print("Dry run — sample Pass-2 renames (first 10):", file=sys.stderr)
        for old, new in list(extra_cfg_renames.items())[:10]:
            print(f"  {old} -> {new}", file=sys.stderr)
        return 0

    trans_displays = _translator_display_names(translator_dir)
    new_files = _apply_to_legacy(
        legacy_dir, renames, display_subs, trans_displays,
    )
    for path, text in new_files.items():
        path.write_text(text, encoding="utf-8")

    if cfg_path.is_file():
        combined = dict(renames)
        combined.update(extra_cfg_renames)
        cfg_text = _apply_to_config(cfg_path, combined)
        cfg_path.write_text(cfg_text, encoding="utf-8")

        # Also rewrite merge-comment lines in consolidated_profiles_*.tf
        # to use the new source res_names.
        for path in legacy_dir.glob("consolidated_profiles_*.tf"):
            text = path.read_text(encoding="utf-8")
            for old, new in sorted(extra_cfg_renames.items(),
                                   key=lambda kv: -len(kv[0])):
                text = re.sub(
                    rf'(?m)^# - {re.escape(old)}\s*$',
                    f"# - {new}",
                    text,
                )
            path.write_text(text, encoding="utf-8")

    print(
        f"Applied: {len(new_files)} .tf files + generate_config_names.py",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--village", required=True)
    ap.add_argument("--translator-dir", type=Path, default=Path("/tmp/tf-out"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--docs-only", action="store_true",
                    help="Only rename document res_names; skip profile + "
                         "move_list cascades (useful when those oscillate).")
    args = ap.parse_args()
    return run(args.village, args.translator_dir, args.apply, args.docs_only)


if __name__ == "__main__":
    sys.exit(main())
