"""A layer that `derives`: a name it knows takes from the rules every form its forms leave empty — in the
lookups and in the reverse indexes — while a layer's own cell or pin still wins, a name no layer knows keeps
today's answer, and the old names table (which does not derive) is read as before."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from verso.ru import naming
from verso.ru.gender import Gender
from verso.ru.naming import names_registry
from verso.ru.naming.lexicon import FormsEntry, Layer, Lexicon, LexiconConflict, NameEntry, PatronymicEntry

M, F = Gender.MALE, Gender.FEMALE


def _layer(*entries: NameEntry | FormsEntry | PatronymicEntry, derives: bool = True) -> Layer:
    return Layer("base", {e.key: e for e in entries if isinstance(e, NameEntry)},
                 {e.key: e for e in entries if isinstance(e, FormsEntry)},  # type: ignore[misc]
                 {e.key: e for e in entries if isinstance(e, PatronymicEntry)}, derives=derives)


@pytest.fixture
def use(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    def install(*layers: Layer) -> Lexicon:
        lexicon = Lexicon.of(list(layers)).complete()
        monkeypatch.setattr(names_registry, "current_lexicon", lambda: lexicon)
        return lexicon
    yield install


ZUZEJ = NameEntry(M, "Зюзей", source="mk")
ZUZKA = NameEntry(M, "Зюзька", ("Зюзей",), source="mk")
ZUZA = NameEntry(F, "Зюза", source="mk")


def test_a_known_name_takes_its_forms_from_the_rules(use) -> None:
    use(_layer(ZUZEJ, ZUZKA, ZUZA))
    assert naming.derive_old_patronymic("Зюзей", M) == "Зюзеев"
    assert naming.derive_old_patronymic("Зюзей", F) == "Зюзеева"
    assert naming.derive_patronymic("Зюзей", F) == "Зюзеевна"
    assert naming.genitive_from_name("Зюзей") == "Зюзея" and naming.genitive_from_name("Зюза") == "Зюзы"
    assert naming.name_from_genitive("Зюзы") == "Зюза"


def test_the_reverse_indexes_read_the_rules_forms_too(use) -> None:
    use(_layer(ZUZEJ, ZUZKA, ZUZA))
    assert naming.canonicalize_patronymic("Зюзеев") == "Зюзеевич"
    assert naming.canonicalize_patronymic("Зюзеева") == "Зюзеевна"
    assert naming.father_name_for_patronymic("Зюзеевич") == "Зюзей"
    assert naming.father_name_for_patronymic("Зюзькин") == "Зюзей"  # a variant's: the father is its base
    assert naming.get_gender_from_old_patronymic("Зюзькина") is F
    assert naming.find_old_patronymic_by_modern("Зюзькич") == "Зюзькин"
    assert naming.validate_old_patronymic("Зюзеев")


def test_a_cell_or_a_pin_of_the_layer_wins(use) -> None:
    use(_layer(ZUZEJ, FormsEntry(M, "Зюзей", old_patronymic_m="Зюзьев", source="editor")))
    assert naming.derive_old_patronymic("Зюзей", M) == "Зюзьев"
    assert naming.derive_old_patronymic("Зюзей", F) == "Зюзеева"  # the cell left empty: the rule's
    assert naming.canonicalize_patronymic("Зюзьев") == "Зюзеевич"
    with pytest.raises(ValueError):
        naming.canonicalize_patronymic("Зюзеевъ")


def test_a_name_no_layer_knows_takes_the_rule(use) -> None:
    use(_layer(ZUZEJ))
    assert naming.derive_old_patronymic("Зюзяк", M) == "Зюзяков"  # the short form by the rule
    with pytest.raises(ValueError):
        naming.canonicalize_patronymic("Зюзяков")


def test_a_layer_that_does_not_derive_is_read_as_before(use) -> None:
    lexicon = use(_layer(ZUZEJ, ZUZA, derives=False))
    assert naming.derive_old_patronymic("Зюзей", M) == ""
    assert naming.genitive_from_name("Зюзей") is None
    assert "Зюзеев" not in lexicon.old_m
    with pytest.raises(ValueError):
        naming.canonicalize_patronymic("Зюзеев")


def test_a_reverse_index_is_built_on_its_first_use() -> None:
    """A lexicon is made without its reverse indexes; each is built when first asked, that one alone, and answers
    two names the rules give one key by a fixed order — refusing them is `complete()`'s, the check."""
    lexicon = Lexicon.of([_layer(NameEntry(M, "Зюзя", source="mk"), NameEntry(M, "Зюзия", source="mk"))])
    built = {name for name in ("old_m", "old_f", "modern_m", "modern_f", "genitive")
             if _is_set(lexicon, name)}
    assert built == set()
    assert lexicon.by_name["Зюзя"].derives == {M}
    assert lexicon.old_m["Зюзин"].father == "Зюзия"   # by spelling: Зюзия before Зюзя
    assert _is_set(lexicon, "old_m") and not _is_set(lexicon, "modern_m")
    with pytest.raises(LexiconConflict):
        lexicon.complete()


def _is_set(lexicon: Lexicon, slot: str) -> bool:
    try:
        object.__getattribute__(lexicon, slot)
    except AttributeError:
        return False
    return True


def test_a_name_held_by_two_layers_answers_alike_both_ways(use) -> None:
    """A deriving layer holds the woman's «Зюзень» alone, a layer that does not derive the man's: the rules
    answer for the woman's key only — forward and in the reverse indexes alike."""
    legacy = _layer(NameEntry(M, "Зюзень", source="names.csv"), derives=False)
    base = _layer(NameEntry(F, "Зюзень", source="mk"))
    lexicon = use(base, legacy)
    assert naming.derive_old_patronymic("Зюзень", M) == ""      # the man's key derives nothing
    assert "Зюзенев" not in lexicon.old_m and "Зюзенева" not in lexicon.old_f
    gen = naming.genitive_from_name("Зюзень")
    assert gen == "Зюзени" and naming.name_from_genitive(gen) == "Зюзень"  # the woman's: the rule's, both ways


def test_two_names_the_rules_give_one_short_form_need_a_pin(use) -> None:
    clash = (NameEntry(M, "Зюзя", source="mk"), NameEntry(M, "Зюзия", source="mk"))
    with pytest.raises(LexiconConflict, match="Зюзин"):
        Lexicon.of([_layer(*clash)]).complete()
    lexicon = use(_layer(*clash, PatronymicEntry(M, "Зюзин", "Зюзия", "Зюзиевич", "editor"),
                         PatronymicEntry(F, "Зюзина", "Зюзия", "Зюзиевна", "editor")))
    assert naming.father_name_for_patronymic("Зюзин") == "Зюзия"
    assert [layer for layer, _ in lexicon.explain("old_m", "Зюзеев")] == []
    assert [(layer, e) for layer, e in Lexicon.of([_layer(ZUZEJ)]).explain("old_m", "Зюзеев")] == [
        ("base", FormsEntry(M, "Зюзей", "Зюзея", "Зюзеевич", "Зюзеевна", "Зюзеев", "Зюзеева", "rule#Зюзей"))]
