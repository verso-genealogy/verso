"""Genitive-case rendering of a person's name.

Used by reader-facing generated prose that names one person *in relation to*
another — «жена Василия Семёновича», «сын Кузьмы Савельевича» — where the
relative's name has to be declined. There is no morphology library in this
project's dependency set (and none is wanted: the runtime deps are deliberately
minimal), so this module resolves the genitive from data first and rules second:

  * **Given names** come from the lexicon's forms (the old names.csv's
    `Родительный падеж`, populated for every row). Measured over the committed `.tf` tree, 350 of
    the 393 distinct given names resolve straight from the table; the 43 misses
    are the Mordva / pre-Christian names of the early Заманиловка and Горюхино
    revisions (Бурмяй, Пичкинза, Адмак, …), which the declension rules of
    `verso.ru.naming.forms` handle.
  * **Patronymics** are rules-only — every one of the 561 distinct patronymics
    in the tree ends in `-ич`, `-на`, or an old possessive `-ин`, all of which
    decline regularly.

Anything the rules cannot classify is returned **verbatim in the nominative**.
This mirrors `verso.ru.ages.format_age`: generated prose degrades to the source
literal rather than raising, because a name that cannot be declined must never
be able to block the whole terraform generation.
"""

from verso.ru.gender import Gender
from verso.ru.naming import forms
from verso.ru.naming.names_registry import genitive_from_name

# Feminine old-form possessive patronymics/surnames (Фомина, Семенова) decline
# like adjectives — `-ой`, not the noun `-ы`. Checked BEFORE the `-на` rule,
# which would otherwise mangle Фомина → «Фомины».
_POSSESSIVE_FEM_ENDINGS = ("ова", "ева", "ёва", "ина", "ына")

# Masculine old-form possessives (Фомин, Семенов) take a plain `-а`.
_POSSESSIVE_MASC_ENDINGS = ("ов", "ев", "ёв", "ин", "ын")


def genitive_given_name(name: str | None, gender: Gender | None = None) -> str:
    """The genitive of a given name — from the lexicon when known, else by rule (`forms.genitive`).

    `gender` only disambiguates a soft-sign ending: masculine `-ь` names are
    second declension (Игорь → Игоря), feminine ones third (Любовь → Любови).
    """
    if not name:
        return ""
    from_table = genitive_from_name(name)
    if from_table:
        return from_table
    return forms.genitive(name, gender)


def genitive_patronymic(patr: str | None) -> str:
    """The genitive of a patronymic, modern («-ич» / «-на») or old possessive."""
    if not patr:
        return ""
    if patr.endswith(_POSSESSIVE_FEM_ENDINGS):
        return patr[:-1] + "ой"
    if patr.endswith("ич"):
        return patr + "а"
    if patr.endswith("на"):
        return patr[:-1] + "ы"
    if patr.endswith(_POSSESSIVE_MASC_ENDINGS):
        return patr + "а"
    return patr


def genitive_person_name(person) -> str:
    """«Василия Семёновича» — a person's canonical given name plus modern
    patronymic, both declined into the genitive.

    Deliberately the same two strings the profile's own `names.ru` carries
    (`first_name` / `middle_name`), and deliberately WITHOUT the surname: this
    renders a reference to somebody already listed in the same household table,
    where given name + patronymic identifies them unambiguously. Returns "" for
    a person with no usable given name.
    """
    if person is None:
        return ""
    first = person.get_canonical_name() or person.name_modern
    parts = [genitive_given_name(first, person.gender)]
    patr = genitive_patronymic(person.patr_modern)
    if patr:
        parts.append(patr)
    return " ".join(p for p in parts if p)
