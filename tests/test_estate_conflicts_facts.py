"""`estate-conflicts`: two сословия of one person, from `Titled`.

The second caller of `verso.ru.facts.rules.disagreement`, and the one the layer's
FAIL gate rests on: if an estate conflict could not be put as «two claims of
one person that cannot both hold», the rule would not be general. On the live
corpus this reading reproduced the (since removed) `about` parser's findings
exactly on all five villages (400 + 28 + 0 + 0 + 0), `--pairs` byte for byte; these tests pin
the classification it inherits and the one thing it adds — a line resting on a
member we reconstructed says so.
"""
from __future__ import annotations

import random
import unittest
from collections.abc import Callable
from unittest import mock

from verso.ru.consolidation.estate_conflicts import estate_conflicts_of
from verso.ru.consolidation import estate_conflicts as ec
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import (
    Assertion, AssertionSet, Citation, Derived, Persona, Record, Stated, Surety, Titled)
from verso.core.targets.geni.profile import GeniProfile

MANILOV = "крестьянин помещика Кузьмы Филипповича Манилова"
PENOCHKIN = "крестьянин помещика Ивана Васильевича Пеночкина"


def _styled(roll: str, entry: int, status: str, *, year: int = 1830,
            basis: Stated | Derived | None = None) -> tuple[Persona, Assertion]:
    who = Persona(f"{roll}#{entry}/member1")
    cite = Citation(village="Тестовка", source_file=roll, record_kind="k",
                    record_num=str(entry), entry=entry, year=year, locator="father")
    return who, Titled(subject=who, cite=cite, status=status, basis=basis or Stated())


def _bridge(placed: dict[Persona, str]) -> Callable[[Record], Callable[[Persona], IdentityKey | None]]:
    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        def key(who: Persona) -> IdentityKey | None:
            canon = placed.get(who)
            return (canon,) if canon is not None else None
        return key
    return identity


def _one_person(*statuses: str) -> list[ec.EstateConflict]:
    rows = [_styled(f"b{i}.py", i, s, year=1830 + i) for i, s in enumerate(statuses)]
    placed = {who: "petr" for who, _ in rows}
    profiles = {"petr": GeniProfile(res_name="petr", first_name="Пётр")}
    return estate_conflicts_of(AssertionSet([a for _, a in rows]), _bridge(placed), profiles)


class TwoEstates(unittest.TestCase):
    def test_two_landlords_are_a_finding(self):
        found = _one_person(MANILOV, PENOCHKIN)
        self.assertEqual(1, len(found))
        self.assertEqual("Пётр", found[0].name)
        self.assertEqual(("landlord:Ивана Васильевича Пеночкина",
                          "landlord:Кузьмы Филипповича Манилова"), found[0].estates)
        self.assertEqual([1830, 1831], [r.year for r in found[0].records])

    def test_one_landlord_twice_is_not(self):
        self.assertEqual([], _one_person(MANILOV, MANILOV))

    def test_a_maiden_and_a_married_surname_are_one_owner(self):
        """`OWNER_ALIASES` is the caller's classification, and the rule never
        sees a spelling — only whether two estates differ."""
        self.assertEqual([], _one_person(
            "крестьянин помещицы Анфисы Спиридоновны Маниловой",
            "крестьянин помещицы Анфисы Спиридоновны Плюшкиной"))

    def test_the_1841_reclassification_is_not_a_conflict(self):
        self.assertEqual([], _one_person("ясачный крестьянин", "казенный крестьянин"))

    def test_a_role_status_contradicts_nothing_and_is_not_printed(self):
        found = _one_person(MANILOV, "солдатка", PENOCHKIN)
        self.assertEqual(1, len(found))
        self.assertNotIn("солдатка", [r.status for r in found[0].records])


class WhoDecides(unittest.TestCase):
    def test_the_disagreement_rule_decides(self):
        """The FAIL gate, pinned: with the rule answering «no contradictions»,
        two landlords are no finding — nothing beside the rule decides."""
        # Patched where the check looks it up: `verso.ru.facts.checks.estates`
        # asks the rule, and nothing else there decides.
        with mock.patch("verso.ru.facts.checks.estates.contradictions",
                        return_value=[]):
            self.assertEqual([], _one_person(MANILOV, PENOCHKIN))


class OurReconstruction(unittest.TestCase):
    def test_a_reconstructed_members_line_is_marked_and_still_counts(self):
        ours = Derived("census.reconstructed-member", Surety.ASSUMED, ())
        a = _styled("rs.py", 0, MANILOV, basis=ours)
        b = _styled("b.py", 1, PENOCHKIN)
        found = estate_conflicts_of(
            AssertionSet([a[1], b[1]]), _bridge({a[0]: "petr", b[0]: "petr"}),
            {"petr": GeniProfile(res_name="petr", first_name="Пётр")})
        self.assertEqual(1, len(found))
        roles = {r.status: r.role for r in found[0].records}
        self.assertIn("восстановлен", roles[MANILOV])
        self.assertNotIn("восстановлен", roles[PENOCHKIN])


class Stable(unittest.TestCase):
    def test_arrival_order_moves_nothing(self):
        rows = [_styled(f"r{i}.py", i, s, year=1830 + i % 2)
                for i, s in enumerate([MANILOV, PENOCHKIN, MANILOV, PENOCHKIN])]
        placed = {who: ("petr" if i < 2 else "ivan") for i, (who, _) in enumerate(rows)}
        profiles = {c: GeniProfile(res_name=c, first_name=c) for c in ("petr", "ivan")}
        seen = set()
        for seed in range(6):
            shuffled = [a for _, a in rows]
            random.Random(seed).shuffle(shuffled)
            found = estate_conflicts_of(AssertionSet(shuffled), _bridge(placed), profiles)
            seen.add(ec.render(found, as_json=True)[0])
        self.assertEqual(1, len(seen))


if __name__ == "__main__":
    unittest.main()


class TheOnlyReading(unittest.TestCase):
    """Each record's own status is what `estate-conflicts` reads. The `about`
    parser it kept behind `--legacy` for one wave was removed on 2026-09-25."""

    def test_it_reads_the_records(self):
        with mock.patch("verso.ru.consolidation.estate_conflicts.estate_findings", return_value=[]) as facts:
            ec.main(["--village", "Тестовка"])
        facts.assert_called_once()

    def test_the_legacy_flag_is_gone(self):
        with self.assertRaises(SystemExit):
            ec.main(["--village", "Тестовка", "--legacy"])
