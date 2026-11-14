"""Low-level cell value parsing helpers."""
from verso.ru.naming import (modernize_orthography, validate_first_name)




def _get(row, idx, default=""):
    if idx is not None and idx < len(row):
        return str(row[idx]).strip()
    return default



_PREREFORM_REPLACEMENTS = [
    ("ъ", ""), ("\u0456", "и"), ("\u0406", "И"),
    ("i", "и"), ("I", "И"), ("ѣ", "е"), ("ѳ", "ф"), ("ѵ", "и"),
]



def _get_orig(row, idx):
    """Read a value from an orig column, stripping pre-reform chars."""
    val = _get(row, idx)
    if val:
        for old, new in _PREREFORM_REPLACEMENTS:
            val = val.replace(old, new)
    return val



def _int_or_none(val):
    try:
        v = int(val)
        return v if v != 0 else None
    except (ValueError, TypeError):
        return None



def _parse_age(val):
    """Parse age: returns int for years, string for months/weeks/days, or None."""
    if not val:
        return None
    val = val.strip()
    try:
        v = int(val)
        return v if v != 0 else None
    except (ValueError, TypeError):
        pass
    import re
    if re.match(r'^\d+\s*(м|н|д)$', val):
        return val
    return None



def _parse_age_v2(years, months, weeks, days):
    """Combine 4 separate age columns into a single age value for the DSL.

    Priority: years (int) > months ("N м") > weeks ("N н") > days ("N д").
    """
    y = _int_or_none(years)
    if y:
        return y
    m = _int_or_none(months)
    if m:
        return f"{m} м"
    w = _int_or_none(weeks)
    if w:
        return f"{w} н"
    d = _int_or_none(days)
    if d:
        return f"{d} д"
    return None



def _split_fio(fio_str):
    """Split 'Name Patronymic' FIO string into (name, patr) tuple.

    Used for familio-standard format where godparents/witnesses only have a
    combined FIO column instead of separate name and patronymic columns.
    Handles surname-first format ('Сидоров Петр Иванович') by
    detecting when the first token is not a valid first name.
    """
    if not fio_str or not fio_str.strip():
        return ("", "")
    tokens = fio_str.strip().split(None, 2)
    name = tokens[0]
    # Detect surname-first format: if first token isn't a valid first name
    # but the second token is, skip the surname and use tokens 1+2
    if (len(tokens) >= 2
            and not validate_first_name(modernize_orthography(name))
            and validate_first_name(modernize_orthography(tokens[1]))):
        return (tokens[1], tokens[2] if len(tokens) > 2 else "")
    return (name, tokens[1] if len(tokens) > 1 else "")



def _q(s):
    """Quote a string for Python output, escaping backslashes, double quotes, and newlines."""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\r', '').replace('\n', ' ') + '"'



def _safe_record_num(val):
    """Format record number for Python output. Quote if non-numeric, default to 0 if empty."""
    if not val or not val.strip():
        return "0"
    val = val.strip()
    try:
        return str(int(val))
    except ValueError:
        return _q(val)  # non-numeric like "15а" → quoted string
