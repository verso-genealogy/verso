"""Which catalog constant a soldier's free-text `status=` means.

`classify` reads a status the catalog does not spell and names the constant it stands for
(«запасный рядовой» → SOLDIER), so a codemod can rewrite it and MIL001 can flag it. It answers
`None` for a catalog text, for a text that is not military, and for a military text it will not
place (`UNPLACED`: a maiden, a cantonist, a vakhmistr — the catalog has no constant for them).
"""

import re

from verso.ru.domain import statuses
from verso.ru.domain.orthography import modern_spelling

# Officers, civil ranks, clerks and clergy are not soldiers (an «унтер-офицер» is one);
# nor is a landlord's peasant — unless «солдат» is said.
_NOT_SOLDIER = re.compile(  # i18n: content — status words: vocabulary
    r"поручик|капитан|полковник|прапорщик|майор|писар|лесничий|ротмистр|корнет|генерал|есаул|хорунж|сотник"  # i18n: content — status words: vocabulary
    r"|(?<!унтер-)(?<!унтер )офицер|регистратор|секретар|советник|асессор|канцеляр|копиист|чиновник|фельдшер"  # i18n: content — status words: vocabulary
    r"|дьяч|пономар|священ|диакон|причетн")  # i18n: content — status words: vocabulary
_LANDLORD = re.compile(r"помещи|дворов")  # i18n: content — status words: vocabulary
_SOLDIER_WORD = re.compile(r"солдат")  # i18n: content — status words: vocabulary
# Military wordings the catalog has no constant for.
UNPLACED = re.compile(r"девиц|кантонист|вахмистр|военный писар")  # i18n: content — status words: vocabulary
# «служб» alone is civil too: only the military service counts.
_MILITARY = re.compile(  # i18n: content — status words: vocabulary
    r"солдат|рядов|запас|отпуск|бессрочн|билетн|военн|(?:действительн|действующ)\w* служб|гусар|улан|гренадер|полк"  # i18n: content — status words: vocabulary
    r"|ефрейтор|фельдфебел|бомбардир|канонир|унтер|сержант|отставн|отданн")  # i18n: content — status words: vocabulary
_UNTER = re.compile(r"унтер")  # i18n: content — status words: vocabulary
_RETIRED = re.compile(r"отставн|уволен\w*\b.*\bс военной службы")  # i18n: content — status words: vocabulary

# A woman's or a child's wording: the leading noun, or the adjective «солдатская/унтер-офицерская»
# before it (the role stays whatever the husband's or father's rank).
_ADJ = r"(?:(?:солдатск|унтер[- ]?офицерск)\w* )"  # i18n: content — status words: vocabulary
_ROLES = (
    (re.compile(rf"{_ADJ}?вдова\b"), "SOLDIER_WIDOW"),  # i18n: content — status words: vocabulary
    (re.compile(r"законная жена солдата\b"), "SOLDIER_LEGAL_WIFE"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатская девка\b"), "SOLDIER_GIRL"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатская женка\b"), "SOLDIER_ZHONKA"),  # i18n: content — status words: vocabulary
    (re.compile(rf"{_ADJ}?жена\b"), "SOLDIER_SPOUSE"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатка\b"), "SOLDIER_WIFE"),  # i18n: content — status words: vocabulary
    (re.compile(rf"{_ADJ}?сын\b"), "SOLDIER_SON"),  # i18n: content — status words: vocabulary
    (re.compile(rf"{_ADJ}?дочь\b"), "SOLDIER_DAUGHTER"),  # i18n: content — status words: vocabulary
)
# The adjective with a noun no constant spells («солдатская внучка»): not a man, not placed.
_ADJ_ODD = re.compile(rf"{_ADJ}\w+")  # i18n: content — status words: vocabulary


def classify(text: str) -> str | None:
    """The catalog constant's NAME a soldier's status means, or None (see the module's words)."""
    modern = modern_spelling(text)
    if modern in {str(v) for v in statuses.catalog().values()}:
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
    if _UNTER.search(low):
        return "UNTER_OFFICER"
    return "RETIRED_SOLDIER" if _RETIRED.search(low) else "SOLDIER"
