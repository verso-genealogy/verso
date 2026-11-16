"""A row-aligned band of a spread: the same y-band cut from an об page and the facing recto, stacked, so a row on the
top is the SAME record as the row at the same height on the bottom — `spread_<лист>_<y0>-<y1>.jpg`.

The об page names the child and the parents, the facing recto names the godparents, and the two are aligned by eye —
the single most repeated error in a reading session is cropping the wrong band of the recto and reading another
family's godparents. A spread is the verso (left) and the NEXT leaf's recto (right): л. 120об faces л. 121.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from verso.core.scans import stanza
from verso.core.scans.image import image_names, pil
from verso.core.scans.look import legible
from verso.ru.messages import t
from verso.ru.scans.album import find, open_page
from verso.ru.scans.cli import add_enhance_flag
from verso.ru.scans.folio import VERSO_SUFFIX, parse_album

__all__ = ["HELP", "add_arguments", "run"]

HELP = "row-aligned verso+recto band (names + godparents)"


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", metavar="DIR")
    p.add_argument("--folio", required=True, help=str(t("scans.help.spread_folio")))
    p.add_argument("--band", type=float, nargs=2, default=(0.07, 0.56),
                   metavar=("Y0", "Y1"), help="fractional y-band, e.g. 0.36 0.60")
    p.add_argument("--scale", type=float, default=2.6)
    add_enhance_flag(p)
    p.add_argument("--out")


def run(args: argparse.Namespace) -> int:
    Image, _, _ = pil()
    directory = Path(args.directory)
    rotation = stanza.rotation(directory)
    pages, bad = parse_album(image_names(directory))
    if not pages:
        raise SystemExit(
            t("scans.spread.no_folios", directory=directory, len=len(bad), join=', '.join(sorted(bad)[:2])))

    verso_label = args.folio if args.folio.endswith(VERSO_SUFFIX) else args.folio + VERSO_SUFFIX
    verso = find(pages, verso_label)
    if verso is None:
        raise SystemExit(f"no page {verso_label} in {directory}")
    recto = find(pages, str(verso.number + 1))
    if recto is None:
        raise SystemExit(t("scans.spread.no_recto", p1=verso.number + 1, directory=directory))

    y0, y1 = args.band
    halves = []
    for page in (verso, recto):
        im = open_page(directory, page, rotation(page.label))
        crop = im.crop((0, int(im.height * y0), im.width, int(im.height * y1)))
        crop = crop.resize((int(crop.width * args.scale), int(crop.height * args.scale)), Image.Resampling.LANCZOS)
        halves.append(legible(crop, grey=True, enhance=args.enhance or 1.0))

    width = max(h.width for h in halves)
    sheet = Image.new("L", (width, sum(h.height + 12 for h in halves)), 255)
    y = 0
    for half in halves:
        sheet.paste(half, (0, y))
        y += half.height + 12
    out = Path(args.out) if args.out else directory / f"spread_{verso.label}_{y0:g}-{y1:g}.jpg"
    sheet.save(out, quality=93)
    print(f"{out}: л. {verso.label} (top) faces л. {recto.label} (bottom), "  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
          f"band {y0:g}–{y1:g}")
    print("The same y-band from both halves: a row on the top is the SAME record as "
          "the row at the same height on the bottom.")
    return 0
