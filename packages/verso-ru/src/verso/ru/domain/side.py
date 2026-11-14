from enum import StrEnum


class Side(StrEnum):
    """Whom a wedding's поручитель stood surety for.

    Часть 2 of a metric book lists the sureties in two groups, «по женихѣ» and
    «по невѣстѣ». The slot a witness sits in (`witness1..6`) is part of their
    res_name on Geni and is never renumbered, so the side is declared on the
    person instead: `witness3=person("Василій", …, side=Side.BRIDE)`. A witness
    without `side=` is one whose side the record does not say.
    """
    GROOM = 'по жениху'  # i18n: content — the side words the DSL's facade writes
    BRIDE = 'по невесте'  # i18n: content — the side words the DSL's facade writes
