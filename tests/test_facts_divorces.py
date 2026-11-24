"""A divorce record → assertions (`verso.ru.facts.extract.divorces`).

What an act of divorce says: these two were spouses, the day the marriage was
dissolved, how old each was — and, where the act names it, the day they had
married. That last one is a later document's claim about a wedding: it is an
`EventDate`, read as an external card's dates are; a text there asserts nothing.
"""
from __future__ import annotations

from calendar import Month
from pathlib import Path
from typing import Any

import pytest

import village_fixture

from verso.ru.domain import EventDate, person
from verso.ru.dsl.records.divorces import divorce
from verso.ru.facts.extract.divorces import RECORD_KIND, facts_from_divorces
from verso.ru.facts.model import (
    AgedYears, AssertionSet, Bound, DivorcedOn, FactDate, MarriedOn, NameClaim, ResidedIn, SpouseOf, Stated)


def _divorce(number: int = 1, day: int | None = 3, month: Month | None = Month.JULY, **more: Any) -> Any:
    more.setdefault("husband", person("Иванъ", "Петровъ", residence="Горюхино"))
    more.setdefault("wife", person("Анна", "Иванова", residence="Горюхино"))
    more.setdefault("year", 1925)
    return divorce(number, day, month, **more)


def _facts(*records: Any, drafts: bool = False) -> AssertionSet:
    return AssertionSet(facts_from_divorces([(r, "divorces_1925.py") for r in records], village="Горюхино",
                                            drafts=drafts))


@pytest.mark.parametrize("named, date", [
    (EventDate(1926, Month.MARCH, 14), FactDate(year=1926, month=3, day=14)),
    (EventDate(1927, Month.FEBRUARY), FactDate(year=1927, month=2)),
    (EventDate(1915), FactDate(year=1915)),
    (EventDate(1915, circa=True), FactDate(year=1915, circa=True)),
    (EventDate(1914, year_end=1915), FactDate(year=1914, bound=Bound.BETWEEN, end_year=1915)),
    (EventDate(1915, date_range="before"), FactDate(year=1915, bound=Bound.BEFORE)),
])
def test_the_wedding_an_act_names_is_its_event_date(named: EventDate, date: FactDate) -> None:
    """A point, a month, a year, «около», a range: the interval the date asserts, as an external card's is read."""
    assert {a.date for a in _facts(_divorce(marriage_date=named)).of(MarriedOn)} == {date}


@pytest.mark.parametrize("named", [EventDate(1926, None, 14), EventDate(None, Month.MARCH, 14)])
def test_a_named_wedding_with_a_day_and_no_month_or_no_year_says_no_more_than_it_can(named: EventDate) -> None:
    """A day needs its month, as for the divorce's own date; a date with no year asserts no wedding."""
    dates = {a.date for a in _facts(_divorce(marriage_date=named)).of(MarriedOn)}
    assert dates == ({FactDate(year=1926)} if named.year else set())


def test_a_wedding_written_as_text_asserts_nothing() -> None:
    """DSL v1's text is kept and exported, and no reader parses it: the layer never guesses a date."""
    with pytest.warns(DeprecationWarning):
        record = _divorce(marriage_date="24 февраля 1920")
    facts = _facts(record)
    assert facts.of(MarriedOn) == () and len(facts.of(DivorcedOn)) == 2


@pytest.mark.parametrize("value", [1926, 1926.0, ["1926"], True])
def test_a_marriage_date_that_is_no_date_names_no_wedding_and_breaks_nothing(value: Any) -> None:
    """A figure where the date belongs must not take the village's reading down with it."""
    facts = _facts(_divorce(marriage_date=value))
    assert facts.of(MarriedOn) == () and len(facts.of(DivorcedOn)) == 2


def test_a_divorce_asserts_the_couple_the_day_and_the_ages() -> None:
    facts = _facts(_divorce(husband_age=30, wife_age=27, marriage_date=EventDate(1920, Month.FEBRUARY, 24)))
    assert {a.cite.record_kind for a in facts} == {RECORD_KIND} == {"divorce"}
    assert {a.cite.locator for a in facts} == {"husband", "wife"}
    divorced = facts.of(DivorcedOn)
    assert [(a.cite.locator, a.date, a.basis) for a in divorced] == [
        ("husband", FactDate(year=1925, month=7, day=3), Stated()),
        ("wife", FactDate(year=1925, month=7, day=3), Stated())]
    husband, wife = (a.subject for a in divorced)
    assert {(a.subject, a.other) for a in facts.of(SpouseOf)} == {(husband, wife), (wife, husband)}
    assert all(a.basis == Stated() for a in facts.of(SpouseOf))
    assert [(a.cite.locator, a.date, a.basis) for a in facts.of(MarriedOn)] == [
        ("husband", FactDate(year=1920, month=2, day=24), Stated()),
        ("wife", FactDate(year=1920, month=2, day=24), Stated())]
    assert [(a.cite.locator, a.age, a.as_of, a.basis) for a in facts.of(AgedYears)] == [
        ("husband", 30, FactDate(year=1925, month=7, day=3), Stated(basis_unknown=True)),
        ("wife", 27, FactDate(year=1925, month=7, day=3), Stated(basis_unknown=True))]
    assert [a.given for a in facts.of(NameClaim)] == ["Иван", "Анна"]


def test_where_they_lived_is_of_unknown_basis() -> None:
    """The record set's defaults fill a residence in place: which of the two the act wrote is not knowable."""
    assert [(a.place, a.basis) for a in _facts(_divorce()).of(ResidedIn)] == [
        ("Горюхино", Stated(basis_unknown=True))] * 2


def test_a_divorce_dated_to_the_year_alone_is_dated_so() -> None:
    facts = _facts(_divorce(day=None, month=None, husband_age=35))
    assert {a.date for a in facts.of(DivorcedOn)} == {FactDate(year=1925)}
    assert [a.as_of for a in facts.of(AgedYears)] == [FactDate(year=1925)]


def test_an_undated_divorce_asserts_no_day_and_no_age() -> None:
    """No day, no month, no year of its own and none from a book: the act is read — its couple, its wedding — and
    dates nothing, so no age is dated by it either."""
    facts = _facts(_divorce(day=None, month=None, year=None, husband_age=30, wife_age=27, marriage_date=EventDate(1920)))
    assert facts.of(DivorcedOn) == () and facts.of(AgedYears) == ()
    assert len(facts.of(SpouseOf)) == 2 and len(facts.of(MarriedOn)) == 2


@pytest.mark.parametrize("day, month, date", [
    ("3?", Month.JULY, FactDate(year=1925, month=7)),
    (3, "июль", FactDate(year=1925)),
    ("3?", "июль", FactDate(year=1925)),
])
def test_a_divorce_dated_in_words_where_a_figure_belongs_breaks_nothing(day: Any, month: Any, date: FactDate) -> None:
    """A day or a month the DSL holds as text is not recorded, as an empty column is: the act is still read, and
    the village's reading with it."""
    facts = _facts(_divorce(day=day, month=month, husband_age=30))
    assert {a.date for a in facts.of(DivorcedOn)} == {date}
    assert [a.as_of for a in facts.of(AgedYears)] == [date]


def test_a_divorce_with_one_spouse_asserts_what_it_has() -> None:
    facts = _facts(_divorce(wife=None, husband_age=30, wife_age=27, marriage_date=EventDate(1920)))
    assert facts.of(SpouseOf) == ()
    assert [a.cite.locator for a in facts.of(DivorcedOn)] == ["husband"]
    assert [a.cite.locator for a in facts.of(MarriedOn)] == ["husband"]
    assert [a.cite.locator for a in facts.of(AgedYears)] == ["husband"]


def test_source_date_error_withdraws_the_wedding_and_keeps_the_divorce() -> None:
    facts = _facts(_divorce(marriage_date=EventDate(1925, Month.SEPTEMBER, 12), source_date_error="так в акте"))
    assert len(facts.of(MarriedOn)) == 2 and facts.believed().of(MarriedOn) == ()
    assert len(facts.believed().of(DivorcedOn)) == 2


def test_calendar_note_rides_on_the_wedding() -> None:
    facts = _facts(_divorce(marriage_date=EventDate(1913, Month.NOVEMBER, 9), calendar_note="суббота, так в акте"))
    assert {a.calendar_note for a in facts.of(MarriedOn)} == {"суббота, так в акте"}
    assert {a.calendar_note for a in _facts(_divorce(marriage_date=EventDate(1913, Month.NOVEMBER, 9))).of(MarriedOn)} == {None}


def test_an_unreviewed_divorce_asserts_nothing_and_is_read_as_a_draft() -> None:
    held = _divorce(husband_age=30, marriage_date=EventDate(1920), reviewed=False)
    assert len(_facts(held)) == 0
    assert len(_facts(held, drafts=True)) == len(_facts(_divorce(husband_age=30, marriage_date=EventDate(1920))))


def test_two_divorces_of_one_file_are_two_entries() -> None:
    facts = _facts(_divorce(1), _divorce(2))
    assert len({a.subject for a in facts}) == 4 and len(facts.records()) == 2


# --- a village's reading ---------------------------------------------------------------------------------------

DIVORCES = '''\
from calendar import Month

from verso.ru.dsl import EventDate, divorce, divorce_records, person

manilovka_divorces_1901 = divorce_records(
    "ГАРО", "9", "1", "4", "Маниловка", "", 1901,
    divorce(7, 3, Month.JULY, husband=person("Иванъ", "Петровъ", "Справкинъ"), wife=person("Анна", "Иванова"),
            marriage_date=EventDate(1901, Month.SEPTEMBER, 12)),
    divorce(8, 5, Month.JULY, husband=person("Павелъ", "Ильинъ"), wife=person("Ольга", "Петрова"),
            marriage_date=EventDate(1895, Month.FEBRUARY, 24)))
'''


@pytest.fixture
def village(tmp_path: Path) -> Path:
    manilovka = village_fixture.root(tmp_path) / "Маниловка"
    (manilovka / "1901").mkdir()
    (manilovka / "1901" / "manilovka_divorces_1901.py").write_text(DIVORCES, encoding="utf-8")
    return manilovka


def test_the_village_s_date_order_report_says_a_divorce_before_its_marriage(village: Path) -> None:
    from verso.ru.cli.facts import date_order
    report, code = date_order(village)
    assert code == 1
    assert "date-order: 1 внутри записи, 0 между записями" in report
    assert report.count("Развод 03.07.1901 раньше брака 12.09.1901, который называет акт.") == 1
    assert "Справкин Иоанн Петрович, Анна Ивановна (manilovka_divorces_1901.py №7):" in {
        line.strip() for line in report.splitlines()}
    assert "№8" not in report


def test_the_snapshot_counts_it_inside_one_entry(village: Path) -> None:
    from verso.ru.cli.facts_snapshot import findings_snapshot
    rows = dict(line.split("\t", 1) for line in findings_snapshot(village).splitlines() if "\t" in line)
    assert rows["date-order-within"] == "1\t-" and rows["date-order-across"] == "0\t-"


def test_a_divorce_is_asked_of_the_cli_by_kind_only_for_what_it_answers(village: Path, capsys: pytest.CaptureFixture[str]):
    """`--kind divorce` reads one kind's assertions for `--dump`, `--why`, `--basis-census`; the pairs report joins
    godparents, witnesses or parents, and an act of divorce names none — so it is refused, saying why."""
    from verso.ru.cli import facts as cli
    assert cli.main(["--village", str(village), "--kind", "divorce"]) == 2
    assert "--dump" in capsys.readouterr().err


UNNUMBERED = '''\
from calendar import Month

from verso.ru.dsl import EventDate, divorce, divorce_records, person

manilovka_divorces_1902 = divorce_records(
    "ГАРО", "9", "1", "5", "Маниловка", "", 1902,
    divorce(None, 3, Month.JULY, husband=person("Иванъ", "Петровъ", "Справкинъ"), wife=person("Анна", "Иванова"),
            marriage_date=EventDate(1902, Month.SEPTEMBER, 12), page="4"))
'''


def test_an_unnumbered_act_is_said_without_a_number(village: Path) -> None:
    """A book that numbers no act: the report says «без номера», never «№none»."""
    from verso.core import i18n
    from verso.ru.cli.facts import date_order
    from verso.ru.messages import t
    (village / "1902").mkdir()
    (village / "1902" / "manilovka_divorces_1902.py").write_text(UNNUMBERED, encoding="utf-8")
    report, _ = date_order(village)
    assert "none" not in report
    assert f"manilovka_divorces_1902.py {i18n.render(t('cli.facts.unnumbered'), 'ru')}" in report


def test_every_report_of_the_facts_cli_names_a_number_one_way():
    """The facts CLI prints a record's number through one helper (`_number`): an f-string `№{…record_num}` written
    anywhere else would print «№none» for an unnumbered entry again."""
    import re
    import inspect
    from verso.ru.cli import facts as cli
    source = inspect.getsource(cli)
    helper = inspect.getsource(cli._number)
    assert re.findall(r"№\{[^}]*record_num\}", source.replace(helper, "")) == []
