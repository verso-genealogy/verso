"""Which catalog constant a soldier's free-text `status=` means.

`classify` reads a status the catalog does not spell and names the constant it stands for
(«запасный рядовой» → SOLDIER), so a codemod can rewrite it and MIL001 can flag it. It answers
`None` for a catalog text, for a text that is not military, and for a military text it will not
place (`unplaced` lists them): a maiden's wording other than «солдатская девица» (`UNPLACED`), and a
woman's or a kinsman's wording whose role word does not lead («запасного рядового жена», «мать
солдатка», «крестьянин, сын запасного рядового»), which must never fall through to a man's constant —
nor must a rank in the genitive with no role before it («невеста запасного рядового»): it is someone
else's rank.

The words are read in lower case, but a capitalised word after the first is a name or a place
(«крестьянин деревни Солдатовки», «сын крестьянина Запасова») and is dropped before matching, even
one spelled like a rank («деревни Запасной»). «отставной» and «отпуск» are no military words
on their own («отставной учитель», «отпускной крестьянин»): they only tell a soldier retired.

A status that also names an estate (a landlord, «из однодворцев»: `estates.names_estate`) is left as
written — the owner's ruling of 2026-11-27: a constant would drop the estate the corpus's estate checks
read — so it is neither placed nor unplaced.

The owner's ruling of 2026-11-26 placed the wordings once left out: «солдатская девица» → SOLDIER_GIRL,
«вахмистр …» → UNTER_OFFICER, «кантонист» → SOLDIER_SON, «военный писарь …» → SOLDIER (a «писарь» with
no «военный» is a civil clerk).
"""

import re

from verso.ru.domain import statuses
from verso.ru.domain.estates import names_estate
from verso.ru.domain.orthography import modern_spelling

# Officers, civil ranks, clerks and clergy are not soldiers (an «унтер-офицер» is one);
# nor is a landlord's peasant — unless «солдат» is said.
_NOT_SOLDIER = re.compile(  # i18n: content — status words: vocabulary
    r"поручик|капитан|полковник|прапорщик|майор|(?<!военный )(?<!военного )писар|лесничий|ротмистр|корнет|генерал|есаул|хорунж|сотник"  # i18n: content — status words: vocabulary
    r"|(?<!унтер-)(?<!унтер )офицер|регистратор|секретар|советник|асессор|канцеляр|копиист|чиновник|фельдшер"  # i18n: content — status words: vocabulary
    r"|лекар|врач|доктор|инженер|урядник|казак"  # i18n: content — status words: vocabulary
    r"|дьяч|пономар|священ|диакон|причетн")  # i18n: content — status words: vocabulary
_LANDLORD = re.compile(r"помещи|дворов")  # i18n: content — status words: vocabulary
_SOLDIER_WORD = re.compile(r"солдат")  # i18n: content — status words: vocabulary
# Military wordings the catalog has no constant for: a maiden's, but a soldier's maiden (SOLDIER_GIRL).
UNPLACED = re.compile(r"(?<!солдатская )девиц")  # i18n: content — status words: vocabulary
# «служб» alone is civil too: only the military service counts. A regiment's word starts a word, and
# «улан» is the noun or «уланский»: inside a name or a place (Туланов, Кулановка, Заполковье) it is no soldier.
_MILITARY = re.compile(  # i18n: content — status words: vocabulary
    r"солдат|рядов|запас|бессрочн|билетн|военн|(?:действительн|действующ)\w* служб|нижн\w* чин"  # i18n: content — status words: vocabulary
    r"|\b(?:гусар|гренадер|полк)|\bулан(?:\b|ск)"  # i18n: content — status words: vocabulary
    r"|ефрейтор|фельдфебел|бомбардир|канонир|унтер|вахмистр|сержант|кантонист|отданн")  # i18n: content — status words: vocabulary
# A vakhmistr is the cavalry's unter-officer.
_UNTER = re.compile(r"унтер|вахмистр")  # i18n: content — status words: vocabulary
# A cantonist is a soldier's son, bound to the service from birth — when the word leads («рядовой из
# кантонистов» is a soldier).
_CANTONIST = re.compile(r"кантонист")  # i18n: content — status words: vocabulary
_RETIRED = re.compile(r"отставн|уволен\w*\b.*\bс военной службы")  # i18n: content — status words: vocabulary

# A woman's or a child's wording: the leading noun, or the adjective «солдатская/унтер-офицерская»
# before it (the role stays whatever the husband's or father's rank).
_ADJ = r"(?:(?:солдатск|унтер[- ]?офицерск)\w* )"  # i18n: content — status words: vocabulary
_ROLES = (
    (re.compile(rf"{_ADJ}?вдова\b"), "SOLDIER_WIDOW"),  # i18n: content — status words: vocabulary
    (re.compile(r"законная жена солдата\b"), "SOLDIER_LEGAL_WIFE"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатская девка\b"), "SOLDIER_GIRL"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатская девица\b"), "SOLDIER_GIRL"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатская женка\b"), "SOLDIER_ZHONKA"),  # i18n: content — status words: vocabulary
    (re.compile(rf"{_ADJ}?жена\b"), "SOLDIER_SPOUSE"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатка\b"), "SOLDIER_WIFE"),  # i18n: content — status words: vocabulary
    (re.compile(rf"{_ADJ}?сын\b"), "SOLDIER_SON"),  # i18n: content — status words: vocabulary
    (re.compile(rf"{_ADJ}?дочь\b"), "SOLDIER_DAUGHTER"),  # i18n: content — status words: vocabulary
)
# The adjective with a noun no constant spells («солдатская внучка»): not a man, not placed.
_ADJ_ODD = re.compile(rf"{_ADJ}\w+")  # i18n: content — status words: vocabulary
# A woman's or a kinsman's word anywhere: when no role above led, the wording is not the man's own.
_KIN = re.compile(  # i18n: content — status words: vocabulary
    r"(?<![а-яё])(?:жен(?!ат)|вдов|солдатк|доч|сын|девиц|девк|внук|внучк|мат(?:ь|ер)|сестр|брат|тещ|сирот"  # i18n: content — status words: vocabulary
    r"|муж|от(?:ец|ц)|крестьянк|мещанк|однодворк)|офицерш")  # i18n: content — status words: vocabulary
# A wording that ends on a feminine adjective («солдатская», «военная»): a woman's, unnamed.
_FEMININE_END = re.compile(r"\w(?:ая|яя)$")  # i18n: content — status words: vocabulary
# A rank in the genitive singular, when no role leads, is someone else's rank: a dependant's, a woman's or a
# servant's wording («невеста запасного рядового», «дворовый человек отставного солдата»).
_GENITIVE_RANK = re.compile(  # i18n: content — status words: vocabulary
    r"(?<![а-яё])(?:солдата|солдатки|рядового|унтер[- ]?офицера|чина|вахмистра|ефрейтора|фельдфебеля"  # i18n: content — status words: vocabulary
    r"|кантониста|бомбардира)(?![а-яё])")  # i18n: content — status words: vocabulary
# A name or a place: a capitalised word (not all capitals) after the first — always, even one spelled
# like a rank («деревни Запасной», «крестьянина Солдата»): a missed rewrite, never a wrong constant.
_PROPER = re.compile(r"\W*[А-ЯЁ][а-яё]")  # i18n: content — status words: vocabulary


def _in_catalog(modern: str) -> bool:
    return modern in {str(v) for v in statuses.catalog().values()}


def _words(modern: str) -> str:
    """`modern` in lower case, the names and places in it (a capitalised word after the first) dropped."""
    head, *rest = modern.split() or [""]
    return " ".join([head, *(w for w in rest if not _PROPER.match(w))]).lower()


def _verdict(text: str) -> tuple[str | None, bool]:
    """(the constant's NAME, or None; whether the text is a soldier's wording left unplaced)."""
    modern = modern_spelling(text)
    if _in_catalog(modern):
        return None, False
    if names_estate(modern):
        return None, False
    low = _words(modern)
    if _NOT_SOLDIER.search(low) or (_LANDLORD.search(low) and not _SOLDIER_WORD.search(low)):
        return None, False
    if not _MILITARY.search(low):
        return None, False
    if UNPLACED.search(low):
        return None, True
    for pattern, constant in _ROLES:
        if pattern.match(low):
            return constant, False
    if _ADJ_ODD.match(low) or _KIN.search(low) or _FEMININE_END.search(low) or _GENITIVE_RANK.search(low):
        return None, True
    if _CANTONIST.match(low):
        return "SOLDIER_SON", False
    if _UNTER.search(low):
        return "UNTER_OFFICER", False
    return ("RETIRED_SOLDIER" if _RETIRED.search(low) else "SOLDIER"), False


def classify(text: str) -> str | None:
    """The catalog constant's NAME a soldier's status means, or None (see the module's words)."""
    return _verdict(text)[0]


def unplaced(text: str) -> bool:
    """A soldier's wording `classify` will not place — a maiden's other than «солдатская девица»
    (`UNPLACED`), the adjective with a noun no constant spells («солдатская внучка»), a woman's or a
    kinsman's wording whose role word does not lead («запасного рядового жена»), a rank in the genitive
    with no role before it, a dependant's or a servant's («невеста запасного рядового», «дворовый
    человек отставного солдата») — listed for a person to decide, never guessed. An officer's, a
    clerk's or a peasant's maiden is no soldier's."""
    return _verdict(text)[1]
