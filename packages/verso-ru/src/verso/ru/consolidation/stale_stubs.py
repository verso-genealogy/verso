#!/usr/bin/env python3
"""CST001/CST002 — consolidation-config entries that name a record the DSL no
longer produces.

`generate_config_names.py` folds per-record stubs into canonical profiles by
res_name. A res_name is DERIVED from the DSL (year, person, record kind, census
household…), so any DSL edit that changes one strands the config entry pointing
at it. Nothing complained: an entry that matches no record simply folds
nothing, so the tree quietly grows the duplicates the entry existed to remove.

Two live incidents were sitting in the repo when this check was written:

  * Заманиловка — 166 references, after `household(None, …)` was replaced with
    the source's own family number (`rs_4_1` → `rs_525_1`). This one at least
    failed loudly downstream, because a stale *kin* key raises
    KinResolutionError; the 108 config-side references did not (fixed).
  * Горюхино — 98 references (58 profile, 40 union), plus 2 in Маниловка.
    Baselined, not yet triaged: re-pointing them changes canonical addresses on
    an APPLIED village, so each needs a moved/removed block.

Detection is exact rather than heuristic: the translator's `Consolidation`
records which config keys actually MATCHED a produced res_name (including via
its spelling aliases and the stripped-last-name fallback, both reported as the
original config spelling). A declared entry absent from that set matched
nothing. So this check costs one full translation per village and cannot drift
from the resolution rules it is checking — unlike `lint_config` (CCN), which is
deliberately static and corpus-blind.

That exactness is the whole point, and it is not pedantry: a first pass done by
grepping res_name-shaped tokens out of the config and diffing them against the
corpus claimed 638 stale entries in Горюхино and 8 in Нижняя Яичница. Both
figures were wrong — the pattern truncated names carrying an archive suffix
(`…_family_member_746-8-140`) at the hyphen, and it could not see that the
resolver's alias/stripped fallbacks match many keys that differ literally. The
real counts are 98 and 0.

Known-stale entries are parked in `<village>/consolidation_stale_baseline.txt`
so the existing debt does not block CI while still being counted; anything new
fails. Shrink a baseline by fixing entries and re-running with
`--update-baseline`.

Run:
    python3 -m verso.ru.consolidation.stale_stubs --village Заманиловка
    python3 -m verso.ru.consolidation.stale_stubs --village Горюхино --update-baseline
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

BASELINE_NAME = "consolidation_stale_baseline.txt"

_BASELINE_HEADER = """\
# Consolidation-config entries that match no record the DSL produces (CST001 /
# CST002 — see verso/ru/consolidation/stale_stubs.py). Each one folds nothing, so
# the duplicate it was written to remove is still in the tree.
#
# This file is a BASELINE of pre-existing debt, not an allowlist of things that
# are fine: entries here are bugs waiting to be triaged. Fix some, then
# regenerate with:
#   verso stale-stubs --village <village> --update-baseline
# Anything NOT listed here fails the check.
"""


class Finding(NamedTuple):
    code: str        # CST001 (profile stub) / CST002 (union stub)
    ref: str         # the stale res_name
    where: str       # the config construct that declares it

    def line(self) -> str:
        return f"[{self.code}] {self.ref} — declared in {self.where}, matches no record"


def _load_config(village: str) -> Any:
    """`<village>/generate_config_names.py`, loaded fresh (`verso.core.pipeline.config`)."""
    from verso.core.pipeline.config import CONFIG_FILE, load_config
    return load_config(Path(village) / CONFIG_FILE)


def declared_references(gcn: Any) -> tuple[dict[str, str], dict[str, str]]:
    """`(profile_stub -> where, union_stub -> where)` declared by the config.

    Canonical TARGETS are deliberately not collected: a cluster key may be a
    synthetic name (`grigorij_ivanovich_chichikov`) that no record produces —
    that is the normal shape of a multi-stub cluster, not an error.
    """
    profiles: dict[str, str] = {}
    for target, entry in getattr(gcn, "profiles_to_consolidate", {}).items():
        if not isinstance(entry, dict):
            continue
        for stub in entry.get("profile_names", []) or []:
            if isinstance(stub, str):
                profiles.setdefault(
                    stub, f'profiles_to_consolidate["{target}"].profile_names')
    for stub in getattr(gcn, "profile_move_list", {}):
        profiles.setdefault(stub, "profile_move_list")

    unions: dict[str, str] = {}
    # union_move_list_v2 is itself built from unions_to_consolidate's
    # `union_names` lists, so its keys cover both constructs.
    for stub in getattr(gcn, "union_move_list_v2", {}):
        unions.setdefault(stub, "union_move_list_v2 / unions_to_consolidate.union_names")
    return profiles, unions


def findings_for(gcn: Any, cons: Any) -> list[Finding]:
    """The stale entries `gcn` declares, given the `Consolidation` that ran.

    Split out of `find_stale` so a caller holding a FINISHED translation can
    ask the question for free. `generate_tf` is one: it has just built the
    tree the stale entry silently left a duplicate in, and running the check
    there reports it in the same command instead of a CI round-trip later.
    """
    if cons is None:
        return []
    profiles, unions = declared_references(gcn)
    findings = [
        Finding("CST001", ref, where)
        for ref, where in sorted(profiles.items())
        if ref not in cons.hit_profile_keys
    ]
    findings += [
        Finding("CST002", ref, where)
        for ref, where in sorted(unions.items())
        if ref not in cons.hit_union_keys
    ]
    return findings


def find_stale(village: str, corpora: dict[str, set[str]] | None = None) -> list[Finding]:
    """Translate the village and report declared entries that matched nothing.

    When `corpora` is given it is filled with the produced `"profiles"` /
    `"unions"` res_names, so `--suggest` does not pay for a second translation.
    """
    from verso.ru.pipeline.translate import translate_village

    gcn = _load_config(village)
    gen, _ = translate_village(village, strict=True)
    if corpora is not None:
        corpora["profiles"] = set(gen.canonical_profiles())
        corpora["unions"] = set(gen.canonical_unions())
    return findings_for(gcn, getattr(gen, "consolidation", None))


# The document anchor inside a res_name: `_mk_births_` / `_mk_marriages_` /
# `_mk_deaths_` / `_rs_`. Everything from here on identifies the RECORD (its
# number, the person's role in it, any archive suffix); everything before it is
# the date and the person's name.
_ANCHOR = re.compile(r'_(?:mk_(?:births|marriages|deaths)|rs)_')


def _split(res_name: str) -> tuple[str, str, str] | None:
    """`(date_prefix, name_segment, record_tail)`, or None without an anchor.

    `_1834_02_20_ivan_petrovich_rs_25_24_family_member`
     →  `_1834_02_20`, `_ivan_petrovich`, `_rs_25_24_family_member`
    """
    m = _ANCHOR.search(res_name)
    if not m:
        return None
    return res_name[:11], res_name[11:m.start()], res_name[m.start():]


def _record_tail(union_res_name: str) -> str:
    """A union res_name's trailing record marker — `_2_1909`, `_d13_1880`,
    `rs60_1850`. Unions have no `_mk_`/`_rs_` anchor, so this is what pins a
    candidate to the same record."""
    return "_".join(union_res_name.split("_")[-2:])


def _suggest_union(ref: str, corpus: set[str]) -> str | None:
    """Union analogue of `suggest`: same trailing record marker, and the two
    names differ by at most one token.

    A union res_name is built from both partners' names, so it moves whenever
    either of them does — a wife gaining her married surname
    (`…_maria_petrovna_2_1909` → `…_maria_petrovna_sidorova_2_1909`) or
    a patronymic being re-read (`ivan_petrovich_rs60_1850` →
    `ivan_pavlovich_rs60_1850`). Requiring the record marker to match
    exactly is what keeps that from turning into a guess about which couple.
    """
    tail = _record_tail(ref)
    ref_tokens = set(ref.split("_"))
    hits = [c for c in corpus
            if _record_tail(c) == tail and len(ref_tokens ^ set(c.split("_"))) <= 2]
    return hits[0] if len(hits) == 1 else None


def suggest(ref: str, corpus: set[str]) -> str | None:
    """The res_name `ref` most likely became, or None when it is not obvious.

    A res_name is `<date><name><record tail>`. Only ONE of the three parts is
    ever allowed to differ, and only when the answer is unique — pointing a
    fold at the wrong record is worse than not folding, so anything vaguer
    yields None:

      1. the NAME changed, date and record identical — the person's spelling
         was canonicalised («Исай»→«Исаия», «Астапович»→«Остапович»,
         «Василеевна»→«Василевна»);
      2. the DATE changed, name and record identical — a census that used to
         emit a bare `_YYYY_00_00_` prefix gained its real date
         (`_1834_00_00_aleksej_rs_85_12…` → `_1834_02_20_aleksej_rs_85_12…`).
         The year must still match; only the month/day may fill in.

    Rule 2 exists because rule 1 alone silently mis-classified 18 Горюхино
    entries as unrepairable: they are the same person in the same census slot,
    so they are LOST FOLDS (the duplicate is live in the tree), not dead text.
    """
    parts = _split(ref)
    if parts is None:
        return _suggest_union(ref, corpus)
    date, name, tail = parts
    rules: tuple[Callable[[str, str, str], bool], ...] = (
        # 1: the name varies, date and record identical
        lambda d, n, t: d == date and t == tail,
        # 2: the date fills in, year/name/record identical
        lambda d, n, t: d[:5] == date[:5] and n == name and t == tail,
    )
    for match in rules:
        hits = [c for c in corpus
                if (p := _split(c)) is not None and match(*p)]
        if len(hits) == 1:
            return hits[0]
    return None


def baseline_path(village: str) -> Path:
    return Path(village) / BASELINE_NAME


def load_baseline(village: str) -> set[str]:
    p = baseline_path(village)
    if not p.is_file():
        return set()
    return {
        ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    }


def write_baseline(village: str, findings: list[Finding]) -> Path:
    p = baseline_path(village)
    body = "".join(f"{f.ref}\n" for f in sorted(findings))
    p.write_text(_BASELINE_HEADER + body, encoding="utf-8")
    return p


def format_report(village: str, new: list[Finding], baselined: int) -> str:
    """The stderr block for NEW stale entries, or "" when there are none.

    Shared with `generate_tf`, so the warning a reader sees while regenerating
    reads the same as the one CI fails on.
    """
    if not new:
        return ""
    lines = [f"\nSTALE consolidation entries in {village} "
             f"({len(new)} new, {baselined} baselined):\n"]
    lines += [f"  {f.line()}" for f in new]
    lines.append(
        "\nEach of these folds nothing, so the duplicate it targets stays in the "
        "tree.\nUsually a DSL edit changed the record's res_name: re-point the "
        "entry at the\ncurrent name (and add a moved/removed block if the village "
        "is already applied)."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--village", required=True)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--update-baseline", action="store_true",
                    help="rewrite the village's baseline from the current findings")
    ap.add_argument("--suggest", action="store_true",
                    help="for every stale entry (baselined ones too), print the "
                         "res_name it most likely became — a triage worklist")
    args = ap.parse_args(argv)

    corpora: dict[str, set[str]] = {}
    findings = find_stale(args.village, corpora if args.suggest else None)

    if args.suggest:
        # Match against the RAW (unconsolidated) corpus: a stale entry's
        # counterpart is usually itself folded, so it is absent from the
        # consolidated set and every question would look unanswerable.
        from verso.ru.pipeline.translate import translate_village
        raw_gen, _ = translate_village(args.village, use_consolidation=False)
        raw = {"CST001": set(raw_gen.canonical_profiles()),
               "CST002": set(raw_gen.canonical_unions())}
        # Folded or not is decided by the CONSOLIDATED corpus, not by whether
        # some construct mentions the counterpart: a union is also consolidated
        # implicitly when a partner is folded (no `union_move_list_v2` entry
        # involved), so "is it declared" answers the wrong question. Absent
        # from the consolidated set ⇒ something folded it.
        consolidated = {"CST001": corpora["profiles"], "CST002": corpora["unions"]}
        verdicts: collections.Counter[str] = collections.Counter()
        for f in findings:
            s = suggest(f.ref, raw[f.code])
            if s is None:
                verdict = "no-counterpart"
            elif s in consolidated[f.code]:
                verdict = "LOST-FOLD"      # stands alone → the duplicate is live
            else:
                verdict = "dead-text"      # already folded → the entry is redundant
            verdicts[verdict] += 1
            print(f"{f.code}\t{verdict}\t{f.ref}\t{s or '?'}")
        print(f"\n{args.village}: " + ", ".join(
            f"{v} {k}" for k, v in verdicts.most_common()), file=sys.stderr)
        print("  dead-text     — the same record is already folded under its "
              "current name; the entry is redundant\n"
              "  LOST-FOLD     — the counterpart is folded by nobody, so the "
              "duplicate is live in the tree\n"
              "  no-counterpart— no unambiguous same-record match; needs a human",
              file=sys.stderr)
        return 0

    if args.update_baseline:
        p = write_baseline(args.village, findings)
        print(f"{args.village}: baseline rewritten with {len(findings)} entries → {p}")
        return 0

    baseline = load_baseline(args.village)
    new = [f for f in findings if f.ref not in baseline]
    fixed = sorted(baseline - {f.ref for f in findings})

    if args.json:
        print(json.dumps({
            "village": args.village,
            "total": len(findings),
            "baselined": len(findings) - len(new),
            "new": [f._asdict() for f in new],
            "fixed": fixed,
        }, ensure_ascii=False))
        return 1 if new else 0

    if fixed:
        print(f"{args.village}: {len(fixed)} baselined entr"
              f"{'y is' if len(fixed) == 1 else 'ies are'} no longer stale — "
              f"re-run with --update-baseline to shrink the baseline.")
    if not new:
        print(f"{args.village}: no new stale consolidation entries "
              f"({len(findings)} baselined).")
        return 0

    print(format_report(args.village, new, len(findings) - len(new)),
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
