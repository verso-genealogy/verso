"""The review ratchet on the toy plugin's dialect: the core's mechanism, the plugin's
calls."""
from __future__ import annotations

from types import ModuleType

import pytest

from tests.core.toy import TOY_CALLS
from verso.core import ratchet
from verso.core.ratchet import CallDialect, RatchetError, RecordCall
from verso.core.targets.geni.held import ON_GENI

pytestmark = pytest.mark.usefixtures("toy_workspace")

SOURCE = '''\
from tests.core.toy import note, notes, who

BOOK = "1-2-3"
book = notes("V", "1", "2", "3", 1850,
    note(3, who("Анна"), page="5"),
    note(4, who("Пётр"), reviewed=False),
)
'''


def _module(source: str) -> ModuleType:
    module = ModuleType("toy_dsl")
    exec(compile(source, "toy_dsl.py", "exec"), vars(module))
    return module


def test_a_toy_records_print_and_label():
    prints = ratchet.record_prints(SOURCE)
    assert [(p.func, p.line, p.label) for p in prints] == [("note", 5, "note 3, p. 5"), ("note", 6, "note 4")]
    (unnumbered,) = ratchet.record_prints('note(who("Иван"))\n')
    assert unnumbered.label == "note"
    (by_keyword,) = ratchet.record_prints('page("7", note(number=8, person=who("Иван")))\n')
    assert by_keyword.label == "note 8, p. 7"


def test_a_comment_does_not_move_a_print_and_a_number_does():
    before = [p.fingerprint for p in ratchet.record_prints(SOURCE)]
    assert [p.fingerprint for p in ratchet.record_prints(SOURCE.replace("1850,", "1850,  # a comment"))] == before
    assert [p.fingerprint for p in ratchet.record_prints(SOURCE.replace("reviewed=False", "reviewed=True"))] == before
    moved = [p.fingerprint for p in ratchet.record_prints(SOURCE.replace("note(4", "note(5"))]
    assert moved[0] == before[0] and moved[1] != before[1]
    assert [p.fingerprint for p in ratchet.record_prints(SOURCE.replace('"1-2-3"', '"1-2-4"'))] != before


def test_the_dialect_is_the_one_given_else_the_plugins():
    other = CallDialect(calls={"who": RecordCall("Who")}, sexes={}, reading_flags=frozenset())
    assert [p.func for p in ratchet.record_prints(SOURCE, other)] == ["who", "who"]
    assert ratchet.record_prints(SOURCE) == ratchet.record_prints(SOURCE, TOY_CALLS)


def test_admit_marks_a_listed_record_on_geni():
    module = _module(SOURCE)
    pairs = ratchet.pair(SOURCE, module, where="1850/v_notes_1850.py")
    assert [type(r).__name__ for r, _ in pairs] == ["Note", "Note"]
    assert ratchet.runtime_records(vars(module)) == [r for r, _ in pairs]
    assert ratchet.admit(pairs, [pairs[1][1].fingerprint, pairs[0][1].fingerprint]) == 1
    assert getattr(pairs[1][0], ON_GENI) is True
    assert not hasattr(pairs[0][0], ON_GENI)      # reviewed: it needs no line


def test_pair_refuses_a_call_paired_with_another_kind():
    wrong = CallDialect(calls={"note": RecordCall("Other", number="number")}, sexes={}, reading_flags=frozenset())
    with pytest.raises(RatchetError, match=r"^f\.py:5: note\(\) paired with a Note$"):
        ratchet.pair(SOURCE, _module(SOURCE), where="f.py", calls=wrong)


def test_the_flag_and_the_leaf_are_the_cores_conventions():
    """The review flag and the лист are read on the records too (`unreviewed`, the records
    JSON's review states and page runs): a dialect cannot rename them in the source alone."""
    from dataclasses import fields
    assert {f.name for f in fields(CallDialect)} == {"calls", "page_label", "gender", "sexes", "reading_flags"}
    assert (ratchet.FLAG, ratchet.PAGE) == ("reviewed", "page")


def test_core_page_label_is_neutral():
    """The leaf's word is the plugin's: the core's default is neutral."""
    assert CallDialect(calls={}).page_label == "p."


def test_core_header_has_no_cyrillic():
    from verso.core.targets.geni.held import HEADER
    assert not any("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in HEADER)


def test_strike_keeps_the_files_header(tmp_path):
    """A list keeps the header it was written with: a corpus's lists keep theirs, byte for byte."""
    header = "# Список — первая строка\n# вторая\n# файл\tотпечаток\tзапись\n"
    rows = "a.py\t1111\tnote 1\na.py\t2222\tnote 2\n"
    (tmp_path / ratchet.LIST_FILE).write_text(header + rows, encoding="utf-8")
    ratchet.strike(tmp_path, "a.py", "1111")
    assert (tmp_path / ratchet.LIST_FILE).read_text(encoding="utf-8") == header + "a.py\t2222\tnote 2\n"


def test_a_new_list_gets_the_cores_header(tmp_path):
    from verso.core.targets.geni.held import HEADER
    assert ratchet.read_header(tmp_path / ratchet.LIST_FILE) is None
    entries = [ratchet.Entry("a.py", "1111", "note 1")]
    text = ratchet.format_list(entries, ratchet.read_header(tmp_path / ratchet.LIST_FILE))
    assert text == HEADER + "a.py\t1111\tnote 1\n"
