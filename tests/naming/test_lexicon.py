"""The lexicon of layers: unique keys, an upper layer replacing its key alone, a conflict that only an
entry of `patronymics` settles, and the keys no layer holds."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.naming.legacy_reference import Reference
from tests.naming.test_legacy_compile import FIXTURE, area
from verso.core import workspace
from verso.ru.gender import Gender
from verso.ru.naming import (
    canonicalize_name, canonicalize_patronymic, derive_patronymic, find_old_patronymic_by_modern,
    get_gender_from_name, matching_base, names_registry, validate_first_name)
from verso.ru.naming.names_registry import ignored_name_gender, is_ignored_name
from verso.ru.naming.legacy import compile_legacy
from verso.ru.naming.lexicon import IGNORE_LIST, FormsEntry, Layer, Lexicon, LexiconConflict, NameEntry, PatronymicEntry

M, F = Gender.MALE, Gender.FEMALE


def layer(name: str, *entries: NameEntry | FormsEntry | PatronymicEntry) -> Layer:
    return Layer(name, {e.key: e for e in entries if isinstance(e, NameEntry)},
                 {e.key: e for e in entries if isinstance(e, FormsEntry)},
                 {e.key: e for e in entries if isinstance(e, PatronymicEntry)})


@pytest.fixture
def substitute(monkeypatch: pytest.MonkeyPatch):
    """Make the naming functions ask this lexicon."""
    def use(lexicon: Lexicon) -> None:
        monkeypatch.setattr(names_registry, "current_lexicon", lambda: lexicon)
    return use


def test_keys_unique(tmp_path: Path) -> None:
    """A layer's tables are keyed by their entries' keys; a table holding one row twice compiles to one entry."""
    row = ["М", "Зюзей", "", "", "", "Зюзея", "Зюзеев", "Зюзеева", "Зюзеевич", "Зюзеевна", ""]
    root = area(tmp_path / "a", [row, row])
    compiled = compile_legacy(root / "names.csv")
    assert list(compiled.names) == [(M, "Зюзей")] and list(compiled.forms) == [(M, "Зюзей")]
    fixture = compile_legacy(FIXTURE / "names.csv", FIXTURE / "names_ignore.csv", FIXTURE / "patronymics_ignore.csv")
    for table in (fixture.names, fixture.forms, fixture.patronymics):
        assert all(key == entry.key for key, entry in table.items())


def test_upper_layer_replaces_key(substitute) -> None:
    """Лука in the base as a man and as a woman, a layer above knowing the man alone, with another base:
    the man answers by the upper layer, the woman by the base, and the name has no one sex (Review Focus 1)."""
    base = layer("base", NameEntry(M, "Лука"), NameEntry(F, "Лука", ("Гликерия",)))
    upper = layer("corpus", NameEntry(M, "Лука", ("Лукиан",)))
    lexicon = Lexicon.of([base, upper])
    substitute(lexicon)
    assert matching_base("Лука", M) == "Лукиан"
    assert matching_base("Лука", F) == "Гликерия"
    assert matching_base("Лука") == "Лука"
    assert get_gender_from_name("Лука") is None
    assert [(where, e.sex) for where, e in lexicon.explain("name", "Лука")] == [("corpus", M), ("base", F)]


def test_two_bases_answer_as_written(tmp_path: Path) -> None:
    """Анис → Анисий | Онисим: compared as written; written as its first row said, through `canonical`,
    whichever row stands first (Review Focus 5)."""
    rows = [["М", "Анис", "Анисий", "", "", "Аниса", "Анисов", "Анисова", "Анисиевич", "Анисиевна", ""],
            ["М", "Анис", "Онисим", "", "", "Аниса", "Анисов", "Анисова", "Онисимович", "Онисимовна", ""],
            ["М", "Анисий", "", "", "", "Анисия", "Анисиев", "Анисиева", "Анисиевич", "Анисиевна", ""],
            ["М", "Онисим", "", "", "", "Онисима", "Онисимов", "Онисимова", "Онисимович", "Онисимовна", ""]]
    for order, name, written in ((rows, "a", "Анисий"), (rows[1:2] + rows[:1] + rows[2:], "b", "Онисим")):
        root = area(tmp_path / name, order)
        entry = compile_legacy(root / "names.csv").names[(M, "Анис")]
        assert entry.bases == ("Анисий", "Онисим") and entry.canonical == written
        with workspace.use(root):
            assert matching_base("Анис", M) == matching_base("Анис") == "Анис"
            assert canonicalize_name("Анис", M) == written == Reference(root / "names.csv").canonicalize_name("Анис", M)


def test_conflict_needs_a_pin(substitute) -> None:
    """Two names deriving one short patronymic, or one modern patronymic two short ones, is a conflict
    `complete()` refuses until an entry of `patronymics` says which holds; a lexicon asked at runtime answers it by
    a fixed order (the first father by spelling, the first short form)."""
    forms = (FormsEntry(M, "Зарон", old_patronymic_m="Заронов", patronymic_m="Заронович"),
             FormsEntry(M, "Зарен", old_patronymic_m="Заронов", patronymic_m="Заренович"))
    with pytest.raises(LexiconConflict) as found:
        Lexicon.of([layer("a", *forms)]).complete()
    assert found.value.key == ("old_m", "Заронов")
    assert Lexicon.of([layer("a", *forms)]).old_m["Заронов"].father == "Зарен"  # runtime: by spelling
    pinned = Lexicon.of([layer("a", *forms, PatronymicEntry(M, "Заронов", "Зарон", "Заронович"))])
    assert pinned.old_patronymic("Заронов") == PatronymicEntry(M, "Заронов", "Зарон", "Заронович")

    modern = (FormsEntry(M, "Кузьма", old_patronymic_m="Кузьмин", patronymic_m="Кузьмич"),
              FormsEntry(M, "Кузма", old_patronymic_m="Кузмин", patronymic_m="Кузьмич"))
    with pytest.raises(LexiconConflict) as found:
        Lexicon.of([layer("a", *modern)]).complete()
    assert found.value.key == ("modern_m", "Кузьмич")
    assert Lexicon.of([layer("a", *modern)]).short_form("Кузьмич") == "Кузмин"
    lexicon = Lexicon.of([layer("a", *modern, PatronymicEntry(M, "Кузьмич", old="Кузьмин"))])
    substitute(lexicon)
    assert find_old_patronymic_by_modern("Кузьмич") == "Кузьмин"
    # The regular form among the two needs no pin.
    Lexicon.of([layer("a", FormsEntry(M, "Ефим", old_patronymic_m="Ефимов", patronymic_m="Ефимович"),
                      FormsEntry(M, "Евфим", old_patronymic_m="Евфимов", patronymic_m="Ефимович"))]).complete()


def test_odd_keys() -> None:
    """`?`, the empty string and the pre-reform «Ѳеодоръ» (which the callers modernise first) answer as
    v0.1.26 did (Review Focus 3)."""
    ref = Reference(FIXTURE / "names.csv", FIXTURE / "names_ignore.csv", FIXTURE / "patronymics_ignore.csv")
    for key in ("?", "", "Ѳеодоръ", "Ив?н", "Аэ́тий"):
        for sex in (M, F, None):
            assert matching_base(key, sex) == ref.matching_base(key, sex)
            assert canonicalize_name(key, sex) == ref.canonicalize_name(key, sex)
            assert derive_patronymic(key, sex) == ref.derive_patronymic(key, sex)
        assert get_gender_from_name(key) is ref.get_gender_from_name(key)
        assert validate_first_name(key) is ref.validate_first_name(key)
    for key in ("?", "", "Ив?нов"):
        assert canonicalize_patronymic(key) == ref.canonicalize_patronymic(key)


def test_explain_names_the_layer_and_the_entry() -> None:
    pin = PatronymicEntry(M, "Заронов", "Зарон", "Заронович", "here")
    lexicon = Lexicon.of([layer("a", FormsEntry(M, "Зарон", old_patronymic_m="Заронов", patronymic_m="Заронович")),
                          layer("b", pin, PatronymicEntry(None, "Кукуев"))])
    assert lexicon.explain("old_m", "Заронов") == [("b", pin)]
    assert [where for where, _ in lexicon.explain("modern_m", "Заронович")] == ["a"]
    assert [where for where, _ in lexicon.explain("ignore_patronymic", "Кукуев")] == ["b"]
    assert lexicon.explain("genitive", "Никого") == []
    with pytest.raises(ValueError, match="nope"):
        lexicon.explain("nope", "x")


def test_an_upper_layer_drops_the_stale_unsexed_answer(substitute) -> None:
    """A layer that replaces a name's sexed entries and says nothing of it without a sex drops the
    lower layers' (None, name) entry: the answer without a sex is then derived over the entries
    summed — not the one pinned against entries the upper layer has replaced."""
    base = layer("base", NameEntry(M, "Зюзан", ("Зюзанф",)), NameEntry(F, "Зюзан", ("Зюзения",)),
                 NameEntry(None, "Зюзан", canonical="Зюзанф"))
    upper = layer("corpus", NameEntry(M, "Зюзан", ("Зюзантипп",)))
    substitute(Lexicon.of([base]))
    assert canonicalize_name("Зюзан") == "Зюзанф"                # the base's own pin
    substitute(Lexicon.of([base, upper]))
    assert canonicalize_name("Зюзан") == "Зюзан"                 # both sexes, nothing pinned: as written
    assert canonicalize_name("Зюзан", M) == "Зюзантипп"
    keeps = layer("corpus", NameEntry(M, "Зюзан", ("Зюзантипп",)), NameEntry(None, "Зюзан", canonical="Зюзантипп"))
    substitute(Lexicon.of([base, keeps]))
    assert canonicalize_name("Зюзан") == "Зюзантипп"             # its own pin stands


def test_an_upper_layer_giving_a_sex_drops_the_ignore_list_entry(substitute) -> None:
    """The ignore list's name without a sex, in a lower layer, under a layer that gives the name a sex: the
    (None, name) entry goes like any other, so the name is no longer ignored and answers by its sex."""
    base = layer("base", NameEntry(None, "Зюзей", source=IGNORE_LIST))
    upper = layer("corpus", NameEntry(M, "Зюзей"))
    substitute(Lexicon.of([base]))
    assert is_ignored_name("Зюзей") and ignored_name_gender("Зюзей") is None
    assert get_gender_from_name("Зюзей") is None
    lexicon = Lexicon.of([base, upper])
    substitute(lexicon)
    assert not is_ignored_name("Зюзей") and ignored_name_gender("Зюзей") is None
    assert get_gender_from_name("Зюзей") is M
    assert lexicon.explain("ignore_name", "Зюзей") == []
    assert [(where, e.sex) for where, e in lexicon.explain("name", "Зюзей")] == [("corpus", M)]


@pytest.mark.parametrize("hers_first", [False, True], ids=["his forms first", "hers first"])
def test_feminine_reads_the_forms_that_hold_it(hers_first: bool) -> None:
    """A name whose man's and woman's forms entries stand on one source (one row of the old table gave
    both): the woman's modern patronymic is the one the entry holding it gives, whichever was written last."""
    his = FormsEntry(M, "Зюзей", "Зюзея", "Зюзеевич", "Зюзеевна", "Зюзеев", None, "t:2")
    hers = FormsEntry(F, "Зюзей", "Зюзеи", source="t:2")
    entries = (hers, his) if hers_first else (his, hers)
    lexicon = Lexicon.of([layer("t", NameEntry(M, "Зюзей"), NameEntry(F, "Зюзей"), *entries)])
    assert lexicon.feminine(lexicon.old_m["Зюзеев"]) == "Зюзеевна"


def test_only_an_unattached_patronymic_has_no_sex() -> None:
    for entry in (PatronymicEntry(None, "Зюзеев", father="Зюзей"), PatronymicEntry(None, "Зюзеев", modern="Зюзеевич"),
                  PatronymicEntry(None, "Зюзеевич", old="Зюзеев")):
        with pytest.raises(ValueError, match="Зюзе"):
            Lexicon.of([layer("bad", entry)])
    assert Lexicon.of([layer("ok", PatronymicEntry(None, "Зюзеев"))]).unattached == {"Зюзеев"}


def test_feminine_reads_no_source() -> None:
    """The woman's patronymic beside a man's reading is read through the reading's own forms, else the woman's short
    form beside it — never through the entries' sources: two pins of one source keep their own women's forms."""
    forms = (FormsEntry(M, "Зарон", "Зарона", "Заронович", "Зароновна", "Заронов", "Заронова", "legacy"),)
    pins = (PatronymicEntry(M, "Заренов", "Зарен", "Заренович", "legacy"),
            PatronymicEntry(F, "Заренова", "Зарен", "Заренична", "legacy"),
            PatronymicEntry(M, "Зурин", "Зура", "Зурич", "legacy"),
            PatronymicEntry(F, "Зурина", "Зура", "Зурична", "legacy"))
    lexicon = Lexicon.of([layer("a", NameEntry(M, "Зарон", source="legacy"), *forms, *pins)])
    assert lexicon.feminine(lexicon.old_m["Заронов"]) == "Зароновна"
    assert lexicon.feminine(lexicon.old_m["Заренов"]) == "Заренична"
    assert lexicon.feminine(lexicon.old_m["Зурин"]) == "Зурична"
    assert lexicon.feminine(PatronymicEntry(M, "Зымов", "Зым", "Зымович", "legacy")) is None


def test_the_ignore_lists_source_is_neutral() -> None:
    assert IGNORE_LIST == "ignore"
