"""Name / patronymic / status normalization helpers."""
from verso.ru.naming import (get_gender_from_name, get_gender_from_old_patronymic, modernize_orthography, canonicalize_patronymic, validate_first_name, validate_old_patronymic)
from verso.ru.domain import Gender as _Gender




def _patr_should_be_lastname(name, patr):
    """Return True if patr is not a valid patronymic and should be treated as last name.

    This covers two cases:
    1. The patr cannot be canonicalized (e.g. "Шилохвостов" is a surname, not a patronymic).
    2. The patr gender conflicts with the name gender (e.g. "Лука" + "Иванова").
    """
    if not name or not patr:
        return False
    patr_modern = modernize_orthography(patr)
    # Check if patr is canonicalizable at all
    try:
        canonicalize_patronymic(patr_modern)
    except ValueError:
        return True  # not a valid patronymic → treat as last name
    # Check for gender conflict
    name_gender = get_gender_from_name(name)
    if not name_gender:
        return False
    patr_gender = get_gender_from_old_patronymic(patr_modern)
    if not patr_gender:
        return False
    if name_gender == patr_gender:
        return False  # genders match → valid patronymic
    # Before declaring gender conflict, check if the opposite-gender patronymic form exists
    swapped = _swap_patronymic_gender(patr_modern)
    if swapped and validate_old_patronymic(swapped):
        return False  # valid patronymic in the other gender form
    return True



def _swap_patronymic_gender(patr):
    """Swap patronymic gender ending (e.g. Петрова→Петров, Петров→Петрова)."""
    if patr.endswith("ова"):
        return patr[:-1]
    if patr.endswith("ева"):
        return patr[:-1]
    if patr.endswith("ина"):
        return patr[:-1]
    if patr.endswith("ов"):
        return patr + "а"
    if patr.endswith("ев"):
        return patr + "а"
    if patr.endswith("ин"):
        return patr + "а"
    return None



_MALE_STATUS_PREFIXES = (
    "крестьянин", "крестьянский ", "помещик", "солдат", "солдатский ",
    "купец", "купеческий ", "мещанин", "дьячок", "священник", "диакон",
    "пономарь", "рядовой", "отрок ", "иерей", "сын ",
    "ясачный ", "экономический ", "казенный ", "государственный ",
    "новокрещёный ", "будный ", "отставной ", "дворовый ",
    "мещанский ", "однодворец", "однодворческий ",
    "земской ", "приказчик ", "служитель ", "временнообязанный ",
    "унтер-офицер",
)

_FEMALE_STATUS_PREFIXES = (
    "крестьянка", "крестьянская ", "помещица", "солдатка", "солдатская ",
    "девка", "девица", "дева", "вдова", "попадья", "мещанка", "мещанская ", "женка",
    "жена ", "дочь ", "законная жена", "диаконская ", "купеческая ",
    "ясачная ", "экономическая ", "казенная ", "государственная ",
    "однодворческая ", "дворовая ", "временнообязанная ",
)



def _detect_status_gender(status_str):
    """Detect gender from a status string prefix. Returns Gender or None."""
    if not status_str:
        return None
    s = status_str.lower()
    for prefix in _FEMALE_STATUS_PREFIXES:
        if s.startswith(prefix):
            return _Gender.FEMALE
    for prefix in _MALE_STATUS_PREFIXES:
        if s.startswith(prefix):
            return _Gender.MALE
    return None



_STATUS_GENDER_SWAP = {
    "крестьянин ": "крестьянка ",
    "крестьянка ": "крестьянин ",
    "ясачный крестьянин": "ясачная крестьянка",
    "ясачная крестьянка": "ясачный крестьянин",
    "экономический крестьянин": "экономическая крестьянка",
    "экономическая крестьянка": "экономический крестьянин",
    "государственный крестьянин": "государственная крестьянка",
    "государственная крестьянка": "государственный крестьянин",
    "временнообязанный крестьянин": "временнообязанная крестьянка",
    "временнообязанная крестьянка": "временнообязанный крестьянин",
}



def _fix_status_gender(status, person_gender):
    """Swap status prefix gender to match the person's gender."""
    if not status or not person_gender:
        return status
    status_gender = _detect_status_gender(status)
    if status_gender and status_gender != person_gender:
        s_lower = status.lower()
        for old_prefix, new_prefix in _STATUS_GENDER_SWAP.items():
            if s_lower.startswith(old_prefix):
                return new_prefix + status[len(old_prefix):]
    return status



def _person_names_set(*name_patr_pairs):
    """Set of 'name' and 'name patr' strings used to detect redundant comments."""
    result = set()
    for name, patr in name_patr_pairs:
        if name and name != "?":
            result.add(name.strip())
            if patr:
                result.add(f"{name.strip()} {patr.strip()}")
    return result



def _parse_orig_names(orig_str, has_child, has_father, has_mother, has_gp1, has_gp2,
                      canon_names=None):
    """
    Parse the combined orig_names string into per-role (name, patr, surname) tuples.
    Returns dict with keys: child, father, mother, gp1, gp2.
    Format: "Имена в МК: child_name; father_name father_patr [surname]; ..."

    canon_names: optional dict mapping role → canonical first name (e.g. {"father": "Василий"}).
    Used to detect when a role's orig entry is missing: if the next part's first token
    doesn't match the canonical name, that role is skipped.

    Returns empty dict if too few parts for the expected roles.
    """
    result = {}
    if not orig_str:
        return result
    text = orig_str.removeprefix("Имена в МК:").strip()
    if not text:
        return result
    parts = [p.strip() for p in text.split(";")]
    num_expected = sum([has_child, has_father, has_mother, has_gp1, has_gp2])
    if canon_names is None:
        canon_names = {}
    # Allow fewer parts than expected when canon_names hints may cause skips.
    # Each canon hint could eliminate one expected role from the mapping.
    min_parts = num_expected - len(canon_names)
    if len(parts) < min_parts:
        return result  # too few parts — ambiguous mapping, caller will use canonical columns
    idx = 0

    def take():
        nonlocal idx
        if idx < len(parts):
            val = parts[idx]
            idx += 1
            return val
        return None

    # Words that are NOT person names — they indicate comment/note text in orig_names
    _NON_NAME_WORDS = frozenset([
        "населенный", "отчество", "незаконнорожденная", "незаконнорожденный",
        "возраст", "дата", "имя", "помещик", "помещица", "восприемники",
        "свидетели", "фамилия", "звание", "примечание",
    ])

    rejected_parts = []  # non-name parts rejected by role_matches

    def role_matches(role):
        """Check whether the next orig part plausibly belongs to this role.

        Uses three heuristics:
        1. Child names are single tokens — a multi-token part can't be a child.
        2. If the first token is a known non-name word, reject.
        3. Gender-based mismatch detection via canonical name hints.
        """
        if idx >= len(parts):
            return False
        part = parts[idx].strip()
        # Strip " - " comments before checking (e.g. "Настасья - неразборчиво...")
        if " - " in part:
            part = part.split(" - ", 1)[0].strip()
        first_token = part.split(None, 1)[0] if part else ""
        # Heuristic 0: reject known non-name words (comments in orig_names)
        if first_token.lower() in _NON_NAME_WORDS:
            rejected_parts.append(parts[idx].strip())
            return False
        # Heuristic 0b: reject if first token is not a recognized name
        if first_token and not validate_first_name(modernize_orthography(first_token)):
            rejected_parts.append(parts[idx].strip())
            return False
        # Heuristic 1: child entries are single-token
        if role == "child":
            if " " in part:
                return False  # multi-token part can't be a child name
            return True  # single-token part IS a child name (skip canon check)
        # Heuristic 2: gender-based mismatch detection.
        # If the canonical name has a known gender and the orig part's first token
        # has the OPPOSITE gender, this role's orig entry is likely missing.
        # This is more reliable than name matching which fails for dialectal
        # variants (e.g. Фоким≈Феоктист, Матрена≈Макрина).
        canon = canon_names.get(role)
        if canon:
            first_token = part.split(None, 1)[0] if part else ""
            canon_gender = get_gender_from_name(modernize_orthography(canon))
            token_gender = get_gender_from_name(modernize_orthography(first_token))
            if canon_gender and token_gender and canon_gender != token_gender:
                return False
        return True

    def split_name_patr(s):
        if not s:
            return ("", "", "")
        # Strip trailing comment after " - " (e.g. "Димитрий Фролов - имя трудно...")
        if " - " in s:
            s = s.split(" - ", 1)[0].strip()
        tokens = s.split(None, 2)  # split into up to 3 tokens (name, patr, surname)
        name = tokens[0]
        patr = tokens[1] if len(tokens) >= 2 else ""
        surname = tokens[2] if len(tokens) >= 3 else ""
        if patr.startswith("- "):
            patr = patr[2:].strip()
        elif patr == "-":
            patr = ""
        if name == "-":
            name = "?"
        return (name, patr, surname)

    if has_child:
        if role_matches("child"):
            val = take()
            if val:
                # Strip " - " comments (e.g. "Настасья - неразборчиво написано...")
                if " - " in val:
                    val = val.split(" - ", 1)[0].strip()
                result["child"] = (val, "", "")

    if has_father:
        if role_matches("father"):
            val = take()
            if val:
                result["father"] = split_name_patr(val)

    if has_mother:
        if role_matches("mother"):
            val = take()
            if val:
                result["mother"] = split_name_patr(val)

    if has_gp1:
        if role_matches("gp1"):
            val = take()
            if val:
                result["gp1"] = split_name_patr(val)

    if has_gp2:
        if role_matches("gp2"):
            val = take()
            if val:
                result["gp2"] = split_name_patr(val)

    # Also collect any remaining unconsumed parts that are non-name text
    while idx < len(parts):
        part = parts[idx].strip()
        if part:
            first_token = part.split(None, 1)[0] if part else ""
            if not first_token or first_token.lower() in _NON_NAME_WORDS or not validate_first_name(modernize_orthography(first_token)):
                rejected_parts.append(part)
        idx += 1

    result["_comments"] = rejected_parts
    return result
