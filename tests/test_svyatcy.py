"""The святцы: reading the 1906 alphabet, and asking the table."""
import unittest

from verso.ru.church_calendar.church_slavonic import (
    fold, modern_name, parse_alphabet, parse_month, parse_numeral)
from verso.ru.church_calendar.julian import is_valid
from verso.ru.church_calendar.svyatcy import (
    Commemorated, Svyatcy, load_svyatcy, name_key, read_rows)
from verso.ru.cli.svyatcy import build_table, rank
from verso.ru.gender import Gender

M, F = Gender.MALE, Gender.FEMALE


class Numerals(unittest.TestCase):
    def test_values(self):
        self.assertEqual(parse_numeral("а҃."), 1)
        self.assertEqual(parse_numeral("є҃і."), 15)  # units before the ten
        self.assertEqual(parse_numeral("к҃д."), 24)
        self.assertEqual(parse_numeral("л҃."), 30)

    def test_without_a_titlo_a_letter_is_a_word(self):
        self.assertIsNone(parse_numeral("а"))
        self.assertEqual(parse_numeral("є.", titlo_required=False), 5)

    def test_a_word_is_not_a_numeral(self):
        self.assertIsNone(parse_numeral("ма́рта"))


class Months(unittest.TestCase):
    def test_genitive_months(self):
        self.assertEqual(parse_month("і҆аннꙋа́рїа"), 1)
        self.assertEqual(parse_month("а҆прі́ллїа"), 4)
        self.assertEqual(parse_month("а҆́ѵгꙋста"), 8)
        self.assertEqual(parse_month("деке́мврїа."), 12)

    def test_a_capitalised_token_is_a_name_not_a_month(self):
        """The women Аѵгꙋста, Іꙋлїа and Іꙋнїа spell what the months do."""
        self.assertIsNone(parse_month("А҆́ѵгꙋста,"))
        self.assertIsNone(parse_month("І҆ꙋ́лїа,"))


class ModernLetters(unittest.TestCase):
    def test_names(self):
        self.assertEqual(modern_name("А҆га́пїа"), "Агапия")
        self.assertEqual(modern_name("І҆ѡа́ннъ"), "Иоанн")
        self.assertEqual(modern_name("Параске́ѵа"), "Параскева")  # ѵ after е is в
        self.assertEqual(modern_name("Є҆ѵдокі́а"), "Евдокия")
        self.assertEqual(modern_name("А҆грѷпі́на"), "Агрипина")  # ѵ after р is и
        self.assertEqual(modern_name("Вирїне́а"), "Виринея")

    def test_an_initial_izhitsa_reads_i(self):
        """`'' in 'ае'` is True: an initial ѵ once read «в» (Впатий, Вакинф)."""
        self.assertEqual(fold("Ѵ҆па́тїй"), "ипатий")
        self.assertEqual(modern_name("Ѵ҆акі́нѳъ"), "Иакинф")

    def test_a_breve_letter_survives(self):
        self.assertEqual(modern_name("А҆вді́й"), "Авдий")


_SAMPLE = """\
[глⷡ҇а л҃и] А҆лфави́тъ и҆ме́нъ

И҆мена̀ мꙋ́жєскїѧ.

А҆

А҆вді́й, септе́мврїа є҃. ное́мврїа ѳ҃і.

Кѷрїѡ́нъ, ма́рта ѳ҃. Кѵ́ръ, і҆аннꙋа́рїа л҃а. і҆ꙋ́нїа к҃и.

Ма́рко и҆лѝ Ма́ркъ, і҆аннꙋа́рїа д҃. ма́рта є. к҃ѳ.

Оу҆аленті́нъ [и҆лѝ Валенті́нъ], і҆ꙋ́лїа ѕ҃.

И҆мена̀ жє́нскїѧ.

А҆́ѵгꙋста, ное́мврїа к҃д.

А҆га́пїа, а҆прі́ллїа ѕ҃і.
"""


class Alphabet(unittest.TestCase):
    def setUp(self):
        self.entries, self.unread = parse_alphabet(_SAMPLE)
        self.by_name = {modern_name(e.headword): e for e in self.entries}

    def test_every_token_is_read(self):
        self.assertEqual([], self.unread)

    def test_the_title_and_letter_headings_are_not_entries(self):
        self.assertEqual(["Авдий", "Кирион", "Кир", "Марко", "Уалентин", "Августа", "Агапия"],
                         [modern_name(e.headword) for e in self.entries])

    def test_genders_follow_the_headings(self):
        self.assertEqual("M", self.by_name["Авдий"].gender)
        self.assertEqual("F", self.by_name["Агапия"].gender)

    def test_two_saints_in_one_paragraph(self):
        self.assertEqual(((3, 9),), self.by_name["Кирион"].dates)
        self.assertEqual(((1, 31), (6, 28)), self.by_name["Кир"].dates)

    def test_other_forms_of_a_name(self):
        self.assertEqual(("Ма́ркъ",), self.by_name["Марко"].alternates)
        self.assertEqual(("Валенті́нъ",), self.by_name["Уалентин"].alternates)

    def test_a_numeral_that_lost_its_titlo_inside_the_dates(self):
        self.assertEqual(((1, 4), (3, 5), (3, 29)), self.by_name["Марко"].dates)

    def test_a_woman_named_for_a_month(self):
        self.assertEqual(((11, 24),), self.by_name["Августа"].dates)

    def test_the_table_carries_a_row_per_form(self):
        table, problems = build_table(_SAMPLE, "abc123")
        self.assertEqual([], problems)
        rows = [ln.split("\t") for ln in table.splitlines() if not ln.startswith("#")]
        self.assertEqual(["gender", "headword", "name", "dates", "variant_of"], rows[0])
        self.assertIn(["M", "Валенті́нъ", "Валентин", "07-06", "Оу҆аленті́нъ"], rows)


class TheCommittedTable(unittest.TestCase):
    """What the 1906 book says, pinned — a reimport that changes these is a
    parser change, not a new edition."""

    @classmethod
    def setUpClass(cls):
        cls.rows = read_rows()
        cls.svyatcy = load_svyatcy()

    def test_size(self):
        main = [r for r in self.rows if r.variant_of is None]
        self.assertGreaterEqual(len(main), 1000)
        self.assertEqual(821, sum(r.gender == M for r in main))
        self.assertEqual(206, sum(r.gender == F for r in main))

    def test_every_day_exists(self):
        for r in self.rows:
            for m, d in r.dates:
                self.assertTrue(is_valid(1800, m, d), (r.headword, m, d))

    def test_known_names(self):
        self.assertEqual(((4, 16),), self.svyatcy.commemorations("Агапия", F))
        self.assertEqual(((7, 26), (10, 14), (10, 28)),
                         self.svyatcy.commemorations("Параскева", F))
        self.assertIn((11, 24), self.svyatcy.commemorations("Августа", F))

    def test_our_forms_find_the_books(self):
        self.assertEqual(self.svyatcy.commemorations("Прасковья", F),
                         self.svyatcy.commemorations("Параскева", F))
        self.assertIn((5, 8), self.svyatcy.commemorations("Иван", M))
        for name, gender in (("Емельян", M), ("Ульяна", F), ("Дарья", F),
                             ("Аграфена", F), ("Созон", M), ("Марта", F)):
            self.assertTrue(self.svyatcy.knows(name, gender), name)

    def test_a_peoples_form_keeps_its_own_days_and_gains_the_saints(self):
        """The book has a Родион of its own; the corpus's April Родионы were
        named for Иродион, 8 April."""
        days = self.svyatcy.commemorations("Родион", M)
        self.assertIn((4, 8), days)
        self.assertIn((11, 10), days)


class NameKeys(unittest.TestCase):
    def test_a_names_csv_cycle_ends(self):
        """Семен and Семён point at each other in names.csv."""
        self.assertEqual(name_key("Семен", M), name_key("Семён", M))
        self.assertEqual(name_key("Семен", M), name_key("Симеон", M))

    def test_a_names_csv_chain_is_followed_to_its_end(self):
        self.assertEqual(name_key("Иоаникий", M), name_key("Иоанникий", M))

    def test_soft_sign_and_doubled_letters(self):
        self.assertEqual(name_key("Дарья", F), name_key("Дария", F))
        self.assertEqual(name_key("Агриппина", F), name_key("Агрипина", F))


def _table(*rows: tuple[Gender, str, tuple[tuple[int, int], ...]]) -> Svyatcy:
    return Svyatcy(Commemorated(gender=g, headword=n, name=n, dates=d) for g, n, d in rows)


class Queries(unittest.TestCase):
    def test_nearest(self):
        s = _table((F, "Агапия", ((4, 16),)))
        self.assertEqual((2, (4, 16)), s.nearest("Агапия", F, (1850, 4, 14)))
        self.assertEqual((-3, (4, 16)), s.nearest("Агапия", F, (1850, 4, 19)))
        self.assertIsNone(s.nearest("Мария", F, (1850, 4, 14)))

    def test_nearest_across_the_new_year(self):
        s = _table((M, "Даниил", ((12, 30),)))
        self.assertEqual((-3, (12, 30)), s.nearest("Даниил", M, (1851, 1, 2)))

    def test_names_near_nearest_first(self):
        s = _table((F, "Агапия", ((4, 16),)), (F, "Ирина", ((4, 16), (5, 5))),
                   (F, "Фомаида", ((4, 13),)), (M, "Иван", ((4, 16),)))
        near = s.names_near((1850, 4, 16), F, 3, 3)
        self.assertEqual(["Агапия", "Ирина", "Фомаида"], [n.name for n in near])
        self.assertEqual([0, 0, -3], [n.offset for n in near])

    def test_a_29_february_saint_is_kept_on_the_28th_in_a_common_year(self):
        s = _table((M, "Кассиан", ((2, 29),)))
        self.assertEqual(["Кассиан"], [n.name for n in s.names_near((1850, 2, 28), M, 0, 0)])
        self.assertEqual([], s.names_near((1852, 2, 28), M, 0, 0))

    def test_rank_by_the_reading(self):
        s = _table((F, "Агапия", ((4, 16),)), (F, "Мария", ((4, 1),)),
                   (F, "Ирина", ((4, 16),)))
        ranked = rank(s.names_near((1850, 4, 16), F, 15, 15), "Марья")
        self.assertEqual("Мария", ranked[0].name)


if __name__ == "__main__":
    unittest.main()


def test_the_kept_forms_find_the_book_under_the_base(base_workspace):
    """`ALSO_KEPT` names, for a people's form, names of the book: each must be one the book files a name under — through
    the base alone, which folds Юлиания onto Иулиания — and Ульяна, the people's form of Юлиана, finds the book."""
    from verso.core import workspace
    from verso.ru.church_calendar.svyatcy import ALSO_KEPT
    with workspace.use(base_workspace):
        book = load_svyatcy()
        filed = {key for _, key in book._dates}              # pyright: ignore[reportPrivateUsage]
        targets = {(g, n): name_key(n, g) for (g, _), names in ALSO_KEPT.items() for n in names}
        assert {t: k in filed for t, k in targets.items()} == {t: True for t in targets}
        assert book.knows("Ульяна", F)
        assert book.commemorations("Ульяна", F)


def test_the_kept_forms_follow_a_layer_that_folds_the_other_way(base_workspace):
    """A layer may fold the book's form onto the people's spelling — Иулиания onto Юлиания, as a corpus keeping its old
    table's bases does. The kept forms are names, so the table files them under the lexicon it files the book under,
    and Ульяна still finds Иулиания's days (v0.1.28 kept the base's key «иулиания» and lost them)."""
    from verso.core import workspace
    from verso.ru.naming import names_registry
    from verso.ru.naming.layer_files import base as names_base
    from verso.ru.naming.lexicon import Layer, Lexicon, NameEntry
    layer = Layer("corpus", {(F, "Иулиания"): NameEntry(F, "Иулиания", ("Юлиания",)),
                             (F, "Юлиания"): NameEntry(F, "Юлиания", ())}, {}, {})
    with workspace.use(base_workspace):
        alone = load_svyatcy().commemorations("Иулиания", F)
        with names_registry.answering(Lexicon.of([names_base().load(), layer])):
            book = load_svyatcy()
            assert name_key("Иулиания", F) == "юлиания"
            assert alone and set(alone) <= set(book.commemorations("Ульяна", F))
