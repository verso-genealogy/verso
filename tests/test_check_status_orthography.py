import ast
import unittest

import verso.ru.linters.checks.status_orthography as check


def _codes(src: str) -> list[str]:
    return [str(i["message"]) for i in check._collect(ast.parse(src), src.splitlines())]


class TestSor001(unittest.TestCase):
    def test_a_literal_status_in_old_spelling_is_flagged(self):
        msgs = _codes('birth(1, father=person("Иванъ", status="крестьянинъ собственникъ"))\n')
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("[SOR001]", msgs[0])
        self.assertIn('"крестьянин собственник"', msgs[0])

    def test_departure_reason_is_flagged(self):
        msgs = _codes('member(4, person("Нестеръ"), CensusRole.NEPHEW, departure_reason="умеръ")\n')
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn('"умер"', msgs[0])

    def test_a_file_constant_is_read_and_pinned_at_its_definition(self):
        src = ('TENTETNIKOV_M = "крестьянин вотчины Г. Тентетникова"\n'
               'DEFAULTS = RecordDefaults(status_male=TENTETNIKOV_M)\n')
        issues = check._collect(ast.parse(src), src.splitlines())
        self.assertEqual([i["line"] for i in issues], [1])
        self.assertIn('"крестьянин вотчины г. Тентетникова"', str(issues[0]["message"]))

    def test_a_catalog_wording_is_named(self):
        msgs = _codes('birth(1, father=person("Тихонъ", status="священникъ"))\n')
        self.assertIn("PRIEST", msgs[0])
        msgs = _codes('birth(1, god_parent1=person("Петръ", status="дьячекъ"))\n')
        self.assertIn("DYACHOK", msgs[0])

    def test_names_and_comments_keep_the_scribes_spelling(self):
        self.assertEqual(_codes(
            'member(1, person("Ѳедоръ", "Харитоновъ"), CensusRole.HEAD, '
            'comment="Василья Харитонова дочь")\n'), [])

    def test_a_modern_status_is_silent(self):
        self.assertEqual(_codes('birth(1, father=person("Иванъ", status="унтер-офицер"))\n'), [])

    def test_a_capitalised_honorific_is_flagged(self):
        msgs = _codes('birth(1, father=person("Иванъ", status="крестьянин вотчины Г-на Ноздрева"))\n')
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("NOZDREV_PEASANT", msgs[0])
        msgs = _codes('birth(1, father=person("Иванъ", status="крестьянин вотчины Гг. Головлевых"))\n')
        self.assertIn("GOLOVLEV_PEASANT", msgs[0])

    def test_an_initial_is_not_an_honorific(self):
        self.assertEqual(_codes(
            'birth(1, father=person("Иванъ", status="крестьянин вотчины дворянина А. Г. Ноздрева"))\n'), [])

    def test_a_lowercase_honorific_is_silent(self):
        self.assertEqual(_codes(
            'birth(1, father=person("Иванъ", status="крестьянин вотчины гг. Головлевых"))\n'), [])

    def test_a_hard_sign_inside_a_word_is_not_a_finding(self):
        """«объездчика» keeps its ъ in modern spelling too."""
        self.assertEqual(_codes('birth(1, mother=person("Марья", status="жена объездчика"))\n'), [])


class TestModernSpelling(unittest.TestCase):
    def test_letters_and_word_final_hard_sign(self):
        cases = {
            "унтеръ-офицеръ": "унтер-офицер",
            "уволенный въ запасъ арміи рядовой": "уволенный в запас армии рядовой",
            "крестьянина собственника дѣвица": "крестьянина собственника девица",
            "отданъ въ рекруты": "отдан в рекруты",
            "діаконъ": "диакон",
            "крестьянин вотчины Г-на Ноздрева": "крестьянин вотчины г-на Ноздрева",
            "земской вотчины малолетных детей Г.Г. Головлевых": "земской вотчины малолетных детей гг. Головлевых",
            "крестьянка отчины Гг. Головлевых": "крестьянка отчины гг. Головлевых",
            "девица вотчины Г. Тентетникова": "девица вотчины г. Тентетникова",
            "дворянина А. Г. Ноздрева": "дворянина А. Г. Ноздрева",
        }
        for old, new in cases.items():
            self.assertEqual(check.modern_spelling(old), new, old)

    def test_adjective_ending_and_voiceless_prefix(self):
        self.assertEqual(check.modern_spelling("унтеръ-офицеръ Финляндскаго полка"),
                         "унтер-офицер Финляндского полка")
        self.assertEqual(check.modern_spelling("безсрочноотпускной солдатъ"),
                         "бессрочноотпускной солдат")

    def test_the_catalog_is_modern(self):
        """`verso.ru.domain.statuses` must not need the rule it serves."""
        old = {name: text for text, name in check.catalog().items() if check.PRE_REFORM.search(text)}
        self.assertEqual(old, {})


if __name__ == "__main__":
    unittest.main()
