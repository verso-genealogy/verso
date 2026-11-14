"""`verso.ru.cli.names add` — placing a new row in names.csv by hand is the step that
keeps going wrong, so the rules it has to respect are pinned here.

Two of them fight each other, and the order matters: the file is *roughly*
alphabetical, but ROW ORDER IS LOAD-BEARING (the table compiles into its layer index by index
«first row wins», `verso.ru.naming.legacy`). So the
alphabetical position is a preference and not shadowing an existing row is a
hard constraint — placement may move forward, never backward.
"""

import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.cli.names import main
from verso.ru.naming.names_table import COLUMNS, build_row, insertion_index, place

LEGACY = Path(__file__).resolve().parent / "fixtures" / "legacy-names"


@pytest.fixture(autouse=True)
def _in_a_workspace_of_the_old_tables() -> Iterator[None]:
    """`--path` is the old tables': in a workspace of schema 6 `add` writes a layer and refuses it."""
    with workspace.use(LEGACY):
        yield


def r(name, **kw):
    row = {c: '' for c in COLUMNS}
    row['Пол'], row['Имя'] = kw.pop('gender', 'Ж'), name
    row.update(kw)
    return row


class TestAlphabeticalPlacement(unittest.TestCase):
    def test_lands_between_its_neighbours(self):
        self.assertEqual(insertion_index(['Абрам', 'Ефим', 'Яков'], 'Макар'), 2)

    def test_first_name_goes_to_the_top(self):
        self.assertEqual(insertion_index(['Ефим', 'Яков'], 'Абрам'), 0)

    def test_last_name_goes_to_the_bottom(self):
        self.assertEqual(insertion_index(['Абрам', 'Ефим'], 'Яков'), 2)

    def test_the_real_case_lands_where_a_human_put_it(self):
        """Евфрасиния belongs after Евфрасий and before Евфрасия."""
        names = ['Евфрасий', 'Евфрасий', 'Евфрасия', 'Евфросин']
        self.assertEqual(insertion_index(names, 'Евфрасиния'), 2)

    def test_a_misplaced_row_does_not_drag_the_result(self):
        """The file holds 572 out-of-order rows, so «everything before is
        smaller» is false. Placement follows the NEAREST smaller name, so the
        stray Яков at index 1 is ignored and Захар lands after Ефим."""
        names = ['Абрам', 'Яков', 'Ефим', 'Иван', 'Макар']
        self.assertEqual(insertion_index(names, 'Захар'), 3)

    def test_equal_names_are_appended_after_not_before(self):
        """A new row must never shadow an existing row of the same name."""
        self.assertEqual(insertion_index(['Абрам', 'Ефим', 'Ефим', 'Яков'], 'Ефим'), 3)


class TestShadowSafety(unittest.TestCase):
    def test_placement_moves_past_a_row_sharing_an_old_patronymic(self):
        rows = [
            r('Абрам'),
            r('Яков', **{'Отчество старое М': 'Ефимов'}),
            r('Яков'),
        ]
        new = r('Ефим', **{'Отчество старое М': 'Ефимов'})
        # alphabetically it belongs at 1; the shared key pushes it past row 1
        self.assertEqual(insertion_index([x['Имя'] for x in rows], 'Ефим'), 1)
        self.assertEqual(place(rows, new), 2)

    def test_placement_is_untouched_when_no_key_is_shared(self):
        rows = [r('Абрам'), r('Яков')]
        self.assertEqual(place(rows, r('Ефим')), 1)

    def test_an_empty_column_is_not_a_shared_key(self):
        rows = [r('Абрам'), r('Яков')]
        self.assertEqual(place(rows, r('Ефим')), 1)

    def test_a_shared_genitive_also_pushes_forward(self):
        rows = [r('Абрам'), r('Яков', **{'Родительный падеж': 'Ефима'})]
        self.assertEqual(place(rows, r('Ефим', **{'Родительный падеж': 'Ефима'})), 2)


class TestBuildRow(unittest.TestCase):
    def test_every_column_is_present_and_ordered(self):
        built = build_row(gender='Ж', name='Евфрасиния', base='Ефросиния',
                          genitive='Евфрасинии', source='МК 1917')
        self.assertEqual(list(built.keys()), COLUMNS)
        self.assertEqual(built['Пол'], 'Ж')
        self.assertEqual(built['Имя'], 'Евфрасиния')
        self.assertEqual(built['Имя-основа'], 'Ефросиния')
        self.assertEqual(built['Родительный падеж'], 'Евфрасинии')
        self.assertEqual(built['Источник'], 'МК 1917')

    def test_unset_columns_are_empty_not_missing(self):
        built = build_row(gender='М', name='Тазей')
        self.assertEqual(built['Отчество М'], '')
        self.assertEqual(built['Имя-основа'], '')


class TestValidation(unittest.TestCase):
    def test_base_absent_from_the_table_is_refused(self):
        rows = [r('Ефросиния')]
        new = build_row(gender='Ж', name='Тазейка', base='Тазей')
        with self.assertRaises(ValueError) as e:
            place(rows, new)
        self.assertIn('Тазей', str(e.exception))

    def test_base_that_is_itself_a_variant_is_refused(self):
        rows = [r('Юлиания'), r('Иулиания', **{'Имя-основа': 'Юлиания'})]
        new = build_row(gender='Ж', name='Иолания', base='Иулиания')
        with self.assertRaises(ValueError) as e:
            place(rows, new)
        self.assertIn('Юлиания', str(e.exception))

    def test_an_identical_row_is_refused(self):
        existing = build_row(gender='Ж', name='Ефросиния')
        with self.assertRaises(ValueError):
            place([existing], dict(existing))

    def test_a_row_the_check_would_pass_is_accepted(self):
        """«Ефрасиния» sorts BEFORE «Ефросиния» (а < о), so it lands above its
        own base — which is fine: the base relation is not an ordering."""
        rows = [r('Ефросиния')]
        new = build_row(gender='Ж', name='Ефрасиния', base='Ефросиния')
        self.assertEqual(place(rows, new), 0)


class TestResultPassesTheIntegrityCheck(unittest.TestCase):
    def test_inserting_leaves_no_hard_finding(self):
        from verso.ru.linters.names_csv import hard_findings
        rows = [r('Ефросиния')]
        new = build_row(gender='Ж', name='Ефрасиния', base='Ефросиния')
        rows.insert(place(rows, new), new)
        self.assertEqual(hard_findings(rows), [])


HEADER = ','.join(COLUMNS)

# The second row is quoted where quoting is not required — names.csv holds six
# such rows, and csv.DictWriter silently strips them when it rewrites the file.
HAND_WRITTEN = [
    HEADER,
    'М,Абрам,,Разг.,,Абрама,Абрамов,Абрамова,Абрамович,Абрамовна,"(вариант отчества)"',
    'Ж,Яков,,,"-а, м.",Якова,,,,,Словарь',
]


class TestWritingTouchesNothingElse(unittest.TestCase):
    """Adding a row must splice one line in, not reformat the file. Rewriting it
    through csv.DictWriter drops hand-written quoting on unrelated rows."""

    def _run(self, path, *argv):
        return main(['add', '--path', str(path), *argv])

    def test_existing_lines_survive_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'names.csv'
            path.write_text('\n'.join(HAND_WRITTEN) + '\n', encoding='utf-8')

            self.assertEqual(self._run(path, '--gender', 'М', '--name', 'Ефим'), 0)

            after = path.read_text(encoding='utf-8').rstrip('\n').split('\n')
            self.assertEqual([line for line in after if 'Ефим' not in line],
                             HAND_WRITTEN)

    def test_the_new_row_lands_between_its_neighbours(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'names.csv'
            path.write_text('\n'.join(HAND_WRITTEN) + '\n', encoding='utf-8')

            self._run(path, '--gender', 'М', '--name', 'Ефим', '--source', 'МК')

            after = path.read_text(encoding='utf-8').rstrip('\n').split('\n')
            self.assertEqual(after[2], 'М,Ефим,,,,,,,,,МК')

    def test_a_refused_row_leaves_the_file_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'names.csv'
            original = '\n'.join(HAND_WRITTEN) + '\n'
            path.write_text(original, encoding='utf-8')

            code = self._run(path, '--gender', 'Ж', '--name', 'Тазейка',
                             '--base', 'Тазей')

            self.assertEqual(code, 1)
            self.assertEqual(path.read_text(encoding='utf-8'), original)


if __name__ == '__main__':
    unittest.main()
