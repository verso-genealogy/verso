"""The сословие a record's status wording puts a person in — «estate» here.

A status is kept verbatim wherever it is read (`verso.ru.facts` asserts it as
`Titled`); what it IMPLIES is this classification, shared by every reader that
asks: `estate-conflicts` (two estates held by one canonical), PSA (a parent's
estate against the newborn's), and the facts check behind the former.

What is deliberately one estate:

* **ясачный → казённый.** Горюхино's population was reclassified from ясачные
  to казённые крестьяне in 1841.
* **экономический ↔ государственный.** Экономические крестьяне were the
  secularised church peasants, folded into the state peasantry long before our
  books; Заманиловка's scribes write both for the same people in no fixed order.

Role and marital descriptors (солдатка, девица, вдова, отрок, …) name no estate
and classify as None; a serf status names its owner, and one owner under two
spellings is one estate (`[owner_aliases]` of the corpus's estates.toml).
"""
from __future__ import annotations

import re

from verso.ru import corpus_data

#: Owner phrase in a serf status: «крестьянин помещика Ивана Васильевича
#: Пеночкина», «девка из крестьян помещицы Лукерьи Кузьминичны Маниловой»,
#: «законная жена крестьянина помещика X». Everything after помещик/помещицы is
#: the owner; the role prefix in front of it is deliberately discarded.
_LANDLORD = re.compile(r"помещи(?:ка|цы|к|ца)\s+(?P<owner>.+?)\s*$")

#: Estate families keyed by a distinctive substring. Order matters: the first
#: match wins, so the landlord test runs before the generic peasant tests
#: (a serf status also contains «крестьянин»).
_ESTATE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # ясачные and казённые are ONE estate: Горюхино was reclassified in 1841.
    # So are экономические and государственные — see the module docstring.
    ("state", ("ясачн", "казенн", "казённ", "государственн", "экономическ")),
    ("odnodvorets", ("однодвор",)),
    ("meshchanin", ("мещан",)),
    ("clergy", ("священник", "дьячок", "дьячих", "пономар", "диакон", "иере",
                "попадь", "протоиере", "причетник")),
    ("budny", ("будн",)),
    ("dvorovy", ("дворов",)),
    ("merchant", ("купец", "купчих")),
)

def estate_of(status: str | None) -> str | None:
    """The estate axis of `status`, or None when it carries no estate.

    A serf status yields `landlord:<owner>`; a state/economic/clergy/… status
    yields that family's key. Role-only and marital statuses yield None.
    """
    if not status:
        return None
    text = " ".join(str(status).split())
    low = text.lower()
    if (m := _LANDLORD.search(text)):
        owner = " ".join(m.group("owner").split())
        return f"landlord:{corpus_data.estates().owner_aliases.get(owner, owner)}"
    for key, markers in _ESTATE_MARKERS:
        if any(mk in low for mk in markers):
            return key
    # Bare «крестьянин»/«крестьянка» names no estate at all.
    return None


def family_root(surname: str) -> str:
    """Gender-insensitive stem of a gentry surname.

    A status names the owner in the genitive, so one family shows up as
    «…Манилова» (masculine) and «…Маниловой» (feminine). Stripping the feminine
    «ой» and the masculine «а» lands both on the same stem. Longer suffixes must
    be tested first, or «Маниловой» loses «а»-less and never matches.
    """
    low = surname.lower()
    for suffix in ("ой", "а"):
        if low.endswith(suffix) and len(low) > len(suffix) + 2:
            return low[: -len(suffix)]
    return low
