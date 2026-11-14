"""verso.ru.persons.people — the index's build kept cheap and its answers unmoved.

The digests below were taken of the index as it was built before the build was made cheap (0.1.32): the keys
every person is matched by, the lives, and the suggestions of a few hundred questions over the synthetic corpus
(`people_synthetic`). A change to the build that moves any of them is a change of what the App offers.

The build's cost is held by what it does, not by a clock: one `match_key` a distinct pair of a name's written and
modern forms, no pass of the cyclic collector. `python tests/people_synthetic.py` times it at the pilot's size.
"""
from __future__ import annotations

import dataclasses
import gc
import hashlib
import random
import threading
from collections.abc import Iterator

import pytest

from people_synthetic import pilot_sightings
from verso.ru.naming.matching import match_key
from verso.ru.persons import people
from verso.ru.persons.lives import record_days
from verso.ru.persons.people import PeopleIndex, Sighting

# A tenth of the pilot: the same shape, a test's time.
_BOOKS, _RECORDS = 130, 2700

MATCHED_BY_DIGEST = "d7e48378ac47f68ba892ff951529e7341d112b30f6732177fcf891f64db01910"
SUGGESTIONS_DIGEST = "7efcaf8d7b14d1eced6bd93087bb431a27839a5542b555583efe2e77901ae04d"
LIVES_DIGEST = "9a585cd169e8161c7261db5cd0c37c91cf4f2d89e1360c22bddd0c7329884384"


@pytest.fixture(scope="module")
def rows() -> list[Sighting]:
    return pilot_sightings(books=_BOOKS, records=_RECORDS)


@pytest.fixture(scope="module")
def index(rows: list[Sighting]) -> PeopleIndex:
    return PeopleIndex(rows)


def _digest(value: object) -> str:
    return hashlib.sha256(repr(value).encode()).hexdigest()


def _keys(index: PeopleIndex) -> list[tuple[object, ...]]:
    return sorted((e.written, tuple(tuple(sorted(k)) for k in e.keys), e.sex, sorted(e.villages.items()),
                   sorted(e.years.items()), e.total, e.seen) for e in index._people)


def _lives(index: PeopleIndex) -> list[tuple[object, ...]]:
    return [(life.members, [dataclasses.astuple(b) for b in life.births], life.ons, life.deaths, life.died, life.last_present, life.newborn)
            for life in index._lives]


def _questions(rows: list[Sighting]) -> list[tuple[tuple[str, str, str], dict[str, object]]]:
    """Prefixes of the written and the modern forms, in either case, a part left out, with the village, a sex,
    a day, a slot's age, the dead and the record's own people asked of in turn."""
    rnd = random.Random(1863)
    out: list[tuple[tuple[str, str, str], dict[str, object]]] = []
    offering = [r for r in rows if r.seen is not None]
    for r in rnd.sample(offering, 300):
        s = r.seen
        assert s is not None
        forms = s.written[:3] if rnd.random() < 0.5 else s.modern
        parts = [f[:rnd.randrange(0, len(f) + 1)] if f else "" for f in forms]
        if rnd.random() < 0.3:
            parts = [p.lower() for p in parts]
        if rnd.random() < 0.3:
            parts[rnd.randrange(3)] = ""
        year = (r.year or 1850) + rnd.randrange(-30, 30)
        kw: dict[str, object] = {"village": r.village if rnd.random() < 0.8 else rows[0].village,
                                 "gender": rnd.choice(("", "", s.sex)),
                                 "limit": rnd.choice((8, 50)),
                                 "exclude": r.record if rnd.random() < 0.3 else None,
                                 "at": record_days(year, rnd.randrange(1, 13)) if rnd.random() < 0.6 else None,
                                 "min_age": rnd.choice((0.0, 0.0, 16.0)),
                                 "dead_days": rnd.choice((0.0, None))}
        out.append(((parts[0], parts[1], parts[2]), kw))
    return out


def test_the_keys_are_those_the_build_gave(index: PeopleIndex) -> None:
    assert _digest(_keys(index)) == MATCHED_BY_DIGEST


def test_the_lives_are_those_the_build_gave(index: PeopleIndex) -> None:
    assert _digest((_lives(index), sorted(index._holding.items()))) == LIVES_DIGEST


def test_the_suggestions_are_those_the_build_gave(rows: list[Sighting], index: PeopleIndex) -> None:
    answers = [index.suggest(*parts, **kw) for parts, kw in _questions(rows)]  # type: ignore[arg-type]
    assert sum(1 for a in answers if a) > 200            # the questions find people
    assert _digest(answers) == SUGGESTIONS_DIGEST


@pytest.mark.parametrize(("text", "key"), [
    ("Ѳедоръ", "федор"), ("Матѳей", "матфей"), ("Алексѣй", "алексей"), ("Іоаннъ Петровъ", "иоанн петров"),
    ("Ѯенія", "ксения"), ("Өома", "фома"), ("Ѵпатій", "ипатий"), ("Объ", "об"), ("ОБЪ", "об"), ("Семёнъ", "семен"),
    ("Подъячій", "подъячий"), ("Бѣлъ,", "бел,"), ("", ""),
])
def test_a_key_is_the_name_in_modern_spelling_lower_case(text: str, key: str) -> None:
    assert match_key(text) == key


def test_a_pair_of_forms_is_keyed_once_a_build(rows: list[Sighting], monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def counted(text: str) -> str:
        asked.append(text)
        return match_key(text)
    monkeypatch.setattr(people, "match_key", counted)
    PeopleIndex(rows)
    pairs = {(t, m) for r in rows if (s := r.seen) is not None
             for t, m in zip((s.name, s.patr, s.surname), s.modern, strict=True)}
    assert len(asked) == sum(1 for t, m in pairs for x in (t, m) if x)
    assert len(asked) < sum(1 for r in rows if r.seen is not None)    # far fewer than the sightings


@pytest.fixture
def collections() -> Iterator[list[int]]:
    """The generations the cyclic collector passes over while the test runs."""
    passed: list[int] = []

    def heard(phase: str, info: dict[str, int]) -> None:
        if phase == "start":
            passed.append(info["generation"])
    gc.callbacks.append(heard)
    try:
        yield passed
    finally:
        gc.callbacks.remove(heard)


def test_the_build_runs_no_collection(rows: list[Sighting], collections: list[int],
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    build = PeopleIndex._build
    during: list[list[int]] = []

    def watched(self: PeopleIndex, found: list[Sighting]) -> None:
        before = len(collections)
        build(self, found)
        during.append(collections[before:])
    monkeypatch.setattr(PeopleIndex, "_build", watched)
    assert gc.isenabled()
    PeopleIndex(rows)
    assert during == [[]]
    assert gc.isenabled()


def test_a_failed_build_lets_the_collector_run_again() -> None:
    def failing() -> Iterator[Sighting]:
        assert not gc.isenabled()
        raise RuntimeError("a book that cannot be read")
        yield
    with pytest.raises(RuntimeError):
        PeopleIndex(failing())
    assert gc.isenabled()


def test_a_collector_held_off_before_stays_so(rows: list[Sighting]) -> None:
    gc.disable()
    try:
        PeopleIndex(rows[:100])
        assert not gc.isenabled()
    finally:
        gc.enable()


def test_two_builds_at_once_let_it_run_when_the_last_ends() -> None:
    inside, release = threading.Event(), threading.Event()

    def held() -> Iterator[Sighting]:
        inside.set()
        release.wait(10)
        yield from ()
    other = threading.Thread(target=PeopleIndex, args=(held(),))
    other.start()
    assert inside.wait(10)
    PeopleIndex([])                     # ends while the other build is under way
    assert not gc.isenabled()
    release.set()
    other.join(10)
    assert gc.isenabled()
