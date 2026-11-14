"""The old names table compiled into one layer answers every naming function as v0.1.26 did.

`compare()` asks every key of every column the old table indexed — and of its two ignore lists —
of every public naming function, with both sexes and none, here and of `legacy_reference`, over
one workspace. The fixture table is asked in its own order and reversed: a reversed table is
another table, with other answers where its rows tied, and compiles into another layer — whose
answers are the reversed table's.

`name_from_genitive` is held to the reference only where one name gives the genitive, and gives it
as its own (the one `genitive_from_name` answers): a name's forms hold one genitive, so the old
table's other spellings of it (Парфён's «Парфена» beside its own «Парфёна») are no key of the
lexicon, and where two names gave one genitive the old answer was the first row's. There the
lexicon answers by its own rule (no question of the corpus asks it), pinned by
`test_a_shared_genitive_answers_by_the_canonical_name`.

The two folds `consolidation.tree_conflicts` read off raw rows are held to the reference too.
"""
from __future__ import annotations

import csv
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.naming.legacy_reference import Reference
from verso.core import workspace
from verso.core.workspace import WorkspaceError
from verso.ru.consolidation import tree_conflicts
from verso.ru.gender import Gender
from verso.ru.naming import (
    canonicalize_name, canonicalize_patronymic, derive_old_patronymic, derive_patronymic, father_name_for_patronymic,
    find_old_patronymic_by_modern, genitive_from_name, genitive_given_name, get_gender_from_name,
    get_gender_from_old_patronymic, matching_base, name_from_genitive, names_registry, validate_first_name,
    validate_old_patronymic)
from verso.ru.naming.legacy import compile_legacy
from verso.ru.naming.lexicon import Lexicon

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "legacy-names"
HEADER = ["Пол", "Имя", "Имя-основа", "От", "Склонения, связи", "Родительный падеж", "Отчество старое М",
          "Отчество старое Ж", "Отчество М", "Отчество Ж", "Источник"]
INDEXED = ("Имя", "Имя-основа", "Родительный падеж", "Отчество старое М", "Отчество старое Ж", "Отчество М",
           "Отчество Ж")
SEXES = (Gender.MALE, Gender.FEMALE, None)


def area(root: Path, rows: list[list[str]], *, ignore: list[tuple[str, str]] | None = None,
         patronymics: list[str] | None = None) -> Path:
    """A workspace of schema 4 whose names tables are these rows (and ignore lists)."""
    root.mkdir(parents=True)
    (root / "verso.toml").write_text('schema = 4\nplugins = ["ru"]\n[names]\ndir = "."\n', encoding="utf-8")
    with (root / "names.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)
    if ignore is not None:
        (root / "names_ignore.csv").write_text("Gender,Name\n" + "".join(f"{g},{n}\n" for g, n in ignore),
                                               encoding="utf-8")
    if patronymics is not None:
        (root / "patronymics_ignore.csv").write_text("Patronymic\n" + "".join(f"{p}\n" for p in patronymics),
                                                     encoding="utf-8")
    return root


def fixture_copy(root: Path, *, reverse: bool) -> Path:
    """The fixture's three tables in a workspace of their own, the names table's rows reversed or not."""
    with (FIXTURE / "names.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))[1:]
    area(root, rows[::-1] if reverse else rows)
    for table in ("names_ignore.csv", "patronymics_ignore.csv"):
        shutil.copy(FIXTURE / table, root / table)
    return root


def reference(root: Path) -> Reference:
    return Reference(root / "names.csv", root / "names_ignore.csv", root / "patronymics_ignore.csv")


def keys(root: Path) -> set[str]:
    """Every key the old table indexed, its ignore lists' and the odd ones."""
    found = {"", "?", "Ив?н", "Ѳеодоръ", "Феодоръ", "Семён", "Семен", "Иванович", "Ивановна", "Кузьмич"}
    with (root / "names.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            found.update(row[c] for c in INDEXED if row[c])
    for table, column in (("names_ignore.csv", "Name"), ("patronymics_ignore.csv", "Patronymic")):
        with (root / table).open(encoding="utf-8", newline="") as f:
            found.update(r[column] for r in csv.DictReader(f) if r[column])
    return found


def own_genitives(root: Path, ref: Reference) -> set[str]:
    """The genitives one name of the table gives, and gives as its own."""
    by: dict[str, set[str]] = {}
    with (root / "names.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["Родительный падеж"]:
                by.setdefault(row["Родительный падеж"], set()).add(row["Имя"])
    return {g for g, names in by.items() if len(names) == 1 and ref.genitive_from_name(next(iter(names))) == g}


def outcome(function: Callable[..., object], *args: object) -> object:
    try:
        return function(*args)
    except ValueError as e:
        return ("raises", type(e).__name__)


#: Each public naming function by its name, and how it is asked: by a key, a key and a sex.
BY_KEY: dict[str, Callable[..., object]] = {
    "canonicalize_patronymic": canonicalize_patronymic,
    "find_old_patronymic_by_modern": find_old_patronymic_by_modern,
    "father_name_for_patronymic": father_name_for_patronymic,
    "genitive_from_name": genitive_from_name,
    "get_gender_from_name": get_gender_from_name,
    "get_gender_from_old_patronymic": get_gender_from_old_patronymic,
    "validate_first_name": validate_first_name,
    "validate_old_patronymic": validate_old_patronymic,
    "validate_old_patronymic(accept_full)": lambda k: validate_old_patronymic(k, accept_full=True),  # pyright: ignore[reportUnknownLambdaType]
    "is_ignored_name": names_registry.is_ignored_name,
    "ignored_name_gender": names_registry.ignored_name_gender,
    "is_ignored_patronymic": names_registry.is_ignored_patronymic,
}
TREE_CONFLICTS: dict[str, Callable[..., object]] = {
    "tree_conflicts_given": tree_conflicts._canonical_given,  # pyright: ignore[reportPrivateUsage]
    "tree_conflicts_patronymic": tree_conflicts._canonical_patronymic,  # pyright: ignore[reportPrivateUsage]
}
BY_KEY_AND_SEX: dict[str, Callable[..., object]] = {
    "canonicalize_name": canonicalize_name,
    "matching_base": matching_base,
    "derive_patronymic": derive_patronymic,
    "derive_old_patronymic": derive_old_patronymic,
    "genitive_given_name": genitive_given_name,
}


def compare(root: Path) -> Iterator[tuple[str, str, object, object, object]]:
    """(function, key, sex, the lexicon's answer, v0.1.26's) for every question they answer differently."""
    ref = reference(root)
    by_key = BY_KEY | TREE_CONFLICTS
    with workspace.use(root):
        for key in sorted(keys(root)):
            for name, function in by_key.items():
                mine = outcome(function, key)
                theirs = outcome(getattr(ref, name.removesuffix("(accept_full)")), key,
                                 *((True,) if name.endswith("(accept_full)") else ()))
                if mine != theirs:
                    yield name, key, None, mine, theirs
            for name, function in BY_KEY_AND_SEX.items():
                for sex in SEXES:
                    mine, theirs = outcome(function, key, sex), outcome(getattr(ref, name), key, sex)
                    if mine != theirs:
                        yield name, key, sex, mine, theirs
        for key in sorted(own_genitives(root, ref)):
            if name_from_genitive(key) != ref.name_from_genitive(key):
                yield "name_from_genitive", key, None, name_from_genitive(key), ref.name_from_genitive(key)


@pytest.mark.parametrize("reverse", [False, True], ids=["file order", "reversed"])
def test_compiled_answers_equal_reference(tmp_path: Path, reverse: bool) -> None:
    root = fixture_copy(tmp_path / "ws", reverse=reverse)
    assert list(compare(root)) == []


def test_reversed_table_is_another_layer(tmp_path: Path) -> None:
    """The two orders compile into different layers — the answers row order decided are written
    into each — and each is a lexicon without a conflict."""
    straight, reversed_ = (fixture_copy(tmp_path / name, reverse=reverse)
                           for name, reverse in (("a", False), ("b", True)))
    layers = [compile_legacy(r / "names.csv", r / "names_ignore.csv", r / "patronymics_ignore.csv")
              for r in (straight, reversed_)]
    assert {k: (e.bases, e.canonical) for k, e in layers[0].names.items()} != \
           {k: (e.bases, e.canonical) for k, e in layers[1].names.items()}
    assert set(layers[0].patronymics) != set(layers[1].patronymics)
    for layer in layers:
        Lexicon.of([layer])


def test_a_shared_genitive_answers_by_the_canonical_name(tmp_path: Path) -> None:
    """Two names giving one genitive: the canonical name answers, whatever row stands first; two
    canonical ones — the first by spelling."""
    rows = [["М", "Зарон", "Заарон", "", "", "Заарона", "Зароннов", "Зароннова", "Заароновичч", "Заароновнна", ""],
            ["М", "Заарон", "", "", "", "Заарона", "Заароннов", "Заароннова", "Заароновичч", "Заароновнна", ""],
            ["М", "Шуп", "", "", "", "Шупа", "Шупов", "Шупова", "Шупович", "Шуповна", ""],
            ["М", "Шупа", "", "", "", "Шупа", "Шупин", "Шупина", "Шупич", "Шупична", ""]]
    for order, name in ((rows, "a"), (rows[::-1], "b")):
        with workspace.use(area(tmp_path / name, order)):
            assert name_from_genitive("Заарона") == "Заарон"
            assert name_from_genitive("Шупа") == "Шуп"


def test_a_sex_the_ignore_list_gives_against_the_table_is_refused(tmp_path: Path) -> None:
    """The ignore list was read first: «Зюзя» Ж there, М in the table, was Ж — a sum of entries
    cannot say that, so the table is refused rather than read otherwise."""
    root = area(tmp_path / "a", [["М", "Зюзя", "", "", "", "Зюзи", "Зюзин", "Зюзина", "Зюзич", "Зюзична", ""]],
                ignore=[("Ж", "Зюзя")])
    with pytest.raises(WorkspaceError, match="Зюзя"):
        compile_legacy(root / "names.csv", root / "names_ignore.csv", None)


def test_the_ignore_list_without_a_sex_beside_the_table(tmp_path: Path) -> None:
    """An ignored name with no sex that the table also holds has no sex,
    and keeps the table's forms."""
    root = area(tmp_path / "a", [["М", "Зюзей", "", "", "", "Зюзея", "Зюзеев", "Зюзеева", "Зюзеевич", "Зюзеевна", ""]],
                ignore=[("", "Зюзей"), ("Ж", "Кукуша")])
    with workspace.use(root):
        ref = reference(root)
        for name in ("Зюзей", "Кукуша"):
            assert get_gender_from_name(name) is ref.get_gender_from_name(name)
            assert names_registry.is_ignored_name(name) and validate_first_name(name)
            assert derive_patronymic(name, Gender.MALE) == ref.derive_patronymic(name, Gender.MALE)
        assert get_gender_from_name("Зюзей") is None and get_gender_from_name("Кукуша") is Gender.FEMALE


def test_spaces_around_sex_and_name_are_read_as_the_linter_reads_them(tmp_path: Path) -> None:
    """«М » is «М» and « Зюзей» is «Зюзей» (NCSV005/006 strip them too); a row left with no name
    or no sex is refused."""
    row = ["М ", " Зюзей", "", "", "", "Зюзея", "Зюзеев", "Зюзеева", "Зюзеевич", "Зюзеевна", ""]
    root = area(tmp_path / "a", [row])
    assert list(compile_legacy(root / "names.csv").names) == [(Gender.MALE, "Зюзей")]
    for bad, name in ((["  ", *row[1:]], "b"), ([row[0], " ", *row[2:]], "c")):
        root = area(tmp_path / name, [bad])
        with pytest.raises(WorkspaceError, match=r"names\.csv, "):
            compile_legacy(root / "names.csv")
