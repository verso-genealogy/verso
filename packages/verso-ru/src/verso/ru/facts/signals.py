"""The checks one record answers alone, and how a finding of theirs is said.

`verso facts --check` asks a village; a record on its card is one entry, read before
anyone has reviewed it and with no consolidation to say who its people are. Six
of the checks need nothing more than that entry — a wedding on a day the Church
did not marry, a name no saint near the birth supports, a christening or a
burial too late, an age at the wedding the law cannot hold, two dates the
entry itself orders wrongly — and `signals_of` asks them of it: the same
functions of `verso.ru.facts.checks`, the same thresholds, the entry read
whether it is reviewed or not (a card is where it gets reviewed).

A finding is said ONCE. `signal_of` turns what a check found into a `Signal` —
a message of the catalog with plain params, why it is worth a second look, the
lines that help the re-reading, how sure, and the field of the record that
stands it down — and both the card and the report of `verso facts --check` say it from
there (`verso.ru.cli.facts.format_signals`). A signal is a prompt to look at
the scan again; it refuses nothing.

Not here: every check that compares records — two births of one person, two
fathers, a roll against a metric book. Those need the people folded first.
"""
from __future__ import annotations

import copy
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from verso.ru.church_calendar.julian import JulianDate
from verso.ru.church_calendar.paschalion import pascha
from verso.ru.church_calendar.svyatcy import Svyatcy, load_svyatcy
from verso.ru.facts.checks.dates import WithinFinding, within_entry
from verso.ru.facts.checks.lags import BAPTISM_DAYS, BURIAL_DAYS, BURIAL_HIGH_DAYS, LagFinding, baptism_lags, burial_lags
from verso.ru.facts.checks.name_days import AFTER, BEFORE, NameDayFinding, name_day_findings
from verso.ru.facts.checks.wedding_ages import GAP_YEARS, WeddingAgeFinding, wedding_age_findings
from verso.ru.facts.checks.wedding_calendar import WeddingFinding, wedding_calendar_findings, weekday_name
from verso.ru.facts.extract.one import Extract, extractor_of
from verso.ru.facts.model import AssertionSet, Citation, FactDate
from verso.ru.messages import PACKAGE, Message

#: The checks a record answers alone, in the order a card lists them.
CHECKS: tuple[str, ...] = ("wedding-calendar", "name-days", "baptism-lag", "burial-lag", "wedding-ages", "date-order")
#: check → the key of the record's `written` that stands its findings down («так в подлиннике»).
STAND_DOWN: dict[str, str] = {
    "wedding-calendar": "calendar_note", "name-days": "calendar_note",
    "baptism-lag": "lag_note", "burial-lag": "lag_note",
    "wedding-ages": "age_note", "date-order": "source_date_error"}
#: The orderings `source_date_error=` answers: it withdraws a christening or a burial, and nothing else.
DATE_ORDER_STOOD_DOWN = frozenset({"baptism_before_birth", "burial_before_death"})
#: The bans that move with Pascha: a reader checks them against the year's.
_MOVABLE_BANS = frozenset({"cheesefare_week", "great_lent", "bright_week", "apostles_fast", "meatfare_sunday"})

type Finding = WeddingFinding | NameDayFinding | LagFinding | WeddingAgeFinding | WithinFinding


def _said(key: str, params: Mapping[str, str | int] | None = None) -> Message:
    """A message of the plugin's catalog as data: its key and its params — text and whole numbers only, so a page
    says it from its own copy of the catalog as the report says it from this one."""
    return Message(PACKAGE, key, dict(params or {}))


@dataclass(frozen=True)
class Signal:
    """One finding of one check on one record."""
    check: str                      # one of CHECKS
    variant: str                    # which finding of the check
    confidence: str                 # "HIGH" | "LOW" — the finding's own, not re-judged
    record: str                     # the record's id, as the caller named it
    locator: str                    # the slot it is about: "child", "groom", "bride", "deceased"; "" — the entry
    said: Message                      # what is wrong
    why: Message                       # why it is worth a second look
    details: tuple[Message, ...]       # lines that help the re-reading: an open day beside, a look-alike name
    stand_down: str | None          # the key of `written` that stands it down; None where no field does
    cite: Citation                  # where it was read: the file, the number, the leaf

    @property
    def key(self) -> str:
        """The key of what it says — what names this kind of signal. Its params are `said`'s; `why` and each of
        `details` are messages of their own, with params of their own."""
        return self.said.key


@dataclass(frozen=True)
class Signals:
    found: tuple[Signal, ...]       # HIGH before LOW, then in the order of CHECKS
    unanswered: tuple[str, ...]     # the checks that could not be asked: no names table, a record that does not build


def _dmy(day: JulianDate | None) -> str:
    return f"{day[2]:02d}.{day[1]:02d}.{day[0]}" if day else "—"


def _dm(month: int, day: int) -> str:
    return f"{day:02d}.{month:02d}"


def _date(date: FactDate) -> str:
    """A date to the day as a card writes one; anything vaguer as the model prints it."""
    if date.bound is None and date.year is not None and date.month is not None and date.day is not None:
        return _dmy((date.year, date.month, date.day))
    return str(date)


def _key(check: str, name: str) -> str:
    return f"facts.signal.{check.replace('-', '_')}.{name}"


def _wedding(f: WeddingFinding) -> tuple[str, str, Message, Message, tuple[Message, ...]]:
    variant = "strict" if f.ban.strict else "loose"
    details: list[Message] = []
    if f.ban.kind in _MOVABLE_BANS:
        details.append(_said(_key("wedding-calendar", "pascha"), {"date": _dm(*pascha(f.day[0]))}))
    if f.other_months:
        details.append(_said(_key("wedding-calendar", "other_months"), {"dates": ", ".join(map(_dmy, f.other_months))}))
    if f.other_days:
        details.append(_said(_key("wedding-calendar", "other_days"), {
            "dates": ", ".join(f"{_dm(m, d)} ({weekday_name((y, m, d))})" for y, m, d in f.other_days)}))
    said = _said(_key("wedding-calendar", variant),
                {"date": _dmy(f.day), "weekday": weekday_name(f.day), "ban": f.ban.label})
    return variant, "", said, _said(_key("wedding-calendar", f"{variant}_why")), tuple(details)


def _name_day(f: NameDayFinding) -> tuple[str, str, Message, Message, tuple[Message, ...]]:
    variant = "lookalike" if f.lookalikes else "far"
    said = _said(_key("name-days", variant), {
        "name": f.name, "born": _dmy(f.born), "christened": _dmy(f.christened),
        "nearest": _dm(*f.nearest), "outside": f.outside})
    why = (_said(_key("name-days", "lookalike_why")) if f.lookalikes
           else _said(_key("name-days", "far_why"), {"before": BEFORE, "after": AFTER}))
    details = (_said(_key("name-days", "lookalikes"), {"names": ", ".join(
        f"{n.name}{f' ({n.base})' if n.base != n.name else ''} {_dm(*n.day)}" for n in f.lookalikes)}),
               ) if f.lookalikes else ()
    return variant, "child", said, why, details


def _lag(f: LagFinding) -> tuple[str, str, Message, Message, tuple[Message, ...]]:
    if f.kind == "baptism":
        variant = "month_carried" if f.month_carried else "late"
        said = _said(_key("baptism-lag", variant), {"born": _dmy(f.first), "christened": _dmy(f.second), "days": f.days})
        why = (_said(_key("baptism-lag", "month_carried_why")) if f.month_carried
               else _said(_key("baptism-lag", "late_why"), {"limit": BAPTISM_DAYS}))
        return variant, "child", said, why, ()
    very = f.confidence == "HIGH"       # the check's own judgement (past BURIAL_HIGH_DAYS), never a second comparison
    variant = "very_late" if very else "late"
    said = _said(_key("burial-lag", variant), {"died": _dmy(f.first), "buried": _dmy(f.second), "days": f.days})
    why = _said(_key("burial-lag", f"{variant}_why"), {"limit": BURIAL_HIGH_DAYS if very else BURIAL_DAYS})
    return variant, "deceased", said, why, ()


def _wedding_age(f: WeddingAgeFinding) -> tuple[str, str, Message, Message, tuple[Message, ...]]:
    if f.kind == "under_age":
        role = f.role or ""
        said = _said(_key("wedding-ages", f"under_age_{role}"),
                    {"age": str(f.age), "minimum": f.minimum or 0, "married": _date(f.married)})
        return "under_age", role, said, _said(_key("wedding-ages", "under_age_why")), ()
    groom, bride = f.ages or ("?", "?")
    said = _said(_key("wedding-ages", "age_gap"), {"groom": str(groom), "bride": str(bride), "years": f"{f.gap_years:g}"})
    return "age_gap", "", said, _said(_key("wedding-ages", "age_gap_why"), {"gap": f"{GAP_YEARS:g}"}), ()


def _within(f: WithinFinding) -> tuple[str, str, Message, Message, tuple[Message, ...]]:
    said = _said(_key("date-order", f.kind), {"left": _date(f.left.date), "right": _date(f.right.date)})
    return f.kind, f.left.cite.locator, said, _said(f"facts.date_order.hint.{f.kind}"), ()


def signal_of(finding: Finding, *, record: str = "") -> Signal:
    """What a check found, as it is said — the one translation, for a card and for a report alike."""
    if isinstance(finding, WeddingFinding):
        check, parts, cite = "wedding-calendar", _wedding(finding), finding.cite
    elif isinstance(finding, NameDayFinding):
        check, parts, cite = "name-days", _name_day(finding), finding.cite
    elif isinstance(finding, LagFinding):
        check, parts, cite = f"{finding.kind}-lag", _lag(finding), finding.cite
    elif isinstance(finding, WeddingAgeFinding):
        check, parts, cite = "wedding-ages", _wedding_age(finding), finding.cite
    else:
        check, parts, cite = "date-order", _within(finding), finding.left.cite
    variant, locator, said, why, details = parts
    stood_down = check != "date-order" or variant in DATE_ORDER_STOOD_DOWN
    return Signal(check=check, variant=variant, confidence=getattr(finding, "confidence", "HIGH"), record=record,
                  locator=locator, said=said, why=why, details=details,
                  stand_down=STAND_DOWN[check] if stood_down else None, cite=cite)


def _assertions(record: Any, extract: Extract, record_id: str, village: str, book_year: int | None) -> AssertionSet:
    """The record's assertions, read whether it is reviewed or not. A record that writes no year is dated by its
    book — as every reader of a book dates it — on a COPY: the caller's record is never changed, not even while it
    is read (an adapter may be writing the same object out)."""
    if getattr(record, "year", None) is None and book_year is not None:
        record = copy.copy(record)
        record.year = book_year

    def named(_record: object) -> str:
        return record_id
    return AssertionSet(list(extract([(record, "")], village=village, drafts=True, ids=named)))


def asked(checks: Collection[str]) -> list[str]:
    """`checks` in the order of CHECKS; a name no check has is refused, and so is a text given for a collection."""
    if isinstance(checks, str):
        raise TypeError(f"checks is a collection of names, not the text {checks!r}")
    unknown = sorted(set(checks) - set(CHECKS))
    if unknown:
        raise ValueError(f"no single-record check named {', '.join(unknown)}; there are: {', '.join(CHECKS)}")
    return [c for c in CHECKS if c in set(checks)]


def findings_of(facts: AssertionSet, check: str, *, svyatcy: Svyatcy | None = None) -> Iterable[Finding]:
    """One check's findings on assertions a reader may believe (`AssertionSet.believed()`)."""
    if check == "wedding-calendar":
        return wedding_calendar_findings(facts).findings
    if check == "name-days":
        return name_day_findings(facts, svyatcy if svyatcy is not None else load_svyatcy()).findings
    if check == "baptism-lag":
        return baptism_lags(facts).findings
    if check == "burial-lag":
        return burial_lags(facts).findings
    if check == "wedding-ages":
        return wedding_age_findings(facts).findings
    return within_entry(facts)


def signals_of(record: object, *, record_id: str, village: str = "", book_year: int | None = None,
               checks: Collection[str] = CHECKS, svyatcy: Svyatcy | None = None) -> Signals:
    """The signals of one record: `checks` asked of what it alone asserts.

    `record` is a built DSL record — a birth, a wedding, a death; anything else
    (a household, a card, a line of a list) answers none of these checks.
    `record_id` names it in every signal; `book_year` dates a record that
    writes no year of its own. `svyatcy` is the table `name-days` reads (the
    package's, when none is given). A check that could not be asked — the
    workspace has no names table to read a name with — is in `unanswered`,
    never silently empty.
    """
    from verso.core.workspace import LexiconNotConfigured

    wanted = asked(checks)
    extract = extractor_of(record)
    if extract is None or not wanted:
        return Signals((), ())
    believed = _assertions(record, extract, record_id, village, book_year).believed()
    found: list[Signal] = []
    unanswered: list[str] = []
    for check in wanted:
        try:
            found += [signal_of(f, record=record_id) for f in findings_of(believed, check, svyatcy=svyatcy)]
        except LexiconNotConfigured:
            unanswered.append(check)
    found.sort(key=lambda s: s.confidence != "HIGH")        # stable: the order of CHECKS within a level
    return Signals(tuple(found), tuple(unanswered))
