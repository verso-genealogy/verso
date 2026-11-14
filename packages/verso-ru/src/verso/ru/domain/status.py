from __future__ import annotations

from typing import ClassVar

from verso.ru.gender import Gender


class Status(str):
    """A status string that optionally carries an expected gender.
    Subclasses str so it can be used anywhere a plain string is expected."""
    gender: Gender | None

    # Class-level registry: status text → declared gender. Populated as
    # Status constants are constructed (e.g. when statuses.py is
    # imported; the constants of a corpus's statuses.toml are not). Lets a plain-string `status="ясачный крестьянин"` in
    # the DSL fall back to the gender attached to the matching constant
    # without requiring the DSL author to use the typed Status object.
    _gender_registry: ClassVar[dict[str, Gender]] = {}
    # The same, of the workspace's corpus when its statuses are data (statuses.toml): replaced whole each
    # time the file is read (`statuses.corpus_statuses`), emptied when it may have changed — so a constant the
    # file drops keeps no sex here. Asked before the registry, as the corpus's module, imported after the
    # library's, overwrites the library's entries there.
    _data_genders: ClassVar[dict[str, Gender]] = {}

    def __new__(cls, value: str, gender: Gender | None = None) -> Status:
        instance = super().__new__(cls, value)
        instance.gender = gender
        if gender is not None:
            cls._gender_registry[value] = gender
        return instance

    @classmethod
    def gender_of(cls, text: str) -> Gender | None:
        """The sex of a status written as words — that of the catalog's constant spelled
        so — or None. A constant registers itself as it is made: a DSL file that writes
        only plain strings makes none, and the workspace's corpus makes its own when its
        catalog is first read — so a miss reads the catalog, and asks again. A corpus's
        `statuses.toml` registers in `_data_genders` instead, asked first — its constant wins
        over the library's of the same words, as a corpus's `statuses.py` does — and followed:
        while it holds anything the file's stamp is asked before each answer, so a constant the
        file drops gives no sex once the file has changed. (A DSL file's own constant of those
        words, made after, wins with `statuses.py` and loses here.)"""
        if cls._data_genders:
            from verso.ru.domain import statuses
            statuses.follow()
        found = cls._data_genders.get(text) or cls._gender_registry.get(text)
        if found is None:
            from verso.ru.domain import statuses
            statuses.catalog()
            found = cls._data_genders.get(text) or cls._gender_registry.get(text)
        return found
