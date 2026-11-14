"""Ignore-rule predicate and RIG001 detection (functional core).

`profiles_to_consolidate[target]["ignore"]` declares values the consolidation
merge should drop. The same test — "does any entry declare this value for this
attribute?" — is consulted from three places: the seed-scrub, the merge, and
conflict detection. This module owns that test, so every consultation is
recorded in one place and an entry that never matched is provably dead.

Detection is CAUSAL, not differential: a rule that never fires cannot have
affected anything, so there are no false positives. It is correspondingly
conservative — an entry that fires but changes nothing is not reported.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Distinct from CONFLICT_FAIL_EXIT_CODE (3) and
#: REDUNDANT_OVERRIDE_FAIL_EXIT_CODE (4) so CI can tell the three apart.
REDUNDANT_IGNORE_FAIL_EXIT_CODE = 5


@dataclass(frozen=True)
class RedundantIgnore:
    """An `ignore` entry whose predicate never matched anything."""

    canonical: str                 # canonical key, e.g. "varvara_lavrovna"
    index: int                     # position in that cluster's ignore list
    declared: tuple[str, ...]      # the attributes the entry declares
    #: Why it never fires, when the caller knows — since 2026-09-25 usually a
    #: retraction on a folded record that already withholds the same date.
    because: str = ""


def matches_ignore(attr: str, value, ignore: list[dict[str, Any]] | None, *,
                   seen: set[tuple[str, int]] | None = None,
                   canonical: str | None = None) -> bool:
    """Does any ignore entry declare `value` for `attr`?

    Every match is recorded into `seen` as `(canonical, index)` when both are
    supplied. Deliberately does NOT short-circuit: when two entries declare
    the same value both are genuinely consulted, and recording only the first
    would report the second as dead. Ignore lists hold one or two entries, so
    the full scan costs nothing.
    """
    hit = False
    for index, entry in enumerate(ignore or []):
        if entry.get(attr) == value:
            hit = True
            if seen is not None and canonical is not None:
                seen.add((canonical, index))
    return hit


def collect_redundant_ignores(
        profile_ignores: dict[str, list[dict[str, Any]]],
        seen: set[tuple[str, int]], *,
        explain: Callable[[str, dict[str, Any]], str] | None = None,
) -> list[RedundantIgnore]:
    """Every configured ignore entry that `seen` never recorded.

    `explain(canonical, entry)` may say why the entry is dead; it is asked
    only about entries already found dead, so it cannot change the verdict.
    """
    findings: list[RedundantIgnore] = []
    for canonical, entries in profile_ignores.items():
        for index, entry in enumerate(entries):
            if (canonical, index) in seen:
                continue
            findings.append(RedundantIgnore(
                canonical=canonical, index=index,
                declared=tuple(attr for attr, val in entry.items() if val),
                because=explain(canonical, entry) if explain else "",
            ))
    return findings


def format_redundant_ignore_report(findings: list[RedundantIgnore]) -> str:
    """Render a human-readable warning, or "" when there are none."""
    if not findings:
        return ""
    lines = [
        f"warning: {len(findings)} ignore entry/entries [RIG001] that never "
        "fire — no source record carries the declared value, so the rule can "
        "never match and removing it changes nothing. Delete the entry (and "
        "the whole `ignore` list if it empties):",
    ]
    lines.extend(
        f"  - {f.canonical}[{f.index}] declares "
        f"{', '.join(f.declared) or '(nothing)'}"
        + (f" — {f.because}" if f.because else "")
        for f in findings)
    return "\n".join(lines)


def exit_code_for_redundant_ignores(
        findings: list[RedundantIgnore], *,
        fail_on_conflicts: bool) -> int:
    """Exit code contributed by RIG001: non-zero only when failing is
    requested and findings exist; otherwise 0 (warn-only)."""
    return (REDUNDANT_IGNORE_FAIL_EXIT_CODE
            if (findings and fail_on_conflicts) else 0)
