"""Which parameter each argument of a DSL call binds to, and how the page writes a new one.

The DSL's description — its functions, their parameters, the constants a field takes —
is `verso.ru.dsl.describe` (L1); this module hands its names on to the edit primitives
(`verso.ru.dsl.source`, the adapter's bookdefaults — L6, the library's since 0.1.0) and keeps
the two tables that are the page's own way of writing a call.
"""
from __future__ import annotations

from verso.ru.dsl.describe import (
    CONTAINER_FUNCS, KIND, KNOWN_FUNCS, PARAM_CATALOG, RECORD_FUNCS, VITAL_FUNCS, Constant, Param, Signature, catalogs, constant_by_code, signature)

__all__ = ["CONTAINER_FUNCS", "IMPORT_OF", "KIND", "KNOWN_FUNCS", "PARAM_CATALOG", "RECORD_FUNCS", "VITAL_FUNCS",
           "WRITTEN_POSITIONALLY", "Constant", "Param", "Signature", "catalogs", "constant_by_code", "signature"]

# Where a function the page may write a call to is imported from, when the
# file does not import it yet: `person` every DSL file already does.
IMPORT_OF = {"relative": "verso.ru.dsl", "RecordDefaults": "verso.ru.dsl"}
# How many leading parameters a new call writes in place: a member's number,
# person and role; `ref_member=` and the rest by name, as the corpus writes them.
WRITTEN_POSITIONALLY = {"member": 3}
