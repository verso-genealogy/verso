"""A village's `[sheets]` refused in the interface's language: the key and the file are named as
written, the words around them are the catalog's."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_cli_language import english_but
from verso.core import i18n
from verso.core.corpus_data import CorpusDataError
from verso.ru.importers.validation import _check_sheets


@pytest.mark.parametrize("sheets", [
    {"site": "x", "nonsense": 1},
    {"site": 5},
    {"site": "x", "header_rows": "two"},
])
def test_a_refused_sheet_reads_in_english(sheets):
    with i18n.use("en"), pytest.raises(CorpusDataError) as e:
        _check_sheets(Path("Заманиловка/village.toml"), sheets)
    assert english_but(str(e.value), "Заманиловка") == ""
    assert "sheets." in str(e.value)


def test_a_refused_sheet_reads_in_russian():
    with i18n.use("ru"), pytest.raises(CorpusDataError) as e:
        _check_sheets(Path("v/village.toml"), {"site": "x", "nonsense": 1})
    assert str(e.value) == "v/village.toml: неизвестный ключ «sheets.nonsense»"
