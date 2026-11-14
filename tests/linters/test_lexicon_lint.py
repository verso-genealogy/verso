"""The lexicon linter (`verso.ru.linters.checks.lexicon`): one wrong row for each of LEX001…LEX006."""
from __future__ import annotations

from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.linters.checks.lexicon import Finding, lint_layer
from verso.ru.naming.layer_files import COLUMNS, FILES, FilesLayer
from verso.ru.naming.lexicon import FormsEntry, Layer, Lexicon, LexiconConflict, NameEntry, PatronymicEntry

M, F = Gender.MALE, Gender.FEMALE


def _layer(directory: Path, rows: dict[str, list[str]], *, name: str = "base") -> FilesLayer:
    """A layer written row by row as given — wrong rows and order included."""
    directory.mkdir(parents=True, exist_ok=True)
    for table, file in FILES.items():
        lines = ["\t".join(COLUMNS[table]), *rows.get(table, [])]
        (directory / file).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return FilesLayer(directory, name=name, writable=False)


def _codes(found: list[Finding]) -> list[tuple[str, str, str, int | None, str]]:
    return [(f.file, f.issue.code, f.issue.variant, f.issue.line, f.issue.level) for f in found]


GOOD = ["M\tЗюзей\t\t\ttrebnik1906:5\t", "M\tЗюзя\tЗюзей\t\tmk\t"]


def test_a_clean_layer_has_no_finding(tmp_path: Path) -> None:
    assert lint_layer(_layer(tmp_path, {"names": GOOD}), base=True) == []


def test_lint_codes(tmp_path: Path) -> None:
    layer = _layer(tmp_path, {
        "names": [*GOOD,
                  "M\tZuzej\t\t\tmk\t",                 # LEX001: not Cyrillic
                  "M\tЗюзеј\t\t\tmk\t",                 # LEX001: not Russian (in the base)
                  "M\tЗю́зька\tЗюзей\t\tmk\t",     # LEX001: a stress mark
                  "M\tЗюзька \tЗюзей\t\tmk\t",          # LEX001: a stray space
                  "X\tЗюзенька\tЗюзей\t\tmk\t",         # LEX001: no such sex
                  "M\tЗюзя\tЗюзей\t\tmk\t",             # LEX002: the key again
                  "M\tЗюзюша\tЗюзон\t\tmk\t",           # LEX003: no such base
                  "M\tЗюзюля\tЗюзя\t\tmk\t",            # LEX004: the base is a variant
                  "M\tЗюзюка\t\t\tПетровский\t"],       # LEX006: no source of the base
        "forms": ["\tЗюзей\tЗюзея\t\t\t\t\teditor",     # LEX001: forms without a sex
                  "M\tЗюзей\tЗюзея\tЗюзьевич\t\t\t\teditor"],  # LEX005: the genitive is the rule's
    })
    assert _codes(lint_layer(layer, base=True)) == [
        ("names.tsv", "LEX001", "not_cyrillic", 4, "error"),
        ("names.tsv", "LEX001", "not_russian", 5, "error"),
        ("names.tsv", "LEX001", "stress", 6, "error"),
        ("names.tsv", "LEX001", "space", 7, "error"),
        ("names.tsv", "LEX001", "bad_sex", 8, "error"),
        ("names.tsv", "LEX002", "duplicate", 9, "error"),
        ("names.tsv", "LEX006", "source", 12, "error"),
        ("forms.tsv", "LEX001", "no_sex", 2, "error"),
        ("names.tsv", "LEX003", "unknown_base", 10, "error"),
        ("names.tsv", "LEX004", "chain", 11, "error"),
        ("forms.tsv", "LEX005", "forms", 3, "warn"),
    ]
    messages = [f.issue.message for f in lint_layer(layer, base=True)]
    assert "[LEX004] «Зюзюля»: основа «Зюзя» сама вариант «Зюзей»" in messages


def test_a_letter_of_another_alphabet_is_the_base_s_error_alone(tmp_path: Path) -> None:
    """A Serbian «ј» in a key is refused in the base; a corpus's own layer may write it."""
    layer = _layer(tmp_path, {"names": ["M\tЗюзеј\t\t\tкнига\t"]}, name="corpus")
    assert _codes(lint_layer(layer)) == []


def test_a_chain_in_an_upper_layer_is_advice(tmp_path: Path) -> None:
    """Above the base, a variant of a variant is a chain the layer may keep (a corpus folds by its own
    base): advice, not an error; and a source is the layer's own business."""
    below = Layer("base", {(M, "Зюзей"): NameEntry(M, "Зюзей", source="mk"),
                           (M, "Зюзя"): NameEntry(M, "Зюзя", ("Зюзей",), source="mk")}, {}, {})
    upper = _layer(tmp_path, {"names": ["M\tЗюзюля\tЗюзя\t\tкнига 1\t"]}, name="corpus")
    assert _codes(lint_layer(upper, below=[below])) == [("names.tsv", "LEX004", "chain", 2, "warn")]


def test_redundant_rows_of_an_upper_layer(tmp_path: Path) -> None:
    """LEX005: a row that answers as the sum without it — a name entry the base holds as it is, a forms cell
    the rule gives, a pin the derivation gives."""
    below = Layer("base", {(M, "Зюзей"): NameEntry(M, "Зюзей", source="mk")},
                  {(M, "Зюзей"): FormsEntry(M, "Зюзей", old_patronymic_m="Зюзьев", source="editor")}, {})
    upper = _layer(tmp_path, {
        "names": ["M\tЗюзей\t\t\tмой\t", "F\tЗюзея\t\t\tмой\t"],
        "forms": ["M\tЗюзей\tЗюзея\tЗюзьевич\t\tЗюзьев\t\tмой"],
        "patronymics": ["M\tЗюзьев\tЗюзей\tЗюзьевич\t\tмой", "M\tЗюзеев\tЗюзей\t\t\tмой"],
    }, name="corpus")
    found = lint_layer(upper, below=[below])
    assert _codes(found) == [
        ("names.tsv", "LEX005", "names", 2, "warn"),
        ("forms.tsv", "LEX005", "forms", 2, "warn"),
        ("patronymics.tsv", "LEX005", "patronymics", 2, "warn"),
    ]
    assert [f.issue.params["column"] for f in found if f.file == "forms.tsv"] == ["genitive"]


def test_a_forms_cell_the_lower_layer_gives_is_not_redundant(tmp_path: Path) -> None:
    """An upper forms entry replaces the lower one whole: a cell equal to the lower layer's, which the rule does not
    give, is the upper entry's own — left empty it would be the rule's (Зюзеев), not the lower layer's (Зюзьев)."""
    below = Layer("base", {(M, "Зюзей"): NameEntry(M, "Зюзей", source="mk")},
                  {(M, "Зюзей"): FormsEntry(M, "Зюзей", old_patronymic_m="Зюзьев", source="editor")}, {})
    upper = _layer(tmp_path, {"forms": ["M\tЗюзей\t\tЗюзьевич\t\tЗюзьев\t\tмой"]}, name="corpus")
    assert [f for f in lint_layer(upper, below=[below]) if f.issue.code == "LEX005"] == []


def test_a_corpus_layer_of_legacy_sources_is_no_lex006(tmp_path: Path) -> None:
    """`legacy` and `ignore` — the sources `verso names layer-diff` writes — is none of the base's SOURCES: refused in the base
    alone, a corpus layer's own business."""
    rows = {"names": ["M\tЗюзей\t\t\tlegacy\t", "M\tЗюзя\tЗюзей\t\tignore\t"],
            "patronymics": ["M\tЗюзьев\tЗюзей\tЗюзьевич\t\tlegacy"]}
    assert "LEX006" not in {f.issue.code for f in lint_layer(_layer(tmp_path / "corpus", rows, name="corpus"))}
    assert {f.issue.code for f in lint_layer(_layer(tmp_path / "base", rows), base=True)} >= {"LEX006"}


def test_a_womans_patronymic_cell_is_not_the_rules(tmp_path: Path) -> None:
    """A woman's name gives no patronymic by rule: a patronymic cell of her forms is never redundant."""
    upper = _layer(tmp_path, {"forms": ["F\tЗюзея\t\tЗюзеич\t\tЗюзеин\t\tмой"]}, name="corpus")
    assert [f for f in lint_layer(upper) if f.issue.code == "LEX005"] == []


def test_a_removal_is_the_upper_layers_alone(tmp_path: Path) -> None:
    """`-` in bases removes a key of the layers below: refused in the base (LEX006), redundant where no layer below
    holds the key (LEX005), and no base to look up (no LEX003)."""
    removal = ["F\tЗюзь\t-\t\tlegacy\t"]
    assert _codes(lint_layer(_layer(tmp_path / "base", {"names": ["F\tЗюзь\t-\t\tmk\t"]}), base=True)) == [
        ("names.tsv", "LEX006", "removal", 2, "error")]
    upper = _layer(tmp_path / "corpus", {"names": removal}, name="corpus")
    assert _codes(lint_layer(upper)) == [("names.tsv", "LEX005", "removal", 2, "warn")]
    below = Layer("base", {(F, "Зюзь"): NameEntry(F, "Зюзь", source="mk")}, {}, {})
    assert _codes(lint_layer(upper, below=[below])) == []


def test_a_collision_the_sum_leaves_unpinned_is_lex007(tmp_path: Path) -> None:
    """Two names whose rules give one short patronymic, no pin: a hard finding naming the key and its candidates;
    the pin settles it."""
    rows = {"names": ["M\tЗюзя\t\t\tmk\t", "M\tЗюзия\t\t\tmk\t"]}
    found = [f for f in lint_layer(_layer(tmp_path / "a", rows, name="corpus")) if f.issue.code == "LEX007"]
    assert [(f.issue.params["key"], f.issue.params["index"], f.issue.level) for f in found] == [
        ("Зюзин", "old_m", "error"), ("Зюзина", "old_f", "error")]
    assert "Зюзия" in str(found[0].issue.params["candidates"]) and "Зюзя" in str(found[0].issue.params["candidates"])
    pinned = {**rows, "patronymics": ["M\tЗюзин\tЗюзия\tЗюзиевич\t\tmk", "F\tЗюзина\tЗюзия\tЗюзиевна\t\tmk"]}
    assert [f for f in lint_layer(_layer(tmp_path / "b", pinned, name="corpus")) if f.issue.code == "LEX007"] == []


def test_a_removal_that_leaves_a_lower_base_dangling_is_lex003(tmp_path: Path) -> None:
    below = Layer("base", {(F, "Зюзь"): NameEntry(F, "Зюзь", source="mk"),
                           (F, "Зюзенька"): NameEntry(F, "Зюзенька", ("Зюзь",), source="mk")}, {}, {})
    upper = _layer(tmp_path, {"names": ["F\tЗюзь\t-\t\tlegacy\t"]}, name="corpus")
    assert _codes(lint_layer(upper, below=[below])) == [("names.tsv", "LEX003", "removed_base", 2, "error")]


def test_an_ignore_row_over_a_plain_one_is_not_redundant(tmp_path: Path) -> None:
    """A name of the ignore list is that by its source (`ignore`): over the base's plain entry of the key it answers
    otherwise (`is_ignored_name`), so it is not redundant."""
    below = Layer("base", {(F, "Зюзея"): NameEntry(F, "Зюзея", source="mk")}, {}, {})
    upper = _layer(tmp_path, {"names": ["F\tЗюзея\t\t\tignore\t"]}, name="corpus")
    assert _codes(lint_layer(upper, below=[below])) == []


def _redundant_by_rebuild(upper: Layer, below: list[Layer]) -> list[str]:
    """The pins of `upper` the sum without each one answers alike, asked of a lexicon built anew for each — what LEX005
    answers without building one."""
    out = []
    for key, pin in upper.patronymics.items():
        rest = {k: p for k, p in upper.patronymics.items() if k != key}
        try:
            lexicon = Lexicon.of([*below, Layer(upper.name, upper.names, upper.forms, rest, derives=True)]).complete()
        except LexiconConflict:
            continue
        male = pin.sex is M
        if pin.is_unattached:
            same = pin.form in lexicon.unattached
        elif pin.old is not None:
            same = (lexicon.modern_m if male else lexicon.modern_f).get(pin.form) == pin.old
        else:
            held = (lexicon.old_m if male else lexicon.old_f).get(pin.form)
            same = held is not None and (held.father, held.modern) == (pin.father, pin.modern)
        if same:
            out.append(pin.form)
    return out


def test_a_redundant_pin_is_what_a_lexicon_without_it_answers(tmp_path: Path) -> None:
    """LEX005 on pins: the derivations are built once and each pin asked of the sum's pins without it — a lower
    layer's pin of its key coming back, a modern pin, a form tied to nothing, a pin settling a conflict — as a
    lexicon built without the pin answers."""
    below = Layer("base", {(M, "Зюзей"): NameEntry(M, "Зюзей", source="mk")},
                  {(M, "Зюзей"): FormsEntry(M, "Зюзей", "Зюзея", "Зюзьевич", "Зюзьевна", "Зюзьев", "Зюзьева", "editor")},
                  {(M, "Зюзьев"): PatronymicEntry(M, "Зюзьев", "Зюзей", "Зюзеевич", "editor"),
                   (M, "Зюзиков"): PatronymicEntry(M, "Зюзиков", source="editor")})
    upper = _layer(tmp_path, {
        "names": ["M\tЗюзон\t\t\tмой\t", "M\tЗюзан\t\t\tмой\t"],
        "forms": ["M\tЗюзон\t\tЗюзонович\t\tЗюзонов\t\tмой", "M\tЗюзан\t\tЗюзанович\t\tЗюзонов\t\tмой"],
        "patronymics": ["M\tЗюзьев\tЗюзей\tЗюзьевич\t\tмой",       # the lower pin comes back: not redundant
                        "M\tЗюзьевна\t\t\tЗюзьева\tмой",           # a woman's modern form as a man's: not redundant
                        "M\tЗюзьевич\t\t\tЗюзьев\tмой",            # the derivation's short form: redundant
                        "\tЗюзиков\t\t\t\tмой",                    # tied to nothing below too: redundant
                        "M\tЗюзонов\tЗюзон\tЗюзонович\t\tмой"],    # settles Зюзон / Зюзан: not redundant
    }, name="corpus")
    found = [f.issue.token for f in lint_layer(upper, below=[below]) if f.file == "patronymics.tsv"]
    assert found == ["Зюзьевич", "Зюзиков"]
    assert found == _redundant_by_rebuild(upper.load(), [below])
