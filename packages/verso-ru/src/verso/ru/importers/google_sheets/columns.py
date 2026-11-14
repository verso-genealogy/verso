"""Spreadsheet column-index constants and shared lookup tables."""



HEADER_ROWS = 2


MONTH_ENUM = {
    1: "Month.JANUARY", 2: "Month.FEBRUARY", 3: "Month.MARCH",
    4: "Month.APRIL", 5: "Month.MAY", 6: "Month.JUNE",
    7: "Month.JULY", 8: "Month.AUGUST", 9: "Month.SEPTEMBER",
    10: "Month.OCTOBER", 11: "Month.NOVEMBER", 12: "Month.DECEMBER",
}


GENDER_MAP = {
    "муж": "Gender.MALE",
    "жен": "Gender.FEMALE",
    "м": "Gender.MALE",
    "ж": "Gender.FEMALE",
    "мужской": "Gender.MALE",
    "женский": "Gender.FEMALE",
}


RELATIONSHIP_VALUES = {
    "отец", "мать", "муж", "жена", "сын", "дочь",
    "свекор", "свекровь", "зять", "сноха",
}


RELATIONSHIP_MAP = {
    "отец": "Relationship.FATHER",
    "мать": "Relationship.MOTHER",
    "муж": "Relationship.HUSBAND",
    "супруг": "Relationship.HUSBAND",
    "жена": "Relationship.WIFE",
    "сын": "Relationship.SON",
    "дочь": "Relationship.DAUGHTER",
    "свекор": "Relationship.FATHER_IN_LAW",
    "свекровь": "Relationship.MOTHER_IN_LAW",
    "зять": "Relationship.SON_IN_LAW",
    "сноха": "Relationship.DAUGHTER_IN_LAW",
}


# Status/title words that may precede a witness name in the comment column
# (used in early records where witnesses were not in dedicated columns)
WITNESS_STATUS_WORDS = frozenset([
    "дьячок", "диакон", "дьякон", "дьяк", "иерей", "протоиерей",
    "священник", "пономарь", "крестьянин",
])


# Ecclesiastical/professional titles that may appear in a name field instead of
# an actual person name (e.g. "дьячок" with the real name in the patronymic slot)
_TITLE_WORDS = frozenset([
    "дьячок", "диакон", "дьякон", "дьяк", "иерей", "протоиерей",
    "священник", "пономарь", "псаломщик",
])


DEFAULT_SHEET_NAMES = {
    "births": "рождение",
    "marriages": "брак",
    "deaths": "смерть",
}


# Birth column indices (0-based)
B_ARCHIVE, B_FUND, B_INVENTORY, B_CASE = 1, 2, 3, 4

B_PAGE = 5

B_VILLAGE = 6

B_CHURCH = 8

B_RECORD_NUM = 10

B_GENDER = 11

B_B_DAY, B_B_MONTH, B_B_YEAR = 12, 13, 14

B_K_DAY, B_K_MONTH = 15, 16

B_CHILD_NAME = 18

B_CHILD_NAME_CANON = 19  # canonical "Имя" col (fallback when "Имя орф." is empty in early records)

B_FATHER_RESIDENCE = 20

B_FATHER_STATUS, B_FATHER_LAST_NAME = 22, 23

B_FATHER_NAME, B_FATHER_PATR = 25, 26

B_FATHER_NAME_CANON, B_FATHER_PATR_CANON = 27, 28  # canonical fallbacks

B_MOTHER_STATUS, B_MOTHER_LAST_NAME = 29, 30

B_MOTHER_NAME, B_MOTHER_PATR = 31, 32

B_MOTHER_NAME_CANON, B_MOTHER_PATR_CANON = 33, 34  # canonical fallbacks

B_GP1_STATUS = 35

B_GP1_RESIDENCE = 36

B_GP1_NAME, B_GP1_PATR = 38, 39

B_GP1_FIO = 42  # canonical FIO fallback for godparent 1

B_GP2_STATUS = 43

B_GP2_RESIDENCE = 44

B_GP2_NAME, B_GP2_PATR = 46, 47

B_GP2_FIO = 50  # canonical FIO fallback for godparent 2

B_PRIEST_FIO = 72

B_DEACON_FIO = 76

B_DYACHOK_FIO = 78

B_COMMENT = 79

B_ORIG_NAMES = 80


# Marriage column indices (0-based)
M_ARCHIVE, M_FUND, M_INVENTORY, M_CASE = 1, 2, 3, 4

M_PAGE = 5

M_VILLAGE = 6

M_CHURCH = 8

M_RECORD_NUM = 10

M_W_DAY, M_W_MONTH = 11, 12

M_GROOM_RESIDENCE = 14

M_GROOM_STATUS, M_GROOM_LAST_NAME = 16, 17

M_GROOM_NAME, M_GROOM_PATR = 19, 20

M_GROOM_NAME_CANON, M_GROOM_PATR_CANON = 21, 22  # canonical fallbacks

M_GROOM_MARRIAGE_NUM = 23

M_GROOM_AGE = 24  # Familio export column "Жених: Лет"

M_BRIDE_RESIDENCE = 35

M_BRIDE_STATUS, M_BRIDE_LAST_NAME = 37, 38

M_BRIDE_NAME, M_BRIDE_PATR = 39, 40

M_BRIDE_NAME_CANON, M_BRIDE_PATR_CANON = 41, 42  # canonical fallbacks

M_BRIDE_MARRIAGE_NUM = 43

M_BRIDE_AGE = 44  # Familio export column "Невеста: Лет"

M_W1_STATUS, M_W1_NAME, M_W1_PATR = 55, 59, 60

M_W1_RESIDENCE = 56

M_W1_LAST_NAME = 58

M_W1_NAME_CANON, M_W1_PATR_CANON, M_W1_FIO = 61, 62, 63  # canonical fallbacks

M_W2_STATUS, M_W2_NAME, M_W2_PATR = 64, 68, 69

M_W2_RESIDENCE = 65

M_W2_LAST_NAME = 67

M_W2_NAME_CANON, M_W2_PATR_CANON, M_W2_FIO = 70, 71, 72  # canonical fallbacks

M_W3_STATUS, M_W3_NAME, M_W3_PATR = 73, None, None  # witness3 only has FIO

M_W3_FIO = 76

M_W4_STATUS, M_W4_FIO = 77, 80

M_PRIEST_FIO = 102

M_DEACON_FIO = 106

M_DYACHOK_FIO = 108

M_COMMENT = 109

M_ORIG_NAMES = 110


# Death column indices (0-based)
D_ARCHIVE, D_FUND, D_INVENTORY, D_CASE = 1, 2, 3, 4

D_PAGE = 5

D_VILLAGE = 6

D_CHURCH = 8

D_RECORD_NUM = 10

D_GENDER = 11

D_D_DAY, D_D_MONTH = 12, 13

D_B_DAY, D_B_MONTH = 15, 16

D_DEC_RESIDENCE = 18

D_DEC_STATUS, D_DEC_LAST_NAME = 20, 21

D_DEC_NAME, D_DEC_PATR = 23, 24

D_DEC_NAME_CANON, D_DEC_PATR_CANON = 25, 26  # canonical fallbacks

D_AGE = 27

D_RELATIONSHIP = 31

D_REL_RESIDENCE = 32

D_REL_STATUS, D_REL_LAST_NAME = 34, 35

D_REL_NAME, D_REL_PATR = 37, 38

D_REL_NAME_CANON, D_REL_PATR_CANON = 39, 40  # canonical fallbacks

D_CAUSE = 41

D_W1_NAME, D_W1_PATR = 42, 43

D_W1_NAME_CANON, D_W1_PATR_CANON = 44, 45  # canonical fallbacks

D_W2_NAME, D_W2_PATR = 46, 47

D_W2_NAME_CANON, D_W2_PATR_CANON = 48, 49  # canonical fallbacks

D_PRIEST_FIO = 55

D_DEACON_FIO = 59

D_DYACHOK_FIO = 61

D_COMMENT = 63

D_ORIG_NAMES = 64
