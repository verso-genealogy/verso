"""The invisible per-section sort-date marker of a profile's `about` (out of the
plugin's translator, which writes it).

The translator appends `<!--sd:YYYY-MM-DD-->` to each about-section header line so that
sections of one year sort by their full date; the profile strips every marker when it
renders the about, so none reaches Geni.
"""
from __future__ import annotations

import re

SECTION_DATE_MARKER = re.compile(r'<!--sd:(\d{4})-(\d{2})-(\d{2})-->')


def marker(year: object, month: object, day: object) -> str | None:
    """The marker of a date, or None when the date is incomplete (a year-only record)."""
    try:
        iso = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return f"<!--sd:{iso}-->"


def strip_section_date_markers(about):
    """Remove every invisible `<!--sd:YYYY-MM-DD-->` sort marker. Called at
    render time so the markers never reach the Geni document body."""
    if not about:
        return about
    return SECTION_DATE_MARKER.sub("", about)
