"""ZGS001–ZGS006: a book of the civil registry (`civil=True`) against what only a church writes,
and DBD001 worded for a registration."""
import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.civil_register as check_civil_register
import verso.ru.linters.checks.deaths_burial_date as check_deaths_burial_date


def _book(kind: str, body: str, *, civil: bool = True, church: str = "", year: int = 1921,
          defaults: str = 'RecordDefaults(residence="Маниловка")') -> str:
    flag = ",\n    civil=True" if civil else ""
    return (f'{kind}("a", "f", "i", "c", "Маниловка", {church!r}, {year},\n'
            f"{body},\n"
            f"    defaults={defaults}{flag})\n")


def _births(*records: str, **kw) -> str:
    return _book("birth_records", "    *birth_month(Month.MARCH,\n        " + ",\n        ".join(records) + ")", **kw)


CHILD = 'child=person("Иван"), father=person("Петр", "Семенов", "Ковыльков")'


class _Check(unittest.TestCase):
    def _run(self, src: str, module=check_civil_register) -> tuple[list[str], list[str]]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            path = Path(f.name)
            advisory = module.check_file_advisory(path) if hasattr(module, "check_file_advisory") else []
            return module.check_file(path), advisory
        finally:
            Path(f.name).unlink()

    def codes(self, src: str) -> tuple[list[str], list[str]]:
        hard, advisory = self._run(src)

        def code(line: str) -> str:
            return line.split("[", 1)[1].split("]", 1)[0]
        return [code(h) for h in hard], [code(a) for a in advisory]


class ChurchInAnAct(_Check):
    def test_a_plain_civil_birth_is_clean(self):
        self.assertEqual(self.codes(_births(f"birth(4, Gender.MALE, 2, 9, {CHILD})")), ([], []))

    def test_a_godparent_is_zgs001(self):
        src = _births(f'birth(4, Gender.MALE, 2, 9, {CHILD}, god_parent1=person("Анна"))')
        self.assertEqual(self.codes(src), (["ZGS001"], []))

    def test_a_positional_godparent_is_zgs001(self):
        src = _births('birth(4, Gender.MALE, 2, 9, None, None, person("Иван"), person("Петр"), None, '
                      'person("Анна"))')
        self.assertEqual(self.codes(src)[0], ["ZGS001"])

    def test_the_clergy_is_zgs001(self):
        src = _births(f'birth(4, Gender.MALE, 2, 9, {CHILD}, priest=person("Петр"))')
        self.assertEqual(self.codes(src)[0], ["ZGS001"])

    def test_a_christening_is_zgs001(self):
        src = _births('christening(4, Gender.MALE, 9, age=3, child=person("Иван"))')
        self.assertEqual(self.codes(src)[0], ["ZGS001"])

    def test_a_wedding_surety_is_zgs001(self):
        src = _book("marriage_records", '    marriage(3, 16, groom=person("Андрей"), bride=person("Анна"), '
                                        'witness1=person("Петр"))')
        self.assertEqual(self.codes(src)[0], ["ZGS001"])

    def test_a_parish_book_may_write_them(self):
        src = _births(f'birth(4, Gender.MALE, 2, 9, {CHILD}, god_parent1=person("Анна"), '
                      'priest=person("Петр"))', civil=False, church="Никольская")
        self.assertEqual(self.codes(src), ([], []))


class RegisteredBeforeBirth(_Check):
    def test_an_earlier_registration_month_is_zgs002(self):
        src = _births(f"birth(4, Gender.MALE, 20, 3, {CHILD}, k_month=Month.FEBRUARY)")
        self.assertEqual(self.codes(src)[0], ["ZGS002"])

    def test_a_smaller_day_in_the_block_is_the_next_month(self):
        # The DSL reads it as April: no finding.
        self.assertEqual(self.codes(_births(f"birth(4, Gender.MALE, 20, 3, {CHILD})"))[0], [])

    def test_a_later_registration_is_clean(self):
        src = _births(f"birth(4, Gender.MALE, 20, 3, {CHILD}, k_month=Month.MAY)")
        self.assertEqual(self.codes(src)[0], [])


class FlagAndYear(_Check):
    def test_a_churchless_book_after_1918_wants_the_flag(self):
        src = _births(f"birth(4, Gender.MALE, 2, 9, {CHILD})", civil=False)
        self.assertEqual(self.codes(src), ([], ["ZGS003"]))

    def test_a_church_book_after_1918_is_left_alone(self):
        src = _births(f"birth(4, Gender.MALE, 2, 9, {CHILD})", civil=False, church="Никольская")
        self.assertEqual(self.codes(src), ([], []))

    def test_a_civil_book_before_1917_is_left_alone(self):
        # An Old Believers' police book of 1880 registers too: the flag is no Soviet one.
        src = _births(f"birth(4, Gender.MALE, 2, 9, {CHILD})", year=1880)
        self.assertEqual(self.codes(src), ([], []))

    def test_a_churchless_book_before_1918_is_left_alone(self):
        src = _births(f"birth(4, Gender.MALE, 2, 9, {CHILD})", civil=False, year=1905)
        self.assertEqual(self.codes(src), ([], []))


class OldOrder(_Check):
    def test_an_owners_estate_is_zgs004(self):
        src = _births('birth(4, Gender.MALE, 2, 9, child=person("Иван"), '
                      'father=person("Петр", status="крестьянин помещика Ноздрева"))')
        self.assertEqual(self.codes(src), ([], ["ZGS004"]))

    def test_a_book_default_estate_is_zgs004(self):
        src = _births(f"birth(4, Gender.MALE, 2, 9, {CHILD})",
                      defaults='RecordDefaults(residence="Маниловка", status_male="казенный крестьянин")')
        self.assertEqual(self.codes(src), ([], ["ZGS004"]))

    def test_plain_peasant_is_left_alone(self):
        src = _births('birth(4, Gender.MALE, 2, 9, child=person("Иван"), '
                      'father=person("Петр", status="крестьянин"))')
        self.assertEqual(self.codes(src), ([], []))

    def test_old_letters_are_zgs005_once_a_person(self):
        src = _births('birth(4, Gender.MALE, 2, 9, child=person("Іоаннъ"), '
                      'father=person("Петръ", "Семеновъ"))')
        self.assertEqual(self.codes(src), ([], ["ZGS005", "ZGS005"]))

    def test_a_parish_book_keeps_its_orthography(self):
        src = _births('birth(4, Gender.MALE, 2, 9, child=person("Іоаннъ"))', civil=False, church="Никольская")
        self.assertEqual(self.codes(src), ([], []))


class DeathRegisteredFirst(unittest.TestCase):
    def _hard(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            return check_deaths_burial_date.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _deaths(self, **kw) -> str:
        return _book("death_records", '    *death_month(Month.APRIL,\n        death(3, Gender.MALE, 11, 2, '
                                      'deceased=person("Семен")))', **kw)

    def test_a_civil_book_says_registration(self):
        [line] = self._hard(self._deaths())
        self.assertIn("[DBD001] registration 2 APRIL precedes death 11 APRIL in a civil registry book", line)

    def test_a_parish_book_still_says_burial(self):
        [line] = self._hard(self._deaths(civil=False, church="Никольская"))
        self.assertIn("[DBD001] burial 2 APRIL precedes death 11 APRIL: swapped days?", line)


class ParentAgesInTheComment(_Check):
    """ZGS006: a civil birth's comment says a parent's age while that role's field is empty."""

    def _zgs006(self, record: str, **kw) -> list[str]:
        _, advisory = self._run(_births(record, **kw))
        return [line.split("] ", 1)[1] for line in advisory if "[ZGS006]" in line]

    def _birth(self, extra: str) -> str:
        return f"birth(4, Gender.MALE, 2, 9, {CHILD}, {extra})"

    def test_both_ages_in_the_comment(self):
        found = self._zgs006(self._birth('comment="записан; отцу 26, матери 22; заявитель — отец"'))
        self.assertEqual(["Возраст отца — в comment; перенесите в father_age=",
                          "Возраст матери — в comment; перенесите в mother_age="], sorted(found, reverse=True))

    def test_fields_written_is_no_finding(self):
        self.assertEqual([], self._zgs006(self._birth('father_age=26, mother_age=22, comment="отцу 26, матери 22"')))

    def test_only_the_empty_role_is_found(self):
        self.assertEqual(["Возраст матери — в comment; перенесите в mother_age="],
                         self._zgs006(self._birth('father_age=26, comment="отцу 26, матери 22"')))

    def test_a_cut_figure_is_no_finding(self):
        self.assertEqual([], self._zgs006(self._birth('comment="матери 3…"')))

    def test_a_doubt_still_gives_its_figure_to_the_field(self):
        self.assertEqual(2, len(self._zgs006(self._birth('comment="отцу 42 (?), матери 43"'))))

    def test_a_church_book_is_no_finding(self):
        self.assertEqual([], self._zgs006(self._birth('comment="отцу 26, матери 22"'), civil=False, church="Церковь"))

    def test_no_comment_no_finding(self):
        self.assertEqual([], self._zgs006(self._birth("reviewed=False")))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
