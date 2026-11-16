"""An album's pages by лист — or, for an album that was never renamed, by frame — and each page's image.

An album renamed to `<кадр>_<лист>.jpg` is read by folio; one still carrying the phone's own `IMG_*.jpg` is read by
frame index («кадр 12»), which verifies nothing, so the caller says so (`note_frame_mode`). A page's image is its
frame turned upright — its own EXIF tag, then the album's declared turn — and cut to the half of a spread it lies on
(`verso.core.scans.image`).

Pillow is imported where it is used.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from verso.core.scans.image import cut_half, image_names, open_upright, pil, turn_upright, turned_frame_size
from verso.ru.messages import t
from verso.ru.scans.folio import FRAME_PREFIX, Page, expand_spreads, frame_pages, parse_album

__all__ = ["find", "load_pages", "note_frame_mode", "open_page", "page_named", "page_size", "titled", "where"]


def open_page(directory: Path, page: Page, rotate: int = 0) -> Any:
    """The frame this page is on, already reduced to the page.

    In albums of spreads one frame is a whole spread — `0241(131об-132).jpg` — so a window expressed in fractions of
    "the page" means nothing until the frame has been cut down to the half the page actually occupies. Every crop,
    contact sheet, spread and zoom goes through here for that reason; for albums where one frame is one side `half`
    is empty and this is just `open_upright`.

    `rotate` is this frame's declared turn (`Stanza.rotation_for`), applied BEFORE the half is cut: on a sideways
    frame the gutter runs horizontally, so splitting first would halve the wrong axis.
    """
    return cut_half(turn_upright(open_upright(directory / page.name), rotate), page.half)


def page_size(directory: Path, page: Page, rotate: int = 0) -> tuple[int, int]:
    """`open_page(directory, page, rotate).size` from the frame's header alone: the size a window on the page is a
    fraction of. The same turn and the same cut of a spread's half, in the same arithmetic. Raises what Pillow raises
    for a file it cannot read."""
    return turned_frame_size(directory / page.name, rotate, page.half)


def standing_frames(directory: Path, turn: int = 0) -> Callable[[Page], bool]:
    """Which frames of an album of spreads hold one page: those whose image stands up — taller than wide as the
    reader sees it, after the file's own orientation tag and the album's declared `turn`. A spread lies on its side.

    Only the image's header is read. Without Pillow, or for a file it cannot read, nothing is known and the frame is
    taken at its name.
    """
    from verso.core.scans.image import upright_size
    try:
        pil()
    except SystemExit:
        return lambda page: False
    sideways = turn % 180 == 90
    known: dict[str, bool] = {}

    def standing(page: Page) -> bool:
        if page.name not in known:
            try:
                width, height = upright_size(directory / page.name)
            except Exception:
                known[page.name] = False
            else:
                if sideways:
                    width, height = height, width
                known[page.name] = height > width
        return known[page.name]

    return standing


def load_pages(directory: Path, *, force_frames: bool = False, expand: bool = False,
               turn: int = 0) -> tuple[list[Page], bool]:
    """(pages in reading order, whether the frame-index fallback was used).

    Falling back silently would be wrong — the fallback verifies nothing — so the caller prints a note
    (`note_frame_mode`); refusing outright would be worse, because it is what made the tools unusable on albums that
    sit in a library as the phone named them. `expand`: the album's frames are spreads named by one leaf
    (`frames = "spread"`), and a frame standing up among them is one page, whatever its name says.
    """
    names = image_names(directory)
    if not force_frames:
        pages, _ = parse_album(names)
        if expand:
            pages = expand_spreads(pages, standing_frames(directory, turn))
        if pages:
            return pages, False
    return frame_pages(names), True


def note_frame_mode(directory: Path, count: int) -> None:
    """Say that `directory`'s `count` pages are numbered by position."""
    print(t("scans.frames_by_position", directory=directory, count=count))


def find(pages: Sequence[Page], label: str) -> Page | None:
    """The page labelled `label`, or None."""
    for page in pages:
        if page.label == label:
            return page
    return None


def page_named(directory: Path, pages: Sequence[Page], by_frame: bool, folio: str) -> Page:
    """The page `--folio` names — under frame numbering a plain «12» is кадр 12 — or SystemExit."""
    wanted = f"{FRAME_PREFIX}{int(folio)}" if by_frame and folio.isdigit() else folio
    page = find(pages, wanted)
    if page is None:
        raise SystemExit(t("scans.rows.no_page", folio=folio, directory=directory))
    return page


def where(page: Page, by_frame: bool) -> str:
    """How a report names a page: «л. 120об», or its frame («кадр12»)."""
    return page.label if by_frame else f"л. {page.label}"  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes


def titled(place: str, part: int) -> str:
    """A ruler's title: the page and the part, «л. 120об · ч.1»."""
    return f"{place} · ч.{part}"  # i18n: content — the book's own words: лист, ч., об, счётъ, кадр, the sex codes
