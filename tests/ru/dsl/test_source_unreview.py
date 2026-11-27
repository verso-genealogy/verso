"""`source.apply(…, unreview=True)`: a proofread record of a DSL file marked unreviewed again — `reviewed=False` on its
own call, the other records and the ratchet left alone. On the invented book of tests/fixtures/mini (its people,
parish and record numbers made up)."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.ru.dsl import source

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "mini" / "root" / "Маниловка"
BOOK = ROOT / "1900" / "manilovka_births_1900.py"
ROLL = ROOT / "1858" / "manilovka_census_1858.py"


def _records(text: str) -> list[source.Record]:
    return source.find_records(text)


def _reviewed(text: str) -> list[bool]:
    return [not r.pending for r in _records(text)]


def test_unreview_writes_reviewed_false():
    text = BOOK.read_text(encoding="utf-8")
    ordinal = _reviewed(text).index(True)                       # the book's proofread record (Агафья)
    rec = _records(text)[ordinal]
    out = source.apply(text, ordinal, rec.sha, unreview=True)
    assert not _reviewed(out)[ordinal]
    lines = out.splitlines()
    assert "reviewed=False" in lines[next(i for i, line in enumerate(lines) if "Агафья" in line) - 1]


def test_unreview_keeps_other_records():
    text = BOOK.read_text(encoding="utf-8")
    before = _reviewed(text)
    ordinal = before.index(True)
    out = source.apply(text, ordinal, _records(text)[ordinal].sha, unreview=True)
    after = _reviewed(out)
    assert [a for i, a in enumerate(after) if i != ordinal] == [b for i, b in enumerate(before) if i != ordinal]
    assert len(out.splitlines()) == len(text.splitlines())


def test_unreview_of_an_unreviewed_record_is_a_no_op():
    text = BOOK.read_text(encoding="utf-8")
    ordinal = _reviewed(text).index(False)
    assert source.apply(text, ordinal, _records(text)[ordinal].sha, unreview=True) == text


def test_unreview_with_an_edit():
    text = BOOK.read_text(encoding="utf-8")
    ordinal = _reviewed(text).index(True)
    ops = [{"op": "set", "path": ["b_day"], "value": {"kind": "int", "value": 7}}]
    out = source.apply(text, ordinal, _records(text)[ordinal].sha, ops, unreview=True)
    assert _records(out)[ordinal].day == 7 and not _reviewed(out)[ordinal]


def test_review_and_unreview_at_once_is_refused():
    text = BOOK.read_text(encoding="utf-8")
    ordinal = _reviewed(text).index(False)
    with pytest.raises(source.EditError):
        source.apply(text, ordinal, _records(text)[ordinal].sha, mark_reviewed=True, unreview=True)


def _read_one(text: str) -> tuple[str, int]:
    """`text` with its first household read (an explicit `reviewed=True` under the roll's `reviewed=False`)."""
    ordinal = _reviewed(text).index(False)
    return source.apply(text, ordinal, _records(text)[ordinal].sha, mark_reviewed=True), ordinal


def test_unreview_under_a_held_roll_drops_the_records_own_flag():
    """A household read under a roll that holds `reviewed=False` (a лист's `page(…, reviewed=False)` is held the same
    way, `_holders`): unreviewed again, its own `True` goes — no redundant `reviewed=False` of its own (RVR001), the
    roll holds it as before."""
    text = ROLL.read_text(encoding="utf-8")
    read, ordinal = _read_one(text)
    assert _reviewed(read)[ordinal] and "reviewed=True" in read
    out = source.apply(read, ordinal, _records(read)[ordinal].sha, unreview=True)
    assert not _reviewed(out)[ordinal]
    assert out == text                                     # back as it was: the roll's flag alone
    assert _records(out)[ordinal].flag == "file"


def test_ops_on_the_flag_with_unreview_are_refused():
    text = BOOK.read_text(encoding="utf-8")
    ordinal = _reviewed(text).index(True)
    with pytest.raises(source.EditError):
        source.apply(text, ordinal, _records(text)[ordinal].sha, [{"op": "delete", "path": ["reviewed"]}],
                     unreview=True)
