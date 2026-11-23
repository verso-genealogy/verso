"""One review flag, and a ratchet on the unreviewed records already on Geni.

`reviewed=False` holds a record off Geni on every record type — until
2026-10-03 a `page(reviewed=False)` around births, marriages and deaths did
nothing, because they defaulted to `True`. The records uploaded meanwhile stay,
listed in `<village>/unreviewed_on_geni.tsv` by fingerprint
(`verso.core.ratchet`); a new unreviewed record, or a listed one edited without
being reviewed, is held. The list only shrinks.
"""
from __future__ import annotations

import tempfile
import textwrap
import unittest
from calendar import Month
from collections.abc import Callable
from pathlib import Path
from typing import Any

from verso.ru.cli import review_ratchet
from verso.core.pipeline.load import discover_records, load_module
from verso.ru.domain import Gender, page, person
from verso.core import ratchet
from verso.ru.dsl.records.births import BirthRecords, birth, birth_records, christening
from verso.ru.dsl.records.deaths import DeathRecords, death, death_records
from verso.ru.dsl.records.divorces import divorce, divorce_records
from verso.ru.dsl.records.marriages import marriage, marriage_records
from verso.ru.dsl.records.reviewed import admitted
from verso.ru.targets.geni.translator import TerraformGenerator

_BOOK = ("TestArchive", "1", "1", "1", "Тестовка", "Никольская", 1800)


def _birth(num: int = 1, surname: str = "Видимов", **kw: Any) -> Any:
    return birth(num, Gender.MALE, 10, 11, Month.MARCH, Month.MARCH,
                 child=person("Иван", last_name_orig=surname),
                 father=person("Петр", last_name_orig=surname), **kw)


def _christening(**kw: Any) -> Any:
    return christening(2, Gender.MALE, 11, Month.MARCH, age=20, child=person("Симеон"), **kw)


def _marriage(**kw: Any) -> Any:
    return marriage(1, 10, Month.MAY, groom=person("Иван"), bride=person("Анна"), **kw)


def _death(**kw: Any) -> Any:
    return death(1, Gender.MALE, 5, 6, Month.MARCH, Month.MARCH, deceased=person("Иван"), age=40, **kw)


def _divorce(**kw: Any) -> Any:
    return divorce(1, 5, Month.MAY, husband=person("Иван"), wife=person("Анна"), **kw)


_KINDS: dict[str, tuple[Callable[..., Any], Callable[..., Any]]] = {
    "birth": (_birth, birth_records),
    "christening": (_christening, birth_records),
    "marriage": (_marriage, marriage_records),
    "death": (_death, death_records),
    "divorce": (_divorce, divorce_records),
}


class OneFlag(unittest.TestCase):
    """Record, page, file — innermost first, on every record type."""

    def test_unstated_until_the_record_set(self):
        for kind, (make, records) in _KINDS.items():
            with self.subTest(kind):
                self.assertIsNone(make().reviewed)
                self.assertEqual([True, False],
                                 [r.reviewed for r in records(*_BOOK, make(), make(reviewed=False)).records])

    def test_a_page_holds_its_leaf(self):
        for kind, (make, records) in _KINDS.items():
            with self.subTest(kind):
                book = records(*_BOOK, *page("5", make(), make(reviewed=True), reviewed=False))
                self.assertEqual([False, True], [r.reviewed for r in book.records])

    def test_a_file_holds_what_did_not_speak(self):
        held = birth_records(*_BOOK, _birth(1), _birth(2, reviewed=True), reviewed=False)
        self.assertEqual([False, True], [r.reviewed for r in held.records])
        self.assertEqual([True, False],
                         [r.reviewed for r in DeathRecords(*_BOOK, [_death(), _death(reviewed=False)]).records])

    def test_a_file_holds_its_divorces(self):
        held = divorce_records(*_BOOK, _divorce(), _divorce(reviewed=True), reviewed=False)
        self.assertEqual([False, True], [r.reviewed for r in held.records])
        self.assertIs(False, held.reviewed)

    def test_page_refuses_a_record_with_no_flag(self):
        class Unflagged:          # no record type of the DSL any more: a divorce has had the flag since 0.1.47
            page = None
        with self.assertRaises(TypeError):
            page("1", Unflagged(), reviewed=False)  # pyright: ignore[reportArgumentType]
        self.assertEqual(1, len(page("1", Unflagged())))  # pyright: ignore[reportArgumentType]

    def test_admitted(self):
        self.assertTrue(admitted(_birth()), "unstated is not held")
        self.assertFalse(admitted(_birth(reviewed=False)))
        listed = _birth(reviewed=False)
        listed.on_geni = True  # pyright: ignore[reportAttributeAccessIssue] — the loader's dynamic mark
        self.assertTrue(admitted(listed))

    def test_the_translator_holds_a_leaf_and_emits_a_listed_record(self):
        records = birth_records(*_BOOK, *page("5", _birth(1, "Скрытов"), _birth(2, "Видимов"),
                                             reviewed=False))
        records.records[1].on_geni = True  # pyright: ignore[reportAttributeAccessIssue]
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")
        self.assertIn("Видимов", output)
        self.assertNotIn("Скрытов", output)
        self.assertIsNone(gen.document_minted_for(records.records[0]))
        self.assertIsNotNone(gen.document_minted_for(records.records[1]))


DSL = '''\
from calendar import Month

from verso.ru.dsl import Gender, RecordDefaults, page, person
from verso.ru.dsl.statuses import PEASANT_MALE
from verso.ru.dsl import birth, birth_month, birth_records

DEFAULTS = RecordDefaults(status_male=PEASANT_MALE)

births = birth_records(
    "ГАВО", "999", "1", "3", "Тестовка", "Покровская", 1887,
    *page("341об", reviewed=False,
          *birth_month(Month.JANUARY,
                       birth(1, Gender.FEMALE, 9, 10, child=person("Агафья"),
                             father=person("Петр", "Ивановъ")),
                       birth(2, Gender.MALE, 17, 18, child=person("Иванъ"),
                             father=person("Петр", "Ивановъ")),
                       ),
          ),
    defaults=DEFAULTS,
)
'''


ROLL = '''\
SHUMILOV_M = "крестьянин вотчины г-на Шумилова"

census = census_records("ГАВО", "162", "8", "100", "Глуповы Горы", 1858,
    household("17",
              member(1, person("Ѳома", None, "Ивановъ", status=SHUMILOV_M), CensusRole.HEAD, age=47),
              member(-1, person("Иванъ"), CensusRole.FATHER, ref_member=1, hidden=True),
              member(2, person("Марья"), CensusRole.WIFE, ref_member=1, age=40.5,
                     relatives=[relative(person("Петръ"), Relationship.BROTHER)])),
    single_age_column=False)
'''


# Two record sets, records under a keyword, under a module-level list and two wrappers deep: what a wrapper's
# context leaves out, asked once a file (`_walk`) and kept once a wrapper.
NESTED = '''\
WIDOW = "вдова"
EARLY = [death(9, Gender.FEMALE, 2, 3, deceased=person("Анна", status=WIDOW), age=60)]

births = birth_records("ГАВО", "1", "2", "3", "Тестовка", 1890,
    *page("12",
          birth(1, Gender.MALE, 4, 5, child=person("Петръ")),
          birth(2, Gender.FEMALE, 6, 7, child=person("Марія", status=WIDOW)),
          reviewed=False),
    *page("13",
          *birth_month(Month.MAY,
                       birth(3, Gender.MALE, 8, 9, child=person("Иванъ")))),
    extra=[christening(4, Gender.MALE, 10, Month.JUNE, age=20, child=person("Симеонъ"))],
    note="книга цела")

deaths = death_records("ГАВО", "1", "2", "4", "Тестовка", 1890,
    death(1, Gender.MALE, 5, 6, deceased=person("Ѳома"), age=40),
    *EARLY)
'''

def _prints(source: str) -> list[str]:
    return [p.fingerprint for p in ratchet.record_prints(source)]


class Fingerprints(unittest.TestCase):
    def test_label(self):
        self.assertEqual(["birth 1 ж, л. 341об", "birth 2 м, л. 341об"],
                         [p.label for p in ratchet.record_prints(DSL)])

    def test_layout_comments_and_the_flags_do_not_count(self):
        same = (DSL.replace('child=person("Агафья"),', 'child=person("Агафья"),  # кадр 8')
                .replace("birth(1, Gender.FEMALE, 9, 10, ", "birth(1, Gender.FEMALE, 9, 10, reviewed=True,\n    ")
                .replace('*page("341об", reviewed=False,', '*page("341об",'))
        self.assertEqual(_prints(DSL), _prints(same))

    def test_what_the_record_says_counts(self):
        before = _prints(DSL)
        for what, edited in (("name", DSL.replace('"Агафья"', '"Агафія"')),
                             ("number", DSL.replace("birth(1,", "birth(3,")),
                             ("month section", DSL.replace("Month.JANUARY", "Month.FEBRUARY")),
                             ("лист", DSL.replace('"341об"', '"342об"')),
                             ("the file's defaults", DSL.replace("status_male=PEASANT_MALE",
                                                                 "status_male=None"))):
            with self.subTest(what):
                self.assertNotEqual(before[0], _prints(edited)[0])

    def test_a_print_is_the_same_on_every_python(self):
        # The villages' lists hold prints taken on 3.14. 3.15's ast.dump leaves `ctx=Load()`
        # out: a print that followed it would read every listed record as «changed» there.
        self.assertEqual(["89c20988f25fdcce", "c606ebffd7e9a9f8"], _prints(DSL))
        self.assertEqual(["83c57ee3a3d165c3"], _prints(ROLL))

    def test_records_under_a_keyword_a_constant_and_two_wrappers_keep_their_prints(self):
        self.assertEqual([("7e321b9b71130f68", "death 9 ж"), ("7fa538b300d232d8", "birth 1 м, л. 12"),
                          ("2bc3609961d891e5", "birth 2 ж, л. 12"), ("71ce36da2334ba51", "birth 3 м, л. 13"),
                          ("aa753851e194693c", "christening 4 м"), ("6a119c3c3f02191b", "death 1 м")],
                         [(p.fingerprint, p.label) for p in ratchet.record_prints(NESTED)])

    def test_one_record_edited_leaves_the_other(self):
        edited = _prints(DSL.replace('"Агафья"', '"Агафія"'))
        self.assertEqual(_prints(DSL)[1], edited[1])

    def test_how_verso_reads_a_roll_does_not_count(self):
        roll = ('census = census_records("ГАВО", "162", "8", "100", "Глуповы Горы", 1858,\n'
                '    household("17", member(1, person("Ѳома"), CensusRole.HEAD, age=47)),\n'
                '    single_age_column=False)\n')
        flagged = roll.replace("single_age_column=False)", "single_age_column=False, female_previous_age=False)")
        self.assertEqual(_prints(roll), _prints(flagged))
        self.assertNotEqual(_prints(roll), _prints(roll.replace("single_age_column=False", "single_age_column=True")))


def _entry(file: str, fp: str) -> ratchet.Entry:
    return ratchet.Entry(file, fp, "")


_P = tuple(ratchet.RecordPrint("birth", n, f"fp{n}", f"birth {n}") for n in range(4))


class TheCheck(unittest.TestCase):
    P = _P

    def kinds(self, entries: list[ratchet.Entry], records: list[tuple[bool, ratchet.RecordPrint]]) -> list[str]:
        return [f.kind for f in ratchet.check_file(entries, records)]

    def test_a_line_matched_by_its_unreviewed_record_is_silent(self):
        self.assertEqual([], self.kinds([_entry("f", "fp0")], [(True, self.P[0])]))

    def test_a_reviewed_record_makes_its_line_stale(self):
        self.assertEqual(["stale"], self.kinds([_entry("f", "fp0")], [(False, self.P[0])]))

    def test_a_record_gone_with_nothing_unreviewed_beside_it(self):
        # Reviewed with an edit, or removed: prunable.
        found = ratchet.check_file([_entry("f", "fp9")], [(False, self.P[1])])
        self.assertEqual(["gone"], [f.kind for f in found])
        self.assertTrue(found[0].prunable)

    def test_a_record_gone_beside_an_unlisted_unreviewed_one_is_a_change(self):
        found = ratchet.check_file([_entry("f", "fp9"), _entry("f", "fp0")],
                                   [(True, self.P[0]), (True, self.P[1])])
        self.assertEqual(["changed"], [f.kind for f in found])
        self.assertFalse(found[0].prunable)
        self.assertIn("birth 1", found[0].note)

    def test_one_line_takes_one_record(self):
        self.assertEqual(["changed"], self.kinds([_entry("f", "fp0"), _entry("f", "fp0")],
                                                 [(True, self.P[0]), (True, self.P[1])]))

    def test_the_list_never_grows(self):
        base = [_entry("a", "fp0"), _entry("a", "fp1")]
        self.assertEqual([], ratchet.added(base, [_entry("b", "fp1")]), "a git mv keeps its lines")
        self.assertEqual(["fp2"], [e.fingerprint for e in ratchet.added(base, [_entry("a", "fp2")])])

    def test_drop_takes_as_many_as_named(self):
        entries = [_entry("a", "fp0"), _entry("a", "fp0"), _entry("a", "fp1")]
        self.assertEqual(["fp0", "fp1"],
                         [e.fingerprint for e in ratchet.drop(entries, {("a", "fp0"): 1})])

    def test_rebind_repoints_a_changed_line_at_the_record_with_its_label(self):
        # Record 1 edited (fp0 → fp9), its line still labelled «birth 1».
        line = ratchet.Entry("f", "fp0", "birth 1")
        edited = ratchet.RecordPrint("birth", 1, "fp9", "birth 1")
        out, refused = ratchet.rebind([line, ratchet.Entry("f", "fp2", "birth 2")],
                                      [(True, edited), (True, self.P[2])])
        self.assertEqual([], refused)
        self.assertEqual(["fp9", "fp2"], [e.fingerprint for e in out])

    def test_rebind_refuses_a_record_whose_number_or_leaf_changed(self):
        line = ratchet.Entry("f", "fp0", "birth 1")
        renumbered = ratchet.RecordPrint("birth", 1, "fp9", "birth 7")
        out, refused = ratchet.rebind([line], [(True, renumbered)])
        self.assertEqual(["changed"], [f.kind for f in refused])
        self.assertEqual([line], out)

    def test_rebind_refuses_a_label_it_cannot_pair_one_to_one(self):
        # One line, two held records of its label (a repeated number): a guess.
        line = ratchet.Entry("f", "fp0", "birth 1")
        held = [(True, ratchet.RecordPrint("birth", n, f"fp{n}9", "birth 1")) for n in (1, 2)]
        _, refused = ratchet.rebind([line], held)
        self.assertEqual(1, len(refused))
        self.assertIn("не угадать", refused[0].note)

    def test_a_rebound_line_is_not_an_added_one(self):
        base = [_entry("f", "fp0")]
        now = [_entry("f", "fp9")]
        rebound = ratchet.rebound(ratchet.added(base, now), ratchet.added(now, base),
                                  {("f", "fp9"): "birth 1"}, {("f", "fp0"): "birth 1"})
        self.assertEqual(now, rebound)

    def test_a_line_carried_over_to_another_record_is_added(self):
        base, now = [_entry("f", "fp0")], [_entry("f", "fp9")]
        for what, label_now, label_base in (
                ("another record", {("f", "fp9"): "birth 2"}, {("f", "fp0"): "birth 1"}),
                ("another file", {("g", "fp9"): "birth 1"}, {("f", "fp0"): "birth 1"}),
                # The old print still stands in the file (reviewed, not edited):
                # the CLI leaves it out of label_base, so nothing stands in for it.
                ("a reviewed record's line", {("f", "fp9"): "birth 1"}, {})):
            with self.subTest(what):
                self.assertEqual([], ratchet.rebound(ratchet.added(base, now), ratchet.added(now, base),
                                                     label_now, label_base))

    def test_the_list_reads_back(self):
        entries = [ratchet.Entry("1887/b.py", "fp0", "birth 1 ж, л. 341об")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ratchet.LIST_FILE
            path.write_text(ratchet.format_list(entries), encoding="utf-8")
            self.assertEqual(entries, ratchet.read_list(path))


class AVillage(unittest.TestCase):
    """The loader, the CLI check and its prune, on a village written to disk."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.village = Path(self._tmp.name) / "Тестовка"
        (self.village / "1887").mkdir(parents=True)
        self.dsl = self.village / "1887" / "t_births_1887.py"
        self.dsl.write_text(DSL, encoding="utf-8")
        self.listed = ratchet.record_prints(DSL)[0]
        (self.village / ratchet.LIST_FILE).write_text(
            ratchet.format_list([ratchet.Entry("1887/t_births_1887.py", self.listed.fingerprint,
                                               self.listed.label)]), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def admitted_records(self) -> list[bool]:
        (_, _, records), = list(discover_records(str(self.village)))
        assert isinstance(records, BirthRecords)
        return [admitted(r) for r in records.records]

    def findings(self) -> list[str]:
        return [f.kind for f in review_ratchet.village_findings(self.village)]

    def test_the_listed_record_passes_and_the_other_is_held(self):
        self.assertEqual([True, False], self.admitted_records())
        self.assertEqual([], self.findings())

    def test_a_listed_record_edited_without_review_is_held_and_fails_the_check(self):
        self.dsl.write_text(DSL.replace('"Агафья"', '"Агафія"'), encoding="utf-8")
        self.assertEqual([False, False], self.admitted_records())
        self.assertEqual(["changed"], self.findings())

    def test_a_correction_without_review_is_rebound_and_stays_on_geni(self):
        self.dsl.write_text(DSL.replace('"Агафья"', '"Агафія"'), encoding="utf-8")
        self.assertEqual(0, review_ratchet.main(["--village", str(self.village),
                                                 "--rebind", "1887/t_births_1887.py"]))
        self.assertEqual([], self.findings())
        self.assertEqual([True, False], self.admitted_records())
        line, = ratchet.read_list(self.village / ratchet.LIST_FILE)
        self.assertEqual(ratchet.record_prints(self.dsl.read_text(encoding="utf-8"))[0].fingerprint,
                         line.fingerprint)

    def test_a_renumbered_record_is_not_rebound(self):
        before = (self.village / ratchet.LIST_FILE).read_text(encoding="utf-8")
        self.dsl.write_text(DSL.replace("birth(1,", "birth(3,"), encoding="utf-8")
        self.assertEqual(1, review_ratchet.main(["--village", str(self.village),
                                                 "--rebind", "1887/t_births_1887.py"]))
        self.assertEqual(before, (self.village / ratchet.LIST_FILE).read_text(encoding="utf-8"))
        self.assertEqual(["changed"], self.findings())

    def test_a_new_unreviewed_record_is_held(self):
        self.dsl.write_text(DSL.replace(
            "                       ),\n          ),",
            "                       birth(3, Gender.MALE, 20, 21, child=person(\"Петръ\")),\n"
            "                       ),\n          ),"), encoding="utf-8")
        self.assertEqual([True, False, False], self.admitted_records())
        self.assertEqual([], self.findings())

    def test_reviewing_it_leaves_a_line_that_prune_strikes(self):
        self.dsl.write_text(DSL.replace("birth(1, Gender.FEMALE, 9, 10,",
                                        "birth(1, Gender.FEMALE, 9, 10, reviewed=True,"), encoding="utf-8")
        self.assertEqual([True, False], self.admitted_records())
        self.assertEqual(["stale"], self.findings())
        self.assertEqual(1, review_ratchet.main(["--village", str(self.village)]))
        self.assertEqual(0, review_ratchet.main(["--village", str(self.village), "--prune"]))
        self.assertEqual([], ratchet.read_list(self.village / ratchet.LIST_FILE))

    def test_a_review_with_an_edit_is_struck_by_hand(self):
        self.dsl.write_text(DSL.replace('child=person("Агафья")', 'reviewed=True, child=person("Агафія")')
                            .replace('child=person("Иванъ")', 'reviewed=True, child=person("Иванъ")'),
                            encoding="utf-8")
        self.assertEqual(["gone"], self.findings())
        drop = f"1887/t_births_1887.py:{self.listed.fingerprint}"
        self.assertEqual(0, review_ratchet.main(["--village", str(self.village), "--drop", drop]))

    def test_a_record_set_bound_to_two_names_is_paired_once(self):
        # One book bound under two names (`alias = births`) built its records
        # twice, and two prints were paired with four records.
        aliased = DSL + "\nt_births_1887 = births\n"
        self.dsl.write_text(aliased, encoding="utf-8")
        listed = ratchet.record_prints(aliased)[0]   # a module-level assignment is in every print
        (self.village / ratchet.LIST_FILE).write_text(
            ratchet.format_list([ratchet.Entry("1887/t_births_1887.py", listed.fingerprint,
                                               listed.label)]), encoding="utf-8")
        module = load_module(self.dsl)
        self.assertEqual(2, len(ratchet.runtime_records(vars(module))))
        self.assertEqual([True, False], self.admitted_records())
        self.assertEqual([], self.findings())

    def test_a_file_that_cannot_be_paired_is_refused(self):
        self.dsl.write_text(DSL + textwrap.dedent('''
            spare = birth(14, Gender.MALE, child=person("Иванъ"))
        '''), encoding="utf-8")
        with self.assertRaises(ratchet.RatchetError):
            list(discover_records(str(self.village)))

    def test_seeding_lists_what_terraform_state_holds(self):
        # «Already on Geni» is what the state says: the record whose document
        # is there is listed, the other is held from now on.
        (self.village / ratchet.LIST_FILE).unlink()
        state = self.village / "state.txt"
        state.write_text("geni_document.birth_of_agafija_petrovna_1_1887\n"
                         "geni_profile.birth_of_ioann_petrovich_2_1887\n", encoding="utf-8")
        self.assertEqual(0, review_ratchet.main(["--village", str(self.village), "--seed",
                                                 "--state-file", str(state)]))
        self.assertEqual(["birth 1 ж, л. 341об"],
                         [e.label for e in ratchet.read_list(self.village / ratchet.LIST_FILE)])
        self.assertEqual([True, False], self.admitted_records())

    def test_seeding_refuses_a_village_that_has_a_list(self):
        self.assertEqual(2, review_ratchet.main(["--village", str(self.village), "--seed",
                                                 "--state-file", str(self.dsl)]))


def test_strike_takes_one_line_of_the_file(tmp_path: Path):
    entries = [ratchet.Entry("1900/a.py", "f1", "№ 1"), ratchet.Entry("1900/a.py", "f1", "№ 1"),
               ratchet.Entry("1900/b.py", "f2", "№ 2")]
    (tmp_path / ratchet.LIST_FILE).write_text(ratchet.format_list(entries), encoding="utf-8")
    assert ratchet.listed(tmp_path, "1900/a.py") == ["f1", "f1"]
    ratchet.strike(tmp_path, "1900/a.py", "f1")
    assert ratchet.listed(tmp_path, "1900/a.py") == ["f1"]
    assert (tmp_path / ratchet.LIST_FILE).read_text(encoding="utf-8") == ratchet.format_list([entries[0], entries[2]])
    assert ratchet.listed(tmp_path / "elsewhere", "1900/a.py") == []


if __name__ == "__main__":
    unittest.main()


def test_ru_writes_its_leaf_label():
    from verso.ru.dsl.calls import CALLS
    assert CALLS.page_label == "л."
