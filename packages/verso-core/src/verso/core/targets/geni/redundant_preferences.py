"""Dead-preference detection (functional core) — RPF001.

`profiles_to_consolidate[target]["preference"]` pins the canonical form of a
name field. Unlike `override`, which assigns unconditionally after every merge,
a preference has exactly THREE effects, and a field that exercises none of them
is dead:

1. **Seed pin** — `TerraformGenerator._apply_preference` writes the declared
   value onto the profile that seeds the canonical, BEFORE any merge. It can
   matter only when the seed carried something else; writing the value already
   there leaves the profile untouched.
2. **Conflict silencing** — `matches_preference_birth_name` lets a `last_name`
   variant that equals the declared `birth_last_name` pass without being
   reported as a dropped value (a married-out woman's maiden surname).
3. **Alias realization** — `matches_preference_alias` / the merge's
   `_add_nickname_if_in_preference` turn an incoming variant into a nickname
   instead of a conflict. That is the `nicknames` list, NOT a name pin.

Detection compares the pin against the value the seeding record ALREADY
carried. The argument is deliberately narrow and therefore airtight: when the
pin writes the value already there, the seed profile is bit-identical with and
without it, so no later merge, conflict query or override can behave
differently. Nothing downstream needs to be modelled — which matters, because
several paths beyond `_merge_consolidated` can still write a name field.

Like RIG001 it is correspondingly conservative: it reports only what it can
prove. A pin that DOES change the seed and is then neutralised downstream —
an `override` assigning the same field, or a surname derivation arriving at the
same answer — is not reported. Measured on Горюхино, at least one such pin
exists (`petr_ivanovich_ezhevikin.last_name`, filling a blank seed with a
surname later paths supply anyway), so a clean run is not proof that every
remaining pin earns its place. Erring this way is the point: a false positive
would delete a pin that is holding a real disagreement down.

## Why `nicknames` is deliberately NOT reported

`_apply_preference` PRE-POPULATES every declared nickname onto the profile
whether or not a source record carries it — a deliberate config-level decision
recorded in its docstring: declared variants are historical aliases worth
preserving even when absent from the current corpus. Measured on Горюхино,
229 of 488 declared nicknames are never encountered in the records, and they
are live curated history («Прусаков», «Васса», «Стефанида», «Пимон»), not
debris. A rule flagging them would be 229 false positives.

The one nickname shape that IS reportable does not depend on the corpus at
all: a nickname equal to the pin of the SAME field in the same preference. The
pinned value is what the profile renders as that field, so the alias can never
be anything but a duplicate of it — dead by construction, whatever the sources
say.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Distinct from CONFLICT_FAIL_EXIT_CODE (3), REDUNDANT_OVERRIDE_FAIL_EXIT_CODE
#: (4) and REDUNDANT_IGNORE_FAIL_EXIT_CODE (5) so CI can tell them apart.
REDUNDANT_PREFERENCE_FAIL_EXIT_CODE = 6

#: The name fields a `preference` pins. `nicknames` is absent on purpose — see
#: the module docstring.
PREFERENCE_PINNED_FIELDS: tuple[str, ...] = (
    "first_name", "middle_name", "last_name", "birth_last_name",
)


@dataclass(frozen=True)
class RedundantPreference:
    """A `preference` entry that cannot change what the profile renders."""

    canonical: str   # canonical key, e.g. "egor_ilich_vidopljasov"
    field: str       # "first_name", "middle_name", "last_name", ...
    value: str       # the declared value, for the report
    reason: str      # why it cannot matter, for the report


def record_preference_hit(seen: set[tuple[str, str]] | None,
                          canonical: str | None, field: str) -> None:
    """Note that `canonical`'s preference `field` actually did something.

    Central so every consultation is recorded in one place, mirroring
    `matches_ignore` for RIG001. A no-op when either argument is missing, so
    call sites need no branching.
    """
    if seen is not None and canonical is not None:
        seen.add((canonical, field))


#: `(canonical, field, value) -> bool`: would RPF001 call that pin dead? What
#: a paste-ready suggestion asks before printing a pin;
#: `TerraformGenerator.preference_pin_is_dead` is the one to pass.
PinIsDead = Callable[[str, str, str], bool]


def pin_is_dead(canonical: str, field: str, value: Any, *,
                seen: set[tuple[str, str]],
                seed_before: dict[tuple[str, str], Any]) -> bool:
    """RPF001's verdict on one pin: it writes the value the seeding record
    already carried, and did no work the seed comparison cannot see.

    The one predicate, so that neither `suggest_preference_pins` nor
    `conflict_capture.structured_suggestion` prints a pin this check would
    then reject.
    """
    return (bool(value) and (canonical, field) not in seen
            and seed_before.get((canonical, field)) == value)


def collect_redundant_preferences(
        profile_preferences: dict[str, dict[str, Any]],
        seen: set[tuple[str, str]],
        *,
        seeded: set[str] | frozenset[str],
        seed_before: dict[tuple[str, str], Any],
) -> list[RedundantPreference]:
    """Pins that restate what the seed already said, plus shadowed aliases.

    `seed_before` maps `(canonical, field)` to the value the seeding record
    carried BEFORE the pin overwrote it. A pin equal to it wrote nothing, so
    the seed profile — and therefore everything computed from it — is the same
    with the pin deleted.

    `seen` names pins that did work the seed comparison cannot see: today only
    `birth_last_name`, whose declared value also silences the maiden-vs-married
    `last_name` conflict via `matches_preference_birth_name`.

    `seeded` names the canonicals a record actually reached. A preference on a
    canonical that no record seeds never ran at all; that whole cluster is
    stale and belongs to CST001, so reporting its fields here would just be the
    same finding twice under a different code.
    """
    findings: list[RedundantPreference] = []
    for canonical, pref in profile_preferences.items():
        if canonical not in seeded:
            continue
        for field in PREFERENCE_PINNED_FIELDS:
            value = pref.get(field)
            if pin_is_dead(canonical, field, value,
                           seen=seen, seed_before=seed_before):
                findings.append(RedundantPreference(
                    canonical=canonical, field=field, value=str(value),
                    reason="the seeding record already said so",
                ))
        pinned = {pref.get(field) for field in PREFERENCE_PINNED_FIELDS
                  if pref.get(field)}
        for nick in pref.get("nicknames") or []:
            if nick in pinned:
                findings.append(RedundantPreference(
                    canonical=canonical, field="nicknames", value=str(nick),
                    reason="shadowed by the pin on the same field",
                ))
    return findings


def format_redundant_preference_report(
        findings: list[RedundantPreference]) -> str:
    """Render a human-readable warning, or "" when there are none."""
    if not findings:
        return ""
    lines = [
        f"warning: {len(findings)} dead preference entry/entries [RPF001] — "
        "the pin cannot change what the profile renders. A pin acts on the "
        "SEEDING record only, so one that writes the value already there "
        "leaves the profile bit-identical; it is decoration, and it hides the "
        "day the sources start to disagree. Remove the field (and the whole "
        "`preference` if it empties):",
    ]
    lines.extend(
        f"  - {f.canonical}.{f.field} = {f.value}  ({f.reason})"
        for f in findings)
    return "\n".join(lines)


def exit_code_for_redundant_preferences(
        findings: list[RedundantPreference], *,
        fail_on_conflicts: bool) -> int:
    """Exit code contributed by RPF001: non-zero only when failing is
    requested and findings exist; otherwise 0 (warn-only)."""
    return (REDUNDANT_PREFERENCE_FAIL_EXIT_CODE
            if (findings and fail_on_conflicts) else 0)
