"""Orthography normalization and canonicalization of names and patronymics."""

import functools
import re

from verso.ru.gender import Gender
from verso.ru.naming import names_registry
from verso.ru.naming.forms import modern_from_old
from verso.ru.naming.names_registry import _full_reading, _name_facts, _old_reading, is_ignored_patronymic


# Pure, and asked of every name a linter reads, many times over: its answers are kept.
@functools.lru_cache(maxsize=1 << 16)
def modernize_orthography(text: str | None) -> str:
    """
    Converts historical Russian orthography to modern.
    Replaces ѣ -> е, і -> и, ѳ -> ф, ѵ -> и, ѯ -> кс, and removes a word's trailing ъ, a doubtful
    reading's «?» after it included («Свиристеловъ?» -> «Свиристелов?»).
    Also handles some common look-alikes like Ө (barred O) for Ѳ (Fita).
    """
    if not text:
        return ""

    # Character replacements
    replacements = {
        'ѣ': 'е', 'Ѣ': 'Е',
        'і': 'и', 'І': 'И',
        'ѳ': 'ф', 'Ѳ': 'Ф',
        'ѵ': 'и', 'Ѵ': 'И',
        'ѯ': 'кс', 'Ѯ': 'Кс',
        'ө': 'ф', 'Ө': 'Ф',  # Look-alikes for Fita
    }

    modernized = text
    for old, new in replacements.items():
        modernized = modernized.replace(old, new)

    # Remove trailing ъ — also before the «?» of a doubtful reading («Свиристеловъ?» → «Свиристелов?», В19)
    modernized = re.sub(r'ъ(?=\s|$|[.,;?])', '', modernized)
    modernized = re.sub(r'Ъ(?=\s|$|[.,;?])', '', modernized)

    return modernized


def canonicalize_name(name: str | None, gender: Gender | None = None) -> str:
    """
    Returns the canonical base form of a name from the lexicon.
    For name variants, returns the primary/canonical form; a canonical name is returned as is.
    If gender is provided, only that sex's entry is read. Without it, a name the lexicon holds
    in one sex answers as that sex's entry, a name of both sexes — «Лука» is М on its own and
    Ж mapping to Гликерия — as itself, unless the lexicon says otherwise (an entry keyed
    (None, name)). A name the lexicon does not know is returned as-is.
    """
    if not name or '?' in name:
        return name or ""

    facts = _name_facts(name)
    if facts is None:
        return name
    if gender is not None:
        entry = facts.male if gender == Gender.MALE else facts.female
        return entry.canonical_form if entry is not None else name
    if facts.unsexed is not None and facts.unsexed.canonical:
        return facts.unsexed.canonical
    if facts.male is not None and facts.female is not None:
        return name
    entry = facts.male or facts.female
    return entry.canonical_form if entry is not None else name


def canonicalize_patronymic(patronymic: str | None) -> str:
    """
    Converts an old-form patronymic to canonical modern form (e.g. Иванов -> Иванович).
    Automatically detects gender from endings or the names table.
    First tries to find the patronymic in the names table, then falls back to algorithmic conversion.
    """
    if not patronymic:
        return ""

    p = patronymic
    if '?' in p:          # partial illegibility — return as-is
        return p

    # Try the lexicon first — a pre-reform spelling that happens to end
    # in a modern suffix (e.g. Володимировна) must resolve to its registered
    # modern canonical form (Владимировна), not short-circuit as "already
    # canonical". Only after that lookup fails do we treat the modern-form
    # ending as "already canonical".
    # One lexicon for the whole question: it is asked on every person a translation builds.
    lexicon = names_registry.current_lexicon()
    row, detected_gender = _old_reading(lexicon, p)
    if row and detected_gender:
        modern = row.modern
        if modern:
            return modern
        # Found in old-patronymic table but modern form is blank — fall through
        # to algorithmic conversion below rather than raise (common for rare
        # 18th-century Mordva/regional names).

    # A *full* form («Абрамович») — resolve it through the stamm (the father's
    # short patronymic) to the registered canonical, so a verbatim WWI/noble
    # full form normalises the same as the short input would: «Абрамович» →
    # «Авраамович», not kept literally. Falls through if the stamm is unknown.
    full_row, full_gender = _full_reading(lexicon, p)
    if full_row and full_gender:
        modern = full_row.modern
        if modern:
            return modern

    # Already in modern canonical form
    if p.endswith(('ович', 'евич', 'ич')):
        return p
    if p.endswith(('овна', 'евна', 'ична', 'ишна')):
        return p

    # Accept ignore-list entries (Mordva/regional, pre-reform variants, genitive forms).
    # Anything else raises so genuine DSL typos surface.
    if row is None and not is_ignored_patronymic(patronymic):
        raise ValueError(f"Cannot canonicalize patronymic '{patronymic}': not found in names table.")

    # The rule over the short form's ending; what it cannot read is returned as written
    modern = modern_from_old(p)
    return modern if modern is not None else p
