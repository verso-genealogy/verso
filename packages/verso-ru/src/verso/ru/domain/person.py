from __future__ import annotations

from verso.ru.domain.side import Side
from verso.ru.domain.status import Status
from verso.ru.gender import Gender
from verso.ru.naming import (
    canonicalize_name, canonicalize_patronymic, get_gender_from_name, get_gender_from_old_patronymic, modernize_orthography, validate_first_name, validate_old_patronymic)


def _coded(error: ValueError, code: str) -> ValueError:
    """`error` with what it is (`verso_code`), for a reader that does not read its text — Verso
    answering a name held only in the other sex (`verso.core.pipeline.load.import_problem`)."""
    error.verso_code = code  # pyright: ignore[reportAttributeAccessIssue]
    return error


class Person:
    def __init__(self,
                 name_orig: str | None = None,
                 patr_orig: str | None = None,
                 last_name: str | None = None,
                 name_modern_orth: str | None = None,
                 patr_old: str | None = None,
                 last_name_modern_orth: str | None = None,
                 residence: str | None = None,
                 status: Status | str | None = None,
                 gender: Gender | None = None,
                 comment: str | None = None,
                 last_name_in_book: bool = True,
                 birth_last_name_modern_orth: str | None = None,
                 occupation: str | None = None,
                 side: Side | None = None):

        self.name_orig = name_orig
        self.name_modern = name_modern_orth
        if self.name_modern is None:
            self.name_modern = modernize_orthography(name_orig)
        if not validate_first_name(self.name_modern):
            raise ValueError(f"Unrecognized first name '{self.name_modern}' (original: '{name_orig}')")

        self.patr_orig = patr_orig
        self.patr_old = patr_old
        if self.patr_old is None:
            self.patr_old = modernize_orthography(patr_orig)
        # accept_full: hand-authored DSL may carry a verbatim full «-вич» form
        # (gwar WWI cards, noble records); the importer keeps the strict default.
        if not validate_old_patronymic(self.patr_old, accept_full=True):
            raise ValueError(f"Unrecognized patronymic '{self.patr_old}' (original: '{patr_orig}')")

        self.patr_modern = canonicalize_patronymic(self.patr_old)

        self.last_name = last_name
        self.last_name_modern = last_name_modern_orth
        if self.last_name_modern is None and last_name is not None:
            self.last_name_modern = modernize_orthography(last_name)
        # Geni's `maiden_name` (девичья фамилия). Two ways it gets set:
        #  1. Explicitly via the `birth_last_name_modern_orth` arg — used for
        #     adult women (mothers, godmothers, brides) whose maiden surname is
        #     known (recovered from Geni or deduced from a named father/brother)
        #     but absent from the record's ФИО column. Lets the per-record
        #     source DSL carry the canonical maiden surname instead of pinning
        #     it in the consolidation override layer.
        #  2. By `Birth.__init__` for female children whose surname was
        #     inherited from a parent rather than recorded in the book — routes
        #     to `maiden_name` instead of `last_name` so unmarried girls don't
        #     end up with a "current" surname.
        # Stored in modern orthography (the only form Geni renders for the
        # maiden field); `modernize_orthography` is idempotent on modern input.
        self.birth_last_name_modern: str | None = (
            modernize_orthography(birth_last_name_modern_orth)
            if birth_last_name_modern_orth is not None
            else None
        )

        # Flag: True means the surname was literally recorded in the
        # book's ФИО (e.g. "Мижуев Иван Егорович"); False means it's
        # known (from a separate Фамилия column or deduced) but NOT in
        # the book's ФИО. Affects document-text rendering only — profile
        # identity (res_name, names block) keeps the surname either way
        # so cross-record consolidation still fires.
        self.last_name_in_book = last_name_in_book

        self.residence = residence
        self.status = status
        # True when `status` was filled in place from the book's
        # `RecordDefaults` rather than passed for this person. Nothing in the
        # translator reads it: it is the breadcrumb the facts layer needs to
        # say it cannot tell a status the scribe wrote from one the author
        # hoisted into the book's defaults (`Stated(basis_unknown=True)`).
        self.status_defaulted = False

        self.gender = gender
        if self.gender is None and self.name_modern:
            self.gender = get_gender_from_name(self.name_modern)
        if self.gender is None and self.patr_old:
            self.gender = get_gender_from_old_patronymic(self.patr_old)
        # Status-based fallback: a typed Status carries .gender directly;
        # a plain string status looks up the gender by value in the
        # Status registry (populated when statuses.py is imported).
        # Used for hidden census ancestors where role=None and the name
        # alone is ambiguous (e.g. "Пичкинза", "Бурмяй", "Ждан").
        if self.gender is None:
            self.gender = self.gender_from_status()

        # Verify gender is consistent with name if possible
        if self.gender and self.name_modern:
            detected_gender = get_gender_from_name(self.name_modern)
            if detected_gender and detected_gender != self.gender:
                raise _coded(ValueError(
                    f"Gender mismatch for name '{self.name_modern}': detected {detected_gender}, but got {self.gender}"),
                    "gender.name")

        if self.gender and self.patr_old:
            detected_gender = get_gender_from_old_patronymic(self.patr_old)
            if detected_gender and detected_gender != self.gender:
                raise _coded(ValueError(
                    f"Gender mismatch for patronymic '{self.patr_old}': detected {detected_gender}, but got {self.gender}"),
                    "gender.patronymic")

        if isinstance(self.status, Status) and self.status.gender is not None:
            if self.gender is not None and self.gender != self.status.gender:
                raise _coded(ValueError(
                    f"Status '{self.status}' implies gender {self.status.gender!r} "
                    f"but person '{self.name_orig}' has gender {self.gender!r}"), "gender.status")

        self.comment = comment
        # Род занятий / occupation — a free-text trade or profession
        # (e.g. «хлебопашец»). Flows to the structured `geni_profile.occupation`
        # attribute via `_profile_from_person`'s getattr fallback. Reusable
        # across record types; WWI cards carry it as «занятие перед войной».
        self.occupation = occupation
        # Whom a wedding's поручитель stood surety for (`Side`). Meaningful only
        # in `marriage(witness1..6=)` — WSD001 refuses it anywhere else. Nothing
        # in the translator reads it: the facts layer and the Familio справочник
        # export do.
        self.side = side

    def gender_from_status(self) -> Gender | None:
        """The gender implied by this person's status, if any.

        Last resort of the gender cascade, for people whose name and patronymic
        cannot resolve it — the single-named archaic hidden census ancestors where the
        role is None or HEAD (e.g. «Пичкинза», «Бурмяй», «Ждан»).

        Exposed as a method rather than inlined in __init__ because
        `RecordDefaults.apply_to_person` assigns `status` AFTER construction:
        without re-running this, hoisting a repeated status into defaults
        silently dropped those people's gender.
        """
        if self.status is None:
            return None
        if isinstance(self.status, Status) and self.status.gender is not None:
            return self.status.gender
        # A plain-string status (Status is a str subclass, so no isinstance
        # needed): the catalog's constant spelled so.
        return Status.gender_of(self.status)

    def get_canonical_name(self) -> str | None:
        return canonicalize_name(self.name_modern, self.gender)

    def get_fio(self) -> str:
        """
        Returns full name using canonical forms.
        Includes surname if present: 'Surname Name Patronymic'
        Otherwise returns: 'Name Patronymic'

        Returns:
            str: "Болтунов Василий Иванович" or "Иван Петрович" or "Иван"
        """
        parts = [self.last_name_modern, self.get_canonical_name(), self.patr_modern]
        return " ".join(filter(None, parts))
