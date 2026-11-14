"""The res_names' transliteration is the profile `ru-v1`, our own table.

Until 0.1.0 it was the `transliterate` package (`translit(…, 'ru', reversed=True)`) behind
the 89 spellings of `names_map`. A res_name is a terraform address: a changed letter
moves every resource it names. Before the package went, the table was checked against
it on every code point, on every pair of the Cyrillic and Latin letters (the package
spells one character at a time) and on every cell of a real corpus's names table; since,
its hash holds it frozen — a new spelling is a new profile, `ru-v2`, never an edit.
Since 0.1.0 a corpus's own surnames the profile spells whole are the corpus's data
(`<corpus>/transliteration.toml`), read before the library's table.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from verso.core import workspace
from verso.core.workspace import WorkspaceError
from verso.ru.naming.transliteration import (
    PROFILES, RU_V1, RU_V2, RU_V2_FILE, TranslitProfile, cyrillic_to_latin, generate_res_name, load_profile,
    profile_data)
from tests.codepaths import child_env


def test_ru_v1_is_frozen():
    blob = json.dumps({"names": dict(RU_V1.names), "chars": dict(RU_V1.chars)}, ensure_ascii=False, sort_keys=True)
    assert hashlib.sha256(blob.encode()).hexdigest() == "d3b9047f121d4d88a1ecf418d9a089e88d4945a9d138be0a8ed44bcfd0e943f8", (
        "профиль ru-v1 заморожен: другая буква переименует ресурсы TF — заведите ru-v2")


def test_ru_v1_maps_66_characters_and_70_given_names():
    assert len(RU_V1.chars) == 66
    assert len(RU_V1.names) == 70
    assert RU_V1.name == "ru-v1"


def _corpus(tmp_path: Path, text: str | None) -> Path:
    (tmp_path / "verso.toml").write_text('schema = 2\n[corpus]\ndir = "corpus"\n', encoding="utf-8")
    (tmp_path / "corpus").mkdir()
    if text is not None:
        (tmp_path / "corpus" / "transliteration.toml").write_text(text, encoding="utf-8")
    return tmp_path


def test_a_corpus_spelling_is_read_before_the_librarys(tmp_path: Path):
    with workspace.use(_corpus(tmp_path, '[names]\n"Сорокоплехин" = "Sorokoplekhin"\n')):
        assert cyrillic_to_latin("Сорокоплехин") == "Sorokoplekhin"
        assert generate_res_name("Сорокоплехин") == "sorokoplekhin"
        # A full name is no word of the table: letter by letter, as the profile always spelled it.
        assert generate_res_name("Иван Сорокоплехин") == "ivan_sorokoplehin"
        assert cyrillic_to_latin("Яков") == "Yakov"


def test_without_the_file_the_librarys_table_alone(tmp_path: Path):
    with workspace.use(_corpus(tmp_path, None)):
        assert cyrillic_to_latin("Сорокоплехин") == "Sorokoplehin"


def test_a_corpus_spelling_edited_is_read_again(tmp_path: Path):
    # As the places and the estates: a running Verso sees an edit without a restart.
    root = _corpus(tmp_path, '[names]\n"Сорокоплехин" = "Sorokoplekhin"\n')
    path = root / "corpus" / "transliteration.toml"
    with workspace.use(root):
        assert cyrillic_to_latin("Сорокоплехин") == "Sorokoplekhin"
        path.write_text('[names]\n"Сорокоплехин" = "Sorokoplyokhin"\n', encoding="utf-8")
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        assert cyrillic_to_latin("Сорокоплехин") == "Sorokoplyokhin"
        path.unlink()
        assert cyrillic_to_latin("Сорокоплехин") == "Sorokoplehin"
        path.write_text('[names]\n"Сорокоплехин" = "Sorokoplekhin"\n', encoding="utf-8")
        os.utime(path, ns=(2_000_000_000, 2_000_000_000))
        assert cyrillic_to_latin("Сорокоплехин") == "Sorokoplekhin"


@pytest.mark.parametrize("text, said", [
    ('[names]\n"Яков" = "Jacob"\n', "Яков"),
    ('[names]\n"Сорокоплехин" = 1\n', "Сорокоплехин"),
    ('[spellings]\n', "spellings"),
])
def test_a_wrong_corpus_spelling_is_refused(tmp_path: Path, text: str, said: str):
    with workspace.use(_corpus(tmp_path, text)), pytest.raises(WorkspaceError, match=f"transliteration.toml.*{said}"):
        cyrillic_to_latin("Сорокоплехин")


def test_the_library_spells_without_transliterate(tmp_path: Path):
    code = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.partition('.')[0] == 'transliterate':\n"
        "            raise ImportError('transliterate is blocked')\n"
        "sys.meta_path.insert(0, Block())\n"
        "from verso.ru.naming.transliteration import cyrillic_to_latin\n"
        "print(cyrillic_to_latin('Плотвичкинъ'))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            cwd=tmp_path, env=child_env(), check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Plotvichkin'"


def test_ru_v1_cannot_be_edited_in_place():
    for table in (RU_V1.names, RU_V1.chars):
        with pytest.raises(TypeError):
            table["Ѳ"] = "F"  # type: ignore[index]


# ru-v2: the profile of the names a person reads — BGN/PCGN without apostrophes, as the maintainers ruled it
# on 11–12.11.2026. Its table is data of the package (naming/data/translit/ru-v2.toml), frozen by its hash.

def test_ru_v2_is_frozen():
    blob = json.dumps(profile_data(RU_V2_FILE), ensure_ascii=False, sort_keys=True)
    assert hashlib.sha256(blob.encode()).hexdigest() == "15cfd1bc4977a54b8b23018816c9b7e0ac91808df04b127efa7cf88235d9b81c", (
        "профиль ru-v2 заморожен: новая буква — новый профиль ru-v3")


def test_profiles_by_name():
    assert dict(PROFILES) == {"ru-v1": RU_V1, "ru-v2": RU_V2}
    assert RU_V2.name == "ru-v2"


def test_ru_v1_takes_the_old_path():
    table = {ord(c): latin for c, latin in RU_V1.chars.items()}
    for text in [*RU_V1.chars, *(c.lower() + "ая" for c in RU_V1.chars), "Ѳеодоръ", "Аэ́тий", "1а", "Tchoubarevа"]:
        assert RU_V1(text) == text.translate(table)
    for name, latin in RU_V1.names.items():
        assert RU_V1(name) == latin


@pytest.mark.parametrize(("text", "latin"), [
    ("Яков", "Yakov"), ("Юрий", "Yury"), ("Хохряков", "Khokhryakov"), ("Зюзин", "Zyuzin"),
    ("Дарья", "Darya"), ("Илья", "Ilya"), ("Ильич", "Ilyich"), ("Мария", "Maria"), ("Сергеевич", "Sergeevich"),
    ("Васильевич", "Vasilyevich"), ("Михайлович", "Mikhaylovich"), ("Подъячев", "Podyachev"),
    ("Щеглов", "Shcheglov"), ("Семён", "Semyon"), ("Пётр", "Pyotr"), ("Шёлков", "Sholkov"), ("Ия", "Iya"),
    ("Покровский", "Pokrovsky"), ("Елена", "Elena"),
    ("Чубарев", "Chubarev"), ("Чугайкин", "Chugaykin"),
])
def test_ru_v2_spells(text: str, latin: str):
    assert RU_V2(text) == latin


@pytest.mark.parametrize(("text", "latin"), [
    ("Семен", "Semyon"), ("Петр", "Pyotr"), ("Федор", "Fyodor"), ("Артем", "Artyom"), ("Алексей", "Alexey"),
    ("Максим", "Maxim"), ("Емельян", "Yemelyan"), ("Еремей", "Yeremey"),
    ("Семенович", "Semenovich"), ("Семен Петров", "Semyon Petrov"),
])
def test_ru_v2_whole_names_are_words(text: str, latin: str):
    """The eight whole names of 12.11 are spelled whole where they stand as a word, never inside one."""
    assert RU_V2(text) == latin


@pytest.mark.parametrize(("text", "latin"), [
    ("ЩЕГЛОВ", "SHCHEGLOV"), ("Ю.", "Yu."), ("Юрий", "Yury"), ("ЮРИЙ", "YURY"), ("щеглов", "shcheglov"),
])
def test_ru_v2_case(text: str, latin: str):
    assert RU_V2(text) == latin


@pytest.mark.parametrize(("text", "latin"), [
    ("Мария-Елена", "Maria-Elena"), ("Юрий Ильич", "Yury Ilyich"), ("Иван Большой", "Ivan Bolshoy"),
])
def test_ru_v2_word_bounds(text: str, latin: str):
    assert RU_V2(text) == latin


@pytest.mark.parametrize(("text", "latin"), [
    ("Ѳеодоръ", "Feodor"), ("Іоаннъ", "Ioann"), ("Аэ́тий", "Aety"), ("Ѵарѳоломей", "Iarfolomey"),
])
def test_ru_v2_old_letters(text: str, latin: str):
    assert RU_V2(text) == latin


@pytest.mark.parametrize(("text", "latin"), [
    ("Бутаковa", "Butakova"), ("1а", "1a"), ("Tchoubarevа", "Tchoubareva"), ("", ""), ("?", "?"),
])
def test_ru_v2_mixed_script(text: str, latin: str):
    """A Latin letter in a Cyrillic word passes as it is; a stray Cyrillic letter in a Latin one is spelled."""
    assert RU_V2(text) == latin


def test_ru_v2_ascii():
    letters = [*RU_V2.chars, *RU_V2.after_sign, *RU_V2.after_hushing, *RU_V2.final]
    for word in letters:
        for text in (word, word.upper(), "б" + word, "ь" + word, "ш" + word):
            out = RU_V2(text)
            assert re.fullmatch(r"[A-Za-z]*", out), (text, out)


def test_a_profile_file_with_an_unknown_key_is_refused(tmp_path: Path):
    path = tmp_path / "p.toml"
    path.write_text('name = "x"\n[chars]\n"а" = "a"\n[middle]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="middle"):
        load_profile(path)


def test_a_profile_without_contexts_is_the_old_path(tmp_path: Path):
    path = tmp_path / "p.toml"
    path.write_text('name = "x"\n[chars]\n"а" = "a"\n', encoding="utf-8")
    profile = load_profile(path)
    assert isinstance(profile, TranslitProfile)
    assert profile("Баба") == "Бaбa"


def test_both_roles_are_ru_v1_with_the_corpus_rules(tmp_path: Path):
    """Until `[translit]` (schema 7) names a role's profile, both roles spell as the res_names always did."""
    from verso.ru.naming.transliteration import address, display, profile_of
    root = _corpus(tmp_path, '[names]\n"Плотвичкин" = "Plotvichkin"\n')
    with workspace.use(root):
        assert profile_of("address") is RU_V1 and profile_of("display") is RU_V1
        assert address()("Плотвичкин") == display()("Плотвичкин") == "Plotvichkin"
        assert address()("Юрий") == display()("Юрий") == "Jurij"
