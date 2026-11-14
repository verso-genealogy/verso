#!/usr/bin/env python3
"""Drive a village's terraform tree to convergence: plan → gate → apply → repeat.

A single `terraform apply` against Geni rarely lands everything. The API rate-limits
and Incapsula-blocks partway through a large run, so the normal shape is
apply → re-plan → apply again, two or three times, until the plan reports
"No changes". Doing that by hand is ~8 steps per village and is easy to misread: a
provider error whose write actually succeeded looks like a failure, and a plan full
of `document_replace` looks like data loss when it is really a missing
`document_sync` pass.

This module encodes that loop, and — more importantly — the two classifications that
make it terminate:

**verify_plan `kind`** decides whether the loop may proceed at all. `document_replace`
is the ONE auto-fixable category (push the text via `document_sync`, which collapses
the replace into an in-place update). Every other category — `profile_delete`,
`union_delete_with_children`, `union_shared_id`, `multi_parent_child`,
`field_erasure` — means a live Geni resource would be destroyed, a conflict created or
a value Geni holds emptied, and needs a human decision. Those halt the loop. Neither
`force=1` nor `erase_ok=1` is ever passed.

**Apply-error class** decides whether retrying is worthwhile. 429 / Incapsula / 500
are transient and converge on re-plan. `access denied` is permanent — a profile
another Geni user manages, which no amount of retrying will fix — and without
recognising it the loop would spin until it hit the round cap.

Run:
    python3 -m verso.ru.consolidation.apply_converge --village Горюхино
    verso apply-converge --village Горюхино
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from verso.ru.consolidation.plan import plan_paths
from verso.core.workspace import child_env
from verso.core.tools import tool

# The single auto-fixable gate category: the document text changed, which
# force-replaces the doc (losing its Geni id) unless pushed via the AJAX endpoint
# first. Everything else in verify_plan means possible data loss.
AUTO_FIXABLE = {"document_replace"}

# Provider failures worth retrying — the write may even have landed already
# (e.g. an Incapsula error whose profile update was in fact applied, so the very
# next plan reported "No changes").
TRANSIENT_PATTERNS = (
    re.compile(r"received 429 status"),
    re.compile(r"received 5\d\d status"),
    re.compile(r"incapsula blocked request"),
    re.compile(r"\btimeout\b"),
)

# Permanent failures: the profile is managed by another Geni user, so linking it to
# our project is refused no matter how often we retry.
PERMANENT_PATTERNS = (
    re.compile(r"access denied"),
    re.compile(r"not authorized"),
)

_NO_CHANGES = "No changes."


@dataclass
class ApplyOutcome:
    returncode: int
    transient: int
    permanent: list[str]

    @property
    def clean(self) -> bool:
        return self.returncode == 0 and not self.permanent


def classify_apply_output(text: str) -> tuple[int, list[str]]:
    """(transient_count, permanent_messages) for one apply's output.

    The provider prints its retry ladder as `#1: ...` / `#2: ...` under an
    `All attempts fail:` header, so a single logical failure contributes several
    lines; counting lines is fine for the transient tally (it is only used to
    decide "worth another round?") but permanent hits are de-duplicated because
    they are reported to the user.
    """
    transient = 0
    permanent: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lower()
        if any(p.search(line) for p in PERMANENT_PATTERNS):
            if raw.strip() not in permanent:
                permanent.append(raw.strip())
        elif any(p.search(line) for p in TRANSIENT_PATTERNS):
            transient += 1
    return transient, permanent


def gate_decision(violations: list[dict[str, object]]) -> tuple[str, set[str]]:
    """('ok' | 'sync' | 'halt', kinds) from verify_plan --json output."""
    kinds = {str(v["kind"]) for v in violations if v.get("severity") == "error"}
    if not kinds:
        return "ok", kinds
    if kinds <= AUTO_FIXABLE:
        return "sync", kinds
    return "halt", kinds


def _stream(cmd: list[str], log: Path | None) -> tuple[int, str]:
    """Run `cmd`, echoing each line as it arrives; return (rc, full output).

    Streamed rather than captured: a Горюхино apply runs ~40 minutes and prints
    thousands of lines, and going silent for that long is unusable. Never pipe this
    through `tail` — a closed pipe is the documented way to break an apply midway.
    """
    print(f"    $ {' '.join(cmd)}", flush=True)
    chunks: list[str] = []
    handle = log.open("a", encoding="utf-8") if log else None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=child_env(),
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            chunks.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()
            if handle:
                handle.write(line)
        proc.wait()
        return proc.returncode, "".join(chunks)
    finally:
        if handle:
            handle.close()


def converge(village: str, max_rounds: int = 5, log_dir: Path | None = None) -> int:
    paths = plan_paths(Path(village).resolve())
    tf_dir, tf = str(paths.tf_dir), tool("terraform")
    log = (log_dir / f"{village}-converge.log") if log_dir else None

    for rnd in range(1, max_rounds + 1):
        print(f"\n=== round {rnd}/{max_rounds} — {village} ===", flush=True)

        rc, out = _stream([tf, f"-chdir={tf_dir}", "plan",
                           "-parallelism=200", "-out", ".plan"], log)
        if rc != 0:
            print(f"\nplan failed (rc={rc}) — stopping.", file=sys.stderr)
            return rc
        if _NO_CHANGES in out:
            print(f"\n✅ {village} converged after {rnd - 1} applied round(s).")
            return 0

        # Keep _plan.json in lockstep: the gate must read the EXACT plan we apply.
        rc, plan_json = _stream([tf, f"-chdir={tf_dir}", "show", "-json", ".plan"], None)
        if rc != 0:
            return rc
        paths.plan_json.write_text(plan_json, encoding="utf-8")

        rc, gate_out = _stream([sys.executable, "-m", "verso.ru.consolidation.verify_plan",
                                "--village", village, "--plan", str(paths.plan_json),
                                "--json"], None)
        violations = json.loads(gate_out or "[]")
        decision, kinds = gate_decision(violations)

        if decision == "halt":
            print(f"\n⛔ {village}: gate blocks this plan — {sorted(kinds)}.\n"
                  f"   These would destroy live Geni resources or create a conflict;\n"
                  f"   they need a human decision, so the loop stops here.\n"
                  f"   Detail:  verso verify-plan "
                  f'--village "{village}"', file=sys.stderr)
            return 1

        if decision == "sync":
            print(f"\n… {len(violations)} document replace(s) — running document_sync "
                  f"before applying.", flush=True)
            _stream([sys.executable, "-m", "verso.ru.consolidation.document_sync",
                     "--village", village], log)
            # document_sync's exit code is meaningless (main() returns None even when
            # individual documents time out), so re-plan and re-verify instead of
            # trusting it.
            continue

        rc, apply_out = _stream([tf, f"-chdir={tf_dir}", "apply", ".plan"], log)
        transient, permanent = classify_apply_output(apply_out)
        outcome = ApplyOutcome(rc, transient, permanent)
        print(f"\n--- round {rnd}: rc={rc}, transient={transient}, "
              f"permanent={len(permanent)} ---", flush=True)

        if permanent:
            print(f"\n⛔ {village}: {len(permanent)} permanent failure(s) — retrying "
                  f"cannot fix these:", file=sys.stderr)
            for msg in permanent[:10]:
                print(f"     {msg}", file=sys.stderr)
            print("   Usually a profile another Geni user manages. Pin it with the\n"
                  '   cluster hint lifecycle_ignore_changes:["projects"].',
                  file=sys.stderr)
            return 1

        if outcome.clean:
            continue  # next round re-plans; "No changes" ends the loop

    print(f"\n⚠ {village}: still not converged after {max_rounds} rounds — "
          f"re-run, or investigate the remaining plan.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--village", required=True)
    ap.add_argument("--max-rounds", type=int, default=5)
    ap.add_argument("--log-dir", type=Path, default=None,
                    help="also tee plan/apply output to <log-dir>/<village>-converge.log")
    args = ap.parse_args(argv)
    return converge(args.village, args.max_rounds, args.log_dir)


if __name__ == "__main__":
    sys.exit(main())
