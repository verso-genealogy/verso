"""A counted noun agrees with its number, in English («1 birth», «2 births») and in Russian («1 запись»,
«2 записи», «5 записей»): a message counts by its `count`, and a message with two counts takes each as a
counted phrase of its own (`counted.*`)."""
from __future__ import annotations

import pytest

from verso.core import i18n
from verso.ru.messages import t


def _say(lang: str, key: str, **params: object) -> str:
    with i18n.use(lang):
        return str(t(key, **params))


def _counted(key: str, n: int):
    return t(f"counted.{key}", count=n)


@pytest.mark.parametrize(("lang", "n", "said"), [
    ("en", 1, "1 file, 1 record → out"), ("en", 2, "2 files, 2 records → out"),
    ("ru", 1, "1 файл, 1 запись → out"), ("ru", 3, "3 файла, 3 записи → out"),
    ("ru", 5, "5 файлов, 5 записей → out"), ("ru", 21, "21 файл, 21 запись → out"),
])
def test_export_records_counts_files_and_records(lang: str, n: int, said: str):
    assert _say(lang, "cli.export_records.done", files=_counted("files", n), records=_counted("records", n),
                target="out") == said


@pytest.mark.parametrize(("lang", "n", "said"), [
    ("en", 1, "N [n] — 1 estate in 1 record:"), ("en", 2, "N [n] — 2 estates in 2 records:"),
    ("ru", 2, "N [n] — 2 сословия в 2 записях:"), ("ru", 5, "N [n] — 5 сословий в 5 записях:"),
    ("ru", 1, "N [n] — 1 сословие в 1 записи:"),
])
def test_estate_conflicts_counts_estates_and_records(lang: str, n: int, said: str):
    assert _say(lang, "consolidation.estate_conflicts.finding", name="N", res_name="n",
                estates=_counted("estates", n), in_records=_counted("in_records", n)) == said


@pytest.mark.parametrize(("lang", "n", "said"), [
    ("en", 1, "name-days: OK — 0 findings of 1 birth."), ("en", 7, "name-days: OK — 0 findings of 7 births."),
    ("ru", 1, "name-days: OK — 0 findings из 1 рождения."), ("ru", 7, "name-days: OK — 0 findings из 7 рождений."),
])
def test_name_days_counts_the_births_it_checked(lang: str, n: int, said: str):
    assert _say(lang, "cli.facts.name_days.ok", of_births=_counted("of_births", n), tail="", noted="") == said


@pytest.mark.parametrize(("lang", "key", "n", "said"), [
    ("en", "cli.svyatcy.written", 1, "f: 1 row"), ("en", "cli.svyatcy.written", 2, "f: 2 rows"),
    ("ru", "cli.svyatcy.written", 1, "f: 1 строка"), ("ru", "cli.svyatcy.written", 2, "f: 2 строки"),
    ("ru", "cli.svyatcy.written", 11, "f: 11 строк"),
    ("en", "cli.facts.dumped", 1, "1 assertion → f"), ("ru", "cli.facts.dumped", 4, "4 утверждения → f"),
])
def test_a_message_counts_by_its_count(lang: str, key: str, n: int, said: str):
    assert _say(lang, key, count=n, out="f", path="f") == said


def test_a_span_of_one_day_is_a_day():
    from verso.ru.cli.facts import _span
    with i18n.use("en"):
        assert (_span(1), _span(3)) == ("1 day", "3 days")
    with i18n.use("ru"):
        assert _span(1) == "1 дн."
