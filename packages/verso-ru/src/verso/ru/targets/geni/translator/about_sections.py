"""Document 'about' section assembly and short-comment extraction."""
import re
from typing import TYPE_CHECKING

from verso.core.targets.geni.about import SECTION_DATE_MARKER, marker
if TYPE_CHECKING:
    pass




# Fix #2: bi-directional stripping of last_name tokens in res_names so
# consolidation keys match regardless of whether the DSL Person has
# `last_name_modern` set. Legacy CSV often had the surname column empty
# for records where today's DSL has it populated (or vice versa), and the
# `profile_move_list` reflects legacy's shape — so literal lookups miss.
_DOC_ANCHOR = re.compile(r'_(mk_(?:births|marriages|deaths)|rs)_')



# Match ANY about-section header that ends in a 4-digit year, capturing the
# leading kind text and the year. Originally limited to `МК|РС`, but census
# documents can carry an arbitrary `document_type` label (e.g. the 1897
# "1-я всеобщая перепись"); an unrecognised header would be treated as an
# override appendix and shoved to the end, breaking chronological order.
# `[^<]*?` is non-greedy so the year matched is the real trailing one (a
# digit inside the label like "1-я" / "38-го" has fewer than 4 digits and is
# skipped). Village names carry no 4-digit runs.
_ABOUT_SECTION_HEADER = re.compile(
    r'<strong>([^<]*?)(\d{4})\s*:</strong>',
)


# Invisible per-section sort-date marker. The translator appends one to each
# about-section header line (via `inject_section_date_marker`, called from
# `_profile_from_person`) carrying the record's full YYYY-MM-DD, so
# `_sort_about_sections` can order SAME-YEAR sections by full date instead of
# record-emission order (which groups all births before all marriages, making
# a Jan wedding sort after a Nov birth of the same year). Markers are stripped
# by `strip_section_date_markers` when the about is rendered, so they never
# reach Geni. Census/РС sections carry no day/month and get no marker; they
# already sort before МК for the same year via `_about_kind_priority`. The marker
# and its stripping are the core's since 0.1.0 (verso.core.targets.geni.about): the
# profile strips it when it renders.


def inject_section_date_marker(about, year, month, day):
    """Append an invisible `<!--sd:YYYY-MM-DD-->` marker to the first section
    header line of `about`. No-op when `about` has no `<strong>` header or the
    date is incomplete (e.g. a year-only census record)."""
    if not about or "</strong>" not in about:
        return about
    mark = marker(year, month, day)
    if mark is None:
        return about
    nl = about.find("\n")
    if nl == -1:
        return about + mark
    return about[:nl] + mark + about[nl:]


def _about_kind_priority(label: str) -> int:
    """Same-year tie-break: census-type sections (РС / перепись / other)
    sort before МК. Legacy stored `source_date=str(year)` for РС and a full
    `YYYY-MM-DD` for МК, so the shorter РС key sorted first for the same
    year; this preserves that ordering. Anything containing "МК" is an МК
    section (priority 1); everything else is census/other (priority 0)."""
    return 1 if "МК" in label else 0



def _sort_about_sections(about):
    """Sort a profile's about-block sections by year ascending.

    Mirrors the earlier generator, which sorted the fragments by their source date
    and so merged the about fragments chronologically. This translator accumulates
    fragments in record-emission order; this helper restores chronology.

    A "section" begins at a `<strong>МК|РС <place> <YEAR>:</strong>`
    header and runs until the next such header (or end of string).
    Sections are sorted by the captured year. Sort is stable for
    same-year sections, preserving insertion order. Anything before
    the first header (= leading indent) is preserved as-is.

    Returns input unchanged when there are 0 or 1 headers, or when
    `about` is falsy.
    """
    if not about:
        return about
    starts = [m.start() for m in _ABOUT_SECTION_HEADER.finditer(about)]
    if len(starts) <= 1:
        return about
    preamble = about[:starts[0]]
    # Strip the inter-section separator (any trailing whitespace) from
    # each section's body so the rejoin produces a consistent separator
    # regardless of the original ordering.
    sep = "\n\n        "
    sections: list[tuple[int, int, int, int, int, str]] = []
    appendix_chunks: list[str] = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(about)
        body = about[s:end].rstrip()
        # Within a section's body, split at the inter-section separator.
        # The first part is the section's natural content (the
        # `<strong>` header + Титул/Комментарий lines). Any remaining
        # parts are the override.about appendix that the earlier generator
        # appended AFTER all sorted sections, but this translator's
        # record-emission order may have left
        # mid-stream — extract them so they can be re-appended at end.
        parts = body.split(sep)
        section_body = parts[0]
        appendix_chunks.extend(parts[1:])
        m = _ABOUT_SECTION_HEADER.search(section_body)
        year = int(m.group(2)) if m else 9999
        kind_prio = _about_kind_priority(m.group(1)) if m else 9
        # Full-date tie-break within the same (year, kind): read the
        # invisible <!--sd:YYYY-MM-DD--> marker. Sections without one (РС /
        # year-only records) get a sentinel (13, 32) so they keep their
        # original-index order after any dated sections in the same group.
        md = SECTION_DATE_MARKER.search(section_body)
        month = int(md.group(2)) if md else 13
        day = int(md.group(3)) if md else 32
        sections.append((year, kind_prio, month, day, i, section_body))
    # Stable sort: (year, kind_priority, month, day, original_index). Kind
    # priority places РС before МК for same-year sections (legacy
    # convention); month/day then order same-year same-kind sections
    # chronologically (e.g. a Jan wedding before a Nov birth).
    sections.sort(key=lambda t: (t[0], t[1], t[2], t[3], t[4]))
    # Preserve the original trailing whitespace of the last section
    # (legacy emits a trailing newline before EOT closure).
    last_orig_end = len(about)
    last_orig_start = starts[-1]
    trailing = about[last_orig_start:last_orig_end][len(about[last_orig_start:last_orig_end].rstrip()):]
    pieces = [t[-1] for t in sections] + appendix_chunks
    return preamble + sep.join(pieces) + trailing



# Legacy's source CSVs carried two comment columns: `авторский комментарий`
# (short form, appended to `Имена в МК:`) and `пометки` (long form,
# separate `>` line). The DSL preserved only the long form. Reconstruct
# the short form from known patterns in the long form so `Имена в МК:`
# matches legacy.
_SHORT_COMMENT_PATTERNS = [
    "Населенный пункт и сословие восприемника не указаны",
    "Населенный пункт и сословие отца не указаны",
    "Сословие и населенный пункт восприемника не указаны",
    "Населенный пункт восприемника не указан",
    "Населенный пункт отца не указан",
    "Сословие восприемника не указано",
    "Сословие отца не указано",
    "Отчество отца не указано",
    "Имя отца не указано",
    "Населенный пункт не указан",
    "Восприемники не указаны",
    "Имя отца не видно",
    "Отчество отца неразборчиво написано",
    "Имена не видно полностью из-за повреждения страницы",
    "Помещица указана как",
    "Помещик указан как",
    "Помещик указан только",
    "Помещик укзан только",  # legacy typo preserved in source CSVs
    "Помещица указана только",
]



def _extract_short_comment(comment: str | None) -> str | None:  # pyright: ignore[reportUnusedFunction]  # retained legacy helper, not currently wired
    """Return the legacy short-form suffix if `comment` starts with one of
    the known short-form patterns. The DSL stores the long form (from the
    `пометки` column); the short form was in a separate
    `авторский комментарий` column. Short form is usually a prefix of the
    long form, truncated before " в МК" or at the first period/comma.

    When the comment starts with a known pattern AND is NOT the long form
    (no " в МК, но " narrative), return the full comment as the short
    form. This preserves tails like ", взято из другой записи" that
    legacy appends directly to `Имена в МК:`.
    """
    if not comment:
        return None
    # Greedy match: walk semicolon-separated segments, consuming each
    # that starts with a known short-form pattern. Stop at the first
    # non-matching segment (likely a separate note like "Лист не указан
    # в МК") or the long-form narrative (" в МК, но "). Legacy joins
    # consecutive short-form segments on the same `Имена в МК:` line.
    segments = [s.strip() for s in comment.split(";")]
    first_segment = segments[0] if segments else ""
    matched_first_pattern = None
    for pattern in _SHORT_COMMENT_PATTERNS:
        if first_segment.startswith(pattern):
            matched_first_pattern = pattern
            break
    if not matched_first_pattern:
        return None
    # Long-form narrative? Return the bare pattern prefix so the
    # narrative ends up on its own separate `>` line.
    if " в МК, " in first_segment or " в МК но" in first_segment:
        return matched_first_pattern
    # Collect the first segment + any subsequent segments that also
    # match a short-form pattern.
    out = [first_segment]
    for seg in segments[1:]:
        if any(seg.startswith(p) for p in _SHORT_COMMENT_PATTERNS):
            out.append(seg)
        else:
            break
    return "; ".join(out)
