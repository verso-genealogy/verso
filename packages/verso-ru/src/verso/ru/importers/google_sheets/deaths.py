"""Death-record DSL generation."""
import re
from collections import Counter, defaultdict
from typing import Any
from verso.ru.naming import (get_gender_from_name, modernize_orthography, canonicalize_patronymic, derive_patronymic, validate_first_name)
from verso.ru.domain import Gender as _Gender
from verso.ru.importers.google_sheets.cells import _get, _get_orig, _int_or_none, _parse_age, _parse_age_v2, _q, _safe_record_num
from verso.ru.importers.google_sheets.columns import GENDER_MAP, MONTH_ENUM, RELATIONSHIP_MAP, WITNESS_STATUS_WORDS
from verso.ru.importers.google_sheets.dsl_emit import _CAUSE_CONSTANTS, _cause_const, _clergy_person_call, _page_sort_key, _person_call, _varname
from verso.ru.importers.google_sheets.formats import DeathColumns
from verso.ru.dsl.source import format_import
from verso.ru.importers.google_sheets.names import _patr_should_be_lastname, _person_names_set




# ─── Death records ────────────────────────────────────────────────────────────

def generate_deaths(rows, archive, fund, inventory, case_, village, church, year,
                     cols=None, status_male="экономический крестьянин",
                     status_female="экономическая крестьянка",
                     cause_of_death="натуральная"):
    if cols is None:
        cols = DeathColumns()
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
        month = _int_or_none(_get(row, cols.D_MONTH)) or 0
        pages[page_id][month].append(row)

    if meta_counter:
        top_meta = meta_counter.most_common(1)[0][0]
        a, f, inv, c = top_meta
    else:
        a, f, inv, c = archive, fund, inventory, case_
    v = _get(rows[0], cols.VILLAGE) or village if rows else village
    ch = _get(rows[0], cols.CHURCH) or church if rows else church
    var_name = _varname(v, "deaths", year)

    lines = []
    uses_relationship = any(_get(row, cols.RELATIONSHIP) for row in rows)
    uses_relative = any(_get(row, cols.REL_NAME) or _get(row, cols.REL_NAME_CANON) for row in rows)
    # DSL v1: the facade and the causes' catalog, and `verso export-csv` writes the CSV.
    relationship_names = [n for n, used in (("Relationship", uses_relationship),
                                            ("relative", uses_relative)) if used]
    lines.append(format_import("verso.ru.dsl", ["Gender", "Month", "RecordDefaults", "death", "death_month",
                                                "death_records", "page", "person", *relationship_names]))
    # Collect cause-of-death constants used in this file
    cause_consts_used = set()
    all_causes = [cause_of_death]
    for row in rows:
        c = _get(row, cols.CAUSE) if cols.CAUSE is not None else ""
        if c:
            all_causes.append(c)
    for c in all_causes:
        if c and c in _CAUSE_CONSTANTS:
            cause_consts_used.add(_CAUSE_CONSTANTS[c])
    if cause_consts_used:
        lines.append(format_import("verso.ru.dsl.causes_of_death", cause_consts_used))
    lines.append("")
    lines.append(f"{var_name} = death_records(")
    lines.append(f"    {_q(a)}, {_q(f)}, {_q(inv)}, {_q(c)}, {_q(v)}, {_q(ch)},")
    lines.append(f"    {year},")

    cause_of_death_default = cause_of_death
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
            lines.append(f"          *death_month({month_enum},")
            for row in sorted(month_map[month], key=lambda r: (_int_or_none(_get(r, cols.RECORD_NUM)) or 0)):
                lines += _format_death_row(row, skip_statuses, cause_of_death_default,
                                           default_village=v, cols=cols)
            lines.append("                       ),")
        lines.append("          ),")

    lines.append("    defaults=RecordDefaults(")
    lines.append(f"        residence={_q(v)},")
    lines.append(f"        status_male={_q(status_male)},")
    lines.append(f"        status_female={_q(status_female)},")
    lines.append(f"        cause_of_death={_cause_const(cause_of_death_default)}")
    lines.append("    ),")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)



def _extract_witnesses_from_comment(comment):
    """Extract witness names embedded in a comment string (early-record format).

    Handles patterns like:
      "свидетели: Иван Иванов, Федор Петров"
      "свидетели: Иван Иванов и Федор Петров"
      "Петр Сидоров - свидетель Осип Ежевикин"
      "Свидетели: Федор Петров и Иван Петров, есть подозрение..."

    Returns (witnesses, remaining_comment) where:
      - witnesses is a list of (name, patr_or_None, status_or_None) tuples (up to 2)
      - remaining_comment is the comment with the witness portion stripped
    """
    if not comment:
        return [], comment
    m = re.search(r'(?i)свидетел[ьи]\s*[;:]?\s*', comment)
    if not m:
        return [], comment
    names_str = comment[m.end():].strip()
    remaining = re.sub(r'[\s\-–;,]+$', '', comment[:m.start()]).strip()
    witnesses = []
    # Split on "и" (and), comma, or semicolon to separate witness entries
    parts = re.split(r'\s+и\s+|[,;]', names_str)
    for i, raw in enumerate(parts):
        raw = raw.strip()
        if not raw:
            continue
        tokens = raw.split()
        status = None
        if tokens and tokens[0].lower() in WITNESS_STATUS_WORDS and len(tokens) >= 2:
            status = tokens[0]
            tokens = tokens[1:]
        name = tokens[0] if tokens else ""
        # Validate that the name token looks like a name (starts with uppercase Cyrillic)
        if not name or not re.match(r'^[А-ЯЁ]', name):
            # Not a name — this and everything after is trailing commentary
            trail = ", ".join(p.strip() for p in parts[i:] if p.strip())
            remaining = (remaining + "; " + trail).strip("; ") if remaining else trail
            break
        patr = tokens[1] if len(tokens) > 1 else None
        witnesses.append((name, patr, status))
        if len(witnesses) == 2:
            # Collect any remaining parts as trailing commentary
            trail_parts = [p.strip() for p in parts[i + 1:] if p.strip()]
            if trail_parts:
                trail = ", ".join(trail_parts)
                remaining = (remaining + "; " + trail).strip("; ") if remaining else trail
            break
    return witnesses, remaining



def _patr_derives_from_father(deceased_patr, father_name, gender_str):
    """Return True if deceased's patronymic is derivable from the father's first name.

    Used to suppress redundant patronymics in death records when both the deceased
    and their father are listed (e.g. deceased "Ирина Васильевна", father "Василий").
    """
    if not deceased_patr or not father_name:
        return False
    try:
        canon_patr = canonicalize_patronymic(modernize_orthography(deceased_patr))
    except ValueError:
        return False
    gender_enum = _Gender.MALE if gender_str in ("муж", "м", "мужской") else _Gender.FEMALE
    expected = derive_patronymic(modernize_orthography(father_name), gender_enum)
    return bool(expected) and canon_patr == expected



def _format_death_row(row, skip_statuses=frozenset(), cause_of_death_default="", default_village="",
                      cols=None):
    if cols is None:
        cols = DeathColumns()

    def _non_default_residence(col_idx):
        val = _get(row, col_idx)
        if val and val.lower() != default_village.lower():
            return val
        return None
    record_num = _safe_record_num(_get(row, cols.RECORD_NUM))
    gender_str = _get(row, cols.GENDER)
    gender = GENDER_MAP.get(gender_str, f"Gender.???_{gender_str}")
    d_day = _int_or_none(_get(row, cols.D_DAY))
    b_day = _int_or_none(_get(row, cols.B_DAY))
    if cols.AGE is not None:
        age = _parse_age(_get(row, cols.AGE))
    else:
        age = _parse_age_v2(
            _get(row, cols.AGE_YEARS), _get(row, cols.AGE_MONTHS),
            _get(row, cols.AGE_WEEKS), _get(row, cols.AGE_DAYS),
        )
    relationship_str = _get(row, cols.RELATIONSHIP)
    cause = _get(row, cols.CAUSE)
    comment = _get(row, cols.COMMENT)

    orig_str = _get(row, cols.ORIG_NAMES)
    orig_parts = []
    orig_comments = []  # " - " comments extracted from orig_parts
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
    # Use first orig comment as record comment if no explicit comment exists
    if not comment and orig_comments:
        comment = orig_comments[0]

    def _orig_matches_canon(orig_part, canon):
        """Check if an orig_names part plausibly matches a canonical name.

        Uses gender-based detection: if the canon and orig first token have
        opposite known genders, they can't be the same person.
        """
        if not canon:
            return True  # no hint → assume match
        first_token = orig_part.split(None, 1)[0] if orig_part else ""
        canon_gender = get_gender_from_name(modernize_orthography(canon))
        token_gender = get_gender_from_name(modernize_orthography(first_token))
        if canon_gender and token_gender and canon_gender != token_gender:
            return False
        return True

    def get_name_patr(orig_idx, name_col, patr_col, canon_name=None):
        if orig_idx < len(orig_parts) and orig_parts[orig_idx]:
            # Check if the orig part matches the expected canonical name
            if canon_name and not _orig_matches_canon(orig_parts[orig_idx], canon_name):
                return _get(row, name_col), _get(row, patr_col)
            tokens = orig_parts[orig_idx].split()
            name = tokens[0] if tokens else ""
            # Reject non-name words (comments in orig_names) — preserve as comment
            if name and not validate_first_name(modernize_orthography(name)):
                nonlocal comment
                if not comment:
                    comment = orig_parts[orig_idx]
                return _get(row, name_col), _get(row, patr_col)
            # Take only the second token as patr (ignore a third surname token —
            # the last name is already in the dedicated D_*_LAST_NAME column).
            patr = tokens[1] if len(tokens) >= 2 else ""
            # If the second token is a surname (not a valid patronymic), clear it
            # so the caller falls back to the canonical patronymic column.
            if patr and _patr_should_be_lastname(name, patr):
                patr = ""
            return name, patr
        return _get(row, name_col), _get(row, patr_col)

    has_deceased = bool(_get(row, cols.DEC_NAME) or _get(row, cols.DEC_NAME_CANON))
    has_relative = bool(_get(row, cols.REL_NAME) or _get(row, cols.REL_NAME_CANON))
    has_w1 = bool(_get(row, cols.W1_NAME) or _get(row, cols.W1_NAME_CANON))
    has_w2 = bool(_get(row, cols.W2_NAME) or _get(row, cols.W2_NAME_CANON))

    # For early records witnesses are embedded in the comment rather than
    # dedicated columns — extract them and strip from the comment text.
    comment_witnesses = []
    if not has_w1 and not has_w2:
        comment_witnesses, comment = _extract_witnesses_from_comment(comment)

    # Pre-resolve deceased and relative names so we can suppress the deceased's
    # patronymic when it is derivable from the father's first name.
    orig_idx = 0
    dn = dp = dec_last_name = dec_status = ""
    if has_deceased:
        dn_fb = _get(row, cols.DEC_NAME) or _get(row, cols.DEC_NAME_CANON)
        dp_fb = _get(row, cols.DEC_PATR) or _get(row, cols.DEC_PATR_CANON)
        dn, dp = get_name_patr(orig_idx, cols.DEC_NAME, cols.DEC_PATR, canon_name=dn_fb)
        dn, dp = dn or dn_fb, dp or dp_fb
        orig_idx += 1
        if cols.DEC_ORIG_NAME is not None:
            dec_orig_n = _get_orig(row, cols.DEC_ORIG_NAME)
            dec_orig_p = _get_orig(row, cols.DEC_ORIG_PATR) if cols.DEC_ORIG_PATR else ""
            if dec_orig_n:
                dn, dp = dec_orig_n, dp or dec_orig_p
        dec_last_name = _get(row, cols.DEC_LAST_NAME)
        dec_status = _get(row, cols.DEC_STATUS)

    rn = rp = rel_last_name = rel_status = ""
    if has_relative:
        rn_fb = _get(row, cols.REL_NAME) or _get(row, cols.REL_NAME_CANON)
        rp_fb = _get(row, cols.REL_PATR) or _get(row, cols.REL_PATR_CANON)
        rn, rp = get_name_patr(orig_idx, cols.REL_NAME, cols.REL_PATR)
        rn, rp = rn or rn_fb, rp or rp_fb
        orig_idx += 1
        if cols.REL_ORIG_NAME is not None:
            rel_orig_n = _get_orig(row, cols.REL_ORIG_NAME)
            rel_orig_p = _get_orig(row, cols.REL_ORIG_PATR) if cols.REL_ORIG_PATR else ""
            if rel_orig_n:
                rn, rp = rel_orig_n, rp or rel_orig_p
        rel_last_name = _get(row, cols.REL_LAST_NAME)
        rel_status = _get(row, cols.REL_STATUS)

    # Suppress deceased's patronymic when it is redundantly derivable from the father
    if relationship_str == "отец" and _patr_derives_from_father(dp, rn, gender_str):
        dp = ""

    _persons = []
    parts = [f"death({record_num}, {gender}, {d_day}, {b_day},"]

    if has_deceased:
        _persons.append((dn, dp))
        residence = _non_default_residence(cols.DEC_RESIDENCE)
        dec_call = _person_call(dn, dp or None, dec_last_name or None, residence=residence,
                               status=dec_status or None, skip_statuses=skip_statuses)
        if age is not None:
            age_repr = age if isinstance(age, int) else _q(str(age))
            parts.append(f"deceased={dec_call}, age={age_repr},")
        else:
            parts.append(f"deceased={dec_call},")

    if has_relative:
        _persons.append((rn, rp))
        residence = _non_default_residence(cols.REL_RESIDENCE)
        rel_call = _person_call(rn, rp or None, rel_last_name or None, residence=residence,
                               status=rel_status or None, skip_statuses=skip_statuses)
        rel_enum = RELATIONSHIP_MAP.get(relationship_str) if relationship_str else None
        if rel_enum is None and relationship_str:
            rel_enum = f"Relationship.???_{relationship_str}"
        parts.append(f"relatives=[relative({rel_call}, {rel_enum or 'None'})],")

    if has_w1:
        wn_fb = _get(row, cols.W1_NAME) or _get(row, cols.W1_NAME_CANON)
        wp_fb = _get(row, cols.W1_PATR) or _get(row, cols.W1_PATR_CANON)
        w1n, w1p = get_name_patr(orig_idx, cols.W1_NAME, cols.W1_PATR)
        w1n, w1p = w1n or wn_fb, w1p or wp_fb
        orig_idx += 1
        _persons.append((w1n, w1p))
        w1_call = _person_call(w1n, w1p or None)
        parts.append(f"witness1={w1_call},")
    elif comment_witnesses:
        cw1n, cw1p, cw1s = comment_witnesses[0]
        _persons.append((cw1n, cw1p))
        w1_call = _person_call(cw1n, cw1p, None, status=cw1s)
        parts.append(f"witness1={w1_call},")

    if has_w2:
        wn_fb = _get(row, cols.W2_NAME) or _get(row, cols.W2_NAME_CANON)
        wp_fb = _get(row, cols.W2_PATR) or _get(row, cols.W2_PATR_CANON)
        w2n, w2p = get_name_patr(orig_idx, cols.W2_NAME, cols.W2_PATR)
        w2n, w2p = w2n or wn_fb, w2p or wp_fb
        _persons.append((w2n, w2p))
        w2_call = _person_call(w2n, w2p or None)
        parts.append(f"witness2={w2_call},")
    elif len(comment_witnesses) > 1:
        cw2n, cw2p, cw2s = comment_witnesses[1]
        _persons.append((cw2n, cw2p))
        w2_call = _person_call(cw2n, cw2p, None, status=cw2s)
        parts.append(f"witness2={w2_call},")

    # Clergy
    for col_fio, param_name in [(cols.PRIEST_FIO, "priest"), (cols.DEACON_FIO, "deacon"),
                                (cols.DYACHOK_FIO, "dyachok")]:
        fio = _get(row, col_fio)
        if fio:
            call = _clergy_person_call(fio)
            if call:
                parts.append(f"{param_name}={call},")

    if cause and cause != cause_of_death_default:
        parts.append(f"cause_of_death={_cause_const(cause)},")

    if comment and not comment.lower().startswith("свидетели:"):
        if comment.strip() not in _person_names_set(*_persons):
            parts.append(f"comment={_q(comment)},")

    last = parts[-1].rstrip(",") + ")"
    parts[-1] = last + ","

    result = []
    result.append("                       " + parts[0])
    for p in parts[1:]:
        result.append("                             " + p.lstrip())
    return result
