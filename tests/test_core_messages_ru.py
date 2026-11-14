"""The core's messages in Russian: the texts lib/tests/core checked before the core spoke
through its catalogs, verbatim — the core's tests speak English now, and a Russian workspace
Russian. Each is the message the core raises, rendered in ru."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import i18n
from verso.core.messages import t

CONFIG = Path("/w/verso.toml")

CASES = [
    (t("cli.command_twice", command="toy-hello", where=t("cli.where_plugins", first="toy", second="twin")),
     "команда «toy-hello» есть у плагинов toy и twin"),
    (t("cli.command_twice", command="tools", where=t("cli.where_core", plugin="shadow")),
     "команда «tools» есть у ядра и у плагина shadow"),
    (t("cli.no_command", command="generate-tf"), "verso: нет команды «generate-tf» — список: verso --help"),
    (t("cli.no_plugins"), "плагинов не установлено — если они в pyproject.toml, переустановите пакеты окружения"),
    (t("plugins.entry_point_fails", name="gone", value="verso_no_such_module:PLUGIN",
       error="No module named 'verso_no_such_module'"),
     "точка входа «gone» (verso_no_such_module:PLUGIN) не загружается: No module named 'verso_no_such_module'"),
    (t("plugins.not_installed", config=CONFIG, name="ru", installed="toy"),
     "/w/verso.toml: плагин «ru» не установлен — установлены: toy; если он в pyproject.toml — переустановите пакеты окружения"),
    (t("plugins.not_installed", config=CONFIG, name="ru", installed=t("plugins.none_installed")),
     "/w/verso.toml: плагин «ru» не установлен — установлены: никакие; если он в pyproject.toml — переустановите пакеты окружения"),
    (t("plugins.no_transliterator", config=CONFIG),
     "/w/verso.toml: ни один включённый плагин не даёт транслита — plugins в verso.toml"),
    (t("plugins.two_transliterators", config=CONFIG, first="toy", second="toy2"),
     "/w/verso.toml: транслит дают два плагина: toy, toy2 — оставьте один"),
    (t("plugins.two_added", name="toy", first="tests.core", second="tests.core"),
     "два плагина с именем «toy»: tests.core, tests.core"),
    (t("plugins.no_dsl", config=CONFIG), "/w/verso.toml: в рабочей области нет плагина с DSL — plugins в verso.toml"),
    (t("plugins.two_dsls", config=CONFIG, first="toy", second="twin"),
     "/w/verso.toml: DSL дают два плагина: toy, twin — в одной рабочей области один"),
    (t("places.unknown_key", where="", key="Вязовка", unknown="familio"), "«Вязовка»: неизвестный ключ «familio»"),
    (t("places.edit_moved", key="Вязовка"), "правка изменила место «Вязовка»"),
    (t("records.decode.no_derived_field", path="book", cls="Notes", key="'shelf'"),
     "book: у Notes нет выведенного поля 'shelf'"),
    (t("records.decode.unknown_set", path="x", node="'births'"), "x: неизвестный вид набора 'births'"),
    (t("workspace.not_found", start="/tmp", env="VERSO_WORKSPACE"),
     "рабочая область не найдена от /tmp: запустите из checkout данных или задайте VERSO_WORKSPACE"),
    (t("places.unsafe_at", where="p: ", key="А", problem=t("places.unsafe", name="city", found=", ".join(
        str(t(k)) for k in ("places.unsafe_quote", "places.unsafe_interpolation")))),
     "p: «А»: в поле «city» кавычка, «${» — в HCL так нельзя, перепишите значение"),
]


@pytest.mark.parametrize("message, text", CASES, ids=[m.key for m, _ in CASES])
def test_the_core_speaks_russian_as_before(message: i18n.Message, text: str):
    with i18n.use("ru"):
        assert str(message) == text


def test_the_ru_catalog_translates_every_key():
    assert i18n.untranslated("verso.core", "ru") == frozenset()
    assert set(i18n.catalog("verso.core", "ru")) == set(i18n.catalog("verso.core", "en"))
