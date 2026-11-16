#!/usr/bin/env python3
"""Fail when a GENERATED artifact is stale with respect to its DSL source.

Three independent checks:

  * TF tree  — regenerate <village>/terraform/geni/ into a temp dir, `terraform
    fmt` it, and diff against what is committed.
  * CSVs     — re-run each DSL year file in a temp mirror and diff every CSV
    committed in a year directory (the familio and the census exporters'
    output) against what it writes.
  * familio  — same as the TF tree, for <village>/terraform/familio/.

This exists because CI's generate guards wrote to $RUNNER_TEMP and only asserted
that generation SUCCEEDS — nothing compared the result to the committed tree. A
DSL commit without `verso generate-tf` was therefore CI-green, and the stale tree
silently rotted until an apply turned it into destroys.

"Committed" means git's index, via `committed_tf_names` / `committed_csvs` —
NOT a directory glob. The distinction is the whole point: an untracked file is
present locally and absent in CI, so globbing makes the same tree pass here and
fail there.

NOTE: "stale" (a generated artifact out of date with its source) is NOT the same
as "drift" (`verso drift`: someone edited the tree on geni.com). The two names
mean different things; do not conflate them.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from verso.core.workspace import child_env
from verso.core.targets.geni.fmt import terraform_fmt

# Filenames the generator OWNS. Anything else committed in terraform/geni/ is
# hand-maintained (main.tf, projects.tf, managed.tf, _moved_manual_*.tf,
# _moved_renames.tf, _moved_auto_renames.tf, ...) and is not our business — the
# generator never emits it, so it drops out of the comparison automatically.
# NB: `_moved_consolidated_profiles.tf` IS generated (from profiles_to_consolidate),
# but `_moved_consolidated_unions.tf` is NOT — its own header says "`generate` does
# NOT emit this file". Union moved/removed blocks are hand-authored. So the prefix
# must be the exact profiles filename, not `_moved_consolidated_`.
# NB: `ir_` is the исповедная роспись's own prefix: `CONFESSION_LIST` pins
# `file_prefix="ir"` (verso/ru/dsl/records/census.py) so a confession list cannot
# collide with a ревизская сказка of the same year. Only the LEFTOVER branch of
# `tf_stale` consults this tuple — an uncommitted or changed file is caught by
# name whatever its prefix — so leaving `ir_` out meant a confession-list file
# whose DSL was deleted, renamed or un-reviewed sat in the tree forever with
# the check reporting OK.
GENERATED_PREFIXES: tuple[str, ...] = (
    "mk_", "rs_", "ir_", "ext_", "list_",
    "consolidated_profiles", "consolidated_unions",
    "_moved_consolidated_profiles",
)

YEAR_DIR = re.compile(r"^\d{4}$")


def _is_generated(name: str) -> bool:
    return name.endswith(".tf") and name.startswith(GENERATED_PREFIXES)


def _same_content(a: Path, b: Path) -> bool:
    """Compare two files the way git stores them — with CRLF normalised to LF.

    `core.autocrlf = input`, so git strips CR when it stores a text file. The
    exporters, however, REPRODUCE it: csv.writer emits \\r\\n, which survives
    inside quoted multi-line fields (a record comment). A fresh CI checkout
    therefore has LF on disk while regeneration produces CRLF, and a raw byte
    compare would flag every such file as stale on every run — a permanently
    red CI. Normalising both sides reproduces git's own comparison.
    """
    return (a.read_bytes().replace(b"\r\n", b"\n")
            == b.read_bytes().replace(b"\r\n", b"\n"))


def _git_tracked(directory: Path) -> set[Path] | None:
    """Every path git STORES under `directory`, relative to it.

    None when git is unavailable or `directory` is not in a repository (a
    tarball, a temp mirror) — there the working tree is the only answer there
    is, and the caller globs. `-C` makes git print the paths relative to
    `directory`, whatever the process's CWD. `-z` both NUL-separates and
    suppresses `core.quotePath` escaping, without which every Cyrillic village
    path would come back as `"\\320\\232..."` and match nothing.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(directory), "ls-files", "-z", "--", "."],
            capture_output=True, check=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {Path(e) for e in out.split("\0") if e}


def committed_tf_names(directory: Path) -> set[str]:
    """The `.tf` filenames git actually STORES directly in `directory`.

    Every check here says "committed", and that has to mean the index, not the
    working tree. Globbing the directory made an untracked-but-present file
    count as committed: a generated `mk_YYYY_birth.tf` — real output of a
    partially-reviewed year — sat unstaged for weeks while `verso stale`
    reported OK, because the file the check was looking for was right there on
    disk. CI caught it only by
    accident: a fresh checkout has no untracked files, so the same code
    happened to compute the right answer there. That is a guard passing
    locally and failing in CI for the same tree — the opposite of useful.

    Only entries directly in `directory` count; `git ls-files` recurses, and
    terraform/geni/ has a `scans/` subdirectory under it. Falls back to
    globbing outside a repository (see `_git_tracked`).
    """
    tracked = _git_tracked(directory)
    if tracked is None:
        return {p.name for p in directory.glob("*.tf")}
    return {p.name for p in tracked if p.suffix == ".tf" and len(p.parts) == 1}


def tf_stale(village: str, tf_dir: Path, fresh_dir: Path,
             committed: set[str] | None = None) -> list[str]:
    """Messages describing how the committed tree differs from fresh output.

    `committed` defaults to what git stores in `tf_dir` (see
    `committed_tf_names`); pass it explicitly to compare against a known set.
    """
    msgs: list[str] = []
    fresh = {p.name for p in fresh_dir.glob("*.tf")}
    if committed is None:
        committed = committed_tf_names(tf_dir)

    for name in sorted(fresh):
        if name not in committed:
            msgs.append(f"{village}: {name} is generated but NOT committed")
        elif not (tf_dir / name).exists():
            msgs.append(
                f"{village}: {name} is committed but missing from the working "
                f"tree (deleted without regenerating?)")
        elif not _same_content(fresh_dir / name, tf_dir / name):
            msgs.append(
                f"{village}: {name} differs from the DSL (committed tree is stale)")

    for name in sorted(committed - fresh):
        if _is_generated(name):
            msgs.append(
                f"{village}: {name} is committed but no longer generated "
                f"(leftover from deleted/renamed DSL)")
    return msgs


def check_tf(village: str, py: str = sys.executable) -> list[str]:
    """Regenerate the village's TF tree into a temp dir and diff it."""
    tf_dir = Path(village) / "terraform" / "geni"
    if not tf_dir.is_dir():
        return []  # not a TF village
    with TemporaryDirectory() as td:
        fresh = Path(td)
        subprocess.run(
            [py, "-m", "verso.ru.cli.generate_tf", "--village", village,
             "--strict", "--fail-on-conflicts", "--output-dir", str(fresh)],
            check=True, capture_output=True, text=True, env=child_env(),
        )
        terraform_fmt(fresh, check=True)
        return tf_stale(village, tf_dir, fresh)


# Filenames the FAMILIO generator owns, under <village>/terraform/familio/.
# Everything else there is hand-maintained (main.tf, _moved_*.tf).
FAMILIO_GENERATED_PREFIXES: tuple[str, ...] = ("familio_",)


def _is_familio_generated(name: str) -> bool:
    return name.endswith(".tf") and name.startswith(FAMILIO_GENERATED_PREFIXES)


def check_familio(village: str, py: str = sys.executable) -> list[str]:
    """Regenerate the village's familio module into a temp dir and diff it.

    Same guard as `check_tf`, for the second publishing target. CI only ever
    asserted that `generate_familio_tf` SUCCEEDS, never that its output matches
    what is committed — so the familio trees rotted unnoticed: a marker leak in
    `verso.ru.familio.projection` silently degraded every shared marriage comment
    to a one-sided «жених»/«невеста» half, and nothing went red because no
    committed familio file was ever compared to fresh output.
    """
    fam_dir = Path(village) / "terraform" / "familio"
    if not fam_dir.is_dir():
        return []  # not a familio village
    with TemporaryDirectory() as td:
        fresh = Path(td)
        subprocess.run(
            [py, "-m", "verso.ru.cli.generate_familio_tf", "--village", village,
             "--strict", "--output-dir", str(fresh)],
            check=True, capture_output=True, text=True, env=child_env(),
        )
        terraform_fmt(fresh, check=True)
        msgs: list[str] = []
        fresh_names = {p.name for p in fresh.glob("*.tf")}
        # git's index, not the glob — same reasoning as `committed_tf_names`.
        committed = committed_tf_names(fam_dir)
        for name in sorted(fresh_names):
            if name not in committed:
                msgs.append(f"{village}: familio/{name} is generated but NOT committed")
            elif not (fam_dir / name).exists():
                msgs.append(
                    f"{village}: familio/{name} is committed but missing from "
                    f"the working tree (deleted without regenerating?)")
            elif not _same_content(fresh / name, fam_dir / name):
                msgs.append(
                    f"{village}: familio/{name} differs from the DSL "
                    f"(committed module is stale)")
        for name in sorted(committed - fresh_names):
            if _is_familio_generated(name):
                msgs.append(
                    f"{village}: familio/{name} is committed but no longer generated")
        return msgs


def committed_csvs(village: Path) -> set[Path]:
    """The CSVs git STORES in the village's year directories, relative to it.

    A year directory holds the DSL year files and what their `__main__` exports
    — `check_csv` runs each one there — so every CSV committed in one is
    exporter output, whatever exporter wrote it: `*_familio.csv` and the census
    / confession-list `*_census[_<suffix>].csv`, 932 and 38 files on 2026-10-13
    and nothing else. A hand-curated CSV lives elsewhere
    (`familio_submissions/location.csv`) and is not compared.

    Until 2026-10-13 the check globbed `*_familio.csv` alone, so no census CSV
    was ever compared: nine had drifted from their DSL (Глуповы Горы 1838
    noticed by hand after a Verso proofread, eight more when this ran first) and
    seven were leftovers of the `archive_suffix` rename — the exporter has
    written `<village>_<year>_census_<suffix>.csv` since 2026-06-18. A list of
    the exporters' name shapes would leave the same hole for the next exporter;
    keying on the year directory does not.

    Git's index, not the working tree — see `committed_tf_names`; falls back to
    globbing outside a repository.
    """
    tracked = _git_tracked(village)
    if tracked is None:
        tracked = {p.relative_to(village) for p in village.glob("*/*.csv")}
    return {p for p in tracked
            if p.suffix == ".csv" and len(p.parts) == 2 and YEAR_DIR.match(p.parts[0])}


def csv_stale(village_dir: str, mirror: Path,
              committed: set[Path] | None = None) -> list[str]:
    """Compare the village's COMMITTED CSVs against freshly generated ones.

    Unlike the TF tree — where every generated file must be committed — the CSV
    set is a CURATED SUBSET. Familio CSVs are committed for the years actually
    submitted to Familio (e.g. Горюхино covers 1754-1861), census CSVs for some
    rolls only, while other DSL years have no committed CSV at all. So
    "generated but not committed" is normal and is NOT reported. We only check
    that what IS committed still matches its DSL.

    `committed` defaults to what git stores in the village's year directories
    (see `committed_csvs`), as paths relative to the village.
    """
    msgs: list[str] = []
    village = Path(village_dir)
    if committed is None:
        committed = committed_csvs(village)
    for rel in sorted(committed):
        produced = mirror / rel
        if not produced.exists():
            msgs.append(
                f"{village.name}: {rel} is committed but no longer generated "
                f"(leftover from deleted/renamed DSL)")
        elif not (village / rel).exists():
            msgs.append(
                f"{village.name}: {rel} is committed but missing from the "
                f"working tree (deleted without regenerating?)")
        elif not _same_content(produced, village / rel):
            msgs.append(
                f"{village.name}: {rel} differs from the DSL (committed CSV is stale)")
    return msgs


def check_csv(village: str) -> list[str]:
    """Write the village's CSVs into a temporary directory (`verso export-csv`'s
    `export_village`); diff them with the committed ones.

    Until 0.1.0 this ran each year file's own `__main__` from a mirror, chdir-ing into it
    — some census files exported into whatever directory they inherited. `export-csv`
    writes where it is told and reads the files in place, so nothing is copied and no
    directory changes."""
    from verso.ru.cli.export_csv import export_village
    village_dir = Path(village).resolve()
    if not any(d.is_dir() and YEAR_DIR.match(d.name) for d in village_dir.iterdir()):
        return []
    with TemporaryDirectory() as td:
        mirror = Path(td)
        export_village(village_dir, mirror)
        return csv_stale(str(village_dir), mirror)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fail if a generated artifact is stale vs its DSL source.")
    ap.add_argument("--village", required=True)
    ap.add_argument("--tf", action="store_true", help="check the terraform tree only")
    ap.add_argument("--csv", action="store_true",
                    help="check the committed CSVs (familio, census) only")
    ap.add_argument("--familio", action="store_true",
                    help="check the terraform/familio module only")
    args = ap.parse_args(argv)

    both = not (args.tf or args.csv or args.familio)
    msgs: list[str] = []
    if args.tf or both:
        msgs += check_tf(args.village)
    if args.csv or both:
        msgs += check_csv(args.village)
    if args.familio or both:
        msgs += check_familio(args.village)

    if not msgs:
        print(f"{args.village}: generated output is up to date.")
        return 0

    print(f"\nSTALE generated output in {args.village}:\n", file=sys.stderr)
    for m in msgs:
        print(f"  {m}", file=sys.stderr)
    print("\nThe DSL is the source of truth — regenerate and commit:", file=sys.stderr)
    print(f'  verso generate-tf --village "{args.village}"'
          "                    # terraform tree", file=sys.stderr)
    print(f'  make generate_csv village="{args.village}" year=YYYY'
          "        # CSVs", file=sys.stderr)
    print(f'  verso generate-familio-tf --village "{args.village}"'
          "            # familio module", file=sys.stderr)
    print("  git add -A && git commit", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
