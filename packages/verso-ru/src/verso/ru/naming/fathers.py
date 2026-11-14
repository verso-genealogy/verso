"""Whether a patronymic and a father's given name can name one man.

The keys `father-claims` compares two claims about one person's father by, and
the census linter (CPL012) a member's patronymic against the parent the
household links them to. One rule for both, so the linter refuses nothing the
facts layer would accept. There are several kinds of key, so that one gap in
the names table cannot manufacture a disagreement:

- the patronymic, canonical and in the child's gender — for a named father,
  the patronymic his name derives (`derive_patronymic`): «Изот» and
  «Изотович» agree here though the table's base for «Изотович» is «Зотей»;
- the father's given name by its base form — for a patronymic, the father the
  names table reads out of it: «Егорович» and «Георгиевич» agree here;
- for a name the table does not know at all — the pre-Christian names of the
  1717–1721 rolls — the patronymic beginning with the father's name less its
  final vowel: «Шумила» and «Шумилович», «Пичкинза» and «Пичкинзин».
"""
from __future__ import annotations

from verso.ru.gender import Gender
from verso.ru.naming.names_registry import father_name_for_patronymic, matching_base
from verso.ru.naming.orthography import canonicalize_patronymic
from verso.ru.naming.patronymics import derive_patronymic

#: Letters the corpus spells two ways — the fold the other name keys use.
_FOLD = str.maketrans({"ѳ": "ф", "і": "и", "ѣ": "е", "ѵ": "и", "ё": "е",  # i18n: content — the old letters folded
                       "й": "и", "ъ": None})  # i18n: content — the old letters folded
_VOWELS = "аеиоуыэюяйь"  # i18n: content — the letters a stem drops


def fold(text: str | None) -> str:
    return (text or "").strip().lower().translate(_FOLD)


def _patronymic_key(patronymic: str | None) -> str | None:
    if not patronymic:
        return None
    return "p:" + fold(canonicalize_patronymic(patronymic) or patronymic)


def _genders(gender: Gender | None) -> tuple[Gender, ...]:
    if gender is Gender.MALE or gender is Gender.FEMALE:
        return (gender,)
    return (Gender.MALE, Gender.FEMALE)


def father_keys(given: str, child: Gender | None) -> frozenset[str]:
    """The keys a named father's claim compares by."""
    keys = {"b:" + fold(matching_base(given, Gender.MALE))}
    for gender in _genders(child):
        if (key := _patronymic_key(derive_patronymic(given, gender))) is not None:
            keys.add(key)
    return frozenset(keys)


def patronymic_keys(patronymic: str, gender: Gender | None) -> frozenset[str]:
    """The keys a patronymic claim compares by."""
    keys: set[str] = set()
    if (key := _patronymic_key(patronymic)) is not None:
        keys.add(key)
    father = father_name_for_patronymic(patronymic)
    if father:
        keys.add("b:" + fold(matching_base(father, Gender.MALE)))
        for g in _genders(gender):
            if (key := _patronymic_key(derive_patronymic(father, g))) is not None:
                keys.add(key)
    return frozenset(keys)


def name_stem(given: str) -> str:
    """A father's name less its final vowel — what a patronymic built from it
    begins with, whether or not the names table knows the name."""
    folded = fold(given)
    return folded[:-1] if folded and folded[-1] in _VOWELS else folded


def stem_agrees(patronymic: str, stems: frozenset[str] | set[str]) -> bool:
    """Whether a patronymic begins with one of a father's stems."""
    raw = fold(patronymic)
    return any(len(stem) >= 3 and raw.startswith(stem) for stem in stems)


def can_name(patronymic: str, father: str, child: Gender | None) -> bool:
    """Whether `patronymic` can be the patronymic of a child of `father`."""
    return bool(patronymic_keys(patronymic, child) & father_keys(father, child)
                or stem_agrees(patronymic, {name_stem(father)}))
