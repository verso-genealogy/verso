from enum import StrEnum


class Gender(StrEnum):
    MALE = 'муж'  # i18n: content — the sources' word (the DSL's facade, the CSVs' «Пол»)
    FEMALE = 'жен'  # i18n: content — the sources' word
