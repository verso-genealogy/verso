"""Record chronological ordering and sort overrides."""
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    pass




def _month_num(m):
    return m.value if m is not None else None



# Per-(year, record_type) sort-key override. Some legacy CSVs were not
# ordered chronologically; for those years the default sort regresses
# line-diff parity. Supported values:
#   "record_num" — legacy CSV was ordered by record_num first.
#   "dsl"        — legacy output preserves original CSV row order, which
#                  the DSL file mirrors as declaration order. Stable-sort
#                  on a constant key keeps the DSL order untouched.
SORT_OVERRIDE: dict[tuple[int, str], str] = {
    (1802, "death"): "record_num",
    # Birth years where legacy preserves the source CSV's row order
    # instead of re-sorting chronologically — typically because the
    # underlying book had non-chronological page layouts (December-of-
    # prev-year front pages, or record-number sequence didn't match
    # date). Opt these years into "dsl" to mirror legacy's ordering.
    # Each entry was validated empirically against the earlier generator's
    # output to ensure "dsl" reduces diff.
    (1784, "birth"): "dsl",
    (1794, "birth"): "dsl",
    (1799, "birth"): "dsl",
    (1800, "birth"): "dsl",
    (1801, "birth"): "dsl",
    (1802, "birth"): "dsl",
    (1803, "birth"): "dsl",
    (1804, "birth"): "dsl",
    (1805, "birth"): "dsl",
    (1806, "birth"): "dsl",
    (1807, "birth"): "dsl",
    (1808, "birth"): "dsl",
    (1809, "birth"): "dsl",
    (1810, "birth"): "dsl",
    (1811, "birth"): "dsl",
    (1812, "birth"): "dsl",
    (1813, "birth"): "dsl",
    (1814, "birth"): "dsl",
    (1815, "birth"): "dsl",
    (1817, "birth"): "dsl",
    (1818, "birth"): "dsl",
    (1819, "birth"): "dsl",
    (1822, "birth"): "chronological_gender",
    (1823, "birth"): "dsl",
    (1824, "birth"): "dsl",
    (1833, "birth"): "dsl",
    (1836, "birth"): "dsl",
    (1837, "birth"): "dsl",
    (1838, "birth"): "dsl",
}



def _chronological_key(rec, default_year, month_attr, day_attr, record_type=None) -> tuple[Any, ...]:
    """Sort key approximating legacy CSV-row / book-page order.

    Compares records by (year, month, day, record_num, gender_order).
    `year` uses the record's explicit year when set (December-of-previous-
    year rollover entries in a new book's first pages) and otherwise
    inherits from the records container. Unknown month/day fall back to
    0 so they cluster first in a year — matches how blank CSV cells
    flowed through the legacy pipeline. Within a same-day tie, male
    sorts before female — matches the CSV convention. Stable sort
    preserves DSL order for otherwise-indistinguishable records.

    Empirical note: no single sort key matches all of legacy's per-year
    emission orders. Chronological primary yields the best net parity
    improvement across the Горюхино corpus — individual years where
    legacy used a record_num-first CSV still end up with residual
    ordering diff, but the aggregate diff shrinks substantially.
    `SORT_OVERRIDE[(year, record_type)] == "record_num"` opts those
    known-bad years out, returning a record-num-first tuple instead.
    """
    yr = getattr(rec, "year", None) or default_year or 0
    m = getattr(rec, month_attr, None)
    d = getattr(rec, day_attr, None)
    m_val = m.value if m is not None else 0
    d_val = d if d is not None else 0
    # Some legacy DSL files carry a non-numeric suffix in `record_num` (e.g.
    # the Cyrillic "15а" variant appears in Горюхино 1837 births to keep a
    # book's letter-suffixed numbering). Coerce to an int key so sort stays
    # total-orderable; non-numeric prefix/suffix falls back to 0.
    rec_num_raw = getattr(rec, "record_num", 0) or 0
    if isinstance(rec_num_raw, int):
        rec_num = rec_num_raw
    else:
        digits = "".join(ch for ch in str(rec_num_raw) if ch.isdigit())
        rec_num = int(digits) if digits else 0
    g = getattr(rec, "gender", None)
    g_order = 1 if g and getattr(g, "name", None) == "FEMALE" else 0
    override = (
        SORT_OVERRIDE.get((default_year, record_type))
        if record_type is not None and default_year is not None
        else None
    )
    if override == "record_num":
        return (rec_num, yr, m_val, d_val, g_order)
    if override == "dsl":
        # Constant key → Python's stable sort preserves DSL order.
        return (0,)
    if override == "month_rec":
        # Sort by (year, month, rec_num, day). Used when legacy's CSV
        # was rec_num-ordered within each month (so day sometimes runs
        # backwards) while months still appear chronologically.
        return (yr, m_val, rec_num, d_val, g_order)
    if override == "chronological_gender":
        # Same as default but gender breaks ties before record_num. Used for
        # years where legacy CSV listed same-day MALE before FEMALE regardless
        # of book record-number sequence.
        return (yr, m_val, d_val, g_order, rec_num)
    return (yr, m_val, d_val, rec_num, g_order)
