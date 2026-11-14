"""Cause-of-death constants for genealogy DSL death records."""

from verso.ru.domain import CauseOfDeath, NOT_IN_DOCUMENT  # noqa: F401

# --- Common diseases ---
SMALLPOX = CauseOfDeath("оспа")
COLIC = CauseOfDeath("колика")
NATURAL = CauseOfDeath("натуральная")
OLD_AGE = CauseOfDeath("от старости")
DIARRHEA = CauseOfDeath("понос")
CONSUMPTION = CauseOfDeath("чахотка")
PLEURISY = CauseOfDeath("колотье")
COUGH = CauseOfDeath("кашель")
FEVER = CauseOfDeath("горячка")
MEASLES = CauseOfDeath("корь")
SCARLET_FEVER = CauseOfDeath("лихорадка")
DROPSY = CauseOfDeath("водянка")
SCABIES = CauseOfDeath("короста")
COLD = CauseOfDeath("простуда")
WHOOPING_COUGH = CauseOfDeath("коклюш")
TYPHUS = CauseOfDeath("тиф")
SCARLATINA = CauseOfDeath("скарлатина")
PNEUMONIA = CauseOfDeath("воспаление легких")
BONE_CARIES = CauseOfDeath("костоеда")
DECREPITUDE = CauseOfDeath("дряхлость")
HERNIA = CauseOfDeath("грыжа")
DEBILITY = CauseOfDeath("слабосилие")

# --- Symptoms / general ---
THROAT = CauseOfDeath("от горла")
HEADACHE = CauseOfDeath("головная боль")
WEAKNESS = CauseOfDeath("слабость")
STOMACH = CauseOfDeath("ослаблением желудка")
INTERNAL = CauseOfDeath("внутренней болезнью")
UNKNOWN = CauseOfDeath("неизвестно")
CONVULSIONS = CauseOfDeath("родимец")
SUFFOCATION = CauseOfDeath("удушьем")
PARALYSIS = CauseOfDeath("паралич")
ANGINA = CauseOfDeath("стенокардия")
THROAT_TIGHTNESS = CauseOfDeath("стеснение горла")
THROAT_CONSTRICTION = CauseOfDeath("стянание горла")
TYPHOID_FEVER = CauseOfDeath("сыпная горячка")
COLD_FEVER = CauseOfDeath("простудная лихорадка")
CONSTIPATION = CauseOfDeath("запоромъ")

# --- Childbirth ---
CHILDBIRTH = CauseOfDeath("роды")
DIFFICULT_BIRTH = CauseOfDeath("от трудного рождения младенца")

# --- Accidents / violent ---
BURNED_IN_FIRE = CauseOfDeath("сгорел в пожаре")
BURNED_IN_FIRE_F = CauseOfDeath("сгорела в пожаре")
FROZE = CauseOfDeath("замерз")
CRUSHED_BY_CART = CauseOfDeath("задавлен возом")
KILLED = CauseOfDeath("убит")
KILLED_BY_BELL = CauseOfDeath("убит упавшим колоколом")
KILLED_BY_MILL = CauseOfDeath("от убития мельницей")
MILL_COLLAPSE = CauseOfDeath("от сломания мельницы")
DOG_BITE = CauseOfDeath("укус бешеной собаки")
STRUCK_BY_LIGHTNING = CauseOfDeath("от удара грома")
STRUCK = CauseOfDeath("от удара")
WOUNDS = CauseOfDeath("от ран")
SUDDEN_DEATH = CauseOfDeath("наглая смерть")
DROWNED = CauseOfDeath("от воды скоропостижной смертью")
ALCOHOL = CauseOfDeath("от излишнего употребления вина")
SEIZURE = CauseOfDeath("от припадка")
APOPLEXY = CauseOfDeath("апликсеским ударом")

# --- Aliases: variant forms → base constant name ---
# Used by the linter to map grammatical variants to the canonical constant.
# Keys are string values found in records; values are the base constant's string value.
# Keys are MODERN spellings: `known_cause` (linters/checks/single_line_calls.py) modernizes
# a literal before the lookup, so «отъ чахотки» / «слабосилія» need no row of their own.
_ALIASES: dict[str, str] = {
    # "от" prefix forms → base
    "от колики": "колика",
    "от поноса": "понос",
    "от колотья": "колотье",
    "от чахотки": "чахотка",
    "от горячки": "горячка",
    "от оспы": "оспа",
    "от кори": "корь",
    "от натуральной": "натуральная",
    "от естественной": "натуральная",
    "от простуды": "простуда",
    "от удушья": "удушьем",
    "от головной боли": "головная боль",
    "От чахотки": "чахотка",
    "От водяной": "водянка",
    "от водянки": "водянка",
    "от колик": "колика",
    "от поносу": "понос",
    "от родов": "роды",
    "от дряхлости": "дряхлость",
    "от грыжи": "грыжа",
    "от слабосилия": "слабосилие",
    # Grammatical case variants
    "горячкою": "горячка",
    "колотьем": "колотье",
    "колотие": "колотье",
    "кашлем": "кашель",
    "оспою": "оспа",
    "корью": "корь",
    "водяною": "водянка",
    "водяная болезнь": "водянка",
    "лихорадкой": "лихорадка",
    "лихорадкою": "лихорадка",
    "поносом": "понос",
    "натуральной": "натуральная",
    "естественная": "натуральная",
    "натурально": "натуральная",
    "горлом": "от горла",
    # Headache variants
    "головная": "головная боль",
    "головной": "головная боль",
    "головною": "головная боль",
    "головною болью": "головная боль",
    "головная болезнь": "головная боль",
    # Internal variants
    "внутренней": "внутренней болезнью",
    "внутренней болью": "внутренней болезнью",
    # Stomach variants
    "расслабление желудка": "ослаблением желудка",
    "расстройством или ослаблением желудка": "ослаблением желудка",
    # Rare spelling
    "пятреною болезнью": "лихорадка",
    "корь, подкинутый ребенок": "корь",
    "от слабости": "слабость",
    "от тифа": "тиф",
    "от коклюша": "коклюш",
    "от скарлатины": "скарлатина",
    "от воспаления легких": "воспаление легких",
    "от кашля": "кашель",
    "костоедною": "костоеда",
    "от костоеды": "костоеда",
}
