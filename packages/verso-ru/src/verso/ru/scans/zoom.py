"""Where on a leaf a named column and a numbered row are — the second reading tier.

Reading a metric book is two-tier and both tiers are obligatory: sweep at the
part preset to FIND a record, then re-crop at 4–9× to READ every name that will
enter the DSL. The sweep tier is `verso scans crops`; this module is the geometry
of the second one, and it exists because that crop was being cut by hand, four
numbers at a time, dozens of times a year.

Two failures made it worth naming the box instead of typing it:

* **The band lands on the wrong record.** Guessing a y-fraction for «the third
  entry» put the crop on the second one — each time costing a re-cut, and once
  nearly attributing another family's godparents. `row(3, 5)` cannot drift.
* **The window lands on the wrong column.** Two surnames one letter apart turn
  on that letter, and telling them apart needs the *godparents* column at 8× —
  not the parents column that a full-width crop centres on.

The column windows below are **measured on one дело's leaves** (~950 px
across) and deliberately OVERLAP: a scribe's column boundary wanders by a
few points between leaves, an overlap costs nothing, and a name cut in half by
an exact boundary costs a whole re-crop. They are a starting box, not a
measurement of the printed rule — `--box` overrides them whenever a leaf sits
differently in the frame.

Pure and dependency-free, like `folio`: the arithmetic is what is worth testing,
and it must run on a machine without Pillow. The window itself (`Box`) is the
core's (`verso.core.scans.window`): it knows no part of a book.
"""
from __future__ import annotations

from verso.core.scans.window import FULL_WIDTH, Box
from verso.ru.messages import t

__all__ = ["COLUMNS", "DEFAULT_TOP", "column_window", "resolve", "row_band"]

# Fraction of the leaf that the printed running header and the column titles
# occupy. Rows are numbered within the writing area BELOW it, because that is how
# a reader counts them — «третья запись сверху» means the third written row, not
# the third band of the paper.
#
# Measured on that дело: the running header, the rule under it and the two-line
# column titles together run to about 0.17. (`crops --top` defaults to 0.07 for
# a different reason — a half-page sweep keeps the titles in view to orient the
# reader, and can afford the space.)
DEFAULT_TOP = 0.17

# A row band is grown by this much on each side. Records are NOT equal height —
# a monthly total («Итого въ Маѣ …») eats a row's worth of space and the entries
# around it stretch — so an even division is a first guess and the pad is what
# keeps the guess usable.
DEFAULT_PAD = 0.02

# (x0, x1) per part and column, as fractions of the leaf width.
#
# ч.1 «О родившихся» (verso carries everything in that дело, incl. воспріемники):
#     счётъ | мѣсяцъ и день | имена родившихся | родители | воспріемники
# ч.2 «О бракосочетавшихся»: the verso carries groom and bride, the RECTO the
#     sureties — so `sureties` is a window on the facing leaf, not this one.
# ч.3 «О умершихъ»: verso carries name, age and cause together.
COLUMNS: dict[int, dict[str, tuple[float, float]]] = {
    1: {
        "count":      (0.00, 0.18),
        "dates":      (0.10, 0.32),
        "name":       (0.22, 0.40),
        "parents":    (0.28, 0.78),
        "godparents": (0.55, 1.00),
    },
    2: {
        "count":      (0.00, 0.14),
        "dates":      (0.06, 0.22),
        "groom":      (0.15, 0.58),
        "bride":      (0.50, 1.00),
        "sureties":   (0.15, 0.75),   # on the facing RECTO
    },
    3: {
        "count":      (0.00, 0.18),
        "dates":      (0.10, 0.30),
        "deceased":   (0.15, 0.64),
        "age":        (0.52, 0.78),
        "cause":      (0.68, 1.00),
    },
}

def column_window(part: int | None, column: str | None) -> tuple[float, float]:
    """(x0, x1) for a named column of a part. Unnamed ⇒ the whole leaf width."""
    if column is None:
        return FULL_WIDTH
    if part is None:
        raise ValueError(f"--col {column!r} needs --part (columns differ by part)")
    try:
        windows = COLUMNS[part]
    except KeyError:
        raise ValueError(str(t("scans.zoom.no_presets", part=part))) from None
    try:
        return windows[column]
    except KeyError:
        known = ", ".join(sorted(windows))
        raise ValueError(str(t("scans.zoom.no_column", part=part, column=repr(column), known=known))) from None


def row_band(row: int, of: int, *, top: float = DEFAULT_TOP,
             bottom: float = 1.0, pad: float = DEFAULT_PAD) -> tuple[float, float]:
    """(y0, y1) for row `row` of `of`, counted in the writing area below the header.

    An even division, padded. Records are not equal height, so this is a first
    guess that lands on the right record and may clip its neighbours in — which
    is the harmless direction to be wrong in.

    `bottom` matters as much as `top`: a leaf photographed with the table's edge
    in frame, or a page whose last third is the priest's signatures, divides
    into rows that are all too tall and all shifted down. Both come from the
    album's `scans.toml` when it has them.
    """
    if of < 1:
        raise ValueError("--row N/M needs M ≥ 1")
    if not 1 <= row <= of:
        raise ValueError(f"--row {row}/{of}: row must be within 1..{of}")
    if not top < bottom:
        raise ValueError(f"the writing area needs top < bottom, got {top} and {bottom}")
    span = (bottom - top) / of
    y0 = top + span * (row - 1) - pad
    y1 = top + span * row + pad
    return (max(0.0, y0), min(1.0, y1))


def resolve(*, part: int | None = None, column: str | None = None,
            row: tuple[int, int] | None = None, box: tuple[float, ...] | None = None,
            top: float = DEFAULT_TOP, bottom: float = 1.0,
            pad: float = DEFAULT_PAD) -> Box:
    """The crop window, from whichever of the three ways of naming it was used.

    `box` wins outright — it is the escape hatch for a leaf that sits differently
    in the frame. Otherwise `column` picks x and `row` picks y, and either may be
    omitted (the whole width, or the whole writing area).
    """
    if box is not None:
        x0, y0, x1, y1 = box
        if not (x0 < x1 and y0 < y1):
            raise ValueError(f"--box wants x0 y0 x1 y1 with x0<x1 and y0<y1, got {box}")
        if not all(0.0 <= v <= 1.0 for v in box):
            raise ValueError(f"--box takes FRACTIONS of the leaf, not pixels: {box}")
        return Box(x0, y0, x1, y1)

    x0, x1 = column_window(part, column)
    y0, y1 = (row_band(*row, top=top, bottom=bottom, pad=pad) if row
              else (top, bottom))
    return Box(x0, y0, x1, y1)
