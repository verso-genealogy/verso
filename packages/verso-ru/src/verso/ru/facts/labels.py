"""How a report names a record by its number: «№7», or «без номера» for an entry its book left unnumbered.

The extractors write such an entry's `record_num` as "none" (`verso.ru.facts.extract.common`); every report that
names a record by its number asks `Citation.number`, here or on the citation, so none prints «№none».
"""
from __future__ import annotations

from verso.ru.facts.model import UNNUMBERED, Citation

__all__ = ["UNNUMBERED", "record_number"]


def record_number(cite: Citation, *, sign: bool = True) -> str:
    """«№7» («7» without the `sign`, where the line says «рек.» before it), or «без номера»."""
    return cite.number(sign=sign)
