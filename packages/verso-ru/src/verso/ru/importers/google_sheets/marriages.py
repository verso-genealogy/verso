"""Marriage-record DSL generation."""
from collections import Counter, defaultdict
from typing import Any
from verso.ru.naming import (get_gender_from_name, modernize_orthography, validate_first_name)
from verso.ru.importers.google_sheets.cells import _get, _get_orig, _int_or_none, _q, _safe_record_num, _split_fio
from verso.ru.importers.google_sheets.columns import MONTH_ENUM
from verso.ru.importers.google_sheets.dsl_emit import _clergy_person_call, _page_sort_key, _person_call, _varname
from verso.ru.importers.google_sheets.formats import MarriageColumns
from verso.ru.dsl.source import format_import
from verso.ru.importers.google_sheets.names import _person_names_set




# ─── Marriage records ─────────────────────────────────────────────────────────

def generate_marriages(rows, archive, fund, inventory, case_, village, church, year,
                       cols=None, status_male="экономический крестьянин",
                       status_female="девица из экономических крестьян",
                       status_bride="девка из экономических крестьян",
                       status_groom=None):
    if cols is None:
        cols = MarriageColumns()
    pages: defaultdict[Any, defaultdict[Any, list[Any]]] = defaultdict(lambda: defaultdict(list))
    page_cases = {}  # page_id -> case from first row on that page
    meta_counter = Counter()

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
        month = _int_or_none(_get(row, cols.W_MONTH)) or 0
        pages[page_id][month].append(row)

    if meta_counter:
        top_meta = meta_counter.most_common(1)[0][0]
        a, f, inv, c = top_meta
    else:
        a, f, inv, c = archive, fund, inventory, case_
    v = _get(rows[0], cols.VILLAGE) or village if rows else village
    ch = _get(rows[0], cols.CHURCH) or church if rows else church
    var_name = _varname(v, "marriages", year)

    lines = []
    # DSL v1: the facade alone, and `verso export-csv` writes the CSV.
    lines.append(format_import("verso.ru.dsl", ["Month", "RecordDefaults", "marriage", "marriage_month",
                                                "marriage_records", "page", "person"]))
    lines.append("")
    lines.append(f"{var_name} = marriage_records(")
    lines.append(f"    {_q(a)}, {_q(f)}, {_q(inv)}, {_q(c)}, {_q(v)}, {_q(ch)},")
    lines.append(f"    {year},")

    skip_set = [status_male, status_female, status_bride]
    if status_groom:
        skip_set.append(status_groom)
    skip_statuses = frozenset(skip_set)
    # Bride-specific: skip status_male and status_bride, but NOT status_female
    # (status_female like "ясачная крестьянка" differs from status_bride like
    # "девка из ясачных крестьян" and should be preserved when explicitly set)
    bride_skip = [status_male, status_bride]
    if status_groom:
        bride_skip.append(status_groom)
    bride_skip_statuses = frozenset(bride_skip)

    for page_id in sorted(pages.keys(), key=_page_sort_key):
        month_map = pages[page_id]
        page_case = page_cases.get(page_id, "")
        if page_case and page_case != c:
            lines.append(f"    *page({_q(page_id)}, case={_q(page_case)},")
        else:
            lines.append(f"    *page({_q(page_id)},")
        for month in sorted(month_map.keys()):
            month_enum = MONTH_ENUM.get(month, "None")
            lines.append(f"          *marriage_month({month_enum},")
            for row in sorted(month_map[month], key=lambda r: (_int_or_none(_get(r, cols.RECORD_NUM)) or 0)):
                lines += _format_marriage_row(row, skip_statuses, default_village=v, cols=cols,
                                              bride_skip_statuses=bride_skip_statuses)
            lines.append("                          ),")
        lines.append("          ),")

    lines.append("    defaults=RecordDefaults(")
    lines.append(f"        residence={_q(v)},")
    lines.append(f"        status_male={_q(status_male)},")
    lines.append(f"        status_female={_q(status_female)},")
    if status_groom:
        lines.append(f"        status_groom={_q(status_groom)},")
    lines.append(f"        status_bride={_q(status_bride)}")
    lines.append("    ),")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)



def _format_marriage_row(row, skip_statuses=frozenset(), default_village="", cols=None,
                         bride_skip_statuses=None):
    if cols is None:
        cols = MarriageColumns()

    def _non_default_residence(col_idx):
        val = _get(row, col_idx)
        if val and val.lower() != default_village.lower():
            return val
        return None

    record_num = _safe_record_num(_get(row, cols.RECORD_NUM))
    w_day = _int_or_none(_get(row, cols.W_DAY))
    comment = _get(row, cols.COMMENT)

    orig_str = _get(row, cols.ORIG_NAMES)
    orig_parts = []
    orig_comments = []  # non-name parts or " - " comments from orig_names
    if orig_str:
        text = orig_str.removeprefix("Имена в МК:").strip()
        for p in text.split(";"):
            p = p.strip()
            if " - " in p:
                name_part, dash_comment = p.split(" - ", 1)
                orig_parts.append(name_part.strip())
                orig_comments.append(dash_comment.strip())
            else:
                orig_parts.append(p)
    if not comment and orig_comments:
        comment = orig_comments[0]

    def orig_name_patr(idx_in_orig, modern_name_col, modern_patr_col, canon_name=None):
        """Return (name, patr, used_orig).  used_orig=True when orig_parts was consumed."""
        if idx_in_orig < len(orig_parts) and orig_parts[idx_in_orig]:
            tokens = orig_parts[idx_in_orig].split(" ", 1)
            name = tokens[0]
            # Reject non-name words (comments in orig_names)
            if not validate_first_name(modernize_orthography(name)):
                # Preserve as comment if no explicit comment exists
                nonlocal comment
                if not comment:
                    comment = orig_parts[idx_in_orig].capitalize()
                return _get(row, modern_name_col), _get(row, modern_patr_col), False
            # Gender-based mismatch check: if canon name has opposite gender, skip orig
            if canon_name:
                canon_gender = get_gender_from_name(modernize_orthography(canon_name))
                orig_gender = get_gender_from_name(modernize_orthography(name))
                if canon_gender and orig_gender and canon_gender != orig_gender:
                    return _get(row, modern_name_col), _get(row, modern_patr_col), False
            patr = tokens[1] if len(tokens) > 1 else ""
            return name, patr, True
        return _get(row, modern_name_col), _get(row, modern_patr_col), False

    has_groom = bool(_get(row, cols.GROOM_NAME) or _get(row, cols.GROOM_NAME_CANON))
    has_bride = bool(_get(row, cols.BRIDE_NAME) or _get(row, cols.BRIDE_NAME_CANON))
    has_w1 = bool(_get(row, cols.W1_NAME) or _get(row, cols.W1_NAME_CANON) or _get(row, cols.W1_FIO))
    has_w2 = bool(_get(row, cols.W2_NAME) or _get(row, cols.W2_NAME_CANON) or _get(row, cols.W2_FIO))
    has_w3 = bool((cols.W3_NAME and _get(row, cols.W3_NAME))
                   or (cols.W3_NAME_CANON and _get(row, cols.W3_NAME_CANON))
                   or _get(row, cols.W3_FIO))
    has_w4 = bool((cols.W4_NAME and _get(row, cols.W4_NAME))
                   or (cols.W4_NAME_CANON and _get(row, cols.W4_NAME_CANON))
                   or _get(row, cols.W4_FIO))

    # orig_parts order: groom, bride, witness1, witness2, ...
    orig_idx = 0
    _persons = []
    parts = [f"marriage({record_num}, {w_day},"]

    if has_groom:
        gn_fb = _get(row, cols.GROOM_NAME) or _get(row, cols.GROOM_NAME_CANON)
        gp_fb = _get(row, cols.GROOM_PATR) or _get(row, cols.GROOM_PATR_CANON)
        gn, gp, used = orig_name_patr(orig_idx, cols.GROOM_NAME, cols.GROOM_PATR, canon_name=gn_fb)
        gn, gp = gn or gn_fb, gp or gp_fb
        if used:
            orig_idx += 1
        if cols.GROOM_ORIG_NAME is not None:
            groom_orig_n = _get_orig(row, cols.GROOM_ORIG_NAME)
            groom_orig_p = _get_orig(row, cols.GROOM_ORIG_PATR) if cols.GROOM_ORIG_PATR else ""
            if groom_orig_n:
                gn, gp = groom_orig_n, groom_orig_p
        last_name = _get(row, cols.GROOM_LAST_NAME)
        status = _get(row, cols.GROOM_STATUS)
        residence = _non_default_residence(cols.GROOM_RESIDENCE)
        _persons.append((gn, gp))
        groom_call = _person_call(gn, gp or None, last_name or None, residence=residence,
                                  status=status or None, skip_statuses=skip_statuses)
        groom_num = _int_or_none(_get(row, cols.GROOM_MARRIAGE_NUM))
        groom_age = (_int_or_none(_get(row, cols.GROOM_AGE))
                     if cols.GROOM_AGE is not None else None)
        groom_extras = []
        if groom_age is not None:
            groom_extras.append(f"groom_age={groom_age}")
        if groom_num:
            groom_extras.append(f"groom_marriage_num={groom_num}")
        if groom_extras:
            parts.append(f"groom={groom_call}, " + ", ".join(groom_extras) + ",")
        else:
            parts.append(f"groom={groom_call},")

    if has_bride:
        bn_fb = _get(row, cols.BRIDE_NAME) or _get(row, cols.BRIDE_NAME_CANON)
        bp_fb = _get(row, cols.BRIDE_PATR) or _get(row, cols.BRIDE_PATR_CANON)
        bn, bp, used = orig_name_patr(orig_idx, cols.BRIDE_NAME, cols.BRIDE_PATR, canon_name=bn_fb)
        bn, bp = bn or bn_fb, bp or bp_fb
        if used:
            orig_idx += 1
        if cols.BRIDE_ORIG_NAME is not None:
            bride_orig_n = _get_orig(row, cols.BRIDE_ORIG_NAME)
            bride_orig_p = _get_orig(row, cols.BRIDE_ORIG_PATR) if cols.BRIDE_ORIG_PATR else ""
            if bride_orig_n:
                bn, bp = bride_orig_n, bride_orig_p
        last_name = _get(row, cols.BRIDE_LAST_NAME)
        status = _get(row, cols.BRIDE_STATUS)
        residence = _non_default_residence(cols.BRIDE_RESIDENCE)
        _persons.append((bn, bp))
        bride_call = _person_call(bn, bp or None, last_name or None, residence=residence,
                                  status=status or None,
                                  skip_statuses=bride_skip_statuses if bride_skip_statuses is not None else skip_statuses)
        bride_num = _int_or_none(_get(row, cols.BRIDE_MARRIAGE_NUM))
        bride_age = (_int_or_none(_get(row, cols.BRIDE_AGE))
                     if cols.BRIDE_AGE is not None else None)
        bride_extras = []
        if bride_age is not None:
            bride_extras.append(f"bride_age={bride_age}")
        if bride_num:
            bride_extras.append(f"bride_marriage_num={bride_num}")
        if bride_extras:
            parts.append(f"bride={bride_call}, " + ", ".join(bride_extras) + ",")
        else:
            parts.append(f"bride={bride_call},")

    if has_w1:
        if cols.W1_NAME is not None:
            wn_fb = _get(row, cols.W1_NAME) or _get(row, cols.W1_NAME_CANON) or _get(row, cols.W1_FIO)
            wp_fb = _get(row, cols.W1_PATR) or _get(row, cols.W1_PATR_CANON)
            w1n, w1p, used = orig_name_patr(orig_idx, cols.W1_NAME, cols.W1_PATR)
            w1n, w1p = w1n or wn_fb, w1p or wp_fb
        else:
            w1n, w1p = _split_fio(_get(row, cols.W1_FIO))
            on, op, used = orig_name_patr(orig_idx, None, None, canon_name=w1n)
            w1n, w1p = on or w1n, op or w1p
        if used:
            orig_idx += 1
        if cols.W1_ORIG_NAME is not None:
            w1_orig_n = _get_orig(row, cols.W1_ORIG_NAME)
            w1_orig_p = _get_orig(row, cols.W1_ORIG_PATR) if cols.W1_ORIG_PATR else ""
            if w1_orig_n:
                w1n, w1p = w1_orig_n, w1_orig_p or w1p
        last_name = _get(row, cols.W1_LAST_NAME)
        status = _get(row, cols.W1_STATUS)
        residence = _non_default_residence(cols.W1_RESIDENCE)
        _persons.append((w1n, w1p))
        w1_call = _person_call(w1n, w1p or None, last_name or None, residence=residence,
                               status=status or None, skip_statuses=skip_statuses)
        parts.append(f"witness1={w1_call},")

    if has_w2:
        if cols.W2_NAME is not None:
            wn_fb = _get(row, cols.W2_NAME) or _get(row, cols.W2_NAME_CANON) or _get(row, cols.W2_FIO)
            wp_fb = _get(row, cols.W2_PATR) or _get(row, cols.W2_PATR_CANON)
            w2n, w2p, used = orig_name_patr(orig_idx, cols.W2_NAME, cols.W2_PATR)
            w2n, w2p = w2n or wn_fb, w2p or wp_fb
        else:
            w2n, w2p = _split_fio(_get(row, cols.W2_FIO))
            on, op, used = orig_name_patr(orig_idx, None, None, canon_name=w2n)
            w2n, w2p = on or w2n, op or w2p
        if used:
            orig_idx += 1
        if cols.W2_ORIG_NAME is not None:
            w2_orig_n = _get_orig(row, cols.W2_ORIG_NAME)
            w2_orig_p = _get_orig(row, cols.W2_ORIG_PATR) if cols.W2_ORIG_PATR else ""
            if w2_orig_n:
                w2n, w2p = w2_orig_n, w2_orig_p or w2p
        last_name = _get(row, cols.W2_LAST_NAME)
        status = _get(row, cols.W2_STATUS)
        residence = _non_default_residence(cols.W2_RESIDENCE)
        _persons.append((w2n, w2p))
        w2_call = _person_call(w2n, w2p or None, last_name or None, residence=residence,
                               status=status or None, skip_statuses=skip_statuses)
        parts.append(f"witness2={w2_call},")

    if has_w3:
        if cols.W3_NAME is not None:
            wn_fb = _get(row, cols.W3_NAME) or (_get(row, cols.W3_NAME_CANON) if cols.W3_NAME_CANON else "") or _get(row, cols.W3_FIO)
            wp_fb = (_get(row, cols.W3_PATR) if cols.W3_PATR else "") or (_get(row, cols.W3_PATR_CANON) if cols.W3_PATR_CANON else "")
            w3n, w3p, used = orig_name_patr(orig_idx, cols.W3_NAME, cols.W3_PATR)
            w3n, w3p = w3n or wn_fb, w3p or wp_fb
        else:
            w3n, w3p = _split_fio(_get(row, cols.W3_FIO))
            on, op, used = orig_name_patr(orig_idx, None, None, canon_name=w3n)
            w3n, w3p = on or w3n, op or w3p
        if used:
            orig_idx += 1
        if cols.W3_ORIG_NAME is not None:
            w3_orig_n = _get_orig(row, cols.W3_ORIG_NAME)
            w3_orig_p = _get_orig(row, cols.W3_ORIG_PATR) if cols.W3_ORIG_PATR else ""
            if w3_orig_n:
                w3n, w3p = w3_orig_n, w3_orig_p or w3p
        last_name = _get(row, cols.W3_LAST_NAME) if cols.W3_LAST_NAME is not None else ""
        status = _get(row, cols.W3_STATUS)
        residence = _non_default_residence(cols.W3_RESIDENCE) if cols.W3_RESIDENCE else ""
        _persons.append((w3n, w3p))
        w3_call = _person_call(w3n, w3p or None, last_name or None, residence=residence,
                               status=status or None, skip_statuses=skip_statuses)
        parts.append(f"witness3={w3_call},")

    if has_w4:
        if cols.W4_NAME is not None:
            wn_fb = _get(row, cols.W4_NAME) or (_get(row, cols.W4_NAME_CANON) if cols.W4_NAME_CANON else "") or _get(row, cols.W4_FIO)
            wp_fb = (_get(row, cols.W4_PATR) if cols.W4_PATR else "") or (_get(row, cols.W4_PATR_CANON) if cols.W4_PATR_CANON else "")
            w4n, w4p, used = orig_name_patr(orig_idx, cols.W4_NAME, cols.W4_PATR)
            w4n, w4p = w4n or wn_fb, w4p or wp_fb
        else:
            w4n, w4p = _split_fio(_get(row, cols.W4_FIO))
            on, op, used = orig_name_patr(orig_idx, None, None, canon_name=w4n)
            w4n, w4p = on or w4n, op or w4p
        if used:
            orig_idx += 1
        if cols.W4_ORIG_NAME is not None:
            w4_orig_n = _get_orig(row, cols.W4_ORIG_NAME)
            w4_orig_p = _get_orig(row, cols.W4_ORIG_PATR) if cols.W4_ORIG_PATR else ""
            if w4_orig_n:
                w4n, w4p = w4_orig_n, w4_orig_p or w4p
        last_name = _get(row, cols.W4_LAST_NAME) if cols.W4_LAST_NAME is not None else ""
        status = _get(row, cols.W4_STATUS)
        residence = _non_default_residence(cols.W4_RESIDENCE) if cols.W4_RESIDENCE else ""
        _persons.append((w4n, w4p))
        w4_call = _person_call(w4n, w4p or None, last_name or None, residence=residence,
                               status=status or None, skip_statuses=skip_statuses)
        parts.append(f"witness4={w4_call},")

    # Clergy
    for col_fio, param_name in [(cols.PRIEST_FIO, "priest"), (cols.DEACON_FIO, "deacon"),
                                (cols.DYACHOK_FIO, "dyachok")]:
        fio = _get(row, col_fio)
        if fio:
            call = _clergy_person_call(fio)
            if call:
                parts.append(f"{param_name}={call},")

    if comment and comment.strip() not in _person_names_set(*_persons):
        parts.append(f"comment={_q(comment)},")

    last = parts[-1].rstrip(",") + ")"
    parts[-1] = last + ","

    result = []
    result.append("                          " + parts[0])
    for p in parts[1:]:
        result.append("                                   " + p.lstrip())
    return result
