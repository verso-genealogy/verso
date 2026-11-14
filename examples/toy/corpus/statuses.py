"""The toy corpus's landlord's statuses: the DSL imports them (`from corpus.statuses import …`)."""
from verso.ru.dsl import Gender, Status

# In definition order: the order is the catalog's.
__all__ = [  # noqa: RUF022
    "ROSTANEV_EI_PEASANT_MALE",
    "ROSTANEV_EI_PEASANT_FEMALE",
    "ROSTANEV_EI_PEASANT_SON",
    "ROSTANEV_EI_PEASANT_DAUGHTER",
]

ROSTANEV_EI_PEASANT_MALE = Status("крестьянин помещика Егора Ильича Ростанева", Gender.MALE)
ROSTANEV_EI_PEASANT_FEMALE = Status("крестьянка помещика Егора Ильича Ростанева", Gender.FEMALE)
ROSTANEV_EI_PEASANT_SON = Status("крестьянский сын помещика Егора Ильича Ростанева", Gender.MALE)
ROSTANEV_EI_PEASANT_DAUGHTER = Status("крестьянская дочь помещика Егора Ильича Ростанева", Gender.FEMALE)
