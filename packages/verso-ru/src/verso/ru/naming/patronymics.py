"""Derive child patronymics (modern and old-form) from a father's name."""

from verso.ru.gender import Gender
from verso.ru.naming.forms import modern_patronymic, old_patronymic
from verso.ru.naming.names_registry import _name_facts, find_old_patronymic_by_modern

_MALE = Gender.MALE


def derive_patronymic(father_name: str | None, child_gender: Gender | None) -> str:
    """
    Derives a child's patronymic from the father's first name.
    The father's forms in the lexicon first; where the lexicon has none, the rule (`forms.modern_patronymic`).
    """
    if not father_name:
        return ""

    name = father_name
    if '?' in name:
        return "?"

    # The lexicon first: the father's own forms
    facts = _name_facts(name)
    if facts is not None:
        forms = facts.forms
        if forms is not None:
            patronymic = forms.patronymic_m if child_gender is _MALE else forms.patronymic_f
            if patronymic:
                return patronymic

    return modern_patronymic(name, child_gender)


def derive_old_patronymic(father_name: str | None, child_gender: Gender | None) -> str:
    """Derive old-form patronymic directly from the father's forms in the lexicon.

    Unlike derive_patronymic() which returns canonical modern form (Гавриилович),
    this returns the old form of the father's OWN spelling (Гаврилов for Гаврил,
    Гавриилов for Гавриил).
    """
    if not father_name or '?' in father_name:
        return ""

    facts = _name_facts(father_name)
    if facts is not None:
        if facts.forms is not None:
            old_form = facts.forms.old_patronymic_m if child_gender == Gender.MALE else facts.forms.old_patronymic_f
            if old_form:
                return old_form
        own = None if facts.forms is None else (
            facts.forms.old_patronymic_m if child_gender == Gender.MALE else facts.forms.old_patronymic_f)
        if _MALE in facts.derives and own is None:
            # A man's name of a layer that writes only the forms the rules do not give: the rule's
            # (`Lexicon.forms_of`, as the reverse indexes read it) — but for a cell that says «no such form» ("").
            return old_patronymic(father_name, child_gender)

    # Then the short form of the modern patronymic, by the lexicon.
    canonical = derive_patronymic(father_name, child_gender)
    if canonical:
        old = find_old_patronymic_by_modern(canonical)
        if old:
            return old
    # A father the lexicon does not know: the rule. One it knows, whose cell says «no such form» or whose layer
    # does not derive, keeps its silence.
    return old_patronymic(father_name, child_gender) if facts is None else ""


def degenitivize_patronymic(genitive_patr: str) -> str:
    """Convert a genitive-case old patronymic to nominative.
    'Иоаннова' -> 'Иоаннов', 'Семенова' -> 'Семенов'.
    'Платоновой' -> 'Платонов' (feminine genitive ending -ой).
    """
    if not genitive_patr:
        return ""
    if genitive_patr.endswith('ой'):
        return genitive_patr[:-2] + 'а'
    if genitive_patr.endswith('а'):
        return genitive_patr[:-1]
    return genitive_patr
