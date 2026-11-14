"""DSL v1: the marital statuses a wedding or a burial writes — a catalog of the facade
`verso.ru.dsl`: `from verso.ru.dsl.marital_status import WIDOW` (not the status `WIDOW`)."""

from verso.ru.domain.marital_status import (DIVORCED, DIVORCED_FEMALE, MARRIED, MARRIED_FEMALE,
                                            SINGLE, SINGLE_FEMALE, WIDOW, WIDOWER)

__all__ = [
    "DIVORCED", "DIVORCED_FEMALE", "MARRIED", "MARRIED_FEMALE", "SINGLE", "SINGLE_FEMALE",
    "WIDOW", "WIDOWER",
]
