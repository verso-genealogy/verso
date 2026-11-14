"""Marital-status (семейное положение) constants for census members and WWI
external-source records.

`marital_status=` on `wwi_record()` / census `member()` is free-text rendered as
«Семейное положение: …». These constants pin the canonical Russian terms (and the
MST001 linter rejects an unknown literal), so the vocabulary stays consistent and
typo-free across the corpus. Plain `str` values — usable anywhere a string is
expected, exactly like `verso.ru.domain.causes_of_death`.
"""

MARRIED = "женат"            # женатый мужчина
MARRIED_FEMALE = "замужем"   # замужняя женщина
SINGLE = "холост"            # холостой мужчина
SINGLE_FEMALE = "девица"     # незамужняя женщина
WIDOWER = "вдовец"           # вдовый мужчина
WIDOW = "вдова"              # вдовая женщина
DIVORCED = "разведён"        # разведённый мужчина
DIVORCED_FEMALE = "разведена"  # разведённая женщина

# All canonical values — the MST001 linter validates string literals against this.
MARITAL_STATUSES = frozenset({
    MARRIED, MARRIED_FEMALE, SINGLE, SINGLE_FEMALE,
    WIDOWER, WIDOW, DIVORCED, DIVORCED_FEMALE,
})
