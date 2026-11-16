"""Filenames of a photographed дело, and whether the album is whole.

The archives' own naming is `<frame>_<лист>.jpg` — `0118_57.jpg`, `0119_57об.jpg`
— which encodes two independent sequences: the order the pages were photographed
and the folio numbering the archivist pencilled on the leaves. Comparing them is
the cheapest check that exists on a set of scans, and it catches the failures
that otherwise cost a whole reading pass:

* a leaf that was never photographed (frames continuous, folios skip);
* a leaf filed under the WRONG YEAR — one misfiled leaf of a year's album,
  found only after the year had been read once;
* an album whose range disagrees with what the archive's inventory records for
  the year.

Pure and dependency-free on purpose: this is the part worth having in the test
suite, and it must run on a machine without Pillow.
"""
from __future__ import annotations

import re
from itertools import pairwise
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from verso.ru.messages import t

__all__ = ["FRAME_PREFIX", "VERSO_SUFFIX", "AlbumReport", "Page", "check_album", "expand_spreads", "format_report",
           "frame_pages", "next_side", "parse_album", "parse_frame", "parse_name", "renumber_scans"]

# `0118_57.jpg`, `0119_57об.jpg`, and the cover/inventory frames that carry a
# word instead of a folio (`001_обложка.jpg`, `002_внутр оп.jpg`).
_NAME = re.compile(r"^(?P<frame>\d+)_(?P<folio>.+?)\.(?:jpg|jpeg|png|tif|tiff)$", re.IGNORECASE)
# `57`, `57об`, and the shapes an inserted leaf takes: `12а`, `12а об` — a
# letter suffix is the archivist's own numbering for a leaf bound in later, and
# the space before «об» is how the photographer typed it.
# The number is bounded at four digits (leading zeros are eaten first, so
# `0005` is лист 5): no дело runs to five. Unbounded, a phone timestamp —
# `20000101_120000.jpg`, which is how an unrenamed album is named — parses
# as «кадр 20000101, лист 120000». That is not merely cosmetic: `check`
# then reports hundreds of absent pages, and `exported_name` concludes the
# filename already carries a лист and ignores the «Название» the reader set
# in Photos, so renaming an album has no effect at all.
_FOLIO = re.compile(r"^0*(?P<number>\d{1,4})\s*(?P<letter>[а-яё])?\s*(?P<verso>об)?$")  # i18n: content — the book's own words: лист, об, кадр
# `0240(131).jpg`, `0241(131об-132).jpg`, `305_(144об-145).jpg`, and the same
# thing with no parentheses at all — `612_388об-389.jpg`. That is how some archives
# name their albums of spreads. One frame there is a whole SPREAD and the filename
# says which two leaves are on it, so the лист numbering IS present and only
# needed reading: without this the album falls back to `frame_pages`, where
# nothing about continuity can be checked and `spread` does not apply.
_PAREN = re.compile(r"^(?P<frame>\d+)_?\((?P<folios>[^)]+)\)"
                    r"\.(?:jpg|jpeg|png|tif|tiff)$", re.IGNORECASE)

VERSO_SUFFIX = "об"  # i18n: content — the book's own words: лист, об, кадр
# How a page with no лист of its own is named — a cover, an inventory frame, or
# every page of an album that was never renamed. Kept free of spaces because the
# label goes into crop filenames as well as into reports.
FRAME_PREFIX = "кадр"  # i18n: content — the book's own words: лист, об, кадр


@dataclass(frozen=True, order=True)
class Page:
    """One photographed page. Sort order is the order it should be read in."""
    number: int          # folio number; 0 for a cover or an inventory frame
    letter: str          # '' — or 'а'/'б' on a leaf bound in later (л. 12а)
    verso: bool          # об — the LEFT half of a spread
    frame: int
    name: str
    # Which half of the FRAME this side occupies, when one frame holds a whole
    # spread: 'L', 'R', or '' for a frame that is a single page. Only albums of
    # spreads need it; everywhere else one frame is one side and this stays ''.
    half: str = ""

    @property
    def is_folio(self) -> bool:
        return self.number > 0

    @property
    def key(self) -> tuple[int, str, bool]:
        return (self.number, self.letter, self.verso)

    @property
    def label(self) -> str:
        if self.number == 0:
            # A cover, an inventory frame, or a page of an album that was never
            # renamed: there is no лист to name it by, so the frame index is the
            # only handle the reader has.
            return f"{FRAME_PREFIX}{self.frame}"
        return f"{self.number}{self.letter}{VERSO_SUFFIX if self.verso else ''}"


def parse_frame(name: str) -> list[Page]:
    """Every page a frame holds — one, or the two leaves of a spread.

    `0119_57об.jpg` → one page. `0241(131об-132).jpg` → two, marked 'L' and 'R'
    so a crop knows which half of the frame to cut before it cuts anything else.
    """
    m = _PAREN.match(name)
    if m:
        frame = int(m.group("frame"))
        parts = [f.strip() for f in m.group("folios").split("-") if f.strip()]
        halves = ["L", "R"] if len(parts) == 2 else [""]
        pages = []
        for folio, half in zip(parts, halves, strict=False):
            fm = _FOLIO.match(folio)
            if not fm:
                return []
            pages.append(Page(number=int(fm.group("number")),
                              letter=fm.group("letter") or "",
                              verso=bool(fm.group("verso")),
                              frame=frame, name=name, half=half))
        return pages
    m = _NAME.match(name)
    if m and "-" in m.group("folio"):
        # `612_388об-389.jpg`: the same spread, written without parentheses.
        parts = [f.strip() for f in m.group("folio").split("-") if f.strip()]
        matches = [_FOLIO.match(f) for f in parts]
        if len(parts) == 2 and all(matches):
            frame = int(m.group("frame"))
            return [Page(number=int(fm.group("number")),
                         letter=fm.group("letter") or "",
                         verso=bool(fm.group("verso")),
                         frame=frame, name=name, half=half)
                    for fm, half in zip(matches, ("L", "R"), strict=True)]
    stem, _, ext = name.rpartition(".")
    if stem and ext.lower() in {"jpg", "jpeg", "png", "tif", "tiff"}:
        # `64об.jpg`, `063.jpg` — the лист and nothing else, which is how some
        # archives name an album. There is no frame number to compare it
        # against, so continuity is checked on the folios alone; `parse_album`
        # numbers the frames by reading order afterwards.
        parts = [f.strip() for f in stem.split("-") if f.strip()]
        matches = [_FOLIO.match(f) for f in parts]
        if 1 <= len(parts) <= 2 and all(matches):
            halves = ("L", "R") if len(parts) == 2 else ("",)
            return [Page(number=int(fm.group("number")),
                         letter=fm.group("letter") or "",
                         verso=bool(fm.group("verso")),
                         frame=0, name=name, half=half)
                    for fm, half in zip(matches, halves, strict=True)]
    page = _parse_single(name)
    return [page] if page is not None else []


def parse_name(name: str) -> Page | None:
    """`0119_57об.jpg` → Page(57, verso=True, frame=119). None if unparseable.

    A spread frame yields its FIRST leaf here; `parse_frame` gives both.
    """
    pages = parse_frame(name)
    return pages[0] if pages else None


def _parse_single(name: str) -> Page | None:
    m = _NAME.match(name)
    if not m:
        return None
    frame = int(m.group("frame"))
    folio = m.group("folio").strip()
    fm = _FOLIO.match(folio)
    if not fm:
        # A cover or the внутренняя опись: it has a frame but no folio, and it
        # sorts before every leaf.
        return Page(number=0, letter="", verso=False, frame=frame, name=name)
    return Page(number=int(fm.group("number")), letter=fm.group("letter") or "",
                verso=bool(fm.group("verso")), frame=frame, name=name)


def parse_album(names: Iterable[str]) -> tuple[list[Page], list[str]]:
    """(pages in reading order, unparseable filenames)."""
    pages, bad = [], []
    for name in names:
        found = parse_frame(name)
        if not found:
            bad.append(name)
        else:
            pages.extend(found)
    pages.sort()
    # A name that carried no frame number (`64об.jpg`) gets one from its place
    # in reading order, so crop filenames stay sortable and the report can talk
    # about frames at all. Gap detection is meaningless on these and is skipped.
    if pages and all(p.frame == 0 for p in pages if p.is_folio):
        pages = [Page(p.number, p.letter, p.verso, i, p.name, p.half)
                 for i, p in enumerate(pages, 1)]
    return pages, bad


def frame_pages(names: Iterable[str]) -> list[Page]:
    """Pages of an album that was never renamed to `<frame>_<лист>.jpg`.

    Whole archives sit in Apple Photos exactly as the phone wrote them
    (`IMG_20000101_120000.jpg`), and renaming fifty albums to read one year out
    of one of them is not worth the afternoon. Filename order IS the order the
    pages were photographed, so the frame index stands in for the folio and
    every page is `Page(number=0, frame=i)`, labelled «кадр 12».  # i18n: content — the book's own words: лист, об, кадр

    What this mode gives up is the whole point of the folio naming: **nothing
    about continuity can be checked**, because a frame index cannot disagree
    with itself. A missing leaf and a leaf filed under the wrong year both look
    like a perfectly tidy album here. Rename the album (see the docs) before
    reading a year that will be read more than once.

    The index is also only as stable as the directory: every image file counts,
    so writing crops back beside the frames renumbers everything after them and
    the notes taken this morning point at the wrong pages this afternoon. Always
    cut to a separate `--out`.
    """
    return [Page(number=0, letter="", verso=False, frame=index, name=name)
            for index, name in enumerate(sorted(names), 1)]


def renumber_scans(pages: Iterable[Page], first_scan: int, first_folio: str) -> list[Page]:
    """An album named by SCAN number, relabelled by лист.

    An ЭЧЗ download names its files by the archive's scan counter —
    `3001.jpg` … `3117.jpg` — which `parse_frame` cannot tell from a лист, so
    it reads «л. 3001». The DSL says where a record is by лист (`page("215об")`),
    and nothing matches. When one scan is one side, in order, the mapping is
    arithmetic: the first scan is `first_folio` («200»), the next its об, the
    next л. 201 — so 3032 is л. 215об.

    A page the rule cannot place (a half of a spread, a lettered leaf, a scan
    before the first) is left as it was.
    """
    fm = _FOLIO.match(first_folio.strip())
    if not fm:
        raise ValueError(str(t("scans.folio.not_a_leaf", first_folio=repr(first_folio))))
    start = 2 * int(fm.group("number")) + (1 if fm.group("verso") else 0)
    out: list[Page] = []
    for page in pages:
        offset = page.number - first_scan
        if page.half or page.letter or not page.is_folio or offset < 0:
            out.append(page)
            continue
        side = start + offset
        out.append(Page(side // 2, "", bool(side % 2), page.frame, page.name, ""))
    return sorted(out)


def next_side(page: Page) -> tuple[int, bool]:
    """The side that follows this one: об → the next leaf's recto, recto → its об."""
    return (page.number + 1, False) if page.verso else (page.number, True)


def expand_spreads(pages: Iterable[Page], single: Callable[[Page], bool] | None = None) -> list[Page]:
    """Split pages whose FILE is a spread but whose NAME gives one лист.

    `64об.jpg` of such an album holds 64об on the left and 65 on the
    right, and says so nowhere — the archive named the frame by its left leaf.
    Left alone, every recto of such an album is reported missing and cannot be
    addressed at all. Which albums are like this is not knowable from a
    filename, so it is declared per album (`frames = "spread"`).

    Two kinds of page are left exactly as they are. One that already carries a
    half came from a name that named both leaves. And one whose facing side is
    named by a FILE OF ITS OWN was photographed alone: these albums mix the two
    — the opening leaves of an album are single frames and the rest
    are spreads — and expanding such a page would invent a second copy of a side
    the album already has.

    A third is a page whose frame SHOWS one page, which only the image can tell
    — `single`, the caller's, since this module reads names alone. An album may
    shoot its blank leaves 31 and 31а standing up among spreads lying on their
    side, with no file for their backs; split, л. 31 opened on the left half of
    its own page, and 31об was claimed by both frames.
    """
    pages = list(pages)
    have = {p.key for p in pages}
    out: list[Page] = []
    for page in pages:
        number, verso = next_side(page)
        if (page.half or not page.is_folio or (number, "", verso) in have
                or (single is not None and single(page))):
            out.append(page)
            continue
        out.append(Page(page.number, page.letter, page.verso,
                        page.frame, page.name, "L"))
        out.append(Page(number, "", verso, page.frame, page.name, "R"))
    return sorted(out)


@dataclass(frozen=True)
class AlbumReport:
    pages: tuple[Page, ...]
    unparseable: tuple[str, ...]
    first_label: str | None     # as the album has it, lettered leaves included
    last_label: str | None
    first_folio: int | None     # the plain run the album claims to cover
    last_folio: int | None
    missing_pages: tuple[str, ...]      # folio sides absent from the album
    duplicate_pages: tuple[str, ...]    # the same folio side photographed twice
    frame_gaps: tuple[tuple[int, int], ...]
    outside_range: tuple[str, ...]      # folios outside a declared range

    @property
    def ok(self) -> bool:
        return not (self.unparseable or self.missing_pages or self.duplicate_pages
                    or self.outside_range)


def _expected_sides(first: int, last: int) -> list[tuple[int, str, bool]]:
    """Every side of the plain run. A LETTERED leaf (12а) is an extra the
    archivist bound in, never something whose absence can be inferred."""
    return [(n, "", verso) for n in range(first, last + 1) for verso in (False, True)]


def check_album(names: Iterable[str], *,
                expect_first: int | None = None,
                expect_last: int | None = None) -> AlbumReport:
    """Continuity of an album, optionally against a declared folio range.

    A missing page is reported per SIDE, because that is how the loss behaves:
    a recto absent while its verso is present means the godparents of every
    christening on the facing page are gone, not that a leaf is missing.

    Frame gaps are reported but are NOT a defect on their own — a leaf whose
    blank verso was not worth a frame leaves one, and every дело has a few.
    """
    pages, bad = parse_album(names)
    folios = [p for p in pages if p.is_folio]

    seen: dict[tuple[int, str, bool], list[Page]] = {}
    for p in folios:
        seen.setdefault(p.key, []).append(p)

    duplicates = tuple(page[0].label for page in
                       sorted((v for v in seen.values() if len(v) > 1),
                              key=lambda v: v[0].key))

    # The expected run is derived from the PLAIN folios only. An album that
    # opens on a lettered leaf (an album starting at л. 12а) does not thereby
    # claim to hold л. 12 — that leaf is the tail of
    # the previous album, and reporting it missing is noise, not a finding.
    plain = [p.number for p in folios if not p.letter]
    first = min(plain, default=None)
    last = max(plain, default=None)

    missing: list[str] = []
    if first is not None and last is not None:
        for side in _expected_sides(first, last):
            if side not in seen:
                number, _, verso = side
                missing.append(f"{number}{VERSO_SUFFIX}" if verso else str(number))

    outside: list[str] = []
    if expect_first is not None and expect_last is not None:
        lo, hi = min(expect_first, expect_last), max(expect_first, expect_last)
        outside = [p.label for p in folios if not lo <= p.number <= hi]

    frames = sorted(p.frame for p in pages)
    gaps = tuple((a, b) for a, b in pairwise(frames) if b - a > 1)

    return AlbumReport(
        pages=tuple(pages), unparseable=tuple(sorted(bad)),
        first_label=folios[0].label if folios else None,
        last_label=folios[-1].label if folios else None,
        first_folio=first, last_folio=last,
        missing_pages=tuple(missing), duplicate_pages=duplicates,
        frame_gaps=gaps, outside_range=tuple(sorted(set(outside))))


def format_report(report: AlbumReport, *, album: str = "") -> str:
    head = f"{album}: " if album else ""
    if report.first_label is None:
        total = len(report.pages) + len(report.unparseable)
        lines = [f"{head}{total} file(s), none carrying a лист — "  # i18n: content — the book's own words: лист, об, кадр
                 f"no folio numbering to check."]
        if report.unparseable:
            lines.append("  · e.g. " + ", ".join(report.unparseable[:3]))
        lines.append("  The other subcommands fall back to numbering pages by FRAME "
                     "(«кадр 12»), which reads fine but verifies nothing: a missing "  # i18n: content — the book's own words: лист, об, кадр
                     "leaf and a leaf filed under the wrong year both look tidy. "
                     "Rename the album (see the docs) before reading "
                     "a year twice.")
        return "\n".join(lines)
    lines = [f"{head}{len(report.pages)} frame(s), "
             f"лл. {report.first_label}–{report.last_label}"]  # i18n: content — the book's own words: лист, об, кадр
    if report.unparseable:
        lines.append(f"  ⚠ {len(report.unparseable)} unparseable name(s): "
                     + ", ".join(report.unparseable[:5]))
    if report.duplicate_pages:
        lines.append("  ⚠ photographed twice: " + ", ".join(report.duplicate_pages))
    if report.missing_pages:
        lines.append(f"  ⚠ {len(report.missing_pages)} page(s) absent from the album: "
                     + ", ".join(report.missing_pages[:20])
                     + (" …" if len(report.missing_pages) > 20 else ""))
        lines.append("    (a blank or an inserted foreign leaf is a normal cause — "
                     "check the archive's inventory before treating it as a loss)")
    if report.outside_range:
        lines.append("  🔴 outside the declared range — a leaf filed under the wrong year? "
                     + ", ".join(report.outside_range))
    if report.frame_gaps:
        pretty = ", ".join(f"{a}→{b}" for a, b in report.frame_gaps[:8])
        lines.append(f"  · {len(report.frame_gaps)} gap(s) in frame numbering: {pretty}")
    if report.ok:
        lines.append("  ✅ continuous: every side present, none doubled.")
    return "\n".join(lines)

