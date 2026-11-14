from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from verso.ru.domain.cause_of_death import NOT_IN_DOCUMENT
from verso.ru.domain.person import Person
from verso.ru.domain.status import Status
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship

if TYPE_CHECKING:
    from verso.ru.dsl.records.births import Birth
    from verso.ru.dsl.records.deaths import Death
    from verso.ru.dsl.records.marriages import Marriage

# The причт a record names. A cleric lives where his church stands, so one the book
# names with no village takes the PARISH (the record set's village), never the
# book's `residence` default: Маниловка's parishioners live in Маниловка, its priest in
# Хлестаковка. The translator mints the причт no profile, so this reaches what
# a record says (the facts layer, the review page's grey text), not Geni.
CLERGY_SLOTS = ("priest", "deacon", "dyachok", "sexton")


def apply_parish_to_clergy(record: object, parish: str) -> None:
    for slot in CLERGY_SLOTS:
        cleric = getattr(record, slot, None)
        if isinstance(cleric, Person) and cleric.residence is None:
            cleric.residence = parish


def _derive_child_status(child: Person | None, parent: Person | None) -> None:
    """A statusless child's сословие from a parent the book's defaults styled.

    `Birth.__init__` and `Death.__init__` derive it from a status the record
    WRITES; a parent left to the book's default had none yet, so the child fell
    to the ADULT default — «крестьянин», where the household's child is a
    «крестьянский сын». Run once the parents have their defaults and before the
    child gets its own: the derived form, when the parent's estate has one
    (`child_status_for`), wins; out of its scope (clergy, a merchant, a
    дворовый) the adult default stays, as it did. The status rests on the
    book's default, so it is marked defaulted."""
    if child is None or child.status is not None or parent is None or not parent.status:
        return
    # Imported here: verso.ru.domain.statuses imports the verso.ru.domain package, which
    # imports this module first.
    from verso.ru.domain.statuses import child_status_for
    derived = child_status_for(str(parent.status), child.gender)
    if derived is not None:
        child.status = derived
        child.status_defaulted = True


class RecordDefaults:
    # A value, not an entity: `_written` keeps it, the records JSON writes it whole (verso.core.written).
    _record_value: ClassVar[bool] = True

    def __init__(
            self,
            residence: str | None = None,
            status_male: Status | str | None = None,
            status_female: Status | str | None = None,
            status_bride: Status | str | None = None,
            status_groom: Status | str | None = None,
            status_mother: Status | str | None = None,
            cause_of_death: str | None = None,
    ):
        self.residence = residence
        self.status_male = status_male
        self.status_female = status_female
        self.status_bride = status_bride
        self.status_groom = status_groom if status_groom is not None else status_male
        self.status_mother = status_mother
        self.cause_of_death = cause_of_death

    def apply_to_person(self, p: Person | None) -> None:
        """Apply default values to a Person if their fields are empty."""
        if p is None:
            return
        if p.residence is None and self.residence is not None:
            p.residence = self.residence
        if p.status is None:
            if p.gender == Gender.FEMALE and self.status_female is not None:
                p.status = self.status_female
            elif self.status_male is not None:
                p.status = self.status_male
            p.status_defaulted = p.status is not None
            # Person.__init__ ends its gender cascade with a status-based
            # fallback, but we are assigning `status` after construction — so
            # re-run it here. Without this, hoisting a repeated status into
            # defaults silently dropped gender for anyone the name/patronymic/
            # role could not resolve (the single-named archaic hidden ancestors of the
            # early censuses), because at __init__ time status was None.
            if p.gender is None:
                p.gender = p.gender_from_status()

    def apply_to_birth(self, b: Birth | None) -> None:
        """Apply default values to all persons in a Birth record."""
        if b is None:
            return
        self.apply_to_person(b.father)
        if b.mother is not None and b.mother.status is None and self.status_mother is not None:
            b.mother.status = self.status_mother
            b.mother.status_defaulted = True
        self.apply_to_person(b.mother)
        # The parents first: a newborn of parents on the book's default is that
        # household's child («крестьянский сын»), not an adult of the default.
        # The father is consulted when he has a status, as in Birth.__init__.
        _derive_child_status(b.child, b.father if b.father is not None and b.father.status else b.mother)
        self.apply_to_person(b.child)
        self.apply_to_person(b.god_parent1)
        self.apply_to_person(b.god_parent2)
        # god_parent3/4 were long omitted here, so a third or fourth
        # восприемник silently kept an empty residence AND an empty status
        # while gp1/gp2 inherited both. Nothing about the extra slots warrants
        # that: they are the same parishioners. NB Birth.__init__ still gives a
        # slot-implied gender only to gp1 (MALE) and gp2 (FEMALE) — a trio has
        # no reliable slot→gender convention — so gp3/gp4 resolve gender from
        # the name alone, and an unnamed-gender person falls to `status_male`
        # below, same as any witness.
        self.apply_to_person(b.god_parent3)
        self.apply_to_person(b.god_parent4)
        for rel in b.relatives:
            self.apply_to_person(rel.person)

    def apply_to_marriage(self, m: Marriage | None) -> None:
        """Apply default values to all persons in a Marriage record."""
        if m is None:
            return
        if m.groom is not None and m.groom.status is None and self.status_groom is not None:
            m.groom.status = self.status_groom
            m.groom.status_defaulted = True
        self.apply_to_person(m.groom)
        if m.bride is not None and m.bride.status is None and self.status_bride is not None:
            m.bride.status = self.status_bride
            m.bride.status_defaulted = True
        self.apply_to_person(m.bride)
        self.apply_to_person(m.witness1)
        self.apply_to_person(m.witness2)
        self.apply_to_person(m.witness3)
        self.apply_to_person(m.witness4)
        self.apply_to_person(m.witness5)
        self.apply_to_person(m.witness6)
        for rel in m.relatives:
            self.apply_to_person(rel.person)

    def apply_to_death(self, d: Death | None) -> None:
        """Apply default values to all persons in a Death record."""
        if d is None:
            return
        if d.cause_of_death is NOT_IN_DOCUMENT:
            d.cause_of_death = None
        elif d.cause_of_death is None and self.cause_of_death is not None:
            d.cause_of_death = self.cause_of_death
        for rel in d.relatives:
            self.apply_to_person(rel.person)
        # The relatives first: a dead child of a father (else a mother) on the
        # book's default is the household's child, as in Death.__init__ — the
        # first FATHER with a status, else the first MOTHER; a HUSBAND never.
        father, mother = (next((rel.person for rel in d.relatives
                                if rel.person.status and rel.relationship == kin), None)
                          for kin in (Relationship.FATHER, Relationship.MOTHER))
        _derive_child_status(d.deceased, father or mother)
        self.apply_to_person(d.deceased)
        self.apply_to_person(d.witness1)
        self.apply_to_person(d.witness2)
