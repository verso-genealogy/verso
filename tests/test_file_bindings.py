import ast
import unittest

from verso.ru.linters.checks.file_bindings import (
    module_bindings, record_defaults_call, string_constants)


def _records_call(src: str) -> ast.Call:
    return next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "birth_records")


class TestFileBindings(unittest.TestCase):
    def test_defaults_written_in_the_call(self):
        src = 'birth_records("a", defaults=RecordDefaults(residence="X"))\n'
        found = record_defaults_call(_records_call(src), module_bindings(ast.parse(src)))
        self.assertIsNotNone(found)

    def test_defaults_bound_by_name(self):
        src = ('DEFAULTS = RecordDefaults(residence="X")\n'
               'birth_records("a", defaults=DEFAULTS)\n')
        found = record_defaults_call(_records_call(src), module_bindings(ast.parse(src)))
        assert found is not None
        self.assertEqual(ast.unparse(found), "RecordDefaults(residence='X')")

    def test_a_name_bound_to_something_else_is_no_defaults(self):
        src = ('DEFAULTS = make_defaults()\n'
               'birth_records("a", defaults=DEFAULTS)\n')
        self.assertIsNone(
            record_defaults_call(_records_call(src), module_bindings(ast.parse(src))))

    def test_a_name_bound_twice_is_left_out(self):
        """Which value a call sees depends on where it stands — no guessing."""
        tree = ast.parse('A = "one"\nB = "b"\nA = "two"\n')
        self.assertEqual(string_constants(module_bindings(tree)), {"B": "b"})

    def test_only_top_level_bindings_count(self):
        tree = ast.parse('def f():\n    A = "inner"\nB: str = "outer"\n')
        self.assertEqual(string_constants(module_bindings(tree)), {"B": "outer"})


if __name__ == "__main__":
    unittest.main()
