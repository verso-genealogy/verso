"""Where each record of a leaf begins, read off the leaf — so a whole page's windows are one step.

Reading a year straight from the scans into the DSL leaves no windows behind: a window is
remembered one record at a time, and a sweep of a thousand records does not stop for a
thousand of them; drawn afterwards by hand from ruler images, a year's windows cost a dozen
image reads. Yet the leaf says where its records are: a metric book's form opens every
record with its number in the счётъ column, at the height of the record's first line, and
nothing else is written there — the column holds a number a record and blank paper between.

So `detect` reads that column's row profile — the ink of each pixel row, less the slowly varying
part the column's ruled lines and the gutter's shadow contribute — and takes each run of ink as a
MARK: where a record (or a monthly total, or the next part's title) begins. A cut is laid in the
white above each mark, measured across the whole leaf so that a name starting a little above its
number stays in its record, and the record runs from its cut to the next one; the last runs to the
end of the writing. `pair` then hands the cuts to the records the reader names in page order —
what the reader has just written into the DSL — and refuses when the counts differ rather than
guess which mark was extra.

What a mark is not told from: a monthly total or a part's title written in the счётъ column is a
mark like a record's number. The reader names it `-` in the record list (`parse_keys`), which also
closes the record above it. A horizontal rule is thin and is dropped; a number the scribe wrote
small, or faded past the threshold, is missed — and the refusal says so, with the marks found and a
ruler image to correct them from (`ruler`).

`verso scans rows` draws the rulers; it writes no window. The windows are the review page's
(Verso writes `scans.toml`), which pairs the marks found here with the records named.

Pillow is imported where it is used, as in `level`: `parse_keys` and `pair` are pure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from verso.ru.messages import t
from verso.ru.scans.zoom import COLUMNS, DEFAULT_TOP

__all__ = ["count_window", "cuts_from", "detect", "pair", "parse_keys", "ruler", "sheet"]

# The height the profile is measured at: 0.0006 of a leaf a row, finer than any cut needs.
_HEIGHT = 1600
# The local paper is the brightest of a neighbourhood this share of the leaf's height across: wider
# than a stroke, narrower than the shadow a page's curve throws.
_PAPER = 1 / 40
# Darker than its paper by this many levels (of 255) is ink.
_INK = 40
# The baseline of a row profile — what a ruled line or a shadow puts into every row alike — is a low
# quantile of this share of the leaf around the row.
_BASELINE = 0.08
_BASELINE_QUANTILE = 0.2
# A leaf is cut into strips this share of its height to find the ruled lines down it: a number is
# shorter than a strip, a «1» too.
_LINE = 0.04
# ... and a rule's slant moves it this share of the leaf's height across a strip.
_DRIFT = 0.001
# ... and a rule covers this much (of 255) of a strip at its place.
_RULED = 128
# A row is ink in the счётъ column when it holds this share of the column's inkiest rows (`_floor`).
_FLOOR = 0.05
# A run of ink thinner than this is a ruled line, not a number.
_RULE = 0.003
# Pieces of ink closer than this are one mark: the strokes of one number, a number and its title.
_JOIN = 0.012
# A mark shorter than this, once joined, is a speck.
_SPECK = 0.004
# A mark's ink is at least this share of the page's typical (median) mark's: the faintest number
# is rarely under a tenth of the usual one, and a stray stroke is.
_SHARE = 0.1
# A cut is looked for this far above its mark: a record's first line stands at its number's height,
# its ascenders a little above.
_REACH = 0.03
# The last record runs to the last ink of the leaf, plus this — and no further than this many times
# the page's median record.
_TAIL = 0.01
_LAST = 1.5

# The share of a leaf the счётъ column takes, by part — the left edge of `zoom.COLUMNS`' «count».
COUNT = {part: columns["count"] for part, columns in COLUMNS.items()}
DEFAULT_COUNT = (0.0, 0.18)

@dataclass(frozen=True)
class Mark:
    """A run of ink in the счётъ column, as fractions of the leaf's height."""
    y0: float
    y1: float


@dataclass(frozen=True)
class Rows:
    """What `detect` found on a leaf: its marks top to bottom, and the cuts between records —
    one more cut than marks, `cuts[i]` opening mark i and the last closing the last mark."""
    marks: tuple[Mark, ...]
    cuts: tuple[float, ...]
    # A mark began on the `top` line and was left out (`detect`).
    cut: bool = False


@dataclass(frozen=True)
class Key:
    """One item of the reader's record list, in page order. `record` None is a mark that is no
    record: `-` one mark (a monthly total, a part's title, the column titles), `*` — last — every
    mark left. `carried` is a record begun on the leaf before (`+м4`, first): it holds the writing
    above the first mark."""
    record: int | str | None
    gender: str = ""
    carried: bool = False
    rest: bool = False

    def __str__(self) -> str:
        if self.record is None:
            return "*" if self.rest else "-"
        return ("+" if self.carried else "") + self.gender + str(self.record)


_KEY = re.compile(r"^(\+?)([мж]?)(#?[0-9]+[а-я]?)$")  # i18n: content — the book's own sex codes


def parse_keys(text: str) -> list[Key]:
    """The record list `+ж3,м1,ж1,-,м2,*` as keys, in page order.

    `м`/`ж` name the count series (ч. 1 and ч. 3 count the sexes apart), a bare number a record
    of one series (ч. 2); `-` is a mark that is no record, `*` (last) every mark after the last
    named one; `+` before the first key is a record carried over from the leaf before.

    >>> [str(k) for k in parse_keys("+ж3, м1 ,-,12,*")]
    ['+ж3', 'м1', '-', '12', '*']
    """
    items = [item.strip() for item in text.split(",")]
    keys: list[Key] = []
    for index, raw in enumerate(items):
        if raw in ("-", "*"):
            if raw == "*" and index != len(items) - 1:
                raise ValueError(str(t("scans.rows.rest_not_last")))
            keys.append(Key(None, rest=raw == "*"))
            continue
        match = _KEY.match(raw)
        if match is None:
            raise ValueError(str(t("scans.rows.bad_key", key=repr(raw))))
        carried, gender, number = match.groups()
        if carried and index:
            raise ValueError(str(t("scans.rows.carried_not_first", key=raw)))
        record: int | str = int(number) if number.isdigit() else number
        keys.append(Key(record, gender, bool(carried)))
    if not any(key.record is not None for key in keys):
        raise ValueError(str(t("scans.rows.no_records")))
    return keys


def count_window(part: int | None, x0: float, x1: float) -> tuple[float, float]:
    """The счётъ column as fractions of the frame, for a leaf lying between `x0` and `x1` of it.

    >>> count_window(1, 0.1, 0.6)
    (0.1, 0.19)
    """
    c0, c1 = COUNT.get(part, DEFAULT_COUNT) if part is not None else DEFAULT_COUNT
    return (round(x0 + c0 * (x1 - x0), 4), round(x0 + c1 * (x1 - x0), 4))


def pair(keys: list[Key], rows: Rows, top: float) -> list[tuple[Key, float, float]]:
    """Each record of `keys` with its band (y0, y1), in page order: the i-th mark's key takes the
    band from cut i to cut i+1, a `-` takes its band away from everyone, a carried record holds
    [top, the first cut).

    Refuses — ValueError, naming both counts — when the keys do not take the marks one for one
    (`*` takes any left over): which mark was extra, or which record's number was missed, is the
    reader's to say, never this function's to guess.
    """
    named = [key for key in keys if not key.carried and not key.rest]
    rest = bool(keys) and keys[-1].rest
    if len(named) > len(rows.marks) or (len(named) < len(rows.marks) and not rest):
        raise ValueError(str(t("scans.rows.counts_differ", keys=len(named), marks=len(rows.marks))))
    bands: list[tuple[Key, float, float]] = []
    if keys[0].carried:
        if not rows.cuts or rows.cuts[0] <= top:
            raise ValueError(str(t("scans.rows.nothing_carried")))
        bands.append((keys[0], top, rows.cuts[0]))
    for index, key in enumerate(named):
        if key.record is not None:
            bands.append((key, rows.cuts[index], rows.cuts[index + 1]))
    return bands


def cuts_from(values: list[float]) -> Rows:
    """`--cuts Y0 Y1 … Yn` as the rows they say: n marks, the i-th opening at cut i.

    >>> cuts_from([0.2, 0.31, 0.45]).cuts
    (0.2, 0.31, 0.45)
    """
    if len(values) < 2:
        raise ValueError(str(t("scans.rows.cuts_too_few")))
    if any(not 0.0 <= v <= 1.0 for v in values) or any(b <= a for a, b in pairwise(values)):
        raise ValueError(str(t("scans.rows.cuts_not_rising", cuts=" ".join(f"{v:g}" for v in values))))
    return Rows(tuple(Mark(a, a) for a in values[:-1]), tuple(values))


# --------------------------------------------------------------------------- detection

def _above(level: int) -> list[int]:
    """A `point` table: 255 at `level` and above, 0 below."""
    return [255 if v >= level else 0 for v in range(256)]


def _ink(region: Any) -> Any:
    """`region` in grey as ink (255) on nothing (0): darker than its local paper by `_INK`.

    The paper is the brightest of each neighbourhood — measured on a reduced copy and laid back,
    so a page's curve, the gutter's shadow and the phone's vignette are paper too."""
    from PIL import Image, ImageChops, ImageFilter
    w, h = region.size
    step = max(1, round(h * _PAPER / 4))
    small = region.resize((max(1, w // step), max(1, h // step)), Image.Resampling.BOX)
    paper = small.filter(ImageFilter.MaxFilter(5)).resize((w, h), Image.Resampling.BILINEAR)
    return ImageChops.subtract(paper, region).point(_above(_INK))


def _rules(ink: Any, height: int) -> Any:
    """The ruled lines running down `ink`, as a mask.

    A form rules its columns, and through the счётъ column four or five such lines run, each as
    much ink a row as a number — and broken where the pen skipped or the paper is pale, so no
    one stretch of a rule is a long run of ink. What a rule has and a number has not is
    persistence: cut the leaf into strips `_LINE` high, and a rule covers most of the strip at
    its place (give or take `_DRIFT` for a slant) in that strip AND the one above or below it,
    while a number, shorter than a strip, can cover at most one strip so. A rule across is thin,
    and `find_marks` drops it by its height."""
    from PIL import Image, ImageChops, ImageFilter
    w, h = ink.size
    strip = max(4, round(_LINE * height))
    drift = 2 * max(1, round(_DRIFT * height)) + 1
    near = ink.filter(ImageFilter.MaxFilter(drift))
    cover = near.resize((w, max(1, h // strip)), Image.Resampling.BOX).point(_above(_RULED))
    either = ImageChops.lighter(ImageChops.offset(cover, 0, 1), ImageChops.offset(cover, 0, -1))
    down = ImageChops.darker(cover, either).resize((w, h), Image.Resampling.NEAREST)
    return ImageChops.darker(down.filter(ImageFilter.MaxFilter(drift)), near)


def _strip(ink: Any, rules: Any) -> Any:
    """`ink` with its ruled lines taken out, a pixel wider than found."""
    from PIL import ImageChops, ImageFilter
    return ImageChops.subtract(ink, rules.filter(ImageFilter.MaxFilter(3)))


def _profile(ink: Any) -> list[float]:
    """The share of each pixel row that is ink."""
    from PIL import Image
    column = ink.resize((1, ink.height), Image.Resampling.BOX)
    return [v / 255 for v in column.tobytes()]


def _smooth(values: list[float], radius: int) -> list[float]:
    if radius < 1:
        return list(values)
    out: list[float] = []
    total = sum(values[:radius])
    n = len(values)
    for i in range(n):
        if i + radius < n:
            total += values[i + radius]
        if i - radius - 1 >= 0:
            total -= values[i - radius - 1]
        lo, hi = max(0, i - radius), min(n - 1, i + radius)
        out.append(total / (hi - lo + 1))
    return out


def _above_baseline(profile: list[float], radius: int) -> list[float]:
    """The profile less its local low quantile: what a ruled line (one crossing of every row) or
    a shadow puts into every row is taken out, a number's strokes stay."""
    n = len(profile)
    out: list[float] = []
    stride = max(1, radius // 8)
    base: list[float] = []
    for i in range(0, n, stride):
        window = sorted(profile[max(0, i - radius):i + radius + 1])
        base.append(window[int(len(window) * _BASELINE_QUANTILE)])
    for i in range(n):
        out.append(max(0.0, profile[i] - base[min(len(base) - 1, round(i / stride))]))
    return out


def _runs(signal: list[float], threshold: float) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, v in enumerate(signal):
        if v > threshold and start is None:
            start = i
        elif v <= threshold and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(signal)))
    return runs


def _floor(signal: list[float]) -> float:
    """The ink a row of the счётъ column needs to be part of a mark: `_FLOOR` of the inkiest rows
    but the few a rule across fills — the 99th percentile, not the maximum, which a rule sets."""
    if not signal:
        return 0.0
    ranked = sorted(signal)
    return ranked[min(len(ranked) - 1, int(len(ranked) * 0.99))] * _FLOOR


def find_marks(signal: list[float], height: int) -> list[tuple[int, int]]:
    """The marks of the счётъ column's signal, as row ranges: runs of ink, ruled lines dropped,
    near pieces joined, specks and the faint left out."""
    floor = _floor(signal)
    if floor <= 0:
        return []
    runs = [r for r in _runs(signal, floor) if r[1] - r[0] >= _RULE * height]
    joined: list[tuple[int, int]] = []
    for run in runs:
        if joined and run[0] - joined[-1][1] < _JOIN * height:
            joined[-1] = (joined[-1][0], run[1])
        else:
            joined.append(run)
    joined = [r for r in joined if r[1] - r[0] >= _SPECK * height]
    if not joined:
        return []
    weight = [sum(signal[a:b]) for a, b in joined]
    typical = sorted(weight)[len(weight) // 2]
    return [r for r, w in zip(joined, weight, strict=True) if w >= typical * _SHARE]


def _cut_above(leaf: list[float], top: int, floor: int) -> int:
    """The row in the white above a mark opening at `top`: the middle of the emptiest stretch of
    the leaf's profile within `_REACH` above it, the stretch nearest the mark of those as empty."""
    lo = max(floor, top - round(_REACH * len(leaf)))
    if lo >= top:
        return top
    window = leaf[lo:top + 1]
    least = min(window)
    best: tuple[int, int] | None = None
    start: int | None = None
    for i, v in enumerate(window + [least + 1]):
        if v <= least + 1e-9:
            start = i if start is None else start
        elif start is not None:
            best = (start, i)            # the last such stretch is the nearest the mark
            start = None
    assert best is not None
    return lo + (best[0] + best[1] - 1) // 2


def detect(page: Any, *, x0: float = 0.0, x1: float = 1.0, count: tuple[float, float] | None = None,
           top: float = DEFAULT_TOP, bottom: float = 1.0) -> Rows:
    """The marks and cuts of a leaf: `page` the frame as `open_page` gives it, the leaf lying
    between `x0` and `x1` of it, the счётъ column at `count` (fractions of the frame), the writing
    between `top` and `bottom`. All the results are fractions of the frame's height.

    A mark that begins on the `top` line is not taken: it is the column titles' printed text, or a
    number half above the line, cut by it — `Rows.cut` says so, and a `top` set a little higher or
    lower settles which."""
    from PIL import Image
    grey = page.convert("L")
    scale = _HEIGHT / grey.height
    if scale < 1:
        grey = grey.resize((max(1, round(grey.width * scale)), _HEIGHT), Image.Resampling.BOX)
    w, h = grey.size
    y_top, y_bottom = round(top * h), round(bottom * h)

    def frac(row: int) -> float:
        return round((y_top + row) / h, 3)

    if y_bottom - y_top < 8 or x1 - x0 <= 0:
        return Rows((), ())
    ink = _ink(grey.crop((round(x0 * w), y_top, round(x1 * w), y_bottom)))
    ink = _strip(ink, _rules(ink, h))
    c0, c1 = count if count is not None else count_window(None, x0, x1)
    span = ink.width / (x1 - x0)
    column = ink.crop((round((c0 - x0) * span), 0, round((c1 - x0) * span), ink.height))
    radius = max(1, round(_BASELINE * h))
    signal = _smooth(_above_baseline(_profile(column), radius), 1)
    leaf = _smooth(_above_baseline(_profile(ink), radius), 2)
    # Ink running on from the top line belongs to what the line cut — the column titles, a number
    # half above it — and, printed and heavy, would set the threshold for every number below.
    lead = 0
    floor = _floor(signal)
    while lead < len(signal) and signal[lead] > floor > 0:
        lead += 1
    signal[:lead] = [0.0] * lead
    found = find_marks(signal, h)
    if found and found[0][0] - lead < _JOIN * h and lead:
        lead, found = found[0][1], found[1:]   # the rest of it, past a skip of the pen
    cut = lead >= _RULE * h
    if not found:
        return Rows((), (), cut)
    cuts: list[int] = []
    floor = 0
    for a, b in found:
        cuts.append(_cut_above(leaf, a, floor))
        floor = b
    last_ink = max((i for i, v in enumerate(leaf) if v > max(leaf) * 0.08), default=found[-1][1])
    end = max(found[-1][1], last_ink) + round(_TAIL * h)
    if len(cuts) > 1:
        # Below the last record a page goes on — a monthly total, the clergy's signatures, the
        # edge of the book — so the last record is held to what a record of this page takes.
        heights = sorted(b - a for a, b in pairwise(cuts))
        end = min(end, cuts[-1] + round(heights[len(heights) // 2] * _LAST))
    cuts.append(min(ink.height, end))
    return Rows(tuple(Mark(frac(a), frac(b)) for a, b in found), tuple(frac(c) for c in cuts), cut)


# --------------------------------------------------------------------------- the reader's check

# A ruler is drawn this high; a sheet lays rulers side by side, so one image read checks a run of
# leaves.
RULER_HEIGHT = 1400
# Its grid: a faint line every `_GRID` of the frame's height, labelled every other one.
_GRID = 0.025
_MARK = (210, 30, 30)
_CUT = (20, 90, 220)
_GRIDLINE = (200, 200, 200)


def ruler(page: Any, rows: Rows, *, x0: float, x1: float, count: tuple[float, float], top: float,
          bottom: float, title: str, labels: list[str] | None = None) -> Any:
    """The leaf with what `detect` found drawn on it, for the reader to confirm before the windows are written.

    Each mark is a red bar beside the счётъ column, numbered in page order — the order the record
    list names them in; each cut a blue line across the leaf with its height, which `--cuts` takes
    as written; a grey grid every 0.025 of the frame for a cut to be read off where a mark is
    missing. `labels` (the record list's keys, one a mark) are written beside the numbers."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    grey = page.convert("L")
    w, h = grey.size
    lo, hi = max(0.0, top - 0.03), min(1.0, bottom)
    region = ImageOps.autocontrast(grey.crop((round(x0 * w), round(lo * h), round(x1 * w), round(hi * h))),
                                   cutoff=1)
    scale = RULER_HEIGHT / max(1, region.height)
    margin = 90
    image = Image.new("RGB", (round(region.width * scale) + margin, RULER_HEIGHT + 40), "white")
    image.paste(region.resize((round(region.width * scale), RULER_HEIGHT)).convert("RGB"), (margin, 40))
    draw = ImageDraw.Draw(image)
    small, large = ImageFont.load_default(size=18), ImageFont.load_default(size=30)

    def y_of(value: float) -> float:
        return 40 + (value - lo) / (hi - lo) * RULER_HEIGHT

    def x_of(value: float) -> float:
        return margin + (value - x0) / (x1 - x0) * region.width * scale

    step = 0
    while step * _GRID <= hi + 1e-9:
        value = step * _GRID
        if value >= lo:
            draw.line([(margin, y_of(value)), (image.width, y_of(value))], fill=_GRIDLINE, width=1)
            if step % 2 == 0:
                draw.text((image.width - 56, y_of(value) - 20), f"{value:.3f}", fill=(120, 120, 120), font=small)
        step += 1
    draw.text((margin, 4), _latin(title), fill=(0, 0, 0), font=large)
    draw.line([(x_of(count[0]), 40), (x_of(count[0]), image.height)], fill=_MARK, width=1)
    draw.line([(x_of(count[1]), 40), (x_of(count[1]), image.height)], fill=_MARK, width=1)
    for value in rows.cuts:
        draw.line([(margin, y_of(value)), (image.width, y_of(value))], fill=_CUT, width=3)
        draw.text((x_of(count[1]) + 6, y_of(value) - 22), f"{value:g}", fill=_CUT, font=small)
    for index, mark in enumerate(rows.marks):
        bar = x_of(count[0]) - 6
        draw.line([(bar, y_of(mark.y0)), (bar, max(y_of(mark.y1), y_of(mark.y0) + 6))], fill=_MARK, width=6)
        name = str(index + 1) + (f" {labels[index]}" if labels and index < len(labels) else "")
        draw.text((bar - 4 - large.getlength(name), y_of(mark.y0) - 4), name, fill=_MARK, font=large)
    return image


# The font Pillow carries has no Cyrillic; a leaf's label holds two words of it.
_LATIN = (("кадр", "frame "), ("об", "v"), ("л. ", "f. "), ("ч.", "part "))  # i18n: content — the book's own words: лист, ч., об, кадр


def _latin(text: str) -> str:
    """`text` in the letters the drawing font has: «кадр12» → «frame 12», «120об» → «120v».

    >>> _latin("л. 120об · ч.1")
    'f. 120v · part 1'
    """
    for word, latin in _LATIN:
        text = text.replace(word, latin)
    return text


def sheet(rulers: list[Any]) -> Any:
    """Rulers side by side, tops aligned, on white."""
    from PIL import Image
    gap = 24
    width = sum(r.width for r in rulers) + gap * (len(rulers) - 1)
    out = Image.new("RGB", (max(1, width), max((r.height for r in rulers), default=1)), "white")
    x = 0
    for r in rulers:
        out.paste(r, (x, 0))
        x += r.width + gap
    return out
