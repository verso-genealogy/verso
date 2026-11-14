"""Terraform resource-name (res_name) derivation helpers."""
import re
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass
from verso.ru.naming.transliteration import generate_res_name
from verso.core import places
from verso.ru.targets.geni.translator.about_sections import _DOC_ANCHOR




def _strip_last_name_token(res_name: str) -> str:
    """Return a version of `res_name` with the token immediately preceding
    the document anchor (`_mk_births_`, `_mk_marriages_`, `_mk_deaths_`,
    `_rs_`) removed, but only when at least three name-tokens sit between
    the date prefix and the anchor — i.e. there's a plausible surname
    token to strip. Returns the input unchanged otherwise.
    """
    m = _DOC_ANCHOR.search(res_name)
    if not m:
        return res_name
    prefix = res_name[:m.start()]
    suffix = res_name[m.start():]
    # Prefix shape: `_YYYY_MM_DD_<name_tokens>` (date always first 3 underscores).
    tokens = prefix[1:].split('_')
    # tokens = [YYYY, MM, DD, first, patr, (last?)] — need ≥6 for a strip.
    if len(tokens) < 6:
        return res_name
    last_us = prefix.rfind('_')
    if last_us <= 0:
        return res_name
    return prefix[:last_us] + suffix



def generate_res_name_2(year, month, day, first_name, middle_name="", last_name="",
                        document_name="", role="", record_number="",
                        # Callers pass "", a bare int (archive/record number)
                        # or None; `suffix_part` below treats falsy as absent
                        # and stringifies the rest.
                        suffix: str | int | None = "") -> str:
    # Pad year/month/day independently so a known month keeps its leading
    # zero when the day is unknown (and vice versa). Unknown components
    # render as empty so the `__+` regex below collapses them into a
    # single underscore, matching the legacy CSV pipeline where empty CSV
    # cells produced the same shape.
    def _fmt(v, width):
        if v is None or v == "":
            return ""
        try:
            return f"{int(v):0{width}d}"
        except (TypeError, ValueError):
            return str(v)

    date_part = f"{_fmt(year, 4)}_{_fmt(month, 2)}_{_fmt(day, 2)}"
    suffix_part = f"_{suffix}" if suffix else ""
    raw = f"_{date_part}_{first_name}_{middle_name}_{last_name}_{document_name}_{record_number}_{role}{suffix_part}"
    return re.sub(r"__+", "_", generate_res_name(raw))



def _location(name):
    """Look up a known place (the corpus's, `verso.core.places`). Unknown names produce
    None, which causes GeniEvent to drop the location block entirely."""
    if not name:
        return None
    return places.current().bodies.get(name)


def location_label(name: str | None) -> str | None:
    """Render a known place as a readable hierarchy string from its structured
    entry in the corpus's places — e.g. "село Нижняя Яичница, Глухоманский уезд,
    Захолустинская губерния, Россия". Returns None for unknown/blank names. Use
    this instead of carrying a free-text place string: the structured entry
    stays the single source of truth."""
    frag = _location(name)
    if not frag:
        return None
    fields = places.parse_body(frag)
    return ", ".join(fields[k] for k in places.FIELDS if fields[k]) or None



def _build_subfamily_union_res_name(
    member, *, year: int, h_index: object = None,
) -> str | None:
    """Legacy convention for sub-family union res_names:
        `{canon_first} {canon_mid} {canon_last} rs{record_number} {year}`
    fed through `generate_res_name()` with a single-pass
    `.strip().replace("  ", " ")` (matches the earlier generator).

    For hidden members (`hidden=True` placeholders) the `record_number`
    is the explicit `int` if set, else a synthetic `{h_index}-{number}`
    string built from the household index and member's slot number —
    which matches the legacy "X-Y" sentinel format that hidden
    ancestors used to carry directly.

    Returns None when there's no `record_number` and no `h_index` to
    synthesize one from.
    """
    rn = getattr(member, "record_number", None)
    if rn is None:
        if member.is_hidden() and h_index is not None:
            rn = f"{h_index}-{member.number}"
        else:
            return None
    p = getattr(member, "person", None)
    if p is None:
        return None
    first = p.get_canonical_name() or p.name_modern or ""
    mid = p.patr_modern or ""
    last = p.last_name_modern or ""
    raw = (
        f"{first} {mid} {last} rs{rn} {year}".strip().replace("  ", " ")
    )
    return generate_res_name(raw)
