"""The rules of a name's forms: the patronymics it gives, modern and short (old), and its genitive.

Pure, and blind to the lexicon: a rule answers by the ending of the string it is given, nothing else. The
lexicon holds the exceptions, as the cells of its `FormsEntry`s. Each caller keeps one convention, written
out in each: a cell that is set answers; an empty one (None or "") leaves the answer to the rule here —
`derive_patronymic` asks `modern_patronymic`, `genitive_given_name` asks `genitive`. `canonicalize_patronymic`
reaches `modern_from_old` only at its tail, after the lexicon's short and full readings have missed and a
patronymic it does not know has been refused (or let through by the ignore list). `derive_old_patronymic`
asks `old_patronymic` after its reverse lookup.

What no ending decides is not a rule but a row of the lexicon's forms: a fleeting vowel (Лев → Львович,
Павел → Павла), «-ий» softening in some names and not in others (Василий → Васильевич beside Анатолий →
Анатолиевич), the four «-инична» names (Илья, Кузьма, Лука, Фома), a patronymic of another name's
(Георгий → Егорович).

A rule is never asked of an empty string or of an illegible one («?»): its callers answer those.
"""
from __future__ import annotations

from verso.ru.gender import Gender

# After a hushing or velar consonant, a first-declension «-а» takes «-и», not «-ы» (the Russian spelling
# rule): Микишка → Микишки, but Марфа → Марфы.
_HUSHING_VELAR = frozenset("жшчщкгхц")
_VOWELS = frozenset("аеёиоуыэюя")
# A module's own name is read faster than an enum's member: `modern_patronymic` is asked some 10⁵
# times a village.
_MALE = Gender.MALE


def modern_patronymic(father: str, child: Gender | None) -> str:
    """The modern patronymic a father's given name gives a son (`Gender.MALE`) or a daughter (any other):

      * a hard consonant takes «-ович/-овна» (Иван → Иванович), the name's own ё kept (Семён → Семёнович);
      * «-й» and «-ь» take «-евич/-евна» (Андрей → Андреевич, Игорь → Игоревич, Авель → Авелевич);
      * «-ия» takes «-иевич/-иевна» (Азария → Азариевич);
      * «-ила/-йла» drop the «-а» for «-ович/-овна» (Гаврила → Гаврилович, Самойла → Самойлович):
        the folk «-а» of a name whose own stem ends in the consonant (Гавриил, Самуил, Шумило). A name of the
        svyatcy whose «-а» is its own (Акила, Вавила, Сила) is a row of the lexicon's forms, «-илич»;
      * any other «-а/-я» takes «-ич/-ична» (Никита → Никитич, Илья → Ильич).
    """
    if not father:
        return ""
    male = child is _MALE
    last = father[-1]
    if last in "ая":
        if father.endswith(("ила", "йла")):
            return father[:-1] + ("ович" if male else "овна")
        if father.endswith("ия"):
            return father[:-1] + ("евич" if male else "евна")
        return father[:-1] + ("ич" if male else "ична")
    if last in "йь":
        return father[:-1] + ("евич" if male else "евна")
    return father + ("ович" if male else "овна")


def old_patronymic(father: str, child: Gender | None) -> str:
    """The short (old) patronymic a father's given name gives a son, by its ending — «-ин» after «-а/-я»
    (Никита → Никитин, Илья → Ильин; «-ия» drops its «и»: Осия → Осин), «-ев» after «-й/-ь» (Андрей →
    Андреев, Игорь → Игорев), «-ов» after anything else (Иван → Иванов) — and a daughter the son's
    form with «-а» (Иванова)."""
    if not father:
        return ""
    last = father[-1]
    if last in "ая":
        son = (father[:-2] if father.endswith("ия") else father[:-1]) + "ин"
    elif last in "йь":
        son = father[:-1] + "ев"
    else:
        son = father + "ов"
    return son if child is _MALE else son + "а"


def genitive(name: str, sex: Gender | None) -> str:
    """The genitive of a given name by its ending. `sex` decides «-ь», a man's is second declension
    (Игорь → Игоря, and so without a sex), a woman's third (Любовь → Любови); and a hard consonant: a
    woman's name ending in one does not decline (Эстер → Эстер, Астрид → Астрид). A vowel the rule has no
    declension for is left as it is (Василько)."""
    if not name:
        return ""
    last = name[-1]
    if last == "а":
        stem = name[:-1]
        return stem + ("и" if stem and stem[-1] in _HUSHING_VELAR else "ы")
    if last == "я":
        return name[:-1] + "и"
    if last == "й":
        return name[:-1] + "я"
    if last == "ь":
        return name[:-1] + ("и" if sex is Gender.FEMALE else "я")
    if last in _VOWELS or sex is Gender.FEMALE:
        return name
    return name + "а"


def modern_from_old(old: str) -> str | None:
    """The modern patronymic of a short (old) one, where its ending says it: «-ов/-ев» → «-ович/-евич»,
    «-ова/-ева» → «-овна/-евна». None for anything else — «-ин» among them (Кузьмин → Кузьмич, Ильин →
    Ильич, Фомина → Фоминична), which only the lexicon knows."""
    if old.endswith(("ов", "ев")):
        return old + "ич"
    if old.endswith(("ова", "ева")):
        return old[:-1] + "на"
    return None
