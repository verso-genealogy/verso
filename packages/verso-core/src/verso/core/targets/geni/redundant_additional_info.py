"""Dead-`additional_info` detection (functional core) — RAI001.

`profiles_to_consolidate[target]["additional_info"]` is a list of supplementary
`GeniProfile`s merged into the canonical near the end of `finalize()`, with the
same fill-in-if-missing semantics as a per-record merge. It is the layer that
carries what the SOURCES do not: a surname recovered from Geni, a death bound
researched from a later census, a co-author's project membership.

That makes it the one layer where "adds nothing" is a real risk. A field it
supplies is silently discarded when the merge already has a value there — and
unlike `override`, which would at least have replaced it, `additional_info`
loses quietly. ROV001 does not cover this: it inspects the override assignment
only, and the two layers are applied by different code paths.

This module is a pure query over before/after snapshots the generator takes
around each merge. It performs no I/O and mutates nothing.

Detection is exact rather than causal: an entry is reported only when the merge
demonstrably changed NOTHING on the target. An entry that fills one field and
loses another is not reported — the surviving field makes it load-bearing, and
splitting it would report a live entry as dead.
"""
from dataclasses import dataclass
from typing import Any

from verso.core.targets.geni.redundant_overrides import values_equal

#: Distinct from the conflict (3), ROV001 (4), RIG001 (5) and RPF001 (6) codes.
REDUNDANT_ADDITIONAL_INFO_FAIL_EXIT_CODE = 7

#: Every field `_merge_consolidated` can write. `about` and `projects` are
#: included — the merge APPENDS to both, so a change there is a real change,
#: unlike the assign-only layer ROV001 watches.
ADDITIONAL_INFO_TRACKED_FIELDS: tuple[str, ...] = (
    "first_name", "middle_name", "last_name", "birth_last_name", "nicknames",
    "current_residence", "occupation", "cause_of_death", "about", "projects",
    "birth", "death", "baptism", "burial",
)


@dataclass(frozen=True)
class RedundantAdditionalInfo:
    """An `additional_info` entry whose merge changed nothing."""

    canonical: str        # canonical key, e.g. "marfa_maksimovna"
    index: int            # position in that cluster's additional_info list
    declared: tuple[str, ...]   # the fields the entry carries


def snapshot(profile: Any) -> dict[str, Any]:
    """Deep-enough copy of every tracked field, for before/after comparison.

    Lists are copied because the merge mutates them in place; the event and
    date objects are compared structurally by `values_equal`, and the merge
    replaces rather than mutates them, so holding the reference is sound.
    """
    values: dict[str, Any] = {}
    for field in ADDITIONAL_INFO_TRACKED_FIELDS:
        value = getattr(profile, field, None)
        values[field] = list(value) if isinstance(value, list) else value
    return values


def detect_redundant_additional_info(
        canonical: str, index: int, add_info: Any,
        before: dict[str, Any], after: dict[str, Any],
) -> RedundantAdditionalInfo | None:
    """Return a finding when merging `add_info` changed nothing, else None."""
    if any(not values_equal(before.get(field), after.get(field))
           for field in ADDITIONAL_INFO_TRACKED_FIELDS):
        return None
    return RedundantAdditionalInfo(
        canonical=canonical, index=index,
        declared=tuple(
            field for field in ADDITIONAL_INFO_TRACKED_FIELDS
            if getattr(add_info, field, None)),
    )


def format_redundant_additional_info_report(
        findings: list[RedundantAdditionalInfo]) -> str:
    """Render a human-readable warning, or "" when there are none."""
    if not findings:
        return ""
    lines = [
        f"warning: {len(findings)} dead additional_info entry/entries "
        "[RAI001] — merging it changed no field on the canonical, so every "
        "value it declares was already there and was silently discarded. "
        "Either the entry is stale, or it was meant to CHANGE a value and "
        "belongs in `override` instead — additional_info fills blanks, it "
        "never replaces:",
    ]
    lines.extend(
        f"  - {f.canonical}[{f.index}] declares "
        f"{', '.join(f.declared) or '(nothing)'}"
        for f in findings)
    return "\n".join(lines)


def exit_code_for_redundant_additional_info(
        findings: list[RedundantAdditionalInfo], *,
        fail_on_conflicts: bool) -> int:
    """Exit code contributed by RAI001: non-zero only when failing is
    requested and findings exist; otherwise 0 (warn-only)."""
    return (REDUNDANT_ADDITIONAL_INFO_FAIL_EXIT_CODE
            if (findings and fail_on_conflicts) else 0)
