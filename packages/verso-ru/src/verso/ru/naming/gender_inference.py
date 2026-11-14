"""Infer a person's gender from a first name or old-form patronymic."""

from verso.ru.gender import Gender
from verso.ru.naming.names_registry import (
    _find_full_patronymic_in_table, _find_old_patronymic_in_table, _name_facts, ignored_name_gender, is_ignored_name)


def get_gender_from_name(name: str | None) -> Gender | None:
    """
    Determines gender based on a name by looking it up in the lexicon: the one sex its
    entries have, or None — a name of both sexes, of no stated sex, or not found.
    A name of the old ignore list answers the sex that list gives (may be None).
    """
    if not name or '?' in name:
        return None

    if is_ignored_name(name):
        return ignored_name_gender(name)

    facts = _name_facts(name)
    if facts is None or (facts.male is not None) == (facts.female is not None):
        return None
    return Gender.MALE if facts.male is not None else Gender.FEMALE


def get_gender_from_old_patronymic(old_patronymic: str) -> Gender | None:
    """Determines gender based on a patronymic by looking it up in the lexicon.
    The men's short forms are asked first, then the women's; None if not found.
    Also resolves a *full* «-ович/-евич» form (gwar WWI / noble records) via its
    stamm so gender inference works for those too.
    """
    _, detected_gender = _find_old_patronymic_in_table(old_patronymic)
    if detected_gender is None:
        _, detected_gender = _find_full_patronymic_in_table(old_patronymic)

    return detected_gender
