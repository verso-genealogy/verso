import re
import unittest
from calendar import Month

from verso.core.targets.geni.union import GeniUnion, UnionOrigin
from verso.ru.dsl.records.births import birth, birth_month, birth_records, christening
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_month, death_records
from verso.ru.domain import Gender, RecordDefaults, page, person
from verso.ru.dsl.records.marriages import marriage, marriage_month, marriage_records
from verso.ru.relationship import Relationship, Relative, relative
from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator, generate_res_name_2


class TestBirthTranslation(unittest.TestCase):
    def _single_birth_records(self):
        return birth_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )

    def test_birth_dsl_produces_expected_child_profile_resource(self):
        records = self._single_birth_records()

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        self.assertIn('resource "geni_profile"', output)
        self.assertIn('Иван', output)
        self.assertIn('gender = "male"', output)

    def test_birth_child_res_name_matches_legacy_format(self):
        records = self._single_birth_records()

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        b = records.records[0]
        child = b.child
        expected_res_name = generate_res_name_2(
            year=1800, month=3, day=10,
            first_name=child.get_canonical_name(),
            middle_name=child.patr_modern or b.derive_child_patronymic() or "",
            last_name=child.last_name_modern or "",
            document_name="mk_births",
            role="child",
            record_number=1,
        )
        self.assertTrue(expected_res_name.startswith("_1800_03_10_ioann_petrovich_mk_births_1_child"),
                        f"unexpected res_name format: {expected_res_name!r}")
        self.assertIn(f'resource "geni_profile" "{expected_res_name}"', output)

    def test_foster_child_goes_to_foster_children(self):
        # A приёмыш (CensusRole.FOSTER_SON) is linked to HEAD's union via
        # foster_children (Geni "foster" relationship), NOT as a biological
        # child. A household with no wife: a «приемыш» of the head.
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1858,
            household("1",
                      member(1, person("Филипъ", "Васильевъ", "Брюквинъ"),
                             CensusRole.HEAD, age=30),
                      member(2, person("Иванъ"), CensusRole.SON, ref_member=1, age=6),
                      member(3, person("Макаръ", "Степановъ"), CensusRole.FOSTER_SON,
                             ref_member=1, age=8,
                             comment="приемыш Филиппа Васильева")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)

        bio = set()
        foster = set()
        for u in list(gen._union_registry.values()) + list(
                gen._consolidated_unions.values()):
            bio |= set(u.children or set())
            foster |= set(getattr(u, "foster_children", None) or set())
        # Biological son in children; foster child in foster_children — and
        # NEVER in the biological children set (disjoint, as the provider
        # requires).
        self.assertIn("ioann_filipovich_brjukvin", " ".join(bio))
        self.assertNotIn("makarij_stepanovich_brjukvin", " ".join(bio))
        self.assertIn("makarij_stepanovich_brjukvin", " ".join(foster))

    def test_foster_parent_without_union_gets_lone_foster_union(self):
        # A приёмыш whose ref_member names a member with NO couple/head union
        # (a brother of the head, no wife) gets a SINGLE-PARENT foster union for
        # that foster parent — NOT attached to the head. Here Тихон is the
        # приёмыш of Исай (a brother of the head Никифор).
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1719,
            household("1",
                      member(1, person("Никифоръ"), CensusRole.HEAD, age=40),
                      member(2, person("Петръ"), CensusRole.SON, ref_member=1, age=10),
                      member(3, person("Исай"), CensusRole.BROTHER, age=25),
                      member(4, person("Тихонъ", "Макаровъ"), CensusRole.FOSTER_SON,
                             ref_member=3, age=4, comment="приёмыш")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        by_name = {u.res_name: u for u in gen._union_registry.values()}
        # A single-partner union for Исай carries Тихон in foster_children...
        isai = next(u for k, u in by_name.items() if k.startswith("isaj") or k.startswith("isa"))
        self.assertEqual(isai.partner_2, None)
        self.assertIn("tihon_makarovich",
                      " ".join(getattr(isai, "foster_children", None) or set()))
        # ...and the head Никифор's union does NOT hold him.
        nikifor = next((u for k, u in by_name.items() if k.startswith("nikifor")), None)
        if nikifor is not None:
            self.assertNotIn("tihon_makarovich",
                             " ".join(getattr(nikifor, "foster_children", None) or set()))

    def test_foster_child_in_head_wife_household(self):
        # A приёмыш in a household WITH a wife must land in the head+wife
        # couple union's foster_children (not orphaned).
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1834,
            household("1",
                      member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=40),
                      member(2, person("Марья", "Иванова"), CensusRole.WIFE,
                             ref_member=1, age=38),
                      member(3, person("Семёнъ"), CensusRole.SON, age=12),
                      member(4, person("Арина", "Яковлева"), CensusRole.FOSTER_DAUGHTER,
                             ref_member=1, age=8, comment="приемыш")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        bio = set()
        foster = set()
        for u in list(gen._union_registry.values()) + list(gen._consolidated_unions.values()):
            bio |= set(u.children or set())
            foster |= set(getattr(u, "foster_children", None) or set())
        # biological son in the couple union; foster daughter in foster_children;
        # foster child NEVER a biological child (disjoint).
        self.assertIn("simeon_ivanovich", " ".join(bio))
        self.assertIn("irina_jakovlevna", " ".join(foster))
        self.assertNotIn("irina_jakovlevna", " ".join(bio))

    def test_foster_child_attaches_to_sub_head_not_head(self):
        # A приёмыш whose ref_member names a SUB-head (a son of the head who has
        # his own wife) attaches to the SUB-head's union foster_children, NOT the
        # household head's: Герасим «приемный сын» of Тимофей (head's son),
        # not of the grandfather Никита.
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1850,
            household("74",
                      member(1, person("Никита", "Артемьевъ"), CensusRole.HEAD, age=51),
                      member(2, person("Тимофей"), CensusRole.SON, age=30),
                      member(3, person("Герасим", "Прохоровъ"), CensusRole.FOSTER_SON,
                             ref_member=2, age=13, comment="приемный сын"),
                      member(4, person("Ксения", "Тихонова"), CensusRole.WIFE, age=57),
                      member(5, person("Пелагея", "Захарова"), CensusRole.WIFE,
                             ref_member=2, age=26)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        by_name = {u.res_name: u for u in gen._union_registry.values()}
        timofej = next(u for k, u in by_name.items() if k.startswith("timofej"))
        nikita = next(u for k, u in by_name.items() if k.startswith("nikita"))
        self.assertIn("gerasim_prohorovich",
                      " ".join(getattr(timofej, "foster_children", None) or set()))
        self.assertEqual(getattr(nikita, "foster_children", None) or set(), set())

    def test_subfamily_parent_with_bio_and_foster_child_one_union(self):
        # A sub-family parent (a brother of the head, no wife) with BOTH a
        # biological child and a приёмыш gets ONE union carrying children AND
        # foster_children — never two separate single-partner unions. Here
        # Назар has a son Прохор and a приёмыш Ипат.
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1719,
            household("1",
                      member(1, person("Афанасей", "Мартыновъ"), CensusRole.HEAD, age=48),
                      member(2, person("Назаръ", "Мартыновъ"), CensusRole.BROTHER, age=27),
                      member(3, person("Прохор"), CensusRole.SON, ref_member=2, age=1),
                      member(4, person("Ипатъ", "Ермиловъ"), CensusRole.FOSTER_SON,
                             ref_member=2, age=12, comment="приёмыш")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        nazarij_unions = [
            u for u in gen._union_registry.values()
            if u.partner_1 and "nazarij" in u.partner_1
        ]
        self.assertEqual(len(nazarij_unions), 1, "expected exactly one Назар union")
        u = nazarij_unions[0]
        self.assertIn("prohor_nazarovich", " ".join(u.children or set()))
        self.assertIn("ipatij_ermilovich",
                      " ".join(getattr(u, "foster_children", None) or set()))
        # disjoint: the foster child is never a biological child
        self.assertNotIn("ipatij_ermilovich", " ".join(u.children or set()))

    def test_foster_children_emitted_in_terraform(self):
        from verso.core.targets.geni.union import GeniUnion
        u = GeniUnion(res_name="u", partner_1="filipp",
                      children={"ioann"}, foster_children={"kazma"})
        out = u.to_terraform()
        self.assertIn("foster_children = [", out)
        self.assertIn("geni_profile.kazma.id", out)
        # biological children block still present and separate
        self.assertIn("children = [", out)
        self.assertIn("geni_profile.ioann.id", out)

    def test_birth_emits_father_mother_godparent_profiles_and_family_union(self):
        records = birth_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      mother=person("Марья", "Иванова"),
                      god_parent1=person("Федор", "Кузьмин"),
                      god_parent2=person("Анна", "Павлова")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        # 5 geni_profile resources: child, father, mother, god_parent_1, god_parent_2
        self.assertEqual(output.count('resource "geni_profile"'), 5,
                         f"expected 5 profiles; output:\n{output}")
        # at least 1 family geni_union (father+mother → child)
        self.assertGreaterEqual(output.count('resource "geni_union"'), 1,
                                f"expected at least one union; output:\n{output}")
        # child should appear in the family union's children list
        self.assertIn("_1800_03_10_ioann_petrovich_mk_births_1_child", output)
        # father's res_name should be referenced
        self.assertIn("mk_births_1_father", output)
        self.assertIn("mk_births_1_mother", output)
        self.assertIn("mk_births_1_god_parent_1", output)
        self.assertIn("mk_births_1_god_parent_2", output)

    def test_child_birth_location_uses_parent_residence_when_book_village_differs(self):
        # Book recorded in Собакевичево (parish), family lives in Горюхино
        # (father's home). Birth event must show Горюхино (where baby was
        # born), baptism must show Собакевичево (where the christening happened).
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "Никольская",
            1754,
            *birth_month(
                Month.APRIL,
                birth(3, Gender.MALE, 16, None,
                      child=person("Фаддей"),
                      father=person("Ермил", "Власов", residence="Горюхино")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        import re as _re
        birth_block = _re.search(r"birth = \{(.*?)\n  \}", output, _re.DOTALL)
        baptism_block = _re.search(r"baptism = \{(.*?)\n  \}", output, _re.DOTALL)
        self.assertIsNotNone(birth_block, f"no birth block in output:\n{output}")
        self.assertIsNotNone(baptism_block, f"no baptism block in output:\n{output}")

        self.assertIn("село Горюхино", birth_block.group(1),
                      "birth.location must be the father's home village (Горюхино)")
        self.assertIn("село Собакевичево", baptism_block.group(1),
                      "baptism.location must be the parish village (Собакевичево)")

    def test_child_profile_current_residence_inherits_father_residence(self):
        # Father lives in Собакевичево; the newborn's current_residence should be
        # derived from the father's residence (births.py), distinct from the
        # book's parish village (Горюхино).
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров", residence="Собакевичево")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        import re as _re
        # Isolate the child profile resource block (res_name ends in *_child).
        chunks = _re.split(r'(?=resource "geni_profile")', output)
        child_chunk = next(c for c in chunks if '_child"' in c.split("\n", 1)[0])
        cr = _re.search(r"current_residence = \{(.*?)\n  \}", child_chunk, _re.DOTALL)
        self.assertIsNotNone(cr, f"no current_residence in child block:\n{child_chunk}")
        self.assertIn("село Собакевичево", cr.group(1),
                      "child current_residence must derive from father's residence")

    def test_child_profile_includes_birth_and_baptism_events(self):
        records = birth_records(
            "TestArchive", "1", "1", "1", "Горюхино", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        # Child's birth event: day=10, month=3, year=1800, located at Горюхино.
        self.assertIn("birth = {", output)
        self.assertIn("day   = 10", output)
        self.assertIn("month = 3", output)
        self.assertIn("year  = 1800", output)
        self.assertIn("село Горюхино", output)
        # Baptism event: christening day=11, month=3 (same b_month), year=1800.
        self.assertIn("baptism = {", output)
        self.assertIn("day   = 11", output)

    def test_christening_emits_circa_birth_year_and_baptism_event(self):
        """A late/adult christening records a circa birth year (christening
        year − age) and a baptism event with the actual christening date,
        and labels the about-text as крещение."""
        records = birth_records(
            "TestArchive", "1", "1", "1", "Нижняя Яичница", "Николаевская",
            1900,
            *birth_month(
                Month.FEBRUARY,
                christening(4, Gender.MALE, 17, age=11,
                            child=person("Александр"),
                            father=person("Иоанн", "Андреев", last_name_orig="Индюшев")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1900_birth.tf")

        # Birth event: circa year = 1900 − 11 = 1889, no day/month.
        birth_block = re.search(r"birth = \{(.*?)\n  \}", output, re.DOTALL)
        self.assertIsNotNone(birth_block, f"no birth block in output:\n{output}")
        self.assertIn("circa = true", birth_block.group(1))
        self.assertIn("year  = 1889", birth_block.group(1))
        self.assertNotIn("day", birth_block.group(1))
        # Baptism event: christening day=24, month=2, year=1900.
        baptism_block = re.search(r"baptism = \{(.*?)\n  \}", output, re.DOTALL)
        self.assertIsNotNone(baptism_block, f"no baptism block in output:\n{output}")
        self.assertIn("day   = 17", baptism_block.group(1))
        self.assertIn("month = 2", baptism_block.group(1))
        self.assertIn("year  = 1900", baptism_block.group(1))
        # About-text labels the event as a christening at a stated age.
        self.assertIn("крещение", output)
        self.assertIn("Крещён в возрасте 11 лет", output)
        # geni_document is labelled крещение (not рождение) and notes the circa year.
        self.assertIn("крещение Александр", output)
        self.assertNotIn("рождение Александр", output)
        self.assertIn("Дата рождения: около 1889 г. (возраст при крещении: 11)", output)

    def test_christening_without_age_labels_baptism_and_omits_birth_date(self):
        """A christening with no stated age renders as крещение everywhere
        (about + geni_document) and emits no birth date — only the baptism
        event carries a date."""
        records = birth_records(
            "TestArchive", "1", "1", "1", "Нижняя Яичница", "Николаевская",
            1893,
            *birth_month(
                Month.MARCH,
                christening(9, Gender.FEMALE, 12,
                            child=person("Параскева"),
                            father=person("Семен", last_name_orig="Индюшев")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1893_birth.tf")

        # Birth event has a location but no date (no circa year either).
        birth_block = re.search(r"birth = \{(.*?)\n  \}", output, re.DOTALL)
        self.assertIsNotNone(birth_block, f"no birth block in output:\n{output}")
        self.assertNotIn("date", birth_block.group(1))
        # Baptism event carries the christening date.
        baptism_block = re.search(r"baptism = \{(.*?)\n  \}", output, re.DOTALL)
        self.assertIsNotNone(baptism_block)
        self.assertIn("day   = 12", baptism_block.group(1))
        # Labelled крещение throughout; no рождение label and no birth-date line.
        self.assertIn("крещение", output)
        self.assertNotIn("рождение", output)
        self.assertNotIn("Дата рождения", output)
        self.assertIn("Дата крещения: 12.3.1893", output)

    def test_name_variant_uses_canonical_first_name_and_res_name(self):
        """
        The translator canonicalizes first names via names.csv so displayed
        profiles and resource identifiers use the modern canonical form
        (e.g. "Тихан" → "Тихон"). Names with no canonical mapping in names.csv
        fall back to the orthographic form unchanged.
        """
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *birth_month(
                Month.MARCH,
                birth(2, Gender.MALE, 19, None,
                      child=person("Тихан"),
                      father=person("Тимофей", "Петров")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        self.assertIn("_1754_03_19_tihon_timofeevich_mk_births_2_child", output)
        self.assertIn('first_name  = "Тихон"', output)
        self.assertNotIn("_1754_03_19_tihan_timofeevich_mk_births_2_child", output)
        self.assertNotIn('first_name  = "Тихан"', output)

    def test_child_profile_about_text_has_bold_document_header(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *birth_month(
                Month.MAY,
                birth(3, Gender.FEMALE, 7, 8,
                      child=person("Мария"),
                      father=person("Иван", "Петров", status="крестьянин")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1810_birth.tf")

        # about block lives on the child profile; legacy format is:
        #   <strong>МК {village} {year}:</strong> рождение
        self.assertIn('<strong>МК Горюхино 1810:</strong> рождение', output)
        # Father's status appears under the child's about as "Титул/звание отца",
        # indented with 8 spaces so it aligns with the opening <strong> line
        # after `terraform fmt` normalizes the trimspace(<<-EOT ...) block.
        self.assertIn('        Титул/звание отца: крестьянин', output)

    def test_child_about_includes_names_in_mk_quote(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *[birth(2, Gender.MALE, 19, None,
                    child=person("Тихан"),
                    father=person("Тимофей", "Петров"),
                    b_month=Month.MARCH)],
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        # Legacy tail format:
        #   Комментарий из МК:
        #   >Имена в МК: Тихан; Тимофей Петров
        self.assertIn("Комментарий из МК:", output)
        self.assertIn(">Имена в МК: Тихан; Тимофей Петров", output)

    def test_person_comment_appended_inline_to_names_in_mk(self):
        """`person("Нестор", comment="имя неразбочиво написано")` should
        render in `Имена в МК` as `Нестор - имя неразбочиво написано`,
        preserving the per-name annotation that legacy carried inline."""
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(21, Gender.MALE, 12, None,
                    child=person("Нестор",
                                 comment="имя неразбочиво написано"),
                    father=person("Елисей", "Лазарев",
                                  residence="Горюхино"),
                    god_parent1=person("Василий", "Артемов",
                                       residence="Горюхино"),
                    b_month=Month.OCTOBER)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        self.assertIn(
            ">Имена в МК: Нестор - имя неразбочиво написано; "
            "Елисей Лазарев; Василий Артемов",
            output,
        )
        self.assertIn(
            "Комментарий: Имена в МК: Нестор - имя неразбочиво написано; "
            "Елисей Лазарев; Василий Артемов",
            output,
        )

    def test_long_form_narrative_drops_short_form_suffix_from_names_in_mk(self):
        """When the comment carries a long-form `<short> в МК, но <reason>`
        narrative (which renders as its own `>` line), don't also append
        the short prefix to `Имена в МК:`. Removes the redundant
        `Имена в МК: …; Населенный пункт не указан` followed by
        `Населенный пункт не указан в МК, но…` pattern."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1801,
            *[birth(1, Gender.FEMALE, 20, 24,
                    child=person("Марфа"),
                    father=person("Фома", "Лазарев"),
                    god_parent1=person("Ульяна", "Макарова"),
                    comment="Населенный пункт не указан в МК, но все крестьяне этого помещика из Горюхино",
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1801_birth.tf")

        # The bare `Имена в МК:` line — no `; Населенный пункт не указан` suffix.
        self.assertIn(
            ">Имена в МК: Марфа; Фома Лазарев; Ульяна Макарова\n",
            output,
        )
        self.assertNotIn(
            ">Имена в МК: Марфа; Фома Лазарев; Ульяна Макарова; Населенный пункт не указан",
            output,
        )
        # Long-form narrative still on its own `>` line.
        self.assertIn(
            ">Населенный пункт не указан в МК, но все крестьяне этого помещика из Горюхино",
            output,
        )

    def test_short_form_only_comment_emitted_on_separate_line(self):
        """`Имена в МК:` always lists names only — comments (short-form
        or otherwise) live on their own `>{comment}` line in the about
        block and `Пометки: {comment}` in the doc text body."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1801,
            *[birth(1, Gender.FEMALE, 5, 5,
                    child=person("Дария"),
                    father=person("Иван", "Петров"),
                    god_parent1=person("Анна", "Сидорова"),
                    comment="Населенный пункт восприемника не указан",
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1801_birth.tf")

        self.assertIn(">Имена в МК: Дария; Иван Петров; Анна Сидорова\n", output)
        self.assertNotIn("; Населенный пункт восприемника не указан", output)
        self.assertIn(">Населенный пункт восприемника не указан", output)
        self.assertIn("Пометки: Населенный пункт восприемника не указан", output)

    def _aged_birth_output(self, **kw):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N", 1801,
            *[birth(1, Gender.FEMALE, 5, 5, child=person("Дария"), father=person("Иван", "Петров"),
                    mother=person("Анна", "Сидорова"), god_parent1=person("Фёкла", "Иванова"),
                    b_month=Month.JANUARY, **kw)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        return gen.get_output("mk_1801_birth.tf")

    def test_parent_ages_reach_the_document_and_the_about_texts(self):
        output = self._aged_birth_output(comment="Заявитель — отец", father_age=31, mother_age=30)
        self.assertIn("Пометки: Заявитель — отец; отцу 31 год, матери 30 лет", output)
        self.assertIn(">Заявитель — отец; отцу 31 год, матери 30 лет", output)
        self.assertEqual(2, output.count("Возраст при рождении ребёнка:"))
        self.assertIn("Возраст при рождении ребёнка: 31 год", output)
        self.assertIn("Возраст при рождении ребёнка: 30 лет", output)

    def test_a_godparents_about_text_shows_the_parents_ages(self):
        output = self._aged_birth_output(comment="Заявитель — отец", father_age=31, mother_age=30)
        godparent = next(blk for blk in output.split('resource "geni_profile"')
                         if "god_parent_1" in blk.split("{", 1)[0])
        self.assertIn(">Заявитель — отец; отцу 31 год, матери 30 лет", godparent)

    def test_a_consolidated_parent_carries_the_age_line(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N", 1801,
            *[birth(1, Gender.FEMALE, 5, 5, child=person("Дария"), father=person("Иван", "Петров"),
                    mother=person("Анна", "Сидорова"), b_month=Month.JANUARY,
                    father_age=31, mother_age=30)],
        )
        plain = TerraformGenerator(village_dir=None)
        plain.add_birth_records(records)
        father_res = next(name for name in re.findall(r'resource "geni_profile" "([^"]+)"', plain.get_output("mk_1801_birth.tf"))
                          if name.endswith("_father"))
        gen = TerraformGenerator(village_dir=None, consolidation=Consolidation(
            profile_move_list={father_res: "ioann_petrov"}))
        gen.add_birth_records(records)
        gen.finalize()
        consolidated = gen.get_output("consolidated_profiles_1.tf")
        self.assertIn('resource "geni_profile" "ioann_petrov"', consolidated)
        self.assertIn("Возраст при рождении ребёнка: 31 год", consolidated)
        self.assertNotIn("Возраст при рождении ребёнка: 30 лет", consolidated)

    def test_a_parent_age_format_age_leaves_alone_is_said_as_written(self):
        output = self._aged_birth_output(father_age="около 30")
        self.assertIn("Пометки: отцу около 30", output)
        self.assertIn("Возраст при рождении ребёнка: около 30", output)

    def test_without_parent_ages_a_birth_has_no_age_lines(self):
        output = self._aged_birth_output(comment="Заявитель — отец")
        self.assertNotIn("Возраст при рождении", output)
        self.assertNotIn("отцу", output)
        self.assertIn("Пометки: Заявитель — отец\n", output.replace("\n        ", "\n"))

    def test_pometki_no_duplication_with_short_prefix(self):
        """Multi-segment comment where one segment matches a short-form
        pattern: the full comment appears once on `>{comment}` and
        `Пометки: {comment}`, with nothing duplicated on `Имена в МК:`."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1801,
            *[birth(4, Gender.MALE, 3, 3,
                    child=person("Мирон"),
                    father=person("Назар", "Власов"),
                    comment="Восприемники не указаны; Лист не указан в МК",
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1801_birth.tf")

        self.assertIn(">Имена в МК: Мирон; Назар Власов\n", output)
        self.assertNotIn("Имена в МК: Мирон; Назар Власов; Восприемники", output)
        self.assertIn(">Восприемники не указаны; Лист не указан в МК", output)
        self.assertIn("Пометки: Восприемники не указаны; Лист не указан в МК", output)

    def test_birth_relative_of_godparent_emits_about_block(self):
        """Relative profiles tied to a godparent get an `about` block
        following legacy format: '<strong>МК ... :</strong> {rel_type}
        восприемника на крещении', plus optional Титул/звание and the
        same Имена в МК line as other profiles in the record."""
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(14, Gender.FEMALE, 8, None,
                    child=person("Фекла"),
                    father=person("Прохор", "Борисов"),
                    god_parent1=person("Марфа", "Лазарева",
                                       residence="Горюхино"),
                    relatives=[Relative(person("Лазарь", "Борисов",
                                               status="ясачный крестьянин"),
                                        Relationship.FATHER,
                                        "восприемника №1")],
                    b_month=Month.JUNE)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        rel_block = output.split(
            '"_1784_06_08_lazar_borisovich_mk_births_14_rel_1"', 1
        )[1].split("\n}\n", 1)[0]
        self.assertIn(
            "<strong>МК Собакевичево 1784:</strong> отец восприемника на крещении",
            rel_block,
        )
        self.assertIn("Титул/звание: ясачный крестьянин", rel_block)
        self.assertIn(
            ">Имена в МК: Фекла; Прохор Борисов; Марфа Лазарева; Лазарь Борисов",
            rel_block,
        )

    def test_birth_husband_of_godparent_about_uses_husband_label(self):
        """HUSBAND-of-godparent → about line says `муж восприемника на крещении`."""
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(7, Gender.FEMALE, 11, None,
                    child=person("Таисия"),
                    father=person("Харитон", "Мефодьев",
                                  residence="Горюхино"),
                    god_parent1=person("Христина", "Нилова",
                                       residence="Горюхино"),
                    relatives=[Relative(person("Захар", "Андреев"),
                                        Relationship.HUSBAND,
                                        "восприемника №1")],
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        rel_block = output.split(
            '"_1784_01_11_zaharija_andreevich_mk_births_7_rel_1"', 1
        )[1].split("\n}\n", 1)[0]
        self.assertIn(
            "<strong>МК Собакевичево 1784:</strong> муж восприемника на крещении",
            rel_block,
        )

    def test_birth_relative_with_unmapped_ref_has_no_about(self):
        """Relatives with unrecognized `relationship_ref` keep the bare
        profile shape (no `about` block) — no false labels emitted."""
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(99, Gender.MALE, 1, None,
                    child=person("Иван"),
                    father=person("Петр", "Сидоров",
                                  residence="Горюхино"),
                    relatives=[Relative(person("Захар", "Леонтьев"),
                                        Relationship.HUSBAND, None)],
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        rel_block = output.split(
            '"_1784_01_01_zaharija_leontevich_mk_births_99_rel_1"', 1
        )[1].split("\n}\n", 1)[0]
        self.assertNotIn("about = {", rel_block)

    def test_birth_relative_of_godparent_emits_parent_child_union(self):
        """A relative tied to a godparent via `relationship_ref="восприемника №N"`
        with a parent-style relationship (FATHER/MOTHER) must produce a
        single-parent union (relative=partner_1, godparent in children).
        Mirrors legacy `god_parent_rel` behavior for non-spouse types."""
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(14, Gender.FEMALE, 8, None,
                    child=person("Фекла"),
                    father=person("Прохор", "Борисов"),
                    god_parent1=person("Марфа", "Лазарева",
                                       residence="Горюхино"),
                    relatives=[Relative(person("Лазарь", "Борисов"),
                                        Relationship.FATHER,
                                        "восприемника №1")],
                    b_month=Month.JUNE)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        self.assertIn(
            'resource "geni_union" "lazar_borisovich_and_marfa_lazarevna_14_1784"',
            output,
        )
        # Union body: relative is partner_1, godparent is in children.
        union_block = output.split(
            '"lazar_borisovich_and_marfa_lazarevna_14_1784"', 1
        )[1].split("}\n", 2)[0]
        self.assertIn(
            "geni_profile._1784_06_08_lazar_borisovich_mk_births_14_rel_1.id",
            union_block,
        )
        self.assertIn(
            "geni_profile._1784_06_08_marfa_lazarevna_mk_births_14_god_parent_1.id",
            union_block,
        )
        self.assertIn("children = [", union_block)

    def test_birth_husband_of_godparent_emits_spouse_union(self):
        """HUSBAND-of-godparent relative produces a spouse-pair union
        (both partners, no children)."""
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(7, Gender.FEMALE, 11, None,
                    child=person("Таисия"),
                    father=person("Харитон", "Мефодьев",
                                  residence="Горюхино"),
                    god_parent1=person("Христина", "Нилова",
                                       residence="Горюхино"),
                    relatives=[Relative(person("Захар", "Андреев"),
                                        Relationship.HUSBAND,
                                        "восприемника №1")],
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        self.assertIn(
            'resource "geni_union" "zaharija_andreevich_and_hristina_nilovna_7_1784"',
            output,
        )
        union_block = output.split(
            '"zaharija_andreevich_and_hristina_nilovna_7_1784"', 1
        )[1].split("}\n", 2)[0]
        self.assertIn("partners = [", union_block)
        # Spouse pair → no `children` set.
        self.assertNotIn("children = [", union_block)

    def test_birth_relative_with_no_ref_emits_no_extra_union(self):
        """When `relationship_ref` is None or doesn't point at any in-record
        target (godparent), the relative profile is still emitted but no
        extra union is built."""
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(99, Gender.MALE, 1, None,
                    child=person("Иван"),
                    father=person("Петр", "Сидоров",
                                  residence="Горюхино"),
                    relatives=[Relative(person("Захар", "Леонтьев"),
                                        Relationship.HUSBAND, None)],
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        # Relative profile still emitted.
        self.assertIn("mk_births_99_rel_1", output)
        # But no `*_and_*_99_1784` godparent-relative union.
        import re
        self.assertEqual(
            len(re.findall(r'resource "geni_union" "zaharija_leontevich_and_', output)),
            0,
        )

    def test_birth_names_in_mk_includes_relative_names(self):
        """Birth records can list `relatives=[...]` (e.g. husband or father
        of a godparent). Their names must surface in `Имена в МК:` after
        the child/parents/godparents — same legacy behavior as death
        records."""
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1784,
            *[birth(14, Gender.FEMALE, 8, None,
                    child=person("Фекла"),
                    father=person("Прохор", "Борисов"),
                    god_parent1=person("Марфа", "Лазарева",
                                       residence="Горюхино"),
                    relatives=[Relative(person("Лазарь", "Борисов"),
                                        Relationship.FATHER,
                                        "восприемника №1")],
                    b_month=Month.JUNE)],
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1784_birth.tf")

        self.assertIn(
            ">Имена в МК: Фекла; Прохор Борисов; Марфа Лазарева; Лазарь Борисов",
            output,
        )

    def test_child_about_carries_comment_as_quoted_line(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *[birth(6, Gender.MALE, 9, None,
                    child=person("Илья"),
                    father=person("Трофим", "Лаврентьев"),
                    comment="Трафим Лаврентьев - звание и НП не указаны",
                    b_month=Month.JULY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        # Two quoted lines in the child's about: the names-in-MK line first,
        # then the comment as its own `>`-prefixed line, matching the legacy
        # generate_config.py format (two separate blockquote lines).
        self.assertIn(">Имена в МК: Илья; Трофим Лаврентьев", output)
        self.assertIn(">Трафим Лаврентьев - звание и НП не указаны", output)
        i_names = output.find(">Имена в МК:")
        i_notes = output.find(">Трафим Лаврентьев - звание и НП не указаны")
        self.assertGreater(i_names, -1)
        self.assertGreater(i_notes, i_names,
                           "comment line must appear after the names-in-MK line")

    def test_long_form_comment_is_emitted_without_short_form_duplication(self):
        """When the comment is a long-form `<short> в МК, но <reason>`
        narrative, only the standalone `>` line carries the text — don't
        also append the short prefix to `Имена в МК:`. Legacy redundantly
        showed both; Option 1 trims the duplication."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1806,
            *[birth(1, Gender.FEMALE, 3, 9,
                    child=person("Дарья"),
                    father=person("Мефодий", "Фролов"),
                    god_parent1=person("Анфиса", "Игнатова"),
                    comment="Населенный пункт восприемника не указан в МК, но все крестьяне этого помещика из Собакевичево.",
                    b_month=Month.JULY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1806_birth.tf")
        # Bare `Имена в МК:` line — no short-form suffix.
        self.assertIn(
            ">Имена в МК: Дарья; Мефодий Фролов; Анфиса Игнатова\n",
            output,
        )
        self.assertNotIn(
            ">Имена в МК: Дарья; Мефодий Фролов; Анфиса Игнатова; "
            "Населенный пункт восприемника не указан",
            output,
        )
        # Long-form comment still on its own `>` line.
        self.assertIn(
            ">Населенный пункт восприемника не указан в МК, но все крестьяне этого помещика из Собакевичево.",
            output,
        )

    def test_short_form_comment_emitted_on_own_line_only(self):
        """Comments — even when they match a single short-form pattern —
        are emitted on their own `>{comment}` and `Пометки: {comment}`
        lines. Names-only on `Имена в МК:`."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1809,
            *[birth(1, Gender.MALE, 5, 6,
                    child=person("Петр"),
                    father=person("Иван", "Сидоров"),
                    comment="Населенный пункт восприемника не указан",
                    b_month=Month.JULY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1809_birth.tf")

        self.assertIn(">Имена в МК: Петр; Иван Сидоров\n", output)
        self.assertNotIn(
            ">Имена в МК: Петр; Иван Сидоров; Населенный пункт",
            output,
        )
        self.assertIn(">Населенный пункт восприемника не указан", output)
        self.assertIn("Пометки: Населенный пункт восприемника не указан", output)

    def test_comment_without_short_form_pattern_leaves_names_unchanged(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1806,
            *[birth(1, Gender.MALE, 3, 5,
                    child=person("Петр"),
                    father=person("Иван", "Сидоров"),
                    comment="Какой-то уникальный комментарий не совпадающий с шаблонами.",
                    b_month=Month.JULY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1806_birth.tf")
        # `Имена в МК:` has no suffix.
        self.assertIn(">Имена в МК: Петр; Иван Сидоров\n", output)

    def test_document_text_emits_komm_and_pometki_on_separate_lines(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *[birth(6, Gender.MALE, 9, None,
                    child=person("Илья"),
                    father=person("Трофим", "Лаврентьев"),
                    comment="Трафим Лаврентьев - звание и НП не указаны",
                    b_month=Month.JULY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        # Two separate lines in document text, not one joined with "; ".
        self.assertIn("Комментарий: Имена в МК: Илья; Трофим Лаврентьев", output)
        self.assertIn("Пометки: Трафим Лаврентьев - звание и НП не указаны", output)
        self.assertNotIn(
            "Комментарий: Трафим Лаврентьев - звание и НП не указаны; Имена в МК:",
            output,
        )
        self.assertNotIn(
            "Комментарий: Имена в МК: Илья; Трофим Лаврентьев; Пометки:",
            output,
        )

    def test_birth_emits_geni_document_with_date_labels_and_profile_refs(self):
        records = birth_records(
            "ГАТО (Тамбов)", "2041", "94", "8", "Горюхино", "Никольская",
            1754,
            *birth_month(
                Month.MARCH,
                birth(2, Gender.MALE, 19, None,
                      child=person("Иван"),
                      father=person("Тимофей", "Петров")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        self.assertIn('resource "geni_document"', output)
        # Document name is derived from child name + record + year.
        self.assertIn('"birth_of_ioann_timofeevich_2_1754"', output)
        # Includes Birth label and date.
        self.assertIn('labels = [', output)
        self.assertIn('"Birth"', output)
        self.assertIn('day   = 19', output)
        self.assertIn('month = 3', output)
        self.assertIn('year  = 1754', output)
        # References the child and father profiles by id.
        self.assertIn('geni_profile._1754_03_19_ioann_timofeevich_mk_births_2_child.id', output)
        self.assertIn('geni_profile._1754_03_19_timofej_petrovich_mk_births_2_father.id', output)

    def test_geni_document_description_includes_page_and_record_number(self):
        records = birth_records(
            "ГАТО (Тамбов)", "2041", "94", "8", "Горюхино", "N",
            1754,
            *[birth(2, Gender.MALE, 19, None,
                    child=person("Иван"),
                    father=person("Тимофей", "Петров"),
                    page="93",
                    b_month=Month.MARCH)],
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        self.assertIn("Лист: 93", output)
        self.assertIn("№ записи: 2", output)

    def test_birth_document_question_mark_page_renders_blank_list_line(self):
        """When `*page("?", ...)` marks the pageboard as unknown, legacy emits
        a bare `Лист:` (blank after the colon). Translator must do the same
        instead of rendering `Лист: ?`. Same rule already applies to
        marriages and deaths; births had an earlier gap."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1806,
            *page(
                "?",
                *birth_month(
                    Month.MARCH,
                    birth(1, Gender.MALE, 10, 11,
                          child=person("Иван"),
                          father=person("Петр", "Сидоров")),
                ),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1806_birth.tf")

        # Blank `Лист:` (no value), once in description and once in text body.
        self.assertEqual(output.count("Лист:\n"), 2,
                         f"expected two bare `Лист:` occurrences; output:\n{output}")
        # And definitely not the `?` placeholder leaking through.
        self.assertNotIn("Лист: ?", output)

    def test_geni_document_text_includes_dates_and_parents(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *[birth(1, Gender.MALE, 22, None,
                    child=person("Иван"),
                    father=person("Тимофей", "Петров", status="крестьянин"),
                    mother=person("Анна", "Петрова"),
                    page="87",
                    b_month=Month.MARCH)],
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        self.assertIn("Дата рождения: 22.3.1754", output)
        # Christening day is unknown → legacy uses `?.3.1754`.
        self.assertIn("Дата крещения: ?.3.1754", output)
        self.assertIn("Ребенок: Иоанн", output)
        # "Отец: {status} {first} {patronymic}" — last name blank here.
        self.assertIn("Отец: крестьянин Тимофей Петрович", output)
        self.assertIn("Мать: ", output)
        self.assertIn("Анна Петровна", output)

    def test_godparent_line_includes_residence_suffix_when_outside_parish(self):
        """When a godparent's residence differs from the parish village,
        legacy appends ` ({residence})` to the `Воспреемник N:` line in
        the birth document's text body. Parents (`Отец`/`Мать`) don't get
        the suffix even when their residence differs. Translator must
        match."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *[birth(1, Gender.MALE, 22, None,
                    child=person("Иван"),
                    father=person("Тимофей", "Андреев",
                                  residence="Собакевичево",
                                  status="крестьянин"),
                    mother=person("Пелагея", "Герасимова",
                                  residence="Собакевичево",
                                  status="законная жена крестьянина"),
                    god_parent1=person("Петр", "Демидов",
                                       residence="Собакевичево",
                                       status="крестьянин"),
                    god_parent2=person("Анна", "Леонтьева",
                                       residence="Горюхино",
                                       status="крестьянка"),
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")

        # Godparent from Собакевичево (outside parish) gets `(Собакевичево)` suffix.
        self.assertIn(
            "Воспреемник 1: крестьянин Петр Демидович (Собакевичево)",
            output,
        )
        # Godparent from the parish village itself does NOT get a suffix.
        self.assertIn("Воспреемник 2: крестьянка Анна Леонтьевна", output)
        self.assertNotIn("Воспреемник 2: крестьянка Анна Леонтьевна (Горюхино)", output)
        # Parents NEVER get the residence suffix, even when their residence
        # differs from the parish.
        self.assertNotIn("Отец: крестьянин Тимофей Андреевич (Собакевичево)", output)
        self.assertIn("Мать: законная жена крестьянина Пелагия Герасимовна\n", output)
        self.assertNotIn("Мать: законная жена крестьянина Пелагия Герасимовна (Собакевичево)", output)

    def test_document_text_lists_godparents_after_mother(self):
        """Legacy birth document body has
        `Воспреемник 1: {title} {first} {patr} [{last}]` and
        `Воспреемник 2: ...` lines between 'Мать:' and 'Комментарий:'.
        The translator must emit these when god_parent1/god_parent2 are set.
        """
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *[birth(1, Gender.MALE, 22, None,
                    child=person("Иван"),
                    father=person("Тимофей", "Андреев",
                                  status="ясачный крестьянин"),
                    mother=person("Пелагея", "Герасимова"),
                    god_parent1=person("Прохор", "Герасимов",
                                       status="ясачный крестьянин"),
                    god_parent2=person("Ольга", "Андреева",
                                       status="ясачная крестьянка"),
                    b_month=Month.MARCH)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn(
            "Воспреемник 1: ясачный крестьянин Прохор Герасимович",
            output,
        )
        self.assertIn(
            "Воспреемник 2: ясачная крестьянка Ольга Андреевна",
            output,
        )

    def test_godparent_profile_carries_birth_range_and_death_after_christening(self):
        """Legacy godparent profile has:
          - `birth.date.range="between"`, circa, year = year-60, end_year = year-6
          - `death.date.range="after"` at the christening date
          - `about = "<strong>МК ...</strong> восприемник на крещении"`
        """
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *[birth(3, Gender.MALE, 4, 5,
                    child=person("Гордей"),
                    father=person("Харитон", "Матвеев"),
                    mother=person("Анна", "Борисова"),
                    god_parent1=person("Иван", "Тихонов",
                                       status="ясачный крестьянин"),
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")

        # Find the godparent1 profile block and assert its fields.
        block = _extract_resource_block(
            output, "_1838_01_04_ioann_tihonovich_mk_births_3_god_parent_1"
        )
        # Birth is an estimated range 60→6 years before the child's birth.
        self.assertIn('range     = "between"', block)
        self.assertIn('year      = 1778', block)
        self.assertIn('end_year  = 1832', block)
        # Death is "after" the christening date. Raw translator output
        # uses the same padded `=` column that the birth block uses.
        self.assertIn('range = "after"', block)
        self.assertIn('day   = 5', block)
        self.assertIn('month = 1', block)
        self.assertIn('year  = 1838', block)
        # About carries the legacy header + status.
        self.assertIn("восприемник на крещении", block)
        self.assertIn("Титул/звание: ясачный крестьянин", block)

    def _birth_with_flag(self, mother_flag=True, gp2_flag=True):
        """Helper: 1838 family-of-Мижуев record where all 4 adults have
        `last_name_orig="Мижуев"`. `mother_flag` and `gp2_flag` control
        whether their surnames are marked as "in book" — when False, the
        translator should drop the surname from doc-text rendering."""
        return birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *[birth(3, Gender.MALE, 4, 5,
                    child=person("Иван"),
                    father=person("Тимофей", "Андреев", last_name_orig="Мижуев"),
                    mother=person("Пелагея", "Герасимова",
                                  last_name_orig="Мижуева",
                                  last_name_in_book=mother_flag),
                    god_parent1=person("Прохор", "Герасимов",
                                       last_name_orig="Мижуев",
                                       status="ясачный крестьянин"),
                    god_parent2=person("Ольга", "Андреева",
                                       last_name_orig="Мижуев",
                                       status="ясачная крестьянка",
                                       last_name_in_book=gp2_flag),
                    b_month=Month.JANUARY)],
        )

    def test_names_in_mk_includes_last_name_by_default(self):
        """Default `last_name_in_book=True` → surname still appears in
        the reconstructed 'Имена в МК:' line. Pins existing behavior."""
        records = self._birth_with_flag(mother_flag=True, gp2_flag=True)
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn(
            "Имена в МК: Иван; Тимофей Андреев Мижуев; "
            "Пелагея Герасимова Мижуева; Прохор Герасимов Мижуев; "
            "Ольга Андреева Мижуев",
            output,
        )

    def test_names_in_mk_skips_last_name_when_flagged_not_in_book(self):
        """With `last_name_in_book=False` on mother + gp2, their
        surnames drop from the 'Имена в МК:' line. Matches legacy
        rendering exactly."""
        records = self._birth_with_flag(mother_flag=False, gp2_flag=False)
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn(
            "Имена в МК: Иван; Тимофей Андреев Мижуев; "
            "Пелагея Герасимова; Прохор Герасимов Мижуев; "
            "Ольга Андреева",
            output,
        )
        self.assertNotIn("Пелагея Герасимова Мижуева", output)
        self.assertNotIn("Ольга Андреева Мижуев", output)

    def test_mother_doc_line_drops_last_name_when_flagged_not_in_book(self):
        """`last_name_in_book=False` suppresses the surname in the
        `Мать:` document-text line too — the role line should reflect
        what the book actually wrote, just like the `Имена в МК:` line."""
        records = self._birth_with_flag(mother_flag=False)
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn("Мать: Пелагия Герасимовна\n", output)
        self.assertNotIn("Мать: Пелагия Герасимовна Мижуева", output)

    def test_godparent_doc_line_drops_last_name_when_flagged_not_in_book(self):
        """Like `Мать:`, the `Воспреемник N:` role line honors
        `last_name_in_book=False` — the surname known to the profile is
        kept off the document text when the book itself didn't write it."""
        records = self._birth_with_flag(gp2_flag=False)
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn(
            "Воспреемник 2: ясачная крестьянка Ольга Андреевна\n",
            output,
        )
        self.assertNotIn(
            "Воспреемник 2: ясачная крестьянка Ольга Андреевна Мижуев",
            output,
        )

    def test_auto_inherited_mother_surname_is_kept_off_doc_text(self):
        """When the mother has no explicit surname and inherits the
        feminized father surname (via Birth.__init__), the document text
        must still render her as the book wrote her — first name + patr
        only — because the inherited surname is deduced, not transcribed."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *[birth(3, Gender.MALE, 4, 5,
                    child=person("Иван"),
                    father=person("Тимофей", "Андреев", last_name_orig="Мижуев"),
                    mother=person("Пелагея", "Герасимова"),
                    b_month=Month.JANUARY)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn("Мать: Пелагия Герасимовна\n", output)
        self.assertNotIn("Мать: Пелагия Герасимовна Мижуева", output)
        # But the mother profile still carries the inherited surname so
        # cross-record consolidation can match her.
        self.assertIn("pelagija_gerasimovna_mizhueva", output)

    def test_profile_res_name_preserves_last_name_even_when_flagged(self):
        """`last_name_in_book=False` is a book-rendering flag only —
        the person's profile keeps its identity-bearing surname in
        res_name, `names` block, and residence-based projects."""
        records = self._birth_with_flag(gp2_flag=False)
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        # Profile res_name still contains `_mizhuev_`.
        self.assertIn("_1838_01_04_olga_andreevna_mizhuev_mk_births_3_god_parent_2", output)
        # Names block still has last_name.
        block = _extract_resource_block(
            output, "_1838_01_04_olga_andreevna_mizhuev_mk_births_3_god_parent_2",
        )
        self.assertIn('last_name   = "Мижуев"', block)

    def test_document_text_omits_godparent_line_when_absent(self):
        """A birth with only one godparent (e.g. only god_parent1) should
        not emit a 'Воспреемник 2:' line at all."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *[birth(1, Gender.MALE, 22, None,
                    child=person("Иван"),
                    father=person("Тимофей", "Петров"),
                    god_parent1=person("Петр", "Иванов"),
                    b_month=Month.MARCH)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")
        self.assertIn("Воспреемник 1: Петр Иванович", output)
        self.assertNotIn("Воспреемник 2:", output)

    def test_document_text_tail_carries_names_in_mk_comment(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *[birth(2, Gender.MALE, 19, None,
                    child=person("Тихан"),
                    father=person("Тимофей", "Петров"),
                    b_month=Month.MARCH)],
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        # In the geni_document's text body, legacy appends:
        #   Комментарий: Имена в МК: Тихан; Тимофей Петров
        self.assertIn("Комментарий: Имена в МК: Тихан; Тимофей Петров", output)

    def test_mother_profile_has_about_block_and_death_stub(self):
        """Legacy mother profile mirrors father's enrichment: an 'мать
        ребенка' about block with status + Имена в МК, plus a
        `death = { range = "after" ... }` alive-as-of-birth stub.
        Translator previously emitted only current_residence for mothers."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров", status="крестьянин"),
                      mother=person("Мария", "Иванова", status="крестьянка")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        # Find the mother profile block.
        block = _extract_resource_block(
            output, "_1800_03_10_marija_ivanovna_mk_births_1_mother",
        )
        # About block with "мать ребенка" role label and status line.
        self.assertIn("about = {", block)
        self.assertIn("<strong>МК Горюхино 1800:</strong> мать ребенка", block)
        self.assertIn("Титул/звание: крестьянка", block)
        # Death stub: range="after" at the child's birth date.
        self.assertIn("death = {", block)
        self.assertIn('range = "after"', block)
        self.assertIn("year  = 1800", block)
        self.assertIn("month = 3", block)
        self.assertIn("day   = 10", block)

    def test_father_profile_has_current_residence_from_person_residence(self):
        records = birth_records(
            "TestArchive", "1", "1", "1", "Горюхино", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров", residence="Собакевичево")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        # Father lives in Собакевичево — emitted as current_residence.
        self.assertIn("current_residence = {", output)
        self.assertIn("село Собакевичево", output)

    def test_child_profile_includes_configured_projects(self):
        records = birth_records(
            "TestArchive", "1", "1", "1", "Горюхино", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )

        projects = ["data.geni_project.automatic_upload.id", "data.geni_project.gorjuhino.id"]
        gen = TerraformGenerator(village_dir=None, projects=projects)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        self.assertIn(
            "projects = [data.geni_project.automatic_upload.id, data.geni_project.gorjuhino.id]",
            output,
        )

    def test_family_union_res_name_uses_legacy_father_record_year_format(self):
        """Legacy generate_config.py builds the family union res_name as
        `{father_first}_{father_middle}_{father_last}__{record}_{year}` run
        through generate_res_name — gives e.g. `ermil_vlasovich__3_1754`."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *birth_month(
                Month.APRIL,
                birth(3, Gender.MALE, 16, None,
                      child=person("Фаддей"),
                      father=person("Ермил", "Власов")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        self.assertIn('resource "geni_union" "ermil_vlasovich__3_1754"', output)
        self.assertNotIn("_1754_04_16_faddej_ilich_mk_births_3_child_family", output)

    def test_births_emitted_in_chronological_order(self):
        """The translator sorts records chronologically before emission, so
        a DSL that declares June records before March records (e.g. a
        book-page-ordered file) still produces output with March first.
        Uses 1820 which is not in SORT_OVERRIDE (so the default
        chronological sort applies)."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            # June records declared FIRST in the DSL …
            *birth_month(
                Month.JUNE,
                birth(10, Gender.MALE, 5, 6,
                      child=person("Алексей"),
                      father=person("Петр", "Иванов")),
                birth(11, Gender.FEMALE, 7, 8,
                      child=person("Мария"),
                      father=person("Иван", "Петров")),
            ),
            # … then March records.
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Иванов")),
                birth(2, Gender.FEMALE, 12, 13,
                      child=person("Анна"),
                      father=person("Иван", "Петров")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1820_birth.tf")

        pos_march_rec1 = output.find("_1820_03_10_ioann_petrovich_mk_births_1_child")
        pos_june_rec10 = output.find("_1820_06_05_aleksij_petrovich_mk_births_10_child")
        self.assertGreater(pos_march_rec1, -1, "March record 1 not emitted")
        self.assertGreater(pos_june_rec10, -1, "June record 10 not emitted")
        self.assertLess(pos_march_rec1, pos_june_rec10,
                        "March must be emitted before June")

    def test_same_day_male_before_female_in_chronological_sort(self):
        """Within a same-day tie the male record sorts before the female —
        matches the legacy CSV convention where same-day male/female pairs
        (twins or coincidental) appear male-first. Uses 1820 which is
        not in SORT_OVERRIDE (chronological sort applies)."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *birth_month(
                Month.JANUARY,
                # Female declared FIRST — sort must flip them.
                birth(2, Gender.FEMALE, 20, 21,
                      child=person("Татьяна"),
                      father=person("Павел", "Иванов")),
                birth(2, Gender.MALE, 20, 21,
                      child=person("Максим"),
                      father=person("Павел", "Иванов")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1820_birth.tf")

        pos_male = output.find("_1820_01_20_maksim_pavlovich_mk_births_2_child")
        pos_female = output.find("_1820_01_20_tatiana_pavlovna_mk_births_2_child")
        self.assertGreater(pos_male, -1)
        self.assertGreater(pos_female, -1)
        self.assertLess(pos_male, pos_female,
                        "male same-day sibling must sort before female")

    def test_year_rollover_records_sort_before_same_year_start(self):
        """A December-of-previous-year record (e.g. Dec-1824 christened in
        a 1825 metric book with explicit year=1824) must sort BEFORE the
        new-year entries whose year defaults to records.year=1825.

        Uses year=1825 which is NOT in SORT_OVERRIDE, so chronological sort
        applies. Years with (year, "birth")="dsl" in SORT_OVERRIDE preserve
        declaration order instead and do not guarantee rollover ordering."""
        rollover = birth(1, Gender.MALE, 28, 5,
                         child=person("Феоктист"),
                         father=person("Тимофей", "Леонтьев"),
                         b_month=Month.DECEMBER,
                         year=1824)
        new_year = birth(2, Gender.MALE, 1, 2,
                         child=person("Иван"),
                         father=person("Петр", "Иванов"),
                         b_month=Month.JANUARY)
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1825,
            new_year,    # declared first — sort must pull rollover above
            rollover,
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1825_birth.tf")

        pos_1824 = output.find("_1824_12_28_feoktist_timofeevich_mk_births_1_child")
        pos_1825 = output.find("_1825_01_01_ioann_petrovich_mk_births_2_child")
        self.assertGreater(pos_1824, -1, "1824 rollover record not emitted")
        self.assertGreater(pos_1825, -1, "1825 new-year record not emitted")
        self.assertLess(pos_1824, pos_1825,
                        "1824 rollover must be emitted before 1825 start")

    def test_1799_birth_preserves_dsl_december_first_ordering(self):
        """Legacy 1799 Горюхино birth output leads with December rows
        (end-of-ecclesiastical-year pages in the book) before January.
        SORT_OVERRIDE[(1799, "birth")] == "dsl" preserves that
        declaration order through the stable sort. Without the override
        the chronological sort would emit January first."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1799,
            # December declared first (matches the 1799 CSV's page order)…
            *birth_month(
                Month.DECEMBER,
                birth(2, Gender.MALE, 9, 13,
                      child=person("Мирон"),
                      father=person("Назар", "Николаев")),
            ),
            # … then January (chronologically earlier).
            *birth_month(
                Month.JANUARY,
                birth(1, Gender.FEMALE, 10, 12,
                      child=person("Мария"),
                      father=person("Иван", "Петров")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1799_birth.tf")

        pos_dec = output.find("_1799_12_09_miron_nazarovich_mk_births_2_child")
        pos_jan = output.find("_1799_01_10_marija_ivanovna_mk_births_1_child")
        self.assertGreater(pos_dec, -1, "December record not emitted")
        self.assertGreater(pos_jan, -1, "January record not emitted")
        self.assertLess(pos_dec, pos_jan,
                        "1799 must preserve DSL December-first order")

    def test_sort_override_registers_known_dsl_years(self):
        """The years where legacy preserves CSV row order (not strictly
        chronological) are registered in SORT_OVERRIDE with mode 'dsl'.
        The list grew as per-year audits found non-chronological sources;
        guard against accidental removal."""
        from verso.ru.targets.geni.translator import SORT_OVERRIDE
        dsl_years = {
            year for (year, rec_type), mode in SORT_OVERRIDE.items()
            if rec_type == "birth" and mode == "dsl"
        }
        # All years empirically validated to benefit from 'dsl' sort.
        for year in (1784, 1794, 1799, 1800, 1803, 1804, 1805, 1807,
                     1815, 1824):
            self.assertIn(year, dsl_years,
                          f"SORT_OVERRIDE[({year}, 'birth')] must be 'dsl'")

    def test_1803_birth_preserves_dsl_declaration_order(self):
        """Legacy 1803 birth output mirrors the source CSV's row order,
        which the DSL file reproduces as declaration order. Within e.g.
        February the same-gender records appear in record_num order
        irrespective of day. SORT_OVERRIDE[(1803, "birth")] == "dsl" opts
        the 1803 birth sort out of chronological re-ordering so stable
        sort preserves the DSL order."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1803,
            # Two February female records: rec#4 on feb-24 declared FIRST,
            # rec#5 on feb-12 SECOND. Chronological sort would invert them
            # (day 12 < 24); DSL-order preserves declaration order.
            *birth_month(
                Month.FEBRUARY,
                birth(4, Gender.FEMALE, 24, 5,
                      child=person("Мария"),
                      father=person("Иван", "Петров")),
                birth(5, Gender.FEMALE, 12, 14,
                      child=person("Ирина"),
                      father=person("Дмитрий", "Петров")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1803_birth.tf")

        pos_rec2 = output.find("_1803_02_24_marija_ivanovna_mk_births_4_child")
        pos_rec3 = output.find("_1803_02_12_irina_dmitrievna_mk_births_5_child")
        self.assertGreater(pos_rec2, -1, "record 2 not emitted")
        self.assertGreater(pos_rec3, -1, "record 3 not emitted")
        self.assertLess(pos_rec2, pos_rec3,
                        "1803 birth must preserve DSL declaration order")

    def test_multiple_births_in_same_year_share_one_output_file(self):
        records = birth_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
                birth(2, Gender.FEMALE, 12, 13,
                      child=person("Мария"),
                      father=person("Алексей", "Кузьмин")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        self.assertIn("mk_births_1_child", output)
        self.assertIn("mk_births_2_child", output)
        # no leakage to a second file
        self.assertEqual(gen.get_output("mk_1800_death.tf"), "")

    def test_birth_does_not_emit_clergy_profiles(self):
        """Clergy (priest/deacon/dyachok/sexton) carried on a birth record
        must NOT materialize as geni_profile resources — the legacy
        generate_config.py pipeline emits no clergy profiles anywhere, so
        we suppress them too for byte-parity."""
        records = birth_records(
            "TestArchive", "1", "1", "1", "Горюхино", "Никольская",
            1754,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 22, None,
                      child=person("Иван"),
                      father=person("Тимофей", "Петров"),
                      priest=person("Василий", "Петров"),
                      deacon=person("Иван", "Герасимов")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1754_birth.tf")

        self.assertNotIn("_priest", output)
        self.assertNotIn("_deacon", output)
        self.assertNotIn("_dyachok", output)
        self.assertNotIn("_sexton", output)

    def test_aux_godparent_union_skipped_when_no_consolidation(self):
        """Legacy only emits the aux `god_parent_rel` union when at least
        one participant is on the consolidation list. Without any
        consolidation config, no aux `_and_<godparent>` union should land
        in either the per-year file or `consolidated_unions.tf` — only
        the primary family union (father+child) stays."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      mother=person("Марья", "Иванова"),
                      god_parent1=person("Федор", "Кузьмин"),
                      god_parent2=person("Анна", "Павлова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        gen.finalize()
        year_file = gen.get_output("mk_1800_birth.tf")
        cu = gen.get_output("consolidated_unions.tf")

        import re as _re
        union_names = _re.findall(r'resource "geni_union" "([^"]+)"', year_file)
        # Only the family union (father+mother+child) should appear.
        self.assertEqual(len(union_names), 1,
                         f"expected only the family union; got {union_names}")
        self.assertNotIn("_and_feodor_kuzmich_", year_file)
        self.assertNotIn("anna_pavlovna__", year_file)  # female-aux shape
        # Consolidated file should be empty (no profile consolidated).
        self.assertNotIn('resource "geni_union"', cu)

    def test_godparent_union_skipped_when_matching_parent_missing(self):
        """A male godparent needs a father to pair with; a female godparent
        needs a mother. If the matching parent slot is empty, the godparent
        profile is still emitted but no auxiliary union is — we don't invent
        partners from thin air."""
        # Male godparent present, but father is None → no godparent union.
        # Mother's presence doesn't matter here because the male godparent
        # would anchor to the father.
        records = birth_records(
            "TestArchive", "1", "1", "1", "Горюхино", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      mother=person("Марья", "Иванова"),
                      god_parent1=person("Федор", "Кузьмин")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        # Godparent profile is still emitted.
        self.assertIn("mk_births_1_god_parent_1", output)
        # Exactly one union: mother + child (the family union). No auxiliary
        # godparent-parent union.
        self.assertEqual(
            output.count('resource "geni_union"'), 1,
            f"expected only the family union; output:\n{output}",
        )

    def test_birth_emits_relative_profiles(self):
        records = birth_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      relatives=[
                          Relative(person("Анна", "Иванова"),
                                   Relationship.MOTHER),
                      ]),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        self.assertIn("mk_births_1_rel_1", output)
        self.assertIn("_1800_03_10_anna_ivanovna_mk_births_1_rel_1", output)

    def test_birth_relative_role_uses_rel_prefix_not_relative(self):
        """Legacy `Горюхино/generate_config.py:496-506` uses `role='rel_1'`
        for birth relatives; `profile_move_list` is keyed on `_rel_N_` too.
        Translator had been emitting `_relative_N_`, which never matched the
        move_list, so those relatives were never consolidated."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      relatives=[
                          Relative(person("Анна", "Иванова"),
                                   Relationship.MOTHER),
                          Relative(person("Мария", "Иванова"),
                                   Relationship.DAUGHTER),
                      ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        self.assertIn("_mk_births_1_rel_1", output)
        self.assertIn("_mk_births_1_rel_2", output)
        self.assertNotIn("_mk_births_1_relative_1", output)
        self.assertNotIn("_mk_births_1_relative_2", output)

    def test_k_day_less_than_b_day_advances_k_month_to_next(self):
        """Auto-detect cross-month christening: inside a
        `birth_month(Month.X, ...)` grouping, when k_day < b_day the
        christening spilled into month X+1 (e.g. born 25 Jan, baptized 1
        Feb). Advance k_month accordingly; previously the DSL required
        explicit k_month= or the baptism event used the birth month."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *birth_month(
                Month.JANUARY,
                birth(1, Gender.FEMALE, 25, 1,
                      child=person("Дарья"),
                      father=person("Иван", "Иванов")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1820_birth.tf")
        # Baptism date 1.2.1820 — month advanced from JANUARY (1) to
        # FEBRUARY (2) because k_day (1) < b_day (25).
        self.assertIn("Дата крещения: 1.2.1820", output)
        self.assertNotIn("Дата крещения: 1.1.1820", output)

    def test_k_day_less_than_b_day_in_december_rolls_k_year(self):
        """December cross-month rollover also advances k_year when
        k_month → January and the caller uses `birth_month_year` (which
        passes `year` alongside `month`). With just `birth_month`,
        year context is lost so only the month advance fires and the
        caller has to set k_year manually."""
        from verso.ru.dsl.records.births import birth_month_year
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1809,
            *birth_month_year(
                Month.DECEMBER, 1809,
                birth(3, Gender.MALE, 26, 2,
                      child=person("Прохор"),
                      father=person("Тимофей", "Иванов")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        # k_year auto-advances to 1810 → record is emitted in the
        # christening-year file.
        output = gen.get_output("mk_1810_birth.tf")
        self.assertIn("Дата крещения: 2.1.1810", output)
        self.assertIn("Дата рождения: 26.12.1809", output)

    def test_anaev_project_added_via_expanded_location_county(self):
        """Legacy adds `data.geni_project.neelovo.id` when the profile's
        residence is anywhere inside its rule's area — the substring
        check runs against the expanded location block (city + county +
        state), not just the short key. Ротозеево's short name doesn't
        literally contain 'Захудалов' but its county does."""
        records = birth_records(
            "A", "1", "1", "1", "Неелово", "Покровская",
            1837,
            *birth_month(
                Month.FEBRUARY,
                birth(1, Gender.MALE, 4, 6,
                      child=person("Иван"),
                      father=person("Матвей", "Лазарев",
                                    residence="Ротозеево")),
            ),
        )
        gen = TerraformGenerator(
            village_dir=None,
            projects=[
                "data.geni_project.automatic_upload.id",
                "data.geni_project.gorjuhino.id",
            ],
            extra_project_rules={"Захудалов": "data.geni_project.neelovo.id"},
        )
        gen.add_birth_records(records)
        output = gen.get_output("mk_1837_birth.tf")
        # Father's profile lives in Ротозеево whose county is
        # "Захудаловский уезд" — substring rule triggers.
        # Neelovo project appears in the profile's `projects = [...]` line.
        self.assertIn("data.geni_project.neelovo.id", output)
        # Control case: the projects rule must NOT fire for a profile
        # residing squarely in Ротозейский уезд (contains no 'Захудалов'
        # substring) — make sure the generator doesn't over-apply.
        records_control = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1837,
            *birth_month(
                Month.FEBRUARY,
                birth(2, Gender.MALE, 4, 6,
                      child=person("Петр"),
                      father=person("Иван", "Сидоров",
                                    residence="Горюхино")),
            ),
        )
        gen2 = TerraformGenerator(
            village_dir=None,
            projects=[
                "data.geni_project.automatic_upload.id",
                "data.geni_project.gorjuhino.id",
            ],
            extra_project_rules={"Захудалов": "data.geni_project.neelovo.id"},
        )
        gen2.add_birth_records(records_control)
        out_control = gen2.get_output("mk_1837_birth.tf")
        self.assertNotIn("data.geni_project.neelovo.id", out_control)

    def test_projects_list_emitted_in_alphabetical_order(self):
        """Regression: `_projects_for_location` returns the union of base
        projects + matching extras alphabetically sorted, matching the
        legacy convention where `projects = [automatic_upload, gorjuhino,
        neelovo]`. Pre-fix the helper returned base+extras (insertion
        order), so a Захудалов-substring match produced
        `[gorjuhino, automatic_upload, neelovo]` from these base projects,
        which drifted from the consolidator's `sorted(set(...))` output."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1837,
            *birth_month(
                Month.FEBRUARY,
                birth(1, Gender.MALE, 4, 6,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров",
                                    residence="Ротозеево")),
            ),
        )
        gen = TerraformGenerator(
            village_dir=None,
            projects=[
                "data.geni_project.gorjuhino.id",
                "data.geni_project.automatic_upload.id",
            ],
            extra_project_rules={"Захудалов": "data.geni_project.neelovo.id"},
        )
        gen.add_birth_records(records)
        output = gen.get_output("mk_1837_birth.tf")

        # Expect the alphabetical order.
        self.assertIn(
            "projects = [data.geni_project.automatic_upload.id, "
            "data.geni_project.gorjuhino.id, "
            "data.geni_project.neelovo.id]",
            output,
        )
        # Insertion-order shape must NOT appear.
        self.assertNotIn(
            "projects = [data.geni_project.gorjuhino.id, "
            "data.geni_project.automatic_upload.id, "
            "data.geni_project.neelovo.id]",
            output,
        )

    def test_projects_list_sorted_when_no_extras_match(self):
        """Same alphabetical sort applies even when no extra-project
        rule fires — base projects come back in sorted order so the
        emit shape is consistent regardless of input ordering."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *birth_month(
                Month.JANUARY,
                birth(1, Gender.MALE, 5, 6,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров",
                                    residence="Горюхино")),
            ),
        )
        # Pass projects in REVERSE alphabetical order to the constructor
        # to confirm the output reorders them.
        gen = TerraformGenerator(
            village_dir=None,
            projects=[
                "data.geni_project.gorjuhino.id",
                "data.geni_project.automatic_upload.id",
            ],
        )
        gen.add_birth_records(records)
        output = gen.get_output("mk_1810_birth.tf")
        self.assertIn(
            "projects = [data.geni_project.automatic_upload.id, "
            "data.geni_project.gorjuhino.id]",
            output,
        )

    def test_birth_child_about_emits_mother_title_when_no_father(self):
        """Illegitimate birth (mother only, no father): child's about
        block carries `Титул/звание матери: {mother.status}` instead of
        the `Титул/звание отца:` line. Mirrors legacy's conditional at
        generate_config.py:314-315."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *birth_month(
                Month.JANUARY,
                birth(1, Gender.FEMALE, 20, 22,
                      child=person("Агафья"),
                      mother=person("Парасковья", "Нестерова",
                                    status="ясачная солдатская жена")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1810_birth.tf")
        # child's about block (first profile emitted) carries mother title.
        child_block = output.split('resource "geni_profile"')[1]
        self.assertIn("Титул/звание матери: ясачная солдатская жена",
                      child_block)
        self.assertNotIn("Титул/звание отца:", child_block)

    def test_birth_child_about_prefers_father_title_when_both_present(self):
        """When both father and mother have status set, the child's about
        block uses Титул/звание отца (not матери). Mother's title is only
        emitted when father has no title."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *birth_month(
                Month.JANUARY,
                birth(1, Gender.MALE, 5, 6,
                      child=person("Иван"),
                      father=person("Петр", "Иванов",
                                    status="ясачный крестьянин"),
                      mother=person("Мария", "Сидорова",
                                    status="ясачная крестьянка")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1810_birth.tf")
        child_block = output.split('resource "geni_profile"')[1]
        self.assertIn("Титул/звание отца: ясачный крестьянин", child_block)
        self.assertNotIn("Титул/звание матери:", child_block)

    def test_family_union_res_name_mother_only_has_single_underscores(self):
        """When only the mother is present (illegitimate birth), the
        legacy res_name collapses empty father-slot spaces via one-pass
        `.replace('  ', ' ')` → `and_{mother}_{rec}_{year}` with single
        underscores between tokens. The translator once produced
        triple/double underscores."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *birth_month(
                Month.FEBRUARY,
                birth(8, Gender.FEMALE, 9, 11,
                      child=person("Агафья"),
                      mother=person("Васса", "Тихонова",
                                    status="солдатка")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn(
            'resource "geni_union" "and_vassa_tihonovna_8_1838"',
            output,
        )
        # Triple-underscore would come from naive " ".join without slot
        # collapse; ensure it doesn't appear.
        self.assertNotIn("and_vassa_tihonovna___8_1838", output)
        self.assertNotIn("and_vassa_tihonovna__8_1838", output)

    def test_godparent_death_after_uses_k_year_for_cross_year(self):
        """Godparents are seen alive at the CHRISTENING. For a Dec birth /
        Jan christening record (k_year = next year), the godparent's
        `death = { range = "after", year = ... }` floor uses k_year, not
        the birth year. Legacy's godparent year matches the christening
        date."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1809,
            *birth_month(
                Month.DECEMBER,
                birth(3, Gender.FEMALE, 27, 2, k_month=Month.JANUARY,
                      k_year=1810,
                      child=person("Ульяна"),
                      father=person("Лазарь", "Иванов"),
                      god_parent1=person("Анфиса", "Климова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1810_birth.tf")
        # Isolate godparent profile by splitting on '# geni_profile' markers.
        gp_section = [
            s for s in output.split("# geni_profile.")
            if "_god_parent_1" in s.split("\n", 1)[0]
        ]
        self.assertEqual(len(gp_section), 1,
                         f"expected exactly one godparent profile:\n{output}")
        gp_block = gp_section[0]
        # death = { range="after", ..., year=1810 } — christening year.
        death_m = re.search(
            r'death = \{\s*date = \{([^}]+)\}', gp_block, re.DOTALL,
        )
        self.assertIsNotNone(death_m)
        death_date = re.sub(r"\s+", " ", death_m.group(1))
        self.assertIn('range = "after"', death_date)
        self.assertIn("year = 1810", death_date)
        self.assertNotIn("year = 1809", death_date)

    def test_priest_appears_in_names_in_mk_for_1810_only(self):
        """Legacy's 1810 Горюхино birth CSV uniquely populated the
        clergy column in its 'Имена в МК' rendering. Other years left
        the priest out. Gate on records.year == 1810 so the priest
        lands in 'Имена в МК:' for 1810 records only."""
        def _make_records(year):
            return birth_records(
                "A", "1", "1", "1", "Горюхино", "N",
                year,
                *birth_month(
                    Month.FEBRUARY,
                    birth(1, Gender.MALE, 5, 6,
                          child=person("Иван"),
                          father=person("Петр", "Иванов"),
                          god_parent1=person("Степан", "Кузьмин"),
                          priest=person("Александр", "Прохоров")),
                ),
            )

        # 1810: priest appears in Имена в МК.
        gen_1810 = TerraformGenerator(village_dir=None)
        gen_1810.add_birth_records(_make_records(1810))
        out_1810 = gen_1810.get_output("mk_1810_birth.tf")
        self.assertIn(
            ">Имена в МК: Иван; Петр Иванов; Степан Кузьмин; Александр Прохоров",
            out_1810,
        )

        # 1811 (or any non-1810 year): priest omitted.
        gen_1811 = TerraformGenerator(village_dir=None)
        gen_1811.add_birth_records(_make_records(1811))
        out_1811 = gen_1811.get_output("mk_1811_birth.tf")
        self.assertIn(
            ">Имена в МК: Иван; Петр Иванов; Степан Кузьмин",
            out_1811,
        )
        self.assertNotIn(
            ">Имена в МК: Иван; Петр Иванов; Степан Кузьмин; Александр Прохоров",
            out_1811,
        )

    def test_birth_with_third_and_fourth_godparents_emits_profiles(self):
        """When the source MK had 3-4 godparents (legacy `Восприемник 3`
        / `Восприемник 4` columns), the translator emits profiles for
        each, mirroring `god_parent1` / `god_parent2`. Roles must be
        `god_parent_3` / `god_parent_4`."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N", 1838,
            *[birth(1, Gender.MALE, 22, None,
                    child=person("Иван"),
                    father=person("Тимофей", "Андреев",
                                  status="ясачный крестьянин"),
                    mother=person("Пелагея", "Герасимова"),
                    god_parent1=person("Прохор", "Герасимов",
                                       status="ясачный крестьянин"),
                    god_parent2=person("Ольга", "Андреева",
                                       status="ясачная крестьянка"),
                    god_parent3=person("Петр", "Сидоров",
                                       status="ясачный крестьянин"),
                    god_parent4=person("Мария", "Иванова",
                                       status="ясачная крестьянка"),
                    b_month=Month.MARCH)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn("god_parent_3", output)
        self.assertIn("god_parent_4", output)
        # All four godparents named (the base's patronymic for "Сидоров"
        # is "Сидорович").
        self.assertIn("Прохор", output)
        self.assertIn("Петр Сидорович", output)
        self.assertIn("Мария Ивановна", output)

    def test_birth_with_three_four_godparents_lists_all_in_text_body(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N", 1838,
            *[birth(1, Gender.MALE, 22, None,
                    child=person("Иван"),
                    father=person("Тимофей", "Андреев",
                                  status="ясачный крестьянин"),
                    mother=person("Пелагея", "Герасимова"),
                    god_parent1=person("Прохор", "Герасимов",
                                       status="ясачный крестьянин"),
                    god_parent2=person("Ольга", "Андреева",
                                       status="ясачная крестьянка"),
                    god_parent3=person("Петр", "Сидоров",
                                       status="ясачный крестьянин"),
                    god_parent4=person("Мария", "Иванова",
                                       status="ясачная крестьянка"),
                    b_month=Month.MARCH)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")
        self.assertIn(
            "Воспреемник 3: ясачный крестьянин Петр Сидорович", output,
        )
        self.assertIn(
            "Воспреемник 4: ясачная крестьянка Мария Ивановна", output,
        )

    def test_female_child_inherits_mother_surname_as_birth_last_name(self):
        """Daughters whose surname is inherited (not in the book) route the
        inherited surname to `birth_last_name` (Geni maiden_name), not
        `last_name` — a newborn girl has no current/married surname."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1838,
            *birth_month(
                Month.JULY,
                birth(24, Gender.FEMALE, 13, 14,
                      child=person("Таисия", comment="незаконнорожденная"),
                      mother=person("Аграфена", "Климова",
                                    last_name_orig="Свистунова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")

        import re as _re
        block = _re.search(
            r'resource "geni_profile" "_1838_07_13_taisija_svistunova_mk_births_24_child"\s*{(.+?)\n}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(block, f"no Таисия resource in:\n{output}")
        body = block.group(1)
        self.assertIn('birth_last_name = "Свистунова"', body)
        self.assertIn('birth_last_name = "Svistunova"', body)
        # No `last_name = "..."` line — Geni would render that as her
        # current/married surname, which she does not have.
        self.assertNotRegex(body, r'\blast_name\s+=\s+"[^"]')

    def test_female_child_inherits_father_surname_feminized_as_birth_last_name(self):
        """When mother has no surname but father does, the inherited surname
        feminizes and routes to birth_last_name for daughters."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *birth_month(
                Month.JULY,
                birth(24, Gender.FEMALE, 13, 14,
                      child=person("Евфимия"),
                      father=person("Гордей", "Антипов",
                                    last_name_orig="Кувшинников"),
                      mother=person("Анфиса", "Гаврилова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")

        import re as _re
        block = _re.search(
            r'resource "geni_profile" "_1838_07_13_evfimija_gordeevna_kuvshinnikova_mk_births_24_child"\s*{(.+?)\n}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(block, f"no Евфимия resource in:\n{output}")
        body = block.group(1)
        self.assertIn('birth_last_name = "Кувшинникова"', body)
        self.assertNotRegex(body, r'\blast_name\s+=\s+"[^"]')

    def test_male_child_inherits_father_surname_as_last_name(self):
        """Sons inherit the surname as `last_name` (their birth and adult
        surname); birth_last_name stays empty."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *birth_month(
                Month.JULY,
                birth(24, Gender.MALE, 13, 14,
                      child=person("Петр"),
                      father=person("Филипп", "Евдокимов",
                                    last_name_orig="Егозин")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")

        import re as _re
        block = _re.search(
            r'resource "geni_profile" "_1838_07_13_petr_filippovich_egozin_mk_births_24_child"\s*{(.+?)\n}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(block, f"no Петр resource in:\n{output}")
        body = block.group(1)
        self.assertRegex(body, r'\blast_name\s+=\s+"Егозин"')
        # birth_last_name should be absent for a son.
        self.assertNotIn('birth_last_name', body)

    def test_mother_explicit_birth_last_name_emits_maiden_and_keeps_married(self):
        """An adult woman (mother) given an explicit maiden surname via
        `person(birth_last_name_modern_orth=...)` carries it as the profile's
        `birth_last_name` while retaining her married/feminized `last_name` —
        the per-record source DSL can thus hold the maiden surname directly,
        instead of pinning it in the consolidation override layer."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1907,
            *birth_month(
                Month.MARCH,
                birth(19, Gender.FEMALE, 14, 15,
                      child=person("Ольга"),
                      father=person("Яков", "Тимофеев",
                                    last_name_orig="Сундукин"),
                      mother=person("Лидия", "Никитина",
                                    birth_last_name_modern_orth="Кривоглазова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1907_birth.tf")

        block = _extract_resource_block(
            output, "_1907_03_14_lidija_nikitichna_sundukina_mk_births_19_mother",
        )
        self.assertIsNotNone(block, f"no Лидия mother resource in:\n{output}")
        # Married (feminized-from-father) surname is retained...
        self.assertRegex(block, r'last_name\s+=\s+"Сундукина"')
        self.assertRegex(block, r'last_name\s+=\s+"Sundukina"')
        # ...alongside the explicit maiden surname.
        self.assertRegex(block, r'birth_last_name\s+=\s+"Кривоглазова"')
        self.assertRegex(block, r'birth_last_name\s+=\s+"Krivoglazova"')

    def test_mother_birth_last_name_does_not_change_res_name(self):
        """Adding a maiden surname to an adult woman must be res_name-neutral
        (the res_name suffix derives from the married surname for non-child
        roles), so migrating it out of `additional_info` causes no Terraform
        address churn / moved blocks."""
        def gen_output(with_maiden):
            mother_kwargs = {"birth_last_name_modern_orth": "Кривоглазова"} if with_maiden else {}
            records = birth_records(
                "A", "1", "1", "1", "Горюхино", "N",
                1907,
                *birth_month(
                    Month.MARCH,
                    birth(19, Gender.FEMALE, 14, 15,
                          child=person("Ольга"),
                          father=person("Яков", "Тимофеев",
                                        last_name_orig="Сундукин"),
                          mother=person("Лидия", "Никитина", **mother_kwargs)),
                ),
            )
            gen = TerraformGenerator(village_dir=None)
            gen.add_birth_records(records)
            return gen.get_output("mk_1907_birth.tf")

        import re as _re

        def addrs(out: str) -> set[str]:
            return set(_re.findall(r'resource "geni_profile" "([^"]+)"', out))

        self.assertEqual(addrs(gen_output(True)), addrs(gen_output(False)))

    def test_bride_with_equal_last_name_and_birth_last_name_suppresses_last_name(self):
        """If a bride's married surname (last_name) ends up equal to her
        maiden (birth_last_name) — e.g. she married someone with the same
        family surname — the redundant `last_name` is suppressed so Geni
        doesn't double-render the maiden as a "current" surname."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         # Same-family-name marriage: groom's surname
                         # would feminize to "Сидорова", matching the
                         # bride's maiden surname.
                         groom=person("Петр", "Иванов",
                                      last_name_orig="Сидоров"),
                         bride=person("Мария", "Петрова",
                                      last_name_orig="Сидорова"),
                         bride_takes_groom_surname=True),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        import re as _re
        block = _re.search(
            r'resource "geni_profile" "_1820_01_20_marija_petrovna_mk_marriages_1_bride"\s*{(.+?)\n}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(block, f"no bride resource in:\n{output}")
        body = block.group(1)
        self.assertIn('birth_last_name = "Сидорова"', body)
        # last_name suppressed since it would equal birth_last_name.
        self.assertNotRegex(body, r'\blast_name\s+=\s+"[^"]')


class TestConsolidation(unittest.TestCase):
    def _records(self):
        return birth_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )

    def test_profile_in_move_list_diverts_to_consolidated_bucket(self):
        records = self._records()
        # Pre-compute child's res_name so we can target it in the move list.
        b = records.records[0]
        child_res = generate_res_name_2(
            year=1800, month=3, day=10,
            first_name=b.child.get_canonical_name(),
            middle_name=b.derive_child_patronymic() or "",
            last_name="",
            document_name="mk_births", role="child", record_number=1,
        )
        consolidation = Consolidation(
            profile_move_list={child_res: "ioann_petrovich"},
        )

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()

        year_file = gen.get_output("mk_1800_birth.tf")
        consolidated = gen.get_output("consolidated_profiles_1.tf")

        # Child's individual per-record profile should NOT appear in the year file.
        self.assertNotIn(f'resource "geni_profile" "{child_res}"', year_file)
        # It should appear consolidated, under the aliased name.
        self.assertIn('resource "geni_profile" "ioann_petrovich"', consolidated)

    def test_consolidated_father_skips_per_record_family_union(self):
        """When the father's per-record profile is consolidated (his res_name is
        in profile_move_list), the legacy pipeline does NOT emit a per-record
        `{child}_family` union — the family union lives in
        consolidated_unions.tf instead. Skip it in the per-year file."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )

        # Read the actual generated father res_name by running once without
        # consolidation, then re-run with consolidation enabled for that name.
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1800_birth.tf")
        match = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_1_father)"',
            probe_out,
        )
        self.assertIsNotNone(match, f"could not find father profile in probe output:\n{probe_out}")
        father_res = match.group(1)
        consolidation = Consolidation(
            profile_move_list={father_res: "petr_consolidated"},
        )

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        self.assertNotIn("_family", output,
                         f"per-record family union should be skipped; output:\n{output}")

    def test_godparent_union_skipped_when_parent_consolidated(self):
        """When the parent anchoring a godparent-parent auxiliary union is
        consolidated (its per-record profile res_name is in profile_move_list),
        the legacy pipeline routes that union into consolidated_unions.tf and
        omits it from the per-year file. Mirror that behavior."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      god_parent1=person("Федор", "Кузьмин")),
            ),
        )

        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1800_birth.tf")
        match = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_1_father)"',
            probe_out,
        )
        self.assertIsNotNone(match, f"could not find father profile; output:\n{probe_out}")
        father_res = match.group(1)
        consolidation = Consolidation(
            profile_move_list={father_res: "petr_consolidated"},
        )

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        year_file = gen.get_output("mk_1800_birth.tf")

        # Male godparent's union normally anchors to father. With father
        # consolidated, the auxiliary godparent-parent union must NOT be
        # emitted in the per-year file.
        from verso.ru.naming.transliteration import generate_res_name
        gp_union_name = generate_res_name("Петр Сидорович  and Федор Кузьмич  1 1800")
        self.assertNotIn(
            f'resource "geni_union" "{gp_union_name}"', year_file,
            f"godparent union should be skipped when parent is consolidated; output:\n{year_file}",
        )

    def test_godparent_union_skipped_when_godparent_consolidated(self):
        """Symmetric case: when the godparent itself is consolidated, the
        auxiliary godparent-parent union also goes to consolidated_unions.tf
        and is skipped in the per-year file."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      god_parent1=person("Федор", "Кузьмин")),
            ),
        )

        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1800_birth.tf")
        match = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_1_god_parent_1)"',
            probe_out,
        )
        self.assertIsNotNone(match, f"could not find godparent profile; output:\n{probe_out}")
        gp_res = match.group(1)
        consolidation = Consolidation(
            profile_move_list={gp_res: "feodor_consolidated"},
        )

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        year_file = gen.get_output("mk_1800_birth.tf")

        from verso.ru.naming.transliteration import generate_res_name
        gp_union_name = generate_res_name("Петр Сидорович  and Федор Кузьмич  1 1800")
        self.assertNotIn(
            f'resource "geni_union" "{gp_union_name}"', year_file,
            f"godparent union should be skipped when godparent is consolidated; output:\n{year_file}",
        )

    def test_consolidated_father_profile_has_death_after_birth_range(self):
        """Legacy emits death = { date = { range = "after"; circa = true;
        day/month/year = birth date } } on the consolidated father profile,
        signalling the father was alive at least until the child's birth."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.APRIL,
                birth(1, Gender.MALE, 5, 6,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )

        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1800_birth.tf")
        match = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_1_father)"',
            probe_out,
        )
        father_res = match.group(1)
        consolidation = Consolidation(profile_move_list={father_res: "petr_consolidated"})

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        consolidated_tf = gen.get_output("consolidated_profiles_1.tf")

        self.assertIn('resource "geni_profile" "petr_consolidated"', consolidated_tf)
        self.assertIn('death = {', consolidated_tf)
        self.assertIn('range = "after"', consolidated_tf)
        self.assertIn('circa = true', consolidated_tf)
        self.assertIn('day   = 5', consolidated_tf)
        self.assertIn('month = 4', consolidated_tf)
        self.assertIn('year  = 1800', consolidated_tf)

    def test_consolidated_father_has_parent_about_text(self):
        """Legacy consolidated father profile about:
            <strong>МК <village> <year>:</strong> отец ребенка
            Титул/звание: <status>
            Комментарий из МК:
            >Имена в МК: <names>
        """
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MAY,
                birth(1, Gender.FEMALE, 3, 4,
                      child=person("Мария"),
                      father=person("Илья", "Петров", status="крестьянин")),
            ),
        )

        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        match = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_1_father)"',
            probe.get_output("mk_1800_birth.tf"),
        )
        father_res = match.group(1)
        consolidation = Consolidation(profile_move_list={father_res: "ilya_petrov"})

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        consolidated_tf = gen.get_output("consolidated_profiles_1.tf")

        self.assertIn("<strong>МК Горюхино 1800:</strong> отец ребенка", consolidated_tf)
        self.assertIn("Титул/звание: крестьянин", consolidated_tf)
        self.assertIn(">Имена в МК: Мария; Илья Петров", consolidated_tf)

    def test_consolidated_profile_aggregates_across_multiple_records(self):
        """When the same father is consolidated across multiple birth records
        (e.g. children born in 1800 and 1810), the consolidated profile must
        aggregate:
          - `death.date.end_year` = max of the per-record "after" ranges
            (latest year father was known to be alive);
          - `about` text from both encounters separated by a blank line.
        Matches legacy `add_to_consolidated_profiles` semantics.
        """
        import re as _re

        records_1800 = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.APRIL,
                birth(1, Gender.MALE, 5, 6,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )
        records_1810 = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *birth_month(
                Month.MAY,
                birth(1, Gender.FEMALE, 7, 8,
                      child=person("Мария"),
                      father=person("Петр", "Сидоров")),
            ),
        )

        # Probe each year for the father's per-record res_name.
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records_1800)
        probe.add_birth_records(records_1810)
        father_pattern = (
            r'resource "geni_profile" "(_{year}_\d\d_\d\d_[^"]+_mk_births_1_father)"'
        )
        match_1800 = _re.search(
            father_pattern.format(year=1800),
            probe.get_output("mk_1800_birth.tf"),
        )
        match_1810 = _re.search(
            father_pattern.format(year=1810),
            probe.get_output("mk_1810_birth.tf"),
        )
        self.assertIsNotNone(match_1800)
        self.assertIsNotNone(match_1810)
        father_res_1800 = match_1800.group(1)
        father_res_1810 = match_1810.group(1)

        consolidation = Consolidation(profile_move_list={
            father_res_1800: "petr",
            father_res_1810: "petr",
        })
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records_1800)
        gen.add_birth_records(records_1810)
        gen.finalize()

        consolidated_tf = gen.get_output("consolidated_profiles_1.tf")

        # Exactly ONE consolidated profile (not two).
        self.assertEqual(
            consolidated_tf.count('resource "geni_profile" "petr"'), 1,
            f"expected one consolidated father profile; got:\n{consolidated_tf}",
        )
        # death.date.end_year must reflect the LATEST record (1810), not 1800.
        self.assertIn('year  = 1810', consolidated_tf)
        self.assertNotIn('year  = 1800', consolidated_tf)
        # About text should carry both record headers.
        self.assertIn("<strong>МК Горюхино 1800:</strong> отец ребенка", consolidated_tf)
        self.assertIn("<strong>МК Горюхино 1810:</strong> отец ребенка", consolidated_tf)

    def test_consolidated_profile_enriches_last_name_from_later_encounter(self):
        """When the first consolidated encounter has no `last_name` but a
        later one does (different DSL records for the same person can have
        the surname populated inconsistently), the consolidated profile
        carries the surname from whichever encounter supplied it."""
        import re as _re
        # 1800 record: father has NO last_name.
        r1 = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.APRIL,
                birth(1, Gender.MALE, 5, 6,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )
        # 1810 record: same person as father, NOW with last_name set.
        r2 = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *birth_month(
                Month.MAY,
                birth(1, Gender.FEMALE, 7, 8,
                      child=person("Мария"),
                      father=person("Петр", "Сидоров",
                                    last_name_modern_orth="Барашкин")),
            ),
        )
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(r1)
        probe.add_birth_records(r2)
        f1 = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_1_father)"',
            probe.get_output("mk_1800_birth.tf"),
        ).group(1)
        f2 = _re.search(
            r'resource "geni_profile" "(_1810_\d\d_\d\d_[^"]+_mk_births_1_father)"',
            probe.get_output("mk_1810_birth.tf"),
        ).group(1)
        consolidation = Consolidation(
            profile_move_list={f1: "petr", f2: "petr"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(r1)
        gen.add_birth_records(r2)
        gen.finalize()
        consolidated_tf = gen.get_output("consolidated_profiles_1.tf")

        self.assertIn('resource "geni_profile" "petr"', consolidated_tf)
        # last_name from the 1810 encounter must appear on the consolidated
        # profile even though 1800 was encountered first and had no surname.
        self.assertIn('last_name   = "Барашкин"', consolidated_tf)

    def test_missing_consolidation_emits_flat_profiles(self):
        records = self._records()

        gen = TerraformGenerator(village_dir=None)  # no consolidation arg
        gen.add_birth_records(records)
        gen.finalize()

        year_file = gen.get_output("mk_1800_birth.tf")
        self.assertIn('_1800_03_10_ioann_petrovich_mk_births_1_child', year_file)
        self.assertEqual(gen.get_output("consolidated_profiles_1.tf"), "")


class TestConsolidationPreferencesAndOverrides(unittest.TestCase):
    """profiles_to_consolidate['preference'] and ['override'] hints from
    legacy's generate_config_names.py. preference pins canonical
    first/middle/last name and turns diverging incoming values into
    nicknames; override unconditionally replaces the field."""

    def _setup_two_record_consolidation(self, *, first_name_variant,
                                          gender=Gender.FEMALE):
        """Build records where the child's first_name differs from the
        pinned canonical. Used to verify preference doesn't get overwritten
        by a later record's first_name."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1801,
            *birth_month(
                Month.JANUARY,
                birth(1, gender, 6, 12,
                      child=person(first_name_variant),
                      father=person("Мефодий", "Фролов")),
            ),
        )
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1801_birth.tf")
        m = _re.search(
            r'resource "geni_profile" "(_1801_\d\d_\d\d_[^"]+_mk_births_1_child)"',
            probe_out,
        )
        self.assertIsNotNone(m, f"child profile not found:\n{probe_out}")
        return records, m.group(1)

    def test_preference_pins_canonical_first_name_and_stores_variant(self):
        """profile_preferences[target] = {first_name='Домна',
        nicknames=['Домника']} pins 'Домна' as the consolidated first_name
        even if the incoming record's first_name is 'Домника', and emits
        the variant via the nicknames list."""
        records, child_res = self._setup_two_record_consolidation(
            first_name_variant="Домника",
        )
        consolidation = Consolidation(
            profile_move_list={child_res: "domna_mefodievna"},
            profile_preferences={
                "domna_mefodievna": {
                    "first_name": "Домна",
                    "nicknames": ["Домника"],
                },
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_profiles_1.tf")

        self.assertIn('resource "geni_profile" "domna_mefodievna"', output)
        self.assertIn('first_name  = "Домна"', output)
        self.assertIn('nicknames   = ["Домника"]', output)
        # Canonical wins — incoming "Домника" must NOT become first_name.
        self.assertNotIn('first_name  = "Домника"', output)

    def test_preference_nicknames_sorted_alphabetically(self):
        """Legacy sorts nicknames via sorted(list(set(...))). Given
        preference nicknames ['Sundukin', 'Prokof''evich'] we expect
        'Prokof''evich' to appear before 'Sundukin' in the output."""
        records, child_res = self._setup_two_record_consolidation(
            first_name_variant="Семен", gender=Gender.MALE,
        )
        consolidation = Consolidation(
            profile_move_list={child_res: "simeon_prokopievich_tjufjakin"},
            profile_preferences={
                "simeon_prokopievich_tjufjakin": {
                    "first_name": "Семен",
                    # Intentionally passed unsorted — output must sort.
                    "nicknames": ["Sundukin", "Prokof'evich"],
                },
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_profiles_1.tf")
        self.assertIn('nicknames   = ["Prokof\'evich", "Sundukin"]', output)
        self.assertNotIn('nicknames   = ["Sundukin", "Prokof\'evich"]', output)

    def test_lifecycle_ignore_changes_emitted_on_canonical(self):
        """profile_lifecycle_ignores[target] = ["projects"] emits a terraform
        lifecycle { ignore_changes = [projects] } block on the canonical —
        the escape hatch for co-author location-derived project drift, where
        the ForceNew replace can't delete the profile and an additional_info
        pin can't link it (access denied)."""
        records, child_res = self._setup_two_record_consolidation(
            first_name_variant="Татьяна",
        )
        consolidation = Consolidation(
            profile_move_list={child_res: "tatiana_pinned"},
            profile_lifecycle_ignores={"tatiana_pinned": ["projects"]},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_profiles_1.tf")
        self.assertIn("lifecycle {", output)
        self.assertIn("ignore_changes = [projects]", output)
        # only the hinted canonical carries the block
        self.assertEqual(output.count("lifecycle {"), 1)

    def test_override_replaces_middle_name_unconditionally(self):
        """profile_overrides[target] = GeniProfile(middle_name='Игнатьевна')
        replaces the consolidated profile's middle_name even when the
        merge-derived value was 'Игнатовна'."""
        from verso.core.targets.geni.profile import GeniProfile
        records, child_res = self._setup_two_record_consolidation(
            first_name_variant="Татьяна",
        )
        consolidation = Consolidation(
            profile_move_list={child_res: "tatiana_ignatievna"},
            profile_overrides={
                "tatiana_ignatievna": GeniProfile(
                    middle_name="Игнатьевна",
                ),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_profiles_1.tf")
        self.assertIn('middle_name = "Игнатьевна"', output)

    def test_override_replaces_current_residence(self):
        """GeniProfile override can also supply current_residence — the
        field replaces whatever the merge inherited from the source
        records (legacy uses this when the consolidated profile lives in
        a location different from any single-record residence)."""
        from verso.core.targets.geni.profile import GeniProfile
        from verso.core import places
        locations = places.current().bodies
        records, child_res = self._setup_two_record_consolidation(
            first_name_variant="Иван", gender=Gender.MALE,
        )
        override_residence = locations["Собакевичево"]
        consolidation = Consolidation(
            profile_move_list={child_res: "ioann_overridden"},
            profile_overrides={
                "ioann_overridden": GeniProfile(
                    current_residence=override_residence,
                ),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_profiles_1.tf")
        self.assertIn('"ioann_overridden"', output)
        # Override residence wins over per-record residence.
        self.assertIn('село Собакевичево', output)


class TestConsolidationAdditionalInfo(unittest.TestCase):
    """profiles_to_consolidate['additional_info'] is a list of GeniProfile
    objects carrying supplementary fields (last_name, birth_last_name,
    precise birth/death events) that legacy merges INTO the consolidated
    profile alongside the per-record entries. Translator reads these
    from Consolidation.profile_additional_info and applies them during
    finalize, using the same fill-in-if-missing semantics as per-record
    merges (overrides still win over both)."""

    def _setup(self, *, first_name="Татьяна", gender=Gender.FEMALE):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1801,
            *birth_month(
                Month.JANUARY,
                birth(1, gender, 6, 12,
                      child=person(first_name),
                      father=person("Иван", "Петров")),
            ),
        )
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1801_birth.tf")
        m = _re.search(
            r'resource "geni_profile" "(_1801_\d\d_\d\d_[^"]+_mk_births_1_child)"',
            probe_out,
        )
        self.assertIsNotNone(m)
        return records, m.group(1)

    def test_additional_info_fills_last_name_and_birth_last_name(self):
        from verso.core.targets.geni.profile import GeniProfile
        records, child_res = self._setup()
        consolidation = Consolidation(
            profile_move_list={child_res: "tatiana_ivanovna"},
            profile_additional_info={
                "tatiana_ivanovna": [
                    GeniProfile(
                        last_name="Тентетникова",
                        birth_last_name="Ежевикина",
                    ),
                ],
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        out = gen.get_output("consolidated_profiles_1.tf")
        self.assertRegex(out, r'last_name\s+=\s+"Тентетникова"')
        self.assertRegex(out, r'birth_last_name\s+=\s+"Ежевикина"')

    def test_additional_info_fills_precise_birth_event(self):
        from verso.core.targets.geni.profile import GeniProfile
        from verso.core.targets.geni.event import GeniEvent
        from verso.core.targets.geni.date import GeniDate
        records, child_res = self._setup()
        # Per-record birth (from the MK record) already carries day=6
        # month=1 year=1801. Additional info supplies an alternative
        # precise date — since the MK is already specific, the more
        # specific of the two should win. Here the additional_info uses
        # a different year to make the test assertion unambiguous.
        consolidation = Consolidation(
            profile_move_list={child_res: "tatiana_ivanovna"},
            profile_additional_info={
                "tatiana_ivanovna": [
                    GeniProfile(
                        death=GeniEvent(
                            date=GeniDate(day=5, month=4, year=1828),
                        ),
                    ),
                ],
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        out = gen.get_output("consolidated_profiles_1.tf")
        self.assertRegex(out, r'day\s+=\s+5\b')
        self.assertRegex(out, r'month\s+=\s+4\b')
        self.assertRegex(out, r'year\s+=\s+1828\b')

    def test_override_still_wins_over_additional_info(self):
        from verso.core.targets.geni.profile import GeniProfile
        records, child_res = self._setup()
        consolidation = Consolidation(
            profile_move_list={child_res: "tatiana_ivanovna"},
            profile_additional_info={
                "tatiana_ivanovna": [
                    GeniProfile(last_name="Тентетникова"),
                ],
            },
            profile_overrides={
                "tatiana_ivanovna": GeniProfile(last_name="Бодаева"),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        out = gen.get_output("consolidated_profiles_1.tf")
        self.assertRegex(out, r'last_name\s+=\s+"Бодаева"')
        self.assertNotIn('"Тентетникова"', out)


class TestMergeConsolidatedEvents(unittest.TestCase):
    """Unit tests for `TerraformGenerator._merge_consolidated` event handling.
    Exercises the death/birth date and location propagation rules directly
    without going through the records pipeline.
    """

    def _profile(self, **kwargs):
        from verso.core.targets.geni.profile import GeniProfile
        defaults = {"res_name": "p", "gender": "male", "alive": False, "public": True}
        defaults.update(kwargs)
        return GeniProfile(**defaults)

    def _event(self, date=None, location=None):
        from verso.core.targets.geni.event import GeniEvent
        return GeniEvent(date=date, location=location)

    def _date(self, **kwargs):
        from verso.core.targets.geni.date import GeniDate
        return GeniDate(**kwargs)

    def test_death_after_then_specific_prefers_specific(self):
        """Census marks profile alive-as-of-1804 (range='after', year=1804).
        A later death record gives the actual 1814-10-01 date. The
        consolidated death should be the specific date, not the range."""
        existing = self._profile(
            death=self._event(date=self._date(year=1804, date_range="after")),
        )
        incoming = self._profile(
            death=self._event(date=self._date(year=1814, month=10, day=1)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertIsNone(existing.death.date.date_range)
        self.assertEqual(existing.death.date.year, 1814)
        self.assertEqual(existing.death.date.month, 10)
        self.assertEqual(existing.death.date.day, 1)

    def test_occupation_of_a_later_record_is_kept(self):
        """A canonical seeded by a birth record, which states no occupation,
        gets one from a WWII card: «чернорабочий». Folding the card must not
        drop it — Geni carries the merged profile's occupation, and the next
        apply would erase it."""
        existing = self._profile()
        incoming = self._profile()
        incoming.occupation = "чернорабочий"
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual("чернорабочий", existing.occupation)
        later = self._profile()
        later.occupation = "колхозник"
        TerraformGenerator._merge_consolidated(existing, later)
        self.assertEqual("чернорабочий", existing.occupation)  # first one stated wins

    def test_death_specific_then_after_keeps_specific(self):
        """Reverse order: specific first, then the lower-precision 'after'
        marker arrives. The specific date should win."""
        existing = self._profile(
            death=self._event(date=self._date(year=1814, month=10, day=1)),
        )
        incoming = self._profile(
            death=self._event(date=self._date(year=1804, date_range="after")),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertIsNone(existing.death.date.date_range)
        self.assertEqual(existing.death.date.year, 1814)

    def test_death_location_propagates_when_existing_has_none(self):
        """Census alive-marker carries no location; actual death record
        does. The consolidated event should keep the death location."""
        existing = self._profile(
            death=self._event(
                date=self._date(year=1804, date_range="after"),
                location=None,
            ),
        )
        incoming = self._profile(
            death=self._event(
                date=self._date(year=1814, month=10, day=1),
                location="село Горюхино",
            ),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual(existing.death.location, "село Горюхино")

    def test_birth_between_then_between_narrows_range(self):
        """Two godparent-style birth estimates both 'between year-60 and
        year-6' (encounters in 1800 and 1820 give 1740-1794 and 1760-1814).
        Narrowing intersection: 1760-1794."""
        existing = self._profile(
            birth=self._event(date=self._date(
                year=1740, end_year=1794, circa=True, end_circa=True,
                date_range="between",
            )),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(
                year=1760, end_year=1814, circa=True, end_circa=True,
                date_range="between",
            )),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual(existing.birth.date.year, 1760)
        self.assertEqual(existing.birth.date.end_year, 1794)
        self.assertEqual(existing.birth.date.date_range, "between")

    def test_birth_between_then_specific_prefers_specific(self):
        """A specific-circa birth within a between range replaces the range."""
        existing = self._profile(
            birth=self._event(date=self._date(
                year=1740, end_year=1794, circa=True, end_circa=True,
                date_range="between",
            )),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1770, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertIsNone(existing.birth.date.date_range)
        self.assertEqual(existing.birth.date.year, 1770)

    def test_birth_location_propagates_when_existing_has_none(self):
        existing = self._profile(
            birth=self._event(date=self._date(year=1770, circa=True), location=None),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1770, circa=True),
                              location="село Неелово"),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual(existing.birth.location, "село Неелово")

    def test_birth_two_circa_different_years_promote_to_between(self):
        """A census says circa 1764, a death record's age=40 in
        1814 says circa Oct 1774. Two single-circa estimates with
        different years should merge into between [1764..Oct 1774]."""
        existing = self._profile(
            birth=self._event(date=self._date(year=1764, circa=True)),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1774, month=10, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.birth.date
        self.assertEqual(d.date_range, "between")
        self.assertTrue(d.circa)
        self.assertTrue(d.end_circa)
        self.assertEqual(d.year, 1764)
        self.assertEqual(d.end_year, 1774)
        self.assertEqual(d.end_month, 10)

    def test_birth_two_circa_different_years_swap_when_existing_later(self):
        """Reverse order: existing is the later year. Should still produce
        between with earlier year as start and later as end."""
        existing = self._profile(
            birth=self._event(date=self._date(year=1774, month=10, circa=True)),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1764, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.birth.date
        self.assertEqual(d.date_range, "between")
        self.assertEqual(d.year, 1764)
        self.assertEqual(d.end_year, 1774)
        self.assertEqual(d.end_month, 10)

    def test_birth_two_circa_same_year_fills_in_month(self):
        """Same year, incoming has month — fill month into existing."""
        existing = self._profile(
            birth=self._event(date=self._date(year=1770, circa=True)),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1770, month=6, day=15, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.birth.date
        self.assertIsNone(d.date_range)
        self.assertEqual(d.year, 1770)
        self.assertEqual(d.month, 6)
        self.assertEqual(d.day, 15)

    def test_birth_between_extends_end_when_incoming_within_two_years_after(self):
        """Existing between [1740..1794], incoming circa 1795 → extend end."""
        existing = self._profile(
            birth=self._event(date=self._date(
                year=1740, end_year=1794, circa=True, end_circa=True,
                date_range="between",
            )),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1795, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.birth.date
        self.assertEqual(d.date_range, "between")
        self.assertEqual(d.year, 1740)
        self.assertEqual(d.end_year, 1795)

    def test_birth_between_extends_end_with_exact_two_year_gap_year_only(self):
        """Existing between [1758..1805] year-only, incoming circa 1807
        year-only → extend end. Regression: a person with a roll
        birth=circa 1807 and a marriage range [1758..1805];
        Jan-1 date arithmetic in to_end_datetime() made the gap
        (1807-01-01 − 1805-01-01) = 104 weeks > the 100-week threshold,
        so branch 5 declined to extend and the precise 1807 estimate
        was discarded. End_year semantics now treat year-only end as
        Dec-31, making the gap 1 day and letting the merge fire."""
        existing = self._profile(
            birth=self._event(date=self._date(
                year=1758, end_year=1805, circa=True, end_circa=True,
                date_range="between",
            )),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1807, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.birth.date
        self.assertEqual(d.date_range, "between")
        self.assertEqual(d.year, 1758)
        self.assertEqual(d.end_year, 1807)

    def test_birth_between_extends_start_when_incoming_within_two_years_before(self):
        """Existing between [1740..1794], incoming circa 1739 → extend start."""
        existing = self._profile(
            birth=self._event(date=self._date(
                year=1740, end_year=1794, circa=True, end_circa=True,
                date_range="between",
            )),
        )
        incoming = self._profile(
            birth=self._event(date=self._date(year=1739, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.birth.date
        self.assertEqual(d.date_range, "between")
        self.assertEqual(d.year, 1739)
        self.assertEqual(d.end_year, 1794)

    def test_death_after_then_later_after_takes_max(self):
        """Both 'after' markers — keep the later one (latest-known-alive)."""
        existing = self._profile(
            death=self._event(date=self._date(year=1804, date_range="after")),
        )
        incoming = self._profile(
            death=self._event(date=self._date(year=1816, date_range="after")),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual(existing.death.date.year, 1816)
        self.assertEqual(existing.death.date.date_range, "after")

    def test_death_after_then_before_converts_to_between(self):
        """Existing 'after 1804', incoming 'before 1820' → between."""
        existing = self._profile(
            death=self._event(date=self._date(year=1804, date_range="after")),
        )
        incoming = self._profile(
            death=self._event(date=self._date(year=1820, date_range="before")),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.death.date
        self.assertEqual(d.date_range, "between")
        self.assertEqual(d.year, 1804)
        self.assertEqual(d.end_year, 1820)

    def test_death_after_with_earlier_circa_within_two_years_keeps_existing(self):
        """'after 1814' + circa 1813 (within 2 yrs before) → keep 'after'."""
        existing = self._profile(
            death=self._event(date=self._date(
                year=1814, circa=True, date_range="after",
            )),
        )
        incoming = self._profile(
            death=self._event(date=self._date(year=1813, circa=True)),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        d = existing.death.date
        self.assertEqual(d.date_range, "after")
        self.assertEqual(d.year, 1814)

    def test_merge_promotes_real_first_name_over_unknown_placeholder(self):
        """When the earliest record has first_name="?" (e.g. damaged
        page rendered as `person("?", ...)`) and a later record has the
        real name, the consolidated profile should adopt the real name —
        not keep "?" and demote the real name to nicknames.

        The legacy generator explicitly promoted the non-"?" name; the
        new `_merge_consolidated` was missing this branch.
        """
        existing = self._profile(first_name="?", middle_name="Григорьевич",
                                 last_name="Таратайкин")
        incoming = self._profile(first_name="Родион", middle_name="Григорьевич",
                                 last_name="Таратайкин")
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual(existing.first_name, "Родион")
        # "?" should not appear in nicknames either.
        self.assertNotIn("?", existing.nicknames or [])

    def test_merge_keeps_real_first_name_when_incoming_is_unknown(self):
        """Reverse order: existing has real name, incoming is "?". Keep
        the real name; do NOT add "?" to nicknames."""
        existing = self._profile(first_name="Родион", middle_name="Григорьевич",
                                 last_name="Таратайкин")
        incoming = self._profile(first_name="?", middle_name="Григорьевич",
                                 last_name="Таратайкин")
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual(existing.first_name, "Родион")
        self.assertNotIn("?", existing.nicknames or [])

    def test_merge_honors_ignore_for_first_name_variant(self):
        """`ignore: [GeniProfile(first_name="Агафоник")]` in the
        consolidation config means the per-record variant `Агафоник`
        is silently dropped during merge — the canonical `Агафон`
        stays as first_name AND `Агафоник` does NOT appear in nicknames.

        The legacy generator dropped such variants the same way.
        """
        existing = self._profile(first_name="Агафон", middle_name="Васильевич")
        incoming = self._profile(first_name="Агафоник", middle_name="Васильевич")
        ignore_list = [{"first_name": "Агафоник"}]
        TerraformGenerator._merge_consolidated(
            existing, incoming, ignore=ignore_list,
        )
        self.assertEqual(existing.first_name, "Агафон")
        self.assertNotIn("Агафоник", existing.nicknames or [])

    def test_merge_honors_ignore_for_middle_name_variant(self):
        """`ignore: [GeniProfile(middle_name=
        "Васильевич")]` means a per-record variant `Васильевич` is
        silently dropped when the canonical is `Гавриилович`."""
        existing = self._profile(first_name="Матвей", middle_name="Гавриилович")
        incoming = self._profile(first_name="Матвей", middle_name="Васильевич")
        ignore_list = [{"middle_name": "Васильевич"}]
        TerraformGenerator._merge_consolidated(
            existing, incoming, ignore=ignore_list,
        )
        self.assertEqual(existing.middle_name, "Гавриилович")

    def test_merge_promotes_married_last_name_over_maiden(self):
        """A woman born Манилова (a child's birth record), later married
        Пеночкин → bride profile carries last_name=Пеночкина,
        birth_last_name=Манилова. When merging, the married last_name
        should WIN over the maiden one already in `existing.last_name`.

        The legacy generator: `existing.last_name == profile.birth_last_name`
        triggers replacement with the married `profile.last_name`.
        """
        existing = self._profile(
            first_name="Анастасия", middle_name="Григорьевна",
            last_name="Манилова",
        )
        incoming = self._profile(
            first_name="Анастасия", middle_name="Григорьевна",
            last_name="Пеночкина", birth_last_name="Манилова",
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertEqual(existing.last_name, "Пеночкина")
        self.assertEqual(existing.birth_last_name, "Манилова")

    def test_preference_pre_populates_and_merge_adds_variants(self):
        """Preference nicknames are pre-populated as a config-level
        decision (declared variants are historical aliases worth
        preserving). On-merge nickname addition then ensures incoming
        variants matching `preference.nicknames` are also captured —
        this catches per-records arriving AFTER seed time.
        """
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        gen = TerraformGenerator(
            village_dir=None,
            consolidation=Consolidation(
                profile_move_list={"_1850_pavel": "pavel_mizhuev"},
                profile_preferences={"pavel_mizhuev": {
                    "first_name": "Павел",
                    "middle_name": "Никифорович",
                    "last_name": "Мижуев",
                    "birth_last_name": None,
                    "nicknames": ["Анучкин", "Никифоров"],
                }},
            ),
        )
        first = self._profile(res_name="_1850_pavel", first_name="Павел",
                              middle_name="Никифорович", last_name="Анучкин")
        gen._emit_profile("dummy.tf", first)
        consolidated = gen._consolidated_profiles["pavel_mizhuev"]
        self.assertEqual(consolidated.last_name, "Мижуев")
        # Both declared variants pre-populated, sorted alphabetically.
        self.assertEqual(consolidated.nicknames, ["Анучкин", "Никифоров"])

    def test_merge_consolidated_includes_baptism_and_burial(self):
        """`_merge_consolidated` was only handling birth/death events;
        baptism and burial events from incoming per-records were silently
        dropped on consolidation. A birth record carrying a baptism =
        {10.11.1796, село Горюхино} ended up missing from the
        consolidated profile.
        """
        existing = self._profile()  # no events yet
        incoming = self._profile(
            baptism=self._event(
                date=self._date(day=10, month=11, year=1796),
                location="село Горюхино",
            ),
            burial=self._event(
                date=self._date(day=15, month=5, year=1850),
                location="село Собакевичево",
            ),
        )
        TerraformGenerator._merge_consolidated(existing, incoming)
        self.assertIsNotNone(existing.baptism, "baptism dropped on merge")
        self.assertEqual(existing.baptism.date.day, 10)
        self.assertEqual(existing.baptism.date.month, 11)
        self.assertEqual(existing.baptism.date.year, 1796)
        self.assertEqual(existing.baptism.location, "село Горюхино")
        self.assertIsNotNone(existing.burial, "burial dropped on merge")
        self.assertEqual(existing.burial.date.year, 1850)

    def test_union_move_list_v2_honors_canonical_orthographic_aliases(self):
        """`union_move_list_v2` keys in `generate_config_names.py` use
        canonical patronymic spellings (e.g. `terentievich`), but the
        new generator emits union res_names with the orthographic
        spelling (`terentevich`, dropped `i`) — derived from the
        partner profiles' name fields. Without alias expansion, the
        v2 lookup misses → unions fall back to partner-lookup → wrong
        wife consolidation.

        Child unions like `osip_terentevich__51_1827` (a second wife's
        daughter) weren't being redirected to
        `osip_terentievich_and_varvara_petrovna` — they fell back to the
        first wife's marriage union, registered first.
        """
        from verso.ru.targets.geni.translator import Consolidation
        consol = Consolidation(union_move_list_v2={
            # Config uses canonical form
            "osip_terentievich__51_1827": "osip_terentievich_and_varvara_petrovna",
        })
        # New generator emits orthographic res_names — lookup via
        # alias expansion should still find the target.
        self.assertEqual(
            consol.union_move_list_v2.get("osip_terentevich__51_1827"),
            "osip_terentievich_and_varvara_petrovna",
            "v2 alias for terentievich/terentevich missing",
        )

    def test_no_aux_godparent_parent_union_without_relative_ref(self):
        """Legacy `god_parent_rel` (Горюхино/generate_config.py:38-62)
        is ONLY called when the source CSV row has
        `Чей родств.N == 'восприемника №N'` — i.e., when there's an
        explicit relative reference to the godparent. For ordinary
        birth records with just `mother + godparents` (no relative-of-
        godparent ref), legacy emits NO synthetic union.

        The shape: mother=Юлиана, godmother=Марина, NO relative ref.
        Legacy wouldn't emit anything; the new generator was emitting a
        `juliana + marina(as child)` synthetic union which then
        leaked marina into Gavriil+Juliana's marriage-union children
        list via partner-lookup consolidation.
        """
        from calendar import Month
        from verso.ru.dsl.records.births import birth, birth_month, birth_records
        from verso.ru.domain import Gender, person
        from verso.ru.targets.geni.translator import TerraformGenerator

        records = birth_records(
            "TestArch", "12", "1", "1", "Тестовка", "Никольская", 1830,
            *birth_month(
                Month.OCTOBER,
                birth(45, Gender.FEMALE, 23, 29,
                      child=person("Анастасия"),
                      mother=person("Юлиана", "Тимофеева"),
                      god_parent1=person("Прохор", "Артемов"),
                      god_parent2=person("Марина", "Власова")),
            ),
        )
        # Mark the mother's per-record stub as consolidated so the
        # aux-loop's consolidation check would fire.
        from verso.ru.targets.geni.translator import Consolidation
        consol = Consolidation(profile_move_list={
            "_1830_10_23_juliana_timofeevna_mk_births_45_mother":
                "juliana_timofeevna_sundukina",
        })
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        gen.add_birth_records(records)
        # Aux loop emits to consolidated_unions when a participant is
        # consolidated. Check that NO aux union with mother+godmother
        # got created (legacy requires explicit relative ref).
        for u_name, u in gen._consolidated_unions.items():
            children = u.children or set()
            self.assertNotIn(
                "_1830_10_23_marina_vlasovna_mk_births_45_god_parent_2",
                children,
                f"godmother stub leaked into union {u_name!r} as a child",
            )

    def test_v2_redirect_overwrites_partner_map_registration(self):
        """When the same partner has TWO v2-redirected unions to
        DIFFERENT targets (e.g. two wives of one man), and they're
        processed in chronological order that doesn't match legacy's
        MK-first → census-second iteration, the partner→target map
        must update to the LATEST v2 target — otherwise non-v2 unions
        (like later RS family-member unions) end up routed to the
        wrong wife.

        Example, a man with two wives (Stefanida → Evdokija): the new
        generator processes 1795 RS first → stefanida v2 target
        registered. Then 1800 MK arrives → evdokija v2 target. With
        setdefault, agafon stays mapped to stefanida. Then rs596_1834
        (no v2) goes to stefanida via partner-lookup. Wrong.
        """
        from verso.core.targets.geni.union import GeniUnion as _GU
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        consol = Consolidation(
            union_move_list_v2={
                "agafon_rs1795": "agafon_and_stefanida",
                "agafon_mk1800": "agafon_and_evdokija",
                "agafon_rs1850": "agafon_and_evdokija",
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        # 1795: stefanida via v2.
        gen._add_to_consolidated_unions(_GU(
            res_name="agafon_rs1795",
            partner_1="agafon", partner_2="stefanida",
            children={"_1795_evdokija_daughter"},
        ))
        # 1800: evdokija via v2 (later, but should win for partner map).
        gen._add_to_consolidated_unions(_GU(
            res_name="agafon_mk1800",
            partner_1="agafon", partner_2=None,
            children={"_1800_feodor"},
        ))
        # rs596_1834 (no v2): should fall back to evdokija (latest v2
        # registered in the partner map after the overwrite fix).
        gen._add_to_consolidated_unions(_GU(
            res_name="agafon_rs596_1834",
            origin=UnionOrigin.ROLL,
            partner_1="agafon", partner_2="evdokija_wife",
            children={"gavriil"},
        ))
        # 1850 RS via v2 — sets partner_2 (only v2 may fill partner_2).
        gen._add_to_consolidated_unions(_GU(
            res_name="agafon_rs1850",
            partner_1="agafon", partner_2="evdokija_wife",
            children=set(),
        ))
        evdokija = gen._consolidated_unions["agafon_and_evdokija"]
        self.assertIn("gavriil", evdokija.children or set(),
                      "non-v2 union routed to wrong wife (latest v2 target should win)")
        self.assertEqual(evdokija.partner_2, "evdokija_wife")

    def test_partner_2_set_by_non_v2_marriage_record(self):
        """A marriage-record union (partner_2 = bride per-record stub
        like `*_mk_marriages_N_bride`) should set partner_2 of the
        existing target even when the union has no v2 entry. Only
        godparent-merge unions (partner_2 = `*_god_parent_N` stub)
        should be blocked.

        Example: a 1810 marriage with Феодосия Семёновна has no v2 entry
        but is the LEGITIMATE source of partner_2. Without this,
        partner_2 stays None.
        """
        from verso.core.targets.geni.union import GeniUnion as _GU
        from verso.ru.targets.geni.translator import TerraformGenerator

        gen = TerraformGenerator(village_dir=None)
        # Seed with a birth record (no partner_2).
        gen._add_to_consolidated_unions(_GU(
            res_name="timofej_alekseevich__18_1816",
            partner_1="timofej_alekseevich", partner_2=None,
            children={"arhipp"},
        ))
        # Marriage record union — partner_2 is a real bride per-record stub.
        gen._add_to_consolidated_unions(_GU(
            res_name="timofej_alekseevich_and_feodosija_makarovna_m4_1810",
            origin=UnionOrigin.MARRIAGE,
            partner_1="timofej_alekseevich",
            partner_2="_1810_02_09_feodosija_makarovna_mk_marriages_4_bride",
            children=set(),
        ))
        target = next(iter(gen._consolidated_unions.values()))
        self.assertEqual(
            target.partner_2,
            "_1810_02_09_feodosija_makarovna_mk_marriages_4_bride",
            "marriage-record partner_2 was not set",
        )

    def test_partner_2_not_polluted_by_non_v2_godparent_merge(self):
        """When a non-v2 godparent-spouse merge union (partner_2 = the
        godparent) is merged into an existing v2 target before the
        target's spouse-bearing v2 source arrives, partner_2 must not
        be set from the godparent. Only v2-redirected unions can fill
        in partner_2 of an existing target."""
        from verso.core.targets.geni.union import GeniUnion as _GU
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        consol = Consolidation(
            union_move_list_v2={
                "agafon_mk1800": "agafon_and_evdokija",  # birth, no partner_2
                "agafon_rs1834": "agafon_and_evdokija",  # RS, has partner_2
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        # Seed: birth-record union, no partner_2.
        gen._add_to_consolidated_unions(_GU(
            res_name="agafon_mk1800",
            partner_1="agafon", partner_2=None,
            children={"feodor"},
        ))
        # Godparent-spouse merge (no v2): partner_2 = godparent.
        gen._add_to_consolidated_unions(_GU(
            res_name="agafon_and_godparent_1800",
            partner_1="agafon", partner_2="ioann_arhippovich",
            children=set(),
        ))
        # RS-record union (v2): partner_2 = real spouse evdokija.
        gen._add_to_consolidated_unions(_GU(
            res_name="agafon_rs1834",
            partner_1="agafon", partner_2="evdokija",
            children={"gavriil"},
        ))
        target = gen._consolidated_unions["agafon_and_evdokija"]
        self.assertEqual(target.partner_2, "evdokija",
                         "partner_2 was polluted by non-v2 godparent merge")

    def test_v2_redirect_overrides_partner_lookup(self):
        """When `union_move_list_v2` explicitly maps a union to a
        target res_name (e.g. for splitting children of a man with
        multiple wives), the partner-lookup fallback must NOT override
        that mapping by collapsing the union into another consolidation
        already keyed on the same partner.

        Example: a 1806 marriage with Праскова → consolidated as
        `georgij_ilich_and_paraskeva_ivanovna`.
        Later 1820+ child unions are explicitly redirected via
        `union_move_list_v2` to `georgij_ilich_and_olga_pavlovna`
        (the second wife). Currently the partner-lookup branch sees
        partner_1 (stefan) is already mapped to the paraskeva union
        and overrides the v2 target — so all children land in paraskeva.
        """
        from verso.core.targets.geni.union import GeniUnion as _GU
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        consol = Consolidation(
            union_move_list_v2={
                "stefan__17_1820": "stefan_and_evfimija",
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        # First union: marriage with first wife. No v2 entry → partner
        # lookup builds `stefan_and_paraskeva` target.
        first = _GU(
            res_name="stefan_and_paraskeva_m1_1806",
            origin=UnionOrigin.MARRIAGE,
            partner_1="stefan", partner_2="paraskeva",
            children=set(),
        )
        gen._add_to_consolidated_unions(first)
        # Second union: child with second wife. v2 explicitly redirects
        # to `stefan_and_evfimija`.
        second = _GU(
            res_name="stefan__17_1820",
            partner_1="stefan", partner_2=None,
            children={"_1820_07_26_evstignej_stepanovich_mk_births_17_child"},
        )
        gen._add_to_consolidated_unions(second)

        self.assertIn("stefan_and_evfimija", gen._consolidated_unions,
                      "v2 target was overridden by partner lookup")
        evfimija_union = gen._consolidated_unions["stefan_and_evfimija"]
        self.assertIn("_1820_07_26_evstignej_stepanovich_mk_births_17_child",
                      evfimija_union.children or set())
        # The child must NOT be in the paraskeva union.
        paraskeva_union = gen._consolidated_unions.get("stefan_and_paraskeva")
        if paraskeva_union:
            self.assertNotIn("_1820_07_26_evstignej_stepanovich_mk_births_17_child",
                             paraskeva_union.children or set())

    def test_subfamily_two_wife_secondary_mother_routing(self):
        """A SUB-FAMILY father (a SON of the head, not the head himself)
        who was widowed and remarried has two WIFE members. Without
        routing, both wives' sub-family unions get EVERY child — a Geni
        `duplicate_parents` tree conflict. A child annotated
        `secondary_role=SON/DAUGHTER` + `secondary_ref_member=<wife>`
        must land in THAT wife's union only, and the head must NOT be
        paired with the sub-family father's wives.

        The shape: a head; his son widowed by his first wife (м14),
        remarried a widow (м15); the early children are the first wife's,
        the youngest is the second's.
        """
        from verso.ru.dsl.records.census import CensusRole, census_records, household, member
        from verso.ru.domain import person, page
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        # Consolidate the father so both sub-family wife-unions route to
        # distinct partner-keyed buckets (the per-year path keys a sub-union
        # on the father alone, so the 2nd wife would overwrite the 1st).
        consol = Consolidation(
            profile_move_list={
                "_1795_00_00_ioann_prohorovich_rs_1_3_family_member": "ioann_prohorovich",
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        records = census_records(
            "ГА Глуповской области", "17", "7", "859", "Горюхино", 1795,
            *page("",
                  household(None, member(1, person("Прохор", "Тихонов"), CensusRole.HEAD, age=58),
                            member(2, person("Евдокия", "Петрова"), CensusRole.WIFE, ref_member=1, age=53),
                            member(3, person("Иван", "Прохоров"), CensusRole.SON, age=36),
                            member(4, person("Фекла", "Егорова"), CensusRole.WIFE, ref_member=3, age=42),
                            member(5, person("Ирина", "Федорова"), CensusRole.WIFE, ref_member=3, age=38),
                            member(6, person("Евграф", "Иванов"), CensusRole.SON, ref_member=3, age=7,
                                   secondary_role=CensusRole.SON, secondary_ref_member=4),
                            member(7, person("Фока", "Иванов"), CensusRole.SON, ref_member=3, age=4,
                                   secondary_role=CensusRole.SON, secondary_ref_member=5)),
                  ),
        )
        gen.add_census_records(records)

        unions = list(gen._consolidated_unions.values()) + list(
            gen._union_registry.values()
        )

        def kids_of(p2_token):
            for u in unions:
                if u.partner_2 and p2_token in u.partner_2:
                    return set(u.children or set())
            return None

        fekla_kids = kids_of("fekla")
        irina_kids = kids_of("irina")
        assert fekla_kids is not None, "Иван+Фекла union missing"
        assert irina_kids is not None, "Иван+Ирина union missing"
        # Evgraf → Fekla only; Foka → Irina only. No overlap — this is the
        # routing fix (without it both unions would hold both children).
        self.assertTrue(any("evgraf" in c for c in fekla_kids))
        self.assertFalse(any("foka" in c for c in fekla_kids))
        self.assertTrue(any("foka" in c for c in irina_kids))
        self.assertFalse(any("evgraf" in c for c in irina_kids))
        # The head (Прохор) must not be paired with a sub-family wife.
        for u in unions:
            if u.partner_1 and "prohor_tihonovich" in u.partner_1:
                self.assertFalse(
                    u.partner_2 and ("fekla" in u.partner_2 or "irina" in u.partner_2),
                    "head wrongly paired with a sub-family father's wife",
                )

    def test_son_with_previous_age_stays_with_head_when_stub_fires(self):
        """In the head-only census-emission path, members with
        `previous_age` are routed to the implied-parent stub union
        when one fires (BROTHER/SISTER pointing at HEAD without an
        explicit `parent_member`). That reroute applies ONLY to
        full-sibling members the stub itself claims (BROTHER/SISTER
        without a `сводный/сводная` step-sibling qualifier). HEAD's
        own SON/DAUGHTER members with `previous_age` (= they were
        attested in the prior RS as HEAD's own children) must stay
        in HEAD's union.

        The shape: a 1850 RS HEAD with previous_age and previous_age-bearing
        SONs plus a manually-added hidden BROTHER representing
        an unrecorded grandfather chain. The stub fires on the
        BROTHER and used to claim ALL previous_age members — leaving
        Pavel's union with empty `ho_children` and silently dropping
        his head-only attestation.
        """
        from verso.ru.dsl.records.census import CensusRole, census_records, household, member
        from verso.ru.domain import person, page
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        consol = Consolidation(
            profile_move_list={
                "_1850_00_00_pavel_matveevich_anuchkin_rs_1_1_family_member":
                    "pavel_anuchkin",
                "_1850_00_00_georgij_pavlovich_anuchkin_rs_1_2_family_member":
                    "georgij_anuchkin",
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        records = census_records(
            "ГА Глуповской области", "32", "6", "2338", "Горюхино",
            1850,
            *page("",
                  household(None, member(1, person("Павел", "Матвеев", "Анучкин"), CensusRole.HEAD, age=61,
                                         previous_age=61,
                                         departure_year=1842, departure_reason="умер"),
                            member(2, person("Егор", "Павлов", "Анучкин"), CensusRole.SON, age=51, previous_age=35),
                            member(3, person("Егор", "Матвеев", "Анучкин"), CensusRole.BROTHER, age="?",
                                   hidden=True)),
                  ),
        )
        gen.add_census_records(records)
        # Find any union whose partner_1 is Pavel and that lists Georgij
        # as a child. With the bug, the stub claims the SON via the
        # previous_age reroute, leaving ho_children empty so no head-
        # only union is emitted.
        found = False
        for union in gen._consolidated_unions.values():
            if union.partner_1 != "pavel_anuchkin":
                continue
            if "georgij_anuchkin" in (union.children or set()):
                found = True
                break
        self.assertTrue(
            found,
            "HEAD's SON with previous_age was rerouted to the brother's "
            "stub instead of staying in HEAD's union",
        )

    def test_deferred_partner_2_does_not_swallow_different_wife_birth(self):
        """When a v2 redirect creates a bucket whose NAME encodes a
        specific wife but `candidate.partner_2` hasn't been populated
        yet (because the redirected source was father-only, e.g. a
        single-parent MK birth), an unrelated birth-record union with
        a DIFFERENT canonical wife must NOT fold into that bucket via
        partner-lookup on the husband.

        The shape: a single-father MK birth was v2-redirected to
        `ignatij_..._and_efrosinija_...` (creating that bucket with
        partner_2=None). A later birth with a second wife Феодосия
        arrived; partner-lookup on Ignatij found Efrosinija's bucket;
        the existing spouse-conflict guard short-circuited on the falsy
        partner_2; the later birth folded wrongly into Efrosinija's
        bucket. Legacy filed it in Feodosija's separate bucket.

        The deferred-wife guard treats the bucket NAME's `_and_<wife>`
        suffix as authoritative when partner_2 is None — but only when
        the incoming union's `<p1>_and_<p2>` is itself a known v2
        target (= a canonical bucket exists for that couple). The
        v2-target check distinguishes legitimate per-record-stub
        folding from genuine different-couple splits.
        """
        from verso.core.targets.geni.union import GeniUnion as _GU
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        consol = Consolidation(
            union_move_list_v2={
                "ignatij_mk1826": "ignatij_and_efrosinija",
                "ignatij_mk1838": "ignatij_and_feodosija",
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        # 1826 birth: father-only, v2-redirected to Efrosinija's
        # target. Bucket created with name `_and_efrosinija_` but
        # partner_2 stays None (no wife in this source).
        gen._add_to_consolidated_unions(_GU(
            res_name="ignatij_mk1826",
            partner_1="ignatij", partner_2=None,
            children={"ilija_ignatievich"},
        ))
        # 1838 birth with the SECOND wife Feodosija — non-v2-redirect
        # path (partner-derived target). Must land in a separate bucket
        # and not fold into Efrosinija's via partner-lookup.
        gen._add_to_consolidated_unions(_GU(
            res_name="ignatij_and_feodosija_18_1838",
            partner_1="ignatij", partner_2="feodosija",
            children={"glikerija"},
        ))
        efrosinija = gen._consolidated_unions["ignatij_and_efrosinija"]
        self.assertNotIn(
            "glikerija", efrosinija.children or set(),
            "1838 birth wrongly folded into the bucket of a different wife"
        )
        feodosija = gen._consolidated_unions.get("ignatij_and_feodosija")
        self.assertIsNotNone(
            feodosija, "Feodosija's bucket was not created",
        )
        self.assertIn(
            "glikerija", feodosija.children or set(),
            "1838 birth was not routed to its own (Feodosija's) bucket",
        )

    def test_consolidated_union_preserves_marriage_event(self):
        """`_add_to_consolidated_unions` was folding partners/children
        from the source union into the consolidated entry but silently
        dropping its `marriage` event. When the consolidated entry was
        seeded from a non-marriage source (e.g. a birth record union)
        and a later marriage record arrived, the marriage event from
        the marriage record was lost.

        The shape: a union seeded from `vasilij_petrovich_rs15_1811`
        (no marriage), then the m2_1826 union arrived with
        marriage = {20.1.1826, село Горюхино} — which vanished from
        the final consolidated union.

        Legacy `Горюхино/generate_config.py:185` calls
        `compare_events(consolidated_union, union, ..., "marriage")`
        to merge the marriage event during union consolidation.
        """
        from verso.core.targets.geni.event import GeniEvent as _GE
        from verso.core.targets.geni.date import GeniDate as _GD
        from verso.core.targets.geni.union import GeniUnion as _GU
        from verso.ru.targets.geni.translator import TerraformGenerator

        gen = TerraformGenerator(village_dir=None)
        # Seed: birth-record union, no marriage event.
        seed = _GU(
            res_name="vasilij_petrovich_rs15_1811",
            origin=UnionOrigin.ROLL,
            partner_1="vasilij_petrovich",
            partner_2=None,
            children={"_1811_00_00_iakov_vasilevich_rs_6_2_family_member"},
        )
        gen._add_to_consolidated_unions(seed)
        # Marriage record arrives later, with the actual marriage event.
        marriage = _GU(
            res_name="vasilij_petrovich_and_irina_pahomovna_m2_1826",
            origin=UnionOrigin.MARRIAGE,
            partner_1="vasilij_petrovich",
            partner_2="_1826_01_20_irina_pahomovna_mk_marriages_2_bride",
            children=set(),
            marriage=_GE(
                date=_GD(day=20, month=1, year=1826),
                location="село Горюхино",
            ),
        )
        gen._add_to_consolidated_unions(marriage)

        # Find the consolidated entry for vasilij_petrovich.
        target = next(
            (u for u in gen._consolidated_unions.values()
             if u.partner_1 == "vasilij_petrovich"),
            None,
        )
        self.assertIsNotNone(target, "consolidated union missing")
        self.assertIsNotNone(target.marriage,
                             "marriage event dropped during consolidation")
        self.assertEqual(target.marriage.date.day, 20)
        self.assertEqual(target.marriage.date.month, 1)
        self.assertEqual(target.marriage.date.year, 1826)
        self.assertEqual(target.marriage.location, "село Горюхино")

    def test_override_about_appends_to_existing(self):
        """An override carries an `about`
        text snippet (`* 13.01.1817\\n\\n        https://rgfond.ru/...`)
        that augments the merged about content. Legacy
        Горюхино/generate_config.py:2293-2296 appends with a `\\n\\n`
        separator (i.e. a blank line) so the override appendix reads as
        a distinct paragraph in the rendered Geni note. Previously the
        new generator's `_apply_profile_overrides` ignored
        override.about entirely.
        """
        from verso.core.targets.geni.profile import GeniProfile as _GP
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator
        profile = self._profile(
            res_name="evfimij_grigorevich_manilov",
            about="<strong>МК Горюхино 1817:</strong> рождение",
        )
        consol = Consolidation(
            profile_overrides={
                "evfimij_grigorevich_manilov": _GP(
                    about="* 13.01.1817\n\n        https://rgfond.ru/person/10001\n",
                ),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        gen._consolidated_profiles["evfimij_grigorevich_manilov"] = profile
        gen._apply_profile_overrides()
        self.assertIn("https://rgfond.ru/person/10001", profile.about)
        self.assertIn("* 13.01.1817", profile.about)
        # Original content preserved.
        self.assertIn("<strong>МК Горюхино 1817:</strong>", profile.about)
        # Blank line separates the existing about from the override
        # appendix — Geni renders that as a paragraph break.
        self.assertIn(
            "<strong>МК Горюхино 1817:</strong> рождение\n\n        * 13.01.1817",
            profile.about,
        )

    def test_override_about_one_blank_line_when_existing_has_trailing_newline(self):
        """Multi-section profiles end with `\\n` after the last merged
        section. Without rstrip(), appending `\\n\\n        ` would produce
        TWO blank lines between the last section and the override
        appendix (the appendix must be separated by exactly one blank line).
        """
        from verso.core.targets.geni.profile import GeniProfile as _GP
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator
        profile = self._profile(
            res_name="timon_lazarevich",
            # Trailing newline as produced by the consolidation merge
            # when multiple records contribute sections.
            about="<strong>МК Горюхино 1815:</strong> восприемник на крещении\n",
        )
        consol = Consolidation(
            profile_overrides={
                "timon_lazarevich": _GP(about="Тимон Лазарев - сын Лазаря Кирилова..."),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        gen._consolidated_profiles["timon_lazarevich"] = profile
        gen._apply_profile_overrides()
        # Exactly ONE blank line, not TWO, between section and appendix.
        self.assertIn(
            "восприемник на крещении\n\n        Тимон Лазарев",
            profile.about,
        )
        self.assertNotIn("\n\n\n", profile.about)

    def test_override_first_name_removes_canonical_from_nicknames(self):
        """Override sets `first_name="Перфил"`.
        During merge, a per-record with first_name="Перфил" met existing
        first_name="Парфений" and "Перфил" landed in nicknames. After
        override pins first_name=Перфил, the nickname entry equal to
        the canonical must be removed (legacy line 2098-2099 simply
        sets `existing.first_name = override.first_name` and the
        consolidation never produced a self-referential nickname).
        """
        from verso.core.targets.geni.profile import GeniProfile as _GP
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator
        profile = self._profile(
            res_name="perfil_terentievich",
            first_name="Парфений",
            middle_name="Терентьевич",
            nicknames=["Перфил"],
        )
        consol = Consolidation(
            profile_overrides={
                "perfil_terentievich": _GP(first_name="Перфил"),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        gen._consolidated_profiles["perfil_terentievich"] = profile
        gen._apply_profile_overrides()
        self.assertEqual(profile.first_name, "Перфил")
        self.assertNotIn("Перфил", profile.nicknames or [])

    def test_override_birth_date_preserves_existing_location(self):
        """A per-record child profile
        has birth = {date: 9.8.1801, location: село Горюхино}. Override
        carries `birth=GeniEvent(date=GeniDate(day=9, month=8, year=1801))`
        — date only, no location. Applying override should replace date
        only and leave location intact. Legacy
        Горюхино/generate_config.py:2326-2338 only sets `.date` (not the
        whole event) when an existing event is present.
        """
        from verso.core.targets.geni.event import GeniEvent as _GE
        from verso.core.targets.geni.date import GeniDate as _GD
        from verso.core.targets.geni.profile import GeniProfile as _GP
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        profile = self._profile(
            res_name="emeljan_fedotovich_gorlopanov",
            birth=_GE(date=_GD(day=9, month=8, year=1801),
                      location="село Горюхино"),
        )
        consol = Consolidation(
            profile_overrides={
                "emeljan_fedotovich_gorlopanov": _GP(
                    birth=_GE(date=_GD(day=9, month=8, year=1801)),
                ),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        gen._consolidated_profiles["emeljan_fedotovich_gorlopanov"] = profile
        gen._apply_profile_overrides()

        self.assertEqual(profile.birth.date.year, 1801)
        # Location MUST survive — override didn't carry one.
        self.assertEqual(profile.birth.location, "село Горюхино")

    def test_override_replaces_nicknames_not_appends(self):
        """Per-record records appearing as
        first_name="Савва" and "Савелий" cause "Савелий" to land in
        nicknames during merge. The override
        `{first_name: "Савелий", nicknames: ["Савва"]}` should then
        REPLACE existing.nicknames entirely — leaving just
        `["Савва"]` (the canonical first_name shouldn't appear in its
        own nicknames). Legacy `Горюхино/generate_config.py:2189-2190`
        is `existing.nicknames = override.nicknames` (replacement, not
        append).
        """
        from verso.core.targets.geni.profile import GeniProfile as _GP
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator
        # Pre-populate a consolidated profile in the same shape the
        # finalize step would see after all per-record merges complete.
        profile = self._profile(
            res_name="savva_semenovich",
            first_name="Савва",
            middle_name="Семенович",
            nicknames=["Савелий"],  # leaked in during merge
        )
        consol = Consolidation(
            profile_overrides={
                "savva_semenovich": _GP(first_name="Савелий",
                                        nicknames=["Савва"]),
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consol)
        gen._consolidated_profiles["savva_semenovich"] = profile
        gen._apply_profile_overrides()

        self.assertEqual(profile.first_name, "Савелий")
        self.assertEqual(profile.nicknames, ["Савва"])
        self.assertNotIn("Савелий", profile.nicknames)

    def test_merge_event_does_not_mutate_shared_existing(self):
        """When a marriage record assigns one `partner_death` GeniEvent to
        BOTH groom and bride profiles by reference, merging a wife's later
        specific death into the wife's consolidated profile must not leak
        that date back into the husband's profile via the shared object.

        The bug: a wife's 1.3.1832 death record was bleeding into
        husband's profile because both held the same `partner_death`
        reference.
        """
        from verso.core.targets.geni.event import GeniEvent
        from verso.core.targets.geni.date import GeniDate
        # Marriage emits ONE partner_death assigned to both spouses.
        partner_death = GeniEvent(
            date=GeniDate(day=9, month=1, year=1799, date_range="after"),
        )
        groom = self._profile(res_name="iosif_titovich", death=partner_death)
        bride = self._profile(res_name="matrona_fedotovna", death=partner_death)
        # Wife's later death record arrives with specific date + location.
        wife_death_record = self._profile(
            res_name="matrona_fedotovna",
            death=self._event(
                date=self._date(day=1, month=3, year=1832),
                location="село Горюхино",
            ),
        )
        # Merge the wife's death record into her consolidated profile.
        TerraformGenerator._merge_consolidated(bride, wife_death_record)
        # Bride's death updates correctly.
        self.assertEqual(bride.death.date.year, 1832)
        self.assertEqual(bride.death.date.month, 3)
        self.assertEqual(bride.death.date.day, 1)
        self.assertEqual(bride.death.location, "село Горюхино")
        # Groom's death MUST be unchanged — the after-marker survives.
        self.assertEqual(groom.death.date.date_range, "after")
        self.assertEqual(groom.death.date.year, 1799)
        self.assertEqual(groom.death.date.month, 1)
        self.assertEqual(groom.death.date.day, 9)
        self.assertIsNone(groom.death.location)


class TestConsolidatedUnionMergedComments(unittest.TestCase):
    """Slice 6a: each consolidated `geni_union` resource is preceded by a
    `# Consolidated union with merged unions:` comment block listing the
    per-year source unions that got folded into it. Mirrors legacy
    `Горюхино/generate_config.py:2640-2653` (verbatim format)."""

    def _make_two_birth_records_for_same_father(self):
        return birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
                birth(2, Gender.FEMALE, 12, 13,
                      child=person("Мария"),
                      father=person("Петр", "Сидоров")),
            ),
        )

    def _force_father_consolidated(self, records):
        """Probe the per-year output to learn the father's res_name, then
        return a Consolidation with that res_name diverted to a stable
        consolidated target."""
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1800_birth.tf")
        father_res_names = _re.findall(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_\d+_father)"',
            probe_out,
        )
        assert father_res_names, f"no father profiles in probe:\n{probe_out}"
        return Consolidation(
            profile_move_list={
                fr: "petr_sidorov" for fr in set(father_res_names)
            },
        )

    def test_consolidated_union_emits_merged_comment_header(self):
        records = self._make_two_birth_records_for_same_father()
        consolidation = self._force_father_consolidated(records)

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_unions.tf")

        # Comment header appears above each consolidated union.
        self.assertIn(
            "# Consolidated union with merged unions:\n", output,
        )
        # Two source unions (one per birth record) get listed under one
        # consolidated `petr_sidorov`-keyed union.
        self.assertEqual(
            output.count("# Consolidated union with merged unions:"), 1,
            f"expected one consolidated union; output:\n{output}",
        )
        # Each source union appears as its own `# - {res_name} (...)` line.
        comment_lines = [
            line for line in output.splitlines()
            if line.startswith("# - ")
        ]
        self.assertEqual(
            len(comment_lines), 2,
            f"expected 2 source-union summary lines; got:\n{comment_lines}",
        )
        # Format: `{res_name} (partners: ...; children: ...)`.
        for line in comment_lines:
            self.assertRegex(
                line,
                r"^# - \S+ \(partners: [^;]+(?:; children: .+)?\)$",
                f"malformed summary line: {line!r}",
            )

    def test_merged_comment_children_are_sorted(self):
        """Within a single source-union summary, children are listed
        alphabetically by res_name (legacy uses `sorted(...)`)."""
        records = self._make_two_birth_records_for_same_father()
        consolidation = self._force_father_consolidated(records)
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_unions.tf")

        # Each summary line should have its `children: ...` portion sorted.
        # We extract them and check sortedness.
        for line in output.splitlines():
            if not line.startswith("# - "):
                continue
            m = re.search(r"children: ([^)]+)\)$", line)
            if not m:
                continue
            children = [c.strip() for c in m.group(1).split(",")]
            self.assertEqual(
                children, sorted(children),
                f"children not sorted on line: {line!r}",
            )

    def test_merged_comment_block_appears_above_resource(self):
        """The comment block is emitted directly above the
        `resource "geni_union" "..."` line — not floating somewhere
        else in the file."""
        records = self._make_two_birth_records_for_same_father()
        consolidation = self._force_father_consolidated(records)
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        output = gen.get_output("consolidated_unions.tf")

        # Header line index must immediately precede (modulo intermediate
        # `# - ` lines) the `resource "geni_union" "..."` declaration.
        lines = output.splitlines()
        header_idx = next(
            i for i, line in enumerate(lines)
            if line == "# Consolidated union with merged unions:"
        )
        # Walk forward over `# - ` lines until we hit the resource line.
        i = header_idx + 1
        while i < len(lines) and lines[i].startswith("# - "):
            i += 1
        self.assertTrue(
            lines[i].startswith('resource "geni_union"'),
            f"expected resource line after comment block, got: {lines[i]!r}",
        )


class TestConsolidationKeyLookup(unittest.TestCase):
    """Fix #2: move_list keys often lack a `last_name` token where the DSL's
    generated res_name has one (or vice versa). Bi-directional stripping
    lets the lookup bridge both asymmetries so consolidation fires."""

    def test_profile_with_dsl_lastname_consolidates_when_movelist_key_omits_it(self):
        """Move_list key has no surname; DSL-generated res_name does. The
        fallback lookup should strip the surname token and still hit."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван", last_name_modern_orth="Мижуев"),
                      father=person("Петр", "Сидоров")),
            ),
        )
        # The DSL-generated child res_name contains the `_mizhuev_` token.
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1800_birth.tf")
        m = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_ioann_[^"]*_mk_births_1_child)"',
            probe_out,
        )
        self.assertIsNotNone(m, f"probe failed:\n{probe_out}")
        # move_list key is the SAME shape WITHOUT the `_mizhuev_` token.
        stripped_key = m.group(1).replace("_mizhuev_mk_births_", "_mk_births_")
        self.assertNotEqual(stripped_key, m.group(1),
                            "test fixture must actually differ by a surname token")
        consolidation = Consolidation(
            profile_move_list={stripped_key: "ioann_consolidated"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()

        year_file = gen.get_output("mk_1800_birth.tf")
        consolidated = gen.get_output("consolidated_profiles_1.tf")
        # Child's per-record profile should have been diverted into the
        # consolidated bucket under the alias.
        self.assertNotIn(m.group(1), year_file,
                         "per-record child profile should not appear in year file")
        self.assertIn('resource "geni_profile" "ioann_consolidated"', consolidated)

    def test_profile_without_dsl_lastname_consolidates_when_movelist_key_has_it(self):
        """Symmetric case: DSL Person has no `last_name`; move_list key has
        a surname token baked in. Strip the move_list key to bridge."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1800_birth.tf")
        m = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_ioann_[^"]*_mk_births_1_child)"',
            probe_out,
        )
        self.assertIsNotNone(m, f"probe failed:\n{probe_out}")
        plain_key = m.group(1)
        # move_list key is the same shape WITH an extra surname token
        # between the patronymic and `_mk_`.
        assert "_petrovich_mk_births_" in plain_key, plain_key
        fancy_key = plain_key.replace("_petrovich_mk_births_",
                                       "_petrovich_mizhuev_mk_births_")
        consolidation = Consolidation(
            profile_move_list={fancy_key: "ioann_mizhuev"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()

        year_file = gen.get_output("mk_1800_birth.tf")
        consolidated = gen.get_output("consolidated_profiles_1.tf")
        self.assertNotIn(plain_key, year_file,
                         "per-record child profile should not appear in year file")
        self.assertIn('resource "geni_profile" "ioann_mizhuev"', consolidated)

    def test_consolidation_lookup_collision_falls_back_safely(self):
        """If two different move_list keys strip to the same stripped form
        but point to different targets, the lookup must NOT guess; it falls
        back to no-consolidation for the ambiguous DSL res_name (keeping
        the profile in the per-year file)."""
        # Two fake move_list keys with identical stripped form but different
        # targets: `_{date}_{name}_{patr}_mizhuev_mk_births_1_child` vs
        # `_{date}_{name}_{patr}_smirennikov_mk_births_1_child`. Both strip to
        # `_{date}_{name}_{patr}_mk_births_1_child`.
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров")),
            ),
        )
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        m = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_ioann_petrovich_mk_births_1_child)"',
            probe.get_output("mk_1800_birth.tf"),
        )
        plain_key = m.group(1)
        variant_a = plain_key.replace("_petrovich_mk_births_",
                                      "_petrovich_mizhuev_mk_births_")
        variant_b = plain_key.replace("_petrovich_mk_births_",
                                      "_petrovich_smirennikov_mk_births_")
        consolidation = Consolidation(
            profile_move_list={variant_a: "ioann_a", variant_b: "ioann_b"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()

        year_file = gen.get_output("mk_1800_birth.tf")
        # Ambiguous: neither consolidation target should swallow the profile.
        self.assertIn(plain_key, year_file,
                      "ambiguous lookup must leave the profile in the year file")


class TestConsolidationSpellingAliases(unittest.TestCase):
    """Legacy profile_move_list was generated with the colloquial "illarion_*"
    spelling (double-L). The translator canonicalizes first names via
    names.csv — so Илларион becomes Иларион and the emitted res_name carries
    "ilarion_*". Consolidation must still fire despite the spelling mismatch
    so the profile ends up in the consolidated bucket, not stranded in the
    per-year file."""

    def test_illarion_key_resolves_ilarion_res_name(self):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *birth_month(
                Month.JANUARY,
                birth(1, Gender.MALE, 5, 10,
                      child=person("Петр"),
                      father=person("Илларион", "Данилов")),
            ),
        )
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1820_birth.tf")
        # Translator canonicalizes to "ilarion" (single L) in res_names.
        m = _re.search(
            r'resource "geni_profile" "(_1820_\d\d_\d\d_ilarion_[^"]*_mk_births_1_father)"',
            probe_out,
        )
        self.assertIsNotNone(m, f"probe failed:\n{probe_out}")
        father_res = m.group(1)
        self.assertNotIn("_illarion_", father_res,
                         "fixture expects translator to canonicalize to single-L")
        # Legacy-style move_list key uses "illarion" (double L).
        legacy_key = father_res.replace("ilarion", "illarion")
        self.assertNotEqual(legacy_key, father_res)

        consolidation = Consolidation(
            profile_move_list={legacy_key: "illarion_consolidated"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()

        year_file = gen.get_output("mk_1820_birth.tf")
        consolidated = gen.get_output("consolidated_profiles_1.tf")
        # The per-record father profile should NOT appear in year file.
        self.assertNotIn(father_res, year_file)
        # The consolidated target should be emitted.
        self.assertIn('resource "geni_profile" "illarion_consolidated"', consolidated)

    def test_alias_does_not_overwrite_existing_canonical_key(self):
        """If the move_list already has both the legacy (illarion) AND the
        canonical (ilarion) key pointing at different targets, the canonical
        one must win — the alias expansion must not clobber it."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *birth_month(
                Month.JANUARY,
                birth(1, Gender.MALE, 5, 10,
                      child=person("Петр"),
                      father=person("Илларион", "Данилов")),
            ),
        )
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output("mk_1820_birth.tf")
        m = _re.search(
            r'resource "geni_profile" "(_1820_\d\d_\d\d_ilarion_[^"]*_mk_births_1_father)"',
            probe_out,
        )
        self.assertIsNotNone(m)
        canonical_key = m.group(1)
        legacy_key = canonical_key.replace("ilarion", "illarion")

        consolidation = Consolidation(
            profile_move_list={
                legacy_key: "should_not_win",
                canonical_key: "canonical_winner",
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()
        consolidated = gen.get_output("consolidated_profiles_1.tf")
        self.assertIn('resource "geni_profile" "canonical_winner"', consolidated)
        self.assertNotIn('resource "geni_profile" "should_not_win"', consolidated)


class TestConsolidatedUnions(unittest.TestCase):
    """Fix #1: family/godparent/marriage/death unions whose participants were
    consolidated must be rendered into `consolidated_unions.tf` (merging
    same-partner unions across records), not dropped on the floor."""

    def _one_birth_record(self, year=1800, rec_num=1, day=10, child_name="Иван"):
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            year,
            *birth_month(
                Month.MARCH,
                birth(rec_num, Gender.MALE, day, day + 1,
                      child=person(child_name),
                      father=person("Петр", "Сидоров")),
            ),
        )
        # Probe to learn the auto-generated father res_name.
        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records)
        probe_out = probe.get_output(f"mk_{year}_birth.tf")
        m = _re.search(
            rf'resource "geni_profile" "(_{year}_\d\d_\d\d_[^"]+_mk_births_{rec_num}_father)"',
            probe_out,
        )
        return records, m.group(1)

    def test_family_union_routed_to_consolidated_unions_file_when_parent_consolidated(self):
        """When the father is consolidated, the per-record family union must
        appear in `consolidated_unions.tf` (not per-year, not dropped)."""
        records, father_res = self._one_birth_record()
        consolidation = Consolidation(
            profile_move_list={father_res: "petr_consolidated"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()

        year_file = gen.get_output("mk_1800_birth.tf")
        cu = gen.get_output("consolidated_unions.tf")

        # Per-year still excludes the family union.
        self.assertNotIn("_family", year_file)
        # Consolidated unions file contains a union keyed by the consolidated
        # partner name (no partner_2 means res_name = partner_1).
        self.assertIn('resource "geni_union" "petr_consolidated"', cu)
        self.assertIn('geni_profile.petr_consolidated.id,', cu)

    def test_aux_godparent_union_skipped_when_neither_participant_consolidated(self):
        """The aux godparent-parent union (legacy `god_parent_rel`) is only
        emitted when at least one participant is consolidated — in that
        case it lands in `consolidated_unions.tf`. When neither the
        anchor parent nor the godparent are on the consolidation list,
        legacy skips the aux union entirely (no stray `_and_`-shaped
        per-year union). Translator must do the same."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1806,
            *birth_month(
                Month.FEBRUARY,
                birth(3, Gender.MALE, 1, 2,
                      child=person("Павел"),
                      father=person("Юстин", "Савельев"),
                      god_parent1=person("Нил", "Савельев")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)  # no consolidation
        gen.add_birth_records(records)
        gen.finalize()
        year_file = gen.get_output("mk_1806_birth.tf")
        cu = gen.get_output("consolidated_unions.tf")

        # The family union (father + child) is still there.
        self.assertIn('resource "geni_union" "iustin_savelevich__3_1806"', year_file)
        # No aux `_and_nil_savelevich_` union in the per-year file.
        self.assertNotIn("_and_nil_savelevich_", year_file)
        # And none in consolidated either (no profile is consolidated).
        self.assertNotIn("_and_nil_savelevich_", cu)

    # `test_godparent_union_routed_to_consolidated_unions_file` removed
    # — it was validating a spurious `<father>_and_<godparent>` aux
    # union that legacy never emits (legacy only emits `god_parent_rel`
    # unions when an explicit relative-of-godparent reference exists in
    # the source row, and even then the relative is partner_1, not the
    # parent). The aux loop in `tf_translator.py:add_birth_records` was
    # removed; see `test_no_aux_godparent_parent_union_without_relative_ref`
    # in `TestMergeConsolidatedEvents` for the regression test.

    def test_repeat_unions_same_partners_merge_children(self):
        """Two birth records with the same consolidated father produce a
        single entry in `consolidated_unions.tf` whose `children` set contains
        BOTH children (not two separate unions)."""
        import re as _re

        records_both = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Алексей"),
                      father=person("Петр", "Сидоров")),
                birth(2, Gender.MALE, 20, 21,
                      child=person("Борис"),
                      father=person("Петр", "Сидоров")),
            ),
        )
        # Both records share the same father — same father res_name.
        probe = TerraformGenerator(village_dir=None)
        probe.add_birth_records(records_both)
        m = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_1_father)"',
            probe.get_output("mk_1800_birth.tf"),
        )
        father_res_1 = m.group(1)
        m2 = _re.search(
            r'resource "geni_profile" "(_1800_\d\d_\d\d_[^"]+_mk_births_2_father)"',
            probe.get_output("mk_1800_birth.tf"),
        )
        father_res_2 = m2.group(1)
        consolidation = Consolidation(
            profile_move_list={
                father_res_1: "petr_consolidated",
                father_res_2: "petr_consolidated",
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records_both)
        gen.finalize()

        cu = gen.get_output("consolidated_unions.tf")
        # Exactly one union resource for petr_consolidated.
        self.assertEqual(
            cu.count('resource "geni_union" "petr_consolidated"'), 1,
            f"expected one merged union, got:\n{cu}",
        )
        # Both children must appear in the children list.
        self.assertIn("aleksij_petrovich", cu)
        self.assertIn("boris_petrovich", cu)

    def test_union_move_list_v2_override_uses_target_res_name(self):
        """When a per-record union's res_name is in `union_move_list_v2`,
        that override name is used as the target in consolidated_unions.tf.
        """
        records, father_res = self._one_birth_record()
        # Compute the per-record family union res_name so we can override it.
        from verso.ru.naming.transliteration import generate_res_name
        src_union = generate_res_name("Петр Сидорович  1 1800")
        consolidation = Consolidation(
            profile_move_list={father_res: "petr_consolidated"},
            union_move_list_v2={src_union: "petr_and_ivanovna"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_birth_records(records)
        gen.finalize()

        cu = gen.get_output("consolidated_unions.tf")
        self.assertIn('resource "geni_union" "petr_and_ivanovna"', cu,
                      f"override should pick the v2 target name; got:\n{cu}")


class TestMarriageTranslation(unittest.TestCase):
    def test_marriage_emits_groom_bride_witnesses_and_union(self):
        records = marriage_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         witness1=person("Сергей", "Алексеев"),
                         witness2=person("Федор", "Тимофеев")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # 4 profiles: groom, bride, witness_1, witness_2
        self.assertEqual(output.count('resource "geni_profile"'), 4,
                         f"expected 4 profiles; output:\n{output}")
        # 1 marriage union (groom + bride)
        self.assertEqual(output.count('resource "geni_union"'), 1,
                         f"expected one union; output:\n{output}")
        self.assertIn("mk_marriages_1_groom", output)
        self.assertIn("mk_marriages_1_bride", output)
        self.assertIn("mk_marriages_1_witness_1", output)
        self.assertIn("mk_marriages_1_witness_2", output)

    def test_partner_birth_uses_age_for_precise_circa_year(self):
        """When `groom_age` / `bride_age` are supplied, partner profile
        `birth = { date = { circa = true; year = <marriage-year - age> } }`
        — single precise circa year, NOT the wide between-range fallback.
        Pins the legacy precision for re-imported pre-1840s marriages."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1773,
            *marriage_month(
                Month.JANUARY,
                marriage(3, 22,
                         groom=person("Макар", "Яковлев"), groom_age=19,
                         bride=person("Дарья", "Власова"), bride_age=16),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1773_marriage.tf")

        # Groom: birth = circa true, year = 1754 (1773 - 19). NO range.
        # The old patronymic Яковлев is rendered in the modern form
        # Яковлевич, so the res_name uses
        # `jakovlevich`.
        groom_block = output.split('"_1773_01_22_makarij_jakovlevich_mk_marriages_3_groom"', 1)[1]
        groom_block = groom_block.split("}\n}", 1)[0]
        groom_birth = groom_block.split("birth = {", 1)[1].split("death = {", 1)[0]
        self.assertRegex(groom_birth, r"circa\s*=\s*true")
        self.assertRegex(groom_birth, r"year\s*=\s*1754")
        self.assertNotIn("range", groom_birth)

        # Bride: birth = circa true, year = 1757 (1773 - 16).
        bride_block = output.split('"_1773_01_22_darija_vlasovna_mk_marriages_3_bride"', 1)[1]
        bride_block = bride_block.split("}\n}", 1)[0]
        bride_birth = bride_block.split("birth = {", 1)[1].split("death = {", 1)[0]
        self.assertRegex(bride_birth, r"year\s*=\s*1757")
        self.assertNotIn("range", bride_birth)

        # Document text body: trailing age on Жених/Невеста lines.
        self.assertIn("Жених: Макарий Яковлевич 19", output)
        self.assertIn("Невеста: Дария Власовна 16", output)

    def test_partner_birth_handles_age_with_months(self):
        """When age is supplied as `"X лет Y мес"`, the fractional months
        must be honored so the birth year is correct relative to the
        wedding month/day. Regression: an 18y6m groom at a January 1915
        wedding was born ~July 1896, NOT 1897 — the prior code did
        `int(year) - int(age_years)` which truncated 18.5 to 18.
        """
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1915,
            *marriage_month(
                Month.JANUARY,
                marriage(21, 24,
                         groom=person("Тихон", "Васильев",
                                      last_name_orig="Свистунов"),
                         groom_age="18 лет 6 мес",
                         bride=person("Анна", "Лукина",
                                      last_name_orig="Тюфякина"),
                         bride_age=20),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1915_marriage.tf")

        # Groom: 1915-01-24 minus 18y6m = 1896-07-24, so birth year 1896.
        groom_block = output.split(
            '"_1915_01_24_tihon_vasilevich_svistunov_mk_marriages_21_groom"', 1)[1]
        groom_block = groom_block.split("}\n}", 1)[0]
        groom_birth = groom_block.split("birth = {", 1)[1].split("death = {", 1)[0]
        self.assertRegex(groom_birth, r"year\s*=\s*1896")
        self.assertNotRegex(groom_birth, r"year\s*=\s*1897")

        # Bride: 20y, 1915-01-24 minus 20y = 1895-01-24, birth year 1895.
        bride_block = output.split(
            '"_1915_01_24_anna_lukinichna_svistunova_mk_marriages_21_bride"', 1)[1]
        bride_block = bride_block.split("}\n}", 1)[0]
        bride_birth = bride_block.split("birth = {", 1)[1].split("death = {", 1)[0]
        self.assertRegex(bride_birth, r"year\s*=\s*1895")

    def test_marriage_doc_body_splits_komm_and_pometki(self):
        """Legacy marriage document text body puts 'Комментарий: Имена
        в МК: ...' and 'Пометки: {notes}' on separate lines. Translator
        previously concatenated them with '; ' into one line."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1832,
            *marriage_month(
                Month.JANUARY,
                marriage(3, 10,
                         groom=person("Лазарь", "Тихонов"),
                         bride=person("Агриппина", "Макарова"),
                         comment="Агриппина Макарова Манилова - отец указан как покойный"),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1832_marriage.tf")

        # Two separate lines in the document text body.
        self.assertIn("Комментарий: Имена в МК: Лазарь Тихонов; Агриппина Макарова", output)
        self.assertIn("Пометки: Агриппина Макарова Манилова - отец указан как покойный",
                      output)
        # Never combined into one 'Комментарий:' line with '; ' separator.
        self.assertNotIn(
            "Комментарий: Агриппина Макарова Манилова - отец указан как покойный; Имена в МК",
            output,
        )

    def test_marriage_imena_v_mk_includes_relatives(self):
        """Relatives attached to a marriage (e.g. bride's father) must appear
        in the 'Комментарий: Имена в МК:' line of the document text body.
        Previously `add_marriage_records` omitted `m.relatives` from the
        `_names_in_mk(...)` call, so the relative's name was silently dropped."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *marriage_month(
                Month.DECEMBER,
                marriage(17, 9,
                         groom=person("Климонт", "Лаврентьев"),
                         bride=person("Агафья", "Тимонова"),
                         relatives=[Relative(person("Тимон", "Лазарев"),
                                             Relationship.FATHER,
                                             relationship_ref="невеста")]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        self.assertIn("Тимон Лазарев", output)
        # Verify it's on the Имена в МК line specifically.
        for line in output.splitlines():
            if "Имена в МК" in line:
                self.assertIn("Тимон Лазарев", line,
                              "Тимон Лазарев must appear on the Имена в МК line")
                break

    def test_witness_profile_has_about_death_birth_and_residence(self):
        """Legacy marriage witness profiles carry:
          - current_residence (from person.residence)
          - birth = { between, year-60 to year-17, circa, end_circa }
          - death = { range = "after" } at the marriage date
          - about = "<strong>МК X Y:</strong> поручитель на свадьбе"
            + optional Титул/звание + optional comment.
        Translator previously emitted only the base profile."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1832,
            *marriage_month(
                Month.JANUARY,
                marriage(3, 10,
                         groom=person("Лазарь", "Тихонов"),
                         bride=person("Агриппина", "Макарова"),
                         witness1=person("Захар", "Борисов",
                                         residence="Скотопригоньевск",
                                         status="коллежский регистратор")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1832_marriage.tf")

        block = _extract_resource_block(
            output, "_1832_01_10_zaharija_borisovich_mk_marriages_3_witness_1",
        )
        # Residence carried through.
        self.assertIn("current_residence", block)
        self.assertIn("Скотопригоньевск", block)
        # Birth between year-60 and year-17, circa.
        self.assertIn("birth = {", block)
        self.assertIn('range     = "between"', block)
        self.assertIn("year      = 1772", block)  # 1832-60
        self.assertIn("end_year  = 1815", block)  # 1832-17
        # Death "after" at marriage date.
        self.assertIn("death = {", block)
        self.assertIn('range = "after"', block)
        self.assertIn("day   = 10", block)
        self.assertIn("year  = 1832", block)
        # About block.
        self.assertIn("about = {", block)
        self.assertIn("<strong>МК Горюхино 1832:</strong> поручитель на свадьбе", block)
        self.assertIn("Титул/звание: коллежский регистратор", block)

    def test_marriage_emits_geni_document(self):
        records = marriage_records(
            "ГАТО (Тамбов)", "2041", "94", "8", "Горюхино", "Никольская",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(2, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         witness1=person("Сергей", "Алексеев"),
                         witness2=person("Федор", "Тимофеев"),
                         page="87"),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # A geni_document resource is emitted for the marriage.
        self.assertIn('resource "geni_document"', output)
        # res_name format: `Marriage of {groom_first} {groom_middle} and {bride_first} {bride_middle} {record} {year}`
        # passed through generate_res_name.
        self.assertIn('"marriage_of_ioann_petrovich_and_marija_ivanovna_m2_1810"', output)
        # Marriage label + date.
        self.assertIn('labels = [', output)
        self.assertIn('"Marriage"', output)
        self.assertIn('day   = 15', output)
        self.assertIn('month = 1', output)
        self.assertIn('year  = 1810', output)
        # References groom, bride, and both witness profiles by id.
        self.assertIn('geni_profile._1810_01_15_ioann_petrovich_mk_marriages_2_groom.id', output)
        self.assertIn('geni_profile._1810_01_15_marija_ivanovna_mk_marriages_2_bride.id', output)
        self.assertIn('geni_profile._1810_01_15_sergij_alekseevich_mk_marriages_2_witness_1.id', output)
        self.assertIn('geni_profile._1810_01_15_feodor_timofeevich_mk_marriages_2_witness_2.id', output)
        # Description contains Лист from page="87" and № записи.
        self.assertIn("Лист: 87", output)
        self.assertIn("№ записи: 2", output)

    def test_marriage_union_carries_marriage_event_with_date_and_location(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(2, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # The geni_union for this marriage has a marriage = {...} event block.
        self.assertIn("marriage = {", output)
        self.assertIn("day   = 15", output)
        self.assertIn("month = 1", output)
        self.assertIn("year  = 1810", output)
        self.assertIn("село Горюхино", output)

    def test_marriage_does_not_emit_clergy_profiles(self):
        """Clergy carried on a marriage record must NOT materialize as
        geni_profile resources — matches legacy byte-parity (no clergy
        profiles anywhere in legacy output)."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         priest=person("Василий", "Петров"),
                         deacon=person("Иван", "Герасимов")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        self.assertNotIn("_priest", output)
        self.assertNotIn("_deacon", output)
        self.assertNotIn("_dyachok", output)
        self.assertNotIn("_sexton", output)

    def test_marriage_emits_relative_profiles(self):
        records = marriage_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         relatives=[
                             Relative(person("Анна", "Иванова"),
                                      Relationship.MOTHER),
                         ]),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        self.assertIn("mk_marriages_1_rel_1", output)
        self.assertIn("_1810_01_15_anna_ivanovna_mk_marriages_1_rel_1", output)

    def test_groom_and_bride_profiles_fully_enriched(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров",
                                      residence="Неелово", status="солдат"),
                         groom_age=25,
                         bride=person("Мария", "Иванова",
                                      residence="Горюхино", status="девка"),
                         bride_age=None),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # --- Groom profile ---
        import re as _re
        groom_match = _re.search(
            r'resource "geni_profile" "_1810_01_15_[^"]+_mk_marriages_1_groom"\s*{(.+?)\n}\n\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(groom_match, f"no groom profile block; output:\n{output}")
        groom_body = groom_match.group(1)
        # Residence lookup via locations[…] — Неелово needs to be among the corpus's places.
        # In case it isn't, we still require the current_residence BLOCK to exist.
        self.assertIn("current_residence = {", groom_body)
        # Birth event: single circa year when age known: 1810 - 25 = 1785.
        self.assertIn("birth = {", groom_body)
        self.assertIn("circa = true", groom_body)
        self.assertIn("year  = 1785", groom_body)
        # Death event: "after" the wedding date.
        self.assertIn('range = "after"', groom_body)
        self.assertIn("day   = 15", groom_body)
        self.assertIn("month = 1", groom_body)
        self.assertIn("year  = 1810", groom_body)
        # About block: role = жених, then the recorded age, then status line.
        self.assertIn("<strong>МК Горюхино 1810:</strong> жених", groom_body)
        self.assertIn(
            "жених\n        Возраст: 25 лет\n        Титул/звание: солдат",
            groom_body,
        )

        # --- Bride profile ---
        bride_match = _re.search(
            r'resource "geni_profile" "_1810_01_15_[^"]+_mk_marriages_1_bride"\s*{(.+?)\n}\n\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(bride_match, f"no bride profile block; output:\n{output}")
        bride_body = bride_match.group(1)
        # Birth event: unknown age → "between" range 1810-60 .. 1810-13.
        self.assertIn('range     = "between"', bride_body)
        self.assertIn("year      = 1750", bride_body)
        self.assertIn("end_year  = 1797", bride_body)
        self.assertIn("end_circa = true", bride_body)
        # About block: role = невеста, status line. Age unknown → no Возраст line.
        self.assertIn("<strong>МК Горюхино 1810:</strong> невеста", bride_body)
        self.assertIn("Титул/звание: девка", bride_body)
        self.assertNotIn("Возраст:", bride_body)

    def test_marriage_union_skipped_when_groom_is_consolidated(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова")),
            ),
        )

        import re as _re
        probe = TerraformGenerator(village_dir=None)
        probe.add_marriage_records(records)
        match = _re.search(
            r'resource "geni_profile" "(_1810_\d\d_\d\d_[^"]+_mk_marriages_1_groom)"',
            probe.get_output("mk_1810_marriage.tf"),
        )
        self.assertIsNotNone(match)
        groom_res = match.group(1)
        consolidation = Consolidation(profile_move_list={groom_res: "ioann_petrovich"})

        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_marriage_records(records)
        gen.finalize()
        year_tf = gen.get_output("mk_1810_marriage.tf")
        consolidated_tf = gen.get_output("consolidated_profiles_1.tf")

        # No per-record union in the year file when groom is consolidated.
        self.assertEqual(year_tf.count('resource "geni_union"'), 0,
                         f"expected NO marriage union; output:\n{year_tf}")
        # Consolidated profile landed.
        self.assertIn('resource "geni_profile" "ioann_petrovich"', consolidated_tf)

    def test_marriage_document_res_name_and_text_match_legacy_format(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров",
                                      residence="Неелово", status="солдат"),
                         groom_age=25,
                         bride=person("Мария", "Иванова",
                                      residence="Горюхино", status="девка")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # Document res_name uses m{record_num} prefix.
        self.assertIn('"marriage_of_ioann_petrovich_and_marija_ivanovna_m1_1810"', output)
        # Description and title keep the village; only the text body's first
        # line drops it (legacy quirk).
        self.assertIn("Метрическая книга Горюхино 1810: брак", output)  # in title/description
        import re as _re
        text_block = _re.search(r"text\s*=\s*<<-EOT\n(.+?)\n\s*EOT", output, _re.DOTALL)
        self.assertIsNotNone(text_block, f"no text block; output:\n{output}")
        text_body = text_block.group(1)
        self.assertIn("Метрическая книга 1810: брак", text_body)
        self.assertNotIn("Метрическая книга Горюхино 1810: брак", text_body)
        self.assertIn("Дата венчания: 15.1.1810", text_body)
        # Жених: status + name + (residence!=parish) + age.
        self.assertIn("Жених: солдат Иоанн Петрович (Неелово) 25", output)
        # Невеста: status + name, residence matches parish so no parens, no age.
        self.assertIn("Невеста: девка Мария Ивановна", output)
        self.assertNotIn("Невеста: девка Мария Ивановна (Горюхино)", output)

    def test_neelovo_residence_adds_neelovo_project_to_profile(self):
        """Legacy appends `data.geni_project.neelovo.id` to a profile's
        `projects` list when that person's residence contains "Неелов"
        (matching Неелово / Неелова etc.). Other profiles in the same
        record keep only the base projects."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *marriage_month(
                Month.APRIL,
                marriage(8, 24,
                         groom=person("Гордей", "Игнатьев",
                                      residence="Горюхино"),
                         bride=person("Евдокия", "Леонтьева",
                                      residence="Неелово")),
            ),
        )
        projects = [
            "data.geni_project.automatic_upload.id",
            "data.geni_project.gorjuhino.id",
        ]
        gen = TerraformGenerator(
            village_dir=None,
            projects=projects,
            extra_project_rules={"Неелов": "data.geni_project.neelovo.id"},
        )
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # Bride lives in Неелово — her profile picks up the extra project.
        import re as _re
        bride_match = _re.search(
            r'resource "geni_profile" "_1810_04_24_[^"]+_mk_marriages_8_bride"\s*{(.+?)\n}\n\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(bride_match)
        self.assertIn("data.geni_project.neelovo.id", bride_match.group(1))

        # Groom lives in Горюхино (the parish) — no neelovo project.
        groom_match = _re.search(
            r'resource "geni_profile" "_1810_04_24_[^"]+_mk_marriages_8_groom"\s*{(.+?)\n}\n\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(groom_match)
        self.assertNotIn("data.geni_project.neelovo.id", groom_match.group(1))

    def test_unknown_day_with_known_month_still_pads_month(self):
        """When only the day is unknown, the month must stay zero-padded
        (e.g. `_1754_09_maksim...`). Previous logic triggered the except
        branch on day=None and dropped the month's leading zero, producing
        `_1754_9_maksim...` — that broke consolidation lookups on legacy
        res_names like `_1754_09_01_maksim_petrovich_mk_deaths_612_deceased`.
        """
        name = generate_res_name_2(
            year=1754, month=9, day=None,
            first_name="Максим", middle_name="Петрович",
            document_name="mk_deaths", role="deceased", record_number=612,
        )
        self.assertIn("_1754_09_", name)
        self.assertNotIn("_1754_9_", name)

    def test_unknown_month_collapses_in_res_name_matching_legacy(self):
        """When w_month is None, the legacy CSV pipeline passed an empty
        string → the int() cast failed → the fallthrough branch produced
        `_YYYY__DD_...` which `re.sub(r"__+", "_")` collapses to
        `_YYYY_DD_...`. Our translator must match the same collapse so
        consolidation lookups (keyed on legacy res_names) still hit."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1796,
            *[marriage(4, 12,
                       groom=person("Иван", "Пахомов"),
                       bride=person("Ирина", "Герасимова"))],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1796_marriage.tf")

        # Collapsed form (legacy): `_1796_12_...`
        self.assertIn("_1796_12_ioann_pahomovich_mk_marriages_4_groom", output)
        # Stale uncollapsed form: `_1796_00_12_...`
        self.assertNotIn("_1796_00_12_ioann_pahomovich", output)

    def test_marriage_records_emit_in_record_num_then_chronological_order(self):
        """Marriage records sort by (year, record_num, chronological) — the
        per-month record_num is the primary key, chronology the tiebreaker.
        (The historical CSV book-global «№ п/п» override was removed.)"""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *marriage_month(
                Month.MARCH,
                marriage(3, 5,
                         groom=person("Петр", "Иванов"),
                         bride=person("Мария", "Петрова")),
            ),
            *marriage_month(
                Month.JANUARY,
                marriage(2, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Анна", "Кузьмина")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)  # no overrides
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")
        # Jan resource should emit before March resource (chronological).
        jan_idx = output.index("_1810_01_15_ioann_petrovich")
        mar_idx = output.index("_1810_03_05_petr_ivanovich")
        self.assertLess(jan_idx, mar_idx)

    def test_marriages_emitted_in_chronological_order(self):
        """Marriages sort chronologically regardless of DSL declaration
        order — same pattern as births."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *marriage_month(
                Month.JUNE,
                marriage(5, 15,
                         groom=person("Петр", "Иванов"),
                         bride=person("Марья", "Иванова")),
            ),
            *marriage_month(
                Month.JANUARY,
                marriage(1, 10,
                         groom=person("Иван", "Петров"),
                         bride=person("Анна", "Петрова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1800_marriage.tf")

        pos_jan = output.find("_1800_01_10_ioann_petrovich_mk_marriages_1_groom")
        pos_jun = output.find("_1800_06_15_petr_ivanovich_mk_marriages_5_groom")
        self.assertGreater(pos_jan, -1)
        self.assertGreater(pos_jun, -1)
        self.assertLess(pos_jan, pos_jun)

    def test_marriage_union_res_name_collapses_double_spaces(self):
        """When groom/bride have no last_name, the joined "{first} {middle}
        {last}" string contains empty slots that must not leave double
        underscores in the final res_name (legacy calls .replace("  ", " "))."""
        records = marriage_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1773,
            *marriage_month(
                Month.JANUARY,
                marriage(3, 22,
                         groom=person("Макар", "Яковлев"),
                         bride=person("Дарья", "Власова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1773_marriage.tf")

        # Correct (legacy) form: single underscores between tokens.
        # The old patronymic Яковлев is rendered in the modern form
        # Яковлевич, so the union res_name uses
        # `jakovlevich`.
        self.assertIn(
            'resource "geni_union" "makarij_jakovlevich_and_darija_vlasovna_m3_1773"',
            output,
        )
        # Must NOT contain double-underscore artefacts from empty last_name slots.
        self.assertNotIn("makarij_jakovlevich__and", output)
        self.assertNotIn("vlasovna__m3_1773", output)

    def test_bride_takes_groom_surname_bride_profile_uses_married_surname(self):
        """When `bride_takes_groom_surname=True`, the bride's per-record
        profile carries her MARRIED surname as `last_name` (feminized
        groom surname) and her maiden surname as `birth_last_name`. The
        res_name embeds the married form so it matches legacy's
        consolidation key."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1832,
            *marriage_month(
                Month.JANUARY,
                marriage(3, 10,
                         groom=person("Лазарь", "Тихонов",
                                      last_name_orig="Пеночкин"),
                         bride=person("Агриппина", "Макарова",
                                      last_name_orig="Манилова"),
                         bride_takes_groom_surname=True),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1832_marriage.tf")

        # Bride profile res_name embeds MARRIED surname (Пеночкина).
        self.assertIn(
            '"_1832_01_10_agripina_makarovna_penochkina_mk_marriages_3_bride"',
            output,
        )
        # And does NOT use the maiden form in the bride's own profile id.
        self.assertNotIn(
            '"_1832_01_10_agripina_makarovna_manilova_mk_marriages_3_bride"',
            output,
        )
        # Inside the bride's profile block: last_name=Пеночкина,
        # birth_last_name=Манилова.
        import re as _re
        bride_block = _re.search(
            r'resource "geni_profile" "_1832_01_10_agripina_makarovna_penochkina_mk_marriages_3_bride"\s*{(.+?)\n}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(bride_block, f"no bride profile in:\n{output}")
        block = bride_block.group(1)
        self.assertIn('last_name   = "Пеночкина"', block)
        self.assertIn('birth_last_name = "Манилова"', block)

    def test_bride_takes_groom_surname_document_keeps_maiden_surname(self):
        """Even when the bride profile switches to the married surname, the
        document res_name, union res_name, title and `Невеста:` partner line
        must stay with the MAIDEN surname — legacy identifies the wedding by
        the names the partners had *at* the wedding."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1832,
            *marriage_month(
                Month.JANUARY,
                marriage(3, 10,
                         groom=person("Лазарь", "Тихонов",
                                      last_name_orig="Пеночкин"),
                         bride=person("Агриппина", "Макарова",
                                      last_name_orig="Манилова",
                                      status="дочь девица помещика"),
                         bride_takes_groom_surname=True),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1832_marriage.tf")

        # Document res_name uses MAIDEN (Манилова), not married (Пеночкина).
        self.assertIn(
            '"marriage_of_lazar_tihonovich_penochkin_and_agripina_makarovna_manilova_m3_1832"',
            output,
        )
        self.assertNotIn(
            '"marriage_of_lazar_tihonovich_penochkin_and_agripina_makarovna_penochkina_m3_1832"',
            output,
        )
        # Union res_name matches the maiden form too.
        self.assertIn(
            'resource "geni_union" "lazar_tihonovich_penochkin_and_agripina_makarovna_manilova_m3_1832"',
            output,
        )
        # Document title uses MAIDEN.
        self.assertIn(
            "брак Лазарь Тихонович Пеночкин и Агрипина Макаровна Манилова",
            output,
        )
        # Невеста: line uses MAIDEN.
        self.assertIn(
            "Невеста: дочь девица помещика Агрипина Макаровна Манилова",
            output,
        )
        self.assertNotIn(
            "Невеста: дочь девица помещика Агрипина Макаровна Пеночкина",
            output,
        )

    def test_bride_takes_groom_surname_without_maiden_renders_no_surname(self):
        """When the bride has no maiden surname in DSL (peasant bride with
        just a patronymic), setting `bride_takes_groom_surname=True` must
        still render the document context WITHOUT any surname — the book
        only recorded her as Дарья Васильевна. The flag MUST NOT leak the
        married surname into the document text."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1837,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 10,
                         groom=person("Исидор", "Иванов",
                                      last_name_orig="Пустомелев"),
                         bride=person("Дарья", "Васильева",
                                      status="девица из ясачных крестьян"),
                         bride_takes_groom_surname=True),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1837_marriage.tf")

        # Document res_name has no bride surname (no `_pustomeleva_`).
        self.assertIn(
            '"marriage_of_isidor_ivanovich_pustomelev_and_darija_vasilevna_m1_1837"',
            output,
        )
        self.assertNotIn("_darija_vasilevna_pustomeleva_m1_", output)
        # Title: bride shows only name+patronymic — "и Дарья Васильевна" must
        # be followed by something other than "Пустомелева".
        self.assertIn(
            "брак Исидор Иванович Пустомелев и Дария Васильевна\n",
            output,
        )
        self.assertNotIn(
            "брак Исидор Иванович Пустомелев и Дария Васильевна Пустомелева",
            output,
        )
        # Невеста: line shows no surname.
        self.assertIn(
            "Невеста: девица из ясачных крестьян Дария Васильевна\n",
            output,
        )
        self.assertNotIn(
            "Невеста: девица из ясачных крестьян Дария Васильевна Пустомелева",
            output,
        )

    def test_bride_flag_true_but_groom_has_no_surname_moves_to_birth_last_name(self):
        """Edge case: the flag is set but the groom has no surname on record.
        The bride's surname comes from her father (last_name_in_book=False or
        deduced from a relative), so it is necessarily her MAIDEN surname.
        Profile: last_name empty, birth_last_name=maiden. Document context
        keeps the maiden surname — that's what she was called at the wedding."""
        records = marriage_records(
            "A", "1", "1", "1", "Неелово", "N",
            1835,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Артемий", "Васильев"),
                         bride=person("Дарья", "Герасимова",
                                      last_name_orig="Прорехина",
                                      status="девица из ясачных крестьян"),
                         bride_takes_groom_surname=True),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1835_marriage.tf")

        # Bride profile res_name has NO surname suffix (last_name is empty;
        # the maiden surname goes to birth_last_name, not into res_name).
        self.assertIn(
            '"_1835_01_20_darija_gerasimovna_mk_marriages_1_bride"',
            output,
        )
        self.assertNotIn(
            '"_1835_01_20_darija_gerasimovna_prorehina_mk_marriages_1_bride"',
            output,
        )
        # Inside the bride profile: birth_last_name=Прорехина, no last_name.
        import re as _re
        bride_block = _re.search(
            r'resource "geni_profile" "_1835_01_20_darija_gerasimovna_mk_marriages_1_bride"\s*{(.+?)\n}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(bride_block, f"no bride profile in:\n{output}")
        block = bride_block.group(1)
        self.assertIn('birth_last_name = "Прорехина"', block)
        self.assertIn('birth_last_name = "Prorehina"', block)
        # No `last_name = "..."` (would have been her maiden under old logic).
        self.assertNotRegex(block, r'\blast_name\s+=\s+"[^"]')
        # Document title still includes bride's maiden — that's what was
        # recorded in the wedding book.
        self.assertIn(
            "брак Артемий Васильевич и Дария Герасимовна Прорехина",
            output,
        )
        # Невеста line keeps the surname too.
        self.assertIn(
            "Невеста: девица из ясачных крестьян Дария Герасимовна Прорехина",
            output,
        )

    def test_bride_flag_explicit_false_keeps_maiden_everywhere(self):
        """DSL can opt out of the default with `bride_takes_groom_surname=False`.
        The bride profile, document, and union must all use her maiden
        (as-DSL) surname — no feminize-from-groom override."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Петр", "Иванов",
                                      last_name_orig="Сидоров"),
                         bride=person("Мария", "Петрова",
                                      last_name_orig="Иванова"),
                         bride_takes_groom_surname=False),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        # Bride profile keeps her own surname.
        self.assertIn(
            '"_1820_01_20_marija_petrovna_ivanova_mk_marriages_1_bride"',
            output,
        )
        import re as _re
        bride_block = _re.search(
            r'resource "geni_profile" "_1820_01_20_marija_petrovna_ivanova_mk_marriages_1_bride"\s*{(.+?)\n}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(bride_block)
        block = bride_block.group(1)
        self.assertIn('last_name   = "Иванова"', block)
        # No birth_last_name (flag is off, so override doesn't fire).
        self.assertNotIn("birth_last_name", block)
        # Document res_name / title / Невеста line all use her own surname.
        self.assertIn(
            '"marriage_of_petr_ivanovich_sidorov_and_marija_petrovna_ivanova_m1_1820"',
            output,
        )
        self.assertIn("и Мария Петровна Иванова", output)

    def test_page_question_mark_treated_as_absent_in_document(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         page="?"),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # "?" is a placeholder — no Лист line should appear at all.
        self.assertNotIn("Лист: ?", output)
        self.assertNotIn("Лист:?", output)

    def test_marriage_emits_six_witnesses_when_provided(self):
        """A marriage with witness1..witness6 emits six witness profiles
        and lists Свидетель 1..6 in the document text body."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1810,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 15,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         witness1=person("Сергей", "Алексеев"),
                         witness2=person("Федор", "Тимофеев"),
                         witness3=person("Михаил", "Ионин"),
                         witness4=person("Климент", "Филипов"),
                         witness5=person("Василий", "Кондратьев"),
                         witness6=person("Давид", "Сидоров")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1810_marriage.tf")

        # 8 profiles: groom, bride, witness_1..witness_6
        self.assertEqual(output.count('resource "geni_profile"'), 8,
                         f"expected 8 profiles; output:\n{output}")
        self.assertIn("mk_marriages_1_witness_5", output)
        self.assertIn("mk_marriages_1_witness_6", output)
        # Document text body lists all six witness lines.
        self.assertIn("Свидетель 5:", output)
        self.assertIn("Свидетель 6:", output)
        # "Имена в МК" string includes all six witness names.
        self.assertIn("Василий Кондратьев", output)
        self.assertIn("Давид Сидоров", output)

    def test_marriage_per_record_village_overrides_parish_location(self):
        """marriage(village=..., church=...) overrides records-level village
        for parish_location, document title, and `Имена в МК`-style
        about/text strings."""
        records = marriage_records(
            "A", "1", "1", "1", "Пробкино", "Христорождественская",
            1815,
            *marriage_month(
                Month.FEBRUARY,
                marriage(5, 9,
                         village="Неелово", church="Покровская",
                         groom=person("Иван", "Казмин",
                                      residence="Ротозеево"),
                         bride=person("Федосья", "Макарова",
                                      residence="Горюхино")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1815_marriage.tf")

        # Document title and description carry the per-record village.
        self.assertIn("Метрическая книга Неелово 1815: брак", output)
        # The geni_document.location renders Неелово's location block.
        self.assertIn("село Неелово", output)
        self.assertIn("Захудаловский уезд", output)
        # The records-level village does NOT leak into the document title.
        self.assertNotIn("Метрическая книга Пробкино 1815: брак", output)

    def test_marriage_per_record_village_does_not_affect_siblings(self):
        """When only one marriage in a records group sets village=, siblings
        keep the records-level village."""
        records = marriage_records(
            "A", "1", "1", "1", "Пробкино", "Христорождественская",
            1815,
            *marriage_month(
                Month.FEBRUARY,
                marriage(13, 17,
                         groom=person("Мартын", "Игнатов"),
                         bride=person("Агафья", "Власова")),
                marriage(5, 9,
                         village="Неелово", church="Покровская",
                         groom=person("Иван", "Казмин"),
                         bride=person("Федосья", "Макарова")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1815_marriage.tf")

        # Both per-village titles appear (one per record).
        self.assertIn("Метрическая книга Пробкино 1815: брак", output)
        self.assertIn("Метрическая книга Неелово 1815: брак", output)


class TestMarriageParents(unittest.TestCase):
    """Slice 4: marriage records carrying a FATHER relative tagged with
    `relationship_ref="жених"` / `"невеста"` emit a male profile plus a
    father-child `bf` union."""

    def test_groom_father_emits_profile_and_family_union(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         relatives=[
                             Relative(person("Петр", "Алексеев",
                                             residence="Брехаловка",
                                             status="ясачный крестьянин"),
                                      Relationship.FATHER, "жених"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        # 3 profiles: groom, bride, groom_father (NOT a generic rel_1).
        self.assertEqual(output.count('resource "geni_profile"'), 3,
                         f"expected 3 profiles; output:\n{output}")
        # Groom-father res_name uses role suffix `groom_father`.
        self.assertIn(
            '"_1820_01_20_petr_alekseevich_mk_marriages_1_groom_father"',
            output,
        )
        self.assertNotIn("mk_marriages_1_rel_1", output)
        # About block.
        self.assertIn("<strong>МК Горюхино 1820:</strong> отец жениха",
                      output)
        self.assertIn("Титул/звание: ясачный крестьянин", output)
        # 2 unions: marriage union (groom+bride) + father-child union.
        self.assertEqual(output.count('resource "geni_union"'), 2,
                         f"expected 2 unions; output:\n{output}")
        # Father-child union: legacy res_name has trailing `bf`.
        self.assertIn(
            '"petr_alekseevich_and_ioann_petrovich_m1_1820_bf"',
            output,
        )
        # Father-child union references father as partner_1 and groom as child.
        import re as _re
        union_m = _re.search(
            r'resource "geni_union" "petr_alekseevich_and_ioann_petrovich_m1_1820_bf" \{(.+?)\n\}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(union_m, output)
        union_block = union_m.group(1)
        self.assertIn(
            "geni_profile._1820_01_20_petr_alekseevich_mk_marriages_1_groom_father.id",
            union_block,
        )
        self.assertIn(
            "geni_profile._1820_01_20_ioann_petrovich_mk_marriages_1_groom.id",
            union_block,
        )

    def test_bride_father_emits_profile_and_family_union(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Климент", "Лаврентьев"),
                         bride=person("Агафья", "Тимонова"),
                         relatives=[
                             Relative(person("Тимон", "Лазарев",
                                             residence="Болтуново",
                                             status="священник"),
                                      Relationship.FATHER, "невеста"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        self.assertEqual(output.count('resource "geni_profile"'), 3,
                         f"expected 3 profiles; output:\n{output}")
        # Bride-father uses legacy role label `bride_relative` so res_names
        # match the consolidation move-list keys.
        self.assertIn(
            '"_1820_01_20_timon_lazarevich_mk_marriages_1_bride_relative"',
            output,
        )
        self.assertNotIn("mk_marriages_1_rel_1", output)
        self.assertIn("<strong>МК Горюхино 1820:</strong> отец невесты",
                      output)
        self.assertIn("Титул/звание: священник", output)
        # Marriage union + bride-father union.
        self.assertEqual(output.count('resource "geni_union"'), 2,
                         f"expected 2 unions; output:\n{output}")
        # Legacy res_name: father FIO + and + bride FIO + m{rec} {year} bf
        # (bride uses her birth/maiden surname — empty here).
        self.assertIn(
            '"timon_lazarevich_and_agafija_timonovna_m1_1820_bf"',
            output,
        )

    def test_bride_deceased_husband_emits_profile_and_widow_union(self):
        """Widow remarrying: the prior-marriage relative (HUSBAND of bride)
        legacy emitted as a `_bf` union with partner_1=ex-husband, partner_2=bride
        (not father→child). New translator must do the same.
        """
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Покровская",
            1836,
            *marriage_month(
                Month.MARCH,
                marriage(17, 28,
                         groom=person("Тихон", "Артемов"),
                         bride=person("Елена", "Павлова",
                                      status="ясачная вдова"),
                         relatives=[
                             Relative(person("Акиндин", "Тихонов",
                                             residence="Горюхино",
                                             status="дьячок"),
                                      Relationship.HUSBAND, "невеста"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1836_marriage.tf")

        # 3 profiles: groom, bride, ex-husband (NOT a generic rel_1).
        self.assertEqual(output.count('resource "geni_profile"'), 3,
                         f"expected 3 profiles; output:\n{output}")
        # Ex-husband uses legacy role label `bride_relative`.
        self.assertIn(
            '"_1836_03_28_akindin_tihonovich_mk_marriages_17_bride_relative"',
            output,
        )
        self.assertNotIn("mk_marriages_17_rel_1", output)
        # 2 unions: marriage union (groom+bride) + widow's prior union.
        self.assertEqual(output.count('resource "geni_union"'), 2,
                         f"expected 2 unions; output:\n{output}")
        # Legacy res_name: ex-husband FIO + and + bride FIO + m{rec} {year} bf
        self.assertIn(
            '"akindin_tihonovich_and_elena_pavlovna_m17_1836_bf"',
            output,
        )
        # Prior-marriage union: ex-husband as partner_1, bride as partner_2,
        # NO children (different from FATHER variant).
        import re as _re
        union_m = _re.search(
            r'resource "geni_union" "akindin_tihonovich_and_elena_pavlovna_m17_1836_bf" \{(.+?)\n\}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(union_m, output)
        union_block = union_m.group(1)
        self.assertIn(
            "geni_profile._1836_03_28_akindin_tihonovich_mk_marriages_17_bride_relative.id",
            union_block,
        )
        self.assertIn(
            "geni_profile._1836_03_28_elena_pavlovna_mk_marriages_17_bride.id",
            union_block,
        )
        # Bride is partner_2, not children.
        partners_m = _re.search(r"partners\s*=\s*\[(.+?)\]", union_block, _re.DOTALL)
        self.assertIsNotNone(partners_m, union_block)
        self.assertIn("elena_pavlovna", partners_m.group(1))
        self.assertNotIn("children", union_block,
                         f"expected no children block in widow's prior union; got:\n{union_block}")

    def test_both_fathers_emit_two_extra_profiles_and_unions(self):
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         relatives=[
                             Relative(person("Петр", "Алексеев"),
                                      Relationship.FATHER, "жених"),
                             Relative(person("Иван", "Сидоров"),
                                      Relationship.FATHER, "невеста"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        # 4 profiles: groom, bride, groom_father, bride_father.
        self.assertEqual(output.count('resource "geni_profile"'), 4,
                         f"expected 4 profiles; output:\n{output}")
        # 3 unions: marriage + groom-father→groom + bride-father→bride.
        self.assertEqual(output.count('resource "geni_union"'), 3,
                         f"expected 3 unions; output:\n{output}")
        # Both father profiles are emitted as resources (referenced from the
        # `bf` family unions). They are intentionally NOT in the document's
        # `profiles = [...]` list — legacy never lists them there either.
        self.assertIn(
            'resource "geni_profile" "_1820_01_20_petr_alekseevich_mk_marriages_1_groom_father"',
            output,
        )
        self.assertIn(
            'resource "geni_profile" "_1820_01_20_ioann_sidorovich_mk_marriages_1_bride_relative"',
            output,
        )
        # Neither father shows up under a generic rel_N role.
        self.assertNotIn("mk_marriages_1_rel_1", output)
        self.assertNotIn("mk_marriages_1_rel_2", output)

    def test_other_father_relative_still_emits_as_rel_n(self):
        """A FATHER relative without a 'жених'/'невеста' ref keeps the
        existing generic rel_N treatment (not lifted to groom_father /
        bride_relative)."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         relatives=[
                             Relative(person("Сидор", "Афанасьев"),
                                      Relationship.FATHER, "поручитель"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        self.assertIn(
            '"_1820_01_20_isidor_afanasevich_mk_marriages_1_rel_1"',
            output,
        )
        # No groom_father / bride_relative role on this record.
        self.assertNotIn("mk_marriages_1_groom_father", output)
        self.assertNotIn("mk_marriages_1_bride_relative", output)

    def test_bride_patronymic_derived_from_father_relative(self):
        """When the bride is declared without a patronymic but a FATHER
        relative is attached with `relationship_ref="невеста"`, the
        emitted bride profile fills `middle_name` from the father's
        first name (mirrors birth-record child patronymic derivation)."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Климент", "Алексеев"),
                         bride=person("Анна"),
                         relatives=[
                             Relative(person("Иван", "Петров"),
                                      Relationship.FATHER, "невеста"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        # The bride profile carries the derived patronymic in its
        # middle_name and res_name.
        self.assertIn(
            '"_1820_01_20_anna_ivanovna_mk_marriages_1_bride"',
            output,
        )
        bride_block = output.split(
            '"_1820_01_20_anna_ivanovna_mk_marriages_1_bride"', 1
        )[1].split("\n}\n", 1)[0]
        self.assertIn('middle_name = "Ивановна"', bride_block)

    def test_groom_patronymic_derived_from_father_relative(self):
        """Symmetric to bride: groom patronymic derived from FATHER
        relative with `relationship_ref="жених"`."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Петр"),
                         bride=person("Мария", "Сергеева"),
                         relatives=[
                             Relative(person("Алексей", "Иванов"),
                                      Relationship.FATHER, "жених"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        self.assertIn(
            '"_1820_01_20_petr_alekseevich_mk_marriages_1_groom"',
            output,
        )
        groom_block = output.split(
            '"_1820_01_20_petr_alekseevich_mk_marriages_1_groom"', 1
        )[1].split("\n}\n", 1)[0]
        self.assertIn('middle_name = "Алексеевич"', groom_block)

    def test_explicit_bride_patronymic_wins_over_derivation(self):
        """When the bride has an explicit patronymic, the FATHER
        relative does NOT override it — the explicit value wins."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Климент", "Алексеев"),
                         bride=person("Анна", "Сергеева"),
                         relatives=[
                             # Father's name disagrees with patronymic;
                             # explicit "Сергеева" must win.
                             Relative(person("Иван", "Петров"),
                                      Relationship.FATHER, "невеста"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        self.assertIn(
            '"_1820_01_20_anna_sergeevna_mk_marriages_1_bride"',
            output,
        )
        self.assertNotIn("anna_ivanovna_mk_marriages_1_bride", output)

    def test_bride_no_patronymic_no_father_relative_stays_blank(self):
        """When the bride has no patronymic and no FATHER relative with
        `невеста` ref, derivation is skipped and middle_name is empty
        (current behavior preserved)."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(1, 20,
                         groom=person("Климент", "Алексеев"),
                         bride=person("Анна")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        # Resource name uses just the bride's first name (no patronymic).
        self.assertIn(
            '"_1820_01_20_anna_mk_marriages_1_bride"',
            output,
        )


class TestDeathBurial(unittest.TestCase):
    """A часть-3 entry's burial reaches the deceased's profile (2026-09-25).

    `b_day`/`b_month` are the BURIAL in a death record; they used to reach only
    the CSV exporters.
    """

    @staticmethod
    def _emit(*records, year=1885):
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(death_records(
            "A", "1", "1", "1", "Горюхино", "N", year, *records))
        return gen.get_output(f"mk_{year}_death.tf")

    @staticmethod
    def _burial_block(output):
        start = output.index("burial = {")
        return output[start:output.index("\n  }", start)]

    def test_the_burial_day_reaches_the_profile(self):
        output = self._emit(*death_month(Month.MARCH, death(
            1, Gender.MALE, 5, 7, deceased=person("Иван", "Петров"), age=45)))
        block = self._burial_block(output)
        self.assertIn("day   = 7", block)
        self.assertIn("month = 3", block)
        self.assertIn("year  = 1885", block)
        self.assertIn("село Горюхино", block)

    def test_no_burial_day_no_burial(self):
        """The section month alone dates nothing the death does not."""
        output = self._emit(*death_month(Month.MARCH, death(
            1, Gender.MALE, 5, None, deceased=person("Иван", "Петров"), age=45)))
        self.assertNotIn("burial = {", output)

    def test_a_withdrawn_burial_is_not_emitted(self):
        output = self._emit(*death_month(Month.MARCH, death(
            1, Gender.MALE, 9, 8, deceased=person("Иван", "Петров"), age=45,
            source_date_error="погребёнъ 8, умеръ 9 — так в подлиннике")))
        self.assertNotIn("burial = {", output)

    def test_a_december_death_buried_in_january_crosses_the_year(self):
        output = self._emit(death(
            1, Gender.MALE, 30, 2, d_month=Month.DECEMBER, b_month=Month.JANUARY,
            deceased=person("Иван", "Петров"), age=45))
        block = self._burial_block(output)
        self.assertIn("year  = 1886", block)
        self.assertIn("month = 1", block)

    def test_the_burial_month_can_differ_from_the_death_month(self):
        output = self._emit(death(
            1, Gender.MALE, 31, 1, d_month=Month.MARCH, b_month=Month.APRIL,
            deceased=person("Иван", "Петров"), age=45))
        block = self._burial_block(output)
        self.assertIn("month = 4", block)
        self.assertIn("year  = 1885", block)


class TestDeathTranslation(unittest.TestCase):
    def test_unnumbered_death_sorts_first_and_does_not_break_sorting(self):
        """`death(None, ...)` — a record the source leaves unnumbered.

        Regression: _death_sort_key used to fall back to the raw record_num,
        putting a None into the sort tuple alongside the ints of every numbered
        record, so `sorted()` raised
        "'<' not supported between instances of 'NoneType' and 'int'"
        and the whole village failed to translate. Mirrors the -1 fallback
        _marriage_book_record_num already used.
        """
        records = death_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1820,
            *death_month(
                Month.JUNE,
                death(2, Gender.MALE, 20, None,
                      deceased=person("Пётр", "Иванов"), age=50),
                death(None, Gender.MALE, 10, None,
                      deceased=person("Иван", "Петров"), age=62),
                death(1, Gender.MALE, 5, None,
                      deceased=person("Фёдор", "Иванов"), age=40),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)  # must not raise
        output = gen.get_output("mk_1820_death.tf")

        # The unnumbered record still emits, with `none` in the number slot.
        self.assertIn("_1820_06_10_ioann_petrovich_mk_deaths_none_deceased", output)
        # ...and the numbered ones keep their numbers and relative order.
        self.assertIn("_1820_06_05_feodor_ivanovich_mk_deaths_1_deceased", output)
        self.assertIn("_1820_06_20_petr_ivanovich_mk_deaths_2_deceased", output)
        self.assertLess(output.index("mk_deaths_none_deceased"),
                        output.index("mk_deaths_1_deceased"),
                        "unnumbered record should sort before the numbered ones")

    def test_death_emits_deceased_profile(self):
        records = death_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Just the deceased for this minimal fixture.
        self.assertEqual(output.count('resource "geni_profile"'), 1,
                         f"expected 1 profile; output:\n{output}")
        self.assertIn("mk_deaths_1_deceased", output)
        self.assertIn("_1820_06_05_ioann_petrovich_mk_deaths_1_deceased", output)

    def test_deceased_profile_has_death_event_and_cause_of_death(self):
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      cause_of_death="оспа"),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Death event on deceased profile: d_day=5, d_month=6, year=1820.
        self.assertIn("death = {", output)
        self.assertIn("day   = 5", output)
        self.assertIn("month = 6", output)
        self.assertIn("year  = 1820", output)
        # Cause of death field.
        self.assertIn('cause_of_death = "оспа"', output)
        # Location of death event.
        self.assertIn("село Горюхино", output)

    def test_infant_death_birth_gains_day(self):
        """A deceased age under 1 month ("3 нед") yields a circa birth day via
        the shared helper: 1857-05-06 − 21 days = 1857-04-15. (≥ 1 month or
        year-bearing ages keep just year+month.)"""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1857,
            *death_month(
                Month.MAY,
                death(1, Gender.MALE, 6, None,
                      deceased=person("Иван", "Петров"),
                      age="3 нед"),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1857_death.tf")
        # Birth event: 1857-04-15 (death May 6 minus 3 weeks).
        self.assertIn("birth = {", output)
        self.assertIn("month = 4", output)
        self.assertIn("day   = 15", output)

    def test_deceased_profile_omits_cause_of_death_when_unset(self):
        """When the Death record carries no `cause_of_death` (no
        per-record value AND no `RecordDefaults(cause_of_death=…)`),
        the emitted profile must NOT include a `cause_of_death = …`
        line. This is the legacy-parity contract that pre-1800 МК
        DSLs rely on (the source CSV's `Причина смерти` column was
        empty for every death in 1754-1799)."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1754,
            *death_month(
                Month.JUNE,
                # No cause_of_death anywhere — neither per-record nor
                # via defaults=RecordDefaults(...).
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1754_death.tf")

        # Profile must exist; the cause field must NOT be present.
        self.assertIn("mk_deaths_1_deceased", output)
        self.assertNotIn("cause_of_death", output,
                         "deceased profile must not emit a "
                         "`cause_of_death = …` line when the cause is "
                         "unset on both Death and RecordDefaults")

    def test_adult_deceased_names_in_mk_includes_relative(self):
        """Adult deceased with a husband relative must surface BOTH names in
        the `Имена в МК:` line — same legacy format used for child deaths
        (`<deceased>; <relative>`). Regression: the translator previously
        only included the deceased's own name for adults, dropping the
        relative."""
        records = death_records(
            "ГАРО (Рязань)", "413", "812", "81", "Собакевичево", "N",
            1773,
            *death_month(
                Month.JANUARY,
                death(3, Gender.FEMALE, 22, None,
                      deceased=person("Фекла", "Петрова",
                                      status="ясачная крестьянка"),
                      relatives=[
                          Relative(person("Максим", "Петров",
                                          status="ясачный крестьянин"),
                                   Relationship.HUSBAND),
                      ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1773_death.tf")

        # Deceased profile, relative profile, and document text all
        # carry the same combined `Имена в МК:` line.
        self.assertEqual(
            output.count(">Имена в МК: Фекла Петрова; Максим Петров"),
            2,
            f"both deceased and relative profile abouts must carry the "
            f"combined names-in-MK line; output:\n{output}",
        )
        self.assertIn(
            "Комментарий: Имена в МК: Фекла Петрова; Максим Петров",
            output,
        )

    def test_death_doc_uses_page_level_archive_override(self):
        """A `page(...)` wrapper that supplies `archive=`, `fund=`,
        `inventory=`, `case=` should override the top-level
        `death_records(...)` values for records on that page. The legacy
        DSL uses this when a single year's records came from two
        different archives/дела."""
        from verso.ru.domain import page as page_helper
        records = death_records(
            "TopArc", "FT", "IT", "CT", "Горюхино", "N",
            1800,
            *page_helper(
                "227об",
                archive="OvrArc", fund="FO", inventory="IO", case="CO",
                *death_month(
                    Month.OCTOBER,
                    death(2, Gender.MALE, 18, None,
                          deceased=person("Леонтий", "Иванов"), age=78),
                ),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1800_death.tf")

        # Description block carries the override values, not the top-level.
        for line in (
            "Архив: OvrArc",
            "Фонд: FO",
            "Опись: IO",
            "Дело: CO",
        ):
            self.assertIn(line, output)
        # Top-level values must not appear anywhere (no leakage).
        self.assertNotIn("TopArc", output)
        self.assertNotIn("Архив: FT", output)

    def test_death_doc_falls_back_to_top_level_archive(self):
        """Without a `page(archive=…)` override the doc uses the
        top-level `death_records(...)` archive. Pins the fallback path."""
        records = death_records(
            "TopArc", "FT", "IT", "CT", "Горюхино", "N",
            1800,
            *death_month(
                Month.OCTOBER,
                death(2, Gender.MALE, 18, None,
                      deceased=person("Леонтий", "Иванов"), age=78),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1800_death.tf")
        for line in ("Архив: TopArc", "Фонд: FT", "Опись: IT", "Дело: CT"):
            self.assertIn(line, output)

    def test_death_emits_geni_document(self):
        records = death_records(
            "ГАТО (Тамбов)", "2041", "94", "8", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      cause_of_death="оспа",
                      page="42"),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        self.assertIn('resource "geni_document"', output)
        self.assertIn('"death_of_ioann_petrovich_d1_1820"', output)
        self.assertIn('labels = [', output)
        self.assertIn('"Death"', output)
        self.assertIn('day   = 5', output)
        self.assertIn('month = 6', output)
        self.assertIn('year  = 1820', output)
        # References the deceased profile by id.
        self.assertIn(
            'geni_profile._1820_06_05_ioann_petrovich_mk_deaths_1_deceased.id',
            output,
        )

    def test_deceased_has_computed_birth_circa_from_age(self):
        records = death_records(
            "ГАТО (Тамбов)", "2041", "94", "8", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      cause_of_death="оспа",
                      page="42"),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Deceased profile has a computed birth event: age 45 at death in 1820
        # → birth circa June 1775.
        self.assertIn("birth = {", output)
        self.assertIn("circa = true", output)
        self.assertIn("month = 6", output)
        self.assertIn("year  = 1775", output)

    def test_death_does_not_emit_clergy_profiles(self):
        """Clergy carried on a death record must NOT materialize as
        geni_profile resources — matches legacy byte-parity."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      priest=person("Василий", "Петров"),
                      dyachok=person("Петр", "Иванов"),
                      sexton=person("Алексей", "Михайлов")),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        self.assertNotIn("_priest", output)
        self.assertNotIn("_deacon", output)
        self.assertNotIn("_dyachok", output)
        self.assertNotIn("_sexton", output)

    def test_deceased_profile_carries_about_block(self):
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров",
                                      status="ясачный крестьянин"),
                      age=45),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Male deceased → "умерший". Female → "умершая" (separately tested).
        # The recorded age follows the role header, before the status line.
        self.assertIn("<strong>МК Горюхино 1820:</strong> умерший", output)
        self.assertIn(
            "умерший\n        Возраст: 45 лет\n        Титул/звание: ясачный крестьянин",
            output,
        )

    def test_deceased_about_age_string_and_absent(self):
        """String ages («2 мес») render verbatim; a None age emits no line."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.FEMALE, 5, None,
                      deceased=person("Мария"), age="2 мес",
                      relatives=[relative(person("Иван", "Петров"), Relationship.FATHER)]),
                death(2, Gender.MALE, 7, None,
                      deceased=person("Пётр", "Иванов"), age=None),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")
        self.assertIn("умершая\n        Возраст: 2 мес", output)
        import re as _re
        deceased2 = _re.search(
            r'resource "geni_profile" "_1820_06_07_[^"]+_mk_deaths_2_deceased"\s*{(.+?)\n}\n\n',
            output, _re.DOTALL)
        self.assertIsNotNone(deceased2, f"no deceased 2 block; output:\n{output}")
        self.assertNotIn("Возраст:", deceased2.group(1))

    def test_female_deceased_about_uses_feminine_umershaya(self):
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.FEMALE, 5, None,
                      deceased=person("Мария", "Иванова"),
                      age=30),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")
        self.assertIn("<strong>МК Горюхино 1820:</strong> умершая", output)

    def test_death_relative_emits_singular_role_with_about_block(self):
        from verso.ru.relationship import Relationship, Relative
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      relatives=[Relative(
                          person("Петр", "Сидоров", status="ясачный крестьянин"),
                          Relationship.FATHER,
                      )]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Role suffix is the singular `relative` (legacy), not `relative_1`.
        self.assertIn("_mk_deaths_1_relative", output)
        self.assertNotIn("_mk_deaths_1_relative_1", output)
        # About block is "{rel_type} умершего" for a male deceased.
        self.assertIn("<strong>МК Горюхино 1820:</strong> отец умершего", output)
        self.assertIn("Титул/звание: ясачный крестьянин", output)

    def test_death_family_union_uses_d_prefix(self):
        from verso.ru.relationship import Relationship, Relative
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      relatives=[Relative(person("Петр", "Иванов"),
                                          Relationship.FATHER)]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Union res_name: {deceased_fio} and {relative_fio} d{record} {year}
        # run through generate_res_name. Deceased "Иван Петрович" (patr
        # derived from father); relative "Петр Иванович".
        self.assertIn(
            'resource "geni_union" "ioann_petrovich_and_petr_ivanovich_d1_1820"',
            output,
        )

    def test_death_document_res_name_uses_d_prefix(self):
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"), age=45),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        self.assertIn('"death_of_ioann_petrovich_d1_1820"', output)

    def test_death_doc_body_splits_komm_and_pometki(self):
        """Legacy death document text body puts 'Комментарий: Имена
        в МК: ...' and 'Пометки: {notes}' on separate lines — same
        birth/marriage convention. Translator used to concatenate."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"), age=45,
                      comment="возраст точно не установлен"),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        self.assertIn("Комментарий: Имена в МК: Иван Петров", output)
        self.assertIn("Пометки: возраст точно не установлен", output)
        # Not combined.
        self.assertNotIn(
            "Комментарий: возраст точно не установлен; Имена в МК",
            output,
        )

    def test_umershij_sub_year_age_uses_expanded_unit_no_let(self):
        """DSL sub-year ages ('6 м', '1 н', '3 дн') get expanded to
        'мес'/'нед'/'дн' in the Умерший line and lose the trailing
        ' лет'. Full-year ages still get ' лет'."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                # 6 months old
                death(1, Gender.MALE, 5, None,
                      deceased=person("Нестор"), age="6 м"),
                # 1 week old
                death(2, Gender.FEMALE, 6, None,
                      deceased=person("Анна"), age="1 н"),
                # 45 years — still gets ' лет'
                death(3, Gender.MALE, 7, None,
                      deceased=person("Иван", "Петров"), age=45),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        self.assertIn("Умерший: Нестор 6 мес", output)
        self.assertNotIn("Нестор 6 м лет", output)
        self.assertIn("Умерший: Анна 1 нед", output)
        self.assertNotIn("Анна 1 н лет", output)
        # Sanity: numeric year age unchanged (full form patronymic).
        self.assertIn("Иоанн Петрович 45 лет", output)

    def test_natural_cause_of_death_emitted_in_profile_not_in_doc_body(self):
        """Legacy emits `cause_of_death = "натуральная"` on the profile
        verbatim (confirmed against Горюхино/terraform/mk_1814_death.tf),
        but SUPPRESSES `Причина смерти: натуральная` from the document
        text body. Asymmetric — mirror both sides."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"), age=45,
                      cause_of_death="натуральная"),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")
        # Profile field present.
        self.assertIn('cause_of_death = "натуральная"', output)
        # Document body line absent.
        self.assertNotIn("Причина смерти: натуральная", output)

        # Sanity: an explicit non-natural cause still appears.
        records2 = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(2, Gender.MALE, 5, None,
                      deceased=person("Семен", "Иванов"), age=50,
                      cause_of_death="оспа"),
            ),
        )
        gen2 = TerraformGenerator(village_dir=None)
        gen2.add_death_records(records2)
        out2 = gen2.get_output("mk_1820_death.tf")
        self.assertIn('cause_of_death = "оспа"', out2)

    def test_nonnatural_cause_of_death_also_suppressed_from_doc_body(self):
        """Legacy's death document text body never carried a standalone
        'Причина смерти:' line — the cause of death lives on the profile
        resource only, regardless of whether it's 'натуральная' or
        explicit like 'оспа' / 'понос' / 'горячка'. The suppression
        applies to all values, not just the default."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1835,
            *death_month(
                Month.JANUARY,
                death(3, Gender.MALE, 17, None,
                      deceased=person("Иосиф"),
                      age="6 м",
                      cause_of_death="понос"),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1835_death.tf")
        # Profile still carries the cause field.
        self.assertIn('cause_of_death = "понос"', output)
        # But the doc body has no 'Причина смерти:' line for it.
        self.assertNotIn("Причина смерти: понос", output)
        self.assertNotIn("Причина смерти: ", output)

    def _extract_birth_block(self, output: str) -> str:
        """Return the deceased's birth = { date = { ... } } block as a
        normalized (whitespace-collapsed) string for substring checks."""
        m = re.search(r"birth = \{\s*date = \{([^}]*)\}", output)
        if not m:
            return ""
        return re.sub(r"\s+", " ", m.group(1)).strip()

    def test_deceased_birth_estimated_from_months_age(self):
        """When age is given in months ('6 м' / '6 мес'), subtract those
        months from the death date to estimate birth. The sub-year
        units once failed float() parsing and no birth
        event was emitted."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1835,
            *death_month(
                Month.JANUARY,
                # Died 17 Jan 1835, age 6 months → born ~17 Jul 1834.
                death(3, Gender.MALE, 17, None,
                      deceased=person("Иосиф"),
                      age="6 м",
                      cause_of_death="понос"),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1835_death.tf")
        birth_block = self._extract_birth_block(output)
        self.assertIn("circa = true", birth_block)
        self.assertIn("month = 7", birth_block)
        self.assertIn("year = 1834", birth_block)

    def test_deceased_birth_estimated_from_weeks_age(self):
        """Age given in weeks ('1 нед') subtracts days-equivalent from the
        death date for the birth estimate."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1835,
            *death_month(
                Month.FEBRUARY,
                # Died 10 Feb 1835, age 5 weeks (~35 days) → born ~Jan 1835.
                death(1, Gender.MALE, 10, None,
                      deceased=person("Петр"),
                      age="5 нед"),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1835_death.tf")
        birth_block = self._extract_birth_block(output)
        # 10 Feb - 5 weeks ≈ 6 Jan — same year, month=1 (January).
        self.assertIn("month = 1", birth_block)
        self.assertIn("year = 1835", birth_block)

    def test_death_doc_res_name_keeps_double_underscore_for_firstname_only(self):
        """Legacy builds the death doc res_name with fixed slots for
        first/middle/last name, then does one-pass `.replace('  ', ' ')`.
        A deceased with ONLY a first name leaves two consecutive spaces
        between the name and `d{rec}` → double underscore in the res_name
        (e.g. `death_of_miron__d11_1802`)."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1802,
            *death_month(
                Month.JANUARY,
                death(11, Gender.MALE, 2, None,
                      deceased=person("Мирон"), age=76),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1802_death.tf")
        self.assertIn(
            'resource "geni_document" "death_of_miron__d11_1802"',
            output,
        )
        self.assertNotIn(
            'resource "geni_document" "death_of_miron_d11_1802"',
            output,
        )

    def test_death_canonical_singleton_emits_bare_comment_marker(self):
        """A deceased with only a first name that already matches the
        canonical form (no orthographic difference, no patronymic, no
        surname, no comment, no relatives) — legacy emitted just
        'Комментарий из МК:\n>' with a bare marker rather than
        'Имена в МК: {name}'. The CSV's 'Имена в МК' column was empty
        for these records because there was nothing orthographic to
        preserve."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1802,
            *death_month(
                Month.JANUARY,
                # 'Мирон' → canonical 'Мирон' (unchanged) → bare marker.
                death(11, Gender.MALE, 2, None,
                      deceased=person("Мирон"), age=76),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1802_death.tf")
        # Comment block has the header + bare marker.
        self.assertIn("Комментарий из МК:\n        >", output)
        # And NOT 'Имена в МК: Мирон' as the body.
        self.assertNotIn(">Имена в МК: Мирон", output)

    def test_death_orthographic_singleton_still_emits_names_in_mk(self):
        """A deceased whose recorded form differs from the canonical
        ('Степан' as written → 'Стефан' canonical) still gets an
        'Имена в МК: Степан' line — the orthographic variant was the
        whole reason legacy filled the CSV's 'Имена в МК' column."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1802,
            *death_month(
                Month.MAY,
                death(6, Gender.MALE, 9, None,
                      deceased=person("Степан"), age=20),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1802_death.tf")
        # Orthographic form preserved on the Имена в МК line.
        self.assertIn(">Имена в МК: Степан", output)
        self.assertNotIn("Комментарий из МК:\n        >\n", output)

    def test_death_document_location_is_parish_not_deceased_residence(self):
        """Legacy death geni_document.location uses the parish (row['Н.П.
        события']) — the book where the record was logged — not the
        deceased's residence. The deceased's `death` event still uses the
        residence (where they died at home); the document-level location
        reflects where the record was filed."""
        records = death_records(
            "A", "1", "1", "1", "Собакевичево", "N",
            1754,
            *death_month(
                Month.SEPTEMBER,
                death(2, Gender.MALE, None, None,
                      deceased=person("Алексей", "Иванов",
                                      residence="Горюхино",
                                      status="ясачный крестьянский сын"),
                      age=4),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1754_death.tf")

        import re as _re
        doc_match = _re.search(
            r'resource "geni_document" "death_of_[^"]+"\s*{(.+?)\n}\n\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(doc_match, f"no death document; output:\n{output}")
        doc_body = doc_match.group(1)

        doc_loc = _re.search(r"\blocation = \{(.+?)\}", doc_body, _re.DOTALL)
        self.assertIsNotNone(doc_loc)
        # Parish village (records.village="Собакевичево") — NOT the deceased's
        # residence (person.residence="Горюхино").
        self.assertIn("село Собакевичево", doc_loc.group(1))
        self.assertNotIn("село Горюхино", doc_loc.group(1))

    def test_deaths_emitted_in_chronological_order(self):
        """Deaths sort chronologically regardless of DSL declaration order."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *death_month(
                Month.JUNE,
                death(5, Gender.MALE, 10, None,
                      deceased=person("Петр", "Иванов"), age=60),
            ),
            *death_month(
                Month.JANUARY,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"), age=70),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1800_death.tf")

        pos_jan = output.find("_1800_01_05_ioann_petrovich_mk_deaths_1_deceased")
        pos_jun = output.find("_1800_06_10_petr_ivanovich_mk_deaths_5_deceased")
        self.assertGreater(pos_jan, -1)
        self.assertGreater(pos_jun, -1)
        self.assertLess(pos_jan, pos_jun)

    def test_death_names_in_mk_includes_deceased_and_relative(self):
        """Legacy death `>Имена в МК: ...` joins the deceased with their
        relative — `<deceased>; <relative>` — but NOT witnesses. Pins the
        deceased+relative inclusion contract; witnesses must not leak in."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1800,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Алексей", "Иванов"),
                      age=45,
                      relatives=[
                          Relative(person("Иван", "Сидоров"),
                                   Relationship.FATHER),
                      ]),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1800_death.tf")

        # Deceased + relative both appear; document text mirrors the line.
        self.assertIn(">Имена в МК: Алексей Иванов; Иван Сидоров", output)
        self.assertIn("Комментарий: Имена в МК: Алексей Иванов; Иван Сидоров",
                      output)

    def test_child_death_names_in_mk_has_given_name_and_parent(self):
        """Child deceased (no own patronymic in DSL) with a FATHER
        relative: legacy renders 'Firstname; Parent Fullname' — the
        child's book-name is the given name alone, no auto-derived
        patronymic, plus the parent as a separate entry."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JANUARY,
                death(3, Gender.MALE, 23, None,
                      deceased=person("Нестор"),  # no patronymic
                      age="6 м",
                      relatives=[
                          Relative(person("Антип", "Лазарев"),
                                   Relationship.FATHER),
                      ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Should be "Нестор; Антип Лазарев" — NOT "Нестор Антипов".
        self.assertIn(">Имена в МК: Нестор; Антип Лазарев", output)
        # Derived patr_old ("Антипов") must not appear in Имена в МК.
        self.assertNotIn(">Имена в МК: Нестор Антипов", output)
        # Same asymmetry inside the document text body.
        self.assertIn("Имена в МК: Нестор; Антип Лазарев", output)

    def test_child_death_with_mother_relative_also_included(self):
        """Same child-case rule applies when the relative is MOTHER
        (father already deceased), e.g. 'Гордей; Надежда Тихонова'."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.MARCH,
                death(4, Gender.MALE, 14, None,
                      deceased=person("Гордей"),
                      age=1,
                      relatives=[
                          Relative(person("Надежда", "Тихонова"),
                                   Relationship.MOTHER),
                      ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        self.assertIn(">Имена в МК: Гордей; Надежда Тихонова", output)

    def test_1802_death_uses_record_num_sort_override(self):
        """Legacy 1802 death CSV was ordered by record_num, not chronologically.
        SORT_OVERRIDE[(1802, "death")] flips to record_num-first so the
        translator matches legacy ordering for that year."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1802,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Петр", "Иванов"), age=60),
            ),
            *death_month(
                Month.JANUARY,
                death(2, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"), age=70),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1802_death.tf")

        pos_rec1 = output.find("_1802_06_05_petr_ivanovich_mk_deaths_1_deceased")
        pos_rec2 = output.find("_1802_01_05_ioann_petrovich_mk_deaths_2_deceased")
        self.assertGreater(pos_rec1, -1, "record 1 not emitted")
        self.assertGreater(pos_rec2, -1, "record 2 not emitted")
        self.assertLess(pos_rec1, pos_rec2,
                        "1802 death must emit in record_num order (override)")

    def test_death_emits_relative_profiles(self):
        records = death_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      relatives=[
                          Relative(person("Анна", "Иванова"),
                                   Relationship.MOTHER),
                      ]),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        # Death uses singular `relative` role (not `relative_1`) to match legacy.
        self.assertIn("_1820_06_05_anna_ivanovna_mk_deaths_1_relative", output)
        self.assertNotIn("_1820_06_05_anna_ivanovna_mk_deaths_1_relative_1", output)


class TestCensusTranslation(unittest.TestCase):
    def test_household_emits_member_profiles(self):
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка",
            1795,
            household(None, member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=63),
                      member(2, person("Евдокия", "Игнатова"), CensusRole.WIFE, age=68),
                      member(3, person("Лука", "Тимонов"), CensusRole.SON, age=56)),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        self.assertEqual(output.count('resource "geni_profile"'), 3,
                         f"expected 3 profiles; output:\n{output}")
        self.assertIn("_1_1_family_member", output)
        self.assertIn("_1_2_family_member", output)
        self.assertIn("_1_3_family_member", output)

    def test_died_before_revision_shows_departure_not_age(self):
        """A member who died BEFORE the revision (departure «умер» in an
        earlier year) has no current-revision age — the census records
        «58/–». The About must surface the document's «Причина, основание
        убытия» line, not a misleading «Возраст: 58». Example: a head with a
        stated previous-revision age who died before this revision."""
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1850,
            household("71", member(1, person("Егор", "Лазарев"), CensusRole.HEAD,
                                   age=58, previous_age=58,
                                   departure_year=1843, departure_reason="умер",
                                   birth_year=1775)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1850_1.tf")

        # The departure line must appear IN THE ABOUT block — right after the
        # <strong>…семья 71</strong> header (anchoring on <strong> avoids
        # matching the same phrase in the census document reestr text).
        self.assertRegex(
            output,
            r"<strong>РС Тестовка 1850:</strong> семья 71\s*"
            r"Причина, основание убытия: умер \(1843\)",
            f"departure line not in the about block:\n{output}")
        self.assertNotIn("Возраст: 58", output,
                         f"stale prev-revision age still shown:\n{output}")

    def test_census_member_profile_carries_death_range_after_census_year(self):
        """A census sighting encodes `alive-up-to` on each family_member as
        `death.range="after" year=<census_year>`. Matches legacy
        Горюхино/generate_config.py:1791-1805 and lets consolidation with
        later encounters pick the max-year `after` range."""
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка",
            1795,
            household(None, member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=63)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        # The member profile carries a death event tagged `range="after"` at
        # the census year (circa because the actual death-by-then is implied).
        self.assertIn('death = {', output)
        self.assertIn('range = "after"', output)
        self.assertIn('year  = 1795', output)

    def test_departed_member_keeps_death_after_stub(self):
        """Legacy parity: members who departed for a non-death reason
        (e.g. `выдана замуж`, `в рекруты`, `переведен в ...`) AND have
        a known current-revision age still get a `death = { range =
        "after"; year = census_year }` stub. The "after" range is a
        LOWER bound on the death year, derived from the fact that the
        census recorded them alive with that age — it does not conflict
        with later sightings elsewhere (which only tighten the lower
        bound). Legacy emitted this stub for every non-deceased member
        with a known current age, regardless of departure reason."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Тихон", "Иванов"), CensusRole.HEAD, age=50),
                      member(2, person("Прасковья", "Тихонова"), CensusRole.DAUGHTER, age=17, destination="Пепелищи",
                             departure_reason="выдана замуж"),
                      member(3, person("Алексей", "Тихонов"), CensusRole.SON, age=20, departure_year=1790,
                             departure_reason="отдан в рекруты")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        for res_name in (
            "_1795_00_00_tihon_ivanovich_rs_1_1_1_family_member",
            "_1795_00_00_paraskeva_tihonovna_rs_1_1_2_family_member",
            "_1795_00_00_aleksij_tihonovich_rs_1_1_3_family_member",
        ):
            block = _extract_resource_block(output, res_name)
            self.assertIn("death = {", block, msg=res_name)
            self.assertIn('range = "after"', block, msg=res_name)
            self.assertIn("year  = 1795", block, msg=res_name)

    def test_departed_member_renders_explicit_current_age(self):
        """Legacy parity: a departed daughter (or any departed member)
        whose DSL carries an explicit `age=X` must render as `-/X` in
        the document body's age column, NOT `-/-`. The source CSV's
        `Лет (текущая РС)` was non-empty for these rows; the DSL author
        preserved that age, and forcing it to "-" would lose data and
        diverge from legacy."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Тихон", "Иванов"), CensusRole.HEAD, age=50),
                      member(2, person("Прасковья", "Тихонова"), CensusRole.DAUGHTER, ref_member=1, age=18,
                             destination="Пепелищи", departure_reason="выдана замуж")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")
        self.assertIn(
            "2. дочь (1): Параскева Тихоновна: -/18", output,
        )

    def test_died_member_keeps_circa_death(self):
        """Regression: members with `departure_reason="умер"` and a
        `departure_year` still get a circa-year death event with the
        village location. This path is unchanged by the non-death-departure
        fix above."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Тихон", "Иванов"), CensusRole.HEAD, age=50),
                      member(2, person("Ирина", "Тихонова"), CensusRole.DAUGHTER, age=21, departure_year=1782,
                             departure_reason="умер")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        died_block = _extract_resource_block(
            output, "_1795_00_00_irina_tihonovna_rs_1_1_2_family_member",
        )
        self.assertIn("death = {", died_block)
        self.assertIn("circa = true", died_block)
        self.assertIn("year  = 1782", died_block)
        # Village location attached to the death event.
        self.assertIn("село Горюхино", died_block)

    def test_alive_member_keeps_after_stub(self):
        """Regression: a no-departure member still gets the
        `range = "after" year = <census_year>` death stub.
        Sanity check that the new branch isn't masking the existing
        alive-at-census path."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Тихон", "Иванов"), CensusRole.HEAD, age=50),
                      member(2, person("Анна", "Тихонова"), CensusRole.DAUGHTER, age=12)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        alive_block = _extract_resource_block(
            output, "_1795_00_00_anna_tihonovna_rs_1_1_2_family_member",
        )
        self.assertIn("death = {", alive_block)
        self.assertIn('range = "after"', alive_block)
        self.assertIn("year  = 1795", alive_block)

    def test_census_member_profile_carries_current_residence_from_village(self):
        """Legacy census member profiles include `current_residence` set
        to the village's location block (same as every adult profile
        elsewhere). Pre-enrichment the translator was emitting profiles
        without residence — legacy has it on every member."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Козма", "Тимонов"), CensusRole.HEAD, age=58)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        self.assertIn("current_residence", output)
        self.assertIn("село Горюхино", output)

    def test_census_member_profile_carries_birth_year_from_age(self):
        """Legacy estimates `birth.date.year = census_year - age`, circa.
        A 70-year-old in the 1762 census has `year = 1692`."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Козма", "Тимонов"), CensusRole.HEAD, age=58),
                      member(2, person("Авдотья", "Прохорова"), CensusRole.WIFE, age=66)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        self.assertIn("birth = {", output)
        self.assertIn("year  = 1696", output)  # wife, 70y

    def test_census_member_birth_year_from_compound_age_string(self):
        """A compound Russian age string ("13 лет 5 мес") must still yield a
        circa birth year. Regression: the fallback used `int(m.age)`, which
        raised ValueError on compound ages and dropped the birth entirely
        (e.g. a village's 1857 roll, which also has no prev-revision-year
        mapping). The whole-year floor matches the bare-int behaviour:
        1857 − 13 = 1844."""
        records = census_records(
            "A", "1", "1", "1", "Нижняя Яичница", 1857,
            household(None, member(1, person("Дорофей", "Прохоров"), CensusRole.HEAD, age=44),
                      member(2, person("Гордей"), CensusRole.SON, ref_member=1, age="13 лет 5 мес")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1857_1.tf")
        self.assertIn("birth = {", output)
        self.assertIn("year  = 1844", output)  # son, 13y5m → 1857 − 13

    def test_census_member_birth_gains_month_from_record_date(self):
        """When the census carries a record date, a member with a sub-year age
        component gains a circa birth MONTH (months/weeks/days-aware arithmetic):
        1857-11-06 − 13y5m = June 1844. The day stays dropped (year-bearing age)."""
        records = census_records(
            "A", "1", "1", "1", "Нижняя Яичница", 1857,
            household(None, member(1, person("Дорофей", "Прохоров"), CensusRole.HEAD, age=44),
                      member(2, person("Гордей"), CensusRole.SON, ref_member=1, age="13 лет 5 мес"), record_day=6,
                      record_month=Month.NOVEMBER),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1857_1.tf")
        self.assertIn("year  = 1844", output)
        self.assertIn("month = 6", output)   # 13y5m before Nov 1857 → June 1844

    def test_census_infant_birth_gains_day_from_record_date(self):
        """An interval under 1 month with a record date yields a circa day too:
        1857-11-06 − 3 нед (21 days) = 1857-10-16. (≥ 1 month → month only.)"""
        records = census_records(
            "A", "1", "1", "1", "Нижняя Яичница", 1857,
            household(None, member(1, person("Дорофей", "Прохоров"), CensusRole.HEAD, age=44),
                      member(2, person("Иван"), CensusRole.SON, ref_member=1, age="3 нед"), record_day=6,
                      record_month=Month.NOVEMBER),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1857_1.tf")
        self.assertIn("year  = 1857", output)
        self.assertIn("month = 10", output)
        self.assertIn("day   = 16", output)

    def test_census_document_type_overrides_title_and_adds_district(self):
        """`document_type` replaces the default "Ревизская сказка" label
        in the census document title (and the description/text header's
        first line), and `district`/`volost` add a "Счетный участок"
        line to the header block. Used by the 1897 First General Census
        of Нижняя Яичница."""
        records = census_records(
            "ГАВО", "148", "6", "550", "Нижняя Яичница", 1897,
            household(None, member(1, person("Василий", "Тимофеев", "Индюшев"), CensusRole.HEAD, age=47), page="88-89"),
            document_type="1-я всеобщая перепись",
            district="20",
            volost="Сонливская",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1897_1.tf")
        self.assertIn(
            'title       = "1-я всеобщая перепись Нижняя Яичница 1897: семья 1"',
            output,
        )
        self.assertIn("Счетный участок: 20 (Сонливская волость)", output)
        self.assertNotIn("Ревизская сказка", output)

    def test_census_household_comment_renders_primechanie_not_delo(self):
        """A household-level `comment=` must NOT leak into the `Дело:`
        header line (regression: the household() helper passed comment
        positionally into the `case` slot). `Дело:` keeps the archive
        case; the comment surfaces as a `Примечание:` line."""
        records = census_records(
            "ГАВО", "148", "6", "550", "Нижняя Яичница", 1897,
            household(None, member(1, person("Иван", "Мартынов", "Индюшев"), CensusRole.HEAD, age=66), page="212-213",
                      comment="семья в полном составе отсутствует – на заводе"),
        )
        # DSL-layer: comment lands in `comment`, not `case`.
        hh = records.households[0]
        self.assertIsNone(hh.case)
        self.assertEqual(
            hh.comment, "семья в полном составе отсутствует – на заводе")
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1897_1.tf")
        self.assertIn("Дело: 550", output)
        self.assertIn(
            "Примечание: семья в полном составе отсутствует – на заводе",
            output,
        )
        self.assertNotIn("Дело: семья", output)

    def test_census_household_without_comment_has_no_primechanie(self):
        """No `Примечание:` line when the household carries no comment;
        `Дело:` still shows the archive case."""
        records = census_records(
            "ГАВО", "148", "6", "550", "Нижняя Яичница", 1897,
            household(None, member(1, person("Иван", "Мартынов", "Индюшев"), CensusRole.HEAD, age=66), page="212-213"),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1897_1.tf")
        self.assertIn("Дело: 550", output)
        self.assertNotIn("Примечание:", output)

    def test_census_document_type_defaults_to_revizskaja_skazka(self):
        """Without `document_type`/`district`/`volost`, the census
        document keeps the legacy "Ревизская сказка" title and emits no
        "Счетный участок" line."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Козма", "Тимонов"), CensusRole.HEAD, age=58)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        self.assertIn(
            'title       = "Ревизская сказка Горюхино 1762: семья 1"',
            output,
        )
        self.assertNotIn("Счетный участок", output)
        self.assertNotIn("Волость", output)

    def test_census_member_about_surfaces_occupation_and_marital_status(self):
        """A census member with `occupation`/`marital_status` but no
        comment still gets an about block (Род занятий / Семейное
        положение lines) AND the native `occupation` profile field. The
        about header + `Комментарий из …` line use the document label /
        its genitive. The shape: a woman member with an occupation
        (повивальная бабка) and marital status (вдова), no comment."""
        records = census_records(
            "ГАВО", "148", "6", "550", "Нижняя Яичница", 1897,
            household(None, member(1, person("Татьяна", "Петрова", "Ляпкина"), CensusRole.HEAD, age=60,
                                   marital_status="вдова",
                                   occupation="повивальная бабка"), page="170-171"),
            document_type="1-я всеобщая перепись",
            document_type_genitive="1-й всеобщей переписи",
            district="20", volost="Сонливская",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1897_1.tf")
        self.assertIn('occupation = "повивальная бабка"', output)
        self.assertIn(
            "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 1",
            output,
        )
        self.assertIn("Возраст: 60", output)
        self.assertIn("Род занятий: повивальная бабка", output)
        self.assertIn("Семейное положение: вдова", output)
        self.assertNotIn("РС Нижняя Яичница 1897", output)

    def test_census_member_about_genitive_label_in_comment_line(self):
        """When a member carries a comment, the `Комментарий из …`
        header uses the genitive document label."""
        records = census_records(
            "ГАВО", "148", "6", "550", "Нижняя Яичница", 1897,
            household(None, member(1, person("Василий", "Тимофеев", "Индюшев"), CensusRole.HEAD, age=47,
                                   occupation="лесной объездчик", comment="грамотный (дома)"), page="88-89"),
            document_type="1-я всеобщая перепись",
            document_type_genitive="1-й всеобщей переписи",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1897_1.tf")
        self.assertIn("Комментарий из 1-й всеобщей переписи 1897 года:", output)
        self.assertIn(">грамотный (дома)", output)

    def test_census_after_death_includes_page_day_month(self):
        """When a household's page carries 'Дата записи' (record_day /
        record_month set on the CensusHousehold), the member's census
        death stub — `death.date = { range="after", year=<census_year> }`
        — picks up that day/month too. Legacy output for 1816/1834 files
        carries the day+month on the 'after' marker because those CSVs
        had a 'Дата записи' column populated."""
        records = census_records(
            "A", "1", "1", "687", "Горюхино", 1816,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=66)),
            record_day=1, record_month=Month.AUGUST,
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1816_1.tf")
        # Normalize the death date block for a clean substring check.
        death_m = re.search(
            r"death = \{\s*date = \{([^}]*)\}", output,
        )
        self.assertIsNotNone(death_m)
        death_date = re.sub(r"\s+", " ", death_m.group(1)).strip()
        self.assertIn('range = "after"', death_date)
        self.assertIn("day = 1", death_date)
        self.assertIn("month = 8", death_date)
        self.assertIn("year = 1816", death_date)

    def test_census_after_death_omits_day_month_without_page_date(self):
        """Control: a household without 'Дата записи' (record_day /
        record_month unset) keeps the bare `after {year}` form — day and
        month must be absent from the census death date block. Prevents
        the fix from falsely injecting 00/00 sentinel values."""
        records = census_records(
            "A", "1", "1", "1074", "Горюхино", 1762,
            household(None, member(1, person("Кузьма", "Тимонов"), CensusRole.HEAD, age=58)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        death_m = re.search(
            r"death = \{\s*date = \{([^}]*)\}", output,
        )
        self.assertIsNotNone(death_m)
        death_date = re.sub(r"\s+", " ", death_m.group(1)).strip()
        self.assertIn('range = "after"', death_date)
        self.assertIn("year = 1762", death_date)
        self.assertNotIn("day =", death_date)
        self.assertNotIn("month =", death_date)

    def test_census_member_profile_with_origin_emits_birth_location(self):
        """A member whose DSL sets `origin=...` (their natal village)
        gets `birth.location` pointing at that locations[] entry in
        addition to the census year. Mirrors legacy's origin-aware
        birth event."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Козма", "Тимонов"), CensusRole.HEAD, age=58),
                      member(2, person("Авдотья", "Прохорова"), CensusRole.WIFE, age=66, origin="Свинорыловка")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        # Find the wife's profile block and check birth.location presence.
        block = _extract_resource_block(
            output, "_1762_00_00_evdokija_prohorovna_rs_1_2_family_member",
        )
        self.assertIn("birth = {", block)
        self.assertIn("location = {", block)
        self.assertIn("деревня Свинорыловка", block)

    def test_head_only_union_excludes_members_with_parent_member(self):
        """A NEPHEW with `parent_member=<hidden>` set has explicit
        lineage to a hidden ancestor — they must NOT also appear as a
        child of HEAD in the head-only union. Regression: a HEAD younger
        than his NEPHEW, whose `parent_member` names a hidden brother,
        was emitting `head → [nephew]`, which is biologically impossible
        (a 14-year-old can't father a 28-year-old)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1721,
            household(None, member(1, person("Дементий", "Тимонов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=14),
                      member(2, person("Тихон", "Лавров",
                                       status="ясачный крестьянин"), CensusRole.NEPHEW, age=28, parent_member=4),
                      member(3, person("Гордей", "Тихонов",
                                       status="ясачный крестьянин"), CensusRole.SON, ref_member=2, age=3),
                      member(4, person("Оска",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1721_1.tf")
        # No head-only union emitted (no qualifying children).
        self.assertNotIn(
            'resource "geni_union" "dometij_timonovich_rs1_1721"', out,
        )
        # Hidden Оска's union DOES include Тихон (via parent_member=4).
        self.assertIn('resource "geni_union" "oska__rs1-4_1721"', out)

    def test_full_brother_only_in_stub_not_head_only(self):
        """A full BROTHER (no `сводный брат` qualifier) of HEAD belongs
        ONLY to the stub union (siblings sharing HEAD's parent), NOT
        to HEAD's head-only union (which represents HEAD as the
        parent). Regression: a full BROTHER of the HEAD was emitted as a
        child in a head-only union (`head_rs1_<year> → [brother]`) —
        biologically wrong, since he is the head's brother, not his son."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1745,
            household(None, member(1, person("Павел", "Артемов",
                                             status="дворовый человек"), CensusRole.HEAD, age=66),
                      member(2, person("Иван", "Артемов",
                                       status="дворовый человек"), CensusRole.BROTHER, age=30)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1745_1.tf")
        # Stub union has both as children of the implied parent.
        stub_anchor = 'resource "geni_union" "head_of_family_1_1745"'
        self.assertIn(stub_anchor, out)
        # No head-only union — Иван is sibling, not son.
        self.assertNotIn(
            'resource "geni_union" "pavel_artemovich_rs1_1745"', out,
        )

    def test_legacy_stub_and_head_only_unions_emitted(self):
        """Legacy partitions a no-wife household with siblings into two
        unions:

        1. `head_of_family_<h>_<year>`: implied stub → [HEAD + BROTHER/
           SISTER siblings with `previous_age` set]. These are the
           members already attested by the prior RS — they share the
           unrecorded ancestor that the stub represents.
        2. `<head>_rs<num>_<year>`: HEAD → [members without
           `previous_age`, effective_ref=1]. New members in this RS
           get HEAD as their parent (genealogically rough — step-
           brothers get pulled in too — but matches legacy).

        Shape: the HEAD and a BROTHER that both carry previous_age
        belong to the stub union; a SON and two step-brothers without
        previous_age belong to the head's head-only union."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1721,
            household(None, member(1, person("Фома", "Тарасов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=34, previous_age=34),
                      member(2, person("Дмитрий",
                                       status="ясачный крестьянин"), CensusRole.SON, age=2),
                      member(3, person("Аверкей", "Макаров",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=21,
                             comment="роль в оригинале: сводный брат"), member(4, person("Ермил", "Макаров",
                                                                                         status="ясачный крестьянин"),
                                                                               CensusRole.BROTHER, age=14,
                                                                               comment="роль в оригинале: сводный брат"),
                      member(6, person("Ипат", "Тарасов",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=27, previous_age=27)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1721_1.tf")

        # Stub union: stub → [HEAD + Петр] (both have previous_age).
        stub_anchor = 'resource "geni_union" "head_of_family_1_1721"'
        self.assertIn(stub_anchor, out)
        idx = out.find(stub_anchor)
        end = out.find("\n}", idx)
        stub_block = out[idx:end]
        self.assertIn("_1721_00_00_unknown_rs_1_not_recorded_head_of_family.id", stub_block)
        self.assertIn("_1721_00_00_foma_tarasovich_rs_1_1_family_member.id", stub_block)
        self.assertIn("_1721_00_00_ipatij_tarasovich_rs_1_6_family_member.id", stub_block)

        # Head-only union: Фома → [Аверкей, Дмитрий, Ермил] (no previous_age + ref=1).
        head_anchor = 'resource "geni_union" "foma_tarasovich_rs1_1721"'
        self.assertIn(head_anchor, out)
        idx = out.find(head_anchor)
        end = out.find("\n}", idx)
        head_block = out[idx:end]
        self.assertIn("_1721_00_00_foma_tarasovich_rs_1_1_family_member.id", head_block)
        self.assertIn("_1721_00_00_dimitrij_fomich_rs_1_2_family_member.id", head_block)
        self.assertIn("_1721_00_00_averkij_makarovich_rs_1_3_family_member.id", head_block)
        self.assertIn("_1721_00_00_ermil_makarovich_rs_1_4_family_member.id", head_block)
        # Петр has previous_age → NOT in head-only union.
        self.assertNotIn("_1721_00_00_ipatij_tarasovich_rs_1_6_family_member.id", head_block)

    def test_arrival_reason_redundant_with_origin_suppressed_in_about(self):
        """Same suppression as the document table, applied to the
        about block: when `arrival_reason="из X"` matches `origin="X"`,
        the `>из X` `Комментарий из РС YYYY года` line is also dropped.
        Legacy emitted only the substantive notes, not the redundant
        origin-restating reason."""
        records = census_records(
            "A", "1", "1", "1", "Собакевичево", 1745,
            household(None, member(1, person("Нестеръ", "Тимофеевъ",
                                             status="крестьянин помещика X"), CensusRole.HEAD, age=47,
                                   origin="Кожемяки",
                                   arrival_reason="из Кожемяки",
                                   comment="Сонливского уезда из деревни Заболотной Ухабы тож; ФИО в документе: Нестеръ Тимофеевъ")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1745_1.tf")
        block = _extract_resource_block(
            out, "_1745_00_00_nestor_timofeevich_rs_1_1_family_member",
        )
        about_section = block.split("about = {")[1] if "about = {" in block else ""
        # Substantive about lines remain.
        self.assertIn(">Сонливского уезда из деревни Заболотной Ухабы тож", about_section)
        # No surname → "ИО" (name + patronymic), auto-generated from person().
        self.assertIn(">ИО в документе: Нестеръ Тимофеевъ", about_section)
        # Redundant origin-restating line dropped.
        self.assertNotIn(">из Кожемяки", about_section)

    def test_arrival_reason_redundant_with_origin_suppressed(self):
        """When `arrival_reason="из X"` exactly matches the member's
        `origin="X"`, the document body should emit only the
        `Населенный пункт откуда поступили/прибыли: X` line — not the
        redundant `Причина, основание поступления/прибытия: из X`.
        Mirrors legacy.

        Regression: a head has origin="Кожемяки" and
        arrival_reason="из Кожемяки". Legacy emitted only the village
        line; the new generator emitted both."""
        records = census_records(
            "A", "1", "1", "1", "Собакевичево", 1745,
            household(None, member(1, person("Нестеръ", "Тимофеевъ",
                                             status="крестьянин помещика X"), CensusRole.HEAD, age=47,
                                   origin="Кожемяки",
                                   arrival_reason="из Кожемяки")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1745_1.tf")
        # Origin line present.
        self.assertIn(
            "Населенный пункт откуда поступили/прибыли: Кожемяки", out,
        )
        # Redundant arrival-reason line absent.
        self.assertNotIn(
            "Причина, основание поступления/прибытия: из Кожемяки", out,
        )

    def test_died_without_year_emits_before_stub(self):
        """When `departure_reason="умер"` is set but `departure_year`
        is missing, the source records "died sometime before this
        revision" — legacy emits `death = { range = "before"; circa =
        true; year = census_year; location = village }` to capture
        that bound. Mirror that.

        Concrete regression: a HEAD has
        `departure_reason="умер"` (no year). Legacy emitted the
        before-stub; the new generator was emitting no death event."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1745,
            household(None, member(1, person("Емельян", "Лазарев",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age="?",
                                   departure_reason="умер")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1745_1.tf")
        block = _extract_resource_block(
            out, "_1745_00_00_emeljan_lazarevich_rs_1_1_family_member",
        )
        self.assertIn("death = {", block)
        self.assertIn('range = "before"', block)
        self.assertIn("circa = true", block)
        self.assertIn("year  = 1745", block)
        self.assertIn("село Горюхино", block.split("death = {")[1].split("}\n  }")[0])

    def test_unknown_age_suppresses_after_death_stub(self):
        """When a member's age is unknown (`"?"`, `None`, etc.) the
        translator can't derive a birth year — and legacy didn't emit
        the alive-after death stub either. Mirror that.

        Concrete regression: a HEAD with
        age=`"?"` — legacy: no death event; new generator was
        emitting `death = { range = "after"; year = 1721 }`."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1721,
            household(None, member(1, person("Никита", "Мартынов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age="?"),
                      member(2, person("Сакя", "Никитин",
                                       status="ясачный крестьянин"), CensusRole.SON, age=4)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1721_1.tf")
        head_block = _extract_resource_block(
            out, "_1721_00_00_nikita_martynovich_rs_1_1_family_member",
        )
        self.assertNotIn("death = {", head_block)
        # SON with known age still has the after-stub.
        son_block = _extract_resource_block(
            out, "_1721_00_00_sakja_nikitich_rs_1_2_family_member",
        )
        self.assertIn("death = {", son_block)

    def test_compressed_prev_age_suppresses_after_death_stub(self):
        """When the DSL records `age == previous_age`, that's the
        compression convention for "current revision's age column was
        empty in source" — the DSL author duplicated the prior age into
        `m.age`. Legacy keyed on the source CSV's `Лет (текущая РС)`
        being empty: empty → no death-after stub. Mirror that.

        Regression: a HEAD whose `age` equals `previous_age`
        (compressed because the source had an empty current age) gained
        `death = { range = "after"; year = <census year> }` in the new
        generator; legacy emitted no death event."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1721,
            household(None, member(1, person("Фома", "Тарасов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=34, previous_age=34),
                      member(2, person("Дмитрий",
                                       status="ясачный крестьянин"), CensusRole.SON, age=2)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1721_1.tf")
        head_block = _extract_resource_block(
            out, "_1721_00_00_foma_tarasovich_rs_1_1_family_member",
        )
        self.assertNotIn("death", head_block.lower())
        # New SON without previous_age still has the after-stub.
        son_block = _extract_resource_block(
            out, "_1721_00_00_dimitrij_fomich_rs_1_2_family_member",
        )
        self.assertIn("death = {", son_block)
        self.assertIn('range = "after"', son_block)

    def test_arrival_year_suppressed_when_origin_already_carries_it(self):
        """When `origin` literally contains a 4-digit year matching
        `arrival_year` (e.g. `origin="Пробкино 1725"` + `arrival_year=1725`),
        the `(YYYY)` parenthetical on the
        `Причина, основание поступления/прибытия:` line is redundant —
        the year is already shown on the `Населенный пункт откуда
        поступили/прибыли:` line above. Suppress the parenthetical to
        match legacy parity (legacy never extracted the year because
        the source CSV's dedicated year column was empty)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Иван", "Иванов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=50),
                      member(2, person("Аграфена", "Ефимова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=42, origin="Пробкино 1725",
                             arrival_year=1725, arrival_reason="взята в жены")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1762_1.tf")
        self.assertIn("Населенный пункт откуда поступили/прибыли: Пробкино 1725", out)
        self.assertIn("Причина, основание поступления/прибытия: взята в жены\n", out)
        self.assertNotIn("взята в жены (1725)", out)

    def test_arrival_year_kept_when_origin_does_not_carry_it(self):
        """Guard: when `origin` does NOT contain the year, the typed
        `arrival_year` must still render as the `(YYYY)` parenthetical —
        it's the only place the year would otherwise appear."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Иван", "Петров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=40,
                                   origin="Ухабово",
                                   arrival_year=1818, arrival_reason="вновь причисленный")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1834_1.tf")
        self.assertIn("Причина, основание поступления/прибытия: вновь причисленный (1818)", out)

    def test_distinct_prev_and_current_age_keeps_after_death_stub(self):
        """When `previous_age` and `m.age` are DIFFERENT values, the
        source CSV had both `Лет (прошлая РС)` and `Лет (текущая РС)`
        filled in (the normal case). Legacy emitted the death-after
        stub for these — the current revision attested the member alive
        with a known age. The new generator's earlier broad `has_prev_age`
        suppression incorrectly dropped the stub for them.

        Regression: a wife whose `previous_age` and `age` differ lost
        the `death after <census year>` stub when she should have kept
        it (legacy did)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Тимон", "Макаров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=63, previous_age=63),
                      member(2, person("Авдотья", "Климова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, ref_member=1, age=47,
                             previous_age=34,
                             origin="Сонливка", arrival_reason="взята в жены")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1795_1.tf")
        wife_block = _extract_resource_block(
            out, "_1795_00_00_evdokija_klimovna_rs_1_2_family_member",
        )
        self.assertIn("death = {", wife_block)
        self.assertIn('range = "after"', wife_block)
        self.assertIn("year  = 1795", wife_block)

    def test_head_of_family_stub_omits_current_residence(self):
        """The `unknown_..._not_recorded_head_of_family` stub represents
        an implied parent the document never enumerated. We don't know
        where they lived. Legacy emitted no `current_residence` on the
        stub; mirror that."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1721,
            household(None, member(1, person("Фома", "Тарасов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=34),
                      member(2, person("Ипат", "Тарасов",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=27)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1721_1.tf")
        # Locate the stub block and assert no current_residence.
        anchor = 'resource "geni_profile" "_1721_00_00_unknown_rs_1_not_recorded_head_of_family"'
        idx = out.find(anchor)
        self.assertNotEqual(idx, -1, "stub not emitted")
        end = out.find("\n}\n", idx)
        block = out[idx:end]
        self.assertNotIn("current_residence", block)

    def test_multi_sibling_falls_back_to_default_ref(self):
        """When MULTIPLE members share the same `parent_member`, the
        "brother of" relationship is ambiguous (which sibling is the
        canonical one?). Legacy's CSV defaulted to `(1)` for siblings —
        i.e. brothers of the HEAD. Mirror that: only derive a sibling
        ref when exactly ONE other member shares the parent_member.

        Regression: a household has three brothers all carrying the same
        `parent_member` (a hidden ancestor). Legacy printed `3. брат (1)`
        for the first of them; the new translator printed `3. брат (4)`
        because the derivation picked the first other sibling found."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1719,
            household(None, member(1, person("Емельян", "Лазарев",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=52),
                      member(3, person("Герасим", "Лазарев",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=42, parent_member=14),
                      member(4, person("Мирон", "Лазарев",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=32, parent_member=14),
                      member(5, person("Иосиф", "Лазарев",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=22, parent_member=14),
                      member(14, person("Лазарь",
                                        status="ясачный крестьянин"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1719_1.tf")
        # Default to brother-of-head; do NOT pick a sibling.
        self.assertIn("3. брат (1): Герасим Лазаревич: -/42", out)
        self.assertIn("4. брат (1): Мирон Лазаревич: -/32", out)
        self.assertIn("5. брат (1): Иосиф Лазаревич: -/22", out)

    def test_sibling_ref_derived_from_shared_parent_member(self):
        """When a BROTHER has no explicit `ref_member` but has
        `parent_member=N` pointing at a hidden ancestor AND another
        household member shares the same `parent_member`, the document
        table renders the sibling's row number as the effective ref —
        e.g. `5. брат (3): Фаддей Лазаревич` (brother of Тимофей #3),
        not `5. брат (1)` (default fall-back to head).

        Regression: both the NEPHEW (#3) and the BROTHER (#5) share
        `parent_member=7` (a hidden ancestor). Legacy emitted
        `5. брат (3)`."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Игнат", "Лавров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=72),
                      member(2, person("Матрена", "Архипова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=67),
                      member(3, person("Тимофей", "Лазарев",
                                       status="ясачный крестьянин"), CensusRole.NEPHEW, age=32, parent_member=7),
                      member(5, person("Фаддей", "Лазарев",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=27, parent_member=7),
                      member(7, person("Лазарь",
                                       status="ясачный крестьянин"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        self.assertIn("5. брат (3): Фаддей Лазаревич: -/27", out)

    def test_parent_member_suppresses_head_of_family_stub(self):
        """A household with BROTHER/SISTER members linked to a hidden
        ancestor via `parent_member=` represents an EXPLICIT upward
        lineage — the household head is the recorded HEAD, and the
        BROTHER's father is the hidden ancestor (e.g. a grandfather
        in #7 or #15). The translator must NOT emit the
        `unknown_..._not_recorded_head_of_family` stub for these
        households.

        Regression: a NEPHEW and a BROTHER both carry `parent_member=7`
        (a hidden ancestor). Legacy emitted no stub. The new translator
        was emitting one because BROTHER's effective_ref defaulted to 1
        once the old `ref_member=3` (brother-of-nephew) was migrated
        away."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Игнат", "Лавров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=72),
                      member(2, person("Матрена", "Архипова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=67),
                      member(3, person("Тимофей", "Лазарев",
                                       status="ясачный крестьянин"), CensusRole.NEPHEW, age=32, parent_member=7),
                      member(5, person("Фаддей", "Лазарев",
                                       status="ясачный крестьянин"), CensusRole.BROTHER, age=27, parent_member=7),
                      member(7, person("Лазарь",
                                       status="ясачный крестьянин"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        self.assertNotIn("not_recorded_head_of_family", out)

    def test_hidden_ancestor_union_emits_before_head_wife_union(self):
        """Legacy emits hidden-ancestor sub-family unions BEFORE the
        head+wife union of the same household — the family-tree
        narrative goes ancestors → descendants. Regression: legacy
        printed the hidden ancestor's union (`…_rs1-7_<year>`) before the
        head's (`…_rs1_<year>`); the new translator had them swapped."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Ипат", "Тимонов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=27, parent_member=7),
                      member(2, person("Фекла", "Тарасова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=22),
                      member(7, person("Тимон", "Бурмяев",
                                       status="ясачный крестьянин"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        simeon_pos = out.find('resource "geni_union" "timon_burmjaevich_rs1-7_1717"')
        ipat_pos = out.find('resource "geni_union" "ipatij_timonovich_rs1_1717"')
        self.assertNotEqual(simeon_pos, -1, "simeon sub-family union missing")
        self.assertNotEqual(ipat_pos, -1, "ipat head+wife union missing")
        self.assertLess(simeon_pos, ipat_pos,
                        "hidden-ancestor union must precede head+wife")

    def test_parent_member_drives_subfamily_union_without_overriding_doc_ref(self):
        """`parent_member=N` is the explicit upward parent link to a
        hidden ancestor, used purely for sub-family union emission.
        Unlike `ref_member=`, it does NOT change the document table's
        `(N)` label, which represents the CSV's primary
        `relationship-number` column (downward — e.g. FATHER OF #1).

        Concrete regression: setting `ref_member=15` on a FATHER role
        flipped the doc table from `3. отец (1)` to `3. отец (15)`,
        because the renderer treats ref_member as the table-display
        relative. Using `parent_member=15` instead keeps the table
        label at the default `(1)` (FATHER → defaults to head)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Харитон", "Прохоров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=37),
                      member(3, person("Прохор", "Мартынов",
                                       status="ясачный крестьянин"), CensusRole.FATHER, age=59, parent_member=15),
                      member(15, person("Мартын",
                                        status="ясачный крестьянин"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        # Doc table: FATHER must default to (1), NOT (15).
        self.assertIn("3. отец (1): Прохор Мартынович: -/59", out)
        # Sub-family union emitted: parent=Мартын, child=Прохор.
        self.assertIn(
            'resource "geni_union" "martin__rs1-15_1717"', out,
        )

    def test_head_with_ref_to_hidden_ancestor_emits_subfamily_union(self):
        """When the HEAD (or any non-child-role member) has `ref_member`
        pointing at a `hidden=True` ancestor, the translator emits a
        one-partner sub-family union connecting the hidden ancestor
        (parent) to the linked member (child).

        Regression: a household has a HEAD whose patronymic names a
        hidden father (hidden=True). Legacy emitted the sub-family union
        `…_rs1-7_<year>` with parent=the hidden father, child=the head.
        The new translator dropped it because pass (b)
        only iterated members with role in {SON, DAUGHTER, STEPSON,
        STEPDAUGHTER}; HEAD wasn't included. After the fix HEAD (and
        any other role) qualifies when its ref_member targets a hidden
        ancestor."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Ипат", "Тимонов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, ref_member=7, age=27),
                      member(2, person("Фекла", "Тарасова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=22),
                      member(7, person("Тимон", "Бурмяев",
                                       status="ясачный крестьянин"), CensusRole.SON, ref_member=8, age="?",
                             hidden=True), member(8, person("Бурмяй",
                                                            status="ясачный крестьянин"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        # Sub-family union: Тимон (parent) → Ипат (child).
        anchor = 'resource "geni_union" "timon_burmjaevich_rs1-7_1717"'
        self.assertIn(anchor, out)
        idx = out.find(anchor)
        end = out.find("\n}", idx)
        simeon_block = out[idx:end]
        self.assertIn(
            "_1717_00_00_timon_burmjaevich_rs_1_7_family_member.id",
            simeon_block,
        )
        self.assertIn(
            "_1717_00_00_ipatij_timonovich_rs_1_1_family_member.id",
            simeon_block,
        )

    def test_hidden_member_with_string_record_number_omits_death_stub(self):
        """A member declared with `hidden=True` is a placeholder profile
        for an out-of-revision ancestor referenced by ref_member. The
        revision book did not record them as alive in this year — so
        no `death = { range = "after"; year = N }` stub. The legacy
        output confirms: Гордей (hidden=True, age="?")
        carries no death block at all.

        Regression: regenerating a roll added an `after <year>` stub to
        a hidden member that the legacy file never had."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Кузьма", "Прохоров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=37),
                      member(14, person("Гордей", status="ясачный крестьянин"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1717_1.tf")
        block = _extract_resource_block(
            output, "_1717_00_00_gordij_rs_1_14_family_member",
        )
        self.assertNotIn("death = {", block)

    def test_household_document_emits_after_sub_family_unions(self):
        """Per legacy-committed `rs_*.tf` files,
        within one household block the emission order is:

            [member profiles] → [head+wife union] → [sub-family unions]
            → [household document]

        Sub-family unions (e.g. uncle+wife who live in the same house) must
        appear BEFORE the household geni_document, not after. Otherwise
        regenerating files with sub-families produces a noisy positional-
        only diff that has no semantic effect."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Кузьма", "Прохоров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=37),
                      member(2, person("Авдотья", "Лазарева",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=33),
                      member(3, person("Иосиф", "Мартынов",
                                       status="ясачный крестьянин"), CensusRole.UNCLE, age=52, record_number=12),
                      member(4, person("Анна", "Борисова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, ref_member=3, age=50)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1717_1.tf")

        sub_union_pos = output.find('resource "geni_union" "iosif_martynovich_rs12_1717"')
        document_pos = output.find('resource "geni_document" "census_of_the_family_number_1_1717"')
        self.assertNotEqual(sub_union_pos, -1, "sub-family union not emitted")
        self.assertNotEqual(document_pos, -1, "household document not emitted")
        self.assertLess(sub_union_pos, document_pos,
                        "sub-family union must precede household document")

    def test_birth_location_not_inferred_without_prev_revision_year(self):
        """The first census of a parish has no prior revision to compare
        against, so we can't infer that a young son was born locally — the
        source document only records where the family lives now, not
        where each member was born. With `prev_revision_year` left unset
        (default), the generator must NOT fabricate a birth.location."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Тозей", "Гордеев"), CensusRole.HEAD, age=47),
                      member(2, person("Иван", "Нилов"), CensusRole.SON, ref_member=1, age=6)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1717_1.tf")
        block = _extract_resource_block(
            output, "_1717_00_00_ioann_nilovich_rs_1_2_family_member",
        )
        # Sanity: birth date is still inferred from age.
        self.assertIn("birth = {", block)
        self.assertIn("circa", block)
        self.assertIn("year  = 1711", block)
        # Bug: birth.location must NOT be set — the source has no info.
        birth_block = re.search(
            r"birth = \{(?:[^{}]|\{[^{}]*\})*\}", block, re.DOTALL,
        )
        self.assertIsNotNone(birth_block, f"no birth block in:\n{block}")
        self.assertNotIn("location", birth_block.group(0))

    def test_birth_location_inferred_when_prev_revision_year_set(self):
        """When the DSL declares a prior revision via `prev_revision_year`,
        the absence-from-prior heuristic is sound: the family was already
        on record at the parish in the prior RS, so a young son with no
        `previous_age` must have been born after the prior RS — and
        therefore born here. The inference is allowed in this case."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Тозей", "Гордеев"), CensusRole.HEAD, age=47, previous_age=30),
                      member(2, person("Иван", "Нилов"), CensusRole.SON, ref_member=1, age=6)),
            prev_revision_year=1745,
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        block = _extract_resource_block(
            output, "_1762_00_00_ioann_nilovich_rs_1_2_family_member",
        )
        self.assertIn("birth = {", block)
        birth_block = re.search(
            r"birth = \{(?:[^{}]|\{[^{}]*\})*\}", block, re.DOTALL,
        )
        self.assertIsNotNone(birth_block)
        self.assertIn("location = {", birth_block.group(0))
        self.assertIn("село Горюхино", birth_block.group(0))

    def test_origin_overrides_inferred_birth_location(self):
        """When a member has an explicit `origin=`, that village wins —
        the gate change must not regress this. The origin-driven path is
        independent of `prev_revision_year`."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Тозей", "Гордеев"), CensusRole.HEAD, age=47),
                      member(2, person("Иван", "Нилов"), CensusRole.SON, ref_member=1, age=6, origin="Кожемяки")),
            prev_revision_year=1745,
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        block = _extract_resource_block(
            output, "_1762_00_00_ioann_nilovich_rs_1_2_family_member",
        )
        birth_block = re.search(
            r"birth = \{(?:[^{}]|\{[^{}]*\})*\}", block, re.DOTALL,
        )
        self.assertIsNotNone(birth_block)
        self.assertIn("location = {", birth_block.group(0))
        self.assertIn("Кожемяки", birth_block.group(0))
        self.assertNotIn("село Горюхино", birth_block.group(0))

    def test_inference_skipped_when_member_has_previous_age(self):
        """A member with `previous_age=` was on the prior RS, so their
        birthplace is already attested elsewhere. Don't re-infer it from
        the current parish — that's the existing per-member guard and
        must keep working after the gate is added."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1762,
            household(None, member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=41, previous_age=24)),
            prev_revision_year=1745,
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        block = _extract_resource_block(
            output, "_1762_00_00_timon_makarovich_rs_1_1_family_member",
        )
        birth_block = re.search(
            r"birth = \{(?:[^{}]|\{[^{}]*\})*\}", block, re.DOTALL,
        )
        self.assertIsNotNone(birth_block)
        self.assertNotIn("location", birth_block.group(0))

    def test_inference_skipped_when_member_has_arrival_reason(self):
        """A member with `arrival_reason=` came *into* this household from
        elsewhere after the prior RS. The absence of `previous_age` then
        signals an external arrival, not a post-prior-RS birth at this
        parish — birth.location must not fall back to the parish village.

        Case: a HEAD bought into the parish (`arrival_reason="куплен у
        …"`, `arrival_year` set). His actual birthplace is wherever the
        seller held him before the purchase. The parish-village default
        would be wrong."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Алексей", "Петров"), CensusRole.HEAD, age=33, arrival_year=1803,
                                   arrival_reason="куплен у помещика")),
            prev_revision_year=1795,
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1811_1.tf")
        block = _extract_resource_block(
            output, "_1811_00_00_aleksij_petrovich_rs_1_1_family_member",
        )
        birth_block = re.search(
            r"birth = \{(?:[^{}]|\{[^{}]*\})*\}", block, re.DOTALL,
        )
        self.assertIsNotNone(birth_block)
        self.assertNotIn("location", birth_block.group(0))

    def test_household_emits_head_wife_union_with_children(self):
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка",
            1795,
            household(None, member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=63),
                      member(2, person("Евдокия", "Игнатова"), CensusRole.WIFE, age=68),
                      member(3, person("Елисей"), CensusRole.SON, age=30),
                      member(4, person("Иван"), CensusRole.SON, age=28),
                      member(5, person("Мария"), CensusRole.DAUGHTER, age=25)),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        # 5 profiles for the members
        self.assertEqual(output.count('resource "geni_profile"'), 5,
                         f"expected 5 profiles; output:\n{output}")
        # Exactly one union for the head+wife family pattern
        self.assertEqual(output.count('resource "geni_union"'), 1,
                         f"expected 1 union; output:\n{output}")
        # Both partners and all three children referenced somewhere in output
        self.assertIn("_1_1_family_member", output)
        self.assertIn("_1_2_family_member", output)
        self.assertIn("_1_3_family_member", output)
        self.assertIn("_1_4_family_member", output)
        self.assertIn("_1_5_family_member", output)

        # The union block should contain all three child references in its
        # children list and both partners.
        union_start = output.index('resource "geni_union"')
        union_end = output.index("}\n", union_start)
        union_block = output[union_start:union_end]
        self.assertIn("children", union_block)
        self.assertIn("_1_3_family_member", union_block)
        self.assertIn("_1_4_family_member", union_block)
        self.assertIn("_1_5_family_member", union_block)
        self.assertIn("_1_1_family_member", union_block)
        self.assertIn("_1_2_family_member", union_block)

    def test_secondary_mother_routes_children_to_second_wife_union(self):
        """A child annotated with `secondary_role=SON/DAUGHTER` +
        `secondary_ref_member=<a second WIFE>` is routed into that
        wife's head+wife union and excluded from the head's primary
        wife union. Case: a household with two wives, the first dead —
        the 2nd wife bore the two hinted children while the 1st had died
        years earlier; without the hint both children land in the 1st
        wife's union."""
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка",
            1795,
            household(None, member(1, person("Герасим", "Егоров"), CensusRole.HEAD, age=60),
                      member(2, person("Матрена", "Андреева"), CensusRole.WIFE, age=55),
                      member(3, person("Дарья", "Иванова"), CensusRole.WIFE, age=40),
                      member(4, person("Ксения"), CensusRole.DAUGHTER, age=20),
                      member(5, person("Тимофей"), CensusRole.SON, age=5, secondary_role=CensusRole.SON,
                             secondary_ref_member=3),
                      member(6, person("Евдокия"), CensusRole.DAUGHTER, age=8, secondary_role=CensusRole.DAUGHTER,
                             secondary_ref_member=3)),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        def union_blocks(text):
            blocks, idx = [], 0
            while True:
                start = text.find('resource "geni_union"', idx)
                if start == -1:
                    break
                end = text.index("}\n", start)
                blocks.append(text[start:end])
                idx = end + 1
            return blocks

        blocks = union_blocks(output)
        self.assertEqual(len(blocks), 2,
                         f"expected 2 unions; output:\n{output}")
        matrena = next(b for b in blocks if "_1_2_family_member" in b)
        darija = next(b for b in blocks if "_1_3_family_member" in b)
        # Primary (Матрена) union: only the unhinted daughter Ксения.
        self.assertIn("_1_4_family_member", matrena)
        self.assertNotIn("_1_5_family_member", matrena)
        self.assertNotIn("_1_6_family_member", matrena)
        # Secondary (Дарья) union: the two hinted children only.
        self.assertIn("_1_5_family_member", darija)
        self.assertIn("_1_6_family_member", darija)
        self.assertNotIn("_1_4_family_member", darija)

    def test_household_without_wife_emits_head_only_union(self):
        """Legacy: a household with HEAD but no WIFE still emits a
        single-partner head-only union with attested children
        (effective_ref=1, no previous_age). Mirror that."""
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка",
            1795,
            household(None, member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=63),
                      member(2, person("Елисей"), CensusRole.SON, age=30)),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")

        self.assertEqual(output.count('resource "geni_union"'), 1)
        self.assertIn('resource "geni_union" "timon_makarovich_rs1_1795"', output)

    def test_head_only_union_keeps_prev_age_children_when_no_stub(self):
        """Legacy parity: when a household has HEAD + child(ren) but no
        BROTHER/SISTER member triggering an implied-parent stub union,
        the head-only union must include ALL child-role members —
        including those with `previous_age` set. The previous_age filter
        only exists to partition members between the stub union (which
        attests members already known from the prior RS) and the
        head-only union (new members). When no stub exists, children
        with previous_age have nowhere else to go and would be orphaned
        — legacy emitted them as the head's children in the head-only
        union.

        Regression: a HEAD (died) and a SON (died), both with
        previous_age. Legacy emitted the head-only union linking them;
        the new generator dropped it because the son was filtered out by
        the previous_age guard."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Мирон", "Ермилов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=64, previous_age=64,
                                   departure_year=1806, departure_reason="умер"), member(2, person("Герасим", "Миронов",
                                                                                                   status="ясачный крестьянин"),
                                                                                         CensusRole.SON, age=33,
                                                                                         previous_age=33,
                                                                                         departure_year=1796,
                                                                                         departure_reason="умер")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1811_1.tf")
        self.assertIn('resource "geni_union"', out)
        # Head-only union should include the SON despite his previous_age.
        anchor = out.find('resource "geni_union"')
        union_block = out[anchor:out.find('\n}', anchor)]
        self.assertIn(
            "_1811_00_00_gerasim_mironovich_rs_1_2_family_member.id",
            union_block,
        )

    def test_head_wife_union_routes_to_consolidated_when_head_move_listed(self):
        """Census head+wife union should be routed to consolidated_unions.tf
        when the head's profile is in profile_move_list — not duplicated in
        the per-year rs_*.tf. Legacy's rs_*.tf files have been trimmed to
        drop head+wife unions whose participants consolidate elsewhere."""
        import re as _re
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Иван", "Андреев"), CensusRole.HEAD, age=67),
                      member(2, person("Елена"), CensusRole.WIFE, age=63)),
        )
        # Probe to discover the actual head res_name (date prefix
        # depends on the household's record_day/record_month defaults;
        # the middle `_1_` here is the `suffix="1"` slot).
        probe = TerraformGenerator(village_dir=None)
        probe.add_census_records(records, suffix="1")
        probe_out = probe.get_output("rs_1834_1.tf")
        head_res_m = _re.search(
            r'resource "geni_profile" "(_1834_\d\d_\d\d_ioann_andreevich_rs[^"]*_family_member)"',
            probe_out,
        )
        self.assertIsNotNone(head_res_m, f"head profile not found:\n{probe_out}")
        head_res = head_res_m.group(1)

        consolidation = Consolidation(
            profile_move_list={head_res: "ioann_andreevich"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_census_records(records, suffix="1")
        gen.finalize()

        rs_output = gen.get_output("rs_1834_1.tf")
        consolidated = gen.get_output("consolidated_unions.tf")

        # Per-year file no longer holds the head+wife union.
        self.assertEqual(
            rs_output.count('resource "geni_union"'), 0,
            f"expected 0 unions in rs file when head is consolidated; got:\n{rs_output}",
        )
        # Consolidated bucket does.
        self.assertIn('resource "geni_union"', consolidated)

    def test_head_wife_union_stays_in_per_year_when_head_not_moved(self):
        """Control case: a head+wife union WITHOUT any consolidated
        participants remains in the per-year rs file (so we don't
        accidentally empty out every household's union)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Иван", "Андреев"), CensusRole.HEAD, age=67),
                      member(2, person("Елена"), CensusRole.WIFE, age=63)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        gen.finalize()
        rs_output = gen.get_output("rs_1834_1.tf")
        self.assertEqual(
            rs_output.count('resource "geni_union"'), 1,
            f"expected 1 union in rs file when nothing consolidated:\n{rs_output}",
        )

    def test_manual_add_member_emits_profile_in_per_year_file(self):
        """A `hidden=True` census member with the
        "Отсутствует в РС …" documentation comment emits its per-year
        profile so cross-references (sub-family unions, document
        profile lists, consolidated mappings) all resolve. The member
        is still skipped from the document text body (they're not in
        the actual revision book), but their profile resource exists
        and the about block surfaces the manual-add note."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40),
                      member(2, person("Пётр", "Иванов"), CensusRole.SON, age=10),
                      member(3, person("Николай", "Петров"), CensusRole.SON, age="?", hidden=True,
                             comment="Отсутствует в РС 1816; персона добавлена вручную по другим материалам.")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        gen.finalize()
        output = gen.get_output("rs_1816_1.tf")

        # Hidden member's profile resource IS emitted.
        self.assertIn(
            "_1816_00_00_nikolaj_petrovich_rs_1_3_family_member",
            output,
        )
        # The "Отсутствует в РС" note surfaces in the about block.
        self.assertIn("Отсутствует в РС 1816", output)
        # Hidden member is still absent from the document text body
        # (they aren't an actual revision-book row).
        self.assertNotIn("3. сын (1): Николай Петрович", output)
        # Non-hidden members still render normally.
        self.assertIn(
            "_1816_00_00_ioann_petrovich_rs_1_1_family_member",
            output,
        )
        self.assertIn("1. глава: Иоанн Петрович: -/40", output)
        # canonicalization: DSL 'Пётр' → canonical 'Петр'.
        self.assertIn("2. сын (1): Петр Иванович: -/10", output)

    def test_manual_add_member_routes_to_consolidated_when_move_listed(self):
        """If a manual-add member's res_name IS in profile_move_list,
        legacy still included the member on the consolidated profile's
        about block (carrying the 'персона добавлена вручную' note).
        Translator should route them via _emit_profile's consolidation
        path rather than dropping them entirely."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40),
                      member(2, person("Николай", "Петров"), CensusRole.SON, age="?", hidden=True,
                             comment="Отсутствует в РС 1816; персона добавлена вручную по другим материалам.")),
        )
        manual_member_res = "_1816_00_00_nikolaj_petrovich_rs_1_2_family_member"
        consolidation = Consolidation(
            profile_move_list={manual_member_res: "nikolaj_consolidated"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_census_records(records)
        gen.finalize()
        rs_output = gen.get_output("rs_1816_1.tf")
        consolidated = gen.get_output("consolidated_profiles_1.tf")

        # Still skipped from per-year file.
        self.assertNotIn(manual_member_res, rs_output)
        # And routed to consolidated — manual-add note surfaces there.
        self.assertIn('resource "geni_profile" "nikolaj_consolidated"',
                      consolidated)
        self.assertIn("Отсутствует в РС 1816", consolidated)


class TestCensusMemberAboutBlock(unittest.TestCase):
    """Member profiles carry an `about` block mirroring legacy's
    `<strong>РС {village} {year}:</strong> семья N` header, followed
    by `Титул/звание:` and a `Комментарий из РС {year} года:` block
    with `>` lines extracted from the DSL `comment=` field."""

    def test_member_with_status_emits_header_and_status(self):
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Емельян", "Ефимов",
                                             status="крестьянин помещицы Любви Александровны Маниловой"),
                                   CensusRole.HEAD, age=30,
                                   comment="ИО в документе: Емельян Ефимов")),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        self.assertIn("about = {", output)
        self.assertIn("<strong>РС Собакевичево 1834:</strong> семья 1", output)
        self.assertIn("Возраст: 30 лет", output)
        # Age line sits directly under the header, before Титул/звание.
        self.assertIn(
            "<strong>РС Собакевичево 1834:</strong> семья 1\n"
            "        Возраст: 30 лет\n"
            "        Титул/звание:",
            output,
        )
        self.assertIn(
            "Титул/звание: крестьянин помещицы Любви Александровны Маниловой",
            output,
        )
        self.assertIn("Комментарий из РС 1834 года:", output)
        self.assertIn(">ИО в документе: Емельян Ефимов", output)

    def test_member_about_always_has_document_name(self):
        """Even with no status/occupation/comment, the about block is now
        emitted: it always carries the auto-generated "ФИО/ИО/Имя в документе"
        line. (Емельян Ефимов has no surname → "ИО".)"""
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Емельян", "Ефимов"), CensusRole.HEAD, age=30)),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        self.assertIn("about = {", output)
        self.assertIn(">ИО в документе: Емельян Ефимов", output)

    def _member_about_output(self, m):
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, m),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        return gen.get_output("rs_1834_Собакевичево_1.tf")

    def test_member_about_unknown_age_omits_age_line(self):
        """Unknown-age sentinels ("?", "-", "", None) → no Возраст line."""
        for unknown in ("?", "-", ""):
            output = self._member_about_output(
                member(1, person("Емельян", "Ефимов", status="крестьянин"),
                       CensusRole.HEAD, age=unknown))
            self.assertNotIn("Возраст:", output)
        output = self._member_about_output(
            member(1, person("Емельян", "Ефимов", status="крестьянин"),
                   CensusRole.HEAD, age=None))
        self.assertNotIn("Возраст:", output)

    def test_member_about_string_age_renders_verbatim(self):
        output = self._member_about_output(
            member(1, person("Емельян", "Ефимов"), CensusRole.HEAD,
                   age="18 лет 6 мес"))
        self.assertIn("Возраст: 18 лет 6 мес", output)

    def test_hidden_member_about_omits_age_line(self):
        """Hidden (reconstructed) members are not recorded in the document,
        so their about carries no document age."""
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Иван", "Петров",
                                             status="крестьянин, умер до ревизии"),
                                   CensusRole.HEAD, age=70, hidden=True),
                      member(2, person("Пётр", "Иванов"), CensusRole.SON,
                             parent_member=1, age=30)),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        self.assertIn("Возраст: 30 лет", output)
        self.assertNotIn("Возраст: 70", output)

    def test_name_in_document_helper_labels(self):
        """_name_in_document labels by component presence: ФИО (name+patr+
        surname), ИО (name+patr), Имя (name only); surname dropped when
        last_name_in_book=False; uses the original-spelling fields verbatim."""
        from verso.ru.targets.geni.translator import _name_in_document
        self.assertEqual(
            _name_in_document(person("Ларионъ", "Васильевъ", "Маниловъ")),
            "ФИО в документе: Ларионъ Васильевъ Маниловъ")
        self.assertEqual(
            _name_in_document(person("Ларионъ", "Васильевъ")),
            "ИО в документе: Ларионъ Васильевъ")
        self.assertEqual(
            _name_in_document(person("Василей")),
            "Имя в документе: Василей")
        # last_name_in_book=False → surname suppressed → ИО, not ФИО.
        self.assertEqual(
            _name_in_document(person("Иван", "Петров", "Индюшев",
                                     last_name_in_book=False)),
            "ИО в документе: Иван Петров")

    def test_female_wife_gets_status_female_and_ia_line(self):
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40),
                      member(2, person("Анна"), CensusRole.WIFE, age=35)),
            archive_suffix="Собакевичево",
            defaults=RecordDefaults(
                status_male="крестьянин помещицы X",
                status_female="жена крестьянина помещицы X",
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        # Wife profile carries the жена-prefixed status, not the male default.
        self.assertIn("Титул/звание: жена крестьянина помещицы X", output)
        # Name only (no patronymic) → "Имя в документе".
        self.assertIn(">Имя в документе: Анна", output)

    def test_document_name_auto_generated_from_person(self):
        """The "в документе" line is auto-generated from person()'s original
        fields — no manual comment needed. Иван Петров has no surname → "ИО"."""
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Иван", "Петров",
                                             status="крестьянин помещицы X"), CensusRole.HEAD, age=40)),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        self.assertIn(">ИО в документе: Иван Петров", output)

    def test_pribyl_marker_with_year_becomes_gt_year_reason_line(self):
        """`прибыл: {reason} YYYY` → `>YYYY: {reason}` in the about
        block, matching legacy's corpus of rs_*.tf files.
        """
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Михайла", "Лазарев",
                                             status="крестьянин помещицы X"), CensusRole.HEAD, age=10,
                                   comment="прибыл: куплен у помещика с матерью 1834; ИО в документе: Михайла Лазарев")),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        # Legacy emits the прибыл reason as a `>YYYY: …` about line.
        self.assertIn(
            ">1834: куплен у помещика с матерью", output,
        )
        # ИО в документе: line still present.
        self.assertIn(">ИО в документе: Михайла Лазарев", output)

    def test_ubyl_marker_with_year_becomes_gt_year_reason_line(self):
        """`убыл: отдан в рекруты 1794` → `>1794: отдан в рекруты`."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Трофим", "Иванов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=40),
                      member(2, person("Григорий", "Семенов",
                                       status="ясачный крестьянин"), CensusRole.SON, age=7,
                             comment=("прошлая РС: 7 лет; убыл: отдан в рекруты "
                                      "1794; ФИО в документе: Григорий Семенов"))),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1795_1.tf")
        self.assertIn(">1794: отдан в рекруты", output)
        # No surname → "ИО" (auto-generated from person()).
        self.assertIn(">ИО в документе: Григорий Семенов", output)

    def test_ubyl_umer_year_does_not_leak_into_about(self):
        """`убыл: умер YYYY` is consumed by the death event — it
        must NOT appear as a `>YYYY: умер` about line."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Иван", "Петров",
                                             status="крестьянин помещицы X"), CensusRole.HEAD, age=40,
                                   comment="прошлая РС: 22 лет; убыл: умер 1812")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1816_1.tf")
        self.assertNotIn(">1812: умер", output)
        # But the death event still carries year 1812.
        death_m = re.search(r"death = \{\s*date = \{([^}]*)\}", output)
        self.assertIsNotNone(death_m)
        death_date = re.sub(r"\s+", " ", death_m.group(1)).strip()
        self.assertIn("year = 1812", death_date)

    def test_ubyl_with_destination_tail_strips_v_dest_from_gt_line(self):
        """`убыл: переведен ... в село Заречье 1812` → `>1812: переведен
        ... в село Заречье` — the trailing year is pulled out, but the
        in-prose destination (in the reason body) stays."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Иван", "Петров",
                                             status="крестьянин"), CensusRole.HEAD, age=40,
                                   comment=("убыл: переведен Дремучинской губернии "
                                            "Сонливской округи в село Заречье 1812"))),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1816_1.tf")
        self.assertIn(
            ">1812: переведен Дремучинской губернии Сонливской округи "
            "в село Заречье",
            output,
        )

    def test_rol_v_originale_marker_stripped_from_about(self):
        """`роль в оригинале: <phrase>` is consumed as the member's
        role-word in the text body (see TestCensusMemberCommentFormatting
        :test_role_v_originale_comment_becomes_role_word); it must NOT
        leak into the about block as a `>роль в оригинале:` line.
        """
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Харитон", "Прохоров",
                                             status="крестьянин"), CensusRole.HEAD, age=37),
                      member(2, person("Тозей", "Гордеев"), None, age=47, comment=("роль в оригинале: связь не указана; "
                                                                                  "ИО в документе: Тозей Гордеев"))),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1717_1.tf")
        # Extract the about block for member 2 — it may not be emitted
        # (no status), but if present, `роль в оригинале:` must not
        # appear as a gt line.
        self.assertNotIn(">роль в оригинале:", output)

    def test_structured_arrival_fields_drive_gt_line(self):
        """A DSL that populates the typed `arrival_reason` /
        `arrival_year` kwargs gets the same `>YYYY: reason` about line
        as one that uses the legacy `прибыл:` comment marker."""
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Михайла", "Лазарев",
                                             status="крестьянин помещицы X"), CensusRole.HEAD, age=10, arrival_year=1834,
                                   arrival_reason=(
                                       "куплен у помещика с матерью"
                                   ), comment="ИО в документе: Михайла Лазарев")),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        self.assertIn(
            ">1834: куплен у помещика с матерью", output,
        )
        self.assertIn(">ИО в документе: Михайла Лазарев", output)

    def test_proshlaya_rs_is_stripped(self):
        """`прошлая РС: N лет` segments appear elsewhere (text body) but
        not in the about block — they should be filtered."""
        records = census_records(
            "A", "1", "1", "1378", "Собакевичево", 1834,
            household(None, member(1, person("Иван", "Петров",
                                             status="крестьянин помещицы X"), CensusRole.HEAD, age=40,
                                   comment="прошлая РС: 22 лет; ИО в документе: Иван Петров")),
            archive_suffix="Собакевичево",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Собакевичево_1.tf")
        self.assertNotIn("прошлая РС", output.split("about = {")[1].split("EOT")[0])
        self.assertIn(">ИО в документе: Иван Петров", output)

    def test_arrival_reason_without_year_emits_bare_gt_line(self):
        """A member with `arrival_reason=` but no `arrival_year=` (e.g.
        an early-RS source where the year is implicit) must still emit
        the reason as a bare `>{reason}` about line. Otherwise the
        about block silently drops the only piece of information the
        DSL had about why this person appeared in this revision.

        Regression: an RS member has `arrival_reason="Указан в
        прибывших"` and no arrival_year. The legacy TF embedded
        `>Указан в прибывших` under `Комментарий из РС 1717 года:` — the
        new translator dropped
        the line because its emit branch required both reason AND year."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Кузьма", "Прохоров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=37),
                      member(2, person("Егор", "Прохоров",
                                       status="ясачный крестьянин"), CensusRole.SON, ref_member=1, age=2,
                             arrival_reason="Указан в прибывших")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1717_1.tf")
        block = _extract_resource_block(
            output, "_1717_00_00_georgij_prohorovich_rs_1_2_family_member",
        )
        self.assertIn("Комментарий из РС 1717 года:", block)
        self.assertIn(">Указан в прибывших", block)

    def test_departure_reason_without_year_emits_bare_gt_line(self):
        """Mirror of arrival_reason path: a `departure_reason=` without
        `departure_year=` (and not "умер") still surfaces as a bare
        `>{reason}` about line."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Иван", "Петров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=52,
                                   departure_reason="отдан в рекруты")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1795_1.tf")
        block = _extract_resource_block(
            output, "_1795_00_00_ioann_petrovich_rs_1_1_family_member",
        )
        self.assertIn("Комментарий из РС 1795 года:", block)
        self.assertIn(">отдан в рекруты", block)

    def test_arrival_reason_vzyata_v_zheny_suppressed_when_descriptor_present(self):
        """Legacy parity: `arrival_reason="взята в жены"` is redundant when
        the comment contains a descriptor that elaborates on it
        (e.g. "взятая со стороны...", "взятая в Неспешинском уезде..."). The
        legacy generator substituted the descriptor for the bare reason;
        the new generator must suppress the bare `>взята в жены` line in
        that case so it does not double up with the descriptor."""
        records = census_records(
            "A", "1", "1", "1074", "Горюхино", 1762,
            household(None, member(1, person("Кузьма", "Тимонов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=72),
                      member(2, person("Авдотья", "Прохорова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=66, origin="Свинорыловка",
                             arrival_reason="взята в жены", comment=("взятая в Неспешинском уезде, деревня "
                                                                     "Свинорыловка, ясачная; "
                                                                     "ИО в документе: Авдотья Прохорова"))),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        block = _extract_resource_block(
            output, "_1762_00_00_evdokija_prohorovna_rs_1_2_family_member",
        )
        self.assertIn(
            ">взятая в Неспешинском уезде, деревня Свинорыловка, ясачная",
            block,
        )
        self.assertNotIn(">взята в жены", block)

    def test_arrival_reason_vzyata_v_zheny_suppressed_when_starinnaja(self):
        """Legacy parity: `>старинная, той же деревни, ясачная` is the
        in-village descriptor counterpart to "взята в жены" and must
        also suppress the bare reason line."""
        records = census_records(
            "A", "1", "1", "1074", "Горюхино", 1762,
            household(None, member(1, person("Иван", "Иванов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=60),
                      member(2, person("Марья", "Петрова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=55, origin="Горюхино",
                             arrival_reason="взята в жены", comment=("старинная, той же деревни, ясачная; "
                                                                     "ИО в документе: Марья Петрова"))),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        block = _extract_resource_block(
            output, "_1762_00_00_marija_petrovna_rs_1_2_family_member",
        )
        self.assertIn(">старинная, той же деревни, ясачная", block)
        self.assertNotIn(">взята в жены", block)

    def test_departure_reason_vydana_zamuzh_suppressed_when_descriptor_present(self):
        """Legacy parity: `departure_reason="выдана замуж"` is suppressed
        when the comment carries the descriptive form
        "выдана в замужество в X за Y"."""
        records = census_records(
            "A", "1", "1", "1074", "Горюхино", 1762,
            household(None, member(1, person("Борис", "Иванов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=50),
                      member(2, person("Анастасия", "Борисова",
                                       status="ясачная крестьянка"), CensusRole.DAUGHTER, ref_member=1, age=27,
                             previous_age=10, departure_reason="выдана замуж",
                             comment=("выдана в замужество в Захребетский уезд, "
                                      "деревню Сонливку за ясачного; "
                                      "ИО в документе: Анастасия"))),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        block = _extract_resource_block(
            output, "_1762_00_00_anastasija_borisovna_rs_1_2_family_member",
        )
        self.assertIn(
            ">выдана в замужество в Захребетский уезд, деревню Сонливку за ясачного",
            block,
        )
        self.assertNotIn(">выдана замуж", block)

    def test_arrival_reason_vzyata_v_zheny_kept_when_no_descriptor(self):
        """Guard: when there is NO descriptor segment in the comment, the
        bare `>взята в жены` line must still be emitted — otherwise the
        about block would silently lose the only marriage signal."""
        records = census_records(
            "A", "1", "1", "1074", "Горюхино", 1762,
            household(None, member(1, person("Иван", "Иванов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=60),
                      member(2, person("Анна", "Петрова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=55,
                             arrival_reason="взята в жены",
                             comment="ИО в документе: Анна Петрова")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1762_1.tf")
        block = _extract_resource_block(
            output, "_1762_00_00_anna_petrovna_rs_1_2_family_member",
        )
        self.assertIn(">взята в жены", block)


class TestCensusRoleInFamilyAboutLine(unittest.TestCase):
    """The «Роль в семье» line names the member's position in the household —
    their own number, the role word, and the relative the role is measured
    against (in the genitive, with that person's number). It restates on the
    profile what the attached document's household table already shows, so the
    two must always agree; see `resolve_display_role`."""

    def _household_output(self, *members, village="Горюхино"):
        records = census_records(
            "A", "1", "1", "1385", village, 1834,
            household(None, *members),
            archive_suffix="Ж",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        return gen.get_output("rs_1834_Ж_1.tf")

    def _member_block(self, number, *members):
        """The profile block of household member `number`. Located by the
        `_rs_1_{number}_family_member` res_name suffix rather than the full
        name, which canonicalization rewrites (Авдотья → Евдокия)."""
        output = self._household_output(*members)
        names = [
            n for n in re.findall(r'resource "geni_profile" "([^"]+)"', output)
            if n.endswith(f"_{number}_family_member")
        ]
        assert len(names) == 1, f"member {number} → {names} in:\n{output}"
        return _extract_resource_block(output, names[0])

    def test_head_gets_the_bare_role_word(self):
        """HEAD carries no reference — it is the thing others refer to."""
        block = self._member_block(
            1,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
        )
        self.assertIn("Роль в семье: глава\n", block)

    def test_wife_names_the_husband_in_the_genitive(self):
        block = self._member_block(
            2,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
            member(2, person("Авдотья"), CensusRole.WIFE, age=25),
        )
        self.assertIn(
            "Роль в семье: жена Василия Семеновича", block,
        )

    def test_line_sits_after_the_fact_lines_before_the_comment_block(self):
        block = self._member_block(
            2,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
            member(2, person("Авдотья", status="ясачная крестьянка"),
                   CensusRole.WIFE, age=25),
        )
        self.assertIn(
            "Возраст: 25 лет\n"
            "        Титул/звание: ясачная крестьянка\n"
            "        Роль в семье: жена Василия Семеновича\n"
            "        Комментарий из РС 1834 года:",
            block,
        )

    def test_explicit_ref_member_points_at_the_sub_family_father(self):
        block = self._member_block(
            3,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
            member(2, person("Кузьма"), CensusRole.SON, age=20),
            member(3, person("Марфа"), CensusRole.DAUGHTER, ref_member=2, age=3),
        )
        self.assertIn(
            "Роль в семье: дочь Космы Васильевича", block,
        )

    def test_unreferenced_role_defaults_to_the_head(self):
        """Mirrors the document table, whose `relationship_number_orig` column
        defaulted to 1 — the about must not disagree with it."""
        block = self._member_block(
            2,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
            member(2, person("Прасковья", "Иванова"), CensusRole.SISTER, age=50),
        )
        self.assertIn(
            "Роль в семье: сестра Василия Семеновича", block,
        )

    def test_sibling_pair_derivation_beats_the_head_default(self):
        """A BROTHER with only `parent_member` refers to the ONE sibling
        sharing that parent, not to the head."""
        block = self._member_block(
            3,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=60),
            member(2, person("Максим", "Исаев"), CensusRole.SON,
                   parent_member=4, age=40),
            member(3, person("Федор", "Исаев"), CensusRole.BROTHER,
                   parent_member=4, age=35),
            member(4, person("Исай", "Петров"), CensusRole.SON, age="?",
                   hidden=True),
        )
        self.assertIn("Роль в семье: брат Максима Исаевича", block)

    def test_role_in_the_book_wording_wins(self):
        """`роль в оригинале:` supplies the displayed word for both the table
        and the about — the typed enum only drives the tree semantics."""
        block = self._member_block(
            2,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=60),
            member(2, person("Степан", "Иванов"), CensusRole.UNCLE, age=70,
                   comment="роль в оригинале: дядя родной"),
        )
        self.assertIn(
            "Роль в семье: дядя родной Василия Семеновича", block,
        )

    def test_member_without_a_role_gets_no_line(self):
        """The pre-1745 bare name lists record no relationship at all."""
        block = self._member_block(
            1,
            member(1, person("Емельян", last_name_orig="Недоедов"), None, age=80),
        )
        self.assertNotIn("Роль в семье:", block)

    def test_hidden_member_keeps_the_role(self):
        """The role is the one thing a reconstructed member's about otherwise
        never states — without it the section only says they are absent from
        the book, not why they hang off this household."""
        block = self._member_block(
            2,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
            member(2, person("Тимофей", "Семенов"), CensusRole.BROTHER,
                   age="?", hidden=True,
                   comment="Отсутствует в РС 1834; персона добавлена вручную."),
        )
        self.assertIn("Отсутствует в РС 1834", block)
        self.assertIn("Роль в семье: брат Василия Семеновича", block)

    def test_hidden_member_without_a_role_still_gets_no_line(self):
        block = self._member_block(
            2,
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
            member(2, person("Тимофей", "Семенов"), None, age="?", hidden=True,
                   comment="Отсутствует в РС 1834; персона добавлена вручную."),
        )
        self.assertNotIn("Роль в семье:", block)

    def test_relative_without_a_patronymic_renders_the_given_name_only(self):
        block = self._member_block(
            2,
            member(1, person("Варвара"), CensusRole.HEAD, age=60),
            member(2, person("Марфа"), CensusRole.DAUGHTER, age=30),
        )
        self.assertIn("Роль в семье: дочь Варвары", block)

    def test_about_and_document_table_never_disagree(self):
        """Anti-drift guard for the shared `resolve_display_role`.

        The about line drops the numbers, so it can no longer be compared to
        the table character-for-character. What must still hold is the claim
        underneath: for every `N. role (ref):` row, the profile of member N
        carries that same role word, naming the person the table's `(ref)`
        points at.
        """
        output = self._household_output(
            member(1, person("Василий", "Семенов"), CensusRole.HEAD, age=40),
            member(2, person("Кузьма"), CensusRole.SON, age=20),
            member(3, person("Авдотья"), CensusRole.WIFE, age=38),
            member(4, person("Марфа"), CensusRole.DAUGHTER, ref_member=2, age=3),
            member(5, person("Прасковья", "Иванова"), CensusRole.SISTER, age=50),
        )
        rows = re.findall(
            r"^\s*(\d+)\. ([^(:]+?)(?: \((\d+)\))?: ([^:]+): ", output, re.M,
        )
        self.assertEqual(len(rows), 5)
        table_names = {num: name.strip() for num, _, _, name in rows}
        for number, role_word, ref, _ in rows:
            block = _extract_resource_block(
                output,
                next(n for n in re.findall(
                    r'resource "geni_profile" "([^"]+)"', output)
                    if n.endswith(f"_{number}_family_member")),
            )
            line = next(
                (ln.strip() for ln in block.split("\n")
                 if ln.strip().startswith("Роль в семье:")), None)
            self.assertIsNotNone(line, f"member {number} has no role line")
            self.assertTrue(
                line.startswith(f"Роль в семье: {role_word}"),
                f"{line!r} disagrees with table row {number} ({role_word})")
            if ref:
                # The table names the referenced member in the nominative; the
                # about declines them, so compare on the given-name stem.
                given = table_names[ref].split()[0]
                self.assertIn(
                    given[:-1], line,
                    f"{line!r} must name member {ref} ({table_names[ref]})")
            else:
                self.assertEqual(line, f"Роль в семье: {role_word}")


class TestCensusPreviousRevisionAge(unittest.TestCase):
    """The `Возраст:` line carries the PREVIOUS revision's age when the book
    recorded one, so both halves of the census prev/cur pair reach the reader.
    The gap between them is what dates a person, and a gap that does not match
    the interval between revisions is the first sign of a bad merge."""

    def _block(self, number, *members):
        records = census_records(
            "A", "1", "1", "1385", "Горюхино", 1834,
            household(None, *members), archive_suffix="Ж",
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1834_Ж_1.tf")
        name = next(
            n for n in re.findall(r'resource "geni_profile" "([^"]+)"', output)
            if n.endswith(f"_{number}_family_member"))
        return _extract_resource_block(output, name)

    def test_previous_age_is_appended(self):
        block = self._block(
            1, member(1, person("Иван", "Петров"), CensusRole.HEAD,
                      age=17, previous_age=3))
        self.assertIn("Возраст: 17 лет (3 года, в предыдущей ревизии)", block)

    def test_absent_previous_age_leaves_the_line_alone(self):
        block = self._block(
            1, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=17))
        self.assertIn("Возраст: 17 лет\n", block)
        self.assertNotIn("предыдущей ревизии", block)

    def test_both_halves_go_through_format_age(self):
        """Agreement and unit expansion apply to the parenthetical too — it is
        reader-facing text, so it may not interpolate the raw value."""
        block = self._block(
            1, member(1, person("Иван", "Петров"), CensusRole.HEAD,
                      age="6 лет 6 мес", previous_age="1 год"))
        self.assertIn(
            "Возраст: 6 лет 6 месяцев (1 год, в предыдущей ревизии)", block)

    def test_repeated_age_is_not_rendered_twice(self):
        """Some DSL compresses prev and cur into the single `age` field (the
        source's «56/-» shape); the document table suppresses the repeat and
        so must this."""
        block = self._block(
            1, member(1, person("Иван", "Петров"), CensusRole.HEAD,
                      age=56, previous_age=56))
        self.assertIn("Возраст: 56 лет\n", block)
        self.assertNotIn("предыдущей ревизии", block)

    def test_comment_marker_is_honoured(self):
        """Older DSL wrote the value as a `прошлая РС:` comment marker."""
        block = self._block(
            1, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30,
                      comment="прошлая РС: 14 лет"))
        self.assertIn("Возраст: 30 лет (14 лет, в предыдущей ревизии)", block)

    def test_hidden_member_gets_neither_age(self):
        block = self._block(
            2,
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40),
            member(2, person("Сидор", "Петров"), CensusRole.BROTHER,
                   age=30, previous_age=14, hidden=True,
                   comment="Отсутствует в РС 1834; персона добавлена вручную."))
        self.assertNotIn("Возраст:", block)
        self.assertNotIn("предыдущей ревизии", block)


class TestCensusHouseholdDocument(unittest.TestCase):
    """Cat F: every household emits a `census_of_the_family_number_N_…`
    geni_document with tabulated member info. Legacy's dominant content
    in rs_*.tf files."""

    def _records(self, *, archive_suffix=None, suffix_in_res_names=False):
        return census_records(
            "ГА Глуповской области", "43", "6", "587", "Горюхино",
            1816,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=45,
                                   comment="прошлая РС: 30 лет; ФИО в документе: Иван Петров"),
                      member(2, person("Мария"), CensusRole.WIFE, age=40),
                      member(3, person("Сергей", "Иванов"), CensusRole.SON, age=10)),
            record_day=1, record_month=Month.MAY,
            archive_suffix=archive_suffix,
            suffix_in_res_names=suffix_in_res_names,
        )

    def _output(self, records):
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        filename = (
            f"rs_{records.year}_{records.archive_suffix}_1.tf"
            if records.archive_suffix else f"rs_{records.year}_1.tf"
        )
        return gen.get_output(filename)

    def test_document_resource_emitted_per_household(self):
        """One geni_document per household — `census_of_the_family_number_N_…`."""
        out = self._output(self._records(archive_suffix="43-6-587"))
        self.assertIn('resource "geni_document" "census_of_the_family_number_1_1816_43-6-587"', out)
        self.assertEqual(out.count('resource "geni_document"'), 1)

    def test_document_name_without_archive_suffix(self):
        """Files without archive_suffix use the shorter
        `census_of_the_family_number_N_{year}` name."""
        out = self._output(self._records())  # no archive_suffix
        self.assertIn('resource "geni_document" "census_of_the_family_number_1_1816"', out)

    def test_document_title_and_header_block(self):
        """Document title + description: 'Ревизская сказка X Y: семья N'
        followed by 6 metadata lines (архив / фонд / опись / дело /
        лист / № семьи)."""
        out = self._output(self._records(archive_suffix="43-6-587"))
        self.assertIn('title       = "Ревизская сказка Горюхино 1816: семья 1"', out)
        self.assertIn("Архив: ГА Глуповской области", out)
        self.assertIn("Фонд: 43", out)
        self.assertIn("Опись: 6", out)
        self.assertIn("Дело: 587", out)
        self.assertIn("№ семьи / № Двора: 1", out)

    def test_document_text_tabulates_members_with_roles(self):
        """Member table renders each person with role, name, and age:
        `1. глава: Иоанн Петрович: 30/45` for the head; WIFE → 'жена (1)',
        SON → 'сын (1)' (non-HEAD members default to referencing the
        head at #1)."""
        out = self._output(self._records(archive_suffix="43-6-587"))
        self.assertIn("1. глава: Иоанн Петрович: 30/45", out)
        self.assertIn("2. жена (1): Мария: -/40", out)
        self.assertIn("3. сын (1): Сергий Иванович: -/10", out)

    def test_document_profiles_reference_member_res_names(self):
        """`profiles = [...]` lists each household member's res_name
        (post-consolidation)."""
        out = self._output(self._records(archive_suffix="43-6-587"))
        # With date+suffix pieces: _1816_05_01_..._rs_1_1_family_member.
        self.assertIn(
            "geni_profile._1816_05_01_ioann_petrovich_rs_1_1_family_member.id",
            out,
        )

    def test_document_emitted_after_member_profiles(self):
        """Legacy orders resources per household as
        `[un-consolidated profiles, document, union]` — profiles land
        BEFORE the document. (The earlier Cat F PR flipped this and has
        been producing the wrong order; samples from legacy's
        rs_*.tf files show profiles consistently appearing first in a
        family's block when any exist un-consolidated.)"""
        out = self._output(self._records(archive_suffix="43-6-587"))
        doc_pos = out.find('resource "geni_document" "census_of_the_family_number_1_')
        profile_pos = out.find('resource "geni_profile" "_1816_05_01_')
        self.assertGreaterEqual(doc_pos, 0)
        self.assertGreaterEqual(profile_pos, 0)
        self.assertLess(profile_pos, doc_pos,
                         "un-consolidated member profiles must precede the document")

    def test_document_date_year_only(self):
        """Census documents use a year-only date (no day/month in the
        document's `date = { ... }`, even when page-level date is set)."""
        out = self._output(self._records(archive_suffix="43-6-587"))
        self.assertIn("date = {\n    year = 1816\n  }", out)

    def test_document_labels_census(self):
        out = self._output(self._records(archive_suffix="43-6-587"))
        self.assertIn('labels = [\n    "Census",\n  ]', out)

    def test_hidden_members_excluded_from_document_text_body(self):
        """Members declared with `hidden=True` are placeholder profiles
        for ancestors referenced via ref_member elsewhere — they were NOT
        enumerated in the original revision book's table. The household
        document's text body must mirror that: skip them in the
        `№. Роль … : age` list. They MAY still appear in the
        `profiles = [...]` list (so Geni links them to the document),
        matching legacy.

        Regression: regenerating a roll added `14. : …: -/-` rows for
        hidden members that the legacy committed file never had."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Кузьма", "Прохоров",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=37),
                      member(14, person("Гордей", status="ясачный крестьянин"), None, age="?", hidden=True),
                      member(15, person("Мартын", status="ясачная крестьянка"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        # Find the document body
        doc_block = out[out.find('resource "geni_document"'):]
        # Hidden members must NOT appear as table rows
        self.assertNotIn("14. : Гордий", doc_block)
        self.assertNotIn("15. : Мартин", doc_block)
        # Their profiles still get emitted as resources (other test).
        self.assertIn(
            'resource "geni_profile" "_1717_00_00_gordij_rs_1_14_family_member"',
            out,
        )

    def test_document_text_has_no_trailing_blank_line_before_eot(self):
        """The per-member renderer appends a blank-line separator after
        each member; the last member's separator must not surface as a
        trailing blank line before the heredoc terminator. Legacy ended
        the text body on the last member's last content line, with EOT
        immediately after."""
        out = self._output(self._records(archive_suffix="43-6-587"))
        # Bug shape: blank line then EOT (e.g. `\n\n                EOT`).
        # Must NOT match for either the description or text heredoc.
        self.assertNotRegex(
            out, r'\n\s*\n\s+EOT\b',
            f"regenerated rs document has blank line before EOT:\n{out}",
        )
        # Positive shape: text body ends on the last member's last content
        # line (now the auto-generated "Комментарий: … в документе" line),
        # immediately followed by the EOT terminator.
        self.assertRegex(
            out,
            r'Комментарий: ИО в документе: Сергей Иванов\n\s+EOT\b',
            f"last-member line not directly followed by EOT:\n{out}",
        )

    def test_document_text_member_separators_preserved_between_members(self):
        """Stripping the trailing blank line must not collapse the
        between-member `---` separators inside the text body.
        The fixture has 3 members + 1 table-header `---`, so 4 total."""
        out = self._output(self._records(archive_suffix="43-6-587"))
        text_block_match = re.search(
            r'text\s*=\s*<<-EOT\n(.+?)\n\s+EOT', out, re.DOTALL,
        )
        self.assertIsNotNone(text_block_match)
        text_body = text_block_match.group(1)
        # 1 table-header + 3 member `---` markers = 4 total.
        marker_count = sum(
            1 for line in text_body.splitlines() if line.strip() == "---"
        )
        self.assertEqual(
            marker_count, 4,
            f"expected 4 `---` markers (1 header + 3 members); got "
            f"{marker_count}; text body:\n{text_body}",
        )

    def test_document_res_name_transliterates_cyrillic_archive_suffix(self):
        """Legacy runs the archive_suffix through cyrillic_to_latin for the
        census doc res_name, so an Собакевичево suffix renders as 'sobakevichevo'.
        The filename / archive_suffix elsewhere keeps the original Cyrillic."""
        out = self._output(self._records(archive_suffix="11-6-412-Собакевичево"))
        self.assertIn(
            'resource "geni_document" "census_of_the_family_number_1_1816_11-6-412-sobakevichevo"',
            out,
        )
        self.assertNotIn(
            'resource "geni_document" "census_of_the_family_number_1_1816_11-6-412-Собакевичево"',
            out,
        )


class TestCensusMemberCommentFormatting(unittest.TestCase):
    """Cat F follow-up: `_render_census_member_lines` comment-segment edge
    cases. Legacy emits trailing 4-digit years in прибыл:/убыл: reasons as
    `(YEAR)` parentheticals; strips redundant `из ORIGIN` tails when the
    origin field already carries the same value; renders `?` / None age as
    `-`; suppresses empty `Комментарий:` lines.
    """

    def _render_one(self, *, age, comment=None, origin=None,
                    role=CensusRole.HEAD, ref_member=None):
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Иван", "Иванов"), role, ref_member=ref_member, age=age, origin=origin,
                                   comment=comment)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        return gen.get_output("rs_1834_1.tf")

    def test_ubyl_segment_trailing_year_becomes_parenthetical(self):
        """`убыл: умер 1826` → `Причина, основание убытия: умер (1826)`."""
        out = self._render_one(age=50, comment="убыл: умер 1826")
        self.assertIn("Причина, основание убытия: умер (1826)", out)
        self.assertNotIn("Причина, основание убытия: умер 1826", out)

    def test_pribyl_segment_trailing_year_and_origin_stripped(self):
        """`прибыл: <reason> 1818 из Ухабово` with `origin="Ухабово"`
        → reason retained, trailing `1818 из Ухабово` stripped and
        year emitted as `(1818)` parenthetical."""
        out = self._render_one(
            age="?",
            origin="Ухабово",
            comment=(
                "прибыл: Вновь причисленный в 1818 году, вольноотпущенный "
                "от господина. 1818 из Ухабово"
            ),
        )
        self.assertIn(
            "Причина, основание поступления/прибытия: "
            "Вновь причисленный в 1818 году, вольноотпущенный "
            "от господина. (1818)",
            out,
        )
        self.assertNotIn("1818 из Ухабово", out)

    def test_unknown_age_question_mark_renders_as_dash(self):
        """DSL `age="?"` → cur_age `-` (matches legacy fallback for
        empty `Лет (текущая РС)` column)."""
        out = self._render_one(age="?", comment="прошлая РС: 30 лет")
        self.assertIn(": 30/-", out)
        self.assertNotIn(": 30/?", out)

    def test_same_age_and_prev_without_markers_renders_as_prev_slash_dash(self):
        """When the DSL's `age` equals the `прошлая РС: X лет` comment value
        and there's no `прибыл:`/`убыл:` marker, the DSL has compressed
        legacy's two-column (Лет пред./текущая) layout into one slot —
        almost always because the current-revision column was empty in the
        source CSV. Translator should render `X/-` (prev only), not `X/X`
        (which is physically implausible across an 18-year revision gap).
        """
        out = self._render_one(
            age=60,
            comment="прошлая РС: 60 лет; ИО в документе: Китай",
        )
        self.assertIn(": 60/-", out)
        self.assertNotIn(": 60/60", out)

    def test_empty_remaining_comment_omits_komentarij_line(self):
        """When the comment contains only extractable markers
        (прошлая РС / прибыл / убыл), no `Комментарий:` line is emitted
        (legacy only emits it when the transcriber-comment column is set)."""
        out = self._render_one(
            age=50, comment="прошлая РС: 30 лет; убыл: умер 1834",
        )
        self.assertNotIn("Комментарий: \n", out)
        self.assertNotIn("Комментарий:\n", out)

    def test_non_head_member_defaults_ref_to_head_number(self):
        """Non-HEAD members without explicit `ref_member` implicitly
        reference the household head (member #1). Legacy CSV pipeline
        had `relationship_number_orig` default to 1 for non-HEAD rows;
        matches the `N. role (1): Name` rendering."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52),
                      member(2, person("Мария"), CensusRole.WIFE, age=45),
                      member(3, person("Пётр", "Иванов"), CensusRole.SON, age=20)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1834_1.tf")
        self.assertIn("2. жена (1): Мария: -/45", out)
        self.assertIn("3. сын (1): Петр Иванович: -/20", out)
        # Head itself still has no ref suffix.
        self.assertIn("1. глава: Иоанн Петрович: -/52", out)
        self.assertNotIn("1. глава (1):", out)

    def test_departed_member_renders_current_age_as_dash(self):
        """A member with an `убыл:` marker in the comment was not present
        in the current revision. Legacy's `Лет (текущая РС)` column was
        empty in that case, rendered as `-`. DSL authors sometimes
        copy-pasted `prev_age` into `age` anyway; coerce to `-` so
        `prev_age/-` matches legacy."""
        out = self._render_one(
            age=27,
            comment="прошлая РС: 27 лет; убыл: умер 1834",
        )
        self.assertIn(": 27/-", out)
        self.assertNotIn(": 27/27", out)

    def test_explicit_ref_member_overrides_head_default(self):
        """Explicit `ref_member=N` wins over the HEAD-default; this
        preserves grandchild/nephew relations (ref=parent, not head)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=62),
                      member(2, person("Пётр", "Иванов"), CensusRole.SON, age=35),
                      member(3, person("Сергей", "Петров"), CensusRole.GRANDSON, ref_member=2, age=10)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1834_1.tf")
        self.assertIn("3. внук (2): Сергий Петрович: -/10", out)

    def test_bare_name_after_prosh_rs_now_renders_as_pometki(self):
        """The legacy bare-name→Комментарий heuristic is gone: the
        `Комментарий:` line is now the auto-generated "в документе" name
        from person(), and any remaining free-text (a bare name with no
        explicit prefix) renders as `Пометки:`."""
        out = self._render_one(
            age=49, role=None,
            comment="прошлая РС: 23 лет; Пракофей Филатов",
        )
        self.assertIn("Комментарий: ИО в документе: Иван Иванов", out)
        self.assertIn("Пометки: Пракофей Филатов", out)

    def test_freetext_phrase_after_prosh_rs_still_renders_as_pometki(self):
        """Long free-text comments (anything beyond 1-3 capitalized tokens)
        remain `Пометки:` — the name-like heuristic must not misclassify
        true notes."""
        out = self._render_one(
            age=50,
            comment="прошлая РС: 30 лет; 5 недель в первой ревизии",
        )
        self.assertIn("Пометки: 5 недель в первой ревизии", out)
        self.assertNotIn("Комментарий: 5 недель в первой ревизии", out)

    def test_residual_v_dokumente_label_superseded_by_autogen(self):
        """A residual hand-written 'Имя/ИО/ФИО в документе:' segment is
        dropped (the name is auto-generated from person() now), so it never
        double-renders; the computed line is the one shown."""
        out = self._render_one(
            age=40, role=None,
            comment="прошлая РС: 22 лет; Имя в документе: Маскай",
        )
        self.assertIn("Комментарий: ИО в документе: Иван Иванов", out)
        self.assertNotIn("Маскай", out)

    def test_role_none_member_renders_without_role_word_or_ref(self):
        """A census member with `role=None` (unspecified relationship —
        trailing family extras the DSL couldn't classify) renders with
        neither a role word nor a parenthesized ref. Legacy only defaulted
        `relationship_number_orig=1` for members with a declared role;
        role=None rows stayed fully bare."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Тимофей", "Лаврентьев"), CensusRole.HEAD, age=62),
                      member(2, person("Прохор", "Дементиев"), None, age=47)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1811_1.tf")
        # No role word, no default "(1)" ref.
        self.assertIn("2. : Прохор Дементиевич: -/47", out)
        self.assertNotIn("2.  (1):", out)

    def test_role_v_originale_overrides_typed_role_word(self):
        """When a member has BOTH a typed role (e.g. CensusRole.UNCLE)
        and a `comment="роль в оригинале: <phrase>"` annotation, the
        comment phrase wins for display purposes — the typed role still
        provides downstream semantics (gender derivation, sub-family
        union detection) but the household document shows the original
        CSV phrasing.

        Concrete regression: the source CSV has 'дядя родной' (paternal
        consanguineous uncle) for an uncle. The DSL has
        `CensusRole.UNCLE` (which maps to bare 'дядя'). Without the
        comment-based override, the more specific 'родной' qualifier
        was silently lost from the rendered document."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37),
                      member(12, person("Иосиф", "Мартынов"), CensusRole.UNCLE, age=52,
                             comment="роль в оригинале: дядя родной; ИО в документе: Осип Мартынов")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        self.assertIn("12. дядя родной (1): Иосиф Мартынович: -/52", out)
        # The role-original marker is consumed; no Пометки line for it.
        self.assertNotIn("Пометки: роль в оригинале:", out)
        self.assertNotIn("Комментарий: роль в оригинале:", out)
        # ИО в документе is auto-generated from person() (Иосиф Мартынов); the
        # residual manual "Осип Мартынов" label is superseded.
        self.assertIn("Комментарий: ИО в документе: Иосиф Мартынов", out)

    def test_role_v_originale_comment_becomes_role_word(self):
        """When a member has role=None but comment contains 'роль в
        оригинале: <phrase>', legacy substitutes that phrase for the
        empty role slot (e.g. 'связь не указана') and applies the
        default (1) ref. Mirror that — and ensure the marker itself is
        stripped from the Пометки free-text."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37),
                      member(6, person("Тозей", "Гордеев"), None, age=47, comment=(
                          "роль в оригинале: связь не указана; "
                          "Указано, что живет в особой избе; "
                          "ИО в документе: Тозей Гордеев"
                      ))),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1717_1.tf")
        # Role phrase substituted + (1) ref applied (canonical
        # patronymic "Гордеевич" for father-name "Гордей"). Legacy
        # canonicalizes Тозей → Тазей via names.csv.
        self.assertIn("6. связь не указана (1): Тазей Гордеевич: -/47", out)
        # Remaining free-text and 'ИО в документе:' still render in
        # document body.
        self.assertIn("Пометки: Указано, что живет в особой избе", out)
        self.assertIn("Комментарий: ИО в документе: Тозей Гордеев", out)
        # The 'роль в оригинале:' marker is consumed by the role-word
        # substitution — ensure the document text body never emits it
        # as a standalone Пометки line.
        self.assertNotIn("Пометки: роль в оригинале:", out)
        self.assertNotIn("Комментарий: роль в оригинале:", out)


class TestCensusMemberDestinationTextBody(unittest.TestCase):
    """Legacy's text body for a moved-out member emits two paired
    lines — `Населенный пункт куда отправлены/убыли: X` (the target
    village) and `Причина, основание убытия: {reason}` (with the
    ` в X` tail stripped, since the destination is rendered
    separately). Mirrors the arrival-side pair
    (`Населенный пункт откуда поступили/прибыли:` + `Причина,
    основание поступления/прибытия:`)."""

    def _render(self, *, members, year=1762, village="Горюхино"):
        records = census_records(
            "A", "1", "1", "1", village, year,
            household(None, *members),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        return gen.get_output(f"rs_{year}_1.tf")

    def test_comment_dest_emits_destination_line_and_trims_reason(self):
        out = self._render(members=[
            member(1, person("Анна", "Иванова",
                             status="ясачная крестьянка"), CensusRole.HEAD, age=18,
                   comment=("убыл: выдана замуж в Неелово; "
                            "ИО в документе: Анна")),
        ])
        self.assertIn(
            "Населенный пункт куда отправлены/убыли: Неелово", out,
        )
        self.assertIn("Причина, основание убытия: выдана замуж", out)
        # The "в Неелово" tail is stripped; reason doesn't duplicate it.
        self.assertNotIn(
            "Причина, основание убытия: выдана замуж в Неелово", out,
        )

    def test_mid_string_v_destination_with_year_not_duplicated(self):
        # "переведен ... в село Заречье 1812" has "в X" MID-reason
        # (trailing year follows). The trailing-tail regex won't match,
        # so no destination line, and the reason text preserves the
        # original "в село Заречье" phrase. Matches legacy's behavior
        # for this pattern.
        out = self._render(members=[
            member(1, person("Иван", "Петров",
                             status="крестьянин"), CensusRole.HEAD, age=40,
                   comment=("убыл: переведен Дремучинской губернии "
                            "Сонливской округи в село Заречье 1812")),
        ], year=1816)
        self.assertNotIn("Населенный пункт куда отправлены/убыли:", out)
        self.assertIn(
            "Причина, основание убытия: переведен Дремучинской "
            "губернии Сонливской округи в село Заречье (1812)",
            out,
        )

    def test_structured_destination_emits_line(self):
        # Same as the comment case but via typed kwargs.
        out = self._render(members=[
            member(1, person("Анна", "Иванова",
                             status="ясачная крестьянка"), CensusRole.HEAD, age=18, destination="Неелово",
                   departure_reason="выдана замуж"),
        ])
        self.assertIn(
            "Населенный пункт куда отправлены/убыли: Неелово", out,
        )
        self.assertIn("Причина, основание убытия: выдана замуж", out)

    def test_no_destination_no_line(self):
        # Sanity: no destination on either side means no dest line.
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, comment="убыл: отдан в рекруты 1794"),
        ])
        self.assertNotIn("Населенный пункт куда отправлены/убыли:", out)


class TestCensusStructuredFieldsOverrideComment(unittest.TestCase):
    """`CensusMember` now exposes typed arrival/departure fields. The
    translator must prefer them over the legacy comment-string parse
    and still render the same surface artifacts (death event year,
    current_residence override, (YYYY) parentheticals in text body,
    and Пометки preservation)."""

    def _render(self, *, members, year=1834, village="Горюхино"):
        records = census_records(
            "A", "1", "1", "1", village, year,
            household(None, *members),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        return gen.get_output(f"rs_{year}_1.tf")

    def test_structured_departure_year_overrides_comment_umer(self):
        # When both sources disagree, the typed field wins.
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52, departure_year=1834, departure_reason="умер",
                   comment="убыл: умер 1826"),
        ])
        death_m = re.search(r"death = \{\s*date = \{([^}]*)\}", out)
        self.assertIsNotNone(death_m)
        death_date = re.sub(r"\s+", " ", death_m.group(1)).strip()
        self.assertIn("year = 1834", death_date)
        self.assertNotIn("1826", death_date)

    def test_structured_destination_overrides_comment_v_village(self):
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, destination="Неелово",
                   comment="убыл: выдана замуж в Свинорыловка"),
        ])
        # current_residence should use the structured destination.
        current_residence_m = re.search(
            r"current_residence = \{([^}]*)\}", out,
        )
        self.assertIsNotNone(current_residence_m)
        self.assertIn("Неелово", current_residence_m.group(1))
        self.assertNotIn("Свинорыловка", current_residence_m.group(1))

    def test_structured_arrival_year_renders_as_parenthetical(self):
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30, arrival_year=1818,
                   arrival_reason="вновь причисленный"),
        ])
        self.assertIn(
            "Причина, основание поступления/прибытия: "
            "вновь причисленный (1818)",
            out,
        )

    def test_structured_departure_reason_renders_in_text_body(self):
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52, departure_year=1834, departure_reason="умер"),
        ])
        self.assertIn("Причина, основание убытия: умер (1834)", out)

    def test_structured_arrival_reason_renders_in_text_body(self):
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30, arrival_year=1820,
                   arrival_reason="вновь причисленный"),
        ])
        self.assertIn(
            "Причина, основание поступления/прибытия: "
            "вновь причисленный (1820)",
            out,
        )

    def test_fallback_parses_comment_when_structured_fields_none(self):
        # Regression guard: legacy DSL files (no structured fields)
        # keep working via the comment-regex fallback.
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52, comment="убыл: умер 1826"),
        ])
        death_m = re.search(r"death = \{\s*date = \{([^}]*)\}", out)
        self.assertIsNotNone(death_m)
        death_date = re.sub(r"\s+", " ", death_m.group(1)).strip()
        self.assertIn("year = 1826", death_date)

    def test_structured_departure_umer_not_rendered_as_about_gt_line(self):
        # Structured `departure_reason="умер"` is consumed by the
        # death event; it must NOT surface as a `>YYYY: умер` about
        # line. (`прибыл:` / `убыл:` with other reasons DO surface —
        # see TestCensusMemberAboutBlock.)
        out = self._render(members=[
            member(1, person("Иван", "Петров",
                             status="крестьянин помещицы Х"), CensusRole.HEAD, age=30, arrival_year=1818,
                   arrival_reason="вновь причисленный", departure_year=1834, departure_reason="умер"),
        ])
        about_m = re.search(r"about = \{.*?\}", out, re.DOTALL)
        self.assertIsNotNone(about_m)
        about_block = about_m.group(0)
        self.assertIn("Титул/звание:", about_block)
        # Arrival surfaces as a gt line (legacy parity).
        self.assertIn(">1818: вновь причисленный", about_block)
        # Departure is 'умер' — death event consumes it.
        self.assertNotIn(">1834: умер", about_block)
        # Raw marker text never leaks in either direction.
        self.assertNotIn("прибыл:", about_block)
        self.assertNotIn("убыл:", about_block)

    def test_free_text_pometki_preserved_when_structured_fields_set(self):
        # Comment free-text (no markers) remains in Пометки even when
        # structured arrival/departure fields carry the marker data.
        out = self._render(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30, arrival_year=1820,
                   arrival_reason="вновь причисленный", comment="жил в особой избе"),
        ])
        self.assertIn(
            "Причина, основание поступления/прибытия: "
            "вновь причисленный (1820)",
            out,
        )
        self.assertIn("Пометки: жил в особой избе", out)


class TestCensusMemberInferredBirthLocation(unittest.TestCase):
    """Inference rules for a male member's birth.location. When the DSL
    declares `prev_revision_year` (the parish has a known prior RS) AND
    the member has a plain integer age AND no explicit `origin` AND no
    `прошлая РС:` marker, the translator sets `birth.location =
    village`. Without `prev_revision_year`, no inference happens —
    that's covered separately in `TestCensusTranslation`."""

    def _member_block(self, *, m, year=1834, village="Горюхино",
                      h_index=1, prev_revision_year=1816):
        records = census_records(
            "A", "1", "1", "1", village, year,
            household(None, *m),
            prev_revision_year=prev_revision_year,
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        return gen.get_output(f"rs_{year}_1.tf")

    def _birth_location_from(self, out, res_name):
        block = _extract_resource_block(out, res_name)
        birth_m = re.search(
            r"birth = \{(.*?)\n  \}", block, re.DOTALL,
        )
        if not birth_m:
            return None
        loc_m = re.search(
            r"location = \{([^}]*)\}", birth_m.group(1), re.DOTALL,
        )
        return loc_m.group(1) if loc_m else None

    def test_son_without_origin_or_prev_rs_gets_parish_birth_location(self):
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52),
            member(2, person("Семен"), CensusRole.SON, age=10),
        ])
        # Son: no origin, no prev-rs marker → parish inferred.
        son_loc = self._birth_location_from(
            out, "_1834_00_00_simeon_ivanovich_rs_1_2_family_member",
        )
        self.assertIsNotNone(son_loc)
        self.assertIn("Горюхино", son_loc)

    def test_head_without_origin_gets_parish_birth_location(self):
        # HEAD is in the inferred-male role set too.
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52),
        ])
        head_loc = self._birth_location_from(
            out, "_1834_00_00_ioann_petrovich_rs_1_1_family_member",
        )
        self.assertIsNotNone(head_loc)
        self.assertIn("Горюхино", head_loc)

    def test_explicit_origin_wins_over_inferred_parish(self):
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52, origin="Неелово"),
        ])
        head_loc = self._birth_location_from(
            out, "_1834_00_00_ioann_petrovich_rs_1_1_family_member",
        )
        self.assertIsNotNone(head_loc)
        self.assertIn("Неелово", head_loc)
        self.assertNotIn("Горюхино", head_loc)

    def test_prev_rs_marker_suppresses_inferred_birth_location(self):
        # A `прошлая РС: N лет` marker signals the member was present
        # in the previous revision → NOT born inter-revision, so no
        # parish inference.
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52, comment="прошлая РС: 32 лет"),
        ])
        head_loc = self._birth_location_from(
            out, "_1834_00_00_ioann_petrovich_rs_1_1_family_member",
        )
        self.assertIsNone(head_loc)

    def test_wife_does_not_get_inferred_parish_birth_location(self):
        # Female roles are excluded — a wife brought in from elsewhere
        # shouldn't be presumed born locally.
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52),
            member(2, person("Мария"), CensusRole.WIFE, age=45),
        ])
        wife_loc = self._birth_location_from(
            out, "_1834_00_00_marija_rs_1_2_family_member",
        )
        self.assertIsNone(wife_loc)

    def test_daughter_does_not_get_inferred_parish_birth_location(self):
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52),
            member(2, person("Анна"), CensusRole.DAUGHTER, age=12),
        ])
        daughter_loc = self._birth_location_from(
            out, "_1834_00_00_anna_ivanovna_rs_1_2_family_member",
        )
        self.assertIsNone(daughter_loc)

    def test_unknown_age_suppresses_inferred_birth_location(self):
        # `age="?"` (unknown) isn't an integer → cannot infer the
        # birth year and legacy also skipped the parish inference.
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age="?"),
        ])
        head_loc = self._birth_location_from(
            out, "_1834_00_00_ioann_petrovich_rs_1_1_family_member",
        )
        self.assertIsNone(head_loc)

    def test_brother_role_not_in_inferred_role_set(self):
        # BROTHER is male but NOT in the legacy-inferred-role set
        # (SON/GRANDSON/NEPHEW/STEPSON/HEAD). A brother's birth
        # location stays unknown without explicit origin.
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52),
            member(2, person("Пётр", "Петров"), CensusRole.BROTHER, age=40),
        ])
        brother_loc = self._birth_location_from(
            out, "_1834_00_00_petr_petrovich_rs_1_2_family_member",
        )
        self.assertIsNone(brother_loc)

    def test_nephew_inherits_parish_birth_location(self):
        out = self._member_block(m=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=52),
            member(2, person("Пётр"), CensusRole.NEPHEW, age=10),
        ])
        nephew_loc = self._birth_location_from(
            out, "_1834_00_00_petr_rs_1_2_family_member",
        )
        self.assertIsNotNone(nephew_loc)
        self.assertIn("Горюхино", nephew_loc)


class TestCensusMemberDestinationFromComment(unittest.TestCase):
    """Retroactive coverage: when a member's `comment`
    contains a `убыл: … в X` marker (e.g. 'выдана замуж в X',
    'Переведен … в X'), the translator sets `current_residence` to X
    instead of the parish. Mirrors legacy's separate 'Н.П. куда
    отправлены / убыли' column that the DSL collapses into the
    comment."""

    def _residence_block(self, *, comment, age=40, village="Горюхино",
                         year=1834):
        records = census_records(
            "A", "1", "1", "1", village, year,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=age, comment=comment)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output(f"rs_{year}_1.tf")
        block = _extract_resource_block(
            out, "_1834_00_00_ioann_petrovich_rs_1_1_family_member",
        )
        res_m = re.search(
            r"current_residence = \{([^}]*)\}", block,
        )
        return res_m.group(1) if res_m else None

    def test_vydana_zamuzh_v_moves_residence_to_destination(self):
        residence = self._residence_block(
            comment="убыл: выдана замуж в Неелово",
        )
        self.assertIsNotNone(residence)
        self.assertIn("Неелово", residence)
        self.assertNotIn("Горюхино", residence)

    def test_perevezen_v_moves_residence_to_destination(self):
        residence = self._residence_block(
            comment="убыл: Переведен в Неелово",
        )
        self.assertIsNotNone(residence)
        self.assertIn("Неелово", residence)
        self.assertNotIn("Горюхино", residence)

    def test_unknown_destination_falls_back_to_parish(self):
        # Legacy's `_location()` returns None for names not in
        # the corpus's places; the translator must fall back to the parish
        # instead of dropping `current_residence` entirely.
        residence = self._residence_block(
            comment="убыл: выдана замуж в НетТакойДеревни",
        )
        self.assertIsNotNone(residence)
        self.assertIn("Горюхино", residence)

    def test_umer_without_destination_preserves_parish_residence(self):
        # `убыл: умер 1826` has no `в X` segment — the destination
        # regex must NOT match, and residence stays at the parish.
        residence = self._residence_block(
            comment="убыл: умер 1826",
        )
        self.assertIsNotNone(residence)
        self.assertIn("Горюхино", residence)

    def test_no_ubyl_marker_preserves_parish_residence(self):
        residence = self._residence_block(
            comment="прошлая РС: 22 лет",
        )
        self.assertIsNotNone(residence)
        self.assertIn("Горюхино", residence)

    def test_destination_respects_semicolon_segment_boundary(self):
        # Comment with multiple `;`-separated segments: the destination
        # name must end at the `;` boundary and not absorb the
        # subsequent segment.
        residence = self._residence_block(
            comment="убыл: выдана замуж в Неелово; прошлая РС: 22 лет",
        )
        self.assertIsNotNone(residence)
        self.assertIn("Неелово", residence)
        self.assertNotIn("прошлая", residence)


class TestCensusBirthYearFromPrevRevision(unittest.TestCase):
    """Census members whose DSL `age=X` is actually the prev-revision
    age (e.g. когда source-CSV current column was empty → DSL collapses
    prev and cur into one field) get the wrong birth year under
    `year - age`. Legacy's precomputed birth column matches the rule
    `prev_revision_year - prev_age`, derived from either the typed
    `previous_age` kwarg or the `прошлая РС: X лет` comment marker.
    """

    def _birth_year(self, *, members, year, village="Горюхино", prev_revision=None):
        records = census_records(
            "A", "1", "1", "1", village, year,
            household(None, *members),
        )
        gen = TerraformGenerator(village_dir=None, prev_revision=prev_revision)
        gen.add_census_records(records)
        out = gen.get_output(f"rs_{year}_1.tf")
        birth_m = re.search(r"birth = \{\s*date = \{([^}]*)\}", out)
        self.assertIsNotNone(birth_m, f"no birth block in:\n{out}")
        date = re.sub(r"\s+", " ", birth_m.group(1)).strip()
        y = re.search(r"year\s*=\s*(\d+)", date)
        self.assertIsNotNone(y, f"no year in birth date: {date}")
        return int(y.group(1))

    def test_compressed_age_uses_prev_revision_formula(self):
        # 1816 → prev revision 1811. age=30 = prev_age → birth 1781.
        y = self._birth_year(year=1816, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30, comment="прошлая РС: 30 лет"),
        ])
        self.assertEqual(y, 1781)

    def test_different_prev_and_current_age_uses_prev(self):
        # 1816, cur=34, prev=30 → birth 1781.
        y = self._birth_year(year=1816, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=34, comment="прошлая РС: 30 лет"),
        ])
        self.assertEqual(y, 1781)

    def test_structured_previous_age_overrides_comment(self):
        # Typed wins over comment-parsed prev_age.
        y = self._birth_year(year=1816, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, previous_age=29, comment="прошлая РС: 30 лет"),
        ])
        self.assertEqual(y, 1811 - 29)

    def test_no_prev_marker_falls_back_to_current_age(self):
        y = self._birth_year(year=1816, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=66),
        ])
        self.assertEqual(y, 1816 - 66)

    def test_census_year_without_known_prev_revision_falls_back(self):
        # 1700 isn't in the revision map → translator uses year - age.
        y = self._birth_year(year=1700, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, previous_age=35),
        ])
        self.assertEqual(y, 1700 - 40)

    def test_deceased_member_without_current_age_births_from_prev_age(self):
        # A roll of 1858 (prev revision 1850): a child who died between
        # revisions has NO current-age column in the source — the DSL
        # carries only previous_age. Birth = 1850 - 1.5 → 1848 (circa),
        # not census_year - age (which would postdate the death).
        y = self._birth_year(year=1858, members=[
            member(1, person("Максимъ", "Ивановъ"), CensusRole.HEAD,
                   previous_age="1.5", departure_year=1854,
                   departure_reason="умер"),
        ])
        self.assertEqual(y, 1848)

    def test_bare_decimal_string_age_still_births(self):
        # A roll's `age="58.5"` (a bare decimal STRING, no
        # unit word): must parse like the float 58.5, not fall through as
        # unparseable (which silently dropped the birth event entirely).
        y = self._birth_year(year=1850, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age="58.5"),
        ])
        self.assertEqual(y, 1850 - 58)

    def test_the_library_dates_1815_by_the_1811_revision(self):
        # The library's table is the revision chain; 1815 is the 7th revision.
        y = self._birth_year(year=1815, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=20, previous_age=20)])
        self.assertEqual(y, 1811 - 20)

    def test_a_village_keeps_its_frozen_exception(self):
        # Горюхино's village.toml: 1815 → 1795 (the legacy CSV's), 1721 → none.
        y = self._birth_year(year=1815, prev_revision={1815: 1795, 1721: None}, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=20, previous_age=20)])
        self.assertEqual(y, 1795 - 20)
        y = self._birth_year(year=1721, prev_revision={1815: 1795, 1721: None}, members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=20, previous_age=20)])
        self.assertEqual(y, 1721 - 20)

    def test_parity_across_all_known_revisions(self):
        # Each (current_census_year, expected_prev_revision_year) pair.
        cases = [
            (1745, 1719),
            (1762, 1745),
            (1795, 1782),
            (1811, 1795),
            (1816, 1811),
            (1834, 1816),
            (1850, 1834),
            (1858, 1850),
        ]
        for census_year, prev_rev in cases:
            with self.subTest(census_year=census_year):
                y = self._birth_year(year=census_year, members=[
                    member(1, person("Иван", "Петров"), CensusRole.HEAD, age=20, previous_age=20),
                ])
                self.assertEqual(y, prev_rev - 20)


class TestCensusBirthDateFromTypedFields(unittest.TestCase):
    """When a census member carries `birth_day`, `birth_month`, and/or
    `birth_year` typed kwargs, the translator emits the precise date
    on the member's `birth` event instead of the
    `prev_revision_year - prev_age` or `year - age` estimates.

    Sourced from the legacy CSV columns `Дата рождения (если указана)`
    and `Год рождения (расчётный)`.
    """

    def _render_birth(self, *, members, year=1850, village="Горюхино"):
        records = census_records(
            "A", "1", "1", "1", village, year,
            household(None, *members),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output(f"rs_{year}_1.tf")
        m = re.search(r"birth = \{\s*date = \{([^}]*)\}", out)
        return m.group(1) if m else None

    def test_full_birth_date_renders_specific_date(self):
        block = self._render_birth(members=[
            member(1, person("Егор", "Тихонов"), CensusRole.HEAD, age=9, birth_day=14, birth_month=Month.JANUARY,
                   birth_year=1841),
        ])
        self.assertIsNotNone(block)
        assert block is not None
        normalized = re.sub(r"\s+", " ", block).strip()
        self.assertIn("day = 14", normalized)
        self.assertIn("month = 1", normalized)
        self.assertIn("year = 1841", normalized)
        # Specific date — not circa.
        self.assertNotIn("circa", normalized)

    def test_birth_year_only_overrides_age_estimate(self):
        # Only year is set; translator emits circa year (consistent with
        # other circa-only birth events) but skips the prev-revision
        # formula and `year - age` fallback.
        block = self._render_birth(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=20, previous_age=15, birth_year=1830),
        ])
        self.assertIsNotNone(block)
        assert block is not None
        normalized = re.sub(r"\s+", " ", block).strip()
        self.assertIn("year = 1830", normalized)
        # Without day/month, legacy uses circa.
        self.assertIn("circa = true", normalized)

    def test_typed_birth_year_wins_over_prev_age(self):
        # 1850 census, prev_age=10 (would give 1834 - 10 = 1824); but
        # explicit birth_year=1820 overrides.
        block = self._render_birth(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=20, previous_age=10, birth_year=1820),
        ])
        self.assertIsNotNone(block)
        assert block is not None
        normalized = re.sub(r"\s+", " ", block).strip()
        self.assertIn("year = 1820", normalized)
        self.assertNotIn("year = 1824", normalized)

    def test_role_none_suppresses_ref_parenthetical(self):
        """When `role=None` (unrelated/independent person sharing the
        household — e.g. a lodger, an unaffiliated adult) and no
        `роль в оригинале:` override fills the role slot, the doc-table
        line should render WITHOUT the `(N)` ref parenthetical, even
        if the DSL carries `ref_member=`. Legacy used the source CSV's
        primary relationship columns (both empty for such rows) and
        emitted neither role nor ref.

        Regression: a member has `role=None, ref_member=7` (the
        secondary CSV column "сын 7"). Legacy emitted `2. : …`; the
        new generator added a stray `(7)` because the ref-display
        guard didn't gate on role being non-empty."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Тимофей", "Лаврентьев"), CensusRole.HEAD, age=62),
                      member(2, person("Прохор", "Дементиев"), None, ref_member=7, age=47),
                      member(7, person("Дементий"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1811_1.tf")
        # Empty role + no ref parenthetical: "2. : Прокопий ...".
        self.assertIn("2. : Прохор Дементиевич: ", out)
        self.assertNotIn("2.  (7): Прохор", out)

    def test_role_override_keeps_ref_parenthetical(self):
        """Guard: when `role=None` BUT a `роль в оригинале:` comment
        override fills the role slot, the ref parenthetical SHOULD
        still render — the override carries the role information,
        and the ref still anchors the relationship."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Иван", "Иванов"), CensusRole.HEAD, age=50),
                      member(2, person("Петр", "Петров"), None, ref_member=1, age=30,
                             comment="роль в оригинале: связь не указана")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1811_1.tf")
        # Role override + ref both render.
        self.assertIn("2. связь не указана (1): Петр Петрович:", out)

    def test_string_previous_age_does_not_raise(self):
        """A `previous_age="5 нед"` (5 weeks) string must not crash the
        translator. Legacy CSVs sometimes record fractional / sub-year
        ages in the prior-revision column when the previous revision
        recorded an infant. The string should be treated as
        "approximately 0 years for birth-year derivation" — the
        document body still shows it verbatim. No ValueError, no
        traceback.

        Concrete regression: a member has `previous_age="5 нед"` in the
        source CSV; the DSL would carry that string. The translator used
        `int(v)` which raised `ValueError: invalid literal for int()
        with base 10: '5 нед'`."""
        block = self._render_birth(members=[
            member(1, person("Иван", "Петров"), CensusRole.HEAD, age=17, previous_age="5 нед"),
        ])
        # Birth-year resolution: 1834 (prev RS) - 0.096 yrs ≈ 1833 after
        # int truncation. The key invariant is: no crash, and a year
        # got emitted.
        self.assertIsNotNone(block)
        assert block is not None
        normalized = re.sub(r"\s+", " ", block).strip()
        self.assertIn("year = 1833", normalized)


class TestCensusSubFamilyUnions(unittest.TestCase):
    """Legacy emits one union per nuclear family inside a census
    household — not just the main HEAD+WIFE pair. Sub-family unions
    fire for every WIFE whose `ref_member` points at a non-HEAD parent
    (UNCLE, FATHER, BROTHER, adult SON), and for any non-HEAD member
    with children pointing at them via `ref_member` (lone sub-head).

    Legacy res_name convention (from the legacy rs_*.tf files):
        `{canon_first} {canon_mid} {canon_last} rs{record_number} {year}`
    where `record_number` is the global `№ п/п` from the source CSV
    (passed in via the typed `record_number` kwarg).
    """

    def _render_rs(self, *, members, year=1717, village="Горюхино"):
        records = census_records(
            "A", "1", "1", "1", village, year,
            household(None, *members),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        return gen.get_output(f"rs_{year}_1.tf")

    def test_uncle_with_wife_emits_subfamily_union(self):
        # Household: HEAD+WIFE (main union) AND UNCLE+WIFE(ref=UNCLE).
        out = self._render_rs(members=[
            member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37, record_number=1),
            member(2, person("Авдотья", "Лазарева"), CensusRole.WIFE, age=33, record_number=2),
            member(12, person("Иосиф", "Мартынов"), CensusRole.UNCLE, age=52, record_number=12),
            member(13, person("Анна", "Борисова"), CensusRole.WIFE, ref_member=12, age=50, record_number=13),
        ])
        # Sub-family union name uses Iosif and
        # patronymic Мартинович (canonical for Мартынов).
        self.assertIn(
            'resource "geni_union" "iosif_martynovich_rs12_1717"', out,
        )

    def test_subfamily_union_partners_reference_correct_profiles(self):
        out = self._render_rs(members=[
            member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37, record_number=1),
            member(2, person("Авдотья", "Лазарева"), CensusRole.WIFE, age=33, record_number=2),
            member(12, person("Иосиф", "Мартынов"), CensusRole.UNCLE, age=52, record_number=12),
            member(13, person("Анна", "Борисова"), CensusRole.WIFE, ref_member=12, age=50, record_number=13),
        ])
        # Block for the iosif_martynovich_rs12_1717 union should
        # reference Iosif and Anna's per-year RS profiles.
        block = re.search(
            r'resource "geni_union" "iosif_martynovich_rs12_1717" \{[^}]+\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(block)
        body = block.group(0)
        self.assertIn("iosif_martynovich_rs_1_12_family_member", body)
        self.assertIn("anna_borisovna_rs_1_13_family_member", body)

    def test_subfamily_union_attaches_children_via_ref_member(self):
        out = self._render_rs(members=[
            member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37, record_number=1),
            member(2, person("Авдотья", "Лазарева"), CensusRole.WIFE, age=33, record_number=2),
            member(3, person("Прохор", "Мартынов"), CensusRole.FATHER, age=59, record_number=3),
            member(4, person("Марья", "Ефимова"), CensusRole.WIFE, ref_member=3, age=47, record_number=4),
            member(11, person("Егор", "Прохоров"), CensusRole.SON, ref_member=3, age=2, record_number=11),
        ])
        block = re.search(
            r'resource "geni_union" "prohor_martynovich_rs3_1717" \{.*?\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(block)
        body = block.group(0)
        # Children include Georgij (SON with ref_member=3).
        self.assertIn("georgij_prohorovich_rs_1_11_family_member", body)

    def test_lone_sub_head_emits_partners_only_union(self):
        # A non-HEAD member with children pointing at them via
        # ref_member but no WIFE → union with single partner.
        # `Пичкинзов` canonicalizes to `Пичкинзович` via the existing
        # patronymic table, matching legacy's union name.
        out = self._render_rs(members=[
            member(1, person("Игнат", "Лавров"), CensusRole.HEAD, age=72, record_number=1),
            member(2, person("Матрена", "Архипова"), CensusRole.WIFE, age=67, record_number=2),
            member(22, person("Тимофей", "Пичкинзов"), CensusRole.NEPHEW, age=32, record_number=22),
            member(23, person("Прохор", "Тимофеев"), CensusRole.SON, ref_member=22, age=7, record_number=23),
            member(24, person("Лаврентий", "Тимофеев"), CensusRole.SON, ref_member=22, age=2, record_number=24),
        ])
        # Union with just timofej_pichkinzovich as the lone partner.
        self.assertIn(
            'resource "geni_union" "timofej_pichkinzovich_rs22_1717"', out,
        )

    def test_subfamily_union_uses_autoincremented_record_number(self):
        # When DSL omits explicit `record_number=`, CensusRecords.__init__
        # auto-assigns from DSL order. The sub-family union still
        # emits, using the auto-incremented number for the rs token.
        out = self._render_rs(members=[
            member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37),
            member(2, person("Авдотья", "Лазарева"), CensusRole.WIFE, age=33),
            member(12, person("Иосиф", "Мартынов"), CensusRole.UNCLE, age=52),
            member(13, person("Анна", "Борисова"), CensusRole.WIFE, ref_member=12, age=50),
        ])
        # Auto-counter: m1=1, m2=2, m12=3, m13=4 → rs3 for the
        # sub-family union (since UNCLE is the 3rd member in DSL order,
        # not the 12th).
        self.assertIn(
            'resource "geni_union" "iosif_martynovich_rs3_1717"', out,
        )

    def test_household_union_consolidates_when_only_child_is_in_move_list(self):
        """Slice 6b.3: legacy routes a household's HEAD+WIFE union to
        `consolidated_unions.tf` when ANY participant — head, wife, OR
        child — is in `profile_move_list`. The new translator previously
        only checked head and wife, so unions whose only consolidated
        participant was a child wrongly went to the per-year file.

        Mirrors `Горюхино/generate_config.py:1979` where
        `at_least_one_consolidated_profile(*union_profile_res_names)`
        folds children into the check via
        `union_profile_res_names = [head, wife?, *children]`.
        """
        # Probe: render once without consolidation, learn the child's
        # per-year res_name, then re-render with that child consolidated.
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37),
                      member(2, person("Авдотья", "Лазарева"), CensusRole.WIFE, age=33),
                      member(3, person("Фаддей"), CensusRole.SON, age=5)),
        )
        probe = TerraformGenerator(village_dir=None)
        probe.add_census_records(records)
        probe_out = probe.get_output("rs_1717_1.tf")
        m = re.search(
            r'resource "geni_profile" "(_1717_00_00_faddej_haritonovich_rs_1_3_family_member)"',
            probe_out,
        )
        self.assertIsNotNone(
            m, f"could not find Тихон's profile in probe:\n{probe_out}",
        )
        child_res = m.group(1)

        consolidation = Consolidation(
            profile_move_list={child_res: "faddej_haritonovich"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_census_records(records)
        gen.finalize()

        year_file = gen.get_output("rs_1717_1.tf")
        consolidated = gen.get_output("consolidated_unions.tf")

        # Without the fix, the HEAD+WIFE union would land in the per-year
        # file. After the fix, it must land in consolidated_unions.tf
        # because Тихон (consolidated) is a child of that union.
        self.assertNotIn(
            'resource "geni_union" "hariton_prohorovich_rs1_1717"', year_file,
            f"household union should not be in per-year file when a "
            f"child is consolidated; output:\n{year_file}",
        )
        self.assertIn("hariton_prohorovich", consolidated)
        self.assertIn("faddej_haritonovich", consolidated)

    def test_subfamily_union_consolidates_when_only_child_is_in_move_list(self):
        """Same children-based routing rule applies to sub-family
        unions (Pass a + Pass b in `tf_translator.py`)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1717,
            household(None, member(1, person("Харитон", "Прохоров"), CensusRole.HEAD, age=37),
                      member(2, person("Авдотья", "Лазарева"), CensusRole.WIFE, age=33),
                      member(3, person("Иосиф", "Мартынов"), CensusRole.UNCLE, age=52),
                      member(4, person("Анна", "Борисова"), CensusRole.WIFE, ref_member=3, age=50),
                      member(5, person("Григорий", "Осипов"), CensusRole.SON, ref_member=3, age=8)),
        )
        probe = TerraformGenerator(village_dir=None)
        probe.add_census_records(records)
        probe_out = probe.get_output("rs_1717_1.tf")
        # "Осипов" canonicalizes to "Осипович" via the patronymic
        # table, so the per-year profile uses `grigorij_osipovich`.
        m = re.search(
            r'resource "geni_profile" "(_1717_00_00_grigorij_osipovich_rs_1_5_family_member)"',
            probe_out,
        )
        self.assertIsNotNone(m)
        son_res = m.group(1)

        consolidation = Consolidation(
            profile_move_list={son_res: "grigorij_osipovich"},
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_census_records(records)
        gen.finalize()

        year_file = gen.get_output("rs_1717_1.tf")
        consolidated = gen.get_output("consolidated_unions.tf")

        # The sub-family union (iosif_martynovich_rs3_1717) now must land
        # in consolidated_unions.tf because Григорий is consolidated.
        self.assertNotIn(
            'resource "geni_union" "iosif_martynovich_rs3_1717"', year_file,
        )
        self.assertIn(
            "iosif_martynovich",
            consolidated,
        )

    def test_head_only_union_not_duplicated_by_pass_b_for_hidden_child(self):
        """Regression: a household of one roll (HEAD Иван Иванов, no WIFE,
        hidden DAUGHTER with ref_member=1) emitted the head-only union TWICE —
        once via the no-WIFE head-only path and again via Pass (b) "lone
        sub-heads" because the dedup guard `seen_subhead_nums` only
        excluded heads that paired with a visible WIFE. With no WIFE the
        head's number was never registered, so Pass (b) re-emitted the
        same HEAD → hidden-DAUGHTER relationship under the same res_name,
        producing invalid HCL (duplicate `resource "geni_union"` blocks)."""
        out = self._render_rs(members=[
            member(1, person("Иван", "Иванов"), CensusRole.HEAD, age=64, record_number=5),
            member(4, person(patr_orig="Иванова"), CensusRole.DAUGHTER, ref_member=1, age="?", hidden=True),
        ], year=1811)
        # Exactly one union resource — not two.
        self.assertEqual(
            out.count('resource "geni_union" "ioann_ivanovich_rs5_1811"'), 1,
            f"head-only union emitted twice (Pass-b duplication):\n{out}",
        )


class TestCensusHeadOfFamilyStub(unittest.TestCase):
    """Legacy emitted a synthetic `unknown_rs_{N}_not_recorded_head_of_family`
    profile whenever a census household had a BROTHER/SISTER member — the
    brothers' implicit father (not listed in the household) got an anchor
    profile so consolidation could merge it with the derivable canonical
    profile (e.g. `grigorij` with `additional_info.first_name="Григорий"`).
    """

    def _records_with_brother(self, *, archive_suffix=None,
                              suffix_in_res_names=False):
        return census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Эраст", "Петров"), CensusRole.HEAD, age=34),
                      member(2, person("Иван", "Петров"), CensusRole.BROTHER, age=17),
                      member(3, person("Николай", "Эрастов"), CensusRole.SON, age=1)),
            archive_suffix=archive_suffix,
            suffix_in_res_names=suffix_in_res_names,
        )

    def test_household_with_brother_emits_head_of_family_stub(self):
        out = _run_generator(self._records_with_brother())
        self.assertIn(
            'resource "geni_profile" '
            '"_1811_00_00_unknown_rs_1_not_recorded_head_of_family"',
            out,
        )

    def test_head_of_family_stub_has_legacy_about_text(self):
        out = _run_generator(self._records_with_brother())
        self.assertIn("семья 1, глава семьи (явно не указан)", out)

    def test_head_of_family_stub_marks_male_deceased_public(self):
        out = _run_generator(self._records_with_brother())
        # The stub resource should carry these three attributes.
        # (Translator emits GeniProfile's raw format — terraform fmt
        # later re-aligns the `=` column.)
        stub_block = _extract_resource_block(
            out, "_1811_00_00_unknown_rs_1_not_recorded_head_of_family"
        )
        self.assertIn('gender = "male"', stub_block)
        self.assertIn('alive  = false', stub_block)
        self.assertIn('public = true', stub_block)

    def test_head_of_family_stub_without_brother_is_not_emitted(self):
        """A vanilla HEAD + WIFE + SON household has no implicit
        out-of-household ancestor — no stub should appear."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40),
                      member(2, person("Марья"), CensusRole.WIFE, age=35),
                      member(3, person("Пётр", "Иванов"), CensusRole.SON, age=10)),
        )
        out = _run_generator(records)
        self.assertNotIn("not_recorded_head_of_family", out)

    def test_head_of_family_stub_emitted_when_mother_role_refs_non_head(self):
        """A MOTHER member with `ref_member` pointing at a non-HEAD
        member is the mother of THAT member, not of HEAD — so the
        head's parent generation is still implicit and the stub must
        be emitted. Regression: a household with a HEAD, a hidden
        BROTHER and a MOTHER whose ref_member=2 names the nephew (so she
        is the nephew's mother). Legacy emitted a head_of_family stub
        with an implied parent of the head and the hidden brother; the
        new translator was bailing because ANY MOTHER role suppressed
        the stub trigger."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1850,
            household(None, member(1, person("Фока", "Лазарев"), CensusRole.HEAD, age=64),
                      member(2, person("Сидор", "Ипатов"), CensusRole.NEPHEW, age=39, parent_member=9),
                      member(8, person("Мавра", "Макарова"), CensusRole.MOTHER, ref_member=2, age=66),
                      member(9, person("Ипат", "Лазарев"), CensusRole.BROTHER, age="?", hidden=True)),
        )
        out = _run_generator(records)
        self.assertIn(
            "_1850_00_00_unknown_rs_1_not_recorded_head_of_family",
            out,
        )

    def test_head_of_family_stub_always_appends_archive_suffix(self):
        """Legacy's stub unconditionally carries the archive_suffix in
        its res_name when the file has one — independent of the
        `suffix_in_res_names` flag that controls member profiles."""
        records = self._records_with_brother(
            archive_suffix="11-6-412-Собакевичево", suffix_in_res_names=False,
        )
        out = _run_generator(records)
        # Legacy lowercases the suffix in the res_name via
        # cyrillic_to_latin — "Собакевичево" → "sobakevichevo".
        self.assertIn(
            "_1811_00_00_unknown_rs_1_not_recorded_head_of_family_11-6-412-sobakevichevo",
            out,
        )

    def test_head_of_family_stub_inherits_birth_location_from_shared_origin(
        self,
    ):
        """When every visible member of a stub-triggering household
        shares the same `origin=`, the implied unrecorded ancestor was
        born there too. Legacy emitted that as `birth.location` on the
        stub. Regression: households of one roll whose members all
        carry `origin="Фамусово"` because the family was transferred
        in. The legacy stub had `birth.location = село Фамусово …`;
        the new translator was emitting the stub with `birth=None`."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Афанасий", "Герасимов"), CensusRole.HEAD, age=32, origin="Фамусово",
                                   arrival_year=1814,
                                   arrival_reason="Переведен из Трясинского уезда"),
                      member(2, person("Иван", "Герасимов"), CensusRole.BROTHER, age=22, origin="Фамусово",
                             arrival_year=1814,
                             arrival_reason="Переведен из Трясинского уезда")),
        )
        out = _run_generator(records)
        stub_block = _extract_resource_block(
            out, "_1816_00_00_unknown_rs_1_not_recorded_head_of_family"
        )
        # Origin "Фамусово" must surface as the stub's birth location;
        # the canonical entry of the corpus's places is `село Фамусово`.
        self.assertIn("birth = {", stub_block)
        self.assertIn("location", stub_block)
        self.assertIn("село Фамусово", stub_block)

    def test_head_of_family_stub_skips_birth_location_when_origins_differ(
        self,
    ):
        """Mixed `origin=` across members → no inference (the
        unrecorded ancestor's village is genuinely unknown)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Афанасий", "Герасимов"), CensusRole.HEAD, age=32, origin="Фамусово"),
                      member(2, person("Иван", "Герасимов"), CensusRole.BROTHER, age=22, origin="Кукишево")),
        )
        out = _run_generator(records)
        stub_block = _extract_resource_block(
            out, "_1816_00_00_unknown_rs_1_not_recorded_head_of_family"
        )
        self.assertNotIn("birth = {", stub_block)


class TestCensusHeadWifePairing(unittest.TestCase):
    """A `WIFE` member is paired with the head of household ONLY when
    her `ref_member` is unset or points at the head. A WIFE whose
    `ref_member` references another member (e.g., a brother of the
    head) belongs in HIS sub-family union, not the head's."""

    def test_wife_with_ref_to_brother_not_paired_with_head(self):
        """Regression: a household had a HEAD, a BROTHER (mn=2) and a
        WIFE (mn=5, ref_member=2) who is the brother's wife. Old code
        picked the first WIFE as the head's wife, putting her in BOTH
        the head's and the brother's unions. After the fix she must NOT
        appear as a partner with the head in any union."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Афанасий", "Герасимов"), CensusRole.HEAD, age=32),
                      member(2, person("Иван", "Герасимов"), CensusRole.BROTHER, age=22),
                      member(5, person("Параскева"), CensusRole.WIFE, ref_member=2, age=22)),
        )
        out = _run_generator(records)
        # No union may pair Афанасий with Параскева (they aren't
        # married). Find every geni_union block and check.
        for u_match in re.finditer(
            r'resource "geni_union" "[^"]*" \{(.*?)\n\}', out, re.DOTALL,
        ):
            block = u_match.group(1)
            partners_match = re.search(
                r'partners\s*=\s*\[(.*?)\]', block, re.DOTALL,
            )
            if not partners_match:
                continue
            partners = partners_match.group(1).lower()
            has_afanasij = "afanasij_gerasimov" in partners
            has_paraskeva = (
                "paraskeva" in partners
            )
            self.assertFalse(
                has_afanasij and has_paraskeva,
                f"Афанасий wrongly paired with Параскева in union: {block}",
            )
        # The core invariant — never co-partner Афанасий + Параскева —
        # is checked by the loop above. Whether Ioann's sub-family
        # union itself emits depends on `record_number` propagation
        # which is orthogonal to this regression; that's covered by
        # other tests.

    def test_no_wife_branch_still_emits_subfamily_union_for_brother_wife(
        self,
    ):
        """When the head has no paired wife (e.g. recruited away,
        leaving an effectively unattached household), Pass (a) — the
        sub-family union for a WIFE whose `ref_member` points at a
        BROTHER of the head — must STILL fire. Originally Pass (a)
        only ran in the head+wife branch; without it the legitimate
        Иван+Параскева union silently disappeared from the household
        after head-wife pairing was tightened."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Афанасий", "Герасимов"), CensusRole.HEAD, age=32, departure_year=1812,
                                   departure_reason="отдан в рекруты"),
                      member(2, person("Иван", "Герасимов"), CensusRole.BROTHER, age=22),
                      member(5, person("Параскева"), CensusRole.WIFE, ref_member=2, age=22)),
        )
        out = _run_generator(records)
        # Sub-family union for Иван+Параскева must appear. The exact
        # union res_name suffix depends on Иван's auto-assigned
        # `record_number` (a global counter), so just match by name
        # prefix.
        ioann_union = re.search(
            r'resource "geni_union" "ioann_gerasimov[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(
            ioann_union,
            "Иван+Параскева sub-family union not emitted in no-WIFE branch",
        )
        block = ioann_union.group(1).lower()
        self.assertIn("ioann_gerasimov", block)
        self.assertTrue(
            "paraskeva" in block,
            f"Параскева missing from Ioann's union: {block}",
        )

    def test_wife_with_ref_to_head_is_paired_with_head(self):
        """Sanity: when WIFE's ref_member IS the head, she pairs with
        him as before (the explicit-positive case)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40),
                      member(2, person("Марья"), CensusRole.WIFE, ref_member=1, age=35)),
        )
        out = _run_generator(records)
        # Translation: "Марья" → "marija" (canonicalized to "Мария",
        # transliterated to "marija"). Match the union resource and
        # check both partners are present.
        m = re.search(
            r'resource "geni_union" "ioann_petrov[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(m, "head+wife union not emitted")
        block = m.group(1).lower()
        self.assertIn("ioann_petrov", block)
        self.assertIn("marija", block)

    def test_wife_with_no_ref_member_is_paired_with_head(self):
        """Sanity: when WIFE has no ref_member at all, she defaults to
        the head as before."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1816,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40),
                      member(2, person("Марья"), CensusRole.WIFE, age=35)),
        )
        out = _run_generator(records)
        m = re.search(
            r'resource "geni_union" "ioann_petrov[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(m, "head+wife union not emitted")
        block = m.group(1).lower()
        self.assertIn("ioann_petrov", block)
        self.assertIn("marija", block)


class TestCensusMultiWifeHeadTieBreak(unittest.TestCase):
    """When the head has multiple WIFE members (1st died before this
    revision, 2nd taken as widow), only one head+wife union is emitted.
    Selection order: (1) WIFE whose profile is in `profile_move_list`
    — i.e. consolidates to a known cross-record person, so legacy's
    fold-in to the consolidated bucket is preserved; (2) alive wife
    over departed/dead one when consolidation status ties.

    Regression source: households with two wives, the first dead and
    the second alive, lost the alive wife to first-encounter-wins logic,
    routing the consolidated union under the dead spouse's per-record
    stub.
    """

    def test_alive_wife_preferred_when_neither_consolidated(self):
        """Both wives are per-record only (no profile_move_list entry)
        — pick the alive one."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=62),
                      member(2, person("Марфа"), CensusRole.WIFE, age=50, departure_year=1788, departure_reason="умер"),
                      member(3, person("Авдотья"), CensusRole.WIFE, age=45)),
        )
        out = _run_generator(records)
        m = re.search(
            r'resource "geni_union" "ioann_petrov[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(m, "head+wife union not emitted")
        block = m.group(1).lower()
        # Avdotya (member 3, alive) — modern form 'evdokija'.
        self.assertIn("evdokija", block,
                      f"alive wife not picked: {block}")
        # Marfa (member 2, dead) must not be the partner.
        partners_match = re.search(
            r'partners\s*=\s*\[(.*?)\]', m.group(1), re.DOTALL,
        )
        self.assertIsNotNone(partners_match)
        partners = partners_match.group(1).lower()
        self.assertNotIn("marfa", partners,
                         f"dead wife wrongly chosen as partner: {partners}")

    def test_consolidated_wife_preferred_over_alive_unconsolidated(self):
        """The dead wife has a profile_move_list entry (e.g. her record
        is shared across multiple revisions / MK records); the alive
        wife does not. Legacy folded the dead wife's union into her
        consolidated bucket — preserve that by preferring the
        consolidated wife even when she's dead.

        Pattern: a household with two wives, the first dead but her
        profile consolidated across several records, the second alive
        with no consolidation.
        """
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Никифор", "Иванов"), CensusRole.HEAD, age=60),
                      member(2, person("Марфа", "Петрова"), CensusRole.WIFE, age=50, departure_year=1787,
                             departure_reason="умер"),
                      member(3, person("Анфиса", "Васильева"), CensusRole.WIFE, age=47)),
        )
        consolidation = Consolidation(
            profile_move_list={
                "_1795_00_00_marfa_petrovna_rs_1_2_family_member":
                    "marfa_petrovna",
            },
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        gen.add_census_records(records)
        gen.finalize()
        # Union routes into consolidated bucket because Marfa is in
        # profile_move_list. Inspect that output.
        cu = gen.get_output("consolidated_unions.tf")
        m = re.search(
            r'resource "geni_union" "[^"]*" \{(.*?)\n\}', cu, re.DOTALL,
        )
        self.assertIsNotNone(m, "consolidated head+wife union not emitted")
        partners_match = re.search(
            r'partners\s*=\s*\[(.*?)\]', m.group(1), re.DOTALL,
        )
        self.assertIsNotNone(partners_match)
        partners = partners_match.group(1).lower()
        # Marfa (dead, consolidated) preferred — moves to canonical name.
        self.assertIn("marfa_petrovna", partners,
                      f"consolidated dead wife not preferred: {partners}")
        self.assertNotIn("anfisa", partners,
                         f"alive but unconsolidated wife wrongly picked: {partners}")


class TestCensusHiddenParentSpouseInference(unittest.TestCase):
    """When a hidden ancestor declares `ref_member=<visible_member>`,
    that visible member becomes the second partner of the
    hidden-parent → child union. Use case: a stepdaughter whose
    biological father is hidden and biological mother is the head's
    current wife — the legacy generator emitted a one-partner union
    capturing only the bio-mother; the new generator can now emit a
    proper two-partner Герасим+Аксинья union."""

    def _stepdaughter_records(self, *, branch="wife"):
        """Build the canonical regression household. `branch` selects which path through
        `add_census_records` we exercise:
            "wife" — head has a paired wife (Pass (b) in the WIFE branch)
            "no_wife" — head is deceased, no wife pairing (no-WIFE Pass (b))
        """
        head_kwargs = {}
        if branch == "no_wife":
            head_kwargs = dict(
                previous_age=65,
                departure_reason="умер",
                departure_year=1827,
            )
        return census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Степан", "Ефимов"), CensusRole.HEAD, age=65, **head_kwargs),
                      member(2, person("Егор", "Степанов"), CensusRole.SON, ref_member=1, age=49),
                      member(3, person("Аксинья"), CensusRole.WIFE, ref_member=2, age=42),
                      member(4, person("Анисья", "Герасимова"), CensusRole.STEPDAUGHTER, ref_member=2, age=8,
                             parent_member=5,
                             comment="ФИО в документе: Анисья Герасимова"),
                      member(5, person("Герасим"), None, ref_member=3, age="?", hidden=True,
                             comment="первый муж Аксиньи; реконструировано")),
        )

    def _find_gerasim_union(self, out):
        return re.search(
            r'resource "geni_union" "gerasim[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )

    def test_two_partner_bio_parent_union_in_wife_branch(self):
        """When the head has a paired wife (Степан→Аксинья via the
        chain of refs), the WIFE-branch Pass (b) fires. The hidden
        Герасим's `ref_member=3` (Аксинья) makes Аксинья the second
        partner, and Анисья becomes their child."""
        out = _run_generator(self._stepdaughter_records(branch="wife"))
        union = self._find_gerasim_union(out)
        self.assertIsNotNone(union, "Герасим's bio-parent union not emitted")
        block = union.group(1)
        partners = re.search(
            r'partners\s*=\s*\[(.*?)\]', block, re.DOTALL,
        ).group(1).lower()
        children = re.search(
            r'children\s*=\s*\[(.*?)\]', block, re.DOTALL,
        ).group(1).lower()
        # Both bio-parents present as partners.
        self.assertIn("gerasim", partners)
        self.assertIn("ksenija", partners)
        # Their daughter is the union's only child.
        self.assertIn("anisija_gerasimovna", children)

    def test_two_partner_bio_parent_union_in_no_wife_branch(self):
        """When the head is deceased and has no paired wife (the
        no-WIFE branch), Pass (b) for hidden parents must ALSO honor
        the `ref_member`-as-spouse inference. Without this, the
        no-WIFE branch silently emits a one-partner Герасим-only
        union."""
        out = _run_generator(self._stepdaughter_records(branch="no_wife"))
        union = self._find_gerasim_union(out)
        self.assertIsNotNone(union, "Герасим's bio-parent union not emitted")
        block = union.group(1)
        partners = re.search(
            r'partners\s*=\s*\[(.*?)\]', block, re.DOTALL,
        ).group(1).lower()
        self.assertIn("gerasim", partners)
        self.assertIn("ksenija", partners)

    def test_stepchild_absent_from_stepparent_subfamily_union(self):
        """A step-child must NOT appear in the step-parent's sub-family
        union — only in the biological parents' union. Анисья is
        Аксинья's daughter by Герасим (her first husband); she is Егор's
        step-daughter (`ref_member=2`). Егор + Аксинья's sub-family
        union must not list her as a child."""
        out = _run_generator(self._stepdaughter_records(branch="wife"))
        # Егор's sub-family union (он SON of head Степан, paired with
        # his wife Аксинья).
        georgij_union = re.search(
            r'resource "geni_union" "georgij_stepanovich[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(
            georgij_union, f"Егор sub-family union not emitted:\n{out}")
        block = georgij_union.group(1)
        # Анисья is the step-daughter — she belongs to Герасим+Аксинья,
        # never to Егор's union.
        self.assertNotIn("anisija_gerasimovna", block.lower())
        # Sanity: she IS still linked via the biological-parent union.
        gerasim_union = self._find_gerasim_union(out)
        self.assertIsNotNone(gerasim_union)
        self.assertIn(
            "anisija_gerasimovna",
            re.search(r'children\s*=\s*\[(.*?)\]',
                      gerasim_union.group(1), re.DOTALL).group(1).lower(),
        )

    def test_brother_with_parent_member_not_claimed_by_heads_parent(self):
        """A BROTHER of the head whose `parent_member` points at a hidden
        ancestor must land ONLY in that ancestor's union — not also be
        swept into the head's-FATHER union by the siblings-share-head's-
        parent heuristic. Case: two BROTHERs of the head are
        sons of a hidden ancestor, not of the head's father."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1719,
            household(None, member(1, person("Кузьма", "Прохоров"), CensusRole.HEAD, age=32),
                      member(2, person("Прохор", "Мартынов"), CensusRole.FATHER, age=72),
                      member(3, person("Тозяй", "Гордеев"), CensusRole.BROTHER, age=42, parent_member=5),
                      member(4, person("Пётр", "Прохоров"), CensusRole.BROTHER, age=27),
                      member(5, person("Гордей"), None, age="?", hidden=True)),
        )
        out = _run_generator(records)
        # Прохор's union: Пётр is his son; Тозяй is NOT.
        shumila = re.search(
            r'resource "geni_union" "prohor[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(shumila, f"Прохор union missing:\n{out}")
        sh_block = shumila.group(1).lower()
        self.assertIn("petr", sh_block)
        # Тозяй canonicalizes to "tazej" — must NOT be Прохор's child.
        self.assertNotIn("tazej", sh_block)
        # Гордей's union: Тозяй IS his son.
        flor = re.search(
            r'resource "geni_union" "gordij[^"]*" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(flor, f"Гордей union missing:\n{out}")
        self.assertIn("tazej", flor.group(1).lower())

    def test_hidden_parent_without_ref_member_emits_one_partner_union(
        self,
    ):
        """Sanity: when the hidden parent has NO `ref_member`, the
        union is still emitted but with only one partner (the
        original Pass (b) behavior — no spouse inference)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Степан", "Ефимов"), CensusRole.HEAD, age=65),
                      member(2, person("Егор", "Степанов"), CensusRole.SON, ref_member=1, age=49),
                      member(3, person("Аксинья"), CensusRole.WIFE, ref_member=2, age=42),
                      member(4, person("Анисья", "Герасимова"), CensusRole.STEPDAUGHTER, ref_member=2, age=8,
                             parent_member=5), member(5, person("Герасим"), None, age="?", hidden=True)),
        )
        out = _run_generator(records)
        union = self._find_gerasim_union(out)
        self.assertIsNotNone(union, "Герасим's parent union not emitted")
        partners = re.search(
            r'partners\s*=\s*\[(.*?)\]',
            union.group(1), re.DOTALL,
        ).group(1).lower()
        # Only Герасим; no Аксинья paired in.
        self.assertIn("gerasim", partners)
        self.assertNotIn("ksenija", partners)

    def test_visible_parent_ref_member_not_treated_as_spouse(self):
        """Regression: a VISIBLE parent with
        `ref_member=N` pointing at their own father (NOT a spouse)
        must produce a one-partner union, not a parent+grandparent
        couple. The `ref_member`-as-spouse inference is restricted
        to *hidden* parents — for visible rows, `ref_member` encodes
        the upward link (e.g. SON's `ref_member` is their father)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1850,
            household(None, member(1, person("Савелий", "Тихонов"), CensusRole.HEAD, age=65, previous_age=65,
                                   departure_year=1841,
                                   departure_reason="умер"),
                      member(2, person("Калина", "Савельев"), CensusRole.SON, age=44, previous_age=27),
                      member(3, person("Тихон", "Калинов"), CensusRole.SON, ref_member=2, age="0.5",
                             departure_year=1837,
                             departure_reason="умер"),
                      member(4, person("Анастасия", "Тихонова"), CensusRole.DAUGHTER, ref_member=3, age=8)),
        )
        out = _run_generator(records)
        tihon_union = re.search(
            r'resource\s+"geni_union"\s+"tihon_kalinovich[^"]*"\s*\{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(
            tihon_union, "Lone-parent union for Тихон not emitted",
        )
        partners = re.search(
            r'partners\s*=\s*\[(.*?)\]',
            tihon_union.group(1), re.DOTALL,
        ).group(1).lower()
        children = re.search(
            r'children\s*=\s*\[(.*?)\]',
            tihon_union.group(1), re.DOTALL,
        ).group(1).lower()
        self.assertIn("tihon_kalinovich", partners)
        # Калина must NOT be paired in as a spouse — he's Rodion's
        # father (m3.ref_member=2 encodes lineage, not marriage).
        self.assertNotIn("kallinik_savelevich", partners)
        # Anastasia is the daughter.
        self.assertIn("anastasija_tihonovna", children)

    def test_hidden_parent_with_hidden_spouse_skips_inference(self):
        """The spouse inference requires a *visible* ref_member. If
        the referenced member is itself hidden, fall back to a
        one-partner union (avoid pairing two hidden ancestors as a
        synthetic couple)."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Степан", "Ефимов"), CensusRole.HEAD, age=65),
                      member(2, person("Анисья", "Герасимова"), CensusRole.DAUGHTER, ref_member=1, age=8,
                             parent_member=4), member(3, person("Аксинья"), None, age="?", hidden=True),
                      member(4, person("Герасим"), None, ref_member=3, age="?", hidden=True)),
        )
        out = _run_generator(records)
        union = self._find_gerasim_union(out)
        if union is None:
            return  # No union emitted at all — also acceptable.
        partners = re.search(
            r'partners\s*=\s*\[(.*?)\]',
            union.group(1), re.DOTALL,
        ).group(1).lower()
        # Hidden Аксинья must NOT be paired in.
        self.assertNotIn("ksenija", partners)


class TestCensusAscendingRoleUnion(unittest.TestCase):
    """A visible MOTHER/FATHER member of the head implies a deceased
    spouse and a marriage that produced the head. Legacy emitted a
    single-partner union named `<first>_<patr>_rs<rn>_<year>` with the
    parent as partner_1 and the head + any BROTHER/SISTER members as
    children. `union_move_list_v2` then merges this into the consolidated
    parent-pair union (e.g. `<mother>_rs303_1834` →
    `nikolaj_and_tatiana_sergeevna`). Without this emission the v2
    redirect has nothing to merge and the parent's profile reference is
    dropped from the consolidated union.

    Shape: a household with a mother as member 2 and a record number of
    its own.
    """

    def test_mother_role_emits_single_partner_union_with_head_as_child(self):
        records = census_records(
            "ГА Глуповской области", "23", "3", "9924", "Горюхино", 1834,
            household("28", member(1, person("Савватей", "Антипов",
                                             status="ясачный крестьянин"), CensusRole.HEAD, age=32, previous_age=14,
                                   record_number=302), member(2, person("Прасковья", "Карпова",
                                                                        status="ясачная крестьянка"), CensusRole.MOTHER,
                                                              age=50, record_number=303), member(3, person("Ирина",
                                                                                                           status="ясачная крестьянка"),
                                                                                                 CensusRole.WIFE,
                                                                                                 age=26,
                                                                                                 record_number=304),
                      member(4, person("Мария", "Савватеева",
                                       status="ясачная крестьянка"), CensusRole.DAUGHTER, age="5 мес",
                             record_number=305,
                             birth_year=1833)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1834_1.tf")
        # Single-partner union for Прасковья must be emitted. Name uses
        # canonical patronymic (Карповна), legacy spelled differently;
        # `_RES_NAME_SPELLING_ALIASES` reconciles them for v2 lookup.
        m = re.search(
            r'resource "geni_union" "paraskeva_karpovna_rs303_1834" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(
            m, "MOTHER-role union paraskeva_karpovna_rs303_1834 not emitted",
        )
        body = m.group(1)
        # partners list must contain Прасковья's profile (and only that).
        partners = re.search(
            r'partners\s*=\s*\[(.*?)\]', body, re.DOTALL,
        ).group(1)
        self.assertIn(
            "_1834_00_00_paraskeva_karpovna_rs_28_2_family_member",
            partners,
        )
        # children list must contain Савватей (head).
        children = re.search(
            r'children\s*=\s*\[(.*?)\]', body, re.DOTALL,
        ).group(1)
        self.assertIn(
            "_1834_00_00_savvatij_antipovich_rs_28_1_family_member",
            children,
        )

    def test_mother_role_includes_brother_siblings_as_children(self):
        """When the household has BROTHER/SISTER members alongside the
        HEAD, the MOTHER's union includes them all as children (they
        share a parent).
        """
        records = census_records(
            "ГА", "23", "3", "9924", "Горюхино", 1834,
            household("5", member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30, record_number=100),
                      member(2, person("Анна", "Сидорова"), CensusRole.MOTHER, age=55, record_number=101),
                      member(3, person("Семен", "Петров"), CensusRole.BROTHER, age=28, record_number=102)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1834_1.tf")
        m = re.search(
            r'resource "geni_union" "anna_sidorovna_rs101_1834" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(m, "MOTHER union not emitted")
        children = re.search(
            r'children\s*=\s*\[(.*?)\]', m.group(1), re.DOTALL,
        ).group(1)
        # Both head (Иван) and brother (Семен) are Анна's children.
        self.assertIn("ioann_petrovich_rs_5_1_family_member", children)
        self.assertIn("simeon_petrovich_rs_5_3_family_member", children)

    def test_mother_role_skipped_when_hidden_ancestor_covers_relationship(self):
        """Regression: a household (a HEAD with parent_member=3, a MOTHER
        m2, a hidden ancestor m3 with ref_member=2) emitted TWO unions
        both attributing the head as the mother's child:

            <mother>_rs24_<year>        (mother → head)
            <father>__rs1a-3_<year>     (father + mother → head)

        The second is the canonical hidden-ancestor union (full parental
        pair). The first is redundant — the mother-only ascending pass
        fired without checking that the same parent-child link is already
        captured. This causes the head to appear as the mother's child
        twice in Geni.

        Expected: when HEAD's `parent_member` points at a hidden member
        whose `ref_member` resolves to this MOTHER, the ascending-parent
        pass must skip emitting the mother-only union.
        """
        records = census_records(
            "ГА Глуповской области", "30", "8", "1227", "Горюхино", 1834,
            household("1а",
                      member(1, person("Василий", "Петров"), CensusRole.HEAD, age=11, record_number=23, birth_year=1823,
                             parent_member=3),
                      member(2, person("Мавра", "Фомина"), CensusRole.MOTHER, age=33, record_number=24,
                             birth_year=1801),
                      member(3, person("Петр"), None, ref_member=2, age="?", birth_year=1825, hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1834_1.tf")

        # No mother-only ascending union: the hidden-ancestor pass
        # already emitted Петр + Матрена → Василий, so a redundant
        # Матрена-only union would attribute Василий as Матрена's child
        # twice.
        self.assertNotIn(
            'resource "geni_union" "mavra_fominichna_rs24_1834"', out,
            "redundant mother-only ascending union emitted alongside "
            "the hidden-ancestor union",
        )
        # Sanity: exactly one geni_union references Василий as a child.
        union_blocks = re.findall(
            r'resource "geni_union" "[^"]+" \{(.*?)\n\}', out, re.DOTALL,
        )
        head_child_unions = [
            b for b in union_blocks
            if "vasilij_petrovich_rs_1a_1_family_member.id" in b
            and "children" in b
            # only count when Василий sits in the children list
            and re.search(
                r'children\s*=\s*\[[^\]]*vasilij_petrovich_rs_1a_1_family_member\.id',
                b, re.DOTALL,
            )
        ]
        self.assertEqual(
            len(head_child_unions), 1,
            f"expected 1 union with Василий as child, got "
            f"{len(head_child_unions)}",
        )

    @staticmethod
    def _unions(out):
        """`{res_name: (partners, children)}` of every geni_union, each
        list as the text between its brackets."""
        unions = {}
        for name, body in re.findall(
            r'resource "geni_union" "([^"]+)" \{(.*?)\n\}', out, re.DOTALL,
        ):
            partners = re.search(r'partners\s*=\s*\[(.*?)\]', body, re.DOTALL)
            children = re.search(r'children\s*=\s*\[(.*?)\]', body, re.DOTALL)
            unions[name] = (
                partners.group(1) if partners else "",
                children.group(1) if children else "",
            )
        return unions

    def test_mother_of_non_head_does_not_claim_heads_brother(self):
        """A MOTHER whose `ref_member` names someone other than the head
        is THAT member's mother, so the head's brothers are not her
        children. A «nephew's mother» (ref_member = the nephew) became
        the mother of the head's brother. He stays a child of the head's
        implied parent (the head-of-family stub), and of no union of
        hers."""
        records = census_records(
            "ГАВО", "162", "8", "100", "Горюхино", 1858,
            household("47",
                      member(1, person("Антон", "Власов"), CensusRole.HEAD, age=56),
                      member(2, person("Игнат", "Власов"), CensusRole.BROTHER, ref_member=1, age=61),
                      member(3, person("Павел", "Артемов"), CensusRole.NEPHEW, ref_member=1, age=23),
                      member(4, person("Марья", "Тимофеева"), CensusRole.MOTHER, ref_member=3, age=57)),
        )
        unions = self._unions(_run_generator(records))
        claimed = [
            name for name, (partners, children) in unions.items()
            if "marija_timofeevna" in partners and "ignatij_vlasovich" in children
        ]
        self.assertEqual(claimed, [], f"The brother made the nephew's mother's child: {unions}")
        self.assertIn("head_of_family_47_1858", unions, "head-of-family stub union missing")
        self.assertIn("ignatij_vlasovich", unions["head_of_family_47_1858"][1])

    def test_mother_of_non_head_does_not_claim_her_hidden_husband(self):
        """A MOTHER member is the mother of the nephew
        (ref_member=2) and the widow of the head's hidden brother. The
        sibling heuristic made her the mother of her own husband."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1850,
            household("9",
                      member(1, person("Фока", "Лазарев"), CensusRole.HEAD, age=64),
                      member(2, person("Сидор", "Ипатов"), CensusRole.NEPHEW, age=39, parent_member=9),
                      member(8, person("Мавра", "Макарова"), CensusRole.MOTHER, ref_member=2, age=66),
                      member(9, person("Ипат", "Лазарев"), CensusRole.BROTHER, ref_member=8, age="?",
                             hidden=True)),
        )
        unions = self._unions(_run_generator(records))
        claimed = [
            name for name, (partners, children) in unions.items()
            if "mavra_makarovna" in partners and "ipatij_lazarevich" in children
        ]
        self.assertEqual(claimed, [], f"The hidden brother made his widow's child: {unions}")


class TestCensusHiddenHeadSkipped(unittest.TestCase):
    """Hidden HEADs are implicit ancestors (e.g. a great-grandfather added
    manually to chain the genealogy). They must NOT be picked as the
    `head_member` for the head+wife union, otherwise the visible head's
    wife gets paired with the wrong ancestor (a phantom union) and the
    visible head ends up as a CHILD of his own great-grandfather's union.

    Concrete regression: a household has a hidden HEAD, a hidden SON of
    his, then a visible HEAD with a WIFE. Without the fix:
    - head_member picked the hidden HEAD (first HEAD seen)
    - wife_member picked the wife (no ref_member, defaulted to that head)
    - Generated union `hidden head + wife → [visible head's children + hidden son]`
    - After consolidation, the hidden head mapped to the hidden son's
      profile, leaving the son's union with himself as a child.
    """

    def test_visible_head_picked_over_hidden_head(self):
        records = census_records(
            "ГА", "32", "6", "2338", "Горюхино", 1850,
            household("69", member(0, person("Ермил"), CensusRole.HEAD, age="?", hidden=True),
                      member(0, person("Тихон", "Ермилов"), CensusRole.SON, age="?", hidden=True),
                      member(1, person("Перфил", "Тихонов",
                                       status="ясачный крестьянин"), CensusRole.HEAD, age=44, record_number=738),
                      member(2, person("Митрофан", "Перфилов",
                                       status="ясачный крестьянин"), CensusRole.SON, age=24, record_number=739),
                      member(4, person("Фекла", "Фомина",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=40, record_number=741)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1850_1.tf")
        # The visible head+wife union must be Perfil+Fekla, not
        # Emeljan+Fekla.
        self.assertIn(
            'resource "geni_union" "perfil_tihonovich_rs738_1850"', out,
        )
        # No phantom union pairing the hidden Ермил with Fekla.
        self.assertNotIn("ermil_and_fekla", out)
        # No `ermil_*_and_*` union at all (Ермил stays in the hidden-
        # ancestor sub-family path, not as a head+wife partner).
        self.assertNotRegex(out, r'geni_union" "ermil[^"]*and[^"]*"')

    def test_hidden_son_not_added_as_head_wife_child(self):
        """A hidden SON-role member must not appear as a child of the
        visible head+wife union — they're an implicit ancestor placed
        for tree-chaining, not a real child.
        """
        records = census_records(
            "ГА", "32", "6", "2338", "Горюхино", 1850,
            household("69", member(0, person("Ермил"), CensusRole.HEAD, age="?", hidden=True),
                      member(0, person("Тихон", "Ермилов"), CensusRole.SON, age="?", hidden=True),
                      member(1, person("Перфил", "Тихонов",
                                       status="ясачный крестьянин"), CensusRole.HEAD, age=44, record_number=738),
                      member(4, person("Фекла", "Фомина",
                                       status="ясачная крестьянка"), CensusRole.WIFE, age=40, record_number=741)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1850_1.tf")
        block = re.search(
            r'resource "geni_union" "perfil_tihonovich_rs738_1850" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(block)
        children_match = re.search(
            r'children\s*=\s*\[(.*?)\]', block.group(1), re.DOTALL,
        )
        # The hidden Тихон must NOT be in the visible head's children.
        children = children_match.group(1) if children_match else ""
        self.assertNotIn("tihon_ermilovich", children)


class TestHiddenChildRefMemberNotSpouse(unittest.TestCase):
    """Hidden ancestors with CHILD role (SON/DAUGHTER/STEPSON/STEPDAUGHTER)
    use `ref_member` to encode their PARENT, not a spouse. The
    spouse-from-ref_member inference (intended for hidden spouses
    encoded via ref_member when no real WIFE row exists) must NOT
    fire on child-role hidden parents.

    Concrete regression: a hidden m12 SON with ref_member=2 (a visible
    member) — without the role check, that member was paired as the
    hidden son's spouse, dragging the hidden son's daughter into the
    member's union.
    """

    def test_hidden_son_ref_member_not_treated_as_spouse(self):
        records = census_records(
            "ГА", "23", "3", "9924", "Горюхино", 1834,
            household("76", member(1, person("Лаврентий", "Тимонов"), CensusRole.HEAD, age=70, previous_age=70,
                                   departure_year=1819, departure_reason="умер", record_number=1),
                      member(2, person("Степан", "Лаврентьев"), CensusRole.SON, ref_member=1, age=54, previous_age=54,
                             departure_year=1823, departure_reason="умер", record_number=2),
                      member(12, person("Прохор", "Степанов"), CensusRole.SON, ref_member=2, age="?", hidden=True),
                      member(3, person("Ксения", "Прохорова"), CensusRole.GRANDDAUGHTER, ref_member=2, age=23,
                             record_number=3, parent_member=12)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1834_1.tf")
        # The hidden Прохор sub-family union must have NO partner_2
        # (Степан is parent, not spouse).
        block = re.search(
            r'resource "geni_union" "prohor_stepanovich_rs76-12_1834" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(block, "Прохор sub-family union missing")
        partners = re.search(
            r'partners\s*=\s*\[(.*?)\]', block.group(1), re.DOTALL,
        ).group(1)
        # Only Прохор as partner_1; no Степан as spurious spouse.
        self.assertNotIn("stefan_lavrentevich", partners)
        self.assertNotIn("_1834_00_00_stefan_lavrentevich", partners)


class TestConsolidatedUnionSpouseConflictGuard(unittest.TestCase):
    """When a partner-lookup-fallback candidate has a partner_2 that
    differs from the incoming union's partner_2 (and partner_1 matches),
    create a NEW bucket instead of folding into the candidate. Otherwise
    children-by-wife splits collapse incorrectly.

    Concrete regression: a man with two wives — the first from a
    marriage record, the second from a later roll. The roll's sub-family
    union (the man + the second wife with two daughters) was folding
    into the first wife's bucket via partner-lookup, putting the second
    wife's daughters into the first wife's children list.
    """

    def test_different_partner_2_creates_new_bucket(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        # Step 1: 1827 marriage with first wife.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="kosma_and_natalija_m1_1827",
            origin=UnionOrigin.MARRIAGE,
            partner_1="kosma_ivanovich_karkadilov",
            partner_2="natalija_fedorovna_karkadilova",
            children={"child_of_natalija"},
        ))
        # Step 2: 1850 sub-family with second wife (different partner_2).
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="kosma_ivanovich_rs393_1850",
            origin=UnionOrigin.ROLL,
            partner_1="kosma_ivanovich_karkadilov",
            partner_2="evfimija_efimovna",
            children={"daughter_evfimija"},
        ))
        # Both buckets must exist — Эфимия's children NOT in Натальа's bucket.
        self.assertIn("kosma_ivanovich_karkadilov_and_natalija_fedorovna_karkadilova",
                      gen._consolidated_unions)
        self.assertIn("kosma_ivanovich_karkadilov_and_evfimija_efimovna",
                      gen._consolidated_unions)
        natalija = gen._consolidated_unions["kosma_ivanovich_karkadilov_and_natalija_fedorovna_karkadilova"]
        evfimija = gen._consolidated_unions["kosma_ivanovich_karkadilov_and_evfimija_efimovna"]
        self.assertIn("child_of_natalija", natalija.children or set())
        self.assertNotIn("daughter_evfimija", natalija.children or set())
        self.assertIn("daughter_evfimija", evfimija.children or set())

    def test_same_partner_2_still_folds(self):
        """When partner_2 matches, the partner-lookup fallback still
        merges normally — no over-correction.
        """
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="alpha_and_beta_m1_1830",
            origin=UnionOrigin.MARRIAGE,
            partner_1="alpha",
            partner_2="beta",
            children={"child_1"},
        ))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="alpha_rs1_1834",
            origin=UnionOrigin.ROLL,
            partner_1="alpha",
            partner_2="beta",
            children={"child_2"},
        ))
        # Both sources merge into one bucket.
        self.assertEqual(len(gen._consolidated_unions), 1)
        union = gen._consolidated_unions["alpha_and_beta"]
        self.assertEqual(union.children, {"child_1", "child_2"})

    def test_none_partner_2_does_not_split(self):
        """When the incoming has partner_2=None (single-partner
        placeholder), the partner-lookup still folds into the
        candidate (placeholder fold). Avoids splitting unrelated
        single-parent sources from spouse-pair sources.
        """
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="alpha_and_beta_m1_1830",
            origin=UnionOrigin.MARRIAGE,
            partner_1="alpha",
            partner_2="beta",
            children={"child_1"},
        ))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="alpha__18_1832",
            partner_1="alpha",
            partner_2=None,
            children={"child_2"},
        ))
        self.assertEqual(len(gen._consolidated_unions), 1)


class TestPartnerLookupPreferConsolidatedTarget(unittest.TestCase):
    """Partner-lookup registration uses `setdefault` (first-wins) for
    non-v2 targets to preserve v2-redirect priority. But when the
    first-registered target's OTHER partner is a per-record stub (e.g.
    `_1815_01_26_evdokija_fedorovna_mk_marriages_4_bride`) and a later
    target's other partner is a CONSOLIDATED profile (e.g.
    `paraskeva_alekseevna_taratajkina`), the consolidated target is more
    canonical — partner-only sources arriving later should route there.

    Concrete regression: a man with two marriages — the first to a wife
    kept as a per-record stub, the second to a consolidated wife. Later
    births carry no mother attribution; legacy routed both to the
    second marriage via partner-lookup. New code's first-wins setdefault
    pinned the father to the first marriage's stub target, diverting
    both children to the wrong bucket.
    """

    def _route(self, stub_wife: str, canonical_wife: str) -> dict[str, GeniUnion]:
        """Two marriages of one father — to a wife no fold touched (a profile
        minted for her record alone) and to a canonical the config folds
        records into — then a birth naming the father alone."""
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None, consolidation=Consolidation(
            profile_move_list={"_1822_05_02_wife_mk_births_5_mother": canonical_wife}))
        gen._minted_res_names.add(stub_wife)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father_and_wife_stub_m1_1815",
            origin=UnionOrigin.MARRIAGE,
            partner_1="father",
            partner_2=stub_wife,
        ))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father_and_wife_canonical_m2_1820",
            origin=UnionOrigin.MARRIAGE,
            partner_1="father",
            partner_2=canonical_wife,
        ))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father__5_1822",
            origin=UnionOrigin.BIRTH,
            partner_1="father",
            partner_2=None,
            children={"child"},
        ))
        gen.finalize()
        return gen._consolidated_unions

    def test_consolidated_target_overrides_stub_target_for_partner(self):
        unions = self._route("_1815_01_28_wife_stub_mk_marriages_1_bride", "wife_canonical")
        canonical = unions.get("father_and_wife_canonical")
        self.assertIsNotNone(canonical)
        self.assertIn("child", canonical.children or set(),
                      "partner-only source should fold into consolidated bucket")
        self.assertNotIn(
            "child", unions["father_and__1815_01_28_wife_stub_mk_marriages_1_bride"].children)

    def test_a_canonical_named_after_its_first_record_is_no_stub(self):
        """Заманиловка names a canonical after its first record
        (`_1834_02_28_…_rs_532_8_family_member`). A `_YYYY_MM_DD_` prefix is
        not what makes a stub — being minted for one record and folded by
        nothing is — so reading the prefix took canonicals for stubs."""
        canonical_wife = "_1834_02_28_wife_rs_532_8_family_member"
        unions = self._route("_1815_01_28_wife_stub_mk_marriages_1_bride", canonical_wife)
        self.assertIn("child", unions[f"father_and_{canonical_wife}"].children)

    def test_a_stub_whose_record_date_lacks_a_month_is_still_a_stub(self):
        """A stub named `_1796_30_…_mk_marriages_1_bride`: the prefix
        reading missed it."""
        unions = self._route("_1796_30_wife_stub_mk_marriages_1_bride", "wife_canonical")
        self.assertIn("child", unions["father_and_wife_canonical"].children or set())
        self.assertNotIn(
            "child", unions["father_and__1796_30_wife_stub_mk_marriages_1_bride"].children)


class TestDeathRecordChildLookup(unittest.TestCase):
    """Death-record unions (legacy res_name pattern
    `<deceased>_and_<surviving_relative>_d<rec>_<year>`) carry only one
    explicit partner (the surviving relative — typically the father).
    When that relative is in MULTIPLE consolidated buckets (e.g. a man
    with two wives), the generic partner-lookup map registers only
    ONE target per partner — picking the first-encountered bucket,
    which may not be where the deceased child actually belongs.

    Fix: pre-tier child-lookup for death-record sources — when the
    deceased child is already in some consolidated union AND that
    union shares a partner with the death source, route there.

    Concrete regression: a birth record places a daughter with a
    father and his second wife. The death record emits
    `<deceased>_and_<father>_d<rec>_<year>` (only the father as
    partner). New code routed via partner-lookup on the father to his
    FIRST wife's bucket. With the fix, child-lookup finds the daughter
    already in the father+second-wife union's children and routes
    there.
    """

    def test_death_record_routes_to_union_containing_deceased(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        # First wife marital union — no children of relevance.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father_and_wife1_m1_1830",
            origin=UnionOrigin.MARRIAGE,
            partner_1="father",
            partner_2="wife1",
            children={"unrelated_child"},
        ))
        # Second wife birth union — has the deceased as a child.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father_and_wife2_5_1837",
            partner_1="father",
            partner_2="wife2",
            children={"deceased_child"},
        ))
        # Death-record union with only father as partner.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="deceased_and_father_d99_1837",
            origin=UnionOrigin.DEATH,
            partner_1="father",
            partner_2=None,
            children={"deceased_child"},
        ))
        gen.finalize()
        # Deceased must be in second wife's bucket, not first.
        wife1 = gen._consolidated_unions["father_and_wife1"]
        wife2 = gen._consolidated_unions["father_and_wife2"]
        self.assertNotIn("deceased_child", wife1.children or set(),
                         "death-record fold polluted wife1's bucket")
        self.assertIn("deceased_child", wife2.children or set())

    def test_death_record_no_existing_child_falls_back_to_partner_lookup(self):
        """Sanity: when no consolidated union contains the deceased,
        the death-record union still folds via partner-lookup as
        before (no regression of normal routing).
        """
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father_and_wife_m1_1830",
            origin=UnionOrigin.MARRIAGE,
            partner_1="father",
            partner_2="wife",
            children={"existing_child"},
        ))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="orphan_and_father_d99_1840",
            origin=UnionOrigin.DEATH,
            partner_1="father",
            partner_2=None,
            children={"orphan_child"},
        ))
        gen.finalize()
        union = gen._consolidated_unions["father_and_wife"]
        self.assertIn("orphan_child", union.children or set(),
                      "death without prior bucket should fold via partner-lookup")


class TestPartnerLookupSpouseConflictPartner1Symmetric(unittest.TestCase):
    """Symmetric to the existing partner_2 spouse-conflict guard:
    when partner-lookup finds a candidate target via the SHARED
    partner_2 (mother) but the incoming and candidate have DIFFERENT
    partner_1 (father), don't fold — split into a separate bucket.

    Concrete regression: a birth has a per-record-stub father (one
    patronymic) and a mother. A later birth has a per-record-stub father
    with a different patronymic and the same mother. Without an explicit
    `profiles_to_consolidate` entry merging the two per-record-stub
    fathers into one canonical man, they remain distinct profiles.
    Legacy emitted these as separate consolidated unions; new code's
    partner-lookup via the shared mother folded the later child into the
    earlier bucket.

    Same guard also fixes the case where a marriage source folded into a
    consolidated union via the shared wife — wrong because the marriage
    was another man's.
    """

    def test_different_partner_1_creates_new_bucket(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father1_and_shared_mother_1_1835",
            partner_1="father1",
            partner_2="shared_mother",
            children={"child_1"},
        ))
        # Different father, same mother → must NOT fold.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father2_and_shared_mother_2_1838",
            partner_1="father2",
            partner_2="shared_mother",
            children={"child_2"},
        ))
        self.assertEqual(len(gen._consolidated_unions), 2,
                         "different fathers must create separate buckets")
        b1 = gen._consolidated_unions["father1_and_shared_mother"]
        b2 = gen._consolidated_unions["father2_and_shared_mother"]
        self.assertEqual(b1.children, {"child_1"})
        self.assertEqual(b2.children, {"child_2"})

    def test_same_partner_1_still_folds(self):
        """Sanity: same father + same mother folds normally."""
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father_and_mother_1_1835",
            partner_1="father",
            partner_2="mother",
            children={"child_1"},
        ))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="father_and_mother_2_1838",
            partner_1="father",
            partner_2="mother",
            children={"child_2"},
        ))
        self.assertEqual(len(gen._consolidated_unions), 1)
        b = gen._consolidated_unions["father_and_mother"]
        self.assertEqual(b.children, {"child_1", "child_2"})


class TestIllegitimateBirthSeparateBucket(unittest.TestCase):
    """Illegitimate-birth unions emitted as `and_<mother>_<recno>_<year>`
    (no father — only mother as partner_1) must NOT fold via partner-
    lookup into the mother's marital union with a different husband.
    The MK record explicitly marks the child as незаконнорожденная;
    attaching them to the husband+mother bucket implies the husband
    is the father, contradicting the source.

    Concrete regression: a soldier's wife (the husband is away) had an
    illegitimate child. Legacy emitted a standalone single-mother
    bucket for the birth; new code with partner-lookup folded it into
    the `<husband>_and_<wife>` bucket.
    """

    def test_illegit_birth_does_not_fold_into_marital_union(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        # Marital union: husband + wife, no children yet.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="husband_and_wife_m1_1810",
            origin=UnionOrigin.MARRIAGE,
            partner_1="husband",
            partner_2="wife",
            children=None,
        ))
        # Illegitimate-birth union: just mother + child, name has
        # `and_<mother>_<recno>_<year>` shape.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="and_wife_5_1815",
            origin=UnionOrigin.BIRTH,
            partner_1=None,
            partner_2="wife",
            children={"illegit_child"},
        ))
        # Two separate buckets must exist:
        marital = gen._consolidated_unions["husband_and_wife"]
        self.assertNotIn("illegit_child", marital.children or set(),
                         "illegitimate child must NOT be folded into marital union")
        self.assertIn("wife", gen._consolidated_unions,
                      "standalone single-mother bucket must exist")
        standalone = gen._consolidated_unions["wife"]
        self.assertIn("illegit_child", standalone.children or set())

    def test_legitimate_birth_still_folds(self):
        """Sanity: a normal `<father>_and_<mother>_<recno>_<year>` source
        (legitimate birth — has father) still folds via partner-lookup
        as before. The guard targets only the `^and_` prefix.
        """
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="husband_and_wife_m1_1810",
            origin=UnionOrigin.MARRIAGE,
            partner_1="husband",
            partner_2="wife",
            children=None,
        ))
        # Normal birth — father+mother source. Folds in.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="husband_and_wife_5_1815",
            partner_1="husband",
            partner_2="wife",
            children={"legit_child"},
        ))
        marital = gen._consolidated_unions["husband_and_wife"]
        self.assertIn("legit_child", marital.children or set())


class TestUndocumentedPartnerHusbandPosition(unittest.TestCase):
    """When `unions_to_consolidate[target]['undocumented_partner']`
    matches the husband-implied prefix of `<husband>_and_<wife>` target
    names, the undocumented partner must land in `partner_1` (rendered
    first), even when an earlier source already populated partner_1
    with the wife. Legacy convention is `partners = [husband, wife]`.

    Concrete regression: a `<husband>_and_<wife>` union absorbs a
    single-partner roll source of the wife (partner_1=<wife stub>),
    then `undocumented_partner=<husband>` was appended as partner_2.
    Result: partners=[wife_stub, husband]. Legacy had
    [husband, wife_stub].
    """

    def test_husband_implied_undocumented_promoted_to_partner_1(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(
            village_dir=None,
            consolidation=Consolidation(
                union_move_list_v2={
                    "wife_stub_rs1_1795": "husband_canonical_and_wife_canonical",
                },
                unions_to_consolidate={
                    "husband_canonical_and_wife_canonical": {
                        "undocumented_partner": "husband_canonical",
                    },
                },
            ),
        )
        # Single-partner source seeds partner_1 with wife.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="wife_stub_rs1_1795",
            origin=UnionOrigin.ROLL,
            partner_1="wife_stub_per_record",
            partner_2=None,
            children={"child_1"},
        ))
        gen.finalize()
        union = gen._consolidated_unions["husband_canonical_and_wife_canonical"]
        self.assertEqual(union.partner_1, "husband_canonical",
                         "husband (matching target prefix) should be partner_1")
        self.assertEqual(union.partner_2, "wife_stub_per_record",
                         "wife stub should be demoted to partner_2")

    def test_husband_implied_with_multi_token_husband(self):
        """Target like `ioann_petrovich_and_maria_ivanovna` has
        a multi-token husband. `_and_` rsplit must extract the full
        husband prefix, not just the first token.
        """
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(
            village_dir=None,
            consolidation=Consolidation(
                union_move_list_v2={
                    "wife_rs1_1795": "ioann_petrovich_and_maria_ivanovna",
                },
                unions_to_consolidate={
                    "ioann_petrovich_and_maria_ivanovna": {
                        "undocumented_partner": "ioann_petrovich",
                    },
                },
            ),
        )
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="wife_rs1_1795",
            origin=UnionOrigin.ROLL,
            partner_1="maria_ivanovna_stub",
            partner_2=None,
            children=None,
        ))
        gen.finalize()
        union = gen._consolidated_unions["ioann_petrovich_and_maria_ivanovna"]
        self.assertEqual(union.partner_1, "ioann_petrovich")
        self.assertEqual(union.partner_2, "maria_ivanovna_stub")


class TestV2RedirectTargetNamePartnerOverride(unittest.TestCase):
    """When a v2 redirect routes multiple unions with the same legacy
    res_name into a single consolidated bucket (e.g. multi-wife seeded
    by the same `<head>_rs<N>_<year>` source), the bucket's partner_2
    must match the spouse implied by the consolidated target's res_name
    (`<husband>_and_<spouse>`), not the first-encountered partner_2.

    Concrete regression: a household has a SON of HEAD with two wives
    (member 6 dead, member 7 alive). Legacy emits `<son>_rs<n>_<year>`
    once per wife. Both emissions v2-redirect to `<son>_and_<second
    wife>`. First encounter sets partner_2=<first wife's stub>; without
    the target-name override, the second (correct) emission can't
    replace it.
    """

    def test_target_name_implied_partner_overrides_per_record_stub(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(
            village_dir=None,
            consolidation=Consolidation(
                union_move_list_v2={
                    "head_rs1_1795": "head_and_canonical_wife",
                },
            ),
        )
        # First emission: per-record stub partner_2 (e.g. dead 1st wife).
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="head_rs1_1795",
            origin=UnionOrigin.ROLL,
            partner_1="head",
            partner_2="_1795_00_00_dead_wife_rs_1_2_family_member",
            children={"child_1"},
        ))
        # Second emission: consolidated wife matching target name.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="head_rs1_1795",
            origin=UnionOrigin.ROLL,
            partner_1="head",
            partner_2="canonical_wife",
            children={"child_2"},
        ))
        union = gen._consolidated_unions["head_and_canonical_wife"]
        self.assertEqual(union.partner_2, "canonical_wife",
                         "target-name implied partner_2 should win")
        # Both children folded.
        self.assertIn("child_1", union.children or set())
        self.assertIn("child_2", union.children or set())

    def test_target_name_override_skipped_when_existing_matches(self):
        """When existing.partner_2 already matches target name suffix,
        a later emission with a non-matching partner_2 must NOT override.
        """
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(
            village_dir=None,
            consolidation=Consolidation(
                union_move_list_v2={
                    "head_rs1_1795": "head_and_canonical_wife",
                },
            ),
        )
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="head_rs1_1795",
            origin=UnionOrigin.ROLL,
            partner_1="head",
            partner_2="canonical_wife",
            children={"child_1"},
        ))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="head_rs1_1795",
            origin=UnionOrigin.ROLL,
            partner_1="head",
            partner_2="_1795_00_00_other_wife_rs_1_3_family_member",
            children={"child_2"},
        ))
        union = gen._consolidated_unions["head_and_canonical_wife"]
        self.assertEqual(union.partner_2, "canonical_wife")


class TestConsolidatedUnionSelfAsChildStripped(unittest.TestCase):
    """A consolidated union must NOT contain its own partner_1 or
    partner_2 in the children set. This can happen when a MOTHER/FATHER
    ascending-role union (parent_1=parent, children=[head]) merges into
    the head's own consolidated union via partner-lookup — the head
    ends up listed as a child of his own union.

    Concrete regression: a household's mother ascending-role union
    (mother=the head's mother, child=the head) folded into
    `<head>_and_<mother>`, producing the head as both partner_1 AND a
    child of himself. That union was itself wrong — he is her husband,
    not her son — and the ascending-role pass no longer emits it
    (`TestCensusAscendingRoleUnion.test_mother_of_non_head_does_not_claim_her_hidden_husband`);
    the strip stays as a guard.
    """

    def test_partner_not_in_own_children(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        # Step 1: head+wife union with normal children.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="ipatij_and_mavra_m1_1803",
            origin=UnionOrigin.MARRIAGE,
            partner_1="ipatij_lazarevich",
            partner_2="mavra_makarovna",
            children={"daughter_evdokija"},
        ))
        # Step 2: mother's ascending-role union — mother as partner_1,
        # head as child. Routes via partner-lookup to the existing
        # head+mother target, where the head gets folded as a child of
        # himself.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="mavra_makarovna_rs56_1850",
            origin=UnionOrigin.ROLL,
            partner_1="mavra_makarovna",
            partner_2=None,
            children={"ipatij_lazarevich"},
        ))
        gen.finalize()
        # After finalize, the self-reference must be stripped.
        union = gen._consolidated_unions["ipatij_lazarevich_and_mavra_makarovna"]
        self.assertNotIn("ipatij_lazarevich", union.children or set())
        self.assertNotIn("mavra_makarovna", union.children or set())
        # Other children preserved.
        self.assertIn("daughter_evdokija", union.children or set())


class TestHiddenSonsIncludedWhenNoHiddenHeadChain(unittest.TestCase):
    """Hidden SON members are head's actual children when the household
    contains NO hidden HEAD. The hidden=True flag in this case marks
    the member as not-recorded-by-name (typically referenced via
    parent_member from GRANDSON entries) rather than as an ancestor.

    Concrete regression: a household has hidden m10 and m11 as SONs of
    the head, referenced by GRANDSON members via parent_member. They
    must land in the head's consolidated union as head's children.
    """

    def test_hidden_sons_included_when_only_visible_head(self):
        records = census_records(
            "ГА", "326", "5", "7552", "Горюхино", 1719,
            household("3", member(1, person("Игнат", "Лавров"), CensusRole.HEAD, age=87, record_number=1),
                      member(3, person("Алексей"), CensusRole.GRANDSON, age=20, record_number=3, parent_member=10),
                      member(10, person("?", "Игнатов"), CensusRole.SON, age="?", record_number=10, hidden=True),
                      member(11, person("Админ"), CensusRole.SON, age="?", record_number=11, hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1719_1.tf")
        # Find Patapij's head_only union (no WIFE in this household).
        block = re.search(
            r'resource "geni_union" "ignatij_lavrovich_rs1_1719" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(block, "ignatij_lavrovich head_only union missing")
        children = re.search(
            r'children\s*=\s*\[(.*?)\]', block.group(1), re.DOTALL,
        ).group(1)
        # Both hidden SONs must appear.
        self.assertIn("ignatovich_rs_3_10_family_member", children)
        self.assertIn("admin_rs_3_11_family_member", children)

    def test_hidden_sons_excluded_when_hidden_head_chain(self):
        """When a hidden HEAD precedes the visible head, hidden SONs
        belong to that ancestor chain — NOT to the visible head's
        children. Mirrors a household where a hidden SON of a hidden
        HEAD is the visible head's father, not his son.
        """
        records = census_records(
            "ГА", "32", "6", "2338", "Горюхино", 1850,
            household("69", member(0, person("Ермил"), CensusRole.HEAD, age="?", hidden=True),
                      member(0, person("Тихон", "Ермилов"), CensusRole.SON, age="?", hidden=True),
                      member(1, person("Перфил", "Тихонов"), CensusRole.HEAD, age=44, record_number=738),
                      member(4, person("Фекла", "Фомина"), CensusRole.WIFE, age=40, record_number=741)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1850_1.tf")
        block = re.search(
            r'resource "geni_union" "perfil_tihonovich_rs738_1850" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(block)
        children_match = re.search(
            r'children\s*=\s*\[(.*?)\]', block.group(1), re.DOTALL,
        )
        children = children_match.group(1) if children_match else ""
        # Hidden Тихон must NOT be in Perfil's children.
        self.assertNotIn("tihon_ermilovich", children)


class TestConsolidatedUnionNoDuplicatePartners(unittest.TestCase):
    """Merging single-partner unions where the same person appears as
    partner_1 in some sources and partner_2 in others must not produce
    `partners=[X, X]`.

    Concrete regression: a birth has father=None and a mother → source
    union partner_1=None, partner_2=<mother>. Later sources arrive with
    partner_1=<mother> (e.g. her death record's union). Without the
    guard, the partner_1 fold writes her into existing.partner_1 even
    though existing.partner_2 already holds her, producing
    partners=[mother, mother].
    """

    def test_no_dup_when_partner_1_equals_existing_partner_2(self):
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        # Step 1: father=None, partner_2=mother (MK-1810 birth-shaped union).
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="_and_agafija_mihajlovna_3_1810",
            partner_1=None,
            partner_2="agafija_mihajlovna",
            children={"child_1810"},
        ))
        existing = gen._consolidated_unions.get("agafija_mihajlovna")
        self.assertIsNotNone(existing)
        self.assertIsNone(existing.partner_1)
        self.assertEqual(existing.partner_2, "agafija_mihajlovna")
        # Step 2: later source brings agafija_mihajlovna as partner_1.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="agafija_mihajlovna_d_1820",
            partner_1="agafija_mihajlovna",
            partner_2=None,
            children={"child_1820"},
        ))
        # Must NOT fold partner_1 since it equals existing.partner_2.
        existing = gen._consolidated_unions["agafija_mihajlovna"]
        self.assertIsNone(existing.partner_1)
        self.assertEqual(existing.partner_2, "agafija_mihajlovna")
        # Children from both sources merged.
        self.assertEqual(existing.children, {"child_1810", "child_1820"})

    def test_no_dup_when_partner_2_equals_existing_partner_1(self):
        """Symmetric guard: incoming partner_2 must not equal existing
        partner_1. Triggered by death-record unions like
        `agafija_and_feodosija_sergeevna_d253_1817` where partner_1 is
        the deceased child and partner_2 is the parent.
        """
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        # Step 1: a single-partner placeholder for feodosija.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="feodosija_sergeevna__1_1815",
            partner_1="feodosija_sergeevna",
            partner_2=None,
            children={"child_1815"},
        ))
        # Step 2: a death-record union with partner_2=feodosija
        # (partner_1 marker matters less; we set the regex match).
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="agafija_and_feodosija_sergeevna_m1_1817",  # a marriage's couple → authoritative
            origin=UnionOrigin.MARRIAGE,
            partner_1="some_other",
            partner_2="feodosija_sergeevna",
            children={"agafija"},
        ))
        existing = gen._consolidated_unions.get("feodosija_sergeevna")
        self.assertIsNotNone(existing)
        # Must NOT fold partner_2 since it equals existing.partner_1.
        self.assertEqual(existing.partner_1, "feodosija_sergeevna")
        self.assertIsNone(existing.partner_2)


class TestCensusFatherRef(unittest.TestCase):
    """`CensusMember.father_ref` lets a wife (or any member whose father
    isn't in the same household) declare an external consolidated
    profile name as her father. The generator emits a single-partner
    sub-family union linking the external father → this member, then
    routes it to consolidation so it merges into the father's bucket
    via partner-lookup.

    Concrete regression: a WIFE married into another household; her
    father lives elsewhere. Without `father_ref`, the link to her
    father's union was lost (legacy inferred it via patronymic-based
    name matching).
    """

    def test_father_ref_emits_subfamily_union_to_external_consolidated(self):
        # `hariton_lavrentievich` consolidated profile must exist via
        # `profile_move_list` (so the wife's per-record profile gets
        # consolidated into ekaterina_haritonovna). `hariton_lavrentievich`
        # itself is in profile_move_list as a value (consolidated target),
        # which the generator uses to gate is_consolidated routing.
        consolidation = Consolidation(
            profile_move_list={
                "_1816_00_00_ekaterina_haritonovna_rs_5_5_family_member":
                    "ekaterina_haritonovna",
                "_1811_00_00_hariton_lavrentievich_rs_1_1_family_member":
                    "hariton_lavrentievich",
            },
        )
        records = census_records(
            "ГА", "36", "5", "793", "Горюхино", 1816,
            household("5", member(1, person("Матвей", "Игнатов"), CensusRole.HEAD, age=52, record_number=1),
                      member(2, person("Лука", "Матвеев"), CensusRole.SON, ref_member=1, age=8, record_number=2),
                      member(5, person("Катерина", "Харитонова",
                                       status="ясачная крестьянка"), CensusRole.WIFE, ref_member=1, age=41,
                             record_number=5,
                             father_ref="hariton_lavrentievich")),
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        gen.add_census_records(records)
        gen.finalize()
        # The synthesized father_ref union must land in
        # `_consolidated_unions` keyed by `hariton_lavrentievich`.
        self.assertIn("hariton_lavrentievich", gen._consolidated_unions)
        kj = gen._consolidated_unions["hariton_lavrentievich"]
        # Катерина (consolidated as ekaterina_haritonovna) is a child.
        self.assertIn("ekaterina_haritonovna", kj.children or set())
        # partner_1 is the consolidated father name.
        self.assertEqual(kj.partner_1, "hariton_lavrentievich")
        # No partner_2 — it's a single-parent placeholder for the
        # cross-household father.
        self.assertIsNone(kj.partner_2)

    def test_father_ref_only_wires_set_members(self):
        """Members without `father_ref` don't get a synthesized union.
        Other family members should not be affected.
        """
        consolidation = Consolidation(
            profile_move_list={
                "_1816_00_00_ekaterina_haritonovna_rs_5_5_family_member":
                    "ekaterina_haritonovna",
            },
        )
        records = census_records(
            "ГА", "36", "5", "793", "Горюхино", 1816,
            household("5", member(1, person("Матвей", "Игнатов"), CensusRole.HEAD, age=52, record_number=1),
                      member(2, person("Лука", "Матвеев"), CensusRole.SON, ref_member=1, age=8, record_number=2),
                      member(6, person("Анфиса", "Матвеева"), CensusRole.DAUGHTER, ref_member=1, age=7,
                             record_number=6)),
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        gen.add_census_records(records)
        # No `hariton_*` consolidated union created.
        self.assertNotIn("hariton_lavrentievich", gen._consolidated_unions)


class TestSiblingInheritsParentFromRefMember(unittest.TestCase):
    """A BROTHER/SISTER/NIECE/NEPHEW/COUSIN member without explicit
    `parent_member` inherits its parent from the sibling pointed to by
    `ref_member`. Semantically: if A's parent is X and B is
    BROTHER ref_member=A, B is also a child of X.

    Concrete regression: a household has a COUSIN with
    `parent_member=12` (a hidden ancestor) and two BROTHERs with
    `ref_member=5` (the cousin). Without the inheritance, the two
    brothers were dropped from the ancestor's consolidated union.
    """

    def test_brother_inherits_parent_from_sibling_ref_member(self):
        records = census_records(
            "ГА", "326", "5", "7552", "Горюхино", 1719,
            household("3", member(1, person("Игнат", "Лавров"), CensusRole.HEAD, age=87, record_number=1),
                      member(5, person("Максим", "Дорофеев"), CensusRole.COUSIN, age=33, record_number=5,
                             parent_member=12),
                      member(8, person("Лука", "Дорофеев"), CensusRole.BROTHER, ref_member=5, age=28, record_number=8),
                      member(9, person("Макар", "Дорофеев"), CensusRole.BROTHER, ref_member=5, age=17,
                             record_number=9), member(12, person("Дорофей"), None, age="?", hidden=True)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        out = gen.get_output("rs_1719_1.tf")
        # Hidden Дорофей's sub-family union must contain Лука and Макар
        # alongside Максим.
        block = re.search(
            r'resource "geni_union" "dorofej__rs3-12_1719" \{(.*?)\n\}',
            out, re.DOTALL,
        )
        self.assertIsNotNone(block, "Дорофей's sub-family union not emitted")
        children_match = re.search(
            r'children\s*=\s*\[(.*?)\]', block.group(1), re.DOTALL,
        )
        self.assertIsNotNone(children_match)
        children = children_match.group(1)
        self.assertIn("maksim_dorofeevich_rs_3_5_family_member", children)
        self.assertIn("luka_dorofeevich_rs_3_8_family_member", children)
        self.assertIn("makarij_dorofeevich_rs_3_9_family_member", children)


class TestConsolidatedUnionFoldRicherIntoV2Target(unittest.TestCase):
    """When a v2-redirected union creates a new target X with a
    spouse-agnostic name (no `_and_<spouse>` suffix), and an existing
    auto-derived target Y for the same partner already holds a richer
    `_and_<spouse>` form, fold Y INTO X (preserve Y's partner_2,
    children, marriage in the v2 target).

    Concrete regression: a `<man>` v2 target arrives after
    `<man>_and_<wife>` was auto-derived from a marriage.
    Without the fold, single-partner sources land in
    `<man>` while pair sources stay in the auto-derived
    target — splitting the same family.
    """

    def test_v2_single_partner_target_absorbs_richer_auto_derived(self):
        from verso.core.targets.geni.union import GeniEvent, GeniUnion

        consolidation = Consolidation(
            unions_to_consolidate={
                "dimitrij": {
                    "union_names": ["dimitrij__1_1820"],
                },
            },
            union_move_list_v2={
                "dimitrij__1_1820": "dimitrij",
            },
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        # Step 1: 1814 marriage union (no v2) — auto-derives to
        # `dimitrij_and_ekaterina`.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="dimitrij_and_ekaterina_m2_1814",
            origin=UnionOrigin.MARRIAGE,
            partner_1="dimitrij",
            partner_2="ekaterina",
            children=set(),
            marriage=GeniEvent(date=None),
        ))
        self.assertIn("dimitrij_and_ekaterina", gen._consolidated_unions)
        # Step 2: v2-redirected birth (single-partner-named target).
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="dimitrij__1_1820",
            partner_1="dimitrij",
            partner_2=None,
            children={"child_1820"},
        ))
        # The richer auto-derived target should be folded INTO the v2
        # target, leaving only one consolidated union.
        self.assertIn("dimitrij", gen._consolidated_unions)
        self.assertNotIn("dimitrij_and_ekaterina", gen._consolidated_unions)
        merged = gen._consolidated_unions["dimitrij"]
        self.assertEqual(merged.partner_1, "dimitrij")
        self.assertEqual(merged.partner_2, "ekaterina")
        self.assertIn("child_1820", merged.children)

    def test_undocumented_children_follow_the_profile_move_list(self):
        """`undocumented_children` is a hand-written list of res_names, so it
        lives in the RECORD namespace while `union.children` holds CANONICAL
        names after consolidation. Adding it raw leaves a dangling
        `geni_profile.<record>` reference in consolidated_unions.tf, and
        terraform fails the plan with "Reference to undeclared resource".

        Regression: folding a census res_name into its canonical broke the
        whole plan, because a union declared the census res_name as an
        undocumented child.
        """
        from verso.core.targets.geni.union import GeniUnion

        consolidation = Consolidation(
            profile_move_list={"_1850_vera_rs_98_12": "vera_andreevna"},
            unions_to_consolidate={
                "andrej_and_evdokija": {
                    "union_names": ["andrej_and_evdokija_1_1832"],
                    "undocumented_children": [
                        "_1850_vera_rs_98_12",   # consolidated -> must be mapped
                        "_1850_aleksij_rs_98_3",  # not consolidated -> unchanged
                    ],
                },
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="andrej_and_evdokija_1_1832",
            partner_1="andrej", partner_2="evdokija", children=set(),
        ))
        children = gen._consolidated_unions["andrej_and_evdokija"].children
        self.assertIn("vera_andreevna", children)
        self.assertNotIn("_1850_vera_rs_98_12", children)
        # A name that is NOT consolidated passes through untouched.
        self.assertIn("_1850_aleksij_rs_98_3", children)

    def test_exclude_children_matches_after_consolidation(self):
        """Mirror of the above: an exclusion written against a record res_name
        must still subtract the child once that record folds into a canonical.
        The raw name is subtracted too, so pre-consolidation configs keep
        working.
        """
        from verso.core.targets.geni.union import GeniUnion

        consolidation = Consolidation(
            profile_move_list={"_1850_vera_rs_98_12": "vera_andreevna"},
            unions_to_consolidate={
                "andrej_and_evdokija": {
                    "union_names": ["andrej_and_evdokija_1_1832"],
                    "exclude_children": ["_1850_vera_rs_98_12"],
                },
            },
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="andrej_and_evdokija_1_1832",
            partner_1="andrej", partner_2="evdokija",
            children={"vera_andreevna", "someone_else"},
        ))
        children = gen._consolidated_unions["andrej_and_evdokija"].children
        self.assertNotIn("vera_andreevna", children)
        self.assertIn("someone_else", children)

    def test_spouse_specific_v2_target_does_not_absorb_different_spouse(self):
        """Symmetric to the placeholder fold-in test: when the v2 target
        encodes a specific spouse (`_and_evfimija`) and the existing
        auto-derived target has a DIFFERENT partner_2 (paraskeva), do
        NOT fold them. Otherwise a different lineage is corrupted.
        """
        from verso.core.targets.geni.union import GeniUnion

        consolidation = Consolidation(
            unions_to_consolidate={
                "stefan_and_evfimija": {
                    "union_names": ["stefan__1_1820"],
                },
            },
            union_move_list_v2={
                "stefan__1_1820": "stefan_and_evfimija",
            },
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        # Step 1: 1806 marriage of Stefan + Paraskeva (no v2).
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="stefan_and_paraskeva_m1_1806",
            origin=UnionOrigin.MARRIAGE,
            partner_1="stefan",
            partner_2="paraskeva",
            children={"child_of_paraskeva"},
        ))
        # Step 2: v2-redirected MK-1820 birth → stefan_and_evfimija.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="stefan__1_1820",
            partner_1="stefan",
            partner_2=None,
            children={"child_of_evfimija"},
        ))
        # Both targets must remain — different lineages.
        self.assertIn("stefan_and_evfimija", gen._consolidated_unions)
        self.assertIn("stefan_and_paraskeva", gen._consolidated_unions)

    def test_spouse_specific_v2_target_does_not_absorb_prior_v2_target(self):
        """A spouse-specific v2 target is not a disposable placeholder
        just because partner_2 has not been discovered yet.

        Regression: a man has Irina and Agafija families. Early
        birth unions route via v2 to `stefan_and_irina`; later birth unions
        route via v2 to `stefan_and_agafija`. Both sources are single-partner
        initially, but the second target must not fold the first one in.
        """
        from verso.core.targets.geni.union import GeniUnion

        consolidation = Consolidation(
            unions_to_consolidate={
                "stefan_and_irina": {
                    "union_names": ["stefan__1_1807"],
                },
                "stefan_and_agafija": {
                    "union_names": ["stefan__3_1814"],
                },
            },
            union_move_list_v2={
                "stefan__1_1807": "stefan_and_irina",
                "stefan__3_1814": "stefan_and_agafija",
            },
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        # First v2 spouse bucket, before its marriage/partner_2 source arrives.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="stefan__1_1807",
            partner_1="stefan",
            partner_2=None,
            children={"irina_child"},
        ))
        # Second v2 spouse bucket for the same father.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="stefan__3_1814",
            partner_1="stefan",
            partner_2=None,
            children={"agafija_child"},
        ))
        # The later marriage source fills Irina's partner_2.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="stefan_and_irina_m4_1802",
            origin=UnionOrigin.MARRIAGE,
            partner_1="stefan",
            partner_2="irina",
            children=set(),
        ))

        self.assertIn("stefan_and_irina", gen._consolidated_unions)
        self.assertIn("stefan_and_agafija", gen._consolidated_unions)
        irina = gen._consolidated_unions["stefan_and_irina"]
        agafija = gen._consolidated_unions["stefan_and_agafija"]
        self.assertEqual(irina.children, {"irina_child"})
        self.assertEqual(agafija.children, {"agafija_child"})
        self.assertEqual(irina.partner_2, "irina")

        irina_sources = [
            u.res_name
            for u in gen._consolidated_unions_sources["stefan_and_irina"]
        ]
        agafija_sources = [
            u.res_name
            for u in gen._consolidated_unions_sources["stefan_and_agafija"]
        ]
        self.assertEqual(irina_sources, ["stefan__1_1807", "stefan_and_irina_m4_1802"])
        self.assertEqual(agafija_sources, ["stefan__3_1814"])


class TestConsolidatedUnionPlaceholderFoldIn(unittest.TestCase):
    """When a v2-redirected union creates a new consolidated target,
    any pre-existing single-partner placeholder consolidated union for
    the same partner gets folded in.

    Concrete regression: an early birth emits union
    `<man>__2_<year>` (no v2 mapping) → creates a `<man>` consolidated
    union (single-partner). A later birth emits `<man>__1_<year>` (in v2
    → `<man>_and_<wife>`). Without the fold-in, the early child is
    stranded in `<man>` while later children land in
    `<man>_and_<wife>`.
    Legacy collapsed both into one via its rename-on-partner_2-
    discovery path.
    """

    def test_v2_target_absorbs_prior_single_partner_placeholder(self):
        from verso.core.targets.geni.union import GeniUnion

        consolidation = Consolidation(
            unions_to_consolidate={
                "alpha_and_beta": {
                    "union_names": ["alpha__1_1804"],
                },
            },
            union_move_list_v2={
                "alpha__1_1804": "alpha_and_beta",
            },
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        # Step 1: MK-1793 union (no v2) — creates `alpha` placeholder.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="alpha__2_1793",
            partner_1="alpha",
            partner_2=None,
            children={"matrona_1793"},
        ))
        self.assertIn("alpha", gen._consolidated_unions)
        # Step 2: MK-1804 union (v2 → alpha_and_beta) — creates new
        # target AND folds `alpha` placeholder into it.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="alpha__1_1804",
            partner_1="alpha",
            partner_2=None,
            children={"grigorij_1804"},
        ))
        self.assertIn("alpha_and_beta", gen._consolidated_unions)
        # `alpha` placeholder should be gone (folded into alpha_and_beta).
        self.assertNotIn("alpha", gen._consolidated_unions)
        # Both children land in the v2 target.
        merged = gen._consolidated_unions["alpha_and_beta"]
        self.assertEqual(merged.children, {"matrona_1793", "grigorij_1804"})

    def test_two_partner_existing_target_NOT_folded_into_v2(self):
        """A v2-redirected union must NOT fold in an existing consolidated
        union that ALREADY has a partner_2 — that's a different spouse.
        Mirrors the children-by-wife split: 1806
        marriage → paraskeva target; 1820+ children v2-redirected →
        evfimija target. Folding paraskeva's union into
        evfimija's would corrupt both lineages.
        """
        from verso.core.targets.geni.union import GeniUnion

        consolidation = Consolidation(
            unions_to_consolidate={
                "stefan_and_evfimija": {
                    "union_names": ["stefan__1_1820"],
                },
            },
            union_move_list_v2={
                "stefan__1_1820": "stefan_and_evfimija",
            },
        )
        gen = TerraformGenerator(
            village_dir=None, consolidation=consolidation,
        )
        # Step 1: 1806 marriage of Stefan + Paraskeva (no v2).
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="stefan_and_paraskeva_m1_1806",
            origin=UnionOrigin.MARRIAGE,
            partner_1="stefan",
            partner_2="paraskeva",
            children={"child_of_paraskeva"},
        ))
        # Step 2: v2-redirected MK-1820 birth → stefan_and_evfimija.
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="stefan__1_1820",
            partner_1="stefan",
            partner_2=None,
            children={"child_of_evfimija"},
        ))
        # Both targets exist; paraskeva's consolidated union is intact.
        self.assertIn("stefan_and_evfimija", gen._consolidated_unions)
        self.assertIn("stefan_and_paraskeva", gen._consolidated_unions)
        paraskeva = gen._consolidated_unions["stefan_and_paraskeva"]
        self.assertEqual(paraskeva.children, {"child_of_paraskeva"})
        evfimija = gen._consolidated_unions["stefan_and_evfimija"]
        self.assertEqual(evfimija.children, {"child_of_evfimija"})


class TestCensusFamilyIdOverride(unittest.TestCase):
    """`household(family_id=...)` lets a household carry an explicit
    Cyrillic-suffixed identity (e.g. "1а"/"1б") instead of the
    auto-incremented numeric. Households with explicit family_id do
    NOT consume a slot in the numeric counter; neighbors continue
    counting 1, 2, 3 around them."""

    def _make_records(self):
        return census_records(
            "A", "1", "1", "687", "Собакевичево", 1816,
            household("1а", member(1, person("Дмитрий", "Тихонов"), CensusRole.HEAD, age=24)),
            household("1б", member(1, person("Дмитрий", "Васильев"), CensusRole.HEAD, age=8)),
            household(None, member(1, person("Ермолай", "Артемов"), CensusRole.HEAD, age=43)),
            archive_suffix="43-6-587",
        )

    def test_family_id_appears_in_member_profile_res_name(self):
        """Member of household(family_id='1а') has '_rs_1а_1_…' in its
        res_name (legacy emits the Cyrillic literal in the rs_*_M
        member-id slot, transliterated by generate_res_name to
        '_rs_1a_1_…'). The suffix '43-6-587' is only on the filename,
        not the res_name (suffix_in_res_names defaults to False)."""
        out = _run_generator(self._make_records())
        # cyrillic_to_latin maps Cyrillic 'а' (U+0430) to Latin 'a'.
        self.assertIn(
            'resource "geni_profile" "_1816_00_00_dimitrij_tihonovich_rs_1a_1_family_member"',
            out,
        )
        # The non-family_id household after them must auto-number to "1",
        # not "3" — the explicit-id slots don't consume the counter.
        self.assertIn(
            'resource "geni_profile" "_1816_00_00_ermolaj_artemovich_rs_1_1_family_member"',
            out,
        )
        self.assertNotIn(
            'resource "geni_profile" "_1816_00_00_ermolaj_artemovich_rs_3_1_family_member"',
            out,
        )

    def test_family_id_appears_in_document_resource_and_title(self):
        """Doc res_name uses the family_id literal (transliterated for
        res_name) and the title shows the Cyrillic original."""
        out = _run_generator(self._make_records())
        self.assertIn(
            'resource "geni_document" "census_of_the_family_number_1а_1816_43-6-587"',
            out,
        )
        self.assertIn(
            'title       = "Ревизская сказка Собакевичево 1816: семья 1а"',
            out,
        )

    def test_rs_filename_appends_one_partition_suffix_without_archive(self):
        """Legacy always emits census files with a `_1` partition
        suffix even when archive_suffix is absent (rs_1795_1.tf,
        rs_1721_1.tf etc.). Translator must use the same filename so
        per-file diff comparisons line up."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Аким", "Власов"), CensusRole.HEAD, age=55)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        # Census output lands in rs_{year}_1.tf …
        self.assertNotEqual(gen.get_output("rs_1795_1.tf"), "")
        # … never in bare rs_{year}.tf.
        self.assertEqual(gen.get_output("rs_1795.tf"), "")

    def test_family_id_does_not_consume_numeric_counter(self):
        """Two explicit-family_id households followed by a regular one
        give the regular one number 1 (not 3) — the family_id households
        live outside the numeric sequence."""
        out = _run_generator(self._make_records())
        # Document for the third household is "семья 1".
        self.assertIn(
            'resource "geni_document" "census_of_the_family_number_1_1816_43-6-587"',
            out,
        )
        # Not "семья 3" (the auto-counter must not have been bumped to 3
        # by the two preceding family_id households).
        self.assertNotIn(
            'resource "geni_document" "census_of_the_family_number_3_1816_43-6-587"',
            out,
        )

    def test_member_origin_location_triggers_project_substring_rule(self):
        """Census wife brought in from Сонливка (county = 'Захудаловский
        уезд') gets the neelovo project on her profile, even though her
        current_residence is the parish Горюхино (whose county lacks
        'Захудалов'). Mirrors legacy's substring-in-`prev_location` check."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Кузьма", "Тимонов"), CensusRole.HEAD, age=58),
                      member(2, person("Авдотья", "Прохорова"), CensusRole.WIFE, age=50, origin="Сонливка")),
        )
        gen = TerraformGenerator(
            village_dir=None,
            projects=[
                "data.geni_project.automatic_upload.id",
                "data.geni_project.gorjuhino.id",
            ],
            extra_project_rules={"Захудалов": "data.geni_project.neelovo.id"},
        )
        gen.add_census_records(records)
        out = gen.get_output("rs_1795_1.tf")
        # The wife's profile carries neelovo via her origin.
        wife_block = _extract_resource_block(
            out,
            "_1795_00_00_evdokija_prohorovna_rs_1_2_family_member",
        )
        self.assertIn("data.geni_project.neelovo.id", wife_block)
        # The head, with no origin and a non-Неелов residence, does not.
        head_block = _extract_resource_block(
            out,
            "_1795_00_00_kosma_timonovich_rs_1_1_family_member",
        )
        self.assertNotIn("data.geni_project.neelovo.id", head_block)


def _run_generator(records):
    gen = TerraformGenerator(village_dir=None)
    gen.add_census_records(records)
    if records.archive_suffix:
        filename = f"rs_{records.year}_{records.archive_suffix}_1.tf"
    else:
        filename = f"rs_{records.year}_1.tf"
    return gen.get_output(filename)


def _extract_resource_block(output: str, res_name: str) -> str:
    """Return the substring of `output` covering the resource block for
    `res_name`, from the opening `resource "geni_profile" "<res>" {` to
    its matching top-level `}`."""
    import re as _re
    start_m = _re.search(
        rf'resource "geni_profile" "{_re.escape(res_name)}" \{{', output
    )
    assert start_m, f"resource {res_name} not found in output"
    # Naive brace scan — works for these well-formed HCL blocks.
    depth = 0
    i = start_m.end() - 1
    while i < len(output):
        ch = output[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return output[start_m.start(): i + 1]
        i += 1
    raise AssertionError("unterminated resource block")


class TestDeathBookRecordNum(unittest.TestCase):
    """Death res_names / union names / document names use the DSL's
    per-gender record_num (the `death()` first positional arg) as the book
    record number, consistently across all years. (The historical
    CSV-derived book-global «№ п/п» override was removed — see
    TRANSLATOR_NOTES D9.)"""

    def _records(self):
        return death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1835,
            *death_month(
                Month.FEBRUARY,
                death(7, Gender.MALE, 24, None,
                      deceased=person("Афанасий", "Игнатов"),
                      age=1,
                      cause_of_death="понос"),
            ),
        )

    def test_record_num_drives_res_name_and_document_name(self):
        """The DSL per-gender record_num (7) is the book record number used
        in the profile res_name, document name, and the "№ записи" line."""
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(self._records())
        output = gen.get_output("mk_1835_death.tf")
        self.assertIn("_1835_02_24_afanasij_ignatovich_mk_deaths_7_deceased", output)
        self.assertIn("death_of_afanasij_ignatovich_d7_1835", output)
        self.assertIn("№ записи: 7", output)

    def test_unknown_day_month_render_as_one_in_death_event(self):
        """Legacy fills `1` (not `?` / None) for unknown day/month in
        the death event's date field AND the "Дата смерти" text-body
        line. Mirror that for byte-parity on records where the source
        CSV had `День = ?` / `Месяц = ?` for the death itself."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1802,
            *death_month(
                None,  # unknown month
                death(37, Gender.MALE, None, None,  # unknown day
                      deceased=person("Иван", "Петров"),
                      age=52),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1802_death.tf")
        # Death event's date carries day=1, month=1 (alignment depends
        # on whether terraform fmt has run; just assert the key=value
        # pair is present without locking the spacing).
        self.assertRegex(output, r"day\s+= 1")
        self.assertRegex(output, r"month\s+= 1")
        # Text body's "Дата смерти" matches.
        self.assertIn("Дата смерти: 1.1.1802", output)
        self.assertNotIn("Дата смерти: ?", output)


class TestDaughterInLawWifeOfDeceasedSon(unittest.TestCase):
    """Rule A: a DAUGHTER_IN_LAW (сноха) member with default ref→HEAD,
    in a household with exactly one deceased SON, is the wife of that
    deceased SON. Emit her as partner_2 of the SON's sub-family union.

    Source shape: a DAUGHTER_IN_LAW (with comment 'роль в оригинале:
    сноха') is the widow of a SON member with departure_reason='умер'.
    Legacy paired her into the deceased son's union.
    """

    def test_daughter_in_law_folded_as_partner_2_of_deceased_son(self):
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=63, previous_age=63,
                                   departure_year=1785,
                                   departure_reason="умер"),
                      member(2, person("Евдокия", "Игнатова"), CensusRole.WIFE, age=68, previous_age=68,
                             departure_year=1782,
                             departure_reason="умер"),
                      member(3, person("Лука", "Тимонов"), CensusRole.SON, age=56, previous_age=43),
                      member(6, person("Ирина", "Пахомова"), CensusRole.DAUGHTER_IN_LAW, age=48, previous_age=48,
                             departure_year=1788, departure_reason="умер", comment="роль в оригинале: сноха"),
                      member(7, person("Нестор", "Тимонов"), CensusRole.SON, age="?", departure_reason="умер"),
                      member(8, person("Влас", "Несторов"), CensusRole.SON, ref_member=7, age=43, previous_age=30)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")
        # Нестор's sub-family union must include Ирина as partner_2.
        # The deceased son is Нестор → nestor_timonovich.
        import re as _re
        union_m = _re.search(
            r'resource "geni_union" "[^"]*nestor_timonovich[^"]*" \{(.+?)\n\}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(union_m, f"Moisej's union missing in:\n{output}")
        block = union_m.group(1)
        # partner_1 should be Нестор (the deceased SON), partner_2 Ирина.
        self.assertIn("nestor_timonovich", block,
                      f"partner_1 should be Нестор; got:\n{block}")
        self.assertIn("irina_pahomovna", block,
                      f"partner_2 should be Ирина Пахомова; got:\n{block}")

    def test_daughter_in_law_not_folded_when_multiple_deceased_sons(self):
        """When the household has multiple deceased SONs, the
        DAUGHTER_IN_LAW is ambiguous — do NOT auto-fold (preserves
        editorial control). Caller can still annotate explicitly."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=63),
                      member(2, person("Ирина", "Пахомова"), CensusRole.DAUGHTER_IN_LAW, age=48,
                             comment="роль в оригинале: сноха"),
                      member(3, person("Иван", "Тимонов"), CensusRole.SON, age="?", departure_reason="умер"),
                      member(4, person("Петр", "Тимонов"), CensusRole.SON, age="?", departure_reason="умер")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")
        # No `ioann_timonovich` or `petr_timonovich` sub-family union
        # should be emitted with Анна as partner — the ambiguity blocks
        # auto-folding.
        import re as _re
        for son_token in ("ioann_timonovich", "petr_timonovich"):
            son_union = _re.search(
                r'resource "geni_union" "[^"]*' + son_token + r'[^"]*" \{(.+?)\n\}\n',
                output, _re.DOTALL,
            )
            if son_union:
                self.assertNotIn("irina_pahomovna", son_union.group(1),
                                 f"{son_token}'s union should not contain Анна "
                                 f"when there are multiple deceased sons; got:\n"
                                 f"{son_union.group(1)}")


class TestSiblingFoldedAsHeadsChild(unittest.TestCase):
    """Rule B: a BROTHER/SISTER member whose ref_member points at a
    visible SON or DAUGHTER of HEAD is genealogically a child of HEAD
    too — fold into HEAD's children list of the head+wife union.

    Source shape: a SISTER (member 3, ref_member=2 → her brother, who
    is a SON of HEAD). Legacy listed the sister alongside the brother as
    children of the HEAD.
    """

    def test_sister_of_head_son_folded_into_head_union(self):
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Дарья", "Тихонова"), CensusRole.HEAD, age=46, previous_age=46,
                                   departure_year=1795,
                                   departure_reason="умер"),
                      member(2, person("Гордей", "Макаров"), CensusRole.SON, age=45, previous_age=32),
                      member(3, person("Агриппина", "Макарова"), CensusRole.SISTER, ref_member=2, age=19,
                             previous_age=19,
                             departure_reason="выдана замуж")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")
        # Document text should still render `сестра (2)` (preserve original).
        self.assertIn("3. сестра (2): Агрипина Макаровна", output)
        # HEAD Дарья's union must list Агриппина as a child alongside Гордей.
        import re as _re
        # head_only union (no WIFE in this household — HEAD is female widow).
        union_m = _re.search(
            r'resource "geni_union" "[^"]*darija_tihonovna[^"]*" \{(.+?)\n\}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(union_m, f"Дарья's union missing in:\n{output}")
        block = union_m.group(1)
        self.assertIn("gordij_makarovich", block,
                      f"Гордей should be a child; got:\n{block}")
        self.assertIn("agripina_makarovna", block,
                      f"Агриппина should also be a child; got:\n{block}")

    def test_step_sibling_not_folded_into_head_union(self):
        """`сводный брат`/`сводная сестра` qualifier means different
        parent — do NOT fold into HEAD's children."""
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Дарья", "Тихонова"), CensusRole.HEAD, age=46),
                      member(2, person("Гордей", "Макаров"), CensusRole.SON, age=45),
                      member(3, person("Аксинья", "Иванова"), CensusRole.SISTER, ref_member=2, age=17,
                             comment="роль в оригинале: сводная сестра")),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records, suffix="1")
        output = gen.get_output("rs_1795_1.tf")
        import re as _re
        union_m = _re.search(
            r'resource "geni_union" "[^"]*darija_tihonovna[^"]*" \{(.+?)\n\}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(union_m, output)
        block = union_m.group(1)
        # Степ-sister NOT in HEAD's children.
        self.assertNotIn("aksinja", block,
                         f"step-sister should not be in HEAD's children; got:\n{block}")


class TestSonInLawHiddenDaughterPair(unittest.TestCase):
    """Option α: when DAUGHTER has parent_member→HEAD (visible) AND
    ref_member→another household member (her husband), both relationships
    must materialize:
      1. HEAD's union lists her as a child (via parent_member→HEAD).
      2. A sub-family union pairs her husband + her with their children.

    Source pattern: a hidden DAUGHTER (m17) is the HEAD's daughter AND
    the wife of a SON_IN_LAW (m8).
    """

    def _records(self):
        return census_records(
            "A", "1", "1", "1", "Горюхино", 1811,
            household(None, member(1, person("Ермил", "Парамонов"), CensusRole.HEAD, age=61, previous_age=61,
                                   departure_year=1798, departure_reason="умер"),
                      member(8, person("Александр", "Тарасов"), CensusRole.SON_IN_LAW, age=62, previous_age=46),
                      member(9, person("Гордей", "Александров"), CensusRole.SON, ref_member=8, age=33),
                      member(11, person("Тимон", "Александров"), CensusRole.SON, ref_member=8, age=24),
                      member(17, person("Ульяна", "Ермилова"), CensusRole.DAUGHTER, ref_member=8, age="?",
                             parent_member=1,
                             hidden=True)),
        )

    def test_head_includes_daughter_when_parent_member_points_to_head(self):
        """Even with `ref_member` pointing at another member (her
        husband), Ульяна is HEAD's daughter via `parent_member=1`."""
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(self._records(), suffix="1")
        output = gen.get_output("rs_1811_1.tf")
        import re as _re
        head_union = _re.search(
            r'resource "geni_union" "[^"]*ermil_paramonovich[^"]*" \{(.+?)\n\}\n',
            output, _re.DOTALL,
        )
        self.assertIsNotNone(head_union, f"HEAD's union missing in:\n{output}")
        self.assertIn("juliana_ermilovna", head_union.group(1),
                      f"Ульяна should be HEAD's daughter; got:\n{head_union.group(1)}")

    def test_son_in_law_husband_wife_union_emitted(self):
        """A sub-family union pairs Александр (m8) with hidden Ульяна
        (m17 ref_member=8) and their sons as children."""
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(self._records(), suffix="1")
        output = gen.get_output("rs_1811_1.tf")
        import re as _re
        # Legacy res_name format: head_of_family_<seya>_<year>_<m>_<arch>
        # but the new format uses _build_subfamily_union_res_name which
        # produces something like aleksandr_avakumov_rs1-8_1811. Match
        # any sub-family union containing both Александр and Ульяна.
        for m in _re.finditer(
            r'resource "geni_union" "([^"]+)" \{((?:[^{}]|\{[^}]*\})+)\}\n',
            output,
        ):
            block = m.group(2)
            # Александр Тарасов canonicalizes to aleksandr_tarasovich.
            if ("aleksandr_tarasovich" in block.lower()
                    and "juliana_ermilovna" in block):
                # Found the union. Check children include the sons.
                self.assertIn("gordij_aleksandrovich", block,
                              f"Антон should be a child; got:\n{block}")
                self.assertIn("timon_aleksandrovich", block,
                              f"Федор should be a child; got:\n{block}")
                return
        self.fail(f"Александр+Ульяна sub-family union missing in:\n{output}")


class TestRoleNoneWithParentMemberHead(unittest.TestCase):
    """A hidden member with `role=None`, `parent_member=HEAD`, and
    `ref_member=<spouse>` represents a child of HEAD whose spouse is
    encoded via `ref_member` (a `role=SON` on the same member would
    cause `ref_member` to be interpreted as the parent — see the
    spouse-inference guard at `tf_translator.py:4784-4787`).

    Such members must be included in HEAD's union as children. Without
    this, e.g. a member (role=None, parent_member=1=head,
    ref_member=15=a wife) is dropped from the head's union's children
    list while still appearing in his own marital union with the wife.
    """

    def _records(self):
        return census_records(
            "A", "1", "1", "1", "Горюхино", 1850,
            household(None, member(1, person("Захар", "Ермолаев"), CensusRole.HEAD, age=69),
                      member(2, person("Лука", "Захаров"), CensusRole.SON, age="?", hidden=True),
                      member(3, person("Фекла", "Прохорова"), CensusRole.MOTHER, ref_member=4, age=56),
                      member(4, person("Ипат", "Захаров"), None, ref_member=3, age="?", parent_member=1,
                             hidden=True)),
        )

    def test_head_union_includes_role_none_child_with_parent_member_head(self):
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(self._records(), suffix="1")
        output = gen.get_output("rs_1850_1.tf")
        head_union = re.search(
            r'resource "geni_union" "[^"]*zaharija_ermolaev[^"]*" \{(.+?)\n\}\n',
            output, re.DOTALL,
        )
        self.assertIsNotNone(head_union, f"HEAD's union missing in:\n{output}")
        block = head_union.group(1)
        self.assertIn("ipatij_zaharovich", block,
                      f"Ипат (role=None, parent_member=HEAD) should be "
                      f"HEAD's child; got:\n{block}")


class TestWifeOfSonInLawIsHeadsDaughterViaParentMember(unittest.TestCase):
    """A WIFE-role member with `parent_member=HEAD` is HEAD's daughter
    (married to a SON_IN_LAW in the same household). Without this,
    HEAD's union is emitted as a singleton with no children even when
    the daughter's patronymic and explicit `parent_member` link her to
    HEAD.

    Source pattern: m1 HEAD, m2 SON_IN_LAW, m3 WIFE (ref_member=2,
    parent_member=1) — m3 is the head's daughter AND the son-in-law's
    wife.
    """

    def _records(self):
        return census_records(
            "A", "1", "1", "1", "Горюхино", 1834,
            household(None, member(1, person("Тимофей", "Артемов"), CensusRole.HEAD, age=63),
                      member(2, person("Перфил", "Ипатов"), CensusRole.SON_IN_LAW, age=48),
                      member(3, person("Татьяна", "Тимофеева"), CensusRole.WIFE, ref_member=2, age=48,
                             parent_member=1)),
        )

    def test_head_union_includes_wife_with_parent_member_head(self):
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(self._records(), suffix="1")
        output = gen.get_output("rs_1834_1.tf")
        head_union = re.search(
            r'resource "geni_union" "[^"]*timofej_artemovich[^"]*" \{(.+?)\n\}\n',
            output, re.DOTALL,
        )
        self.assertIsNotNone(head_union, f"HEAD's union missing in:\n{output}")
        block = head_union.group(1)
        self.assertIn("tatiana_timofeevna", block,
                      f"Татьяна (WIFE, parent_member=HEAD) should be HEAD's "
                      f"daughter; got:\n{block}")


class TestSecondaryRoleHusbandHiddenBrother(unittest.TestCase):
    """A hidden BROTHER of HEAD whose `secondary_role=HUSBAND,
    secondary_ref_member=<wife>` describes an additional marital
    relationship beyond his primary BROTHER role. The translator must
    emit a marital union pairing the hidden BROTHER with his wife.

    Source pattern: m1 HEAD, m2 DAUGHTER_IN_LAW (сноха), m12 a hidden
    BROTHER of HEAD who is the husband of m2. Legacy emitted a
    sub-family union with both partners.
    The new translator needs an explicit secondary-role annotation
    because BROTHER's `ref_member` already encodes a primary
    relationship (sibling parent chain).
    """

    def _records(self):
        return census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None, member(1, person("Семен", "Гордеев"), CensusRole.HEAD, age=51),
                      member(2, person("Афимья", "Власова"), CensusRole.DAUGHTER_IN_LAW, age=46),
                      member(3, person("Тимон", "Гордеев"), CensusRole.BROTHER, age="?",
                             secondary_role=CensusRole.HUSBAND, secondary_ref_member=2, hidden=True)),
        )

    def test_marital_union_emitted_from_secondary_husband(self):
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(self._records(), suffix="1")
        output = gen.get_output("rs_1795_1.tf")
        # Find any union pairing Тимон Гордеев with Афимья Власова.
        for m in re.finditer(
            r'resource "geni_union" "([^"]+)" \{((?:[^{}]|\{[^}]*\})+)\}\n',
            output,
        ):
            block = m.group(2)
            if ("timon_gordeevich" in block
                    and "afimja_vlasovna" in block.lower().replace(
                        "afimja_vlasovna", "afimja_vlasovna")):
                return
            # Patronymic may render as evfimija_fominichna (Афимья ↔ Ефимия
            # canonicalization) — accept either.
            if ("timon_gordeevich" in block
                    and ("vlasovna" in block)):
                return
        self.fail(
            f"Marital union for hidden Тимон + Афимья missing in:\n{output}"
        )


class TestAboutSectionsSortedByYear(unittest.TestCase):
    """Profile about-blocks should be sorted chronologically by the year
    in each `<strong>МК|РС <place> <YEAR>:</strong>` section header.

    Mirrors legacy `Горюхино/generate_config.py:2272-2291` which used
    `sorted(date_to_source.keys())` to merge about-blocks in date order.
    The new translator accumulates blocks in record-emission order; this
    test exercises the finalize-time sort that restores chronology.
    """

    def test_sort_about_sections_by_year(self):
        from verso.ru.targets.geni.translator import _sort_about_sections
        about = (
            "<strong>МК Горюхино 1796:</strong> отец ребенка\n"
            "        Комментарий: 1796 record\n"
            "\n"
            "        <strong>МК Собакевичево 1784:</strong> жених\n"
            "        Комментарий: 1784 record\n"
            "\n"
            "        <strong>РС Горюхино 1834:</strong> семья 7\n"
            "        Комментарий: 1834 record\n"
            "\n"
            "        <strong>РС Горюхино 1795:</strong> семья 28\n"
            "        Комментарий: 1795 record"
        )
        sorted_about = _sort_about_sections(about)
        years_in_order = [
            int(m) for m in re.findall(
                r'<strong>(?:МК|РС)[^<]*?(\d{4}):', sorted_about)
        ]
        self.assertEqual(years_in_order, [1784, 1795, 1796, 1834],
                         f"sections not sorted; got order {years_in_order} "
                         f"in:\n{sorted_about}")

    def test_sort_about_sections_same_year_by_full_date_marker(self):
        """Two same-year same-kind (МК) sections must order by full date
        from the embedded <!--sd:--> marker, not record-emission order.
        Regression: one person's жених (22 Jan 1839) and отец
        ребенка (7 Nov 1839) sections, both МК 1839 — showed the Nov birth
        above the Jan wedding because births are emitted before
        marriages."""
        from verso.ru.targets.geni.translator import _sort_about_sections
        # Birth (Nov) declared FIRST; sort must pull the Jan wedding above it.
        about = (
            "<strong>МК Горюхино 1839:</strong> отец ребенка<!--sd:1839-11-07-->\n"
            "        Комментарий: birth Nov\n"
            "\n"
            "        <strong>МК Горюхино 1839:</strong> жених<!--sd:1839-01-22-->\n"
            "        Комментарий: marriage Jan"
        )
        sorted_about = _sort_about_sections(about)
        self.assertLess(
            sorted_about.find("жених"), sorted_about.find("отец ребенка"),
            f"Jan wedding must precede Nov birth:\n{sorted_about}")

    def test_strip_section_date_markers_removes_marker(self):
        from verso.core.targets.geni.about import strip_section_date_markers
        s = ("<strong>МК Горюхино 1839:</strong> жених<!--sd:1839-01-22-->\n"
             "        foo")
        self.assertEqual(
            strip_section_date_markers(s),
            "<strong>МК Горюхино 1839:</strong> жених\n        foo")
        self.assertEqual(strip_section_date_markers(""), "")
        self.assertEqual(strip_section_date_markers(None), None)

    def test_sort_about_sections_non_mk_rs_label(self):
        """Census documents with a custom `document_type` label (not the
        legacy МК/РС prefixes) must still be recognised as sortable
        sections. Regression: the 1897 "1-я всеобщая перепись" header
        was unrecognised, so a перепись section sandwiched between МК
        sections got shoved to the end instead of sorting by year."""
        from verso.ru.targets.geni.translator import _sort_about_sections
        about = (
            "<strong>МК Нижняя Яичница 1896:</strong> мать ребенка\n"
            "        Комментарий: 1896\n"
            "\n"
            "        <strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 9\n"
            "        Род занятий: повивальная бабка\n"
            "\n"
            "        <strong>МК Нижняя Яичница 1894:</strong> мать ребенка\n"
            "        Комментарий: 1894"
        )
        sorted_about = _sort_about_sections(about)
        years_in_order = [
            int(m) for m in re.findall(
                r'<strong>[^<]*?(\d{4})\s*:', sorted_about)
        ]
        self.assertEqual(years_in_order, [1894, 1896, 1897],
                         f"got {years_in_order} in:\n{sorted_about}")

    def test_sort_about_single_section_is_noop(self):
        from verso.ru.targets.geni.translator import _sort_about_sections
        about = "<strong>МК Горюхино 1810:</strong> отец ребенка\nfoo"
        self.assertEqual(_sort_about_sections(about), about)

    def test_sort_about_empty_is_noop(self):
        from verso.ru.targets.geni.translator import _sort_about_sections
        self.assertEqual(_sort_about_sections(""), "")
        self.assertEqual(_sort_about_sections(None), None)

    def test_sort_about_preserves_inter_section_separator(self):
        """Reordered sections should still have `\\n\\n        ` between
        them (blank line + 8-space indent), regardless of how the
        original separators were distributed across the input.

        Regression: original implementation kept trailing separators on
        each extracted section, so when sections moved their separators
        moved with them — producing two adjacent sections without the
        blank-line + indent (sections would butt up against each other).
        """
        from verso.ru.targets.geni.translator import _sort_about_sections
        # Two sections in reverse chronological order (1850 first, 1834
        # second). Sort should produce 1834 then 1850, separated cleanly.
        about = (
            "        <strong>РС Горюхино 1850:</strong> семья 7\n"
            "        Комментарий: 1850\n"
            "\n"
            "        <strong>РС Горюхино 1834:</strong> семья 7\n"
            "        Комментарий: 1834"
        )
        sorted_about = _sort_about_sections(about)
        self.assertIn(
            "1834\n"
            "\n"
            "        <strong>РС Горюхино 1850:",
            sorted_about,
            f"inter-section separator missing/wrong; got:\n{sorted_about}",
        )

    def test_sort_about_appendix_emitted_at_end(self):
        """Override.about appendix (life-dates + URL) attached mid-stream
        in the record-emission order must end up AFTER all sorted
        sections, matching legacy `Горюхино/generate_config.py:2293-2296`
        which appends override.about after the sort step.
        """
        from verso.ru.targets.geni.translator import _sort_about_sections
        about = (
            "<strong>МК Горюхино 1818:</strong> умерший\n"
            "        Титул/звание: помещик\n"
            "\n"
            "        около 1750 – 1818\n"
            "\n"
            "        https://rgfond.ru/person/10002\n"
            "\n"
            "        <strong>МК Горюхино 1832:</strong> отец невесты\n"
            "        Титул/звание: помещик"
        )
        sorted_about = _sort_about_sections(about)
        # Sections in chronological order, appendix at the end.
        # Find positions of each marker:
        pos_1818 = sorted_about.find("МК Горюхино 1818")
        pos_1832 = sorted_about.find("МК Горюхино 1832")
        pos_url = sorted_about.find("rgfond.ru/person/10002")
        pos_dates = sorted_about.find("около 1750 – 1818")
        self.assertGreater(pos_1832, pos_1818, "1832 must be after 1818")
        self.assertGreater(pos_dates, pos_1832,
                           "appendix dates must come after last section")
        self.assertGreater(pos_url, pos_1832,
                           "appendix URL must come after last section")

    def test_sort_about_rs_before_mk_same_year(self):
        """For sections in the same year, РС should sort before МК
        (legacy convention: source_date='YYYY' for РС sorts as a
        shorter prefix before source_date='YYYY-MM-DD' for МК).
        """
        from verso.ru.targets.geni.translator import _sort_about_sections
        about = (
            "        <strong>МК Горюхино 1816:</strong> поручитель\n"
            "        line MK\n"
            "\n"
            "        <strong>РС Собакевичево 1816:</strong> семья 2\n"
            "        line RS"
        )
        sorted_about = _sort_about_sections(about)
        kinds = re.findall(r'<strong>(МК|РС)', sorted_about)
        self.assertEqual(kinds, ["РС", "МК"],
                         f"РС should precede МК for same year; got {kinds} "
                         f"in:\n{sorted_about}")

    def test_sort_about_stable_within_same_year(self):
        from verso.ru.targets.geni.translator import _sort_about_sections
        about = (
            "<strong>МК Горюхино 1816:</strong> A\n"
            "        line A\n"
            "\n"
            "        <strong>МК Горюхино 1810:</strong> X\n"
            "        line X\n"
            "\n"
            "        <strong>МК Горюхино 1816:</strong> B\n"
            "        line B"
        )
        sorted_about = _sort_about_sections(about)
        labels = re.findall(r'<strong>МК Горюхино \d{4}:</strong> (\w)',
                            sorted_about)
        self.assertEqual(labels, ["X", "A", "B"])


class TestUnreviewedRecordsAreSkipped(unittest.TestCase):
    """Records with reviewed=False are dropped before TF emission."""

    def test_unreviewed_birth_does_not_produce_resources(self):
        records = birth_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *birth_month(
                Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван", last_name_orig="Reviewedov"),
                      father=person("Петр", last_name_orig="Reviewedov"),
                      reviewed=True),
                birth(2, Gender.FEMALE, 12, 13,
                      child=person("Мария", last_name_orig="Skippedov"),
                      father=person("Алексей", last_name_orig="Skippedov"),
                      reviewed=False),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1800_birth.tf")

        self.assertIn("Reviewedov", output)
        self.assertNotIn("Skippedov", output)

    def test_unreviewed_death_does_not_produce_resources(self):
        records = death_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *death_month(
                Month.MARCH,
                death(1, Gender.MALE, 5,
                      deceased=person("Иван", last_name_orig="Reviewedov"),
                      age=42, reviewed=True),
                death(2, Gender.MALE, 6,
                      deceased=person("Алексей", last_name_orig="Skippedov"),
                      age=50, reviewed=False),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1800_death.tf")

        self.assertIn("Reviewedov", output)
        self.assertNotIn("Skippedov", output)

    def test_unreviewed_marriage_does_not_produce_resources(self):
        records = marriage_records(
            "TestArchive", "1", "1", "1", "Тестовка", "Никольская",
            1800,
            *marriage_month(
                Month.MARCH,
                marriage(1, 10,
                         groom=person("Иван", last_name_orig="Reviewedov"),
                         bride=person("Анна", last_name_orig="Reviewedova"),
                         reviewed=True),
                marriage(2, 15,
                         groom=person("Алексей", last_name_orig="Skippedov"),
                         bride=person("Марфа", last_name_orig="Skippedova"),
                         reviewed=False),
            ),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1800_marriage.tf")

        self.assertIn("Reviewedov", output)
        self.assertNotIn("Skippedov", output)

    def test_unreviewed_household_does_not_produce_resources(self):
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1811,
            household("1", member(1, person("Иван", "Петров", "Reviewedov"),
                                  CensusRole.HEAD, age=40)),
            household("2", member(1, person("Алексей", "Петров", "Skippedov"),
                                  CensusRole.HEAD, age=30),
                      reviewed=False),
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1811_1.tf")

        self.assertIn("Reviewedov", output)
        self.assertNotIn("Skippedov", output)

    def test_file_level_reviewed_false_skips_every_household(self):
        records = census_records(
            "TestArchive", "1", "1", "1", "Тестовка", 1811,
            household("1", member(1, person("Иван", "Петров", "Skippedov"),
                                  CensusRole.HEAD, age=40)),
            household("2", member(1, person("Алексей", "Петров", "Reviewedov"),
                                  CensusRole.HEAD, age=30),
                      reviewed=True),
            reviewed=False,
        )

        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        output = gen.get_output("rs_1811_1.tf")

        # The file default suppresses household 1; household 2 opts back in.
        self.assertNotIn("Skippedov", output)
        self.assertIn("Reviewedov", output)


if __name__ == "__main__":
    unittest.main()


class CensusDaughterMaidenResName(unittest.TestCase):
    """A daughter's res_name must keep her surname even when it lives in
    `birth_last_name` (maiden) rather than `last_name`.

    `CensusHousehold.__init__` reslots a DAUGHTER's derived surname to
    birth_last_name (Geni maiden_name), leaving last_name_modern empty. Keying
    the res_name off last_name alone therefore DROPPED the surname the moment a
    redundant explicit one was removed from the DSL — renaming live
    profiles, which on an applied village is a destroy+recreate. The MK path
    already falls back to the maiden (`res_name_last = last_name or
    birth_last_name`); the census path must too.
    """

    def test_daughter_keeps_derived_surname_in_res_name(self):
        from verso.ru.dsl.records.census import CensusRole, census_records, household, member
        from verso.ru.domain import person, page
        from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator

        recs = census_records(
            "a", "f", "i", "d", "Горюхино", 1850,
            *page("1", household(None, member(1, person("Варфоломей", "Иванов", "Кашеваров"),
                                              CensusRole.HEAD, age=50),
                                 member(2, person("Акилина"), CensusRole.DAUGHTER,
                                        ref_member=1, age=20)), day=1, month=Month.OCTOBER),
        )
        gen = TerraformGenerator(consolidation=Consolidation())
        gen.add_census_records(recs)
        daughter = [n for n in gen.canonical_profiles() if "akilina" in n]
        self.assertTrue(daughter, list(gen.canonical_profiles()))
        self.assertTrue(
            any("kashevarova" in n for n in daughter),
            f"daughter res_name lost the derived maiden surname: {daughter}")


class TestParentBirthEstimate(unittest.TestCase):
    """Fathers and mothers named in a metric-book record get a synthetic
    `birth` range anchored on the CHILD's (estimated) birth year — see
    `verso.ru.targets.geni.translator.birth_estimates`."""

    def test_birth_record_parents_get_anchored_between_range(self):
        """The child's birth year is the anchor: father 60→15 years earlier,
        mother 50→15."""
        records = birth_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1838,
            *birth_month(
                Month.JANUARY,
                birth(3, Gender.MALE, 4, 5,
                      child=person("Гордей"),
                      father=person("Харитон", "Матвеев"),
                      mother=person("Анна", "Борисова")),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1838_birth.tf")

        father = _extract_resource_block(
            output, "_1838_01_04_hariton_matveevich_mk_births_3_father")
        self.assertIn('range     = "between"', father)
        self.assertIn('year      = 1778', father)   # 1838 − 60
        self.assertIn('end_year  = 1823', father)   # 1838 − 15

        mother = _extract_resource_block(
            output, "_1838_01_04_anna_borisovna_mk_births_3_mother")
        self.assertIn('range     = "between"', mother)
        self.assertIn('year      = 1788', mother)   # 1838 − 50
        self.assertIn('end_year  = 1823', mother)   # 1838 − 15

    def test_marriage_father_anchored_on_partner_age(self):
        """Groom aged 20 in 1820 ⇒ born 1800 ⇒ his father born 1740–1785."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(2, 20,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         groom_age=20,
                         relatives=[
                             Relative(person("Петр", "Алексеев"),
                                      Relationship.FATHER, "жених"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        block = _extract_resource_block(
            output, "_1820_01_20_petr_alekseevich_mk_marriages_2_groom_father")
        self.assertIn('range     = "between"', block)
        self.assertIn('year      = 1740', block)   # 1800 − 60
        self.assertIn('end_year  = 1785', block)   # 1800 − 15

    def test_marriage_father_without_partner_age_gets_before_bound_only(self):
        """No stated groom age ⇒ no anchor ⇒ only the upper bound. A flat
        window off the wedding year would assert a false LOWER bound."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(2, 20,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         relatives=[
                             Relative(person("Петр", "Алексеев"),
                                      Relationship.FATHER, "жених"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        block = _extract_resource_block(
            output, "_1820_01_20_petr_alekseevich_mk_marriages_2_groom_father")
        self.assertIn('range = "before"', block)
        self.assertIn('year  = 1805', block)       # 1820 − 15
        self.assertNotIn("end_year", block)

    def test_marriage_mother_relative_uses_mother_bound(self):
        """A MOTHER tagged `relationship_ref="невеста"` flows through
        `_emit_relatives` and gets the 50-year mother window."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(2, 20,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         bride_age=18,
                         relatives=[
                             Relative(person("Дарья", "Кузьмина"),
                                      Relationship.MOTHER, "невеста"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        block = _extract_resource_block(
            output, "_1820_01_20_darija_kuzminichna_mk_marriages_2_rel_1")
        self.assertIn('range     = "between"', block)
        self.assertIn('year      = 1752', block)   # 1802 − 50
        self.assertIn('end_year  = 1787', block)   # 1802 − 15

    def test_marriage_witness_relative_stays_bare(self):
        """A non-parent relative gets no birth estimate — the offset rule
        does not apply to siblings/in-laws."""
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "Никольская",
            1820,
            *marriage_month(
                Month.JANUARY,
                marriage(7, 20,
                         groom=person("Иван", "Петров"),
                         bride=person("Мария", "Иванова"),
                         groom_age=20,
                         relatives=[
                             Relative(person("Сидор", "Петров"),
                                      Relationship.SON, "жених"),
                         ]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1820_marriage.tf")

        block = _extract_resource_block(
            output, "_1820_01_20_isidor_petrovich_mk_marriages_7_rel_1")
        self.assertNotIn("birth = {", block)

    def test_death_record_father_anchored_on_deceased_birth_year(self):
        """Deceased aged 45 in 1820 ⇒ born 1775 ⇒ father born 1715–1760."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      age=45,
                      relatives=[Relative(person("Петр", "Алексеев"),
                                          Relationship.FATHER)]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        block = _extract_resource_block(
            output, "_1820_06_05_petr_alekseevich_mk_deaths_1_relative")
        self.assertIn('range     = "between"', block)
        self.assertIn('year      = 1715', block)   # 1775 − 60
        self.assertIn('end_year  = 1760', block)   # 1775 − 15

    def test_death_record_husband_relative_stays_bare(self):
        """A HUSBAND of the deceased is same-generation — no estimate."""
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.FEMALE, 5, None,
                      deceased=person("Мария", "Иванова"),
                      age=45,
                      relatives=[Relative(person("Петр", "Алексеев"),
                                          Relationship.HUSBAND)]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        block = _extract_resource_block(
            output, "_1820_06_05_petr_alekseevich_mk_deaths_1_relative")
        self.assertNotIn("birth = {", block)

    def test_death_record_father_without_deceased_age_gets_before_bound(self):
        records = death_records(
            "A", "1", "1", "1", "Горюхино", "N",
            1820,
            *death_month(
                Month.JUNE,
                death(1, Gender.MALE, 5, None,
                      deceased=person("Иван", "Петров"),
                      relatives=[Relative(person("Петр", "Алексеев"),
                                          Relationship.FATHER)]),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_death_records(records)
        output = gen.get_output("mk_1820_death.tf")

        block = _extract_resource_block(
            output, "_1820_06_05_petr_alekseevich_mk_deaths_1_relative")
        self.assertIn('range = "before"', block)
        self.assertIn('year  = 1805', block)
        self.assertNotIn("end_year", block)


class TestAdultBirthWindowRefactor(unittest.TestCase):
    """`adult_birth_window` replaced three inline copies of the same
    `between [year-60, year-N]` shape. Guard the exact output."""

    def test_windows_match_previous_inline_shapes(self):
        from verso.ru.targets.geni.translator.birth_estimates import adult_birth_window

        for min_age, expected_end in ((6, 1832), (13, 1825), (17, 1821)):
            with self.subTest(min_age=min_age):
                ev = adult_birth_window(1838, min_age=min_age)
                self.assertEqual(ev.date.year, 1778)
                self.assertEqual(ev.date.end_year, expected_end)
                self.assertEqual(ev.date.date_range, "between")
                self.assertTrue(ev.date.circa)
                self.assertTrue(ev.date.end_circa)


class TestPickBestDateBeforeBound(unittest.TestCase):
    """A `range="before"` parent-birth estimate must never win over a real
    date — otherwise consolidation would discard e.g. a census circa year."""

    @staticmethod
    def _pick(existing, incoming):
        return TerraformGenerator._pick_best_date(existing, incoming)

    def test_before_bound_yields_to_circa_year_inside_it(self):
        from verso.core.targets.geni.date import GeniDate

        existing = GeniDate(year=1805, circa=True, date_range="before")
        incoming = GeniDate(year=1775, circa=True)
        merged = self._pick(existing, incoming)
        self.assertIs(merged, incoming)

    def test_before_bound_yields_to_specific_date_inside_it(self):
        from verso.core.targets.geni.date import GeniDate

        existing = GeniDate(year=1805, circa=True, date_range="before")
        incoming = GeniDate(day=3, month=4, year=1775)
        merged = self._pick(existing, incoming)
        self.assertIs(merged, incoming)

    def test_incoming_before_bound_does_not_override_existing_date(self):
        from verso.core.targets.geni.date import GeniDate

        existing = GeniDate(year=1775, circa=True)
        incoming = GeniDate(year=1805, circa=True, date_range="before")
        merged = self._pick(existing, incoming)
        self.assertEqual(merged.year, 1775)
        self.assertIsNone(merged.date_range)


class TestJulianLeapDay(unittest.TestCase):
    """The books are kept in the JULIAN calendar, where every fourth year is a
    leap year — 1700, 1800 and 1900 included. Python's `datetime` is proleptic
    GREGORIAN, where those three are not. A death record of 1800 is dated
    «29 го» February on the scan, and merging it into its canonical crashed
    the whole generate with «day 29 must be in range 1..28».
    """

    def test_a_julian_leap_day_sorts_between_its_neighbours(self):
        from verso.core.targets.geni.date import GeniDate

        before = GeniDate(day=28, month=2, year=1800).to_datetime()
        leap = GeniDate(day=29, month=2, year=1800).to_datetime()
        after = GeniDate(day=1, month=3, year=1800).to_datetime()
        assert before is not None and leap is not None and after is not None
        self.assertLess(before, leap)
        self.assertLess(leap, after)

    def test_an_end_bound_on_a_julian_leap_day_sorts_too(self):
        from verso.core.targets.geni.date import GeniDate

        g = GeniDate(year=1799, date_range="between",
                     end_day=29, end_month=2, end_year=1800)
        end = g.to_end_datetime()
        before = GeniDate(day=28, month=2, year=1800).to_datetime()
        after = GeniDate(day=1, month=3, year=1800).to_datetime()
        assert end is not None and before is not None and after is not None
        self.assertLess(before, end)
        self.assertLess(end, after)

    def test_merging_it_into_a_canonical_does_not_crash(self):
        """The shape that crashed: a revision's survival bound on the
        canonical, then the burial record's exact date arriving."""
        from verso.core.targets.geni.date import GeniDate

        existing = GeniDate(year=1762, date_range="after")
        incoming = GeniDate(day=29, month=2, year=1800)
        merged = TerraformGenerator._pick_best_date(existing, incoming)
        self.assertEqual((29, 2, 1800), (merged.day, merged.month, merged.year))

    def test_any_other_impossible_date_still_fails_loudly(self):
        """Only the Julian leap day is tolerated. 31 November
        and 29 February in a Julian COMMON year are transcription errors, and a
        crash is how they get noticed."""
        from verso.core.targets.geni.date import GeniDate

        for g in (GeniDate(day=31, month=11, year=1822),
                  GeniDate(day=29, month=2, year=1801)):
            with self.subTest(str(g)), self.assertRaises(ValueError):
                g.to_datetime()


class TestSyntheticEstimateDropsOutOfConsolidation(unittest.TestCase):
    """A parent-birth estimate is DERIVED from a relative's date, not read off
    a record. It gives an otherwise dateless per-record stub something for Geni
    to match on, and drops out entirely as soon as any other dated birth is in
    play — so every already-consolidated date stays exactly what it was."""

    @staticmethod
    def _estimate(year, end_year):
        from verso.core.targets.geni.date import GeniDate
        return GeniDate(year=year, end_year=end_year, circa=True,
                        end_circa=True, date_range="between", synthetic=True)

    @staticmethod
    def _merge(a, b):
        from verso.core.targets.geni.event import GeniEvent
        return TerraformGenerator._merge_event(GeniEvent(date=a),
                                               GeniEvent(date=b))

    def test_record_date_survives_a_conflicting_estimate(self):
        """A recorded circa 1896 vs an estimate saying
        1849–1884. Letting the estimate in silently hid a real age conflict."""
        from verso.core.targets.geni.date import GeniDate

        real = GeniDate(year=1896, circa=True)
        est = self._estimate(1849, 1884)
        self.assertIs(self._merge(est, real).date, real)
        self.assertIs(self._merge(real, est).date, real)

    def test_estimate_never_widens_a_known_year(self):
        from verso.core.targets.geni.date import GeniDate

        real = GeniDate(year=1796, circa=True)
        merged = self._merge(self._estimate(1810, 1818), real).date
        self.assertIsNone(merged.date_range)
        self.assertEqual(merged.year, 1796)

    def test_estimate_yields_to_a_godparent_window_too(self):
        """Even another ESTIMATE wins over it — the rule is order-independent
        on purpose, so consolidated dates cannot shift with merge order."""
        from verso.core.targets.geni.date import GeniDate

        window = GeniDate(year=1778, end_year=1832, circa=True,
                          end_circa=True, date_range="between")
        est = self._estimate(1789, 1822)
        self.assertIs(self._merge(window, est).date, window)
        self.assertIs(self._merge(est, window).date, window)

    def test_estimate_survives_when_nothing_else_is_dated(self):
        from verso.core.targets.geni.event import GeniEvent

        est = self._estimate(1789, 1822)
        merged = TerraformGenerator._merge_event(
            GeniEvent(date=est), GeniEvent(date=None, location="X"))
        self.assertIs(merged.date, est)

    def test_two_estimates_still_intersect(self):
        merged = self._merge(self._estimate(1778, 1832),
                             self._estimate(1789, 1822)).date
        self.assertEqual(merged.date_range, "between")
        self.assertEqual(merged.year, 1789)
        self.assertEqual(merged.end_year, 1822)

    def test_synthetic_flag_is_not_emitted_to_terraform(self):
        block = self._estimate(1789, 1822).to_terraform()
        self.assertNotIn("synthetic", block)


class TestEstimateVsEstimateIntersects(unittest.TestCase):
    """Two BIRTH ESTIMATES must intersect, not let the looser one win.

    `_merge_event` drops a `synthetic` date whenever the other side is not
    synthetic, on the theory that a non-synthetic date was "read off a record"
    and is therefore better. `adult_birth_window` is not read off a record — it
    is the loosest estimate we emit (a godparent window is 54 years wide,
    min_age=6) — so leaving it unflagged let it beat the far tighter
    `parent_birth_estimate` outright instead of reaching `_pick_best_date`,
    whose branch 7 already narrows two overlapping between-ranges.

    The case: a mother in 1911 and 1914, widened from 1864-1896 to 1847-1901
    when her 1907 godparent record was folded in — admitting a birth that
    would make her 64 at the 1911 childbirth.
    """

    @staticmethod
    def _merge(a, b):
        return TerraformGenerator._merge_event(a, b)

    def test_godparent_window_does_not_widen_parent_estimate(self):
        from verso.ru.gender import Gender
        from verso.ru.targets.geni.translator.birth_estimates import (
            adult_birth_window, parent_birth_estimate)

        mother_1911 = parent_birth_estimate(1911, Gender.FEMALE, record_year=1911)
        mother_1914 = parent_birth_estimate(1914, Gender.FEMALE, record_year=1914)
        godparent_1907 = adult_birth_window(1907, min_age=6)

        both_mothers = self._merge(mother_1911, mother_1914)
        self.assertEqual((both_mothers.date.year, both_mothers.date.end_year),
                         (1864, 1896))

        merged = self._merge(both_mothers, godparent_1907)
        self.assertEqual((merged.date.year, merged.date.end_year), (1864, 1896),
                         "the 54-year godparent window must not replace the "
                         "tighter parent estimate")

    def test_real_date_still_beats_an_adult_window(self):
        """Flagging the window synthetic must not let it outrank a real date."""
        from verso.core.targets.geni.date import GeniDate
        from verso.core.targets.geni.event import GeniEvent
        from verso.ru.targets.geni.translator.birth_estimates import adult_birth_window

        window = adult_birth_window(1838, min_age=17)
        real = GeniEvent(date=GeniDate(day=5, month=3, year=1819))
        for a, b in ((window, real), (real, window)):
            with self.subTest(order=(a is window)):
                merged = self._merge(a, b)
                self.assertEqual(merged.date.year, 1819)
                self.assertIsNone(merged.date.date_range)


class TestRelativeOfMotherAndWitness(unittest.TestCase):
    """`relationship_ref` values the allowlist blesses but the translator never
    wired: «мать» (the mother's own father or husband, in незаконнорождённые
    births) and «свидетель №N» (a marriage witness's relative). Without a union
    the relative is emitted as a profile with no edge to anyone."""

    def test_birth_father_of_mother_emits_parent_child_union(self):
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Заманиловка", "N", 1812,
            *[birth(66, Gender.MALE, 4, 7,
                    child=person("Иванъ"),
                    mother=person("Дарья", "Тимофеева"),
                    relatives=[Relative(person("Тимофей", "Петровъ"),
                                        Relationship.FATHER, "мать")],
                    b_month=Month.JUNE)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1812_birth.tf")
        self.assertIn(
            'resource "geni_union" "timofej_petrovich_and_darija_timofeevna_66_1812"',
            output)
        block = output.split('"timofej_petrovich_and_darija_timofeevna_66_1812"', 1)[1]
        block = block.split("}\n", 2)[0]
        self.assertIn("children = [", block)
        self.assertIn("mk_births_66_mother.id", block)

    def test_birth_husband_of_mother_emits_spouse_union(self):
        from verso.ru.relationship import Relationship, Relative
        records = birth_records(
            "A", "1", "1", "1", "Заманиловка", "N", 1814,
            *[birth(91, Gender.MALE, 14, 14,
                    child=person("Варлаамъ"),
                    mother=person("Анна", "Герасимова"),
                    relatives=[Relative(person("Яковъ", "Макаровъ"),
                                        Relationship.HUSBAND, "мать")],
                    b_month=Month.JUNE)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_birth_records(records)
        output = gen.get_output("mk_1814_birth.tf")
        self.assertIn(
            'resource "geni_union" "iakov_makarovich_and_anna_gerasimovna_91_1814"',
            output)
        block = output.split('"iakov_makarovich_and_anna_gerasimovna_91_1814"', 1)[1]
        block = block.split("}\n", 2)[0]
        self.assertNotIn("children = [", block)   # spouse pair, not parent→child

    def test_marriage_husband_of_witness_emits_spouse_union(self):
        from verso.ru.relationship import Relationship, Relative
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N", 1836,
            *[marriage(17, 12,
                       groom=person("Иванъ", "Мартыновъ"),
                       bride=person("Анфиса", "Иванова"),
                       witness6=person("Анна", "Лукина"),
                       relatives=[Relative(person("Тихонъ", "Ефимовъ"),
                                           Relationship.HUSBAND, "поручитель №6")],
                       w_month=Month.OCTOBER)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        output = gen.get_output("mk_1836_marriage.tf")
        self.assertIn("tihon_efimovich_and_anna_lukinichna", output)


class TestWitnessRefGenitive(unittest.TestCase):
    """The about line reads «{родство} {кого}», so the ref needs the genitive —
    and it has to agree with the witness's gender: a дьячок is the husband of a
    поручительницы, not of a «поручитель №6»."""

    def _about(self, witness_kwarg, relative_person, relationship):
        from verso.ru.relationship import Relative
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N", 1836,
            *[marriage(17, 12,
                       groom=person("Иванъ", "Мартыновъ"),
                       bride=person("Анфиса", "Иванова"),
                       relatives=[Relative(relative_person, relationship, "поручитель №6")],
                       w_month=Month.OCTOBER, **witness_kwarg)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        return gen.get_output("mk_1836_marriage.tf")

    def test_female_witness_takes_poruchitelnicy(self):
        from verso.ru.relationship import Relationship
        out = self._about({"witness6": person("Анна", "Лукина")},
                          person("Тихонъ", "Ефимовъ"), Relationship.HUSBAND)
        self.assertIn("муж поручительницы №6", out)
        self.assertNotIn("муж поручитель №6", out)

    def test_male_witness_takes_poruchitelja(self):
        from verso.ru.relationship import Relationship
        out = self._about({"witness6": person("Иванъ", "Петровъ")},
                          person("Петръ", "Сергеевъ"), Relationship.FATHER)
        self.assertIn("отец поручителя №6", out)

    def test_groom_and_bride_refs_are_unchanged(self):
        from verso.ru.relationship import Relationship, Relative
        records = marriage_records(
            "A", "1", "1", "1", "Горюхино", "N", 1836,
            *[marriage(17, 12,
                       groom=person("Иванъ", "Мартыновъ"),
                       bride=person("Анфиса", "Иванова"),
                       relatives=[Relative(person("Мартынъ", "Сергеевъ"),
                                           Relationship.FATHER, "жених")],
                       w_month=Month.OCTOBER)],
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_marriage_records(records)
        self.assertIn("отец жениха", gen.get_output("mk_1836_marriage.tf"))


class TestDepartureLineForMarriedOutBrides(unittest.TestCase):
    """The «Причина, основание убытия» column is rendered for any recorded
    departure, not only for death.

    It is a real column of the сказка, so surfacing it is faithful. The typed
    path used to be hardcoded to `умер` + a year, which left brides silent —
    and a «выдана замуж» member seldom carries a departure_year at all, so the
    year has to be optional or the line can never appear for them.
    """

    def _render(self, **kw):
        records = census_records(
            "A", "1", "1", "1", "Горюхино", 1795,
            household(None,
                      member(1, person("Тимон", "Макаров"), CensusRole.HEAD, age=50),
                      member(2, person("Марфа"), CensusRole.DAUGHTER, ref_member=1, **kw)),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_census_records(records)
        return gen.get_output("rs_1795_1.tf")

    @staticmethod
    def _profile_block(out, name_fragment):
        """Just the geni_profile resource — the document renders the same label
        from a DIFFERENT method, so asserting on the whole file proves nothing
        about the profile's about section."""
        m = re.search(rf'resource "geni_profile" "[^"]*{name_fragment}[^"]*" \{{(.*?)\n\}}',
                      out, re.S)
        assert m, f"no geni_profile matching {name_fragment}"
        return m.group(1)

    def test_married_out_bride_without_year(self):
        out = self._render(previous_age=15, destination="Пепелищи",
                           departure_reason="выдана замуж")
        block = self._profile_block(out, "marfa")
        self.assertIn("Причина, основание убытия: выдана замуж", block)
        self.assertNotIn("выдана замуж (", block)

    def test_married_out_bride_with_year_keeps_the_parenthetical(self):
        out = self._render(previous_age=15, destination="Пепелищи",
                           departure_reason="выдана замуж", departure_year=1787)
        self.assertIn("Причина, основание убытия: выдана замуж (1787)",
                      self._profile_block(out, "marfa"))

    def test_recruit_departure_also_rendered(self):
        out = self._render(previous_age=15, departure_reason="отдан в рекруты",
                           departure_year=1789)
        self.assertIn("Причина, основание убытия: отдан в рекруты (1789)",
                      self._profile_block(out, "marfa"))

    def test_death_line_unchanged(self):
        out = self._render(previous_age=40, departure_reason="умер", departure_year=1785)
        self.assertIn("Причина, основание убытия: умер (1785)",
                      self._profile_block(out, "marfa"))

    def test_living_member_has_no_departure_line(self):
        out = self._render(age=15, previous_age=2)
        self.assertNotIn("Причина, основание убытия", self._profile_block(out, "marfa"))


class TestHouseholdUnionWiring(unittest.TestCase):
    """Two ways a household member's union used to go missing."""

    @staticmethod
    def _tf(*households):
        records = census_records("A", "1", "1", "1", "V", 1858, *households)
        gen = TerraformGenerator()
        gen.add_census_records(records)
        return "".join(gen._outputs.values())

    def test_child_with_ref_member_at_the_head_lands_in_the_head_union(self):
        """`SON, ref_member=<head>` says exactly what an unset ref_member says.

        Before, the head+wife pass skipped ANY explicit ref_member as "points
        at an intermediate parent", so such a child was emitted attached to no
        union at all.
        """
        tf = self._tf(*page("1", household(
            "5",
            member(1, person("Иванъ", "Макаровъ"), CensusRole.HEAD, age=78),
            member(2, person("Параскева", "Власова"), CensusRole.WIFE, age=74),
            member(3, person("Григорій"), CensusRole.SON, ref_member=1, age=54),
        )))
        union = re.search(
            r'resource "geni_union" "ioann_makarovich_rs1_1858" \{(.*?)\n\}',
            tf, re.S)
        self.assertIsNotNone(union)
        self.assertIn("grigorij_ivanovich", union.group(1))

    def test_secondary_marriage_and_subfamily_merge_into_one_union(self):
        """One res_name, one `resource` block.

        The secondary-relationship pass keys the marital union on the husband,
        and so does the sub-family pass that collects his children. Emitting
        both appended two `resource "geni_union"` blocks under a single name —
        a terraform duplicate.
        """
        tf = self._tf(*page("1", household(
            "5",
            member(1, person("Иванъ", "Макаровъ"), CensusRole.HEAD, age=78),
            member(2, person("Параскева", "Власова"), CensusRole.WIFE, age=74),
            member(3, person("Дарья", "Герасимова"), CensusRole.DAUGHTER_IN_LAW,
                   ref_member=1, age=34,
                   secondary_role=CensusRole.WIFE, secondary_ref_member=5),
            member(4, person("Яковъ"), CensusRole.SON, ref_member=5, age=15),
            member(5, person("Максимъ", "Ивановъ"), CensusRole.SON,
                   ref_member=1, hidden=True),
        )))
        names = re.findall(r'resource "geni_union" "([^"]+)"', tf)
        self.assertEqual(len(names), len(set(names)), f"duplicate union: {names}")
        union = re.search(
            r'resource "geni_union" "maksim_ivanovich_rs5-5_1858" \{(.*?)\n\}',
            tf, re.S)
        self.assertIsNotNone(union, names)
        body = union.group(1)
        # Both halves survived the merge: the marriage AND the children.
        self.assertIn("darija_gerasimovna", body)
        self.assertIn("iakov_maksimovich", body)


class TestUnionKindIsItsOrigin(unittest.TestCase):
    """The union consolidation asks a union which record made it
    (`GeniUnion.origin`) rather than reading that off the res_name, which a
    record number with a letter in it, or none at all, defeated."""

    def _spouse_after(self, name: str, origin: UnionOrigin | None) -> str | None:
        """A father's single-partner bucket, then a union naming his wife:
        does the wife reach the bucket?"""
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="head__1_1810", origin=UnionOrigin.BIRTH,
            partner_1="head", partner_2=None, children={"kid"}))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name=name, origin=origin, partner_1="head", partner_2="wife"))
        (bucket,) = gen._consolidated_unions.values()
        return bucket.partner_2

    def test_a_real_spouse_whatever_the_name(self):
        for name, origin in (
                ("head_and_wife_mnone_1864", UnionOrigin.MARRIAGE),  # entered without a number
                ("head_rs1a-11_1816", UnionOrigin.ROLL),             # household «1а»
                ("head_and_wife__7_1897", UnionOrigin.ROLL)):        # a head's second wife
            with self.subTest(name):
                self.assertEqual("wife", self._spouse_after(name, origin))

    def test_a_godparent_beside_the_father_is_no_spouse(self):
        self.assertIsNone(self._spouse_after("head_and_godmother_5_1822", None))

    def test_a_fatherless_birth_numbered_with_a_letter_stays_apart(self):
        """Глуповы Горы numbers its births «м68», «ж27»."""
        from verso.core.targets.geni.union import GeniUnion

        gen = TerraformGenerator(village_dir=None)
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="husband_and_wife_m1_1890", origin=UnionOrigin.MARRIAGE,
            partner_1="husband", partner_2="wife"))
        gen._add_to_consolidated_unions(GeniUnion(
            res_name="and_wife_zh27_1899", origin=UnionOrigin.BIRTH,
            partner_1=None, partner_2="wife", children={"illegit_child"}))
        self.assertNotIn("illegit_child",
                         gen._consolidated_unions["husband_and_wife"].children)
        self.assertIn("illegit_child", gen._consolidated_unions["wife"].children)
