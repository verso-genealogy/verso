import re
from verso.ru.domain import person
from verso.ru.dsl.records.name_lists import name_list_records, listed_person
from verso.ru.targets.geni.translator.generator import TerraformGenerator


def _emit(**kw):
    r = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(512, person("Домна", "Лукинична", "Телятникова"), age=66),
        listed_person(516, person("Савва", "Фомич", "Телятников"), age=44),
        document_type="Список избирателей на выборах в Учредительное собрание",
        **kw,
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    return "".join(gen._outputs.values())


def test_emits_one_profile_per_entry():
    tf = _emit()
    assert tf.count('resource "geni_profile"') == 2


def test_profile_has_circa_birth_year_minus_age():
    tf = _emit()
    # Домна: 1917 − 66 = 1851, circa
    m = re.search(r'geni_profile.*?domna.*?birth\s*=\s*\{.*?year\s*=\s*(\d{4})',
                  tf, re.S | re.I)
    assert m and m.group(1) == "1851"
    assert "circa = true" in tf


def test_about_block_matches_metric_book_shape():
    # Bold `<strong>{document_type} {village} {year}:</strong> № {number}`
    # header + `Возраст:` fact line, mirroring МК / census about blocks.
    tf = _emit()
    assert (
        "<strong>Список избирателей на выборах в Учредительное собрание "
        "Маниловка 1917:</strong> № 512"
    ) in tf
    assert "Возраст: 66" in tf
    # The old free-form "Место:" line is gone.
    assert "Место:" not in tf


def test_about_comment_uses_komentarij_iz_genitive_section():
    r = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(431, person("Иван", "Тихонович", "Телятников"), age=40,
                      comment="в списке 30 — ошибка"),
        document_type="Список избирателей",
        document_type_genitive="Списка избирателей",
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    # Genitive label + year in the comment header, comment on a `>` line.
    assert "Комментарий из Списка избирателей 1917 года:" in tf
    assert ">в списке 30 — ошибка" in tf


def test_about_comment_genitive_falls_back_to_document_type():
    r = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(1, person("Иван", "Иванович", "Телятников"), age=40,
                      comment="note"),
        document_type="Список",  # no genitive → falls back to document_type
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    assert "Комментарий из Список 1917 года:" in tf


def test_about_includes_fio_v_dokumente_as_written():
    # As-written полуотчество spelling preserved from the person's orig fields,
    # even though the profile name canonicalizes the patronymic.
    r = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(512, person("Домна", "Лукина", "Телятникова"), age=66),
        document_type="Список избирателей",
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    # Surname-first (Фамилия Имя Отчество) matches the source order + «ФИО» label.
    assert ">ФИО в документе: Телятникова Домна Лукина" in tf


def test_age_optional_no_birth_no_vozrast_line():
    # age omitted → no birth event, no «Возраст:» line, but the profile + doc
    # (with «ФИО в документе») are still emitted.
    r = name_list_records(
        "ГАТО", "F", "I", "C", "Горюхино", 1917,
        listed_person(418, person("Прохор", "Гаврилов", "Ладаев")),
        document_type="Список избирателей",
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    assert tf.count('resource "geni_profile"') == 1
    assert "birth = {" not in tf
    assert "Возраст:" not in tf
    assert ">ФИО в документе: Ладаев Прохор Гаврилов" in tf  # as-written orig patronymic
    # Roster line carries no "— N лет" suffix (patronymic canonicalizes to Гавриилович).
    assert "418. Прохор Гаврилович Ладаев\n" in tf


def test_emits_one_shared_document_with_all_profiles():
    tf = _emit()
    assert tf.count('resource "geni_document"') == 1
    doc = tf[tf.index('resource "geni_document"'):]
    assert "domna" in doc.lower() and "savva" in doc.lower()  # both profiles listed


def test_document_labels_other_and_text_roster():
    tf = _emit()
    assert '"Other"' in tf
    assert "512" in tf and "516" in tf                  # № in the text roster
    assert "Список избирателей" in tf                    # document_type in title/desc


def test_document_text_has_census_style_header():
    tf = _emit()
    doc = tf[tf.index('resource "geni_document"'):]
    text = doc[doc.index("text        = <<-EOT"):]
    # The text body leads with the title + archive coordinates (like census),
    # a `---` separator, then the roster.
    assert "Список избирателей на выборах в Учредительное собрание, Маниловка 1917" in text
    assert "Архив: ГАРО" in text
    assert "Фонд: F" in text
    assert "Опись: I" in text
    assert "Дело: C" in text
    assert "---" in text
    assert "512." in text and "516." in text  # roster entries after the header


def test_scan_file_switches_document_body_to_file():
    tf = _emit(scan_file="scans/list.jpg")
    assert 'filebase64("${path.module}/scans/list.jpg")' in tf
    # ExactlyOneOf: text heredoc must be dropped when file is present
    doc = tf[tf.index('resource "geni_document"'):]
    assert "text        = <<-EOT" not in doc


def test_source_url_without_scan_drops_text():
    tf = _emit(source_url="https://example.org/list")
    doc = tf[tf.index('resource "geni_document"'):]
    assert 'source_url   = "https://example.org/list"' in doc
    # ExactlyOneOf: text heredoc must be dropped when source_url is present
    assert "text        = <<-EOT" not in doc


def test_all_unreviewed_emits_nothing():
    r = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(1, person("Иван", "Иванович", "Телятников"), age=41,
                      reviewed=False),
        document_type="Список",
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    assert 'resource "geni_profile"' not in tf
    assert 'resource "geni_document"' not in tf


def test_district_disambiguates_document_res_name():
    gen = TerraformGenerator()
    r1 = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(512, person("Домна", "Лукинична", "Телятникова"), age=66),
        document_type="Список избирателей",
        district="1-й участок",
    )
    r2 = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(516, person("Савва", "Фомич", "Телятников"), age=44),
        document_type="Список избирателей",
        district="2-й участок",
    )
    gen.add_name_list_records(r1)
    gen.add_name_list_records(r2)
    tf = "".join(gen._outputs.values())
    names = re.findall(r'resource "geni_document" "([^"]+)"', tf)
    assert len(names) == 2
    assert names[0] != names[1]


def test_nonnumeric_age_mints_profile_without_birth():
    r = name_list_records(
        "ГАРО", "F", "I", "C", "Маниловка", 1917,
        listed_person(1, person("Иван", "Иванович", "Телятников"), age="?"),
        document_type="Список",
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    assert tf.count('resource "geni_profile"') == 1
    prof = tf[tf.index('resource "geni_profile"'):tf.index('resource "geni_document"')]
    assert "birth = {" not in prof


def test_about_carries_the_sheet_when_page_is_used():
    from verso.ru.domain import page
    r = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        *page("7", listed_person(91, person("Осип", "Пахомов", "Бечков"))),
        document_type="Список избирателей",
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    assert "Лист: 7" in tf


def test_about_omits_the_sheet_line_without_page():
    tf = _emit()
    assert "Лист:" not in tf


def test_roster_line_carries_the_sheet():
    from verso.ru.domain import page
    r = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        *page("7", listed_person(91, person("Осип", "Пахомов", "Бечков"))),
        document_type="Список избирателей",
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    tf = "".join(gen._outputs.values())
    # The roster prints the canonical profile name (Осип → Иосиф); the
    # as-written spelling lives in the about block's «ФИО в документе» line.
    assert "91. Иосиф Пахомович Бечков (л. 7)" in tf


def test_unreviewed_entries_emit_nothing():
    r = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        listed_person(91, person("Пахом", "Лукин", "Бечков")),
        listed_person(92, person("Ульяна", "Иванова", "Бечкова")),
        document_type="Список избирателей",
        reviewed=False,
    )
    gen = TerraformGenerator()
    gen.add_name_list_records(r)
    assert "".join(gen._outputs.values()) == ""
