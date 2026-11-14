"""Census migration field resolvers (departure/arrival/age)."""
from typing import TYPE_CHECKING

from verso.ru.ages import split_age

if TYPE_CHECKING:
    from verso.ru.dsl.records.census import CensusMember




def _resolve_departure_year(m):
    """Prefer CensusMember.departure_year; fall back to legacy
    `убыл:\\s*умер\\s+YYYY` parse on `comment`."""
    if getattr(m, "departure_year", None) is not None:
        return m.departure_year
    import re as _re
    if m.comment:
        dm = _re.search(r"убыл:\s*умер\s+(\d{4})", m.comment)
        if dm:
            return int(dm.group(1))
    return None



def _resolve_departure_reason(m):
    """Prefer CensusMember.departure_reason; fall back to the reason
    text embedded in a `убыл:` marker on `comment` (trailing year is
    stripped by `_split_reason_trailing_year` at the call site)."""
    if getattr(m, "departure_reason", None) is not None:
        return m.departure_reason
    import re as _re
    if m.comment:
        mm = _re.search(r"убыл:\s*([^;]+?)(?:\s*;|$)", m.comment)
        if mm:
            # The legacy comment-death path only triggered on 'умер':
            # expose the same narrowed reason here so callers that gate
            # on it (death-event emission) get the same behavior.
            seg = mm.group(1).strip()
            umer_m = _re.search(r"^умер\b", seg)
            if umer_m:
                return "умер"
    return None



def _resolve_destination(m):
    """Prefer CensusMember.destination; fall back to the `в X` tail of
    a `убыл:` marker in `comment`."""
    if getattr(m, "destination", None):
        return m.destination
    import re as _re
    if m.comment:
        dest_m = _re.search(
            r"убыл:[^;]*?\s+в\s+([А-ЯЁ][А-ЯЁа-яё\- ]+?)(?:\s*;|$)",
            m.comment,
        )
        if dest_m:
            return dest_m.group(1).strip(" .,;")
    return None



def _resolve_arrival_year(m):
    """Prefer CensusMember.arrival_year; no comment fallback — the
    year is extracted from the raw `прибыл:` segment by
    `_split_reason_trailing_year` at the call site."""
    if getattr(m, "arrival_year", None) is not None:
        return m.arrival_year
    return None



def _resolve_arrival_reason(m):
    """Prefer CensusMember.arrival_reason; no comment fallback — the
    reason text is extracted from the raw `прибыл:` segment at the
    call site."""
    if getattr(m, "arrival_reason", None) is not None:
        return m.arrival_reason
    return None






def resolve_previous_age_raw(m):
    """The previous-revision age AS RECORDED — `int`, or the source's own
    string («6 лет 6 мес»). None when absent.

    Separate from `_resolve_previous_age`, which collapses the same value to a
    float number of years for birth-year arithmetic: that is lossy on purpose
    ("6 лет 6 мес" → 6.5) and so cannot be rendered back to a reader. Display
    paths need the raw value to hand to `format_age`.

    The comment fallback uses the same loose pattern as the document table
    (`прошлая РС: <anything>`), not the digits-only one the float resolver
    settles for, so the about and the table quote the same text.
    """
    v = getattr(m, "previous_age", None)
    if v is not None:
        return v
    if m.comment and "прошлая РС:" in m.comment:
        import re as _re
        mm = _re.search(r"прошлая РС:\s*([^;]+?)(?:\s*;|$)", m.comment)
        if mm:
            return mm.group(1).strip() or None
    return None


def _resolve_previous_age(m) -> float | None:
    """Prefer the typed `previous_age` kwarg; fall back to the
    `прошлая РС: N лет` comment marker.

    Returns the age in years as a float so sub-year strings (e.g.
    `"5 нед"`, `"3 мес"`) and fractional values (`0.5`) round-trip
    through `_age_to_years`. Returns None when the value is missing
    or unparseable. Consumers that need an integer year subtraction
    should `int()` the result themselves."""
    v = getattr(m, "previous_age", None)
    if v is not None:
        if isinstance(v, (int, float)):
            return float(v)
        return _age_to_years(v)
    if m.comment:
        import re as _re
        mm = _re.search(r"прошлая РС:\s*(\d+)\s*лет", m.comment)
        if mm:
            return float(mm.group(1))
    return None



def _age_to_components(age) -> tuple[int, int, int, int] | None:
    """Parse an age value (int/float/str) into (years, months, weeks, days)
    integer components. Returns None when the value is missing or unparseable.

    Wraps `_split_age` (the single age tokenizer used by the CSV exporters),
    which dumps unparseable strings verbatim into the years slot — so every
    slot must be digits before it is trusted."""
    if age is None or isinstance(age, bool):
        return None
    if isinstance(age, (int, float)):
        # Split a fractional year into whole years + months so "1.5" → 1y 6mo
        # (the death path relied on this for sub-year birth-month placement).
        whole = int(age)
        return (whole, round((age - whole) * 12), 0, 0)
    if not isinstance(age, str):
        return None
    # A bare numeric string (`"1.5"`, `"58.5"`, `"33"`) — the Маниловка/
    # Горюхино decimal style — parses like its number, not through the
    # unit-word tokenizer (which would drop it as unparseable).
    try:
        return _age_to_components(float(age.strip().replace(",", ".")))
    except ValueError:
        pass
    parts = []
    for slot in split_age(age):
        parts.append(int(slot) if slot and slot.isdigit() else None)
    if all(p is None for p in parts):
        return None
    y, m, w, d = (p or 0 for p in parts)
    return (y, m, w, d)


def _age_to_years(age) -> float | None:
    """Best-effort conversion of an age value to a float number of years for
    birth-year calculation. Weeks/days aware. Returns None when the value is
    None or unparseable."""
    parts = _age_to_components(age)
    if parts is None:
        return None
    y, m, w, d = parts
    return y + m / 12.0 + w * 7 / 365.25 + d / 365.25


def _birth_date_from_age(ref_year, ref_month, ref_day, age,
                         *, bare_year_keeps_ref_month=False):
    """Estimate a (circa) birth date by subtracting an age (Y/M/W/D) from a
    reference date (the census record date, or the death date). Returns a
    `(year, month, day)` tuple — any component may be None — or None when the
    age is unparseable.

    Precision rules (the reference day/month is not the birthday, so spurious
    components are dropped):
      - Age carries sub-year info (months/weeks/days) AND `ref_month` is known:
        subtract a calendar-correct `relativedelta`.
          * age has a years component → year + month (drop day).
          * short duration (no years) AND `ref_day` known → year + month + day.
          * otherwise → year + month.
      - Bare-year age (no sub-year info), or no `ref_month`: year only — a bare
        "55" tells us the birth year, not the month. EXCEPT: death records keep
        the reference (death) month for bare-year ages as legacy parity — pass
        `bare_year_keeps_ref_month=True` to opt in. (Census passes False, so
        bare-year census members stay year-only as before.)
    """
    parts = _age_to_components(age)
    if parts is None:
        return None
    years, months, weeks, days = parts
    has_subyear = bool(months or weeks or days)
    if ref_month is None or not has_subyear:
        year_only = int(ref_year) - int(_age_to_years(age) or 0)
        month = int(ref_month) if (bare_year_keeps_ref_month and ref_month is not None) else None
        return (year_only, month, None)
    from datetime import date as _date
    from dateutil.relativedelta import relativedelta as _rd
    try:
        base = _date(int(ref_year), int(ref_month), int(ref_day) if ref_day else 15)
        est = base - _rd(years=years, months=months, weeks=weeks, days=days)
    except (ValueError, TypeError):
        return (int(ref_year) - int(_age_to_years(age) or 0), None, None)
    # Keep the day ONLY for very short intervals (< ~1 month): a baby a few
    # days/weeks old has a meaningful day, but for any longer span the reference
    # day is not the birthday, so emit year+month only.
    under_one_month = years == 0 and months == 0 and (weeks * 7 + days) < 30
    keep_day = under_one_month and bool(ref_day)
    return (est.year, est.month, est.day if keep_day else None)






def resolve_display_role(m, household=None) -> tuple[str, int | None]:
    """The `(role_word, effective_ref)` pair as the document table displays it.

    `role_word` is the household role in the book's own wording; `effective_ref`
    is the member number the role is measured against (None when the role stands
    alone). Rendered by `_render_census_member_lines` as `N. {role_word} ({ref}):
    …`, and by `_build_census_member_about` as the profile's «Роль в семье» line
    — hence living here rather than inside either caller, so the document body
    and the about text can never disagree about who is whose wife.

    Resolution, in order:
      1. HEAD renders as «глава»; any other typed role renders as its enum value.
      2. A `comment="роль в оригинале: …"` phrase overrides the word — the DSL
         records the book's exact qualifier there («дядя родной» vs the enum's
         bare «дядя»), and for `role=None` members it is the only role text
         there is. The typed enum still drives gender, unions and the rest.
      3. `ref_member` wins when set. Otherwise a BROTHER/SISTER/COUSIN carrying
         only a `parent_member` refers to the ONE sibling sharing that parent
         (with several siblings the relationship is ambiguous, so it falls
         through to the head, mirroring the legacy CSV).
      4. Any remaining non-HEAD member with a role defaults to member 1 — the
         legacy `relationship_number_orig` column defaulted to the head.
      5. HEAD never carries a ref, even when `ref_member` points at a hidden
         ancestor (that link exists for the sub-family union only).
      6. An empty role word suppresses the ref too: the unrelated-person case
         (lodger / unaffiliated adult) where the source's primary relationship
         columns were both deliberately left blank.
    """
    import re as _re

    from verso.ru.dsl.records.census import CensusRole
    role_word = {
        CensusRole.HEAD: "глава",
    }.get(m.role, m.role.value if m.role else "")
    override_role_from_comment = None
    if m.comment:
        role_m = _re.search(
            r"роль в оригинале:\s*([^;]+?)(?:\s*;|$)", m.comment,
        )
        if role_m:
            override_role_from_comment = role_m.group(1).strip()
            role_word = override_role_from_comment
    effective_ref = m.ref_member
    if (effective_ref is None
            and m.role in (CensusRole.BROTHER, CensusRole.SISTER,
                           CensusRole.COUSIN)
            and getattr(m, "parent_member", None) is not None
            and household is not None):
        siblings = [
            sib for sib in household.members
            if sib.number != m.number
            and getattr(sib, "parent_member", None) == m.parent_member
        ]
        if len(siblings) == 1:
            effective_ref = siblings[0].number
    if effective_ref is None and m.role != CensusRole.HEAD and (
        m.role is not None or override_role_from_comment
    ):
        effective_ref = 1
    if m.role == CensusRole.HEAD:
        effective_ref = None
    if not role_word:
        effective_ref = None
    return role_word, effective_ref


def _resolve_parent_ref(c, members_by_num: dict[int, CensusMember]) -> int | None:
    """Determine the upward parent link for a census member, used for
    sub-family union emission.

    Precedence:
      1. Explicit `parent_member=` (the new typed kwarg) wins.
      2. For child roles (SON/DAUGHTER/STEPSON/STEPDAUGHTER), the
         legacy `ref_member=` is the parent.
      3. Legacy compat: a non-child role with `ref_member=` pointing at
         a `#hidden` ancestor (string `record_number`) is treated as an
         upward link. Newly-authored DSLs should use `parent_member=`
         instead.
      4. Sibling roles (BROTHER/SISTER/NIECE/NEPHEW/COUSIN) with
         `ref_member=` pointing at a sibling that has a `parent_member`
         inherit that parent. Semantically: if Сергей's parent is X
         and Федор is BROTHER ref_member=Сергей, Федор's parent is
         also X. Mirrors legacy's patronymic-based grouping that linked
         e.g. Федор Исаиев (BROTHER of Сергей Исаев, ref=5) to the
         hidden Исай via Сергей's parent_member.

    Returns the parent member number or None if no upward link exists.
    """
    from verso.ru.dsl.records.census import CensusRole, _FOSTER_ROLES
    # A foster child (приёмыш; FOSTER_SON/FOSTER_DAUGHTER) is recorded in the
    # household but is not a biological child of any member — emit no biological
    # parent-union, even if an explicit ref_member/parent_member points at the
    # foster parent.
    if c.role in _FOSTER_ROLES:
        return None
    child_roles = {
        CensusRole.SON, CensusRole.DAUGHTER,
        CensusRole.STEPSON, CensusRole.STEPDAUGHTER,
    }
    sibling_roles = {
        CensusRole.BROTHER, CensusRole.SISTER,
        CensusRole.NIECE, CensusRole.NEPHEW, CensusRole.COUSIN,
    }
    pm = getattr(c, "parent_member", None)
    if pm is not None:
        return pm
    rm = c.ref_member
    if rm is None:
        return None
    if c.role in child_roles:
        return rm
    parent_m = members_by_num.get(rm)
    if parent_m is not None and parent_m.is_hidden():
        return rm
    if c.role in sibling_roles and parent_m is not None:
        sibling_pm = getattr(parent_m, "parent_member", None)
        if sibling_pm is not None:
            return sibling_pm
    return None
