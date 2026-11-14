"""Consolidation-conflict detection (functional core).

When `profiles_to_consolidate` folds several per-record profiles into one
canonical profile, the merge (`tf_translator._merge_consolidated`) silently
discards a differing field value when nothing pins it. This module is a pure
query: given the accumulated `existing` profile and an `incoming` per-record
profile (plus the cluster's `preference`/`ignore` config), it returns the
values that would be silently lost — without mutating anything or performing
any I/O. The generator turns these into warnings.
"""
from dataclasses import dataclass
from typing import Any

from verso.core import plugins
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.redundant_ignores import matches_ignore
from verso.core.targets.geni.redundant_preferences import PinIsDead, record_preference_hit


@dataclass(frozen=True)
class ConsolidationConflict:
    """A field value silently dropped while merging one source record into a
    consolidated canonical profile."""

    canonical: str   # canonical key, e.g. "ivan_gavriilovich_lodaev"
    field: str       # "last_name", "birth.date", "cause_of_death", ...
    kept: str        # value retained on the canonical
    discarded: str   # value from `source` that was silently dropped
    source: str      # res_name of the record contributing the dropped value


def is_ignored_value(attr: str, value, ignore: list[dict[str, Any]] | None,
                     *, seen: set[tuple[str, int]] | None = None,
                     canonical: str | None = None) -> bool:
    """The cluster's `ignore` config declares this value should be dropped.

    Delegates to the shared predicate so the consultation is recorded for
    RIG001; the name is kept because callers and tests use it.
    """
    return matches_ignore(attr, value, ignore, seen=seen, canonical=canonical)


def matches_preference_alias(value, preference: dict[str, Any] | None,
                             override=None) -> bool:
    """The value survives as a nicknames alias — kept, not lost.

    `override.nicknames` REPLACES the merged nicknames wholesale (see
    `TerraformGenerator._apply_profile_overrides`, which runs after every
    merge), so when the override carries any nicknames it alone decides what
    survives: a `preference.nicknames` entry the override does not repeat is
    discarded before rendering, and vouching for it here would be a silent
    data loss — exactly what this module exists to catch. Conversely an alias
    kept only by `override.nicknames` is genuinely kept, so it must not be
    reported.
    """
    override_nicknames = list(getattr(override, "nicknames", None) or [])
    if override_nicknames:
        return value in override_nicknames
    return value in ((preference or {}).get("nicknames") or [])


def matches_preference_birth_name(
        value, preference: dict[str, Any] | None, *,
        seen: set[tuple[str, str]] | None = None,
        canonical: str | None = None) -> bool:
    """The dropped last_name is preserved as the canonical's `birth_last_name`
    (maiden name) — kept in a dedicated field, not lost. So pinning
    `preference.birth_last_name` to a married-out woman's maiden surname
    self-clears the maiden-vs-married `last_name` drop, with no redundant
    `ignore`/`nicknames` entry.

    A match is the `birth_last_name` pin doing work that its seed assignment
    alone would not, so it is recorded into `seen` for RPF001."""
    hit = bool(value) and value == (preference or {}).get("birth_last_name")
    if hit:
        record_preference_hit(seen, canonical, "birth_last_name")
    return hit


def resolved_by_override(field: str, override) -> bool:
    """The override pins this name field outright — an explicit resolution.
    (Alternative names are declared in `preference.nicknames`, not here.)"""
    return override is not None and bool(getattr(override, field, None))


def is_maiden_to_married_promotion(
        existing: GeniProfile, incoming: GeniProfile) -> bool:
    """`existing.last_name` is the maiden form and `incoming` carries the
    married form (its `birth_last_name` matches) — the merge adopts the
    married name rather than dropping anything."""
    return bool(existing.last_name
                and existing.last_name == incoming.birth_last_name)


def specific_dates_disagree(a, b) -> bool:
    """Both dates are *specific* (not `circa`, no range) and genuinely
    contradict — same precision component differs. A year-only date refined by
    a same-year full date is enrichment, not a contradiction."""
    if a is None or b is None:
        return False
    if a.circa or b.circa or a.date_range or b.date_range:
        return False
    if a.year and b.year and a.year != b.year:
        return True
    if a.year == b.year and a.month and b.month and a.month != b.month:
        return True
    if (a.year == b.year and a.month == b.month
            and a.day and b.day and a.day != b.day):
        return True
    return False


def _format_date(d) -> str:
    return ".".join(str(x) for x in (d.day, d.month, d.year) if x)


def detect_consolidation_conflicts(
        existing: GeniProfile, incoming: GeniProfile, *,
        canonical: str, source: str,
        preference: dict[str, Any] | None = None, ignore: list[dict[str, Any]] | None = None,
        override: GeniProfile | None = None,
        ignore_seen: set[tuple[str, int]] | None = None,
        preference_seen: set[tuple[str, str]] | None = None,
) -> list[ConsolidationConflict]:
    """Return the values the merge would silently drop when folding `incoming`
    into `existing`. Pure — never mutates its arguments.

    An `override` (the consolidation target's `override` GeniProfile) is an
    explicit resolution: when it pins an event, that event's date conflict is
    suppressed."""
    conflicts: list[ConsolidationConflict] = []

    if (incoming.last_name and existing.last_name
            and existing.last_name != incoming.last_name
            and "?" not in (existing.last_name, incoming.last_name)
            and not is_ignored_value("last_name", incoming.last_name, ignore,
                                     seen=ignore_seen, canonical=canonical)
            and not is_maiden_to_married_promotion(existing, incoming)
            and not matches_preference_alias(incoming.last_name, preference,
                                             override)
            and not matches_preference_birth_name(
                incoming.last_name, preference,
                seen=preference_seen, canonical=canonical)
            and not resolved_by_override("last_name", override)):
        conflicts.append(ConsolidationConflict(
            canonical=canonical, field="last_name",
            kept=existing.last_name, discarded=incoming.last_name,
            source=source,
        ))

    for field in ("middle_name", "birth_last_name"):
        kept = getattr(existing, field)
        discarded = getattr(incoming, field)
        if (discarded and kept and kept != discarded
                and "?" not in (kept, discarded)
                and not is_ignored_value(field, discarded, ignore,
                                         seen=ignore_seen, canonical=canonical)
                and not matches_preference_alias(discarded, preference,
                                                 override)
                and not resolved_by_override(field, override)):
            conflicts.append(ConsolidationConflict(
                canonical=canonical, field=field,
                kept=kept, discarded=discarded, source=source,
            ))

    if (incoming.cause_of_death and existing.cause_of_death
            and existing.cause_of_death != incoming.cause_of_death
            and not is_ignored_value(
                "cause_of_death", incoming.cause_of_death, ignore,
                seen=ignore_seen, canonical=canonical)):
        conflicts.append(ConsolidationConflict(
            canonical=canonical, field="cause_of_death",
            kept=existing.cause_of_death, discarded=incoming.cause_of_death,
            source=source,
        ))

    for event_name in ("birth", "death", "baptism", "burial"):
        if override is not None and getattr(override, event_name, None) is not None:
            continue  # explicitly resolved — the override pins this event
        existing_event = getattr(existing, event_name)
        incoming_event = getattr(incoming, event_name)
        if (existing_event is not None and incoming_event is not None
                and specific_dates_disagree(existing_event.date,
                                            incoming_event.date)
                and not is_ignored_value(f"{event_name}.date",
                                         incoming_event.date, ignore,
                                         seen=ignore_seen,
                                         canonical=canonical)):
            conflicts.append(ConsolidationConflict(
                canonical=canonical, field=f"{event_name}.date",
                kept=_format_date(existing_event.date),
                discarded=_format_date(incoming_event.date),
                source=source,
            ))

    return conflicts


# Distinct from `--strict`'s exit code 2 (skipped DSL files) so the two guards
# are tellable apart in CI / scripts.
CONFLICT_FAIL_EXIT_CODE = 3


# Name fields whose conflict is resolved by a `preference` pin (the discarded
# value becomes a `nicknames` alias). Date/cause-of-death conflicts need an
# `override` instead, so they're left out of the paste-ready suggestion.
_NAME_PIN_FIELDS = ("first_name", "middle_name", "last_name", "birth_last_name")


def _looks_like_birth_name(discarded: str, canonical: str) -> bool:
    """A dropped `last_name` that matches the consolidation key's own surname is
    the person's birth/maiden surname (the key is keyed on their birth family)
    — suggest it as `birth_last_name`, not a `nicknames` alias. A scribal
    variant of the kept surname (Мижуев/Анучкин) does NOT match the key and so
    still goes to `nicknames`."""
    translit = plugins.transliterator()(discarded).lower()
    return bool(translit) and translit in set(canonical.lower().split("_"))


def suggest_preference_pins(conflicts: list[ConsolidationConflict], *,
                            pin_is_dead: PinIsDead | None = None) -> str:
    """Group name-field conflicts by canonical into ready-to-paste `preference`
    pins (kept value pinned, dropped values preserved). A dropped `last_name`
    that is the key's own surname is suggested as `birth_last_name` (the maiden
    name of a married-out woman); every other dropped variant is preserved as a
    `nicknames` alias, mirroring how a clean sibling canonical resolves it.

    The kept value is left out where `pin_is_dead` says RPF001 would reject it
    — the seeding record already carries it, so the pin would write nothing
    and the alias alone resolves the conflict. Without `pin_is_dead` every
    kept value is pinned. Returns "" when no name-field conflicts are present."""
    by_canon: dict[str, dict[str, Any]] = {}
    for c in conflicts:
        if c.field not in _NAME_PIN_FIELDS:
            continue
        entry = by_canon.setdefault(
            c.canonical, {"fields": {}, "aliases": [], "birth_last_name": None})
        if (c.field not in entry["fields"]
                and not (pin_is_dead and pin_is_dead(c.canonical, c.field,
                                                     c.kept))):
            entry["fields"][c.field] = c.kept
        if c.field == "last_name" and _looks_like_birth_name(c.discarded, c.canonical):
            entry["birth_last_name"] = c.discarded
        elif c.discarded not in entry["aliases"]:
            entry["aliases"].append(c.discarded)
    if not by_canon:
        return ""
    lines = [
        "",
        # NB: the override-vs-preference nicknames rule is stated once, in
        # `format_conflict_report`'s header — repeating it here would put the
        # word "nicknames" into pins that deliberately suggest
        # `birth_last_name` instead.
        "Suggested preference pin(s) — paste into the cluster (resolves the "
        "name-variant conflicts above):",
    ]
    for canon, entry in by_canon.items():
        parts = [f'{f}="{v}"' for f, v in entry["fields"].items()]
        if entry["birth_last_name"]:
            parts.append(f'birth_last_name="{entry["birth_last_name"]}"')
        if entry["aliases"]:
            nicks = ", ".join(f'"{a}"' for a in entry["aliases"])
            parts.append(f"nicknames=[{nicks}]")
        lines.append(f"  {canon}:")
        lines.append(f'    "preference": GeniProfile({", ".join(parts)}),')
    return "\n".join(lines)


def format_conflict_report(conflicts: list[ConsolidationConflict], *,
                           pin_is_dead: PinIsDead | None = None) -> str:
    """Render a human-readable warning for the dropped values, or "" if none.
    `pin_is_dead` is handed to `suggest_preference_pins`."""
    if not conflicts:
        return ""
    lines = [
        f"warning: {len(conflicts)} consolidation field conflict(s) — a "
        "source record's value was silently dropped. Resolve by pinning the "
        "field via `override.<field>` (note: `preference.<field>` only picks "
        "the winner — it does NOT clear the drop), or list the dropped value "
        "in `ignore`, or keep it as an alias in `nicknames` — in "
        "`override.nicknames` when the cluster has an override, since that "
        "REPLACES the merged nicknames, otherwise `preference.nicknames`:",
    ]
    for c in conflicts:
        lines.append(
            f"  - {c.canonical}.{c.field}: kept {c.kept!r}, "
            f"dropped {c.discarded!r} (from {c.source})"
        )
    pins = suggest_preference_pins(conflicts, pin_is_dead=pin_is_dead)
    if pins:
        lines.append(pins)
    return "\n".join(lines)


def exit_code_for_conflicts(
        conflicts: list[ConsolidationConflict], *,
        fail_on_conflicts: bool) -> int:
    """Exit code contributed by conflicts: non-zero only when failing is
    requested and conflicts exist; otherwise 0 (warn-only)."""
    return CONFLICT_FAIL_EXIT_CODE if (conflicts and fail_on_conflicts) else 0
