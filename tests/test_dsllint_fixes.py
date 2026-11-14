from __future__ import annotations

import ast
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from verso.ru.linters import fixes


def src(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


WRAPPED = src('''
    from verso.ru.dsl import person
    a = person(
        "Николай",
        "Феодоров",
        last_name_orig="Бекешев",
    )
''')


class JoinLines(unittest.TestCase):
    def test_keeps_the_indentation_of_the_first_line(self):
        joined = fixes.join_lines(["        person(", '            "Пётр",', '            "Иоаннов")'])
        self.assertTrue(joined.startswith("        person("))

    def test_tightens_brackets_and_commas(self):
        joined = fixes.join_lines(["person(", '  "Пётр" ,', '  "Иоаннов" )'])
        self.assertEqual('person("Пётр", "Иоаннов")', joined)

    def test_drops_the_magic_trailing_comma(self):
        joined = fixes.join_lines(["person(", '  "Пётр",', ")"])
        self.assertEqual('person("Пётр")', joined)


class FixSource(unittest.TestCase):
    def test_wrapped_call_is_joined(self):
        new, joined, skipped = fixes.fix_source(WRAPPED)
        self.assertEqual(1, joined)
        self.assertEqual([], skipped)
        self.assertIn('person("Николай", "Феодоров", last_name_orig="Бекешев")', new)

    def test_the_parse_tree_is_unchanged(self):
        new, _, _ = fixes.fix_source(WRAPPED)
        self.assertEqual(ast.dump(ast.parse(WRAPPED)), ast.dump(ast.parse(new)))

    def test_already_single_line_is_left_alone(self):
        source = src('''
            from verso.ru.dsl import person
            a = person("Николай", "Феодоров")
        ''')
        new, joined, skipped = fixes.fix_source(source)
        self.assertEqual((source, 0, []), (new, joined, skipped))

    def test_call_with_a_comment_is_skipped(self):
        source = src('''
            from verso.ru.dsl import person
            b = person("Пётр",  # scribal variant
                       "Иоаннов")
        ''')
        new, joined, skipped = fixes.fix_source(source)
        self.assertEqual(0, joined)
        self.assertEqual(source, new)
        self.assertEqual(1, len(skipped))
        self.assertIn("comment", skipped[0])

    def test_several_calls_are_all_joined(self):
        source = src('''
            from verso.ru.dsl import person
            a = person(
                "Николай",
                "Феодоров")
            b = person(
                "Пётр",
                "Иоаннов")
        ''')
        new, joined, _ = fixes.fix_source(source)
        self.assertEqual(2, joined)
        self.assertIn('person("Николай", "Феодоров")', new)
        self.assertIn('person("Пётр", "Иоаннов")', new)

    def test_syntax_error_rewrites_nothing(self):
        source = "person(\n"
        new, joined, skipped = fixes.fix_source(source)
        self.assertEqual((source, 0), (new, joined))
        self.assertIn("SyntaxError", skipped[0])

    def test_trailing_newline_is_preserved(self):
        new, _, _ = fixes.fix_source(WRAPPED)
        self.assertTrue(new.endswith("\n"))


class FixFile(unittest.TestCase):
    def _write(self, tmp: str, text: str) -> Path:
        p = Path(tmp) / "year.py"
        p.write_text(text, encoding="utf-8")
        return p

    def test_dry_run_leaves_the_file_alone(self):
        with TemporaryDirectory() as tmp:
            p = self._write(tmp, WRAPPED)
            result = fixes.fix_file(p, dry_run=True)
            self.assertEqual(1, result.joined)
            self.assertEqual(WRAPPED, p.read_text(encoding="utf-8"))

    def test_write_mode_rewrites(self):
        with TemporaryDirectory() as tmp:
            p = self._write(tmp, WRAPPED)
            fixes.fix_file(p)
            self.assertIn('person("Николай", "Феодоров", last_name_orig="Бекешев")',
                          p.read_text(encoding="utf-8"))

    def test_run_exits_non_zero_only_on_a_skip(self):
        with TemporaryDirectory() as tmp:
            clean = self._write(tmp, WRAPPED)
            _, code = fixes.run([clean], dry_run=True)
            self.assertEqual(0, code)

            skipped = Path(tmp) / "commented.py"
            skipped.write_text(src('''
                from verso.ru.dsl import person
                b = person("Пётр",  # note
                           "Иоаннов")
            '''), encoding="utf-8")
            _, code = fixes.run([skipped], dry_run=True)
            self.assertEqual(1, code)


class Report(unittest.TestCase):
    def test_nothing_to_do(self):
        self.assertIn("nothing to join", fixes.format_report([]))

    def test_counts_files_and_calls(self):
        results = [fixes.FixResult(path=Path("1894/births.py"), joined=3, skipped=())]
        text = fixes.format_report(results)
        self.assertIn("joined 3 wrapped call(s)", text)
        self.assertIn("3 call(s) in 1 file(s)", text)

    def test_dry_run_wording(self):
        results = [fixes.FixResult(path=Path("x.py"), joined=1, skipped=())]
        self.assertIn("would join", fixes.format_report(results, dry_run=True))


if __name__ == "__main__":
    unittest.main()
