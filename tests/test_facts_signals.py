"""The six single-record checks asked of ONE record — `verso.ru.facts.signals`.

A record on its card is read alone: no village, no consolidation, reviewed or not. `signals_of` asks it the
checks `facts-check` asks a village — the same functions, the same thresholds — and says each finding as a
`Signal`: a message of the catalog and its params, how sure, where, and the field that stands it down.
"""
from __future__ import annotations

from calendar import Month
from typing import Any

import pytest

from verso.core import i18n
from verso.ru.church_calendar.paschalion import wedding_ban
from verso.ru.church_calendar.svyatcy import Commemorated, Svyatcy
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, christening
from verso.ru.dsl.records.deaths import death
from verso.ru.dsl.records.divorces import divorce
from verso.ru.dsl.records.marriages import marriage
from verso.ru.facts.checks.dates import orderings, within_entry, within_orderings
from verso.ru.facts.checks.lags import baptism_lags, burial_lags
from verso.ru.facts.checks.name_days import name_day_findings
from verso.ru.facts.checks.wedding_ages import wedding_age_findings
from verso.ru.facts.checks.wedding_calendar import wedding_calendar_findings
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import AssertionSet
from verso.ru.facts.signals import CHECKS, STAND_DOWN, Signal, Signals, signal_of, signals_of
from verso.ru.gender import Gender
from verso.ru.messages import t

M, F = Gender.MALE, Gender.FEMALE
RID = "r1:Маниловка/1-1-1/1850/marriage/3"

_SVYATCY = Svyatcy([
    Commemorated(gender=F, headword="Екатерина", name="Екатерина", dates=((11, 24),)),
    Commemorated(gender=M, headword="Симеон", name="Симеон", dates=((9, 1),)),
    Commemorated(gender=M, headword="Симон", name="Симон", dates=((5, 10),)),
    Commemorated(gender=M, headword="Иоанн", name="Иоанн", dates=((5, 8),)),
])


def _wedding(day: int = 1, month: Month = Month.DECEMBER, year: int | None = 1850, **more):
    rec = marriage(3, day, month, person("Иван", "Петров"), person("Анна", "Ильина"), **more)
    rec.year = year
    return rec


def _born(b_day: int, k_day: int, b_month: Month, k_month: Month | None = None, name: str = "Иван", gender: Gender = M,
          **more):
    return birth(1, gender, b_day, k_day, b_month, k_month or b_month, year=1850,
                 child=person(name), father=person("Петр", "Иванов"), **more)


def _died(d_day: int, b_day: int, d_month: Month, b_month: Month | None = None, **more):
    return death(1, M, d_day, b_day, d_month, b_month or d_month, year=1850, deceased=person("Иван"), **more)


def _divorced(married: str | None = None, **more):
    return divorce(1, 3, Month.JULY, person("Иван", "Петров"), person("Анна", "Ильина"), marriage_date=married,
                   year=1925, **more)


def _of(check: str, record: object, **more) -> list[Signal]:
    return [s for s in signals_of(record, record_id=RID, svyatcy=_SVYATCY, **more).found if s.check == check]


def _open_day() -> tuple[int, Month]:
    """A day of January 1850 on which the Church married: no ban at all."""
    day = next(d for d in range(8, 32) if wedding_ban(1850, 1, d) is None)
    return day, Month.JANUARY


# --- the shape ------------------------------------------------------------------------------------------

def test_a_wedding_in_the_nativity_fast_is_a_strict_signal():
    [s] = _of("wedding-calendar", _wedding())
    assert (s.variant, s.confidence, s.stand_down) == ("strict", "HIGH", "calendar_note")
    assert s.key == "facts.signal.wedding_calendar.strict"
    assert s.why.key == "facts.signal.wedding_calendar.strict_why"
    assert (s.record, s.locator) == (RID, "")
    assert s.said.params["date"] == "01.12.1850"
    assert s.cite.record_num == "3"


def test_the_checks_and_the_fields_that_stand_them_down():
    assert CHECKS == ("wedding-calendar", "name-days", "baptism-lag", "burial-lag", "wedding-ages", "date-order")
    assert STAND_DOWN == {"wedding-calendar": "calendar_note", "name-days": "calendar_note",
                          "baptism-lag": "lag_note", "burial-lag": "lag_note",
                          "wedding-ages": "age_note", "date-order": "source_date_error"}


def test_a_divorce_before_the_marriage_its_act_names_is_said_once():
    [s] = signals_of(_divorced("12 сентября 1925"), record_id=RID).found
    assert (s.check, s.variant, s.confidence, s.locator, s.stand_down) == (
        "date-order", "divorce_before_marriage", "HIGH", "husband", "source_date_error")
    assert s.said.params == {"left": "03.07.1925", "right": "12.09.1925"}
    assert i18n.render(s.said, "ru") == "Развод 03.07.1925 раньше брака 12.09.1925, который называет акт."
    assert signals_of(_divorced("12 сентября 1925", source_date_error="так в акте"), record_id=RID).found == ()
    assert signals_of(_divorced("12 сентября 1924"), record_id=RID).found == ()


def test_the_church_wedding_a_divorce_names_is_asked_of_the_calendar():
    [s] = signals_of(_divorced("1 декабря 1915"), record_id=RID).found
    assert (s.check, s.variant, s.confidence, s.stand_down) == ("wedding-calendar", "strict", "HIGH", "calendar_note")
    assert s.cite.record_kind == "divorce"
    assert signals_of(_divorced("1 декабря 1915", calendar_note="так в акте"), record_id=RID).found == ()
    # a marriage of the registry's years is no church wedding: the calendar is not asked past 1917
    assert signals_of(_divorced("1 декабря 1924"), record_id=RID).found == ()


def test_a_held_divorce_answers_like_a_reviewed_one():
    held = signals_of(_divorced("12 сентября 1925", reviewed=False), record_id=RID).found
    assert [s.variant for s in held] == ["divorce_before_marriage"]


def test_high_comes_before_low_then_the_order_of_the_checks():
    """A wedding in a fast (HIGH), its spouses far apart (LOW) and the bride under age (HIGH)."""
    found = signals_of(_wedding(groom_age=50, bride_age=14), record_id=RID).found
    assert [(s.check, s.variant, s.confidence) for s in found] == [
        ("wedding-calendar", "strict", "HIGH"), ("wedding-ages", "under_age", "HIGH"), ("wedding-ages", "age_gap", "LOW")]


def test_only_the_checks_asked():
    record = _wedding(groom_age=16, bride_age=18)
    assert {s.check for s in signals_of(record, record_id=RID, checks=["wedding-ages"]).found} == {"wedding-ages"}
    assert signals_of(record, record_id=RID, checks=[]).found == ()


def test_a_check_no_one_knows_is_refused():
    with pytest.raises(ValueError):
        signals_of(_wedding(), record_id=RID, checks=["birth-claims"])


# --- each check, each variant ---------------------------------------------------------------------------

def test_a_strict_ban_names_the_same_day_a_month_either_side():
    [s] = _of("wedding-calendar", _wedding())
    assert t("facts.signal.wedding_calendar.other_months", dates="01.11.1850") in s.details


def test_a_movable_ban_names_pascha():
    """15 March 1850 is in Great Lent: Pascha was 23 April."""
    [s] = _of("wedding-calendar", _wedding(15, Month.MARCH))
    assert t("facts.signal.wedding_calendar.pascha", date="23.04") in s.details


def test_the_loose_bans_explanation_names_every_loose_ban():
    """Tuesdays, Thursdays, Saturdays, the eves of feasts — and Meatfare Sunday, which the check also holds loose."""
    for lang, word in (("ru", "мясопустное воскресенье"), ("en", "Meatfare Sunday")):
        assert word in str(i18n.catalog("verso.ru", lang)["facts.signal.wedding_calendar.loose_why"])


def test_a_weekday_the_church_did_not_marry_on_is_a_loose_signal():
    day = next(d for d in range(8, 32) if (ban := wedding_ban(1850, 1, d)) is not None and not ban.strict)
    [s] = _of("wedding-calendar", _wedding(day, Month.JANUARY))
    assert (s.variant, s.confidence, s.key) == ("loose", "LOW", "facts.signal.wedding_calendar.loose")


def test_a_wedding_on_an_open_day_gives_nothing():
    assert _of("wedding-calendar", _wedding(*_open_day())) == []


def test_calendar_note_stands_the_wedding_down():
    assert _of("wedding-calendar", _wedding(calendar_note="так в подлиннике")) == []


def test_a_name_far_from_its_saint():
    [s] = _of("name-days", _born(15, 16, Month.MAY, name="Екатерина", gender=F))
    assert (s.variant, s.confidence, s.locator, s.stand_down) == ("far", "LOW", "child", "calendar_note")
    assert (s.said.params["name"], s.said.params["nearest"]) == ("Екатерина", "24.11")


def test_a_look_alike_kept_in_the_window_makes_it_high():
    """«Симон», born 28 August: Симеон Столпник is kept on 1 September."""
    [s] = _of("name-days", _born(28, 29, Month.AUGUST, name="Симон"))
    assert (s.variant, s.confidence) == ("lookalike", "HIGH")
    assert [d.key for d in s.details] == ["facts.signal.name_days.lookalikes"]
    assert "Симеон" in str(s.details[0].params["names"])


def test_calendar_note_stands_the_name_down():
    assert _of("name-days", _born(15, 16, Month.MAY, name="Екатерина", gender=F, calendar_note="так в подлиннике")) == []


def test_a_late_christening():
    [s] = _of("baptism-lag", _born(3, 20, Month.JANUARY))
    assert (s.variant, s.confidence, s.locator, s.stand_down) == ("late", "LOW", "child", "lag_note")
    assert (s.said.params["born"], s.said.params["christened"], s.said.params["days"]) == ("03.01.1850", "20.01.1850", 17)


def test_a_christening_carried_into_the_next_month_is_high():
    [s] = _of("baptism-lag", _born(20, 5, Month.JANUARY, Month.FEBRUARY))
    assert (s.variant, s.confidence) == ("month_carried", "HIGH")


def test_a_late_burial_and_a_very_late_one():
    [late] = _of("burial-lag", _died(3, 8, Month.MARCH))
    [very] = _of("burial-lag", _died(3, 1, Month.MARCH, Month.APRIL))
    assert (late.variant, late.confidence, late.locator, late.stand_down) == ("late", "LOW", "deceased", "lag_note")
    assert (very.variant, very.confidence, very.said.params["days"]) == ("very_late", "HIGH", 29)


def test_lag_note_stands_a_lag_down():
    assert _of("baptism-lag", _born(3, 20, Month.JANUARY, lag_note="так в подлиннике")) == []
    assert _of("burial-lag", _died(3, 1, Month.MARCH, Month.APRIL, lag_note="так в подлиннике")) == []


def test_an_under_age_groom_and_bride():
    [groom] = _of("wedding-ages", _wedding(groom_age=16, bride_age=18))
    [bride] = _of("wedding-ages", _wedding(groom_age=25, bride_age=14))
    assert (groom.variant, groom.confidence, groom.locator, groom.key) == (
        "under_age", "HIGH", "groom", "facts.signal.wedding_ages.under_age_groom")
    assert (bride.locator, bride.key, bride.said.params["minimum"]) == ("bride", "facts.signal.wedding_ages.under_age_bride", 16)
    assert groom.stand_down == "age_note"


def test_spouses_far_apart():
    [s] = _of("wedding-ages", _wedding(groom_age=45, bride_age=20))
    assert (s.variant, s.confidence, s.locator, s.said.params["years"]) == ("age_gap", "LOW", "", "25")
    with i18n.use("ru"):
        assert str(s.said) == "Жениху «45», невесте «20»: разница в возрасте — 25."


def test_age_note_stands_the_ages_down():
    assert _of("wedding-ages", _wedding(groom_age=16, bride_age=18, age_note="так в подлиннике")) == []


def test_a_christening_before_the_birth():
    [s] = _of("date-order", _born(18, 11, Month.OCTOBER))
    assert (s.variant, s.confidence, s.locator, s.stand_down) == ("baptism_before_birth", "HIGH", "child", "source_date_error")
    assert s.key == "facts.signal.date_order.baptism_before_birth"
    assert s.why.key == "facts.date_order.hint.baptism_before_birth"
    assert (s.said.params["left"], s.said.params["right"]) == ("11.10.1850", "18.10.1850")


def test_a_burial_before_the_death_and_its_retraction():
    [s] = _of("date-order", _died(9, 8, Month.MARCH))
    assert (s.variant, s.stand_down) == ("burial_before_death", "source_date_error")
    assert _of("date-order", _died(9, 8, Month.MARCH, source_date_error="так в подлиннике")) == []


def test_only_the_orderings_a_retraction_answers_name_a_field():
    """`source_date_error=` withdraws a christening, a burial or the marriage an act of divorce names: no other
    ordering has a field of its own."""
    from verso.ru.facts.signals import DATE_ORDER_STOOD_DOWN
    assert DATE_ORDER_STOOD_DOWN == {"baptism_before_birth", "burial_before_death", "divorce_before_marriage"}
    assert DATE_ORDER_STOOD_DOWN <= {kind for _l, _r, kind, _e, _w in (*orderings(), *within_orderings())}


# --- what a record alone is, and is not -----------------------------------------------------------------

def test_an_unreviewed_record_is_read():
    assert _of("wedding-calendar", _wedding(reviewed=False))


def test_the_book_s_year_dates_a_record_that_writes_none_and_is_not_left_on_it():
    record = _wedding(year=None)
    assert _of("wedding-calendar", record) == []
    [s] = _of("wedding-calendar", record, book_year=1850)
    assert s.said.params["date"] == "01.12.1850"
    assert record.year is None


@pytest.mark.parametrize("record", [
    _wedding(0),                                                  # no day
    _wedding(None),                                               # no day at all
    _wedding(year=1925),                                          # after the church books
    _died(30, 31, Month.FEBRUARY),                                # days February does not have: DBD002's, no signal
    _born(30, 31, Month.APRIL),
    christening(1, M, 16, Month.APRIL, age=11, child=person("Иван"), father=person("Петр", "Иванов")),
], ids=["day-0", "no-day", "1925", "30-february", "31-april", "christening"])
def test_dates_the_rules_do_not_ask(record):
    got = signals_of(record, record_id=RID, svyatcy=_SVYATCY)
    assert got == Signals((), ())


def test_more_dates_the_rules_do_not_ask():
    """A wedding with no month, ages no one can count, a birth with no day, a christening in the next year: nothing
    raises, and no check invents a finding."""
    no_month = marriage(3, 1, None, person("Иван", "Петров"), person("Анна", "Ильина"), groom_age=16, bride_age=18)
    no_month.year = 1850
    assert {s.check for s in signals_of(no_month, record_id=RID).found} == {"wedding-ages"}
    for age in ("лет", "", "17 л 9 мес"):               # no age to count, and one inside the half-year the books allow
        text_age = _wedding(*_open_day(), groom_age=age, bride_age=18)
        assert signals_of(text_age, record_id=RID).found == ()
    # …while an age that CAN be counted is judged as the rule judges it, however it is spelt: a groom of «полгода»
    [half] = signals_of(_wedding(*_open_day(), groom_age="полгода", bride_age=18), record_id=RID, checks=["wedding-ages"]).found
    assert (half.variant, half.locator, half.said.params["age"]) == ("under_age", "groom", "полгода")
    no_birth_day = _born(None, 20, Month.JANUARY)
    assert _of("baptism-lag", no_birth_day) == [] and _of("date-order", no_birth_day) == []
    next_year = birth(1, M, 30, 2, Month.DECEMBER, Month.JANUARY, year=1850, k_year=1851, child=person("Иван"),
                      father=person("Петр", "Иванов"))
    assert _of("date-order", next_year) == [] and _of("baptism-lag", next_year) == []


def test_the_record_is_never_changed_while_it_is_read(monkeypatch):
    """A card's adapter may be writing the same object out while it is asked: the book's year dates a COPY."""
    import verso.ru.facts.signals as module

    record = _wedding(year=None)
    seen: list[object] = []

    def spying(items: Any, **kwargs: Any) -> Any:
        seen.append(record.year)
        return facts_from_marriages(items, **kwargs)

    def extractor(_record: object) -> Any:
        return spying

    monkeypatch.setattr(module, "extractor_of", extractor)
    [signal] = [s for s in signals_of(record, record_id=RID, book_year=1850).found if s.check == "wedding-calendar"]
    assert signal.said.params["date"] == "01.12.1850"
    assert seen == [None] and record.year is None


def test_a_signal_has_no_shortcut_to_one_message_s_params():
    """`said`, `why` and each of `details` carry their own params; a shortcut to `said`'s alone would leave a page
    rendering «{limit}» raw in `why`."""
    [s] = _of("burial-lag", _died(3, 8, Month.MARCH))
    assert not hasattr(s, "params") and not hasattr(s, "why_key")
    assert (s.key, s.said.key, s.why.key) == ("facts.signal.burial_lag.late",) * 2 + ("facts.signal.burial_lag.late_why",)
    assert s.why.params == {"limit": 3}


def test_the_variant_and_the_level_of_a_burial_are_one_judgement():
    """`very_late` is the check's HIGH, read off the finding — never a second comparison with the threshold."""
    for d_day, b_day, b_month in ((3, 8, Month.MARCH), (3, 13, Month.MARCH), (3, 1, Month.APRIL)):
        [s] = _of("burial-lag", _died(d_day, b_day, Month.MARCH, b_month))
        assert (s.variant == "very_late") == (s.confidence == "HIGH")


def test_a_civil_register_s_second_date_is_no_christening_and_no_burial():
    late_birth, late_death = _born(3, 20, Month.JANUARY), _died(3, 1, Month.MARCH, Month.APRIL)
    late_birth.civil = late_death.civil = True
    assert _of("baptism-lag", late_birth) == [] and _of("burial-lag", late_death) == []


@pytest.mark.parametrize("other", [object(), person("Иван"), None])
def test_what_is_no_metric_record_gives_nothing(other):
    assert signals_of(other, record_id=RID) == Signals((), ())


# --- one translation, one text --------------------------------------------------------------------------

def test_signal_of_is_the_one_translation():
    """`signals_of` is the six checks on the record's assertions, each finding said by `signal_of`."""
    wedding = _wedding(groom_age=50, bride_age=14)
    facts = AssertionSet(facts_from_marriages([(wedding, "")], village="", drafts=True, ids=lambda _r: RID)).believed()
    expected = [*wedding_calendar_findings(facts).findings, *wedding_age_findings(facts).findings]
    assert set(map(repr, signals_of(wedding, record_id=RID).found)) == {repr(signal_of(f, record=RID)) for f in expected}

    born = _born(18, 11, Month.MAY, name="Екатерина", gender=F)
    facts = AssertionSet(facts_from_births([(born, "")], village="", drafts=True, ids=lambda _r: RID)).believed()
    expected = [*name_day_findings(facts, _SVYATCY).findings, *baptism_lags(facts).findings, *within_entry(facts)]
    assert len(expected) == 2
    assert set(map(repr, signals_of(born, record_id=RID, svyatcy=_SVYATCY).found)) == {
        repr(signal_of(f, record=RID)) for f in expected}

    died = _died(3, 1, Month.MARCH, Month.APRIL)
    facts = AssertionSet(facts_from_deaths([(died, "")], village="", drafts=True, ids=lambda _r: RID)).believed()
    assert [repr(s) for s in signals_of(died, record_id=RID).found] == [
        repr(signal_of(f, record=RID)) for f in burial_lags(facts).findings]


def _every_signal() -> list[Signal]:
    records = [
        _wedding(), _wedding(15, Month.MARCH), _wedding(groom_age=16, bride_age=18), _wedding(groom_age=25, bride_age=14),
        _wedding(groom_age=45, bride_age=20),
        _wedding(next(d for d in range(8, 32) if (b := wedding_ban(1850, 1, d)) is not None and not b.strict), Month.JANUARY),
        _born(15, 16, Month.MAY, name="Екатерина", gender=F), _born(28, 29, Month.AUGUST, name="Симон"),
        _born(3, 20, Month.JANUARY), _born(20, 5, Month.JANUARY, Month.FEBRUARY), _born(18, 11, Month.OCTOBER),
        _died(3, 8, Month.MARCH), _died(3, 1, Month.MARCH, Month.APRIL), _died(9, 8, Month.MARCH),
        _divorced("12 сентября 1925"), _divorced("1 декабря 1915"),
    ]
    return [s for r in records for s in signals_of(r, record_id=RID, svyatcy=_SVYATCY).found]


def test_every_signal_has_its_text_in_both_catalogs():
    said = [m for s in _every_signal() for m in (s.said, s.why, *s.details)]
    assert {s.key for s in _every_signal()} >= {
        "facts.signal.wedding_calendar.strict", "facts.signal.wedding_calendar.loose", "facts.signal.name_days.far",
        "facts.signal.name_days.lookalike", "facts.signal.baptism_lag.late", "facts.signal.baptism_lag.month_carried",
        "facts.signal.burial_lag.late", "facts.signal.burial_lag.very_late", "facts.signal.wedding_ages.under_age_groom",
        "facts.signal.wedding_ages.under_age_bride", "facts.signal.wedding_ages.age_gap",
        "facts.signal.date_order.baptism_before_birth", "facts.signal.date_order.burial_before_death",
        "facts.signal.date_order.divorce_before_marriage"}
    for lang in ("ru", "en"):
        catalog = i18n.catalog("verso.ru", lang)
        for message in said:
            assert message.key in catalog, f"{lang}: {message.key}"
            assert message.package == "verso.ru"
            text = i18n.render(message, lang)
            assert text and "{" not in text, f"{lang}: {message.key} → {text}"
    for _left, _right, kind, _event, _reference in (*orderings(), *within_orderings()):   # those no sample here reaches
        for lang in ("ru", "en"):
            assert f"facts.signal.date_order.{kind}" in i18n.catalog("verso.ru", lang)


#: Every message of a signal: `facts.signal.<check>.<name>`. The code builds the key (tests/test_catalog_ru.py lets
#: the family through as computed), so the catalogs are held to this table here — no key missing, none left over.
SIGNAL_KEYS = {
    "note_default",
    *(f"wedding_calendar.{n}" for n in ("strict", "strict_why", "loose", "loose_why", "pascha", "other_months", "other_days")),
    *(f"name_days.{n}" for n in ("far", "far_why", "lookalike", "lookalike_why", "lookalikes")),
    *(f"baptism_lag.{n}" for n in ("late", "late_why", "month_carried", "month_carried_why")),
    *(f"burial_lag.{n}" for n in ("late", "late_why", "very_late", "very_late_why")),
    *(f"wedding_ages.{n}" for n in ("under_age_groom", "under_age_bride", "under_age_why", "age_gap", "age_gap_why")),
    *(f"date_order.{kind}" for _l, _r, kind, _e, _w in (*orderings(), *within_orderings())),
}


def test_the_catalogs_hold_the_signals_messages_and_no_other():
    for lang in ("ru", "en"):
        held = {key.removeprefix("facts.signal.") for key in i18n.catalog("verso.ru", lang) if key.startswith("facts.signal.")}
        assert held == SIGNAL_KEYS, lang
    used = {m.key.removeprefix("facts.signal.") for s in _every_signal() for m in (s.said, s.why, *s.details)
            if m.key.startswith("facts.signal.")}
    assert used <= SIGNAL_KEYS
    # what no sample above reaches: the nine orderings a metric record cannot break inside itself, a weekday's open days
    assert SIGNAL_KEYS - used - {"note_default"} <= {
        "wedding_calendar.other_days", *(f"date_order.{k}" for _l, _r, k, _e, _w in orderings())}


def test_a_signal_s_params_are_plain_values():
    """A card says a signal from its key and params in a browser: text and whole numbers only, no format left to guess."""
    for s in _every_signal():
        for message in (s.said, s.why, *s.details):
            assert all(type(v) in (str, int) for v in message.params.values()), (message.key, message.params)


def test_the_note_s_default_text_is_content():
    for lang in ("ru", "en"):
        assert str(i18n.catalog("verso.ru", lang)["facts.signal.note_default"]) == "так в подлиннике"
