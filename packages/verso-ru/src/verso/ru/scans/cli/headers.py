"""Contact sheets of the running headers, to find where each part of the book begins: the top strip of every page,
eight to a sheet, `headers_NN.jpg`, each sheet's leaves printed."""
from __future__ import annotations

import argparse
from pathlib import Path

from verso.core.scans.image import pil
from verso.core.scans.sheets import contact_sheet, fit_width
from verso.ru.messages import t
from verso.ru.scans.album import album_of, load_pages, note_frame_mode, open_page
from verso.ru.scans.cli import add_frames_flag

__all__ = ["HELP", "add_arguments", "run"]

HELP = "contact sheets of the running headers (find the parts)"
HEADER_STRIP = 0.17
CONTACT_SHEET_ROWS = 8
CONTACT_SHEET_WIDTH = 760


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("directory", metavar="DIR")
    p.add_argument("--out", required=True)
    p.add_argument("--strip", type=float, default=HEADER_STRIP)
    p.add_argument("--rows", type=int, default=CONTACT_SHEET_ROWS)
    add_frames_flag(p)


def run(args: argparse.Namespace) -> int:
    pil()
    directory = Path(args.directory)
    album = album_of(directory)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pages, by_frame = load_pages(directory, force_frames=args.frames,
                                 expand=bool(album and album.frames == "spread"),
                                 turn=album.rotate if album else 0)
    if by_frame:
        note_frame_mode(directory, len(pages))
    strips = []
    for page in pages:
        im = open_page(directory, page, album.rotation_for(page.label) if album else 0)
        strip = im.crop((0, 0, im.width, int(im.height * args.strip)))
        strips.append((page.label, fit_width(strip, CONTACT_SHEET_WIDTH)))

    written = []
    for i in range(0, len(strips), args.rows):
        chunk = strips[i:i + args.rows]
        path = out / f"headers_{i // args.rows:02d}.jpg"
        contact_sheet([s for _, s in chunk], CONTACT_SHEET_WIDTH).save(path, quality=88)
        written.append((path, [label for label, _ in chunk]))

    for path, labels in written:
        listed = ", ".join(labels)
        print(f"{path}: {listed}" if by_frame else f"{path}: лл. {listed}")  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
    print(t("scans.headers.done", len=len(written)))
    return 0
