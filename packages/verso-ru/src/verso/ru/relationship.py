from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from verso.ru.gender import Gender
from verso.core.written import captures_written

if TYPE_CHECKING:
    from verso.ru.domain import Person


class Relationship(StrEnum):
    """Kinship of a named relative to the person a record is about.

    Used by death, marriage AND birth records alike — not death-only, as this
    docstring claimed while the enum still lived in the death-records module.
    `Relative.relationship_ref` names which party the relative attaches to: the
    deceased by default, otherwise e.g. "невеста" (marriages, the bride's
    father) or "восприемница" (births, the godmother's husband). Birth and
    marriage records need it stated precisely because they name several people
    a relative could hang off; a death record has only the one.

    Census and divorce records do not use it.
    """
    FATHER = "отец"  # father
    MOTHER = "мать"  # mother
    HUSBAND = "муж"  # husband
    WIFE = "жена"  # wife
    SON = "сын"  # son
    DAUGHTER = "дочь"  # daughter
    FATHER_IN_LAW = "свекор"  # father-in-law
    MOTHER_IN_LAW = "свекровь"  # mother-in-law
    SON_IN_LAW = "зять"  # son-in-law
    DAUGHTER_IN_LAW = "сноха"  # daughter-in-law
    FOSTER_FATHER = "приемный отец" # foster father
    FOSTER_MOTHER = "приемная мать" # foster mother
    STEP_MOTHER = "мачеха" # stepmother
    STEP_FATHER = "отчим" # stepfather


def gender_from_relationship(relationship: Relationship) -> Gender | None:
    if relationship in (Relationship.FATHER, Relationship.HUSBAND, Relationship.SON,
                        Relationship.FATHER_IN_LAW, Relationship.SON_IN_LAW):
        return Gender.MALE
    if relationship in (Relationship.MOTHER, Relationship.WIFE, Relationship.DAUGHTER,
                        Relationship.MOTHER_IN_LAW, Relationship.DAUGHTER_IN_LAW):
        return Gender.FEMALE
    return None


class Relative:
    # `relationship` is None where a burial names a relative without saying
    # what they are to the deceased: `relative(person(…), None)`.
    def __init__(self, person: Person, relationship: Relationship | None,
                 relationship_ref: str | None = None):
        self.person = person
        self.relationship = relationship
        self.relationship_ref = relationship_ref


@captures_written
def relative(person: Person, relationship: Relationship | None,
             relationship_ref: str | None = None) -> Relative:
    return Relative(person, relationship, relationship_ref)
