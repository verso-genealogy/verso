"""The six single-record reports of `facts-check` are printed from the signals a card shows.

One finding, one text: `verso.ru.cli.facts.format_signals` prints a check's findings in the words of
`verso.ru.facts.signals.signal_of` — the words a record's card says — under the check's own line of counts.
"""
from __future__ import annotations

import inspect
from calendar import Month

from verso.core import i18n
from verso.ru.cli import facts as cli
from verso.ru.cli.facts import format_signals, signal_report
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth
from verso.ru.dsl.records.deaths import death
from verso.ru.dsl.records.marriages import marriage
from verso.ru.facts.checks.dates import WithinFinding, within_entry
from verso.ru.facts.checks.lags import baptism_lags, burial_lags
from verso.ru.facts.checks.wedding_ages import wedding_age_findings
from verso.ru.facts.checks.wedding_calendar import wedding_calendar_findings
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import AssertionSet
from verso.ru.facts.signals import signal_of
from verso.ru.gender import Gender

M = Gender.MALE


def _deaths(*records) -> AssertionSet:
    return AssertionSet(facts_from_deaths([(r, "deaths_1850.py") for r in records], village="Маниловка")).believed()


def _births(*records) -> AssertionSet:
    return AssertionSet(facts_from_births([(r, "births_1850.py") for r in records], village="Маниловка")).believed()


def _weddings(*records) -> AssertionSet:
    for r in records:
        r.year = 1850
    return AssertionSet(facts_from_marriages([(r, "weddings_1850.py") for r in records], village="Маниловка")).believed()


def _died(num: int, d_day: int, b_day: int, b_month: Month = Month.MARCH, **more):
    return death(num, M, d_day, b_day, Month.MARCH, b_month, year=1850, deceased=person("Иван"), page="12об", **more)


def _born(num: int, b_day: int, k_day: int, **more):
    return birth(num, M, b_day, k_day, Month.JANUARY, Month.JANUARY, year=1850, child=person("Иван"),
                 father=person("Петр", "Иванов"), **more)


def test_the_report_says_a_finding_in_the_signal_s_words():
    lags = burial_lags(_deaths(_died(9, 3, 1, Month.APRIL)))
    [signal] = [signal_of(f) for f in lags.findings]
    report = signal_report("burial-lag", lags)
    assert f"[HIGH] {signal.said}" in report
    assert "[HIGH] Погребение 01.04.1850 — через 29 дн. после смерти 03.03.1850." in report
    assert "    deaths_1850.py №9, л. 12об" in report
    assert str(signal.why) in report


def test_an_explanation_is_printed_once_per_variant():
    lags = burial_lags(_deaths(_died(1, 3, 8), _died(2, 3, 9), _died(9, 3, 1, Month.APRIL)))
    signals = [signal_of(f) for f in lags.findings]
    report = signal_report("burial-lag", lags)
    assert len(signals) == 3 and len({s.why for s in signals}) == 2
    for why in {s.why for s in signals}:
        assert report.count(str(why)) == 1
    lines = report.splitlines()
    assert lines.index(str(signals[0].why)) < next(i for i, line in enumerate(lines) if line.startswith("["))


def test_the_helping_lines_stand_under_their_finding():
    wedding = marriage(3, 15, Month.MARCH, person("Иван", "Петров"), person("Анна", "Ильина"))
    report = signal_report("wedding-calendar", wedding_calendar_findings(_weddings(wedding)))
    lines = report.splitlines()
    at = lines.index("[HIGH] Венчание 15.03.1850 (ср) — Великий пост.")
    assert lines[at + 1:at + 4] == ["    Пасха 23.04.", "    Тот же день в соседнем месяце разрешён: 15.02.1850.",
                                    "    weddings_1850.py №3"]


def test_every_finding_is_a_line_and_a_place():
    """The reports name the records the checks found, each once, HIGH and LOW as the check judged."""
    lags = baptism_lags(_births(_born(1, 3, 20), _born(2, 3, 4), _born(7, 2, 25)))
    report = signal_report("baptism-lag", lags)
    assert [line[:5] for line in report.splitlines() if line.startswith("[")] == ["[LOW]", "[LOW]"]
    assert {"    births_1850.py №1", "    births_1850.py №7"} <= set(report.splitlines())
    assert "№2" not in report


def test_no_finding_is_the_head_alone():
    report = signal_report("baptism-lag", baptism_lags(_births(_born(2, 3, 4))))
    assert report.splitlines() == ["baptism-lag: OK — 0 findings."]


def test_a_note_s_count_is_in_the_head():
    report = signal_report("baptism-lag", baptism_lags(_births(_born(1, 3, 20, lag_note="так в подлиннике"))))
    assert report == "baptism-lag: OK — 0 findings; снято заметкой lag_note — 1."
    ages = wedding_age_findings(_weddings(marriage(1, 9, Month.JANUARY, person("Иван", "Петров"), person("Анна", "Ильина"),
                                                   groom_age=16, bride_age=18, age_note="так в подлиннике")))
    assert "снято заметкой age_note — 1" in signal_report("wedding-ages", ages)


def test_format_signals_prints_any_signals_under_any_head():
    within = [signal_of(f) for f in within_entry(_deaths(_died(4, 9, 8)))]
    assert format_signals(within, head="внутри записи:").splitlines() == [
        "внутри записи:", str(within[0].why), "", "[HIGH] Погребение 08.03.1850 раньше смерти 09.03.1850.",
        "    deaths_1850.py №4, л. 12об"]


def test_date_order_s_class_inside_one_entry_is_said_by_the_signal():
    """`date_order_report` prints the class «внутри записи» in the signal's words, under the person."""
    [found] = within_entry(_deaths(_died(4, 9, 8)))
    signal = signal_of(WithinFinding(kind=found.kind, left=found.left, right=found.right))

    class Gen:
        @staticmethod
        def canonical_profiles() -> dict[str, object]:
            return {}

    report, code = cli.date_order_report({"ivan_1": [(found.kind, "", "", found.left, found.right)]}, {}, Gen())
    assert code == 1
    assert f"      {signal.said}  [burial_before_death]  deaths_1850.py №4" in report
    assert f"      → {signal.why}" in report


def test_the_reports_speak_english():
    lags = burial_lags(_deaths(_died(9, 3, 1, Month.APRIL)))
    with i18n.use("en"):
        report = signal_report("burial-lag", lags)
    assert "[HIGH] Buried 01.04.1850, 29 days after the death on 03.03.1850." in report


def test_no_printer_of_its_own_is_left_for_any_of_the_six():
    """One function prints findings: the four `format_*` of the six checks are gone, and so are the catalog's lines
    they printed from (kept in the catalogs as deprecated keys until 0.2 — tests/test_catalog_ru.py)."""
    for name in ("format_name_days", "format_wedding_calendar", "format_lags", "format_wedding_ages"):
        assert not hasattr(cli, name), name
    source = inspect.getsource(cli)
    for key in ("cli.facts.name_days.finding", "cli.facts.name_days.lookalikes", "cli.facts.name_days.note",
                "cli.facts.wedding_calendar.note", "cli.facts.wedding_calendar.pascha",
                "cli.facts.wedding_calendar.other_months", "cli.facts.wedding_calendar.other_days",
                "cli.facts.lags.finding", "cli.facts.lags.baptism_note", "cli.facts.lags.burial_note",
                "cli.facts.wedding_ages.under_age", "cli.facts.wedding_ages.gap", "cli.facts.wedding_ages.note",
                "cli.facts.wedding_ages.groom", "cli.facts.wedding_ages.bride", "cli.facts.abbr."):
        assert key not in source, key
