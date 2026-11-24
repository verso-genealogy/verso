"""A facts persona is named by its id in the records JSON (rule r1, `verso.core.records.ids`).

One id for `facts.jsonl`, the records export and a Verso link — and, unlike the
positional `<file>#<entry>` it replaced, one that no record inserted or held
elsewhere can move. On a scratch copy of the Verso fixture's village.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import village_fixture
from verso.core.pipeline import records
from verso.core.pipeline.records import export_village
from verso.ru.dsl.records.divorces import DivorceRecords
from verso.ru.facts.model import Assertion, AssertionSet, DivorcedOn, FactDate, MarriedOn, Record, Relational
from verso.ru.facts.projection import LooseIndex, consolidated_identity
from verso.ru.pipeline.facts import consolidated_facts
from verso.ru.pipeline.translate import translate_village

# A reviewed roll and burial (the fixture's are held), a list and a card: every kind
# the facts read.
EXTRA = '''\
from calendar import Month

from verso.ru.dsl import Gender, person
from verso.ru.dsl import CensusRole, census_records, household, member
from verso.ru.dsl import death, death_records
from verso.ru.dsl import divorce, divorce_records
from verso.ru.dsl import Relationship, relative
from verso.ru.dsl import external_source_records, wwi_record
from verso.ru.dsl import listed_person, name_list_records

manilovka_census_1901 = census_records(
    "ГА Глуповской области", "5", "1", "20", "Маниловка", 1901,
    household("1",
              member(1, person("Петръ", "Ивановъ", "Примеровъ"), CensusRole.HEAD, age=45),
              member(2, person("Анна", "Петрова"), CensusRole.WIFE, ref_member=1, age=40)),
    household("2",
              member(1, person("Сергій", "Косьминъ", "Опискинъ"), CensusRole.HEAD, age=50),
              member(2, person("Марія"), CensusRole.DAUGHTER, ref_member=1, age=20)),
    household("3",
              member(1, person("Іоаннъ", "Петровъ", "Примеровъ"), CensusRole.HEAD, age=30)))
manilovka_deaths_1901 = death_records(
    "ГАРО", "1", "2", "3", "Хлестаковка", "Покровская", 1901,
    death(3, Gender.FEMALE, 9, 11, Month.MARCH, Month.MARCH, deceased=person("Ульяна", "Петрова"),
          relatives=[relative(person("Ѳедоръ", "Ивановъ", "Заметкинъ"), Relationship.HUSBAND)]))
manilovka_name_lists_1901 = name_list_records(
    "ГАТО", "1", "1", "1", "Маниловка", 1901, listed_person(1, person("Петръ", "Ивановъ")),
    document_type="Список")
manilovka_external_sources_1901 = external_source_records(
    "Маниловка", wwi_record(person("Василій"), source_url="https://gwar.mil.ru/heroes/chelovek_plen1/"))
# Three acts of divorce: one numbered, two the book left unnumbered — the second of them with words where
# the archive's дело is expected.
manilovka_divorces_1901 = divorce_records(
    "ГАРО", "9", "1", "4", "Маниловка", "", 1901,
    divorce(7, 3, Month.JULY, husband=person("Иванъ", "Петровъ", "Справкинъ"), wife=person("Анна", "Иванова"),
            husband_age=30, wife_age=27, marriage_date="24 февраля 1895"),
    divorce(None, 5, Month.JULY, husband=person("Павелъ", "Ильинъ"), wife=person("Ольга", "Петрова")),
    divorce(None, 9, Month.JULY, husband=person("Сергій", "Ильинъ"), wife=person("Марія", "Петрова"),
            case="судъ 2-го участка"))
'''
ROLL = "manilovka_extra_1901.py"
MARRIAGES_1899 = "1899/manilovka_marriages_1899.py"
# A wedding of 1899 for the fixture's January section, in front of its first.
INSERTED = '''                    marriage(30, 5,
                             groom=person("Павел", "Ильин", "Справкин"), groom_age=20,
                             bride=person("Ольга", "Петрова", "Пробникова"), bride_age=19),
'''


@pytest.fixture
def village(tmp_path: Path) -> Path:
    manilovka = village_fixture.root(tmp_path) / "Маниловка"
    (manilovka / "1901").mkdir()
    (manilovka / "1901" / ROLL).write_text(EXTRA, encoding="utf-8")
    return manilovka


def _facts(village: Path) -> AssertionSet:
    facts, _, _ = consolidated_facts(village)
    return facts


def _personas(facts: AssertionSet, source_file: str | None = None) -> list[str]:
    """Every persona the facts name — subjects and the others of a relation — in order."""
    out: list[str] = []
    for a in facts:
        if source_file is not None and a.cite.source_file != source_file:
            continue
        out.append(a.subject.id)
        if isinstance(a, Relational):
            out.append(a.other.id)
    return out


def _json_personas(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for d in doc.get("documents", ()):
            for run in d.get("pages", ()):
                for record in run["records"]:
                    found.update(p["id"] for p in record["persons"])
    return found


def test_every_persona_is_a_persona_of_the_records_json(village: Path, tmp_path: Path):
    facts = _facts(village)
    export_village(village, tmp_path / "records")
    named = set(_personas(facts))
    assert {a.cite.record_kind for a in facts} == {"birth", "marriage", "death", "census", "list",
                                                   "external", "divorce"}
    assert named and all(p.startswith("r1:") for p in named)   # the parish is Хлестаковка
    assert named <= _json_personas(tmp_path / "records"), sorted(named - _json_personas(tmp_path / "records"))


def test_a_record_inserted_in_another_file_moves_no_persona(village: Path):
    """A wedding added to 1899 shifts every later wedding's place in the reading —
    the old id was that place — and none of the 1900 personas."""
    before = _facts(village)
    path = village / MARRIAGES_1899
    text = path.read_text(encoding="utf-8")
    anchor = "    *marriage_month(Month.JANUARY,\n"
    assert anchor in text
    path.write_text(text.replace(anchor, anchor + INSERTED), encoding="utf-8")
    after = _facts(village)

    weddings = "manilovka_marriages_1900.py"
    assert _personas(after, weddings) == _personas(before, weddings)
    places = [{a.cite.entry for a in facts if a.cite.source_file == weddings} for facts in (before, after)]
    assert places[1] == {e + 1 for e in places[0]}, "the insert must stand before them in the reading"


def test_a_household_held_back_moves_no_other_household(village: Path):
    """Holding двор 2 back (`reviewed=False`) takes it out of the reading, and двор 3's
    place with it; its persona stays."""
    before = _facts(village)
    path = village / "1901" / ROLL
    text = path.read_text(encoding="utf-8")
    held = 'ref_member=1, age=20)),'
    assert held in text
    path.write_text(text.replace(held, 'ref_member=1, age=20), reviewed=False),'), encoding="utf-8")
    after = _facts(village)

    def third(facts: AssertionSet) -> list[str]:
        return [p for p in _personas(facts, ROLL) if "/household/3/" in p]

    assert third(after) == third(before) == ["r1:Маниловка/5-1-20/1901/household/3/member1"] * len(third(before))
    assert not [p for p in _personas(after, ROLL) if "/household/2/" in p]
    entries = [{a.cite.entry for a in facts if "/household/3/" in a.subject.id} for facts in (before, after)]
    assert entries[1] == {e - 1 for e in entries[0]}, "the held двор must stand before it in the reading"


def _divorces(facts: AssertionSet) -> list[Assertion]:
    return [a for a in facts if a.cite.record_kind == "divorce"]


def test_the_divorces_are_read_in_the_village_s_one_walk(village: Path):
    """The translator does not read a divorce, so its record sets reach the facts beside the ones it was fed:
    from the same walk, each persona named by the records JSON — an unnumbered act and one with words for
    its дело included."""
    facts, gen, _ = consolidated_facts(village)
    assert not [recs for _, recs in gen.fed_sources if isinstance(recs, DivorceRecords)]
    found = _divorces(facts)
    assert {a.date for a in found if isinstance(a, DivorcedOn)} == {
        FactDate(year=1901, month=7, day=d) for d in (3, 5, 9)}
    assert {a.date for a in found if isinstance(a, MarriedOn)} == {FactDate(year=1895, month=2, day=24)}
    personas = {a.subject.id for a in found}
    assert len(personas) == 6 and all(p.startswith("r1:") and p.endswith(("/husband", "/wife")) for p in personas)
    assert len({p.rsplit("/", 1)[0] for p in personas}) == 3, "three acts, three ids"


def test_the_translation_is_fed_no_divorce_unless_asked(village: Path):
    gen, _ = translate_village(village)
    assert {type(recs).__name__ for _, recs in gen.fed_sources}.isdisjoint({"DivorceRecords"})
    beside: list[tuple[str, object]] = []
    translate_village(village, untranslated=beside)
    assert [(name, type(recs)) for name, recs in beside] == [(ROLL, DivorceRecords)]


def test_the_divorces_are_the_same_read_from_the_records_json(village: Path, tmp_path: Path):
    export_village(village, tmp_path / "rec")
    dsl = [(type(a).__name__, a.subject.id, a.sort_key) for a in _facts(village).sorted()]
    with records.use(tmp_path / "rec"):
        js = [(type(a).__name__, a.subject.id, a.sort_key) for a in _facts(village).sorted()]
    assert [x for x in dsl if "/divorce/" in x[1]], "the divorces are among what is compared"
    assert dsl == js


def test_a_divorce_s_people_are_placed_on_no_canonical(village: Path):
    """No profile is minted for them, so the bridge refuses — and every reader that asks who a persona is
    (the folds, the loose stubs, the name matches) passes a divorce by."""
    facts, gen, slots = consolidated_facts(village)
    key_of = consolidated_identity(gen, slots.object_of)(Record(()))
    loose = LooseIndex(gen, slots, "")
    personas = {a.subject for a in _divorces(facts)}
    assert personas and all(key_of(p) is None and not loose.is_loose(p) for p in personas)


def test_a_divorce_is_dumped_and_explained_whatever_its_id_holds(village: Path, tmp_path: Path):
    from verso.ru.cli.facts import dump, explain
    facts = _facts(village)
    assert dump(facts, tmp_path / "facts.jsonl") == len(facts)
    lines = (tmp_path / "facts.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum('"DivorcedOn"' in line for line in lines) == 6
    assert "DivorcedOn" in explain(facts, "1901:7")


def test_the_bridge_counts_a_kind_the_tree_does_not_publish_apart(village: Path):
    """A divorce's people are refused because their record is of a kind no profile is minted for — known, like the
    причт, and no defect of the bridge: told which kinds those are, the reach counts them apart."""
    from verso.ru.cli.facts import identity_report
    from verso.ru.facts.checks.reach import identity_reach
    from verso.ru.pipeline.facts import unpublished_kinds

    assert unpublished_kinds() == {"divorce"}
    facts, gen, slots = consolidated_facts(village)
    strict = identity_reach(facts, gen, slots)
    reach = identity_reach(facts, gen, slots, unpublished=unpublished_kinds())
    assert strict.unpublished == {} and reach.unpublished == {"divorce": 6}
    assert strict.refused_beyond_clergy - reach.refused_beyond_clergy == 6
    assert reach.refused == strict.refused and reach.total == strict.total
    report, code = identity_report(facts, gen, slots)
    assert code == 0
    assert "    из них вид без профилей (divorce):   6" in report.splitlines()


def test_a_village_without_such_a_kind_reads_as_before(tmp_path: Path):
    from verso.ru.cli.facts import identity_report
    from verso.ru.facts.checks.reach import identity_reach
    from verso.ru.pipeline.facts import unpublished_kinds

    facts, gen, slots = consolidated_facts(village_fixture.root(tmp_path) / "Маниловка")
    reach = identity_reach(facts, gen, slots, unpublished=unpublished_kinds())
    assert reach.unpublished == {}
    assert reach.refused_beyond_clergy == identity_reach(facts, gen, slots).refused_beyond_clergy
    assert "вид без профилей" not in identity_report(facts, gen, slots)[0]


def test_the_snapshot_holds_the_bridge_to_no_refusal_beyond_the_known(village: Path):
    """The committed count is the reach told which kinds have no profiles: six refusals fewer than the strict one."""
    from verso.ru.cli.facts_snapshot import findings_snapshot
    from verso.ru.facts.checks.reach import identity_reach

    strict = identity_reach(*consolidated_facts(village)).refused_beyond_clergy
    rows = dict(line.split("\t", 1) for line in findings_snapshot(village).splitlines() if "\t" in line)
    assert rows["identity-refused-beyond-clergy"] == f"{strict - 6}\t-"


def test_the_cli_reads_a_divorce_as_a_kind_of_its_own(village: Path, capsys: pytest.CaptureFixture[str]):
    """`verso facts --kind divorce` with `--why`, `--basis-census` and `--dump`: one kind's assertions, read
    without a translation — from the record sets the translator is not fed."""
    from verso.ru.cli import facts as cli

    loaded = cli.load(village, "divorce")
    assert {a.cite.record_kind for a in loaded} == {"divorce"} and len({a.subject for a in loaded}) == 6
    assert {a.subject.id for a in loaded} == {a.subject.id for a in _divorces(_facts(village))}

    assert cli.main(["--village", str(village), "--kind", "divorce", "--why", "1901:7"]) == 0
    assert "DivorcedOn" in capsys.readouterr().out
    assert cli.main(["--village", str(village), "--kind", "divorce", "--basis-census"]) == 0
    assert capsys.readouterr().out.strip()
    assert cli.main(["--village", str(village), "--kind", "divorce", "--dump"]) == 0
    assert sum('"DivorcedOn"' in line for line in (village / "facts.jsonl").read_text(encoding="utf-8").splitlines()) == 6
    assert cli.main(["--village", str(village), "--kind", "divorce"]) == 0        # no pair to report, and no crash


HELD = '''\
from calendar import Month

from verso.ru.dsl import divorce, divorce_records, page, person

manilovka_divorces_1902 = divorce_records(
    "ГАРО", "9", "1", "5", "Маниловка", "", 1902,
    divorce(1, 3, Month.JULY, husband=person("Иванъ", "Петровъ"), wife=person("Анна", "Иванова")),
    divorce(2, 4, Month.JULY, husband=person("Павелъ", "Ильинъ"), wife=person("Ольга", "Петрова"), reviewed=False),
    *page("7", divorce(3, 5, Month.JULY, husband=person("Сергій", "Ильинъ"), wife=person("Марія", "Петрова")),
          reviewed=False))
'''


def test_a_held_divorce_asserts_nothing_from_the_dsl_or_from_the_records_json(village: Path, tmp_path: Path):
    """`reviewed=False` on the act or on its лист: the village's reading holds no claim of it, whichever of the two
    it is read from."""
    (village / "1902").mkdir()
    (village / "1902" / "manilovka_divorces_1902.py").write_text(HELD, encoding="utf-8")

    def of_1902(facts: AssertionSet) -> set[str]:
        return {a.cite.record_num for a in _divorces(facts) if a.cite.year == 1902}

    assert of_1902(_facts(village)) == {"1"}
    export_village(village, tmp_path / "rec")
    with records.use(tmp_path / "rec"):
        assert of_1902(_facts(village)) == {"1"}
