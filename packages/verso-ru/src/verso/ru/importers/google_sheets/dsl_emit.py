"""DSL code-string emission primitives (person() calls, cause constants)."""
from verso.ru.naming import (get_gender_from_name, modernize_orthography, validate_old_patronymic, find_old_patronymic_by_modern)
from verso.ru.importers.google_sheets.cells import _q
from verso.ru.importers.google_sheets.columns import _TITLE_WORDS
from verso.ru.importers.google_sheets.names import _fix_status_gender, _patr_should_be_lastname




# Load cause-of-death constants for code generation
def _load_cause_constants() -> dict[str, str]:
    """Return {string_value: CONSTANT_NAME} from causes_of_death.py, including aliases."""
    try:
        from verso.ru.linters.checks.single_line_calls import KNOWN_CAUSES
        return KNOWN_CAUSES
    except Exception:
        return {}



_CAUSE_CONSTANTS: dict[str, str] = _load_cause_constants()



def _cause_const(value: str) -> str:
    """Return the constant name for a cause-of-death value, or quoted string if not known."""
    if value in _CAUSE_CONSTANTS:
        return _CAUSE_CONSTANTS[value]
    try:
        from verso.ru.linters.checks.single_line_calls import known_cause
        const = known_cause(value)
    except Exception:
        const = None
    return const or _q(value)



def _clergy_person_call(fio_str):
    """Build a person(...) call for clergy from a combined FIO string like 'Степан Космин'."""
    if not fio_str or not fio_str.strip():
        return None
    parts = fio_str.strip().split()
    name = parts[0]
    patr = " ".join(parts[1:]) if len(parts) > 1 else None
    # Convert modern-form patronymics to old form, or drop if unrecognized
    if patr and not validate_old_patronymic(modernize_orthography(patr)):
        old_form = find_old_patronymic_by_modern(modernize_orthography(patr))
        if old_form:
            patr = old_form
        else:
            patr = None
    args = [_q(name)]
    if patr:
        args.append(_q(patr))
    return "person(" + ", ".join(args) + ")"



def _person_call(name, patr=None, last_name=None, residence=None, status=None, comment=None,
                 skip_statuses=frozenset()):
    """Build a person(...) call string."""
    if not name:
        return None
    # "Имена" in the name field is a placeholder meaning the name is unrecorded.
    if name == "Имена":
        name = "?"
        patr = None
        last_name = None
    # A known title/status word in the name field: the real name is in patr (or last_name).
    elif name.lower() in _TITLE_WORDS:
        status = status or name
        name = patr or last_name or "?"
        patr = None
        last_name = None
    # If patronymic is invalid or conflicts with name gender, treat it as a last name instead
    if patr and _patr_should_be_lastname(name, patr):
        last_name = last_name or patr
        patr = None
    # Drop long-form modern patronymics (e.g. "Иванович" from *_PATR_CANON columns) that
    # genealogy.py's validate_old_patronymic would reject at runtime.
    if patr and not validate_old_patronymic(modernize_orthography(patr)):
        patr = None
    # Auto-swap status gender to match the person's name gender
    if status:
        person_gender = get_gender_from_name(modernize_orthography(name)) if name and name != "?" else None
        status = _fix_status_gender(status, person_gender)
    args = [_q(name)]
    if patr:
        args.append(_q(patr))
    kwargs = []
    if last_name:
        kwargs.append(f"last_name_orig={_q(last_name)}")
    if residence:
        kwargs.append(f"residence={_q(residence)}")
    if status and status not in skip_statuses:
        kwargs.append(f"status={_q(status)}")
    if comment:
        kwargs.append(f"comment={_q(comment)}")
    all_args = args + kwargs
    return f"person({', '.join(all_args)})"



# ─── Helpers ──────────────────────────────────────────────────────────────────

def _varname(village, record_type, year):
    """Generate Python variable name from village name."""
    transliteration = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    # Strip "село" prefix if present
    name = village.lower()
    for prefix in ("село ", "деревня ", "с. ", "д. "):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    result = ""
    for ch in name:
        result += transliteration.get(ch, ch if ch.isalnum() else "_")
    result = result.strip("_")
    return f"{result}_{record_type}_{year}"



def _page_sort_key(page_id):
    """Sort pages: numeric value first, then 'об' suffix."""
    s = str(page_id).lower().rstrip()
    is_ob = s.endswith("об")
    num_str = s.removesuffix("об").strip()
    try:
        return (int(num_str), 1 if is_ob else 0)
    except ValueError:
        return (float("inf"), s)
