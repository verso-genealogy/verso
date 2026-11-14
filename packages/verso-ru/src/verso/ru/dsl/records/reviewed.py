"""What `reviewed=False` means, once for every record type, and who may pass.

**`reviewed=False` is the only review flag**: the record was read from the scan
and not yet checked back against it. It is written at three levels and
resolved innermost-first:

    birth_records(..., reviewed=False)       # the file, `bool` (True)
      └ page("341об", ..., reviewed=False)   # a whole лист, `bool | None`
          └ birth(12, ..., reviewed=True)    # one record, `bool | None`

`page()` fills a record's flag only where the record left it `None`, and the
record set fills whatever is still `None` from its own default. Every record
type that `page()` wraps defaults to `None`, so a лист can be held whole — until
2026-10-03 births, marriages and deaths defaulted to `True`, and a
`page(reviewed=False)` around them was silently a no-op.

**An unreviewed record does not reach Geni — unless it already had.** Records
uploaded while that no-op stood (Глуповы Горы's лист markers) stay, and are
listed per village in `unreviewed_on_geni.tsv`, the ratchet
(`verso.core.ratchet`). The loader marks a listed record `on_geni` when its
fingerprint is unchanged; a new unreviewed record, or a listed one edited
without being reviewed, is not listed and is held. The list only shrinks.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def admitted(record: Any) -> bool:
    """Whether a record reaches Geni and the facts layer: reviewed, or
    unreviewed but on the ratchet's list (`on_geni`, set by the loader).

    Only an explicit `False` is unreviewed. `None` is «not stated» — the record
    set's default is `True` — so a record read without its record set around it
    (the facts extractors, the sweep, a test) is not held for want of one.
    """
    if getattr(record, "reviewed", None) is not False:
        return True
    return bool(getattr(record, "on_geni", False))


def resolve_reviewed(records: Iterable[Any], default: bool) -> None:
    """Fill every record's unstated `reviewed` from the record set's default."""
    for record in records:
        if record.reviewed is None:
            record.reviewed = default
