"""One record at reading zoom — the SECOND tier: a window named by its part's column and its row, or given outright,
cut from the page and enlarged, `zoom_<лист>_<tag>.jpg`.

Reading is two-tier and the second tier is not optional: the part crop is enough to LOCATE a record and not always
enough to READ a name. Two surnames one letter apart can turn on that letter at 8×. That crop used to be cut by
hand, four numbers at a time; `--col` and `--row` name the window instead, so the band cannot land on the
neighbouring record. The album's stanza of `scans.toml` gives the writing's `top` and `bottom`, the frame's turn and
the faded hand's `enhance`; a window remembered there is the review page's (Verso), not this command's.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from verso.core.scans import stanza
from verso.core.scans.image import pil
from verso.core.scans.look import legible
from verso.ru.messages import t
from verso.ru.scans.album import find, load_pages, open_page
from verso.ru.scans.cli import add_enhance_flag, add_frames_flag
from verso.ru.scans.folio import FRAME_PREFIX
from verso.ru.scans.zoom import COLUMNS, DEFAULT_PAD, DEFAULT_TOP, resolve

__all__ = ["HELP", "add_arguments", "run"]

HELP = "one record at reading zoom — the SECOND tier"


def add_arguments(p: argparse.ArgumentParser) -> None:
    columns = sorted({name for windows in COLUMNS.values() for name in windows})
    p.add_argument("directory", metavar="DIR")
    p.add_argument("--folio", required=True, help=str(t("scans.help.folio")))
    p.add_argument("--part", type=int, choices=sorted(COLUMNS), help=str(t("scans.help.zoom_part")))
    p.add_argument("--col", choices=columns, metavar="COLUMN",
                   help=f"the column to crop, per --part: {', '.join(columns)}")
    p.add_argument("--row", type=int, nargs=2, metavar=("N", "OF"),
                   help="record N of OF on this page — an even division of the "
                        "writing area, padded")
    p.add_argument("--box", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                   help="name the window outright, in leaf FRACTIONS; overrides "
                        "--col/--row")
    p.add_argument("--layout", help="path to scans.toml (default: the album's "
                                    "own, else --village's)")
    p.add_argument("--village", help="village directory holding the durable "
                                     "scans.toml")
    p.add_argument("--album-title", help="which album's section to use, when "
                                         "scans.toml holds more than one")
    p.add_argument("--scale", type=float, default=6.0,
                   help="zoom (default 6× — the tier that reads a name)")
    p.add_argument("--top", type=float, default=DEFAULT_TOP,
                   help=f"where the writing area begins (default {DEFAULT_TOP:g})")
    p.add_argument("--pad", type=float, default=DEFAULT_PAD,
                   help=f"grow a --row band on each side (default {DEFAULT_PAD:g})")
    p.add_argument("--colour", action="store_true",
                   help="keep colour (default is greyscale + autocontrast)")
    add_enhance_flag(p)
    add_frames_flag(p)
    p.add_argument("--tag", default="a", help="suffix for the output filename")
    p.add_argument("--out")


def run(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    layout_path, album_title, stanzas = stanza.for_album(directory, layout=args.layout, village=args.village,
                                                         album_title=args.album_title)
    album = stanzas.album(album_title) if album_title else None
    enhance = args.enhance
    from_stanza = enhance is None
    if enhance is None:
        enhance = stanza.enhance_for(directory, layout=args.layout, village=args.village, read_path=layout_path,
                                     title=album_title, album=album)
    pages, by_frame = load_pages(directory, force_frames=args.frames,
                                 expand=bool(album and album.frames == "spread"),
                                 turn=album.rotate if album else 0)

    wanted = args.folio
    if by_frame and wanted.isdigit():
        # Under frame numbering «12» means кадр 12, not л. 12 — and the reader who just ran `headers` has frame
        # numbers in front of them.
        wanted = f"{FRAME_PREFIX}{int(wanted)}"
    page = find(pages, wanted)
    if page is None:
        where = ("A frame is named «кадр 12», or just «12» in this mode." if by_frame  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
                 else "An об page is written «420об», its recto «421».")  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
        raise SystemExit(f"no page {args.folio} in {directory}. {where}")

    try:
        box = resolve(part=args.part, column=args.col, row=args.row, box=args.box,
                      top=(album.top if album and album.top is not None
                           and args.top == DEFAULT_TOP else args.top),
                      bottom=(album.bottom if album and album.bottom is not None
                              else 1.0),
                      pad=args.pad)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    Image, _, _ = pil()
    im = open_page(directory, page, album.rotation_for(page.label) if album else 0)
    crop = im.crop(box.pixels(im.width, im.height))
    crop = crop.resize((int(crop.width * args.scale), int(crop.height * args.scale)), Image.Resampling.LANCZOS)
    # Greyscale + autocontrast is what makes a faded iron-gall hand legible at this zoom, so it is the DEFAULT here
    # (unlike `crops`, where the sweep tier keeps colour to tell ink from paper damage).
    crop = legible(crop, grey=not args.colour, enhance=enhance)

    out = Path(args.out) if args.out else directory / f"zoom_{page.label}_{args.tag}.jpg"
    crop.save(out, quality=93)
    named = f", ч.{args.part} {args.col}" if args.col else ""  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
    rowed = f", row {args.row[0]}/{args.row[1]}" if args.row else ""
    where = page.label if by_frame else f"л. {page.label}"  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
    pushed = str(t("scans.zoom.from_stanza", enhance=f"{enhance:g}")) if from_stanza and enhance > 1 and not args.colour else ""
    print(f"{out}: {where} — {box}{named}{rowed} at {args.scale:g}×{pushed}")
    if args.row:
        print("⚠ Rows are an EVEN division of the writing area; records are not "
              "equal height (a monthly total eats a row). If the band missed, "
              "widen with --pad or name the band outright with --box.")
    return 0
