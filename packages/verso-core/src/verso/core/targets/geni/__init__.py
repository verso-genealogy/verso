"""Geni's terraform models — a profile, a union, an event, a date — and what the target keeps of
the corpus (what is on Geni, the about's sections, the consolidation's conflicts).

The four models are public: a village's consolidation config builds its overrides with them,
`from verso.core.targets.geni import GeniDate, GeniEvent, GeniProfile, GeniUnion`. They import
only the plugin registry and one another, so importing the package is cheap; the translator onto
them is the plugin's (:mod:`verso.ru.targets.geni.translator`), never imported from here.
"""

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.union import GeniUnion

__all__ = ["GeniDate", "GeniEvent", "GeniProfile", "GeniUnion"]
