"""Which catalog constant a soldier's free-text `status=` means.

`classify` reads a status the catalog does not spell and names the constant it stands for
(«запасный рядовой» → SOLDIER), so a codemod can rewrite it and MIL001 can flag it. It answers
`None` for a catalog text, for a text that is not military, and for a military text it will not
place (`UNPLACED`: a maiden, a cantonist, a vakhmistr — the catalog has no constant for them).
"""

import re

from verso.ru.domain import statuses
from verso.ru.domain.orthography import modern_spelling

# Officers, clerks and clergy are not soldiers; nor is a landlord's peasant — unless «солдат» is said.
_NOT_SOLDIER = re.compile(r"поручик|капитан|полковник|прапорщик|майор|писар|лесничий"  # i18n: content — status words: vocabulary
                          r"|дьяч|пономар|священ|диакон|причетн")  # i18n: content — status words: vocabulary
_LANDLORD = re.compile(r"помещи|дворов")  # i18n: content — status words: vocabulary
# Military wordings the catalog has no constant for.
UNPLACED = re.compile(r"девиц|кантонист|вахмистр|военный писар")  # i18n: content — status words: vocabulary
_MILITARY = re.compile(r"солдат|рядов|запас|отпуск|бессрочн|билетн|военн|служб|гусар|улан|гренадер|полк"  # i18n: content — status words: vocabulary
                       r"|ефрейтор|фельдфебел|бомбардир|канонир|унтер|сержант|отставн|отданн")  # i18n: content — status words: vocabulary
_RETIRED = re.compile(r"отставн|уволен\w*\b.*\bс военной службы")  # i18n: content — status words: vocabulary

# The role, by the leading words (first match wins): the woman's and the child's wordings.
_ROLES = (
    (re.compile(r"вдова"), "SOLDIER_WIDOW"),  # i18n: content — status words: vocabulary
    (re.compile(r"жена"), "SOLDIER_SPOUSE"),  # i18n: content — status words: vocabulary
    (re.compile(r"солдатка"), "SOLDIER_WIFE"),  # i18n: content — status words: vocabulary
    (re.compile(r"сын"), "SOLDIER_SON"),  # i18n: content — status words: vocabulary
    (re.compile(r"дочь"), "SOLDIER_DAUGHTER"),  # i18n: content — status words: vocabulary
)


def classify(text: str) -> str | None:
    """The catalog constant's NAME a soldier's status means, or None (see the module's words)."""
    modern = modern_spelling(text)
    if modern in {str(v) for v in statuses.catalog().values()}:
        return None
    low = modern.lower()
    if _NOT_SOLDIER.search(low) or (_LANDLORD.search(low) and "солдат" not in low):
        return None
    if UNPLACED.search(low) or not _MILITARY.search(low):
        return None
    for pattern, constant in _ROLES:
        if pattern.match(low):
            return constant
    if re.search(r"(?:солдатская|унтер-?офицерская) жена", low):  # i18n: content — status words: vocabulary
        return "SOLDIER_SPOUSE"
    if "унтер" in low:
        return "UNTER_OFFICER"
    return "RETIRED_SOLDIER" if _RETIRED.search(low) else "SOLDIER"
