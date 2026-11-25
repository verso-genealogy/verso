import os
import tempfile
import unittest
from pathlib import Path

from verso.ru.exporters.csv import BirthRecordsCsvExporter
from verso.ru.exporters.base import RecordsExporter
from verso.ru.domain import Person
from verso.ru.dsl.records.births import Birth, BirthRecords
from tests.codepaths import code_files, module_name, package_dir


def walked() -> list[Path]:
    """The library's modules the LF guard reads."""
    return code_files("verso.core", "verso.ru")


class TestBirthCsvParentAges(unittest.TestCase):
    def _comment(self, **kw):
        birth = Birth(record_num=1, gender="муж", b_day=15, k_day=16, b_month=3, k_month=3,
                      child=Person("Иванъ", name_modern_orth="Иван"), father=None, mother=None,
                      god_parent1=None, god_parent2=None, **kw)
        records = BirthRecords(archive="ГАТО", fund="1", inventory="1", case="1", village="Заманиловка",
                               church="Троицкая", year=1920, records=[birth])
        import csv
        with tempfile.TemporaryDirectory() as tmpdir:
            name = BirthRecordsCsvExporter().export(records, tmpdir)
            with open(name, encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                return next(reader)[header.index("Комментарий")]

    def test_ages_follow_the_comment(self):
        self.assertEqual("Заявитель — отец; отцу 31, матери 30",
                         self._comment(comment="Заявитель — отец", father_age=31, mother_age=30))

    def test_without_ages_the_comment_is_as_it_was(self):
        self.assertEqual("Заявитель — отец", self._comment(comment="Заявитель — отец"))
        self.assertEqual("", self._comment())


class TestBirthRecordsCsvExporter(unittest.TestCase):

    def test_inherits_from_records_exporter(self):
        self.assertTrue(issubclass(BirthRecordsCsvExporter, RecordsExporter))  # type: ignore[reportUnnecessaryIsInstance]

    def test_export_creates_csv_file(self):
        child = Person("Иванъ", name_modern_orth="Иван")
        father = Person("Петръ", "Ивановъ", name_modern_orth="Петр", patr_old="Иванов", status="крестьянин")
        mother = Person("Марія", "Петрова", name_modern_orth="Мария", patr_old="Петрова")

        birth_record = Birth(record_num=1, gender="муж", b_day=15, k_day=16, b_month=3, k_month=3, child=child,
                             father=father, mother=mother, god_parent1=None, god_parent2=None)

        records = BirthRecords(
            archive="ГАТО",
            fund="1049",
            inventory="1",
            case="100",
            village="Заманиловка",
            church="Троицкая",
            year=1804,
            records=[birth_record]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                exporter = BirthRecordsCsvExporter()
                exporter.export(records)

                expected_file = os.path.join(tmpdir, "Заманиловка_1804_births.csv")
                self.assertTrue(os.path.exists(expected_file))

                with open(expected_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.assertIn("№", content)
                    self.assertIn("Иван", content)
            finally:
                os.chdir(original_cwd)


if __name__ == '__main__':
    unittest.main()


class CsvFilesAreWrittenWithLfEndings(unittest.TestCase):
    """`csv.writer` obeys RFC 4180 and terminates lines with CRLF.

    Every CSV this repo writes is committed, and the repo stores LF — so the
    default made each regeneration rewrite 225 files with nothing in them but
    carriage returns. In `git status` that is indistinguishable from real work:
    the churn was mistaken for someone's unfinished changes and left alone for
    months, and it buries the diffs that matter.
    """

    def test_the_shared_writer_terminates_with_lf(self):
        import io as _io

        from verso.ru.exporters.base import csv_writer
        buf = _io.StringIO(newline="")
        csv_writer(buf).writerow(["a", "b"])
        self.assertEqual("a,b\n", buf.getvalue())

    def test_the_shared_dict_writer_terminates_with_lf(self):
        import io as _io

        from verso.ru.exporters.base import csv_dict_writer
        buf = _io.StringIO(newline="")
        w = csv_dict_writer(buf, ["a", "b"])
        w.writeheader()
        w.writerow({"a": "1", "b": "2"})
        self.assertEqual("a,b\n1,2\n", buf.getvalue())

    def test_nothing_in_the_package_calls_a_csv_writer_directly(self):
        """The guard: anything reaching for the stdlib writers gets CRLF.

        Scoped to the whole package, and to `DictWriter` as well as `writer`,
        because the first version of this guard looked only for `csv.writer`
        under `verso/ru/exporters/` — and `verso/ru/cli/remove_duplicates.py` sat
        outside it building a bare `csv.DictWriter`, rewriting `names.csv`
        with CRLF. It missed on both axes at once.

        An explicit `lineterminator=` is allowed: stating it is the point, and
        `verso/ru/cli/names.py` legitimately passes `""` to compose a row by hand.
        """
        import ast as _ast

        offenders = []
        base = package_dir("verso.ru.exporters") / "base.py"
        self.assertGreaterEqual(len(walked()), 250, "modules of the library found")
        for module in walked():
            if module == base:
                continue
            for node in _ast.walk(_ast.parse(module.read_text(encoding="utf-8"))):
                if (isinstance(node, _ast.Call)
                        and isinstance(node.func, _ast.Attribute)
                        and node.func.attr in ("writer", "DictWriter")
                        and isinstance(node.func.value, _ast.Name)
                        and node.func.value.id == "csv"
                        and not any(kw.arg == "lineterminator"
                                    for kw in node.keywords)):
                    offenders.append(f"{module_name(module)}:{node.lineno}")
        self.assertEqual([], offenders,
                         "use verso.ru.exporters.base.csv_writer / csv_dict_writer, "
                         "which write LF")
