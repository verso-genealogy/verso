#!/usr/bin/env python3
"""The review ratchet: `<village>/unreviewed_on_geni.tsv` (`verso.core.ratchet`).

The list names the unreviewed records already on Geni. Every other
`reviewed=False` record is held, and the list only shrinks.

    python3 -m verso.ru.cli.review_ratchet --village "Глуповы Горы"              # check
    python3 -m verso.ru.cli.review_ratchet --village "Глуповы Горы" --base REF   # + no new line (CI)
    python3 -m verso.ru.cli.review_ratchet --village "Глуповы Горы" --prune      # strike reviewed lines
    python3 -m verso.ru.cli.review_ratchet --village "Глуповы Горы" --drop FILE:FINGERPRINT
    python3 -m verso.ru.cli.review_ratchet --village "Глуповы Горы" --rebind FILE  # edited, kept unreviewed
    python3 -m verso.ru.cli.review_ratchet --village "Глуповы Горы" --seed [--state-file F]

The check fails on every line that does not stand for an unreviewed record of
its file, as it reads now:

* `changed` — the record is gone and an unreviewed record not on the list
  stands in its file: edited without being reviewed. Held, its profiles would
  leave the tree and the next plan destroy them. Review it (Verso «Вычитано»)
  or revert the edit; a review made by hand is acknowledged with `--drop`.
  An edit made WITHOUT a review (a misreading corrected on the
  scan) keeps the record on Geni with `--rebind FILE`: each such line is
  repointed at the record with its own call, number, sex and лист, or refused.
* `missing` — the file is gone or no longer loads. A `git mv` keeps the
  fingerprints: correct the path in the list.
* `stale` — the record is reviewed now; `gone` — the record is gone and
  nothing unreviewed could be it (reviewed with an edit, or deleted). Both are
  the list lagging behind a review, and `--prune` strikes them.
* `added` (with `--base`) — a line the base commit did not have. A rebound line
  is not one: it stands in for a base line of its file that is gone, and the
  base source and this one give the two the same label (`ratchet.rebound`).

`--seed` writes the list once, for a village that has none: an unreviewed
record is listed when the geni_document it emits is in terraform state (read
with `state list` — no refresh, no Geni auth), so «already on Geni» is what
the state says, not what the DSL hopes.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

from verso.core import ratchet
from verso.core.tools import tool
from verso.ru.messages import t


def list_path(village_dir: Path) -> Path:
    return village_dir / ratchet.LIST_FILE


def village_findings(village_dir: Path) -> list[ratchet.Finding]:
    """The findings of every line of the village's list, file by file."""
    from verso.core.pipeline.load import load_module

    out: list[ratchet.Finding] = []
    for file, lines in ratchet.by_file(ratchet.read_list(list_path(village_dir))).items():
        path = village_dir / file
        if not path.is_file():
            out.extend(ratchet.Finding("missing", e, str(t("cli.review_ratchet.file_gone")))
                       for e in lines)
            continue
        try:
            pairs = ratchet.pair(path.read_text(encoding="utf-8"), load_module(path), where=file)
        except Exception as exc:  # a file that does not load holds nobody to the list
            out.extend(ratchet.Finding("missing", e, str(t("cli.review_ratchet.file_unreadable", error=type(exc).__name__, detail=exc)))
                       for e in lines)
            continue
        out.extend(ratchet.check_file(lines, [(ratchet.unreviewed(r), p) for r, p in pairs]))
    return out


def _git_show(ref: str, path: Path) -> str | None:
    proc = subprocess.run(["git", "show", f"{ref}:{path.as_posix()}"], capture_output=True,
                          text=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


def _labels(source: str | None, file: str) -> dict[tuple[str, str], str]:
    """(file, fingerprint) → label for every record call of one file's source."""
    if source is None:
        return {}
    try:
        prints = ratchet.record_prints(source)
    except SyntaxError:
        return {}
    return {(file, p.fingerprint): p.label for p in prints}


def rebound_lines(village_dir: Path, ref: str, base: list[ratchet.Entry],
                  entries: list[ratchet.Entry]) -> list[ratchet.Entry]:
    """The lines `entries` adds over `base` that only repoint a line `--rebind`
    replaced: labelled from the files as they read now and as `ref` has them."""
    new = ratchet.added(base, entries)
    removed = ratchet.added(entries, base)
    label_now: dict[tuple[str, str], str] = {}
    for file in {e.file for e in new} | {e.file for e in removed}:
        path = village_dir / file
        label_now.update(_labels(path.read_text(encoding="utf-8") if path.is_file() else None, file))
    label_base: dict[tuple[str, str], str] = {}
    for file in {e.file for e in removed}:
        for key, label in _labels(_git_show(ref, village_dir / file), file).items():
            if key not in label_now:          # the print is gone from the file now
                label_base[key] = label
    return ratchet.rebound(new, removed, label_now, label_base)


def base_list(village_dir: Path, ref: str) -> list[ratchet.Entry] | None:
    """The list as `ref` has it, or None when `ref` has none (the seeding commit)."""
    rel = list_path(village_dir).as_posix()
    proc = subprocess.run(["git", "show", f"{ref}:{rel}"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    entries = []
    for raw in proc.stdout.splitlines():
        if raw.strip() and not raw.startswith("#"):
            file, fingerprint, label = (raw.split("\t") + ["", ""])[:3]
            entries.append(ratchet.Entry(file, fingerprint, label))
    return entries


def state_documents(village_dir: Path, state_file: str | None) -> set[str]:
    """The geni_document res_names in the village's terraform state."""
    if state_file:
        text = Path(state_file).read_text(encoding="utf-8")
    else:
        module = village_dir / "terraform" / "geni"
        proc = subprocess.run([tool("terraform"), f"-chdir={module}", "state", "list"],
                              capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise SystemExit(f"`terraform state list` failed in {module} — run it where the module "
                             f"is initialised and pass --state-file:\n{proc.stderr.strip()}")
        text = proc.stdout
    prefix = "geni_document."
    return {ln.strip()[len(prefix):] for ln in text.splitlines() if ln.strip().startswith(prefix)}


def seed(village_dir: Path, state_file: str | None) -> int:
    from verso.ru.pipeline.translate import translate_village

    path = list_path(village_dir)
    if ratchet.read_list(path):
        print(t("cli.review_ratchet.seeded_already", path=path), file=sys.stderr)
        return 2
    documents = state_documents(village_dir, state_file)
    seen: list[tuple[str, object, ratchet.RecordPrint]] = []
    gen, _ = translate_village(village_dir, strict=True, admit_all_unreviewed=True, seen=seen)
    named = Counter(gen.document_minted_for(r) for _, r, _ in seen)
    entries: list[ratchet.Entry] = []
    held: Counter[str] = Counter()
    nameless = shared = 0
    for file, record, p in seen:
        doc = gen.document_minted_for(record)
        if doc is None:
            nameless += 1
            held[file] += 1
        elif doc in documents:
            entries.append(ratchet.Entry(file, p.fingerprint, p.label))
            shared += named[doc] > 1
        else:
            held[file] += 1
    if entries:
        path.write_text(ratchet.format_list(entries, ratchet.read_header(path)), encoding="utf-8")
    print(t("cli.review_ratchet.seeded", village=village_dir.name, unreviewed=len(seen), listed=len(entries), list_name=path.name, held=sum(held.values())))
    if nameless:
        print(t("cli.review_ratchet.nameless", nameless=nameless))
    if shared:
        print(t("cli.review_ratchet.shared_name", count=shared))
    for file, n in sorted(held.items()):
        print(t("cli.review_ratchet.held_in_file", file=file, n=n))
    return 0


def rebind(village_dir: Path, path: Path, entries: list[ratchet.Entry], files: list[str]) -> int:
    """Repoint each named file's `changed` lines (`ratchet.rebind`); write the
    list only when every one of them found its record."""
    from verso.core.pipeline.load import load_module

    lines = ratchet.by_file(entries)
    out = list(entries)
    refused: list[ratchet.Finding] = []
    moved = 0
    for file in files:
        dsl = village_dir / file
        if file not in lines or not dsl.is_file():
            print(t("cli.review_ratchet.no_lines_of_file", file=file), file=sys.stderr)
            return 2
        pairs = ratchet.pair(dsl.read_text(encoding="utf-8"), load_module(dsl), where=file)
        mine, why = ratchet.rebind(lines[file], [(ratchet.unreviewed(r), p) for r, p in pairs])
        refused += why
        swap = iter(mine)
        out = [next(swap) if e.file == file else e for e in out]
        moved += sum(a.fingerprint != b.fingerprint for a, b in zip(lines[file], mine, strict=True))
    if refused:
        report(refused)
        print(t("cli.review_ratchet.nothing_rebound"), file=sys.stderr)
        return 1
    path.write_text(ratchet.format_list(out, ratchet.read_header(path)), encoding="utf-8")
    print(t("cli.review_ratchet.rebound", village=village_dir.name, moved=moved))
    return 0


def report(findings: list[ratchet.Finding]) -> None:
    for f in findings:
        e = f.entry
        print(f"{f.kind:8} {e.file}  {e.label}  [{e.fingerprint}] — {f.note}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--village", required=True)
    ap.add_argument("--base", help="fail on a line this git ref's list does not have")
    ap.add_argument("--prune", action="store_true",
                    help="strike the lines whose record is reviewed or gone (stale, gone)")
    ap.add_argument("--drop", action="append", default=[], metavar="FILE:FINGERPRINT",
                    help="strike one line by hand — a record reviewed by hand with an edit")
    ap.add_argument("--rebind", action="append", default=[], metavar="FILE",
                    help="repoint the file's changed lines at the records edited without a review")
    ap.add_argument("--seed", action="store_true", help="write the list once, from terraform state")
    ap.add_argument("--state-file", help="a `terraform state list` dump for --seed")
    args = ap.parse_args(argv)

    village_dir = Path(args.village)
    if args.seed:
        return seed(village_dir, args.state_file)

    path = list_path(village_dir)
    entries = ratchet.read_list(path)
    if args.rebind:
        code = rebind(village_dir, path, entries, args.rebind)
        if code:
            return code
        entries = ratchet.read_list(path)
    if args.prune or args.drop:
        gone: Counter[tuple[str, str]] = Counter()
        for spec in args.drop:
            file, _, fingerprint = spec.rpartition(":")
            if not any(e.file == file and e.fingerprint == fingerprint for e in entries):
                print(t("cli.review_ratchet.no_line", spec=spec), file=sys.stderr)
                return 2
            gone[(file, fingerprint)] += 1
        if args.prune:
            for f in village_findings(village_dir):
                if f.prunable:
                    gone[(f.entry.file, f.entry.fingerprint)] += 1
        kept = ratchet.drop(entries, gone)
        if len(kept) != len(entries):
            path.write_text(ratchet.format_list(kept, ratchet.read_header(path)), encoding="utf-8")
        print(t("cli.review_ratchet.pruned", village=village_dir.name, struck=len(entries) - len(kept), left=len(kept)))
        entries = kept

    findings = village_findings(village_dir) if entries else []
    if args.base:
        base = base_list(village_dir, args.base)
        if base is not None:
            kept = Counter((e.file, e.fingerprint)
                           for e in rebound_lines(village_dir, args.base, base, entries))
            for e in ratchet.added(base, entries):
                if kept[(e.file, e.fingerprint)] > 0:
                    kept[(e.file, e.fingerprint)] -= 1
                    continue
                findings.append(ratchet.Finding("added", e, str(t("cli.review_ratchet.line_not_in_base", base=args.base))))
    if not findings:
        print(t("cli.review_ratchet.ok", village=village_dir.name, count=len(entries)))
        return 0
    report(findings)
    if all(f.prunable for f in findings):
        print(t("cli.review_ratchet.behind", village=village_dir.name))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
