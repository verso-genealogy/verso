"""Birth-record DSL generation."""
from collections import Counter, defaultdict
from typing import Any
from verso.ru.naming import (get_gender_from_name, modernize_orthography)
from verso.ru.importers.google_sheets.cells import _get, _get_orig, _int_or_none, _q, _safe_record_num, _split_fio
from verso.ru.importers.google_sheets.columns import GENDER_MAP, MONTH_ENUM
from verso.ru.importers.google_sheets.dsl_emit import _clergy_person_call, _page_sort_key, _person_call, _varname
from verso.ru.importers.google_sheets.formats import BirthColumns
from verso.ru.dsl.source import format_import
from verso.ru.importers.google_sheets.names import _parse_orig_names, _person_names_set




# ─── Birth records ────────────────────────────────────────────────────────────


def generate_births(rows, archive, fund, inventory, case_, village, church, year,
                     cols=None, status_male="экономический крестьянин",
                     status_female="экономическая крестьянка"):
    """Generate Python source for a birth_records(...) call."""
    if cols is None:
        cols = BirthColumns()
    # Group rows: page -> month -> list of rows
    pages: defaultdict[Any, defaultdict[Any, list[Any]]] = defaultdict(lambda: defaultdict(list))
    page_cases = {}  # page_id -> case from first row on that page
    meta_counter = Counter()  # (archive, fund, inv, case) -> count

    for row in rows:
        row_meta = (
            _get(row, cols.ARCHIVE) or archive,
            _get(row, cols.FUND) or fund,
            _get(row, cols.INVENTORY) or inventory,
            _get(row, cols.CASE) or case_,
        )
        meta_counter[row_meta] += 1
        page_id = _get(row, cols.PAGE) or "?"
        if page_id not in page_cases:
            page_cases[page_id] = _get(row, cols.CASE) or ""
        month = _int_or_none(_get(row, cols.B_MONTH)) or _int_or_none(_get(row, cols.K_MONTH)) or 0
        pages[page_id][month].append(row)

    # Use the most common archive reference for the header
    if meta_counter:
        top_meta = meta_counter.most_common(1)[0][0]
        a, f, inv, c = top_meta
    else:
        a, f, inv, c = archive, fund, inventory, case_
    v = _get(rows[0], cols.VILLAGE) or village if rows else village
    ch = _get(rows[0], cols.CHURCH) or church if rows else church
    var_name = _varname(v, "births", year)

    lines = []
    uses_person = any(
        _get(row, cols.CHILD_NAME) or _get(row, cols.CHILD_NAME_CANON)
        or _get(row, cols.FATHER_NAME) or _get(row, cols.FATHER_NAME_CANON)
        or _get(row, cols.MOTHER_NAME) or _get(row, cols.MOTHER_NAME_CANON)
        or _get(row, cols.GP1_NAME) or _get(row, cols.GP1_FIO)
        or _get(row, cols.GP2_NAME) or _get(row, cols.GP2_FIO)
        for row in rows
    )
    # DSL v1: the facade alone, and `verso export-csv` writes the CSV.
    names = ["Gender", "Month", "RecordDefaults", "birth", "birth_month", "birth_records", "page"]
    lines.append(format_import("verso.ru.dsl", [*names, "person"] if uses_person else names))
    lines.append("")
    lines.append(f"{var_name} = birth_records(")
    lines.append(f"    {_q(a)}, {_q(f)}, {_q(inv)}, {_q(c)}, {_q(v)}, {_q(ch)},")
    lines.append(f"    {year},")

    skip_statuses = frozenset([status_male, status_female])

    for page_id in sorted(pages.keys(), key=_page_sort_key):
        month_map = pages[page_id]
        page_case = page_cases.get(page_id, "")
        if page_case and page_case != c:
            lines.append(f"    *page({_q(page_id)}, case={_q(page_case)},")
        else:
            lines.append(f"    *page({_q(page_id)},")
        for month in sorted(month_map.keys()):
            month_enum = MONTH_ENUM.get(month, "None")
            lines.append(f"          *birth_month({month_enum},")
            for row in sorted(month_map[month], key=lambda r: (_int_or_none(_get(r, cols.RECORD_NUM)) or 0)):
                lines += _format_birth_row(row, skip_statuses, default_village=v, cols=cols)
            lines.append("                       ),")
        lines.append("          ),")

    lines.append("    defaults=RecordDefaults(")
    lines.append(f"        residence={_q(v)},")
    lines.append(f"        status_male={_q(status_male)},")
    lines.append(f"        status_female={_q(status_female)}")
    lines.append("    ),")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)



def _format_birth_row(row, skip_statuses=frozenset(), default_village="", cols=None):
    if cols is None:
        cols = BirthColumns()
    record_num = _safe_record_num(_get(row, cols.RECORD_NUM))
    gender_str = _get(row, cols.GENDER)
    gender = GENDER_MAP.get(gender_str, f"Gender.???_{gender_str}")
    b_day = _int_or_none(_get(row, cols.B_DAY))
    k_day = _int_or_none(_get(row, cols.K_DAY))
    comment = _get(row, cols.COMMENT)
    orig_str = _get(row, cols.ORIG_NAMES)

    has_child = bool(_get(row, cols.CHILD_NAME) or _get(row, cols.CHILD_NAME_CANON))
    has_father = bool(_get(row, cols.FATHER_NAME) or _get(row, cols.FATHER_NAME_CANON))
    has_mother = bool(_get(row, cols.MOTHER_NAME) or _get(row, cols.MOTHER_NAME_CANON))
    has_gp1 = bool(_get(row, cols.GP1_NAME) or _get(row, cols.GP1_FIO))
    has_gp2 = bool(_get(row, cols.GP2_NAME) or _get(row, cols.GP2_FIO))
    # Build canonical name hints for misalignment detection
    canon_hints = {}
    if has_child:
        canon_hints["child"] = _get(row, cols.CHILD_NAME) or _get(row, cols.CHILD_NAME_CANON)
    if has_father:
        canon_hints["father"] = _get(row, cols.FATHER_NAME) or _get(row, cols.FATHER_NAME_CANON)
    if has_mother:
        canon_hints["mother"] = _get(row, cols.MOTHER_NAME) or _get(row, cols.MOTHER_NAME_CANON)
    if has_gp1:
        gp1_canon = _get(row, cols.GP1_NAME) if cols.GP1_NAME else _split_fio(_get(row, cols.GP1_FIO))[0]
        if gp1_canon:
            canon_hints["gp1"] = gp1_canon
    if has_gp2:
        gp2_canon = _get(row, cols.GP2_NAME) if cols.GP2_NAME else _split_fio(_get(row, cols.GP2_FIO))[0]
        if gp2_canon:
            canon_hints["gp2"] = gp2_canon
    orig = _parse_orig_names(orig_str, has_child, has_father, has_mother, has_gp1, has_gp2,
                             canon_names=canon_hints)
    # If positional mapping failed (part count mismatch), preserve orig_str as a comment
    if orig_str and not orig:
        comment = (comment + "; " + orig_str) if comment else orig_str
    # Preserve non-name orig parts (rejected by role_matches) as comment
    orig_rejected = orig.pop("_comments", [])
    if not comment and orig_rejected:
        comment = orig_rejected[0]

    # Override with dedicated orig columns if available (pre-reform chars stripped)
    # Preserve existing surname from _parse_orig_names when orig columns don't have it
    def _override_orig(role, orig_name_col, orig_patr_col):
        orig_n = _get_orig(row, orig_name_col)
        if not orig_n:
            return
        orig_p = _get_orig(row, orig_patr_col) if orig_patr_col else ""
        # Preserve surname from comment-based parsing
        existing = orig.get(role, ("", "", ""))
        surname = existing[2] if len(existing) > 2 else ""
        orig[role] = (orig_n, orig_p, surname)

    if cols.CHILD_ORIG_NAME is not None:
        child_orig = _get_orig(row, cols.CHILD_ORIG_NAME)
        if child_orig:
            orig["child"] = (child_orig, "", "")

    _override_orig("father", cols.FATHER_ORIG_NAME, cols.FATHER_ORIG_PATR)
    _override_orig("mother", cols.MOTHER_ORIG_NAME, cols.MOTHER_ORIG_PATR)
    _override_orig("gp1", cols.GP1_ORIG_NAME, cols.GP1_ORIG_PATR)
    _override_orig("gp2", cols.GP2_ORIG_NAME, cols.GP2_ORIG_PATR)

    def _non_default_residence(col_idx):
        val = _get(row, col_idx)
        if val and val.lower() != default_village.lower():
            return val
        return None

    # Auto-swap record gender if it conflicts with the child's name gender
    if has_child:
        child_name_fallback = _get(row, cols.CHILD_NAME) or _get(row, cols.CHILD_NAME_CANON)
        child_name_for_gender = orig.get("child", (child_name_fallback, "", ""))[0] or child_name_fallback
        child_gender = get_gender_from_name(modernize_orthography(child_name_for_gender)) if child_name_for_gender else None
        if child_gender:
            expected_gender = GENDER_MAP.get(child_gender.value)
            if expected_gender and gender != expected_gender:
                gender = expected_gender

    _persons = []
    parts = [f"birth({record_num}, {gender}, {b_day}, {k_day},"]
    if has_child:
        child_name_fallback = _get(row, cols.CHILD_NAME) or _get(row, cols.CHILD_NAME_CANON)
        child_name = orig.get("child", (child_name_fallback, "", ""))[0]
        _persons.append((child_name, ""))
        parts.append(f"                             child=person({_q(child_name)}),")
    if has_father:
        fn_fb = _get(row, cols.FATHER_NAME) or _get(row, cols.FATHER_NAME_CANON)
        fp_fb = _get(row, cols.FATHER_PATR) or _get(row, cols.FATHER_PATR_CANON)
        fn, fp, f_surname = orig.get("father", (fn_fb, fp_fb, ""))
        fp = fp or fp_fb
        last_name = _get(row, cols.FATHER_LAST_NAME) or f_surname
        status = _get(row, cols.FATHER_STATUS)
        residence = _non_default_residence(cols.FATHER_RESIDENCE)
        _persons.append((fn, fp))
        father_call = _person_call(fn, fp or None, last_name or None, residence, status or None,
                                   skip_statuses=skip_statuses)
        parts.append(f"                             father={father_call},")
    if has_mother:
        mn_fb = _get(row, cols.MOTHER_NAME) or _get(row, cols.MOTHER_NAME_CANON)
        mp_fb = _get(row, cols.MOTHER_PATR) or _get(row, cols.MOTHER_PATR_CANON)
        mn, mp, m_surname = orig.get("mother", (mn_fb, mp_fb, ""))
        mp = mp or mp_fb
        last_name = _get(row, cols.MOTHER_LAST_NAME) or m_surname
        status = _get(row, cols.MOTHER_STATUS)
        _persons.append((mn, mp))
        mother_call = _person_call(mn, mp or None, last_name or None, None, status or None,
                                   skip_statuses=skip_statuses)
        parts.append(f"                             mother={mother_call},")
    if has_gp1:
        if cols.GP1_NAME is not None:
            gn_fb = _get(row, cols.GP1_NAME) or _get(row, cols.GP1_FIO)
            gn, gp, g_surname = orig.get("gp1", (gn_fb, _get(row, cols.GP1_PATR), ""))
            gp = gp or _get(row, cols.GP1_PATR)
        else:
            gn_fb, gp_fb = _split_fio(_get(row, cols.GP1_FIO))
            gn, gp, g_surname = orig.get("gp1", (gn_fb, gp_fb, ""))
        g_surname = g_surname or _get(row, cols.GP1_LAST_NAME)
        status = _get(row, cols.GP1_STATUS)
        residence = _non_default_residence(cols.GP1_RESIDENCE)
        _persons.append((gn, gp))
        gp1_call = _person_call(gn, gp or None, g_surname or None, residence, status or None,
                                skip_statuses=skip_statuses)
        parts.append(f"                             god_parent1={gp1_call},")
    if has_gp2:
        if cols.GP2_NAME is not None:
            gn_fb = _get(row, cols.GP2_NAME) or _get(row, cols.GP2_FIO)
            gn, gp, g_surname = orig.get("gp2", (gn_fb, _get(row, cols.GP2_PATR), ""))
            gp = gp or _get(row, cols.GP2_PATR)
        else:
            gn_fb, gp_fb = _split_fio(_get(row, cols.GP2_FIO))
            gn, gp, g_surname = orig.get("gp2", (gn_fb, gp_fb, ""))
        g_surname = g_surname or _get(row, cols.GP2_LAST_NAME)
        status = _get(row, cols.GP2_STATUS)
        residence = _non_default_residence(cols.GP2_RESIDENCE)
        _persons.append((gn, gp))
        gp2_call = _person_call(gn, gp or None, g_surname or None, residence, status or None,
                                skip_statuses=skip_statuses)
        parts.append(f"                             god_parent2={gp2_call},")
    # Clergy
    for col_fio, param_name in [(cols.PRIEST_FIO, "priest"), (cols.DEACON_FIO, "deacon"),
                                (cols.DYACHOK_FIO, "dyachok")]:
        fio = _get(row, col_fio)
        if fio:
            call = _clergy_person_call(fio)
            if call:
                parts.append(f"                             {param_name}={call},")
    if comment and comment.strip() not in _person_names_set(*_persons):
        parts.append(f"                             comment={_q(comment)},")

    # Close the birth(...) call — move the last trailing comma to closing paren
    last = parts[-1].rstrip(",") + ")"
    parts[-1] = last + ","
    # Indent and wrap inside birth_month block
    result = []
    first_line = "                       " + parts[0]
    result.append(first_line)
    for p in parts[1:]:
        result.append("                             " + p.lstrip())
    return result
