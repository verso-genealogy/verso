import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.witness_side as check_witness_side


def _marriages(body: str) -> str:
    return (
        'marriage_records("a", "f", "i", "c", "Маниловка", "Церковь", 1864,\n'
        f"{body},\n"
        '    defaults=RecordDefaults(residence="Маниловка"))\n'
    )


def _wedding(*witnesses: str, comment: str | None = None) -> str:
    slots = "".join(f",\n             witness{n}={w}" for n, w in enumerate(witnesses, start=1))
    tail = f",\n             comment={comment!r}" if comment else ""
    return _marriages('    marriage(4, 12, groom=person("Иванъ"), bride=person("Анна")'
                      f"{slots}{tail})")


GROOM = 'person("Даніилъ", side=Side.GROOM)'
BRIDE = 'person("Василій", side=Side.BRIDE)'
BARE = 'person("Петръ")'


class _Check(unittest.TestCase):
    def _run(self, src: str) -> tuple[list[str], list[str]]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            path = Path(f.name)
            return (check_witness_side.check_file(path),
                    check_witness_side.check_file_advisory(path))
        finally:
            Path(f.name).unlink()

    def codes(self, src: str) -> tuple[list[str], list[str]]:
        hard, advisory = self._run(src)
        def code(line: str) -> str:
            return line.split("[", 1)[1].split("]", 1)[0]
        return [code(h) for h in hard], [code(a) for a in advisory]


class Hard(_Check):
    def test_sides_on_the_witnesses_are_clean(self):
        self.assertEqual(self.codes(_wedding(GROOM, GROOM, BRIDE, BRIDE)), ([], []))

    def test_a_side_on_the_groom_is_wsd001(self):
        src = _marriages('    marriage(4, 12, groom=person("Иванъ", side=Side.GROOM), '
                         'bride=person("Анна"))')
        self.assertEqual(self.codes(src), (["WSD001"], []))

    def test_a_side_in_a_birth_is_wsd001(self):
        src = ('birth_records("a", "f", "i", "c", "Маниловка", "Церковь", 1864,\n'
               '    birth(1, Gender.MALE, 1, 2, child=person("Иванъ"),\n'
               '          god_parent1=person("Петръ", side=Side.BRIDE)))\n')
        self.assertEqual(self.codes(src)[0], ["WSD001"])

    def test_a_side_on_a_witness_relative_is_wsd001(self):
        src = _marriages('    marriage(4, 12, groom=person("Иванъ"), bride=person("Анна"),\n'
                         f'             witness1={GROOM},\n'
                         '             relatives=[relative(person("Ѳедоръ", side=Side.GROOM), '
                         'Relationship.FATHER, "поручитель №1")])')
        self.assertEqual(self.codes(src)[0], ["WSD001"])

    def test_a_side_against_its_own_words_is_wsd002(self):
        w = 'person("Даніилъ", side=Side.GROOM, comment="поручитель по невѣстѣ")'
        self.assertEqual(self.codes(_wedding(w))[0], ["WSD002"])

    def test_a_positional_witness_counts_as_a_witness(self):
        src = _marriages('    marriage(4, 12, Month.MAY, person("Иванъ"), person("Анна"), '
                         f'1, 1, 20, 18, {GROOM})')
        self.assertEqual(self.codes(src), ([], []))


class Advisory(_Check):
    def test_words_without_a_side_are_wsd003(self):
        w = 'person("Даніилъ", comment="поручитель по жениху; деревня не названа")'
        self.assertEqual(self.codes(_wedding(w)), ([], ["WSD003"]))

    def test_words_repeating_the_side_are_wsd003(self):
        w = 'person("Даніилъ", side=Side.GROOM, comment="поручитель по жениху")'
        hard, advisory = self._run(_wedding(w))
        self.assertEqual(hard, [])
        self.assertIn("repeats", advisory[0])

    def test_the_old_orthography_is_read(self):
        for words in ("по женихѣ", "по женихе", "по невѣстѣ", "со стороны жениха"):
            w = f'person("Даніилъ", comment="{words}")'
            self.assertEqual(self.codes(_wedding(w))[1], ["WSD003"], words)

    def test_a_record_comment_naming_sides_wants_them_declared(self):
        src = _wedding(BARE, BARE, BARE, BARE,
                       comment="поручители 1 и 2 — по женихе, 3 и 4 — по невесте")
        self.assertEqual(self.codes(src)[1], ["WSD003"])

    def test_the_record_comment_is_quiet_once_every_side_is_declared(self):
        src = _wedding(GROOM, GROOM, BRIDE, BRIDE,
                       comment="поручители 1 и 2 — по женихе, 3 и 4 — по невесте")
        self.assertEqual(self.codes(src), ([], []))

    def test_a_half_declared_record_is_wsd004(self):
        self.assertEqual(self.codes(_wedding(GROOM, BARE))[1], ["WSD004"])

    def test_a_record_without_sides_is_quiet(self):
        self.assertEqual(self.codes(_wedding(BARE, BARE, BARE)), ([], []))

    def test_a_grooms_surety_after_a_brides_is_wsd005(self):
        self.assertEqual(self.codes(_wedding(BRIDE, GROOM))[1], ["WSD005"])

    def test_four_on_one_side_is_wsd006(self):
        self.assertEqual(self.codes(_wedding(GROOM, GROOM, GROOM, GROOM))[1], ["WSD006"])


if __name__ == "__main__":
    unittest.main()
