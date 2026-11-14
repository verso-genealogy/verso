#!/usr/bin/env python3
"""Apply pending geni_document changes the Geni OAuth API cannot manage.

The OAuth API exposes neither a document's `text` body nor its `projects` on
read (and cannot update `text` at all — no bulk projects endpoint either). So
terraform's state always lacks both fields and shows a spurious diff: a
destroy+recreate over `text`, and a `+ projects` once text is enriched.

This script:
  1. parses the terraform plan for changed geni_document resources;
  2. (text) calls `geni document text set` per doc, which fetches the current
     body via the website's AJAX endpoint, compares against the config text
     after normalising trailing whitespace, and POSTs only when they differ;
  3. patches terraform state so state.text / state.projects match config,
     clearing the spurious diff.

`projects` needs no Geni-side action — documents are already members; the API
just can't read it back. Use --no-update for a state-only enrichment of
text + projects.

Requires `geni` v1.13.0+ (on PATH or in verso.toml's `[tools] path`). The first invocation of an AJAX
command prompts y/N for one-time consent; this script sets
GENI_WEB_CONSENT=accepted so re-runs don't stall.

Usage:
  python3 update_documents.py --ids document-1,document-2   # test a few
  python3 update_documents.py                               # full run
  python3 update_documents.py --plan plan.json --no-update  # state patch only
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from verso.ru.consolidation.plan import plan_paths
from verso.core.tools import tool



def log(*a):
    print(*a, file=sys.stderr, flush=True)


def changed_documents(plan_path):
    """geni_document resources with a pending change (replace or update):
    their tf id, the config `text`, and the config `projects` list.

    Values are kept verbatim — terraform's heredoc text (incl. its trailing
    newline) must match exactly for the state patch to clear the diff. The
    CLI normalises trailing whitespace separately when deciding whether to
    POST.
    """
    plan = json.load(open(plan_path))
    out = []
    for rc in plan["resource_changes"]:
        if rc["type"] != "geni_document":
            continue
        actions = rc["change"]["actions"]
        replace = "delete" in actions and "create" in actions
        if not (replace or actions == ["update"]):
            continue
        before = rc["change"]["before"] or {}
        after = rc["change"]["after"] or {}
        tf_id = before.get("id")
        if not tf_id:
            continue
        out.append({
            "name": rc["address"].split(".", 1)[1],
            "tf_id": tf_id,
            "text": after.get("text"),
            "projects": after.get("projects"),
        })
    return out


def update_one(tf_id, text):
    """Run `geni document text set <tf_id>` with text on stdin.

    Returns the verdict — 'updated', 'unchanged', or 'error' — matching the
    Python script's historical vocabulary so log parsing is unaffected.
    """
    env = {**os.environ, "GENI_WEB_CONSENT": "accepted"}
    try:
        res = subprocess.run(
            [tool("geni"), "document", "text", "set", tf_id],
            input=text, capture_output=True, text=True,
            timeout=120, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"verdict": "error", "error": "timeout after 120s"}

    if res.returncode != 0:
        return {"verdict": "error", "error": (res.stderr or res.stdout)[:200].strip()}
    try:
        out = json.loads(res.stdout)
    except json.JSONDecodeError:
        return {"verdict": "error", "error": f"non-JSON output: {res.stdout[:200]!r}"}

    status = out.get("status")
    if status == "updated":
        return {"verdict": "updated", "bytes": out.get("bytes_written")}
    if status == "unchanged":
        return {"verdict": "unchanged"}
    return {"verdict": "error", "error": f"unexpected status {status!r}"}


def patch_state(docs, tf_dir):
    """Enrich attributes.text and attributes.projects for each geni_document in
    terraform state, so the OAuth-unreadable fields stop showing a spurious diff."""
    pulled = subprocess.run([tool("terraform"), f"-chdir={tf_dir}", "state", "pull"],
                            capture_output=True, text=True, check=True)
    state = json.loads(pulled.stdout)
    # Match on the document's stable Geni id, not the terraform res_name: a
    # renamed document (a `moved {}` block not yet applied) still sits in state
    # under its old name, so name-matching would skip it and leave a spurious
    # diff that apply turns into a destructive destroy+recreate.
    by_id = {d["tf_id"]: d for d in docs}
    patched = 0
    for res in state.get("resources", []):
        if res.get("type") != "geni_document":
            continue
        for inst in res.get("instances", []):
            attrs = inst.setdefault("attributes", {})
            d = by_id.get(attrs.get("id"))
            if not d:
                continue
            if d.get("text") is not None:
                attrs["text"] = d["text"]
            if d.get("projects") is not None:
                attrs["projects"] = d["projects"]
            patched += 1
    state["serial"] = state.get("serial", 0) + 1
    tmp = Path("/tmp/patched_state.json")
    tmp.write_text(json.dumps(state))
    subprocess.run([tool("terraform"), f"-chdir={tf_dir}", "state", "push", str(tmp)],
                   check=True)
    return patched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=None, help="terraform plan JSON path")
    ap.add_argument("--limit", type=int, help="process only the first N documents")
    ap.add_argument("--ids", help="comma-separated tf ids to restrict to")
    ap.add_argument("--no-update", action="store_true",
                    help="skip Geni text updates (state patch only)")
    ap.add_argument("--no-state", action="store_true", help="skip state patch")
    ap.add_argument("--village", default=None, help="village dir (default: cwd)")
    args = ap.parse_args()

    paths = plan_paths(Path(args.village).resolve() if args.village else Path.cwd())
    docs = changed_documents(args.plan or str(paths.plan_json))
    if args.ids:
        wanted = set(args.ids.split(","))
        docs = [d for d in docs if d["tf_id"] in wanted]
    if args.limit:
        docs = docs[:args.limit]
    log(f"{len(docs)} geni_document(s) to process")
    if not docs:
        return

    if not args.no_update:
        with_text = [d for d in docs if d["text"] is not None]
        counts = {}
        for i, d in enumerate(with_text, 1):
            r = update_one(d["tf_id"], d["text"])
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
            if r["verdict"] == "error":
                log(f"  {d['tf_id']} error: {r.get('error')}")
            if i % 10 == 0 or i == len(with_text):
                log(f"  {i}/{len(with_text)}  {counts}")
        log(f"update summary: {counts}")

    if not args.no_state:
        n = patch_state(docs, str(paths.tf_dir))
        log(f"patched state (text + projects) for {n} document instance(s)")


if __name__ == "__main__":
    main()
