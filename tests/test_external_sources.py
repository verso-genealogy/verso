import unittest
from calendar import Month

from verso.ru.domain import EventDate, Gender, person
from verso.ru.dsl.records.external_sources import (
    ExternalSourceKind, ExternalSourceRecord, ExternalSourceRecords, SourceCitation, WwiDocumentType, WwiiDocumentType, criminal_record, external_source_records, wwi_record, wwii_record)


class TestWwiDocumentType(unittest.TestCase):
    def test_value_is_verbatim_gwar_label(self):
        self.assertEqual(
            WwiDocumentType.CASUALTY_CARD_LOWER.value,
            "Карточка на выбывших (нижние чины)",
        )
        self.assertEqual(WwiDocumentType.AWARD_LISTS.value, "Списки награжденных")

    def test_covers_every_label_present_in_committed_data(self):
        # The eight distinct «Тип документа» strings used across the Горюхино
        # and Нижняя Яичница wwi_record() data must all have an enum member.
        labels = {m.value for m in WwiDocumentType}
        for expected in (
            "Именные списки потерь",
            "Карточка на выбывших (нижние чины)",
            "Уведомление о приеме раненого",
            "Карточка на прибывших (высшие чины)",
            "Карточка на прибывших (нижние чины)",
            "Списки награжденных",
            "Отчетно-осведомительные карточки",
            "Карточки военнопленных",
        ):
            self.assertIn(expected, labels)

    def test_only_award_lists_is_award(self):
        self.assertTrue(WwiDocumentType.AWARD_LISTS.is_award)
        for m in WwiDocumentType:
            if m is not WwiDocumentType.AWARD_LISTS:
                self.assertFalse(m.is_award, f"{m} should not be an award type")


class TestCriminalRecord(unittest.TestCase):
    def _rec(self) -> ExternalSourceRecord:
        return criminal_record(
            person("Тимоѳей", "Лукинъ", "Индюшевъ",
                   name_modern_orth="Тимофей",
                   last_name_modern_orth="Индюшев"),
            source_url="https://familio.org/catalogs/vss/persons/00000000-0000-4000-8000-8a0a20497177",
            original_text="4711. ИНДЮШЕВ, Тимофей Лукин. Кр. Глухоман. у., ... в тюрьму на 4 м. Исп. 17 Марта 1888 г.",
            birth_year=1851,
            date=EventDate(1888, Month.MARCH, 17),
            page="45",
            record_number=4711,
            age=37,
        )

    def test_kind_and_citation(self):
        r = self._rec()
        self.assertEqual(r.kind, ExternalSourceKind.CRIMINAL)
        self.assertEqual(r.page, "45")
        self.assertEqual(r.record_number, 4711)
        self.assertEqual(r.age, 37)
        self.assertIsInstance(r.citation, SourceCitation)
        self.assertIn("vss/persons", r.citation.source_url)
        self.assertIn("4711", r.citation.original_text or "")
        self.assertEqual(r.citation.catalog, "Ведомости справок о судимости 1870–1927")
        self.assertEqual(r.birth_year, 1851)
        self.assertEqual(r.event_year, 1888)
        self.assertEqual(r.event_month, Month.MARCH)

    def test_default_label_is_other(self):
        self.assertEqual(self._rec().labels, ["Other"])

    def test_gender_inferred_from_name(self):
        self.assertEqual(self._rec().person.gender, Gender.MALE)


class TestWwiRecord(unittest.TestCase):
    def _rec(self) -> ExternalSourceRecord:
        return wwi_record(
            person("Тимоѳей", "Павловъ", "Добчинскій",
                   name_modern_orth="Тимофей",
                   last_name_modern_orth="Добчинский"),
            source_url="https://gwar.mil.ru/heroes/chelovek_x1/",
            date=EventDate(1915),
        )

    def test_kind_and_military_label(self):
        r = self._rec()
        self.assertEqual(r.kind, ExternalSourceKind.WWI)
        self.assertEqual(r.labels, ["Military"])
        self.assertIn("gwar.mil.ru", r.citation.source_url)
        self.assertEqual(
            r.citation.catalog,
            "Списки участников Первой мировой войны "
            "(проект Памяти героев Великой войны 1914–1918)",
        )

    def test_card_fields_stored(self):
        r = wwi_record(
            person("Иван", "Васильевъ", name_modern_orth="Иван"),
            source_url="https://gwar.mil.ru/heroes/chelovek_x/",
            rank="ст. унтер-офицер",
            military_unit="Захолустинская команда выздоравливающих",
            casualty_reason="болен",
            document_type=WwiDocumentType.ARRIVAL_CARD_HIGHER,
            archive="РГВИА",
            fund="Картотека бюро учёта потерь",
            archive_location="Шкаф б/н, ящик 12-Б",
        )
        self.assertEqual(r.rank, "ст. унтер-офицер")
        self.assertEqual(r.military_unit, "Захолустинская команда выздоравливающих")
        self.assertEqual(r.casualty_reason, "болен")
        self.assertEqual(r.document_type, WwiDocumentType.ARRIVAL_CARD_HIGHER)
        self.assertEqual(r.citation.archive, "РГВИА")
        self.assertEqual(r.citation.fund, "Картотека бюро учёта потерь")
        self.assertEqual(r.citation.archive_location, "Шкаф б/н, ящик 12-Б")

    def test_award_fields_stored(self):
        r = wwi_record(
            person("Иван", "Васильевъ", name_modern_orth="Иван"),
            source_url="https://gwar.mil.ru/heroes/chelovek_x/",
            document_type=WwiDocumentType.AWARD_LISTS,
            award="Георгиевский крест IV-й степени",
            award_number=400123,
        )
        self.assertEqual(r.award, "Георгиевский крест IV-й степени")
        self.assertEqual(r.award_number, 400123)

    def test_casualty_fields_stored(self):
        r = wwi_record(
            person("Иван", "Васильевъ", name_modern_orth="Иван"),
            source_url="https://gwar.mil.ru/heroes/chelovek_x/",
            document_type=WwiDocumentType.WOUNDED_NOTICE,
            casualty_reason="ранен",
            marital_status="женат",
            place_of_casualty="у д. Глуховка",
            casualty_date=EventDate(1915, Month.JUNE, 11),
        )
        self.assertEqual(r.marital_status, "женат")
        self.assertEqual(r.place_of_casualty, "у д. Глуховка")
        self.assertEqual(r.casualty_date.year, 1915)

    def test_occupation_carried_on_person(self):
        r = wwi_record(
            person("Иван", "Васильевъ", name_modern_orth="Иван",
                   occupation="хлебопашец"),
            source_url="https://gwar.mil.ru/heroes/chelovek_x/",
        )
        self.assertEqual(r.person.occupation, "хлебопашец")


class TestWwiiDocumentType(unittest.TestCase):
    def test_value_is_verbatim_pamyat_naroda_label(self):
        self.assertEqual(WwiiDocumentType.NAGRADNOY_LIST.value, "Наградной лист")
        self.assertEqual(
            WwiiDocumentType.CASUALTY_REPORT.value,
            "Донесение о безвозвратных потерях",
        )

    def test_covers_every_expected_label(self):
        labels = {m.value for m in WwiiDocumentType}
        for expected in (
            "Наградной лист",
            "Приказ (указ) о награждении",
            "Юбилейная картотека награждений",
            "Донесение о безвозвратных потерях",
            "Книга памяти",
            "Учётно-послужная картотека",
            "Картотека военнопленных",
            "Картотека награждений",
            "Документ, уточняющий потери",
            "Картотека ранений",
            "Военно-пересыльные пункты и запасные полки",
            "Именной список части",
        ):
            self.assertIn(expected, labels)

    def test_only_the_award_members_are_award(self):
        award_members = {
            WwiiDocumentType.NAGRADNOY_LIST,
            WwiiDocumentType.AWARD_ORDER,
            WwiiDocumentType.ANNIVERSARY_AWARD,
            WwiiDocumentType.AWARD_CARD,
        }
        for m in WwiiDocumentType:
            self.assertEqual(m.is_award, m in award_members,
                              f"{m} is_award mismatch")


class TestWwiiRecord(unittest.TestCase):
    def _rec(self) -> ExternalSourceRecord:
        return wwii_record(
            person("Иванъ", "Петровъ", "Сидоровъ",
                   name_modern_orth="Иван", last_name_modern_orth="Сидоров"),
            source_url="https://pamyat-naroda.ru/heroes/person123/",
            date=EventDate(1943, Month.MAY, 9),
        )

    def test_kind_and_military_label(self):
        r = self._rec()
        self.assertEqual(r.kind, ExternalSourceKind.WWII)
        self.assertEqual(r.labels, ["Military"])
        self.assertIn("pamyat-naroda.ru", r.citation.source_url)
        self.assertEqual(
            r.citation.catalog, "Память народа (проект Минобороны РФ)"
        )

    def test_gender_inferred_from_name(self):
        self.assertEqual(self._rec().person.gender, Gender.MALE)

    def test_card_fields_stored(self):
        r = wwii_record(
            person("Иванъ", "Петровъ", name_modern_orth="Иван"),
            source_url="https://pamyat-naroda.ru/heroes/person456/",
            rank="сержант",
            military_unit="123-й стрелковый полк",
            document_type=WwiiDocumentType.NAGRADNOY_LIST,
            award="Орден Красной Звезды",
            award_number="45/н",
            draft_board="Глухоманский РВК",
            draft_date=EventDate(1941, Month.JUNE, 23),
            feat_date=EventDate(1943, Month.AUGUST, 5),
        )
        self.assertEqual(r.rank, "сержант")
        self.assertEqual(r.military_unit, "123-й стрелковый полк")
        self.assertEqual(r.document_type, WwiiDocumentType.NAGRADNOY_LIST)
        self.assertEqual(r.award, "Орден Красной Звезды")
        self.assertEqual(r.award_number, "45/н")
        self.assertEqual(r.draft_board, "Глухоманский РВК")
        self.assertEqual(r.draft_date.year, 1941)
        self.assertEqual(r.feat_date.year, 1943)

    def test_birth_date_stored(self):
        # wwii_record takes a full birth_date (EventDate), not a bare birth_year.
        r = wwii_record(
            person("Иванъ", "Петровъ", name_modern_orth="Иван"),
            source_url="https://pamyat-naroda.ru/heroes/person789/",
            birth_date=EventDate(1909, Month.NOVEMBER, 3),
        )
        self.assertEqual(r.birth_date.year, 1909)
        self.assertEqual(r.birth_date.month, Month.NOVEMBER)
        self.assertEqual(r.birth_date.day, 3)

    def test_year_only_birth_date(self):
        r = wwii_record(
            person("Иванъ", "Петровъ", name_modern_orth="Иван"),
            source_url="https://pamyat-naroda.ru/heroes/person789/",
            birth_date=EventDate(1923),
        )
        self.assertEqual(r.birth_date.year, 1923)
        self.assertIsNone(r.birth_date.day)

    def test_scan_file_accepts_list(self):
        # A record can carry several scans (приказ + наградной лист pages).
        r = wwii_record(
            person("Иванъ", "Петровъ", name_modern_orth="Иван"),
            source_url="https://pamyat-naroda.ru/heroes/person789/",
            scan_file=["scans/a.jpg", "scans/b.jpg"],
        )
        self.assertEqual(r.citation.scan_files, ["scans/a.jpg", "scans/b.jpg"])

    def test_scan_file_single_str_normalizes_to_list(self):
        r = wwii_record(
            person("Иванъ", "Петровъ", name_modern_orth="Иван"),
            source_url="https://pamyat-naroda.ru/heroes/person789/",
            scan_file="scans/a.jpg",
        )
        self.assertEqual(r.citation.scan_files, ["scans/a.jpg"])


class TestDocumentResourceSourceUrl(unittest.TestCase):
    def _doc(self, text="body", date_year: int | None = 1888, **kw):
        from verso.ru.targets.geni.translator.resources import _document_resource
        return _document_resource(
            res_name="d", title="T", description="desc", text=text,
            date_day=None, date_month=None, date_year=date_year,
            labels=["Other"], location=None, profiles=["p"], projects=[],
            **kw,
        )

    def test_emits_source_url_and_content_type_when_set(self):
        out = self._doc(source_url="https://example.org/x", content_type="text/html")
        self.assertIn('source_url   = "https://example.org/x"', out)
        self.assertIn('content_type = "text/html"', out)

    def test_omits_them_when_unset(self):
        out = self._doc()
        self.assertNotIn("source_url", out)
        self.assertNotIn("content_type", out)

    def test_omits_text_block_when_text_empty(self):
        # A source_url document must not also emit `text` (ExactlyOneOf).
        out = self._doc(source_url="https://example.org/x", content_type="text/html", text="")
        self.assertNotIn("text        = <<-EOT", out)

    def test_keeps_text_block_when_text_present(self):
        self.assertIn("text        = <<-EOT", self._doc())

    def test_omits_date_block_when_no_date(self):
        out = self._doc(text="", source_url="https://x/y", content_type="text/html",
                        date_year=None)
        self.assertNotIn("date = {", out)

    def test_keeps_date_block_when_year_present(self):
        self.assertIn("date = {", self._doc())

    def test_emits_file_block_for_scan(self):
        out = self._doc(text="", file="scans/x.jpg", file_name="x.jpg",
                        content_type="image/jpg")
        self.assertIn('file         = filebase64("${path.module}/scans/x.jpg")', out)
        self.assertIn('file_name    = "x.jpg"', out)
        self.assertIn('content_type = "image/jpg"', out)

    def test_file_excludes_source_url_and_text(self):
        # ExactlyOneOf: a file upload suppresses both source_url and the text
        # heredoc even when they are passed in.
        out = self._doc(text="body", file="scans/x.jpg", file_name="x.jpg",
                        content_type="image/jpg", source_url="https://x/y")
        self.assertNotIn("source_url", out)
        self.assertNotIn("text        = <<-EOT", out)


class TestTranslatorEmission(unittest.TestCase):
    def _gen_output(self, consolidation=None):
        from verso.ru.targets.geni.translator import TerraformGenerator
        recs = external_source_records(
            "Нижняя Яичница",
            criminal_record(
                person("Тимоѳей", "Лукинъ", "Индюшевъ",
                       name_modern_orth="Тимофей", last_name_modern_orth="Индюшев",
                       residence="Нижняя Яичница"),
                source_url="https://familio.org/catalogs/vss/persons/a1b2c3d4",
                original_text="4711. ИНДЮШЕВ, Тимофей Лукин ... Исп. 17 Марта 1888 г.",
                bibliography="Ведомость справок о судимости. 1889, кн. 3, ч. 2. С. 45.",
                birth_year=1851,
                date=EventDate(1888, Month.MARCH, 17),
                page="45",
                record_number=4711,
                age=37,
            ),
        )
        gen = TerraformGenerator(village_dir=None, consolidation=consolidation)
        gen.add_external_source_records(recs)
        return gen, gen.get_output("ext_1888.tf")

    def test_emits_profile_and_document_with_source_url(self):
        _, out = self._gen_output()
        self.assertIn('resource "geni_profile"', out)
        self.assertIn('resource "geni_document"', out)
        self.assertIn('source_url   = "https://familio.org/catalogs/vss/persons/a1b2c3d4"', out)
        self.assertIn('content_type = "text/html"', out)
        self.assertIn('"Other"', out)        # судимость label
        self.assertIn("4711", out)          # transcription in description
        # No `text` heredoc (ExactlyOneOf with source_url)
        self.assertNotIn("text        = <<-EOT", out)

    def test_description_carries_bibliography_and_record_fields(self):
        _, out = self._gen_output()
        # судимость layout: Источник directly under the catalog header, then
        # № записи / Страница, then Имя / Возраст / Дата события.
        self.assertIn("Источник: Ведомость справок о судимости. 1889", out)
        self.assertIn("№ записи: 4711", out)
        self.assertIn("Страница: 45", out)
        self.assertIn("Имя: Тимофей Лукич Индюшев", out)
        self.assertIn("Возраст: 37", out)
        self.assertIn("Дата события: 17.3.1888", out)
        # No separate "Скан:" line — the source page is the doc's source_url.
        self.assertNotIn("Скан:", out)

    def test_place_derived_from_locations_helper_not_freetext(self):
        # No geography field; place comes from the corpus's places via location_label —
        # rendered into the structured current_residence/location blocks (the
        # «Место:» free-text line was dropped from the about).
        _, out = self._gen_output()
        self.assertIn('city    = "село Нижняя Яичница"', out)
        self.assertIn('county  = "Глухоманский уезд"', out)
        self.assertNotIn("География", out)

    def _minted_res_name(self, out: str) -> str:
        import re
        m = re.search(r'resource "geni_profile" "([^"]+)"', out)
        assert m is not None, "no geni_profile emitted"
        return m.group(1)

    def test_document_links_to_minted_profile(self):
        _, out = self._gen_output()
        # The minted profile res_name appears both as the profile resource and
        # in the document's profiles list.
        res_name = self._minted_res_name(out)
        self.assertIn(f"geni_profile.{res_name}.id", out)

    def test_res_name_uses_record_number_as_key(self):
        # record_number (4711) becomes the res_name index (no manual record_num).
        _, out = self._gen_output()
        self.assertIn("4711", self._minted_res_name(out))

    def test_birth_year_derived_from_age_when_not_given(self):
        from verso.ru.targets.geni.translator import TerraformGenerator
        recs = external_source_records(
            "Нижняя Яичница",
            criminal_record(
                person("Тимоѳей", "Лукинъ", "Индюшевъ",
                       name_modern_orth="Тимофей", last_name_modern_orth="Индюшев",
                       residence="Нижняя Яичница"),
                source_url="https://familio.org/catalogs/vss/persons/x",
                original_text="4711. …",
                age=37,
                date=EventDate(1888, Month.MARCH, 17),
                record_number=4711,
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_external_source_records(recs)
        out = gen.get_output("ext_1888.tf")
        # 1888 − 37 = 1851 → the circa birth event (no longer shown in the
        # судимость description, which dropped Год рождения).
        self.assertIn("year  = 1851", out)

    def test_wwi_scan_file_emits_file_upload(self):
        from verso.ru.targets.geni.translator import TerraformGenerator
        recs = external_source_records(
            "Нижняя Яичница",
            wwi_record(
                person("Иванъ", "Васильевъ", "Индюшевъ", residence="Нижняя Яичница"),
                source_url="https://gwar.mil.ru/heroes/chelovek_x2/",
                scan_file="scans/wwi_ivan_indjushev_1914.jpg",
                scan_content_type="image/jpg",
                date=EventDate(1914, Month.NOVEMBER, 21),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_external_source_records(recs)
        out = gen.get_output("ext_1914.tf")
        # The document body is the uploaded scan (file/file_name/content_type)…
        self.assertIn(
            'file         = filebase64("${path.module}/scans/wwi_ivan_indjushev_1914.jpg")',
            out)
        self.assertIn('file_name    = "wwi_ivan_indjushev_1914.jpg"', out)
        self.assertIn('content_type = "image/jpg"', out)
        # …not source_url (ExactlyOneOf); the gwar page URL moves into the
        # description as a provenance line.
        self.assertNotIn("source_url   =", out)
        self.assertIn(
            "Онлайн-просмотр: https://gwar.mil.ru/heroes/chelovek_x2/", out)

    def test_document_profiles_follow_consolidation_redirect(self):
        from verso.ru.targets.geni.translator import Consolidation
        # First find the minted res_name with no consolidation.
        _, out0 = self._gen_output()
        stub = self._minted_res_name(out0)
        cons = Consolidation(profile_move_list={stub: "timofej_lukich_indjushev"})
        _, out = self._gen_output(consolidation=cons)
        self.assertIn("geni_profile.timofej_lukich_indjushev.id", out)


class TestLocationLabel(unittest.TestCase):
    def test_known_place_renders_full_hierarchy(self):
        from verso.ru.targets.geni.translator.res_names import location_label
        self.assertEqual(
            location_label("Нижняя Яичница"),
            "село Нижняя Яичница, Глухоманский уезд, "
            "Захолустинская губерния, Россия",
        )

    def test_unknown_place_returns_none(self):
        from verso.ru.targets.geni.translator.res_names import location_label
        self.assertIsNone(location_label("Нету Такого Места"))
        self.assertIsNone(location_label(None))


class TestEsc001Linter(unittest.TestCase):
    def _lint(self, code: str):
        import ast
        import tempfile
        from pathlib import Path
        from verso.ru.linters.checks.external_sources import check_file_structured
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as f:
            f.write(code)
            p = Path(f.name)
        ast.parse(code)  # sanity
        return check_file_structured(p)

    def test_flags_gwar_url_on_criminal_record(self):
        issues = self._lint(
            'criminal_record(person("Иван"), source_url="https://gwar.mil.ru/x",'
            ' original_text="t", birth_year=1850, record_num=1)'
        )
        self.assertTrue(any("ESC001" in i["message"] for i in issues))

    def test_flags_vss_url_on_wwi_record(self):
        issues = self._lint(
            'wwi_record(person("Иван"),'
            ' source_url="https://familio.org/catalogs/vss/persons/x", record_num=1)'
        )
        self.assertTrue(any("ESC001" in i["message"] for i in issues))

    def test_accepts_rsl_viewer_url_on_criminal_record(self):
        # Record-only vss entries have no Familio person page, so the RSL viewer
        # link (where the scan is re-hosted from) is the canonical proof URL.
        issues = self._lint(
            'criminal_record(person("Иван"),'
            ' source_url="https://viewer.rsl.ru/ru/rsl01001234567?page=12",'
            ' original_text="4712. ...", birth_year=1844, record_num=1)'
        )
        self.assertEqual(issues, [])

    def test_esc001_message_lists_both_accepted_hosts(self):
        issues = self._lint(
            'criminal_record(person("Иван"), source_url="https://gwar.mil.ru/x",'
            ' original_text="t", birth_year=1850, record_num=1)'
        )
        msg = next(i["message"] for i in issues if "ESC001" in i["message"])
        self.assertIn("familio.org/catalogs/vss", msg)
        self.assertIn("viewer.rsl.ru", msg)

    def test_flags_empty_original_text(self):
        issues = self._lint(
            'criminal_record(person("Иван"),'
            ' source_url="https://familio.org/catalogs/vss/persons/x",'
            ' original_text="  ", birth_year=1850, record_num=1)'
        )
        self.assertTrue(any("ESC002" in i["message"] for i in issues))

    def test_clean_records_pass(self):
        issues = self._lint(
            'criminal_record(person("Иван"),'
            ' source_url="https://familio.org/catalogs/vss/persons/x",'
            ' original_text="4711. ...", birth_year=1850, record_num=1)\n'
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x", record_num=2)'
        )
        self.assertEqual(issues, [])

    def test_flags_casualty_reason_on_award_document(self):
        issues = self._lint(
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' document_type=WwiDocumentType.AWARD_LISTS, casualty_reason="ранен")'
        )
        self.assertTrue(any("ESC003" in i["message"] for i in issues))

    def test_award_document_without_casualty_reason_passes(self):
        issues = self._lint(
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' document_type=WwiDocumentType.AWARD_LISTS)'
        )
        self.assertFalse(any("ESC003" in i["message"] for i in issues))

    def test_casualty_reason_on_casualty_document_passes(self):
        issues = self._lint(
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' document_type=WwiDocumentType.CASUALTY_CARD_LOWER, casualty_reason="убит")'
        )
        self.assertFalse(any("ESC003" in i["message"] for i in issues))

    def test_flags_award_on_non_award_document(self):
        issues = self._lint(
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' document_type=WwiDocumentType.CASUALTY_CARD_LOWER,'
            ' award="Георгиевский крест IV-й степени")'
        )
        self.assertTrue(any("ESC004" in i["message"] for i in issues))

    def test_flags_award_number_without_document_type(self):
        issues = self._lint(
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' award_number=400123)'
        )
        self.assertTrue(any("ESC004" in i["message"] for i in issues))

    def test_award_fields_on_award_document_pass(self):
        issues = self._lint(
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' document_type=WwiDocumentType.AWARD_LISTS,'
            ' award="Георгиевский крест IV-й степени", award_number=400123)'
        )
        self.assertFalse(any("ESC004" in i["message"] for i in issues))

    def test_award_none_on_non_award_document_passes(self):
        # award=None is "unset" — must not trip ESC004.
        issues = self._lint(
            'wwi_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' document_type=WwiDocumentType.CASUALTY_CARD_LOWER, award=None)'
        )
        self.assertFalse(any("ESC004" in i["message"] for i in issues))

    def test_flags_gwar_url_on_wwii_record(self):
        issues = self._lint(
            'wwii_record(person("Иван"), source_url="https://gwar.mil.ru/heroes/x",'
            ' record_num=1)'
        )
        self.assertTrue(any("ESC001" in i["message"] for i in issues))

    def test_accepts_pamyat_naroda_url_on_wwii_record(self):
        issues = self._lint(
            'wwii_record(person("Иван"),'
            ' source_url="https://pamyat-naroda.ru/heroes/person123/", record_num=1)'
        )
        self.assertEqual(issues, [])

    def test_accepts_podvignaroda_url_on_wwii_record(self):
        issues = self._lint(
            'wwii_record(person("Иван"),'
            ' source_url="https://podvignaroda.ru/?id=verify1_a1", record_num=1)'
        )
        self.assertEqual(issues, [])

    def test_flags_award_on_non_award_wwii_document(self):
        issues = self._lint(
            'wwii_record(person("Иван"), source_url="https://pamyat-naroda.ru/heroes/x",'
            ' document_type=WwiiDocumentType.CASUALTY_REPORT,'
            ' award="Орден Красной Звезды")'
        )
        self.assertTrue(any("ESC004" in i["message"] for i in issues))

    def test_award_fields_on_award_wwii_document_pass(self):
        issues = self._lint(
            'wwii_record(person("Иван"), source_url="https://pamyat-naroda.ru/heroes/x",'
            ' document_type=WwiiDocumentType.NAGRADNOY_LIST,'
            ' award="Орден Красной Звезды", award_number="45/н")'
        )
        self.assertFalse(any("ESC004" in i["message"] for i in issues))


class TestContainer(unittest.TestCase):
    def test_factory_collects_records_and_village(self):
        recs = external_source_records(
            "Нижняя Яичница",
            wwi_record(person("Иван", "Васильевъ", name_modern_orth="Иван"),
                       source_url="https://gwar.mil.ru/heroes/chelovek_x/"),
        )
        self.assertIsInstance(recs, ExternalSourceRecords)
        self.assertEqual(recs.village, "Нижняя Яичница")
        self.assertEqual(len(recs.records), 1)
        # factory assigns a 1-based positional index for res_name fallback
        self.assertEqual(recs.records[0].index, 1)
        self.assertEqual(recs.records[0].res_key, 1)


class TestWwiTranslatorEmission(unittest.TestCase):
    def _out(self, **card):
        from verso.ru.targets.geni.translator import TerraformGenerator
        recs = external_source_records(
            "Нижняя Яичница",
            wwi_record(
                person("Иван", "Васильевъ", name_modern_orth="Иван",
                       residence="Нижняя Яичница"),
                source_url="https://gwar.mil.ru/heroes/chelovek_x/",
                **card,
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_external_source_records(recs)
        ev = card.get("date")
        year = ev.year if ev else None
        return gen.get_output(f"ext_{year if year else 'undated'}.tf")

    def test_card_fields_render_in_description(self):
        out = self._out(
            date=EventDate(1917, Month.SEPTEMBER, 11),
            rank="ст. унтер-офицер",
            military_unit="Захолустинская команда выздоравливающих",
            casualty_reason="болен",
            document_type=WwiDocumentType.ARRIVAL_CARD_HIGHER,
            archive="РГВИА", fund="Картотека бюро учёта потерь",
            inventory="Оп. 1", case="Д. 43",
        )
        self.assertIn("Звание: ст. унтер-офицер", out)
        self.assertIn("Воинская часть: Захолустинская команда выздоравливающих", out)
        self.assertIn("Причина выбытия: болен", out)
        self.assertIn("Тип документа: Карточка на прибывших (высшие чины)", out)
        self.assertIn("Архив: РГВИА", out)
        self.assertIn("Фонд: Картотека бюро учёта потерь", out)
        self.assertIn("Опись: Оп. 1", out)
        self.assertIn("Дело: Д. 43", out)

    def test_non_fatal_casualty_no_death_event(self):
        out = self._out(date=EventDate(1917, Month.SEPTEMBER, 11),
                        casualty_reason="болен")
        self.assertNotIn("death = {", out)

    def test_fatal_casualty_emits_death_event(self):
        out = self._out(date=EventDate(1916, Month.JUNE, 5),
                        casualty_reason="убит")
        self.assertIn("death = {", out)
        self.assertIn('cause_of_death = "убит"', out)
        self.assertIn("year  = 1916", out)

    def test_fatal_from_wounds_uses_wounds_cause(self):
        out = self._out(date=EventDate(1916, Month.JUNE, 5),
                        casualty_reason="умер от ран")
        self.assertIn("death = {", out)
        self.assertIn('cause_of_death = "от ран"', out)

    def test_fatal_with_ranged_event_renders_range_on_death(self):
        out = self._out(
            date=EventDate(1916, Month.JUNE, 5, day_end=7, month_end=Month.JUNE),
            casualty_reason="убит",
        )
        self.assertIn("death = {", out)
        self.assertIn('range', out)
        self.assertIn("end_day", out)

    def test_award_fields_render_in_description(self):
        out = self._out(
            date=EventDate(1915, Month.AUGUST, 28),
            document_type=WwiDocumentType.AWARD_LISTS,
            award="Георгиевский крест IV-й степени",
            award_number=400123,
        )
        self.assertIn("Награда: Георгиевский крест IV-й степени", out)
        self.assertIn("Номер награждения: 400123", out)

    def test_casualty_fields_render_in_description(self):
        out = self._out(
            date=EventDate(1915, Month.JUNE, 14),
            document_type=WwiDocumentType.WOUNDED_NOTICE,
            casualty_reason="ранен",
            marital_status="женат",
            place_of_casualty="у д. Кривушино",
            casualty_date=EventDate(1915, Month.JUNE, 9),
        )
        self.assertIn("Семейное положение: женат", out)
        self.assertIn("Место выбытия: у д. Кривушино", out)
        self.assertIn("Дата выбытия:", out)
        # «Место выбытия» is distinct from the residence-derived «Место:» line.
        self.assertIn("Место: ", out)

    def test_occupation_renders_as_profile_attribute(self):
        from verso.ru.targets.geni.translator import TerraformGenerator
        recs = external_source_records(
            "Нижняя Яичница",
            wwi_record(
                person("Иван", "Васильевъ", name_modern_orth="Иван",
                       residence="Нижняя Яичница", occupation="хлебопашец"),
                source_url="https://gwar.mil.ru/heroes/chelovek_x/",
                date=EventDate(1915),
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_external_source_records(recs)
        out = gen.get_output("ext_1915.tf")
        self.assertIn('occupation = "хлебопашец"', out)


class TestWwiiTranslatorEmission(unittest.TestCase):
    def _out(self, **card):
        from verso.ru.targets.geni.translator import TerraformGenerator
        recs = external_source_records(
            "Нижняя Яичница",
            wwii_record(
                person("Иван", "Петровъ", name_modern_orth="Иван",
                       residence="Нижняя Яичница"),
                source_url="https://pamyat-naroda.ru/heroes/person789/",
                **card,
            ),
        )
        gen = TerraformGenerator(village_dir=None)
        gen.add_external_source_records(recs)
        ev = card.get("date")
        year = ev.year if ev else None
        return gen.get_output(f"ext_{year if year else 'undated'}.tf")

    def _minted_res_name(self, out: str) -> str:
        import re
        m = re.search(r'resource "geni_profile" "([^"]+)"', out)
        assert m is not None, "no geni_profile emitted"
        return m.group(1)

    def _doc_description(self, out: str) -> str:
        """The proof geni_document's description heredoc (not the profile about)."""
        import re
        m = re.search(r'description\s*=\s*<<-EOT(.*?)\n\s*EOT', out, re.DOTALL)
        assert m is not None, "no document description emitted"
        return m.group(1)

    def _birth_block(self, out: str) -> str:
        import re
        m = re.search(r'birth\s*=\s*\{(.*?)\n  \}', out, re.DOTALL)
        return re.sub(r" +", " ", m.group(1)) if m else ""  # collapse column alignment

    def test_birth_date_full_emits_exact_birth_event(self):
        out = self._out(date=EventDate(1943, Month.MAY, 9),
                        birth_date=EventDate(1909, Month.NOVEMBER, 3))
        b = self._birth_block(out)
        self.assertIn("year = 1909", b)
        self.assertIn("month = 11", b)
        self.assertIn("day = 3", b)
        self.assertNotIn("circa", b)          # a full stated date is exact

    def test_birth_date_year_only_is_circa(self):
        out = self._out(date=EventDate(1943, Month.MAY, 9),
                        birth_date=EventDate(1923))
        b = self._birth_block(out)
        self.assertIn("year = 1923", b)
        self.assertIn("circa = true", b)      # year-only → circa (matching aid)
        self.assertNotIn("month", b)

    def test_scan_file_list_emits_one_document_per_scan(self):
        import re
        out = self._out(date=EventDate(1945, Month.MAY, 9),
                        scan_file=["scans/pamyat_prikaz.jpg",
                                   "scans/pamyat_nagr1.jpg"])
        docs = re.findall(r'resource "geni_document" "([^"]+)"', out)
        self.assertEqual(len(docs), 2)               # one doc per scan
        self.assertEqual(len(set(docs)), 2)          # unique res_names
        self.assertEqual(out.count("filebase64("), 2)
        self.assertIn("pamyat_prikaz.jpg", out)
        self.assertIn("pamyat_nagr1.jpg", out)
        prof = self._minted_res_name(out)
        self.assertEqual(out.count(f"geni_profile.{prof}.id"), 2)  # both link the one profile
        self.assertEqual(out.count('resource "geni_profile"'), 1)  # still ONE profile

    def test_single_scan_file_still_one_document(self):
        import re
        out = self._out(date=EventDate(1945, Month.MAY, 9),
                        scan_file="scans/pamyat_one.jpg")
        self.assertEqual(len(re.findall(r'resource "geni_document"', out)), 1)
        self.assertIn("filebase64(", out)

    def test_label_is_military(self):
        out = self._out(date=EventDate(1943, Month.MAY, 9))
        self.assertIn('"Military"', out)

    def test_profile_res_name_routes_through_ext_pn(self):
        out = self._out(date=EventDate(1943, Month.MAY, 9))
        self.assertIn("ext_pn", self._minted_res_name(out))

    def test_draft_and_feat_fields_render_in_description(self):
        out = self._out(
            date=EventDate(1943, Month.MAY, 9),
            draft_board="Глухоманский РВК",
            draft_date=EventDate(1941, Month.JUNE, 23),
            feat_date=EventDate(1943, Month.AUGUST, 5),
        )
        desc = self._doc_description(out)
        self.assertIn("Военкомат: Глухоманский РВК", desc)
        self.assertIn("Дата призыва: 23.6.1941", desc)
        self.assertIn("Дата подвига: 5.8.1943", desc)

    def test_draft_and_feat_fields_omitted_when_unset(self):
        out = self._out(date=EventDate(1943, Month.MAY, 9))
        self.assertNotIn("Военкомат:", out)
        self.assertNotIn("Дата призыва:", out)
        self.assertNotIn("Дата подвига:", out)

    def test_award_fields_render_in_description(self):
        out = self._out(
            date=EventDate(1943, Month.MAY, 9),
            document_type=WwiiDocumentType.NAGRADNOY_LIST,
            award="Орден Красной Звезды",
            award_number="45/н",
        )
        self.assertIn("Награда: Орден Красной Звезды", out)
        self.assertIn("Номер награждения: 45/н", out)

    def test_fatal_casualty_emits_death_event(self):
        out = self._out(date=EventDate(1943, Month.MAY, 9),
                        casualty_reason="убит")
        self.assertIn("death = {", out)
        self.assertIn('cause_of_death = "убит"', out)
        self.assertIn("year  = 1943", out)


class TestEventDate(unittest.TestCase):
    def test_point_date(self):
        e = EventDate(1888, Month.OCTOBER, 10)
        self.assertEqual((e.year, e.month, e.day), (1888, Month.OCTOBER, 10))
        self.assertFalse(e.has_range)
        self.assertIsNone(e.date_range)

    def test_range_auto_between(self):
        e = EventDate(1914, Month.NOVEMBER, 21, day_end=23, month_end=Month.DECEMBER)
        self.assertTrue(e.has_range)
        self.assertEqual(e.date_range, "between")  # auto when an end bound is set

    def test_stored_on_record(self):
        r = wwi_record(person("Иван", "Васильевъ", name_modern_orth="Иван"),
                       source_url="https://gwar.mil.ru/heroes/x/",
                       date=EventDate(1915, Month.AUGUST, 9))
        self.assertEqual(r.date.year, 1915)
        self.assertEqual(r.event_year, 1915)        # start-date property
        self.assertEqual(r.event_month, Month.AUGUST)


if __name__ == "__main__":
    unittest.main()
