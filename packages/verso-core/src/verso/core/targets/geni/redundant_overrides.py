"""Redundant-override detection (functional core) — ROV001.

`profiles_to_consolidate[target]["override"]` UNCONDITIONALLY replaces fields
on the consolidated profile, after every merge (see
`TerraformGenerator._apply_profile_overrides`). When the value it writes is
already the value present, the override does nothing today — and is a latent
silent veto: a later DSL correction gets quietly re-overwritten and never
reaches Geni.

This module is a pure query over before/after snapshots the generator takes
around the assignment. It performs no I/O and mutates nothing.

An override supplying a value the sources do NOT carry (a Geni-recovered
surname, per the `additional_info_belongs_in_override_layer` note) changes the
profile and is therefore not a no-op — this check structurally cannot reach it.
"""
from dataclasses import dataclass
from typing import Any

#: Distinct from CONFLICT_FAIL_EXIT_CODE (3) so CI can tell the two apart.
REDUNDANT_OVERRIDE_FAIL_EXIT_CODE = 4

#: Fields `_apply_profile_overrides` ASSIGNS. `about` is deliberately absent:
#: it is APPENDED, so "already equal" is not a no-op there.
OVERRIDE_TRACKED_FIELDS: tuple[str, ...] = (
    "first_name", "middle_name", "last_name", "birth_last_name",
    "current_residence", "occupation", "nicknames",
    "birth", "death", "baptism", "burial",
)


@dataclass(frozen=True)
class RedundantOverride:
    """An `override` field whose value the profile already had."""

    canonical: str   # canonical key, e.g. "savva_fedorovich"
    field: str       # "first_name", "current_residence", "birth", ...
    value: str       # rendered value, for the report


#: Every field that distinguishes one rendered `GeniDate` from another.
#: `GeniDate.__eq__` compares ONLY (day, month, year) — deliberately, for merge
#: logic — so `circa 1805 == between 1805 and 1809` is True. Leaning on that
#: here would call a range-narrowing override dead when it plainly is not.
_DATE_STRUCTURAL_ATTRS = (
    "day", "month", "year", "circa",
    "date_range", "end_day", "end_month", "end_year", "end_circa",
)


def _render(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def values_equal(old: Any, new: Any) -> bool:
    """Structural equality — everything that reaches the generated terraform.

    Falls back to `==` for strings and lists, where it means what it says.
    """
    if old is None or new is None:
        return old is None and new is None
    if hasattr(old, "date") and hasattr(old, "location"):          # GeniEvent
        return (values_equal(old.date, new.date)
                and old.location == getattr(new, "location", None))
    if hasattr(old, "year") and hasattr(old, "circa"):             # GeniDate
        return all(getattr(old, attr, None) == getattr(new, attr, None)
                   for attr in _DATE_STRUCTURAL_ATTRS)
    return bool(old == new)


def detect_redundant_overrides(
        canonical: str, before: dict[str, Any], after: dict[str, Any], *,
        suppressed_fields: frozenset[str] | set[str] = frozenset(),
) -> list[RedundantOverride]:
    """Return the override fields whose removal would change nothing.

    `before` holds a deep copy of each field the override sets, captured
    BEFORE application; `after` holds the same keys read back afterwards.

    `suppressed_fields` names the fields whose override silenced a
    consolidation conflict (`resolved_by_override`). Such an override is
    load-bearing even when its value is a no-op — dropping it would surface a
    real source disagreement — so it is never reported. "Dead" means removal
    changes neither the rendered profile NOR the conflict set.
    """
    return [
        RedundantOverride(canonical=canonical, field=field,
                          value=_render(after.get(field)))
        for field, old in before.items()
        if field not in suppressed_fields
        and values_equal(old, after.get(field))
    ]


def format_redundant_override_report(
        findings: list[RedundantOverride]) -> str:
    """Render a human-readable warning, or "" when there are none."""
    if not findings:
        return ""
    lines = [
        f"warning: {len(findings)} redundant override field(s) [ROV001] — the "
        "override sets a value the consolidated profile already has. It "
        "changes nothing today and silently re-imposes the old value if the "
        "DSL is later corrected. Remove the field, and the whole `override` "
        "entry if it empties:",
    ]
    lines.extend(
        f"  - {f.canonical}.{f.field} = {f.value}" for f in findings)
    lines.append(
        "  Fix them all with: "
        "verso strip-dead-overrides --village <village>")
    return "\n".join(lines)


def exit_code_for_redundant_overrides(
        findings: list[RedundantOverride], *,
        fail_on_conflicts: bool) -> int:
    """Exit code contributed by ROV001: non-zero only when failing is
    requested and findings exist; otherwise 0 (warn-only)."""
    return (REDUNDANT_OVERRIDE_FAIL_EXIT_CODE
            if (findings and fail_on_conflicts) else 0)
