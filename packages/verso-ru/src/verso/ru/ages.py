"""Age tokenizer and renderer for metric-book age strings.

`split_age` is the single age parser shared by the CSV exporters
(`verso.ru.exporters.csv_familio`), the census birth-date resolvers
(`verso.ru.targets.geni.translator.census_resolvers`) and the consolidation
candidate finder (`verso.ru.consolidation.candidates`). It produces the four
tabular slots (Лет, Месяцев, Недель, Дней) and is deliberately NOT changed by
the prose renderer below — CSV columns never carry prose.

`age_bounds` reads a stated age as the DAY INTERVAL it asserts — the arithmetic
every cross-record check shares (`verso death-age`, `sibling-spacing`,
`birth-claims`, the sweep's infant matcher), built on `split_age` so a change
to age syntax cannot make a check and the exported columns disagree.

`format_age` is the single renderer for READER-FACING text: the `Возраст:` line
of a profile's `about`, the death document's `Умерший:` line, the name-list
roster. Before it existed, nine separate f-strings in the Terraform translator
each formatted the raw DSL value their own way, appending a fixed " лет" that
ignored Russian numeral agreement («3 лет», «1 лет») and doubled the unit when
the value already carried one («полгода лет», «6 недель лет»).
"""

import re

_AGE_UNIT_TO_SLOT = {
    # 0=years, 1=months, 2=weeks, 3=days
    "г": 0, "л": 0, "лет": 0, "год": 0, "года": 0, "годов": 0,
    "м": 1, "мес": 1, "месяц": 1, "месяца": 1, "месяцев": 1,
    "н": 2, "нед": 2, "неделя": 2, "недели": 2, "недель": 2,
    "д": 3, "дн": 3, "день": 3, "дня": 3, "дней": 3,
}

_AGE_TOKEN_RE = re.compile(r'(\d+)\s*([а-яё]+)\.?', re.IGNORECASE)

# Common pre-formal Russian idioms used by old metric books — pre-expanded
# so authors don't have to migrate, and `split_age` produces the same
# tabular CSV output as the formal grammar would.
_AGE_IDIOMS = {
    "полгода": ("", "6", "", ""),
    "пол года": ("", "6", "", ""),
    "полу года": ("", "6", "", ""),
    "полтора года": ("1", "6", "", ""),
}


def split_age(age):
    """Split age into (Лет, Месяцев, Недель, Дней) tuple.

    Accepts:
      - None → all empty
      - int / float → goes into Лет
      - bare digit string → goes into Лет
      - compound string like "19 лет 6 мес", "6 м", "1 н" → parsed by unit
      - unparseable string → placed verbatim into Лет
    """
    if age is None:
        return ("", "", "", "")
    if isinstance(age, (int, float)):
        return (str(age), "", "", "")
    s = str(age).strip()
    if not s:
        return ("", "", "", "")
    if s.isdigit():
        return (s, "", "", "")
    idiom = _AGE_IDIOMS.get(s.lower())
    if idiom is not None:
        return idiom
    slots = ["", "", "", ""]
    pos = 0
    matched_any = False
    for m in _AGE_TOKEN_RE.finditer(s):
        # Reject if there's non-whitespace junk between tokens.
        if s[pos:m.start()].strip():
            return (s, "", "", "")
        unit = m.group(2).lower().rstrip(".")
        slot = _AGE_UNIT_TO_SLOT.get(unit)
        if slot is None:
            return (s, "", "", "")
        if slots[slot]:
            return (s, "", "", "")
        slots[slot] = m.group(1)
        pos = m.end()
        matched_any = True
    if not matched_any or s[pos:].strip():
        return (s, "", "", "")
    return tuple(slots)


# --------------------------------------------------------------------------- #
# Whole years                                                                  #
# --------------------------------------------------------------------------- #

#: The record calls and keywords whose age the DSL writes as an integer when it
#: is a whole number of years (AGE001, `verso.ru.linters.checks.ages`). An edit
#: of the page writes such an age by the same rule (`verso.ru.dsl.paths`).
AGE_CALLS = ("death", "marriage", "criminal_record", "wwi_record", "wwii_record")
AGE_KWARGS = ("age", "groom_age", "bride_age")

_YEAR_UNITS = frozenset(u for u, slot in _AGE_UNIT_TO_SLOT.items() if slot == 0)
_BARE_DIGITS_RE = re.compile(r'^\s*(\d+)\s*$')
_ONE_TOKEN_RE = re.compile(r'^\s*(\d+)\s*([а-яё]+)\.?\s*$', re.IGNORECASE)


def whole_years(s: str) -> str | None:
    """The digits of `s` when it spells a WHOLE number of years, else None.

    Matches a bare number ("70") and a single <number><year-unit> token
    ("1 год", "5 лет", "1 г"). Idioms carry a months component the integer
    cannot express, so they are excluded up front; compound and sub-year ages
    never match the single-token shape. `split_age` reads the integer and the
    string alike, so writing the integer moves no output.
    """
    if s.strip().lower() in _AGE_IDIOMS:
        return None
    m = _BARE_DIGITS_RE.match(s)
    if m:
        return m.group(1)
    m = _ONE_TOKEN_RE.match(s)
    if m and m.group(2).lower().rstrip(".") in _YEAR_UNITS:
        return m.group(1)
    return None


# --------------------------------------------------------------------------- #
# Prose rendering                                                              #
# --------------------------------------------------------------------------- #

# Values that mean "age not recorded". Callers already guard on these before
# emitting a `Возраст:` line; `format_age` returns None so they can keep doing so.
_AGE_ABSENT = (None, "", "?", "-")


def age_recorded(age) -> bool:
    """Whether a DSL age states a figure at all.

    `None`, `""`, `"?"` and `"-"` are the transcriber's «не записано». This is
    NOT `format_age(age) is not None`, though the two agree almost everywhere:
    `format_age` also returns None for a figure it has no words for — 0.02 of a
    year, a week-old infant — and a reader asking «did the book give an age?»
    must not lose those.
    """
    if isinstance(age, bool):  # bool is an int subclass — never an age
        return False
    if isinstance(age, str):
        age = age.strip()
    return age not in _AGE_ABSENT

# A bare decimal age string, e.g. "2.5" / "34,5" (mirrors census_age._BARE_NUMBER_RE).
_DECIMAL_AGE_RE = re.compile(r'^(\d+[.,]\d+)$')

# (one, few, many) per slot, in split_age order.
_SLOT_FORMS = (
    ("год", "года", "лет"),
    ("месяц", "месяца", "месяцев"),
    ("неделя", "недели", "недель"),
    ("день", "дня", "дней"),
)


def agree(n, one, few, many):
    """Pick the Russian form agreeing with `n`: 1 год / 3 года / 5 лет.

    11–14 take the `many` form despite ending in 1–4 («11 лет», «12 лет»).
    """
    n = abs(int(n))
    if n % 100 in (11, 12, 13, 14):
        return many
    last = n % 10
    if last == 1:
        return one
    if last in (2, 3, 4):
        return few
    return many


def _render_slots(slots):
    """Join non-empty split_age slots into agreeing prose, or None if all empty."""
    parts = []
    for value, (one, few, many) in zip(slots, _SLOT_FORMS, strict=True):
        if not value:
            continue
        try:
            n = int(value)
        except (TypeError, ValueError):
            # Non-numeric in a slot means split_age fell back to dumping the
            # whole unparseable string into Лет — hand it back verbatim.
            return str(value)
        parts.append(f"{n} {agree(n, one, few, many)}")
    return " ".join(parts) if parts else None


def _split_fractional_years(value):
    """(years, months) for a fractional year count, carrying 12 months up.

    Census revisions record half-years as `56.5`, which reads as data rather
    than prose; this turns the fraction into whole months.
    """
    years = int(value)
    months = round((float(value) - years) * 12)
    if months >= 12:
        years += 1
        months = 0
    return years, months


def format_age(age):
    """Render a DSL age as reader-facing Russian prose, or None if absent.

    45 → «45 лет»; 1 → «1 год»; 3 → «3 года»; 0.5 → «полгода»;
    1.5 → «1 год 6 месяцев»; "6 мес" → «6 месяцев»; "3 нед" → «3 недели»;
    "19 лет 6 мес" → «19 лет 6 месяцев».

    An idiom is returned verbatim — it is already prose, and re-deriving it
    from the parsed slots would silently rewrite `age="6 мес"` as «полгода».
    An age the tokenizer cannot parse (the source-literal «году», «с годом»
    of the 1719 revisions) is likewise passed through untouched: it is a
    faithful transcription, not a formatting error.
    """
    if age in _AGE_ABSENT:
        return None
    if isinstance(age, bool):  # bool is an int subclass — never an age
        return None

    if isinstance(age, str):
        s = age.strip()
        if not s:
            return None
        if s.lower() in _AGE_IDIOMS:
            return s
        # Census revisions write half-years as a bare decimal — "2.5", and in
        # the Маниловка 1858 list "34,5". split_age has no token for it and would
        # hand the string back verbatim, so convert to the float path here.
        m = _DECIMAL_AGE_RE.match(s)
        if m:
            age = float(m.group(1).replace(",", "."))
    if isinstance(age, float):
        if age.is_integer():
            # split_age would stringify 45.0 as "45.0", which no slot can parse
            # and which would then fall through to the verbatim path.
            age = int(age)
        else:
            years, months = _split_fractional_years(age)
            if years == 0 and months == 6:
                return "полгода"
            slots = (str(years) if years else "",
                     str(months) if months else "", "", "")
            return _render_slots(slots)

    return _render_slots(split_age(age))


# Calendar-free conversions. The sources give ages in whole units a clerk
# rounded by hand, so a day-exact calendar would add precision the input never
# had; these are good to a couple of days over a human lifetime.
DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = 30.44
DAYS_PER_WEEK = 7.0


def age_bounds(age) -> tuple[float, float] | None:
    """Stated age → the DAY INTERVAL it actually asserts, or None if unstated.

    **A stated age is a floor, not a measurement.** A clerk writing «1 годъ»
    means "has completed one year", so the child is anywhere in [1, 2) years —
    an interval a whole year wide. Comparing the midpoint, or the floor, against
    an elapsed time turns every ordinary truncation into a finding: on Горюхино
    that alone produced a hundred and thirty of them, all of them correct
    records. The interval is what the source claims, so the interval is what
    gets compared.

    Width comes from the SMALLEST unit written: «1 г 9 мес» is precise to the
    month, «6 нед» to the week, a bare «1» only to the year. A fractional value
    («5½ мѣс», «2¼») is a clerk being deliberate, and is treated as exact.

    Parsing is delegated to `split_age`, the same tabular parser the CSV
    exporters use, so a change to age syntax cannot make this check and the
    exported columns disagree. Verbatim idioms the tokenizer passes through
    («полгода», «с годом») yield no numbers and are skipped rather than guessed.
    """
    if age is None or str(age).strip() in ("", "?", "-"):
        return None
    parts = zip(split_age(age), (DAYS_PER_YEAR, DAYS_PER_MONTH, DAYS_PER_WEEK, 1.0),
                strict=True)
    total = 0.0
    granularity = 0.0
    seen = False
    for value, factor in parts:
        if not value:
            continue
        try:
            number = float(str(value).replace(",", "."))
        except ValueError:
            return None
        total += number * factor
        # The last (smallest) unit written sets the width; a fraction in it
        # means the clerk was not truncating.
        granularity = 0.0 if number != int(number) else factor
        seen = True
    return (total, total + granularity) if seen else None


def parent_age_prose(age) -> str | None:
    """A parent's age an act states, as reader-facing prose; «?» and «-» (not recorded, as RET004
    reads them) and an age `format_age` cannot render say nothing."""
    return format_age(age)


def birth_notes(b) -> str | None:
    """A birth's `comment=` and the parents' ages its fields hold — what the comment said before
    the ages had fields of their own («отцу 31 год, матери 30 лет»). A record without the fields
    answers its comment, byte for byte."""
    said = [f"{who} {text}" for who, text in (("отцу", parent_age_prose(getattr(b, "father_age", None))),
                                              ("матери", parent_age_prose(getattr(b, "mother_age", None))))
            if text]
    if not said:
        return b.comment
    return "; ".join(filter(None, [b.comment, ", ".join(said)]))
