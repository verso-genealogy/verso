"""Validate first names and old-form patronymics against the names registry."""

from verso.ru.naming.names_registry import (
    _find_full_patronymic_in_table, _find_old_patronymic_in_table, _name_facts, is_ignored_name, is_ignored_patronymic)


def validate_first_name(name: str | None) -> bool:
    """
    Validates that the lexicon knows a first name: an entry of a known sex, or the old
    ignore list.
    """
    if not name or '?' in name:
        return True

    if is_ignored_name(name):
        return True

    facts = _name_facts(name)
    return facts is not None and bool(facts.sexed)


def validate_old_patronymic(patronymic: str | None, accept_full: bool = False) -> bool:
    """
    Validates that the lexicon knows a patronymic: a short (old) form of either sex, or one
    it knows tied to nothing (the old patronymics_ignore.csv).

    By default only the short pre-reform полуотчество form is accepted — the
    Google-Sheets importer relies on this strictness to *drop* a modern/full form
    mistakenly placed in the old-patronymic column. Pass `accept_full=True` for
    hand-authored DSL (Person / the names linter): then a *full* «-ович/-евич»
    form is also accepted when its stamm (the father's short patronymic) is
    registered, so gwar.mil.ru WWI cards and noble records keep their verbatim
    form. A full form whose stamm is unknown is still rejected (typos surface).
    """
    if not patronymic or '?' in patronymic:
        return True

    row, _ = _find_old_patronymic_in_table(patronymic)
    if row is not None:
        return True

    if accept_full:
        full_row, _ = _find_full_patronymic_in_table(patronymic)
        if full_row is not None:
            return True

    return is_ignored_patronymic(patronymic)
