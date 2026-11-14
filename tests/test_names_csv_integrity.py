"""Integrity of names.csv itself, as opposed to the DSL that reads it.

The table's ROW ORDER is load-bearing — the table compiles into its layer
(`verso.ru.naming.legacy`) index by index «first row wins», so the first row
carrying a key wins and later rows are deliberate variants. That rules out a
sort check, and it rules out ever sorting the file. What is left are the
relations the table asserts about itself, and those are checkable.
"""

import unittest


from verso.ru.linters.names_csv import ADVISORY_CODES, check_rows, hard_findings

COLUMNS = ['Пол', 'Имя', 'Имя-основа', 'От', 'Склонения, связи',
           'Родительный падеж', 'Отчество старое М', 'Отчество старое Ж',
           'Отчество М', 'Отчество Ж', 'Источник']


def row(gender='Ж', name='Ефросиния', base='', **kw):
    r = {c: '' for c in COLUMNS}
    r['Пол'], r['Имя'], r['Имя-основа'] = gender, name, base
    r.update(kw)
    return r


def codes(rows):
    return [f.code for f in check_rows(rows)]


class TestDanglingBase(unittest.TestCase):
    def test_base_absent_from_table_is_reported(self):
        self.assertEqual(codes([row(name='Тазейка', base='Тазей')]), ['NCSV001'])

    def test_base_present_in_table_is_accepted(self):
        rows = [row(name='Ефросиния'), row(name='Ефрасиния', base='Ефросиния')]
        self.assertEqual(codes(rows), [])

    def test_finding_names_the_row_and_its_line(self):
        found = check_rows([row(name='Ефросиния'), row(name='Тазейка', base='Тазей')])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, 'Тазейка')
        # header is line 1, so the second data row is line 3
        self.assertEqual(found[0].line, 3)


class TestSelfReferencingBase(unittest.TestCase):
    def test_base_equal_to_name_is_reported(self):
        self.assertEqual(codes([row(name='Ульяна', base='Ульяна')]), ['NCSV002'])

    def test_empty_base_means_canonical_and_is_accepted(self):
        self.assertEqual(codes([row(name='Ульяна')]), [])


class TestBaseChain(unittest.TestCase):
    def test_base_that_is_itself_a_variant_is_reported(self):
        rows = [
            row(name='Салманида', base='Соломонида'),
            row(name='Соломонида'),
            row(name='Саламанида', base='Салманида'),
        ]
        self.assertEqual(codes(rows), ['NCSV003'])

    def test_base_pointing_at_a_canonical_row_is_accepted(self):
        rows = [row(name='Соломонида'), row(name='Саламанида', base='Соломонида')]
        self.assertEqual(codes(rows), [])

    def test_a_name_that_is_canonical_somewhere_is_accepted(self):
        """The same Имя may hold several rows; one canonical row is enough."""
        rows = [
            row(name='Ефросиния', base='Евфросиния'),
            row(name='Ефросиния'),
            row(name='Ефрасиния', base='Ефросиния'),
            row(name='Евфросиния'),
        ]
        self.assertEqual(codes(rows), [])


class TestDuplicateRow(unittest.TestCase):
    def test_byte_identical_row_is_reported_once(self):
        r = row(name='Агап', **{'Отчество старое М': 'Агапов'})
        self.assertEqual(codes([r, dict(r)]), ['NCSV004'])

    def test_rows_differing_in_any_column_are_kept(self):
        a = row(name='Агап', **{'Отчество М': 'Агапович'})
        b = row(name='Агап', **{'Отчество М': 'Агапиевич'})
        self.assertEqual(codes([a, b]), [])


class TestStructuralColumns(unittest.TestCase):
    def test_gender_outside_M_and_F_is_reported(self):
        self.assertEqual(codes([row(gender='X', name='Ефим')]), ['NCSV005'])

    def test_empty_name_is_reported(self):
        self.assertEqual(codes([row(name='')]), ['NCSV006'])

    def test_empty_name_is_not_also_reported_as_a_bad_base(self):
        """A blank Имя must not cascade into the base rules."""
        self.assertEqual(codes([row(name='', base='Ефросиния')]), ['NCSV006'])


class TestWhitespaceTolerance(unittest.TestCase):
    def test_base_matching_after_stripping_is_accepted(self):
        rows = [row(name='Ефросиния'), row(name='Ефрасиния', base=' Ефросиния ')]
        self.assertEqual(codes(rows), [])


class TestSeverity(unittest.TestCase):
    """A base chain is a real defect, but repairing it renames Geni resources —
    canonicalize_name feeds res_names — so it reports and never gates."""

    def test_base_chain_is_advisory(self):
        self.assertIn('NCSV003', ADVISORY_CODES)

    def test_hard_findings_exclude_the_advisory_ones(self):
        rows = [
            row(name='Юлиания'),
            row(name='Иулиания', base='Юлиания'),
            row(name='Иолания', base='Иулиания'),   # NCSV003, advisory
            row(name='Тазейка', base='Тазей'),      # NCSV001, hard
        ]
        self.assertEqual([f.code for f in check_rows(rows)], ['NCSV003', 'NCSV001'])
        self.assertEqual([f.code for f in hard_findings(rows)], ['NCSV001'])


if __name__ == '__main__':
    unittest.main()
