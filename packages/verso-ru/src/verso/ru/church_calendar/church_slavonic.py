"""Reading the Church Slavonic of the 1906 Требник: names, numerals, months.

Only what the «Алфавит имён всех святых» needs. A paragraph there is

    А҆га́пїа, а҆прі́ллїа ѕ҃і.

— a Church Slavonic nominative, then genitive month names each followed by
day numerals with a titlo. Nothing here guesses: a token that is neither a
month nor a numeral is reported, not skipped, so an unexpected shape in the
source surfaces at import rather than as a missing saint.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: Combining titlo — what makes «а҃» the number one and «а» the conjunction.
TITLO = "҃"

#: Precomposed letters that carry a mark of their own, mapped before the
#: combining marks are dropped. Everything else is a base letter + marks.
_PRECOMPOSED = str.maketrans({
    "ѷ": "ѵ", "Ѷ": "Ѵ",  # izhitsa with double grave
    "ѐ": "е", "Ѐ": "Е", "ѝ": "и", "Ѝ": "И",
    "ї": "і", "Ї": "І",
})

#: Church Slavonic letters with their modern reading. ѵ is contextual (see
#: `fold`), and «оу» is a digraph.
_LETTERS = {
    "ѳ": "ф", "ѯ": "кс", "ѱ": "пс", "ѕ": "з", "ѡ": "о", "ѻ": "о", "ꙍ": "о",
    "ѽ": "о", "ѿ": "от", "є": "е", "ѣ": "е", "і": "и", "ꙋ": "у", "ѹ": "у",
    "ѧ": "я", "ꙗ": "я", "ꙑ": "ы", "ѫ": "у", "ᲂ": "о",
}

_VOWELS = "аеиоуыэюяєѣіѡѻꙋ"


def strip_marks(text: str) -> str:
    """Drop accents, breathings and titla. Precomposed letters such as «й» are
    single code points of their own and survive — decomposing to NFD first
    would turn «й» into «и» + breve and lose it."""
    text = text.translate(_PRECOMPOSED)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def fold(word: str) -> str:
    """A Church Slavonic word in modern letters, lower-case, marks dropped.

    ѵ reads «в» after а/е (Параскеѵа, Єѵдокіа) and «и» elsewhere (Агрѵпина);
    «оу» is one letter, у.
    """
    s = strip_marks(word).lower().replace("оу", "у").replace("ᲂу", "у")
    out: list[str] = []
    for i, c in enumerate(s):
        if c == "ѵ":
            # Not `s[i-1] if i else ""`: the empty string is `in` every string,
            # and an initial ѵ (Ѵпатїй, Ѵакінѳъ) would read «в».
            out.append("в" if i > 0 and s[i - 1] in "аеє" else "и")
        else:
            out.append(_LETTERS.get(c, c))
    return "".join(out)


def modern_name(headword: str) -> str:
    """A headword as a modern given name: «А҆га́пїа» → «Агапия», «Іѡа́ннъ» →
    «Иоанн», «Параске́ѵа» → «Параскева». The final ъ goes; «-иа» is «-ия»."""
    s = fold(headword).strip(".,;:")
    if s.endswith("ъ"):
        s = s[:-1]
    s = re.sub(r"иа$", "ия", s)
    s = re.sub(r"еа$", "ея", s)
    return s[:1].upper() + s[1:]


#: Day numerals. «є҃і» is 15 — units before the ten — so the value is a sum.
_DIGITS = {
    "а": 1, "в": 2, "г": 3, "д": 4, "є": 5, "е": 5, "ѕ": 6, "з": 7, "и": 8,
    "ѳ": 9, "і": 10, "к": 20, "л": 30,
}


def parse_numeral(token: str, *, titlo_required: bool = True) -> int | None:
    """A Cyrillic numeral as an int, or None when the token is not one.

    The titlo is required by default: without it «а» is a word. Inside a run
    of dates the OCR has dropped it once («ма́рта є. к҃ѳ.» under Ма́рко), so a
    caller that already knows the month may relax it for a token ending in a
    full stop."""
    if titlo_required and TITLO not in token:
        return None
    letters = strip_marks(token).lower().strip(".,;:")
    if not letters or any(c not in _DIGITS for c in letters):
        return None
    return sum(_DIGITS[c] for c in letters)


#: Genitive month names, as `fold` reads them.
MONTHS = {
    "ианнуариа": 1, "февруариа": 2, "марта": 3, "априллиа": 4, "маиа": 5,
    "иуниа": 6, "иулиа": 7, "августа": 8, "септемвриа": 9, "октовриа": 10,
    "ноемвриа": 11, "декемвриа": 12,
}


def parse_month(token: str) -> int | None:
    """The month a lower-case genitive names. A capitalised token is a NAME —
    the women Аѵгꙋста, Іꙋлїа and Іꙋнїа spell exactly what August, July and
    June do."""
    bare = strip_marks(token).strip(".,;:")
    if not bare or not bare[0].islower():
        return None
    return MONTHS.get(fold(bare))


@dataclass(frozen=True)
class AlphabetEntry:
    """One paragraph of the alphabet: the name as printed, the names given in
    brackets beside it («[и҆лѝ Валенті́нъ]»), and its days."""
    gender: str  # "M" or "F"
    headword: str
    alternates: tuple[str, ...]
    dates: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Unread:
    """A token the parser could not place — reported, never dropped."""
    headword: str
    token: str


#: «И҆мена̀ мꙋ́жєскїѧ.» and «И҆мена̀ жє́нскїѧ.» as `_heading` reads them.
#: «И҆мена̀ мꙋ́жєскїѧ.» and «И҆мена̀ жє́нскїѧ.» as `_heading` reads them.
_MALE_HEADING = "именамужеския"
_FEMALE_HEADING = "именаженския"
_BRACKETS = re.compile(r"\[([^\]]*)\]")
#: Words that introduce another form of the same name: «и҆лѝ Ма́ркъ»,
#: «ѻ҆́ный же І҆ѡ́сифъ», «[то́ же что̀ Васі́лїй]».
_LINKING_WORDS = frozenset({"или", "оныи", "оный", "же", "то", "что"})


def _heading(paragraph: str) -> str:
    return re.sub(r"[^а-я]", "", fold(paragraph))


def _bare(token: str) -> str:
    return strip_marks(token).strip(".,;:")


@dataclass
class _Open:
    headword: str
    alternates: list[str]
    dates: list[tuple[int, int]]
    month: int | None = None


def parse_alphabet(text: str) -> tuple[list[AlphabetEntry], list[Unread]]:
    """Every entry of «Алфавит имён», in the order of the book.

    Paragraphs are separated by blank lines and may wrap. Before the «Имена
    мужескія» heading is the chapter's title; a paragraph without a date is a
    letter heading («А҆»). Inside a paragraph a capitalised word before the
    first date is another form of the headword; after a date it opens the
    next entry — «Кѷрїѡ́нъ, ма́рта ѳ҃. Кѵ́ръ, і҆аннꙋа́рїа л҃а.» is two saints.
    Bracketed forms belong to the paragraph's first name.
    """
    entries: list[AlphabetEntry] = []
    unread: list[Unread] = []
    gender: str | None = None
    for raw in re.split(r"\n\s*\n", text):
        paragraph = " ".join(raw.split())
        if not paragraph:
            continue
        heading = _heading(paragraph)
        if heading == _MALE_HEADING:
            gender = "M"
            continue
        if heading == _FEMALE_HEADING:
            gender = "F"
            continue
        if gender is None:
            continue
        bracketed = [
            " ".join(w for w in group.split() if fold(_bare(w)) not in _LINKING_WORDS)
            .strip(" ,.")
            for group in _BRACKETS.findall(paragraph)
        ]
        opened: list[_Open] = []
        for token in _BRACKETS.sub(" ", paragraph).split():
            bare = _bare(token)
            if not bare:
                continue
            current = opened[-1] if opened else None
            if current is None:
                opened.append(_Open(token.strip(",."), [b for b in bracketed if b], []))
                continue
            if (m := parse_month(token)) is not None:
                current.month = m
                continue
            if current.month is not None and (
                    (d := parse_numeral(token)) is not None
                    or (token.endswith(".")
                        and (d := parse_numeral(token, titlo_required=False)) is not None)):
                current.dates.append((current.month, d))
                continue
            if fold(bare).lower() in _LINKING_WORDS:
                continue
            if bare[0].isupper():
                if current.dates:
                    opened.append(_Open(token.strip(",."), [], []))
                else:
                    current.alternates.append(token.strip(",."))
                continue
            unread.append(Unread(current.headword, token))
        for entry in opened:
            if not entry.dates:
                if entry.alternates or entry.month is not None:
                    unread.append(Unread(entry.headword, "(нет ни одной даты)"))
                continue
            entries.append(AlphabetEntry(gender, entry.headword, tuple(entry.alternates),
                                         tuple(entry.dates)))
    return entries, unread
