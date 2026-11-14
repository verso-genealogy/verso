"""Surname grammatical transforms (feminization, degenitivization), and the
root two scribes' spellings of one family share (`normalise_surname`,
`within_one_letter`) — the comparison `name-variants` and the reconciliation
channel both make."""

import re


def feminize_surname(name: str) -> str:
    """Convert a masculine Russian surname to its feminine form. Used by
    `Birth.__init__` when a daughter inherits her father's surname (which
    the source document records in male form) so the emitted profile
    uses the grammatically-correct feminine ending.

    Standard suffix transforms:
      -ов / -ев      → -ова / -ева
      -ин             → -ина
      -ский / -цкий  → -ская / -цкая
      -ой             → -ая   (adjectival, e.g. Кривой → Кривая)

    Any name that doesn't match a standard suffix (including already-
    feminine forms or non-Russian surnames) is returned unchanged.
    """
    if not name:
        return name
    for suf, fem in (
        ("ский", "ская"),
        ("цкий", "цкая"),
        ("ой", "ая"),
        ("ов", "ова"),
        ("ев", "ева"),
        ("ин", "ина"),
    ):
        if name.endswith(suf):
            return name[:-len(suf)] + fem
    return name


def degenitivize_surname(genitive_surname: str) -> str:
    """Convert a genitive-case surname to nominative.
    'Индюшева' -> 'Индюшев', 'Ляпкина' -> 'Ляпкин'.
    Strip trailing 'а' or 'ой' for male genitive forms.
    """
    if not genitive_surname:
        return ""
    if genitive_surname.endswith('ой'):
        return genitive_surname[:-2]
    if genitive_surname.endswith('а'):
        return genitive_surname[:-1]
    return genitive_surname


_GENDER_ENDINGS = re.compile(r"(ова|ева|ина|ына|ского|ская|ов|ев|ин|ын|а)$")


def normalise_surname(surname: str) -> str:
    """A surname reduced to the root the scribes agree on.

    Folds the orthography they do not (ѣ/е, і/и, ё/е, trailing ъ), strips the
    gendered ending so «Оляпкин» meets «Оляпкина», and normalises a leading
    а→о — «Аляпкин» and «Оляпкин» are one family.
    """
    s = surname.strip().lower()
    s = s.replace("ѣ", "е").replace("і", "и").replace("ё", "е").replace("ъ", "")
    s = _GENDER_ENDINGS.sub("", s)
    return "о" + s[1:] if s.startswith("а") else s


def within_one_letter(a: str, b: str) -> bool:
    """True when two roots differ by at most one insertion, deletion or swap."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = seen = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            seen += 1
            if seen > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
        else:
            i += 1
            j += 1
    return seen + (len(b) - j) <= 1
