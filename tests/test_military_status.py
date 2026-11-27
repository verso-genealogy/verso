"""classify(): a soldier's free-text status → the catalog constant it means."""
import re

import pytest

from verso.ru.domain.military_status import UNPLACED, classify, unplaced


@pytest.mark.parametrize("text, constant", [
    *[(t, "SOLDIER") for t in (
        "запасный солдат", "запасной солдат", "запасно-отпускной солдат", "уволенный в запас армии",
        "уволенный в запас армии бомбардир", "состоящий на военной службе",
        "находящийся на военной службе солдат из крестьян", "военнослужащий", "бессрочноотпускной рядовой",
        "уволенный во временный отпуск рядовой", "билетный солдат", "рядовой солдат",
        "отданный в солдаты", "запасный рядовой из крестьян")],
    *[(t, "RETIRED_SOLDIER") for t in (
        "отставной рядовой", "военный отставной солдат",
        "отставной сержант", "рядовой, уволенный с военной службы по болезни")],
    *[(t, "UNTER_OFFICER") for t in (
        "запасный старший унтер-офицер", "лейб гвардии Глуповского полка инвалидный унтер офицер",
        "отставной унтер-офицер")],
    *[(t, "SOLDIER_SPOUSE") for t in (
        "жена запасного рядового", "унтер-офицерская жена", "солдатская жена из крестьян")],
    *[(t, "SOLDIER_WIFE") for t in ("Солдатка", "солдатка из крестьян")],
    ("вдова солдатка", "SOLDIER_WIDOW"),
    *[(t, "SOLDIER_SON") for t in ("сын бессрочноотпускного рядового", "сын унтер-офицера")],
    ("дочь запасного рядового", "SOLDIER_DAUGHTER"),
    ("запасный солдатъ", "SOLDIER"),
    ("состоящий на действующей службе", "SOLDIER"),
    ("женатый запасный рядовой", "SOLDIER"),
    ("солдатская дочь из крестьян", "SOLDIER_DAUGHTER"),
    ("солдатская вдова из крестьян", "SOLDIER_WIDOW"),
    ("солдатская девка из крестьян", "SOLDIER_GIRL"),
    ("солдатская женка из крестьян", "SOLDIER_ZHONKA"),
    ("законная жена солдата из крестьян", "SOLDIER_LEGAL_WIFE"),
    ("солдатский сын из крестьян", "SOLDIER_SON"),
    ("унтер-офицерская вдова", "SOLDIER_WIDOW"),
    ("унтер-офицерская дочь", "SOLDIER_DAUGHTER"),
    ("унтер офицерская жена", "SOLDIER_SPOUSE"),  # pre-reform spelling is read as modern
    ("рядовой Глуповского уланского полка", "SOLDIER"),
    # the owner's ruling of 2026-11-26: the wordings once left unplaced
    *[(t, "SOLDIER_GIRL") for t in ("солдатская девица", "солдатская девица из крестьян")],
    *[(t, "UNTER_OFFICER") for t in (
        "вахмистр Глуповского конного полка", "отставной вахмистр Глуповского гусарского полка",
        "отпущенный по билету вахмистр")],
    *[(t, "SOLDIER_SON") for t in ("кантонист", "кантонист Глуповского батальона")],
    *[(t, "SOLDIER") for t in ("военный писарь в бессрочном отпуску", "военный писарь Глуповской команды")],
    ("улан Глуповского полка", "SOLDIER"),
])
def test_classify_places_each_wording(text, constant):
    assert classify(text) == constant


@pytest.mark.parametrize("text", [
    "солдат", "отставной солдат", "рядовой", "унтер-офицер", "солдатка",  # catalog texts
    "крестьянин поручика Ноздрева", "дворовый человек штабс-капитанши Коробочки", "отставной капитан",
    "лесничий штабс-капитан", "сельский писарь", "жена волостного писаря", "экономический крестьянин",
    "дьячок, уволенный от службы", "отставной коллежский регистратор", "отставной титулярный советник",
    "отставной канцелярист", "отставной ротмистр", "отставной корнет", "отставной офицер", "отставной фельдшер",
    "жена отставного коллежского регистратора", "дочь отставного ротмистра",
    "состоящий на службе в волостном правлении", "солдатская внучка",
    "писарь", "волостной писарь", "отставной писарь",  # a clerk with no «военный» is civil
    "унтер-офицерская девица", "дочь запасного рядового девица",  # unplaced
    # a military root inside a name or a place is not the word
    "крестьянин деревни Кулановки", "сын крестьянина Туланова", "крестьянин Уланчиков", "из крестьян сельца Заполковья",
])
def test_classify_leaves_others(text):
    assert classify(text) is None


@pytest.mark.parametrize("text", ["унтер-офицерская девица", "дочь запасного рядового девица"])
def test_unplaced_matches_what_classify_refuses(text):
    assert re.search(UNPLACED, text.lower())


# The whole-branch review's probes (2026-11-26).

# C1: a woman's or a kinsman's wording whose role word does not lead is never a man's constant: unplaced.
WOMEN_AND_KIN = [
    "крестьянка, жена запасного рядового", "из крестьян жена запасного рядового", "запасного рядового жена",
    "мать солдатка", "внучка солдата", "сестра солдата", "военная", "военная вдова", "фельдфебельская жена",
    "солдатская", "отставного солдата жена", "отставная солдатка", "вахмистрова жена", "унтер-офицерша",
    "унтер-офицерская", "крестьянин, сын запасного рядового", "бессрочноотпускного рядового сын",
    "военного писаря сын", "сирота солдатский сын",
    # M3: a relative's rank in a comment
    "муж запасный рядовой", "отецъ — запасный рядовой",
]


@pytest.mark.parametrize("text", WOMEN_AND_KIN)
def test_a_woman_or_kinsman_not_leading_is_unplaced(text):
    assert classify(text) is None
    assert unplaced(text)


# C2: «отставной», «отпуск» alone are no soldier's words; medics, engineers, Cossacks and the police are none.
# I1: a capitalised word after the first is a name or a place.
@pytest.mark.parametrize("text", [
    "отпускная девка", "отставной учитель", "отставной почтальон", "отставной сторож", "отставной полицейский",
    "отставной городовой", "отставной урядник", "отставной лесник", "отставной писец", "отставной лекарь",
    "отставной казак", "отставной матрос", "крестьянин, отставной", "жена отставного казака", "отпускной крестьянин",
    "военный лекарь", "военный врач", "военный инженер", "полковой врач", "полковой лекарь",
    "крестьянин деревни Солдатовки", "крестьянин села Полковое", "крестьянин села Гусаровка", "крестьянин села Рядово",
    "мещанин Запасов", "мещанин города Военного", "сын крестьянина Солдатенкова", "крестьянка деревни Отставное",
])
def test_civil_names_and_places_are_no_soldiers(text):
    assert classify(text) is None
    assert not unplaced(text)


@pytest.mark.parametrize("text, constant", [
    # I2: a cantonist is a soldier's son only when the word leads
    ("рядовой из кантонистов", "SOLDIER"), ("солдат из кантонистов", "SOLDIER"),
    ("унтер-офицер из кантонистов", "UNTER_OFFICER"), ("военный писарь из кантонистов", "SOLDIER"),
    # I1: the first word is kept whatever its case, and a word in capitals is no name
    ("уланского полка Рядовой", "SOLDIER"), ("Глуповского Гусарского полка второго эскадрона рядовой", "SOLDIER"),
    ("Вдова солдатка", "SOLDIER_WIDOW"), ("ВДОВА СОЛДАТКА", "SOLDIER_WIDOW"),
    ("запасный рядовой Ноздрев", "SOLDIER"),
    # C2: «отставной» still tells a soldier retired
    ("отставной от военной службы", "RETIRED_SOLDIER"), ("отставной вахмистр", "UNTER_OFFICER"),
    # «нижний чин» is the army's word for a private
    ("отставной нижний чин", "RETIRED_SOLDIER"), ("нижний чин Глуповского полка", "SOLDIER"),
])
def test_the_review_keeps_these(text, constant):
    assert classify(text) == constant


# The re-review: when no role leads, a rank in the genitive singular is someone else's rank — a dependant's,
# a woman's, a servant's wording — so it is listed, never a man's constant.
DEPENDANTS = [
    "невеста запасного рядового", "супруга запасного рядового", "падчерица солдата", "невестка рядового",
    "племянница солдата", "воспитанница солдата", "свояченица солдата", "незаконнорожденная солдата",
    "пасынок рядового", "воспитанник солдата", "работник запасного рядового", "крестьянин нижнего чина",
    "супруга отставного солдата", "сноха отставного солдата", "работница отставного солдата",
    "отставного солдата жонка", "зять отставного солдата", "племянник отставного солдата",
    "приемыш отставного солдата",
]


@pytest.mark.parametrize("text", DEPENDANTS)
def test_a_dependant_of_a_rank_is_unplaced(text):
    assert classify(text) is None
    assert unplaced(text)


@pytest.mark.parametrize("text, constant", [
    # a role that leads keeps its constant, whatever rank follows in the genitive
    ("жена запасного рядового", "SOLDIER_SPOUSE"), ("сын унтер-офицера", "SOLDIER_SON"),
    ("вдова отставного солдата", "SOLDIER_WIDOW"), ("дочь вахмистра", "SOLDIER_DAUGHTER"),
    ("законная жена солдата из крестьян", "SOLDIER_LEGAL_WIFE"),
    ("крестьянин отставной солдат", "RETIRED_SOLDIER"),
    # a capitalised word after the first is always a name or a place, even when spelled like a rank: a missed
    # rewrite, never a wrong constant
    ("крестьянин Отставной солдат", "SOLDIER"),
])
def test_a_leading_role_and_a_capitalised_rank_are_kept(text, constant):
    assert classify(text) == constant


@pytest.mark.parametrize("text", [
    "крестьянин Унтер-офицер", "бывший Солдат",
    "крестьянин деревни Запасной", "крестьянин деревни Рядовой",  # a place's genitive spelled like the rank
    "сын крестьянина Солдата", "дочь крестьянина Рядового",  # a surname spelled like the rank
    "крестьянин «Солдат»", "крестьянин (Солдат)",
])
def test_a_capitalised_word_spelled_like_a_rank_is_a_name(text):
    assert classify(text) is None
    assert not unplaced(text)


ESTATE_TEXTS = [
    "солдатская жена из крестьян помещика Михаила Семёновича Собакевича",
    "солдатка помещицы Настасьи Петровны Коробочки",
    "отставной солдат помещика Фрола Лаврентьевича Манилова",
    "солдатка из однодворцев",
    "солдат из однодворцев",
    "солдатка из однодворцов",
    "дворовый человек отставного солдата",  # a servant: an estate («дворов»), no longer unplaced
    "казенный крестьянин отставной солдат",  # a state peasant: an estate marker too
]


@pytest.mark.parametrize("text", ESTATE_TEXTS)
def test_a_status_naming_an_estate_stays_as_written(text):
    assert classify(text) is None
    assert unplaced(text) is False


@pytest.mark.parametrize("text, constant", [
    # a place or a name spelled like an estate marker is no estate
    ("отставной солдат деревни Дворовой", "RETIRED_SOLDIER"),
    ("запасный рядовой Купецкой слободы", "SOLDIER"),
    ("запасный рядовой Казенной палаты", "SOLDIER"),
])
def test_a_place_spelled_like_an_estate_is_no_estate(text, constant):
    assert classify(text) == constant


def test_names_estate_agrees_with_estate_of():
    from verso.ru.domain.estates import estate_of, names_estate
    for t in (*ESTATE_TEXTS, "казенный крестьянин", "мещанская вдова", "купец Глуповский", "дворовый человек",
              "запасный солдат", "крестьянин", "жена запасного рядового из крестьян", "", None):
        assert names_estate(t) == (estate_of(t) is not None), t


def test_a_status_with_no_estate_is_still_placed():
    assert classify("запасный солдат") == "SOLDIER"
    assert classify("жена запасного рядового") == "SOLDIER_SPOUSE"
