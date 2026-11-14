"""Name handling: gender inference, orthography/canonicalization, patronymic and
surname derivation, validation — split by domain concept from the former
naming_utils module. Public functions are re-exported here so callers can use
``from verso.ru.naming import derive_patronymic`` regardless of the owning submodule.
"""

from verso.ru.naming.gender_inference import (
    get_gender_from_name, get_gender_from_old_patronymic)
from verso.ru.naming.genitive import (
    genitive_given_name, genitive_patronymic, genitive_person_name)
from verso.ru.naming.names_registry import (
    _find_name_in_table, father_name_for_patronymic, matching_base, find_old_patronymic_by_modern, genitive_from_name, name_from_genitive)
from verso.ru.naming.orthography import (
    canonicalize_name, canonicalize_patronymic, modernize_orthography)
from verso.ru.naming.patronymics import (
    degenitivize_patronymic, derive_old_patronymic, derive_patronymic)
from verso.ru.naming.surnames import degenitivize_surname, feminize_surname
from verso.ru.naming.validation import validate_first_name, validate_old_patronymic

__all__ = [
    "_find_name_in_table",
    "canonicalize_name",
    "canonicalize_patronymic",
    "degenitivize_patronymic",
    "degenitivize_surname",
    "derive_old_patronymic",
    "derive_patronymic",
    "father_name_for_patronymic",
    "feminize_surname",
    "find_old_patronymic_by_modern",
    "genitive_from_name",
    "genitive_given_name",
    "genitive_patronymic",
    "genitive_person_name",
    "get_gender_from_name",
    "get_gender_from_old_patronymic",
    "matching_base",
    "modernize_orthography",
    "name_from_genitive",
    "validate_first_name",
    "validate_old_patronymic",
]
