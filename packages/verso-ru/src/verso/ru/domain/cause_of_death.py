from __future__ import annotations


class CauseOfDeath(str):
    """A cause-of-death string constant.
    Subclasses str so it can be used anywhere a plain string is expected."""

    def __new__(cls, value: str) -> CauseOfDeath:
        return super().__new__(cls, value)


# Sentinel: source document didn't specify a cause of death. Marking a
# Death with `cause_of_death=NOT_IN_DOCUMENT` suppresses the
# `RecordDefaults.cause_of_death` fallback for that record.
NOT_IN_DOCUMENT = CauseOfDeath("")
