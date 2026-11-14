"""The names base the library ships (`verso/ru/naming/data/base/`): built by `tools/names_build/build.py` from
the святцы, Wikidata and the metric books' spellings, a source on every row."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.names_build import build
from verso.ru.gender import Gender
from verso.ru.naming import forms as rules
from verso.ru.naming import names_registry
from verso.ru.naming.layer_files import BASE, FILES, base, is_base_source
from verso.ru.naming.lexicon import Layer, Lexicon


@pytest.fixture(scope="module")
def layer() -> Layer:
    return base().load()


def test_base_is_reproducible(tmp_path: Path) -> None:
    """Two builds give the same bytes — one here, one in a process of its own with another hash seed, so no
    order of a set or a dict leaks into them — and they are the bytes the package ships."""
    one, two = tmp_path / "one", tmp_path / "two"
    build.write(build.build(), one)
    seed = "1" if os.environ.get("PYTHONHASHSEED") != "1" else "2"
    subprocess.run([sys.executable, str(Path(build.__file__)), "--out", str(two)], check=True, capture_output=True,
                   env={**os.environ, "PYTHONHASHSEED": seed})
    for file in FILES.values():
        assert (one / file).read_bytes() == (two / file).read_bytes()
        assert (one / file).read_bytes() == (BASE / file).read_bytes(), f"{file}: run tools/names_build/build.py"


def test_base_reads_no_names_csv() -> None:
    """The base is built from its free sources alone: the old names table is no input of it."""
    source = Path(build.__file__).read_text(encoding="utf-8")
    assert "names.csv" not in source and "names_registry" not in source


def _svyatcy() -> dict[int, tuple[str, str]]:
    lines = build.SVYATCY.read_text(encoding="utf-8").split("\n")
    return {n: (c[0], c[2]) for n, line in enumerate(lines, start=1)
            if line and not line.startswith(("#", "gender\t")) for c in [line.split("\t")]}


def _entries(layer: Layer) -> Iterator[tuple[str, object, str]]:
    for table in ("names", "forms", "patronymics"):
        for entry in getattr(layer, table).values():
            yield table, entry, entry.source


def test_base_sources(layer: Layer) -> None:
    """Every row names one of `SOURCES`; a line of the святцы holds that name of that sex, a Wikidata item is
    in the snapshot with that label."""
    svyatcy = _svyatcy()
    snapshot = json.loads(build.WIKIDATA.read_text(encoding="utf-8"))
    items = {i["qid"]: (i["label"], i["sex"]) for i in snapshot["items"]}
    assert [(t, e) for t, e, s in _entries(layer) if not is_base_source(s)] == []
    sex: dict[Gender | None, str] = {Gender.MALE: "M", Gender.FEMALE: "F", None: ""}
    for entry in layer.names.values():
        kind, _, ref = entry.source.partition(":")
        if kind == "trebnik1906":
            assert svyatcy.get(int(ref)) == (sex[entry.sex], entry.name), entry
        elif kind == "wikidata":
            label, sexes = items[ref]
            assert label == entry.name and sex[entry.sex] in sexes, entry
    assert {e.source.partition(":")[0] for e in layer.names.values()} == {"trebnik1906", "wikidata", "mk", "editor"}
    assert {e.source for e in layer.forms.values()} == {"editor"}


def test_base_fixed_point(layer: Layer, monkeypatch: pytest.MonkeyPatch) -> None:
    """A base is never itself a variant: `matching_base` of a base is the base, with or without a sex."""
    lexicon = Lexicon.of([layer])
    monkeypatch.setattr(names_registry, "current_lexicon", lambda: lexicon)
    for sex, name in layer.names:
        for asked in {sex, None}:
            once = names_registry.matching_base(name, asked)
            assert names_registry.matching_base(once, asked) == once, (name, asked)
    for entry in layer.names.values():
        for b in entry.bases:
            assert not layer.names[(entry.sex, b)].bases, entry


def test_base_holds_given_names_only(layer: Layer) -> None:
    """A key of the base is one word of the Russian alphabet, and no patronymic or surname form is a name of
    it: the Wikidata labels of other alphabets and the patronymics labelled as given names stay out."""
    import re
    russian = re.compile(r"[А-ЯЁ][а-яё]*(?:-[А-ЯЁ][а-яё]*)?")
    assert [n for _, n in layer.names if not russian.fullmatch(n)] == []
    assert [n for _, n in layer.names if n.endswith(("вич", "вна"))] == []
    for name in ("Иванович", "Константинович", "Ильич", "Костадинов", "Інна", "Андреј"):
        assert all(n != name for _, n in layer.names), name


def test_the_svyatcy_and_the_books_decide_a_names_sex(layer: Layer) -> None:
    """A name the святцы or the books hold in one sex takes no Wikidata row of the other sex: Борис is a man's
    name, Мария a woman's, whatever item of the other sex Wikidata keeps."""
    attested = {key for key, e in layer.names.items() if e.source.startswith(("trebnik1906:", "mk"))}
    other = {Gender.MALE: Gender.FEMALE, Gender.FEMALE: Gender.MALE}
    assert [e for key, e in layer.names.items() if e.source.startswith("wikidata:") and key[0] is not None
            and (other[key[0]], key[1]) in attested] == []
    for sex, name in ((Gender.FEMALE, "Борис"), (Gender.MALE, "Мария"), (Gender.FEMALE, "Захар")):
        assert (sex, name) not in layer.names, name
    assert (Gender.MALE, "Борис") in layer.names and (Gender.FEMALE, "Мария") in layer.names


def test_rule_equals_forms(layer: Layer) -> None:
    """A name without a forms entry takes its forms from the rules; an entry's cell is never what the rule
    gives (it would be redundant, LEX005)."""
    for (sex, name) in layer.names:
        if sex is not None and (sex, name) not in layer.forms:
            assert rules.genitive(name, sex) and rules.modern_patronymic(name, Gender.MALE)
            assert rules.old_patronymic(name, Gender.FEMALE)
    for fe in layer.forms.values():
        assert (fe.sex, fe.name) in layer.names
        rule = (rules.genitive(fe.name, fe.sex), rules.modern_patronymic(fe.name, Gender.MALE),
                rules.modern_patronymic(fe.name, Gender.FEMALE), rules.old_patronymic(fe.name, Gender.MALE),
                rules.old_patronymic(fe.name, Gender.FEMALE))
        cells = fe[2:7]
        assert any(cells) and all(c is None or c != r for c, r in zip(cells, rule, strict=True)), fe


def test_base_no_conflicts(layer: Layer) -> None:
    lexicon = Lexicon.of([layer]).complete()
    assert lexicon.layers == ("base",)
    assert lexicon.old_m["Львов"].father == "Лев"
    female = lexicon.by_name["Прасковья"].female
    assert female is not None and female.bases == ("Параскева",)


def test_base_passes_its_linter() -> None:
    from verso.ru.linters.checks.lexicon import lint_layer
    assert [f.issue.message for f in lint_layer(base(), base=True)] == []
