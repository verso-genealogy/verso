#!/usr/bin/env python3
"""Download scans from a КАИСА electronic reading room (ЭЧЗ).

One CLI for every archive on the platform — pick it with `--archive`:

    python3 -m verso.ru.cli.echz --archive gavo meta 590 5 67   # ГАВО (vladimir.kaisa.ru)
    python3 -m verso.ru.cli.echz --archive gato meta 12 1 475   # ГАТО (kaisa.tambovarchiv.ru)

Three steps, each resumable, all writing into the current directory:

    meta  <fund> <опись> <дело>   resolve the дело → echz_meta.json (per-scan URLs)
    notes                         harvest every scan's filename → notes.json + лист index
    get   <листы>                 download листы by citation → ./<f>-<o>-<d>/…
    get   all                     …or the whole дело

**`get` locates листы by binary search over the filenames**, so `notes` is optional:
a уездное дело runs 300–2000 scans while one parish holds 10–40 листы of it, and
harvesting every note to fetch thirty images is the wrong trade. Run `notes` when you
want the whole picture — which листы were shot at all, which sides are missing, where
a лист «51а» sits — or when `get` reports that the filenames carry no лист number.

AUTH: the session JWT goes in ./echz_token.txt (copy it from the signed-in
browser session of the reading room). Access is sold **by the hour** and
activated by hand; until an абонемент is active the viewer returns no pages at
all. Resolve what you need BEFORE activating.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from verso.ru.archives.kaisa import (
    INSTANCES, Client, Delo, KaisaError, folio_index, folio_span, pages_for)
from verso.ru.messages import t

META = "echz_meta.json"
NOTES = "notes.json"


def _client(archive: str) -> Client:
    inst = INSTANCES.get(archive)
    if inst is None:
        sys.exit(str(t("cli.echz.unknown_archive", archive=repr(archive), known=", ".join(sorted(INSTANCES)))))
    return Client.from_token_file(inst)


def _load_meta() -> Delo:
    if not os.path.exists(META):
        sys.exit(str(t("cli.echz.no_meta", meta=META)))
    with open(META) as fh:
        raw = json.load(fh)
    return Delo(code=raw["code"], object_id=raw["objectId"], title=raw.get("title"),
                dates=raw.get("dates"), folios=raw.get("folios"), urls=raw["urls"])


def _load_notes() -> dict[int, str]:
    if not os.path.exists(NOTES):
        return {}
    with open(NOTES) as fh:
        return {int(k): v for k, v in json.load(fh).items() if v}


def _save_notes(notes: dict[int, str]) -> None:
    with open(NOTES, "w") as fh:
        json.dump({str(k): v for k, v in sorted(notes.items())}, fh, ensure_ascii=False)


def cmd_meta(archive: str, fund: str, opis: str, delo: str) -> None:
    found = _client(archive).find_delo(fund, delo, opis)
    if found is None:
        sys.exit(str(t("cli.echz.not_in_reading_room", fund=fund, opis=opis, delo=delo)))
    if not found.urls:
        sys.exit(str(t("cli.echz.no_pages", code=found.code)))
    with open(META, "w") as fh:
        json.dump({"code": found.code, "objectId": found.object_id, "title": found.title,
                   "dates": found.dates, "folios": found.folios,
                   "dir": f"{fund}-{opis}-{delo}", "totalPages": found.total_pages,
                   "urls": found.urls}, fh, ensure_ascii=False)
    print(f"{found.code}: {found.title}")
    print(t("cli.echz.case_summary", dates=found.dates, folios=found.folios, total_pages=found.total_pages))
    print(f"  → {META}")


def cmd_notes(archive: str, workers: int) -> None:
    delo = _load_meta()
    notes = _client(archive).notes(delo.urls, workers=workers, known=_load_notes())
    _save_notes(notes)
    missing = [p for p in range(1, delo.total_pages + 1) if p not in notes]
    print(f"notes: {len(notes)}/{delo.total_pages}"
          + (str(t("cli.echz.notes_missing", missing=missing[:10])) if missing else ""))
    _report(notes)


def _report(notes: dict[int, str]) -> None:
    idx = folio_index(notes)
    plain = sorted(int(f) for f in idx if f.isdigit())
    if not plain:
        print(t("cli.echz.no_folio_names"))
        return
    gaps = [n for n in range(plain[0], plain[-1] + 1) if str(n) not in idx]
    letters = sorted(f for f in idx if not f.isdigit())
    spreads = sum(1 for v in notes.values()
                  if (sp := folio_span(v)) and sp[0][0] != sp[1][0])
    other = sorted(v for v in notes.values() if not folio_span(v))
    print(t("cli.echz.folio_range", first=plain[0], last=plain[-1], count=len(plain)))
    print(t("cli.echz.folios_missing", missing=gaps or '—'))
    print(t("cli.echz.spreads", spreads=spreads))
    print(t("cli.echz.lettered", lettered=letters or '—'))
    print(t("cli.echz.not_folios", other=other[:6], more=' …' if len(other) > 6 else ''))


def cmd_get(archive: str, spec: str, workers: int, outdir: str | None) -> None:
    client, delo = _client(archive), _load_meta()
    notes = _load_notes()
    try:
        if spec == "all" or notes:
            pages = pages_for(spec, notes, delo.total_pages)
        else:
            pages, notes = client.locate(spec, delo)
    except KaisaError as err:
        sys.exit(str(err))
    if not pages:
        sys.exit(str(t("cli.echz.no_such_folios", spec=spec)))
    target = outdir or f"{delo.code.replace('Ф. ', '').replace(' Оп. ', '-').replace(' Д. ', '-')}"  # i18n: content — the archive's shelfmark, as it writes it
    got, failed = client.download(delo, pages, target, names=notes, workers=workers)
    print(str(t("cli.echz.downloaded", spec=spec, count=len(pages), target=target, got=got))
          + (str(t("cli.echz.not_downloaded", failed=failed)) if failed else ""))
    if failed:
        print(t("cli.echz.session_expired"))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", default="gavo", choices=sorted(INSTANCES),
                    help=str(t("cli.echz.help_archive")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("meta", help=str(t("cli.echz.help_meta")))
    m.add_argument("fund")
    m.add_argument("opis")
    m.add_argument("delo")
    n = sub.add_parser("notes", help=str(t("cli.echz.help_notes")))
    n.add_argument("--workers", type=int, default=12)
    g = sub.add_parser("get", help=str(t("cli.echz.help_get")))
    g.add_argument("folios")
    g.add_argument("--workers", type=int, default=6)
    g.add_argument("--out", help=str(t("cli.echz.help_out")))
    args = ap.parse_args(argv)
    if args.cmd == "meta":
        cmd_meta(args.archive, args.fund, args.opis, args.delo)
    elif args.cmd == "notes":
        cmd_notes(args.archive, args.workers)
    else:
        cmd_get(args.archive, args.folios, args.workers, args.out)


if __name__ == "__main__":
    main()
