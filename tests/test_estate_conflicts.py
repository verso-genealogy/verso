"""Tests for `verso.ru.consolidation.estate_conflicts`.

The check exists to surface consolidations that fused two people, using the
сословие as the tell. Its whole value depends on NOT firing on the legitimate
variation this corpus is full of — the reclassification of 1841, role wording,
and military-family descriptors — so most of these tests pin the negatives.

A finding is built the way the live check builds it: one `Titled` per record,
placed on its canonical, handed to `verso.ru.consolidation.estate_conflicts.estate_conflicts_of`.
"""
import tempfile
import unittest
from pathlib import Path

from verso.ru.consolidation.estate_conflicts import estate_conflicts_of, render
from verso.ru.domain.estates import estate_of
from verso.ru.facts.model import AssertionSet, Citation, Persona, Stated, Titled
from verso.core.targets.geni.profile import GeniProfile
from verso.core.workspace import use


def _found(**people):
    """Findings for `people` — canonical → (year, status) per record, each
    status one record's own «Титул/звание»."""
    claims, placed = [], {}
    for canon, rows in people.items():
        for year, status in rows:
            n = len(claims)
            who = Persona(f"r{n}.py#{n}/member1")
            cite = Citation(village="Тестовка", source_file=f"r{n}.py",
                            record_kind="k", record_num=str(n), entry=n,
                            year=year, locator="god_parent1")
            claims.append(Titled(subject=who, cite=cite, status=status,
                                 basis=Stated()))
            placed[who] = canon

    def identity(_record):
        def key(who):
            canon = placed.get(who)
            return (canon,) if canon is not None else None
        return key

    profiles = {c: GeniProfile(res_name=c, first_name="Анна",
                               middle_name="Максимовна") for c in people}
    return estate_conflicts_of(AssertionSet(claims), identity, profiles)


class TestEstateOf(unittest.TestCase):
    def test_landlord_owner_is_the_estate(self):
        self.assertEqual(
            estate_of("крестьянка помещика Ивана Васильевича Пеночкина"),
            "landlord:Ивана Васильевича Пеночкина")

    def test_role_prefix_does_not_change_the_owner(self):
        """Every wording for one owner's serfs must collapse to one key."""
        owner = "landlord:Ивана Васильевича Пеночкина"
        for status in (
            "крестьянин помещика Ивана Васильевича Пеночкина",
            "крестьянка помещика Ивана Васильевича Пеночкина",
            "девка из крестьян помещика Ивана Васильевича Пеночкина",
            "девица из крестьян помещика Ивана Васильевича Пеночкина",
            "законная жена крестьянина помещика Ивана Васильевича Пеночкина",
        ):
            with self.subTest(status=status):
                self.assertEqual(estate_of(status), owner)

    def test_landlady_is_recognised(self):
        self.assertEqual(
            estate_of("крестьянин помещицы Анфисы Спиридоновны Плюшкиной"),
            "landlord:Анфисы Спиридоновны Плюшкиной")

    def test_yasak_and_kazennyj_are_one_estate(self):
        """Горюхино was reclassified in 1841 — this must never be a conflict."""
        self.assertEqual(estate_of("ясачный крестьянин"), "state")
        self.assertEqual(estate_of("казенная крестьянка"), "state")
        self.assertEqual(estate_of("девка из ясачных крестьян"), "state")

    def test_role_only_statuses_carry_no_estate(self):
        for status in ("девица", "вдова", "женка", "солдатка",
                       "солдатская дочь", "крестьянин", "крестьянка",
                       "рядовой", "кантонист", None, ""):
            with self.subTest(status=status):
                self.assertIsNone(estate_of(status))

    def test_economic_and_state_are_one_estate(self):
        """Заманиловка's scribes write both for the same people — «государственная»
        in the 1850 roll, «экономическая» at her burial in 1864."""
        self.assertEqual(estate_of("экономический крестьянин"), "state")
        self.assertEqual(estate_of("экономическая крестьянка"),
                         estate_of("государственная крестьянка"))

    def test_other_estates(self):
        self.assertEqual(estate_of("мещанин"), "meshchanin")
        self.assertEqual(estate_of("дочь священника"), "clergy")
        self.assertEqual(estate_of("будный крестьянин"), "budny")


class TestFindEstateConflicts(unittest.TestCase):
    def test_two_landlords_conflict(self):
        """The anna_maksimovna shape: Пеночкин vs Собакевич across records."""
        found = _found(anna_maksimovna=[
            (1832, "девица из крестьян помещика Ивана Васильевича Пеночкина"),
            (1835, "крестьянка помещика Трифона Лукича Собакевича"),
        ])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].landlord_count, 2)
        self.assertEqual(len(found[0].records), 2)

    def test_reclassification_is_not_a_conflict(self):
        self.assertEqual(_found(x=[(1837, "ясачная крестьянка"),
                                   (1841, "казенная крестьянка")]), [])

    def test_soldier_wife_after_peasant_is_not_a_conflict(self):
        """`tatjana_karpovna`: ясачная 1831/1837, солдатка 1839/1841 — one woman."""
        self.assertEqual(_found(tatjana_karpovna=[
            (1831, "ясачная крестьянка"), (1839, "солдатка"), (1841, "солдатка"),
        ]), [])

    def test_same_landlord_different_roles_is_not_a_conflict(self):
        self.assertEqual(_found(x=[
            (1832, "девица из крестьян помещика Ивана Васильевича Пеночкина"),
            (1836, "законная жена крестьянина помещика Ивана Васильевича Пеночкина"),
        ]), [])

    def test_single_record_profile_is_skipped(self):
        self.assertEqual(_found(stub=[
            (1830, "крестьянка помещика Ивана Васильевича Пеночкина")]), [])

    def test_landlord_against_state_conflicts(self):
        found = _found(x=[(1839, "ясачная крестьянка"),
                          (1840, "крестьянка помещика Ивана Васильевича Пеночкина")])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].estates,
                         ("landlord:Ивана Васильевича Пеночкина", "state"))

    def test_records_are_ordered_chronologically(self):
        found = _found(x=[(1841, "крестьянка помещика Б"),
                          (1832, "крестьянка помещика А")])
        self.assertEqual([r.year for r in found[0].records], [1832, 1841])

    def test_worst_first_ordering(self):
        found = _found(
            two=[(1832, "крестьянка помещика А"), (1835, "крестьянка помещика Б")],
            three=[(1832, "крестьянка помещика А"), (1835, "крестьянка помещика Б"),
                   (1839, "ясачная крестьянка")])
        self.assertEqual([f.res_name for f in found], ["three", "two"])


class TestRender(unittest.TestCase):
    def test_exit_code_and_ok_message(self):
        text, code = render([], as_json=False)
        self.assertEqual(code, 0)
        self.assertIn("OK — 0 findings", text)

    def test_exit_code_on_findings(self):
        found = _found(x=[(1832, "крестьянка помещика А"),
                          (1835, "крестьянка помещика Б")])
        _, code = render(found, as_json=False)
        self.assertEqual(code, 1)

    def test_json_is_machine_readable(self):
        import json
        found = _found(x=[(1832, "крестьянка помещика А"),
                          (1835, "крестьянка помещика Б")])
        text, _ = render(found, as_json=True)
        payload = json.loads(text)
        self.assertEqual(payload[0]["res_name"], "x")
        self.assertEqual(payload[0]["landlord_count"], 2)


class TestOwnerAliases(unittest.TestCase):
    """A landlady under maiden and married surnames is ONE owner."""

    def test_alias_collapses_two_spellings(self):
        """Uses a fictional pair so the test does not depend on shipped aliases."""
        rows = [(1837, "крестьянка помещицы Тестовой Пробовны Первой"),
                (1841, "крестьянка помещицы Тестовой Пробовны Второй")]
        self.assertEqual(len(_found(x=rows)), 1)

        # The aliases are the corpus's (corpus/estates.toml), read through the workspace.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "verso.toml").write_text('schema = 2\n[corpus]\ndir = "c"\n', encoding="utf-8")
            (root / "c").mkdir()
            (root / "c" / "estates.toml").write_text(
                '[owner_aliases]\n"Тестовой Пробовны Второй" = "Тестовой Пробовны Первой"\n', encoding="utf-8")
            with use(root):
                self.assertEqual(_found(x=rows), [])

    def test_shipped_pljushkina_alias_is_applied(self):
        """The researched alias must actually collapse the two spellings."""
        self.assertEqual(
            estate_of("крестьянка помещицы Анфисы Спиридоновны Маниловой"),
            estate_of("крестьянин помещицы Анфисы Спиридоновны Плюшкиной"))

    def test_pljushkina_pairs_as_same_family_with_her_brother(self):
        """Née Манилова, so she and Кузьма Филиппович are one household."""
        from verso.ru.consolidation.estate_conflicts import _pair_flag

        self.assertEqual(
            _pair_flag("landlord:Кузьмы Филипповича Манилова",
                       "landlord:Анфисы Спиридоновны Плюшкиной"), "SAME")

    def test_pljushkina_pairs_as_same_family_with_her_husband(self):
        """Married Плюшкин, so she and Гурий Евсеевич are one household too.

        She belongs to BOTH families — born Манилова, married Плюшкина — so the
        flag must see her as same-household with her brother AND her husband.
        """
        from verso.ru.consolidation.estate_conflicts import _pair_flag

        self.assertEqual(
            _pair_flag("landlord:Гурия Евсеевича Плюшкина",
                       "landlord:Анфисы Спиридоновны Плюшкиной"), "SAME")

    def test_unrelated_family_still_flags_cross_family(self):
        from verso.ru.consolidation.estate_conflicts import _pair_flag

        self.assertEqual(
            _pair_flag("landlord:Трифона Лукича Собакевича",
                       "landlord:Анфисы Спиридоновны Плюшкиной"), "----")

    def test_maiden_family_does_not_merge_owners(self):
        """A maiden-family entry affects flagging only, never identity."""
        self.assertEqual(len(_found(x=[
            (1837, "крестьянин помещика Кузьмы Филипповича Манилова"),
            (1841, "крестьянка помещицы Анфисы Спиридоновны Плюшкиной"),
        ])), 1)


class TestFormatPairs(unittest.TestCase):
    """The triage view: hundreds of per-person findings → a few pair rows."""

    def test_pairs_are_ranked_and_counted(self):
        from verso.ru.consolidation.estate_conflicts import format_pairs

        a_b = [(1832, "крестьянка помещика А"), (1835, "крестьянка помещика Б")]
        a_c = [(1832, "крестьянка помещика А"), (1835, "крестьянка помещика В")]
        found = _found(p1=a_b, p2=a_b, p3=a_c)
        text = format_pairs(found)
        self.assertIn("3 finding(s) over 2 distinct estate pair(s)", text)
        # The A✕Б pair (2 profiles) must be listed above A✕В (1 profile).
        self.assertLess(text.index("landlord:А  ✕  landlord:Б"),
                        text.index("landlord:А  ✕  landlord:В"))

    def test_three_estates_yield_three_pairs(self):
        from verso.ru.consolidation.estate_conflicts import format_pairs

        text = format_pairs(_found(x=[(1832, "крестьянка помещика А"),
                                      (1835, "крестьянка помещика Б"),
                                      (1839, "ясачная крестьянка")]))
        self.assertIn("3 distinct estate pair(s)", text)


class TestPairFlags(unittest.TestCase):
    """The severity axis: ALIAS > cross-family > same-family."""

    def test_flags(self):
        from verso.ru.consolidation.estate_conflicts import _pair_flag

        cases = [
            # same given name + patronymic, different surname → one woman
            ("landlord:Анфисы Спиридоновны Плюшкиной",
             "landlord:Анфисы Спиридоновны Маниловой", "ALIAS"),
            # two different Маниловs — an estate divided among relatives
            ("landlord:Кузьмы Филипповича Манилова",
             "landlord:Лукерьи Кузьминичны Маниловой", "SAME"),
            # different landowning families — the strongest finding
            ("landlord:Ивана Васильевича Пеночкина",
             "landlord:Трифона Лукича Собакевича", "----"),
            # a landlord against the state peasantry
            ("landlord:Ивана Васильевича Пеночкина", "state", "----"),
        ]
        for a, b, expected in cases:
            with self.subTest(a=a, b=b):
                self.assertEqual(_pair_flag(a, b), expected)

    def test_family_root_is_gender_insensitive(self):
        from verso.ru.domain.estates import family_root

        self.assertEqual(family_root("Манилова"), family_root("Манилов"))
        self.assertEqual(family_root("Пеночкиной"), family_root("Пеночкин"))


if __name__ == "__main__":
    unittest.main()


def test_the_pairs_report_names_where_an_alias_goes():
    """An owner alias is the corpus's data (corpus/estates.toml), not a dict in the code."""
    from verso.ru.consolidation.estate_conflicts import format_pairs
    rows = [(1837, "крестьянка помещицы Тестовой Пробовны Первой"),
            (1841, "крестьянка помещицы Тестовой Пробовны Второй")]
    text = format_pairs(_found(x=rows))
    assert "[owner_aliases] of corpus/estates.toml" in text
    assert "OWNER_ALIASES" not in text
    assert "owners of one family is ordinary" in text      # no landlord named in the library
