"""Modern spelling of a classification text: the pre-reform letters, endings and honorifics a status is
read without (SOR001 flags them; the soldiers' classifier reads through them)."""

import re

CONSONANTS = "бвгджзклмнпрстфхцчшщБВГДЖЗКЛМНПРСТФХЦЧШЩ"  # i18n: content — the old orthography and status words: vocabulary


# The modern word where the 1918 spelling is not the letter-for-letter one:
# a catalog wording the corpus standardizes on.
_WORDS = {"дьячек": "дьячок"}  # i18n: content — the old orthography and status words: vocabulary


def modern_spelling(text: str) -> str:
    """The text in modern orthography: ѣ→е, і→и, ѳ→ф, ѵ→и, a word-final ъ
    dropped, the adjective ending -аго/-яго → -ого/-его, без-/из-/раз-/
    воз-/низ-/чрез- before a voiceless consonant spelled with с, and an
    abbreviated honorific in lowercase (Г-на → г-на, Г.Г./Гг. → гг.)."""
    s = text
    for old, new in (("ѣ", "е"), ("Ѣ", "Е"), ("і", "и"), ("І", "И"),  # i18n: content — the old orthography and status words: vocabulary
                     ("ѳ", "ф"), ("Ѳ", "Ф"), ("ѵ", "и"), ("Ѵ", "И")):  # i18n: content — the old orthography and status words: vocabulary
        s = s.replace(old, new)
    s = re.sub(rf"(?<=[{CONSONANTS}])ъ(?![а-яёА-ЯЁ])", "", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<=[а-яё])аго\b", "ого", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<=[а-яё])яго\b", "его", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"\b(без|из|раз|воз|низ|чрез)(?=[кпстфхцчшщ])",  # i18n: content — the old orthography and status words: vocabulary
               lambda m: m.group(1)[:-1] + "с", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<![а-яёА-ЯЁ])Г\.\s?Г\.|(?<![а-яёА-ЯЁ])Гг\.", "гг.", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<![а-яёА-ЯЁ])Г-(?=[нж])", "г-", s)  # i18n: content — the old orthography and status words: vocabulary
    s = re.sub(r"(?<=отчины )Г\.(?=\s)", "г.", s)  # i18n: content — the old orthography and status words: vocabulary
    return " ".join(_WORDS.get(w, w) for w in s.split(" "))
