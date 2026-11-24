"""How a report names a record by its number: «№7», or «без номера» for an entry its book left unnumbered.

The extractors write such an entry's `record_num` as "none" (`verso.ru.facts.extract.common.Slot`); every report
that names a record by its number asks here, so none prints «№none».
"""
from __future__ import annotations

from verso.ru.facts.model import Citation
from verso.ru.messages import t

#: The `record_num` of an entry its book left unnumbered.
UNNUMBERED = "none"


def record_number(cite: Citation, *, sign: bool = True) -> str:
    """«№7» («7» without the `sign`, where the line says «рек.» before it), or «без номера»."""
    if cite.record_num == UNNUMBERED:
        return str(t("cli.facts.unnumbered"))
    return ("№" if sign else "") + cite.record_num
