"""`FactDate` must mean exactly what the `GeniDate` it came from means.

Risk #1 of the facts plan: a date bridge that rounds differently would not
fail loudly — it would quietly hand the migrated checks intervals the oracle
does not have, and `age_conflicts` is nothing but interval arithmetic. So the
bridge is pinned against `GeniDate`'s OWN conventions (`to_datetime` /
`to_end_datetime`), not against a restatement of them.
"""
from __future__ import annotations

import unittest

from verso.ru.facts.model import FactDate
from verso.ru.facts.projection import fact_date, geni_date
from verso.core.targets.geni.date import GeniDate

CASES = [
    GeniDate(year=1875),
    GeniDate(month=2, year=1875),
    GeniDate(day=17, month=3, year=1875),
    GeniDate(year=1898, month=9, circa=True),
    GeniDate(year=1850, date_range="after"),
    GeniDate(year=1875, date_range="before"),
    GeniDate(year=1848, date_range="between", end_year=1883, end_circa=True),
    GeniDate(year=1860, month=5, date_range="between", end_year=1861, end_month=7),
]


class AgreesWithGeniDate(unittest.TestCase):
    def test_earliest_matches_to_datetime(self):
        for g in CASES:
            with self.subTest(str(g)):
                f = fact_date(g)
                assert f is not None
                if f.earliest is None:
                    self.assertEqual("before", g.date_range)
                    continue
                dt = g.to_datetime()
                self.assertIsNotNone(dt)
                assert dt is not None
                self.assertEqual((dt.year, dt.month, dt.day), f.earliest)

    def test_latest_matches_to_end_datetime_when_there_is_an_end(self):
        for g in (c for c in CASES if c.end_year is not None):
            with self.subTest(str(g)):
                f = fact_date(g)
                assert f is not None
                dt = g.to_end_datetime()
                assert dt is not None
                self.assertEqual((dt.year, dt.month, dt.day), f.latest)

    def test_an_after_range_has_no_latest(self):
        f = fact_date(GeniDate(year=1850, date_range="after"))
        assert f is not None
        self.assertIsNone(f.latest)

    def test_round_trip_preserves_every_field(self):
        for g in CASES:
            with self.subTest(str(g)):
                back = geni_date(fact_date(g))
                assert back is not None
                for attr in ("day", "month", "year", "circa", "end_day",
                             "end_month", "end_year", "end_circa", "date_range"):
                    self.assertEqual(getattr(g, attr), getattr(back, attr), attr)

    def test_synthetic_is_not_carried(self):
        """A derived bound is a Basis, not a date field — see fact_date's docstring."""
        back = geni_date(fact_date(GeniDate(year=1800, synthetic=True)))
        assert back is not None
        self.assertFalse(back.synthetic)

    def test_none_passes_through(self):
        self.assertIsNone(fact_date(None))
        self.assertIsNone(geni_date(None))

    def test_an_unknown_range_word_is_not_invented_into_a_bound(self):
        self.assertIsNone(fact_date(GeniDate(year=1800, date_range="sometime")).bound)


class AJulianLeapDay(unittest.TestCase):
    """29 February 1800 exists in the Julian calendar the books were kept in
    and not in the proleptic Gregorian one `datetime` uses, so no `datetime`
    can carry day 29 of that month: the label parity pinned above is
    unattainable for this one date. What the translator USES the datetime for
    is ordering, so that is what agrees — the fact keeps the book's label.
    """

    def test_ordering_agrees_where_the_label_cannot(self):
        days = [GeniDate(day=28, month=2, year=1800),
                GeniDate(day=29, month=2, year=1800),
                GeniDate(day=1, month=3, year=1800)]
        facts = [fact_date(g) for g in days]
        assert all(f is not None for f in facts)
        by_fact = sorted(range(3), key=lambda i: facts[i].earliest)  # type: ignore[union-attr]
        by_dt = sorted(range(3), key=lambda i: days[i].to_datetime())  # type: ignore[arg-type,return-value]
        self.assertEqual([0, 1, 2], by_fact)
        self.assertEqual(by_fact, by_dt)

    def test_the_fact_keeps_the_books_own_day(self):
        f = fact_date(GeniDate(day=29, month=2, year=1800))
        assert f is not None
        self.assertEqual((1800, 2, 29), f.earliest)


class KnownShapes(unittest.TestCase):
    def test_an_alive_at_bound_never_orders_before_anything(self):
        """77% of Горюхино's death events are `after` — lower bounds wearing
        an event's clothes. They must not settle an ordering."""
        alive = fact_date(GeniDate(year=1850, date_range="after"))
        assert alive is not None
        self.assertFalse(alive.definitely_before(FactDate(year=1900)))
        self.assertTrue(alive.overlaps(FactDate(year=1900)))


class TheBridgeRefusesRatherThanGuesses(unittest.TestCase):
    """`consolidated_identity` — an appearance folded the way the config folds.

    The property that makes it a bridge and not a heuristic: it answers with a
    canonical or with nothing. A wrong fold invents a person; a refusal only
    declines to answer, and the refusals are counted (`--check identity`).
    """

    class _Minted:
        """What the bridge needs of a finished translation."""

        def __init__(self, minted: dict[object, str], folds: dict[str, str]):
            self._minted, self._folds = minted, folds

        def profile_minted_for(self, person: object) -> str | None:
            return self._minted.get(person)

        def resolve_canonical(self, res_name: str) -> str:
            return self._folds.get(res_name, res_name)

    @staticmethod
    def _key(minted, folds, slots):
        from verso.ru.facts.model import Record
        from verso.ru.facts.projection import consolidated_identity
        bridge = TheBridgeRefusesRatherThanGuesses._Minted(minted, folds)
        return consolidated_identity(bridge, slots.object_of)(Record(()))

    def _slots(self, *pairs):
        from verso.ru.facts.extract.common import SlotIndex
        index = SlotIndex()
        for persona, obj in pairs:
            index.record(persona, obj)
        return index

    @staticmethod
    def _persona(entry: int, ordinal: int = 0):
        from verso.ru.facts.model import Persona
        return Persona(f"f.py#{entry}/{ordinal}")

    def test_an_appearance_with_no_object_is_refused(self):
        key = self._key({}, {}, self._slots())
        self.assertIsNone(key(self._persona(1)))

    def test_an_appearance_whose_profile_was_never_minted_is_refused(self):
        """The причт: no profile exists, so there is no canonical to name.
        3308 of Заманиловка's appearances and 555 of Горюхино's are this."""
        priest = object()
        key = self._key({}, {}, self._slots((self._persona(1), priest)))
        self.assertIsNone(key(self._persona(1)))

    def test_a_minted_appearance_resolves_through_the_fold(self):
        father = object()
        key = self._key({father: "_1875_ivan_mk_births_3_father"},
                        {"_1875_ivan_mk_births_3_father": "ivan_petrovich"},
                        self._slots((self._persona(1), father)))
        self.assertEqual(("ivan_petrovich",), key(self._persona(1)))

    def test_two_appearances_the_config_folds_get_ONE_key(self):
        """The whole point: 2773 canonicals on Горюхино hold more than one."""
        a, b = object(), object()
        key = self._key(
            {a: "_1875_ivan_mk_births_3_father", b: "_1880_ivan_mk_deaths_9_deceased"},
            {"_1875_ivan_mk_births_3_father": "ivan_petrovich",
             "_1880_ivan_mk_deaths_9_deceased": "ivan_petrovich"},
            self._slots((self._persona(1), a), (self._persona(2), b)))
        self.assertEqual(key(self._persona(1)), key(self._persona(2)))

    def test_two_appearances_the_config_does_not_fold_stay_apart(self):
        a, b = object(), object()
        key = self._key({a: "ivan_1", b: "ivan_2"}, {},
                        self._slots((self._persona(1), a), (self._persona(2), b)))
        self.assertNotEqual(key(self._persona(1)), key(self._persona(2)))


class TheJoinKeyIsTheAppearance(unittest.TestCase):
    def test_two_same_named_people_are_two_keys(self):
        """`Person` is a plain class, so identity — not equality — is the key,
        which is exactly the distinction an identity has to make."""
        from verso.ru.domain import person
        from verso.ru.facts.extract.common import SlotIndex
        from verso.ru.facts.model import Persona
        one, two = person("Иванъ", "Петровъ"), person("Иванъ", "Петровъ")
        index = SlotIndex()
        index.record(Persona("f#1/0"), one)
        index.record(Persona("f#2/0"), two)
        self.assertIs(one, index.object_of(Persona("f#1/0")))
        self.assertIs(two, index.object_of(Persona("f#2/0")))
        self.assertEqual(2, len(index))

    def test_the_first_reading_of_a_slot_wins(self):
        from verso.ru.facts.extract.common import SlotIndex
        from verso.ru.facts.model import Persona
        first, second = object(), object()
        index = SlotIndex()
        index.record(Persona("f#1/0"), first)
        index.record(Persona("f#1/0"), second)
        self.assertIs(first, index.object_of(Persona("f#1/0")))

    def test_the_translator_records_what_it_minted(self):
        from verso.ru.domain import person
        from verso.ru.targets.geni.translator import TerraformGenerator
        gen = TerraformGenerator(village_dir="Тестовка")
        p = person("Иванъ", "Петровъ")
        profile = gen._profile_from_person(
            p, year=1875, month=3, day=5, document_name="mk_births",
            record_number="7", role="father")
        self.assertEqual(profile.res_name, gen.profile_minted_for(p))
        self.assertIsNone(gen.profile_minted_for(person("Иванъ", "Петровъ")))
        self.assertEqual([], gen.minted_twice())

    def test_the_translator_keeps_the_section_it_minted(self):
        """The section a canonical's about is folded together from, kept by
        the appearance — without the sort marker, as it reads once folded."""
        from verso.ru.domain import person
        from verso.ru.targets.geni.translator import TerraformGenerator
        gen = TerraformGenerator(village_dir="Тестовка")
        p = person("Иванъ", "Петровъ")
        section = "<strong>МК Тестовка 1875:</strong> отец ребенка\n        Титул/звание: крестьянин"
        profile = gen._profile_from_person(
            p, year=1875, month=3, day=5, document_name="mk_births",
            record_number="7", role="father", about=section)
        self.assertIn("<!--sd:1875-03-05-->", profile.about)
        self.assertEqual(section, gen.section_minted_for(p))
        self.assertIsNone(gen.section_minted_for(person("Иванъ", "Петровъ")))
