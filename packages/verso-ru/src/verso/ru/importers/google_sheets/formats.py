"""Per-record column dataclasses and spreadsheet format definitions."""
from dataclasses import dataclass
from verso.ru.importers.google_sheets.columns import B_ARCHIVE, B_B_DAY, B_B_MONTH, B_B_YEAR, B_CASE, B_CHILD_NAME, B_CHILD_NAME_CANON, B_CHURCH, B_COMMENT, B_DEACON_FIO, B_DYACHOK_FIO, B_FATHER_LAST_NAME, B_FATHER_NAME, B_FATHER_NAME_CANON, B_FATHER_PATR, B_FATHER_PATR_CANON, B_FATHER_RESIDENCE, B_FATHER_STATUS, B_FUND, B_GENDER, B_GP1_FIO, B_GP1_NAME, B_GP1_PATR, B_GP1_RESIDENCE, B_GP1_STATUS, B_GP2_FIO, B_GP2_NAME, B_GP2_PATR, B_GP2_RESIDENCE, B_GP2_STATUS, B_INVENTORY, B_K_DAY, B_K_MONTH, B_MOTHER_LAST_NAME, B_MOTHER_NAME, B_MOTHER_NAME_CANON, B_MOTHER_PATR, B_MOTHER_PATR_CANON, B_MOTHER_STATUS, B_ORIG_NAMES, B_PAGE, B_PRIEST_FIO, B_RECORD_NUM, B_VILLAGE, D_AGE, D_ARCHIVE, D_B_DAY, D_B_MONTH, D_CASE, D_CAUSE, D_CHURCH, D_COMMENT, D_DEACON_FIO, D_DEC_LAST_NAME, D_DEC_NAME, D_DEC_NAME_CANON, D_DEC_PATR, D_DEC_PATR_CANON, D_DEC_RESIDENCE, D_DEC_STATUS, D_DYACHOK_FIO, D_D_DAY, D_D_MONTH, D_FUND, D_GENDER, D_INVENTORY, D_ORIG_NAMES, D_PAGE, D_PRIEST_FIO, D_RECORD_NUM, D_RELATIONSHIP, D_REL_LAST_NAME, D_REL_NAME, D_REL_NAME_CANON, D_REL_PATR, D_REL_PATR_CANON, D_REL_RESIDENCE, D_REL_STATUS, D_VILLAGE, D_W1_NAME, D_W1_NAME_CANON, D_W1_PATR, D_W1_PATR_CANON, D_W2_NAME, D_W2_NAME_CANON, D_W2_PATR, D_W2_PATR_CANON, M_ARCHIVE, M_BRIDE_AGE, M_BRIDE_LAST_NAME, M_BRIDE_MARRIAGE_NUM, M_BRIDE_NAME, M_BRIDE_NAME_CANON, M_BRIDE_PATR, M_BRIDE_PATR_CANON, M_BRIDE_RESIDENCE, M_BRIDE_STATUS, M_CASE, M_CHURCH, M_COMMENT, M_DEACON_FIO, M_DYACHOK_FIO, M_FUND, M_GROOM_AGE, M_GROOM_LAST_NAME, M_GROOM_MARRIAGE_NUM, M_GROOM_NAME, M_GROOM_NAME_CANON, M_GROOM_PATR, M_GROOM_PATR_CANON, M_GROOM_RESIDENCE, M_GROOM_STATUS, M_INVENTORY, M_ORIG_NAMES, M_PAGE, M_PRIEST_FIO, M_RECORD_NUM, M_VILLAGE, M_W1_FIO, M_W1_LAST_NAME, M_W1_NAME, M_W1_NAME_CANON, M_W1_PATR, M_W1_PATR_CANON, M_W1_RESIDENCE, M_W1_STATUS, M_W2_FIO, M_W2_LAST_NAME, M_W2_NAME, M_W2_NAME_CANON, M_W2_PATR, M_W2_PATR_CANON, M_W2_RESIDENCE, M_W2_STATUS, M_W3_FIO, M_W3_NAME, M_W3_PATR, M_W3_STATUS, M_W4_FIO, M_W4_STATUS, M_W_DAY, M_W_MONTH




# ─── Column configuration dataclasses ────────────────────────────────────────


@dataclass(frozen=True)
class BirthColumns:
    ARCHIVE: int = B_ARCHIVE
    FUND: int = B_FUND
    INVENTORY: int = B_INVENTORY
    CASE: int = B_CASE
    PAGE: int = B_PAGE
    VILLAGE: int = B_VILLAGE
    CHURCH: int = B_CHURCH
    RECORD_NUM: int = B_RECORD_NUM
    GENDER: int = B_GENDER
    B_DAY: int = B_B_DAY
    B_MONTH: int = B_B_MONTH
    B_YEAR: int = B_B_YEAR
    K_DAY: int = B_K_DAY
    K_MONTH: int = B_K_MONTH
    CHILD_NAME: int = B_CHILD_NAME
    CHILD_NAME_CANON: int | None = B_CHILD_NAME_CANON
    FATHER_RESIDENCE: int = B_FATHER_RESIDENCE
    FATHER_STATUS: int = B_FATHER_STATUS
    FATHER_LAST_NAME: int = B_FATHER_LAST_NAME
    FATHER_NAME: int = B_FATHER_NAME
    FATHER_PATR: int = B_FATHER_PATR
    FATHER_NAME_CANON: int | None = B_FATHER_NAME_CANON
    FATHER_PATR_CANON: int | None = B_FATHER_PATR_CANON
    MOTHER_STATUS: int = B_MOTHER_STATUS
    MOTHER_LAST_NAME: int = B_MOTHER_LAST_NAME
    MOTHER_NAME: int = B_MOTHER_NAME
    MOTHER_PATR: int = B_MOTHER_PATR
    MOTHER_NAME_CANON: int | None = B_MOTHER_NAME_CANON
    MOTHER_PATR_CANON: int | None = B_MOTHER_PATR_CANON
    GP1_STATUS: int = B_GP1_STATUS
    GP1_RESIDENCE: int = B_GP1_RESIDENCE
    GP1_LAST_NAME: int | None = None
    GP1_NAME: int | None = B_GP1_NAME
    GP1_PATR: int | None = B_GP1_PATR
    GP1_FIO: int | None = B_GP1_FIO
    GP2_STATUS: int = B_GP2_STATUS
    GP2_RESIDENCE: int = B_GP2_RESIDENCE
    GP2_LAST_NAME: int | None = None
    GP2_NAME: int | None = B_GP2_NAME
    GP2_PATR: int | None = B_GP2_PATR
    GP2_FIO: int | None = B_GP2_FIO
    CHILD_ORIG_NAME: int | None = None
    FATHER_ORIG_NAME: int | None = None
    FATHER_ORIG_PATR: int | None = None
    MOTHER_ORIG_NAME: int | None = None
    MOTHER_ORIG_PATR: int | None = None
    GP1_ORIG_NAME: int | None = None
    GP1_ORIG_PATR: int | None = None
    GP2_ORIG_NAME: int | None = None
    GP2_ORIG_PATR: int | None = None
    PRIEST_FIO: int = B_PRIEST_FIO
    DEACON_FIO: int = B_DEACON_FIO
    DYACHOK_FIO: int = B_DYACHOK_FIO
    COMMENT: int = B_COMMENT
    ORIG_NAMES: int = B_ORIG_NAMES
    # Birth relative columns (godparent relatives)
    REL1_WHOSE: int | None = None
    REL1_RELATIONSHIP: int | None = None
    REL1_STATUS: int | None = None
    REL1_RESIDENCE: int | None = None
    REL1_FIO: int | None = None
    REL1_LAST_NAME: int | None = None
    REL1_NAME: int | None = None
    REL1_PATR: int | None = None
    REL1_NAME_CANON: int | None = None
    REL1_PATR_CANON: int | None = None
    REL2_WHOSE: int | None = None
    REL2_RELATIONSHIP: int | None = None
    REL2_STATUS: int | None = None
    REL2_RESIDENCE: int | None = None
    REL2_FIO: int | None = None



@dataclass(frozen=True)
class MarriageColumns:
    ARCHIVE: int = M_ARCHIVE
    FUND: int = M_FUND
    INVENTORY: int = M_INVENTORY
    CASE: int = M_CASE
    PAGE: int = M_PAGE
    VILLAGE: int = M_VILLAGE
    CHURCH: int = M_CHURCH
    RECORD_NUM: int = M_RECORD_NUM
    W_DAY: int = M_W_DAY
    W_MONTH: int = M_W_MONTH
    GROOM_RESIDENCE: int = M_GROOM_RESIDENCE
    GROOM_STATUS: int = M_GROOM_STATUS
    GROOM_LAST_NAME: int = M_GROOM_LAST_NAME
    GROOM_NAME: int = M_GROOM_NAME
    GROOM_PATR: int = M_GROOM_PATR
    GROOM_NAME_CANON: int | None = M_GROOM_NAME_CANON
    GROOM_PATR_CANON: int | None = M_GROOM_PATR_CANON
    GROOM_ORIG_NAME: int | None = None
    GROOM_ORIG_PATR: int | None = None
    GROOM_MARRIAGE_NUM: int = M_GROOM_MARRIAGE_NUM
    GROOM_AGE: int | None = M_GROOM_AGE
    BRIDE_RESIDENCE: int = M_BRIDE_RESIDENCE
    BRIDE_STATUS: int = M_BRIDE_STATUS
    BRIDE_LAST_NAME: int = M_BRIDE_LAST_NAME
    BRIDE_NAME: int = M_BRIDE_NAME
    BRIDE_PATR: int = M_BRIDE_PATR
    BRIDE_NAME_CANON: int | None = M_BRIDE_NAME_CANON
    BRIDE_PATR_CANON: int | None = M_BRIDE_PATR_CANON
    BRIDE_ORIG_NAME: int | None = None
    BRIDE_ORIG_PATR: int | None = None
    BRIDE_MARRIAGE_NUM: int = M_BRIDE_MARRIAGE_NUM
    BRIDE_AGE: int | None = M_BRIDE_AGE
    W1_STATUS: int | None = M_W1_STATUS
    W1_RESIDENCE: int | None = M_W1_RESIDENCE
    W1_NAME: int | None = M_W1_NAME
    W1_PATR: int | None = M_W1_PATR
    W1_LAST_NAME: int | None = M_W1_LAST_NAME
    W1_NAME_CANON: int | None = M_W1_NAME_CANON
    W1_PATR_CANON: int | None = M_W1_PATR_CANON
    W1_FIO: int | None = M_W1_FIO
    W1_ORIG_NAME: int | None = None
    W1_ORIG_PATR: int | None = None
    W2_STATUS: int | None = M_W2_STATUS
    W2_RESIDENCE: int | None = M_W2_RESIDENCE
    W2_NAME: int | None = M_W2_NAME
    W2_PATR: int | None = M_W2_PATR
    W2_LAST_NAME: int | None = M_W2_LAST_NAME
    W2_NAME_CANON: int | None = M_W2_NAME_CANON
    W2_PATR_CANON: int | None = M_W2_PATR_CANON
    W2_FIO: int | None = M_W2_FIO
    W2_ORIG_NAME: int | None = None
    W2_ORIG_PATR: int | None = None
    W3_STATUS: int | None = M_W3_STATUS
    W3_RESIDENCE: int | None = None
    W3_NAME: int | None = M_W3_NAME
    W3_PATR: int | None = M_W3_PATR
    W3_LAST_NAME: int | None = None
    W3_NAME_CANON: int | None = None
    W3_PATR_CANON: int | None = None
    W3_FIO: int | None = M_W3_FIO
    W3_ORIG_NAME: int | None = None
    W3_ORIG_PATR: int | None = None
    W4_STATUS: int | None = M_W4_STATUS
    W4_RESIDENCE: int | None = None
    W4_NAME: int | None = None
    W4_PATR: int | None = None
    W4_LAST_NAME: int | None = None
    W4_NAME_CANON: int | None = None
    W4_PATR_CANON: int | None = None
    W4_FIO: int | None = M_W4_FIO
    W4_ORIG_NAME: int | None = None
    W4_ORIG_PATR: int | None = None
    PRIEST_FIO: int = M_PRIEST_FIO
    DEACON_FIO: int = M_DEACON_FIO
    DYACHOK_FIO: int = M_DYACHOK_FIO
    COMMENT: int = M_COMMENT
    ORIG_NAMES: int = M_ORIG_NAMES



@dataclass(frozen=True)
class DeathColumns:
    ARCHIVE: int = D_ARCHIVE
    FUND: int = D_FUND
    INVENTORY: int = D_INVENTORY
    CASE: int = D_CASE
    PAGE: int = D_PAGE
    VILLAGE: int = D_VILLAGE
    CHURCH: int = D_CHURCH
    RECORD_NUM: int = D_RECORD_NUM
    GENDER: int = D_GENDER
    D_DAY: int = D_D_DAY
    D_MONTH: int = D_D_MONTH
    B_DAY: int = D_B_DAY
    B_MONTH: int = D_B_MONTH
    DEC_RESIDENCE: int = D_DEC_RESIDENCE
    DEC_STATUS: int = D_DEC_STATUS
    DEC_LAST_NAME: int = D_DEC_LAST_NAME
    DEC_NAME: int = D_DEC_NAME
    DEC_PATR: int = D_DEC_PATR
    DEC_NAME_CANON: int | None = D_DEC_NAME_CANON
    DEC_PATR_CANON: int | None = D_DEC_PATR_CANON
    DEC_ORIG_NAME: int | None = None
    DEC_ORIG_PATR: int | None = None
    AGE: int | None = D_AGE
    AGE_YEARS: int | None = None
    AGE_MONTHS: int | None = None
    AGE_WEEKS: int | None = None
    AGE_DAYS: int | None = None
    RELATIONSHIP: int = D_RELATIONSHIP
    REL_RESIDENCE: int = D_REL_RESIDENCE
    REL_STATUS: int = D_REL_STATUS
    REL_LAST_NAME: int = D_REL_LAST_NAME
    REL_NAME: int = D_REL_NAME
    REL_PATR: int = D_REL_PATR
    REL_NAME_CANON: int | None = D_REL_NAME_CANON
    REL_PATR_CANON: int | None = D_REL_PATR_CANON
    REL_ORIG_NAME: int | None = None
    REL_ORIG_PATR: int | None = None
    CAUSE: int | None = D_CAUSE
    W1_NAME: int | None = D_W1_NAME
    W1_PATR: int | None = D_W1_PATR
    W1_NAME_CANON: int | None = D_W1_NAME_CANON
    W1_PATR_CANON: int | None = D_W1_PATR_CANON
    W2_NAME: int | None = D_W2_NAME
    W2_PATR: int | None = D_W2_PATR
    W2_NAME_CANON: int | None = D_W2_NAME_CANON
    W2_PATR_CANON: int | None = D_W2_PATR_CANON
    PRIEST_FIO: int = D_PRIEST_FIO
    DEACON_FIO: int = D_DEACON_FIO
    DYACHOK_FIO: int = D_DYACHOK_FIO
    COMMENT: int = D_COMMENT
    ORIG_NAMES: int = D_ORIG_NAMES



@dataclass(frozen=True)
class SpreadsheetFormat:
    header_rows: int
    sheet_names: dict[str, str]
    year_cols: dict[str, int]
    birth_cols: BirthColumns
    marriage_cols: MarriageColumns
    death_cols: DeathColumns



FORMAT_FAMILIO_EXTENDED = SpreadsheetFormat(
    header_rows=2,
    sheet_names={"births": "рождение", "marriages": "брак", "deaths": "смерть"},
    year_cols={"births": 14, "marriages": 13, "deaths": 14},
    birth_cols=BirthColumns(),
    marriage_cols=MarriageColumns(),
    death_cols=DeathColumns(),
)


FORMAT_FAMILIO_STANDARD = SpreadsheetFormat(
    header_rows=3,
    sheet_names={"births": "f - 1", "marriages": "f - 2", "deaths": "f - 3"},
    year_cols={"births": 14, "marriages": 13, "deaths": 14},
    birth_cols=BirthColumns(
        CHILD_NAME=18, CHILD_NAME_CANON=None, CHILD_ORIG_NAME=20,
        FATHER_RESIDENCE=21, FATHER_STATUS=23, FATHER_LAST_NAME=24,
        FATHER_NAME=26, FATHER_PATR=27, FATHER_NAME_CANON=None, FATHER_PATR_CANON=None,
        FATHER_ORIG_NAME=30, FATHER_ORIG_PATR=31,
        MOTHER_STATUS=32, MOTHER_LAST_NAME=33, MOTHER_NAME=34, MOTHER_PATR=35,
        MOTHER_NAME_CANON=None, MOTHER_PATR_CANON=None,
        MOTHER_ORIG_NAME=38, MOTHER_ORIG_PATR=39,
        GP1_STATUS=40, GP1_RESIDENCE=41, GP1_LAST_NAME=44,
        GP1_NAME=45, GP1_PATR=46, GP1_FIO=43,
        GP1_ORIG_NAME=47, GP1_ORIG_PATR=48,
        GP2_STATUS=51, GP2_RESIDENCE=52, GP2_LAST_NAME=55,
        GP2_NAME=56, GP2_PATR=57, GP2_FIO=54,
        GP2_ORIG_NAME=58, GP2_ORIG_PATR=59,
        REL1_WHOSE=84, REL1_RELATIONSHIP=85, REL1_STATUS=86, REL1_RESIDENCE=87, REL1_FIO=89,
        REL2_WHOSE=90, REL2_RELATIONSHIP=91, REL2_STATUS=92, REL2_RESIDENCE=93, REL2_FIO=95,
        REL1_LAST_NAME=116, REL1_NAME=117, REL1_PATR=118, REL1_NAME_CANON=119, REL1_PATR_CANON=120,
        PRIEST_FIO=97, DEACON_FIO=101, DYACHOK_FIO=103,
        COMMENT=104, ORIG_NAMES=105,
    ),
    marriage_cols=MarriageColumns(
        GROOM_MARRIAGE_NUM=25,
        GROOM_AGE=None,  # familio-standard: column index unverified, opt out
        GROOM_NAME_CANON=None, GROOM_PATR_CANON=None,
        GROOM_ORIG_NAME=23, GROOM_ORIG_PATR=24,
        BRIDE_RESIDENCE=37, BRIDE_STATUS=39, BRIDE_LAST_NAME=40,
        BRIDE_NAME=41, BRIDE_PATR=42,
        BRIDE_NAME_CANON=None, BRIDE_PATR_CANON=None,
        BRIDE_ORIG_NAME=45, BRIDE_ORIG_PATR=46,
        BRIDE_MARRIAGE_NUM=47,
        BRIDE_AGE=None,  # familio-standard: column index unverified, opt out
        W1_STATUS=61, W1_RESIDENCE=62, W1_LAST_NAME=65,
        W1_NAME=66, W1_PATR=67, W1_NAME_CANON=None, W1_PATR_CANON=None, W1_FIO=64,
        W1_ORIG_NAME=68, W1_ORIG_PATR=69,
        W2_STATUS=70, W2_RESIDENCE=71, W2_LAST_NAME=74,
        W2_NAME=75, W2_PATR=76, W2_NAME_CANON=None, W2_PATR_CANON=None, W2_FIO=73,
        W2_ORIG_NAME=77, W2_ORIG_PATR=78,
        W3_STATUS=79, W3_RESIDENCE=80, W3_LAST_NAME=83,
        W3_NAME=84, W3_PATR=85, W3_NAME_CANON=129, W3_PATR_CANON=130, W3_FIO=82,
        W3_ORIG_NAME=86, W3_ORIG_PATR=87,
        W4_STATUS=88, W4_RESIDENCE=89, W4_LAST_NAME=92,
        W4_NAME=93, W4_PATR=94, W4_NAME_CANON=131, W4_PATR_CANON=132, W4_FIO=91,
        W4_ORIG_NAME=95, W4_ORIG_PATR=96,
        PRIEST_FIO=118, DEACON_FIO=122, DYACHOK_FIO=124,
        COMMENT=125, ORIG_NAMES=126,
    ),
    death_cols=DeathColumns(
        DEC_NAME_CANON=None, DEC_PATR_CANON=None,
        DEC_ORIG_NAME=27, DEC_ORIG_PATR=28,
        AGE=None, AGE_YEARS=29, AGE_MONTHS=30, AGE_WEEKS=31, AGE_DAYS=32,
        RELATIONSHIP=33, REL_RESIDENCE=34,
        REL_STATUS=36, REL_LAST_NAME=37,
        REL_NAME=39, REL_PATR=40,
        REL_NAME_CANON=None, REL_PATR_CANON=None,
        REL_ORIG_NAME=43, REL_ORIG_PATR=44,
        CAUSE=45,
        W1_NAME=None, W1_PATR=None, W1_NAME_CANON=None, W1_PATR_CANON=None,
        W2_NAME=None, W2_PATR=None, W2_NAME_CANON=None, W2_PATR_CANON=None,
        PRIEST_FIO=47, DEACON_FIO=55, DYACHOK_FIO=57,
        COMMENT=59, ORIG_NAMES=60,
    ),
)


FORMATS = {
    "familio-extended": FORMAT_FAMILIO_EXTENDED,
    "familio-standard": FORMAT_FAMILIO_STANDARD,
}
