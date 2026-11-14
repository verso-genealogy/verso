"""Pascha, and the days on which the Church did not marry.

A wedding dated in Great Lent, in Bright Week or in Святки is almost always a
misread month or day: the books record what the priest did, and he did not
marry then. The question is asked of the DATE, so it needs the movable part
of the year — Pascha — as much as the fixed one.

`pascha()` is Meeus' algorithm for the Julian computus. `dateutil.easter(y,
EASTER_JULIAN)` gives the same Julian-numbered day; the tests hold the two
together over 1700–1917, and this module stays stdlib-only so a linter can
import it.

Which days carried a ban follows the modern summaries of the Устав (letovohram.ru,
rpsc.ru); no pre-1917 primary text was at hand. The split into `strict`
periods (the fasts, the Bright Week, Святки, the one-day fasts) and the rest
(eves of Wednesday, Friday and Sunday; eves of great feasts; Meatfare Sunday)
is a prior, and the `wedding-calendar` check says how often the books keep
each. Храмовые праздники are not here: they belong to a parish, not to the
Church.
"""
from __future__ import annotations

from dataclasses import dataclass

from verso.ru.church_calendar.julian import (
    SATURDAY, THURSDAY, TUESDAY, jdn, weekday)


def pascha(year: int) -> tuple[int, int]:
    """(month, day) of Pascha in `year`, Julian numbering (1850 → 23 April)."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return month, day


@dataclass(frozen=True)
class WeddingBan:
    """Why венчание was not performed on a day. `kind` is stable for code and
    reports; `label` is what a reader of the book would call it."""
    kind: str
    label: str
    strict: bool


CHEESEFARE_WEEK = WeddingBan("cheesefare_week", "сырная седмица", True)
GREAT_LENT = WeddingBan("great_lent", "Великий пост", True)
BRIGHT_WEEK = WeddingBan("bright_week", "Светлая седмица", True)
APOSTLES_FAST = WeddingBan("apostles_fast", "Петров пост", True)
DORMITION_FAST = WeddingBan("dormition_fast", "Успенский пост", True)
NATIVITY_FAST = WeddingBan("nativity_fast", "Рождественский пост", True)
SVYATKI = WeddingBan("svyatki", "Святки", True)
BEHEADING = WeddingBan("one_day_fast", "Усекновение главы Иоанна Предтечи (пост)", True)
EXALTATION = WeddingBan("one_day_fast", "Воздвижение (пост)", True)

MEATFARE_SUNDAY = WeddingBan("meatfare_sunday", "мясопустное воскресенье", False)
FEAST_EVE = WeddingBan("feast_eve", "канун великого праздника", False)
FAST_DAY_EVE = WeddingBan("fast_day_eve", "канун постного дня (вторник, четверг)", False)
SUNDAY_EVE = WeddingBan("sunday_eve", "канун воскресенья (суббота)", False)

#: Eves of the fixed двунадесятые and великие праздники, and of the two
#: one-day fasts. Those inside a fast or Святки are listed anyway: the strict
#: ban wins, and the list stays the calendar's rather than a residue.
_FIXED_EVES = frozenset({
    (1, 5),    # Богоявление
    (2, 1),    # Сретение
    (3, 24),   # Благовещение
    (8, 5),    # Преображение
    (8, 14),   # Успение
    (8, 28),   # Усекновение главы
    (9, 7),    # Рождество Богородицы
    (9, 13),   # Воздвижение
    (11, 20),  # Введение
    (12, 24),  # Рождество Христово
})

#: Offsets from Pascha of the movable eves not already inside a fast or on a
#: Saturday: P+38, the eve of the Ascension (P+39). P−8, the eve of Вход
#: Господень, is in Lent, and P+48, the eve of Троица, is a Saturday.
_MOVABLE_EVES = frozenset({38})


def wedding_ban(year: int, month: int, day: int) -> WeddingBan | None:
    """Why no wedding was performed on this Julian date, or None.

    A strict period wins over an eve or a weekday, and within each tier the
    order below decides the label — so the answer never depends on how two
    overlapping reasons happen to be iterated.
    """
    n = jdn(year, month, day)
    since_pascha = n - jdn(year, *pascha(year))
    md = (month, day)

    if -55 <= since_pascha <= -49:
        return CHEESEFARE_WEEK
    if -48 <= since_pascha <= -1:
        return GREAT_LENT
    if 0 <= since_pascha <= 6:
        return BRIGHT_WEEK
    # From the Monday after All Saints to the eve of Петров день. With the
    # Julian Pascha no later than 25 April the fast is never empty — at its
    # shortest it runs 21–28 June.
    if since_pascha >= 57 and md <= (6, 28):
        return APOSTLES_FAST
    if (8, 1) <= md <= (8, 14):
        return DORMITION_FAST
    if (11, 15) <= md <= (12, 24):
        return NATIVITY_FAST
    if md >= (12, 25) or md <= (1, 6):
        return SVYATKI
    if md == (8, 29):
        return BEHEADING
    if md == (9, 14):
        return EXALTATION

    if since_pascha == -56:
        return MEATFARE_SUNDAY
    if md in _FIXED_EVES or since_pascha in _MOVABLE_EVES:
        return FEAST_EVE
    wd = weekday(year, month, day)
    if wd in (TUESDAY, THURSDAY):
        return FAST_DAY_EVE
    if wd == SATURDAY:
        return SUNDAY_EVE
    return None
