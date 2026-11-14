"""синтетический корпус тестов — ни одной записи настоящего: the landlords' statuses of the tests' corpus.

Each names an invented owner (Маниловы, Собакевичи — Собакевичево and Горюхино; Ноздрев, Головлевы —
Глуповы Горы). The DSL imports them from here (`from corpus.statuses import …`); the library reads them
through the workspace (`verso.ru.domain.statuses.catalog()`), in this order, before LANDLORD. An estate
that derives a child derives both: a son's form beside a daughter's (`child_status_for`).
"""
from verso.ru.dsl import Gender, Status

# In definition order, not sorted: the order is the catalog's.
__all__ = [  # noqa: RUF022
    "MANILOV_PS_PEASANT_MALE",
    "MANILOV_PS_PEASANT_FEMALE",
    "MANILOV_OV_PEASANT_MALE",
    "MANILOV_OV_PEASANT_FEMALE",
    "MANILOV_OVS_PEASANT_MALE",
    "MANILOV_PS_PEASANT_SON",
    "MANILOV_KF_PEASANT_MALE",
    "MANILOV_KF_PEASANT_FEMALE",
    "MANILOV_KF_PEASANT_SON",
    "MANILOV_KF_PEASANT_DAUGHTER",
    "MANILOV_LK_PEASANT_MALE",
    "MANILOV_LK_PEASANT_SON",
    "MANILOV_LK_PEASANT_DAUGHTER",
    "MANILOV_LK_SOLDIER_WIFE",
    "MANILOV_DN_PEASANT_SON",
    "MANILOV_DN_PEASANT_DAUGHTER",
    "MANILOV_SP_PEASANT_DAUGHTER",
    "MANILOV_SP_DVOROVY",
    "MANILOV_SP_DVOROVY_SON",
    "MANILOV_SP_DVOROVY_DAUGHTER",
    "MANILOV_SP_LEGAL_WIFE",
    "MANILOV_KF_LEGAL_WIFE",
    "MANILOV_PS_PEASANT_DAUGHTER",
    "MANILOV_SP_PEASANT_SON",
    "SOBAKEVICH_ZP_PEASANT_MALE",
    "SOBAKEVICH_ZP_COL_PEASANT_MALE",
    "SOBAKEVICH_TL_PEASANT_MALE",
    "SOBAKEVICH_TL_PEASANT_SON",
    "SOBAKEVICH_TL_PEASANT_DAUGHTER",
    "SOBAKEVICH_TL_PEASANT_MAIDEN",
    "SOBAKEVICH_UK_PEASANT_MALE",
    "SOBAKEVICH_UK_PEASANT_SON",
    "SOBAKEVICH_UK_PEASANT_DAUGHTER",
    "SOBAKEVICH_ZP_PEASANT_SON",
    "SOBAKEVICH_ZP_PEASANT_DAUGHTER",
    "NOZDREV_PEASANT",
    "NOZDREV_PEASANT_FEMALE",
    "NOZDREV_PEASANT_WIFE",
    "NOZDREV_PEASANT_SON",
    "NOZDREV_PEASANT_DAUGHTER",
    "GOLOVLEV_PEASANT",
    "GOLOVLEV_PEASANT_FEMALE",
    "GOLOVLEV_PEASANT_WIFE",
    "GOLOVLEV_PEASANT_LEGAL_WIFE",
    "GOLOVLEV_PEASANT_SON",
    "GOLOVLEV_PEASANT_DAUGHTER",
    "GOLOVLEV_PEASANT_SPOUSE",
    "GOLOVLEV_PEASANT_DAUGHTER_GIRL",
    "GOLOVLEV_ZEMSKOY",
    "GOLOVLEV_ZEMSKOY_WIFE",
    "GOLOVLEV_CHILDREN_ZEMSKOY",
    "GOLOVLEV_CHILDREN_ZEMSKOY_WIFE",
    "GOLOVLEV_STEWARD",
]

MANILOV_PS_PEASANT_MALE = Status("крестьянин помещика Прохора Савельевича Манилова", Gender.MALE)
MANILOV_PS_PEASANT_FEMALE = Status("крестьянка помещика Прохора Савельевича Манилова", Gender.FEMALE)
MANILOV_OV_PEASANT_MALE = Status("крестьянин помещицы Ольги Власьевны Маниловой", Gender.MALE)
MANILOV_OV_PEASANT_FEMALE = Status("крестьянка помещицы Ольги Власьевны Маниловой", Gender.FEMALE)
MANILOV_OVS_PEASANT_MALE = Status("крестьянин помещицы Ольги Власовны Маниловой", Gender.MALE)
MANILOV_PS_PEASANT_SON = Status("крестьянский сын помещика Прохора Савельевича Манилова", Gender.MALE)
MANILOV_KF_PEASANT_MALE = Status("крестьянин помещика Кузьмы Филипповича Манилова", Gender.MALE)
MANILOV_KF_PEASANT_FEMALE = Status("крестьянка помещика Кузьмы Филипповича Манилова", Gender.FEMALE)
MANILOV_KF_PEASANT_SON = Status("крестьянский сын помещика Кузьмы Филипповича Манилова", Gender.MALE)
MANILOV_KF_PEASANT_DAUGHTER = Status("крестьянская дочь помещика Кузьмы Филипповича Манилова", Gender.FEMALE)
MANILOV_LK_PEASANT_MALE = Status("крестьянин помещицы Лукерьи Кузьминичны Маниловой", Gender.MALE)
MANILOV_LK_PEASANT_SON = Status("крестьянский сын помещицы Лукерьи Кузьминичны Маниловой", Gender.MALE)
MANILOV_LK_PEASANT_DAUGHTER = Status("крестьянская дочь помещицы Лукерьи Кузьминичны Маниловой", Gender.FEMALE)
MANILOV_LK_SOLDIER_WIFE = Status("солдатская жена из крестьян помещицы Лукерьи Кузьминичны Маниловой", Gender.FEMALE)
MANILOV_DN_PEASANT_SON = Status("крестьянский сын помещика Демьяна Назаровича Манилова", Gender.MALE)
MANILOV_DN_PEASANT_DAUGHTER = Status("крестьянская дочь помещика Демьяна Назаровича Манилова", Gender.FEMALE)
MANILOV_SP_PEASANT_DAUGHTER = Status("крестьянская дочь помещика Саввы Пантелеевича Манилова", Gender.FEMALE)
MANILOV_SP_DVOROVY = Status("дворовый человек помещика Саввы Пантелеевича Манилова", Gender.MALE)
MANILOV_SP_DVOROVY_SON = Status("сын дворового человека помещика Саввы Пантелеевича Манилова", Gender.MALE)
MANILOV_SP_DVOROVY_DAUGHTER = Status("дочь дворового человека помещика Саввы Пантелеевича Манилова", Gender.FEMALE)
MANILOV_SP_LEGAL_WIFE = Status("законная жена крестьянина помещика Саввы Пантелеевича Манилова", Gender.FEMALE)
MANILOV_KF_LEGAL_WIFE = Status("законная жена крестьянина помещика Кузьмы Филипповича Манилова", Gender.FEMALE)
MANILOV_PS_PEASANT_DAUGHTER = Status("крестьянская дочь помещика Прохора Савельевича Манилова", Gender.FEMALE)
MANILOV_SP_PEASANT_SON = Status("крестьянский сын помещика Саввы Пантелеевича Манилова", Gender.MALE)
SOBAKEVICH_ZP_PEASANT_MALE = Status("крестьянин помещика Захара Порфирьевича Собакевича", Gender.MALE)
SOBAKEVICH_ZP_COL_PEASANT_MALE = Status("крестьянин полковника Захара Порфирьевича Собакевича", Gender.MALE)
SOBAKEVICH_TL_PEASANT_MALE = Status("крестьянин помещика Трифона Лукича Собакевича", Gender.MALE)
SOBAKEVICH_TL_PEASANT_SON = Status("крестьянский сын помещика Трифона Лукича Собакевича", Gender.MALE)
SOBAKEVICH_TL_PEASANT_DAUGHTER = Status("крестьянская дочь помещика Трифона Лукича Собакевича", Gender.FEMALE)
SOBAKEVICH_TL_PEASANT_MAIDEN = Status("девица из крестьян помещика Трифона Лукича Собакевича", Gender.FEMALE)
SOBAKEVICH_UK_PEASANT_MALE = Status("крестьянин помещицы Ульяны Корнеевны Собакевич", Gender.MALE)
SOBAKEVICH_UK_PEASANT_SON = Status("крестьянский сын помещицы Ульяны Корнеевны Собакевич", Gender.MALE)
SOBAKEVICH_UK_PEASANT_DAUGHTER = Status("крестьянская дочь помещицы Ульяны Корнеевны Собакевич", Gender.FEMALE)
SOBAKEVICH_ZP_PEASANT_SON = Status("крестьянский сын помещика Захара Порфирьевича Собакевича", Gender.MALE)
SOBAKEVICH_ZP_PEASANT_DAUGHTER = Status("крестьянская дочь помещика Захара Порфирьевича Собакевича", Gender.FEMALE)
NOZDREV_PEASANT = Status("крестьянин вотчины г-на Ноздрева", Gender.MALE)
NOZDREV_PEASANT_FEMALE = Status("крестьянка вотчины г-на Ноздрева", Gender.FEMALE)
NOZDREV_PEASANT_WIFE = Status("жена крестьянина вотчины г-на Ноздрева", Gender.FEMALE)
NOZDREV_PEASANT_SON = Status("крестьянский сын вотчины г-на Ноздрева", Gender.MALE)
NOZDREV_PEASANT_DAUGHTER = Status("крестьянская дочь вотчины г-на Ноздрева", Gender.FEMALE)
GOLOVLEV_PEASANT = Status("крестьянин вотчины гг. Головлевых", Gender.MALE)
GOLOVLEV_PEASANT_FEMALE = Status("крестьянка вотчины гг. Головлевых", Gender.FEMALE)
GOLOVLEV_PEASANT_WIFE = Status("жена крестьянина вотчины гг. Головлевых", Gender.FEMALE)
GOLOVLEV_PEASANT_LEGAL_WIFE = Status("законная жена крестьянина вотчины гг. Головлевых", Gender.FEMALE)
GOLOVLEV_PEASANT_SON = Status("крестьянский сын вотчины гг. Головлевых", Gender.MALE)
GOLOVLEV_PEASANT_DAUGHTER = Status("крестьянская дочь вотчины гг. Головлевых", Gender.FEMALE)
GOLOVLEV_PEASANT_SPOUSE = Status("крестьянская жена вотчины гг. Головлевых", Gender.FEMALE)
GOLOVLEV_PEASANT_DAUGHTER_GIRL = Status("крестьянская дочь девка вотчины гг. Головлевых", Gender.FEMALE)
GOLOVLEV_ZEMSKOY = Status("земской вотчины гг. Головлевых", Gender.MALE)
GOLOVLEV_ZEMSKOY_WIFE = Status("жена земского вотчины гг. Головлевых", Gender.FEMALE)
GOLOVLEV_CHILDREN_ZEMSKOY = Status("земской вотчины детей гг. Головлевых", Gender.MALE)
GOLOVLEV_CHILDREN_ZEMSKOY_WIFE = Status("жена земского вотчины детей гг. Головлевых", Gender.FEMALE)
GOLOVLEV_STEWARD = Status("приказчик вотчины гг. Головлевых", Gender.MALE)

# Estates the catalog spells under several bases, for `child_status_for`: the полковник is the
# помещик; a земской of the Головлевы's estate (or of their children's) is its peasant.
CHILD_ESTATE_ALIASES: dict[str, str] = {
    "SOBAKEVICH_ZP_COL_PEASANT": "SOBAKEVICH_ZP_PEASANT",
    "GOLOVLEV_ZEMSKOY": "GOLOVLEV_PEASANT",
    "GOLOVLEV_CHILDREN_ZEMSKOY": "GOLOVLEV_PEASANT",
}

# The corpus's part of `parent_status.ESTATE_ALIASES` (PSA): one Головлевы estate under each wording.
ESTATE_ALIASES: dict[str, str] = {
    "SOBAKEVICH_ZP_COL_PEASANT": "SOBAKEVICH_ZP_PEASANT",
    **{base: "GOLOVLEV_PEASANT" for base in ("GOLOVLEV_ZEMSKOY", "GOLOVLEV_CHILDREN_ZEMSKOY", "GOLOVLEV_STEWARD")},
}
