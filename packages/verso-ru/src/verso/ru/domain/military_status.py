"""Which catalog constant a soldier's free-text `status=` means.

`classify` reads a status the catalog does not spell and names the constant it stands for
(«запасный рядовой» → SOLDIER), so a codemod can rewrite it and MIL001 can flag it. It answers
`None` for a catalog text, for a text that is not military, and for a military text it will not
place (`UNPLACED`: a maiden's wording other than «солдатская девица»; `unplaced` lists them).

The owner's ruling of 2026-11-26 placed the wordings once left out: «солдатская девица» → SOLDIER_GIRL,
«вахмистр …» → UNTER_OFFICER, «кантонист» → SOLDIER_SON, «военный писарь …» → SOLDIER (a «писарь» with
no «военный» is a civil clerk).
"""

import re

from verso.ru.domain import statuses
from verso.ru.domain.orthography import modern_spelling

# Officers, civil ranks, clerks and clergy are not soldiers (an «унтер-офицер» is one);
# nor is a landlord's peasant — unless «солдат» is said.
_NOT_SOLDIER = re.compile(  # i18n: content — status words: vocabulary
    r"поручик|капитан|полковник|прапорщик|майор|(?<!военный )(?<!военного )писар|лесничий|ротмистр|корнет|генерал|есаул|хорунж|сотник"  # i18n: content — status words: vocabulary
    r"|(?<!унтер-)(?<!унтер )офицер|регистратор|секретар|советник|асессор|канцеляр|копиист|чиновник|фельдшер"  # i18n: content — status words: vocabulary
    r"|дьяч|пономар|священ|диакон|причетн")  # i18n: content — status words: vocabulary
_LANDLORD = re.compile(r"помещи|дворов")  # i18n: content — status words: vocabulary
_SOLDIER_WORD = re.compile(r"солдат")  # i18n: content — status words: vocabulary
# Military wordings the catalog has no constant for: a maiden's, but a soldier's maiden (SOLDIER_GIRL).
UNPLACED = re.compile(r"(?<!солдатская )девиц")  # i18n: content — status words: vocabulary
# «служб» alone is civil too: only the military service counts. A regiment's word starts a word, and
# «улан» is the noun or «уланский»: inside a name or a place (Туланов, Кулановка, Заполковье) it is no soldier.
_MILITARY = re.compile(  # i18n: content — status words: vocabulary
    r"солдат|рядов|запас|отпуск|бессрочн|билетн|военн|(?:действительн|действующ)\w* служб"  # i18n: content — status words: vocabulary
    r"|\b(?:гусар|гренадер|полк)|\bулан(?:\b|ск)"  # i18n: content — status words: vocabulary
    r"|ефрейтор|фельдфебел|бомбардир|канонир|унтер|вахмистр|сержант|кантонист|отставн|отданн")  # i18n: content — status words: vocabulary
# A vakhmistr is the cavalry's unter-officer.
_UNTER = re.compile(r"унтер|вахмистр")  # i18n: content — status words: vocabulary
# A cantonist is a soldier's son, bound to the service from birth.
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


def _in_catalog(modern: str) -> bool:
    return modern in {str(v) for v in statuses.catalog().values()}


def classify(text: str) -> str | None:
    """The catalog constant's NAME a soldier's status means, or None (see the module's words)."""
    modern = modern_spelling(text)
    if _in_catalog(modern):
        return None
    low = modern.lower()
    if _NOT_SOLDIER.search(low) or (_LANDLORD.search(low) and not _SOLDIER_WORD.search(low)):
        return None
    if UNPLACED.search(low) or not _MILITARY.search(low):
        return None
    for pattern, constant in _ROLES:
        if pattern.match(low):
            return constant
    if _ADJ_ODD.match(low):
        return None
    if _CANTONIST.search(low):
        return "SOLDIER_SON"
    if _UNTER.search(low):
        return "UNTER_OFFICER"
    return "RETIRED_SOLDIER" if _RETIRED.search(low) else "SOLDIER"


def unplaced(text: str) -> bool:
    """A soldier's wording `classify` will not place — a maiden's other than «солдатская девица»
    (`UNPLACED`), or the adjective with a noun no constant spells («солдатская внучка») — listed for a
    person to decide, never guessed. An officer's, a clerk's or a peasant's maiden is no soldier's."""
    modern = modern_spelling(text)
    low = modern.lower()
    if _in_catalog(modern) or classify(text) is not None:
        return False
    if _NOT_SOLDIER.search(low) or not _MILITARY.search(low):
        return False
    return UNPLACED.search(low) is not None or _ADJ_ODD.match(low) is not None
