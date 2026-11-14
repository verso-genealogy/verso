import unittest
from abc import ABC

from verso.ru.exporters.base import RecordsExporter


class TestRecordsExporter(unittest.TestCase):

    def test_is_abstract(self):
        self.assertTrue(issubclass(RecordsExporter, ABC))  # type: ignore[reportUnnecessaryIsInstance]

    def test_cannot_instantiate(self):
        with self.assertRaises(TypeError):
            RecordsExporter()  # type: ignore[abstract]

    def test_subclass_must_implement_export(self):
        class IncompleteExporter(RecordsExporter):
            pass

        with self.assertRaises(TypeError):
            IncompleteExporter()  # type: ignore[abstract]

    def test_subclass_with_export_can_instantiate(self):
        class CompleteExporter(RecordsExporter):
            def export(self, records_container, target_dir=None):
                return "exported"

        exporter = CompleteExporter()
        self.assertEqual(exporter.export(None), "exported")


if __name__ == '__main__':
    unittest.main()
