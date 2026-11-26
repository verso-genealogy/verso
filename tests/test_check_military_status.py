import ast
import unittest
from typing import Any

import verso.ru.linters.checks.military_status as check


def _issues(src: str) -> list[dict[str, Any]]:
    return check._collect(ast.parse(src), src.splitlines())


def _msgs(src: str) -> list[str]:
    return [str(i["message"]) for i in _issues(src)]


class TestMil001(unittest.TestCase):
    def test_a_literal_soldier_wording_is_refused(self):
        msgs = _msgs('birth(1, father=person("Иванъ", status="запасный солдат"))\n')
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("[MIL001]", msgs[0])
        self.assertIn("SOLDIER", msgs[0])
        self.assertIn('comment="запасный солдат"', msgs[0])

    def test_the_role_picks_the_constant(self):
        wife = _msgs('person("Анна", status="жена запасного рядового")\n')
        self.assertIn("→ SOLDIER_SPOUSE,", wife[0])
        retired = _msgs('person("Иван", status="отставной рядовой")\n')
        self.assertIn("→ RETIRED_SOLDIER,", retired[0])

    def test_old_spelling_goes_modern_in_the_comment(self):
        msgs = _msgs('person("Иванъ", status="отставной рядовой")\n')
        self.assertIn('comment="отставной рядовой"', msgs[0])
        msgs = _msgs('person("Иванъ", status="запасный рядовой")\n')
        self.assertIn('comment="запасный рядовой"', msgs[0])

    def test_catalog_and_officer_texts_are_quiet(self):
        for status in ('SOLDIER', '"солдат"', '"крестьянин поручика Ноздрева"', '"унтер-офицерская девица"'):
            self.assertEqual(_msgs(f'person("Иван", status={status})\n'), [], status)

    def test_a_file_constant_is_pinned_at_its_definition(self):
        src = 'X = "уволенный в запас армии"\nperson("Иван", status=X)\n'
        issues = _issues(src)
        self.assertEqual([i["line"] for i in issues], [1])
        self.assertIn('status=X (= "уволенный в запас армии")', str(issues[0]["message"]))

    def test_record_defaults_forms_are_read(self):
        self.assertEqual(len(_issues('RecordDefaults(status_male="запасный солдат")\n')), 1)

    def test_departure_reason_is_not_a_status(self):
        self.assertEqual(_issues('member(1, person("Иван"), departure_reason="в солдаты")\n'), [])


if __name__ == "__main__":
    unittest.main()
