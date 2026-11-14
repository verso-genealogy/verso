"""The Wikidata snapshot of Russian given names — the base's one input that needs the network.

    python tools/names_build/wikidata.py --out tools/names_build/wikidata-<YYYY-MM-DD>.json

Three SPARQL query files go to the public endpoint, with a User-Agent that says who asks (Wikimedia's
policy): `query.sparql` (every male or female given name with a Russian label, run once per range of item
numbers — the endpoint cuts a query at 60 s, and a range it cuts is split in two), `links.sparql` (what those
names link to, in batches) and `labels.sparql` (the Russian label and the sex of every linked item). The snapshot is committed; the build reads
it and never goes to the network. Wikidata's data is CC0.

Per item: QID, Russian label (a single Cyrillic word; the others are listed under `skipped_labels`), sex (from
the class), and its links — `P460` (said to be the same as) and `P1560` (given name version for other
gender). `links` holds every linked QID with its Russian label and sex where Wikidata has them, so the build
needs no network. The file is stable (sorted, no ASCII escapes): the diff of a re-run reads as what Wikidata
changed.
"""
from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "verso-names-build/0.1 (https://github.com/verso-genealogy/verso; names dictionary snapshot)"
HERE = Path(__file__).parent
QUERY = HERE / "query.sparql"
LABELS = HERE / "labels.sparql"
LINKS = HERE / "links.sparql"
SEX = {"Q12308941": "M", "Q11879590": "F"}
CYRILLIC = re.compile(r"^[Ѐ-ӿ]+$")
#: Item numbers are asked in ranges this wide (a range the endpoint cuts is split in two).
STEP = 10_000_000
TOP = 10_000_000_000
BATCH = 250
PAUSE = 1.0


class Cut(Exception):
    """The endpoint cut the query short (60 s) — ask for less."""


def fetch(query: str, *, timeout: float = 100) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        ENDPOINT, data=urllib.parse.urlencode({"query": query}).encode(),
        headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
    for _ in range(8):
        time.sleep(PAUSE)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)["results"]["bindings"]
        except urllib.error.HTTPError as error:
            if error.code in (429, 503):  # asked to wait
                wait = int(error.headers.get("Retry-After", "30"))
                print(f"  waiting {wait} s ({error.code})", file=sys.stderr)
                time.sleep(wait)
                continue
            raise Cut(str(error.code)) from error
        except (json.JSONDecodeError, TimeoutError, urllib.error.URLError, http.client.HTTPException) as error:
            raise Cut(type(error).__name__) from error
    raise Cut("rate limited")


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def ranged(template: str, low: int, high: int) -> list[dict[str, Any]]:
    """The query for item numbers low <= n < high; split in two where the endpoint cuts it."""
    try:
        rows = fetch(template.replace("@LO@", str(low)).replace("@HI@", str(high)))
    except Cut as cut:
        if high - low <= 1:
            raise
        middle = (low + high) // 2
        print(f"  Q{low}..Q{high}: cut ({cut}), split", file=sys.stderr)
        return ranged(template, low, middle) + ranged(template, middle, high)
    print(f"  Q{low}..Q{high}: {len(rows)} rows", file=sys.stderr)
    return rows


def snapshot(bindings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """(items, skipped labels). One entry per item; an item of both classes keeps both sexes. A label that is
    not a single Cyrillic word (a stress mark, «Дем'ян», «Абид (имя)», two names) is skipped and listed."""
    items: dict[str, dict[str, Any]] = {}
    skipped: set[str] = set()
    for row in bindings:
        item = qid(row["item"]["value"])
        label = row["label"]["value"]
        if not CYRILLIC.match(label):
            skipped.add(f"{item} {label}")
            continue
        entry = items.setdefault(item, {"qid": item, "label": label, "sex": set(), "p460": [], "p1560": []})
        entry["sex"].add(SEX[qid(row["class"]["value"])])
    return [{**e, "sex": "".join(sorted(e["sex"]))}
            for e in sorted(items.values(), key=lambda e: int(e["qid"][1:]))], sorted(skipped)


def add_links(items: list[dict[str, Any]]) -> None:
    """Fill each item's `p460` and `p1560` (sorted QIDs), batch by batch."""
    template = LINKS.read_text(encoding="utf-8")
    by_qid = {i["qid"]: i for i in items}
    found: dict[str, dict[str, set[str]]] = {q: {"p460": set(), "p1560": set()} for q in by_qid}
    qids = sorted(by_qid, key=lambda q: int(q[1:]))
    for start in range(0, len(qids), BATCH):
        batch = qids[start:start + BATCH]
        for row in fetch(template.replace("@ITEMS@", " ".join(f"wd:{q}" for q in batch))):
            found[qid(row["item"]["value"])][row["property"]["value"]].add(qid(row["target"]["value"]))
        if (start // BATCH) % 10 == 0:
            print(f"  links {min(start + BATCH, len(qids))}/{len(qids)}", file=sys.stderr)
    for q, item in by_qid.items():
        item["p460"], item["p1560"] = sorted(found[q]["p460"]), sorted(found[q]["p1560"])


def links_of(items: list[dict[str, Any]]) -> list[str]:
    return sorted({t for i in items for key in ("p460", "p1560") for t in i[key]},
                  key=lambda q: int(q[1:]))


def link_labels(targets: list[str]) -> dict[str, dict[str, str | None]]:
    """{QID: {label, sex}} of the linked items: the Russian label (None if Wikidata has none) and the sex."""
    template = LABELS.read_text(encoding="utf-8")
    found: dict[str, dict[str, Any]] = {t: {"label": None, "sex": set()} for t in targets}
    for start in range(0, len(targets), BATCH):
        batch = targets[start:start + BATCH]
        rows = fetch(template.replace("@ITEMS@", " ".join(f"wd:{t}" for t in batch)))
        for row in rows:
            entry = found[qid(row["item"]["value"])]
            if "label" in row:
                entry["label"] = row["label"]["value"]
            if "class" in row:
                entry["sex"].add(SEX[qid(row["class"]["value"])])
        if (start // BATCH) % 10 == 0:
            print(f"  labels {min(start + BATCH, len(targets))}/{len(targets)}", file=sys.stderr)
    return {t: {"label": e["label"], "sex": "".join(sorted(e["sex"])) or None} for t, e in found.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    template = QUERY.read_text(encoding="utf-8")
    bindings: list[dict[str, Any]] = []
    for low in range(0, TOP, STEP):
        if low >= 200_000_000:  # one open range past the newest items
            bindings += ranged(template, low, TOP)
            break
        bindings += ranged(template, low, low + STEP)
    items, skipped = snapshot(bindings)
    add_links(items)
    links = link_labels(links_of(items))
    document = {"source": "Wikidata (CC0)", "endpoint": ENDPOINT, "date": date.today().isoformat(),
                "query": template, "links_query": LINKS.read_text(encoding="utf-8"),
                "labels_query": LABELS.read_text(encoding="utf-8"),
                "skipped_labels": skipped, "items": items, "links": links}
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    resolved = sum(1 for v in links.values() if v["label"] and CYRILLIC.match(v["label"]))
    print(f"{len(items)} items: M {sum('M' in i['sex'] for i in items)}, F {sum('F' in i['sex'] for i in items)}, "
          f"P460 {sum(len(i['p460']) for i in items)}, P1560 {sum(len(i['p1560']) for i in items)}; "
          f"{len(links)} link targets, {resolved} with a Cyrillic ru label", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
