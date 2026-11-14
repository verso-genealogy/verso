"""verso.ru.notes.stale_notes — the notes a proofread has made stale.

The fixtures model a proofread that replaces a record's father and mother: a
1876 birth № м7, read first as «Григорій Фалалеевъ ⚭ Агафья Ежевикина»,
proofread to «Григорій Тюфяевъ ⚭ Ульяна Кувшинникова», while another «Григорій
Фалалеевъ», of a neighbouring village, goes on being written in other records.
"""
from __future__ import annotations

import io
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from verso.ru.notes import stale_notes as sn

HEAD = '''from verso.ru.dsl import Gender, birth, birth_month, birth_records, page, person
'''


def births(*records: str, header: str = "") -> str:
    body = ",\n".join(records)
    return f'''{HEAD}
{header}
selo = birth_records("ГАВО", "381", "4", "10", "Село", "Покровская", 1876,
    *page("612об",
          *birth_month(None,
{body},
          )),
)
'''


def b(num: int, father: str, mother: str, *, gp: str = 'person("Ѳедоръ", "Егоровъ")', sex: str = "MALE") -> str:
    return (f"birth({num}, Gender.{sex}, 9, 10, child=person(\"Трофимъ\"), father={father}, "
            f"mother={mother}, god_parent1={gp})")


OLD_M5 = b(7, 'person("Григорій", "Фалалеевъ", residence="Горелово")', 'person("Агафья", "Ежевикина")')
NEW_M5 = b(7, 'person("Григорій", "Тюфяевъ", residence="Горелово")', 'person("Ульяна", "Кувшинникова")')
M3 = b(4, 'person("Фока", "Семеновъ")', 'person("Мелания", "Лаврентьева")',
       gp='person("Григорій", "Фалалеевъ", residence="Горелово")')


def change_texts(found: list[sn.Change]) -> list[tuple[str, str, str]]:
    return [(c.where, c.old, c.new) for c in found]


class WhatChanged(unittest.TestCase):
    def test_a_reading_is_a_change_addressed_by_its_record(self):
        found = sn.changes(births(OLD_M5), births(NEW_M5), "1876/selo_births_1876.py")
        self.assertEqual(change_texts(found), [
            ("birth 7 MALE · father", "Григорій Фалалеевъ", "Григорій Тюфяевъ"),
            ("birth 7 MALE · mother", "Агафья Ежевикина", "Ульяна Кувшинникова"),
        ])
        self.assertTrue(all(c.kind == sn.READING for c in found))
        self.assertEqual(found[0].leaf, "612об")
        self.assertEqual(found[0].number, ("7", "м"))

    def test_orthography_alone_is_a_spelling(self):
        old = births(b(1, 'person("Алексій", "Фалалеевъ")', 'person("Агафья", "Андреева")'))
        new = births(b(1, 'person("Алексѣй", "Фалалеевъ")', 'person("Агафія", "Андреева")'))
        found = sn.changes(old, new, "1876/f.py")
        self.assertEqual([c.kind for c in found], [sn.SPELLING, sn.SPELLING])

    def test_case_space_question_mark_and_an_added_word_are_no_change(self):
        old = births(b(1, 'person("Григорій", "Фалалеевъ?")', 'person("Агафья")'))
        new = births(b(1, 'person("Григорій ", "фалалеевъ")', 'person("Агафья", "Андреева")'))
        self.assertEqual(sn.changes(old, new, "1876/f.py"), [])

    def test_an_inserted_record_shifts_nothing(self):
        other = b(5, 'person("Петръ", "Ивановъ")', 'person("Анна", "Петрова")')
        found = sn.changes(births(M3, OLD_M5), births(M3, other, NEW_M5), "1876/f.py")
        self.assertEqual([c.where for c in found], ["birth 7 MALE · father", "birth 7 MALE · mother"])

    def test_a_record_moved_and_changed_is_found(self):
        moved = births(M3, header="").replace(
            '*page("612об",', f'*page("613об", *birth_month(None, {NEW_M5})),\n    *page("612об",')
        found = sn.changes(births(OLD_M5, M3), moved, "1876/f.py")
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].leaf, "613об")

    def test_a_renumbered_record_pairs_by_its_shape(self):
        found = sn.changes(births(OLD_M5), births(NEW_M5.replace("birth(7,", "birth(8,")), "1876/f.py")
        self.assertEqual([c.old for c in found], ["Григорій Фалалеевъ", "Агафья Ежевикина"])

    def test_a_roll_member_is_addressed_by_household_and_number(self):
        roll = '''from verso.ru.dsl import census_records, household, member
census = census_records("ГАВО", "301", "5", "1", "Село", 1858,
    *page("511об", household("34",
        member(1, person("Лаврентій", "Карповъ"), None),
        member(6, person("{wife}", "Семенова"), CensusRole.WIFE, ref_member=1))))
'''
        found = sn.changes(roll.format(wife="Фекла"), roll.format(wife="Мелания"), "1858/c.py")
        self.assertEqual(change_texts(found), [("household 34 · member 6", "Фекла Семенова", "Мелания Семенова")])

    def test_a_one_word_name_is_listed_without_a_pair(self):
        old = births(b(1, 'person("Иванъ")', 'person("Анна")').replace('"Трофимъ"', '"Марѳа"'))
        new = births(b(1, 'person("Иванъ")', 'person("Анна")').replace('"Трофимъ"', '"Марфа"'))
        (found,) = sn.changes(old, new, "1876/f.py")
        self.assertEqual((found.old, found.new, found.pairs), ("Марѳа", "Марфа", ()))

    def test_a_three_word_name_keeps_its_sequence(self):
        old = births(b(21, 'person("Тихонъ", "Лукинъ")', 'person("Параскева", "Игнатьева")',
                       gp='person("Иванъ", "Павловъ", last_name_orig="Фалалеевъ")'))
        new = births(b(21, 'person("Тихонъ", "Лукинъ")', 'person("Параскева", "Игнатьева")',
                       gp='person("Павелъ", "Фалалеевъ")'))
        (found,) = sn.changes(old, new, "1876/f.py")
        self.assertEqual([(p.first, p.second) for p in found.pairs], [("Иванъ", "Павловъ"), ("Павловъ", "Фалалеевъ")])
        self.assertEqual(found.sequences, (("Иванъ", "Павловъ", "Фалалеевъ"),))


DSL = "Село/1876/selo_births_1876.py"
# The repository's notes, as its verso.toml names them — the corpus's own four.
WORKSPACE = ('schema = 1\n[notes]\nglobs = ["{village}/*.md", "{village}/families/**/*.md", '
             '"parish-notes/{slug}/**/*.md", "{village}/generate_config_names.py"]\n')


def report(notes: dict[str, str], sources: dict[str, str] | None = None, *, show_settled: bool = False,
           old: str = births(OLD_M5), new: str = births(NEW_M5)) -> sn.Report:
    """Notes keyed by path: a `.py` path is read as Python, anything else as Markdown."""
    found = sn.changes(old, new, "1876/selo_births_1876.py")
    parsed: list[sn.Note] = []
    for path, text in notes.items():
        parsed += sn.python_notes(text, path) if path.endswith(".py") else [sn.markdown_note(text, path)]
    return sn.make_report("Село", "A..B", "B", found, parsed, sources or {DSL: new}, show_settled)


def shown(r: sn.Report) -> list[tuple[str, int, str]]:
    return sorted((h.path, h.line, h.stale.text) for h in r.shown)


class WhereTheOldFormIsWritten(unittest.TestCase):
    def test_inflected_capitalised_marked_up_and_wrapped(self):
        md = ("в 1876 г. у него уже сын Трофимъ при жене Агафіи Ежевикиной.\n\n"
              "🔴 **ДВЕ АГАФЬИ ЕЖЕВИКИНЫ** — так и было.\n\n"
              "мать — **Агафья**\nЕжевикина, сверено.\n")
        self.assertEqual(shown(report({"Село/ARCHIVES.md": md})), [
            ("Село/ARCHIVES.md", 1, "Агафья Ежевикина"),
            ("Село/ARCHIVES.md", 3, "Агафья Ежевикина"),
            ("Село/ARCHIVES.md", 5, "Агафья Ежевикина"),
        ])

    def test_a_pair_wraps_across_comment_lines(self):
        dsl = births(NEW_M5, header="# 🔴 мать — Агафья\n# Ежевикина, сверено при 5×")
        self.assertEqual(shown(report({DSL: dsl}, {DSL: births(NEW_M5)})), [(DSL, 3, "Агафья Ежевикина")])

    def test_not_one_word_and_not_across_punctuation(self):
        md = "Агафья родила сына. Ежевикина — фамилия соседей. Григорій ⚭ Агафья, Ежевикина.\n"
        self.assertEqual(shown(report({"Село/ARCHIVES.md": md})), [])

    def test_a_spelling_is_looked_for_letter_by_letter(self):
        old = births(b(12, 'person("Мартынъ", "Ѳоминъ")', 'person("Прасковья", "Иванова")'))
        new = births(b(12, 'person("Мартынъ", "Фоминъ")', 'person("Прасковья", "Иванова")'))
        notes = {"Село/ARCHIVES.md": "МК 1876 даёт Мартына Ѳомина.\n", "Село/README.md": "А вот Мартынъ Фоминъ.\n"}
        r = report(notes, {DSL: new}, old=old, new=new)
        self.assertEqual(shown(r), [("Село/ARCHIVES.md", 1, "Мартынъ Ѳоминъ")])
        self.assertEqual(r.stales[0].kind, sn.SPELLING)

    def test_a_note_that_already_says_so_is_settled(self):
        md = ("там Григорій Тюфяевъ ⚭ Ульяна Кувшинникова, а не «Агафья Ежевикина».\n\n"
              "«Агафья Ежевикина» → «Ульяна Кувшинникова».\n\n"
              "⛔ Первое чтение дало «Агафья Ежевикина».\n\n"
              "«Агафья Ежевикина» снята вычиткой.\n")
        self.assertEqual(shown(report({"Село/ARCHIVES.md": md})), [])
        self.assertEqual(len(shown(report({"Село/ARCHIVES.md": md}, show_settled=True))), 4)

    def test_the_part_of_the_name_that_stayed_is_no_correction(self):
        """2026-10-26: a surname re-read, the given name and the patronymic kept — the old note writes the
        kept pair, which the new name writes too, and it was taken for the new name beside the old."""
        old = births(b(12, 'person("Фома", "Фомичъ", last_name_orig="Опискинъ")', 'person("Прасковья", "Ильинишна")'))
        new = births(b(12, 'person("Фома", "Фомичъ", last_name_orig="Ростаневъ")', 'person("Прасковья", "Ильинишна")'))
        dsl = births(b(12, 'person("Фома", "Фомичъ", last_name_orig="Ростаневъ")', 'person("Прасковья", "Ильинишна")'),
                     header="# отецъ — Фома Фомичъ Опискинъ, приживалъ")
        self.assertEqual(shown(report({DSL: dsl}, {DSL: new}, old=old, new=new)), [(DSL, 3, "Фомичъ Опискинъ")])

    def test_a_hypothesis_is_not_a_retraction(self):
        md = "МК 1876 г. даёт ему жену Агафью Ежевикину; перемена жены или ошибка чтения отчества.\n"
        self.assertEqual(len(shown(report({"Село/ARCHIVES.md": md}))), 1)


class APairTheDSLStillWrites(unittest.TestCase):
    """«Григорій Фалалеевъ» is also the godfather of № м4, so a note naming him may
    be about that man — it counts only where it is tied to № м7."""

    def father_hits(self, notes: dict[str, str], sources: dict[str, str] | None = None) -> list[tuple[str, int]]:
        r = report(notes, sources or {DSL: births(M3, NEW_M5)}, old=births(M3, OLD_M5), new=births(M3, NEW_M5))
        return [(p, line) for p, line, text in shown(r) if text == "Григорій Фалалеевъ"]

    def test_its_year_cited_before_the_name_ties_it(self):
        md = "7 января 1878 г. венчается Григорій Фалалеевъ — а МК 1876 г. даёт Григорія Фалалеева отцом.\n"
        self.assertEqual(len(self.father_hits({"Село/ARCHIVES.md": md})), 1)

    def test_a_year_after_the_name_is_another_events(self):
        md = "восприемникъ у его сына — Григорій Фалалеевъ. Родоначальник — Прохоръ Митрофановъ († 3 мая 1876).\n"
        self.assertEqual(self.father_hits({"Село/ARCHIVES.md": md}), [])

    def test_a_headline_year_after_the_name_ties_it(self):
        md = "1879 год указал происхождение. 🔴 **ГРИГОРІЙ ФАЛАЛЕЕВЪ — ОТЕЦ УЖЕ В 1876 г.**\n"
        self.assertEqual(len(self.father_hits({"Село/ARCHIVES.md": md})), 1)

    def test_the_markdown_section_gives_the_year(self):
        md = "##### Что дал 1876 год\n\nГореловскій Григорій Фалалеевъ с женой.\n\n##### 1878\n\nГригорій Фалалеевъ венчается.\n"
        self.assertEqual(self.father_hits({"Село/ARCHIVES.md": md}), [("Село/ARCHIVES.md", 3)])

    def test_another_record_cited_beside_it_unties_it(self):
        md = "в 1876 г. стоит воспріемникомъ «Григорій Фалалеевъ» (ч. 1 № м4).\n"
        self.assertEqual(self.father_hits({"Село/ARCHIVES.md": md}), [])

    def test_its_number_or_its_leaf_ties_it(self):
        md = "в 1876 г. Григорій Фалалеевъ (№ м7) отец.\n\nвосприемница у Григорія Фалалеева (л. 612об).\n"
        self.assertEqual(len(self.father_hits({"Село/ARCHIVES.md": md})), 2)

    def test_in_a_file_that_writes_the_pair_only_the_record_ties_it(self):
        about_m3 = births(M3, NEW_M5, header="# Григорій Фалалеевъ — воспріемникъ в 1876 г.")
        about_m5 = births(M3, NEW_M5, header="# Григорій Фалалеевъ — отец (№ м7) в 1876 г.")
        sources = {DSL: births(M3, NEW_M5)}
        self.assertEqual(self.father_hits({DSL: about_m3}, sources), [])
        self.assertEqual(len(self.father_hits({DSL: about_m5}, sources)), 1)

    def test_the_block_above_a_record_writing_the_pair_is_that_records(self):
        m3_note = "# 🔴 Григорій Фалалеевъ — воспріемникъ, и в 1876 г. отцом № м7 его не делает ничто\n" + M3
        text = births(m3_note, NEW_M5)
        self.assertEqual(self.father_hits({DSL: text}, {DSL: text}), [])

    def test_another_years_file_writing_the_pair_quotes_its_own_record(self):
        other = "Село/1878/selo_births_1878.py"
        text = births(b(3, 'person("Григорій", "Фалалеевъ")', 'person("Домна", "Андреева")'),
                      header="# Григорій Фалалеевъ и жена его Домна — как в 1876 г.")
        sources = {DSL: births(M3, NEW_M5), other: text}
        self.assertEqual(self.father_hits({other: text}, sources), [])

    def test_a_namesake_pair_needs_the_whole_old_name(self):
        old = births(b(21, 'person("Тихонъ", "Лукинъ")', 'person("Параскева", "Игнатьева")',
                       gp='person("Иванъ", "Павловъ", last_name_orig="Фалалеевъ")'))
        new = births(b(21, 'person("Тихонъ", "Лукинъ")', 'person("Параскева", "Игнатьева")',
                       gp='person("Павелъ", "Фалалеевъ")'))
        md = "Мавра Ивана Павлова умерла.\n\nвоспріемникъ — отпускной солдатъ **Иванъ Павловъ Фалалеевъ**.\n"
        r = report({"Село/ARCHIVES.md": md}, {DSL: new}, old=old, new=new)
        self.assertEqual({line for _, line, _ in shown(r)}, {3})


class Headers(unittest.TestCase):
    def test_a_hold_note_over_no_held_record(self):
        source = births(NEW_M5, header="# reviewed=False: прочитано один раз при 4.2×.")
        header = sn.stale_header(source, DSL)
        assert header is not None
        self.assertEqual((header.line, header.text), (3, "reviewed=False: прочитано один раз при 4.2×."))

    def test_a_file_still_holding_a_record(self):
        source = births(NEW_M5, header="# reviewed=False: прочитано один раз.").replace(
            '*page("612об",', '*page("612об", reviewed=False,')
        self.assertIsNone(sn.stale_header(source, DSL))

    def test_only_the_header_and_only_the_note_form(self):
        below = births(NEW_M5).replace("    *page(", "    # reviewed=False: снято 13.10\n    *page(")
        history = births(NEW_M5, header="# records added by that sweep are reviewed=False.")
        self.assertIsNone(sn.stale_header(below, DSL))
        self.assertIsNone(sn.stale_header(history, DSL))


class Command(unittest.TestCase):
    """The whole command over a scratch git repository."""

    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        prev = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, prev)
        self.git("init", "-q")
        dsl = self.root / DSL
        dsl.parent.mkdir(parents=True)
        dsl.write_text(births(M3, OLD_M5, header="# reviewed=False: прочитано один раз."), encoding="utf-8")
        (self.root / "Село/ARCHIVES.md").write_text("МК 1876 даёт Григорія Фалалеева при жене Агафьѣ Ежевикиной.\n",
                                                   encoding="utf-8")
        rules = self.root / "parish-notes/selo/README.md"
        rules.parent.mkdir(parents=True)
        rules.write_text("Правило: Агафья Ежевикина — жена гореловского Григорія.\n", encoding="utf-8")
        (self.root / "Село/generate_config_names.py").write_text("# agafja — «Агафья Ежевикина» 1876\nX = 1\n",
                                                                 encoding="utf-8")
        (self.root / "verso.toml").write_text(WORKSPACE, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "read")
        dsl.write_text(births(M3, NEW_M5, header="# reviewed=False: прочитано один раз."), encoding="utf-8")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.root, check=True)

    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = sn.main(["--village", "Село", *args])
        return code, out.getvalue()

    def test_the_notes_are_searched_in_the_workspaces_order(self):
        tree = sn.Tree(self.root, None)
        globs = ["{village}/generate_config_names.py", "parish-notes/{slug}/**/*.md", "{village}/*.md"]
        self.assertEqual(sn.note_files(tree, "Село", [DSL], globs),
                         [DSL, "Село/generate_config_names.py", "parish-notes/selo/README.md", "Село/ARCHIVES.md"])

    def test_a_glob_naming_the_slug_is_skipped_without_one(self):
        tree = sn.Tree(self.root, None)
        self.assertEqual(sn.note_files(tree, "Село", [], ["parish-notes/{slug}/**/*.md", "{village}/*.md"]),
                         ["Село/ARCHIVES.md"])

    def test_without_notes_only_the_dsl_is_read(self):
        (self.root / "verso.toml").write_text("schema = 1\n", encoding="utf-8")
        code, out = self.run_main("--rev", "HEAD..")
        self.assertEqual(code, 1)
        for where in ("Село/ARCHIVES.md", "parish-notes/selo/README.md", "Село/generate_config_names.py"):
            self.assertNotIn(where, out)

    def test_a_repo_without_verso_toml_is_refused(self):
        (self.root / "verso.toml").unlink()
        err = io.StringIO()
        with redirect_stderr(err):
            code, _ = self.run_main("--rev", "HEAD..")
        self.assertEqual(code, 2)
        self.assertIn("нет verso.toml", err.getvalue())

    def test_the_working_tree_against_head(self):
        code, out = self.run_main("--rev", "HEAD..")
        self.assertEqual(code, 1)
        self.assertIn("«Агафья Ежевикина» → «Ульяна Кувшинникова»", out)
        for where in ("Село/ARCHIVES.md:1", "parish-notes/selo/README.md:1", "Село/generate_config_names.py:1"):
            self.assertIn(where, out)
        self.assertIn(f"{DSL}:3  reviewed=False: прочитано один раз.", out)

    def test_a_committed_proofread_and_the_notes_at_a_revision(self):
        self.git("commit", "-qam", "proofread")
        code, out = self.run_main("--rev", "HEAD~1..HEAD", "--notes-at", "HEAD~1", "--json")
        self.assertEqual(code, 1)
        self.assertIn('"Агафья Ежевикина"', out)
        self.assertIn('"notes_at": "HEAD~1"', out)

    def test_nothing_changed(self):
        self.git("commit", "-qam", "proofread")
        (self.root / DSL).write_text(births(M3, NEW_M5), encoding="utf-8")
        self.git("commit", "-qam", "header")
        code, out = self.run_main("--rev", "HEAD..")
        self.assertEqual(code, 0)
        self.assertIn("изменённых имён 0", out)


class Folding(unittest.TestCase):
    def test_stems_take_a_case_ending(self):
        self.assertEqual(sn.stem(sn.reading_key("Григорій")), "григор")
        self.assertEqual(sn.stem(sn.reading_key("Агафья")), "агаф")
        self.assertEqual(sn.stem(sn.reading_key("Ежевикина")), "ежевикин")
        self.assertEqual(sn.stem(sn.spelling_key("Ѳоминъ")), "ѳомин")

    def test_a_given_name_by_its_base_form(self):
        self.assertEqual(sn.given_key("Іоаннъ"), sn.given_key("Иванъ"))
        self.assertNotEqual(sn.given_key("Агафья"), sn.given_key("Домна"))

    def test_parse_revs(self):
        self.assertEqual(sn.parse_revs("HEAD~1.."), ("HEAD~1", None))
        self.assertEqual(sn.parse_revs("A..B"), ("A", "B"))
        self.assertEqual(sn.parse_revs("A"), ("A", None))


if __name__ == "__main__":
    unittest.main()
