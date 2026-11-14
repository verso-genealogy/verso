"""RET001–RET003: an age retraction on a record that states no such age."""
import ast
import unittest

from verso.ru.linters.checks.retractions import _collect


def _codes(src: str) -> list[str]:
    return [str(i["message"]).split("]")[0].lstrip("[") for i in _collect(ast.parse(src))]


class RetractionsThatRetractSomething(unittest.TestCase):
    def test_a_line_with_both_ages(self):
        self.assertEqual([], _codes(
            'member(1, person("Фока"), CensusRole.HEAD, age=51, previous_age=33, '
            'source_age_error="x")'))

    def test_previous_age_error_with_a_previous_age(self):
        self.assertEqual([], _codes(
            'member(1, person("Тихон"), CensusRole.SON, age=37, previous_age=15, '
            'previous_age_error="x")'))

    def test_previous_age_error_with_the_comment_marker(self):
        self.assertEqual([], _codes(
            'member(1, person("Иван"), CensusRole.SON, age=5, '
            'comment="прошлая РС: 4.5 лет", previous_age_error="x")'))

    def test_source_age_error_on_a_typed_birth_year(self):
        self.assertEqual([], _codes(
            'member(1, person("Иван"), CensusRole.SON, birth_year=1802, '
            'source_age_error="x")'))

    def test_a_burial_with_an_age(self):
        self.assertEqual([], _codes(
            'death(3, Gender.MALE, 26, None, deceased=person("Иван"), age=3, '
            'source_age_error="x")'))
        self.assertEqual([], _codes(
            'death(3, Gender.FEMALE, 26, None, deceased=person("Анна"), age="1 мес", '
            'namesake="x")'))


class RetractionsThatRetractNothing(unittest.TestCase):
    def test_ret001_previous_age_error_without_a_previous_figure(self):
        self.assertEqual(["RET001"], _codes(
            'member(1, person("Иван"), CensusRole.SON, age=5, previous_age_error="x")'))

    def test_ret002_source_age_error_on_a_line_without_age(self):
        self.assertEqual(["RET002"], _codes(
            'member(1, person("Иван"), CensusRole.SON, source_age_error="x")'))

    def test_ret002_a_not_recorded_age_is_no_age(self):
        self.assertEqual(["RET002"], _codes(
            'member(1, person("Иван"), CensusRole.SON, age="?", source_age_error="x")'))

    def test_ret002_on_a_burial_without_age(self):
        self.assertEqual(["RET002", "RET002"], _codes(
            'death(3, Gender.MALE, 26, None, deceased=person("Иван"), '
            'source_age_error="x", namesake="y")'))

    def test_ret003_both_retractions_on_one_line(self):
        self.assertEqual(["RET003"], _codes(
            'member(1, person("Фока"), CensusRole.HEAD, age=51, previous_age=33, '
            'source_age_error="x", previous_age_error="y")'))


if __name__ == "__main__":
    unittest.main()
